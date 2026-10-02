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
  this->mappings_.push_back(
      new MatterCoverMapping(cover, endpoint_id, supports_tilt));
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
  this->cover_->add_on_state_callback(
      [this]() { this->on_cover_state_(); });

  // Initialize Matter from the backend's current state. This updates only
  // attributes and deliberately never restores a Matter target by moving the
  // physical cover.
  this->push_state_to_matter_(true);
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

  // Matter Window Covering percentages are 0=open, 10000=closed. ESPHome is
  // normalized in the opposite direction: 0=closed, 1=open.
  float value = 1.0f - (target.Value() / 10000.0f);
  {
    std::lock_guard<std::mutex> lock(this->pending_mutex_);
    uint32_t generation = ++this->next_generation_;
    AxisTarget &axis = type == WindowCoveringType::Lift
                           ? this->pending_lift_
                           : this->pending_tilt_;
    axis = {true, std::clamp(value, 0.0f, 1.0f), generation};
  }
  this->schedule_drain_();
  return CHIP_NO_ERROR;
}

CHIP_ERROR MatterCoverMapping::HandleStopMotion() {
  {
    std::lock_guard<std::mutex> lock(this->pending_mutex_);
    this->stop_pending_ = true;
    this->stop_generation_ = ++this->next_generation_;
    // Stop is an ordering barrier. All movement admitted before it is stale.
    this->pending_lift_ = {};
    this->pending_tilt_ = {};
  }
  this->schedule_drain_();

  // The backend publishes its actual stopped position on the main loop. Tell
  // connectedhomeip not to reconcile targets prematurely in the Matter task.
  return CHIP_ERROR_IN_PROGRESS;
}

void MatterCoverMapping::schedule_drain_() {
  bool schedule = false;
  {
    std::lock_guard<std::mutex> lock(this->pending_mutex_);
    if (!this->drain_scheduled_) {
      this->drain_scheduled_ = true;
      schedule = true;
    }
  }
  if (schedule && global_matter_component != nullptr) {
    global_matter_component->defer_to_main_loop(
        [this]() { this->drain_pending_(); });
  }
}

void MatterCoverMapping::drain_pending_() {
  bool stop;
  uint32_t stop_generation;
  AxisTarget lift;
  AxisTarget tilt;
  {
    std::lock_guard<std::mutex> lock(this->pending_mutex_);
    stop = this->stop_pending_;
    stop_generation = this->stop_generation_;
    lift = this->pending_lift_;
    tilt = this->pending_tilt_;
    this->stop_pending_ = false;
    this->pending_lift_ = {};
    this->pending_tilt_ = {};
    this->drain_scheduled_ = false;
  }

  if (stop) {
    this->followup_tilt_.reset();
    this->reconcile_after_stop_ = true;
    auto call = this->cover_->make_call();
    call.set_stop(true);
    call.perform();
  }

  // A genuinely newer request may follow Stop; stale pre-Stop work may not.
  if (stop && lift.present && lift.generation <= stop_generation)
    lift = {};
  if (stop && tilt.present && tilt.generation <= stop_generation)
    tilt = {};

  if (lift.present) {
    if (tilt.present)
      this->followup_tilt_ = tilt.value;
    if (std::fabs(this->cover_->position - lift.value) < POSITION_EPSILON) {
      if (tilt.present) {
        this->followup_tilt_.reset();
        this->perform_tilt_(tilt.value);
      }
    } else {
      this->perform_position_(lift.value);
    }
  } else if (tilt.present) {
    this->perform_tilt_(tilt.value);
  }
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
  bool reconcile_targets = false;
  if (this->reconcile_after_stop_ &&
      this->cover_->current_operation == cover::COVER_OPERATION_IDLE) {
    this->reconcile_after_stop_ = false;
    reconcile_targets = true;
  }

  this->push_state_to_matter_(reconcile_targets);

  // The representative Venetian backend has a single motor and processes a
  // position movement before a requested final slat angle.
  if (this->followup_tilt_.has_value() &&
      this->cover_->current_operation == cover::COVER_OPERATION_IDLE) {
    float tilt = *this->followup_tilt_;
    this->followup_tilt_.reset();
    if (std::fabs(this->cover_->tilt - tilt) >= POSITION_EPSILON)
      this->perform_tilt_(tilt);
  }
}

void MatterCoverMapping::push_state_to_matter_(bool reconcile_targets) {
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

  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [endpoint_id, lift, tilt, supports_tilt, operation,
       reconcile_targets]() {
        using namespace chip;
        using namespace chip::app::Clusters::WindowCovering;

        app::DataModel::Nullable<Percent100ths> lift_value;
        lift_value.SetNonNull(lift);
        LiftPositionSet(endpoint_id, lift_value);

        app::DataModel::Nullable<Percent100ths> tilt_value;
        if (supports_tilt) {
          tilt_value.SetNonNull(tilt);
          TiltPositionSet(endpoint_id, tilt_value);
        }

        OperationalState state = OperationalState::Stall;
        if (operation == cover::COVER_OPERATION_OPENING)
          state = OperationalState::MovingUpOrOpen;
        else if (operation == cover::COVER_OPERATION_CLOSING)
          state = OperationalState::MovingDownOrClose;
        OperationalStateSet(endpoint_id, OperationalStatus::kLift, state);
        if (supports_tilt)
          OperationalStateSet(endpoint_id, OperationalStatus::kTilt, state);

        if (reconcile_targets) {
          Attributes::TargetPositionLiftPercent100ths::Set(endpoint_id,
                                                            lift_value);
          if (supports_tilt)
            Attributes::TargetPositionTiltPercent100ths::Set(endpoint_id,
                                                              tilt_value);
        }
      });
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_COVER
