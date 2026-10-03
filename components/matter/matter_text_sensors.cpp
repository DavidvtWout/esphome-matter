#include "matter_text_sensors.h"

#ifdef USE_MATTER

#ifdef USE_TEXT_SENSOR
#include "matter_component.h"

#include <app/server/Server.h>
#include <platform/CHIPDeviceLayer.h>

#include <cinttypes>
#include <cstdio>
#include <vector>
#endif

namespace esphome::matter {

std::string format_manual_pairing_code(const std::string &code) {
  if (code.length() != 11)
    return code;
  return code.substr(0, 4) + "-" + code.substr(4, 3) + "-" + code.substr(7, 4);
}

#ifdef USE_TEXT_SENSOR
void MatterComponent::publish_commissioning_code_sensors_() {
  if (this->manual_pairing_code_sensor_ != nullptr &&
      !this->manual_pairing_code_.empty()) {
    this->manual_pairing_code_sensor_->publish_state(
        format_manual_pairing_code(this->manual_pairing_code_));
  }
  if (this->qr_code_sensor_ != nullptr && !this->qr_code_.empty())
    this->qr_code_sensor_->publish_state(this->qr_code_);
}

void MatterComponent::schedule_fabric_sensor_update() {
  this->defer([this]() { this->publish_fabric_sensors_(); });
}

MatterFabricSensorRegistration &
MatterComponent::get_fabric_sensors_(size_t slot) {
  for (auto &sensors : this->fabric_sensors_) {
    if (sensors.slot == slot)
      return sensors;
  }
  this->fabric_sensors_.emplace_back();
  this->fabric_sensors_.back().slot = slot;
  return this->fabric_sensors_.back();
}

void MatterComponent::set_fabric_compressed_id_sensor(
    size_t slot, text_sensor::TextSensor *sensor) {
  this->get_fabric_sensors_(slot).compressed_id = sensor;
}

void MatterComponent::set_fabric_id_sensor(size_t slot,
                                           text_sensor::TextSensor *sensor) {
  this->get_fabric_sensors_(slot).fabric_id = sensor;
}

void MatterComponent::set_fabric_label_sensor(size_t slot,
                                              text_sensor::TextSensor *sensor) {
  this->get_fabric_sensors_(slot).label = sensor;
}

void MatterComponent::set_fabric_node_id_sensor(
    size_t slot, text_sensor::TextSensor *sensor) {
  this->get_fabric_sensors_(slot).node_id = sensor;
}

void MatterComponent::set_fabric_vendor_id_sensor(
    size_t slot, text_sensor::TextSensor *sensor) {
  this->get_fabric_sensors_(slot).vendor_id = sensor;
}

void MatterComponent::publish_fabric_sensors_() {
  struct FabricSensorValues {
    size_t slot;
    bool present{false};
    std::string compressed_id;
    std::string fabric_id;
    std::string label;
    std::string node_id;
    std::string vendor_id;
  };
  std::vector<FabricSensorValues> values;
  values.reserve(this->fabric_sensors_.size());
  for (const auto &sensors : this->fabric_sensors_) {
    values.emplace_back();
    values.back().slot = sensors.slot;
  }

  chip::DeviceLayer::PlatformMgr().LockChipStack();
  size_t slot = 0;
  for (const auto &fabric : chip::Server::GetInstance().GetFabricTable()) {
    for (auto &value : values) {
      if (value.slot != slot)
        continue;
      value.present = true;
      char compressed_id[19];
      snprintf(compressed_id, sizeof(compressed_id), "0x%016" PRIX64,
               fabric.GetCompressedFabricId());
      value.compressed_id = compressed_id;
      char fabric_id[19];
      snprintf(fabric_id, sizeof(fabric_id), "0x%016" PRIX64,
               fabric.GetFabricId());
      value.fabric_id = fabric_id;
      const chip::CharSpan label = fabric.GetFabricLabel();
      value.label.assign(label.data(), label.size());
      char node_id[19];
      snprintf(node_id, sizeof(node_id), "0x%016" PRIX64, fabric.GetNodeId());
      value.node_id = node_id;
      char vendor_id[7];
      snprintf(vendor_id, sizeof(vendor_id), "0x%04" PRIX16,
               static_cast<uint16_t>(fabric.GetVendorId()));
      value.vendor_id = vendor_id;
      break;
    }
    slot++;
  }
  chip::DeviceLayer::PlatformMgr().UnlockChipStack();

  for (size_t i = 0; i < values.size(); i++) {
    const auto &sensors = this->fabric_sensors_[i];
    const auto &value = values[i];
    if (sensors.compressed_id != nullptr &&
        (value.present || sensors.compressed_id->has_state()))
      sensors.compressed_id->publish_state(value.compressed_id);
    if (sensors.fabric_id != nullptr &&
        (value.present || sensors.fabric_id->has_state()))
      sensors.fabric_id->publish_state(value.fabric_id);
    if (sensors.label != nullptr &&
        (value.present || sensors.label->has_state()))
      sensors.label->publish_state(value.label);
    if (sensors.node_id != nullptr &&
        (value.present || sensors.node_id->has_state()))
      sensors.node_id->publish_state(value.node_id);
    if (sensors.vendor_id != nullptr &&
        (value.present || sensors.vendor_id->has_state()))
      sensors.vendor_id->publish_state(value.vendor_id);
  }
}
#endif

} // namespace esphome::matter

#endif // USE_MATTER
