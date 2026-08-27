from .const import *


def _field(field_type: str, key: str, default=None):
    return {"type": field_type, "key": key, "default": default}


# Commands marked "absolute" fully determine the state of the (single) axis their
# cluster controls, so a newer one makes an older one that has not been sent yet
# redundant. The outbound command queue uses this to drop superseded commands
# instead of sending both (see matter_actions.cpp). Relative commands (Toggle,
# Move, Step, ...) must never be dropped: their effect depends on the state they
# are applied to, so losing or reordering one desynchronises the device.
#
# Only OnOff and LevelControl are marked. ColorControl is deliberately left
# relative even for its MoveTo* commands: hue, saturation, xy and colour
# temperature are orthogonal axes, so a newer MoveToHue does not supersede a
# pending MoveToColorTemperature.
_ABSOLUTE = {"absolute": True}


MATTER_COMMANDS: dict[int | str, dict] = {
    CLUSTER_IDENTIFY: {
        "id": 0x0003,
        "commands": {
            COMMAND_IDENTIFY: {
                "id": 0x00,
                "fields": [_field("U16", FIELD_IDENTIFY_TIME)],
            },
            COMMAND_TRIGGER_EFFECT: {
                "id": 0x40,
                "fields": [
                    _field("U8", FIELD_EFFECT_IDENTIFIER),
                    _field("U8", FIELD_EFFECT_VARIANT, 0),
                ],
            },
        },
    },
    CLUSTER_ON_OFF: {
        "id": 0x0006,
        "commands": {
            COMMAND_OFF: {"id": 0x00, **_ABSOLUTE},
            COMMAND_ON: {"id": 0x01, **_ABSOLUTE},
            COMMAND_TOGGLE: {"id": 0x02},
            COMMAND_OFF_WITH_EFFECT: {
                "id": 0x40,
                "fields": [
                    _field("U8", FIELD_EFFECT_IDENTIFIER),
                    _field("U8", FIELD_EFFECT_VARIANT, 0),
                ],
            },
            COMMAND_ON_WITH_RECALL_GLOBAL_SCENE: {"id": 0x41},
            COMMAND_ON_WITH_TIMED_OFF: {
                "id": 0x42,
                "fields": [
                    _field("U8", FIELD_ON_OFF_CONTROL, 0),
                    _field(
                        "U16", FIELD_ON_TIME
                    ),  # TODO: support s (multiply seconds by 10)
                    _field(
                        "U16", FIELD_OFF_WAIT_TIME, 0
                    ),  # TODO: support s (multiply seconds by 10)
                ],
            },
        },
    },
    CLUSTER_LEVEL_CONTROL: {
        "id": 0x0008,
        "commands": {
            COMMAND_MOVE_TO_LEVEL: {
                "id": 0x00,
                **_ABSOLUTE,
                "fields": [
                    _field("U8", FIELD_LEVEL),  # TODO: support %
                    _field("U16", FIELD_TRANSITION_TIME, 0),  # TODO: support s
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE: {
                "id": 0x01,
                "fields": [
                    _field("U8", FIELD_MOVE_MODE),  # TODO: support up/down aliases
                    _field("U8", FIELD_RATE),  # TODO: support %/s?
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP: {
                "id": 0x02,
                "fields": [
                    _field("U8", FIELD_STEP_MODE),
                    _field("U8", FIELD_STEP_SIZE),  # TODO: support %
                    _field("U16", FIELD_TRANSITION_TIME, 0),  # TODO: support s
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP: {
                "id": 0x03,
                "fields": [
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_LEVEL_WITH_ON_OFF: {
                "id": 0x04,
                **_ABSOLUTE,
                "fields": [
                    _field("U8", FIELD_LEVEL),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_WITH_ON_OFF: {
                "id": 0x05,
                "fields": [
                    _field("U8", FIELD_MOVE_MODE),
                    _field("U8", FIELD_RATE),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_WITH_ON_OFF: {
                "id": 0x06,
                "fields": [
                    _field("U8", FIELD_STEP_MODE),
                    _field("U8", FIELD_STEP_SIZE),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP_WITH_ON_OFF: {
                "id": 0x07,
                "fields": [
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
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
                    _field("U8", FIELD_HUE),
                    _field("U8", FIELD_DIRECTION),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_HUE: {
                "id": 0x01,
                "fields": [
                    _field("U8", FIELD_MOVE_MODE),
                    _field("U8", FIELD_RATE),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_HUE: {
                "id": 0x02,
                "fields": [
                    _field("U8", FIELD_STEP_MODE),
                    _field("U8", FIELD_STEP_SIZE),
                    _field("U8", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_SATURATION: {
                "id": 0x03,
                "fields": [
                    _field("U8", FIELD_SATURATION),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_SATURATION: {
                "id": 0x04,
                "fields": [
                    _field("U8", FIELD_MOVE_MODE),
                    _field("U8", FIELD_RATE),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_SATURATION: {
                "id": 0x05,
                "fields": [
                    _field("U8", FIELD_STEP_MODE),
                    _field("U8", FIELD_STEP_SIZE),
                    _field("U8", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_HUE_AND_SATURATION: {
                "id": 0x06,
                "fields": [
                    _field("U8", FIELD_HUE),
                    _field("U8", FIELD_SATURATION),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_COLOR: {
                "id": 0x07,
                "fields": [
                    _field("U16", FIELD_COLOR_X),
                    _field("U16", FIELD_COLOR_Y),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_COLOR: {
                "id": 0x08,
                "fields": [
                    _field("I16", FIELD_RATE_X),
                    _field("I16", FIELD_RATE_Y),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_COLOR: {
                "id": 0x09,
                "fields": [
                    _field("I16", FIELD_STEP_X),
                    _field("I16", FIELD_STEP_Y),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_TO_COLOR_TEMPERATURE: {
                "id": 0x0A,
                "fields": [
                    _field("U16", FIELD_COLOR_TEMPERATURE_MIREDS),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            # COMMAND_ENHANCED_MOVE_TO_HUE: {"id": 0x40},
            # COMMAND_ENHANCED_MOVE_HUE: {"id": 0x41},
            # COMMAND_ENHANCED_STEP_HUE: {"id": 0x42},
            # COMMAND_ENHANCED_MOVE_TO_HUE_AND_SATURATION: {"id": 0x43},
            COMMAND_COLOR_LOOP_SET: {
                "id": 0x44,
                "fields": [
                    _field("U8", FIELD_UPDATE_FLAGS),
                    _field("U8", FIELD_ACTION),
                    _field("U8", FIELD_DIRECTION),
                    _field("U16", FIELD_TIME),
                    _field("U16", FIELD_START_HUE),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STOP_MOVE_STEP: {
                "id": 0x47,
                "fields": [
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_MOVE_COLOR_TEMPERATURE: {
                "id": 0x4B,
                "fields": [
                    _field("U8", FIELD_MOVE_MODE),
                    _field("U16", FIELD_RATE),
                    _field("U16", FIELD_COLOR_TEMPERATURE_MINIMUM_MIREDS),
                    _field("U16", FIELD_COLOR_TEMPERATURE_MAXIMUM_MIREDS),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
            COMMAND_STEP_COLOR_TEMPERATURE: {
                "id": 0x4C,
                "fields": [
                    _field("U8", FIELD_STEP_MODE),
                    _field("U16", FIELD_STEP_SIZE),
                    _field("U16", FIELD_TRANSITION_TIME, 0),
                    _field("U16", FIELD_COLOR_TEMPERATURE_MINIMUM_MIREDS),
                    _field("U16", FIELD_COLOR_TEMPERATURE_MAXIMUM_MIREDS),
                    _field("U8", FIELD_OPTIONS_MASK, 0),
                    _field("U8", FIELD_OPTIONS_OVERRIDE, 0),
                ],
            },
        },
    },
}
