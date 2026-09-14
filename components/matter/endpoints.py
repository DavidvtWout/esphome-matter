import logging
from collections import defaultdict
from dataclasses import dataclass, field

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components.binary_sensor import BinarySensor
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.components.sensor import Sensor
from esphome.const import CONF_LIGHT_ID, CONF_TRIGGER_ID
from esphome.core import ID
from esphome.types import ConfigType

from .const import *
from .data_model.attributes import SensorAttribute, attribute_value_type
from .data_model.clusters import CLUSTERS, CLUSTERS_BY_NAME, Cluster
from .data_model.device_types import (
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    DeviceType,
)
from .types import MatterAttributeTrigger, MatterEndpointRef
from .util import snake_case

_LOGGER = logging.getLogger(__name__)


def _on_attribute_schema():
    options = {}
    for cluster in CLUSTERS:
        attributes = {}
        for attribute in cluster.server_attributes:
            if attribute.name is None:
                continue
            value_type = attribute_value_type(attribute)
            trigger_schema = {}
            if value_type is not None:
                trigger_schema[cv.GenerateID(CONF_TRIGGER_ID)] = cv.declare_id(
                    MatterAttributeTrigger.template(value_type)
                )
            attribute_key = snake_case(attribute.name)
            automation_schema = automation.validate_automation(trigger_schema)
            attributes[cv.Optional(attribute_key)] = automation_schema
            options[cv.Optional(f"{snake_case(cluster.name)}.{attribute_key}")] = (
                automation_schema
            )
        if attributes:
            options[cv.Optional(snake_case(cluster.name))] = cv.Schema(attributes)
    return cv.Schema(options)


def _validate_on_attribute_forms(config):
    configured = config.get(CONF_ON_ATTRIBUTE, {})
    for cluster in CLUSTERS:
        cluster_key = snake_case(cluster.name)
        nested = configured.get(cluster_key, {})
        for attribute in cluster.server_attributes:
            if attribute.name is None:
                continue
            attribute_key = snake_case(attribute.name)
            short_key = f"{cluster_key}.{attribute_key}"
            if attribute_key in nested and short_key in configured:
                raise cv.Invalid(
                    f"Matter attribute {short_key} cannot be configured in both "
                    "nested and short form"
                )
    return config


ON_ATTRIBUTE_SCHEMA = _on_attribute_schema()


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_EXTRA_CLUSTERS, default=list): cv.ensure_list(
                cv.one_of(*(cluster.name for cluster in CLUSTERS))
            ),
            cv.Optional(CONF_ON_ATTRIBUTE): ON_ATTRIBUTE_SCHEMA,
        }
        | {device_type.schema_key: device_type.schema() for device_type in DEVICE_TYPES}
    ),
    _validate_on_attribute_forms,
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
        self._device_types: list[DeviceType] = []

    async def register(self, var):
        # Collect the complete endpoint structure before emitting its build callback.
        for conf_key, device_config in self._config.items():
            device_type = DEVICE_TYPES_BY_CONF_KEY.get(conf_key)
            if device_type:
                await self._configure_device_type(device_type, device_config)

        for cluster_name in self._config[CONF_EXTRA_CLUSTERS]:
            cluster = CLUSTERS_BY_NAME[cluster_name]
            self.enabled_sdkconfig_options.add(cluster.sdkconfig_option)
            self._cluster_configs.setdefault(cluster_name, _ClusterConfig())

        await self._register_attribute_automations()

        cg.add(
            var.register_endpoint(
                self._endpoint_id, cg.RawExpression(self._make_build_callback())
            )
        )

    async def _register_attribute_automations(self):
        configured_clusters = self._config.get(CONF_ON_ATTRIBUTE, {})
        for cluster in CLUSTERS:
            cluster_config = configured_clusters.get(snake_case(cluster.name), {})
            if not cluster_config:
                continue
            for attribute in cluster.server_attributes:
                if attribute.name is None:
                    continue
                value_type = attribute_value_type(attribute)
                if value_type is None:
                    continue
                attribute_key = snake_case(attribute.name)
                configurations = [
                    *cluster_config.get(attribute_key, []),
                    *configured_clusters.get(
                        f"{snake_case(cluster.name)}.{attribute_key}", []
                    ),
                ]
                for conf in configurations:
                    trigger = cg.new_Pvariable(
                        conf[CONF_TRIGGER_ID],
                        self._var,
                        self._endpoint_id,
                        cluster.id,
                        attribute.id,
                    )
                    cg.add(self._var.register_attribute_trigger(trigger))
                    await automation.build_automation(
                        trigger, [(value_type, "value")], conf
                    )

    async def _configure_device_type(
        self, device_type: DeviceType, device_config: dict
    ):
        """Collect the endpoint structure and register its runtime entity mappings."""
        self._device_types.append(device_type)

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
                cluster_config = self._cluster_configs[cluster.name]
                if enabled_feature in (f.name for f in cluster.features):
                    cluster_config.enabled_features[enabled_feature] = True

    def _make_device_type_lines(self, device_type: DeviceType, index: int):
        config_var = f"device_config_{index}"
        lines = [
            f"esp_matter::endpoint::{device_type.namespace}::config_t {config_var}{{}};"
        ]

        # Configure cluster features
        for cluster in device_type.server_clusters:
            if not cluster.required:
                continue  # Non-required clusters must be created after the device_type
            cluster_config = self._cluster_configs[cluster.name]
            features_by_name = {f.name: f for f in cluster.features}
            feature_flags = []
            for feature_name, enabled in cluster_config.enabled_features.items():
                if not enabled:
                    continue
                feature = features_by_name[feature_name]
                if cluster.is_choice_feature(feature):
                    feature_flags.append(
                        f"esp_matter::cluster::{cluster.espm_namespace}::feature::{feature.namespace}::get_id()"
                    )
            if feature_flags:
                lines.append(
                    f"{config_var}.{cluster.espm_namespace}.feature_flags = {' | '.join(feature_flags)};"
                )

        lines.extend(
            (
                f"if (esp_matter::endpoint::{device_type.namespace}::add(endpoint, &{config_var}) != ESP_OK)",
                "  return false;",
            )
        )
        return lines

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
            args = [sensor, self._endpoint_id, cluster.id, attribute.id, converter]
            if sensor_attribute.code_driven:
                self.global_includes.add(cluster.chip_include)
                args.append(
                    cg.RawExpression("esphome::matter::update_boolean_state_attribute")
                )
            cg.add(self._var.register_binary_sensor_attribute(*args))
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

    def _make_cluster_lines(self, cluster: Cluster):
        """Build lines for a cluster not created by a device type."""
        cluster_ns = f"esp_matter::cluster::{cluster.espm_namespace}"

        config_var = f"{cluster.espm_namespace}_config"
        lines = [f"{cluster_ns}::config_t {config_var}{{}};"]
        feature_flags = []
        features_by_name = {feature.name: feature for feature in cluster.features}
        cluster_config = self._cluster_configs[cluster.name]
        for feature_name, enabled in cluster_config.enabled_features.items():
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
            lines.append(f"{config_var}.feature_flags = {' | '.join(feature_flags)};")
        lines.extend(
            (
                f"if ({cluster_ns}::create(endpoint, &{config_var}, esp_matter::CLUSTER_FLAG_SERVER) == nullptr)",
                "  return false;",
            )
        )
        return lines

    def _make_build_callback(self) -> str:
        lines = ["[](esp_matter::endpoint_t *endpoint) -> bool {"]

        for index, device_type in enumerate(self._device_types):
            lines.extend(self._make_device_type_lines(device_type, index))

        extra_clusters = [
            CLUSTERS_BY_NAME[cluster_name]
            for cluster_name, cluster_config in self._cluster_configs.items()
            if not cluster_config.created
        ]
        for cluster in extra_clusters:
            lines.extend(self._make_cluster_lines(cluster))

        # Choice features must be present in the config used to create their
        # cluster. Other features on device-type-created clusters are added
        # directly after the device type has created the cluster.
        for cluster_name, cluster_config in self._cluster_configs.items():
            if not cluster_config.created:
                continue
            cluster = CLUSTERS_BY_NAME[cluster_name]
            features_by_name = {feature.name: feature for feature in cluster.features}
            direct_features = [
                features_by_name[feature_name]
                for feature_name, enabled in cluster_config.enabled_features.items()
                if enabled
                and feature_name in features_by_name
                and not cluster.is_choice_feature(features_by_name[feature_name])
            ]
            if not direct_features:
                continue
            cluster_var = f"{cluster.espm_namespace}_cluster"
            lines.extend(
                (
                    f"auto *{cluster_var} = esp_matter::cluster::get(endpoint, {cluster.id});",
                    f"if ({cluster_var} == nullptr)",
                    "  return false;",
                )
            )
            for feature in direct_features:
                lines.extend(
                    (
                        f"if (esphome::matter::add_feature({cluster_var}, esp_matter::cluster::{cluster.espm_namespace}::feature::{feature.namespace}::add) != ESP_OK)",
                        "  return false;",
                    )
                )

        lines.extend(("return true;", "}"))
        return "\n".join(lines)


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
