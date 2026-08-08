#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_WIFI)

#include "esphome/core/log.h"

#include <esp_event.h>
#include <esp_wifi.h>
#include <lib/core/CHIPError.h>
#include <platform/ESP32/ESP32Utils.h>
#include <platform/ESP32/PlatformManagerImpl.h>

// TODO: patch esp-matter to allow setting
// kWiFiStationMode_ApplicationControlled before starting matter. That would
// make this override completely redundant.

namespace {
static const char *const TAG = "matter.wifi";
bool wifi_events_registered{false};
} // namespace

extern "C" CHIP_ERROR esphome_matter_wrap_esp32_init_wifi_stack() asm(
    "__wrap__ZN4chip11DeviceLayer8Internal10ESP32Utils13InitWiFiStackEv");
extern "C" CHIP_ERROR esphome_matter_wrap_esp32_init_wifi_stack() {
  if (wifi_events_registered)
    return CHIP_NO_ERROR;

  ESP_LOGV(TAG, "Skipping CHIP Wi-Fi stack init; ESPHome owns Wi-Fi");
  esp_err_t err = esp_event_handler_register(
      WIFI_EVENT, ESP_EVENT_ANY_ID,
      chip::DeviceLayer::PlatformManagerImpl::HandleESPSystemEvent, nullptr);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to register CHIP Wi-Fi event handler: %s",
             esp_err_to_name(err));
    return chip::DeviceLayer::Internal::ESP32Utils::MapError(err);
  }
  wifi_events_registered = true;
  return CHIP_NO_ERROR;
}

#endif // USE_MATTER && USE_WIFI
