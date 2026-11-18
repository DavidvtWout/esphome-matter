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
  // With the Rocking feature enabled, RockSupport must advertise at least one rock direction. esp-matter defaults it
  // to 0 and the Fan Control cluster reads RockSupport only at startup (it can't be changed afterwards), so every
  // RockSetting != 0 would be rejected with CONSTRAINT_ERROR. Advertise all directions by default.
  if constexpr (requires { config.rock_support; })
    config.rock_support = 0x07;
  return add_fn(cluster, &config);
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
