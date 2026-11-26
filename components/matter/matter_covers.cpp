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

using namespace chip::app::Clusters::WindowCovering;

static const char *const TAG = "matter.cover";

namespace {
chip::app::DataModel::Nullable<chip::Percent100ths> to_matter_position(float value) {
  chip::app::DataModel::Nullable<chip::Percent100ths> result;
  if (std::isfinite(value))
    result.SetNonNull(static_cast<chip::Percent100ths>(std::lroundf((1.0f - std::clamp(value, 0.0f, 1.0f)) * 10000.0f)));
  else
    result.SetNull();
  return result;
}
}  // namespace

void MatterComponent::register_cover(cover::Cover *cover, uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterCoverMapping(cover, endpoint_id));
}

void MatterCoverMapping::initialize() {
  {
    esp_matter::lock::ScopedChipStackLock lock(portMAX_DELAY);
    this->SetEndpoint(this->endpoint_id());
    SetDefaultDelegate(this->endpoint_id(), this);
    this->has_lift_ = HasFeaturePaLift(this->endpoint_id());
    this->has_tilt_ = HasFeaturePaTilt(this->endpoint_id());
    // Synchronize persisted ConfigStatus with the endpoint's features and mode.
    ConfigStatusUpdateFeatures(this->endpoint_id());
    auto mode = ModeGet(this->endpoint_id());
    ModeSet(this->endpoint_id(), mode);
  }
  this->cover_->add_on_state_callback([this]() { this->push_state_to_matter_(); });
  // Initialize from the existing cover without restoring a motor target.
  this->push_state_to_matter_();
}

CHIP_ERROR MatterCoverMapping::HandleMovement(WindowCoveringType type) {
  chip::app::DataModel::Nullable<chip::Percent100ths> target;
  auto status = type == WindowCoveringType::Lift
                    ? Attributes::TargetPositionLiftPercent100ths::Get(this->endpoint_id(), target)
                    : Attributes::TargetPositionTiltPercent100ths::Get(this->endpoint_id(), target);
  if (status != chip::Protocols::InteractionModel::Status::Success || target.IsNull())
    return CHIP_ERROR_INCORRECT_STATE;

  // Matter uses 0=open, 10000=closed; ESPHome uses 1=open, 0=closed.
  const float position = 1.0f - target.Value() / 10000.0f;
  const uint32_t revision = ++this->command_revision_;
  global_matter_component->defer_to_main_loop([this, type, position, revision]() {
    this->applied_command_revision_ = revision;
    auto call = this->cover_->make_call();
    if (type == WindowCoveringType::Lift)
      call.set_position(position);
    else
      call.set_tilt(position);
    call.perform();
  });
  return CHIP_NO_ERROR;
}

CHIP_ERROR MatterCoverMapping::HandleStopMotion() {
  const uint32_t revision = ++this->command_revision_;
  global_matter_component->defer_to_main_loop([this, revision]() {
    this->applied_command_revision_ = revision;
    auto call = this->cover_->make_call();
    call.set_stop(true);
    call.perform();
  });
  // CHIP must wait for the backend's stopped position before updating targets.
  return CHIP_ERROR_IN_PROGRESS;
}

void MatterCoverMapping::push_state_to_matter_() {
  struct State {
    float position;
    float tilt;
    uint32_t command_revision;
    uint8_t operation;
    bool reconcile_targets;
  };
  // Targets are only reconciled by a publication newer than the applied
  // command; the CHIP task re-checks because it runs after this capture.
  const uint32_t revision = this->command_revision_.load();
  const State state{this->cover_->position, this->cover_->tilt, revision,
                    static_cast<uint8_t>(this->cover_->current_operation),
                    this->applied_command_revision_ == revision};
  // Capture values on the ESPHome loop; touch Matter attributes on the CHIP task.
  auto error = chip::DeviceLayer::SystemLayer().ScheduleLambda([this, state]() {
    const auto endpoint = this->endpoint_id();
    const auto lift = to_matter_position(state.position);
    const auto tilt = to_matter_position(state.tilt);
    if (this->has_lift_)
      LiftPositionSet(endpoint, lift);
    if (this->has_tilt_)
      TiltPositionSet(endpoint, tilt);

    if (state.operation == cover::COVER_OPERATION_IDLE) {
      // ESPHome does not expose native command targets. Once settled, the
      // actual position is authoritative for Matter, API, and local movements.
      if (state.reconcile_targets && this->command_revision_.load() == state.command_revision) {
        if (this->has_lift_)
          Attributes::TargetPositionLiftPercent100ths::Set(endpoint, lift);
        if (this->has_tilt_)
          Attributes::TargetPositionTiltPercent100ths::Set(endpoint, tilt);
        OperationalStateSet(endpoint, OperationalStatus::kLift, OperationalState::Stall);
        OperationalStateSet(endpoint, OperationalStatus::kTilt, OperationalState::Stall);
      }
      return;
    }
    OperationalState operation = OperationalState::Stall;
    if (state.operation == cover::COVER_OPERATION_OPENING)
      operation = OperationalState::MovingUpOrOpen;
    else if (state.operation == cover::COVER_OPERATION_CLOSING)
      operation = OperationalState::MovingDownOrClose;
    // ESPHome exposes one operation. Report it on lift, or tilt for tilt-only
    // covers; CHIP derives the overall status from its axis states.
    const auto axis = this->has_lift_ ? OperationalStatus::kLift : OperationalStatus::kTilt;
    const auto &current = this->has_lift_ ? lift : tilt;
    if (state.reconcile_targets && this->command_revision_.load() == state.command_revision &&
        operation != OperationalState::Stall && !current.IsNull()) {
      // Movements started outside Matter keep the previous target, which
      // controllers use to show the direction. Point it at the end of travel.
      chip::app::DataModel::Nullable<chip::Percent100ths> target;
      if (this->has_lift_)
        Attributes::TargetPositionLiftPercent100ths::Get(endpoint, target);
      else
        Attributes::TargetPositionTiltPercent100ths::Get(endpoint, target);
      const bool opening = operation == OperationalState::MovingUpOrOpen;
      if (target.IsNull() || (opening ? target.Value() > current.Value() : target.Value() < current.Value())) {
        target.SetNonNull(opening ? 0 : 10000);
        if (this->has_lift_)
          Attributes::TargetPositionLiftPercent100ths::Set(endpoint, target);
        else
          Attributes::TargetPositionTiltPercent100ths::Set(endpoint, target);
      }
    }
    OperationalStateSet(endpoint, axis, operation);
  });
  if (error != CHIP_NO_ERROR)
    ESP_LOGW(TAG, "Failed to schedule cover state update: %s", chip::ErrorStr(error));
}

}  // namespace esphome::matter

#endif  // USE_MATTER && USE_COVER
