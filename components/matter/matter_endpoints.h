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

// Not every esp-matter cluster config has a feature_flags member (e.g. fan_control has none).
template <typename ConfigT>
inline constexpr bool has_feature_flags = requires(ConfigT config) {
  config.feature_flags;
};

// Sets config.feature_flags if the config has such a member. Otherwise the features have to be added with add()
// after the cluster has been created.
template <typename ConfigT>
void set_feature_flags(ConfigT &config, uint32_t feature_flags) {
  if constexpr (has_feature_flags<ConfigT>)
    config.feature_flags = feature_flags;
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
