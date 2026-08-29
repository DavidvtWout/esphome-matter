#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER
#include "esphome/core/automation.h"

#include <esp_matter.h>

#include <string>

namespace esphome::matter {

// Registers the esp_matter client request callbacks that build outgoing
// command data payloads. Called once during endpoint creation.
void register_client_request_callbacks();

// Sends a client command through the Binding cluster of the given local
// endpoint. command_data must use esp-matter's JSON command-data format.
esp_err_t send_client_command(uint16_t endpoint_id, chip::ClusterId cluster,
                              chip::CommandId command,
                              const char *command_data = "{}");

template <typename... Ts> class MatterSendCommandAction : public Action<Ts...> {
public:
  void set_endpoint_id(uint16_t endpoint_id) {
    this->endpoint_id_ = endpoint_id;
  }
  void set_cluster_id(uint32_t cluster_id) { this->cluster_id_ = cluster_id; }
  void set_command_id(uint32_t command_id) { this->command_id_ = command_id; }
  void set_data(const char *data) { this->data_ = data; }

  void play(Ts... x) override {
    send_client_command(this->endpoint_id_, this->cluster_id_,
                        this->command_id_, this->data_.c_str());
  }

protected:
  uint16_t endpoint_id_{0};
  uint32_t cluster_id_{0};
  uint32_t command_id_{0};
  std::string data_{"{}"};
};

// Sets a local Matter server attribute to an already converted Matter value.
// The caller is responsible for constructing a value with the attribute's
// expected type and unit.
esp_err_t set_attribute(uint16_t endpoint_id, chip::ClusterId cluster,
                        chip::AttributeId attribute,
                        esp_matter_attr_val_t value);

template <typename... Ts>
class MatterSetAttributeAction : public Action<Ts...> {
public:
  void set_endpoint_id(uint16_t endpoint_id) {
    this->endpoint_id_ = endpoint_id;
  }
  void set_cluster_id(uint32_t cluster_id) { this->cluster_id_ = cluster_id; }
  void set_attribute_id(uint32_t attribute_id) {
    this->attribute_id_ = attribute_id;
  }
  void set_value(esp_matter_attr_val_t value) { this->value_ = value; }

  void play(Ts... x) override {
    set_attribute(this->endpoint_id_, this->cluster_id_, this->attribute_id_,
                  this->value_);
  }

protected:
  uint16_t endpoint_id_{0};
  uint32_t cluster_id_{0};
  uint32_t attribute_id_{0};
  esp_matter_attr_val_t value_{};
};

} // namespace esphome::matter

#endif // USE_MATTER
