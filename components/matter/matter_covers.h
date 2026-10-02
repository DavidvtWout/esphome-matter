#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_COVER)

#include "esphome/components/cover/cover.h"
#include "matter_endpoints.h"

#include <app/clusters/window-covering-server/WindowCoveringCluster.h>

#include <cstdint>
#include <mutex>
#include <optional>

namespace esphome::matter {

class MatterCoverMapping
    : public MatterEndpointMappingBase,
      public chip::app::Clusters::WindowCovering::WindowCoveringDelegate {
public:
  MatterCoverMapping(cover::Cover *cover, uint16_t endpoint_id,
                     bool supports_tilt);

  bool validate() override;
  void register_callbacks() override;
  MatterCoverMapping *as_cover_mapping() override { return this; }

  CHIP_ERROR HandleMovement(
      chip::app::Clusters::WindowCovering::WindowCoveringType type) override;
  CHIP_ERROR HandleStopMotion() override;

protected:
  struct AxisTarget {
    bool present{false};
    float value{0.0f};
    uint32_t generation{0};
  };

  void schedule_drain_();
  void drain_pending_();
  void on_cover_state_();
  void push_state_to_matter_(bool reconcile_targets);
  void perform_position_(float position);
  void perform_tilt_(float tilt);

  cover::Cover *cover_;
  bool supports_tilt_;

  std::mutex pending_mutex_;
  uint32_t next_generation_{0};
  bool drain_scheduled_{false};
  bool stop_pending_{false};
  uint32_t stop_generation_{0};
  AxisTarget pending_lift_{};
  AxisTarget pending_tilt_{};

  // Main-loop-only sequencing state. The underlying Venetian blind uses one
  // motor, so a requested tilt is applied after a lift reaches its target.
  std::optional<float> followup_tilt_{};
  bool reconcile_after_stop_{false};
};

} // namespace esphome::matter

#endif // USE_MATTER && USE_COVER
