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
#include <esp_matter_cluster.h>

#include <cstdint>
#include <type_traits>

namespace esphome::matter {

#ifdef USE_LIGHT
class MatterLightMapping;
#endif

template <typename ConfigT, typename = void>
struct MatterEndpointConfigHasBinding : std::false_type {};

template <typename ConfigT>
struct MatterEndpointConfigHasBinding<
    ConfigT, std::void_t<decltype(std::declval<ConfigT>().binding)>>
    : std::true_type {};

esp_matter::endpoint_t *
create_endpoint_for_registration(esp_matter::node_t *node,
                                 uint16_t endpoint_id);

class MatterEndpointRegistrationBase {
public:
  explicit MatterEndpointRegistrationBase(uint16_t endpoint_id)
      : endpoint_id_(endpoint_id) {}
  virtual ~MatterEndpointRegistrationBase() = default;

  virtual bool create_endpoint(esp_matter::node_t *node) = 0;

  uint16_t endpoint_id() const { return this->endpoint_id_; }

protected:
  esp_matter::endpoint_t *endpoint_{nullptr};
  uint16_t endpoint_id_;
};

template <typename ConfigT,
          esp_err_t (*AddFn)(esp_matter::endpoint_t *, ConfigT *)>
class MatterEndpointRegistration : public MatterEndpointRegistrationBase {
public:
  explicit MatterEndpointRegistration(uint16_t endpoint_id)
      : MatterEndpointRegistrationBase(endpoint_id) {}

  bool create_endpoint(esp_matter::node_t *node) override {
    ConfigT config;
    bool existing_endpoint =
        esp_matter::endpoint::get(node, this->endpoint_id_) != nullptr;
    this->endpoint_ =
        create_endpoint_for_registration(node, this->endpoint_id_);
    if (this->endpoint_ == nullptr) {
      ESP_LOGE("matter", "Failed to create endpoint %u", this->endpoint_id_);
      return false;
    }

    if (this->endpoint_id_ != 0 && !existing_endpoint) {
      esp_matter::cluster_t *descriptor_cluster =
          esp_matter::cluster::descriptor::create(
              this->endpoint_, &(config.descriptor),
              esp_matter::CLUSTER_FLAG_SERVER);
      if (descriptor_cluster == nullptr) {
        ESP_LOGE("matter", "Failed to create endpoint %u descriptor cluster",
                 this->endpoint_id_);
        return false;
      }
    }

    if (AddFn(this->endpoint_, &config) != ESP_OK) {
      ESP_LOGE("matter", "Failed to add endpoint %u clusters",
               this->endpoint_id_);
      return false;
    }

    if constexpr (MatterEndpointConfigHasBinding<ConfigT>::value) {
      esp_matter::cluster_t *binding_cluster =
          esp_matter::cluster::binding::create(this->endpoint_,
                                               &(config.binding),
                                               esp_matter::CLUSTER_FLAG_SERVER);
      if (binding_cluster == nullptr) {
        ESP_LOGE("matter", "Failed to create endpoint %u binding cluster",
                 this->endpoint_id_);
        return false;
      }
    }

    ESP_LOGD("matter", "Endpoint created: id=%u", this->endpoint_id_);
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
#endif

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
#endif

#ifdef USE_SENSOR
class MatterSensorMapping : public MatterEndpointMappingBase {
public:
  MatterSensorMapping(sensor::Sensor *sensor, uint16_t endpoint_id);

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
