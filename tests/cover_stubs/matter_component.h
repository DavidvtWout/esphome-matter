#pragma once
#include "cover_test_runtime.h"
#include "matter_covers.h"
namespace esphome::matter {
class MatterComponent : public Component {
 public:
  void map_cover_to_endpoint(cover::Cover*, uint16_t, bool);
  void cancel_cover_pending_commands(cover::Cover*);
  MatterCoverMapping* get_cover_mapping(cover::Cover*);
  void defer_to_main_loop(std::function<void()>&& callback) { work_.push_back(std::move(callback)); }
  void run_main_loop() {
    // Deferred callbacks queued during this turn run on the next turn.
    auto turn = std::move(work_);
    work_.clear();
    for (auto& callback : turn) callback();
  }
  std::vector<MatterCoverMapping*> cover_mappings_;
  std::vector<MatterEndpointMappingBase*> mappings_;
  std::vector<std::function<void()>> work_;
};
inline MatterComponent* global_matter_component = nullptr;
}  // namespace esphome::matter
