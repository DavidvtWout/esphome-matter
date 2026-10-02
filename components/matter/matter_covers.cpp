#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_COVER)

#include <app-common/zap-generated/attributes/Accessors.h>
#include <platform/CHIPDeviceLayer.h>

#include <algorithm>
#include <cmath>

#include "esphome/core/log.h"
#include "matter_component.h"
#include "matter_covers.h"

namespace esphome::matter {

static const char* const TAG = "matter.cover";
static constexpr float POSITION_EPSILON = 0.00005f;

using chip::app::Clusters::WindowCovering::WindowCoveringType;

MatterCoverMapping::MatterCoverMapping(cover::Cover* cover, uint16_t endpoint_id, bool supports_tilt)
    : MatterEndpointMappingBase(endpoint_id), cover_(cover), supports_tilt_(supports_tilt) {}

void MatterComponent::map_cover_to_endpoint(cover::Cover* cover, uint16_t endpoint_id, bool supports_tilt) {
  auto* mapping = new MatterCoverMapping(cover, endpoint_id, supports_tilt);
  this->cover_mappings_.push_back(mapping);
  this->mappings_.push_back(mapping);
}

void MatterComponent::cancel_cover_pending_commands(cover::Cover* cover) {
  if (auto* mapping = this->get_cover_mapping(cover)) {
    mapping->cancel_pending_commands();
    return;
  }
  ESP_LOGW(TAG, "No Matter Window Covering mapping found for local Stop");
}

MatterCoverMapping* MatterComponent::get_cover_mapping(cover::Cover* cover) {
  for (auto* mapping : this->cover_mappings_) {
    if (mapping->matches_cover(cover)) return mapping;
  }
  return nullptr;
}

bool MatterCoverMapping::validate() {
  if (this->cover_ == nullptr) {
    ESP_LOGE(TAG, "Endpoint %u has no ESPHome cover", this->endpoint_id());
    return false;
  }

  auto traits = this->cover_->get_traits();
  bool valid = true;
  if (!traits.get_supports_position()) {
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support position", this->cover_->get_name().c_str(),
             this->endpoint_id());
    valid = false;
  }
  if (!traits.get_supports_stop()) {
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support Stop", this->cover_->get_name().c_str(), this->endpoint_id());
    valid = false;
  }
  if (this->supports_tilt_ && !traits.get_supports_tilt()) {
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support tilt", this->cover_->get_name().c_str(), this->endpoint_id());
    valid = false;
  }
  return valid;
}

void MatterCoverMapping::initialize() {
  using namespace chip::app::Clusters::WindowCovering;
  this->SetEndpoint(this->endpoint_id());
  SetDefaultDelegate(this->endpoint_id(), this);
  this->register_state_callback();
  this->matter_initialized_ = true;

  // Initialize Matter from the backend's current state. This updates only
  // attributes and deliberately never restores a Matter target by moving the
  // physical cover.
  this->push_state_to_matter_(true);
}

void MatterCoverMapping::register_state_callback() {
  if (this->state_callback_registered_) return;
  this->state_callback_registered_ = true;
  this->cover_->add_on_state_callback([this]() { this->on_cover_state_(); });
}

void MatterCoverMapping::handle_native_call(const cover::CoverCall& call) {
  if ((call.get_position().has_value() && !std::isfinite(*call.get_position())) ||
      (call.get_tilt().has_value() && !std::isfinite(*call.get_tilt()))) {
    ESP_LOGW(TAG, "Rejecting native cover command with a non-finite target");
    return;
  }
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  AxisTarget lift{};
  AxisTarget tilt{};
  if (call.get_stop()) {
    // A native Stop invalidates Matter-owned continuations before the backend
    // can synchronously publish IDLE, including a Stop at the lift target.
    this->command_queue_.request_stop();
  } else {
    if (call.get_position().has_value()) lift = this->command_queue_.enqueue_lift(*call.get_position());
    if (call.get_tilt().has_value() && this->supports_tilt_) tilt = this->command_queue_.enqueue_tilt(*call.get_tilt());
    if (!lift.present && !tilt.present) return;
    this->push_native_targets_to_matter_(lift, tilt);
  }

  // Native calls already run on the ESPHome loop. Drain here so this control
  // path also works if Matter initialization failed. A previously deferred
  // Matter drain will see an empty batch or only subsequently admitted work.
  this->drain_pending_();
}

void MatterCoverMapping::cancel_pending_commands() {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  // A Matter Stop already established the barrier before asking ESPHome to
  // stop. The backend may synchronously run user stop actions from that call;
  // they must not move the barrier past a newer Matter command queued behind
  // the Stop.
  if (this->internal_stop_dispatch_) return;

  this->command_queue_.cancel_pending();

  // This action is intended to run immediately before a local cover.stop.
  // Marking the phase before the CoverCall prevents a synchronous state
  // callback from treating the ensuing IDLE publication as lift completion.
  this->phase_ = MotionPhase::STOPPING;
  this->active_lift_ = {};
  this->followup_tilt_ = {};
  this->post_stop_lift_ = {};
  this->post_stop_tilt_ = {};
  this->finish_stop_if_idle_();
}

CHIP_ERROR MatterCoverMapping::HandleMovement(WindowCoveringType type) {
  using namespace chip;
  using namespace chip::app::Clusters::WindowCovering;

  app::DataModel::Nullable<Percent100ths> target;
  auto status = type == WindowCoveringType::Lift
                    ? Attributes::TargetPositionLiftPercent100ths::Get(this->endpoint_id(), target)
                    : Attributes::TargetPositionTiltPercent100ths::Get(this->endpoint_id(), target);
  if (status != Protocols::InteractionModel::Status::Success || target.IsNull()) {
    ESP_LOGE(TAG, "Endpoint %u received movement without a valid target", this->endpoint_id());
    return CHIP_ERROR_INCORRECT_STATE;
  }
  if (type == WindowCoveringType::Tilt && !this->supports_tilt_) return CHIP_ERROR_UNSUPPORTED_CHIP_FEATURE;

  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);

  // Matter Window Covering percentages are 0=open, 10000=closed. ESPHome is
  // normalized in the opposite direction: 0=closed, 1=open.
  float value = 1.0f - (target.Value() / 10000.0f);
  if (type == WindowCoveringType::Lift)
    this->command_queue_.enqueue_lift(std::clamp(value, 0.0f, 1.0f));
  else
    this->command_queue_.enqueue_tilt(std::clamp(value, 0.0f, 1.0f));
  this->schedule_drain_();
  return CHIP_NO_ERROR;
}

CHIP_ERROR MatterCoverMapping::HandleStopMotion() {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  // Stop is an ordering barrier. All movement admitted before it is stale.
  this->command_queue_.request_stop();
  this->schedule_drain_();

  // The backend publishes its actual stopped position on the main loop. Tell
  // connectedhomeip not to reconcile targets prematurely in the Matter task.
  return CHIP_ERROR_IN_PROGRESS;
}

void MatterCoverMapping::schedule_drain_() {
  if (this->command_queue_.mark_drain_scheduled() && global_matter_component != nullptr) {
    global_matter_component->defer_to_main_loop([this]() { this->drain_pending_(); });
  }
}

void MatterCoverMapping::drain_pending_() {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  auto batch = this->command_queue_.take_pending();
  const bool stop = batch.stop;
  const uint32_t stop_generation = batch.stop_generation;
  AxisTarget lift = batch.lift;
  AxisTarget tilt = batch.tilt;

  if (stop) {
    // Invalidate continuations before calling the backend: CoverCall::perform
    // may publish state synchronously and re-enter on_cover_state_().
    this->phase_ = MotionPhase::STOPPING;
    this->active_lift_ = {};
    this->followup_tilt_ = {};
    this->post_stop_lift_ = {};
    this->post_stop_tilt_ = {};
    if (lift.present && lift.generation > stop_generation) this->post_stop_lift_ = lift;
    if (tilt.present && tilt.generation > stop_generation) this->post_stop_tilt_ = tilt;
    this->perform_stop_();
    this->finish_stop_if_idle_();
    return;
  }

  this->apply_targets_(lift, tilt);
}

bool MatterCoverMapping::is_current_(const AxisTarget& target, bool lift) {
  return this->command_queue_.is_current(target, lift);
}

void MatterCoverMapping::apply_targets_(AxisTarget lift, AxisTarget tilt) {
  if (lift.present && !this->is_current_(lift, true)) lift = {};
  if (tilt.present && !this->is_current_(tilt, false)) tilt = {};

  // A backend may take time to acknowledge Stop. New commands stay bounded
  // and replace only their axis until the backend actually reports IDLE.
  if (this->phase_ == MotionPhase::STOPPING) {
    if (lift.present) this->post_stop_lift_ = lift;
    if (tilt.present) this->post_stop_tilt_ = tilt;
    this->finish_stop_if_idle_();
    return;
  }

  if (lift.present) {
    // While a lift is active, later tilt commands replace its continuation.
    // This prevents a scheduler tick from deciding whether tilt interrupts
    // the lift and ensures the last accepted tilt wins.
    if (tilt.present) {
      this->followup_tilt_ = tilt;
    }
    this->start_lift_(lift);
    return;
  }

  if (!tilt.present) return;
  if (this->phase_ == MotionPhase::LIFTING ||
      (this->phase_ == MotionPhase::IDLE && this->cover_->current_operation != cover::COVER_OPERATION_IDLE)) {
    this->followup_tilt_ = tilt;
    return;
  }
  this->start_tilt_(tilt);
}

void MatterCoverMapping::start_lift_(AxisTarget lift) {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  if (!this->is_current_(lift, true)) return;

  // If a movement is already in progress, requesting its current position is
  // a retarget to the present location and must cancel the old destination.
  if (std::fabs(this->cover_->position - lift.value) < POSITION_EPSILON &&
      this->cover_->current_operation != cover::COVER_OPERATION_IDLE) {
    this->phase_ = MotionPhase::STOPPING;
    this->active_lift_ = {};
    this->post_stop_lift_ = {};
    this->post_stop_tilt_ = this->followup_tilt_;
    this->followup_tilt_ = {};
    this->perform_stop_();
    this->finish_stop_if_idle_();
    return;
  }

  this->phase_ = MotionPhase::LIFTING;
  this->active_lift_ = lift;
  this->active_lift_start_position_ = this->cover_->position;
  // Equal idle endpoints still belong to the backend: Venetian Close can
  // rotate open slats, and other covers use repeat requests for calibration.
  this->perform_position_(lift.value);
  // Some backends intentionally do nothing at an already reached target and
  // publish no state. Complete that no-op without losing a requested tilt.
  if (this->phase_ == MotionPhase::LIFTING && this->cover_->current_operation == cover::COVER_OPERATION_IDLE &&
      std::fabs(this->cover_->position - lift.value) < POSITION_EPSILON)
    this->on_cover_state_();
}

void MatterCoverMapping::start_tilt_(AxisTarget tilt) {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  if (!this->supports_tilt_ || !this->is_current_(tilt, false)) return;
  if (this->cover_->current_operation == cover::COVER_OPERATION_IDLE &&
      std::fabs(this->cover_->tilt - tilt.value) < POSITION_EPSILON) {
    this->phase_ = MotionPhase::IDLE;
    return;
  }
  this->phase_ = MotionPhase::TILTING;
  // The preceding lift's completion can synchronously start this tilt before
  // its state callback finishes. That completed lift delta is not tilt motion.
  this->previous_position_ = this->cover_->position;
  this->previous_tilt_ = this->cover_->tilt;
  this->perform_tilt_(tilt.value);
}

void MatterCoverMapping::finish_stop_if_idle_() {
  if (this->phase_ != MotionPhase::STOPPING || this->cover_->current_operation != cover::COVER_OPERATION_IDLE) return;

  this->phase_ = MotionPhase::IDLE;
  AxisTarget lift = this->post_stop_lift_;
  AxisTarget tilt = this->post_stop_tilt_;
  const bool skip_lift_target = lift.present;
  const bool skip_tilt_target = tilt.present;
  this->post_stop_lift_ = {};
  this->post_stop_tilt_ = {};
  this->push_state_to_matter_(true, skip_lift_target, skip_tilt_target);
  this->apply_targets_(lift, tilt);
}

void MatterCoverMapping::perform_position_(float position) {
  auto call = this->cover_->make_call();
  call.set_position(position);
  call.perform();
}

void MatterCoverMapping::perform_tilt_(float tilt) {
  auto call = this->cover_->make_call();
  call.set_tilt(tilt);
  call.perform();
}

void MatterCoverMapping::perform_stop_() {
  // Only suppress the cancellation action synchronously invoked by our own
  // backend Stop. An independent Stop while awaiting feedback is a new barrier.
  const bool previous_dispatch = this->internal_stop_dispatch_;
  this->internal_stop_dispatch_ = true;
  auto call = this->cover_->make_call();
  call.set_stop(true);
  call.perform();
  this->internal_stop_dispatch_ = previous_dispatch;
}

void MatterCoverMapping::on_cover_state_() {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  const bool idle = this->cover_->current_operation == cover::COVER_OPERATION_IDLE;
  bool reconcile_targets = false;
  bool skip_lift_target = false;
  bool skip_tilt_target = false;

  if (idle && this->phase_ == MotionPhase::LIFTING) {
    // IDLE alone does not mean success: a local Stop also publishes IDLE.
    // Only continue a combined request when the lift reached its owned target.
    const float target = this->active_lift_.value;
    const float position = this->cover_->position;
    const bool current_lift = this->is_current_(this->active_lift_, true);
    // Time-estimated backends stop after crossing a target, rather than
    // snapping their reported position to it. Explicit Stop cancels ownership
    // before this callback, so crossing cannot revive a cancelled continuation.
    bool reached_target = current_lift && std::fabs(position - target) < POSITION_EPSILON;
    if (current_lift && target > this->active_lift_start_position_)
      reached_target = position + POSITION_EPSILON >= target;
    else if (current_lift && target < this->active_lift_start_position_)
      reached_target = position - POSITION_EPSILON <= target;
    this->phase_ = MotionPhase::IDLE;
    this->active_lift_ = {};
    if (reached_target && this->followup_tilt_.present) {
      AxisTarget tilt = this->followup_tilt_;
      this->followup_tilt_ = {};
      this->start_tilt_(tilt);
    } else if (reached_target) {
      // The backend can rotate the slats as part of lift. Keep the accepted
      // lift target, but synchronize the resulting tilt if no newer tilt
      // request is waiting.
      reconcile_targets = true;
      skip_lift_target = true;
    } else {
      // This covers a local Stop before the requested lift target. The generic
      // Cover state callback has no stop-reason field, so an explicit local
      // Stop exactly at the target cannot be distinguished from completion.
      // Preserve the latest tilt across a newer lift waiting for its main-loop
      // drain, but never dispatch it from the stale lift's completion callback.
      if (!this->command_queue_.snapshot().lift_pending) this->followup_tilt_ = {};
      reconcile_targets = true;
    }
  } else if (idle && this->phase_ == MotionPhase::TILTING) {
    this->phase_ = MotionPhase::IDLE;
    reconcile_targets = true;
  } else if (idle && this->phase_ == MotionPhase::IDLE) {
    const bool lift_pending = this->command_queue_.snapshot().lift_pending;
    if (!lift_pending && this->followup_tilt_.present && this->is_current_(this->followup_tilt_, false)) {
      // A Matter tilt request received during local movement waits for that
      // movement to settle, just as it does during a Matter-owned lift.
      AxisTarget tilt = this->followup_tilt_;
      this->followup_tilt_ = {};
      this->start_tilt_(tilt);
      reconcile_targets = true;
      skip_tilt_target = true;
    } else {
      if (!lift_pending) this->followup_tilt_ = {};
      // Local movement and local Stop have no Matter-owned target. Once
      // settled, align targets with the state the backend actually reports.
      reconcile_targets = true;
    }
  }

  this->push_state_to_matter_(reconcile_targets, skip_lift_target, skip_tilt_target);
  this->finish_stop_if_idle_();
}

void MatterCoverMapping::push_state_to_matter_(bool reconcile_targets, bool skip_lift_target, bool skip_tilt_target) {
  if (!this->matter_initialized_) return;

  const float position = this->cover_->position;
  const float tilt = this->cover_->tilt;
  const auto commands = this->command_queue_.snapshot();
  skip_lift_target = skip_lift_target || commands.lift_pending || this->post_stop_lift_.present;
  skip_tilt_target =
      skip_tilt_target || commands.tilt_pending || this->followup_tilt_.present || this->post_stop_tilt_.present;
  bool lift_changed = false;
  bool tilt_changed = false;
  if (this->have_previous_state_) {
    lift_changed = std::fabs(position - this->previous_position_) >= POSITION_EPSILON;
    tilt_changed = std::fabs(tilt - this->previous_tilt_) >= POSITION_EPSILON;
  }
  this->previous_position_ = position;
  this->previous_tilt_ = tilt;
  this->have_previous_state_ = true;

  {
    std::lock_guard<std::mutex> lock(this->matter_update_mutex_);
    auto& pending = this->pending_matter_update_;
    if (pending.state.present && pending.state.operation == this->cover_->current_operation &&
        pending.state.phase == this->phase_) {
      lift_changed = lift_changed || pending.state.lift_changed;
      tilt_changed = tilt_changed || pending.state.tilt_changed;
    }
    pending.state = {true, position, tilt, this->cover_->current_operation, this->phase_, lift_changed, tilt_changed};
    // Keep reconciliation separate from the latest state snapshot: a later
    // progress publication must not erase the final stopped target update.
    if (reconcile_targets && !skip_lift_target) pending.lift_target = {true, false, position, commands.lift_generation};
    if (reconcile_targets && !skip_tilt_target && this->supports_tilt_)
      pending.tilt_target = {true, false, tilt, commands.tilt_generation};
  }
  this->schedule_matter_update_();
}

void MatterCoverMapping::push_native_targets_to_matter_(AxisTarget lift, AxisTarget tilt) {
  if (!this->matter_initialized_) return;
  {
    std::lock_guard<std::mutex> lock(this->matter_update_mutex_);
    auto& pending = this->pending_matter_update_;
    if (lift.present) pending.lift_target = {true, true, lift.value, lift.generation};
    if (tilt.present) pending.tilt_target = {true, true, tilt.value, tilt.generation};
  }
  this->schedule_matter_update_();
}

void MatterCoverMapping::schedule_matter_update_() {
  bool retry = false;
  CHIP_ERROR error = CHIP_NO_ERROR;
  {
    std::lock_guard<std::mutex> lock(this->matter_update_mutex_);
    const auto& pending = this->pending_matter_update_;
    if (this->matter_update_scheduled_ ||
        (!pending.state.present && !pending.lift_target.present && !pending.tilt_target.present))
      return;
    this->matter_update_scheduled_ = true;
    error = chip::DeviceLayer::SystemLayer().ScheduleLambda([this]() { this->flush_matter_update_(); });
    if (error != CHIP_NO_ERROR) {
      this->matter_update_scheduled_ = false;
      // The final report remains in the mailbox. Retry once per main-loop
      // turn even when an idle backend will never publish another state.
      if (!this->matter_retry_scheduled_ && global_matter_component != nullptr) {
        this->matter_retry_scheduled_ = true;
        retry = true;
      }
    }
  }
  if (error != CHIP_NO_ERROR)
    ESP_LOGW(TAG, "Failed to schedule Window Covering state update: %s", chip::ErrorStr(error));
  if (retry) {
    global_matter_component->defer_to_main_loop([this]() {
      {
        std::lock_guard<std::mutex> lock(this->matter_update_mutex_);
        this->matter_retry_scheduled_ = false;
      }
      this->schedule_matter_update_();
    });
  }
}

void MatterCoverMapping::flush_matter_update_() {
  using namespace chip;
  using namespace chip::app::Clusters::WindowCovering;
  MatterUpdate update;
  {
    std::lock_guard<std::mutex> lock(this->matter_update_mutex_);
    update = this->pending_matter_update_;
    this->pending_matter_update_ = {};
    this->matter_update_scheduled_ = false;
  }
  auto to_matter = [](float value) {
    app::DataModel::Nullable<Percent100ths> result;
    if (std::isfinite(value)) {
      result.SetNonNull(static_cast<Percent100ths>(std::lroundf((1.0f - std::clamp(value, 0.0f, 1.0f)) * 10000.0f)));
    } else {
      result.SetNull();
    }
    return result;
  };
  auto target_is_current = [this](const AttributeTarget& target, bool lift) {
    if (!target.present) return false;
    if (target.command) return this->is_current_({true, target.value, target.generation}, lift);
    return lift ? this->command_queue_.lift_generation_matches(target.generation)
                : this->command_queue_.tilt_generation_matches(target.generation);
  };
  const auto endpoint_id = this->endpoint_id();
  if (target_is_current(update.lift_target, true))
    Attributes::TargetPositionLiftPercent100ths::Set(endpoint_id, to_matter(update.lift_target.value));
  if (this->supports_tilt_ && target_is_current(update.tilt_target, false))
    Attributes::TargetPositionTiltPercent100ths::Set(endpoint_id, to_matter(update.tilt_target.value));
  if (!update.state.present) return;

  const auto& state = update.state;
  LiftPositionSet(endpoint_id, to_matter(state.lift));
  if (this->supports_tilt_) TiltPositionSet(endpoint_id, to_matter(state.tilt));
  OperationalState moving_state = OperationalState::Stall;
  if (state.operation == cover::COVER_OPERATION_OPENING)
    moving_state = OperationalState::MovingUpOrOpen;
  else if (state.operation == cover::COVER_OPERATION_CLOSING)
    moving_state = OperationalState::MovingDownOrClose;
  OperationalState lift_state = OperationalState::Stall;
  OperationalState tilt_state = OperationalState::Stall;
  if (state.operation != cover::COVER_OPERATION_IDLE) {
    lift_state = state.lift_changed ? moving_state : OperationalState::Stall;
    tilt_state = state.tilt_changed ? moving_state : OperationalState::Stall;
    if (!state.lift_changed && !state.tilt_changed) {
      if (state.phase == MotionPhase::LIFTING)
        lift_state = moving_state;
      else if (state.phase == MotionPhase::TILTING)
        tilt_state = moving_state;
    }
  }
  // Attribute target changes can themselves derive an operational state in
  // CHIP. Set the backend's authoritative status last, including final IDLE.
  OperationalStateSet(endpoint_id, OperationalStatus::kLift, lift_state);
  if (this->supports_tilt_) OperationalStateSet(endpoint_id, OperationalStatus::kTilt, tilt_state);
}

void MatterNativeCover::setup() {
  this->mapping_ = this->parent_->get_cover_mapping(this->source_);
  if (this->mapping_ == nullptr) {
    ESP_LOGE(TAG, "Native cover '%s' has no Window Covering mapping", this->get_name().c_str());
    this->mark_failed();
    return;
  }
  this->mapping_->register_state_callback();
  this->source_->add_on_state_callback([this]() { this->publish_source_state_(); });
  this->publish_source_state_();
}

void MatterNativeCover::dump_config() { LOG_COVER("", "Matter Native Cover", this); }

cover::CoverTraits MatterNativeCover::get_traits() {
  auto source_traits = this->source_->get_traits();
  cover::CoverTraits traits{};
  traits.set_is_assumed_state(source_traits.get_is_assumed_state());
  traits.set_supports_stop(source_traits.get_supports_stop());
  traits.set_supports_position(source_traits.get_supports_position());
  traits.set_supports_tilt(source_traits.get_supports_tilt() && this->mapping_ != nullptr &&
                           this->mapping_->supports_tilt());
  return traits;
}

void MatterNativeCover::control(const cover::CoverCall& call) {
  if (this->mapping_ != nullptr) this->mapping_->handle_native_call(call);
}

void MatterNativeCover::publish_source_state_() {
  this->position = this->source_->position;
  this->tilt = this->source_->tilt;
  this->current_operation = this->source_->current_operation;
  this->publish_state(false);
}

}  // namespace esphome::matter

#endif  // USE_MATTER && USE_COVER
