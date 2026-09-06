#include "matter_sensors.h"

#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_component.h"

#include <platform/CHIPDeviceLayer.h>

#include <cinttypes>

namespace esphome::matter {

static const char *const TAG = "matter.sensor";

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
#endif

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
#endif

} // namespace esphome::matter

#endif // USE_MATTER
