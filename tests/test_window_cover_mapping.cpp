#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>
#include <type_traits>

#include "matter_component.h"

using namespace esphome;
using namespace esphome::matter;
using namespace chip::app::Clusters::WindowCovering;

class Backend final : public cover::Cover {
 public:
  enum class Kind { LIFT, TILT, STOP };
  struct Command {
    Kind kind;
    float value;
  };
  cover::CoverTraits get_traits() override {
    cover::CoverTraits traits;
    traits.set_supports_position(true);
    traits.set_supports_tilt(true);
    traits.set_supports_stop(true);
    return traits;
  }
  void finish(float lift, float angle) {
    position = lift;
    tilt = angle;
    current_operation = cover::COVER_OPERATION_IDLE;
    publish_state();
  }
  unsigned count(Kind kind) const {
    unsigned result = 0;
    for (const auto& command : commands) result += command.kind == kind;
    return result;
  }
  bool asynchronous_stop{false};
  bool repeat_endpoint_moves{false};
  bool publish_start{true};
  std::function<void()> stop_callback;
  std::vector<Command> commands;

 protected:
  void control(const cover::CoverCall& call) override {
    if (call.get_stop()) {
      commands.push_back({Kind::STOP, 0.0f});
      if (stop_callback) stop_callback();
      if (!asynchronous_stop) {
        current_operation = cover::COVER_OPERATION_IDLE;
        publish_state();
      }
      return;
    }
    if (call.get_position().has_value()) {
      const float target = *call.get_position();
      commands.push_back({Kind::LIFT, target});
      if (target == position && !repeat_endpoint_moves) return;
      current_operation = target <= position ? cover::COVER_OPERATION_CLOSING : cover::COVER_OPERATION_OPENING;
      if (publish_start) publish_state();
    }
    if (call.get_tilt().has_value()) {
      const float target = *call.get_tilt();
      commands.push_back({Kind::TILT, target});
      if (target == tilt) return;
      current_operation = target < tilt ? cover::COVER_OPERATION_CLOSING : cover::COVER_OPERATION_OPENING;
      if (publish_start) publish_state();
    }
  }
};

struct Fixture {
  static constexpr uint16_t ENDPOINT = 1;
  MatterComponent component;
  Backend backend;
  MatterCoverMapping mapping{&backend, ENDPOINT, true};
  Fixture() {
    chip::DeviceLayer::system_layer = {};
    endpoints.clear();
    global_matter_component = &component;
    component.cover_mappings_.push_back(&mapping);
    mapping.initialize();
    chip::DeviceLayer::SystemLayer().run();
  }
  ~Fixture() {
    for (unsigned i = 0; i < 20 && !component.work_.empty(); ++i) component.run_main_loop();
    chip::DeviceLayer::SystemLayer().run();
    assert(component.work_.empty());
    global_matter_component = nullptr;
  }
  void native(float lift, float angle) {
    auto call = backend.make_call();
    call.set_position(lift).set_tilt(angle);
    mapping.handle_native_call(call);
  }
  void native_lift(float lift) {
    auto call = backend.make_call();
    call.set_position(lift);
    mapping.handle_native_call(call);
  }
  void native_tilt(float angle) {
    auto call = backend.make_call();
    call.set_tilt(angle);
    mapping.handle_native_call(call);
  }
  void native_stop() {
    auto call = backend.make_call();
    call.set_stop(true);
    mapping.handle_native_call(call);
  }
  void matter_move(WindowCoveringType axis, float value) {
    chip::app::DataModel::Nullable<chip::Percent100ths> target;
    target.SetNonNull(static_cast<chip::Percent100ths>(std::lroundf((1.0f - value) * 10000.0f)));
    if (axis == WindowCoveringType::Lift)
      Attributes::TargetPositionLiftPercent100ths::Set(ENDPOINT, target);
    else
      Attributes::TargetPositionTiltPercent100ths::Set(ENDPOINT, target);
    assert(mapping.HandleMovement(axis) == CHIP_NO_ERROR);
  }
  void local_stop() {
    mapping.cancel_pending_commands();
    auto call = backend.make_call();
    call.set_stop(true).perform();
  }
  void flush() {
    component.run_main_loop();
    chip::DeviceLayer::SystemLayer().run();
  }
};

void test_overshoot_continues_latest_tilt() {
  for (const bool opening : {false, true}) {
    Fixture f;
    f.backend.position = opening ? 0.0f : 1.0f;
    f.native(0.5f, 0.25f);
    assert(f.backend.count(Backend::Kind::TILT) == 0);
    f.native_tilt(0.3f);
    f.backend.finish(opening ? 0.5002f : 0.4998f, opening ? 1.0f : 0.0f);
    assert(f.backend.count(Backend::Kind::TILT) == 1);
    assert(f.backend.commands.back().value == 0.3f);
  }
}

void test_stop_cancels_tilt_at_and_past_target() {
  for (const float position : {0.499f, 0.5f, 0.501f}) {
    Fixture f;
    f.native(0.5f, 0.25f);
    f.backend.position = position;
    f.local_stop();
    assert(f.backend.count(Backend::Kind::TILT) == 0);
    assert(f.backend.current_operation == cover::COVER_OPERATION_IDLE);
  }
}

void test_async_local_stop_clears_post_stop_lift() {
  Fixture f;
  f.backend.asynchronous_stop = true;
  f.backend.current_operation = cover::COVER_OPERATION_OPENING;
  assert(f.mapping.HandleStopMotion() == CHIP_ERROR_IN_PROGRESS);
  f.matter_move(WindowCoveringType::Lift, 0.75f);
  f.component.run_main_loop();
  assert(f.backend.count(Backend::Kind::LIFT) == 0);
  f.local_stop();
  f.backend.finish(0.2f, 0.0f);
  assert(f.backend.count(Backend::Kind::LIFT) == 0);
}

void test_async_stop_holds_and_coalesces_later_commands() {
  Fixture f;
  f.backend.asynchronous_stop = true;
  f.backend.current_operation = cover::COVER_OPERATION_OPENING;
  f.native_stop();
  f.native(0.6f, 0.2f);
  f.native_lift(0.7f);
  f.native_tilt(0.3f);
  assert(f.backend.count(Backend::Kind::LIFT) == 0);
  assert(f.backend.count(Backend::Kind::TILT) == 0);
  f.backend.finish(0.2f, 0.0f);
  assert(f.backend.count(Backend::Kind::LIFT) == 1);
  assert(f.backend.commands.back().value == 0.7f);
  f.backend.finish(0.7002f, 1.0f);
  assert(f.backend.count(Backend::Kind::TILT) == 1);
  assert(f.backend.commands.back().value == 0.3f);
}

void test_internal_stop_callback_preserves_newer_command() {
  Fixture f;
  f.backend.asynchronous_stop = true;
  f.backend.current_operation = cover::COVER_OPERATION_OPENING;
  f.backend.stop_callback = [&f]() { f.mapping.cancel_pending_commands(); };
  assert(f.mapping.HandleStopMotion() == CHIP_ERROR_IN_PROGRESS);
  f.matter_move(WindowCoveringType::Lift, 0.75f);
  f.component.run_main_loop();
  f.backend.finish(0.2f, 0.0f);
  assert(f.backend.count(Backend::Kind::LIFT) == 1);
  assert(f.backend.commands.back().value == 0.75f);
}

void test_equal_idle_position_reaches_backend() {
  Fixture f;
  f.backend.position = 0.0f;
  f.backend.tilt = 1.0f;
  f.backend.repeat_endpoint_moves = true;
  f.native_lift(0.0f);
  assert(f.backend.count(Backend::Kind::LIFT) == 1);
  assert(f.backend.current_operation == cover::COVER_OPERATION_CLOSING);
  f.backend.finish(0.0f, 0.0f);
  f.native_lift(0.0f);
  assert(f.backend.count(Backend::Kind::LIFT) == 2);
}

void test_idle_noop_completes_combined_request() {
  Fixture f;
  f.backend.position = 0.5f;
  f.native(0.5f, 0.4f);
  assert(f.backend.count(Backend::Kind::LIFT) == 1);
  assert(f.backend.count(Backend::Kind::TILT) == 1);
}

void test_moving_equal_retarget_stops_and_waits_for_idle() {
  Fixture f;
  f.backend.asynchronous_stop = true;
  f.native_lift(0.8f);
  f.backend.position = 0.25f;
  f.native(0.25f, 0.4f);
  assert(f.backend.count(Backend::Kind::STOP) == 1);
  assert(f.backend.count(Backend::Kind::LIFT) == 1);
  assert(f.backend.count(Backend::Kind::TILT) == 0);
  f.backend.finish(0.25f, 0.0f);
  assert(f.backend.count(Backend::Kind::TILT) == 1);
}

void test_new_lift_prevents_stale_completion_tilt() {
  Fixture f;
  f.native(0.5f, 0.25f);
  f.matter_move(WindowCoveringType::Lift, 0.8f);
  f.backend.finish(0.5002f, 1.0f);
  f.backend.publish_state(false);
  assert(f.backend.count(Backend::Kind::TILT) == 0);
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[Fixture::ENDPOINT].tilt_target.Value() == 7500);
  f.component.run_main_loop();
  assert(f.backend.commands.back().value == 0.8f);
  f.backend.finish(0.8002f, 1.0f);
  assert(f.backend.count(Backend::Kind::TILT) == 1);
}

void test_reports_coalesce_and_final_idle_wins() {
  Fixture f;
  f.native_lift(0.8f);
  for (unsigned i = 1; i <= 1000; ++i) {
    f.backend.position = 0.8f * i / 1000.0f;
    f.backend.publish_state(false);
  }
  assert(chip::DeviceLayer::SystemLayer().work.size() == 1);
  f.backend.finish(0.8002f, 1.0f);
  assert(chip::DeviceLayer::SystemLayer().work.size() == 1);
  chip::DeviceLayer::SystemLayer().run();
  const auto& state = endpoints[Fixture::ENDPOINT];
  assert(state.lift.Value() == 1998);
  assert(state.tilt_target.Value() == 0);
  assert(state.lift_target.Value() == 2000);
  assert(state.lift_status == OperationalState::Stall);
  assert(state.tilt_status == OperationalState::Stall);
}

void test_followup_tilt_reports_only_its_axis() {
  Fixture f;
  f.native(0.5f, 0.25f);
  f.backend.finish(0.5002f, 1.0f);
  chip::DeviceLayer::SystemLayer().run();
  const auto& state = endpoints[Fixture::ENDPOINT];
  assert(state.lift_status == OperationalState::Stall);
  assert(state.tilt_status == OperationalState::MovingDownOrClose);
  assert(state.tilt_target.Value() == 7500);
}

void test_final_reconciliation_survives_later_progress() {
  Fixture f;
  f.native_lift(0.8f);
  chip::DeviceLayer::SystemLayer().run();
  f.backend.position = 0.25f;
  f.local_stop();
  // Simulate local motion starting before CHIP consumes the stopped snapshot.
  f.backend.position = 0.3f;
  f.backend.current_operation = cover::COVER_OPERATION_OPENING;
  f.backend.publish_state(false);
  assert(chip::DeviceLayer::SystemLayer().work.size() == 1);
  chip::DeviceLayer::SystemLayer().run();
  const auto& state = endpoints[Fixture::ENDPOINT];
  assert(state.lift_target.Value() == 7500);
  assert(state.lift.Value() == 7000);
  assert(state.lift_status == OperationalState::MovingUpOrOpen);
}

void test_stale_reconciliation_does_not_overwrite_new_matter_target() {
  Fixture f;
  f.backend.finish(0.3f, 0.0f);
  f.matter_move(WindowCoveringType::Lift, 0.8f);
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[Fixture::ENDPOINT].lift_target.Value() == 2000);
  f.component.run_main_loop();
}

void test_schedule_failure_retries_final_state_without_new_publication() {
  Fixture f;
  chip::DeviceLayer::SystemLayer().failures_remaining = 2;
  f.backend.finish(0.25f, 0.5f);
  assert(chip::DeviceLayer::SystemLayer().work.empty());
  assert(f.component.work_.size() == 1);
  f.component.run_main_loop();
  assert(f.component.work_.size() == 1);
  f.component.run_main_loop();
  assert(chip::DeviceLayer::SystemLayer().work.size() == 1);
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[Fixture::ENDPOINT].lift.Value() == 7500);
  assert(endpoints[Fixture::ENDPOINT].tilt_target.Value() == 5000);
  assert(endpoints[Fixture::ENDPOINT].lift_status == OperationalState::Stall);
}

void test_nonfinite_state_reports_unknown_and_commands_are_rejected() {
  Fixture f;
  f.native(std::numeric_limits<float>::quiet_NaN(), 0.5f);
  assert(f.backend.commands.empty());
  f.backend.finish(std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity());
  chip::DeviceLayer::SystemLayer().run();
  assert(endpoints[Fixture::ENDPOINT].lift.IsNull());
  assert(endpoints[Fixture::ENDPOINT].tilt.IsNull());
}

void test_native_proxy_mirrors_backend_and_routes_stop() {
  Fixture f;
  MatterNativeCover native;
  native.set_source(&f.backend);
  native.set_parent(&f.component);
  native.setup();
  assert(native.get_traits().get_supports_tilt());
  auto call = native.make_call();
  call.set_position(0.8f).set_tilt(0.25f).perform();
  f.backend.position = 0.3f;
  f.backend.publish_state(false);
  assert(native.position == 0.3f);
  auto stop = native.make_call();
  stop.set_stop(true).perform();
  assert(native.current_operation == cover::COVER_OPERATION_IDLE);
  assert(f.backend.count(Backend::Kind::TILT) == 0);
}

int main() {
  static_assert(std::is_final_v<MatterCoverMapping>);
  static_assert(std::is_final_v<MatterNativeCover>);
  test_overshoot_continues_latest_tilt();
  test_stop_cancels_tilt_at_and_past_target();
  test_async_local_stop_clears_post_stop_lift();
  test_async_stop_holds_and_coalesces_later_commands();
  test_internal_stop_callback_preserves_newer_command();
  test_equal_idle_position_reaches_backend();
  test_idle_noop_completes_combined_request();
  test_moving_equal_retarget_stops_and_waits_for_idle();
  test_new_lift_prevents_stale_completion_tilt();
  test_reports_coalesce_and_final_idle_wins();
  test_followup_tilt_reports_only_its_axis();
  test_final_reconciliation_survives_later_progress();
  test_stale_reconciliation_does_not_overwrite_new_matter_target();
  test_schedule_failure_retries_final_state_without_new_publication();
  test_nonfinite_state_reports_unknown_and_commands_are_rejected();
  test_native_proxy_mirrors_backend_and_routes_stop();
  std::puts("Matter cover mapping: 16 regression cases passed");
}
