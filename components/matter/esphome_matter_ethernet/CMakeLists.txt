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
# Match source identity independently of symlink or absolute/relative spelling.
set(ethernet_sources "")
set(dnssd_sources "")
foreach(source IN LISTS matter_sources)
    get_filename_component(source_name "${source}" NAME)
    if(source_name STREQUAL "NetworkCommissioningDriver_Ethernet.cpp")
        list(APPEND ethernet_sources "${source}")
    elseif(source_name STREQUAL "ESP32DnssdImpl.cpp")
        list(APPEND dnssd_sources "${source}")
    endif()
endforeach()
list(LENGTH ethernet_sources ethernet_source_count)
if(NOT ethernet_source_count EQUAL 1)
    message(FATAL_ERROR "Expected exactly one esp_matter Ethernet driver source; found ${ethernet_source_count}. Review the ESPHome adapter")
endif()
list(REMOVE_ITEM matter_sources ${ethernet_sources})
set_property(TARGET ${matter_lib} PROPERTY SOURCES "${matter_sources}")
target_sources(${matter_lib} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/ethernet_driver.cpp")

# esp_matter 1.6.0~2 excludes ESP32DnssdImpl.cpp when both Wi-Fi modes
# are disabled. Keep this condition aligned with CONFIG_ENABLE_WIFI_STATION
# and CONFIG_ENABLE_WIFI_AP in matter/__init__.py. Add it to the SDK target,
# so its private include paths, CHIP definitions and compiler flags apply.
if(CONFIG_ENABLE_ETHERNET_TELEMETRY AND NOT CONFIG_USE_MINIMAL_MDNS
   AND NOT CONFIG_ENABLE_WIFI_STATION AND NOT CONFIG_ENABLE_WIFI_AP)
    set(dnssd_source "${matter_dir}/connectedhomeip/connectedhomeip/src/platform/ESP32/ESP32DnssdImpl.cpp")
    if(NOT dnssd_sources)
        target_sources(${matter_lib} PRIVATE "${dnssd_source}")
    endif()
endif()

# The SDK's GetNetworks is inline. Use a derived driver at the cluster's factory
# call instead of redefining the SDK class in different translation units.
set(commissioning_sources "")
foreach(source IN LISTS matter_sources)
    if(source MATCHES "(^|/)network_commissioning/integration\\.cpp$")
        list(APPEND commissioning_sources "${source}")
    endif()
endforeach()
list(LENGTH commissioning_sources commissioning_source_count)
if(NOT commissioning_source_count EQUAL 1)
    message(FATAL_ERROR "Expected exactly one network commissioning integration source; review the ESPHome adapter")
endif()
list(GET commissioning_sources 0 commissioning_source)
get_target_property(matter_source_dir ${matter_lib} SOURCE_DIR)
get_filename_component(commissioning_read_source "${commissioning_source}" ABSOLUTE BASE_DIR "${matter_source_dir}")
configure_file("${commissioning_read_source}" "${CMAKE_CURRENT_BINARY_DIR}/network_commissioning.original.cpp" COPYONLY)
file(READ "${commissioning_read_source}" commissioning_content)
set(old_factory "ESPEthernetDriver::GetInstance()")
string(FIND "${commissioning_content}" "${old_factory}" factory_position)
if(factory_position EQUAL -1)
    message(FATAL_ERROR "esp_matter Ethernet driver factory changed; review the ESPHome adapter")
endif()
string(REPLACE "${old_factory}" "ESPHomeEthernetDriver::GetInstance()" commissioning_content "${commissioning_content}")
string(PREPEND commissioning_content "#include \"esphome_matter_ethernet_driver.h\"\n")
set(commissioning_adapter "${CMAKE_CURRENT_BINARY_DIR}/network_commissioning_integration.cpp")
set(previous_content "")
if(EXISTS "${commissioning_adapter}")
    file(READ "${commissioning_adapter}" previous_content)
endif()
if(NOT previous_content STREQUAL commissioning_content)
    file(WRITE "${commissioning_adapter}" "${commissioning_content}")
endif()
get_target_property(matter_sources ${matter_lib} SOURCES)
list(REMOVE_ITEM matter_sources ${commissioning_sources})
set_property(TARGET ${matter_lib} PROPERTY SOURCES "${matter_sources}")
target_sources(${matter_lib} PRIVATE "${commissioning_adapter}")
target_include_directories(${matter_lib} PRIVATE "${CMAKE_CURRENT_LIST_DIR}")
