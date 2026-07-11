#pragma once
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"

#include <vector>

#ifdef USE_MATTER

#include <esp_matter.h>

namespace esphome::matter {

enum class SwitchDeviceType {
  LATCHED,
  MOMENTARY,
  MOMENTARY_RELEASE,
  MOMENTARY_LONG_PRESS,
  MOMENTARY_MULTI_PRESS,
  MOMENTARY_FULL,
};

struct MatterSwitch {
  binary_sensor::BinarySensor *sensor;
  SwitchDeviceType device_type;
  uint16_t endpoint_id;  // 0 = auto-assign
};

class MatterComponent : public Component {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::BEFORE_CONNECTION; }
  void factory_reset();
  void add_switch(binary_sensor::BinarySensor *sensor, SwitchDeviceType device_type, uint16_t endpoint_id) {
    this->switches_.push_back({sensor, device_type, endpoint_id});
  }

 private:
  uint16_t discriminator_{0};
  uint32_t passcode_{0};
  std::vector<MatterSwitch> switches_;
};

template <typename... Ts>
class MatterFactoryResetAction : public Action<Ts...>, public Parented<MatterComponent> {
 public:
  void play(Ts... x) override { this->parent_->factory_reset(); }
};

}  // namespace esphome::matter

#endif  // USE_MATTER
