// Compiled in esp_matter's target instead of its RMII-specific driver source.
#include <esp_netif.h>
#include <lib/support/logging/CHIPLogging.h>
#include <platform/ESP32/NetworkCommissioningDriver.h>

namespace chip::DeviceLayer::NetworkCommissioning {

CHIP_ERROR ESPEthernetDriver::Init(NetworkStatusChangeCallback *callback) {
  (void) callback;
  if (esp_netif_get_handle_from_ifkey("ETH_DEF") == nullptr) {
    ChipLogError(DeviceLayer, "ESPHome Ethernet interface is not initialized");
    return CHIP_ERROR_INCORRECT_STATE;
  }
  ChipLogProgress(DeviceLayer, "Using ESPHome Ethernet interface");
  return CHIP_NO_ERROR;
}

} // namespace chip::DeviceLayer::NetworkCommissioning
