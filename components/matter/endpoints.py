import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import (
    CONF_ID,
    CONF_LIGHT_ID,
    CONF_SENSOR_ID,
)
from esphome.types import ConfigType

from .const import *
from .types import MatterEndpointRef
from .device_types import DEVICE_TYPES


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
        }
        | {
            cv.Optional(dt_name): dt_config["schema"]
            for dt_name, dt_config in DEVICE_TYPES.items()
        }
    ),
)


async def configure_endpoints(var, config: ConfigType):
    for endpoint_id, endpoint_config in config[CONF_ENDPOINTS].items():
        ref = cg.new_Pvariable(endpoint_config[CONF_ID])
        for device_type, device_config in endpoint_config.items():
            if device_type not in DEVICE_TYPES:
                continue
            endpoint_ns = f"esp_matter::endpoint::{device_type}"
            method = var.register_endpoint.template(
                cg.RawExpression(f"{endpoint_ns}::config_t"),
                cg.RawExpression(f"{endpoint_ns}::create"),
            )
            cg.add(method(ref))
            if CONF_SENSOR_ID in device_config:
                sensor_ = await cg.get_variable(device_config[CONF_SENSOR_ID])
                cg.add(var.map_sensor_to_endpoint(sensor_, ref))
            elif CONF_LIGHT_ID in device_config:
                light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
                cg.add(var.map_light_to_endpoint(light_, ref))
