#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_actions.h"
#include "matter_component.h"

#include <platform/CHIPDeviceLayer.h>
#ifdef USE_BINARY_SENSOR
#include <app/clusters/boolean-state-server/CodegenIntegration.h>
#include <app/clusters/occupancy-sensor-server/CodegenIntegration.h>
#endif // USE_BINARY_SENSOR
#ifdef USE_SENSOR
#include <app/clusters/flow-measurement-server/FlowMeasurementCluster.h>
#include <app/clusters/illuminance-measurement-server/IlluminanceMeasurementCluster.h>
#include <app/clusters/pressure-measurement-server/PressureMeasurementCluster.h>
#include <app/clusters/relative-humidity-measurement-server/RelativeHumidityMeasurementCluster.h>
#include <app/clusters/temperature-measurement-server/TemperatureMeasurementCluster.h>
#include <data_model_provider/esp_matter_data_model_provider.h>
#endif // USE_SENSOR

#include <algorithm>
#include <cmath>
#include <esp_matter_cluster.h>

static const char *const TAG = "matter";

namespace esphome::matter {

namespace {

// Mirrors the start of esp-matter's private node layout to advance its endpoint
// allocator watermark.
struct EspMatterNodeHeader {
  void *endpoint_list;
  uint16_t min_unused_endpoint_id;
};

#ifdef USE_SENSOR
chip::app::DataModel::Nullable<int16_t>
temperature_sensor_value_to_matter(float value) {
  chip::app::DataModel::Nullable<int16_t> measured_value;
  if (!std::isnan(value) && value >= -273.15f && value <= 327.67f) {
    measured_value.SetNonNull(
        static_cast<int16_t>(std::lroundf(value * 100.0f)));
  }
  return measured_value;
}

chip::app::DataModel::Nullable<uint16_t>
humidity_sensor_value_to_matter(float value) {
  chip::app::DataModel::Nullable<uint16_t> measured_value;
  if (!std::isnan(value) && value >= 0.0f && value <= 100.0f) {
    measured_value.SetNonNull(
        static_cast<uint16_t>(std::lroundf(value * 100.0f)));
  }
  return measured_value;
}

chip::app::DataModel::Nullable<uint16_t>
illuminance_sensor_value_to_matter(float value) {
  chip::app::DataModel::Nullable<uint16_t> measured_value;
  if (std::isnan(value) || value < 0.0f)
    return measured_value;
  if (value == 0.0f) {
    measured_value.SetNonNull(0);
    return measured_value;
  }

  long encoded = std::lroundf(10000.0f * std::log10(value) + 1.0f);
  encoded = std::clamp(encoded, 0L, 65534L);
  measured_value.SetNonNull(static_cast<uint16_t>(encoded));
  return measured_value;
}

chip::app::DataModel::Nullable<int16_t>
pressure_sensor_value_to_matter(float value) {
  chip::app::DataModel::Nullable<int16_t> measured_value;
  if (!std::isnan(value) && value >= -327670.0f && value <= 327670.0f) {
    measured_value.SetNonNull(
        static_cast<int16_t>(std::lroundf(value / 10.0f)));
  }
  return measured_value;
}

chip::app::DataModel::Nullable<uint16_t>
flow_sensor_value_to_matter(float value) {
  chip::app::DataModel::Nullable<uint16_t> measured_value;
  if (!std::isnan(value) && value >= 0.0f && value <= 6553.4f) {
    measured_value.SetNonNull(
        static_cast<uint16_t>(std::lroundf(value * 10.0f)));
  }
  return measured_value;
}

template <typename ClusterT, chip::ClusterId ClusterId, typename ValueT>
void publish_measurement(uint16_t endpoint_id,
                         chip::app::DataModel::Nullable<ValueT> measured_value,
                         const char *name) {
  chip::DeviceLayer::SystemLayer().ScheduleLambda([endpoint_id, measured_value,
                                                   name]() {
    auto *server =
        esp_matter::data_model::provider::get_instance().registry().Get(
            {endpoint_id, ClusterId});
    if (server == nullptr) {
      ESP_LOGE(TAG, "%s cluster missing on endpoint %u", name, endpoint_id);
      return;
    }

    auto *cluster = static_cast<ClusterT *>(server);
    CHIP_ERROR err = cluster->SetMeasuredValue(measured_value);
    if (err != CHIP_NO_ERROR) {
      ESP_LOGE(TAG, "Failed to update %s on endpoint %u: %" CHIP_ERROR_FORMAT,
               name, endpoint_id, err.Format());
    }
  });
}
#endif // USE_SENSOR

#ifdef USE_BINARY_SENSOR
template <typename FindCluster, typename SetValue>
void publish_binary_state(uint16_t endpoint_id, bool value, const char *name,
                          FindCluster find_cluster, SetValue set_value) {
  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [endpoint_id, value, name, find_cluster, set_value]() {
        auto *cluster = find_cluster(endpoint_id);
        if (cluster == nullptr) {
          ESP_LOGE(TAG, "%s cluster missing on endpoint %u", name, endpoint_id);
          return;
        }
        set_value(cluster, value);
      });
}
#endif // USE_BINARY_SENSOR

} // namespace

void MatterComponent::register_endpoint(uint16_t endpoint_id) {
  for (uint16_t registered_endpoint_id : this->endpoint_ids_) {
    if (registered_endpoint_id == endpoint_id)
      return;
  }
  this->endpoint_ids_.push_back(endpoint_id);
}

void MatterComponent::register_binding(uint16_t endpoint_id) {
  this->register_endpoint(endpoint_id);
  for (uint16_t registered_endpoint_id : this->binding_endpoint_ids_) {
    if (registered_endpoint_id == endpoint_id)
      return;
  }
  this->binding_endpoint_ids_.push_back(endpoint_id);
}

bool MatterEndpointMappingBase::has_server_cluster(uint32_t cluster_id) const {
  auto *endpoint = esp_matter::endpoint::get(this->endpoint_id());
  if (endpoint == nullptr)
    return false;
  auto *cluster = esp_matter::cluster::get(endpoint, cluster_id);
  return cluster != nullptr && (esp_matter::cluster::get_flags(cluster) &
                                esp_matter::CLUSTER_FLAG_SERVER);
}

// -------------------------------------------------------------------- //
//  Lights                                                              //
// -------------------------------------------------------------------- //

#ifdef USE_LIGHT

// Register lights from endpoints.py
void MatterComponent::map_light_to_endpoint(light::LightState *light,
                                            uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterLightMapping(light, endpoint_id));
}

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

// -------------------------------------------------------------------- //
//  Sensors                                                             //
// -------------------------------------------------------------------- //

#ifdef USE_SENSOR

// Register sensors from endpoints.py
void MatterComponent::map_sensor_to_endpoint(sensor::Sensor *sensor,
                                             uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterSensorMapping(sensor, endpoint_id));
}

MatterSensorMapping::MatterSensorMapping(sensor::Sensor *sensor,
                                         uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), sensor_(sensor) {}

void MatterSensorMapping::register_callbacks() {
  if (this->sensor_ == nullptr)
    return;
  this->sensor_->add_on_state_callback(
      [this](float value) { this->push_state_to_matter(value); });
  if (this->sensor_->has_state())
    this->push_state_to_matter(this->sensor_->state);
}

void MatterSensorMapping::push_state_to_matter(float value) {
  using namespace chip::app::Clusters;
  uint16_t eid = this->endpoint_id();
  if (this->has_server_cluster(TemperatureMeasurement::Id)) {
    publish_measurement<TemperatureMeasurementCluster,
                        TemperatureMeasurement::Id>(
        eid, temperature_sensor_value_to_matter(value), "temperature");
  }
  if (this->has_server_cluster(RelativeHumidityMeasurement::Id)) {
    publish_measurement<RelativeHumidityMeasurementCluster,
                        RelativeHumidityMeasurement::Id>(
        eid, humidity_sensor_value_to_matter(value), "humidity");
  }
  if (this->has_server_cluster(IlluminanceMeasurement::Id)) {
    publish_measurement<IlluminanceMeasurementCluster,
                        IlluminanceMeasurement::Id>(
        eid, illuminance_sensor_value_to_matter(value), "illuminance");
  }
  if (this->has_server_cluster(PressureMeasurement::Id)) {
    publish_measurement<PressureMeasurementCluster, PressureMeasurement::Id>(
        eid, pressure_sensor_value_to_matter(value), "pressure");
  }
  if (this->has_server_cluster(FlowMeasurement::Id)) {
    publish_measurement<FlowMeasurementCluster, FlowMeasurement::Id>(
        eid, flow_sensor_value_to_matter(value), "flow");
  }
}
#endif // USE_SENSOR

// -------------------------------------------------------------------- //
//  Binary sensors                                                      //
// -------------------------------------------------------------------- //

#ifdef USE_BINARY_SENSOR

// Register binary sensors from endpoints.py
void MatterComponent::map_binary_sensor_to_endpoint(
    binary_sensor::BinarySensor *binary_sensor, uint16_t endpoint_id) {
  this->mappings_.push_back(
      new MatterBinarySensorMapping(binary_sensor, endpoint_id));
}

MatterBinarySensorMapping::MatterBinarySensorMapping(
    binary_sensor::BinarySensor *binary_sensor, uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), binary_sensor_(binary_sensor) {}

void MatterBinarySensorMapping::register_callbacks() {
  if (this->binary_sensor_ == nullptr)
    return;
  this->binary_sensor_->add_on_state_callback(
      [this](bool value) { this->push_state_to_matter(value); });
  if (this->binary_sensor_->has_state())
    this->push_state_to_matter(this->binary_sensor_->state);
}

void MatterBinarySensorMapping::push_state_to_matter(bool value) {
  using namespace chip::app::Clusters;
  uint16_t eid = this->endpoint_id();
  if (this->has_server_cluster(OccupancySensing::Id)) {
    publish_binary_state(eid, value, "occupancy",
                         OccupancySensing::FindClusterOnEndpoint,
                         [](OccupancySensingCluster *cluster, bool occupied) {
                           cluster->SetOccupancy(occupied);
                         });
  }
  if (this->has_server_cluster(BooleanState::Id)) {
    publish_binary_state(eid, value, "Boolean State",
                         BooleanState::FindClusterOnEndpoint,
                         [](BooleanStateCluster *cluster, bool state) {
                           cluster->SetStateValue(state);
                         });
  }
}

#endif // USE_BINARY_SENSOR

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

    // Add binding cluster
    if (std::find(this->binding_endpoint_ids_.begin(),
                  this->binding_endpoint_ids_.end(),
                  endpoint_id) != this->binding_endpoint_ids_.end()) {
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

    ESP_LOGV(TAG, "Created endpoint %u", endpoint_id);
  }

  // Add device types to endpoints
  for (auto *device_type_registration : this->device_type_registrations_) {
    // add_clusters is defined in matter_endpoints.h
    if (!device_type_registration->add_clusters(node))
      return false;
  }

  register_client_request_callbacks();

  return true;
}

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
