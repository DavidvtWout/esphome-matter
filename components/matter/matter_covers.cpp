#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_COVER)

#include "esphome/core/log.h"
#include "matter_component.h"
#include "matter_covers.h"

#include <algorithm>
#include <app-common/zap-generated/attributes/Accessors.h>
#include <cmath>
#include <platform/CHIPDeviceLayer.h>

namespace esphome::matter {

static const char *const TAG = "matter.cover";
static constexpr float POSITION_EPSILON = 0.00005f;

using chip::app::Clusters::WindowCovering::WindowCoveringType;

MatterCoverMapping::MatterCoverMapping(cover::Cover *cover,
                                       uint16_t endpoint_id,
                                       bool supports_tilt)
    : MatterEndpointMappingBase(endpoint_id), cover_(cover),
      supports_tilt_(supports_tilt) {}

void MatterComponent::map_cover_to_endpoint(cover::Cover *cover,
                                            uint16_t endpoint_id,
                                            bool supports_tilt) {
  auto *mapping = new MatterCoverMapping(cover, endpoint_id, supports_tilt);
  this->cover_mappings_.push_back(mapping);
  this->mappings_.push_back(mapping);
}

void MatterComponent::cancel_cover_pending_commands(cover::Cover *cover) {
  if (auto *mapping = this->get_cover_mapping(cover)) {
    mapping->cancel_pending_commands();
    return;
  }
  ESP_LOGW(TAG, "No Matter Window Covering mapping found for local Stop");
}

MatterCoverMapping *MatterComponent::get_cover_mapping(cover::Cover *cover) {
  for (auto *mapping : this->cover_mappings_) {
    if (mapping->matches_cover(cover))
      return mapping;
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
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support position",
             this->cover_->get_name().c_str(), this->endpoint_id());
    valid = false;
  }
  if (!traits.get_supports_stop()) {
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support Stop",
             this->cover_->get_name().c_str(), this->endpoint_id());
    valid = false;
  }
  if (this->supports_tilt_ && !traits.get_supports_tilt()) {
    ESP_LOGE(TAG, "Cover '%s' on endpoint %u must support tilt",
             this->cover_->get_name().c_str(), this->endpoint_id());
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
  if (this->state_callback_registered_)
    return;
  this->state_callback_registered_ = true;
  this->cover_->add_on_state_callback(
      [this]() { this->on_cover_state_(); });
}

void MatterCoverMapping::handle_native_call(const cover::CoverCall &call) {
  if ((call.get_position().has_value() &&
       !std::isfinite(*call.get_position())) ||
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
    if (call.get_position().has_value())
      lift = this->command_queue_.enqueue_lift(*call.get_position());
    if (call.get_tilt().has_value() && this->supports_tilt_)
      tilt = this->command_queue_.enqueue_tilt(*call.get_tilt());
    if (!lift.present && !tilt.present)
      return;
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
  if (this->phase_ == MotionPhase::STOPPING)
    return;

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
                    ? Attributes::TargetPositionLiftPercent100ths::Get(
                          this->endpoint_id(), target)
                    : Attributes::TargetPositionTiltPercent100ths::Get(
                          this->endpoint_id(), target);
  if (status != Protocols::InteractionModel::Status::Success ||
      target.IsNull()) {
    ESP_LOGE(TAG, "Endpoint %u received movement without a valid target",
             this->endpoint_id());
    return CHIP_ERROR_INCORRECT_STATE;
  }
  if (type == WindowCoveringType::Tilt && !this->supports_tilt_)
    return CHIP_ERROR_UNSUPPORTED_CHIP_FEATURE;

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
  if (this->command_queue_.mark_drain_scheduled() &&
      global_matter_component != nullptr) {
    global_matter_component->defer_to_main_loop(
        [this]() { this->drain_pending_(); });
  }
}

void MatterCoverMapping::drain_pending_() {
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
    if (lift.present && lift.generation > stop_generation)
      this->post_stop_lift_ = lift;
    if (tilt.present && tilt.generation > stop_generation)
      this->post_stop_tilt_ = tilt;
    auto call = this->cover_->make_call();
    call.set_stop(true);
    call.perform();
    this->finish_stop_if_idle_();
    return;
  }

  this->apply_targets_(lift, tilt);
}

bool MatterCoverMapping::is_current_(const AxisTarget &target,
                                     bool lift) {
  return this->command_queue_.is_current(target, lift);
}

void MatterCoverMapping::apply_targets_(AxisTarget lift, AxisTarget tilt) {
  if (lift.present && !this->is_current_(lift, true))
    lift = {};
  if (tilt.present && !this->is_current_(tilt, false))
    tilt = {};

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

  if (!tilt.present)
    return;
  if (this->phase_ == MotionPhase::LIFTING ||
      (this->phase_ == MotionPhase::IDLE &&
       this->cover_->current_operation != cover::COVER_OPERATION_IDLE)) {
    this->followup_tilt_ = tilt;
    return;
  }
  this->start_tilt_(tilt);
}

void MatterCoverMapping::start_lift_(AxisTarget lift) {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  if (!this->is_current_(lift, true))
    return;

  // If a movement is already in progress, requesting its current position is
  // a retarget to the present location and must cancel the old destination.
  if (std::fabs(this->cover_->position - lift.value) < POSITION_EPSILON) {
    if (this->cover_->current_operation != cover::COVER_OPERATION_IDLE) {
      this->phase_ = MotionPhase::STOPPING;
      this->active_lift_ = {};
      this->post_stop_lift_ = {};
      this->post_stop_tilt_ = this->followup_tilt_;
      this->followup_tilt_ = {};
      auto call = this->cover_->make_call();
      call.set_stop(true);
      call.perform();
      this->finish_stop_if_idle_();
      return;
    }
    this->phase_ = MotionPhase::IDLE;
    this->active_lift_ = {};
    if (this->followup_tilt_.present) {
      AxisTarget next_tilt = this->followup_tilt_;
      this->followup_tilt_ = {};
      this->start_tilt_(next_tilt);
    }
    return;
  }

  this->phase_ = MotionPhase::LIFTING;
  this->active_lift_ = lift;
  this->perform_position_(lift.value);
}

void MatterCoverMapping::start_tilt_(AxisTarget tilt) {
  std::lock_guard<std::recursive_mutex> command_lock(this->command_mutex_);
  if (!this->supports_tilt_ || !this->is_current_(tilt, false))
    return;
  if (this->cover_->current_operation == cover::COVER_OPERATION_IDLE &&
      std::fabs(this->cover_->tilt - tilt.value) < POSITION_EPSILON) {
    this->phase_ = MotionPhase::IDLE;
    return;
  }
  this->phase_ = MotionPhase::TILTING;
  this->perform_tilt_(tilt.value);
}

void MatterCoverMapping::finish_stop_if_idle_() {
  if (this->phase_ != MotionPhase::STOPPING ||
      this->cover_->current_operation != cover::COVER_OPERATION_IDLE)
    return;

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

void MatterCoverMapping::on_cover_state_() {
  const bool idle =
      this->cover_->current_operation == cover::COVER_OPERATION_IDLE;
  bool reconcile_targets = false;
  bool skip_lift_target = false;
  bool skip_tilt_target = false;

  if (idle && this->phase_ == MotionPhase::LIFTING) {
    // IDLE alone does not mean success: a local Stop also publishes IDLE.
    // Only continue a combined request when the lift reached its owned target.
    const bool reached_target =
        this->active_lift_.present &&
        std::fabs(this->cover_->position - this->active_lift_.value) <
            POSITION_EPSILON;
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
      this->followup_tilt_ = {};
      reconcile_targets = true;
    }
  } else if (idle && this->phase_ == MotionPhase::TILTING) {
    this->phase_ = MotionPhase::IDLE;
    reconcile_targets = true;
  } else if (idle && this->phase_ == MotionPhase::IDLE) {
    if (this->followup_tilt_.present &&
        this->is_current_(this->followup_tilt_, false)) {
      // A Matter tilt request received during local movement waits for that
      // movement to settle, just as it does during a Matter-owned lift.
      AxisTarget tilt = this->followup_tilt_;
      this->followup_tilt_ = {};
      this->start_tilt_(tilt);
      reconcile_targets = true;
      skip_tilt_target = true;
    } else {
      this->followup_tilt_ = {};
      // Local movement and local Stop have no Matter-owned target. Once
      // settled, align targets with the state the backend actually reports.
      reconcile_targets = true;
    }
  }

  this->push_state_to_matter_(reconcile_targets, skip_lift_target,
                              skip_tilt_target);
  this->finish_stop_if_idle_();
}

void MatterCoverMapping::push_state_to_matter_(bool reconcile_targets,
                                              bool skip_lift_target,
                                              bool skip_tilt_target) {
  if (!this->matter_initialized_)
    return;
  using namespace chip::app::Clusters::WindowCovering;

  auto to_matter = [](float value) -> chip::Percent100ths {
    value = std::clamp(value, 0.0f, 1.0f);
    return static_cast<chip::Percent100ths>(
        std::lroundf((1.0f - value) * 10000.0f));
  };

  uint16_t endpoint_id = this->endpoint_id();
  chip::Percent100ths lift = to_matter(this->cover_->position);
  chip::Percent100ths tilt = to_matter(this->cover_->tilt);
  bool supports_tilt = this->supports_tilt_;
  cover::CoverOperation operation = this->cover_->current_operation;
  float position = this->cover_->position;
  float cover_tilt = this->cover_->tilt;
  MotionPhase phase = this->phase_;
  auto command_snapshot = this->command_queue_.snapshot();
  uint32_t lift_generation = command_snapshot.lift_generation;
  uint32_t tilt_generation = command_snapshot.tilt_generation;
  skip_lift_target = skip_lift_target || command_snapshot.lift_pending;
  skip_tilt_target = skip_tilt_target || command_snapshot.tilt_pending;

  bool lift_changed = false;
  bool tilt_changed = false;
  if (this->have_previous_state_) {
    lift_changed = std::fabs(position - this->previous_position_) >=
                   POSITION_EPSILON;
    tilt_changed = std::fabs(cover_tilt - this->previous_tilt_) >=
                   POSITION_EPSILON;
  }
  this->previous_position_ = position;
  this->previous_tilt_ = cover_tilt;
  this->have_previous_state_ = true;

  struct StateSnapshot {
    uint16_t endpoint_id;
    chip::Percent100ths lift;
    chip::Percent100ths tilt;
    bool supports_tilt;
    cover::CoverOperation operation;
    MotionPhase phase;
    bool lift_changed;
    bool tilt_changed;
    bool reconcile_targets;
    bool skip_lift_target;
    bool skip_tilt_target;
    uint32_t lift_generation;
    uint32_t tilt_generation;
  };
  auto *snapshot = new StateSnapshot{endpoint_id,
                                     lift,
                                     tilt,
                                     supports_tilt,
                                     operation,
                                     phase,
                                     lift_changed,
                                     tilt_changed,
                                     reconcile_targets,
                                     skip_lift_target,
                                     skip_tilt_target,
                                     lift_generation,
                                     tilt_generation};

  const auto schedule_error = chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [this, snapshot]() {
        using namespace chip;
        using namespace chip::app::Clusters::WindowCovering;

        const uint16_t endpoint_id = snapshot->endpoint_id;
        const Percent100ths lift = snapshot->lift;
        const Percent100ths tilt = snapshot->tilt;
        const bool supports_tilt = snapshot->supports_tilt;
        const cover::CoverOperation operation = snapshot->operation;
        const MotionPhase phase = snapshot->phase;
        const bool lift_changed = snapshot->lift_changed;
        const bool tilt_changed = snapshot->tilt_changed;
        const bool reconcile_targets = snapshot->reconcile_targets;
        const bool skip_lift_target = snapshot->skip_lift_target;
        const bool skip_tilt_target = snapshot->skip_tilt_target;
        const uint32_t lift_generation = snapshot->lift_generation;
        const uint32_t tilt_generation = snapshot->tilt_generation;

        app::DataModel::Nullable<Percent100ths> lift_value;
        lift_value.SetNonNull(lift);
        LiftPositionSet(endpoint_id, lift_value);

        app::DataModel::Nullable<Percent100ths> tilt_value;
        if (supports_tilt) {
          tilt_value.SetNonNull(tilt);
          TiltPositionSet(endpoint_id, tilt_value);
        }

        OperationalState moving_state = OperationalState::Stall;
        if (operation == cover::COVER_OPERATION_OPENING)
          moving_state = OperationalState::MovingUpOrOpen;
        else if (operation == cover::COVER_OPERATION_CLOSING)
          moving_state = OperationalState::MovingDownOrClose;

        OperationalState lift_state = OperationalState::Stall;
        OperationalState tilt_state = OperationalState::Stall;
        if (operation != cover::COVER_OPERATION_IDLE) {
          lift_state = lift_changed ? moving_state : OperationalState::Stall;
          tilt_state = tilt_changed ? moving_state : OperationalState::Stall;
          // Before the backend publishes its first progress update, report
          // only the axis the adapter is currently commanding.
          if (!lift_changed && !tilt_changed) {
            if (phase == MotionPhase::LIFTING)
              lift_state = moving_state;
            else if (phase == MotionPhase::TILTING)
              tilt_state = moving_state;
          }
        }
        OperationalStateSet(endpoint_id, OperationalStatus::kLift, lift_state);
        if (supports_tilt)
          OperationalStateSet(endpoint_id, OperationalStatus::kTilt,
                               tilt_state);

        if (reconcile_targets) {
          bool reconcile_lift = !skip_lift_target;
          bool reconcile_tilt = !skip_tilt_target;
          reconcile_lift = reconcile_lift &&
                           this->command_queue_.lift_generation_matches(
                               lift_generation);
          reconcile_tilt = reconcile_tilt &&
                           this->command_queue_.tilt_generation_matches(
                               tilt_generation);
          if (reconcile_lift)
            Attributes::TargetPositionLiftPercent100ths::Set(endpoint_id,
                                                              lift_value);
          if (supports_tilt && reconcile_tilt)
            Attributes::TargetPositionTiltPercent100ths::Set(endpoint_id,
                                                              tilt_value);
        }
        delete snapshot;
      });
  if (schedule_error != CHIP_NO_ERROR) {
    delete snapshot;
    ESP_LOGE(TAG, "Failed to schedule Window Covering state update: %s",
             chip::ErrorStr(schedule_error));
  }
}

void MatterCoverMapping::push_native_targets_to_matter_(AxisTarget lift,
                                                       AxisTarget tilt) {
  if (!this->matter_initialized_)
    return;
  struct NativeTargets {
    AxisTarget lift;
    AxisTarget tilt;
  };
  // CHIP's event bridge has a bounded lambda capture size (24 bytes on C6).
  auto *targets = new NativeTargets{lift, tilt};
  const auto error = chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [this, targets]() {
        using namespace chip::app::Clusters::WindowCovering;
        const AxisTarget lift = targets->lift;
        const AxisTarget tilt = targets->tilt;
        auto to_matter = [](float value) {
          chip::app::DataModel::Nullable<chip::Percent100ths> result;
          result.SetNonNull(static_cast<chip::Percent100ths>(
              std::lroundf((1.0f - std::clamp(value, 0.0f, 1.0f)) * 10000.0f)));
          return result;
        };
        if (this->is_current_(lift, true))
          Attributes::TargetPositionLiftPercent100ths::Set(
              this->endpoint_id(), to_matter(lift.value));
        if (this->is_current_(tilt, false))
          Attributes::TargetPositionTiltPercent100ths::Set(
              this->endpoint_id(), to_matter(tilt.value));
        delete targets;
      });
  if (error != CHIP_NO_ERROR) {
    delete targets;
    ESP_LOGE(TAG, "Failed to schedule native cover targets: %s",
             chip::ErrorStr(error));
  }
}

void MatterNativeCover::setup() {
  this->mapping_ = this->parent_->get_cover_mapping(this->source_);
  if (this->mapping_ == nullptr) {
    ESP_LOGE(TAG, "Native cover '%s' has no Window Covering mapping",
             this->get_name().c_str());
    this->mark_failed();
    return;
  }
  this->mapping_->register_state_callback();
  this->source_->add_on_state_callback(
      [this]() { this->publish_source_state_(); });
  this->publish_source_state_();
}

void MatterNativeCover::dump_config() {
  LOG_COVER("", "Matter Native Cover", this);
}

cover::CoverTraits MatterNativeCover::get_traits() {
  auto source_traits = this->source_->get_traits();
  cover::CoverTraits traits{};
  traits.set_is_assumed_state(source_traits.get_is_assumed_state());
  traits.set_supports_stop(source_traits.get_supports_stop());
  traits.set_supports_position(source_traits.get_supports_position());
  traits.set_supports_tilt(source_traits.get_supports_tilt() &&
                           this->mapping_ != nullptr &&
                           this->mapping_->supports_tilt());
  return traits;
}

void MatterNativeCover::control(const cover::CoverCall &call) {
  if (this->mapping_ != nullptr)
    this->mapping_->handle_native_call(call);
}

void MatterNativeCover::publish_source_state_() {
  this->position = this->source_->position;
  this->tilt = this->source_->tilt;
  this->current_operation = this->source_->current_operation;
  this->publish_state(false);
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_COVER
