#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "esphome/core/log.h"
#include "matter_attributes.h"
#include "matter_component.h"

#include <cinttypes>

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
