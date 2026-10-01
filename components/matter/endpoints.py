import logging
from collections import defaultdict
from dataclasses import dataclass, field

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import light
from esphome.components.binary_sensor import BinarySensor
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.components.sensor import Sensor
from esphome.config import Config
from esphome.const import CONF_ID, CONF_LIGHT_ID, CONF_RESTORE_MODE, CONF_TRIGGER_ID
from esphome.core import CORE, ID
from esphome.types import ConfigType

from .actions import get_attribute_from_config, get_event_from_config
from .const import *
from .data_model.attributes import Attribute, SensorAttribute, attribute_value_type
from .data_model.clusters import CLUSTERS, CLUSTERS_BY_NAME, Cluster
from .data_model.conformance import (
    ConformanceDisposition,
    ConformanceError,
    resolve_feature_requirements,
)
from .data_model.device_types import (
    DEVICE_TYPES,
    DEVICE_TYPES_BY_CONF_KEY,
    DEVICE_TYPES_BY_ID,
    DeviceType,
)
from .data_model.events import Event
from .types import MatterAttributeTrigger, MatterEndpointRef
from .util import iter_matter_actions, maybe_empty, snake_case

_LOGGER = logging.getLogger(__name__)


def _on_attribute_schema():
    options = {}
    for cluster in CLUSTERS:
        attributes = {}
        for attribute in cluster.attributes:
            if not attribute.server:
                continue
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
        for attribute in cluster.attributes:
            if not attribute.server:
                continue
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


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_CLUSTERS, default=dict): {
                cluster.schema_key: maybe_empty(cluster.schema())
                for cluster in CLUSTERS
            },
            # TODO: move on_attribute to clusters
            cv.Optional(CONF_ON_ATTRIBUTE): _on_attribute_schema(),
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
    def __init__(self, endpoint_id: int, config: dict):
        self._endpoint_id = endpoint_id
        self._config = config
        self.usages: list[tuple[Cluster, Attribute | Event]] = []
        self.enabled_sdkconfig_options: set[str] = set()
        self.global_includes: set[str] = set()
        self._cluster_configs: defaultdict[str, _ClusterConfig] = defaultdict(
            _ClusterConfig
        )
        self._device_types: list[DeviceType] = []
        self._light_variables = {}

    @property
    def endpoint_id(self) -> int:
        return self._endpoint_id

    @property
    def config(self) -> dict:
        return self._config

    def register_usage(self, cluster: Cluster, usage: Attribute | Event) -> None:
        self.usages.append((cluster, usage))

    def _cluster_state(self, cluster: Cluster):
        enabled_codes = set()
        cluster_present = False
        device_features = []

        explicit_cluster_config = self._config[CONF_CLUSTERS].get(
            snake_case(cluster.name)
        )
        if explicit_cluster_config is not None:
            cluster_present = True
            for feature_name in explicit_cluster_config.get(CONF_WITH_FEATURES, ()):
                feature = cluster.get_feature(feature_name)
                if feature is not None:
                    enabled_codes.add(feature.code)

        for config_key, device_config in self._config.items():
            device_type = DEVICE_TYPES_BY_CONF_KEY.get(config_key)
            if device_type is None:
                continue
            for device_cluster in device_type.server_clusters:
                if device_cluster.name != cluster.name:
                    continue
                cluster_present |= device_cluster.required
                device_features.extend(device_cluster.features)
            for feature_name in device_config.get(CONF_WITH_FEATURES, ()):
                feature = cluster.get_feature(feature_name)
                if feature is not None:
                    enabled_codes.add(feature.code)

        # A mandatory feature can make another conditional feature mandatory, so
        # evaluate the composed cluster/device-type conformance to a fixed point.
        changed = True
        while changed:
            changed = False
            for feature in device_features:
                if feature.conformance is None or feature.code in enabled_codes:
                    continue
                if (
                    feature.conformance.disposition(enabled_codes)
                    is ConformanceDisposition.MANDATORY
                ):
                    enabled_codes.add(feature.code)
                    changed = True

        disallowed_codes = {
            feature.code
            for feature in device_features
            if feature.conformance is not None
            and feature.conformance.disposition(enabled_codes)
            is ConformanceDisposition.DISALLOWED
        }

        return cluster_present, enabled_codes, disallowed_codes

    def resolve(self) -> None:
        usages_by_cluster = defaultdict(list)
        clusters_by_id = {}
        for cluster, usage in self.usages:
            clusters_by_id[cluster.id] = cluster
            if usage.conformance is not None:
                usages_by_cluster[cluster.id].append(usage)

        for cluster_name in self._config[CONF_CLUSTERS]:
            cluster = CLUSTERS_BY_NAME[cluster_name]
            clusters_by_id[cluster.id] = cluster

        for config_key, device_config in self._config.items():
            device_type = DEVICE_TYPES_BY_CONF_KEY.get(config_key)
            if device_type is None:
                continue
            configured_features = device_config.get(CONF_WITH_FEATURES, ())
            for cluster in device_type.server_clusters:
                if cluster.required or any(
                    cluster.get_feature(feature_name) is not None
                    for feature_name in configured_features
                ):
                    clusters_by_id[cluster.id] = cluster

        for cluster_id, cluster in clusters_by_id.items():
            usages = usages_by_cluster[cluster_id]
            cluster_present, enabled_codes, disallowed_codes = self._cluster_state(
                cluster
            )
            if not cluster_present:
                usage_names = ", ".join(usage.name for usage in usages)
                raise cv.Invalid(
                    f"Matter endpoint {self._endpoint_id} does not contain the "
                    f"{cluster.name} cluster required by: {usage_names}"
                )

            feature_conformance = {
                feature.code: feature.conformance for feature in cluster.features
            }
            try:
                inferred_codes = resolve_feature_requirements(
                    [usage.conformance for usage in usages],
                    feature_conformance,
                    enabled_codes,
                )
            except ConformanceError as err:
                usage_names = ", ".join(usage.name for usage in usages)
                raise cv.Invalid(
                    f"Cannot resolve features for endpoint {self._endpoint_id} "
                    f"from {usage_names}: {err}"
                ) from err

            invalid_codes = (enabled_codes | inferred_codes) & disallowed_codes
            if invalid_codes:
                names = ", ".join(
                    cluster.get_feature(code).conf_key for code in sorted(invalid_codes)
                )
                raise cv.Invalid(
                    f"Matter elements on endpoint {self._endpoint_id} require "
                    f"features disallowed by its device type: {names}"
                )

            resulting_codes = enabled_codes | inferred_codes
            choices = defaultdict(list)
            for feature in cluster.features:
                if feature.conformance is not None and feature.conformance.choice:
                    choices[feature.conformance.choice].append(feature)
            for choice, features in choices.items():
                selected = [
                    feature.conf_key
                    for feature in features
                    if feature.code in resulting_codes
                ]
                if choice.max is not None and len(selected) > choice.max:
                    raise cv.Invalid(
                        f"Matter endpoint {self._endpoint_id} selects conflicting "
                        f"{cluster.name} features: {', '.join(selected)}"
                    )

            cluster_config = self._cluster_configs[cluster.name]
            for code in inferred_codes:
                cluster_config.enabled_features[cluster.get_feature(code).name] = True

    async def register(self, var):
        """Registers an endpoint using the register_endpoint function in matter_component.h.

        Using ESPHome codegen, a function is built and registered that adds device types and clusters to an endpoint.
        These functions are called just before Matter is started.

        Sadly, device type and cluster creation is quite complicated and not easily generalizable for all device types.
        For example, most optional clusters must be created after the device type has been created. However, the
        Electrical Sensor is an exception to this rule. The matter spec defines that this device type must have at least
        one of the "ElectricalEnergyMeasurement" or "ElectricalPowerMeasurement" clusters. esp-matter enforces this
        by adding a "with_clusters" argument to the electrical_sensor config.

        Cluster creation also often requires a custom config to be created successfully. This config is either passed
        directly to the create function of the cluster or to the device type config if the cluster is mandatory.

        Because of all of these complications, the endpoint creation process is a bit of a mess now. The mandatory
        clusters of a device type are always created by esp-matter (except for the binding cluster...).
        The same is true for cluster attributes. Mandatory attributes are always created, some optional attributes are
        created through config options, and some are created after the cluster.
        This whole process could have easily been made more generalizable by esp-matter, but they decided not to...

        In the future I might bypass esp-matter entirely for endpoint creation and use connectedhomeip directly.
        However, this also brings challenges and isn't entirely generalizable either. For example, the concentration
        measurement clusters use a different namespace naming than most other clusters.
        """

        # Collect the complete endpoint structure before emitting its build callback.
        for conf_key, device_config in self._config.items():
            device_type = DEVICE_TYPES_BY_CONF_KEY.get(conf_key)
            if device_type:
                await self._configure_device_type(var, device_type, device_config)

        for cluster_name, config in self._config[CONF_CLUSTERS].items():
            cluster = CLUSTERS_BY_NAME[cluster_name]
            self.enabled_sdkconfig_options.add(cluster.sdkconfig_option)
            cluster_config = self._cluster_configs[cluster_name]
            for configured_feature in config.get(CONF_WITH_FEATURES, ()):
                if feature := cluster.get_feature(configured_feature):
                    cluster_config.enabled_features[feature.name] = True

        await self._register_attribute_automations(var)

        build_fn = cg.RawExpression(self._make_build_callback())
        cg.add(var.register_endpoint(self._endpoint_id, build_fn))

    async def _register_attribute_automations(self, var):
        configured_clusters = self._config.get(CONF_ON_ATTRIBUTE, {})
        for cluster in CLUSTERS:
            cluster_key = snake_case(cluster.name)
            cluster_config = configured_clusters.get(cluster_key, {})
            for attribute in cluster.attributes:
                if not attribute.server:
                    continue
                if attribute.name is None:
                    continue
                value_type = attribute_value_type(attribute)
                if value_type is None:
                    continue
                attribute_key = snake_case(attribute.name)
                configurations = [
                    *cluster_config.get(attribute_key, []),
                    *configured_clusters.get(f"{cluster_key}.{attribute_key}", []),
                ]
                for conf in configurations:
                    trigger = cg.new_Pvariable(
                        conf[CONF_TRIGGER_ID],
                        var,
                        self._endpoint_id,
                        cluster.id,
                        attribute.id,
                    )
                    cg.add(var.register_attribute_trigger(trigger))
                    await automation.build_automation(
                        trigger, [(value_type, "value")], conf
                    )

    async def _configure_device_type(
        self, var, device_type: DeviceType, device_config: dict
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
                await self._register_sensor_attribute(var, sensor_id, sensor_attr)

        # Register ESPHome entities
        if CONF_LIGHT_ID in device_config:
            light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
            self._light_variables[device_type.name] = light_
            cg.add(var.register_light(light_, self._endpoint_id))

        # Register extra features
        for enabled_feature in device_config.get(CONF_WITH_FEATURES, ()):
            for cluster in device_type.server_clusters:
                if feature := cluster.get_feature(enabled_feature):
                    cluster_config = self._cluster_configs[cluster.name]
                    cluster_config.enabled_features[feature.name] = True

    def _make_device_type_lines(self, device_type: DeviceType, index: int):
        config_var = f"device_config_{index}"
        lines = [
            f"esp_matter::endpoint::{device_type.namespace}::config_t {config_var}{{}};"
        ]

        device_config = self._config[device_type.conf_key]
        if min_level := device_config.get(CONF_MIN_LEVEL):
            lines.append(f"{config_var}.level_control.min_level = {min_level};")
        if max_level := device_config.get(CONF_MAX_LEVEL):
            lines.append(f"{config_var}.level_control.max_level = {max_level};")

        if device_type.name in ("color_temperature_light", "extended_color_light"):
            light = self._light_variables.get(device_type.name)
            if light is not None:
                self.global_includes.add(
                    '#include "esphome/components/matter/matter_conversions.h"'
                )
                traits_var = f"light_traits_{index}"
                lines.extend(
                    (
                        f"auto {traits_var} = {light}->get_traits();",
                        f"{config_var}.color_control_color_temperature.color_temp_physical_min_mireds = "
                        f"esphome::matter::conversion::to_matter::color_temperature({traits_var}.get_min_mireds());",
                        f"{config_var}.color_control_color_temperature.color_temp_physical_max_mireds = "
                        f"esphome::matter::conversion::to_matter::color_temperature({traits_var}.get_max_mireds());",
                    )
                )

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
                if feature.conformance is not None and feature.conformance.choice:
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
        self, var, sensor_id: ID, sensor_attribute: SensorAttribute
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
            f"esphome::matter::conversion::{sensor_attribute.converter}"
        )
        if sensor_attribute.sensor_type is BinarySensor:
            args = [sensor, self._endpoint_id, cluster.id, attribute.id, converter]
            if sensor_attribute.code_driven:
                self.global_includes.add(cluster.chip_include)
                args.append(
                    cg.RawExpression("esphome::matter::update_boolean_state_attribute")
                )
            cg.add(var.register_binary_sensor_attribute(*args))
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
            register = var.register_code_driven_sensor_attribute.template(
                cluster_type, value_type, setter
            )
            cg.add(
                register(sensor, self._endpoint_id, cluster.id, attribute.id, converter)
            )
        else:
            register_sensor_attribute = var.register_sensor_attribute(
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
        """ """
        lines = ["[](esp_matter::endpoint_t *endpoint) -> bool {"]

        for index, device_type in enumerate(self._device_types):
            lines.extend(self._make_device_type_lines(device_type, index))

        for cluster_name, cluster_config in self._cluster_configs.items():
            if not cluster_config.created:
                lines.extend(self._make_cluster_lines(CLUSTERS_BY_NAME[cluster_name]))

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
                and (
                    features_by_name[feature_name].conformance is None
                    or features_by_name[feature_name].conformance.choice is None
                )
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


class EndpointRegistry:
    def __init__(self):
        self._endpoints: list[Endpoint] = []
        self._lookup: dict[int | ID, Endpoint] = {}

    def register(self, endpoint: Endpoint):
        self._endpoints.append(endpoint)
        self._lookup[endpoint.endpoint_id] = endpoint
        self._lookup[endpoint.config[CONF_ID]] = endpoint

    def lookup(self, endpoint_reference: int | ID) -> Endpoint:
        endpoint = self._lookup.get(endpoint_reference)
        if endpoint is None:
            raise cv.Invalid(f"Unknown Matter endpoint '{endpoint_reference}'")
        return endpoint

    def __iter__(self):
        return iter(self._endpoints)


def build_endpoints(matter_config: dict, full_config: Config) -> EndpointRegistry:
    """During validation an endpoint registry is built and stored in CORE.data["matter"]["endpoints"]."""
    endpoints = EndpointRegistry()
    for endpoint_id, endpoint_config in matter_config[CONF_ENDPOINTS].items():
        endpoints.register(Endpoint(endpoint_id, endpoint_config))

    # Register matter actions that might require specific features to the endpoints.
    for action_type, action in iter_matter_actions(full_config):
        if action_type not in ("matter.send_event", "matter.set_attribute"):
            continue
        endpoint = endpoints.lookup(action[CONF_ENDPOINT])
        if action_type == "matter.send_event":
            cluster, event = get_event_from_config(action)
            endpoint.register_usage(cluster, event)
        else:
            cluster, attribute = get_attribute_from_config(action)
            endpoint.register_usage(cluster, attribute)

    for endpoint in endpoints:
        endpoint.resolve()

    CORE.data.setdefault(CONF_MATTER, {})[CONF_ENDPOINTS] = endpoints
    return endpoints


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

    for endpoint in CORE.data[CONF_MATTER][CONF_ENDPOINTS]:
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
