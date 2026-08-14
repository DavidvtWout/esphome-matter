#pragma once
#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/automation.h"
#include "esphome/core/component.h"

#include "matter_endpoints.h"

#include <functional>
#include <vector>

#include <esp_matter.h>

namespace esphome::matter {

class MatterComponent : public Component {
public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override {
#ifdef USE_OPENTHREAD
    // Must run after the OpenThreadSrpComponent.
    return setup_priority::AFTER_CONNECTION - 5.0f;
#else
    return setup_priority::AFTER_CONNECTION;
// TODO: AFTER_BLUETOOTH in BLE commissioning mode.
#endif
  }

  void factory_reset();
  template <typename ConfigT,
            esp_matter::endpoint_t *(*CreateFn)(esp_matter::node_t *, ConfigT *,
                                                uint8_t, void *)>
  void register_endpoint(MatterEndpointRef *ref) {
    this->endpoint_registrations_.push_back(
        new MatterEndpointRegistration<ConfigT, CreateFn>(ref));
  }
#ifdef USE_LIGHT
  void map_light_to_endpoint(light::LightState *light, MatterEndpointRef *ref);
#endif
#ifdef USE_SENSOR
  void map_sensor_to_endpoint(sensor::Sensor *sensor, MatterEndpointRef *ref);
#endif
#ifdef USE_LIGHT
  MatterLightMapping *get_light_mapping_by_endpoint(uint16_t endpoint_id);
#endif
  // Public wrapper around the protected Component scheduler; used by the
  // Matter-thread callbacks to hop onto the main loop (defer is thread-safe).
  void defer_to_main_loop(std::function<void()> &&f) {
    this->defer(std::move(f));
  }

private:
  // Defined in matter_endpoints.cpp
  bool create_endpoints_(esp_matter::node_t *node);
  void register_endpoint_callbacks_();

  uint16_t discriminator_{0};
  uint32_t passcode_{0};

  std::vector<MatterEndpointRegistrationBase *> endpoint_registrations_;
  std::vector<MatterEndpointMappingBase *> mappings_;
};

extern MatterComponent *
    global_matter_component; // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

template <typename... Ts>
class MatterFactoryResetAction : public Action<Ts...>,
                                 public Parented<MatterComponent> {
public:
  void play(Ts... x) override { this->parent_->factory_reset(); }
};

} // namespace esphome::matter

#endif // USE_MATTER
