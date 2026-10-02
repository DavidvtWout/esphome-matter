"""Shared final validation for Matter cover ownership and diagnostics."""

import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_PLATFORM, CONF_TYPE_ID
from esphome.core import ID

from .const import (
    CONF_COVER_ID,
    CONF_ENDPOINTS,
    CONF_MANUAL_PAIRING_CODE,
    CONF_MATTER,
    CONF_MATTER_ID,
    CONF_QR_CODE,
)

_CANCEL_PENDING_ACTION = "matter.cover.cancel_pending"


def _backend_cover(full_config, cover_id):
    for config in full_config.get("cover", []):
        if str(config.get(CONF_ID)) != str(cover_id):
            continue
        if config.get(CONF_PLATFORM) == CONF_MATTER:
            raise cv.Invalid(
                "Matter cover_id must refer to a physical backend cover, "
                "not a Matter native cover",
                path=[CONF_COVER_ID],
            )
        return config
    raise cv.Invalid(
        "Matter cover_id must refer to a backend cover", path=[CONF_COVER_ID]
    )


def _mapped_covers(matter_config):
    for endpoint_id, endpoint in matter_config.get(CONF_ENDPOINTS, {}).items():
        if cover_id := endpoint.get("window_covering", {}).get(CONF_COVER_ID):
            yield endpoint_id, cover_id


def require_cover_mapping(
    full_config, cover_id, matter_id, *, parent_key=CONF_MATTER_ID
):
    """Return a physical backend owned by exactly one endpoint of the parent."""
    matter_config = full_config.get(CONF_MATTER, {})
    if str(matter_config.get(CONF_ID)) != str(matter_id):
        raise cv.Invalid(
            "The selected Matter parent does not own this cover mapping",
            path=[parent_key],
        )
    backend = _backend_cover(full_config, cover_id)
    matches = [
        endpoint_id
        for endpoint_id, mapped_cover_id in _mapped_covers(matter_config)
        if str(mapped_cover_id) == str(cover_id)
    ]
    if len(matches) != 1:
        raise cv.Invalid(
            "Matter cover_id must be mapped to exactly one Matter "
            "window_covering endpoint",
            path=[CONF_COVER_ID],
        )
    return backend


def validate_cover_mappings(matter_config, full_config):
    """Reject multiple coordinators for the same physical cover."""
    seen = {}
    for endpoint_id, cover_id in _mapped_covers(matter_config):
        with cv.prepend_path([CONF_ENDPOINTS, endpoint_id, "window_covering"]):
            _backend_cover(full_config, cover_id)
            key = str(cover_id)
            if key in seen:
                raise cv.Invalid(
                    f"Cover '{cover_id}' is already mapped to Matter endpoint "
                    f"{seen[key]}; each backend may be mapped to exactly one "
                    "Matter window_covering endpoint",
                    path=[CONF_COVER_ID],
                )
            seen[key] = endpoint_id


def _cancel_pending_actions(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            # Match validated action wrappers, not arbitrary user dictionaries
            # such as HTTP JSON payloads that happen to contain this key.
            if key == _CANCEL_PENDING_ACTION and isinstance(
                value.get(CONF_TYPE_ID), ID
            ):
                yield child_path, child
            else:
                yield from _cancel_pending_actions(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _cancel_pending_actions(child, (*path, index))


def validate_cancel_pending_actions(full_config):
    """Actions have no final-validation hook, so validate them from Matter."""
    for path, action in _cancel_pending_actions(full_config):
        with cv.prepend_path([cv.ROOT_CONFIG_PATH, *path]):
            require_cover_mapping(
                full_config,
                action[CONF_COVER_ID],
                action[CONF_ID],
                parent_key=CONF_ID,
            )


def validate_unique_text_sensors(config, full_config):
    """A Matter parent has one publishing slot for each commissioning code."""
    parent_id = str(config[CONF_MATTER_ID])
    for kind in (CONF_MANUAL_PAIRING_CODE, CONF_QR_CODE):
        if kind not in config:
            continue
        matches = [
            item
            for item in full_config.get("text_sensor", [])
            if item.get(CONF_PLATFORM) == CONF_MATTER
            and str(item.get(CONF_MATTER_ID)) == parent_id
            and kind in item
        ]
        if len(matches) > 1:
            raise cv.Invalid(
                f"Only one {kind} text sensor may be configured per Matter parent",
                path=[kind],
            )
