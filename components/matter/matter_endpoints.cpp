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
    esp_matter::endpoint::on_off_light_switch::config_t sw_config;
    esp_matter::endpoint_t *ep =
        esp_matter::endpoint::on_off_light_switch::create(node, &sw_config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
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

    // Physical colour-temperature limits come from the ESPHome light itself, so
    // controllers never offer a range the hardware cannot reach. ESPHome and
    // Matter both express colour temperature in mireds, so no conversion here.
    const auto &traits = ml->light->get_traits();
    uint16_t min_mireds = 1;
    uint16_t max_mireds = 0xfeff;
    if (ml->has_color_temperature() && traits.get_min_mireds() > 0 && traits.get_max_mireds() > 0) {
      min_mireds = static_cast<uint16_t>(std::lroundf(traits.get_min_mireds()));
      max_mireds = static_cast<uint16_t>(std::lroundf(traits.get_max_mireds()));
    }

    switch (ml->type) {
      case MatterLightType::ON_OFF: {
        esp_matter::endpoint::on_off_light::config_t cfg;
        ep = esp_matter::endpoint::on_off_light::create(node, &cfg, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
        break;
      }
      case MatterLightType::DIMMABLE: {
        esp_matter::endpoint::dimmable_light::config_t cfg;
        ep = esp_matter::endpoint::dimmable_light::create(node, &cfg, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
        break;
      }
      case MatterLightType::COLOR_TEMPERATURE: {
        esp_matter::endpoint::color_temperature_light::config_t cfg;
        // ColorMode 2 / EnhancedColorMode 2 = ColorTemperatureMireds.
        cfg.color_control.color_mode = 2;
        cfg.color_control.enhanced_color_mode = 2;
        cfg.color_control_color_temperature.color_temp_physical_min_mireds = min_mireds;
        cfg.color_control_color_temperature.color_temp_physical_max_mireds = max_mireds;
        cfg.color_control_color_temperature.couple_color_temp_to_level_min_mireds = min_mireds;
        ep = esp_matter::endpoint::color_temperature_light::create(node, &cfg, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
        break;
      }
      case MatterLightType::EXTENDED_COLOR: {
        esp_matter::endpoint::extended_color_light::config_t cfg;
        // ColorMode 0 / EnhancedColorMode 0 = CurrentHue + CurrentSaturation.
        cfg.color_control.color_mode = 0;
        cfg.color_control.enhanced_color_mode = 0;
        cfg.color_control_color_temperature.color_temp_physical_min_mireds = min_mireds;
        cfg.color_control_color_temperature.color_temp_physical_max_mireds = max_mireds;
        cfg.color_control_color_temperature.couple_color_temp_to_level_min_mireds = min_mireds;
        ep = esp_matter::endpoint::extended_color_light::create(node, &cfg, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
        // extended_color_light ships XY and ColorTemperature; HueSaturation is
        // an optional feature and must be added explicitly.
        if (ep != nullptr) {
          esp_matter::cluster_t *cc =
              esp_matter::cluster::get(ep, chip::app::Clusters::ColorControl::Id);
          if (cc != nullptr) {
            esp_matter::cluster::color_control::feature::hue_saturation::config_t hs_cfg;
            esp_matter::cluster::color_control::feature::hue_saturation::add(cc, &hs_cfg);
          } else {
            ESP_LOGE(TAG, "ColorControl cluster missing on extended_color_light endpoint");
            return false;
          }
        }
        break;
      }
    }

    if (ep == nullptr) {
      ESP_LOGE(TAG, "Failed to create %s endpoint", ml->type_name());
      return false;
    }
    ml->endpoint_id = esp_matter::endpoint::get_id(ep);
    ml->ref->endpoint_id = ml->endpoint_id;
    ESP_LOGD(TAG, "%s endpoint created: id=%u", ml->type_name(), ml->endpoint_id);
  }
#endif

  if (!this->on_off_switches_.empty() || !this->dimmer_switches_.empty()) {
    register_client_request_callbacks();
  }

  return true;
}

#ifdef USE_LIGHT

const char *MatterLight::type_name() const {
  switch (this->type) {
    case MatterLightType::ON_OFF:
      return "on_off_light";
    case MatterLightType::DIMMABLE:
      return "dimmable_light";
    case MatterLightType::COLOR_TEMPERATURE:
      return "color_temperature_light";
    case MatterLightType::EXTENDED_COLOR:
      return "extended_color_light";
  }
  return "light";
}

namespace {

// Matter carries hue as 0..254 over 360 degrees and saturation as 0..254 over
// full scale. ESPHome stores colour as normalised RGB, so both directions need
// an explicit conversion; neither library exposes one we can rely on.
void rgb_to_matter_hs(float r, float g, float b, uint8_t *hue_out, uint8_t *sat_out) {
  const float max_c = std::fmax(r, std::fmax(g, b));
  const float min_c = std::fmin(r, std::fmin(g, b));
  const float delta = max_c - min_c;

  float hue_deg = 0.0f;
  if (delta > 1e-6f) {
    if (max_c == r) {
      hue_deg = 60.0f * std::fmod((g - b) / delta, 6.0f);
    } else if (max_c == g) {
      hue_deg = 60.0f * (((b - r) / delta) + 2.0f);
    } else {
      hue_deg = 60.0f * (((r - g) / delta) + 4.0f);
    }
  }
  if (hue_deg < 0.0f)
    hue_deg += 360.0f;

  const float sat = (max_c <= 1e-6f) ? 0.0f : (delta / max_c);

  long hue_raw = std::lroundf(hue_deg * 254.0f / 360.0f);
  if (hue_raw > 254)
    hue_raw = 254;
  if (hue_raw < 0)
    hue_raw = 0;
  long sat_raw = std::lroundf(sat * 254.0f);
  if (sat_raw > 254)
    sat_raw = 254;
  if (sat_raw < 0)
    sat_raw = 0;

  *hue_out = static_cast<uint8_t>(hue_raw);
  *sat_out = static_cast<uint8_t>(sat_raw);
}

// Matter has no white channel. On a light with a dedicated white element the
// RGB triple carries the hue and ESPHome's color_brightness / white pair carries
// how much of the output is coloured versus white, so saturation has to account
// for both. A light with no white element reports color_brightness 1 and white
// 0, which leaves the result identical to rgb_to_matter_hs.
void light_to_matter_hs(const light::LightColorValues &values, bool has_white, uint8_t *hue_out,
                        uint8_t *sat_out) {
  rgb_to_matter_hs(values.get_red(), values.get_green(), values.get_blue(), hue_out, sat_out);
  if (!has_white)
    return;
  const float cb = values.get_color_brightness();
  const float w = values.get_white();
  const float denom = cb + w;
  if (denom <= 1e-6f)
    return;  // nothing lit; leave the RGB-derived saturation alone
  long sat_raw = std::lroundf(static_cast<float>(*sat_out) * (cb / denom));
  if (sat_raw > 254)
    sat_raw = 254;
  if (sat_raw < 0)
    sat_raw = 0;
  *sat_out = static_cast<uint8_t>(sat_raw);
}

// Value is fixed at 1.0: Matter keeps brightness in LevelControl, separate from
// the hue/saturation pair, so folding it in here would double-apply it.
void matter_hs_to_rgb(uint8_t hue_raw, uint8_t sat_raw, float *r, float *g, float *b) {
  const float h = (static_cast<float>(hue_raw) * 360.0f / 254.0f);
  const float s = static_cast<float>(sat_raw) / 254.0f;
  const float c = s;
  const float x = c * (1.0f - std::fabs(std::fmod(h / 60.0f, 2.0f) - 1.0f));
  const float m = 1.0f - c;

  float rr = 0.0f, gg = 0.0f, bb = 0.0f;
  if (h < 60.0f) {
    rr = c; gg = x; bb = 0.0f;
  } else if (h < 120.0f) {
    rr = x; gg = c; bb = 0.0f;
  } else if (h < 180.0f) {
    rr = 0.0f; gg = c; bb = x;
  } else if (h < 240.0f) {
    rr = 0.0f; gg = x; bb = c;
  } else if (h < 300.0f) {
    rr = x; gg = 0.0f; bb = c;
  } else {
    rr = c; gg = 0.0f; bb = x;
  }
  *r = rr + m;
  *g = gg + m;
  *b = bb + m;
}

}  // namespace

// Mirrors the current ESPHome light state to the Matter attributes.
// Runs on the main loop; the attribute writes hop to the Matter thread.
void MatterLight::push_state_to_matter() {
  // Suppress the echo: this state change originated from Matter.
  if (this->applying_from_matter_)
    return;

  uint16_t eid = this->endpoint_id;
  bool dim = this->dimmable();
  bool do_ct = this->has_color_temperature();
  bool do_hs = this->has_hue_saturation();

  const auto &values = this->light->remote_values;
  bool on = values.is_on();
  auto level = static_cast<uint8_t>(std::lroundf(values.get_brightness() * 254.0f));
  level = level < 1 ? 1 : level;

  uint8_t hue = 0, sat = 0;
  if (do_hs)
    light_to_matter_hs(values, this->has_white_channel(), &hue, &sat);

  // ESPHome and Matter both use mireds. A light reporting 0 has no valid
  // colour temperature yet, so leave the attribute alone rather than write junk.
  float ct_mireds = values.get_color_temperature();
  bool ct_valid = do_ct && ct_mireds > 0.0f && std::isfinite(ct_mireds);
  auto ct = static_cast<uint16_t>(std::lroundf(ct_mireds));

  // Report which mode the light is actually in, or controllers show stale
  // colour after a colour-temperature change (and vice versa).
  bool in_ct_mode = values.get_color_mode() == light::ColorMode::COLOR_TEMPERATURE;
  auto color_mode = static_cast<uint8_t>(in_ct_mode ? 2 : 0);

  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [eid, dim, do_ct, do_hs, on, level, hue, sat, ct, ct_valid, color_mode]() {
        using namespace chip::app::Clusters;
        esp_matter_attr_val_t on_val = esp_matter_bool(on);
        esp_matter::attribute::update(eid, OnOff::Id, OnOff::Attributes::OnOff::Id, &on_val);
        if (dim) {
          esp_matter_attr_val_t level_val = esp_matter_nullable_uint8(nullable<uint8_t>(level));
          esp_matter::attribute::update(eid, LevelControl::Id, LevelControl::Attributes::CurrentLevel::Id, &level_val);
        }
        if (do_hs) {
          esp_matter_attr_val_t hue_val = esp_matter_uint8(hue);
          esp_matter::attribute::update(eid, ColorControl::Id, ColorControl::Attributes::CurrentHue::Id, &hue_val);
          esp_matter_attr_val_t sat_val = esp_matter_uint8(sat);
          esp_matter::attribute::update(eid, ColorControl::Id, ColorControl::Attributes::CurrentSaturation::Id,
                                        &sat_val);
        }
        if (do_ct && ct_valid) {
          esp_matter_attr_val_t ct_val = esp_matter_uint16(ct);
          esp_matter::attribute::update(eid, ColorControl::Id, ColorControl::Attributes::ColorTemperatureMireds::Id,
                                        &ct_val);
        }
        if (do_ct || do_hs) {
          esp_matter_attr_val_t mode_val = esp_matter_enum8(color_mode);
          esp_matter::attribute::update(eid, ColorControl::Id, ColorControl::Attributes::ColorMode::Id, &mode_val);
          esp_matter_attr_val_t emode_val = esp_matter_enum8(color_mode);
          esp_matter::attribute::update(eid, ColorControl::Id, ColorControl::Attributes::EnhancedColorMode::Id,
                                        &emode_val);
        }
      });
}

// Applies a Matter-side attribute change to the ESPHome light. Runs on the
// main loop (deferred from the Matter thread). Values that already match the
// light's state are ignored, which also breaks the mirror echo loop.
void MatterLight::apply_matter_update(uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t val) {
  using namespace chip::app::Clusters;

  // Guards the whole apply: any ESPHome state callback raised while this runs
  // is a consequence of the Matter write, not a new local change.
  struct EchoGuard {
    bool &flag;
    explicit EchoGuard(bool &f) : flag(f) { flag = true; }
    ~EchoGuard() { flag = false; }
  };

  if (cluster_id == OnOff::Id && attribute_id == OnOff::Attributes::OnOff::Id) {
    bool on = val.val.b;
    if (this->light->remote_values.is_on() == on)
      return;
    EchoGuard guard(this->applying_from_matter_);
    auto call = this->light->make_call();
    call.set_state(on);
    // The Matter side already ramps CurrentLevel during transitions; a second
    // ESPHome-side transition would double-smooth every change.
    call.set_transition_length(0);
    call.perform();
  } else if (this->dimmable() && cluster_id == LevelControl::Id &&
             attribute_id == LevelControl::Attributes::CurrentLevel::Id) {
    uint8_t level = val.val.u8;
    if (level < 1 || level > 254)
      return;  // null or out of spec range
    float brightness = level / 254.0f;
    if (std::fabs(this->light->remote_values.get_brightness() - brightness) < (0.5f / 254.0f))
      return;
    EchoGuard guard(this->applying_from_matter_);
    auto call = this->light->make_call();
    call.set_brightness(brightness);
    call.set_transition_length(0);
    call.perform();
  } else if (this->has_hue_saturation() && cluster_id == ColorControl::Id &&
             (attribute_id == ColorControl::Attributes::CurrentHue::Id ||
              attribute_id == ColorControl::Attributes::CurrentSaturation::Id)) {
    // Hue and saturation arrive as separate attribute writes. Read the current
    // pair and replace only the one that changed, or setting hue would reset
    // saturation to whatever the last RGB round-trip happened to produce.
    const bool has_white = this->has_white_channel();
    uint8_t hue = 0, sat = 0;
    light_to_matter_hs(this->light->remote_values, has_white, &hue, &sat);
    if (attribute_id == ColorControl::Attributes::CurrentHue::Id) {
      if (hue == val.val.u8)
        return;
      hue = val.val.u8;
    } else {
      if (sat == val.val.u8)
        return;
      sat = val.val.u8;
    }
    // On a light with a white element, desaturation is rendered by the white
    // LED rather than by washing the RGB triple out to grey: the triple stays at
    // the pure hue and the colour/white split carries the saturation. Without a
    // white element the saturation is folded into the RGB triple as before.
    float r, g, b;
    matter_hs_to_rgb(hue, has_white ? 254 : sat, &r, &g, &b);
    EchoGuard guard(this->applying_from_matter_);
    auto call = this->light->make_call();
    const auto &traits = this->light->get_traits();
    if (traits.supports_color_mode(light::ColorMode::RGB_COLOR_TEMPERATURE) ||
        traits.supports_color_mode(light::ColorMode::RGB_WHITE) ||
        traits.supports_color_mode(light::ColorMode::RGB)) {
      call.set_rgb(r, g, b);
    }
    if (has_white) {
      const float sat_f = static_cast<float>(sat) / 254.0f;
      call.set_color_mode_if_supported(light::ColorMode::RGB_WHITE);
      call.set_color_brightness_if_supported(sat_f);
      call.set_white_if_supported(1.0f - sat_f);
    }
    call.set_transition_length(0);
    call.perform();
  } else if (this->has_color_temperature() && cluster_id == ColorControl::Id &&
             attribute_id == ColorControl::Attributes::ColorTemperatureMireds::Id) {
    // Silently ignored rather than treated as an error: extended_color_light
    // must advertise ColorTemperature, but the ESPHome light behind it may have
    // no COLOR_TEMPERATURE capability at all.
    if (!this->light->get_traits().supports_color_capability(light::ColorCapability::COLOR_TEMPERATURE))
      return;
    auto mireds = static_cast<float>(val.val.u16);
    if (mireds <= 0.0f)
      return;
    const auto &traits = this->light->get_traits();
    if (mireds < traits.get_min_mireds())
      mireds = traits.get_min_mireds();
    if (mireds > traits.get_max_mireds())
      mireds = traits.get_max_mireds();
    if (std::fabs(this->light->remote_values.get_color_temperature() - mireds) < 0.5f)
      return;
    EchoGuard guard(this->applying_from_matter_);
    auto call = this->light->make_call();
    call.set_color_temperature(mireds);
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
