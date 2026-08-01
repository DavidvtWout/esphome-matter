#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include <platform/internal/CHIPDeviceLayerInternal.h>
#include <platform/ESP32/NetworkCommissioningDriver.h>
#include <esp_netif.h>

#if CHIP_DEVICE_CONFIG_ENABLE_ETHERNET

// Linker-override stubs for Ethernet hardware init.
//
// When CHIP's ESP32 ethernet support is enabled, it provides DNS-SD and operational discovery
// without depending on CONFIG_ENABLE_WIFI_STATION. ESPHome owns the actual network interfaces,
// so keep connectedhomeip from trying to initialize ethernet hardware by overriding its init
// hooks with no-ops.
//
// Both functions are defined in the `chip` static library archive. The linker prefers definitions
// from object files over archive members, so these strong-symbol definitions win without errors.

namespace chip::DeviceLayer {

CHIP_ERROR ConnectivityManagerImpl::InitEthernet() { return CHIP_NO_ERROR; }
void ConnectivityManagerImpl::OnEthernetIPv4AddressAvailable(const ip_event_got_ip_t &) {}
void ConnectivityManagerImpl::OnEthernetIPv4AddressLost() {}
void ConnectivityManagerImpl::OnEthernetIPv6AddressAvailable(const ip_event_got_ip6_t &) {}
void ConnectivityManagerImpl::OnEthernetPlatformEvent(const ChipDeviceEvent *) {}

} // namespace chip::DeviceLayer

namespace chip::DeviceLayer::NetworkCommissioning {

CHIP_ERROR ESPEthernetDriver::Init(NetworkStatusChangeCallback *) { return CHIP_NO_ERROR; }

} // namespace chip::DeviceLayer::NetworkCommissioning

#endif // CHIP_DEVICE_CONFIG_ENABLE_ETHERNET
#endif // USE_MATTER
