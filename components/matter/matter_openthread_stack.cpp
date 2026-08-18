#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_OPENTHREAD)

#include "esphome/core/log.h"

#include <esp_err.h>

// TODO: patch connectedhomeip ESP32 ThreadStackManager to bind to an existing
// OpenThread instance without calling openthread_init_stack().

namespace {
static const char *const TAG = "matter.openthread";
}

extern "C" esp_err_t esphome_matter_wrap_openthread_init_stack() asm(
    "__wrap__Z21openthread_init_stackv");
extern "C" esp_err_t esphome_matter_wrap_openthread_init_stack() {
  ESP_LOGD(TAG, "Skipping CHIP OpenThread stack init; ESPHome owns it");
  return ESP_OK;
}

#endif // USE_MATTER && USE_OPENTHREAD
