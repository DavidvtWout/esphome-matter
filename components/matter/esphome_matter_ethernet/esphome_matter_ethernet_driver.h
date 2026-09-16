#pragma once

#include <platform/ESP32/NetworkCommissioningDriver.h>

namespace chip::DeviceLayer::NetworkCommissioning {

// Keep the SDK class definition intact; the cluster uses this derived driver.
class ESPHomeEthernetDriver : public ESPEthernetDriver {
 public:
  NetworkIterator *GetNetworks() override;
  static ESPHomeEthernetDriver &GetInstance();
};

} // namespace chip::DeviceLayer::NetworkCommissioning
