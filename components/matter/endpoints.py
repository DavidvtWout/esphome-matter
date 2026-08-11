from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import light, sensor
from esphome.const import CONF_ID, CONF_LIGHT_ID, CONF_SENSOR_ID
from esphome.types import ConfigType

from .const import (
    CONF_DIMMABLE_LIGHT,
    CONF_DIMMER_SWITCH,
    CONF_ENDPOINTS,
    CONF_ON_OFF_LIGHT,
    CONF_ON_OFF_SWITCH,
    CONF_TEMPERATURE_SENSOR,
)
from .types import (
    MatterComponent,
    MatterDimAction,
    MatterDimStopAction,
    MatterEndpointRef,
    MatterFactoryResetAction,
    MatterToggleAction,
    MatterTurnOffAction,
    MatterTurnOnAction,
)


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
        elif CONF_ON_OFF_LIGHT in ep_conf:
            light_var = await cg.get_variable(ep_conf[CONF_ON_OFF_LIGHT][CONF_LIGHT_ID])
            cg.add(var.add_on_off_light(light_var, ref))
        elif CONF_DIMMABLE_LIGHT in ep_conf:
            light_var = await cg.get_variable(
                ep_conf[CONF_DIMMABLE_LIGHT][CONF_LIGHT_ID]
            )
            cg.add(var.add_dimmable_light(light_var, ref))


# Accepts both `matter.turn_on: {id: my_endpoint}` and the short form
# `matter.turn_on: my_endpoint`, like the light/switch component actions.
MATTER_CLIENT_ACTION_SCHEMA = automation.maybe_simple_id(
    {
        cv.Required(CONF_ID): cv.use_id(MatterEndpointRef),
    }
)


@automation.register_action(
    "matter.factory_reset",
    MatterFactoryResetAction,
    cv.Schema({cv.GenerateID(): cv.use_id(MatterComponent)}),
)
async def matter_factory_reset_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


async def _matter_client_action_to_code(config, action_id, template_arg):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


@automation.register_action(
    "matter.turn_on", MatterTurnOnAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_turn_on_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action(
    "matter.turn_off", MatterTurnOffAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_turn_off_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action(
    "matter.toggle", MatterToggleAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_toggle_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action(
    "matter.dim_up", MatterDimAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_dim_up_to_code(config, action_id, template_arg, args):
    var = await _matter_client_action_to_code(config, action_id, template_arg)
    cg.add(var.set_direction(0))
    return var


@automation.register_action(
    "matter.dim_down", MatterDimAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_dim_down_to_code(config, action_id, template_arg, args):
    var = await _matter_client_action_to_code(config, action_id, template_arg)
    cg.add(var.set_direction(1))
    return var


@automation.register_action(
    "matter.dim_stop", MatterDimStopAction, MATTER_CLIENT_ACTION_SCHEMA
)
async def matter_dim_stop_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)
