#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_LIGHT)

#include "esphome/core/application.h"
#include "esphome/core/log.h"
#include "esphome/core/optional.h"
#include "matter_component.h"
#include "matter_conversions.h"
#include "matter_lights.h"

#include <algorithm>
#include <cmath>
#include <esp_matter_cluster.h>
#include <platform/CHIPDeviceLayer.h>

namespace esphome::matter {

namespace {

struct MatterColorTemperatureRange {
  uint16_t min_mireds;
  uint16_t max_mireds;
};

struct MatterLightSyncSnapshot {
  uint16_t endpoint_id;
  bool has_level;
  optional<MatterColorTemperatureRange> color_temperature_range;
};

optional<MatterColorTemperatureRange>
get_color_temperature_range(const light::LightTraits &traits) {
  float min_mireds = traits.get_min_mireds();
  float max_mireds = traits.get_max_mireds();
  if (!std::isfinite(min_mireds) || !std::isfinite(max_mireds) ||
      min_mireds <= 0.0f || max_mireds <= 0.0f || min_mireds > max_mireds)
    return nullopt;

  return MatterColorTemperatureRange{
      conversion::to_matter::color_temperature(min_mireds),
      conversion::to_matter::color_temperature(max_mireds),
  };
}

} // namespace

void MatterComponent::map_light_to_endpoint(light::LightState *light,
                                            uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterLightMapping(light, endpoint_id));
}

MatterLightMapping::MatterLightMapping(light::LightState *light,
                                       uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), light_(light) {}

void MatterLightMapping::on_light_remote_values_update() {
  if (this->synchronizing_from_matter_)
    return;
  this->push_state_to_matter();
}

void MatterLightMapping::register_callbacks() {
  if (this->light_ == nullptr)
    return;
  this->light_->add_remote_values_listener(this);
  App.scheduler.set_timeout(this, 15000,
                            [this]() { this->sync_state_from_matter(); });
}

MatterLightMapping *MatterLightMapping::as_light_mapping() { return this; }

void MatterLightMapping::push_state_to_matter() {
  uint16_t eid = this->endpoint_id();
  bool has_level =
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id);
  bool has_color_temperature =
      this->has_server_cluster(chip::app::Clusters::ColorControl::Id) &&
      get_color_temperature_range(this->light_->get_traits()).has_value();
  bool on = this->light_->remote_values.is_on();
  float brightness = this->light_->remote_values.get_brightness();
  auto level = conversion::brightness_to_level(brightness);
  auto color_temperature = conversion::to_matter::color_temperature(
      this->light_->remote_values.get_color_temperature());
  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [eid, has_level, has_color_temperature, on, level, color_temperature]() {
        using namespace chip::app::Clusters;
        esp_matter_attr_val_t on_val = esp_matter_bool(on);
        esp_matter::attribute::update(eid, OnOff::Id,
                                      OnOff::Attributes::OnOff::Id, &on_val);
        if (has_level) {
          esp_matter_attr_val_t level_val =
              esp_matter_nullable_uint8(nullable<uint8_t>(level));
          esp_matter::attribute::update(
              eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id,
              &level_val);
        }
        if (has_color_temperature) {
          esp_matter_attr_val_t color_temperature_val =
              esp_matter_uint16(color_temperature);
          esp_matter::attribute::update(
              eid, ColorControl::Id,
              ColorControl::Attributes::ColorTemperatureMireds::Id,
              &color_temperature_val);
        }
      });
}

void MatterLightMapping::sync_state_from_matter() {
  // ESPHome entities must be accessed from the main loop, so copy only the
  // values needed by the Matter-thread callback.
  auto traits = this->light_->get_traits();
  auto color_temperature_range = get_color_temperature_range(traits);
  if (!this->has_server_cluster(chip::app::Clusters::ColorControl::Id))
    color_temperature_range = nullopt;
  MatterLightSyncSnapshot snapshot{
      this->endpoint_id(),
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id),
      color_temperature_range,
  };
  if (snapshot.color_temperature_range.has_value()) {
    const auto &range = *snapshot.color_temperature_range;
    ESP_LOGD("matter",
             "Scheduling light synchronization: endpoint=%u, level=%s, color "
             "temperature=YES, range=%u-%u mireds",
             snapshot.endpoint_id, YESNO(snapshot.has_level), range.min_mireds,
             range.max_mireds);
  } else {
    ESP_LOGD("matter",
             "Scheduling light synchronization: endpoint=%u, level=%s, color "
             "temperature=NO",
             snapshot.endpoint_id, YESNO(snapshot.has_level));
  }
  chip::DeviceLayer::SystemLayer().ScheduleLambda([this, snapshot]() {
    uint16_t eid = snapshot.endpoint_id;
    ESP_LOGD("matter", "Synchronizing light state: endpoint=%u", eid);

    using namespace chip::app::Clusters;
    esp_matter_attr_val_t on_value;
    esp_err_t on_err = esp_matter::attribute::get_val(
        eid, OnOff::Id, OnOff::Attributes::OnOff::Id, &on_value);
    bool on_is_null = on_err == ESP_OK && on_value.is_null();
    if (on_err != ESP_OK || on_is_null) {
      ESP_LOGD("matter",
               "Cannot synchronize light endpoint %u: reading OnOff failed "
               "with %s (null=%s)",
               eid, esp_err_to_name(on_err), YESNO(on_is_null));
      return;
    }

    bool on = on_value.val.b;
    ESP_LOGD("matter", "Initial OnOff value: endpoint=%u, value=%s", eid,
             ONOFF(on));
    bool has_valid_level = false;
    uint8_t level = 0;
    if (snapshot.has_level) {
      esp_matter_attr_val_t level_value;
      if (esp_matter::attribute::get_val(
              eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id,
              &level_value) == ESP_OK &&
          !level_value.is_null() && level_value.val.u8 >= 1 &&
          level_value.val.u8 <= 254) {
        has_valid_level = true;
        level = level_value.val.u8;
        ESP_LOGD("matter", "Initial level value: endpoint=%u, value=%u", eid,
                 level);
      }
    }

    bool has_valid_color_temperature = false;
    uint16_t color_temperature = 0;
    if (snapshot.color_temperature_range.has_value()) {
      const auto &range = *snapshot.color_temperature_range;
      esp_matter_attr_val_t min_value = esp_matter_uint16(range.min_mireds);
      esp_err_t min_err = esp_matter::attribute::update(
          eid, ColorControl::Id,
          ColorControl::Attributes::ColorTempPhysicalMinMireds::Id, &min_value);
      esp_matter_attr_val_t max_value = esp_matter_uint16(range.max_mireds);
      esp_err_t max_err = esp_matter::attribute::update(
          eid, ColorControl::Id,
          ColorControl::Attributes::ColorTempPhysicalMaxMireds::Id, &max_value);
      ESP_LOGD("matter",
               "Updated physical color temperature range: endpoint=%u, "
               "minimum=%u (%s), maximum=%u (%s)",
               eid, range.min_mireds, esp_err_to_name(min_err),
               range.max_mireds, esp_err_to_name(max_err));

      esp_matter_attr_val_t color_temperature_value;
      if (esp_matter::attribute::get_val(
              eid, ColorControl::Id,
              ColorControl::Attributes::ColorTemperatureMireds::Id,
              &color_temperature_value) == ESP_OK &&
          !color_temperature_value.is_null()) {
        has_valid_color_temperature = true;
        color_temperature = std::clamp(color_temperature_value.val.u16,
                                       range.min_mireds, range.max_mireds);
        ESP_LOGD("matter",
                 "Initial color temperature: endpoint=%u, stored=%u, "
                 "clamped=%u",
                 eid, color_temperature_value.val.u16, color_temperature);
        if (color_temperature != color_temperature_value.val.u16) {
          color_temperature_value.val.u16 = color_temperature;
          esp_matter::attribute::update(
              eid, ColorControl::Id,
              ColorControl::Attributes::ColorTemperatureMireds::Id,
              &color_temperature_value);
        }
      }
    }

    global_matter_component->defer_to_main_loop(
        [this, on, has_valid_level, level, has_valid_color_temperature,
         color_temperature]() {
          this->synchronizing_from_matter_ = true;
          auto call = this->light_->make_call();
          call.set_state(on);
          if (has_valid_level)
            call.set_brightness(conversion::level_to_brightness(level));
          if (has_valid_color_temperature)
            call.set_color_temperature(color_temperature);
          call.set_transition_length(0);
          call.perform();
          this->synchronizing_from_matter_ = false;
        });
  });
}

void MatterLightMapping::apply_matter_update(uint32_t cluster_id,
                                             uint32_t attribute_id,
                                             esp_matter_attr_val_t val) {
  using namespace chip::app::Clusters;
  if (cluster_id == OnOff::Id && attribute_id == OnOff::Attributes::OnOff::Id) {
    bool on = val.val.b;
    if (this->light_->remote_values.is_on() == on)
      return;
    auto call = this->light_->make_call();
    call.set_state(on);
    call.set_transition_length(0);
    call.perform();
  } else if (this->has_server_cluster(LevelControl::Id) &&
             cluster_id == LevelControl::Id &&
             attribute_id == LevelControl::Attributes::CurrentLevel::Id) {
    uint8_t level = val.val.u8;
    if (level < 1 || level > 254)
      return;
    float brightness = conversion::level_to_brightness(level);
    if (std::fabs(this->light_->remote_values.get_brightness() - brightness) <
        (0.5f / 254.0f))
      return;
    auto call = this->light_->make_call();
    call.set_brightness(brightness);
    call.set_transition_length(0);
    call.perform();
  } else if (this->has_server_cluster(ColorControl::Id) &&
             get_color_temperature_range(this->light_->get_traits())
                 .has_value() &&
             cluster_id == ColorControl::Id &&
             attribute_id ==
                 ColorControl::Attributes::ColorTemperatureMireds::Id) {
    uint16_t color_temperature = val.val.u16;
    if (std::fabs(this->light_->remote_values.get_color_temperature() -
                  color_temperature) < 0.5f)
      return;
    auto call = this->light_->make_call();
    call.set_color_temperature(color_temperature);
    call.set_transition_length(0);
    call.perform();
  }
}

MatterLightMapping *
MatterComponent::get_light_mapping_by_endpoint(uint16_t endpoint_id) {
  for (auto *mapping : this->mappings_) {
    auto *light_mapping = mapping->as_light_mapping();
    if (light_mapping != nullptr &&
        light_mapping->endpoint_id() == endpoint_id) {
      return light_mapping;
    }
  }
  return nullptr;
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_LIGHT
