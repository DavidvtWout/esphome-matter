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

// esp-matter's legacy window covering feature add returns ESP_ERR_NOT_FINISHED
// when the persisted attribute already holds the value it sets. The feature is
// added, and esp-matter itself treats that code as "nothing to report".
inline esp_err_t feature_add_result(esp_err_t err) {
  return err == ESP_ERR_NOT_FINISHED ? ESP_OK : err;
}

inline esp_err_t add_feature(esp_matter::cluster_t *cluster,
                             MatterFeatureAddFn add_fn) {
  return feature_add_result(add_fn(cluster));
}

template <typename ConfigT>
esp_err_t add_feature(esp_matter::cluster_t *cluster,
                      esp_err_t (*add_fn)(esp_matter::cluster_t *, ConfigT *)) {
  ConfigT config{};
  return feature_add_result(add_fn(cluster, &config));
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
