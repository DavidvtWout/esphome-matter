import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar

import esphome.config_validation as cv
from esphome import automation
from esphome.components import cover, light
from esphome.const import CONF_LIGHT_ID

from ..const import (
    CONF_COVER_ID,
    CONF_END_PRODUCT_TYPE,
    CONF_FEATURES,
    CONF_MAX_LEVEL,
    CONF_MIN_LEVEL,
)
from ..util import maybe_empty
from .attributes import SENSOR_ATTRIBUTES, SensorAttribute
from .clusters import CLUSTERS_BY_ID, CLUSTERS_BY_NAME, Cluster, Feature
from .units import percentage

_LOGGER = logging.getLogger(__name__)


def _parse_cluster_include(data: dict) -> Cluster:
    cluster = CLUSTERS_BY_ID[data["id"]]
    required = data.get("required", False)
    enabled_features = data.get("features", ())

    features = []
    choice_features = []
    for feature in cluster.features:
        if feature.code in enabled_features:
            feature = replace(feature, enabled=True)
        features.append(feature)
    for choice in cluster.choice_features:
        new_choice_features = []
        for feature in choice.features:
            if feature.code in enabled_features:
                feature = replace(feature, enabled=True)
            new_choice_features.append(feature)
        # Remove choice features if device type already solves the choice by enabling any of the choice features.
        if choice.max != 1 or not any(
            feature.enabled for feature in new_choice_features
        ):
            choice_features.append(replace(choice, features=tuple(new_choice_features)))
        else:
            features.extend(new_choice_features)

    # TODO: also update attribute and command info
    return replace(
        cluster,
        required=required,
        features=tuple(features),
        choice_features=tuple(choice_features),
    )


@dataclass(frozen=True, slots=True)
class DeviceType:
    id: int
    name: str  # snake_case
    server_clusters: tuple[Cluster, ...] = ()
    sensor_attributes: tuple[SensorAttribute, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        server_clusters = tuple(
            [_parse_cluster_include(c) for c in data["server_clusters"]]
        )
        sensor_attributes = []
        for cluster in server_clusters:
            for attribute_name, sensor_attribute in SENSOR_ATTRIBUTES.get(
                cluster.name, {}
            ).items():
                sensor_attributes.append(
                    replace(
                        sensor_attribute,
                        cluster=cluster,
                        attribute=cluster.get_attribute(attribute_name),
                    )
                )

        return cls(
            name=data["name"],
            id=data["id"],
            server_clusters=server_clusters,
            sensor_attributes=tuple(sensor_attributes),
        )

    @property
    def namespace(self) -> str:
        """esp_matter::endpoints::<device_type>"""
        return self.name

    @property
    def conf_key(self) -> str:
        return self.name

    def get_features(self) -> set[Feature]:
        """Get all features that the clusters of this device type supports."""
        features = set()
        for cluster in self.server_clusters:
            features.update(cluster.features)
        return features

    def configured_server_clusters(self, config: dict) -> set[Cluster]:
        clusters = {cluster for cluster in self.server_clusters if cluster.required}
        for sensor_attribute in self.sensor_attributes:
            if config.get(sensor_attribute.conf_key) is not None:
                clusters.add(CLUSTERS_BY_NAME[sensor_attribute.cluster.name])
        return clusters

    # TODO: fix this mess...
    # def implicit_features(self, config: dict) -> set[str]:
    #     features = set()
    #     configured_cluster_ids = {
    #         cluster.id for cluster in self.configured_server_clusters(config)
    #     }
    #     for cluster in self.server_clusters:
    #         if cluster.id not in configured_cluster_ids:
    #             continue
    #         features.update(
    #             feature.name
    #             for feature in cluster.features
    #             if feature.code in cluster.enabled_features
    #         )
    #     for sensor_attribute in self.sensor_attributes:
    #         if config.get(sensor_attribute.conf_key) is not None:
    #             features.update(sensor_attribute.features)
    #     return features

    def _validate_features(self, config: dict) -> dict:
        # enabled_features = list(config.get(CONF_FEATURES, ()))
        # for feature in sorted(self.implicit_features(config)):
        #     if feature not in enabled_features:
        #         enabled_features.append(feature)
        #
        # enabled_feature_set = frozenset(enabled_features)
        # for cluster in self.configured_server_clusters(config):
        #     for item in cluster.features:
        #         if not isinstance(item, FeatureChoice):
        #             continue
        #         selected = enabled_feature_set.intersection(
        #             feature.name for feature in item.features
        #         )
        #         if len(selected) < item.min:
        #             choices = ", ".join(feature.name for feature in item.features)
        #             raise cv.Invalid(
        #                 f"Cluster {cluster.name} requires at least {item.min} of "
        #                 f"these features: {choices}"
        #             )
        #         if item.max is not None and len(selected) > item.max:
        #             choices = ", ".join(feature.name for feature in item.features)
        #             raise cv.Invalid(
        #                 f"Cluster {cluster.name} allows at most {item.max} of "
        #                 f"these features: {choices}"
        #             )

        # if enabled_features:
        #     config[CONF_FEATURES] = enabled_features
        return config

    @property
    def schema_key(self):
        return cv.Optional(self.conf_key)

    def _schema(self):
        schema = {
            cv.Optional(sensor_attribute.conf_key): cv.use_id(
                sensor_attribute.sensor_type
            )
            for sensor_attribute in self.sensor_attributes
        }

        if features := self.get_features():
            schema[cv.Optional(CONF_FEATURES)] = cv.ensure_list(
                cv.one_of(*(feature.name for feature in features))
            )

        # TODO: replace with something better
        if self.name.endswith("light"):
            schema[cv.Optional(CONF_LIGHT_ID)] = cv.use_id(light.LightState)

        if self.name.endswith("light") and any(
            cluster.name == "LevelControl" and cluster.required
            for cluster in self.server_clusters
        ):
            level = cv.All(percentage(), cv.int_range(min=1, max=254))
            schema[cv.Optional(CONF_MIN_LEVEL, default=1)] = level
            schema[cv.Optional(CONF_MAX_LEVEL, default=254)] = level

        # If a device type is a simple sensor with only a single sensor attribute the config may be simplified from;
        #   temperature_sensor:
        #     temperature: sensor_id
        # to;
        #   temperature_sensor: sensor_id
        if len(self.sensor_attributes) == 1:
            sensor_attribute = self.sensor_attributes[0]
            schema = automation.maybe_conf(sensor_attribute.conf_key, schema)

        return schema

    def config_lines(self, config: dict, config_var: str) -> list[str]:
        """Return device-type-specific C++ config assignments."""
        return []

    def config_constructor_args(self, config: dict) -> list[str]:
        """Return arguments for the esp-matter device config constructor."""
        return []

    def schema(self):
        # TODO: only maybe_empty if there are no clusters or features for which a mandatory choice must be made.
        return cv.All(maybe_empty(self._schema()), self._validate_features)


class WindowCoveringDeviceType(DeviceType):
    """Window Covering schema for an optional ESPHome cover mapping.

    Unmapped Window Covering endpoints retain the generic schema. A mapped
    endpoint is deliberately narrower: ESPHome covers expose normalized
    percentage positions, not absolute physical measurements.
    """

    _LIFT_FEATURES = frozenset(("Lift", "PositionAwareLift"))
    _VENETIAN_FEATURES = _LIFT_FEATURES | frozenset(
        ("Tilt", "PositionAwareTilt")
    )
    _END_PRODUCT_TYPES: ClassVar[dict[str, int]] = {
        "roller_shade": 0x00,
        "interior_venetian_blind": 0x0C,
        "exterior_venetian_blind": 0x0D,
    }

    def _schema(self):
        schema = super()._schema()
        schema[cv.Optional(CONF_COVER_ID)] = cv.use_id(cover.Cover)
        schema[cv.Optional(CONF_END_PRODUCT_TYPE)] = cv.one_of(
            *self._END_PRODUCT_TYPES, lower=True
        )
        return schema

    def _validate_features(self, config: dict) -> dict:
        config = super()._validate_features(config)
        features = frozenset(config.get(CONF_FEATURES, ()))

        dependencies = {
            "PositionAwareLift": "Lift",
            "PositionAwareTilt": "Tilt",
        }
        for feature, required_feature in dependencies.items():
            if feature in features and required_feature not in features:
                raise cv.Invalid(
                    f"Window Covering feature {feature} requires {required_feature}"
                )

        if CONF_COVER_ID not in config:
            return config

        if "AbsolutePosition" in features:
            raise cv.Invalid(
                "Mapped ESPHome covers use normalized percentage positions; "
                "AbsolutePosition is not supported"
            )

        supported = (self._LIFT_FEATURES, self._VENETIAN_FEATURES)
        if features not in supported:
            raise cv.Invalid(
                "A mapped Window Covering must enable either Lift + "
                "PositionAwareLift, or Lift + PositionAwareLift + Tilt + "
                "PositionAwareTilt"
            )

        end_product_type = config.get(CONF_END_PRODUCT_TYPE)
        if features == self._LIFT_FEATURES:
            if end_product_type not in (None, "roller_shade"):
                raise cv.Invalid(
                    "A lift-only mapped Window Covering must use "
                    "end_product_type: roller_shade"
                )
            config[CONF_END_PRODUCT_TYPE] = "roller_shade"
        else:
            if end_product_type is None:
                config[CONF_END_PRODUCT_TYPE] = "interior_venetian_blind"
            elif end_product_type == "roller_shade":
                raise cv.Invalid(
                    "A lift-and-tilt mapped Window Covering must use an "
                    "interior or exterior Venetian blind end product type"
                )

        return config

    def config_lines(self, config: dict, config_var: str) -> list[str]:
        if CONF_COVER_ID not in config:
            return []

        features = frozenset(config[CONF_FEATURES])
        # Matter Window Covering Type: RollerShade=0x00,
        # TiltBlindLiftAndTilt=0x08.
        window_covering_type = (
            0x08 if features == self._VENETIAN_FEATURES else 0x00
        )
        return [
            f"{config_var}.window_covering.type = 0x{window_covering_type:02X};",
        ]

    def config_constructor_args(self, config: dict) -> list[str]:
        if CONF_COVER_ID not in config:
            return []
        end_product_type = self._END_PRODUCT_TYPES[config[CONF_END_PRODUCT_TYPE]]
        return [f"0x{end_product_type:02X}"]


# class ElectricalSensor(DeviceType):
#     def _schema(self):
#         schema = DeviceType._schema(self)
#         schema[cv.Required("with_clusters")] = cv.All(
#             cv.ensure_list(
#                 cv.one_of("ElectricalEnergyMeasurement", "ElectricalPowerMeasurement")
#             ),
#             cv.Length(min=1),
#         )
#         return schema
#
#     def _config_expression(self, config: dict):
#         namespace = f"esp_matter::endpoint::{self.namespace}"
#         lines = ["[] {", f"{namespace}::config_t config{{}};"]
#         lines.extend(self._feature_config_lines(config))
#         for cluster_name in config["with_clusters"]:
#             lines.append(f"config.with_{snake_case(cluster_name)}();")
#         lines.extend(("return config;", "}()"))
#         return cg.RawExpression("\n".join(lines))
#
#     def configured_server_clusters(self, config: dict) -> set[Cluster]:
#         clusters = DeviceType.configured_server_clusters(self, config)
#         clusters.update(
#             CLUSTERS_BY_NAME[cluster_name] for cluster_name in config["with_clusters"]
#         )
#         return clusters
#
#     def register(self, var, endpoint_id: int, config: dict) -> set[Cluster]:
#         created_clusters = DeviceType.register(self, var, endpoint_id, config)
#         # esp_matter is written by idiots and doesn't properly guard cluster compilation...
#         for cluster_name in (
#             "electrical_energy_measurement",
#             "electrical_power_measurement",
#         ):
#             created_clusters.add(CLUSTERS_BY_CONF_KEY[cluster_name])
#         return created_clusters


DEVICE_TYPE_OVERRIDES = {
    "window_covering": WindowCoveringDeviceType,
    # "electrical_sensor": ElectricalSensor,
}


def _load_device_types(
    device_types_file: Path = Path(__file__).resolve().parent / "device_types.json",
) -> tuple[DeviceType, ...]:
    device_types: list[DeviceType] = []

    with open(device_types_file, "r") as file:
        contents = json.load(file)

    for device_type_data in contents:
        device_type_class = DEVICE_TYPE_OVERRIDES.get(
            device_type_data["name"], DeviceType
        )
        device_types.append(device_type_class.from_dict(device_type_data))

    return tuple(device_types)


DEVICE_TYPES: tuple[DeviceType, ...] = _load_device_types()
DEVICE_TYPES_BY_ID: dict[int, DeviceType] = {
    device_type.id: device_type for device_type in DEVICE_TYPES
}
DEVICE_TYPES_BY_CONF_KEY: dict[str, DeviceType] = {
    device_type.conf_key: device_type for device_type in DEVICE_TYPES
}
