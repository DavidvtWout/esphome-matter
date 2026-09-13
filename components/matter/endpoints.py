import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import cast

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.binary_sensor import BinarySensor
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.components.sensor import Sensor
from esphome.const import CONF_LIGHT_ID
from esphome.core import ID
from esphome.types import ConfigType

from .const import *
from .data_model.attributes import SensorAttribute
from .data_model.clusters import CLUSTERS, CLUSTERS_BY_NAME, Cluster
from .data_model.device_types import (
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    DeviceType,
)
from .types import MatterEndpointRef

_LOGGER = logging.getLogger(__name__)

ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_EXTRA_CLUSTERS, default=list): cv.ensure_list(
                cv.one_of(*(cluster.name for cluster in CLUSTERS))
            ),
        }
        | {device_type.schema_key: device_type.schema() for device_type in DEVICE_TYPES}
    ),
)


@dataclass
class _ClusterConfig:
    # Whether or not the cluster is already created by a device type config.
    created: bool = False
    # Keys are feature names.
    enabled_features: dict[str, bool] = field(default_factory=dict)


class Endpoint:
    def __init__(self, var, endpoint_id: int, config: dict):
        self._var = var
        self._endpoint_id = endpoint_id
        self._config = config

        self.enabled_sdkconfig_options: set[str] = set()
        self.global_includes: set[str] = set()

        self._cluster_configs: defaultdict[str, _ClusterConfig] = defaultdict(
            _ClusterConfig
        )

    async def register(self, var):
        cg.add(var.register_endpoint(self._endpoint_id))

        # Register device types.
        for conf_key, device_config in self._config.items():
            device_type = DEVICE_TYPES_BY_CONF_KEY.get(conf_key)
            if device_type:
                await self._register_device_type(device_type, device_config)

        # Register clusters that haven't already been created by device type registration.
        for cluster_name, cluster_config in self._cluster_configs.items():
            if not cluster_config.created:
                cluster = CLUSTERS_BY_NAME[cluster_name]
                self._register_cluster(cluster)

        # TODO: Register features that haven't already been enabled by cluster registration.

        # TODO: Register attributes that haven't already been created by cluster registration.

    async def _register_device_type(self, device_type: DeviceType, device_config: dict):
        """Registers a device type via the register_device_type method."""
        for cluster in device_type.server_clusters:
            # Enable all clusters and not only the enabled ones because esp_matter doesn't correctly guard endpoint compilation...
            self.enabled_sdkconfig_options.add(cluster.sdkconfig_option)
            if cluster.required:
                self._cluster_configs[cluster.name].created = True
                if cluster.name == "Binding":
                    # esp_matter doesn't create the binding cluster when adding a device type to an endpoint, even when
                    # the device type requires it so it must always be forcibly created when a device type needs it.
                    self._cluster_configs["Binding"].created = False

        # Register sensor attributes
        for sensor_attr in device_type.sensor_attributes:
            if sensor_id := device_config.get(sensor_attr.conf_key):
                await self._register_sensor_attribute(sensor_id, sensor_attr)

        # Register ESPHome entities
        if CONF_LIGHT_ID in device_config:
            light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
            cg.add(self._var.map_light_to_endpoint(light_, self._endpoint_id))

        # Register extra features
        for enabled_feature in device_config.get(CONF_FEATURES, ()):
            for cluster in device_type.server_clusters:
                if enabled_feature in (f.name for f in cluster.features):
                    self._cluster_configs[cluster.name].enabled_features[
                        enabled_feature
                    ] = True

        # Send device type registration to codegen
        register_device_type = self._var.register_device_type.template(
            cg.RawExpression(
                f"esp_matter::endpoint::{device_type.namespace}::config_t"
            ),
            cg.RawExpression(f"esp_matter::endpoint::{device_type.namespace}::add"),
        )
        device_type_config = self._make_device_type_config(device_type)
        cg.add(
            register_device_type(
                self._endpoint_id, device_type.namespace, device_type_config
            )
        )

    def _make_device_type_config(self, device_type: DeviceType):
        lines = [
            "[] {",
            f"esp_matter::endpoint::{device_type.namespace}::config_t config{{}};",
        ]

        # Configure cluster features
        for cluster in device_type.server_clusters:
            if not cluster.required:
                continue  # Non-required clusters must be created after the device_type
            enabled_features = []
            cluster_config = self._cluster_configs[cluster.name]
            for feature_name, enabled in cluster_config.enabled_features.items():
                if enabled:
                    enabled_features.append(feature_name)
            if enabled_features:
                features_by_name = {f.name: f for f in cluster.features}
                feature_flags = []
                for feature_name in enabled_features:
                    feature = features_by_name[feature_name]
                    feature_flags.append(
                        f"esp_matter::cluster::{cluster.espm_namespace}::feature::{feature.namespace}::get_id()"
                    )
                lines.append(
                    f"config.{cluster.espm_namespace}.feature_flags = {' | '.join(feature_flags)};"
                )

        lines.extend(("return config;", "}()"))
        return cg.RawExpression("\n".join(lines))

    async def _register_sensor_attribute(
        self, sensor_id: ID, sensor_attribute: SensorAttribute
    ):
        cluster = sensor_attribute.cluster
        attribute = sensor_attribute.attribute
        if cluster is None or attribute is None:
            raise cv.Invalid(
                f"sensor_attribute {sensor_attribute.conf_key} is not initialized"
            )

        self._cluster_configs[cluster.name].created |= False
        for feature_name in sensor_attribute.features:
            self._cluster_configs[cluster.name].enabled_features[feature_name] = True

        sensor = await cg.get_variable(sensor_id)
        converter = cg.RawExpression(
            f"esphome::matter::sensor_converter::{sensor_attribute.converter}"
        )
        if sensor_attribute.sensor_type is BinarySensor:
            register_binary_sensor_attribute = (
                self._var.register_binary_sensor_attribute(
                    sensor, self._endpoint_id, cluster.id, attribute.id, converter
                )
            )
            cg.add(register_binary_sensor_attribute)
        elif sensor_attribute.code_driven:
            self.global_includes.add(cluster.chip_include)
            cluster_type = cg.RawExpression(cluster.chip_fqn)
            value_type = cg.RawExpression(
                {
                    "int16s": "int16_t",
                    "int16u": "uint16_t",
                    "temperature": "int16_t",
                }[attribute.type]
            )
            setter = cg.RawExpression(f"&{cluster.chip_fqn}::SetMeasuredValue")
            register = self._var.register_code_driven_sensor_attribute.template(
                cluster_type, value_type, setter
            )
            cg.add(
                register(sensor, self._endpoint_id, cluster.id, attribute.id, converter)
            )
        else:
            register_sensor_attribute = self._var.register_sensor_attribute(
                sensor, self._endpoint_id, cluster.id, attribute.id, converter
            )
            cg.add(register_sensor_attribute)

    def _register_cluster(self, cluster: Cluster):
        """Most clusters are already created when adding a device type to an endpoint. _register_cluster should
        only be used for clusters that are optional to a device type and aren't already created.
        """
        cluster_ns = f"esp_matter::cluster::{cluster.espm_namespace}"

        # Make cluster config expression
        lines = ["[] {", f"{cluster_ns}::config_t config{{}};"]
        feature_flags = []
        features_by_name = {feature.name: feature for feature in cluster.features}
        for feature_name, enabled in self._cluster_configs[
            cluster.name
        ].enabled_features.items():
            if not enabled:
                continue
            feature = features_by_name.get(feature_name)
            if not feature:
                raise cv.Invalid(
                    f"Cluster {cluster.name} has no feature {feature_name}"
                )
            feature_flags.append(
                f"{cluster_ns}::feature::{feature.namespace}::get_id()"
            )
        if feature_flags:
            lines.append(f"config.feature_flags = {' | '.join(feature_flags)};")
        lines.append("return config;")
        lines.append("}()")
        config_expression = cg.RawExpression("\n".join(lines))

        cg.add(
            self._var.register_cluster(
                cg.TemplateArguments(
                    cluster.id,
                    cg.RawExpression(f"{cluster_ns}::config_t"),
                    cg.RawExpression(f"{cluster_ns}::create"),
                ),
                self._endpoint_id,
                cluster.name,
                config_expression,
            )
        )


async def register_endpoints(var, config: ConfigType):
    root_node = DEVICE_TYPES_BY_ID[22]
    global_includes = set()
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
        endpoint = Endpoint(var, endpoint_id, endpoint_config)
        await endpoint.register(var)
        global_includes.update(endpoint.global_includes)
        enabled_sdkconfig_clusters.update(endpoint.enabled_sdkconfig_options)

    # Set sdkconfig options to compile the correct clusters.
    for cluster in CLUSTERS:
        sdkconfig_option = cluster.sdkconfig_option
        add_idf_sdkconfig_option(
            sdkconfig_option, sdkconfig_option in enabled_sdkconfig_clusters
        )

    for global_include in global_includes:
        cg.add_global(cg.RawStatement(global_include), prepend=True)
