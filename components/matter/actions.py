import json
from wsgiref import validate

from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import (
    CONF_COMMAND,
    CONF_ID,
    CONF_VALUE,
)
from esphome.core import CORE, ID
from esphome.types import ConfigType

from .const import *
from .data_model import COMMANDS, CLUSTER_NAME_TO_ID, Command
from .types import (
    MatterComponent,
    MatterEndpointRef,
    MatterFactoryResetAction,
    MatterSendCommandAction,
)
from .util import snake_case


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
    for command in COMMANDS:
        automation.register_action(
            f"matter.{snake_case(command.cluster_name)}.{snake_case(command.name)}",
            MatterSendCommandAction,
            _command_schema(command),
            synchronous=True,
        )(_make_send_command_to_code(command))


def _make_send_command_to_code(command: Command):
    async def to_code(config, action_id: ID, template_arg: cg.TemplateArguments, args):
        return await _new_send_command_action(
            config,
            action_id,
            template_arg,
            command,
        )

    to_code.__name__ = (
        f"matter_{snake_case(command.cluster_name)}_{snake_case(command.name)}_to_code"
    )
    return to_code


async def _new_send_command_action(
    config: ConfigType,
    action_id: ID,
    template_arg: cg.TemplateArguments,
    command: Command,
):
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cg.add(var.set_cluster_id(CLUSTER_NAME_TO_ID[command.cluster_name]))
    cg.add(var.set_command_id(command.id))
    cg.add(var.set_data(_build_data(config, command)))
    return var


def _resolve_endpoint_id(endpoint_id: ID | int) -> int:
    if not isinstance(endpoint_id, ID):
        return endpoint_id
    endpoint_ids = CORE.data.get(CONF_MATTER, {}).get(KEY_ENDPOINT_ID_MAP, {})
    if endpoint_id in endpoint_ids:
        return endpoint_ids[endpoint_id]
    raise cv.Invalid(f"Unknown Matter endpoint id '{endpoint_id}'")


def _build_data(config, command: Command) -> str:
    """Creates a date payload that's compatible with esp_matter::client::request_handle.request_data.

    It's JSON formatted crap... Here's an example:

       {"0:U8":0,"1:U16":10}

    This means that the first field is an uint8 with a value of 0 and the second field is uint16 with value 10.
    """
    data = {}

    for arg in command.args:
        data[arg.data_key] = config[arg.conf_key]

    return json.dumps(data)


def _command_schema(command: Command):
    schema = {
        # TODO: validate endpoint id to exist
        cv.Required(CONF_ENDPOINT_ID): cv.Any(
            cv.uint16_t, cv.use_id(MatterEndpointRef)
        ),
    }

    has_required = False
    for arg in command.args:
        validator = cv.int_range(min=-0x80000000, max=0x7FFFFFFF)  # TODO
        if not arg.optional:
            schema[cv.Required(arg.conf_key)] = validator
            has_required = True
        if arg.default is not None:
            schema[cv.Optional(arg.conf_key, default=arg.default)] = validator
        else:
            schema[cv.Optional(arg.conf_key)] = validator

    if has_required:
        return schema
    else:
        return automation.maybe_conf(CONF_ENDPOINT_ID, schema)
