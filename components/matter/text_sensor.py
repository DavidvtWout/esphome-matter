"""Expose stored Matter commissioning codes through the native ESPHome API."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import text_sensor
from esphome.const import CONF_ID, ENTITY_CATEGORY_DIAGNOSTIC

from .const import (
    CONF_COMPRESSED_FABRIC_ID,
    CONF_FABRIC_ID,
    CONF_LABEL,
    CONF_MANUAL_PAIRING_CODE,
    CONF_NODE_ID,
    CONF_QR_CODE,
    CONF_VENDOR_ID,
)
from .types import MatterComponent

DEPENDENCIES = ["matter"]

FABRIC_KEYS = tuple(f"fabric_{index}" for index in range(1, 256))


FABRIC_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.Optional(CONF_COMPRESSED_FABRIC_ID): text_sensor.text_sensor_schema(
                icon="mdi:identifier",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_FABRIC_ID): text_sensor.text_sensor_schema(
                icon="mdi:identifier",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_LABEL): text_sensor.text_sensor_schema(
                icon="mdi:label",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_NODE_ID): text_sensor.text_sensor_schema(
                icon="mdi:identifier",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_VENDOR_ID): text_sensor.text_sensor_schema(
                icon="mdi:identifier",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
        }
    ),
    cv.has_at_least_one_key(
        CONF_COMPRESSED_FABRIC_ID,
        CONF_FABRIC_ID,
        CONF_LABEL,
        CONF_NODE_ID,
        CONF_VENDOR_ID,
    ),
)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.use_id(MatterComponent),
            cv.Optional(CONF_MANUAL_PAIRING_CODE): text_sensor.text_sensor_schema(
                icon="mdi:key",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_QR_CODE): text_sensor.text_sensor_schema(
                icon="mdi:qrcode",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            **{cv.Optional(key): FABRIC_SCHEMA for key in FABRIC_KEYS},
        }
    ),
    cv.has_at_least_one_key(CONF_MANUAL_PAIRING_CODE, CONF_QR_CODE, *FABRIC_KEYS),
)


async def to_code(config):
    parent = await cg.get_variable(config[CONF_ID])

    if sensor_config := config.get(CONF_MANUAL_PAIRING_CODE):
        sens = await text_sensor.new_text_sensor(sensor_config)
        cg.add(parent.set_manual_pairing_code_sensor(sens))

    if sensor_config := config.get(CONF_QR_CODE):
        sens = await text_sensor.new_text_sensor(sensor_config)
        cg.add(parent.set_qr_code_sensor(sens))

    for slot, key in enumerate(FABRIC_KEYS):
        if fabric_config := config.get(key):
            if sensor_config := fabric_config.get(CONF_COMPRESSED_FABRIC_ID):
                sens = await text_sensor.new_text_sensor(sensor_config)
                cg.add(parent.set_fabric_compressed_id_sensor(slot, sens))
            if sensor_config := fabric_config.get(CONF_FABRIC_ID):
                sens = await text_sensor.new_text_sensor(sensor_config)
                cg.add(parent.set_fabric_id_sensor(slot, sens))
            if sensor_config := fabric_config.get(CONF_LABEL):
                sens = await text_sensor.new_text_sensor(sensor_config)
                cg.add(parent.set_fabric_label_sensor(slot, sens))
            if sensor_config := fabric_config.get(CONF_NODE_ID):
                sens = await text_sensor.new_text_sensor(sensor_config)
                cg.add(parent.set_fabric_node_id_sensor(slot, sens))
            if sensor_config := fabric_config.get(CONF_VENDOR_ID):
                sens = await text_sensor.new_text_sensor(sensor_config)
                cg.add(parent.set_fabric_vendor_id_sensor(slot, sens))
