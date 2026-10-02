#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_COVER)

#include <app/clusters/window-covering-server/WindowCoveringCluster.h>

#include <cstdint>
#include <mutex>

#include "esphome/components/cover/cover.h"
#include "esphome/core/component.h"
#include "matter_cover_command_queue.h"
#include "matter_endpoints.h"

namespace esphome::matter {

class MatterComponent;

class MatterCoverMapping final : public MatterEndpointMappingBase,
                                 public chip::app::Clusters::WindowCovering::WindowCoveringDelegate {
 public:
  MatterCoverMapping(cover::Cover* cover, uint16_t endpoint_id, bool supports_tilt);

  bool validate() override;
  void initialize() override;

  bool matches_cover(const cover::Cover* cover) const { return this->cover_ == cover; }
  void cancel_pending_commands();
  void register_state_callback();
  bool supports_tilt() const { return this->supports_tilt_; }
  // ESPHome API calls arrive on the main loop. Both axes and Stop use the
  // same generations and continuations as commands from Matter controllers.
  void handle_native_call(const cover::CoverCall& call);

  CHIP_ERROR HandleMovement(chip::app::Clusters::WindowCovering::WindowCoveringType type) override;
  CHIP_ERROR HandleStopMotion() override;

 protected:
  using AxisTarget = MatterCoverCommandQueue::Target;

  enum class MotionPhase : uint8_t { IDLE, LIFTING, TILTING, STOPPING };

  void schedule_drain_();
  void drain_pending_();
  void on_cover_state_();
  void push_state_to_matter_(bool reconcile_targets, bool skip_lift_target = false, bool skip_tilt_target = false);
  bool is_current_(const AxisTarget& target, bool lift);
  void apply_targets_(AxisTarget lift, AxisTarget tilt);
  void start_lift_(AxisTarget lift);
  void start_tilt_(AxisTarget tilt);
  void finish_stop_if_idle_();
  void perform_position_(float position);
  void perform_tilt_(float tilt);
  void perform_stop_();
  void push_native_targets_to_matter_(AxisTarget lift, AxisTarget tilt);
  void schedule_matter_update_();
  void flush_matter_update_();

  cover::Cover* cover_;
  bool supports_tilt_;

  // Serializes Matter command admission with backend dispatch. Recursive
  // because a backend CoverCall may publish synchronously and re-enter the
  // mapping on the same ESPHome loop thread.
  std::recursive_mutex command_mutex_;
  MatterCoverCommandQueue command_queue_;

  // Main-loop-only operation state. A continuation is tied to the lift and
  // tilt generations that created it, so cancellation or a newer request
  // cannot accidentally revive stale work.
  MotionPhase phase_{MotionPhase::IDLE};
  AxisTarget active_lift_{};
  float active_lift_start_position_{0.0f};
  AxisTarget followup_tilt_{};
  AxisTarget post_stop_lift_{};
  AxisTarget post_stop_tilt_{};
  float previous_position_{0.0f};
  float previous_tilt_{0.0f};
  bool have_previous_state_{false};
  bool state_callback_registered_{false};
  bool matter_initialized_{false};
  bool internal_stop_dispatch_{false};

  struct StateSnapshot {
    bool present{false};
    float lift{0.0f};
    float tilt{0.0f};
    cover::CoverOperation operation{cover::COVER_OPERATION_IDLE};
    MotionPhase phase{MotionPhase::IDLE};
    bool lift_changed{false};
    bool tilt_changed{false};
  };
  struct AttributeTarget {
    bool present{false};
    bool command{false};
    float value{0.0f};
    uint32_t generation{0};
  };
  struct MatterUpdate {
    StateSnapshot state{};
    AttributeTarget lift_target{};
    AttributeTarget tilt_target{};
  };

  // One fixed mailbox per mapping. Publications replace the current-state
  // snapshot while target reconciliation survives until consumed. The CHIP
  // work item captures only this pointer, independently of publication rate.
  std::mutex matter_update_mutex_;
  MatterUpdate pending_matter_update_{};
  bool matter_update_scheduled_{false};
  bool matter_retry_scheduled_{false};
};

// The backend remains internal; this entity is the native API/Web control
// surface. It mirrors backend publications without restoring motor targets.
class MatterNativeCover final : public cover::Cover, public Component, public Parented<MatterComponent> {
 public:
  void set_source(cover::Cover* source) { this->source_ = source; }
  void setup() override;
  void dump_config() override;
  cover::CoverTraits get_traits() override;

 protected:
  void control(const cover::CoverCall& call) override;
  void publish_source_state_();

  cover::Cover* source_{nullptr};
  MatterCoverMapping* mapping_{nullptr};
};

}  // namespace esphome::matter

#endif  // USE_MATTER && USE_COVER
