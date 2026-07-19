#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_component.h"
#include "matter_actions.h"
#include "esphome/core/log.h"

#include <cmath>

static const char *const TAG = "matter";

namespace esphome::matter {

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
    sw.ref->endpoint_id = sw.endpoint_id;
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
    sw.ref->endpoint_id = sw.endpoint_id;
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
    ts.ref->endpoint_id = ts.endpoint_id;
    ESP_LOGD(TAG, "Temperature sensor endpoint created: id=%u", ts.endpoint_id);
  }
#endif

  if (!this->on_off_switches_.empty() || !this->dimmer_switches_.empty()) {
    register_client_request_callbacks();
  }

  return true;
}

// Wires ESPHome entities to Matter attributes. Must run after esp_matter::start().
// Client switch endpoints have no wiring here: their behaviour comes from
// matter.* actions in YAML automations.
void MatterComponent::register_endpoint_callbacks_() {
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
