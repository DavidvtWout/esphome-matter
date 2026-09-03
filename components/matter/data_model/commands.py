import esphome.config_validation as cv


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
