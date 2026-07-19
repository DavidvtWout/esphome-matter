from pathlib import Path

from esphome import automation
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor
from esphome.components.esp32 import add_idf_component, add_idf_sdkconfig_option, require_vfs_select
from esphome.const import CONF_ID, Framework
from esphome.core import CORE
from esphome.coroutine import CoroPriority, coroutine_with_priority
from esphome.helpers import write_file_if_changed

from .kconfig import disable_unused_clusters

CODEOWNERS = ["@DavidvtWout"]

# DEPENDENCIES = ["network"]

CONF_DISCRIMINATOR = "discriminator"
CONF_PASSCODE = "passcode"
CONF_DEVICES = "devices"
CONF_DEVICE_TYPE = "device_type"
CONF_ENDPOINT_ID = "endpoint_id"
CONF_SWITCH_TYPE = "switch_type"
CONF_UP_ID = "up_id"
CONF_DOWN_ID = "down_id"

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
SwitchDeviceType = matter_ns.enum("SwitchDeviceType", is_class=True)


MATTER_DEVICE_TYPES = ["on_off_switch", "dimmer_switch"]


def _validate_device(config):
    dt = config[CONF_DEVICE_TYPE]
    if dt == "on_off_switch":
        for key in (CONF_SWITCH_TYPE, CONF_UP_ID, CONF_DOWN_ID):
            if key in config:
                raise cv.Invalid(f"on_off_switch does not use '{key}'")
        if CONF_ID not in config:
            raise cv.Invalid("on_off_switch requires 'id'")
    elif dt == "dimmer_switch":
        for key in (CONF_SWITCH_TYPE, CONF_ID):
            if key in config:
                raise cv.Invalid(f"dimmer_switch does not use '{key}'")
        for key in (CONF_UP_ID, CONF_DOWN_ID):
            if key not in config:
                raise cv.Invalid(f"dimmer_switch requires '{key}'")
    return config


def _require_vfs_select(config):
    """Register VFS select requirement during config validation."""
    if CORE.is_esp32:
        require_vfs_select()
    return config


DEVICE_SCHEMA = cv.All(
    cv.Schema({
        cv.Optional(CONF_ID): cv.use_id(binary_sensor.BinarySensor),
        cv.Optional(CONF_UP_ID): cv.use_id(binary_sensor.BinarySensor),
        cv.Optional(CONF_DOWN_ID): cv.use_id(binary_sensor.BinarySensor),
        cv.Optional(CONF_ENDPOINT_ID): cv.int_range(min=1, max=0xFFFF),
        cv.Required(CONF_DEVICE_TYPE): cv.one_of(*MATTER_DEVICE_TYPES, lower=True),
    }),
    _validate_device,
    _require_vfs_select, # TODO: Only needed when openthread is enabled
)


def _validate_unique_endpoint_ids(config):
    ids = [d[CONF_ENDPOINT_ID] for d in config.get(CONF_DEVICES, []) if CONF_ENDPOINT_ID in d]
    if len(ids) != len(set(ids)):
        raise cv.Invalid("Duplicate endpoint_id values in matter devices")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(MatterComponent),
        cv.Optional(CONF_DISCRIMINATOR): cv.int_range(min=0, max=4095),
        cv.Optional(CONF_PASSCODE): _validate_passcode,
        cv.Optional(CONF_DEVICES, default=[]): cv.ensure_list(DEVICE_SCHEMA),
    }).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    cv.only_with_framework(Framework.ESP_IDF),
    _validate_unique_endpoint_ids,
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

    for dev_conf in config[CONF_DEVICES]:
        endpoint_id = dev_conf.get(CONF_ENDPOINT_ID, 0)
        dt = dev_conf[CONF_DEVICE_TYPE]
        if dt == "on_off_switch":
            sensor = await cg.get_variable(dev_conf[CONF_ID])
            cg.add(var.add_on_off_switch(sensor, endpoint_id))
        elif dt == "dimmer_switch":
            up_sensor = await cg.get_variable(dev_conf[CONF_UP_ID])
            down_sensor = await cg.get_variable(dev_conf[CONF_DOWN_ID])
            cg.add(var.add_dimmer_switch(up_sensor, down_sensor, endpoint_id))


@automation.register_action(
    "matter.factory_reset",
    MatterFactoryResetAction,
    cv.Schema({cv.GenerateID(): cv.use_id(MatterComponent)}),
)
async def matter_factory_reset_to_code(config, action_id, template_arg, args):
    var = cg.new_Pvariable(action_id, template_arg)
    await cg.register_parented(var, config[CONF_ID])
    return var
