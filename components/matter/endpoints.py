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
    MatterInvokeBoundCommandAction,
    MatterToggleAction,
    MatterTurnOffAction,
    MatterTurnOnAction,
)


CONF_CLUSTER_ID = "cluster_id"
CONF_COMMAND_ID = "command_id"
CONF_ENDPOINT_ID = "endpoint_id"


def _field(tag, key, default=None):
    return {"tag": tag, "key": key, "default": default}


MATTER_BOUND_COMMANDS = {
    "Identify": {
        "id": 0x0003,
        "commands": {
            "Identify": {
                "id": 0x00,
                "fields": [_field("0:U16", "identify_time")],
            },
            "TriggerEffect": {
                "id": 0x40,
                "fields": [
                    _field("0:U8", "effect_identifier"),
                    _field("1:U8", "effect_variant", 0),
                ],
            },
        },
    },
    "OnOff": {
        "id": 0x0006,
        "commands": {
            "Off": {"id": 0x00},
            "On": {"id": 0x01},
            "Toggle": {"id": 0x02},
            "OffWithEffect": {
                "id": 0x40,
                "fields": [
                    _field("0:U8", "effect_identifier"),
                    _field("1:U8", "effect_variant", 0),
                ],
            },
            "OnWithRecallGlobalScene": {"id": 0x41},
            "OnWithTimedOff": {
                "id": 0x42,
                "fields": [
                    _field("0:U8", "on_off_control", 0),
                    _field("1:U16", "on_time"),
                    _field("2:U16", "off_wait_time", 0),
                ],
            },
        },
    },
    "LevelControl": {
        "id": 0x0008,
        "commands": {
            # "MoveToLevel": {"id": 0x00},
            # "Move": {"id": 0x01},
            # "Step": {"id": 0x02},
            # "Stop": {"id": 0x03},
            # "MoveToLevelWithOnOff": {"id": 0x04},
            "MoveWithOnOff": {
                "id": 0x05,
                "fields": [
                    _field("0:U8", "move_mode"),
                    _field("1:U8", "rate", 50),
                    _field("2:U8", "options_mask", 0),
                    _field("3:U8", "options_override", 0),
                ],
            },
            # "StepWithOnOff": {"id": 0x06},
            "StopWithOnOff": {
                "id": 0x07,
                "fields": [
                    _field("0:U8", "options_mask", 0),
                    _field("1:U8", "options_override", 0),
                ],
            },
            # "MoveToClosestFrequency": {"id": 0x08},
        },
    },
    "ColorControl": {
        "id": 0x0300,
        "commands": {
            "MoveToHue": {
                "id": 0x00,
                "fields": [
                    _field("0:U8", "hue"),
                    _field("1:U8", "direction", 0),
                    _field("2:U16", "transition_time", 0),
                    _field("3:U8", "options_mask", 0),
                    _field("4:U8", "options_override", 0),
                ],
            },
            "MoveHue": {
                "id": 0x01,
                "fields": [
                    _field("0:U8", "move_mode"),
                    _field("1:U8", "rate", 50),
                    _field("2:U8", "options_mask", 0),
                    _field("3:U8", "options_override", 0),
                ],
            },
            # "StepHue": {"id": 0x02},
            "MoveToSaturation": {
                "id": 0x03,
                "fields": [
                    _field("0:U8", "saturation"),
                    _field("1:U16", "transition_time", 0),
                    _field("2:U8", "options_mask", 0),
                    _field("3:U8", "options_override", 0),
                ],
            },
            "MoveSaturation": {
                "id": 0x04,
                "fields": [
                    _field("0:U8", "move_mode"),
                    _field("1:U8", "rate", 50),
                    _field("2:U8", "options_mask", 0),
                    _field("3:U8", "options_override", 0),
                ],
            },
            # "StepSaturation": {"id": 0x05},
            "MoveToHueAndSaturation": {
                "id": 0x06,
                "fields": [
                    _field("0:U8", "hue"),
                    _field("1:U8", "saturation"),
                    _field("2:U16", "transition_time", 0),
                    _field("3:U8", "options_mask", 0),
                    _field("4:U8", "options_override", 0),
                ],
            },
            # "MoveToColor": {"id": 0x07},
            # "MoveColor": {"id": 0x08},
            # "StepColor": {"id": 0x09},
            "MoveToColorTemperature": {
                "id": 0x0A,
                "fields": [
                    _field("0:U16", "color_temperature_mireds"),
                    _field("1:U16", "transition_time", 0),
                    _field("2:U8", "options_mask", 0),
                    _field("3:U8", "options_override", 0),
                ],
            },
            # "EnhancedMoveToHue": {"id": 0x40},
            # "EnhancedMoveHue": {"id": 0x41},
            # "EnhancedStepHue": {"id": 0x42},
            # "EnhancedMoveToHueAndSaturation": {"id": 0x43},
            # "ColorLoopSet": {"id": 0x44},
            "StopMoveStep": {"id": 0x47},
            # "MoveColorTemperature": {"id": 0x4B},
            # "StepColorTemperature": {"id": 0x4C},
        },
    },
}


def _resolve_cluster_id(value):
    if isinstance(value, str):
        try:
            return MATTER_BOUND_COMMANDS[value]["id"]
        except KeyError as err:
            raise cv.Invalid(f"Unknown Matter cluster '{value}'") from err
    return value


def _resolve_command_id(cluster_id, value):
    if not isinstance(value, str):
        return value
    for cluster in MATTER_BOUND_COMMANDS.values():
        if cluster["id"] == cluster_id:
            try:
                return cluster["commands"][value]["id"]
            except KeyError as err:
                raise cv.Invalid(
                    f"Unknown Matter command '{value}' for cluster 0x{cluster_id:04X}"
                ) from err
    raise cv.Invalid("Command names require a known cluster name or ID")


def _command_spec(cluster_id, command_id):
    for cluster in MATTER_BOUND_COMMANDS.values():
        if cluster["id"] != cluster_id:
            continue
        for command in cluster["commands"].values():
            if command["id"] == command_id:
                return command
    return None


def _build_payload(spec, value):
    if value is None:
        value = {}
    if isinstance(value, str):
        return value

    fields = [] if spec is None else spec.get("fields", [])
    if not fields:
        if value not in ({}, None):
            raise cv.Invalid("This command does not take a value")
        return "{}"

    if not isinstance(value, dict):
        value = {fields[0]["key"]: value}

    entries = []
    for field in fields:
        if field["key"] in value:
            field_value = value[field["key"]]
        elif field["default"] is not None:
            field_value = field["default"]
        else:
            raise cv.Invalid(f"Missing value field '{field['key']}'")
        entries.append(f'"{field["tag"]}": {cv.uint32_t(field_value)}')
    return "{" + ", ".join(entries) + "}"


def _validate_invoke_bound_command(config):
    config = dict(config)
    cluster_id = _resolve_cluster_id(config[CONF_CLUSTER_ID])
    command_id = _resolve_command_id(cluster_id, config[CONF_COMMAND])
    config[CONF_CLUSTER_ID] = cluster_id
    config[CONF_COMMAND_ID] = command_id
    config["payload"] = _build_payload(
        _command_spec(cluster_id, command_id), config.get(CONF_VALUE)
    )
    return config


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

INVOKE_BOUND_COMMAND_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterInvokeBoundCommandAction),
            cv.Required(CONF_ENDPOINT_ID): cv.Any(
                cv.uint16_t, cv.use_id(MatterEndpointRef)
            ),
            cv.Required(CONF_CLUSTER_ID): cv.Any(str, cv.hex_uint32_t),
            cv.Required(CONF_COMMAND): cv.Any(str, cv.hex_uint32_t),
            cv.Optional(CONF_VALUE): cv.Any(str, cv.uint32_t, dict),
        }
    ),
    _validate_invoke_bound_command,
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


@automation.register_action(
    "matter._invoke_bound_command",
    MatterInvokeBoundCommandAction,
    INVOKE_BOUND_COMMAND_SCHEMA,
)
async def matter_invoke_bound_command_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    endpoint_id = config[CONF_ENDPOINT_ID]
    if isinstance(endpoint_id, ID):
        endpoint_ref = await cg.get_variable(endpoint_id)
        cg.add(var.set_endpoint_ref(endpoint_ref))
    else:
        cg.add(var.set_endpoint_id(endpoint_id))
    cg.add(var.set_cluster_id(config[CONF_CLUSTER_ID]))
    cg.add(var.set_command_id(config[CONF_COMMAND_ID]))
    cg.add(var.set_payload(config["payload"]))
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
