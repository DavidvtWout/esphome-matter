#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_endpoints.h"
#include "matter_sensor_converters.h"

#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif

namespace esphome::matter {

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
#endif

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
#endif

} // namespace esphome::matter

#endif // USE_MATTER
