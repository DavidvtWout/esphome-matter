#pragma once
#include "esphome/core/component.h"

#ifdef USE_MATTER

#include <esp_matter.h>

namespace esphome::matter {

class MatterComponent : public Component {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::BEFORE_CONNECTION; }

 private:
  uint16_t discriminator_{0};
  uint32_t passcode_{0};
};

}  // namespace esphome::matter

#endif  // USE_MATTER
