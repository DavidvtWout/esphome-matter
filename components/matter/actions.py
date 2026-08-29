import json
import re

from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import (
    CONF_COMMAND,
    CONF_ID,
    CONF_TYPE,
    CONF_VALUE,
)
from esphome.core import CORE, ID
from esphome.types import ConfigType

from .clusters import MATTER_COMMANDS
from .const import *
from .types import (
    MatterComponent,
    MatterEndpointRef,
    MatterFactoryResetAction,
    MatterSetAttributeAction,
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


# ------------------------------ #
#  matter._set_attribute action  #
# ------------------------------ #

ATTRIBUTE_VALUE_TYPES = {
    "BOOL": (cv.boolean, "esp_matter_bool"),
    "FLOAT": (cv.float_, "esp_matter_float"),
    "I8": (cv.int_range(min=-128, max=127), "esp_matter_int8"),
    "U8": (cv.uint8_t, "esp_matter_uint8"),
    "I16": (cv.int_range(min=-32768, max=32767), "esp_matter_int16"),
    "U16": (cv.uint16_t, "esp_matter_uint16"),
    "I32": (cv.int_range(min=-2147483648, max=2147483647), "esp_matter_int32"),
    "U32": (cv.uint32_t, "esp_matter_uint32"),
    "I64": (
        cv.int_range(min=-9223372036854775808, max=9223372036854775807),
        "esp_matter_int64",
    ),
    "U64": (
        cv.int_range(min=0, max=18446744073709551615),
        "esp_matter_uint64",
    ),
    "ENUM8": (cv.uint8_t, "esp_matter_enum8"),
    "ENUM16": (cv.uint16_t, "esp_matter_enum16"),
    "BITMAP8": (cv.uint8_t, "esp_matter_bitmap8"),
    "BITMAP16": (cv.uint16_t, "esp_matter_bitmap16"),
    "BITMAP32": (cv.uint32_t, "esp_matter_bitmap32"),
}


def _validate_set_attribute(config):
    validator, _ = ATTRIBUTE_VALUE_TYPES[config[CONF_TYPE]]
    config[CONF_VALUE] = validator(config[CONF_VALUE])
    return config


@automation.register_action(
    "matter._set_attribute",
    MatterSetAttributeAction,
    cv.All(
        cv.Schema(
            {
                cv.GenerateID(): cv.declare_id(MatterSetAttributeAction),
                cv.Required(CONF_ENDPOINT_ID): cv.Any(
                    cv.use_id(MatterEndpointRef), cv.uint16_t
                ),
                cv.Required(CONF_CLUSTER_ID): cv.hex_uint32_t,
                cv.Required(CONF_ATTRIBUTE_ID): cv.hex_uint32_t,
                cv.Required(CONF_TYPE): cv.one_of(*ATTRIBUTE_VALUE_TYPES, upper=True),
                cv.Required(CONF_VALUE): object,
            }
        ),
        _validate_set_attribute,
    ),
    synchronous=True,
)
async def matter_set_attribute_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    """The matter._set_attribute action is an escape hatch to set arbitrary attribute values.
    Mainly for debugging purposes so don't use it if you don't know what you're doing.
    """
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cg.add(var.set_cluster_id(config[CONF_CLUSTER_ID]))
    cg.add(var.set_attribute_id(config[CONF_ATTRIBUTE_ID]))
    _, constructor = ATTRIBUTE_VALUE_TYPES[config[CONF_TYPE]]
    value = config[CONF_VALUE]
    if isinstance(value, bool):
        value = str(value).lower()
    cg.add(var.set_value(cg.RawExpression(f"{constructor}({value})")))
    return var


# ------------------------------------------------ #
#  Actions that invoke commands on bound clusters  #
# ------------------------------------------------ #


@automation.register_action(
    "matter._send_command",
    MatterSendCommandAction,
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterSendCommandAction),
            cv.Required(CONF_ENDPOINT_ID): cv.Any(
                cv.use_id(MatterEndpointRef), cv.uint16_t
            ),
            cv.Required(CONF_CLUSTER_ID): cv.hex_uint32_t,
            cv.Required(CONF_COMMAND_ID): cv.hex_uint32_t,
            cv.Required(CONF_DATA): str,
        }
    ),
    synchronous=True,
)
async def matter_send_command_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    """The matter._send_command action is an escape hatch to send arbitrary commands that have not
    yet been implemented by esphome-matter. It doesn't support data formatting so you have to
    provide an esp-matter compatible string yourself.

      matter._send_command:
        endpoint_id: some_endpoint (either esphome id or numerical matter endpoint id)
        cluster_id: 8 # LevelControl
        command_id: 0 # MoveToLevel
        data: '{"0:U8":0,"1:U16":50,"2:U8":0,"3:U8":0}'

    Don't forget to also enable the cluster if it isn't enabled by default:

      esp32:
        framework:
          sdkconfig_options:
            CONFIG_SUPPORT_<cluster_name>_CLUSTER=y  # For example CONFIG_SUPPORT_MICROWAVE_OVEN_CONTROL_CLUSTER

    """
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cg.add(var.set_cluster_id(config[CONF_CLUSTER_ID]))
    cg.add(var.set_command_id(config[CONF_COMMAND_ID]))
    cg.add(var.set_data(config[CONF_DATA]))
    return var


# TODO: matter._send_command_to_node (send command to a single node without using the binding cluster)
# TODO: matter._send_command_to_nodes (send command to multiple node without using the binding cluster)


def register_bound_command_actions():
    """Registers all commands from MATTER_COMMANDS as esphome actions.

    Actions are named after the snake_case cluster and command names:
      matter.cluster_name.command_name

    Commands that have no mandatory fields may be called with only the endpoint_id:
      matter.on_off.on: some_endpoint
    or
      matter.on_off.on:
        endpoint_id: some_endpoint

    Commands that do have mandatory fields must be called like this:
      matter.level_control.move_with_on_off:
        endpoint_id: some_endpoint
        move_mode: 0  # up
        rate: 50      # ~20% per second
    """
    for cluster_name, cluster in MATTER_COMMANDS.items():
        for command_name in cluster[CONF_COMMANDS]:
            automation.register_action(
                f"matter.{_snake_case(cluster_name)}.{_snake_case(command_name)}",
                MatterSendCommandAction,
                _command_schema(cluster_name, command_name),
                synchronous=True,
            )(_make_send_command_to_code(cluster_name, command_name))


def _make_send_command_to_code(cluster_name: str, command_name: str):
    async def to_code(config, action_id: ID, template_arg: cg.TemplateArguments, args):
        return await _new_send_command_action(
            config,
            action_id,
            template_arg,
            cluster_name,
            command_name,
        )

    to_code.__name__ = (
        f"matter_{_snake_case(cluster_name)}_{_snake_case(command_name)}_to_code"
    )
    return to_code


async def _new_send_command_action(
    config: ConfigType,
    action_id: ID,
    template_arg: cg.TemplateArguments,
    cluster_name: str,
    command_name: str,
):
    cluster_id, command_id = _resolve_command_id(cluster_name, command_name)

    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cg.add(var.set_cluster_id(cluster_id))
    cg.add(var.set_command_id(command_id))
    cg.add(var.set_data(_build_data(config, cluster_name, command_name)))
    return var


def _resolve_endpoint_id(endpoint_id: ID | int) -> int:
    if not isinstance(endpoint_id, ID):
        return endpoint_id
    endpoint_ids = CORE.data.get(CONF_MATTER, {}).get(KEY_ENDPOINT_ID_MAP, {})
    if endpoint_id in endpoint_ids:
        return endpoint_ids[endpoint_id]
    raise cv.Invalid(f"Unknown Matter endpoint id '{endpoint_id}'")


def _build_data(config, cluster_name: str, command_name: str) -> str:
    """Creates a date payload that's compatible with esp_matter::client::request_handle.request_data.

    It's JSON formatted crap... Here's an example:

       {"0:U8":0,"1:U16":10}

    This means that the first field is an uint8 with a value of 0 and the second field is uint16 with value 10.
    """
    data = {}

    command = MATTER_COMMANDS[cluster_name][CONF_COMMANDS][command_name]
    for i, field in enumerate(command.get("fields", [])):
        data[f"{i}:{field.type}"] = config[field.key]

    return json.dumps(data)


def _resolve_command_id(cluster_name: str, command_name: str) -> tuple[int, int]:
    """Resolves a cluster and command name to their numerical value.

    e.g.: _resolve_command_id("LevelControl", "StopWithOnOff") -> (8, 7)
    """
    try:
        cluster = MATTER_COMMANDS[cluster_name]
    except KeyError as err:
        raise cv.Invalid(f"Unknown Matter cluster '{cluster_name}'") from err

    try:
        command = cluster["commands"][command_name]
    except KeyError as err:
        raise cv.Invalid(
            f"Unknown Matter command '{cluster_name}.{command_name}'"
        ) from err

    return cluster["id"], command["id"]


def _command_schema(cluster_name: str, command_name: str):
    schema = {
        # TODO: validate endpoint id to exist
        cv.Required(CONF_ENDPOINT_ID): cv.Any(
            cv.uint16_t, cv.use_id(MatterEndpointRef)
        ),
    }

    command = MATTER_COMMANDS[cluster_name][CONF_COMMANDS][command_name]
    has_required = False
    for field in command.get("fields", []):
        schema[field.schema_key] = field.validator
        has_required |= field.required

    if has_required:
        return schema
    else:
        return automation.maybe_conf(CONF_ENDPOINT_ID, schema)


def _snake_case(name):
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()
