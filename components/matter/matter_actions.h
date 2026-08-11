#pragma once
#include "esphome/core/defines.h"

#ifdef USE_MATTER

#include "esphome/core/automation.h"
#include "matter_endpoints.h"

#include <esp_matter.h>

#include <string>

namespace esphome::matter {

// Registers the esp_matter client request callbacks that build outgoing
// command payloads. Called once during endpoint creation.
void register_client_request_callbacks();

// Sends a client command through the Binding cluster of the given local
// endpoint. command_data must use esp-matter's JSON command-data format.
void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster,
                         chip::CommandId command,
                         const char *command_data = "{}");

template <typename... Ts>
class MatterInvokeBoundCommandAction : public Action<Ts...> {
public:
  void set_endpoint_ref(MatterEndpointRef *endpoint_ref) {
    this->endpoint_ref_ = endpoint_ref;
  }
  void set_endpoint_id(uint16_t endpoint_id) {
    this->endpoint_id_ = endpoint_id;
  }
  void set_cluster_id(uint32_t cluster_id) { this->cluster_id_ = cluster_id; }
  void set_command_id(uint32_t command_id) { this->command_id_ = command_id; }
  void set_payload(const char *payload) { this->payload_ = payload; }

  void play(Ts... x) override {
    uint16_t endpoint_id = this->endpoint_ref_ != nullptr
                               ? this->endpoint_ref_->endpoint_id
                               : this->endpoint_id_;
    send_client_command(endpoint_id, this->cluster_id_, this->command_id_,
                        this->payload_.c_str());
  }

protected:
  MatterEndpointRef *endpoint_ref_{nullptr};
  uint16_t endpoint_id_{0};
  uint32_t cluster_id_{0};
  uint32_t command_id_{0};
  std::string payload_{"{}"};
};

} // namespace esphome::matter

#endif // USE_MATTER
