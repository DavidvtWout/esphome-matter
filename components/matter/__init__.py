import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import (
    add_idf_component,
    add_idf_sdkconfig_option,
    require_vfs_select,
)
from esphome.const import (
    CONF_ENABLE_IPV6,
    CONF_ID,
    Framework,
    __version__ as ESPHOME_VERSION,
)
from esphome.core import CORE
from esphome.coroutine import CoroPriority, coroutine_with_priority
import esphome.final_validate as fv
from esphome.types import ConfigType

from .actions import register_bound_command_actions
from .endpoints import ENDPOINT_SCHEMA, configure_endpoints
from .kconfig import disable_unused_clusters
from .types import MatterComponent

from .const import *

register_bound_command_actions()

CODEOWNERS = ["@DavidvtWout"]

AUTO_LOAD = ["network"]

MIN_ESPHOME_THREAD_VERSION = "2026.6.0"
MIN_ESPHOME_IDF_TOOLCHAIN_VERSION = "2026.9.0"

# Matter spec section 5.1.7.1: these passcodes are explicitly forbidden.
_FORBIDDEN_PASSCODES = {
    11111111,
    22222222,
    33333333,
    44444444,
    55555555,
    66666666,
    77777777,
    88888888,
    99999999,
    12345678,
    87654321,
}


def _validate_passcode(value):
    value = cv.int_(value)
    if not (0 < value <= 99999998) or value in _FORBIDDEN_PASSCODES:
        raise cv.Invalid(
            f"Passcode {value} is not allowed by the Matter specification (section 5.1.7.1)"
        )
    return value


def _validate_basic_information_name(value):
    value = cv.string_strict(value)
    if not (0 < len(value) <= 32):
        raise cv.Invalid("Matter vendor and product names must be 1 to 32 characters")
    return value


def _require_vfs_select(config):
    """Register VFS select requirement during config validation."""
    if CORE.is_esp32:
        require_vfs_select()
    return config


def _require_platformio_toolchain(config):
    if not CORE.using_toolchain_platformio:
        raise cv.Invalid(
            "The esphome-matter external component currently requires the ESP32 PlatformIO "
            "toolchain. Please use `esp32.toolchain: platformio`."
        )
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterComponent),
            cv.Optional(
                CONF_VENDOR_NAME, default="ESPHome"
            ): _validate_basic_information_name,
            cv.Optional(
                CONF_PRODUCT_NAME, default=lambda: CORE.name[:32]
            ): _validate_basic_information_name,
            cv.Optional(CONF_DISCRIMINATOR): cv.int_range(min=0, max=4095),
            cv.Optional(CONF_PASSCODE): _validate_passcode,
            cv.Optional(CONF_ENDPOINTS, default={}): cv.Schema(
                {
                    cv.int_range(min=0, max=65534): ENDPOINT_SCHEMA,
                }
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    cv.only_with_framework(Framework.ESP_IDF),
    _require_vfs_select,  # TODO: Only needed when openthread is enabled
)


def _final_validate(_):
    full_config = fv.full_config.get()
    if "openthread" in full_config:
        cv.validate_esphome_version(MIN_ESPHOME_THREAD_VERSION)
    if CORE.using_toolchain_esp_idf:
        cv.validate_esphome_version(MIN_ESPHOME_IDF_TOOLCHAIN_VERSION)

    network_config = full_config.get("network", {})
    if not network_config.get(CONF_ENABLE_IPV6, False):
        raise cv.Invalid(
            "Matter requires IPv6 to be enabled in the network component. "
            "Please set `enable_ipv6: true` in the `network` configuration."
        )


FINAL_VALIDATE_SCHEMA = _final_validate


# The esp32 component already sets board_build.cmake_extra_args at FINAL priority so we need
# to set it after that to prevent this platformio option from being overwritten.
# TODO: remove when esphome-matter requires ESPHome >=2026.9.0
@coroutine_with_priority(CoroPriority.FINAL - 1)
async def _set_executable_component_name():
    # esp_matter's CMakeLists.txt defaults EXECUTABLE_COMPONENT_NAME to "main", but ESPHome names
    # the app component "src".
    if CORE.using_toolchain_platformio:
        key = "board_build.cmake_extra_args"
        value = CORE.platformio_options.get(key, "")
        value += " -DEXECUTABLE_COMPONENT_NAME=src"
        cg.add_platformio_option(key, value)


@coroutine_with_priority(CoroPriority.NETWORK_SERVICES)
async def to_code(config: ConfigType):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    # Register endpoint IDs globally for later use by actions, etc...
    CORE.data.setdefault(CONF_MATTER, {})[KEY_ENDPOINT_ID_MAP] = {
        endpoint_config[CONF_ID]: endpoint_id
        for endpoint_id, endpoint_config in config.get(CONF_ENDPOINTS, {}).items()
    }

    add_idf_component(
        name="davidvtwout/esp_matter",
        ref="1.6.0~2",
    )

    cg.add_define("USE_MATTER")

    # esp_matter's CMakeLists.txt defaults EXECUTABLE_COMPONENT_NAME to "main", but ESPHome
    # names the app component "src".
    try:
        cg.add_cmake_arg("EXECUTABLE_COMPONENT_NAME", "src")
    except AttributeError:
        CORE.add_job(_set_executable_component_name)

    add_idf_sdkconfig_option("CONFIG_MBEDTLS_HKDF_C", True)
    try:
        from esphome.components.esp32 import require_certificate_bundle

        # Supported from ESPHome 2026.9.0
        require_certificate_bundle()
    except ImportError:
        # TODO: remove when esphome-matter requires ESPHome >=2026.9.0
        add_idf_sdkconfig_option("CONFIG_MBEDTLS_CERTIFICATE_BUNDLE", True)

    if CONF_DISCRIMINATOR in config:
        cg.add_define("MATTER_DISCRIMINATOR", config[CONF_DISCRIMINATOR])
    if CONF_PASSCODE in config:
        cg.add_define("MATTER_PASSCODE", config[CONF_PASSCODE])
    cg.add_build_flag(
        f'-DCHIP_DEVICE_CONFIG_DEVICE_VENDOR_NAME=\\"{config[CONF_VENDOR_NAME]}\\"'
    )
    cg.add_build_flag(
        f'-DCHIP_DEVICE_CONFIG_DEVICE_PRODUCT_NAME=\\"{config[CONF_PRODUCT_NAME]}\\"'
    )

    use_openthread = "openthread" in CORE.loaded_integrations
    use_wifi = "wifi" in CORE.loaded_integrations
    use_ethernet = "ethernet" in CORE.loaded_integrations
    # has_connectivity determines whether the device should be commissioned over BLE or not.
    has_connectivity = use_openthread or use_wifi  # or use_ethernet

    # CONFIG_USE_MINIMAL_MDNS=n makes connectedhomeip use the espressif/mdns component.
    add_idf_sdkconfig_option("CONFIG_USE_MINIMAL_MDNS", False)

    # CONFIG_ENABLE_MATTER_OVER_THREAD is enabled by default and must explicitly be disabled when not needed.
    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_MATTER_OVER_THREAD", use_openthread or not has_connectivity
    )
    if use_openthread:
        # Prevent esp-matter from trying to initialize another openthread stack.
        add_idf_sdkconfig_option("CONFIG_ESP_MATTER_ENABLE_OPENTHREAD", False)
    if use_openthread or not has_connectivity:
        add_idf_sdkconfig_option("CONFIG_LWIP_IPV6_NUM_ADDRESSES", 6)

    if use_openthread or use_wifi:
        # Force the Matter DNS-SD bridge object into the final link. ESP-IDF/PlatformIO may compile
        # component sources that the static-link step still discards unless an exported symbol is referenced.
        cg.add_build_flag("-Wl,-u,esphome_matter_link_dnssd")

    add_idf_sdkconfig_option("CONFIG_ENABLE_WIFI_AP", False)
    # CONFIG_ENABLE_WIFI_STATION is enabled by default and must explicitly be disabled when not needed.
    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_WIFI_STATION", use_wifi or not has_connectivity
    )
    if use_wifi:
        cg.add_build_flag(
            "-Wl,--wrap=_ZN4chip11DeviceLayer23ConnectivityManagerImpl8InitWiFiEv"
        )
        cg.add_build_flag(
            "-Wl,--wrap=_ZN4chip11DeviceLayer8Internal10ESP32Utils13InitWiFiStackEv"
        )
    if use_wifi or use_ethernet:
        # lwIP must add the route to the thread network via the border router to its routing table.
        add_idf_sdkconfig_option("CONFIG_LWIP_IPV6_ND6_ROUTE_INFO_OPTION_SUPPORT", True)

    # Has nothing to do with telemetry... But this is how connectedhomeip names the option that enables ethernet.
    add_idf_sdkconfig_option("CONFIG_ENABLE_ETHERNET_TELEMETRY", use_ethernet)

    # CONFIG_ENABLE_CHIPOBLE is enabled by default and must explicitly be disabled when not needed.
    add_idf_sdkconfig_option("CONFIG_ENABLE_CHIPOBLE", not has_connectivity)
    if not has_connectivity:
        # If no network is configured, commissioning over the network isn't possible and esphome-matter must fall
        # back to BlueTooth (BLE) commissioning (the default for most matter devices). In this mode, the device can be
        # commissioned as matter-over-thread or matter-over-wifi device depending on the hardware capabilities of the
        # device. If the device supports both, it can be commissioned in either mode.

        # TODO: only enable if device supports it
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_CLI", False)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_CONSOLE_ENABLE", False)
        add_idf_sdkconfig_option("CONFIG_OPENTHREAD_SRP_CLIENT", True)

        # TODO: use CORE.data?
        add_idf_sdkconfig_option("CONFIG_BT_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_BT_BLUEDROID_ENABLED", False)
        add_idf_sdkconfig_option("CONFIG_BT_NIMBLE_ENABLED", True)
        add_idf_sdkconfig_option("CONFIG_BT_NIMBLE_ENABLE_CONN_REATTEMPT", False)
        # TODO: set USE_BLE_ONLY_FOR_COMMISSIONING to false if other esphome components need it?
        # TODO: stop api from restarting device in commissioning mode?

    disable_unused_clusters()
    await configure_endpoints(var, config)
