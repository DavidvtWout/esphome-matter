from pathlib import Path

from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import light, sensor
from esphome.components.esp32 import add_idf_component, add_idf_sdkconfig_option, require_vfs_select
from esphome.const import CONF_ID, CONF_LIGHT_ID, CONF_SENSOR_ID, Framework
from esphome.core import CORE
from esphome.coroutine import CoroPriority, coroutine_with_priority
from esphome.helpers import write_file_if_changed

from .kconfig import disable_unused_clusters

CODEOWNERS = ["@DavidvtWout"]

# DEPENDENCIES = ["network"]

CONF_DISCRIMINATOR = "discriminator"
CONF_PASSCODE = "passcode"
CONF_ENDPOINTS = "endpoints"
CONF_ON_OFF_SWITCH = "on_off_switch"
CONF_DIMMER_SWITCH = "dimmer_switch"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_ON_OFF_LIGHT = "on_off_light"
CONF_DIMMABLE_LIGHT = "dimmable_light"

# Matter spec section 5.1.7.1: these passcodes are explicitly forbidden.
_FORBIDDEN_PASSCODES = {
    11111111, 22222222, 33333333, 44444444, 55555555,
    66666666, 77777777, 88888888, 99999999, 12345678, 87654321,
}


def _validate_passcode(value):
    value = cv.int_(value)
    if not (0 < value <= 99999998) or value in _FORBIDDEN_PASSCODES:
        raise cv.Invalid(
            f"Passcode {value} is not allowed by the Matter specification (section 5.1.7.1)"
        )
    return value


matter_ns = cg.esphome_ns.namespace("matter")
MatterComponent = matter_ns.class_("MatterComponent", cg.Component)
MatterFactoryResetAction = matter_ns.class_("MatterFactoryResetAction", automation.Action)
MatterEndpointRef = matter_ns.class_("MatterEndpointRef")
MatterTurnOnAction = matter_ns.class_("MatterTurnOnAction", automation.Action)
MatterTurnOffAction = matter_ns.class_("MatterTurnOffAction", automation.Action)
MatterToggleAction = matter_ns.class_("MatterToggleAction", automation.Action)
MatterDimAction = matter_ns.class_("MatterDimAction", automation.Action)
MatterDimStopAction = matter_ns.class_("MatterDimStopAction", automation.Action)


def _require_vfs_select(config):
    """Register VFS select requirement during config validation."""
    if CORE.is_esp32:
        require_vfs_select()
    return config


def _none_to_dict(value):
    """Allow a bare `on_off_switch:` (no options)."""
    return {} if value is None else value


# Client switch endpoints take no options: they only define the Matter device
# type (clusters + Binding). Behaviour is wired in YAML automations using the
# matter.* actions, referencing the endpoint's id.
ON_OFF_SWITCH_SCHEMA = cv.All(_none_to_dict, cv.Schema({}))

DIMMER_SWITCH_SCHEMA = cv.All(_none_to_dict, cv.Schema({}))

TEMPERATURE_SENSOR_SCHEMA = cv.Schema({
    cv.Required(CONF_SENSOR_ID): cv.use_id(sensor.Sensor),
})

LIGHT_SCHEMA = cv.Schema({
    cv.Required(CONF_LIGHT_ID): cv.use_id(light.LightState),
})


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
# or reordered once the device is commissioned — append only.
ENDPOINT_SCHEMA = cv.All(
    cv.Schema({
        # Referenceable from matter.* actions via endpoint_ref.
        cv.GenerateID(): cv.declare_id(MatterEndpointRef),
        cv.Optional(CONF_ON_OFF_SWITCH): ON_OFF_SWITCH_SCHEMA,
        cv.Optional(CONF_DIMMER_SWITCH): DIMMER_SWITCH_SCHEMA,
        cv.Optional(CONF_TEMPERATURE_SENSOR): TEMPERATURE_SENSOR_SCHEMA,
        cv.Optional(CONF_ON_OFF_LIGHT): LIGHT_SCHEMA,
        cv.Optional(CONF_DIMMABLE_LIGHT): LIGHT_SCHEMA,
    }),
    _validate_endpoint,
)

CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(MatterComponent),
        cv.Optional(CONF_DISCRIMINATOR): cv.int_range(min=0, max=4095),
        cv.Optional(CONF_PASSCODE): _validate_passcode,
        cv.Optional(CONF_ENDPOINTS, default=[]): cv.ensure_list(ENDPOINT_SCHEMA),
    }).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    cv.only_with_framework(Framework.ESP_IDF),
    _require_vfs_select,  # TODO: Only needed when openthread is enabled
)

# Wifi, ethernet and thread run at COMMUNICATION priority. Matter needs to start just after that and
# NETWORK_SERVICES is the next CoroPriority so we choose that one.
@coroutine_with_priority(CoroPriority.NETWORK_SERVICES)
async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    # The 1.4.0 tag is too far behind and doesn't include some essential bug-fixes. For now I pinned a specific
    # commit but in the future the release/v1.4 branch should probably be pinned.
    add_idf_component(
        name="espressif/esp_matter",
        repo="https://github.com/espressif/esp-matter",
        ref="88cdc085f95cc9d806608e2ddd9ca6d2e6224ce6"
    )

    # esp_matter's CMakeLists.txt defaults EXECUTABLE_COMPONENT_NAME to "main", but
    # PlatformIO names the app component "src". We write the project CMakeLists.txt
    # ourselves with the correct variable before PlatformIO gets a chance to create it
    # (PlatformIO only generates CMakeLists.txt when the file doesn't already exist).
    cmake_path = CORE.relative_build_path("CMakeLists.txt")
    cmake_path.parent.mkdir(parents=True, exist_ok=True)
    write_file_if_changed(
        cmake_path,
        "cmake_minimum_required(VERSION 3.16.0)\n"
        'set(EXECUTABLE_COMPONENT_NAME "src")\n'
        'include($ENV{IDF_PATH}/tools/cmake/project.cmake)\n'
        f"project({CORE.name})\n",
    )

    cg.add_define("USE_MATTER")

    if CONF_DISCRIMINATOR in config:
        cg.add_define("MATTER_DISCRIMINATOR", config[CONF_DISCRIMINATOR])
    if CONF_PASSCODE in config:
        cg.add_define("MATTER_PASSCODE", config[CONF_PASSCODE])

    # has_wifi = "wifi" in CORE.loaded_integrations
    # has_ethernet = "ethernet" in CORE.loaded_integrations
    # has_openthread = "openthread" in CORE.loaded_integrations

    enable_ble = True
    enable_openthread = True
    enable_wifi = False

    # TODO: use CORE.data?
    if enable_ble:
        add_idf_sdkconfig_option("CONFIG_BT_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_BT_BLUEDROID_ENABLED", False)
        add_idf_sdkconfig_option("CONFIG_BT_NIMBLE_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_BT_NIMBLE_ENABLE_CONN_REATTEMPT", False)
        # TODO: set USE_BLE_ONLY_FOR_COMMISSIONING to false if other esphome components need it?

    add_idf_sdkconfig_option("CONFIG_USE_MINIMAL_MDNS", False)
    add_idf_sdkconfig_option("CONFIG_ENABLE_EXTENDED_DISCOVERY", True)

    add_idf_sdkconfig_option("CONFIG_ENABLE_WIFI_AP", False)
    add_idf_sdkconfig_option("CONFIG_ENABLE_WIFI_STATION", enable_wifi)

    if enable_openthread:
        add_idf_sdkconfig_option("CONFIG_ESP_MATTER_ENABLE_OPENTHREAD", True)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_SRP_CLIENT", True)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_DNS_CLIENT", True)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_CLI", False)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_CONSOLE_ENABLE", False)
        add_idf_sdkconfig_option("CONFIG_ENABLE_MATTER_OVER_THREAD", True)
        add_idf_sdkconfig_option("CONFIG_ENABLE_CHIP_DATA_MODEL", True)

        add_idf_sdkconfig_option("CONFIG_LWIP_IPV6_NUM_ADDRESSES", 6)
        add_idf_sdkconfig_option("CONFIG_LWIP_HOOK_IP6_ROUTE_DEFAULT", True)
        add_idf_sdkconfig_option("CONFIG_LWIP_HOOK_ND6_GET_GW_DEFAULT", True)
        add_idf_sdkconfig_option("CONFIG_LWIP_MULTICAST_PING", True)
        add_idf_sdkconfig_option("CONFIG_LWIP_IPV4", False)
        add_idf_sdkconfig_option("CONFIG_DISABLE_IPV4", True)  # chip core

    disable_unused_clusters()

    # TODO: ENABLE_ESP32_FACTORY_DATA_PROVIDER?

    # TODO: stop api from restarting device in commissioning mode?

    # CHIP's mbedTLS crypto backend calls mbedtls_hkdf() (CHIPCryptoPALmbedTLS.cpp).
    # ESP-IDF's mbedTLS disables HKDF by default; enabling this compiles mbedtls/hkdf.c
    # into the mbedTLS library so the symbol is present at link time.
    add_idf_sdkconfig_option("CONFIG_MBEDTLS_HKDF_C", True)

    # connectedhomeip's GN build sets CHIP_HAVE_CONFIG_H=1 for all its sources (src/BUILD.gn).
    # Without it, SystemConfig.h can't find the GN-generated SystemBuildConfig.h and
    # CHIPDeviceBuildConfig.h that live in the chip component's binary dir (already in
    # PlatformIO's CPPPATH via the chip CMakeLists.txt INTERFACE include_directories).
    # Adding this define to PlatformIO's src compilation makes CHIP headers work when
    # included from our ESPHome component files.
    cg.add_build_flag("-DCHIP_HAVE_CONFIG_H=1")

    # TODO: probably not needed?
    cg.add_build_flag("-DCHIP_CRYPTO_KEYSTORE_RAW=1")

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
            light_var = await cg.get_variable(ep_conf[CONF_DIMMABLE_LIGHT][CONF_LIGHT_ID])
            cg.add(var.add_dimmable_light(light_var, ref))


@automation.register_action(
    "matter.factory_reset",
    MatterFactoryResetAction,
    cv.Schema({cv.GenerateID(): cv.use_id(MatterComponent)}),
)
async def matter_factory_reset_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


# Accepts both `matter.turn_on: {id: my_endpoint}` and the short form
# `matter.turn_on: my_endpoint`, like the light/switch component actions.
MATTER_CLIENT_ACTION_SCHEMA = automation.maybe_simple_id({
    cv.Required(CONF_ID): cv.use_id(MatterEndpointRef),
})


async def _matter_client_action_to_code(config, action_id, template_arg):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var


@automation.register_action("matter.turn_on", MatterTurnOnAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_turn_on_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action("matter.turn_off", MatterTurnOffAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_turn_off_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action("matter.toggle", MatterToggleAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_toggle_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)


@automation.register_action("matter.dim_up", MatterDimAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_dim_up_to_code(config, action_id, template_arg, args):
    var = await _matter_client_action_to_code(config, action_id, template_arg)
    cg.add(var.set_direction(0))
    return var


@automation.register_action("matter.dim_down", MatterDimAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_dim_down_to_code(config, action_id, template_arg, args):
    var = await _matter_client_action_to_code(config, action_id, template_arg)
    cg.add(var.set_direction(1))
    return var


@automation.register_action("matter.dim_stop", MatterDimStopAction, MATTER_CLIENT_ACTION_SCHEMA)
async def matter_dim_stop_to_code(config, action_id, template_arg, args):
    return await _matter_client_action_to_code(config, action_id, template_arg)
