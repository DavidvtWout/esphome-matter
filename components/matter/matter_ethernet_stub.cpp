#include "esphome/core/defines.h"
#ifdef USE_MATTER

// Linker-override stubs for Ethernet hardware init.
//
// CONFIG_ENABLE_ETHERNET_TELEMETRY enables CHIP_DEVICE_CONFIG_ENABLE_ETHERNET, which gives us
// working DNS-SD and operational discovery without depending on CONFIG_ENABLE_WIFI_STATION.
// But we don't want connectedhomeip to actually drive an ethernet chip so we override the
// init functions with no-ops.
//
// Both functions are defined in the `chip` static library archive. The linker prefers definitions
// from object files over archive members, so these strong-symbol definitions win without errors.

#include <platform/internal/CHIPDeviceLayerInternal.h>
#include <platform/ESP32/NetworkCommissioningDriver.h>
#include <esp_netif.h>

namespace chip {
namespace DeviceLayer {

CHIP_ERROR ConnectivityManagerImpl::InitEthernet() { return CHIP_NO_ERROR; }
void ConnectivityManagerImpl::OnEthernetIPv4AddressAvailable(const ip_event_got_ip_t &) {}
void ConnectivityManagerImpl::OnEthernetIPv4AddressLost() {}
void ConnectivityManagerImpl::OnEthernetIPv6AddressAvailable(const ip_event_got_ip6_t &) {}
void ConnectivityManagerImpl::OnEthernetPlatformEvent(const ChipDeviceEvent *) {}

namespace NetworkCommissioning {

CHIP_ERROR ESPEthernetDriver::Init(NetworkStatusChangeCallback *) { return CHIP_NO_ERROR; }

} // namespace NetworkCommissioning
} // namespace DeviceLayer
} // namespace chip

#endif // USE_MATTER
