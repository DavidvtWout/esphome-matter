#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_FAN)

#include "esphome/core/log.h"
#include "matter_component.h"
#include "matter_fans.h"

#include <algorithm>
#include <app/clusters/fan-control-server/FanControlCluster.h>
#include <cmath>
#include <data_model_provider/esp_matter_data_model_provider.h>
#include <esp_matter_cluster.h>
#include <platform/CHIPDeviceLayer.h>

namespace chip::app::Clusters::FanControl {
void SetDefaultDelegate(EndpointId endpoint_id, Delegate *delegate);
} // namespace chip::app::Clusters::FanControl

static const char *const TAG = "matter.fan";

namespace esphome::matter {

namespace {

using namespace chip::app::Clusters;

const char *find_auto_preset(fan::Fan *fan) {
  auto traits = fan->get_traits();
  for (const char *name : {"Auto", "auto", "AUTO"}) {
    if (const char *preset = traits.find_preset_mode(name))
      return preset;
  }
  return nullptr;
}

uint8_t matter_speed_count(fan::Fan *fan) {
  auto traits = fan->get_traits();
  if (!traits.supports_speed())
    return 0;
  return static_cast<uint8_t>(
      std::clamp(traits.supported_speed_count(), 1, 100));
}

uint8_t speed_to_percent(uint8_t speed, uint8_t speed_count) {
  if (speed_count == 0)
    return speed > 0 ? 100 : 0;
  return static_cast<uint8_t>(std::min(100, speed * 100 / speed_count));
}

uint8_t percent_to_speed(uint8_t percent, uint8_t speed_count) {
  if (percent == 0 || speed_count == 0)
    return 0;
  return static_cast<uint8_t>(std::clamp((percent * speed_count + 99) / 100, 1,
                                         static_cast<int>(speed_count)));
}

} // namespace

bool configure_fan_control(esp_matter::endpoint_t *endpoint, fan::Fan *fan) {
  namespace fan_control = esp_matter::cluster::fan_control;
  auto *cluster = esp_matter::cluster::get(endpoint, FanControl::Id);
  if (cluster == nullptr || fan == nullptr)
    return false;

  uint8_t speed_count = matter_speed_count(fan);
  bool fan_has_auto = find_auto_preset(fan) != nullptr;

  auto *speed_max =
      esp_matter::attribute::get(cluster, FanControl::Attributes::SpeedMax::Id);
  bool has_multi_speed = speed_max != nullptr;
  esp_matter_attr_val_t feature_map = esp_matter_bitmap32(0);
  auto *feature_map_attribute = esp_matter::attribute::get(
      cluster, chip::app::Clusters::Globals::Attributes::FeatureMap::Id);
  if (feature_map_attribute != nullptr)
    esp_matter::attribute::get_val(feature_map_attribute, &feature_map);
  bool has_auto =
      (feature_map.val.u32 & fan_control::feature::fan_auto::get_id()) != 0;

  if (speed_count > 1 && !has_multi_speed)
    ESP_LOGW(TAG,
             "Fan has %u speeds; add the multi_speed feature to expose "
             "them",
             speed_count);
  if (fan_has_auto != has_auto)
    ESP_LOGW(TAG, "Fan %s an Auto preset but the auto feature is %s",
             fan_has_auto ? "has" : "lacks", has_auto ? "enabled" : "disabled");

  if (has_multi_speed) {
    esp_matter_attr_val_t value =
        esp_matter_uint8(std::max<uint8_t>(speed_count, 1));
    if (esp_matter::attribute::set_val(speed_max, &value, false) != ESP_OK)
      return false;
  }

  FanControl::FanModeSequenceEnum sequence;
  if (speed_count >= 3) {
    sequence = has_auto ? FanControl::FanModeSequenceEnum::kOffLowMedHighAuto
                        : FanControl::FanModeSequenceEnum::kOffLowMedHigh;
  } else if (speed_count == 2) {
    sequence = has_auto ? FanControl::FanModeSequenceEnum::kOffLowHighAuto
                        : FanControl::FanModeSequenceEnum::kOffLowHigh;
  } else {
    sequence = has_auto ? FanControl::FanModeSequenceEnum::kOffHighAuto
                        : FanControl::FanModeSequenceEnum::kOffHigh;
  }
  auto *attribute = esp_matter::attribute::get(
      cluster, FanControl::Attributes::FanModeSequence::Id);
  if (attribute == nullptr)
    return false;
  esp_matter_attr_val_t value =
      esp_matter_enum8(static_cast<uint8_t>(sequence));
  return esp_matter::attribute::set_val(attribute, &value, false) == ESP_OK;
}

void MatterComponent::register_fan(fan::Fan *fan, uint16_t endpoint_id) {
  this->mappings_.push_back(new MatterFanMapping(fan, endpoint_id));
}

MatterFanMapping::MatterFanMapping(fan::Fan *fan, uint16_t endpoint_id)
    : MatterEndpointMappingBase(endpoint_id), FanControl::Delegate(endpoint_id),
      fan_(fan) {}

void MatterFanMapping::initialize() {
  if (this->fan_ == nullptr)
    return;

  this->auto_preset_ = find_auto_preset(this->fan_);
  this->speed_count_ = matter_speed_count(this->fan_);
  this->has_on_off_ = this->has_server_cluster(OnOff::Id);

  if (this->has_on_off_) {
    global_matter_component->register_attribute_callback(
        this->endpoint_id(), OnOff::Id, OnOff::Attributes::OnOff::Id,
        [this](const esp_matter_attr_val_t &value) {
          bool on = value.val.b;
          global_matter_component->defer_to_main_loop(
              [this, on]() { this->apply_on_off_from_matter_(on); });
        });
  }

  this->fan_->add_on_state_callback([this]() {
    if (this->applying_from_matter_)
      return;
    this->push_state_to_matter_();
  });

  uint16_t eid = this->endpoint_id();
  chip::DeviceLayer::SystemLayer().ScheduleLambda([this, eid]() {
    FanControl::SetDefaultDelegate(eid, this);
    global_matter_component->defer_to_main_loop(
        [this]() { this->push_state_to_matter_(); });
  });
}

void MatterFanMapping::push_state_to_matter_() {
  MatterFanState state;
  state.on = this->fan_->state;
  state.automatic = state.on && this->auto_preset_ != nullptr &&
                    this->fan_->get_preset_mode() == this->auto_preset_;
  uint8_t speed_count = this->speed_count_;
  if (state.on) {
    state.speed =
        speed_count == 0
            ? 1
            : static_cast<uint8_t>(std::clamp(this->fan_->speed, 1,
                                              static_cast<int>(speed_count)));
  }
  uint16_t eid = this->endpoint_id();
  bool has_on_off = this->has_on_off_;

  chip::DeviceLayer::SystemLayer().ScheduleLambda(
      [this, eid, state, speed_count, has_on_off]() {
        auto *server =
            esp_matter::data_model::provider::get_instance().registry().Get(
                {eid, FanControl::Id});
        if (server == nullptr)
          return;
        auto *cluster = static_cast<FanControlCluster *>(server);

        this->pushing_to_matter_ = true;
        uint8_t percent = speed_to_percent(state.speed, speed_count);
        if (!state.on) {
          cluster->SetFanMode(FanControl::FanModeEnum::kOff);
        } else if (state.automatic) {
          cluster->SetFanMode(FanControl::FanModeEnum::kAuto);
        } else {
          cluster->SetPercentSetting(
              chip::app::DataModel::MakeNullable<chip::Percent>(percent));
          if (speed_count > 1)
            cluster->SetSpeedSetting(
                chip::app::DataModel::MakeNullable<uint8_t>(state.speed));
        }
        if (state.on) {
          cluster->SetPercentCurrent(percent);
          if (speed_count > 1)
            cluster->SetSpeedCurrent(state.speed);
        }
        this->pushing_to_matter_ = false;

        if (has_on_off) {
          esp_matter_attr_val_t on_val = esp_matter_bool(state.on);
          esp_matter::attribute::report(eid, OnOff::Id,
                                        OnOff::Attributes::OnOff::Id, &on_val);
        }
      });
}

chip::Protocols::InteractionModel::Status
MatterFanMapping::HandleStep(FanControl::StepDirectionEnum direction, bool wrap,
                             bool lowest_off) {
  return chip::Protocols::InteractionModel::Status::UnsupportedCommand;
}

void MatterFanMapping::OnFanDriveStateChanged(
    const FanControl::FanDriveState &drive_state) {
  if (this->pushing_to_matter_)
    return;

  uint8_t speed_count = this->speed_count_;
  MatterFanState state;
  switch (drive_state.mode) {
  case FanControl::FanModeEnum::kOff:
    break;
  case FanControl::FanModeEnum::kAuto:
  case FanControl::FanModeEnum::kSmart:
    state.on = true;
    state.automatic = true;
    break;
  default:
    state.on = true;
    if (speed_count > 1 && !drive_state.speedSetting.IsNull() &&
        drive_state.speedSetting.Value() > 0) {
      state.speed = std::min(drive_state.speedSetting.Value(), speed_count);
    } else if (!drive_state.percentSetting.IsNull()) {
      state.speed =
          percent_to_speed(drive_state.percentSetting.Value(), speed_count);
    }
    if (state.speed == 0 && speed_count > 0)
      state.speed = 1;
    break;
  }

  ESP_LOGD(TAG, "Endpoint %u: Matter set on=%d auto=%d speed=%u",
           this->endpoint_id(), state.on, state.automatic, state.speed);
  global_matter_component->defer_to_main_loop(
      [this, state]() { this->apply_state_from_matter_(state); });
}

void MatterFanMapping::apply_state_from_matter_(MatterFanState state) {
  auto call = state.on ? this->fan_->turn_on() : this->fan_->turn_off();
  if (state.on) {
    if (state.automatic) {
      if (this->auto_preset_ != nullptr)
        call.set_preset_mode(this->auto_preset_);
    } else if (this->speed_count_ > 0) {
      call.set_speed(state.speed);
    }
  }
  this->applying_from_matter_ = true;
  call.perform();
  this->applying_from_matter_ = false;
  this->push_state_to_matter_();
}

void MatterFanMapping::apply_on_off_from_matter_(bool on) {
  if (this->fan_->state == on)
    return;
  auto call = on ? this->fan_->turn_on() : this->fan_->turn_off();
  this->applying_from_matter_ = true;
  call.perform();
  this->applying_from_matter_ = false;
  this->push_state_to_matter_();
}

} // namespace esphome::matter

#endif // USE_MATTER && USE_FAN
