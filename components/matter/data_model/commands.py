import json
from dataclasses import dataclass, field
from pathlib import Path

import esphome.config_validation as cv

from ..util import snake_case

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


def _load_commands(
    commands_file: Path = Path(__file__).resolve().parent / "commands.json",
) -> tuple[Command, ...]:
    commands: list[Command] = []
    with open(commands_file, "r") as file:
        contents = json.load(file)
    for cluster_name, commands_data in contents.items():
        for name, data in commands_data.items():
            commands.append(Command.from_dict(cluster_name, name, data))
    return tuple(commands)


COMMANDS: tuple[Command, ...] = _load_commands()


"""
The parsed Matter data model does not specify the meaning of the command arguments. For example, the transition time
in LevelControl commands is a uint16 and measures the time in multiples of 100 ms. So a value of 15 means 1.5 _seconds.
Because the unit and meaning of the values are missing from the data model, these must be defined separately which
is done here.
"""


def _seconds(multiplier=1):
    def _validate(value: int | str):
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            raise cv.Invalid(f"Floats are ambiguous. Use '{value}s' instead.")

        period_ms = cv.positive_time_period_milliseconds(value).total_milliseconds
        scaled = period_ms * multiplier
        if scaled % 1000 != 0:
            raise cv.Invalid(f"Duration must be a multiple of {1000 / multiplier:g}ms")

        return scaled // 1000

    return _validate


def _percentage(multiplier=254):
    def _validate(value: int | float | str):
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            raise cv.Invalid(f"Floats are ambiguous. Use '{value}%' instead.")

        return round(cv.percentage(value) * multiplier)

    return _validate


def _percentage_per_second(multiplier=254):
    def _validate(value: int | str):
        if isinstance(value, int):
            return value
        if not isinstance(value, str) or not value.endswith("%/s"):
            raise cv.Invalid("Expected a percentage rate such as 50%/s")

        return round(cv.percentage(value.removesuffix("/s")) * multiplier)

    return _validate


# Arranged by Cluster, Command, CommandArg
COMMAND_ARG_TYPES = {
    "Identify": {  # 0x0003
        "Identify": {"IdentifyTime": _seconds()},
    },
    "OnOff": {  # 0x0006
        "OnWithTimedOff": {
            "OnTime": _seconds(multiplier=10),
            "OffWaitTime": _seconds(multiplier=10),
        }
    },
    "LevelControl": {  # 0x0008
        "MoveToLevel": {
            "Level": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "Move": {"Rate": _percentage_per_second()},
        "Step": {
            "StepSize": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "MoveToLevelWithOnOff": {
            "Level": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "MoveWithOnOff": {"Rate": _percentage_per_second()},
        "StepWithOnOff": {
            "StepSize": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
    },
    "ColorControl": {  # 0x0300
        "MoveToHue": {"TransitionTime": _seconds(multiplier=10)},
        "MoveHue": {"Rate": _percentage_per_second()},
        "StepHue": {"TransitionTime": _seconds(multiplier=10)},
        "MoveToSaturation": {
            "Saturation": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "MoveSaturation": {"Rate": _percentage_per_second()},
        "StepSaturation": {
            "StepSize": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "MoveToHueAndSaturation": {
            "Saturation": _percentage(),
            "TransitionTime": _seconds(multiplier=10),
        },
        "MoveToColor": {"TransitionTime": _seconds(multiplier=10)},
        "StepColor": {"TransitionTime": _seconds(multiplier=10)},
        "MoveToColorTemperature": {"TransitionTime": _seconds(multiplier=10)},
        "ColorLoopSet": {"Time": _seconds()},
        "StepColorTemperature": {"TransitionTime": _seconds(multiplier=10)},
    },
}
