import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.types import ConfigType

from .const import *
from .device_types import DEVICE_TYPES
from .types import MatterEndpointRef


ENDPOINT_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(MatterEndpointRef),
            cv.Optional(CONF_ENABLE_BINDING): cv.boolean,
        }
        | {
            cv.Optional(dt_name): dt_config["schema"]
            for dt_name, dt_config in DEVICE_TYPES.items()
        }
    ),
)


def _endpoint_binding_enabled(endpoint_config: ConfigType) -> bool:
    if CONF_ENABLE_BINDING in endpoint_config:
        return endpoint_config[CONF_ENABLE_BINDING]
    return any(
        DEVICE_TYPES[device_type].get(CONF_ENABLE_BINDING, False)
        for device_type in endpoint_config
        if device_type in DEVICE_TYPES
    )


async def configure_endpoints(var, config: ConfigType):
    for endpoint_id, endpoint_config in config[CONF_ENDPOINTS].items():
        cg.add(var.register_endpoint(endpoint_id))
        if _endpoint_binding_enabled(endpoint_config):
            cg.add(var.register_binding(endpoint_id))
        for device_type, device_config in endpoint_config.items():
            if device_type not in DEVICE_TYPES:
                continue
            register_device_type = var.register_device_type.template(
                cg.RawExpression(f"esp_matter::endpoint::{device_type}::config_t"),
                cg.RawExpression(f"esp_matter::endpoint::{device_type}::add"),
            )
            cg.add(register_device_type(endpoint_id, device_type))

            # Map entities to Matter endpoints. The device type schema must make sure that
            # only one <entity>_id is allowed for a device type.
            entity_ids = [
                value
                for key, value in device_config.items()
                if str(key).endswith("_id")
            ]
            if len(entity_ids) > 1:
                raise cv.Invalid("A Matter device type can reference only one entity")
            if entity_ids:
                entity = await cg.get_variable(entity_ids[0])
                map_entity_to_endpoint = var.map_entity_to_endpoint.template(
                    DEVICE_TYPES[device_type]["mapping"]
                )
                cg.add(map_entity_to_endpoint(entity, endpoint_id))
