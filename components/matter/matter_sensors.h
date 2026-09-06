#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_endpoints.h"

#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif // USE_BINARY_SENSOR
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#include <data_model_provider/esp_matter_data_model_provider.h>
#include <type_traits>
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
using SensorAttributeUpdater = CHIP_ERROR (*)(uint16_t, uint32_t,
                                              esp_matter_attr_val_t);

template <
    typename ClusterT, typename ValueT,
    CHIP_ERROR (ClusterT::*Setter)(chip::app::DataModel::Nullable<ValueT>)>
CHIP_ERROR update_code_driven_sensor_attribute(uint16_t endpoint_id,
                                               uint32_t cluster_id,
                                               esp_matter_attr_val_t value) {
  auto *server =
      esp_matter::data_model::provider::get_instance().registry().Get(
          {endpoint_id, cluster_id});
  if (server == nullptr)
    return CHIP_ERROR_NOT_FOUND;

  chip::app::DataModel::Nullable<ValueT> converted;
  if (!value.is_null()) {
    if constexpr (std::is_same_v<ValueT, int16_t>)
      converted.SetNonNull(value.val.i16);
    else if constexpr (std::is_same_v<ValueT, uint16_t>)
      converted.SetNonNull(value.val.u16);
  }
  return (static_cast<ClusterT *>(server)->*Setter)(converted);
}

class MatterSensorAttributeMapping : public MatterEndpointMappingBase {
public:
  MatterSensorAttributeMapping(sensor::Sensor *sensor, uint16_t endpoint_id,
                               uint32_t cluster_id, uint32_t attribute_id,
                               SensorValueConverter converter,
                               SensorAttributeUpdater updater = nullptr);

  void register_callbacks() override;

protected:
  void publish_(float value);

  sensor::Sensor *sensor_;
  uint32_t cluster_id_;
  uint32_t attribute_id_;
  SensorValueConverter converter_;
  SensorAttributeUpdater updater_;
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
