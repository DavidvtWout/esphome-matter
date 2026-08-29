from esphome import automation
import esphome.config_validation as cv
from esphome.components import binary_sensor, light, sensor
from esphome.const import CONF_LIGHT_ID, CONF_SENSOR_ID

from .const import *
from .types import (
    MatterBinarySensorMapping,
    MatterLightMapping,
    MatterSensorMapping,
)


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
BINARY_SENSOR_SCHEMA = cv.All(
    empty_to_dict,
    automation.maybe_conf(
        CONF_SENSOR_ID,
        cv.Schema(
            {
                cv.Optional(CONF_SENSOR_ID): cv.use_id(binary_sensor.BinarySensor),
            }
        ),
    ),
)

DEVICE_TYPES = {
    # Lights
    CONF_ON_OFF_LIGHT: {
        "schema": LIGHT_SCHEMA,
        "mapping": MatterLightMapping,
    },
    CONF_DIMMABLE_LIGHT: {
        "schema": LIGHT_SCHEMA,
        "mapping": MatterLightMapping,
    },
    CONF_COLOUR_TEMPERATURE_LIGHT: {
        "schema": LIGHT_SCHEMA,
        "mapping": MatterLightMapping,
    },
    CONF_EXTENDED_COLOUR_LIGHT: {
        "schema": LIGHT_SCHEMA,
        "mapping": MatterLightMapping,
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
    CONF_COLOR_DIMMER_SWITCH: {
        "schema": EMPTY_SCHEMA,
        CONF_ENABLE_BINDING: True,
    },
    CONF_GENERIC_SWITCH: {
        "schema": EMPTY_SCHEMA,
    },
    # Sensors
    CONF_TEMPERATURE_SENSOR: {
        "schema": SENSOR_SCHEMA,
        "mapping": MatterSensorMapping,
    },
    CONF_HUMIDITY_SENSOR: {
        "schema": SENSOR_SCHEMA,
        "mapping": MatterSensorMapping,
    },
    CONF_OCCUPANCY_SENSOR: {
        "schema": BINARY_SENSOR_SCHEMA,
        "mapping": MatterBinarySensorMapping,
    },
    CONF_CONTACT_SENSOR: {
        "schema": BINARY_SENSOR_SCHEMA,
        "mapping": MatterBinarySensorMapping,
    },
    CONF_LIGHT_SENSOR: {
        "schema": SENSOR_SCHEMA,
        "mapping": MatterSensorMapping,
    },
    CONF_PRESSURE_SENSOR: {
        "schema": SENSOR_SCHEMA,
        "mapping": MatterSensorMapping,
    },
    CONF_FLOW_SENSOR: {
        "schema": SENSOR_SCHEMA,
        "mapping": MatterSensorMapping,
    },
}
