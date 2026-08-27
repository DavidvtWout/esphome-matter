#pragma once
#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/automation.h"
#include "esphome/core/component.h"

#include "matter_endpoints.h"

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
  void add_on_off_switch(MatterEndpointRef *ref) {
    this->on_off_switches_.push_back({ref, 0});
  }
  void add_dimmer_switch(MatterEndpointRef *ref) {
    this->dimmer_switches_.push_back({ref, 0});
  }
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
  void defer_to_main_loop(std::function<void()> &&f) {
    this->defer(std::move(f));
  }

  // Public wrapper around the protected Component scheduler, used by the
  // outbound command queue in matter_actions.cpp. The id-keyed overload avoids
  // the heap allocation a named timeout would need. Unlike defer(), the
  // scheduler's set_timeout() is not thread-safe, so this must only be called
  // from the main loop task.
  void schedule_command_pump(uint32_t id, uint32_t delay_ms,
                             std::function<void()> &&f) {
    this->set_timeout(id, delay_ms, std::move(f));
  }

  // Delay between sending a command to the group (multicast) bindings of an
  // endpoint and sending it to its unicast bindings. Multicast is unreliable
  // but immediate; unicast is reliable but can be delayed for seconds while
  // MRP retransmits or a CASE session is established. Holding the unicast back
  // gives a rapid second command a chance to supersede the first one before it
  // goes out, which stops a late unicast from undoing a newer multicast.
  // Defaults to 0, which preserves the original send-immediately behaviour.
  void set_unicast_delay(uint32_t delay_ms) {
    this->unicast_delay_ms_ = delay_ms;
  }
  uint32_t get_unicast_delay() const { return this->unicast_delay_ms_; }

  // Minimum spacing between two commands sent to the same local endpoint and
  // cluster. Some devices drop commands that arrive back-to-back. Defaults to
  // 0 (no rate limiting).
  void set_min_command_interval(uint32_t interval_ms) {
    this->min_command_interval_ms_ = interval_ms;
  }
  uint32_t get_min_command_interval() const {
    return this->min_command_interval_ms_;
  }

  // How many relative commands (Toggle, Move, Step, ...) may be queued for one
  // local endpoint and cluster before the oldest is dropped. Absolute commands
  // replace the queue rather than extending it, so they never hit this limit.
  // Raise it for automations that legitimately burst; lower it to bound how far
  // behind the device can lag when the queue is being paced.
  void set_max_pending_commands(uint8_t max_pending) {
    this->max_pending_commands_ = max_pending;
  }
  uint8_t get_max_pending_commands() const {
    return this->max_pending_commands_;
  }

private:
  // Defined in matter_endpoints.cpp
  bool create_endpoints_(esp_matter::node_t *node);
  void register_endpoint_callbacks_();

  uint16_t discriminator_{0};
  uint32_t passcode_{0};
  uint32_t unicast_delay_ms_{0};
  uint32_t min_command_interval_ms_{0};
  uint8_t max_pending_commands_{8};
  std::vector<MatterOnOffSwitch> on_off_switches_;
  std::vector<MatterDimmerSwitch> dimmer_switches_;
#ifdef USE_SENSOR
  std::vector<MatterTemperatureSensor> temperature_sensors_;
#endif
#ifdef USE_LIGHT
  std::vector<MatterLight *> lights_;
#endif
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
