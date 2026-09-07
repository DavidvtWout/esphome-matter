import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import light
from esphome.const import CONF_LIGHT_ID

from ..util import maybe_empty, snake_case
from .attributes import SENSOR_ATTRIBUTES, Attribute, SensorAttribute
from .clusters import CLUSTERS_BY_CONF_KEY, CLUSTERS_BY_ID, CLUSTERS_BY_NAME, Cluster

_LOGGER = logging.getLogger(__name__)


@dataclass
class _ClusterInclude:
    included_cluster: Cluster
    required: bool
    feature_codes: tuple[str, ...] = ()
    required_attribute_names: tuple[str, ...] = ()  # By "define" value
    required_command_names: tuple[str, ...] = ()  # By CamelCase name

    @classmethod
    def from_dict(cls, data: dict):
        cluster = CLUSTERS_BY_ID[data["id"]]
        return cls(
            included_cluster=cluster,
            required=data.get("required", False),
            feature_codes=data.get("features", ()),
            required_attribute_names=data.get("required_attributes", ()),
            required_command_names=data.get("required_commands", ()),
        )

    @property
    def cluster(self) -> Cluster:
        # TODO: also update feature, attribute, command info
        return replace(self.included_cluster, required=self.required)

    @property
    def server_attributes(self) -> tuple[Attribute, ...]:
        attrs = []
        for attr in self.cluster.server_attributes:
            if attr.optional and attr.define in self.required_attribute_names:
                attrs.append(replace(attr, optional=False))
            else:
                attrs.append(attr)
        return tuple(attrs)

    @property
    def client_attributes(self) -> tuple[Attribute, ...]:
        attrs = []
        for attr in self.cluster.client_attributes:
            if attr.optional and attr.define in self.required_attribute_names:
                attrs.append(replace(attr, optional=False))
            else:
                attrs.append(attr)
        return tuple(attrs)


@dataclass(frozen=True, slots=True)
class DeviceType:
    id: int
    name: str  # snake_case
    revision: int
    _server_cluster_includes: tuple[_ClusterInclude, ...] = ()
    _client_cluster_includes: tuple[_ClusterInclude, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            id=data["id"],
            revision=data["revision"],
            _server_cluster_includes=tuple(
                [_ClusterInclude.from_dict(c) for c in data["server_clusters"]]
            ),
            _client_cluster_includes=tuple(
                [_ClusterInclude.from_dict(c) for c in data["client_clusters"]]
            ),
        )

    @property
    def server_clusters(self) -> tuple[Cluster, ...]:
        return tuple(include.cluster for include in self._server_cluster_includes)

    @property
    def client_clusters(self) -> tuple[Cluster, ...]:
        return tuple(include.cluster for include in self._client_cluster_includes)

    @property
    def namespace(self) -> str:
        return self.name

    @property
    def conf_key(self) -> str:
        return self.name

    @property
    def sensor_attributes(self) -> tuple[tuple[str, str, SensorAttribute], ...]:
        sensor_attributes = []
        for cluster in self.server_clusters:
            for attribute_name, sensor_attribute in SENSOR_ATTRIBUTES.get(
                cluster.camel_case_name, {}
            ).items():
                sensor_attributes.append(
                    (cluster.camel_case_name, attribute_name, sensor_attribute)
                )
        return tuple(sensor_attributes)

    @property
    def schema_key(self):
        return cv.Optional(self.conf_key)

    def _schema(self):
        sensor_attributes: dict[str, SensorAttribute] = {}
        for _, _, sensor_attribute in self.sensor_attributes:
            sensor_attributes[sensor_attribute.conf_key] = sensor_attribute

        schema = {
            cv.Optional(conf_key): cv.use_id(sensor_attribute.sensor_type)
            for conf_key, sensor_attribute in sensor_attributes.items()
        }

        # TODO: replace with something better
        if self.name.endswith("light"):
            schema[cv.Optional(CONF_LIGHT_ID)] = cv.use_id(light.LightState)

        if len(sensor_attributes) == 1:
            schema = automation.maybe_conf(next(iter(sensor_attributes)), schema)
        return schema

    def schema(self):
        return maybe_empty(self._schema())

    def _config_expression(self, config: dict):
        return cg.RawExpression(f"esp_matter::endpoint::{self.namespace}::config_t{{}}")

    def register(self, var, endpoint_id: int, config: dict) -> set[Cluster]:
        _LOGGER.debug(
            "[Matter] Registering device type %s on endpoint %s",
            self.name,
            endpoint_id,
        )
        register_device_type = var.register_device_type.template(
            cg.RawExpression(f"esp_matter::endpoint::{self.namespace}::config_t"),
            cg.RawExpression(f"esp_matter::endpoint::{self.namespace}::add"),
        )
        cg.add(
            register_device_type(
                endpoint_id, self.namespace, self._config_expression(config)
            )
        )
        created_clusters = {
            cluster for cluster in self.server_clusters if cluster.required
        }
        for cluster_name, _, sensor_attr in self.sensor_attributes:
            sensor_id = config.get(sensor_attr.conf_key)
            if sensor_id is not None:
                created_clusters.add(CLUSTERS_BY_NAME[cluster_name])
        return created_clusters


class ElectricalSensor(DeviceType):
    def _schema(self):
        schema = DeviceType._schema(self)
        schema[cv.Required("with_clusters")] = cv.All(
            cv.ensure_list(
                cv.one_of("ElectricalEnergyMeasurement", "ElectricalPowerMeasurement")
            ),
            cv.Length(min=1),
        )
        return schema

    def _config_expression(self, config: dict):
        namespace = f"esp_matter::endpoint::{self.namespace}"
        lines = ["[] {", f"{namespace}::config_t config{{}};"]
        lines.append(
            "config.power_topology.feature_flags = esp_matter::cluster::power_topology::feature::node_topology::get_id();"
        )
        lines.append(
            "config.electrical_power_measurement.feature_flags = esp_matter::cluster::electrical_power_measurement::feature::direct_current::get_id();"
        )
        for cluster_name in config["with_clusters"]:
            lines.append(f"config.with_{snake_case(cluster_name)}();")
        lines.extend(("return config;", "}()"))
        return cg.RawExpression("\n".join(lines))

    def register(self, var, endpoint_id: int, config: dict) -> set[Cluster]:
        created_clusters = DeviceType.register(self, var, endpoint_id, config)
        # esp_matter is written by idiots and doesn't properly guard cluster compilation...
        for cluster_name in (
            "electrical_energy_measurement",
            "electrical_power_measurement",
        ):
            created_clusters.add(CLUSTERS_BY_CONF_KEY[cluster_name])
        return created_clusters


DEVICE_TYPE_OVERRIDES = {
    "electrical_sensor": ElectricalSensor,
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


# Device types
DEVICE_TYPES: tuple[DeviceType, ...] = _load_device_types()
DEVICE_TYPES_BY_NAME: dict[str, DeviceType] = {
    device_type.name: device_type for device_type in DEVICE_TYPES
}
DEVICE_TYPES_BY_ID: dict[int, DeviceType] = {
    device_type.id: device_type for device_type in DEVICE_TYPES
}
DEVICE_TYPES_BY_CONF_KEY: dict[str, DeviceType] = {
    device_type.conf_key: device_type for device_type in DEVICE_TYPES
}
