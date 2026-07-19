#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_component.h"
#include "esphome/core/application.h"
#include "esphome/core/log.h"

#include <cinttypes>
#include <cstring>
#include <algorithm>
#include <nvs.h>
#include <esp_random.h>

#include <app/server/Server.h>
#include <crypto/CHIPCryptoPAL.h>
#if CHIP_DEVICE_CONFIG_ENABLE_THREAD
#include <platform/ESP32/OpenthreadLauncher.h>
#endif
#include <lib/support/Base64.h>
#include <setup_payload/ManualSetupPayloadGenerator.h>
#include <setup_payload/QRCodeSetupPayloadGenerator.h>
#include <setup_payload/SetupPayload.h>

static const char *const TAG = "matter";

// Keys in the "chip-factory" NVS namespace, matching CHIP's ESP32Config key names.
static constexpr const char *NVS_NAMESPACE           = "chip-factory";
static constexpr const char *NVS_KEY_DISCRIMINATOR   = "discriminator";
static constexpr const char *NVS_KEY_PASSCODE        = "pin-code";
static constexpr const char *NVS_KEY_ITERATION_COUNT = "iteration-count";
static constexpr const char *NVS_KEY_SALT            = "salt";
static constexpr const char *NVS_KEY_VERIFIER        = "verifier";

static constexpr uint32_t SPAKE2P_ITERATION_COUNT = 1000;
static constexpr size_t   SPAKE2P_SALT_LENGTH     = 32;

static bool is_valid_passcode(uint32_t pin) {
  if (pin == 0 || pin > 99999998)
    return false;
  static constexpr uint32_t FORBIDDEN[] = {
      11111111, 22222222, 33333333, 44444444, 55555555,
      66666666, 77777777, 88888888, 99999999, 12345678, 87654321,
  };
  for (uint32_t f : FORBIDDEN) {
    if (pin == f)
      return false;
  }
  return true;
}

// Loads existing commissioning data from NVS, or generates random values and stores them.
// The EXAMPLE_COMMISSIONABLE_DATA_PROVIDER reads these same NVS keys on every boot,
// so whatever we write here becomes the device's commissioning identity.
static bool load_or_generate_commissioning_data(uint16_t &discriminator, uint32_t &passcode) {
  nvs_handle_t handle;
  if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
    ESP_LOGE(TAG, "Failed to open NVS namespace '%s'", NVS_NAMESPACE);
    return false;
  }

  uint32_t stored_discriminator, stored_passcode;
  bool already_provisioned = (nvs_get_u32(handle, NVS_KEY_DISCRIMINATOR, &stored_discriminator) == ESP_OK &&
                              nvs_get_u32(handle, NVS_KEY_PASSCODE, &stored_passcode) == ESP_OK);
  if (already_provisioned) {
    discriminator = (uint16_t) stored_discriminator;
    passcode = stored_passcode;
    nvs_close(handle);
    return true;
  }

#ifdef MATTER_DISCRIMINATOR
  discriminator = MATTER_DISCRIMINATOR;
#else
  discriminator = (uint16_t)(esp_random() & 0x0FFFu);
#endif

#ifdef MATTER_PASSCODE
  passcode = MATTER_PASSCODE;
#else
  do {
    passcode = (esp_random() % 99999998u) + 1u;
  } while (!is_valid_passcode(passcode));
#endif

  // Generate random salt using the ESP32 hardware RNG.
  uint8_t salt[SPAKE2P_SALT_LENGTH];
  for (size_t i = 0; i < SPAKE2P_SALT_LENGTH; i += sizeof(uint32_t)) {
    uint32_t r = esp_random();
    size_t bytes = std::min(sizeof(uint32_t), SPAKE2P_SALT_LENGTH - i);
    memcpy(salt + i, &r, bytes);
  }

  // Compute the Spake2p verifier from the passcode + salt + iteration count.
  // Storing the verifier (rather than the raw passcode) means future boots don't need
  // to recompute it, and the factory partition holds a stronger derived secret.
  chip::Crypto::Spake2pVerifier verifier;
  if (verifier.Generate(SPAKE2P_ITERATION_COUNT, chip::ByteSpan(salt, SPAKE2P_SALT_LENGTH), passcode) != CHIP_NO_ERROR) {
    ESP_LOGE(TAG, "Failed to generate Spake2p verifier");
    nvs_close(handle);
    return false;
  }
  uint8_t verifier_bytes[chip::Crypto::kSpake2p_VerifierSerialized_Length];
  chip::MutableByteSpan verifier_span(verifier_bytes, sizeof(verifier_bytes));
  if (verifier.Serialize(verifier_span) != CHIP_NO_ERROR) {
    ESP_LOGE(TAG, "Failed to serialize Spake2p verifier");
    nvs_close(handle);
    return false;
  }

  char salt_b64[BASE64_ENCODED_LEN(SPAKE2P_SALT_LENGTH) + 1];
  salt_b64[chip::Base64Encode32(salt, SPAKE2P_SALT_LENGTH, salt_b64)] = '\0';

  char verifier_b64[BASE64_ENCODED_LEN(chip::Crypto::kSpake2p_VerifierSerialized_Length) + 1];
  verifier_b64[chip::Base64Encode32(verifier_bytes, sizeof(verifier_bytes), verifier_b64)] = '\0';

  nvs_set_u32(handle, NVS_KEY_DISCRIMINATOR, discriminator);
  nvs_set_u32(handle, NVS_KEY_PASSCODE, passcode);
  nvs_set_u32(handle, NVS_KEY_ITERATION_COUNT, SPAKE2P_ITERATION_COUNT);
  nvs_set_str(handle, NVS_KEY_SALT, salt_b64);
  nvs_set_str(handle, NVS_KEY_VERIFIER, verifier_b64);
  nvs_commit(handle);
  nvs_close(handle);

  return true;
}

namespace esphome::matter {

static void client_invoke_cb(esp_matter::client::peer_device_t *peer_device,
                              esp_matter::client::request_handle_t *req_handle, void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD)
    return;
  using namespace chip::app::Clusters;
  char cmd_data[48] = "{}";
  if (req_handle->command_path.mClusterId == LevelControl::Id) {
    if (req_handle->command_path.mCommandId == LevelControl::Commands::MoveWithOnOff::Id) {
      uint8_t mode = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(req_handle->request_data));
      snprintf(cmd_data, sizeof(cmd_data),
               "{\"0:U8\": %u, \"1:U8\": 50, \"2:U8\": 0, \"3:U8\": 0}", mode);
    } else {
      // StopWithOnOff: OptionsMask=0, OptionsOverride=0
      strcpy(cmd_data, "{\"0:U8\": 0, \"1:U8\": 0}");
    }
  }
  esp_matter::client::interaction::invoke::send_request(nullptr, peer_device, req_handle->command_path,
                                                        cmd_data, nullptr, nullptr, chip::NullOptional);
}

static void client_group_invoke_cb(uint8_t fabric_index, esp_matter::client::request_handle_t *req_handle,
                                    void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD)
    return;
  using namespace chip::app::Clusters;
  char cmd_data[48] = "{}";
  if (req_handle->command_path.mClusterId == LevelControl::Id) {
    if (req_handle->command_path.mCommandId == LevelControl::Commands::MoveWithOnOff::Id) {
      uint8_t mode = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(req_handle->request_data));
      snprintf(cmd_data, sizeof(cmd_data),
               "{\"0:U8\": %u, \"1:U8\": 50, \"2:U8\": 0, \"3:U8\": 0}", mode);
    } else {
      strcpy(cmd_data, "{\"0:U8\": 0, \"1:U8\": 0}");
    }
  }
  esp_matter::client::interaction::invoke::send_group_request(fabric_index, req_handle->command_path, cmd_data);
}

static void event_callback(const ChipDeviceEvent *event, intptr_t arg) {
  switch (event->Type) {
    case chip::DeviceLayer::DeviceEventType::kInterfaceIpAddressChanged:
      ESP_LOGI(TAG, "Interface IP Address changed");
      break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningComplete:
      ESP_LOGI(TAG, "Commissioning complete");
      break;
    case chip::DeviceLayer::DeviceEventType::kFailSafeTimerExpired:
      ESP_LOGI(TAG, "Commissioning failed, fail safe timer expired");
      break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningSessionStarted:
      ESP_LOGI(TAG, "Commissioning session started");
      break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningSessionStopped:
      ESP_LOGI(TAG, "Commissioning session stopped");
      break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningWindowOpened:
      ESP_LOGI(TAG, "Commissioning window opened");
      break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningWindowClosed:
      ESP_LOGI(TAG, "Commissioning window closed");
      break;
    case chip::DeviceLayer::DeviceEventType::kFabricRemoved:
      ESP_LOGI(TAG, "Fabric removed");
      // TODO: reopen commissioning window?
      break;
    case chip::DeviceLayer::DeviceEventType::kFabricWillBeRemoved:
      ESP_LOGI(TAG, "Fabric will be removed");
      break;
    case chip::DeviceLayer::DeviceEventType::kFabricUpdated:
      ESP_LOGI(TAG, "Fabric is updated");
      break;
    case chip::DeviceLayer::DeviceEventType::kFabricCommitted:
      ESP_LOGI(TAG, "Fabric is committed");
      break;
    default:
      ESP_LOGD(TAG, "Matter event: 0x%04X", event->Type);
      break;
  }
}

void MatterComponent::setup() {
  uint16_t discriminator;
  uint32_t passcode;
  if (!load_or_generate_commissioning_data(discriminator, passcode)) {
    this->mark_failed();
    return;
  }
  this->discriminator_ = discriminator;
  this->passcode_ = passcode;

  // Always update device-name so it stays in sync if the ESPHome device name changes.
  // This is the DN TXT record in _matterc._udp — what controllers show in their UI.
  {
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) == ESP_OK) {
      nvs_set_str(h, "device-name", App.get_name().c_str());
      nvs_commit(h);
      nvs_close(h);
    }
  }

  esp_matter::node::config_t node_config;
  esp_matter::node_t *node = esp_matter::node::create(&node_config, nullptr, nullptr);
  if (node == nullptr) {
    ESP_LOGE(TAG, "Failed to create Matter node");
    this->mark_failed();
    return;
  }

  for (auto &sw : this->on_off_switches_) {
    esp_matter::endpoint::on_off_switch::config_t sw_config;
    esp_matter::endpoint_t *ep =
        esp_matter::endpoint::on_off_switch::create(node, &sw_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create on_off_switch endpoint");
      this->mark_failed();
      return;
    }
    sw.endpoint_id = esp_matter::endpoint::get_id(ep);
    ESP_LOGD(TAG, "On/Off switch endpoint created: id=%u", sw.endpoint_id);
  }

  for (auto &sw : this->dimmer_switches_) {
    esp_matter::endpoint::dimmer_switch::config_t sw_config;
    esp_matter::endpoint_t *ep =
        esp_matter::endpoint::dimmer_switch::create(node, &sw_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create dimmer_switch endpoint");
      this->mark_failed();
      return;
    }
    sw.endpoint_id = esp_matter::endpoint::get_id(ep);
    ESP_LOGD(TAG, "Dimmer switch endpoint created: id=%u", sw.endpoint_id);
  }

  if (!this->on_off_switches_.empty() || !this->dimmer_switches_.empty()) {
    esp_matter::client::set_request_callback(client_invoke_cb, client_group_invoke_cb, nullptr);
  }

#if CHIP_DEVICE_CONFIG_ENABLE_THREAD
  /* Set OpenThread platform config */
  esp_openthread_platform_config_t ot_config = {
    .radio_config = { .radio_mode = RADIO_MODE_NATIVE },
    .host_config  = { .host_connection_mode = HOST_CONNECTION_MODE_NONE },
    .port_config  = { .storage_partition_name = "nvs", .netif_queue_size = 10, .task_queue_size = 10 },
  };
  // TODO:
  //  esp_openthread_platform_config_t ot_config = {
  //      .radio_config = ESP_OPENTHREAD_DEFAULT_RADIO_CONFIG(),
  //      .host_config = ESP_OPENTHREAD_DEFAULT_HOST_CONFIG(),
  //      .port_config = ESP_OPENTHREAD_DEFAULT_PORT_CONFIG(),
  //  };
  set_openthread_platform_config(&ot_config);
#endif

  /* Matter start */
  esp_err_t err = esp_matter::start(event_callback);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to start Matter: %s", esp_err_to_name(err));
    this->mark_failed();
    return;
  } else {
    ESP_LOGD(TAG, "Matter started successfully");
  }

  for (const auto &sw : this->on_off_switches_) {
    uint16_t eid = sw.endpoint_id;
    sw.sensor->add_on_state_callback([eid](bool state) {
      using namespace chip::app::Clusters;
      esp_matter::client::request_handle_t req;
      req.type = esp_matter::client::INVOKE_CMD;
      req.command_path.mClusterId = OnOff::Id;
      req.command_path.mCommandId = state ? OnOff::Commands::On::Id : OnOff::Commands::Off::Id;
      esp_matter::lock::chip_stack_lock(portMAX_DELAY);
      esp_matter::client::cluster_update(eid, &req);
      esp_matter::lock::chip_stack_unlock();
    });
  }

  for (const auto &sw : this->dimmer_switches_) {
    uint16_t eid = sw.endpoint_id;
    auto send_level = [eid](bool press, uint8_t move_mode) {
      using namespace chip::app::Clusters;
      esp_matter::client::request_handle_t req;
      req.type = esp_matter::client::INVOKE_CMD;
      req.command_path.mClusterId = LevelControl::Id;
      if (press) {
        req.command_path.mCommandId = LevelControl::Commands::MoveWithOnOff::Id;
        req.request_data = reinterpret_cast<void *>(static_cast<uintptr_t>(move_mode));
      } else {
        req.command_path.mCommandId = LevelControl::Commands::StopWithOnOff::Id;
      }
      esp_matter::lock::chip_stack_lock(portMAX_DELAY);
      esp_matter::client::cluster_update(eid, &req);
      esp_matter::lock::chip_stack_unlock();
    };
    sw.up_sensor->add_on_state_callback([send_level](bool state) { send_level(state, 0); });
    sw.down_sensor->add_on_state_callback([send_level](bool state) { send_level(state, 1); });
  }
}

void MatterComponent::factory_reset() {
  ESP_LOGW(TAG, "Matter factory reset. Erasing fabric data and rebooting");
  for (const char *ns : {"chip-config", "chip-counters", "CHIP_KVS"}) {
    nvs_handle_t h;
    if (nvs_open(ns, NVS_READWRITE, &h) == ESP_OK) {
      nvs_erase_all(h);
      nvs_commit(h);
      nvs_close(h);
    }
  }
  App.safe_reboot();
}

void MatterComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Matter:");
  if (this->is_failed()) {
    ESP_LOGE(TAG, "  Failed to initialize!");
    return;
  }

  chip::SetupPayload payload;
  payload.version = 0;
  payload.vendorID = CHIP_DEVICE_CONFIG_DEVICE_VENDOR_ID;
  payload.productID = CHIP_DEVICE_CONFIG_DEVICE_PRODUCT_ID;
  payload.commissioningFlow = chip::CommissioningFlow::kStandard;
  payload.rendezvousInformation.SetValue(chip::RendezvousInformationFlag::kBLE);
  payload.discriminator.SetLongValue(this->discriminator_);
  payload.setUpPINCode = this->passcode_;

  std::string qr_code;
  if (chip::QRCodeSetupPayloadGenerator(payload).payloadBase38Representation(qr_code) == CHIP_NO_ERROR) {
    ESP_LOGCONFIG(TAG, "  SetupQRCode: %s", qr_code.c_str());
    ESP_LOGCONFIG(TAG, "  QR URL: https://project-chip.github.io/connectedhomeip/qrcode.html?data=%s",
                  qr_code.c_str());
  } else {
    ESP_LOGE(TAG, "  Failed to generate QR code");
  }

  std::string manual_code;
  if (chip::ManualSetupPayloadGenerator(payload).payloadDecimalStringRepresentation(manual_code) == CHIP_NO_ERROR) {
    ESP_LOGCONFIG(TAG, "  Manual pairing code: %s", manual_code.c_str());
  }

  chip::DeviceLayer::PlatformMgr().LockChipStack();
  auto &server = chip::Server::GetInstance();
  ESP_LOGCONFIG(TAG, "  Commissioning window: %s",
                server.GetCommissioningWindowManager().IsCommissioningWindowOpen() ? "open" : "closed");
  const auto &fabric_table = server.GetFabricTable();
  if (fabric_table.FabricCount() == 0) {
    ESP_LOGCONFIG(TAG, "  Fabrics: none");
  } else {
    ESP_LOGCONFIG(TAG, "  Fabrics:");
    for (const auto &fabric : fabric_table) {
      char label[chip::kFabricLabelMaxLengthInBytes + 1] = {0};
      auto label_span = fabric.GetFabricLabel();
      memcpy(label, label_span.data(), std::min(label_span.size(), sizeof(label) - 1));
      uint64_t fabric_id = fabric.GetFabricId();
      uint64_t node_id = fabric.GetNodeId();
      ESP_LOGCONFIG(TAG, "    [%u] FabricId: 0x%08" PRIx32 "%08" PRIx32
                         ", NodeId: 0x%08" PRIx32 "%08" PRIx32
                         ", VendorId: 0x%04x%s%s",
                    fabric.GetFabricIndex(),
                    (uint32_t)(fabric_id >> 32), (uint32_t)(fabric_id),
                    (uint32_t)(node_id >> 32), (uint32_t)(node_id),
                    (uint16_t)fabric.GetVendorId(),
                    label[0] ? ", Label: " : "", label);
    }
  }
  chip::DeviceLayer::PlatformMgr().UnlockChipStack();
}

}  // namespace esphome::matter

#endif  // USE_MATTER
