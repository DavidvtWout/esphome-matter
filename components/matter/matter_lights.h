#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_LIGHT)

#include "esphome/components/light/light_state.h"
#include "esphome/core/optional.h"
#include "matter_endpoints.h"

#include <esp_matter.h>

#include <cstdint>

namespace esphome::matter {

struct MatterColorTemperatureRange {
  uint16_t min_mireds;
  uint16_t max_mireds;
};

struct MatterLightCapabilities {
  bool has_level{false};
  optional<MatterColorTemperatureRange> color_temperature_range;
};

class MatterLightMapping : public MatterEndpointMappingBase,
                           public light::LightRemoteValuesListener {
public:
  MatterLightMapping(light::LightState *light, uint16_t endpoint_id);

  void on_light_remote_values_update() override;
  void initialize() override;

  void push_state_to_matter();
  void sync_state_from_matter();

protected:
  void initialize_capabilities_();
  void apply_on_off_(bool on);
  void apply_level_(uint8_t level);
  void apply_color_temperature_(uint16_t color_temperature);

  light::LightState *light_;
  MatterLightCapabilities capabilities_;
  bool synchronizing_from_matter_{false};
};

} // namespace esphome::matter

#endif // USE_MATTER && USE_LIGHT
