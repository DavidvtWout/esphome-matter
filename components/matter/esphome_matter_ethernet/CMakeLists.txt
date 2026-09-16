# Registered by matter/__init__.py only when ESPHome Ethernet is enabled.
idf_component_register(REQUIRES davidvtwout__esp_matter)

# The dependency scan does not create targets or load sdkconfig yet.
if(CMAKE_BUILD_EARLY_EXPANSION)
    return()
endif()

idf_component_get_property(matter_lib davidvtwout__esp_matter COMPONENT_LIB)
idf_component_get_property(matter_dir davidvtwout__esp_matter COMPONENT_DIR)
get_target_property(matter_sources ${matter_lib} SOURCES)

# Init owns the SDK vtable, so --wrap cannot interpose references from that same
# translation unit. Replace the source explicitly: exactly one definition, built
# with the SDK's flags, and no SDK RMII driver compiled on SPI-only targets.
set(ethernet_source "${matter_dir}/connectedhomeip/connectedhomeip/src/platform/ESP32/NetworkCommissioningDriver_Ethernet.cpp")
if(NOT ethernet_source IN_LIST matter_sources)
    message(FATAL_ERROR "esp_matter Ethernet source selection changed; review the ESPHome adapter")
endif()
list(REMOVE_ITEM matter_sources "${ethernet_source}")
set_property(TARGET ${matter_lib} PROPERTY SOURCES "${matter_sources}")
target_sources(${matter_lib} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/ethernet_driver.cpp")

# esp_matter 1.6.0~2 excludes ESP32DnssdImpl.cpp when both Wi-Fi modes
# are disabled. Keep this condition aligned with CONFIG_ENABLE_WIFI_STATION
# and CONFIG_ENABLE_WIFI_AP in matter/__init__.py. Add it to the SDK target,
# so its private include paths, CHIP definitions and compiler flags apply.
if(CONFIG_ENABLE_ETHERNET_TELEMETRY AND NOT CONFIG_USE_MINIMAL_MDNS
   AND NOT CONFIG_ENABLE_WIFI_STATION AND NOT CONFIG_ENABLE_WIFI_AP)
    set(dnssd_source "${matter_dir}/connectedhomeip/connectedhomeip/src/platform/ESP32/ESP32DnssdImpl.cpp")
    get_target_property(matter_sources ${matter_lib} SOURCES)
    if(NOT dnssd_source IN_LIST matter_sources)
        target_sources(${matter_lib} PRIVATE "${dnssd_source}")
    endif()
endif()
