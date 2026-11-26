#pragma once

#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <optional>
#include <vector>

using CHIP_ERROR = int;
constexpr CHIP_ERROR CHIP_NO_ERROR = 0;
constexpr CHIP_ERROR CHIP_ERROR_INCORRECT_STATE = 1;
constexpr CHIP_ERROR CHIP_ERROR_IN_PROGRESS = 2;
constexpr int portMAX_DELAY = -1;

namespace esp_matter::lock {
inline bool held{false};
class ScopedChipStackLock {
 public:
  explicit ScopedChipStackLock(int) { held = true; }
  ~ScopedChipStackLock() { held = false; }
};
}

namespace chip {
using Percent100ths = uint16_t;
inline const char *ErrorStr(CHIP_ERROR) { return "scheduling failed"; }
namespace Protocols::InteractionModel {
enum class Status { Success, Failure };
}
namespace app::DataModel {
template <typename T> class Nullable {
 public:
  void SetNonNull(T value) { value_ = value; }
  void SetNull() { value_.reset(); }
  bool IsNull() const { return !value_; }
  T Value() const { return value_.value(); }
 private:
  std::optional<T> value_;
};
}
namespace app::Clusters::WindowCovering {
using Position = app::DataModel::Nullable<Percent100ths>;
enum class WindowCoveringType { Lift, Tilt };
enum class OperationalState { Stall, MovingUpOrOpen, MovingDownOrClose };
enum class OperationalStatus { kGlobal, kLift, kTilt };
class WindowCoveringDelegate {
 public:
  virtual ~WindowCoveringDelegate() = default;
  virtual CHIP_ERROR HandleMovement(WindowCoveringType) = 0;
  virtual CHIP_ERROR HandleStopMotion() = 0;
  void SetEndpoint(uint16_t) {}
};
struct Endpoint {
  Position lift, tilt, lift_target, tilt_target;
  bool has_lift{true}, has_tilt{true};
  uint8_t mode{0}, config_status{0};
  OperationalState operation{OperationalState::Stall};
  OperationalState lift_operation{OperationalState::Stall}, tilt_operation{OperationalState::Stall};
};
inline std::map<uint16_t, Endpoint> endpoints;
inline void SetDefaultDelegate(uint16_t, WindowCoveringDelegate *) {}
inline bool HasFeaturePaLift(uint16_t id) { assert(esp_matter::lock::held); return endpoints[id].has_lift; }
inline bool HasFeaturePaTilt(uint16_t id) { assert(esp_matter::lock::held); return endpoints[id].has_tilt; }
inline void ConfigStatusUpdateFeatures(uint16_t id) {
  assert(esp_matter::lock::held);
  auto &state = endpoints[id];
  state.config_status = (state.config_status & ~0x18) | (state.has_lift ? 0x08 : 0) | (state.has_tilt ? 0x10 : 0);
}
inline uint8_t ModeGet(uint16_t id) { assert(esp_matter::lock::held); return endpoints[id].mode; }
inline void ModeSet(uint16_t id, uint8_t &mode) {
  assert(esp_matter::lock::held);
  auto &state = endpoints[id];
  state.mode = mode;
  state.config_status = (state.config_status & ~0x05) | ((mode & 0x06) ? 0 : 0x01) | ((mode & 0x01) ? 0x04 : 0);
}
inline void LiftPositionSet(uint16_t id, Position value) { endpoints[id].lift = value; }
inline void TiltPositionSet(uint16_t id, Position value) { endpoints[id].tilt = value; }
inline void OperationalStateSet(uint16_t id, OperationalStatus axis, OperationalState value) {
  // Match CHIP: only axis updates are accepted; lift has global priority.
  if (axis == OperationalStatus::kGlobal) return;
  auto &state = endpoints[id];
  if (axis == OperationalStatus::kLift) state.lift_operation = value;
  else state.tilt_operation = value;
  state.operation = state.lift_operation != OperationalState::Stall
                        ? state.lift_operation : state.tilt_operation;
}
namespace Attributes {
struct TargetPositionLiftPercent100ths {
  static Protocols::InteractionModel::Status Get(uint16_t id, Position &value) {
    value = endpoints[id].lift_target;
    return Protocols::InteractionModel::Status::Success;
  }
  static void Set(uint16_t id, Position value) { endpoints[id].lift_target = value; }
};
struct TargetPositionTiltPercent100ths {
  static Protocols::InteractionModel::Status Get(uint16_t id, Position &value) {
    value = endpoints[id].tilt_target;
    return Protocols::InteractionModel::Status::Success;
  }
  static void Set(uint16_t id, Position value) { endpoints[id].tilt_target = value; }
};
}
}
namespace DeviceLayer {
class System {
 public:
  template <typename F> CHIP_ERROR ScheduleLambda(F callback) {
    static_assert(sizeof(F) <= 24, "CHIP ScheduleLambda capture limit");
    work.emplace_back(callback);
    return CHIP_NO_ERROR;
  }
  void run() {
    while (!work.empty()) {
      auto callback = std::move(work.front());
      work.pop_front();
      callback();
    }
  }
  std::deque<std::function<void()>> work;
};
inline System system_layer;
inline System &SystemLayer() { return system_layer; }
}
}

namespace esphome::cover {
enum CoverOperation : uint8_t { COVER_OPERATION_IDLE, COVER_OPERATION_OPENING, COVER_OPERATION_CLOSING };
class Cover;
class CoverCall {
 public:
  explicit CoverCall(Cover *parent) : parent_(parent) {}
  CoverCall &set_position(float value) { position = value; return *this; }
  CoverCall &set_tilt(float value) { tilt = value; return *this; }
  CoverCall &set_stop(bool value) { stop = value; return *this; }
  void perform();
  std::optional<float> position, tilt;
  bool stop{false};
 private:
  Cover *parent_;
};
class Cover {
 public:
  virtual ~Cover() = default;
  CoverCall make_call() { return CoverCall(this); }
  void add_on_state_callback(std::function<void()> callback) { callbacks_.push_back(callback); }
  void publish_state() { for (auto &callback : callbacks_) callback(); }
  virtual void control(const CoverCall &) = 0;
  float position{0.5f}, tilt{0.5f};
  CoverOperation current_operation{COVER_OPERATION_IDLE};
 private:
  std::vector<std::function<void()>> callbacks_;
};
inline void CoverCall::perform() { parent_->control(*this); }
}
