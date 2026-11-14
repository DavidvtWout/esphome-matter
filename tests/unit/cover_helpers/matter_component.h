#pragma once
#include "runtime.h"
#include "matter_covers.h"

namespace esphome::matter {
class MatterComponent {
 public:
  void register_cover(cover::Cover *, uint16_t);
  void defer_to_main_loop(std::function<void()> callback) { work_.push_back(callback); }
  void run() {
    while (!work_.empty()) {
      auto callback = std::move(work_.front());
      work_.pop_front();
      callback();
    }
  }
  std::vector<MatterEndpointMappingBase *> mappings_;
  std::deque<std::function<void()>> work_;
};
inline MatterComponent *global_matter_component;
}
