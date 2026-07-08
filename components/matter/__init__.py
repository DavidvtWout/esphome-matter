from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_component, add_idf_sdkconfig_option
from esphome.const import CONF_ID, Framework
from esphome.core import CORE
from esphome.helpers import write_file_if_changed

CODEOWNERS = ["@DavidvtWout"]

DEPENDENCIES = ["network"]

CONF_DISCRIMINATOR = "discriminator"
CONF_PASSCODE = "passcode"

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

CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(MatterComponent),
        cv.Optional(CONF_DISCRIMINATOR): cv.int_range(min=0, max=4095),
        cv.Optional(CONF_PASSCODE): _validate_passcode,
    }).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    cv.only_with_framework(Framework.ESP_IDF),
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    add_idf_component(name="espressif/esp_matter", ref="1.4.0")

    cg.add_define("USE_MATTER")

    if CONF_DISCRIMINATOR in config:
        cg.add_define("MATTER_DISCRIMINATOR", config[CONF_DISCRIMINATOR])
    if CONF_PASSCODE in config:
        cg.add_define("MATTER_PASSCODE", config[CONF_PASSCODE])

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

    # Disable esp_matter's own Thread stack init: ESPHome's openthread component already
    # called esp_openthread_init(). Letting esp_matter also call it (the default) causes a
    # double-init crash. With this False, esp_matter::start() skips InitThreadStack() and
    # StartThreadTask(); CHIP's UDP layer still reaches the Thread netif via LWIP.
    add_idf_sdkconfig_option("CONFIG_ESP_MATTER_ENABLE_OPENTHREAD", False)

    # On-network commissioning (device already connected via ESPHome Wi-Fi/Thread config)
    # uses mDNS/SRP discovery + PASE over UDP. BLE is not involved. Disabling it saves
    # memory and avoids radio coexistence issues on ESP32-C6 where BLE and 802.15.4 share
    # the same RF hardware. CHIP drops CHIPoBLE automatically when BT is disabled and falls
    # back to IP-only commissioning.
    add_idf_sdkconfig_option("CONFIG_BT_ENABLED", False)

    # CHIP's mbedTLS crypto backend calls mbedtls_hkdf() (CHIPCryptoPALmbedTLS.cpp).
    # ESP-IDF's mbedTLS disables HKDF by default; enabling this compiles mbedtls/hkdf.c
    # into the mbedTLS library so the symbol is present at link time.
    add_idf_sdkconfig_option("CONFIG_MBEDTLS_HKDF_C", True)

    # connectedhomeip's ConnectivityManagerImpl static-asserts that the Wi-Fi and Thread
    # Matter NetworkCommissioning cluster endpoint IDs are different. Both Kconfig options
    # default to 0 on ESP32-C6 (which has hardware for both). Setting Thread=2 prevents the
    # assertion. These are Matter application-layer endpoint numbers, not network interface
    # IDs, the actual Wi-Fi/Thread connectivity is still managed by ESPHome's Wi-Fi/OpenThread.
    add_idf_sdkconfig_option("CONFIG_WIFI_NETWORK_ENDPOINT_ID", 0)
    add_idf_sdkconfig_option("CONFIG_THREAD_NETWORK_ENDPOINT_ID", 2)

    # connectedhomeip's GN build sets CHIP_HAVE_CONFIG_H=1 for all its sources (src/BUILD.gn).
    # Without it, SystemConfig.h can't find the GN-generated SystemBuildConfig.h and
    # CHIPDeviceBuildConfig.h that live in the chip component's binary dir (already in
    # PlatformIO's CPPPATH via the chip CMakeLists.txt INTERFACE include_directories).
    # Adding this define to PlatformIO's src compilation makes CHIP headers work when
    # included from our ESPHome component files.
    cg.add_build_flag("-DCHIP_HAVE_CONFIG_H=1")
