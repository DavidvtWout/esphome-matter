#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include "matter_code_driven.h"

#include <app/clusters/air-quality-server/AirQualityCluster.h>
#include <app/clusters/fan-control-server/FanControlCluster.h>
#include <app/clusters/resource-monitoring-server/ResourceMonitoringCluster.h>
#include <data_model_provider/esp_matter_data_model_provider.h>
#include <sdkconfig.h>

namespace esphome::matter {

namespace {

using namespace chip::app::Clusters;
using chip::Protocols::InteractionModel::Status;

template <typename ClusterT>
ClusterT *find_cluster(uint16_t endpoint_id, uint32_t cluster_id) {
  auto *server =
      esp_matter::data_model::provider::get_instance().registry().Get(
          {endpoint_id, cluster_id});
  return static_cast<ClusterT *>(server);
}

CHIP_ERROR to_chip_error(Status status) {
  return status == Status::Success ? CHIP_NO_ERROR
                                   : CHIP_ERROR_INVALID_ARGUMENT;
}

#ifdef CONFIG_SUPPORT_FAN_CONTROL_CLUSTER
CHIP_ERROR update_fan_mode(uint16_t endpoint_id, uint32_t cluster_id,
                           esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<FanControlCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(
      cluster->SetFanMode(static_cast<FanControl::FanModeEnum>(value.val.u8)));
}

CHIP_ERROR update_fan_percent_setting(uint16_t endpoint_id, uint32_t cluster_id,
                                      esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<FanControlCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(cluster->SetPercentSetting(
      chip::app::DataModel::MakeNullable<chip::Percent>(value.val.u8)));
}

CHIP_ERROR update_fan_speed_setting(uint16_t endpoint_id, uint32_t cluster_id,
                                    esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<FanControlCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(cluster->SetSpeedSetting(
      chip::app::DataModel::MakeNullable<uint8_t>(value.val.u8)));
}

CHIP_ERROR update_fan_percent_current(uint16_t endpoint_id, uint32_t cluster_id,
                                      esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<FanControlCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  cluster->SetPercentCurrent(value.val.u8);
  return CHIP_NO_ERROR;
}

CHIP_ERROR update_fan_speed_current(uint16_t endpoint_id, uint32_t cluster_id,
                                    esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<FanControlCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  cluster->SetSpeedCurrent(value.val.u8);
  return CHIP_NO_ERROR;
}
#endif // CONFIG_SUPPORT_FAN_CONTROL_CLUSTER

} // namespace

#ifdef CONFIG_SUPPORT_AIR_QUALITY_CLUSTER
CHIP_ERROR update_air_quality_attribute(uint16_t endpoint_id,
                                        uint32_t cluster_id,
                                        esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<AirQualityCluster>(endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(cluster->SetAirQuality(
      static_cast<AirQuality::AirQualityEnum>(value.val.u8)));
}
#endif // CONFIG_SUPPORT_AIR_QUALITY_CLUSTER

#if defined(CONFIG_SUPPORT_HEPA_FILTER_MONITORING_CLUSTER) ||                  \
    defined(CONFIG_SUPPORT_ACTIVATED_CARBON_FILTER_MONITORING_CLUSTER)
CHIP_ERROR update_resource_condition_attribute(uint16_t endpoint_id,
                                               uint32_t cluster_id,
                                               esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<ResourceMonitoring::ResourceMonitoringCluster>(
      endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(cluster->UpdateCondition(value.val.u8));
}

CHIP_ERROR update_resource_change_indication_attribute(
    uint16_t endpoint_id, uint32_t cluster_id, esp_matter_attr_val_t value) {
  auto *cluster = find_cluster<ResourceMonitoring::ResourceMonitoringCluster>(
      endpoint_id, cluster_id);
  if (cluster == nullptr)
    return CHIP_ERROR_NOT_FOUND;
  return to_chip_error(cluster->UpdateChangeIndication(
      static_cast<ResourceMonitoring::ChangeIndicationEnum>(value.val.u8)));
}
#endif

CodeDrivenAttributeUpdater find_code_driven_updater(uint32_t cluster_id,
                                                    uint32_t attribute_id) {
  switch (cluster_id) {
#ifdef CONFIG_SUPPORT_FAN_CONTROL_CLUSTER
  case FanControl::Id:
    switch (attribute_id) {
    case FanControl::Attributes::FanMode::Id:
      return update_fan_mode;
    case FanControl::Attributes::PercentSetting::Id:
      return update_fan_percent_setting;
    case FanControl::Attributes::PercentCurrent::Id:
      return update_fan_percent_current;
    case FanControl::Attributes::SpeedSetting::Id:
      return update_fan_speed_setting;
    case FanControl::Attributes::SpeedCurrent::Id:
      return update_fan_speed_current;
    }
    break;
#endif // CONFIG_SUPPORT_FAN_CONTROL_CLUSTER
#ifdef CONFIG_SUPPORT_AIR_QUALITY_CLUSTER
  case AirQuality::Id:
    if (attribute_id == AirQuality::Attributes::AirQuality::Id)
      return update_air_quality_attribute;
    break;
#endif // CONFIG_SUPPORT_AIR_QUALITY_CLUSTER
#ifdef CONFIG_SUPPORT_HEPA_FILTER_MONITORING_CLUSTER
  case HepaFilterMonitoring::Id:
#endif
#ifdef CONFIG_SUPPORT_ACTIVATED_CARBON_FILTER_MONITORING_CLUSTER
  case ActivatedCarbonFilterMonitoring::Id:
#endif
#if defined(CONFIG_SUPPORT_HEPA_FILTER_MONITORING_CLUSTER) ||                  \
    defined(CONFIG_SUPPORT_ACTIVATED_CARBON_FILTER_MONITORING_CLUSTER)
    switch (attribute_id) {
    case ResourceMonitoring::Attributes::Condition::Id:
      return update_resource_condition_attribute;
    case ResourceMonitoring::Attributes::ChangeIndication::Id:
      return update_resource_change_indication_attribute;
    }
    break;
#endif
  }
  return nullptr;
}

} // namespace esphome::matter

#endif // USE_MATTER
