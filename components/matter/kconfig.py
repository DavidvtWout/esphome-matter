from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.core import CORE
from esphome.helpers import write_file_if_changed

# Exclude unused clusters to optimize flash and memory usage
DISABLED_CLUSTERS = [
    "ACCOUNT_LOGIN",
    "ACTIVATED_CARBON_FILTER_MONITORING",
    "AIR_QUALITY",
    "APPLICATION_BASIC",
    "APPLICATION_LAUNCHER",
    "AUDIO_OUTPUT",
    "BOOLEAN_STATE_CONFIGURATION",
    "BRIDGED_DEVICE_BASIC_INFORMATION",
    "CARBON_DIOXIDE_CONCENTRATION_MEASUREMENT",
    "CARBON_MONOXIDE_CONCENTRATION_MEASUREMENT",
    "CHANNEL",
    "COMMISSIONER_CONTROL",
    "CONTENT_LAUNCHER",
    "CONTENT_CONTROL",
    "CONTENT_APP_OBSERVER",
    "DEVICE_ENERGY_MANAGEMENT",
    "DEVICE_ENERGY_MANAGEMENT_MODE",
    "DIAGNOSTIC_LOGS",
    "DISHWASHER_ALARM",
    "DISHWASHER_MODE",
    "MICROWAVE_OVEN_MODE",
    "DOOR_LOCK",
    "ECOSYSTEM_INFORMATION",
    "ELECTRICAL_ENERGY_MEASUREMENT",
    "ELECTRICAL_POWER_MEASUREMENT",
    "ENERGY_EVSE",
    "ENERGY_EVSE_MODE",
    "ENERGY_PREFERENCE",
    "FAN_CONTROL",
    "FAULT_INJECTION",
    "FIXED_LABEL",
    "FORMALDEHYDE_CONCENTRATION_MEASUREMENT",
    "HEPA_FILTER_MONITORING",
    "ICD_MANAGEMENT",
    "KEYPAD_INPUT",
    "LAUNDRY_WASHER_MODE",
    "LOCALIZATION_CONFIGURATION",
    "LOW_POWER",
    "MEDIA_INPUT",
    "MEDIA_PLAYBACK",
    "MICROWAVE_OVEN_CONTROL",
    "MESSAGES",
    "MODE_SELECT",
    "NITROGEN_DIOXIDE_CONCENTRATION_MEASUREMENT",
    "SAMPLE_MEI",
    "OCCUPANCY_SENSING",
    "POWER_TOPOLOGY",
    "OPERATIONAL_STATE",
    "OPERATIONAL_STATE_OVEN",
    "OPERATIONAL_STATE_RVC",
    "OVEN_MODE",
    "OZONE_CONCENTRATION_MEASUREMENT",
    "PM10_CONCENTRATION_MEASUREMENT",
    "PM1_CONCENTRATION_MEASUREMENT",
    "PM2_5_CONCENTRATION_MEASUREMENT",
    "POWER_SOURCE",
    "POWER_SOURCE_CONFIGURATION",
    "PUMP_CONFIGURATION_AND_CONTROL",
    "RADON_CONCENTRATION_MEASUREMENT",
    "REFRIGERATOR_ALARM",
    "REFRIGERATOR_AND_TEMPERATURE_CONTROLLED_CABINET_MODE",
    "RVC_CLEAN_MODE",
    "RVC_RUN_MODE",
    "SERVICE_AREA",
    "SMOKE_CO_ALARM",
    "SOFTWARE_DIAGNOSTICS",
    "TARGET_NAVIGATOR",
    "TEMPERATURE_CONTROL",
    "THERMOSTAT",
    "THERMOSTAT_USER_INTERFACE_CONFIGURATION",
    "THREAD_BORDER_ROUTER_MANAGEMENT",
    "THREAD_NETWORK_DIRECTORY",
    "TIME_FORMAT_LOCALIZATION",
    "TIME_SYNCHRONIZATION",
    "TIMER",
    "TVOC_CONCENTRATION_MEASUREMENT",
    "UNIT_TESTING",
    "USER_LABEL",
    "VALVE_CONFIGURATION_AND_CONTROL",
    "WAKE_ON_LAN",
    "LAUNDRY_WASHER_CONTROLS",
    "LAUNDRY_DRYER_CONTROLS",
    "WIFI_NETWORK_MANAGEMENT",
    "WINDOW_COVERING",
    "WATER_HEATER_MANAGEMENT",
    "WATER_HEATER_MODE",
]


def write_kconfig_projbuild() -> None:
    # connectedhomeip's Kconfig defines GPIO_RANGE_MAX with chip-specific defaults for
    # ESP32/S2/C3/S3/H2 but not for C6 or other targets. The symbol also has
    # `depends on ENABLE_ETHERNET_TELEMETRY`, making it invisible (str_value='') when that
    # option is off, which crashes kconfgen's write_json_menus (int('', 10) on the range
    # endpoint). Adding a fallback default of 255 here fixes both cases: visible-but-no-C6-
    # default AND invisible (Kconfiglib evaluates defaults even for invisible symbols).
    # There are probably better, less hacky approaches, but simply using
    # add_idf_sdkconfig_option(GPIO_RANGE_MAX, 255) didn't work...
    kconfig_projbuild_path = CORE.relative_build_path("src/Kconfig.projbuild")
    kconfig_projbuild_path.parent.mkdir(parents=True, exist_ok=True)
    write_file_if_changed(
        kconfig_projbuild_path,
        "config GPIO_RANGE_MAX\n"
        "    int\n"
        "    default 255\n",
    )


def disable_unused_clusters() -> None:
    for name in DISABLED_CLUSTERS:
        add_idf_sdkconfig_option(f"CONFIG_SUPPORT_{name}_CLUSTER", False)
