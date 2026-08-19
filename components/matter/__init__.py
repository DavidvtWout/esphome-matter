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

# Only for matter-over-thread
MIN_ESPHOME_VERSION = "2026.6.0"

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
    _require_platformio_toolchain,
    _require_vfs_select,  # TODO: Only needed when openthread is enabled
)


def _final_validate(_):
    full_config = fv.full_config.get()
    if "openthread" in full_config:
        cv.validate_esphome_version(MIN_ESPHOME_VERSION)

    network_config = full_config.get("network", {})
    if not network_config.get(CONF_ENABLE_IPV6, False):
        raise cv.Invalid(
            "Matter requires IPv6 to be enabled in the network component. "
            "Please set `enable_ipv6: true` in the `network` configuration."
        )


FINAL_VALIDATE_SCHEMA = _final_validate


# The esp32 component already sets board_build.cmake_extra_args at FINAL priority so we need
# to set it after that to prevent this platformio option from being overwritten.
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

    add_idf_component(
        name="espressif/esp_matter",
        ref="1.5.1",
    )

    CORE.add_job(_set_executable_component_name)

    cg.add_define("USE_MATTER")

    if CONF_DISCRIMINATOR in config:
        cg.add_define("MATTER_DISCRIMINATOR", config[CONF_DISCRIMINATOR])
    if CONF_PASSCODE in config:
        cg.add_define("MATTER_PASSCODE", config[CONF_PASSCODE])

    use_openthread = "openthread" in CORE.loaded_integrations
    use_wifi = "wifi" in CORE.loaded_integrations
    use_ethernet = "ethernet" in CORE.loaded_integrations
    # has_connectivity determines whether the device should be commissioned over BLE or not.
    has_connectivity = use_openthread or use_wifi  # or use_ethernet

    # CONFIG_USE_MINIMAL_MDNS=n makes matter use the espressif/mdns component which is also used by ESPHome.
    add_idf_sdkconfig_option("CONFIG_USE_MINIMAL_MDNS", False)  # connectedhomeip
    add_idf_sdkconfig_option("CONFIG_ENABLE_EXTENDED_DISCOVERY", True)

    add_idf_sdkconfig_option("CONFIG_LWIP_IPV6_NUM_ADDRESSES", 6)

    # Disable Intermittently Connected Device (ICD).
    add_idf_sdkconfig_option("CONFIG_ENABLE_ICD_SERVER", False)  # connectedhomeip
    add_idf_sdkconfig_option("CONFIG_ENABLE_ICD_LIT", False)  # connectedhomeip
    add_idf_sdkconfig_option("CONFIG_ENABLE_ICD_CIP", False)  # connectedhomeip
    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_ICD_USER_ACTIVE_MODE_TRIGGER", False
    )  # connectedhomeip

    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_MATTER_OVER_THREAD", not has_connectivity or use_openthread
    )  # connectedhomeip
    if use_openthread:
        # ESP_MATTER_ENABLE_OPENTHREAD is enabled by default and must explicitly be disabled. It stops
        # esp-matter from initializing an openthread stack (the openthread component already does that).
        add_idf_sdkconfig_option(
            "CONFIG_ESP_MATTER_ENABLE_OPENTHREAD", False
        )  # esp-matter
        cg.add_build_flag("-Wl,--wrap=_Z21openthread_init_stackv")

        # add_idf_sdkconfig_option("CONFIG_OPENTHREAD_DNS_CLIENT", True)
        add_idf_sdkconfig_option("CONFIG_ENABLE_CHIP_DATA_MODEL", True)  # esp-matter
        add_idf_sdkconfig_option("CONFIG_LWIP_MULTICAST_PING", True)

        # TODO: fix the network implementation of ESPHome. Currently the network component doesn't even support IPv6-only.
        # add_idf_sdkconfig_option("CONFIG_LWIP_IPV4", False)
        # add_idf_sdkconfig_option("CONFIG_DISABLE_IPV4", True)  # connectedhomeip

    if use_openthread or use_wifi:
        # Force the Matter DNS-SD bridge object into the final link. ESP-IDF/PlatformIO may compile
        # component sources that the static-link step still discards unless an exported symbol is referenced.
        cg.add_build_flag("-Wl,-u,esphome_matter_link_dnssd")

    add_idf_sdkconfig_option("CONFIG_ENABLE_WIFI_AP", False)  # connectedhomeip
    # CONFIG_ENABLE_WIFI_STATION is enabled by default and must explicitly be disabled when not needed.
    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_WIFI_STATION", not has_connectivity or use_wifi
    )  # connectedhomeip
    if use_wifi:
        # ESPHome already owns esp_netif, the Wi-Fi driver and the default STA
        # netif. Keep CHIP Wi-Fi station support compiled in, but skip its
        # platform Wi-Fi initialization to avoid resetting an active ESPHome
        # connection attempt.
        cg.add_build_flag(
            "-Wl,--wrap=_ZN4chip11DeviceLayer23ConnectivityManagerImpl8InitWiFiEv"
        )
        cg.add_build_flag(
            "-Wl,--wrap=_ZN4chip11DeviceLayer8Internal10ESP32Utils13InitWiFiStackEv"
        )
    if use_wifi or use_ethernet:
        # lwIP must add the route to the thread network via the border router to its routing table.
        add_idf_sdkconfig_option("CONFIG_LWIP_IPV6_ND6_ROUTE_INFO_OPTION_SUPPORT", True)
    if use_ethernet:
        # Has nothing to do with telemetry... But this is how connectedhomeip names the option that enables ethernet.
        add_idf_sdkconfig_option(
            "CONFIG_ENABLE_ETHERNET_TELEMETRY", True
        )  # connectedhomeip

    # CONFIG_ENABLE_CHIPOBLE is enabled by default and must explicitly be disabled when not needed.
    add_idf_sdkconfig_option(
        "CONFIG_ENABLE_CHIPOBLE", not has_connectivity
    )  # connectedhomeip
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

    # TODO: ENABLE_ESP32_FACTORY_DATA_PROVIDER?

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

    disable_unused_clusters()
    await configure_endpoints(var, config)
