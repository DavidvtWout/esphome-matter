#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_LIGHT)

#include "esphome/core/log.h"
#include "matter_component.h"
#include "matter_conversions.h"
#include "matter_lights.h"

#include <algorithm>
#include <cmath>
#include <esp_matter_cluster.h>
#include <platform/CHIPDeviceLayer.h>

static const char *const TAG = "matter";

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
  this->capabilities_.has_color =
      this->has_server_cluster(chip::app::Clusters::ColorControl::Id);
  this->capabilities_.color_temperature_range =
      get_color_temperature_range(this->light_->get_traits());
  if (!this->has_server_cluster(chip::app::Clusters::ColorControl::Id))
    this->capabilities_.color_temperature_range = nullopt;

  // Register attribute callbacks
  using namespace chip::app::Clusters;
  global_matter_component->register_attribute_callback(
      this->endpoint_id(), OnOff::Id, OnOff::Attributes::OnOff::Id,
      [this](const esp_matter_attr_val_t &value) {
        bool on = value.val.b;
        global_matter_component->defer_to_main_loop(
            [this, on]() { this->apply_on_off_(on); });
      });
  if (this->capabilities_.has_level) {
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), LevelControl::Id,
        LevelControl::Attributes::CurrentLevel::Id,
        [this](const esp_matter_attr_val_t &value) {
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
          uint16_t color_temperature = value.val.u16;
          global_matter_component->defer_to_main_loop(
              [this, color_temperature]() {
                this->apply_color_temperature_(color_temperature);
              });
        });
  }
  if (this->capabilities_.has_color) {
    MatterAttributeCallback color_callback =
        [this](const esp_matter_attr_val_t &) {
          if (this->color_update_pending_)
            return;
          this->color_update_pending_ = true;
          // CurrentX and CurrentY are updated separately. Read the pair after
          // the current Matter work item completes so a new coordinate is not
          // combined with the previous value of the other coordinate.
          chip::DeviceLayer::SystemLayer().ScheduleLambda([this]() {
            this->color_update_pending_ = false;
            using namespace chip::app::Clusters;
            esp_matter_attr_val_t x_value;
            esp_matter_attr_val_t y_value;
            if (esp_matter::attribute::get_val(
                    this->endpoint_id(), ColorControl::Id,
                    ColorControl::Attributes::CurrentX::Id,
                    &x_value) != ESP_OK ||
                esp_matter::attribute::get_val(
                    this->endpoint_id(), ColorControl::Id,
                    ColorControl::Attributes::CurrentY::Id,
                    &y_value) != ESP_OK ||
                x_value.is_null() || y_value.is_null())
              return;
            uint16_t x = x_value.val.u16;
            uint16_t y = y_value.val.u16;
            global_matter_component->defer_to_main_loop(
                [this, x, y]() { this->apply_color_(x, y); });
          });
        };
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::CurrentX::Id, color_callback);
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::CurrentY::Id, std::move(color_callback));
  }
  if (this->capabilities_.has_color ||
      this->capabilities_.color_temperature_range.has_value()) {
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::ColorMode::Id,
        [this](const esp_matter_attr_val_t &value) {
          this->apply_color_mode_(value.val.u8);
        });
  }

  // Light calls on_light_remote_values_update() on updates.
  this->light_->add_remote_values_listener(this);

  chip::DeviceLayer::SystemLayer().ScheduleLambda([this]() {
    this->initialize_matter_attributes_();
    using namespace chip::app::Clusters;
    global_matter_component->replay_attribute_callback(
        this->endpoint_id(), OnOff::Id, OnOff::Attributes::OnOff::Id);
    if (this->capabilities_.has_level)
      global_matter_component->replay_attribute_callback(
          this->endpoint_id(), LevelControl::Id,
          LevelControl::Attributes::CurrentLevel::Id);
    // The color_mode callback triggers the mired and xy colour callbacks so
    // these don't need to be called explicitely here.
    if (this->capabilities_.has_color ||
        this->capabilities_.color_temperature_range.has_value())
      global_matter_component->replay_attribute_callback(
          this->endpoint_id(), ColorControl::Id,
          ColorControl::Attributes::ColorMode::Id);
  });
}

void MatterLightMapping::on_light_remote_values_update() {
  if (this->synchronizing_from_matter_)
    return; // TODO: Fix this race-condition
  this->push_state_to_matter();
}

// Pushes the whole state of the light to Matter. esp-matter "deduplicates"
// attribute updates so it's okay to not check if the values are changed.
void MatterLightMapping::push_state_to_matter() {
  uint16_t eid = this->endpoint_id();
  bool has_level = this->capabilities_.has_level;
  const auto &values = this->light_->remote_values;
  auto color_mode = values.get_color_mode();
  bool has_color = this->capabilities_.has_color &&
                   (color_mode & light::ColorCapability::RGB);
  bool has_color_temperature =
      this->capabilities_.color_temperature_range.has_value() && !has_color &&
      (color_mode & (light::ColorCapability::COLOR_TEMPERATURE |
                     light::ColorCapability::COLD_WARM_WHITE));
  bool on = this->light_->remote_values.is_on();
  float brightness = this->light_->remote_values.get_brightness();
  auto level = conversion::to_matter::brightness(brightness);
  uint16_t color_x = 0;
  uint16_t color_y = 0;
  if (has_color &&
      !conversion::to_matter::color(values.get_red(), values.get_green(),
                                    values.get_blue(), color_x, color_y))
    has_color = false;
  auto color_temperature = conversion::to_matter::color_temperature(
      this->light_->remote_values.get_color_temperature());
  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [eid, has_level, has_color, has_color_temperature, on, level, color_x,
       color_y, color_temperature]() {
        using namespace chip::app::Clusters;
        esp_matter_attr_val_t on_val = esp_matter_bool(on);
        esp_matter::attribute::report(eid, OnOff::Id,
                                      OnOff::Attributes::OnOff::Id, &on_val);
        if (has_level) {
          esp_matter_attr_val_t level_val =
              esp_matter_nullable_uint8(nullable<uint8_t>(level));
          esp_matter::attribute::report(
              eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id,
              &level_val);
        }
        if (has_color) {
          esp_matter_attr_val_t x_val = esp_matter_uint16(color_x);
          esp_matter::attribute::report(eid, ColorControl::Id,
                                        ColorControl::Attributes::CurrentX::Id,
                                        &x_val);
          esp_matter_attr_val_t y_val = esp_matter_uint16(color_y);
          esp_matter::attribute::report(eid, ColorControl::Id,
                                        ColorControl::Attributes::CurrentY::Id,
                                        &y_val);
          esp_matter_attr_val_t color_mode_val =
              esp_matter_enum8(static_cast<uint8_t>(
                  ColorControl::ColorModeEnum::kCurrentXAndCurrentY));
          esp_matter::attribute::report(eid, ColorControl::Id,
                                        ColorControl::Attributes::ColorMode::Id,
                                        &color_mode_val);
          esp_matter::attribute::report(
              eid, ColorControl::Id,
              ColorControl::Attributes::EnhancedColorMode::Id, &color_mode_val);
        }
        if (has_color_temperature) {
          esp_matter_attr_val_t color_temperature_val =
              esp_matter_uint16(color_temperature);
          esp_matter::attribute::report(
              eid, ColorControl::Id,
              ColorControl::Attributes::ColorTemperatureMireds::Id,
              &color_temperature_val);
          esp_matter_attr_val_t color_mode_val =
              esp_matter_enum8(static_cast<uint8_t>(
                  ColorControl::ColorModeEnum::kColorTemperatureMireds));
          esp_matter::attribute::report(eid, ColorControl::Id,
                                        ColorControl::Attributes::ColorMode::Id,
                                        &color_mode_val);
          esp_matter::attribute::report(
              eid, ColorControl::Id,
              ColorControl::Attributes::EnhancedColorMode::Id, &color_mode_val);
        }
      });
}

// Set "static" attribute values at startup such as hardware capabilities of the
// light.
void MatterLightMapping::initialize_matter_attributes_() {
  if (this->capabilities_.color_temperature_range.has_value()) {
    using namespace chip::app::Clusters;
    uint16_t endpoint_id = this->endpoint_id();
    const auto &range = *this->capabilities_.color_temperature_range;
    esp_matter_attr_val_t min_value = esp_matter_uint16(range.min_mireds);
    esp_matter::attribute::report(
        endpoint_id, ColorControl::Id,
        ColorControl::Attributes::ColorTempPhysicalMinMireds::Id, &min_value);
    esp_matter_attr_val_t max_value = esp_matter_uint16(range.max_mireds);
    esp_matter::attribute::report(
        endpoint_id, ColorControl::Id,
        ColorControl::Attributes::ColorTempPhysicalMaxMireds::Id, &max_value);
  }
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
  float brightness = conversion::from_matter::brightness(level);
  if (std::fabs(this->light_->remote_values.get_brightness() - brightness) <
      (0.5f / 254.0f)) {
    return;
  }
  auto call = this->light_->make_call();
  call.set_brightness(brightness);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

void MatterLightMapping::apply_color_temperature_(uint16_t color_temperature) {
  if (std::fabs(this->light_->remote_values.get_color_temperature() -
                color_temperature) < 0.5f) {
    return;
  }
  auto call = this->light_->make_call();
  call.set_color_temperature(color_temperature);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

void MatterLightMapping::apply_color_(uint16_t x, uint16_t y) {
  float red;
  float green;
  float blue;
  if (!conversion::from_matter::color(x, y, red, green, blue)) {
    ESP_LOGW(TAG, "Failed to convert Matter xy color: endpoint=%u, x=%u, y=%u",
             this->endpoint_id(), x, y);
    return;
  }
  auto call = this->light_->make_call();
  call.set_rgb(red, green, blue);
  call.set_transition_length(0);
  this->synchronizing_from_matter_ = true;
  call.perform();
  this->synchronizing_from_matter_ = false;
}

// The color mode should always update before the mireds or current_x or
// current_y attributes. But just in case, replay the colour state attributes
// updates for when the mode attribute is updated later.
void MatterLightMapping::apply_color_mode_(uint8_t color_mode) {
  using namespace chip::app::Clusters;
  auto mode = static_cast<ColorControl::ColorModeEnum>(color_mode);
  if (mode == ColorControl::ColorModeEnum::kCurrentXAndCurrentY &&
      this->capabilities_.has_color) {
    global_matter_component->replay_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::CurrentX::Id);
    global_matter_component->replay_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::CurrentY::Id);
  } else if (mode == ColorControl::ColorModeEnum::kColorTemperatureMireds &&
             this->capabilities_.color_temperature_range.has_value()) {
    global_matter_component->replay_attribute_callback(
        this->endpoint_id(), ColorControl::Id,
        ColorControl::Attributes::ColorTemperatureMireds::Id);
  }
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_LIGHT
