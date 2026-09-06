#include "matter_sensor_converters.h"

#ifdef USE_MATTER

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace esphome::matter::sensor_converter {

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

esp_matter_attr_val_t amperes_to_milliamperes(float value) {
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

esp_matter_attr_val_t percent_to_hundredths(float value) {
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

esp_matter_attr_val_t volts_to_millivolts(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

esp_matter_attr_val_t watts_to_milliwatts(float value) {
  return nullable_int64_scaled(value, 1000.0f);
}

} // namespace esphome::matter::sensor_converter

#endif // USE_MATTER
