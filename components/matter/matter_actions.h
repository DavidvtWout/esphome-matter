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
//
// Group (multicast) bindings are served immediately. Unicast bindings are
// served from a per-(endpoint, cluster) queue that the main loop drains, which
// bounds how fast commands are sent (MatterComponent::min_command_interval) and
// lets a newer command supersede an older one that has not gone out yet.
//
// Set absolute when the command fully determines the state it writes (On, Off,
// MoveToLevel). Such a command clears anything still queued for the same
// endpoint and cluster, because sending the superseded command first would
// briefly drive the device to a stale state. Commands whose effect depends on
// the current state (Toggle, Move, Step) must not be marked absolute; they are
// appended and sent in order.
//
// Must be called from the ESPHome main loop task; it uses the component
// scheduler, which is not thread-safe. Matter-task callbacks should hop across
// with MatterComponent::defer_to_main_loop() first.
//
// command_data must stay valid until the command has actually been sent, which
// may be long after this call returns: esp-matter only shallow-copies the
// pointer and the unicast send waits for a CASE session. Actions satisfy this
// by owning the string for the lifetime of the program.
void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster,
                         chip::CommandId command,
                         const char *command_data = "{}",
                         bool absolute = false);

template <typename... Ts> class MatterSendCommandAction : public Action<Ts...> {
public:
  void set_endpoint_id(uint16_t endpoint_id) {
    this->endpoint_id_ = endpoint_id;
  }
  void set_cluster_id(uint32_t cluster_id) { this->cluster_id_ = cluster_id; }
  void set_command_id(uint32_t command_id) { this->command_id_ = command_id; }
  void set_data(const char *data) { this->data_ = data; }
  void set_absolute(bool absolute) { this->absolute_ = absolute; }

  void play(Ts... x) override {
    // data_ is never reassigned after codegen, so the pointer stays valid for
    // as long as the queued command needs it.
    send_client_command(this->endpoint_id_, this->cluster_id_,
                        this->command_id_, this->data_.c_str(), this->absolute_);
  }

protected:
  uint16_t endpoint_id_{0};
  uint32_t cluster_id_{0};
  uint32_t command_id_{0};
  std::string data_{"{}"};
  bool absolute_{false};
};

} // namespace esphome::matter

#endif // USE_MATTER
