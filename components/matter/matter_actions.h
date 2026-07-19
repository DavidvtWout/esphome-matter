#pragma once
#include "esphome/core/defines.h"

#ifdef USE_MATTER

#include "esphome/core/automation.h"
#include "matter_endpoints.h"

#include <esp_matter.h>

namespace esphome::matter {

// Registers the esp_matter client request callbacks that build outgoing
// command payloads. Called once during endpoint creation.
void register_client_request_callbacks();

// Sends a client command through the Binding cluster of the given local endpoint.
// move_mode is only used for LevelControl Move commands.
void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster, chip::CommandId command,
                         uint8_t move_mode = 0);

template<typename... Ts> class MatterTurnOnAction : public Action<Ts...>, public Parented<MatterEndpointRef> {
 public:
  void play(Ts... x) override {
    using namespace chip::app::Clusters;
    send_client_command(this->parent_->endpoint_id, OnOff::Id, OnOff::Commands::On::Id);
  }
};

template<typename... Ts> class MatterTurnOffAction : public Action<Ts...>, public Parented<MatterEndpointRef> {
 public:
  void play(Ts... x) override {
    using namespace chip::app::Clusters;
    send_client_command(this->parent_->endpoint_id, OnOff::Id, OnOff::Commands::Off::Id);
  }
};

template<typename... Ts> class MatterToggleAction : public Action<Ts...>, public Parented<MatterEndpointRef> {
 public:
  void play(Ts... x) override {
    using namespace chip::app::Clusters;
    send_client_command(this->parent_->endpoint_id, OnOff::Id, OnOff::Commands::Toggle::Id);
  }
};

template<typename... Ts> class MatterDimAction : public Action<Ts...>, public Parented<MatterEndpointRef> {
 public:
  void set_direction(uint8_t direction) { this->direction_ = direction; }
  void play(Ts... x) override {
    using namespace chip::app::Clusters;
    send_client_command(this->parent_->endpoint_id, LevelControl::Id, LevelControl::Commands::MoveWithOnOff::Id,
                        this->direction_);
  }

 protected:
  uint8_t direction_{0};  // 0 = up, 1 = down
};

template<typename... Ts> class MatterDimStopAction : public Action<Ts...>, public Parented<MatterEndpointRef> {
 public:
  void play(Ts... x) override {
    using namespace chip::app::Clusters;
    send_client_command(this->parent_->endpoint_id, LevelControl::Id, LevelControl::Commands::StopWithOnOff::Id);
  }
};

}  // namespace esphome::matter

#endif  // USE_MATTER
