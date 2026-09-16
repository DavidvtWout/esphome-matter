#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_ETHERNET) && !defined(USE_WIFI)

// davidvtwout/esp_matter 1.6.0~2 excludes this backend from its CMake source
// list when Wi-Fi is disabled, even though it also serves Ethernet. Compile
// the bundled implementation here until the SDK's Ethernet build is fixed.
// Do not include it for Wi-Fi builds, where the SDK already compiles it.
#include <platform/ESP32/ESP32DnssdImpl.cpp>

#endif // USE_MATTER && USE_ETHERNET && !USE_WIFI
