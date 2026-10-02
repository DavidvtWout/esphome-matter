"""Expose stored Matter commissioning codes through the native ESPHome API."""

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import text_sensor
from esphome.const import ENTITY_CATEGORY_DIAGNOSTIC

from .const import CONF_MANUAL_PAIRING_CODE, CONF_MATTER_ID, CONF_QR_CODE
from .types import MatterComponent
from .validation import validate_unique_text_sensors

DEPENDENCIES = ["matter"]

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(CONF_MATTER_ID): cv.use_id(MatterComponent),
            cv.Optional(CONF_MANUAL_PAIRING_CODE): text_sensor.text_sensor_schema(
                icon="mdi:key",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_QR_CODE): text_sensor.text_sensor_schema(
                icon="mdi:qrcode",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
        }
    ),
    cv.has_at_least_one_key(CONF_MANUAL_PAIRING_CODE, CONF_QR_CODE),
)


def _final_validate(config):
    validate_unique_text_sensors(config, fv.full_config.get())


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    cg.add_define("USE_MATTER_TEXT_SENSOR")
    parent = await cg.get_variable(config[CONF_MATTER_ID])

    if sensor_config := config.get(CONF_MANUAL_PAIRING_CODE):
        sens = await text_sensor.new_text_sensor(sensor_config)
        cg.add(parent.set_manual_pairing_code_sensor(sens))

    if sensor_config := config.get(CONF_QR_CODE):
        sens = await text_sensor.new_text_sensor(sensor_config)
        cg.add(parent.set_qr_code_sensor(sens))
