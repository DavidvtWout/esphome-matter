#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_actions.h"

#include <cstdio>
#include <cstring>

namespace esphome::matter {

// Builds the JSON command payload for outgoing client commands. Called by
// esp_matter for every command sent through cluster_update().
static void client_invoke_cb(esp_matter::client::peer_device_t *peer_device,
                              esp_matter::client::request_handle_t *req_handle, void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD)
    return;
  using namespace chip::app::Clusters;
  char cmd_data[48] = "{}";
  if (req_handle->command_path.mClusterId == LevelControl::Id) {
    if (req_handle->command_path.mCommandId == LevelControl::Commands::MoveWithOnOff::Id) {
      uint8_t mode = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(req_handle->request_data));
      snprintf(cmd_data, sizeof(cmd_data),
               "{\"0:U8\": %u, \"1:U8\": 50, \"2:U8\": 0, \"3:U8\": 0}", mode);
    } else {
      // StopWithOnOff: OptionsMask=0, OptionsOverride=0
      strcpy(cmd_data, "{\"0:U8\": 0, \"1:U8\": 0}");
    }
  }
  esp_matter::client::interaction::invoke::send_request(nullptr, peer_device, req_handle->command_path,
                                                        cmd_data, nullptr, nullptr, chip::NullOptional);
}

static void client_group_invoke_cb(uint8_t fabric_index, esp_matter::client::request_handle_t *req_handle,
                                    void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD)
    return;
  using namespace chip::app::Clusters;
  char cmd_data[48] = "{}";
  if (req_handle->command_path.mClusterId == LevelControl::Id) {
    if (req_handle->command_path.mCommandId == LevelControl::Commands::MoveWithOnOff::Id) {
      uint8_t mode = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(req_handle->request_data));
      snprintf(cmd_data, sizeof(cmd_data),
               "{\"0:U8\": %u, \"1:U8\": 50, \"2:U8\": 0, \"3:U8\": 0}", mode);
    } else {
      strcpy(cmd_data, "{\"0:U8\": 0, \"1:U8\": 0}");
    }
  }
  esp_matter::client::interaction::invoke::send_group_request(fabric_index, req_handle->command_path, cmd_data);
}

void register_client_request_callbacks() {
  esp_matter::client::set_request_callback(client_invoke_cb, client_group_invoke_cb, nullptr);
}

void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster, chip::CommandId command, uint8_t move_mode) {
  esp_matter::client::request_handle_t req;
  req.type = esp_matter::client::INVOKE_CMD;
  req.command_path.mClusterId = cluster;
  req.command_path.mCommandId = command;
  req.request_data = reinterpret_cast<void *>(static_cast<uintptr_t>(move_mode));
  esp_matter::lock::chip_stack_lock(portMAX_DELAY);
  esp_matter::client::cluster_update(endpoint_id, &req);
  esp_matter::lock::chip_stack_unlock();
}

}  // namespace esphome::matter

#endif  // USE_MATTER
