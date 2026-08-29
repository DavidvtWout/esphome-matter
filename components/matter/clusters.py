from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import esphome.config_validation as cv

from .const import *


@dataclass(frozen=True, slots=True)
class Field:
    type: str
    key: str
    default: Any = None
    unit: Callable[[Any], Any] | None = None

    @property
    def required(self) -> bool:
        return self.default is None

    @property
    def _validator(self):
        try:
            return {
                "U8": cv.uint8_t,
                "U16": cv.uint16_t,
                "U32": cv.uint32_t,
                "I8": cv.int_range(min=-128, max=127),
                "I16": cv.int_range(min=-32768, max=32767),
                "I32": cv.int_range(min=-2147483648, max=2147483647),
            }[self.type]
        except KeyError as err:
            raise cv.Invalid(f"Unsupported Matter field type '{self.type}'") from err

    @property
    def validator(self):
        if self.unit is None:
            return self._validator
        return cv.All(self.unit, self._validator)

    @property
    def schema_key(self):
        if self.required:
            return cv.Required(self.key)
        return cv.Optional(self.key, default=self.default)


def _seconds(multiplier=1):
    def _validate(value: int | str):
        if isinstance(value, int):
            return value

        period_ms = cv.positive_time_period_milliseconds(value).total_milliseconds
        scaled = period_ms * multiplier
        if scaled % 1000 != 0:
            raise cv.Invalid(f"Duration must be a multiple of {1000 / multiplier:g}ms")

        return scaled // 1000

    return _validate


def _percentage(multiplier=254):
    def _validate(value: int | str):
        if isinstance(value, int):
            return value

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


MATTER_COMMANDS: dict[int | str, dict] = {
    CLUSTER_IDENTIFY: {
        "id": 0x0003,
        "commands": {
            COMMAND_IDENTIFY: {
                "id": 0x00,
                "fields": [Field("U16", FIELD_IDENTIFY_TIME, unit=_seconds())],
            },
            COMMAND_TRIGGER_EFFECT: {
                "id": 0x40,
                "fields": [
                    Field("U8", FIELD_EFFECT_IDENTIFIER),
                    Field("U8", FIELD_EFFECT_VARIANT, 0),
                ],
            },
        },
    },
    CLUSTER_ON_OFF: {
        "id": 0x0006,
        "commands": {
            COMMAND_OFF: {"id": 0x00},
            COMMAND_ON: {"id": 0x01},
            COMMAND_TOGGLE: {"id": 0x02},
            COMMAND_OFF_WITH_EFFECT: {
                "id": 0x40,
                "fields": [
                    Field("U8", FIELD_EFFECT_IDENTIFIER),
                    Field("U8", FIELD_EFFECT_VARIANT, 0),
                ],
            },
            COMMAND_ON_WITH_RECALL_GLOBAL_SCENE: {"id": 0x41},
            COMMAND_ON_WITH_TIMED_OFF: {
                "id": 0x42,
                "fields": [
                    Field("U8", FIELD_ON_OFF_CONTROL, 0),
                    Field("U16", FIELD_ON_TIME, unit=_seconds(multiplier=10)),
                    Field("U16", FIELD_OFF_WAIT_TIME, 0, unit=_seconds(multiplier=10)),
                ],
            },
        },
    },
    CLUSTER_LEVEL_CONTROL: {
        "id": 0x0008,
        "commands": {
            COMMAND_MOVE_TO_LEVEL: {
                "id": 0x00,
                "fields": [
                    Field("U8", FIELD_LEVEL, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE: {
                "id": 0x01,
                "fields": [
                    Field("U8", FIELD_MOVE_MODE),  # TODO: support up/down aliases
                    Field("U8", FIELD_RATE, unit=_percentage_per_second()),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP: {
                "id": 0x02,
                "fields": [
                    Field("U8", FIELD_STEP_MODE),
                    Field("U8", FIELD_STEP_SIZE, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP: {
                "id": 0x03,
                "fields": [
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_LEVEL_WITH_ON_OFF: {
                "id": 0x04,
                "fields": [
                    Field("U8", FIELD_LEVEL, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_WITH_ON_OFF: {
                "id": 0x05,
                "fields": [
                    Field("U8", FIELD_MOVE_MODE),
                    Field("U8", FIELD_RATE, unit=_percentage_per_second()),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_WITH_ON_OFF: {
                "id": 0x06,
                "fields": [
                    Field("U8", FIELD_STEP_MODE),
                    Field("U8", FIELD_STEP_SIZE, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP_WITH_ON_OFF: {
                "id": 0x07,
                "fields": [
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            # COMMAND_MOVE_TO_CLOSEST_FREQUENCY: {"id": 0x08},
        },
    },
    CLUSTER_COLOR_CONTROL: {
        "id": 0x0300,
        "commands": {
            COMMAND_MOVE_TO_HUE: {
                "id": 0x00,
                "fields": [
                    Field("U8", FIELD_HUE),
                    Field("U8", FIELD_DIRECTION),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_HUE: {
                "id": 0x01,
                "fields": [
                    Field("U8", FIELD_MOVE_MODE),
                    Field("U8", FIELD_RATE, unit=_percentage_per_second()),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_HUE: {
                "id": 0x02,
                "fields": [
                    Field("U8", FIELD_STEP_MODE),
                    Field("U8", FIELD_STEP_SIZE),
                    Field("U8", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_SATURATION: {
                "id": 0x03,
                "fields": [
                    Field("U8", FIELD_SATURATION, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_SATURATION: {
                "id": 0x04,
                "fields": [
                    Field("U8", FIELD_MOVE_MODE),
                    Field("U8", FIELD_RATE, unit=_percentage_per_second()),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_SATURATION: {
                "id": 0x05,
                "fields": [
                    Field("U8", FIELD_STEP_MODE),
                    Field("U8", FIELD_STEP_SIZE, unit=_percentage()),
                    Field("U8", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_HUE_AND_SATURATION: {
                "id": 0x06,
                "fields": [
                    Field("U8", FIELD_HUE),
                    Field("U8", FIELD_SATURATION, unit=_percentage()),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_COLOR: {
                "id": 0x07,
                "fields": [
                    Field("U16", FIELD_COLOR_X),
                    Field("U16", FIELD_COLOR_Y),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_COLOR: {
                "id": 0x08,
                "fields": [
                    Field("I16", FIELD_RATE_X),
                    Field("I16", FIELD_RATE_Y),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_COLOR: {
                "id": 0x09,
                "fields": [
                    Field("I16", FIELD_STEP_X),
                    Field("I16", FIELD_STEP_Y),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_COLOR_TEMPERATURE: {
                "id": 0x0A,
                "fields": [
                    Field("U16", FIELD_COLOR_TEMPERATURE_MIREDS),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            # COMMAND_ENHANCED_MOVE_TO_HUE: {"id": 0x40},
            # COMMAND_ENHANCED_MOVE_HUE: {"id": 0x41},
            # COMMAND_ENHANCED_STEP_HUE: {"id": 0x42},
            # COMMAND_ENHANCED_MOVE_TO_HUE_AND_SATURATION: {"id": 0x43},
            COMMAND_COLOR_LOOP_SET: {
                "id": 0x44,
                "fields": [
                    Field("U8", FIELD_UPDATE_FLAGS),
                    Field("U8", FIELD_ACTION),
                    Field("U8", FIELD_DIRECTION),
                    Field("U16", FIELD_TIME, unit=_seconds()),
                    Field("U16", FIELD_START_HUE),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP_MOVE_STEP: {
                "id": 0x47,
                "fields": [
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_COLOR_TEMPERATURE: {
                "id": 0x4B,
                "fields": [
                    Field("U8", FIELD_MOVE_MODE),
                    Field("U16", FIELD_RATE),
                    Field("U16", FIELD_COLOR_TEMPERATURE_MINIMUM_MIREDS),
                    Field("U16", FIELD_COLOR_TEMPERATURE_MAXIMUM_MIREDS),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_COLOR_TEMPERATURE: {
                "id": 0x4C,
                "fields": [
                    Field("U8", FIELD_STEP_MODE),
                    Field("U16", FIELD_STEP_SIZE),
                    Field(
                        "U16", FIELD_TRANSITION_TIME, 0, unit=_seconds(multiplier=10)
                    ),
                    Field("U16", FIELD_COLOR_TEMPERATURE_MINIMUM_MIREDS),
                    Field("U16", FIELD_COLOR_TEMPERATURE_MAXIMUM_MIREDS),
                    Field("U8", FIELD_OPTIONS_MASK, 0),
                    Field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
        },
    },
}
