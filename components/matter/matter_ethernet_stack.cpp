#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_ETHERNET)

#include <esp_event.h>
#include <platform/PlatformManager.h>

// The bundled SDK copies STA_GOT_IP data but omits ETH_GOT_IP data. Preserve
// Ethernet's address payload before forwarding it onto the Matter event loop.
extern "C" void esphome_matter_real_system_event(
    void *arg, esp_event_base_t base, int32_t id, void *data)
    asm("__real__ZN4chip11DeviceLayer19PlatformManagerImpl20HandleESPSystemEventEPvPKclS2_");
extern "C" void esphome_matter_wrap_system_event(
    void *arg, esp_event_base_t base, int32_t id, void *data)
    asm("__wrap__ZN4chip11DeviceLayer19PlatformManagerImpl20HandleESPSystemEventEPvPKclS2_");

extern "C" void esphome_matter_wrap_system_event(
    void *arg, esp_event_base_t base, int32_t id, void *data) {
  if (base == IP_EVENT && id == IP_EVENT_ETH_GOT_IP && data != nullptr) {
    chip::DeviceLayer::ChipDeviceEvent event{};
    event.Type = chip::DeviceLayer::DeviceEventType::kESPSystemEvent;
    event.Platform.ESPSystemEvent.Base = base;
    event.Platform.ESPSystemEvent.Id = id;
    event.Platform.ESPSystemEvent.Data.IpGotIp =
        *static_cast<const ip_event_got_ip_t *>(data);
    chip::DeviceLayer::PlatformMgr().PostEventOrDie(&event);
    return;
  }
  esphome_matter_real_system_event(arg, base, id, data);
}

#endif // USE_MATTER && USE_ETHERNET
