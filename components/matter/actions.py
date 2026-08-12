import json
import re

from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import (
    CONF_COMMAND,
    CONF_ID,
    CONF_VALUE,
)
from esphome.core import ID

from .clusters import MATTER_COMMANDS
from .const import *
from .types import (
    MatterComponent,
    MatterEndpointRef,
    MatterFactoryResetAction,
    MatterSendCommandAction,
)


@automation.register_action(
    "matter.factory_reset",
    MatterFactoryResetAction,
    cv.Schema({cv.GenerateID(): cv.use_id(MatterComponent)}),
    synchronous=True,
)
async def matter_factory_reset_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


# ------------------------------------------------ #
#  Actions that invoke commands on bound clusters  #
# ------------------------------------------------ #


def _resolve_cluster_id(cluster_id: int | str) -> int:
    if isinstance(cluster_id, str):
        try:
            return MATTER_COMMANDS[cluster_id]["id"]
        except KeyError as err:
            raise cv.Invalid(f"Unknown Matter cluster '{cluster_id}'") from err
    return cluster_id


def _resolve_command_id(cluster_id: int | str, command_id: int | str) -> int:
    if not isinstance(command_id, str):
        return command_id
    cluster_id = _resolve_cluster_id(cluster_id)
    for cluster in MATTER_COMMANDS.values():
        if cluster["id"] == cluster_id:
            try:
                return cluster["commands"][command_id]["id"]
            except KeyError as err:
                raise cv.Invalid(
                    f"Unknown Matter command '{command_id}' for cluster 0x{cluster_id:04X}"
                ) from err
    raise cv.Invalid("Command names require a known cluster name or ID")


def _command_spec(cluster_id: int | str, command_id: int | str) -> dict | None:
    cluster_id = _resolve_cluster_id(cluster_id)
    command_id = _resolve_command_id(cluster_id, command_id)
    for cluster in MATTER_COMMANDS.values():
        if cluster["id"] != cluster_id:
            continue
        for command in cluster["commands"].values():
            if command["id"] == command_id:
                return command
    return None


def _field_validator(field_type: str):
    try:
        return {
            "U8": cv.uint8_t,
            "U16": cv.uint16_t,
            "U32": cv.uint32_t,
            "I8": cv.int_range(min=-128, max=127),
            "I16": cv.int_range(min=-32768, max=32767),
            "I32": cv.int_range(min=-2147483648, max=2147483647),
        }[field_type]
    except KeyError as err:
        raise cv.Invalid(f"Unsupported Matter field type '{field_type}'") from err


def _build_payload(spec: dict, value) -> str:
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

    payload = {}
    for i, field in enumerate(fields):
        if field["key"] in value:
            field_value = value[field["key"]]
        elif field["default"] is not None:
            field_value = field["default"]
        else:
            raise cv.Invalid(f"Missing value field '{field['key']}'")
        field_type = field["type"]
        payload[f"{i}:{field_type}"] = _field_validator(field_type)(field_value)
    return json.dumps(payload)


def _validate_invoke_bound_command(config):
    config = dict(config)
    cluster_id = _resolve_cluster_id(config[CONF_CLUSTER_ID])
    command_id = _resolve_command_id(cluster_id, config[CONF_COMMAND])
    config[CONF_CLUSTER_ID] = cluster_id
    config[CONF_COMMAND_ID] = command_id
    config[CONF_PAYLOAD] = _build_payload(
        _command_spec(cluster_id, command_id), config.get(CONF_VALUE)
    )
    return config


def _command_schema(cluster_name: str, command_name: str):
    schema = {
        cv.Required(CONF_ENDPOINT_ID): cv.use_id(MatterEndpointRef),
    }
    for field in MATTER_COMMANDS[cluster_name][CONF_COMMANDS][command_name].get(
        "fields", []
    ):
        key = field["key"]
        validator = _field_validator(field["type"])
        if field["default"] is None:
            schema[cv.Required(key)] = validator
        else:
            schema[cv.Optional(key, default=field["default"])] = validator
    return automation.maybe_conf(CONF_ENDPOINT_ID, schema)


def _payload_from_action_config(
    config, cluster_id: int | str, command_id: int | str, default_value=None
):
    spec = _command_spec(cluster_id, command_id)
    field_keys = (
        [] if spec is None else [field["key"] for field in spec.get("fields", [])]
    )
    direct_value = {key: config[key] for key in field_keys if key in config}

    if CONF_VALUE in config:
        value = config[CONF_VALUE]
        if direct_value:
            if not isinstance(value, dict):
                raise cv.Invalid(
                    "Direct command fields can only be combined with a dict value"
                )
            value = {**value, **direct_value}
    elif direct_value:
        value = {**(default_value or {}), **direct_value}
    else:
        value = default_value

    return _build_payload(spec, value)


async def _new_send_command_action(
    config,
    action_id: ID,
    template_arg: cg.TemplateArguments,
    cluster_id: int | str,
    command_id: int | str,
    default_value=None,
):
    var = cg.new_Pvariable(action_id, template_arg)
    # TODO: set endpoint_id instead of endpoint_ref
    endpoint_ref = await cg.get_variable(config[CONF_ENDPOINT_ID])
    cg.add(var.set_endpoint_ref(endpoint_ref))
    cg.add(var.set_cluster_id(_resolve_cluster_id(cluster_id)))
    cg.add(var.set_command_id(_resolve_command_id(cluster_id, command_id)))
    cg.add(
        var.set_payload(
            _payload_from_action_config(config, cluster_id, command_id, default_value)
        )
    )
    return var


def _snake_case(name):
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def register_bound_command_actions():
    for cluster_name, cluster in MATTER_COMMANDS.items():
        for command_name in cluster[CONF_COMMANDS]:
            action_name = (
                f"matter.{_snake_case(cluster_name)}.{_snake_case(command_name)}"
            )

            async def to_code(
                config, action_id: ID, template_arg: cg.TemplateArguments, args
            ):
                return await _new_send_command_action(
                    config,
                    action_id,
                    template_arg,
                    cluster_name,
                    command_name,
                )

            to_code.__name__ = f"matter_{_snake_case(cluster_name)}_{_snake_case(command_name)}_to_code"
            automation.register_action(
                action_name,
                MatterSendCommandAction,
                _command_schema(cluster_name, command_name),
                synchronous=True,
            )(to_code)


SEND_COMMAND_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterSendCommandAction),
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
    "matter._send_command",
    MatterSendCommandAction,
    SEND_COMMAND_SCHEMA,
    synchronous=True,
)
async def matter_send_command_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    endpoint_id = config[CONF_ENDPOINT_ID]
    if isinstance(endpoint_id, ID):
        endpoint_ref = await cg.get_variable(endpoint_id)
        cg.add(var.set_endpoint_ref(endpoint_ref))
    else:
        cg.add(var.set_endpoint_id(endpoint_id))
    cg.add(var.set_cluster_id(config[CONF_CLUSTER_ID]))
    cg.add(var.set_command_id(config[CONF_COMMAND_ID]))
    cg.add(var.set_payload(config[CONF_PAYLOAD]))
    return var


# TODO: matter._send_command_to_node (send command to a single node without using the binding cluster)
# TODO: matter._send_command_to_nodes (send commands to multiple node without using the binding cluster)


def _send_command_schema(*fields):
    schema = {
        cv.Required(CONF_ENDPOINT_ID): cv.use_id(MatterEndpointRef),
    }
    for field in fields:
        schema[cv.Optional(field)] = cv.uint32_t
    return automation.maybe_conf(CONF_ENDPOINT_ID, schema)


@automation.register_action(
    "matter.turn_off",
    MatterSendCommandAction,
    _send_command_schema(),
    synchronous=True,
)
async def matter_turn_off_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config, action_id, template_arg, CLUSTER_ON_OFF, COMMAND_OFF
    )


@automation.register_action(
    "matter.turn_on",
    MatterSendCommandAction,
    _send_command_schema(),
    synchronous=True,
)
async def matter_turn_on_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config, action_id, template_arg, CLUSTER_ON_OFF, COMMAND_ON
    )


@automation.register_action(
    "matter.toggle",
    MatterSendCommandAction,
    _send_command_schema(),
    synchronous=True,
)
async def matter_toggle_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config, action_id, template_arg, CLUSTER_ON_OFF, COMMAND_TOGGLE
    )


@automation.register_action(
    "matter.dim_up",
    MatterSendCommandAction,
    _send_command_schema(FIELD_RATE),
    synchronous=True,
)
async def matter_dim_up_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config,
        action_id,
        template_arg,
        CLUSTER_LEVEL_CONTROL,
        COMMAND_MOVE_WITH_ON_OFF,
        {"move_mode": 0, FIELD_RATE: 50},
    )


@automation.register_action(
    "matter.dim_down",
    MatterSendCommandAction,
    _send_command_schema(FIELD_RATE),
    synchronous=True,
)
async def matter_dim_down_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config,
        action_id,
        template_arg,
        CLUSTER_LEVEL_CONTROL,
        COMMAND_MOVE_WITH_ON_OFF,
        {"move_mode": 1, FIELD_RATE: 50},
    )


@automation.register_action(
    "matter.dim_stop",
    MatterSendCommandAction,
    _send_command_schema(),
    synchronous=True,
)
async def matter_dim_stop_to_code(config, action_id, template_arg, args):
    return await _new_send_command_action(
        config,
        action_id,
        template_arg,
        CLUSTER_LEVEL_CONTROL,
        COMMAND_STOP_WITH_ON_OFF,
    )
