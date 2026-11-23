#pragma once

#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_FAN)

#include "esphome/components/fan/fan.h"
#include "matter_endpoints.h"

#include <app/clusters/fan-control-server/fan-control-delegate.h>
#include <esp_matter.h>

#include <cstdint>

namespace esphome::matter {

bool configure_fan_control(esp_matter::endpoint_t *endpoint, fan::Fan *fan);

struct MatterFanState {
  bool on{false};
  bool automatic{false};
  uint8_t speed{0};
};

class MatterFanMapping : public MatterEndpointMappingBase,
                         public chip::app::Clusters::FanControl::Delegate {
public:
  MatterFanMapping(fan::Fan *fan, uint16_t endpoint_id);

  void initialize() override;

  chip::Protocols::InteractionModel::Status
  HandleStep(chip::app::Clusters::FanControl::StepDirectionEnum direction,
             bool wrap, bool lowest_off) override;
  void OnFanDriveStateChanged(
      const chip::app::Clusters::FanControl::FanDriveState &state) override;

protected:
  void push_state_to_matter_();
  void apply_state_from_matter_(MatterFanState state);
  void apply_on_off_from_matter_(bool on);

  fan::Fan *fan_;
  const char *auto_preset_{nullptr};
  uint8_t speed_count_{0};
  bool has_on_off_{false};
  bool pushing_to_matter_{false};
  bool applying_from_matter_{false};
};

} // namespace esphome::matter

#endif // USE_MATTER && USE_FAN
