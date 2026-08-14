from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import light, sensor
from esphome.const import (
    CONF_COMMAND,
    CONF_ID,
    CONF_LIGHT_ID,
    CONF_SENSOR_ID,
    CONF_VALUE,
)
from esphome.core import ID
from esphome.types import ConfigType

from .const import *
from .types import MatterEndpointRef


def _maybe_empty_schema(schema):
    return lambda value: schema({} if value is None else value)


def _validate_endpoint(config):
    device_types = [k for k in config if k != CONF_ID]
    if len(device_types) != 1:
        raise cv.Invalid(
            "Each endpoint must have exactly one device type "
            "(multiple device types per endpoint are not supported yet)"
        )
    return config


LIGHT_SCHEMA = _maybe_empty_schema(
    cv.Schema(
        {
            cv.Required(CONF_LIGHT_ID): cv.use_id(light.LightState),
        }
    )
)
SENSOR_SCHEMA = _maybe_empty_schema(
    cv.Schema(
        {
            cv.Required(CONF_SENSOR_ID): cv.use_id(sensor.Sensor),
        }
    )
)

ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            # Lights
            cv.Optional(CONF_ON_OFF_LIGHT): LIGHT_SCHEMA,
            cv.Optional(CONF_DIMMABLE_LIGHT): LIGHT_SCHEMA,
            cv.Optional(CONF_COLOUR_TEMPERATURE_LIGHT): LIGHT_SCHEMA,
            cv.Optional(CONF_EXTENDED_COLOUR_LIGHT): LIGHT_SCHEMA,
            # Switches
            cv.Optional(CONF_ON_OFF_LIGHT_SWITCH): cv.Schema({}),
            cv.Optional(CONF_DIMMER_SWITCH): cv.Schema({}),
            cv.Optional(CONF_COLOUR_DIMMER_SWITCH): cv.Schema({}),
            cv.Optional(CONF_GENERIC_SWITCH): cv.Schema({}),
            # Sensors
            cv.Optional(CONF_TEMPERATURE_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_HUMIDITY_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_OCCUPANCY_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_CONTACT_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_LIGHT_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_PRESSURE_SENSOR): SENSOR_SCHEMA,
            cv.Optional(CONF_FLOW_SENSOR): SENSOR_SCHEMA,
        }
    ),
    _validate_endpoint,
)


async def configure_endpoints(var, config: ConfigType):
    for ep_conf in config[CONF_ENDPOINTS]:
        ref = cg.new_Pvariable(ep_conf[CONF_ID])
        if CONF_ON_OFF_LIGHT_SWITCH in ep_conf:
            cg.add(var.add_on_off_switch(ref))
        elif CONF_DIMMER_SWITCH in ep_conf:
            cg.add(var.add_dimmer_switch(ref))
        elif CONF_TEMPERATURE_SENSOR in ep_conf:
            opts = ep_conf[CONF_TEMPERATURE_SENSOR]
            sens = await cg.get_variable(opts[CONF_SENSOR_ID])
            cg.add(var.add_temperature_sensor(sens, ref))
        elif CONF_ON_OFF_LIGHT in ep_conf:
            light_var = await cg.get_variable(ep_conf[CONF_ON_OFF_LIGHT][CONF_LIGHT_ID])
            cg.add(var.add_on_off_light(light_var, ref))
        elif CONF_DIMMABLE_LIGHT in ep_conf:
            light_var = await cg.get_variable(
                ep_conf[CONF_DIMMABLE_LIGHT][CONF_LIGHT_ID]
            )
            cg.add(var.add_dimmable_light(light_var, ref))
