#pragma once
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"

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
  void add_on_off_switch(binary_sensor::BinarySensor *sensor, uint16_t endpoint_id) {
    this->on_off_switches_.push_back({sensor, endpoint_id});
  }
  void add_dimmer_switch(binary_sensor::BinarySensor *up_sensor, binary_sensor::BinarySensor *down_sensor,
                         uint16_t endpoint_id) {
    this->dimmer_switches_.push_back({up_sensor, down_sensor, endpoint_id});
  }

 private:
  // Defined in matter_endpoints.cpp
  bool create_endpoints_(esp_matter::node_t *node);
  void register_endpoint_callbacks_();

  uint16_t discriminator_{0};
  uint32_t passcode_{0};
  std::vector<MatterOnOffSwitch> on_off_switches_;
  std::vector<MatterDimmerSwitch> dimmer_switches_;
};

template <typename... Ts>
class MatterFactoryResetAction : public Action<Ts...>, public Parented<MatterComponent> {
 public:
  void play(Ts... x) override { this->parent_->factory_reset(); }
};

}  // namespace esphome::matter

#endif  // USE_MATTER
