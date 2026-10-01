import json
import logging
from collections.abc import Mapping

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.const import (
    CONF_ATTRIBUTE,
    CONF_COMMAND,
    CONF_ID,
    CONF_PATH,
    CONF_VALUE,
)
from esphome.core import CORE, ID
from esphome.types import ConfigType

from .const import *
from .data_model.attributes import Attribute, attribute_value_type
from .data_model.clusters import (
    CLUSTERS,
    CLUSTERS_BY_CONF_KEY,
    CLUSTERS_BY_NAME,
    Cluster,
)
from .data_model.commands import Command
from .data_model.events import Event
from .types import (
    MatterComponent,
    MatterEndpointRef,
    MatterFactoryResetAction,
    MatterSendCommandAction,
    MatterSendEventAction,
    MatterSetAttributeAction,
)
from .util import snake_case

_LOGGER = logging.getLogger(__name__)


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
#  matter.set_attribute                            #
# ------------------------------------------------ #


def get_attribute_from_config(config: Mapping) -> tuple[Cluster, Attribute]:
    cluster = CLUSTERS_BY_CONF_KEY.get(config[CONF_CLUSTER])
    if cluster is None:
        raise cv.Invalid(f"Unknown Matter cluster {config[CONF_CLUSTER]}")
    attribute = cluster.get_attribute(config[CONF_ATTRIBUTE])
    if attribute is None:
        raise cv.Invalid(
            f"Unknown Matter attribute {config[CONF_CLUSTER]}.{config[CONF_ATTRIBUTE]}"
        )
    return cluster, attribute


def _normalize_set_attribute(config):
    if CONF_PATH in config:
        parts = config.pop(CONF_PATH).split(".")
        if len(parts) != 3 or not all(parts):
            raise cv.Invalid(
                "matter.set_attribute path must use the form 'endpoint.cluster.attribute'"
            )
        endpoint, config[CONF_CLUSTER], config[CONF_ATTRIBUTE] = parts
        try:
            config[CONF_ENDPOINT] = cv.uint16_t(endpoint)
        except cv.Invalid:
            config[CONF_ENDPOINT] = cv.use_id(MatterEndpointRef)(endpoint)
    return config


def _validate_set_attribute(config):
    _, attribute = get_attribute_from_config(config)
    if attribute_value_type(attribute) is None:
        raise cv.Invalid(
            f"Matter attribute {config[CONF_CLUSTER]}.{config[CONF_ATTRIBUTE]} "
            "does not have a supported scalar type"
        )
    return config


@automation.register_action(
    "matter.set_attribute",
    MatterSetAttributeAction,
    cv.All(
        cv.Schema(
            {
                cv.Inclusive(CONF_ENDPOINT, "explicit_attribute_path"): cv.Any(
                    cv.use_id(MatterEndpointRef), cv.uint16_t
                ),
                cv.Inclusive(CONF_CLUSTER, "explicit_attribute_path"): cv.string_strict,
                cv.Inclusive(
                    CONF_ATTRIBUTE, "explicit_attribute_path"
                ): cv.string_strict,
                cv.Optional(CONF_PATH): cv.string_strict,
                cv.Required(CONF_VALUE): cv.templatable(lambda value: value),
            }
        ),
        cv.has_exactly_one_key(CONF_PATH, CONF_ENDPOINT),
        _normalize_set_attribute,
        _validate_set_attribute,
    ),
    synchronous=True,
)
async def matter_set_attribute_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    cluster, attribute = get_attribute_from_config(config)
    value_type = attribute_value_type(attribute)
    action_template_arg = cg.TemplateArguments(value_type, *template_arg)
    var = cg.new_Pvariable(action_id, action_template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT])))
    cg.add(var.set_cluster_id(cluster.id))
    cg.add(var.set_attribute_id(attribute.id))
    value = await cg.templatable(config[CONF_VALUE], args, value_type)
    cg.add(var.set_value(value))
    return var


# ------------------------------------------------ #
#  matter.send_command                             #
# ------------------------------------------------ #


def get_command_from_config(config: Mapping) -> Command:
    cluster_key = config[CONF_CLUSTER]
    command_key = config[CONF_COMMAND]
    cluster = CLUSTERS_BY_CONF_KEY.get(cluster_key)
    if cluster is not None:
        command = cluster.get_command(command_key)
        if command is not None:
            return command
    raise cv.Invalid(f"Unknown Matter command {cluster_key}.{command_key}")


def _parse_endpoint(value):
    try:
        return cv.uint16_t(value)
    except cv.Invalid:
        return cv.use_id(MatterEndpointRef)(value)


def _validate_command_name(value):
    # YAML 1.1 parses unquoted "on" and "off" as booleans.
    if isinstance(value, bool):
        return "on" if value else "off"
    return cv.string_strict(value)


def _normalize_send_command(config):
    if CONF_PATH in config:
        parts = config.pop(CONF_PATH).split(".")
        if len(parts) != 3 or not all(parts):
            raise cv.Invalid(
                "matter.send_command path must use the form 'endpoint.cluster.command'"
            )
        endpoint, config[CONF_CLUSTER], config[CONF_COMMAND] = parts
        config[CONF_ENDPOINT] = _parse_endpoint(endpoint)
    return config


def _validate_send_command(config):
    command = get_command_from_config(config)
    config[CONF_ARGUMENTS] = _validate_fields(config[CONF_ARGUMENTS], command.args)
    return config


SEND_COMMAND_SCHEMA = automation.maybe_conf(
    CONF_PATH,
    cv.All(
        cv.Schema(
            {
                cv.Inclusive(CONF_ENDPOINT, "explicit_command_path"): cv.Any(
                    cv.use_id(MatterEndpointRef), cv.uint16_t
                ),
                cv.Inclusive(CONF_CLUSTER, "explicit_command_path"): cv.string_strict,
                cv.Inclusive(
                    CONF_COMMAND, "explicit_command_path"
                ): _validate_command_name,
                cv.Optional(CONF_PATH): cv.string_strict,
                cv.Optional(CONF_ARGUMENTS, default={}): dict,
            }
        ),
        cv.has_exactly_one_key(CONF_PATH, CONF_ENDPOINT),
        _normalize_send_command,
        _validate_send_command,
    ),
)


@automation.register_action(
    "matter.send_command",
    MatterSendCommandAction,
    SEND_COMMAND_SCHEMA,
    synchronous=True,
)
async def matter_send_command_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    command = get_command_from_config(config)
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT])))
    cluster = CLUSTERS_BY_NAME[command.cluster_name]
    cg.add(var.set_cluster_id(cluster.id))
    cg.add(var.set_command_id(command.id))
    cg.add(var.set_data(_build_data(config[CONF_ARGUMENTS], command.args)))
    return var


# ------------------------------------------------ #
#  matter.send_event                               #
# ------------------------------------------------ #


def get_event_from_config(config: Mapping) -> Event:
    cluster_key = config[CONF_CLUSTER]
    event_key = config[CONF_EVENT]
    cluster = CLUSTERS_BY_CONF_KEY.get(cluster_key)
    if cluster is not None:
        event = cluster.get_event(event_key)
        if event is not None:
            return event
    raise cv.Invalid(f"Unknown Matter event {cluster_key}.{event_key}")


def _normalize_send_event(config):
    if CONF_PATH in config:
        parts = config.pop(CONF_PATH).split(".")
        if len(parts) != 3 or not all(parts):
            raise cv.Invalid(
                "matter.send_event path must use the form 'endpoint.cluster.event'"
            )
        endpoint, config[CONF_CLUSTER], config[CONF_EVENT] = parts
        config[CONF_ENDPOINT] = _parse_endpoint(endpoint)
    return config


def _validate_send_event(config):
    event = get_event_from_config(config)
    config[CONF_FIELDS] = _validate_fields(config[CONF_FIELDS], event.fields)
    return config


SEND_EVENT_SCHEMA = automation.maybe_conf(
    CONF_PATH,
    cv.All(
        cv.Schema(
            {
                cv.Inclusive(CONF_ENDPOINT, "explicit_event_path"): cv.Any(
                    cv.use_id(MatterEndpointRef), cv.uint16_t
                ),
                cv.Inclusive(CONF_CLUSTER, "explicit_event_path"): cv.string_strict,
                cv.Inclusive(CONF_EVENT, "explicit_event_path"): cv.string_strict,
                cv.Optional(CONF_PATH): cv.string_strict,
                cv.Optional(CONF_FIELDS, default={}): dict,
            }
        ),
        cv.has_exactly_one_key(CONF_PATH, CONF_ENDPOINT),
        _normalize_send_event,
        _validate_send_event,
    ),
)


@automation.register_action(
    "matter.send_event",
    MatterSendEventAction,
    SEND_EVENT_SCHEMA,
    synchronous=True,
)
async def matter_send_event_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    event = get_event_from_config(config)
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT])))
    cluster = CLUSTERS_BY_NAME[event.cluster_name]
    cg.add(var.set_cluster_id(cluster.id))
    cg.add(var.set_event_id(event.id))
    cg.add(var.set_priority(event.priority))
    cg.add(var.set_data(_build_data(config[CONF_FIELDS], event.fields)))
    return var


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
async def matter_raw_send_command_to_code(
    config: ConfigType, action_id: ID, template_arg, args
):
    """The matter._send_command action is an escape hatch to send arbitrary commands that have not
    yet been implemented by esphome-matter. It doesn't support data formatting, so you have to
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
            CONFIG_SUPPORT_<cluster_name>_CLUSTER=y  # For example, CONFIG_SUPPORT_MICROWAVE_OVEN_CONTROL_CLUSTER

    """
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cg.add(var.set_cluster_id(config[CONF_CLUSTER_ID]))
    cg.add(var.set_command_id(config[CONF_COMMAND_ID]))
    cg.add(var.set_data(config[CONF_DATA]))
    return var


# TODO: matter._send_command_to_node (send command to a single node without using the binding cluster)
# TODO: matter._send_command_to_nodes (send command to multiple node without using the binding cluster)


# ------------------------------------------------ #
#  Legacy send command actions                     #
# ------------------------------------------------ #


def register_bound_command_actions():
    """Registers deprecated per-command compatibility actions.

    Legacy actions are named after the snake_case cluster and command names:
      matter.cluster_name.command_name
    """
    for cluster in CLUSTERS:
        for command in cluster.commands:
            automation.register_action(
                f"matter.{snake_case(cluster.name)}.{snake_case(command.name)}",
                MatterSendCommandAction,
                cv.All(_command_schema(command), _warn_deprecated_command(command)),
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


def _warn_deprecated_command(command: Command):
    old_name = f"matter.{snake_case(command.cluster_name)}.{snake_case(command.name)}"
    new_path = f"{snake_case(command.cluster_name)}.{snake_case(command.name)}"

    def validator(config):
        _LOGGER.warning(
            "The '%s' action is deprecated; use 'matter.send_command' with "
            "cluster/command or path ending in '%s' instead.",
            old_name,
            new_path,
        )
        return config

    return validator


async def _new_send_command_action(
    config: ConfigType,
    action_id: ID,
    template_arg: cg.TemplateArguments,
    command: Command,
):
    var = cg.new_Pvariable(action_id, template_arg)
    cg.add(var.set_endpoint_id(_resolve_endpoint_id(config[CONF_ENDPOINT_ID])))
    cluster = CLUSTERS_BY_NAME[command.cluster_name]
    cg.add(var.set_cluster_id(cluster.id))
    cg.add(var.set_command_id(command.id))
    cg.add(var.set_data(_build_data(config, command.args)))
    return var


def _command_schema(command: Command):
    schema = {
        cv.Required(CONF_ENDPOINT_ID): cv.Any(
            cv.uint16_t, cv.use_id(MatterEndpointRef)
        ),
    }

    has_required = False
    for arg in command.args:
        schema[arg.schema_key] = arg.schema
        if not arg.optional:
            has_required = True

    if has_required:
        return schema
    else:
        return automation.maybe_conf(CONF_ENDPOINT_ID, schema)


# ------------------------------------------------ #
#  Helper functions                                #
# ------------------------------------------------ #


def _validate_fields(values, fields):
    return cv.Schema({field.schema_key: field.schema for field in fields})(values)


def _build_data(values, fields) -> str:
    """Creates a data payload compatible with esp-matter's JSON-to-TLV format.

    It's JSON formatted crap... Here's an example:

       {"0:U8":0,"1:U16":10}

    This means that the first field is an uint8 with a value of 0 and the second field is uint16 with value 10.
    """
    return json.dumps({field.data_key: values[field.schema_key] for field in fields})


def _resolve_endpoint_id(endpoint_id: ID | int) -> int:
    endpoints = CORE.data.get(CONF_MATTER, {}).get(CONF_ENDPOINTS)
    return endpoints.lookup(endpoint_id).endpoint_id
