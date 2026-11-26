#pragma once

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include <esp_matter.h>
#include <lib/core/CHIPError.h>

#include <cstdint>

namespace esphome::matter {

using CodeDrivenAttributeUpdater = CHIP_ERROR (*)(uint16_t, uint32_t,
                                                  esp_matter_attr_val_t);

CodeDrivenAttributeUpdater find_code_driven_updater(uint32_t cluster_id,
                                                    uint32_t attribute_id);

CHIP_ERROR update_air_quality_attribute(uint16_t endpoint_id,
                                        uint32_t cluster_id,
                                        esp_matter_attr_val_t value);
CHIP_ERROR update_resource_condition_attribute(uint16_t endpoint_id,
                                               uint32_t cluster_id,
                                               esp_matter_attr_val_t value);
CHIP_ERROR update_resource_change_indication_attribute(
    uint16_t endpoint_id, uint32_t cluster_id, esp_matter_attr_val_t value);

} // namespace esphome::matter

#endif // USE_MATTER
