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
// Which Matter light device type an endpoint presents. Ordered by capability:
// each level adds clusters on top of the previous one.
enum class MatterLightType : uint8_t {
  ON_OFF = 0,            // OnOff
  DIMMABLE = 1,          // + LevelControl
  COLOR_TEMPERATURE = 2, // + ColorControl (ColorTemperature feature)
  EXTENDED_COLOR = 3,    // + ColorControl (HueSaturation + ColorTemperature)
};

// Bidirectional bridge between an ESPHome light and a Matter light endpoint.
// Heap-allocated so the listener registration pointer stays stable.
class MatterLight : public light::LightRemoteValuesListener {
 public:
  MatterLight(light::LightState *light, MatterLightType type, MatterEndpointRef *ref)
      : light(light), type(type), ref(ref) {}

  bool dimmable() const { return this->type != MatterLightType::ON_OFF; }
  bool has_color_temperature() const {
    return this->type == MatterLightType::COLOR_TEMPERATURE || this->type == MatterLightType::EXTENDED_COLOR;
  }
  bool has_hue_saturation() const { return this->type == MatterLightType::EXTENDED_COLOR; }
  // True when the ESPHome light has a dedicated white element (an RGBW strip,
  // for instance). Matter has no white channel, so saturation is the only place
  // it can be represented; see the conversion helpers in matter_endpoints.cpp.
  bool has_white_channel() const {
    return this->light->get_traits().supports_color_capability(light::ColorCapability::WHITE);
  }
  const char *type_name() const;

  // ESPHome light changed (main loop): mirror the state to the Matter attributes.
  void on_light_remote_values_update() override { this->push_state_to_matter(); }
  void push_state_to_matter();
  // A Matter attribute changed (main loop, deferred from Matter thread): apply to the light.
  void apply_matter_update(uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t val);

  light::LightState *light;
  MatterLightType type;
  MatterEndpointRef *ref;
  uint16_t endpoint_id{0};

 protected:
  // Set while applying a Matter-originated change, so the resulting ESPHome
  // state callback does not immediately echo the same value back to Matter.
  bool applying_from_matter_{false};
};
#endif

// Common esp_matter attribute update callback, passed to node::create().
// Routes server-cluster changes (e.g. light commands) to the ESPHome entities.
esp_err_t endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type, uint16_t endpoint_id,
                                       uint32_t cluster_id, uint32_t attribute_id, esp_matter_attr_val_t *val,
                                       void *priv_data);

}  // namespace esphome::matter

#endif  // USE_MATTER
