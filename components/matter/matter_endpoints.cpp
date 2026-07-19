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

#ifdef USE_LIGHT
  for (auto *ml : this->lights_) {
    esp_matter::endpoint_t *ep = nullptr;
    if (ml->dimmable) {
      esp_matter::endpoint::dimmable_light::config_t light_config;
      ep = esp_matter::endpoint::dimmable_light::create(node, &light_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    } else {
      esp_matter::endpoint::on_off_light::config_t light_config;
      ep = esp_matter::endpoint::on_off_light::create(node, &light_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    }
    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create %s endpoint", ml->dimmable ? "dimmable_light" : "on_off_light");
      return false;
    }
    ml->endpoint_id = esp_matter::endpoint::get_id(ep);
    ml->ref->endpoint_id = ml->endpoint_id;
    ESP_LOGD(TAG, "%s endpoint created: id=%u", ml->dimmable ? "Dimmable light" : "On/Off light", ml->endpoint_id);
  }
#endif

  if (!this->on_off_switches_.empty() || !this->dimmer_switches_.empty()) {
    register_client_request_callbacks();
  }

  return true;
}

#ifdef USE_LIGHT
// Mirrors the current ESPHome light state to the Matter attributes.
// Runs on the main loop; the attribute writes hop to the Matter thread.
void MatterLight::push_state_to_matter() {
  uint16_t eid = this->endpoint_id;
  bool dim = this->dimmable;
  bool on = this->light->remote_values.is_on();
  float brightness = this->light->remote_values.get_brightness();
  auto level = static_cast<uint8_t>(std::lroundf(brightness * 254.0f));
  level = level < 1 ? 1 : level;
  chip::DeviceLayer::SystemLayer().ScheduleLambda([eid, dim, on, level]() {
    using namespace chip::app::Clusters;
    esp_matter_attr_val_t on_val = esp_matter_bool(on);
    esp_matter::attribute::update(eid, OnOff::Id, OnOff::Attributes::OnOff::Id, &on_val);
    if (dim) {
      esp_matter_attr_val_t level_val = esp_matter_nullable_uint8(nullable<uint8_t>(level));
      esp_matter::attribute::update(eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id, &level_val);
    }
  });
}

// Applies a Matter-side attribute change to the ESPHome light. Runs on the
// main loop (deferred from the Matter thread). Values that already match the
// light's state are ignored, which also breaks the mirror echo loop.
void MatterLight::apply_matter_update(uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t val) {
  using namespace chip::app::Clusters;
  if (cluster_id == OnOff::Id && attribute_id == OnOff::Attributes::OnOff::Id) {
    bool on = val.val.b;
    if (this->light->remote_values.is_on() == on)
      return;
    auto call = this->light->make_call();
    call.set_state(on);
    // The Matter side already ramps CurrentLevel during transitions; a second
    // ESPHome-side transition would double-smooth every change.
    call.set_transition_length(0);
    call.perform();
  } else if (this->dimmable && cluster_id == LevelControl::Id &&
             attribute_id == LevelControl::Attributes::CurrentLevel::Id) {
    uint8_t level = val.val.u8;
    if (level < 1 || level > 254)
      return;  // null or out of spec range
    float brightness = level / 254.0f;
    if (std::fabs(this->light->remote_values.get_brightness() - brightness) < (0.5f / 254.0f))
      return;
    auto call = this->light->make_call();
    call.set_brightness(brightness);
    call.set_transition_length(0);
    call.perform();
  }
}
#endif  // USE_LIGHT

esp_err_t endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type, uint16_t endpoint_id,
                                       uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t *val,
                                       void *priv_data) {
#ifdef USE_LIGHT
  if (type != esp_matter::attribute::POST_UPDATE || global_matter_component == nullptr)
    return ESP_OK;
  MatterLight *ml = global_matter_component->get_light_by_endpoint(endpoint_id);
  if (ml == nullptr)
    return ESP_OK;
  // This callback runs in the Matter thread; ESPHome entities are main-loop only.
  esp_matter_attr_val_t val_copy = *val;
  global_matter_component->defer_to_main_loop([ml, cluster_id, attribute_id, val_copy]() {
    ml->apply_matter_update(cluster_id, attribute_id, val_copy);
  });
#endif
  return ESP_OK;
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

#ifdef USE_LIGHT
  for (auto *ml : this->lights_) {
    ml->light->add_remote_values_listener(ml);
    ml->push_state_to_matter();  // initial sync so controllers read the real state
  }
#endif
}

}  // namespace esphome::matter

#endif  // USE_MATTER
