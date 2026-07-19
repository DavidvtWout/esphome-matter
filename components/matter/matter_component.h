#pragma once
#include "esphome/core/automation.h"
#include "esphome/core/component.h"

#include "matter_endpoints.h"

#include <vector>

#ifdef USE_MATTER

#include <esp_matter.h>

namespace esphome::matter {

class MatterComponent : public Component {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::BEFORE_CONNECTION; }
  void factory_reset();
  void add_on_off_switch(MatterEndpointRef *ref) { this->on_off_switches_.push_back({ref, 0}); }
  void add_dimmer_switch(MatterEndpointRef *ref) { this->dimmer_switches_.push_back({ref, 0}); }
#ifdef USE_SENSOR
  void add_temperature_sensor(sensor::Sensor *sensor, MatterEndpointRef *ref) {
    this->temperature_sensors_.push_back({sensor, ref, 0});
  }
#endif
#ifdef USE_LIGHT
  void add_on_off_light(light::LightState *light, MatterEndpointRef *ref) {
    this->lights_.push_back(new MatterLight(light, false, ref));
  }
  void add_dimmable_light(light::LightState *light, MatterEndpointRef *ref) {
    this->lights_.push_back(new MatterLight(light, true, ref));
  }
  MatterLight *get_light_by_endpoint(uint16_t endpoint_id) {
    for (auto *ml : this->lights_) {
      if (ml->endpoint_id == endpoint_id)
        return ml;
    }
    return nullptr;
  }
#endif
  // Public wrapper around the protected Component scheduler; used by the
  // Matter-thread callbacks to hop onto the main loop (defer is thread-safe).
  void defer_to_main_loop(std::function<void()> &&f) { this->defer(std::move(f)); }

 private:
  // Defined in matter_endpoints.cpp
  bool create_endpoints_(esp_matter::node_t *node);
  void register_endpoint_callbacks_();

  uint16_t discriminator_{0};
  uint32_t passcode_{0};
  std::vector<MatterOnOffSwitch> on_off_switches_;
  std::vector<MatterDimmerSwitch> dimmer_switches_;
#ifdef USE_SENSOR
  std::vector<MatterTemperatureSensor> temperature_sensors_;
#endif
#ifdef USE_LIGHT
  std::vector<MatterLight *> lights_;
#endif
};

extern MatterComponent *global_matter_component;  // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

template <typename... Ts>
class MatterFactoryResetAction : public Action<Ts...>, public Parented<MatterComponent> {
 public:
  void play(Ts... x) override { this->parent_->factory_reset(); }
};

}  // namespace esphome::matter

#endif  // USE_MATTER
