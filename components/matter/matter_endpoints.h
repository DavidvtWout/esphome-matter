#pragma once
#include "esphome/core/defines.h"
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif
#ifdef USE_LIGHT
#include "esphome/components/light/light_state.h"
#endif

#ifdef USE_MATTER

#include <esp_matter.h>

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

#ifdef USE_LIGHT
// Bidirectional bridge between an ESPHome light and a Matter light endpoint
// (on_off_light or dimmable_light server clusters). Heap-allocated so the
// listener registration pointer stays stable.
class MatterLight : public light::LightRemoteValuesListener {
 public:
  MatterLight(light::LightState *light, bool dimmable, MatterEndpointRef *ref)
      : light(light), dimmable(dimmable), ref(ref) {}

  // ESPHome light changed (main loop): mirror the state to the Matter attributes.
  void on_light_remote_values_update() override { this->push_state_to_matter(); }
  void push_state_to_matter();
  // A Matter attribute changed (main loop, deferred from Matter thread): apply to the light.
  void apply_matter_update(uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t val);

  light::LightState *light;
  bool dimmable;
  MatterEndpointRef *ref;
  uint16_t endpoint_id{0};
};
#endif

// Common esp_matter attribute update callback, passed to node::create().
// Routes server-cluster changes (e.g. light commands) to the ESPHome entities.
esp_err_t endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type, uint16_t endpoint_id,
                                       uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t *val,
                                       void *priv_data);

}  // namespace esphome::matter

#endif  // USE_MATTER
