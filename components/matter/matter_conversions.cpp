#include "matter_conversions.h"

#ifdef USE_MATTER

#include <algorithm>
#include <cmath>
#include <limits>

namespace esphome::matter::conversion {

namespace {

esp_matter_attr_val_t nullable_int64_scaled(float value, float multiplier) {
  nullable<int64_t> converted;
  double scaled = static_cast<double>(value) * multiplier;
  if (std::isfinite(scaled) &&
      scaled >= static_cast<double>(std::numeric_limits<int64_t>::min()) &&
      scaled <= static_cast<double>(std::numeric_limits<int64_t>::max())) {
    converted = static_cast<int64_t>(std::llround(scaled));
  }
  return esp_matter_nullable_int64(converted);
}

} // namespace

bool convert_attribute_value(const esp_matter_attr_val_t &value, bool &out) {
  if (value.get_base_type() != ESP_MATTER_VAL_TYPE_BOOLEAN)
    return false;
  out = value.val.b;
  return true;
}

bool convert_attribute_value(const esp_matter_attr_val_t &value, float &out) {
  if (value.get_base_type() != ESP_MATTER_VAL_TYPE_FLOAT)
    return false;
  out = value.val.f;
  return true;
}

bool convert_attribute_value(const esp_matter_attr_val_t &value, int64_t &out) {
  switch (value.get_base_type()) {
  case ESP_MATTER_VAL_TYPE_INT8:
    out = value.val.i8;
    return true;
  case ESP_MATTER_VAL_TYPE_INT16:
    out = value.val.i16;
    return true;
  case ESP_MATTER_VAL_TYPE_INT32:
    out = value.val.i32;
    return true;
  case ESP_MATTER_VAL_TYPE_INT64:
    out = value.val.i64;
    return true;
  default:
    return false;
  }
}

bool convert_attribute_value(const esp_matter_attr_val_t &value,
                             uint64_t &out) {
  switch (value.get_base_type()) {
  case ESP_MATTER_VAL_TYPE_UINT8:
  case ESP_MATTER_VAL_TYPE_ENUM8:
  case ESP_MATTER_VAL_TYPE_BITMAP8:
    out = value.val.u8;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT16:
  case ESP_MATTER_VAL_TYPE_ENUM16:
  case ESP_MATTER_VAL_TYPE_BITMAP16:
    out = value.val.u16;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT32:
  case ESP_MATTER_VAL_TYPE_BITMAP32:
    out = value.val.u32;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT64:
    out = value.val.u64;
    return true;
  default:
    return false;
  }
}

bool convert_attribute_value(const esp_matter_attr_val_t &value,
                             std::string &out) {
  auto type = value.get_base_type();
  if (type != ESP_MATTER_VAL_TYPE_CHAR_STRING &&
      type != ESP_MATTER_VAL_TYPE_LONG_CHAR_STRING)
    return false;
  out.assign(reinterpret_cast<const char *>(value.val.a.b), value.val.a.s);
  return true;
}

esp_matter_attr_val_t ampere(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

esp_matter_attr_val_t boolean_state(bool value) {
  return esp_matter_bool(value);
}

esp_matter_attr_val_t concentration(float value) {
  nullable<float> converted;
  if (std::isfinite(value))
    converted = value;
  return esp_matter_nullable_float(converted);
}

esp_matter_attr_val_t flow(float value) {
  nullable<uint16_t> converted;
  float scaled = value * 10.0f;
  if (std::isfinite(scaled) && scaled >= 0.0f && scaled <= 65534.0f)
    converted = static_cast<uint16_t>(std::lround(scaled));
  return esp_matter_nullable_uint16(converted);
}

esp_matter_attr_val_t frequency(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

esp_matter_attr_val_t illuminance(float value) {
  nullable<uint16_t> converted;
  if (std::isfinite(value) && value >= 0.0f) {
    uint16_t measured_value = 0;
    if (value > 0.0f) {
      float encoded = 10000.0f * std::log10(value) + 1.0f;
      encoded = std::max(encoded, 1.0f);
      encoded = std::min(encoded, 65534.0f);
      measured_value = static_cast<uint16_t>(std::lround(encoded));
    }
    converted = measured_value;
  }
  return esp_matter_nullable_uint16(converted);
}

esp_matter_attr_val_t occupancy(bool value) {
  return esp_matter_bitmap8(value ? 1 : 0);
}

esp_matter_attr_val_t percentage(float value) {
  nullable<uint16_t> converted;
  if (std::isfinite(value) && value >= 0.0f && value <= 100.0f) {
    converted = static_cast<uint16_t>(std::lround(value * 100.0f));
  }
  return esp_matter_nullable_uint16(converted);
}

esp_matter_attr_val_t pressure(float value) {
  nullable<int16_t> converted;
  if (std::isfinite(value) && value >= -32768.0f && value <= 32767.0f)
    converted = static_cast<int16_t>(std::lround(value));
  return esp_matter_nullable_int16(converted);
}

esp_matter_attr_val_t temperature(float value) {
  nullable<int16_t> converted;
  float scaled = value * 100.0f;
  if (std::isfinite(scaled) && scaled >= -27315.0f && scaled <= 32767.0f)
    converted = static_cast<int16_t>(std::lround(scaled));
  return esp_matter_nullable_int16(converted);
}

esp_matter_attr_val_t volts(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

esp_matter_attr_val_t watts(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

namespace to_matter {

uint8_t brightness(float brightness) {
  auto level = static_cast<uint8_t>(std::lroundf(brightness * 254.0f));
  return level < 1 ? 1 : level;
}

// ESPHome uses normalized RGB channel values while Matter uses CIE xy. Use
// chromaticity only because brightness is represented by Level Control.
bool color(float red, float green, float blue, uint16_t &matter_x,
           uint16_t &matter_y) {
  auto gamma_decode = [](float channel) {
    channel = std::clamp(channel, 0.0f, 1.0f);
    return channel <= 0.04045f ? channel / 12.92f
                               : std::pow((channel + 0.055f) / 1.055f, 2.4f);
  };
  red = gamma_decode(red);
  green = gamma_decode(green);
  blue = gamma_decode(blue);

  float cie_x = 0.4124f * red + 0.3576f * green + 0.1805f * blue;
  float cie_y = 0.2126f * red + 0.7152f * green + 0.0722f * blue;
  float cie_z = 0.0193f * red + 0.1192f * green + 0.9505f * blue;
  float sum = cie_x + cie_y + cie_z;
  if (sum <= 0.0f)
    return false;

  matter_x = static_cast<uint16_t>(
      std::lroundf(std::clamp(cie_x / sum * 65536.0f, 0.0f, 65279.0f)));
  matter_y = static_cast<uint16_t>(
      std::lroundf(std::clamp(cie_y / sum * 65536.0f, 0.0f, 65279.0f)));
  return true;
}

// ESPHome and Matter both use mireds for color temperature, but ESPHome uses
// floating-point values while Matter uses integers.
uint16_t color_temperature(float color_temperature) {
  return static_cast<uint16_t>(
      std::lroundf(std::clamp(color_temperature, 1.0f, 65279.0f)));
}

} // namespace to_matter

namespace from_matter {

float brightness(uint8_t level) { return level / 254.0f; }

// Matter uses CIE xy while ESPHome uses normalized RGB channel values. Use
// unit luminance because brightness is represented by Level Control.
bool color(uint16_t matter_x, uint16_t matter_y, float &red, float &green,
           float &blue) {
  float x = matter_x / 65536.0f;
  float y = matter_y / 65536.0f;
  if (y <= 0.0f || x + y > 1.0f)
    return false;

  float cie_x = x / y;
  float cie_y = 1.0f;
  float cie_z = (1.0f - x - y) / y;
  red = 3.2406f * cie_x - 1.5372f * cie_y - 0.4986f * cie_z;
  green = -0.9689f * cie_x + 1.8758f * cie_y + 0.0415f * cie_z;
  blue = 0.0557f * cie_x - 0.2040f * cie_y + 1.0570f * cie_z;

  red = std::max(red, 0.0f);
  green = std::max(green, 0.0f);
  blue = std::max(blue, 0.0f);
  if (std::max({red, green, blue}) <= 0.0f)
    return false;

  auto gamma_encode = [](float channel) {
    return channel <= 0.0031308f
               ? 12.92f * channel
               : 1.055f * std::pow(channel, 1.0f / 2.4f) - 0.055f;
  };
  red = gamma_encode(red);
  green = gamma_encode(green);
  blue = gamma_encode(blue);
  float maximum = std::max({red, green, blue});
  if (maximum > 1.0f) {
    red /= maximum;
    green /= maximum;
    blue /= maximum;
  }
  return true;
}

} // namespace from_matter

} // namespace esphome::matter::conversion

#endif // USE_MATTER
