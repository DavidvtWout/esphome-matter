import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

import esphome.config_validation as cv
from esphome import automation
from esphome.components import light
from esphome.const import CONF_LIGHT_ID

from ..const import CONF_MAX_LEVEL, CONF_MIN_LEVEL, CONF_WITH_FEATURES
from ..util import maybe_empty
from .attributes import SENSOR_ATTRIBUTES, SensorAttribute
from .clusters import CLUSTERS_BY_ID, CLUSTERS_BY_NAME, Cluster, Feature
from .units import percentage

_LOGGER = logging.getLogger(__name__)


def _parse_cluster_include(data: dict) -> Cluster:
    cluster = CLUSTERS_BY_ID[data["id"]]
    required = data.get("required", False)
    mandatory_features = set()
    disallowed_features = set()
    for code, conformance in data.get("features", {}).items():
        if conformance == "mandatory":
            mandatory_features.add(code)
        elif conformance == "disallowed":
            disallowed_features.add(code)

    def _replace(f):
        if f.code in mandatory_features:
            return replace(f, mandatory=True)
        elif f.code in disallowed_features:
            return replace(f, disallowed=True)
        else:
            return f

    features = []
    choice_features = []
    for feature in cluster.features:
        features.append(_replace(feature))
    for choice in cluster.choice_features:
        new_choice_features = []
        for feature in choice.features:
            new_choice_features.append(_replace(feature))
        # Remove choice features if device type already solves the choice by enabling any of the choice features.
        if not any(feature.mandatory for feature in new_choice_features):
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

        # TODO: validate complex conform rules for features. The ensures that the user
        #  can't create invalid device_type configs that result in runtime errors.
        if self.get_features():
            # Features must be given in snake_case. e.g.: "average_measurement"
            schema[cv.Optional(CONF_WITH_FEATURES, default=list)] = cv.ensure_list(
                cv.one_of(*(feature.conf_key for feature in self.get_features()))
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

        # If a device type is a simple sensor with only a single sensor attribute, the config may be simplified from;
        #   temperature_sensor:
        #     temperature: sensor_id
        # to;
        #   temperature_sensor: sensor_id
        if len(self.sensor_attributes) == 1:
            sensor_attribute = self.sensor_attributes[0]
            schema = automation.maybe_conf(sensor_attribute.conf_key, schema)

        return schema

    def schema(self):
        # TODO: only maybe_empty if there are no clusters or features for which a mandatory choice must be made.
        return maybe_empty(self._schema())


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
