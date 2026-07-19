#pragma once
#include "esphome/core/defines.h"
#include "esphome/components/binary_sensor/binary_sensor.h"

#ifdef USE_MATTER

#include <cstdint>

namespace esphome::matter {

struct MatterOnOffSwitch {
  binary_sensor::BinarySensor *sensor;
  uint16_t endpoint_id;
};

struct MatterDimmerSwitch {
  binary_sensor::BinarySensor *up_sensor;
  binary_sensor::BinarySensor *down_sensor;
  uint32_t long_press_ms;
  uint16_t endpoint_id;
};

}  // namespace esphome::matter

#endif  // USE_MATTER
