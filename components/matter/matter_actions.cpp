#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_actions.h"

#include "esphome/core/log.h"

#include <app/clusters/bindings/binding-table.h>
#include <cstdio>
#include <cstring>
#include <inttypes.h>
#include <string>

static const char *const TAG = "matter.actions";

namespace esphome::matter {

static void invoke_response_cb(void *,
                               const chip::app::ConcreteCommandPath &path,
                               const chip::app::StatusIB &status,
                               chip::TLV::TLVReader *) {
  ESP_LOGD(TAG, "Response: endpoint=%u cluster=%lu command=%lu status=0x%02x",
           static_cast<unsigned>(path.mEndpointId),
           static_cast<unsigned long>(path.mClusterId),
           static_cast<unsigned long>(path.mCommandId),
           static_cast<unsigned>(status.mStatus));
}

static void invoke_failure_cb(void *, CHIP_ERROR error) {
  ESP_LOGW(TAG, "Send command failed: %" CHIP_ERROR_FORMAT, error.Format());
}

// Builds the JSON command payload for outgoing client commands. Called by
// esp_matter for every command sent through cluster_update().
static void client_invoke_cb(esp_matter::client::peer_device_t *peer_device,
                             esp_matter::client::request_handle_t *req_handle,
                             void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD) {
    return;
  }
  const char *cmd_data =
      req_handle->request_data != nullptr
          ? static_cast<const char *>(req_handle->request_data)
          : "{}";
  ESP_LOGV(TAG, "Sending request");
  esp_matter::client::interaction::invoke::send_request(
      nullptr, peer_device, req_handle->command_path, cmd_data,
      invoke_response_cb, invoke_failure_cb, chip::NullOptional);
}

static void
client_group_invoke_cb(uint8_t fabric_index,
                       esp_matter::client::request_handle_t *req_handle,
                       void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD) {
    return;
  }
  const char *cmd_data =
      req_handle->request_data != nullptr
          ? static_cast<const char *>(req_handle->request_data)
          : "{}";
  ESP_LOGV(TAG, "Sending group request");
  esp_matter::client::interaction::invoke::send_group_request(
      fabric_index, req_handle->command_path, cmd_data);
}

void register_client_request_callbacks() {
  esp_matter::client::set_request_callback(client_invoke_cb,
                                           client_group_invoke_cb, nullptr);
}

void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster,
                         chip::CommandId command, const char *command_data) {
  auto &binding_table = chip::app::Clusters::Binding::Table::GetInstance();
  std::string node_ids;
  for (const auto &entry : binding_table) {
    if (entry.local == endpoint_id &&
        (!entry.clusterId.has_value() || entry.clusterId.value() == cluster)) {
      if (!node_ids.empty())
        node_ids += ",";
      char node_id[21];
      snprintf(node_id, sizeof(node_id), "%" PRIu64,
               static_cast<uint64_t>(entry.nodeId));
      node_ids += node_id;
    }
  }

  if (node_ids.empty()) {
    ESP_LOGW(TAG, "No bound nodes for endpoint=%u cluster=%u", endpoint_id,
             static_cast<uint32_t>(cluster));
    return;
  }
  ESP_LOGD(
      TAG,
      "Sending command: nodes=[%s] endpoint=%u cluster=%u command=%u data=%s",
      node_ids.c_str(), endpoint_id, static_cast<uint32_t>(cluster),
      static_cast<uint32_t>(command),
      command_data != nullptr ? command_data : "{}");

  esp_matter::client::request_handle_t req;
  req.type = esp_matter::client::INVOKE_CMD;
  req.command_path.mClusterId = cluster;
  req.command_path.mCommandId = command;
  req.request_data =
      const_cast<char *>(command_data != nullptr ? command_data : "{}");
  esp_matter::lock::ScopedChipStackLock scoped_lock(portMAX_DELAY);
  esp_err_t err = esp_matter::client::cluster_update(endpoint_id, &req);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "cluster_update failed: %s", esp_err_to_name(err));
  }
}

} // namespace esphome::matter

#endif // USE_MATTER
