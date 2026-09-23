import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import esphome.config_validation as cv

from ..util import snake_case

_LOGGER = logging.getLogger(__name__)


def _seconds(multiplier=1):
    def _validate(value):
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
    def _validate(value):
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            raise cv.Invalid(f"Floats are ambiguous. Use '{value}%' instead.")
        return round(cv.percentage(value) * multiplier)

    return _validate


def _hue(multiplier):
    def _validate(value):
        if isinstance(value, int):
            _LOGGER.warning(
                "Integer hue value %s is interpreted as a raw Matter value. Degrees values such as '180°' are recommended.",
                value,
            )
            return value
        return round(cv.angle(value) / 360 * multiplier)

    return _validate


def _saturation(multiplier=254):
    def _validate(value):
        if isinstance(value, int):
            _LOGGER.warning(
                "Integer saturation value %s is interpreted as a raw Matter value. A value between 0.0 and 1.0 is recommended",
                value,
            )
            return value
        if isinstance(value, float):
            if not 0.0 <= value <= 1.0:
                raise cv.Invalid("Saturation must be between 0.0 and 1.0")
            return round(value * multiplier)
        raise cv.Invalid("Saturation should be a float value between 0.0 and 1.0")

    return _validate


def _xy_colour(multiplier=65536):
    def _validate(value):
        if isinstance(value, int):
            _LOGGER.warning(
                "Integer XY colour value %s is interpreted as a raw Matter value. A float is recommended",
                value,
            )
            return value
        if isinstance(value, float):
            if not 0.0 <= value <= 1.0:
                raise cv.Invalid("XY colour value must be in the range [0.0, 1.0]")
            return round(value * multiplier)
        raise cv.Invalid("XY colour value should be a float")

    return _validate


def _xy_colour_rate(multiplier=65536):
    def _validate(value):
        if isinstance(value, int):
            _LOGGER.warning(
                "Integer XY colour value %s is interpreted as a raw Matter value. A float is recommended",
                value,
            )
            return value
        if isinstance(value, float):
            if not -0.5 <= value < 0.5:
                raise cv.Invalid("XY colour rate must be in the range [-0.5, 0.5)")
            return round(value * multiplier)
        raise cv.Invalid("XY colour rate should be a float")

    return _validate


def _rate(validator_factory):
    def _factory(multiplier=None):
        def _validate(value):
            if isinstance(value, str):
                value = value.removesuffix("/s")
            if multiplier is not None:
                return validator_factory(multiplier)(value)
            else:
                return validator_factory()(value)

        return _validate

    return _factory


_UNIT_VALIDATORS = {
    "seconds": _seconds,
    "percentage": _percentage,
    "percentage_rate": _rate(_percentage),
    "hue": _hue,
    "hue_rate": _rate(_hue),
    "saturation": _saturation,
    "saturation_rate": _saturation,  # Unitless so no rate.
    "xy_colour": _xy_colour,
    "xy_colour_rate": _xy_colour_rate,
}


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

_ESP_MATTER_JSON_TYPES = {
    "int8s": "I8",
    "int16s": "I16",
    "int32s": "I32",
    "int64s": "I64",
    "int8u": "U8",
    "int16u": "U16",
    "int32u": "U32",
    "int64u": "U64",
    "enum8": "U8",
    "enum16": "U16",
    "bitmap8": "U8",
    "bitmap16": "U16",
    "bitmap32": "U32",
    "bitmap64": "U64",
    "boolean": "BOOL",
    "single": "FP",
    "double": "DFP",
    "char_string": "STR",
    "long_char_string": "STR",
    "octet_string": "BYT",
    "long_octet_string": "BYT",
    "struct": "OBJ",
}


@dataclass(frozen=True, slots=True)
class CommandArg:
    name: str  # CamelCase
    type: str
    id: int
    optional: bool = False
    default: int | None = None
    min: int | None = None
    max: int | None = None
    unit: str | None = None
    multiplier: int | None = None
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
            id=data["id"],
            name=data["name"],
            type=data["type"],
            optional=optional,
            default=default,
            min=data.get("min"),
            max=data.get("max"),
            unit=data.get("unit"),
            multiplier=data.get("multiplier"),
            enum_values=data.get("enum_values", {}),
            bitmap_masks=bitmap_masks,
            struct_items=data.get("struct", []),
        )

    @property
    def data_key(self) -> str:
        """Key for esp_matter JSON data."""
        return f"{self.id}:{_ESP_MATTER_JSON_TYPES[self.type]}"

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
                validator = cv.All(self._validate_enum, validator)
            elif self.bitmap_masks:
                validator = cv.All(self._validate_bitmap, validator)
        elif self.type == "boolean":
            validator = cv.boolean
        elif self.type in ("single", "double"):
            validator = cv.float_
        elif self.type in (
            "char_string",
            "long_char_string",
            "octet_string",
            "long_octet_string",
        ):
            validator = cv.string_strict
        else:
            validator = cv.valid

        if self.unit is not None:
            try:
                unit_validator = _UNIT_VALIDATORS[self.unit]
            except KeyError as err:
                raise ValueError(f"Unknown command argument unit: {self.unit}") from err
            if self.multiplier is not None:
                validator = cv.All(unit_validator(self.multiplier), validator)
            else:
                validator = cv.All(unit_validator(), validator)
        return validator


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
