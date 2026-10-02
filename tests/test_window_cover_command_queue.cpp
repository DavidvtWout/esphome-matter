#include "../components/matter/matter_cover_command_queue.h"

#include <cassert>

using esphome::matter::MatterCoverCommandQueue;

int main() {
  {
    MatterCoverCommandQueue queue;
    const auto first_lift = queue.enqueue_lift(0.8f);
    const auto first_tilt = queue.enqueue_tilt(0.6f);
    const auto latest_tilt = queue.enqueue_tilt(0.3f);
    assert(queue.mark_drain_scheduled());
    assert(!queue.mark_drain_scheduled());

    const auto batch = queue.take_pending();
    assert(!batch.stop);
    assert(batch.lift.generation == first_lift.generation);
    assert(batch.tilt.generation == latest_tilt.generation);
    assert(batch.tilt.generation != first_tilt.generation);
    assert(queue.is_current(batch.lift, true));
    assert(queue.is_current(batch.tilt, false));
  }

  {
    MatterCoverCommandQueue queue;
    const auto old_lift = queue.enqueue_lift(0.8f);
    const auto old_tilt = queue.enqueue_tilt(0.6f);
    const auto stop_generation = queue.request_stop();
    assert(!queue.is_current(old_lift, true));
    assert(!queue.is_current(old_tilt, false));

    const auto batch = queue.take_pending();
    assert(batch.stop);
    assert(batch.stop_generation == stop_generation);
    assert(!batch.lift.present);
    assert(!batch.tilt.present);
  }

  {
    MatterCoverCommandQueue queue;
    const auto old_lift = queue.enqueue_lift(0.8f);
    const auto old_tilt = queue.enqueue_tilt(0.6f);
    const auto stop_generation = queue.request_stop();
    const auto new_lift = queue.enqueue_lift(0.4f);
    const auto new_tilt = queue.enqueue_tilt(0.2f);

    const auto batch = queue.take_pending();
    assert(batch.stop);
    assert(batch.stop_generation == stop_generation);
    assert(batch.lift.generation == new_lift.generation);
    assert(batch.tilt.generation == new_tilt.generation);
    assert(!queue.is_current(old_lift, true));
    assert(!queue.is_current(old_tilt, false));
    assert(queue.is_current(batch.lift, true));
    assert(queue.is_current(batch.tilt, false));
  }

  {
    MatterCoverCommandQueue queue;
    const auto detached = queue.enqueue_lift(0.8f);
    const auto batch = queue.take_pending();
    assert(batch.lift.generation == detached.generation);

    // A local Stop can arrive after a drain detached its batch. It invalidates
    // that work even though it cannot remove the local copy held by the drain.
    queue.cancel_pending();
    assert(!queue.is_current(detached, true));
    assert(!queue.snapshot().lift_pending);

    const auto newer = queue.enqueue_lift(0.3f);
    assert(queue.is_current(newer, true));
  }

  {
    MatterCoverCommandQueue queue;
    const auto before = queue.snapshot();
    assert(queue.lift_generation_matches(before.lift_generation));
    queue.enqueue_lift(0.7f);
    assert(!queue.lift_generation_matches(before.lift_generation));
    assert(queue.tilt_generation_matches(before.tilt_generation));
  }
}
