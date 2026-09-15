#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER
#include "esphome/core/automation.h"
#include "esphome/core/component.h"

#include "matter_attributes.h"
#include "matter_endpoints.h"
#include "matter_lights.h"
#include "matter_sensors.h"

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

  // Register Matter endpoints
  void register_endpoint(uint16_t endpoint_id, MatterEndpointBuildFn build_fn);

  // Register attribute update actions
  void register_attribute_trigger(MatterAttributeTriggerBase *trigger) {
    this->attribute_triggers_.push_back(trigger);
  }
  std::vector<MatterAttributeTriggerBase *> attribute_triggers_;

  // Register ESPHome entities
#ifdef USE_LIGHT
  void map_light_to_endpoint(light::LightState *light, uint16_t endpoint_id);
  MatterLightMapping *get_light_mapping_by_endpoint(uint16_t endpoint_id);
#endif // USE_LIGHT
#ifdef USE_SENSOR
  void register_sensor_attribute(sensor::Sensor *sensor, uint16_t endpoint_id,
                                 uint32_t cluster_id, uint32_t attribute_id,
                                 SensorValueConverter converter);

  template <
      typename ClusterT, typename ValueT,
      CHIP_ERROR (ClusterT::*Setter)(chip::app::DataModel::Nullable<ValueT>)>
  void register_code_driven_sensor_attribute(sensor::Sensor *sensor,
                                             uint16_t endpoint_id,
                                             uint32_t cluster_id,
                                             uint32_t attribute_id,
                                             SensorValueConverter converter) {
    this->mappings_.push_back(new MatterSensorAttributeMapping(
        sensor, endpoint_id, cluster_id, attribute_id, converter,
        update_code_driven_sensor_attribute<ClusterT, ValueT, Setter>));
  }
#endif // USE_SENSOR
#ifdef USE_BINARY_SENSOR
  void
  register_binary_sensor_attribute(binary_sensor::BinarySensor *sensor,
                                   uint16_t endpoint_id, uint32_t cluster_id,
                                   uint32_t attribute_id,
                                   BinarySensorValueConverter converter,
                                   SensorAttributeUpdater updater = nullptr);
#endif // USE_BINARY_SENSOR

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

  std::vector<MatterEndpointRegistration> endpoint_registrations_;
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
