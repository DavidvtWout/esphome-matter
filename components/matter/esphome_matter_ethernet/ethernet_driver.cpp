// Compiled in esp_matter's target instead of its RMII-specific driver source.
#include <cstring>
#include <esp_netif.h>
#include <lib/support/logging/CHIPLogging.h>
#include "esphome_matter_ethernet_driver.h"

namespace chip::DeviceLayer::NetworkCommissioning {
namespace {
// ESPHome uses esp_netif_new(ESP_NETIF_DEFAULT_ETH()) in
// EthernetComponent::ethernet_lazy_init_(), which registers this interface key.
constexpr char ETHERNET_INTERFACE_KEY[] = "ETH_DEF";
static_assert(sizeof(ETHERNET_INTERFACE_KEY) - 1 <= kMaxNetworkIDLen);

class ESPHomeEthernetNetworkIterator final : public NetworkIterator {
 public:
  explicit ESPHomeEthernetNetworkIterator(esp_netif_t *netif)
      : present_(netif != nullptr),
        connected_(netif != nullptr && esp_netif_is_netif_up(netif)) {}

  size_t Count() override { return this->present_ ? 1 : 0; }

  bool Next(Network &item) override {
    if (!this->present_ || this->exhausted_)
      return false;
    this->exhausted_ = true;
    item = {};
    std::memcpy(item.networkID, ETHERNET_INTERFACE_KEY,
                sizeof(ETHERNET_INTERFACE_KEY) - 1);
    item.networkIDLen = sizeof(ETHERNET_INTERFACE_KEY) - 1;
    item.connected = this->connected_;
    return true;
  }

  void Release() override { delete this; }

 private:
  bool present_;
  bool connected_;
  bool exhausted_{false};
};
} // namespace

NetworkIterator *ESPHomeEthernetDriver::GetNetworks() {
  return new ESPHomeEthernetNetworkIterator(
      esp_netif_get_handle_from_ifkey(ETHERNET_INTERFACE_KEY));
}

ESPHomeEthernetDriver &ESPHomeEthernetDriver::GetInstance() {
  static ESPHomeEthernetDriver instance;
  return instance;
}

CHIP_ERROR ESPEthernetDriver::Init(NetworkStatusChangeCallback *callback) {
  (void) callback;
  if (esp_netif_get_handle_from_ifkey(ETHERNET_INTERFACE_KEY) == nullptr) {
#if CHIP_DEVICE_CONFIG_ENABLE_WIFI
    ChipLogProgress(DeviceLayer, "Ethernet unavailable; Matter can use Wi-Fi");
    return CHIP_NO_ERROR;
#else
    ChipLogError(DeviceLayer, "ESPHome Ethernet interface is not initialized");
    return CHIP_ERROR_INCORRECT_STATE;
#endif
  }
  ChipLogProgress(DeviceLayer, "Using ESPHome Ethernet interface");
  return CHIP_NO_ERROR;
}

} // namespace chip::DeviceLayer::NetworkCommissioning
