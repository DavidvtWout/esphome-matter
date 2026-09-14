#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_actions.h"
#include "matter_component.h"

#include <algorithm>
#include <cmath>
#include <esp_matter_cluster.h>
#include <platform/CHIPDeviceLayer.h>

static const char *const TAG = "matter";

namespace esphome::matter {

namespace {

// Mirrors the start of esp-matter's private node layout to advance its endpoint
// allocator watermark.
struct EspMatterNodeHeader {
  void *endpoint_list;
  uint16_t min_unused_endpoint_id;
};

} // namespace

void MatterComponent::register_endpoint(uint16_t endpoint_id,
                                        MatterEndpointBuildFn build_fn) {
  for (const auto &registration : this->endpoint_registrations_) {
    if (registration.endpoint_id == endpoint_id)
      return;
  }
  this->endpoint_registrations_.push_back({endpoint_id, build_fn});
}

#ifdef USE_LIGHT
void MatterComponent::map_light_to_endpoint(light::LightState *light,
                                            uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterLightMapping(light, endpoint_id));
}
#endif // USE_LIGHT

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
#endif // USE_LIGHT

bool MatterComponent::create_endpoints_(esp_matter::node_t *node) {
  if (!this->endpoint_registrations_.empty()) {
    // esp-matter only resumes endpoint IDs below its private
    // min_unused_endpoint_id. ESPHome creates all static endpoints before
    // esp_matter::start(), so advance the single node's allocator watermark
    // once before resuming them.
    auto max_registration =
        std::max_element(this->endpoint_registrations_.begin(),
                         this->endpoint_registrations_.end(),
                         [](const auto &lhs, const auto &rhs) {
                           return lhs.endpoint_id < rhs.endpoint_id;
                         });
    uint16_t max_endpoint_id = max_registration->endpoint_id;
    auto *node_header = reinterpret_cast<EspMatterNodeHeader *>(node);
    if (node_header->min_unused_endpoint_id <= max_endpoint_id)
      node_header->min_unused_endpoint_id = max_endpoint_id + 1;
  }

  // Create endpoints
  for (const auto &registration : this->endpoint_registrations_) {
    uint16_t endpoint_id = registration.endpoint_id;
    if (esp_matter::endpoint::get(node, endpoint_id) != nullptr) {
      ESP_LOGE(TAG, "Matter endpoint id %u is already in use", endpoint_id);
      return false;
    }

    esp_matter::endpoint_t *endpoint = esp_matter::endpoint::resume(
        node, esp_matter::ENDPOINT_FLAG_NONE, endpoint_id, nullptr);
    if (endpoint == nullptr) {
      ESP_LOGE(TAG, "Failed to create endpoint %u", endpoint_id);
      return false;
    }

    // Create "empty" descriptor cluster. Connectedhomip fills this internally.
    esp_matter::cluster::descriptor::config_t descriptor_config;
    esp_matter::cluster_t *descriptor_cluster =
        esp_matter::cluster::descriptor::create(
            endpoint, &descriptor_config, esp_matter::CLUSTER_FLAG_SERVER);
    if (descriptor_cluster == nullptr) {
      ESP_LOGE(TAG, "Failed to create descriptor cluster for endpoint %u",
               endpoint_id);
      return false;
    }

    if (registration.build_fn == nullptr || !registration.build_fn(endpoint)) {
      ESP_LOGE(TAG, "Failed to build endpoint %u", endpoint_id);
      return false;
    }

    ESP_LOGD(TAG, "Endpoint created: id=%u", endpoint_id);
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

// Wires ESPHome entities to Matter attributes. Must run after
// esp_matter::start().
void MatterComponent::register_endpoint_callbacks_() {
  for (auto *mapping : this->mappings_) {
    mapping->register_callbacks();
  }
}

} // namespace esphome::matter

#endif // USE_MATTER
