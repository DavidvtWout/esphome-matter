#include <cassert>
#include <limits>
#include "matter_component.h"

using namespace esphome;
using namespace esphome::matter;
using namespace chip::app::Clusters::WindowCovering;

class Backend : public cover::Cover {
 public:
  void control(const cover::CoverCall &call) override {
    calls.push_back(call);
    if (call.stop) current_operation = cover::COVER_OPERATION_IDLE;
    else current_operation = cover::COVER_OPERATION_OPENING;
    publish_state();
  }
  std::vector<cover::CoverCall> calls;
};

int main() {
  MatterComponent component;
  global_matter_component = &component;
  Backend backend;
  MatterCoverMapping mapping(&backend, 1);
  mapping.initialize();
  chip::DeviceLayer::SystemLayer().run();
  auto &state = endpoints[1];
  assert(backend.calls.empty());  // Boot only reports state.
  assert(state.lift.Value() == 5000 && state.tilt.Value() == 5000);
  assert(state.mode == 0 && state.config_status == 0x19);  // Operational, lift and tilt position aware.

  auto move = [&](WindowCoveringType axis, uint16_t target) {
    Position value;
    value.SetNonNull(target);
    if (axis == WindowCoveringType::Lift) state.lift_target = value;
    else state.tilt_target = value;
    assert(mapping.HandleMovement(axis) == CHIP_NO_ERROR);
  };
  move(WindowCoveringType::Lift, 2500);
  move(WindowCoveringType::Tilt, 7500);
  assert(backend.calls.empty());  // Cover is called only on the ESPHome loop.
  component.run();
  assert(backend.calls.size() == 2);
  assert(backend.calls[0].position == 0.75f);
  assert(backend.calls[1].tilt == 0.25f);  // Tilt does not wait for lift completion.
  chip::DeviceLayer::SystemLayer().run();
  assert(state.operation == OperationalState::MovingUpOrOpen);

  assert(mapping.HandleStopMotion() == CHIP_ERROR_IN_PROGRESS);
  component.run();
  assert(backend.calls.back().stop);
  chip::DeviceLayer::SystemLayer().run();
  assert(state.operation == OperationalState::Stall);
  assert(state.lift_target.Value() == 5000);

  // Native/API/local changes only publish actual backend state to Matter.
  backend.position = 0.2f;
  backend.tilt = 0.8f;
  backend.current_operation = cover::COVER_OPERATION_CLOSING;
  backend.publish_state();
  chip::DeviceLayer::SystemLayer().run();
  assert(state.lift.Value() == 8000 && state.tilt.Value() == 2000);
  assert(state.operation == OperationalState::MovingDownOrClose);
  // The stale opening target (5000) is pointed at the actual direction.
  assert(state.lift_target.Value() == 10000);
  auto native_stop = backend.make_call();
  native_stop.set_stop(true).perform();
  chip::DeviceLayer::SystemLayer().run();
  assert(state.lift_target.Value() == 8000 && state.tilt_target.Value() == 2000);

  // An older idle report must not overwrite a command admitted afterward.
  backend.publish_state();
  move(WindowCoveringType::Lift, 1000);
  // The SDK marks the requested axis moving when the target is written.
  OperationalStateSet(1, OperationalStatus::kLift, OperationalState::MovingUpOrOpen);
  chip::DeviceLayer::SystemLayer().run();
  assert(state.lift_target.Value() == 1000);
  assert(state.operation == OperationalState::MovingUpOrOpen);
  // Nor may an idle report while that command awaits the ESPHome loop.
  backend.publish_state();
  chip::DeviceLayer::SystemLayer().run();
  assert(state.lift_target.Value() == 1000);
  assert(state.operation == OperationalState::MovingUpOrOpen);
  component.run();
  chip::DeviceLayer::SystemLayer().run();
  assert(backend.calls.back().position == 0.9f);
  assert(state.lift_target.Value() == 1000);  // A Matter target in the moving direction is kept.

  backend.position = std::numeric_limits<float>::quiet_NaN();
  backend.publish_state();
  chip::DeviceLayer::SystemLayer().run();
  assert(state.lift.IsNull());

  // Discover capabilities from the actual Matter endpoint (including tilt-only).
  endpoints[2].has_lift = false;
  MatterCoverMapping tilt_only(&backend, 2);
  tilt_only.initialize();
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[2].lift.IsNull() && !endpoints[2].tilt.IsNull());
  assert(endpoints[2].config_status == 0x11);  // Operational and tilt position aware.
  backend.current_operation = cover::COVER_OPERATION_CLOSING;
  backend.publish_state();
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[2].lift_operation == OperationalState::Stall);
  assert(endpoints[2].tilt_operation == OperationalState::MovingDownOrClose);
  assert(endpoints[2].operation == OperationalState::MovingDownOrClose);

  // Persisted maintenance/calibration modes stay locked, without moving at boot.
  for (uint8_t mode : {uint8_t{0x02}, uint8_t{0x04}}) {
    const uint16_t id = 10 + mode;
    endpoints[id].mode = mode;
    endpoints[id].config_status = 0x01;  // Stale operational flag.
    MatterCoverMapping locked(&backend, id);
    const auto previous_calls = backend.calls.size();
    locked.initialize();
    chip::DeviceLayer::SystemLayer().run();
    assert(endpoints[id].mode == mode);
    assert(endpoints[id].config_status == 0x18);
    assert(backend.calls.size() == previous_calls);
  }
}
