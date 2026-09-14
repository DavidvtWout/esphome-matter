#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER
#include "esphome/core/log.h"
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

using MatterEndpointBuildFn = bool (*)(esp_matter::endpoint_t *);

struct MatterEndpointRegistration {
  uint16_t endpoint_id;
  MatterEndpointBuildFn build_fn;
};

using MatterFeatureAddFn = esp_err_t (*)(esp_matter::cluster_t *);

inline esp_err_t add_feature(esp_matter::cluster_t *cluster,
                             MatterFeatureAddFn add_fn) {
  return add_fn(cluster);
}

template <typename ConfigT>
esp_err_t add_feature(esp_matter::cluster_t *cluster,
                      esp_err_t (*add_fn)(esp_matter::cluster_t *, ConfigT *)) {
  ConfigT config{};
  return add_fn(cluster, &config);
}

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

} // namespace esphome::matter

#endif // USE_MATTER
