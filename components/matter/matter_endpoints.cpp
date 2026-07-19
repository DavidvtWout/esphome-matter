#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_component.h"
#include "esphome/core/log.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>

static const char *const TAG = "matter";

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

bool MatterComponent::create_endpoints_(esp_matter::node_t *node) {
  for (auto &sw : this->on_off_switches_) {
    esp_matter::endpoint::on_off_switch::config_t sw_config;
    esp_matter::endpoint_t *ep =
        esp_matter::endpoint::on_off_switch::create(node, &sw_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create on_off_switch endpoint");
      return false;
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
      return false;
    }
    sw.endpoint_id = esp_matter::endpoint::get_id(ep);
    ESP_LOGD(TAG, "Dimmer switch endpoint created: id=%u", sw.endpoint_id);
  }

#ifdef USE_SENSOR
  for (auto &ts : this->temperature_sensors_) {
    esp_matter::endpoint::temperature_sensor::config_t ts_config;
    esp_matter::endpoint_t *ep =
        esp_matter::endpoint::temperature_sensor::create(node, &ts_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create temperature_sensor endpoint");
      return false;
    }
    ts.endpoint_id = esp_matter::endpoint::get_id(ep);
    ESP_LOGD(TAG, "Temperature sensor endpoint created: id=%u", ts.endpoint_id);
  }
#endif

  if (!this->on_off_switches_.empty() || !this->dimmer_switches_.empty()) {
    esp_matter::client::set_request_callback(client_invoke_cb, client_group_invoke_cb, nullptr);
  }

  return true;
}

// Wires the binary sensors to outgoing client commands. Must run after esp_matter::start().
void MatterComponent::register_endpoint_callbacks_() {
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

#ifdef USE_SENSOR
  for (const auto &ts : this->temperature_sensors_) {
    uint16_t eid = ts.endpoint_id;
    ts.sensor->add_on_state_callback([eid](float value) {
      // Matter spec: MeasuredValue = temperature in °C * 100, nullable int16
      // (valid range -273.15 °C .. 327.67 °C). Out-of-range or NaN reports null.
      bool is_null = std::isnan(value) || value < -273.15f || value > 327.67f;
      int16_t raw = is_null ? 0 : static_cast<int16_t>(lroundf(value * 100.0f));
      // Attribute updates must run in the Matter thread (same pattern as the
      // esp-matter sensors example).
      chip::DeviceLayer::SystemLayer().ScheduleLambda([eid, raw, is_null]() {
        using namespace chip::app::Clusters;
        esp_matter_attr_val_t val =
            esp_matter_nullable_int16(is_null ? nullable<int16_t>() : nullable<int16_t>(raw));
        esp_matter::attribute::update(eid, TemperatureMeasurement::Id,
                                      TemperatureMeasurement::Attributes::MeasuredValue::Id, &val);
      });
    });
  }
#endif
}

}  // namespace esphome::matter

#endif  // USE_MATTER
