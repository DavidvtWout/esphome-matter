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

void MatterComponent::register_endpoint(uint16_t endpoint_id) {
  for (uint16_t registered_endpoint_id : this->endpoint_ids_) {
    if (registered_endpoint_id == endpoint_id)
      return;
  }
  this->endpoint_ids_.push_back(endpoint_id);
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
  if (!this->endpoint_ids_.empty()) {
    // esp-matter only resumes endpoint IDs below its private
    // min_unused_endpoint_id. ESPHome creates all static endpoints before
    // esp_matter::start(), so advance the single node's allocator watermark
    // once before resuming them.
    uint16_t max_endpoint_id = *std::max_element(this->endpoint_ids_.begin(),
                                                 this->endpoint_ids_.end());
    auto *node_header = reinterpret_cast<EspMatterNodeHeader *>(node);
    if (node_header->min_unused_endpoint_id <= max_endpoint_id)
      node_header->min_unused_endpoint_id = max_endpoint_id + 1;
  }

  // Create endpoints
  for (uint16_t endpoint_id : this->endpoint_ids_) {
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

    ESP_LOGV(TAG, "Endpoint created: id=%u", endpoint_id);
  }

  // Add device types to endpoints
  for (auto *device_type_registration : this->device_type_registrations_) {
    if (!device_type_registration->add_clusters(node))
      return false;
  }

  // Add extra optional clusters
  for (auto *cluster_registration : this->cluster_registrations_) {
    if (!cluster_registration->add_cluster(node))
      return false;
  }

  // Add features which were not needed in the cluster config during creation.
  for (auto *feature_registration : this->feature_registrations_) {
    if (!feature_registration->add_feature(node))
      return false;
  }

  register_client_request_callbacks();

  return true;
}

bool MatterFeatureRegistration::add_feature(esp_matter::node_t *node) {
  esp_matter::endpoint_t *endpoint =
      esp_matter::endpoint::get(node, this->endpoint_id_);
  if (endpoint == nullptr) {
    ESP_LOGE(TAG, "Cannot add %s feature for missing endpoint %u",
             this->feature_name_, this->endpoint_id_);
    return false;
  }

  esp_matter::cluster_t *cluster =
      esp_matter::cluster::get(endpoint, this->cluster_id_);
  // Device-level feature names apply only to clusters which are actually
  // created for the endpoint.
  if (cluster == nullptr)
    return true;

  esp_matter_attr_val_t feature_map;
  if (esp_matter::attribute::get_val(this->endpoint_id_, this->cluster_id_,
                                     0xFFFC, &feature_map) != ESP_OK) {
    ESP_LOGE(TAG, "Failed to read FeatureMap for %s cluster on endpoint %u",
             this->cluster_name_, this->endpoint_id_);
    return false;
  }
  if (feature_map.val.u32 & this->feature_id_)
    return true;

  if (this->add_fn_(cluster) != ESP_OK) {
    ESP_LOGE(TAG, "Failed to add %s feature to %s cluster on endpoint %u",
             this->feature_name_, this->cluster_name_, this->endpoint_id_);
    return false;
  }
  ESP_LOGD(TAG, "Added %s feature to %s cluster on endpoint %u",
           this->feature_name_, this->cluster_name_, this->endpoint_id_);
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
#endif // USE_LIGHT
  return ESP_OK;
}

// Wires ESPHome entities to Matter attributes. Must run after
// esp_matter::start().
void MatterComponent::register_endpoint_callbacks_() {
  for (auto *mapping : this->mappings_) {
    mapping->register_callbacks();
  }
}

} // namespace esphome::matter

#endif // USE_MATTER
