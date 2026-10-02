"""Expose a mapped cover through ESPHome using the Matter command coordinator."""

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import cover
from esphome.const import CONF_ID, CONF_INTERNAL, CONF_NAME, CONF_PLATFORM

from .const import CONF_COVER_ID, CONF_ENDPOINTS
from .types import MatterComponent, matter_ns

DEPENDENCIES = ["matter"]

CONF_MATTER_ID = "matter_id"
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
    source_id = str(config[CONF_COVER_ID])
    sources = [
        item
        for item in full_config.get("cover", [])
        if str(item.get(CONF_ID)) == source_id
    ]
    if not sources or sources[0].get(CONF_PLATFORM) == "matter":
        raise cv.Invalid("matter cover_id must refer to a backend cover")
    if not sources[0].get(CONF_INTERNAL, False):
        raise cv.Invalid(
            "The backend of a Matter native cover must be internal: true so "
            "direct API commands cannot bypass command coordination"
        )
    if config.get(CONF_NAME) == sources[0].get(CONF_NAME):
        raise cv.Invalid(
            "The native cover must have a different name from its backend "
            "so web requests select the coordinated control entity"
        )

    endpoints = full_config.get("matter", {}).get(CONF_ENDPOINTS, {})
    matches = [
        endpoint
        for endpoint in endpoints.values()
        if str(endpoint.get("window_covering", {}).get(CONF_COVER_ID)) == source_id
    ]
    if len(matches) != 1:
        raise cv.Invalid(
            "matter cover_id must be mapped to exactly one Matter window_covering endpoint"
        )


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    var = await cover.new_cover(config)
    await cg.register_component(var, config)
    await cg.register_parented(var, config[CONF_MATTER_ID])
    source = await cg.get_variable(config[CONF_COVER_ID])
    cg.add(var.set_source(source))
