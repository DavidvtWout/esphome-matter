from esphome import automation
import esphome.config_validation as cv
from esphome.components import light, sensor
from esphome.const import CONF_LIGHT_ID, CONF_SENSOR_ID

from .const import *


def empty_to_dict(value):
    return {} if value is None else value


EMPTY_SCHEMA = cv.All(empty_to_dict, cv.Schema({}))
LIGHT_SCHEMA = cv.All(
    empty_to_dict,
    automation.maybe_conf(
        CONF_LIGHT_ID,
        cv.Schema(
            {
                cv.Optional(CONF_LIGHT_ID): cv.use_id(light.LightState),
            }
        ),
    ),
)
SENSOR_SCHEMA = cv.All(
    empty_to_dict,
    automation.maybe_conf(
        CONF_SENSOR_ID,
        cv.Schema(
            {
                cv.Optional(CONF_SENSOR_ID): cv.use_id(sensor.Sensor),
            }
        ),
    ),
)

DEVICE_TYPES = {
    # Lights
    CONF_ON_OFF_LIGHT: {
        "schema": LIGHT_SCHEMA,
    },
    CONF_DIMMABLE_LIGHT: {
        "schema": LIGHT_SCHEMA,
    },
    CONF_COLOUR_TEMPERATURE_LIGHT: {
        "schema": LIGHT_SCHEMA,
    },
    CONF_EXTENDED_COLOUR_LIGHT: {
        "schema": LIGHT_SCHEMA,
    },
    # Switches
    CONF_ON_OFF_LIGHT_SWITCH: {
        "schema": EMPTY_SCHEMA,
        CONF_ENABLE_BINDING: True,
    },
    CONF_DIMMER_SWITCH: {
        "schema": EMPTY_SCHEMA,
        CONF_ENABLE_BINDING: True,
    },
    # Sensors
    CONF_TEMPERATURE_SENSOR: {
        "schema": SENSOR_SCHEMA,
    },
}
