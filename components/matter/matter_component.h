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
    // Must run after ESPHome's network service components. On Wi-Fi/Ethernet
    // this lets ESPHome initialize the shared mDNS responder before Matter
    // publishes DNS-SD records; on Thread it keeps Matter after SRP setup.
    return setup_priority::AFTER_CONNECTION - 5.0f;
    // TODO: AFTER_BLUETOOTH in BLE commissioning mode.
  }

  void factory_reset();

  // Endpoints
  void register_endpoint(uint16_t endpoint_id);
  void register_binding(uint16_t endpoint_id);
  template <typename ConfigT,
            esp_err_t (*AddFn)(esp_matter::endpoint_t *, ConfigT *)>
  void register_device_type(uint16_t endpoint_id) {
    this->device_type_registrations_.push_back(
        new MatterDeviceTypeRegistration<ConfigT, AddFn>(endpoint_id));
  }
#ifdef USE_LIGHT
  void map_light_to_endpoint(light::LightState *light, uint16_t endpoint_id);
#endif
#ifdef USE_SENSOR
  void map_sensor_to_endpoint(sensor::Sensor *sensor, uint16_t endpoint_id);
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

  std::vector<uint16_t> endpoint_ids_;
  std::vector<uint16_t> binding_endpoint_ids_;
  std::vector<MatterDeviceTypeRegistrationBase *> device_type_registrations_;
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
