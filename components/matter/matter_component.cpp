#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_component.h"
#include "esphome/core/application.h"
#include "esphome/core/log.h"

#include <cstring>
#include <algorithm>
#include <nvs.h>
#include <esp_random.h>

#include <crypto/CHIPCryptoPAL.h>
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

#if defined(MATTER_DISCRIMINATOR)
  discriminator = MATTER_DISCRIMINATOR;
#else
  discriminator = (uint16_t)(esp_random() & 0x0FFFu);
#endif

#if defined(MATTER_PASSCODE)
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

static void event_callback(const ChipDeviceEvent *event, intptr_t arg) {
  switch (event->Type) {
    case chip::DeviceLayer::DeviceEventType::kCommissioningComplete:
      ESP_LOGI(TAG, "Commissioning complete");
      break;
    case chip::DeviceLayer::DeviceEventType::kFabricRemoved:
      ESP_LOGI(TAG, "Fabric removed");
      break;
    default:
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

  esp_err_t err = esp_matter::start(event_callback);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to start Matter: %s", esp_err_to_name(err));
    this->mark_failed();
    return;
  }
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
  payload.rendezvousInformation.SetValue(chip::RendezvousInformationFlag::kOnNetwork);
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
}

}  // namespace esphome::matter

#endif  // USE_MATTER
