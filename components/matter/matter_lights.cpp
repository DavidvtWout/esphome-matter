#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_LIGHT)

#include "matter_component.h"
#include "matter_conversions.h"
#include "matter_lights.h"

#include <algorithm>
#include <cmath>
#include <esp_matter_cluster.h>
#include <platform/CHIPDeviceLayer.h>

namespace esphome::matter {

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
  this->sync_state_from_matter();
}

MatterLightMapping *MatterLightMapping::as_light_mapping() { return this; }

void MatterLightMapping::push_state_to_matter() {
  uint16_t eid = this->endpoint_id();
  bool has_level =
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id);
  bool has_color_temperature =
      this->has_server_cluster(chip::app::Clusters::ColorControl::Id) &&
      this->light_->get_traits().supports_color_capability(
          light::ColorCapability::COLOR_TEMPERATURE);
  bool on = this->light_->remote_values.is_on();
  float brightness = this->light_->remote_values.get_brightness();
  auto level = conversion::brightness_to_level(brightness);
  auto color_temperature = conversion::color_temperature_to_mireds(
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
  uint16_t eid = this->endpoint_id();
  bool has_level =
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id);
  auto traits = this->light_->get_traits();
  bool has_color_temperature =
      this->has_server_cluster(chip::app::Clusters::ColorControl::Id) &&
      traits.supports_color_capability(
          light::ColorCapability::COLOR_TEMPERATURE);
  auto min_mireds =
      conversion::color_temperature_to_mireds(traits.get_min_mireds());
  auto max_mireds =
      conversion::color_temperature_to_mireds(traits.get_max_mireds());
  chip::DeviceLayer::SystemLayer().ScheduleLambda([this, eid, has_level,
                                                   has_color_temperature,
                                                   min_mireds, max_mireds]() {
    using namespace chip::app::Clusters;
    esp_matter_attr_val_t on_value;
    if (esp_matter::attribute::get_val(eid, OnOff::Id,
                                       OnOff::Attributes::OnOff::Id,
                                       &on_value) != ESP_OK ||
        on_value.is_null())
      return;

    bool on = on_value.val.b;
    bool has_valid_level = false;
    uint8_t level = 0;
    if (has_level) {
      esp_matter_attr_val_t level_value;
      if (esp_matter::attribute::get_val(
              eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id,
              &level_value) == ESP_OK &&
          !level_value.is_null() && level_value.val.u8 >= 1 &&
          level_value.val.u8 <= 254) {
        has_valid_level = true;
        level = level_value.val.u8;
      }
    }

    bool has_valid_color_temperature = false;
    uint16_t color_temperature = 0;
    if (has_color_temperature && min_mireds <= max_mireds) {
      esp_matter_attr_val_t min_value = esp_matter_uint16(min_mireds);
      esp_matter::attribute::update(
          eid, ColorControl::Id,
          ColorControl::Attributes::ColorTempPhysicalMinMireds::Id, &min_value);
      esp_matter_attr_val_t max_value = esp_matter_uint16(max_mireds);
      esp_matter::attribute::update(
          eid, ColorControl::Id,
          ColorControl::Attributes::ColorTempPhysicalMaxMireds::Id, &max_value);

      esp_matter_attr_val_t color_temperature_value;
      if (esp_matter::attribute::get_val(
              eid, ColorControl::Id,
              ColorControl::Attributes::ColorTemperatureMireds::Id,
              &color_temperature_value) == ESP_OK &&
          !color_temperature_value.is_null()) {
        has_valid_color_temperature = true;
        color_temperature =
            std::clamp(color_temperature_value.val.u16, min_mireds, max_mireds);
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
             this->light_->get_traits().supports_color_capability(
                 light::ColorCapability::COLOR_TEMPERATURE) &&
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
