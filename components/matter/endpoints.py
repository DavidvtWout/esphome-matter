import logging
from collections import defaultdict

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.const import CONF_LIGHT_ID
from esphome.types import ConfigType

from .const import *
from .data_model import (
    CLUSTERS,
    CLUSTERS_BY_NAME,
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    ClusterConfig,
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
        | {device_type.schema_key: device_type.schema() for device_type in DEVICE_TYPES}
    ),
)


async def _register_endpoint(var, endpoint_id, endpoint_config):
    enabled_clusters: set[str] = set()  # sdkconfig options
    extra_clusters: dict[str, ClusterConfig] = defaultdict(ClusterConfig)
    extra_clusters["Binding"] = ClusterConfig(create=False)
    for cluster_name in endpoint_config[CONF_EXTRA_CLUSTERS]:
        extra_clusters[cluster_name] = ClusterConfig(create=True)

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
                extra_clusters[cluster.camel_case_name].create = False
            # esp_matter doesn't create the binding cluster when adding a device type to an endpoint, even when
            # the device type requires it so it must always be forcibly created when a device type needs it.
            if cluster.camel_case_name == "Binding":
                extra_clusters["Binding"].create = True

        # Find extra clusters that need to be enabled for sensor attributes
        for (
            cluster_name,
            attribute_name,
            sensor_attribute,
        ) in device_type.sensor_attributes:
            # TODO: what if multiple device_types register the same sensor_attribute?
            sensor_id = device_config.get(sensor_attribute.conf_key)
            if sensor_id is not None:
                extra_clusters[cluster_name].create &= True
                for feature in sensor_attribute.features:
                    extra_clusters[cluster_name].enabled_features[feature] = True
                cluster = CLUSTERS_BY_NAME[cluster_name]
                attribute = next(
                    attribute
                    for attribute in cluster.server_attributes
                    if attribute.name == attribute_name
                )
                await sensor_attribute.register(
                    var,
                    endpoint_id,
                    cluster_name,
                    cluster.id,
                    attribute,
                    device_config,
                )

        # Register device type
        created_clusters = device_type.register(var, endpoint_id, device_config)
        for cluster in created_clusters:
            enabled_clusters.add(cluster.sdkconfig_option)

        # Register ESPHome entities
        if CONF_LIGHT_ID in device_config:
            light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
            cg.add(var.map_light_to_endpoint(light_, endpoint_id))

    # Register extra clusters
    for cluster_name, cluster_config in extra_clusters.items():
        if not cluster_config.create:
            continue
        cluster = CLUSTERS_BY_NAME[cluster_name]
        enabled_clusters.add(cluster.sdkconfig_option)
        cluster.register(var, endpoint_id, cluster_config)

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
