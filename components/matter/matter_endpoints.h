#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER
#include "esphome/core/log.h"

#include <esp_matter.h>
#include <esp_matter_cluster.h>

#include <cstdint>

namespace esphome::matter {

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

inline bool set_initial_enum8(esp_matter::endpoint_t *endpoint,
                              uint32_t cluster_id, uint32_t attribute_id,
                              uint8_t value) {
  auto *cluster = esp_matter::cluster::get(endpoint, cluster_id);
  if (cluster == nullptr)
    return false;
  auto *attribute = esp_matter::attribute::get(cluster, attribute_id);
  if (attribute == nullptr)
    return false;
  esp_matter_attr_val_t attribute_value = esp_matter_enum8(value);
  return esp_matter::attribute::set_val(attribute, &attribute_value, false) ==
         ESP_OK;
}

class MatterEndpointMappingBase {
public:
  explicit MatterEndpointMappingBase(uint16_t endpoint_id)
      : endpoint_id_(endpoint_id) {}
  virtual ~MatterEndpointMappingBase() = default;

  virtual void initialize() {}

  uint16_t endpoint_id() const { return this->endpoint_id_; }

protected:
  bool has_server_cluster(uint32_t cluster_id) const;

  uint16_t endpoint_id_;
};

} // namespace esphome::matter

#endif // USE_MATTER
