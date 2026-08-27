#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_actions.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "matter_component.h"

#include <app/CommandPathParams.h>
#include <app/DeviceProxy.h>
#include <app/clusters/bindings/binding-table.h>
#include <deque>
#include <inttypes.h>
#include <vector>

static const char *const TAG = "matter.actions";

namespace esphome::matter {

namespace {

// Longest chain of relative commands (Toggle, Move, Step, ...) kept queued for
// one local endpoint and cluster. Beyond this the oldest is dropped: the queue
// exists to pace and reorder-protect a burst of button presses, not to buffer an
// unbounded backlog that would replay minutes later.
constexpr size_t MAX_PENDING_COMMANDS = 8;

// Base for the scheduler ids handed to MatterComponent::schedule_command_pump.
// Offset well away from 0 so these cannot collide with any small integer id
// ESPHome itself might schedule on the Matter component.
constexpr uint32_t PUMP_ID_BASE = 0x4D415400;  // 'M','A','T',0

struct PendingCommand {
  chip::CommandId command;
  // Not owned. See the send_client_command() contract in matter_actions.h.
  const char *data;
};

// One queue per (local endpoint, cluster). Commands for different clusters are
// independent, so an OnOff command never supersedes a pending LevelControl one.
//
// Only the unicast path is queued. Group commands go out immediately, so they are
// neither paced nor superseded: a group is addressed as a whole and delaying it
// would give up the one advantage multicast has.
struct CommandQueue {
  uint16_t endpoint_id{0};
  chip::ClusterId cluster{0};
  std::deque<PendingCommand> pending;
  uint32_t last_send_ms{0};
  bool has_sent{false};
  bool pump_scheduled{false};
};

// Queues are created on first use and never destroyed, so indices stay valid
// for use as scheduler ids and inside pump callbacks. Function-local static to
// avoid depending on static initialization order.
std::vector<CommandQueue *> &queues() {
  static std::vector<CommandQueue *> instance;  // NOLINT
  return instance;
}

size_t queue_index(uint16_t endpoint_id, chip::ClusterId cluster) {
  auto &all = queues();
  for (size_t i = 0; i < all.size(); i++) {
    if (all[i]->endpoint_id == endpoint_id && all[i]->cluster == cluster) {
      return i;
    }
  }
  auto *queue = new CommandQueue();  // NOLINT(cppcoreguidelines-owning-memory)
  queue->endpoint_id = endpoint_id;
  queue->cluster = cluster;
  all.push_back(queue);
  return all.size() - 1;
}

// Set for the duration of the cluster_update() call that serves unicast
// bindings, and read by client_group_invoke_cb() to skip the group bindings that
// send_client_command() has already served directly.
//
// This is safe despite looking racy: CHIP's binding manager dispatches multicast
// entries synchronously from NotifyBoundClusterChanged(), and we hold the CHIP
// stack lock across the whole call, so nothing else can run on the Matter task
// in between. Unicast entries are dispatched asynchronously once CASE completes,
// long after the flag is cleared, and go through client_invoke_cb() anyway.
//
// Without this, every queued command would go out to the group a second time.
// That is harmless for an absolute command but wrong for a relative one: a
// duplicated Toggle cancels itself and a duplicated Step moves twice.
bool suppress_group_dispatch = false;  // NOLINT

uint32_t configured_unicast_delay() {
  return global_matter_component != nullptr
             ? global_matter_component->get_unicast_delay()
             : 0;
}

uint32_t configured_min_interval() {
  return global_matter_component != nullptr
             ? global_matter_component->get_min_command_interval()
             : 0;
}

}  // namespace

// Builds the JSON command payload for outgoing client commands. Called by
// esp_matter once per matching binding entry for every command sent through
// cluster_update(), so a single action fans out to one call per bound node.
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
  // Captured into the response/failure callbacks below so each log line names
  // the node it came from; without it, fan-out to several bound nodes produces
  // indistinguishable lines. Captured rather than passed through send_request's
  // void *ctx because a 64-bit NodeId does not fit in a 32-bit pointer.
  const uint64_t node_id = static_cast<uint64_t>(peer_device->GetDeviceId());
  ESP_LOGV(TAG, "Sending request to node=%" PRIu64, node_id);
  esp_matter::client::interaction::invoke::send_request(
      nullptr, peer_device, req_handle->command_path, cmd_data,
      [node_id](void *, const chip::app::ConcreteCommandPath &path,
                const chip::app::StatusIB &status, chip::TLV::TLVReader *) {
        ESP_LOGD(TAG,
                 "Response: node=%" PRIu64
                 " endpoint=%u cluster=%lu command=%lu status=0x%02x",
                 node_id, static_cast<unsigned>(path.mEndpointId),
                 static_cast<unsigned long>(path.mClusterId),
                 static_cast<unsigned long>(path.mCommandId),
                 static_cast<unsigned>(status.mStatus));
      },
      [node_id](void *, CHIP_ERROR error) {
        ESP_LOGW(TAG,
                 "Send command to node=%" PRIu64 " failed: %" CHIP_ERROR_FORMAT,
                 node_id, error.Format());
      },
      chip::NullOptional);
}

static void
client_group_invoke_cb(uint8_t fabric_index,
                       esp_matter::client::request_handle_t *req_handle,
                       void *priv_data) {
  if (req_handle->type != esp_matter::client::INVOKE_CMD) {
    return;
  }
  if (suppress_group_dispatch) {
    ESP_LOGV(TAG, "Skipping group request; already sent directly");
    return;
  }
  const char *cmd_data =
      req_handle->request_data != nullptr
          ? static_cast<const char *>(req_handle->request_data)
          : "{}";
  ESP_LOGV(TAG, "Sending group request");
  esp_err_t err = esp_matter::client::interaction::invoke::send_group_request(
      fabric_index, req_handle->command_path, cmd_data);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "Group request for group=0x%04x failed: %s",
             static_cast<unsigned>(req_handle->command_path.mGroupId),
             esp_err_to_name(err));
  }
}

void register_client_request_callbacks() {
  esp_matter::client::set_request_callback(client_invoke_cb,
                                           client_group_invoke_cb, nullptr);
}

// Sends command to every group binding of endpoint_id/cluster and counts the
// unicast bindings that still need serving. Must be called with the CHIP stack
// lock held.
static void send_to_group_bindings_(uint16_t endpoint_id,
                                    chip::ClusterId cluster,
                                    chip::CommandId command, const char *data,
                                    size_t *group_count,
                                    size_t *unicast_count) {
  *group_count = 0;
  *unicast_count = 0;
  for (const auto &entry :
       chip::app::Clusters::Binding::Table::GetInstance()) {
    if (entry.local != endpoint_id ||
        (entry.clusterId.has_value() && entry.clusterId.value() != cluster)) {
      continue;
    }
    if (entry.type == MATTER_UNICAST_BINDING) {
      (*unicast_count)++;
      continue;
    }
    if (entry.type != MATTER_MULTICAST_BINDING) {
      continue;
    }
    (*group_count)++;
    // Groups have no per-entry remote endpoint: the group id addresses the
    // endpoints, so the command path carries the group instead of an endpoint.
    // BitFlags' single-flag constructor is explicit, so it cannot be spelled as
    // a bare enumerator here.
    chip::app::CommandPathParams path(
        0, entry.groupId, cluster, command,
        chip::BitFlags<chip::app::CommandPathFlags>(
            chip::app::CommandPathFlags::kGroupIdValid));
    esp_err_t err = esp_matter::client::interaction::invoke::send_group_request(
        entry.fabricIndex, path, data);
    if (err != ESP_OK) {
      ESP_LOGW(TAG, "Group request for group=0x%04x failed: %s",
               static_cast<unsigned>(entry.groupId), esp_err_to_name(err));
    } else {
      ESP_LOGD(TAG,
               "Sent group command: group=0x%04x cluster=0x%04" PRIx32
               " command=0x%04" PRIx32 " data=%s",
               static_cast<unsigned>(entry.groupId),
               static_cast<uint32_t>(cluster), static_cast<uint32_t>(command),
               data);
    }
  }
}

static void pump_queue_(size_t index);

static void schedule_pump_(size_t index, uint32_t delay_ms) {
  if (global_matter_component == nullptr) {
    ESP_LOGE(TAG, "Matter component not available; dropping queued command");
    queues()[index]->pending.clear();
    return;
  }
  queues()[index]->pump_scheduled = true;
  global_matter_component->schedule_command_pump(
      PUMP_ID_BASE + static_cast<uint32_t>(index), delay_ms,
      [index]() { pump_queue_(index); });
}

// Sends the command at the head of the queue to the unicast bindings of its
// endpoint, then reschedules itself if more are waiting.
static void pump_queue_(size_t index) {
  CommandQueue *queue = queues()[index];
  queue->pump_scheduled = false;
  if (queue->pending.empty()) {
    return;
  }
  const PendingCommand cmd = queue->pending.front();
  queue->pending.pop_front();

  ESP_LOGD(TAG,
           "Sending command to unicast bindings: endpoint=%u "
           "cluster=0x%04" PRIx32 " command=0x%04" PRIx32 " data=%s",
           queue->endpoint_id, static_cast<uint32_t>(queue->cluster),
           static_cast<uint32_t>(cmd.command), cmd.data);

  esp_matter::client::request_handle_t req;
  req.type = esp_matter::client::INVOKE_CMD;
  req.command_path.mClusterId = queue->cluster;
  req.command_path.mCommandId = cmd.command;
  req.request_data = const_cast<char *>(cmd.data);
  {
    esp_matter::lock::ScopedChipStackLock scoped_lock(portMAX_DELAY);
    // CHIP's binding manager does the work here: it walks the binding table,
    // establishes a CASE session per bound node and rewrites the command path
    // to that node's remote endpoint before invoking client_invoke_cb.
    suppress_group_dispatch = true;
    esp_err_t err = esp_matter::client::cluster_update(queue->endpoint_id, &req);
    suppress_group_dispatch = false;
    if (err != ESP_OK) {
      ESP_LOGW(TAG, "cluster_update failed: %s", esp_err_to_name(err));
    }
  }

  queue->last_send_ms = millis();
  queue->has_sent = true;
  if (!queue->pending.empty()) {
    schedule_pump_(index, configured_min_interval());
  }
}

// How long to hold the next command back: the configured unicast delay, extended
// if the minimum inter-command interval has not elapsed yet.
static uint32_t next_delay_(const CommandQueue *queue) {
  uint32_t delay_ms = configured_unicast_delay();
  const uint32_t min_interval = configured_min_interval();
  if (queue->has_sent && min_interval > 0) {
    const uint32_t elapsed = millis() - queue->last_send_ms;
    if (elapsed < min_interval && min_interval - elapsed > delay_ms) {
      delay_ms = min_interval - elapsed;
    }
  }
  return delay_ms;
}

void send_client_command(uint16_t endpoint_id, chip::ClusterId cluster,
                         chip::CommandId command, const char *command_data,
                         bool absolute) {
  const char *data = command_data != nullptr ? command_data : "{}";

  size_t group_count = 0;
  size_t unicast_count = 0;
  {
    // The binding table is owned by the Matter task; reading it without the
    // stack lock races against commissioning and binding writes.
    esp_matter::lock::ScopedChipStackLock scoped_lock(portMAX_DELAY);
    send_to_group_bindings_(endpoint_id, cluster, command, data, &group_count,
                            &unicast_count);
  }

  if (group_count == 0 && unicast_count == 0) {
    ESP_LOGW(TAG, "No bound nodes for endpoint=%u cluster=0x%04" PRIx32,
             endpoint_id, static_cast<uint32_t>(cluster));
    return;
  }
  if (unicast_count == 0) {
    return;
  }

  const size_t index = queue_index(endpoint_id, cluster);
  CommandQueue *queue = queues()[index];

  if (absolute) {
    if (!queue->pending.empty()) {
      ESP_LOGD(TAG,
               "Superseding %u queued command(s) for endpoint=%u "
               "cluster=0x%04" PRIx32,
               static_cast<unsigned>(queue->pending.size()), endpoint_id,
               static_cast<uint32_t>(cluster));
      queue->pending.clear();
    }
  } else if (queue->pending.size() >= MAX_PENDING_COMMANDS) {
    ESP_LOGW(TAG,
             "Command queue full for endpoint=%u cluster=0x%04" PRIx32
             "; dropping oldest command",
             endpoint_id, static_cast<uint32_t>(cluster));
    queue->pending.pop_front();
  }
  queue->pending.push_back({command, data});

  // A pump that is already scheduled keeps its deadline and will pick up the new
  // head of the queue. Rescheduling here would push the deadline out on every
  // press and starve the queue while the user keeps clicking.
  if (!queue->pump_scheduled) {
    schedule_pump_(index, next_delay_(queue));
  }
}

} // namespace esphome::matter

#endif // USE_MATTER
