import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_LIGHT_ID, CONF_SENSOR_ID
from esphome.types import ConfigType

from .const import *
from .data_model import DEVICE_TYPES, DEVICE_TYPES_BY_CONF_KEY
from .types import MatterEndpointRef


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
        }
        | {
            cv.Optional(device_type.conf_key): device_type.schema()
            for device_type in DEVICE_TYPES
        }
    ),
)


async def register_endpoints(var, config: ConfigType):
    for endpoint_id, endpoint_config in config[CONF_ENDPOINTS].items():
        # Register endpoint
        cg.add(var.register_endpoint(endpoint_id))

        enable_binding = False
        for conf_key, device_config in endpoint_config.items():
            try:
                device_type = DEVICE_TYPES_BY_CONF_KEY[conf_key]
            except KeyError:
                continue

            enable_binding |= any(c.name == "Binding" for c in device_type.clusters)

            # Register device type
            register_device_type = var.register_device_type.template(
                cg.RawExpression(
                    f"esp_matter::endpoint::{device_type.namespace}::config_t"
                ),
                cg.RawExpression(f"esp_matter::endpoint::{device_type.namespace}::add"),
            )
            cg.add(register_device_type(endpoint_id, device_type.namespace))

            # Register ESPHome entities
            if CONF_SENSOR_ID in device_config:
                sensor_ = await cg.get_variable(device_config[CONF_SENSOR_ID])
                cg.add(var.map_sensor_to_endpoint(sensor_, endpoint_id))
            elif CONF_LIGHT_ID in device_config:
                light_ = await cg.get_variable(device_config[CONF_LIGHT_ID])
                cg.add(var.map_light_to_endpoint(light_, endpoint_id))

        # Register binding on endpoint
        if enable_binding:
            cg.add(var.register_binding(endpoint_id))
