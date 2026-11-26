#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_COVER)

#include <app/clusters/window-covering-server/WindowCoveringCluster.h>
#include <atomic>

#include "esphome/components/cover/cover.h"
#include "matter_endpoints.h"

namespace esphome::matter {

class MatterCoverMapping : public MatterEndpointMappingBase,
                           public chip::app::Clusters::WindowCovering::WindowCoveringDelegate {
 public:
  MatterCoverMapping(cover::Cover *cover, uint16_t endpoint_id)
      : MatterEndpointMappingBase(endpoint_id), cover_(cover) {}

  void initialize() override;
  CHIP_ERROR HandleMovement(chip::app::Clusters::WindowCovering::WindowCoveringType type) override;
  CHIP_ERROR HandleStopMotion() override;

 protected:
  void push_state_to_matter_();

  cover::Cover *cover_;
  bool has_lift_{false};
  bool has_tilt_{false};
  // Only the newest command may reconcile targets, so a state publication
  // captured before a newer command cannot overwrite that command's target.
  // Commands themselves are still forwarded to the backend in arrival order.
  std::atomic<uint32_t> command_revision_{0};
  uint32_t applied_command_revision_{0};  // ESPHome main loop only.
};

}  // namespace esphome::matter

#endif  // USE_MATTER && USE_COVER
