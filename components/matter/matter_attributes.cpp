#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_attributes.h"
#include "matter_component.h"

#include <platform/CHIPDeviceLayer.h>

#include <cinttypes>
#include <variant>

static const char *const TAG = "matter";

namespace esphome::matter {

void defer_to_main_loop(MatterComponent *component, std::function<void()> &&f) {
  component->defer_to_main_loop(std::move(f));
}

bool convert_attribute_value(const esp_matter_attr_val_t &value, bool &out) {
  if (value.get_base_type() != ESP_MATTER_VAL_TYPE_BOOLEAN)
    return false;
  out = value.val.b;
  return true;
}

bool convert_attribute_value(const esp_matter_attr_val_t &value, float &out) {
  if (value.get_base_type() != ESP_MATTER_VAL_TYPE_FLOAT)
    return false;
  out = value.val.f;
  return true;
}

bool convert_attribute_value(const esp_matter_attr_val_t &value, int64_t &out) {
  switch (value.get_base_type()) {
  case ESP_MATTER_VAL_TYPE_INT8:
    out = value.val.i8;
    return true;
  case ESP_MATTER_VAL_TYPE_INT16:
    out = value.val.i16;
    return true;
  case ESP_MATTER_VAL_TYPE_INT32:
    out = value.val.i32;
    return true;
  case ESP_MATTER_VAL_TYPE_INT64:
    out = value.val.i64;
    return true;
  default:
    return false;
  }
}

bool convert_attribute_value(const esp_matter_attr_val_t &value,
                             uint64_t &out) {
  switch (value.get_base_type()) {
  case ESP_MATTER_VAL_TYPE_UINT8:
  case ESP_MATTER_VAL_TYPE_ENUM8:
  case ESP_MATTER_VAL_TYPE_BITMAP8:
    out = value.val.u8;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT16:
  case ESP_MATTER_VAL_TYPE_ENUM16:
  case ESP_MATTER_VAL_TYPE_BITMAP16:
    out = value.val.u16;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT32:
  case ESP_MATTER_VAL_TYPE_BITMAP32:
    out = value.val.u32;
    return true;
  case ESP_MATTER_VAL_TYPE_UINT64:
    out = value.val.u64;
    return true;
  default:
    return false;
  }
}

bool convert_attribute_value(const esp_matter_attr_val_t &value,
                             std::string &out) {
  auto type = value.get_base_type();
  if (type != ESP_MATTER_VAL_TYPE_CHAR_STRING &&
      type != ESP_MATTER_VAL_TYPE_LONG_CHAR_STRING)
    return false;
  out.assign(reinterpret_cast<const char *>(value.val.a.b), value.val.a.s);
  return true;
}

namespace {

using AttributeActionValue =
    std::variant<bool, float, int64_t, uint64_t, std::string>;

struct AttributeActionUpdate {
  uint16_t endpoint_id;
  uint32_t cluster_id;
  uint32_t attribute_id;
  AttributeActionValue value;
};

void set_attribute_value_on_matter_thread(uint16_t endpoint_id,
                                          uint32_t cluster_id,
                                          uint32_t attribute_id,
                                          const AttributeActionValue &value) {
  esp_matter_val_type_t type = esp_matter::attribute::get_val_type(
      endpoint_id, cluster_id, attribute_id);
  if (type == ESP_MATTER_VAL_TYPE_INVALID) {
    ESP_LOGE(TAG,
             "Cannot set unknown attribute: endpoint=%u cluster=0x%08" PRIx32
             " attribute=0x%08" PRIx32,
             endpoint_id, cluster_id, attribute_id);
    return;
  }

  esp_matter_attr_val_t attribute_value;
  attribute_value.type = type;
  switch (attribute_value.get_base_type()) {
  case ESP_MATTER_VAL_TYPE_BOOLEAN:
    if (!std::holds_alternative<bool>(value))
      return;
    attribute_value.val.b = std::get<bool>(value);
    break;
  case ESP_MATTER_VAL_TYPE_FLOAT:
    if (!std::holds_alternative<float>(value))
      return;
    attribute_value.val.f = std::get<float>(value);
    break;
  case ESP_MATTER_VAL_TYPE_INT8:
  case ESP_MATTER_VAL_TYPE_INT16:
  case ESP_MATTER_VAL_TYPE_INT32:
  case ESP_MATTER_VAL_TYPE_INT64: {
    if (!std::holds_alternative<int64_t>(value))
      return;
    int64_t number = std::get<int64_t>(value);
    if (attribute_value.get_base_type() == ESP_MATTER_VAL_TYPE_INT8)
      attribute_value.val.i8 = static_cast<int8_t>(number);
    else if (attribute_value.get_base_type() == ESP_MATTER_VAL_TYPE_INT16)
      attribute_value.val.i16 = static_cast<int16_t>(number);
    else if (attribute_value.get_base_type() == ESP_MATTER_VAL_TYPE_INT32)
      attribute_value.val.i32 = static_cast<int32_t>(number);
    else
      attribute_value.val.i64 = number;
    break;
  }
  case ESP_MATTER_VAL_TYPE_UINT8:
  case ESP_MATTER_VAL_TYPE_ENUM8:
  case ESP_MATTER_VAL_TYPE_BITMAP8:
  case ESP_MATTER_VAL_TYPE_UINT16:
  case ESP_MATTER_VAL_TYPE_ENUM16:
  case ESP_MATTER_VAL_TYPE_BITMAP16:
  case ESP_MATTER_VAL_TYPE_UINT32:
  case ESP_MATTER_VAL_TYPE_BITMAP32:
  case ESP_MATTER_VAL_TYPE_UINT64: {
    if (!std::holds_alternative<uint64_t>(value))
      return;
    uint64_t number = std::get<uint64_t>(value);
    auto base_type = attribute_value.get_base_type();
    if (base_type == ESP_MATTER_VAL_TYPE_UINT8 ||
        base_type == ESP_MATTER_VAL_TYPE_ENUM8 ||
        base_type == ESP_MATTER_VAL_TYPE_BITMAP8)
      attribute_value.val.u8 = static_cast<uint8_t>(number);
    else if (base_type == ESP_MATTER_VAL_TYPE_UINT16 ||
             base_type == ESP_MATTER_VAL_TYPE_ENUM16 ||
             base_type == ESP_MATTER_VAL_TYPE_BITMAP16)
      attribute_value.val.u16 = static_cast<uint16_t>(number);
    else if (base_type == ESP_MATTER_VAL_TYPE_UINT32 ||
             base_type == ESP_MATTER_VAL_TYPE_BITMAP32)
      attribute_value.val.u32 = static_cast<uint32_t>(number);
    else
      attribute_value.val.u64 = number;
    break;
  }
  case ESP_MATTER_VAL_TYPE_CHAR_STRING:
  case ESP_MATTER_VAL_TYPE_LONG_CHAR_STRING: {
    if (!std::holds_alternative<std::string>(value))
      return;
    const auto &string_value = std::get<std::string>(value);
    attribute_value.val.a.b =
        reinterpret_cast<uint8_t *>(const_cast<char *>(string_value.data()));
    attribute_value.val.a.s = string_value.size();
    attribute_value.val.a.t = string_value.size();
    attribute_value.val.a.max =
        attribute_value.get_base_type() == ESP_MATTER_VAL_TYPE_CHAR_STRING
            ? UINT8_MAX
            : UINT16_MAX;
    break;
  }
  default:
    ESP_LOGE(TAG,
             "Unsupported attribute type %u: endpoint=%u cluster=0x%08" PRIx32
             " attribute=0x%08" PRIx32,
             static_cast<unsigned>(type), endpoint_id, cluster_id,
             attribute_id);
    return;
  }

  esp_err_t err = esp_matter::attribute::update(endpoint_id, cluster_id,
                                                attribute_id, &attribute_value);
  if (err != ESP_OK) {
    ESP_LOGE(TAG,
             "Failed to set attribute: endpoint=%u cluster=0x%08" PRIx32
             " attribute=0x%08" PRIx32 ": %s",
             endpoint_id, cluster_id, attribute_id, esp_err_to_name(err));
  }
}

void update_attribute_action_on_matter_thread(intptr_t context) {
  auto *update = reinterpret_cast<AttributeActionUpdate *>(context);
  set_attribute_value_on_matter_thread(update->endpoint_id, update->cluster_id,
                                       update->attribute_id, update->value);
  delete update;
}

template <typename T>
void schedule_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                              uint32_t attribute_id, T value) {
  auto *update =
      new AttributeActionUpdate{endpoint_id, cluster_id, attribute_id,
                                AttributeActionValue(std::move(value))};
  CHIP_ERROR err = chip::DeviceLayer::PlatformMgr().ScheduleWork(
      update_attribute_action_on_matter_thread,
      reinterpret_cast<intptr_t>(update));
  if (err != CHIP_NO_ERROR) {
    ESP_LOGE(TAG, "Failed to schedule Matter attribute update: %s",
             err.AsString());
    delete update;
  }
}

} // namespace

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, bool value) {
  schedule_attribute_value(endpoint_id, cluster_id, attribute_id, value);
}

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, float value) {
  schedule_attribute_value(endpoint_id, cluster_id, attribute_id, value);
}

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, int64_t value) {
  schedule_attribute_value(endpoint_id, cluster_id, attribute_id, value);
}

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, uint64_t value) {
  schedule_attribute_value(endpoint_id, cluster_id, attribute_id, value);
}

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, const std::string &value) {
  schedule_attribute_value(endpoint_id, cluster_id, attribute_id, value);
}

esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data) {
  ESP_LOGV(TAG,
           "Attribute update: type=%u, endpoint=%u, cluster=0x%08" PRIx32
           ", attribute=0x%08" PRIx32,
           static_cast<unsigned>(type), endpoint_id, cluster_id, attribute_id);

  if (type != esp_matter::attribute::POST_UPDATE ||
      global_matter_component == nullptr || val == nullptr)
    return ESP_OK;

  for (auto *trigger : global_matter_component->attribute_triggers_) {
    if (trigger->matches(endpoint_id, cluster_id, attribute_id))
      trigger->dispatch(*val);
  }

#ifdef USE_LIGHT
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

} // namespace esphome::matter

#endif // USE_MATTER
