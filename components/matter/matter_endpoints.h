#pragma once
#include "esphome/core/defines.h"
#include "esphome/core/log.h"
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif
#ifdef USE_LIGHT
#include "esphome/components/light/light_state.h"
#endif

#ifdef USE_MATTER

#include <esp_matter.h>

#include <cstdint>

namespace esphome::matter {

// Referenceable handle for one configured endpoint. The endpoint_id is filled
// in during endpoint creation; actions resolve it at play() time.
class MatterEndpointRef {
public:
  uint16_t endpoint_id{0};
};

#ifdef USE_LIGHT
class MatterLightMapping;
#endif

class MatterEndpointRegistrationBase {
public:
  explicit MatterEndpointRegistrationBase(MatterEndpointRef *ref) : ref_(ref) {}
  virtual ~MatterEndpointRegistrationBase() = default;

  virtual bool create_endpoint(esp_matter::node_t *node) = 0;

  uint16_t endpoint_id() const { return this->endpoint_id_; }

protected:
  MatterEndpointRef *ref_;
  esp_matter::endpoint_t *endpoint_{nullptr};
  uint16_t endpoint_id_{0};
};

template <typename ConfigT,
          esp_matter::endpoint_t *(*CreateFn)(esp_matter::node_t *, ConfigT *,
                                              uint8_t, void *)>
class MatterEndpointRegistration : public MatterEndpointRegistrationBase {
public:
  explicit MatterEndpointRegistration(MatterEndpointRef *ref)
      : MatterEndpointRegistrationBase(ref) {}

  bool create_endpoint(esp_matter::node_t *node) override {
    ConfigT config;
    this->endpoint_ =
        CreateFn(node, &config, esp_matter::ENDPOINT_FLAG_NONE, nullptr);
    if (this->endpoint_ == nullptr) {
      ESP_LOGE("matter", "Failed to create endpoint");
      return false;
    }
    this->endpoint_id_ = esp_matter::endpoint::get_id(this->endpoint_);
    this->ref_->endpoint_id = this->endpoint_id_;
    ESP_LOGD("matter", "Endpoint created: id=%u", this->endpoint_id_);
    return true;
  }
};

class MatterEndpointMappingBase {
public:
  explicit MatterEndpointMappingBase(MatterEndpointRef *ref) : ref_(ref) {}
  virtual ~MatterEndpointMappingBase() = default;

  virtual void register_callbacks() {}
#ifdef USE_LIGHT
  virtual MatterLightMapping *as_light_mapping() { return nullptr; }
#endif

  uint16_t endpoint_id() const { return this->ref_->endpoint_id; }

protected:
  bool has_server_cluster(uint32_t cluster_id) const;

  MatterEndpointRef *ref_;
};

#ifdef USE_LIGHT
class MatterLightMapping : public MatterEndpointMappingBase,
                           public light::LightRemoteValuesListener {
public:
  MatterLightMapping(light::LightState *light, MatterEndpointRef *ref);

  void on_light_remote_values_update() override;
  void register_callbacks() override;
  MatterLightMapping *as_light_mapping() override;

  void push_state_to_matter();
  void apply_matter_update(uint32_t cluster_id, uint32_t attribute_id,
                           esp_matter_attr_val_t val);

protected:
  light::LightState *light_;
};
#endif

#ifdef USE_SENSOR
class MatterSensorMapping : public MatterEndpointMappingBase {
public:
  MatterSensorMapping(sensor::Sensor *sensor, MatterEndpointRef *ref);

  void register_callbacks() override;
  void push_state_to_matter(float value);

protected:
  sensor::Sensor *sensor_;
};
#endif

// Common esp_matter attribute update callback, passed to node::create().
// Routes server-cluster changes (e.g. light commands) to the ESPHome entities.
esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data);

} // namespace esphome::matter

#endif // USE_MATTER
