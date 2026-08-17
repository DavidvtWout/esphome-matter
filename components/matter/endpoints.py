from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate, light, sensor
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


def _none_to_dict(value):
    """Allow a bare `on_off_switch:` (no options)."""
    return {} if value is None else value


# Client switch endpoints take no options: they only define the Matter device
# type (clusters + Binding). Behaviour is wired in YAML automations using the
# matter.* actions, referencing the endpoint's id.
ON_OFF_SWITCH_SCHEMA = cv.All(_none_to_dict, cv.Schema({}))

DIMMER_SWITCH_SCHEMA = cv.All(_none_to_dict, cv.Schema({}))

TEMPERATURE_SENSOR_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_SENSOR_ID): cv.use_id(sensor.Sensor),
    }
)

LIGHT_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_LIGHT_ID): cv.use_id(light.LightState),
    }
)

THERMOSTAT_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_CLIMATE_ID): cv.use_id(climate.Climate),
    }
)


def _validate_endpoint(config):
    device_types = [k for k in config if k != CONF_ID]
    if len(device_types) != 1:
        raise cv.Invalid(
            "Each endpoint must have exactly one device type "
            "(multiple device types per endpoint are not supported yet)"
        )
    return config


# Each list entry is one Matter endpoint; the key selects the device type.
# Endpoint ids are assigned in list order, so entries must never be removed
# or reordered once the device is commissioned; append only.
ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            # Referenceable from matter.* actions via endpoint_ref.
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_ON_OFF_SWITCH): ON_OFF_SWITCH_SCHEMA,
            cv.Optional(CONF_DIMMER_SWITCH): DIMMER_SWITCH_SCHEMA,
            cv.Optional(CONF_TEMPERATURE_SENSOR): TEMPERATURE_SENSOR_SCHEMA,
            cv.Optional(CONF_THERMOSTAT): THERMOSTAT_SCHEMA,
            cv.Optional(CONF_ON_OFF_LIGHT): LIGHT_SCHEMA,
            cv.Optional(CONF_DIMMABLE_LIGHT): LIGHT_SCHEMA,
        }
    ),
    _validate_endpoint,
)


async def configure_endpoints(var, config: ConfigType):
    for ep_conf in config[CONF_ENDPOINTS]:
        ref = cg.new_Pvariable(ep_conf[CONF_ID])
        if CONF_ON_OFF_SWITCH in ep_conf:
            cg.add(var.add_on_off_switch(ref))
        elif CONF_DIMMER_SWITCH in ep_conf:
            cg.add(var.add_dimmer_switch(ref))
        elif CONF_TEMPERATURE_SENSOR in ep_conf:
            opts = ep_conf[CONF_TEMPERATURE_SENSOR]
            sens = await cg.get_variable(opts[CONF_SENSOR_ID])
            cg.add(var.add_temperature_sensor(sens, ref))
        elif CONF_THERMOSTAT in ep_conf:
            opts = ep_conf[CONF_THERMOSTAT]
            climate_var = await cg.get_variable(opts[CONF_CLIMATE_ID])
            cg.add(var.add_thermostat(climate_var, ref))
        elif CONF_ON_OFF_LIGHT in ep_conf:
            light_var = await cg.get_variable(ep_conf[CONF_ON_OFF_LIGHT][CONF_LIGHT_ID])
            cg.add(var.add_on_off_light(light_var, ref))
        elif CONF_DIMMABLE_LIGHT in ep_conf:
            light_var = await cg.get_variable(
                ep_conf[CONF_DIMMABLE_LIGHT][CONF_LIGHT_ID]
            )
            cg.add(var.add_dimmable_light(light_var, ref))
