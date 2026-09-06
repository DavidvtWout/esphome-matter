import logging

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.const import CONF_LIGHT_ID, CONF_SENSOR_ID
from esphome.types import ConfigType

from .const import *
from .data_model import (
    CLUSTERS,
    CLUSTERS_BY_NAME,
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    Cluster,
    DeviceType,
)
from .types import MatterEndpointRef

_LOGGER = logging.getLogger(__name__)

ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_EXTRA_CLUSTERS, default=list): cv.ensure_list(
                cv.one_of(*(cluster.camel_case_name for cluster in CLUSTERS))
            ),
        }
        | {device_type.schema_key: device_type.schema for device_type in DEVICE_TYPES}
    ),
)


def _register_cluster(var, endpoint_id: int, cluster: Cluster):
    _LOGGER.debug(
        "[Matter] Registering cluster %s on endpoint %s",
        cluster.name,
        endpoint_id,
    )
    cluster_namespace = f"esp_matter::cluster::{cluster.namespace}"
    cluster_config = cg.RawExpression(f"{cluster_namespace}::config_t{{}}")
    cg.add(
        var.register_cluster(
            cg.TemplateArguments(
                cluster.id,
                cg.RawExpression(f"{cluster_namespace}::config_t"),
                cg.RawExpression(f"{cluster_namespace}::create"),
            ),
            endpoint_id,
            cluster.name,
            cluster_config,
        )
    )


def _register_device_type(var, endpoint_id: int, device_type: DeviceType):
    _LOGGER.debug(
        "[Matter] Registering device type %s on endpoint %s",
        device_type.name,
        endpoint_id,
    )
    device_type_namespace = f"esp_matter::endpoint::{device_type.namespace}"
    device_type_config = cg.RawExpression(f"{device_type_namespace}::config_t{{}}")
    register_device_type = var.register_device_type.template(
        cg.RawExpression(f"{device_type_namespace}::config_t"),
        cg.RawExpression(f"esp_matter::endpoint::{device_type.namespace}::add"),
    )
    cg.add(register_device_type(endpoint_id, device_type.namespace, device_type_config))


async def _register_endpoint(var, endpoint_id, endpoint_config):
    enabled_clusters: set[str] = set()  # sdkconfig options
    extra_clusters: dict[str, bool] = {
        cluster_name: True for cluster_name in endpoint_config[CONF_EXTRA_CLUSTERS]
    }

    # Register endpoint
    cg.add(var.register_endpoint(endpoint_id))

    for conf_key, device_config in endpoint_config.items():
        # Skip endpoint config options that aren't device types.
        try:
            device_type = DEVICE_TYPES_BY_CONF_KEY[conf_key]
        except KeyError:
            continue

        for cluster in device_type.server_clusters:
            if cluster.required:
                extra_clusters[cluster.camel_case_name] = False
            # esp_matter doesn't create the binding cluster when adding a device type to an endpoint, even when
            # the device type requires it so it must always be forcibly created when a device type needs it.
            if cluster.camel_case_name == "Binding":
                extra_clusters["Binding"] = True

        # Find extra clusters that need to be enabled for sensor attributes
        for (
            cluster_name,
            attribute_name,
            sensor_attribute,
        ) in device_type.sensor_attributes:
            # TODO: what if multiple device_types register the same sensor_attribute?
            sensor_id = device_config.get(sensor_attribute.conf_key)
            if sensor_id is not None:
                extra_clusters[cluster_name] = True & extra_clusters.get(
                    cluster_name, True
                )
                # TODO: register sensor

        # Register device type
        _register_device_type(var, endpoint_id, device_type)

        # Enable clusters in esp_matter
        for cluster in device_type.server_clusters:
            if cluster.required:
                enabled_clusters.add(cluster.sdkconfig_option)

        # Register ESPHome entities
        if CONF_SENSOR_ID in device_config:
            sensor_ = await cg.get_variable(device_config[CONF_SENSOR_ID])
            cg.add(var.map_sensor_to_endpoint(sensor_, endpoint_id))
        elif CONF_LIGHT_ID in device_config:
            light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
            cg.add(var.map_light_to_endpoint(light_, endpoint_id))

    # Register extra clusters
    for cluster_name, must_create in extra_clusters.items():
        if not must_create:
            continue
        cluster = CLUSTERS_BY_NAME[cluster_name]
        enabled_clusters.add(cluster.sdkconfig_option)
        _register_cluster(var, endpoint_id, cluster)

    return enabled_clusters


async def register_endpoints(var, config: ConfigType):
    root_node = DEVICE_TYPES_BY_ID[22]
    enabled_sdkconfig_clusters = {
        cluster.sdkconfig_option
        for cluster in root_node.server_clusters
        if cluster.required
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
        enabled_clusters = await _register_endpoint(var, endpoint_id, endpoint_config)
        enabled_sdkconfig_clusters.update(enabled_clusters)

    # Set sdkconfig options to compile the correct clusters.
    for cluster in CLUSTERS:
        sdkconfig_option = cluster.sdkconfig_option
        add_idf_sdkconfig_option(
            sdkconfig_option, sdkconfig_option in enabled_sdkconfig_clusters
        )
