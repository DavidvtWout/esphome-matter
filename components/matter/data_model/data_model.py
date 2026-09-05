import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import esphome.config_validation as cv
from esphome import automation
from esphome.components import light
from esphome.const import CONF_LIGHT_ID

from ..util import maybe_empty, snake_case
from .attributes import SENSOR_ATTRIBUTES, SensorAttribute

DATA_MODEL_DIR = Path(__file__).resolve().parent


_INTEGER_RANGES = {
    "int8u": (0, 0xFF),
    "int16u": (0, 0xFFFF),
    "int32u": (0, 0xFFFFFFFF),
    "int64u": (0, 0xFFFFFFFFFFFFFFFF),
    "int8s": (-0x80, 0x7F),
    "int16s": (-0x8000, 0x7FFF),
    "int32s": (-0x80000000, 0x7FFFFFFF),
    "int64s": (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
    "enum8": (0, 0xFF),
    "bitmap8": (0, 0xFF),
    "bitmap16": (0, 0xFFFF),
    "bitmap32": (0, 0xFFFFFFFF),
    "bitmap64": (0, 0xFFFFFFFFFFFFFFFF),
}


@dataclass(frozen=True, slots=True)
class CommandArg:
    name: str  # CamelCase
    type: str
    id: int | None = None
    optional: bool = False
    default: int | None = None
    min: int | None = None
    max: int | None = None
    # is_nullable: bool = False
    # enum_values and bitmap_values keys are snake_case.
    enum_values: dict[str, int] = field(default_factory=dict)
    bitmap_masks: dict[str, int] = field(default_factory=dict)
    struct_items: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict):
        # TODO: validate enum and bitmap names to be snake_case

        optional = data.get("optional", False)
        default = data.get("default")
        bitmap_masks = data.get("bitmap_masks", {})
        if bitmap_masks and default is None:
            default = 0
        if default is not None:
            optional = True

        return cls(
            id=data.get("id"),
            name=data["name"],
            type=data["type"],
            optional=optional,
            default=default,
            min=data.get("min"),
            max=data.get("max"),
            enum_values=data.get("enum_values", {}),
            bitmap_masks=bitmap_masks,
            struct_items=data.get("struct", []),
        )

    @property
    def data_key(self) -> str:
        """Key for esp_matter JSON data."""
        return f"{self.id}:{self.type}"

    @property
    def schema_key(self) -> str:
        """Key as used in device config YAML."""
        conf_key = snake_case(self.name)
        if not self.optional:
            return cv.Required(conf_key)
        if self.default is not None:
            return cv.Optional(conf_key, default=self.default)
        else:
            return cv.Optional(conf_key)

    def _validate_enum(self, value):
        if isinstance(value, int):
            return value
        if not isinstance(value, str):
            raise cv.Invalid("Expected an enum name or integer")
        enum_value = self.enum_values.get(value)
        if enum_value is not None:
            return enum_value
        raise cv.Invalid(
            f"Unknown enum name '{value}'; expected one of: {', '.join(self.enum_values)}"
        )

    def _validate_bitmap(self, value):
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return self.bitmap_masks[value]
            except KeyError:
                raise cv.Invalid(
                    f"Unknown bitmask name '{value}'; expected one of: {', '.join(self.enum_values)}"
                )
        if isinstance(value, list):
            result = 0
            for v in value:
                try:
                    result += self.bitmap_masks[v]
                except KeyError:
                    raise cv.Invalid(
                        f"Unknown bitmask name '{v}'; expected one of: {', '.join(self.enum_values)}"
                    )
            return result
        raise cv.Invalid("Expected a (list of) bitmask name(s) or integer")

    @property
    def schema(self):
        if self.type in _INTEGER_RANGES:
            type_min, type_max = _INTEGER_RANGES[self.type]
            validator = cv.int_range(
                min=max(type_min, self.min) if self.min is not None else type_min,
                max=min(type_max, self.max) if self.max is not None else type_max,
            )
            if self.enum_values:
                return cv.All(self._validate_enum, validator)
            if self.bitmap_masks:
                return cv.All(self._validate_bitmap, validator)
            return validator
        if self.type == "boolean":
            return cv.boolean
        if self.type in ("single", "double"):
            return cv.float_
        if self.type in (
            "char_string",
            "long_char_string",
            "octet_string",
            "long_octet_string",
        ):
            return cv.string_strict
        return cv.valid
        # raise cv.Invalid(f"[{self.name}] Command arg type '{self.type}' is not yet supported")


@dataclass(frozen=True, slots=True)
class Command:
    cluster_name: str  # CamelCase
    name: str  # CamelCase
    id: int
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
    name: str | None  # CamelCase
    type: str
    # max: int | None = None
    define: str | None = None
    # is_nullable: bool = False
    writable: bool = False
    optional: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data.get("name"),
            type=data["type"],
            define=data["define"],
            writable=data["writable"],
            optional=data["optional"],
        )


@dataclass(frozen=True, slots=True)
class Cluster:
    id: int
    name: str  # Name with spaces and special characters such as "/"
    revision: int
    required: bool = False
    features: tuple[Feature, ...] = ()
    server_attributes: tuple[Attribute, ...] = ()
    client_attributes: tuple[Attribute, ...] = ()
    commands: tuple[Command, ...] = ()
    responses: tuple[Command, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            revision=data.get(
                "revision", 1
            ),  # Some lack a revision. Assuming it's 1...
            features=tuple(),  # TODO
            server_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("server_attributes", ())
            ),
            client_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("client_attributes", ())
            ),
            commands=tuple(),  # TODO
            responses=tuple(),  # TODO
        )

    @property
    def sdkconfig_option(self) -> str:
        sdkconfig_name = (
            self.name.replace(" ", "_")
            .replace("/", "_")
            .replace(".", "_")
            .replace("-", "")
            .upper()
        )
        sdkconfig_name = sdkconfig_name.replace("WEBRTC", "WEB_RTC")
        sdkconfig_name = sdkconfig_name.replace(
            "TOTAL_VOLATILE_ORGANIC_COMPOUNDS", "TVOC"
        )
        sdkconfig_name = sdkconfig_name.replace("SCENES_MANAGEMENT", "SCENES")
        sdkconfig_name = sdkconfig_name.replace(
            "OVEN_CAVITY_OPERATIONAL_STATE", "OPERATIONAL_STATE_OVEN"
        )
        sdkconfig_name = sdkconfig_name.replace(
            "RVC_OPERATIONAL_STATE", "OPERATIONAL_STATE_RVC"
        )
        return f"CONFIG_SUPPORT_{sdkconfig_name}_CLUSTER"

    @property
    def camel_case_name(self) -> str:
        return (
            self.name.replace("/", "")
            .replace(" ", "")
            .replace("-", "")
            .replace(".", "")
        )

    @property
    def namespace(self) -> str:
        """esp_matter::cluster:: namespace"""
        return (
            self.name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "")
            .replace(".", "")
            .lower()
        )


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

    @property
    def schema(self):
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
        return maybe_empty(schema)


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


def _load_clusters(
    clusters_file: Path = DATA_MODEL_DIR / "clusters.json",
) -> tuple[Cluster, ...]:
    clusters: list[Cluster] = []
    with open(clusters_file, "r") as file:
        contents = json.load(file)
    for clusters_data in contents:
        clusters.append(Cluster.from_dict(clusters_data))
    return tuple(clusters)


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

# Cluster
CLUSTERS: tuple[Cluster, ...] = _load_clusters()
CLUSTERS_BY_ID: dict[int, Cluster] = {cluster.id: cluster for cluster in CLUSTERS}
CLUSTERS_BY_NAME: dict[str, Cluster] = {
    cluster.camel_case_name: cluster for cluster in CLUSTERS
}

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
