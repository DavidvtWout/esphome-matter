"""Expose a mapped cover through ESPHome using the Matter command coordinator."""

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import cover
from esphome.const import CONF_INTERNAL, CONF_NAME

from .const import CONF_COVER_ID, CONF_MATTER_ID
from .types import MatterComponent, matter_ns
from .validation import require_cover_mapping

DEPENDENCIES = ["matter"]

MatterNativeCover = matter_ns.class_("MatterNativeCover", cover.Cover, cg.Component)

CONFIG_SCHEMA = (
    cover.cover_schema(MatterNativeCover)
    .extend(
        {
            cv.GenerateID(CONF_MATTER_ID): cv.use_id(MatterComponent),
            cv.Required(CONF_COVER_ID): cv.use_id(cover.Cover),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
)


def _final_validate(config):
    full_config = fv.full_config.get()
    source = require_cover_mapping(
        full_config, config[CONF_COVER_ID], config[CONF_MATTER_ID]
    )
    if not source.get(CONF_INTERNAL, False):
        raise cv.Invalid(
            "The backend of a Matter native cover must be internal: true so "
            "direct API commands cannot bypass command coordination"
        )
    if config.get(CONF_NAME) == source.get(CONF_NAME):
        raise cv.Invalid(
            "The native cover must have a different name from its backend "
            "so web requests select the coordinated control entity"
        )


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    var = await cover.new_cover(config)
    await cg.register_component(var, config)
    await cg.register_parented(var, config[CONF_MATTER_ID])
    source = await cg.get_variable(config[CONF_COVER_ID])
    cg.add(var.set_source(source))
