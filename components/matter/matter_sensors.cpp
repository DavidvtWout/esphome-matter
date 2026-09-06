#include "matter_sensors.h"

#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_component.h"

#include <platform/CHIPDeviceLayer.h>

#include <algorithm>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <limits>

namespace esphome::matter {

static const char *const TAG = "matter.sensor";

namespace sensor_converter {

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

} // namespace sensor_converter

namespace {

struct AttributeUpdate {
  uint16_t endpoint_id;
  uint32_t cluster_id;
  uint32_t attribute_id;
  esp_matter_attr_val_t value;
};

void update_attribute_on_matter_thread(intptr_t context) {
  auto *update = reinterpret_cast<AttributeUpdate *>(context);
  esp_err_t err =
      esp_matter::attribute::update(update->endpoint_id, update->cluster_id,
                                    update->attribute_id, &update->value);
  if (err != ESP_OK) {
    ESP_LOGE(TAG,
             "Failed to update attribute 0x%08" PRIX32
             " on cluster 0x%08" PRIX32 ", endpoint %u: %s",
             update->attribute_id, update->cluster_id, update->endpoint_id,
             esp_err_to_name(err));
  }
  delete update;
}

void update_attribute(uint16_t endpoint_id, uint32_t cluster_id,
                      uint32_t attribute_id,
                      esp_matter_attr_val_t attribute_value) {
  auto *update = new AttributeUpdate{endpoint_id, cluster_id, attribute_id,
                                     attribute_value};
  CHIP_ERROR err = chip::DeviceLayer::PlatformMgr().ScheduleWork(
      update_attribute_on_matter_thread, reinterpret_cast<intptr_t>(update));
  if (err != CHIP_NO_ERROR) {
    ESP_LOGE(TAG, "Failed to schedule Matter attribute update: %s",
             err.AsString());
    delete update;
  }
}

} // namespace

#ifdef USE_SENSOR
void MatterComponent::register_sensor_attribute(
    sensor::Sensor *sensor, uint16_t endpoint_id, uint32_t cluster_id,
    uint32_t attribute_id, SensorValueConverter converter) {
  this->mappings_.push_back(new MatterSensorAttributeMapping(
      sensor, endpoint_id, cluster_id, attribute_id, converter));
}

MatterSensorAttributeMapping::MatterSensorAttributeMapping(
    sensor::Sensor *sensor, uint16_t endpoint_id, uint32_t cluster_id,
    uint32_t attribute_id, SensorValueConverter converter)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor),
      cluster_id_(cluster_id), attribute_id_(attribute_id),
      converter_(converter) {}

void MatterSensorAttributeMapping::register_callbacks() {
  if (this->sensor_ == nullptr || this->converter_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](float value) { this->publish_(value); });
  if (this->sensor_->has_state())
    this->publish_(this->sensor_->state);
}

void MatterSensorAttributeMapping::publish_(float value) {
  update_attribute(this->endpoint_id_, this->cluster_id_, this->attribute_id_,
                   this->converter_(value));
}
#endif // USE_SENSOR

#ifdef USE_BINARY_SENSOR
void MatterComponent::register_binary_sensor_attribute(
    binary_sensor::BinarySensor *sensor, uint16_t endpoint_id,
    uint32_t cluster_id, uint32_t attribute_id,
    BinarySensorValueConverter converter) {
  this->mappings_.push_back(new MatterBinarySensorAttributeMapping(
      sensor, endpoint_id, cluster_id, attribute_id, converter));
}

MatterBinarySensorAttributeMapping::MatterBinarySensorAttributeMapping(
    binary_sensor::BinarySensor *sensor, uint16_t endpoint_id,
    uint32_t cluster_id, uint32_t attribute_id,
    BinarySensorValueConverter converter)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor),
      cluster_id_(cluster_id), attribute_id_(attribute_id),
      converter_(converter) {}

void MatterBinarySensorAttributeMapping::register_callbacks() {
  if (this->sensor_ == nullptr || this->converter_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](bool value) { this->publish_(value); });
  if (this->sensor_->has_state())
    this->publish_(this->sensor_->state);
}

void MatterBinarySensorAttributeMapping::publish_(bool value) {
  update_attribute(this->endpoint_id_, this->cluster_id_, this->attribute_id_,
                   this->converter_(value));
}
#endif // USE_BINARY_SENSOR

} // namespace esphome::matter

#endif // USE_MATTER
