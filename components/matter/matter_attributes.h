#pragma once

#include "esphome/core/automation.h"
#include "esphome/core/defines.h"
#include "esphome/core/helpers.h"
#ifdef USE_MATTER

#include "matter_conversions.h"

#include <esp_matter.h>

#include <cstdint>
#include <functional>
#include <string>
#include <utility>

namespace esphome::matter {

class MatterComponent;

void defer_to_main_loop(MatterComponent *component, std::function<void()> &&f);

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
void replay_attribute_triggers(MatterComponent *component);

class MatterAttributeDispatchGuard {
public:
  MatterAttributeDispatchGuard(uint16_t endpoint_id, uint32_t cluster_id,
                               uint32_t attribute_id);
  ~MatterAttributeDispatchGuard();

protected:
  bool previous_active_;
  uint16_t previous_endpoint_id_;
  uint32_t previous_cluster_id_;
  uint32_t previous_attribute_id_;
};

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
  uint16_t endpoint_id() const { return this->endpoint_id_; }
  uint32_t cluster_id() const { return this->cluster_id_; }
  uint32_t attribute_id() const { return this->attribute_id_; }
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
    if (!conversion::convert_attribute_value(value, converted))
      return;

    {
      LockGuard guard(this->pending_mutex_);
      this->pending_value_ = std::move(converted);
      if (this->dispatch_pending_)
        return;
      this->dispatch_pending_ = true;
    }

    defer_to_main_loop(this->parent_, [this]() {
      T pending_value;
      {
        LockGuard guard(this->pending_mutex_);
        pending_value = this->pending_value_;
        this->dispatch_pending_ = false;
      }
      MatterAttributeDispatchGuard dispatch_guard(
          this->endpoint_id_, this->cluster_id_, this->attribute_id_);
      this->trigger(pending_value);
    });
  }

protected:
  MatterComponent *parent_;
  Mutex pending_mutex_;
  T pending_value_{};
  bool dispatch_pending_{false};
};

esp_err_t
endpoint_attribute_update_cb(esp_matter::attribute::callback_type_t type,
                             uint16_t endpoint_id, uint32_t cluster_id,
                             uint32_t attribute_id, esp_matter_attr_val_t *val,
                             void *priv_data);

} // namespace esphome::matter

#endif // USE_MATTER
