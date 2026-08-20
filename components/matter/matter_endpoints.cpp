#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_actions.h"
#include "matter_component.h"

#include <platform/CHIPDeviceLayer.h>

#include <cmath>
#include <esp_matter_cluster.h>

static const char *const TAG = "matter";

namespace esphome::matter {

namespace {

struct EspMatterNodeHeader {
  void *endpoint_list;
  uint16_t min_unused_endpoint_id;
};

esp_matter::endpoint_t *resume_endpoint_at_id(esp_matter::node_t *node,
                                              uint16_t endpoint_id,
                                              uint8_t flags, void *priv_data) {
  if (esp_matter::endpoint::get(node, endpoint_id) != nullptr) {
    ESP_LOGE(TAG, "Matter endpoint id %u is already in use", endpoint_id);
    return nullptr;
  }

  // esp-matter only exposes endpoint::resume(node, id) for IDs below its
  // private min_unused_endpoint_id. Static ESPHome endpoints are created before
  // esp_matter::start(), so advance that private allocator watermark directly
  // and then let esp-matter's resume path add the endpoint normally.
  auto *node_header = reinterpret_cast<EspMatterNodeHeader *>(node);
  if (node_header->min_unused_endpoint_id <= endpoint_id)
    node_header->min_unused_endpoint_id = endpoint_id + 1;

  return esp_matter::endpoint::resume(node, flags, endpoint_id, priv_data);
}

} // namespace

esp_matter::endpoint_t *
create_endpoint_for_registration(esp_matter::node_t *node,
                                 uint16_t endpoint_id) {
  if (auto *endpoint = esp_matter::endpoint::get(node, endpoint_id);
      endpoint != nullptr)
    return endpoint;
  return resume_endpoint_at_id(node, endpoint_id,
                               esp_matter::ENDPOINT_FLAG_NONE, nullptr);
}

void MatterComponent::register_binding(uint16_t endpoint_id) {
  this->binding_endpoint_ids_.push_back(endpoint_id);
}

#ifdef USE_LIGHT
void MatterComponent::map_light_to_endpoint(light::LightState *light,
                                            uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterLightMapping(light, endpoint_id));
}
#endif

#ifdef USE_SENSOR
void MatterComponent::map_sensor_to_endpoint(sensor::Sensor *sensor,
                                             uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterSensorMapping(sensor, endpoint_id));
}
#endif

bool MatterEndpointMappingBase::has_server_cluster(uint32_t cluster_id) const {
  auto *endpoint = esp_matter::endpoint::get(this->endpoint_id());
  if (endpoint == nullptr)
    return false;
  auto *cluster = esp_matter::cluster::get(endpoint, cluster_id);
  return cluster != nullptr && (esp_matter::cluster::get_flags(cluster) &
                                esp_matter::CLUSTER_FLAG_SERVER);
}

#ifdef USE_LIGHT
MatterLightMapping::MatterLightMapping(light::LightState *light,
                                       uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), light_(light) {}

void MatterLightMapping::on_light_remote_values_update() {
  this->push_state_to_matter();
}

void MatterLightMapping::register_callbacks() {
  if (this->light_ == nullptr)
    return;
  this->light_->add_remote_values_listener(this);
  this->push_state_to_matter();
}

MatterLightMapping *MatterLightMapping::as_light_mapping() { return this; }

void MatterLightMapping::push_state_to_matter() {
  uint16_t eid = this->endpoint_id();
  bool has_level =
      this->has_server_cluster(chip::app::Clusters::LevelControl::Id);
  bool on = this->light_->remote_values.is_on();
  float brightness = this->light_->remote_values.get_brightness();
  auto level = static_cast<uint8_t>(std::lroundf(brightness * 254.0f));
  level = level < 1 ? 1 : level;
  chip::DeviceLayer::SystemLayer().ScheduleLambda([eid, has_level, on,
                                                   level]() {
    using namespace chip::app::Clusters;
    esp_matter_attr_val_t on_val = esp_matter_bool(on);
    esp_matter::attribute::update(eid, OnOff::Id, OnOff::Attributes::OnOff::Id,
                                  &on_val);
    if (has_level) {
      esp_matter_attr_val_t level_val =
          esp_matter_nullable_uint8(nullable<uint8_t>(level));
      esp_matter::attribute::update(eid, LevelControl::Id,
                                    LevelControl::Attributes::CurrentLevel::Id,
                                    &level_val);
    }
  });
}

void MatterLightMapping::apply_matter_update(uint32_t cluster_id,
                                             uint32_t attribute_id,
                                             esp_matter_attr_val_t val) {
  using namespace chip::app::Clusters;
  if (cluster_id == OnOff::Id && attribute_id == OnOff::Attributes::OnOff::Id) {
    bool on = val.val.b;
    if (this->light_->remote_values.is_on() == on)
      return;
    auto call = this->light_->make_call();
    call.set_state(on);
    call.set_transition_length(0);
    call.perform();
  } else if (this->has_server_cluster(LevelControl::Id) &&
             cluster_id == LevelControl::Id &&
             attribute_id == LevelControl::Attributes::CurrentLevel::Id) {
    uint8_t level = val.val.u8;
    if (level < 1 || level > 254)
      return;
    float brightness = level / 254.0f;
    if (std::fabs(this->light_->remote_values.get_brightness() - brightness) <
        (0.5f / 254.0f))
      return;
    auto call = this->light_->make_call();
    call.set_brightness(brightness);
    call.set_transition_length(0);
    call.perform();
  }
}
#endif

#ifdef USE_SENSOR
MatterSensorMapping::MatterSensorMapping(sensor::Sensor *sensor,
                                         uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor) {}

void MatterSensorMapping::register_callbacks() {
  if (this->sensor_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](float value) { this->push_state_to_matter(value); });
}

void MatterSensorMapping::push_state_to_matter(float value) {
  using namespace chip::app::Clusters;
  uint16_t eid = this->endpoint_id();
  if (this->has_server_cluster(TemperatureMeasurement::Id)) {
    bool is_null = std::isnan(value) || value < -273.15f || value > 327.67f;
    int16_t raw = is_null ? 0 : static_cast<int16_t>(lroundf(value * 100.0f));
    chip::DeviceLayer::SystemLayer().ScheduleLambda([eid, raw, is_null]() {
      esp_matter_attr_val_t val = esp_matter_nullable_int16(
          is_null ? nullable<int16_t>() : nullable<int16_t>(raw));
      esp_matter::attribute::update(
          eid, TemperatureMeasurement::Id,
          TemperatureMeasurement::Attributes::MeasuredValue::Id, &val);
    });
  }
}
#endif

bool MatterComponent::create_endpoints_(esp_matter::node_t *node) {
  for (auto *endpoint : this->endpoint_registrations_) {
    if (!endpoint->create_endpoint(node))
      return false;
  }

  for (uint16_t endpoint_id : this->binding_endpoint_ids_) {
    esp_matter::endpoint_t *endpoint =
        esp_matter::endpoint::get(node, endpoint_id);
    if (endpoint == nullptr) {
      ESP_LOGE(TAG, "Cannot create binding cluster for missing endpoint %u",
               endpoint_id);
      return false;
    }
    esp_matter::cluster::binding::config_t config;
    esp_matter::cluster_t *binding_cluster =
        esp_matter::cluster::binding::create(endpoint, &config,
                                             esp_matter::CLUSTER_FLAG_SERVER);
    if (binding_cluster == nullptr) {
      ESP_LOGE(TAG, "Failed to create endpoint %u binding cluster",
               endpoint_id);
      return false;
    }
  }

  register_client_request_callbacks();

  return true;
}

#ifdef USE_LIGHT
MatterLightMapping *
MatterComponent::get_light_mapping_by_endpoint(uint16_t endpoint_id) {
  for (auto *mapping : this->mappings_) {
    auto *light_mapping = mapping->as_light_mapping();
    if (light_mapping != nullptr &&
        light_mapping->endpoint_id() == endpoint_id) {
      return light_mapping;
    }
  }
  return nullptr;
}
#endif // USE_LIGHT

esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data) {
#ifdef USE_LIGHT
  if (type != esp_matter::attribute::POST_UPDATE ||
      global_matter_component == nullptr)
    return ESP_OK;
  MatterLightMapping *ml =
      global_matter_component->get_light_mapping_by_endpoint(endpoint_id);
  if (ml == nullptr)
    return ESP_OK;
  // This callback runs in the Matter thread; ESPHome entities are main-loop
  // only.
  esp_matter_attr_val_t val_copy = *val;
  global_matter_component->defer_to_main_loop(
      [ml, cluster_id, attribute_id, val_copy]() {
        ml->apply_matter_update(cluster_id, attribute_id, val_copy);
      });
#endif
  return ESP_OK;
}

// Wires ESPHome entities to Matter attributes. Must run after
// esp_matter::start(). Bare endpoints and client switch endpoints have no
// wiring here.
void MatterComponent::register_endpoint_callbacks_() {
  for (auto *mapping : this->mappings_) {
    mapping->register_callbacks();
  }
}

} // namespace esphome::matter

#endif // USE_MATTER
