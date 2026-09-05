import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.const import CONF_LIGHT_ID, CONF_SENSOR_ID
from esphome.types import ConfigType

from .const import *
from .data_model import (
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    CLUSTER_SDKCONFIG_OPTIONS,
)
from .types import MatterEndpointRef


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
        }
        | {device_type.schema_key: device_type.schema for device_type in DEVICE_TYPES}
    ),
)


async def register_endpoints(var, config: ConfigType):
    root_node = DEVICE_TYPES_BY_ID[22]
    enabled_sdkconfig_clusters = {
        cluster.sdkconfig_option for cluster in root_node.clusters
    }
    enabled_sdkconfig_clusters.update(
        {
            "CONFIG_SUPPORT_BINDING_CLUSTER",
            "CONFIG_SUPPORT_TLS_CERTIFICATE_MANAGEMENT_CLUSTER",
            # A bug in esp_matter builds the LevelControl cluster unconditionally...
            "CONFIG_SUPPORT_LEVEL_CONTROL_CLUSTER",
            "CONFIG_SUPPORT_COLOR_CONTROL_CLUSTER",
            "CONFIG_SUPPORT_SCENES_CLUSTER",
        }
    )

    for endpoint_id, endpoint_config in config[CONF_ENDPOINTS].items():
        # Register endpoint
        cg.add(var.register_endpoint(endpoint_id))

        enable_binding = False
        for conf_key, device_config in endpoint_config.items():
            try:
                device_type = DEVICE_TYPES_BY_CONF_KEY[conf_key]
            except KeyError:
                continue

            enable_binding |= any(
                c.camel_case_name == "Binding" for c in device_type.clusters
            )

            # Register device type
            register_device_type = var.register_device_type.template(
                cg.RawExpression(
                    f"esp_matter::endpoint::{device_type.namespace}::config_t"
                ),
                cg.RawExpression(f"esp_matter::endpoint::{device_type.namespace}::add"),
            )
            cg.add(register_device_type(endpoint_id, device_type.namespace))

            # Register ESPHome entities
            if CONF_SENSOR_ID in device_config:
                sensor_ = await cg.get_variable(device_config[CONF_SENSOR_ID])
                cg.add(var.map_sensor_to_endpoint(sensor_, endpoint_id))
            elif CONF_LIGHT_ID in device_config:
                light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
                cg.add(var.map_light_to_endpoint(light_, endpoint_id))

            # Enable clusters in esp_matter
            # TODO: only enable clusters that are actually used
            for cluster in device_type.clusters:
                enabled_sdkconfig_clusters.add(cluster.sdkconfig_option)

        # Register binding on endpoint
        if enable_binding:
            cg.add(var.register_binding(endpoint_id))

    for sdkconfig_option in CLUSTER_SDKCONFIG_OPTIONS:
        add_idf_sdkconfig_option(
            sdkconfig_option, sdkconfig_option in enabled_sdkconfig_clusters
        )
