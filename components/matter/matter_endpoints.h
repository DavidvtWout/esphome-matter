#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER
#include "esphome/core/log.h"
#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif // USE_BINARY_SENSOR
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif // USE_SENSOR
#ifdef USE_LIGHT
#include "esphome/components/light/light_state.h"
#endif // USE_LIGHT

#include <esp_matter.h>
#include <esp_matter_cluster.h>

#include <cstdint>

namespace esphome::matter {

#ifdef USE_LIGHT
class MatterLightMapping;
#endif // USE_LIGHT

class MatterDeviceTypeRegistrationBase {
public:
  MatterDeviceTypeRegistrationBase(uint16_t endpoint_id,
                                   const char *device_type)
      : endpoint_id_(endpoint_id), device_type_(device_type) {}
  virtual ~MatterDeviceTypeRegistrationBase() = default;

  virtual bool add_clusters(esp_matter::node_t *node) = 0;

  uint16_t endpoint_id() const { return this->endpoint_id_; }

protected:
  uint16_t endpoint_id_;
  const char *device_type_;
};

template <typename ConfigT,
          esp_err_t (*AddFn)(esp_matter::endpoint_t *, ConfigT *)>
class MatterDeviceTypeRegistration : public MatterDeviceTypeRegistrationBase {
public:
  MatterDeviceTypeRegistration(uint16_t endpoint_id, const char *device_type)
      : MatterDeviceTypeRegistrationBase(endpoint_id, device_type) {}

  bool add_clusters(esp_matter::node_t *node) override {
    ConfigT config;
    esp_matter::endpoint_t *endpoint =
        esp_matter::endpoint::get(node, this->endpoint_id_);
    if (endpoint == nullptr) {
      ESP_LOGE("matter", "Cannot add %s device type for missing endpoint %u",
               this->device_type_, this->endpoint_id_);
      return false;
    }

    if (AddFn(endpoint, &config) != ESP_OK) {
      ESP_LOGE("matter", "Failed to add %s device type to endpoint %u",
               this->device_type_, this->endpoint_id_);
      return false;
    }

    ESP_LOGD("matter", "Added device type %s to endpoint %u",
             this->device_type_, this->endpoint_id_);
    return true;
  }
};

class MatterEndpointMappingBase {
public:
  explicit MatterEndpointMappingBase(uint16_t endpoint_id)
      : endpoint_id_(endpoint_id) {}
  virtual ~MatterEndpointMappingBase() = default;

  virtual void register_callbacks() {}
#ifdef USE_LIGHT
  virtual MatterLightMapping *as_light_mapping() { return nullptr; }
#endif // USE_LIGHT

  uint16_t endpoint_id() const { return this->endpoint_id_; }

protected:
  bool has_server_cluster(uint32_t cluster_id) const;

  uint16_t endpoint_id_;
};

#ifdef USE_LIGHT
class MatterLightMapping : public MatterEndpointMappingBase,
                           public light::LightRemoteValuesListener {
public:
  MatterLightMapping(light::LightState *light, uint16_t endpoint_id);

  void on_light_remote_values_update() override;
  void register_callbacks() override;
  MatterLightMapping *as_light_mapping() override;

  void push_state_to_matter();
  void apply_matter_update(uint32_t cluster_id, uint32_t attribute_id,
                           esp_matter_attr_val_t val);

protected:
  light::LightState *light_;
};
#endif // USE_LIGHT

#ifdef USE_SENSOR
class MatterSensorMapping : public MatterEndpointMappingBase {
public:
  MatterSensorMapping(sensor::Sensor *sensor, uint16_t endpoint_id);

  void register_callbacks() override;
  void push_state_to_matter(float value);

protected:
  sensor::Sensor *sensor_;
};
#endif // USE_SENSOR

#ifdef USE_BINARY_SENSOR
class MatterBinarySensorMapping : public MatterEndpointMappingBase {
public:
  MatterBinarySensorMapping(binary_sensor::BinarySensor *binary_sensor,
                            uint16_t endpoint_id);

  void register_callbacks() override;
  void push_state_to_matter(bool value);

protected:
  binary_sensor::BinarySensor *binary_sensor_;
};
#endif // USE_BINARY_SENSOR

// Common esp_matter attribute update callback, passed to node::create().
// Routes server-cluster changes (e.g. light commands) to the ESPHome entities.
esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data);

} // namespace esphome::matter

#endif // USE_MATTER
