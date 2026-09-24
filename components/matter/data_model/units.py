import logging

import esphome.config_validation as cv

_LOGGER = logging.getLogger(__name__)


def seconds(multiplier=1):
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


def percentage(multiplier=254):
    def _validate(value):
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            raise cv.Invalid(f"Floats are ambiguous. Use '{value}%' instead.")
        return round(cv.percentage(value) * multiplier)

    return _validate


def hue(multiplier):
    def _validate(value):
        if isinstance(value, int):
            _LOGGER.warning(
                "Integer hue value %s is interpreted as a raw Matter value. Degrees values such as '180°' are recommended.",
                value,
            )
            return value
        return round(cv.angle(value) / 360 * multiplier)

    return _validate


def saturation(multiplier=254):
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


def xy_colour(multiplier=65536):
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


def xy_colour_rate(multiplier=65536):
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


def rate(validator_factory):
    def _factory(multiplier=None):
        def _validate(value):
            if isinstance(value, str):
                value = value.removesuffix("/s")
            if multiplier is not None:
                return validator_factory(multiplier)(value)
            return validator_factory()(value)

        return _validate

    return _factory


UNIT_VALIDATORS = {
    "seconds": seconds,
    "percentage": percentage,
    "percentage_rate": rate(percentage),
    "hue": hue,
    "hue_rate": rate(hue),
    "saturation": saturation,
    "saturation_rate": saturation,  # Unitless so no rate.
    "xy_colour": xy_colour,
    "xy_colour_rate": xy_colour_rate,
}
