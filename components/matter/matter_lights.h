#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_LIGHT)

#include "esphome/components/light/light_state.h"
#include "matter_endpoints.h"

#include <esp_matter.h>

#include <cstdint>

namespace esphome::matter {

class MatterLightMapping : public MatterEndpointMappingBase,
                           public light::LightRemoteValuesListener {
public:
  MatterLightMapping(light::LightState *light, uint16_t endpoint_id);

  void on_light_remote_values_update() override;
  void register_callbacks() override;
  MatterLightMapping *as_light_mapping() override;

  void push_state_to_matter();
  void sync_state_from_matter();
  void apply_matter_update(uint32_t cluster_id, uint32_t attribute_id,
                           esp_matter_attr_val_t val);

protected:
  light::LightState *light_;
  bool synchronizing_from_matter_{false};
};

} // namespace esphome::matter

#endif // USE_MATTER && USE_LIGHT
