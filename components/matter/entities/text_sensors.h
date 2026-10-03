#pragma once

// ESPHome text sensor integrations for Matter component state.

#include "esphome/core/defines.h"

#ifdef USE_MATTER

#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif

#include <cstddef>
#include <string>

namespace esphome::matter {

#ifdef USE_TEXT_SENSOR
struct MatterFabricSensorRegistration {
  size_t slot{0};
  text_sensor::TextSensor *compressed_id{nullptr};
  text_sensor::TextSensor *fabric_id{nullptr};
  text_sensor::TextSensor *label{nullptr};
  text_sensor::TextSensor *node_id{nullptr};
  text_sensor::TextSensor *vendor_id{nullptr};
};
#endif

std::string format_manual_pairing_code(const std::string &code);

} // namespace esphome::matter

#endif // USE_MATTER
