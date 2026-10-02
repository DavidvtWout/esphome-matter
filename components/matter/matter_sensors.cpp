#include "matter_sensors.h"

#if defined(USE_MATTER) && (defined(USE_SENSOR) || defined(USE_BINARY_SENSOR))

#include "esphome/core/log.h"
#include "matter_component.h"

#include <app/clusters/boolean-state-server/BooleanStateCluster.h>
#include <platform/CHIPDeviceLayer.h>

#include <cinttypes>
#include <cstdint>

namespace esphome::matter {

static const char *const TAG = "matter.sensor";

namespace {

struct AttributeUpdate {
  uint16_t endpoint_id;
  uint32_t cluster_id;
  uint32_t attribute_id;
  esp_matter_attr_val_t value;
  SensorAttributeUpdater updater;
};

void update_attribute_on_matter_thread(intptr_t context) {
  auto *update = reinterpret_cast<AttributeUpdate *>(context);
  if (update->updater != nullptr) {
    CHIP_ERROR err =
        update->updater(update->endpoint_id, update->cluster_id, update->value);
    if (err != CHIP_NO_ERROR) {
      ESP_LOGE(TAG,
               "Failed to update attribute 0x%08" PRIX32
               " on cluster 0x%08" PRIX32 ", endpoint %u: %s",
               update->attribute_id, update->cluster_id, update->endpoint_id,
               err.AsString());
    }
    delete update;
    return;
  }

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
                      esp_matter_attr_val_t attribute_value,
                      SensorAttributeUpdater updater = nullptr) {
  auto *update = new AttributeUpdate{endpoint_id, cluster_id, attribute_id,
                                     attribute_value, updater};
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
    uint32_t attribute_id, SensorValueConverter converter,
    SensorAttributeUpdater updater)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor),
      cluster_id_(cluster_id), attribute_id_(attribute_id),
      converter_(converter), updater_(updater) {}

void MatterSensorAttributeMapping::initialize() {
  if (this->sensor_ == nullptr || this->converter_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](float value) { this->publish_(value); });
  if (this->sensor_->has_state())
    this->publish_(this->sensor_->state);
}

void MatterSensorAttributeMapping::publish_(float value) {
  update_attribute(this->endpoint_id_, this->cluster_id_, this->attribute_id_,
                   this->converter_(value), this->updater_);
}
#endif // USE_SENSOR

#ifdef USE_BINARY_SENSOR
CHIP_ERROR update_boolean_state_attribute(uint16_t endpoint_id,
                                          uint32_t cluster_id,
                                          esp_matter_attr_val_t value) {
  auto *server =
      esp_matter::data_model::provider::get_instance().registry().Get(
          {endpoint_id, cluster_id});
  if (server == nullptr)
    return CHIP_ERROR_NOT_FOUND;

  static_cast<chip::app::Clusters::BooleanStateCluster *>(server)
      ->SetStateValue(value.val.b);
  return CHIP_NO_ERROR;
}

void MatterComponent::register_binary_sensor_attribute(
    binary_sensor::BinarySensor *sensor, uint16_t endpoint_id,
    uint32_t cluster_id, uint32_t attribute_id,
    BinarySensorValueConverter converter, SensorAttributeUpdater updater) {
  this->mappings_.push_back(new MatterBinarySensorAttributeMapping(
      sensor, endpoint_id, cluster_id, attribute_id, converter, updater));
}

MatterBinarySensorAttributeMapping::MatterBinarySensorAttributeMapping(
    binary_sensor::BinarySensor *sensor, uint16_t endpoint_id,
    uint32_t cluster_id, uint32_t attribute_id,
    BinarySensorValueConverter converter, SensorAttributeUpdater updater)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor),
      cluster_id_(cluster_id), attribute_id_(attribute_id),
      converter_(converter), updater_(updater) {}

void MatterBinarySensorAttributeMapping::initialize() {
  if (this->sensor_ == nullptr || this->converter_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](bool value) { this->publish_(value); });
  if (this->sensor_->has_state())
    this->publish_(this->sensor_->state);
}

void MatterBinarySensorAttributeMapping::publish_(bool value) {
  update_attribute(this->endpoint_id_, this->cluster_id_, this->attribute_id_,
                   this->converter_(value), this->updater_);
}
#endif // USE_BINARY_SENSOR

} // namespace esphome::matter

#endif // USE_MATTER && (USE_SENSOR || USE_BINARY_SENSOR)
