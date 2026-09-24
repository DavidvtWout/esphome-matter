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

namespace {

optional<MatterColorTemperatureRange>
get_color_temperature_range(const light::LightTraits &traits) {
  float min_mireds = traits.get_min_mireds();
  float max_mireds = traits.get_max_mireds();
  if (min_mireds <= 0.0f || max_mireds <= 0.0f)
    return nullopt;
  return MatterColorTemperatureRange{
      conversion::to_matter::color_temperature(min_mireds),
      conversion::to_matter::color_temperature(max_mireds),
  };
}

} // namespace

void MatterComponent::register_light(light::LightState *light,
                                     uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterLightMapping(light, endpoint_id));
}

MatterLightMapping::MatterLightMapping(light::LightState *light,
                                       uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), light_(light) {}

void MatterLightMapping::initialize() {
  if (this->light_ == nullptr)
    return;

  // Initialize capabilities
  this->capabilities_.has_level =
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id);
  this->capabilities_.color_temperature_range =
      get_color_temperature_range(this->light_->get_traits());
  if (!this->has_server_cluster(chip::app::Clusters::ColorControl::Id))
    this->capabilities_.color_temperature_range = nullopt;

  // Register attribute callbacks
  using namespace chip::app::Clusters;
  global_matter_component->register_attribute_callback(
      this->endpoint_id(), OnOff::Id, OnOff::Attributes::OnOff::Id,
      [this](const esp_matter_attr_val_t &value) {
        if (value.is_null())
          return;
        bool on = value.val.b;
        global_matter_component->defer_to_main_loop(
            [this, on]() { this->apply_on_off_(on); });
      });
  if (this->capabilities_.has_level) {
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), LevelControl::Id,
        LevelControl::Attributes::CurrentLevel::Id,
        [this](const esp_matter_attr_val_t &value) {
          if (value.is_null())
            return;
          uint8_t level = value.val.u8;
          global_matter_component->defer_to_main_loop(
              [this, level]() { this->apply_level_(level); });
        });
  }
  if (this->capabilities_.color_temperature_range.has_value()) {
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::ColorTemperatureMireds::Id,
        [this](const esp_matter_attr_val_t &value) {
          if (value.is_null())
            return;
          uint16_t color_temperature = value.val.u16;
          global_matter_component->defer_to_main_loop(
              [this, color_temperature]() {
                this->apply_color_temperature_(color_temperature);
              });
        });
  }

  // Light calls on_light_remote_values_update() on updates.
  this->light_->add_remote_values_listener(this);

  chip::DeviceLayer::SystemLayer().ScheduleLambda([this]() {
    this->initialize_matter_attributes_();
    this->restore_light_state_from_matter_();
  });
}

void MatterLightMapping::on_light_remote_values_update() {
  if (this->synchronizing_from_matter_)
    return;
  this->push_state_to_matter();
}

void MatterLightMapping::push_state_to_matter() {
  uint16_t eid = this->endpoint_id();
  bool has_level = this->capabilities_.has_level;
  bool has_color_temperature =
      this->capabilities_.color_temperature_range.has_value();
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

void MatterLightMapping::initialize_matter_attributes_() {
  if (!this->capabilities_.color_temperature_range.has_value())
    return;

  using namespace chip::app::Clusters;
  uint16_t endpoint_id = this->endpoint_id();
  const auto &range = *this->capabilities_.color_temperature_range;
  esp_matter_attr_val_t min_value = esp_matter_uint16(range.min_mireds);
  esp_matter::attribute::update(
      endpoint_id, ColorControl::Id,
      ColorControl::Attributes::ColorTempPhysicalMinMireds::Id, &min_value);
  esp_matter_attr_val_t max_value = esp_matter_uint16(range.max_mireds);
  esp_matter::attribute::update(
      endpoint_id, ColorControl::Id,
      ColorControl::Attributes::ColorTempPhysicalMaxMireds::Id, &max_value);

  esp_matter_attr_val_t color_temperature_value;
  if (esp_matter::attribute::get_val(
          endpoint_id, ColorControl::Id,
          ColorControl::Attributes::ColorTemperatureMireds::Id,
          &color_temperature_value) != ESP_OK ||
      color_temperature_value.is_null())
    return;

  uint16_t color_temperature = std::clamp(color_temperature_value.val.u16,
                                          range.min_mireds, range.max_mireds);
  if (color_temperature == color_temperature_value.val.u16)
    return;
  color_temperature_value.val.u16 = color_temperature;
  esp_matter::attribute::update(
      endpoint_id, ColorControl::Id,
      ColorControl::Attributes::ColorTemperatureMireds::Id,
      &color_temperature_value);
}

void MatterLightMapping::restore_light_state_from_matter_() {
  using namespace chip::app::Clusters;
  uint16_t endpoint_id = this->endpoint_id();
  esp_matter_attr_val_t on_value;
  if (esp_matter::attribute::get_val(endpoint_id, OnOff::Id,
                                     OnOff::Attributes::OnOff::Id,
                                     &on_value) != ESP_OK ||
      on_value.is_null())
    return;

  bool on = on_value.val.b;
  bool has_valid_level = false;
  uint8_t level = 0;
  if (this->capabilities_.has_level) {
    esp_matter_attr_val_t level_value;
    if (esp_matter::attribute::get_val(
            endpoint_id, LevelControl::Id,
            LevelControl::Attributes::CurrentLevel::Id,
            &level_value) == ESP_OK &&
        !level_value.is_null() && level_value.val.u8 >= 1 &&
        level_value.val.u8 <= 254) {
      has_valid_level = true;
      level = level_value.val.u8;
    }
  }

  bool has_valid_color_temperature = false;
  uint16_t color_temperature = 0;
  if (this->capabilities_.color_temperature_range.has_value()) {
    esp_matter_attr_val_t color_temperature_value;
    if (esp_matter::attribute::get_val(
            endpoint_id, ColorControl::Id,
            ColorControl::Attributes::ColorTemperatureMireds::Id,
            &color_temperature_value) == ESP_OK &&
        !color_temperature_value.is_null()) {
      has_valid_color_temperature = true;
      color_temperature = color_temperature_value.val.u16;
    }
  }

  global_matter_component->defer_to_main_loop([this, on, has_valid_level, level,
                                               has_valid_color_temperature,
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
}

void MatterLightMapping::apply_on_off_(bool on) {
  if (this->light_->remote_values.is_on() == on)
    return;
  auto call = this->light_->make_call();
  call.set_state(on);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

void MatterLightMapping::apply_level_(uint8_t level) {
  if (level < 1 || level > 254)
    return;
  float brightness = conversion::level_to_brightness(level);
  if (std::fabs(this->light_->remote_values.get_brightness() - brightness) <
      (0.5f / 254.0f))
    return;
  auto call = this->light_->make_call();
  call.set_brightness(brightness);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

void MatterLightMapping::apply_color_temperature_(uint16_t color_temperature) {
  if (std::fabs(this->light_->remote_values.get_color_temperature() -
                color_temperature) < 0.5f)
    return;
  auto call = this->light_->make_call();
  call.set_color_temperature(color_temperature);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_LIGHT
