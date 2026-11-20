import asyncio
import importlib.util
from pathlib import Path

import esphome.codegen as cg
from esphome.core import CORE

from components.matter.const import CONF_CLUSTERS, CONF_WITH_FEATURES
from components.matter.data_model.clusters import CLUSTERS_BY_CONF_KEY
from components.matter.endpoints import Endpoint

# Spec names stay as the YAML keys. These are the identifiers esp-matter actually
# declares, which are not produced by snake_case of the spec feature name.
EXPECTED_ESP_MATTER_NAMESPACES = {
    ("color_control", "hue_and_saturation"): "hue_saturation",
    ("energy_evse", "so_c_reporting"): "soc_reporting",
    ("energy_evse", "v2_x"): "v2x",
    ("door_lock", "unbolt"): "unbolting",
    ("door_lock", "week_day_access_schedules"): "weekday_access_schedules",
    ("door_lock", "credentials_over_the_air_access"): "credential_over_the_air_access",
    ("fan_control", "auto"): "fan_auto",
}


def test_feature_yaml_keys_keep_spec_names() -> None:
    for (cluster_key, conf_key), namespace in EXPECTED_ESP_MATTER_NAMESPACES.items():
        feature = CLUSTERS_BY_CONF_KEY[cluster_key].get_feature(conf_key)
        assert feature is not None, f"{cluster_key}.{conf_key} is missing"
        assert feature.conf_key == conf_key
        assert feature.namespace == namespace
        assert feature.namespace != feature.conf_key


def test_hue_and_saturation_codegen_uses_esp_matter_namespace() -> None:
    endpoint = Endpoint(
        1,
        {
            CONF_CLUSTERS: {},
            "extended_color_light": {CONF_WITH_FEATURES: ["hue_and_saturation"]},
        },
    )
    asyncio.run(endpoint.register(cg.MockObj("matter", "->")))

    generated = CORE.cpp_main_section
    assert (
        "esp_matter::cluster::color_control::feature::hue_saturation::add" in generated
    )
    assert "feature::hue_and_saturation" not in generated


def test_feature_override_merge_keeps_other_feature_fields() -> None:
    converter_path = Path(__file__).parents[2] / "tools" / "zap_converter.py"
    spec = importlib.util.spec_from_file_location("zap_converter", converter_path)
    assert spec is not None and spec.loader is not None
    converter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(converter)

    clusters = {
        "768": {
            "name": "Color Control",
            "features": {
                "0": {
                    "code": "HS",
                    "name": "Hue And Saturation",
                    "conformance": {"optional": True},
                }
            },
        }
    }
    converter.apply_cluster_overrides(
        clusters,
        {
            "Color Control": {
                "chip_fqn": "ColorControlServer",
                "features": {"HS": {"esp_matter_namespace": "hue_saturation"}},
            }
        },
    )

    feature = clusters["768"]["features"]["0"]
    assert feature["name"] == "Hue And Saturation"
    assert feature["conformance"] == {"optional": True}
    assert feature["esp_matter_namespace"] == "hue_saturation"
    assert clusters["768"]["chip_fqn"] == "ColorControlServer"
