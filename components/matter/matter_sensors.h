#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_endpoints.h"

#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif // USE_BINARY_SENSOR
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif // USE_SENSOR

namespace esphome::matter {

namespace sensor_converter {

esp_matter_attr_val_t ampere(float value);
esp_matter_attr_val_t boolean_state(bool value);
esp_matter_attr_val_t concentration(float value);
esp_matter_attr_val_t flow(float value);
esp_matter_attr_val_t frequency(float value);
esp_matter_attr_val_t illuminance(float value);
esp_matter_attr_val_t occupancy(bool value);
esp_matter_attr_val_t percentage(float value);
esp_matter_attr_val_t pressure(float value);
esp_matter_attr_val_t temperature(float value);
esp_matter_attr_val_t volts(float value);
esp_matter_attr_val_t watts(float value);

} // namespace sensor_converter

using SensorValueConverter = esp_matter_attr_val_t (*)(float);
using BinarySensorValueConverter = esp_matter_attr_val_t (*)(bool);

#ifdef USE_SENSOR
class MatterSensorAttributeMapping : public MatterEndpointMappingBase {
public:
  MatterSensorAttributeMapping(sensor::Sensor *sensor, uint16_t endpoint_id,
                               uint32_t cluster_id, uint32_t attribute_id,
                               SensorValueConverter converter);

  void register_callbacks() override;

protected:
  void publish_(float value);

  sensor::Sensor *sensor_;
  uint32_t cluster_id_;
  uint32_t attribute_id_;
  SensorValueConverter converter_;
};
#endif // USE_SENSOR

#ifdef USE_BINARY_SENSOR
class MatterBinarySensorAttributeMapping : public MatterEndpointMappingBase {
public:
  MatterBinarySensorAttributeMapping(binary_sensor::BinarySensor *sensor,
                                     uint16_t endpoint_id, uint32_t cluster_id,
                                     uint32_t attribute_id,
                                     BinarySensorValueConverter converter);

  void register_callbacks() override;

protected:
  void publish_(bool value);

  binary_sensor::BinarySensor *sensor_;
  uint32_t cluster_id_;
  uint32_t attribute_id_;
  BinarySensorValueConverter converter_;
};
#endif // USE_BINARY_SENSOR

} // namespace esphome::matter

#endif // USE_MATTER
