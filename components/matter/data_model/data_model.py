from pathlib import Path

import esphome.config_validation as cv
import json
from dataclasses import dataclass
from esphome import automation

from .attributes import SENSOR_ATTRIBUTES, SensorAttribute
from ..util import snake_case

DATA_MODEL_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class CommandArg:
    name: str  # CamelCase
    type: str
    id: int | None = None
    optional: bool = False
    default: int | None = None
    # min: int | None = None
    # max: int | None = None
    # is_nullable: bool = False
    enum_values: tuple[tuple[str, int], ...] = ()
    # converter: str | None = None

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id"),
            name=data["name"],
            type=data["type"],
            optional=data.get("optional", False),
            default=data.get("default"),
            enum_values=data.get("enum_values", ()),
        )

    @property
    def data_key(self) -> str:
        """Key for esp_matter JSON data."""
        return f"{self.id}:{self.type}"

    @property
    def conf_key(self) -> str:
        """Key as used in device config YAML."""
        return snake_case(self.name)


@dataclass(frozen=True, slots=True)
class Command:
    cluster_name: str  # CamelCase
    name: str  # CamelCase
    id: int
    # source: str  # either client or server
    # optional: bool = False
    args: tuple[CommandArg, ...] = ()

    @classmethod
    def from_dict(cls, cluster_name: str, name: str, data: dict):
        return cls(
            cluster_name=cluster_name,
            name=name,
            id=data["id"],
            args=tuple([CommandArg.from_dict(arg) for arg in data["args"]]),
        )


@dataclass(frozen=True, slots=True)
class Feature:
    code: str
    name: str  # CamelCase
    bit: int


@dataclass(frozen=True, slots=True)
class Attribute:
    id: int
    name: str  # CamelCase
    # side: str  # TODO: either "client", "server" or "either". Maybe enum type?
    type: str  # TODO: maybe enum?
    # max: int | None = None
    # define: str | None = None
    # is_nullable: bool = False
    # writable: bool = False
    # optional: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
        )


@dataclass(frozen=True, slots=True)
class Cluster:
    id: int
    name: str  # CamelCase
    revision: int
    client: bool
    server: bool
    # features: tuple[Feature, ...] = ()
    attributes: tuple[Attribute, ...] = ()
    # commands: tuple[Command, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            revision=data.get("revision", 1),
            client=data.get("client"),
            server=data.get("server"),
            attributes=tuple([Attribute.from_dict(a) for a in data["attributes"]]),
        )

    @property
    def namespace(self) -> str:
        return snake_case(self.name)


@dataclass(frozen=True, slots=True)
class DeviceType:
    id: int
    name: str  # snake_case
    revision: int
    clusters: tuple[Cluster, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            id=data["id"],
            revision=data["revision"],
            clusters=tuple([Cluster.from_dict(c) for c in data["clusters"]]),
        )

    @property
    def namespace(self) -> str:
        return self.name

    @property
    def conf_key(self) -> str:
        return self.name

    @property
    def sensor_attributes(self) -> list[SensorAttribute]:
        sensor_attributes = []
        for cluster in self.clusters:
            for sensor_attribute in SENSOR_ATTRIBUTES.get(cluster.name, {}).values():
                sensor_attributes.append(sensor_attribute)
        return sensor_attributes

    def schema(self):
        sensor_attributes: dict[str, SensorAttribute] = {}
        for sensor_attribute in self.sensor_attributes:
            sensor_attributes[sensor_attribute.conf_key] = sensor_attribute

        schema = {
            cv.Optional(conf_key): cv.use_id(sensor_attribute.sensor_type)
            for conf_key, sensor_attribute in sensor_attributes.items()
        }

        if len(sensor_attributes) == 1:
            return automation.maybe_conf(next(iter(sensor_attributes)), schema)
        return schema


def _load_commands(
    commands_file: Path = DATA_MODEL_DIR / "commands.json",
) -> tuple[Command, ...]:
    commands: list[Command] = []

    with open(commands_file, "r") as file:
        contents = json.load(file)

    for cluster_name, commands_data in contents.items():
        for name, data in commands_data.items():
            commands.append(Command.from_dict(cluster_name, name, data))

    return tuple(commands)


def _load_device_types(
    device_types_file: Path = DATA_MODEL_DIR / "device_types.json",
) -> tuple[DeviceType, ...]:
    device_types: list[DeviceType] = []

    with open(device_types_file, "r") as file:
        contents = json.load(file)

    for device_type_data in contents:
        device_types.append(DeviceType.from_dict(device_type_data))

    return tuple(device_types)


# Commands by ClusterName
COMMANDS: tuple[Command, ...] = _load_commands()

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

CLUSTER_ID_TO_NAME = {}
CLUSTER_NAME_TO_ID = {}
for dt in DEVICE_TYPES:
    for c in dt.clusters:
        CLUSTER_ID_TO_NAME[c.id] = c.name
        CLUSTER_NAME_TO_ID[c.name] = c.id
