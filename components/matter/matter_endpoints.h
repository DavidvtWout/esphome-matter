#pragma once
#include "esphome/core/defines.h"
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif

#ifdef USE_MATTER

#include <cstdint>

namespace esphome::matter {

// Referenceable handle for one configured endpoint. The endpoint_id is filled
// in during endpoint creation; actions resolve it at play() time.
class MatterEndpointRef {
 public:
  uint16_t endpoint_id{0};
};

// Client endpoints carry no entity references: behaviour is wired in YAML
// automations via the matter.* actions, targeting the endpoint's ref id.
struct MatterOnOffSwitch {
  MatterEndpointRef *ref;
  uint16_t endpoint_id;
};

struct MatterDimmerSwitch {
  MatterEndpointRef *ref;
  uint16_t endpoint_id;
};

#ifdef USE_SENSOR
struct MatterTemperatureSensor {
  sensor::Sensor *sensor;
  MatterEndpointRef *ref;
  uint16_t endpoint_id;
};
#endif

}  // namespace esphome::matter

#endif  // USE_MATTER
