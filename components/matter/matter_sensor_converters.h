#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include <esp_matter.h>

namespace esphome::matter::sensor_converter {

esp_matter_attr_val_t amperes_to_milliamperes(float value);
esp_matter_attr_val_t boolean_state(bool value);
esp_matter_attr_val_t concentration(float value);
esp_matter_attr_val_t flow(float value);
esp_matter_attr_val_t frequency(float value);
esp_matter_attr_val_t illuminance(float value);
esp_matter_attr_val_t occupancy(bool value);
esp_matter_attr_val_t percent_to_hundredths(float value);
esp_matter_attr_val_t pressure(float value);
esp_matter_attr_val_t temperature(float value);
esp_matter_attr_val_t volts_to_millivolts(float value);
esp_matter_attr_val_t watts_to_milliwatts(float value);

} // namespace esphome::matter::sensor_converter

#endif // USE_MATTER
