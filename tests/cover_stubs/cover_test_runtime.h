#pragma once

#include <array>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

using CHIP_ERROR = int;
constexpr CHIP_ERROR CHIP_NO_ERROR = 0;
constexpr CHIP_ERROR CHIP_ERROR_INCORRECT_STATE = 1;
constexpr CHIP_ERROR CHIP_ERROR_UNSUPPORTED_CHIP_FEATURE = 2;
constexpr CHIP_ERROR CHIP_ERROR_IN_PROGRESS = 3;

namespace chip {
using Percent100ths = uint16_t;
inline const char* ErrorStr(CHIP_ERROR) { return "host scheduling error"; }
namespace Protocols::InteractionModel {
enum class Status { Success, Failure };
}
namespace app::DataModel {
template <typename T>
class Nullable {
 public:
  void SetNonNull(T value) { value_ = value; }
  void SetNull() { value_.reset(); }
  bool IsNull() const { return !value_.has_value(); }
  T Value() const { return value_.value(); }

 private:
  std::optional<T> value_;
};
}  // namespace app::DataModel
namespace app::Clusters::WindowCovering {
enum class WindowCoveringType { Lift, Tilt };
enum class OperationalState { Stall, MovingUpOrOpen, MovingDownOrClose };
enum class OperationalStatus { kLift, kTilt };
class WindowCoveringDelegate {
 public:
  virtual ~WindowCoveringDelegate() = default;
  virtual CHIP_ERROR HandleMovement(WindowCoveringType) = 0;
  virtual CHIP_ERROR HandleStopMotion() = 0;
  void SetEndpoint(uint16_t) {}
};
struct EndpointState {
  app::DataModel::Nullable<Percent100ths> lift;
  app::DataModel::Nullable<Percent100ths> tilt;
  app::DataModel::Nullable<Percent100ths> lift_target;
  app::DataModel::Nullable<Percent100ths> tilt_target;
  OperationalState lift_status{OperationalState::Stall};
  OperationalState tilt_status{OperationalState::Stall};
};
inline std::map<uint16_t, EndpointState> endpoints;
inline void SetDefaultDelegate(uint16_t, WindowCoveringDelegate*) {}
inline void LiftPositionSet(uint16_t endpoint, app::DataModel::Nullable<Percent100ths> value) {
  endpoints[endpoint].lift = value;
}
inline void TiltPositionSet(uint16_t endpoint, app::DataModel::Nullable<Percent100ths> value) {
  endpoints[endpoint].tilt = value;
}
inline void OperationalStateSet(uint16_t endpoint, OperationalStatus axis, OperationalState value) {
  auto& state = endpoints[endpoint];
  (axis == OperationalStatus::kLift ? state.lift_status : state.tilt_status) = value;
}
namespace Attributes {
struct TargetPositionLiftPercent100ths {
  static Protocols::InteractionModel::Status Get(uint16_t endpoint, app::DataModel::Nullable<Percent100ths>& out) {
    out = endpoints[endpoint].lift_target;
    return Protocols::InteractionModel::Status::Success;
  }
  static void Set(uint16_t endpoint, app::DataModel::Nullable<Percent100ths> value) {
    auto& state = endpoints[endpoint];
    state.lift_target = value;
    // CHIP derives motion from target writes; the adapter must override it
    // with backend IDLE after reconciliation, including overshoot.
    if (!value.IsNull() && !state.lift.IsNull())
      state.lift_status = value.Value() == state.lift.Value()  ? OperationalState::Stall
                          : value.Value() < state.lift.Value() ? OperationalState::MovingUpOrOpen
                                                               : OperationalState::MovingDownOrClose;
  }
};
struct TargetPositionTiltPercent100ths {
  static Protocols::InteractionModel::Status Get(uint16_t endpoint, app::DataModel::Nullable<Percent100ths>& out) {
    out = endpoints[endpoint].tilt_target;
    return Protocols::InteractionModel::Status::Success;
  }
  static void Set(uint16_t endpoint, app::DataModel::Nullable<Percent100ths> value) {
    auto& state = endpoints[endpoint];
    state.tilt_target = value;
    if (!value.IsNull() && !state.tilt.IsNull())
      state.tilt_status = value.Value() == state.tilt.Value()  ? OperationalState::Stall
                          : value.Value() < state.tilt.Value() ? OperationalState::MovingUpOrOpen
                                                               : OperationalState::MovingDownOrClose;
  }
};
}  // namespace Attributes
}  // namespace app::Clusters::WindowCovering
namespace DeviceLayer {
class HostSystemLayer {
 public:
  template <typename F>
  CHIP_ERROR ScheduleLambda(F callback) {
    static_assert(sizeof(F) <= 24, "CHIP capture limit must hold on the host too");
    if (failures_remaining > 0) {
      --failures_remaining;
      return CHIP_ERROR_INCORRECT_STATE;
    }
    work.emplace_back(callback);
    return CHIP_NO_ERROR;
  }
  void run() {
    while (!work.empty()) {
      auto next = std::move(work.front());
      work.pop_front();
      next();
    }
  }
  std::deque<std::function<void()>> work;
  unsigned failures_remaining{0};
};
inline HostSystemLayer system_layer;
inline HostSystemLayer& SystemLayer() { return system_layer; }
}  // namespace DeviceLayer
}  // namespace chip

namespace esphome {
class Component {
 public:
  virtual ~Component() = default;
  virtual void setup() {}
  virtual void dump_config() {}
  void mark_failed() { failed_ = true; }

 protected:
  bool failed_{false};
};
template <typename T>
class Parented {
 public:
  void set_parent(T* parent) { parent_ = parent; }

 protected:
  T* parent_{nullptr};
};
namespace cover {
enum CoverOperation { COVER_OPERATION_IDLE, COVER_OPERATION_OPENING, COVER_OPERATION_CLOSING };
class CoverTraits {
 public:
  bool get_supports_position() const { return position_; }
  bool get_supports_stop() const { return stop_; }
  bool get_supports_tilt() const { return tilt_; }
  bool get_is_assumed_state() const { return assumed_; }
  void set_supports_position(bool value) { position_ = value; }
  void set_supports_stop(bool value) { stop_ = value; }
  void set_supports_tilt(bool value) { tilt_ = value; }
  void set_is_assumed_state(bool value) { assumed_ = value; }

 private:
  bool position_{false}, stop_{false}, tilt_{false}, assumed_{false};
};
class Cover;
class CoverCall {
 public:
  explicit CoverCall(Cover* parent) : parent_(parent) {}
  const std::optional<float>& get_position() const { return position_; }
  const std::optional<float>& get_tilt() const { return tilt_; }
  bool get_stop() const { return stop_; }
  CoverCall& set_position(float value) {
    position_ = value;
    return *this;
  }
  CoverCall& set_tilt(float value) {
    tilt_ = value;
    return *this;
  }
  CoverCall& set_stop(bool value) {
    stop_ = value;
    return *this;
  }
  void perform();

 private:
  Cover* parent_;
  std::optional<float> position_, tilt_;
  bool stop_{false};
};
class Cover {
 public:
  virtual ~Cover() = default;
  virtual CoverTraits get_traits() = 0;
  CoverCall make_call() { return CoverCall(this); }
  const std::string& get_name() const { return name_; }
  void set_name(const std::string& name) { name_ = name; }
  void add_on_state_callback(std::function<void()> callback) { callbacks_.push_back(std::move(callback)); }
  void publish_state(bool = true) {
    for (auto& callback : callbacks_) callback();
  }
  float position{0.0f}, tilt{0.0f};
  CoverOperation current_operation{COVER_OPERATION_IDLE};

 protected:
  friend class CoverCall;
  virtual void control(const CoverCall&) = 0;

 private:
  std::string name_{"Host test cover"};
  std::vector<std::function<void()>> callbacks_;
};
inline void CoverCall::perform() { parent_->control(*this); }
}  // namespace cover
}  // namespace esphome
