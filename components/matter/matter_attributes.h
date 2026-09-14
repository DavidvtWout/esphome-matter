#pragma once

#include "esphome/core/automation.h"
#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include <esp_matter.h>

#include <cstdint>
#include <functional>
#include <string>

namespace esphome::matter {

class MatterComponent;

void defer_to_main_loop(MatterComponent *component, std::function<void()> &&f);

bool convert_attribute_value(const esp_matter_attr_val_t &value, bool &out);
bool convert_attribute_value(const esp_matter_attr_val_t &value, float &out);
bool convert_attribute_value(const esp_matter_attr_val_t &value, int64_t &out);
bool convert_attribute_value(const esp_matter_attr_val_t &value, uint64_t &out);
bool convert_attribute_value(const esp_matter_attr_val_t &value,
                             std::string &out);

void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, bool value);
void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, float value);
void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, int64_t value);
void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, uint64_t value);
void set_attribute_value(uint16_t endpoint_id, uint32_t cluster_id,
                         uint32_t attribute_id, const std::string &value);

class MatterAttributeTriggerBase {
public:
  MatterAttributeTriggerBase(uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id)
      : endpoint_id_(endpoint_id), cluster_id_(cluster_id),
        attribute_id_(attribute_id) {}
  virtual ~MatterAttributeTriggerBase() = default;

  bool matches(uint16_t endpoint_id, uint32_t cluster_id,
               uint32_t attribute_id) const {
    return this->endpoint_id_ == endpoint_id &&
           this->cluster_id_ == cluster_id &&
           this->attribute_id_ == attribute_id;
  }
  virtual void dispatch(const esp_matter_attr_val_t &value) = 0;

protected:
  uint16_t endpoint_id_;
  uint32_t cluster_id_;
  uint32_t attribute_id_;
};

template <typename T>
class MatterAttributeTrigger : public Trigger<T>,
                               public MatterAttributeTriggerBase {
public:
  MatterAttributeTrigger(MatterComponent *parent, uint16_t endpoint_id,
                         uint32_t cluster_id, uint32_t attribute_id)
      : MatterAttributeTriggerBase(endpoint_id, cluster_id, attribute_id),
        parent_(parent) {}

  void dispatch(const esp_matter_attr_val_t &value) override {
    if (value.is_null())
      return;
    T converted{};
    if (!convert_attribute_value(value, converted))
      return;
    defer_to_main_loop(this->parent_,
                       [this, converted]() { this->trigger(converted); });
  }

protected:
  MatterComponent *parent_;
};

esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data);

} // namespace esphome::matter

#endif // USE_MATTER
