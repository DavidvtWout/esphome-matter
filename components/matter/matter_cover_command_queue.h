#pragma once

#include <cstdint>
#include <mutex>

namespace esphome::matter {

// Thread-safe latest-value queue shared by Matter callbacks and the ESPHome
// main loop. Kept independent of ESPHome/CHIP so its ordering rules can be
// exercised by the native command-sequencing tests.
class MatterCoverCommandQueue {
public:
  struct Target {
    bool present{false};
    float value{0.0f};
    uint32_t generation{0};
  };

  struct Batch {
    bool stop{false};
    uint32_t stop_generation{0};
    Target lift{};
    Target tilt{};
  };

  struct Snapshot {
    uint32_t lift_generation{0};
    uint32_t tilt_generation{0};
    bool lift_pending{false};
    bool tilt_pending{false};
  };

  Target enqueue_lift(float value) { return this->enqueue_(true, value); }
  Target enqueue_tilt(float value) { return this->enqueue_(false, value); }

  uint32_t request_stop() {
    std::lock_guard<std::mutex> lock(this->mutex_);
    this->stop_pending_ = true;
    this->stop_generation_ = ++this->next_generation_;
    this->latest_stop_generation_ = this->stop_generation_;
    this->lift_ = {};
    this->tilt_ = {};
    return this->stop_generation_;
  }

  // Used by a local stop notification before cover.stop is issued.
  uint32_t cancel_pending() {
    std::lock_guard<std::mutex> lock(this->mutex_);
    this->latest_stop_generation_ = ++this->next_generation_;
    this->stop_generation_ = this->latest_stop_generation_;
    this->lift_ = {};
    this->tilt_ = {};
    return this->stop_generation_;
  }

  bool mark_drain_scheduled() {
    std::lock_guard<std::mutex> lock(this->mutex_);
    if (this->drain_scheduled_)
      return false;
    this->drain_scheduled_ = true;
    return true;
  }

  Batch take_pending() {
    std::lock_guard<std::mutex> lock(this->mutex_);
    Batch batch{this->stop_pending_, this->stop_generation_, this->lift_,
                this->tilt_};
    this->stop_pending_ = false;
    this->lift_ = {};
    this->tilt_ = {};
    this->drain_scheduled_ = false;
    return batch;
  }

  bool is_current(const Target &target, bool lift) const {
    if (!target.present)
      return false;
    std::lock_guard<std::mutex> lock(this->mutex_);
    const uint32_t latest = lift ? this->latest_lift_generation_
                                 : this->latest_tilt_generation_;
    return target.generation == latest &&
           target.generation > this->latest_stop_generation_;
  }

  Snapshot snapshot() const {
    std::lock_guard<std::mutex> lock(this->mutex_);
    return {this->latest_lift_generation_, this->latest_tilt_generation_,
            this->lift_.present, this->tilt_.present};
  }

  bool lift_generation_matches(uint32_t generation) const {
    std::lock_guard<std::mutex> lock(this->mutex_);
    return this->latest_lift_generation_ == generation;
  }

  bool tilt_generation_matches(uint32_t generation) const {
    std::lock_guard<std::mutex> lock(this->mutex_);
    return this->latest_tilt_generation_ == generation;
  }

private:
  Target enqueue_(bool lift, float value) {
    std::lock_guard<std::mutex> lock(this->mutex_);
    const uint32_t generation = ++this->next_generation_;
    Target target{true, value, generation};
    if (lift) {
      this->lift_ = target;
      this->latest_lift_generation_ = generation;
    } else {
      this->tilt_ = target;
      this->latest_tilt_generation_ = generation;
    }
    return target;
  }

  mutable std::mutex mutex_;
  uint32_t next_generation_{0};
  bool drain_scheduled_{false};
  bool stop_pending_{false};
  uint32_t stop_generation_{0};
  uint32_t latest_stop_generation_{0};
  uint32_t latest_lift_generation_{0};
  uint32_t latest_tilt_generation_{0};
  Target lift_{};
  Target tilt_{};
};

} // namespace esphome::matter
