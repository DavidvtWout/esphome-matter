import copy
from pathlib import Path

import pytest
from esphome.__main__ import generate_cpp_contents
from esphome.config import validate_config
from esphome.core import CORE
from esphome.yaml_util import load_yaml

CONFIG_DIR = Path(__file__).parents[1] / "configs"


def generate(config_name="esp32-window-covering.yaml", edit=None):
    path = CONFIG_DIR / config_name
    raw = copy.deepcopy(load_yaml(path))
    if edit is not None:
        edit(raw)
    CORE.config_path = path
    config = validate_config(raw, {})
    assert not config.errors, "\n".join(str(error) for error in config.errors)
    CORE.config = config
    generate_cpp_contents(config)
    return CORE.cpp_main_section


@pytest.mark.parametrize(
    "config_name",
    ["esp32-window-covering.yaml", "esp32-thread-window-covering.yaml"],
)
def test_existing_public_cover_is_mapped(config_name):
    generated = generate(config_name)
    assert "register_cover(simulated_blind, 1)" in generated
    assert "window_covering::feature::lift::get_id()" in generated
    assert "window_covering::feature::tilt::get_id()" in generated
    assert "position_aware_lift::add" in generated
    assert "position_aware_tilt::add" in generated
    assert "window_covering::config_t device_config_0{0x0C}" in generated
    assert "device_config_0.window_covering.type = 0x08" in generated


@pytest.mark.parametrize(
    "features,expected_type,expected_product",
    [
        (["position_aware_lift"], "0x00", "0x00"),
        (["position_aware_tilt"], "0x07", "0x0C"),
    ],
)
def test_single_axis_metadata(features, expected_type, expected_product):
    def edit(raw):
        raw["matter"]["endpoints"]["1"]["window_covering"]["with_features"] = features

    generated = generate(edit=edit)
    assert f"window_covering::config_t device_config_0{{{expected_product}}}" in generated
    assert f"device_config_0.window_covering.type = {expected_type}" in generated


def test_unmapped_endpoint_metadata():
    def edit(raw):
        endpoint = raw["matter"]["endpoints"]["1"]["window_covering"]
        del endpoint["cover_id"]
        endpoint["with_features"] = ["tilt"]

    generated = generate(edit=edit)
    assert "register_cover(simulated_blind, 1)" not in generated
    assert "window_covering::config_t device_config_0{0x0C}" in generated
    assert "device_config_0.window_covering.type = 0x07" in generated


def test_explicit_end_product_type():
    def edit(raw):
        raw["matter"]["endpoints"]["1"]["window_covering"]["end_product_type"] = (
            "exterior_venetian_blind"
        )

    assert "window_covering::config_t device_config_0{0x0D}" in generate(edit=edit)


@pytest.mark.parametrize(
    "features,message",
    [
        (["position_aware_lift", "absolute_position"], None),
        (["lift"], "position_aware_lift"),
        (["position_aware_lift", "tilt"], "position_aware_tilt"),
    ],
)
def test_adapter_rejects_unimplemented_position_units(features, message):
    path = CONFIG_DIR / "esp32-window-covering.yaml"
    raw = load_yaml(path)
    raw["matter"]["endpoints"]["1"]["window_covering"]["with_features"] = features
    CORE.config_path = path
    config = validate_config(raw, {})
    assert config.errors
    if message is not None:
        assert message in "\n".join(str(error) for error in config.errors)
