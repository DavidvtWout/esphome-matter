"""Validate public platform schemas and generated setup code without a build.

Complete ESPHome configurations use local component sources and simulated
covers. Code generation stays in memory and never controls a device.
"""

import copy
import unittest
from pathlib import Path

from esphome.__main__ import generate_cpp_contents
from esphome.config import validate_config
from esphome.core import CORE
from esphome.yaml_util import load_yaml

ROOT = Path(__file__).resolve().parents[1]
WIFI_FIXTURE = ROOT / "tests/configs/esp32-window-covering.yaml"
THREAD_FIXTURE = ROOT / "tests/configs/esp32-thread-window-covering.yaml"
LIFT_FEATURES = ["lift", "position_aware_lift"]


class MatterPlatformTest(unittest.TestCase):
    def setUp(self):
        self.raw = load_yaml(WIFI_FIXTURE)

    def tearDown(self):
        CORE.reset()

    def validate(self, raw=None, fixture=WIFI_FIXTURE):
        CORE.reset()
        CORE.config_path = fixture
        return validate_config(copy.deepcopy(self.raw if raw is None else raw), {})

    def assert_valid(self, raw=None, fixture=WIFI_FIXTURE):
        result = self.validate(raw, fixture)
        self.assertFalse(
            result.errors, "\n".join(str(error) for error in result.errors)
        )
        return result

    def assert_invalid(self, message, raw=None):
        result = self.validate(raw)
        self.assertTrue(result.errors)
        errors = "\n".join(str(error) for error in result.errors).lower()
        self.assertRegex(errors, message.lower())

    def window_config(self):
        return self.raw["matter"]["endpoints"]["1"]["window_covering"]

    def test_wifi_and_thread_generate_native_cover_and_pairing_sensors(self):
        for fixture in (WIFI_FIXTURE, THREAD_FIXTURE):
            with self.subTest(fixture=fixture.name):
                raw = load_yaml(fixture)
                config = self.assert_valid(raw, fixture)
                CORE.config = config
                generate_cpp_contents(config)
                generated = CORE.cpp_main_section
                self.assertIn("matter::MatterNativeCover()", generated)
                self.assertIn(
                    "native_venetian_blind->set_source(simulated_venetian_blind)",
                    generated,
                )
                self.assertIn(
                    "set_manual_pairing_code_sensor(matter_manual_code)", generated
                )
                self.assertIn("set_qr_code_sensor(matter_qr_payload)", generated)
                self.assertIn("set_cover(simulated_venetian_blind)", generated)
                self.assertIn(
                    "map_cover_to_endpoint(simulated_venetian_blind, 1, true)",
                    generated,
                )
                self.assertTrue(
                    any(
                        define.name == "USE_MATTER_TEXT_SENSOR"
                        for define in CORE.defines
                    )
                )

    def test_cluster_features_cannot_bypass_mapping_constraints(self):
        self.raw["matter"]["endpoints"]["1"]["clusters"] = {
            "window_covering": {"with_features": ["absolute_position"]}
        }
        self.assert_invalid("cluster features cannot add capabilities")

    def generate_unmapped_window(self, device_features, cluster_features):
        self.raw["cover"] = self.raw["cover"][:1]
        self.raw.pop("script")
        self.raw["matter"]["endpoints"]["1"] = {
            "window_covering": {"with_features": device_features},
            "clusters": {"window_covering": {"with_features": cluster_features}},
        }
        CORE.config = self.assert_valid()
        generate_cpp_contents(CORE.config)
        return CORE.cpp_main_section

    def test_unmapped_device_and_cluster_features_are_combined(self):
        generated = self.generate_unmapped_window(["position_aware_lift"], ["lift"])
        self.assertIn("window_covering::feature::lift::get_id()", generated)
        self.assertIn("window_covering::feature::position_aware_lift::add", generated)
        self.assertNotIn("map_cover_to_endpoint", generated)

    def test_unmapped_cluster_only_features_are_preserved(self):
        generated = self.generate_unmapped_window([], ["lift", "position_aware_lift"])
        self.assertIn("window_covering::feature::lift::get_id()", generated)
        self.assertIn("window_covering::feature::position_aware_lift::add", generated)
        self.assertNotIn("map_cover_to_endpoint", generated)

    def test_duplicate_mapping_without_native_proxy_is_rejected(self):
        self.raw["cover"] = self.raw["cover"][:1]
        self.raw["script"] = self.raw["script"][:1]
        self.raw["matter"]["endpoints"][2] = copy.deepcopy(
            self.raw["matter"]["endpoints"]["1"]
        )
        self.assert_invalid("exactly one|more than one|multiple|already mapped")

    def test_native_proxy_cannot_be_an_endpoint_backend(self):
        self.window_config()["cover_id"] = "native_venetian_blind"
        self.assert_invalid("backend")

    def test_native_proxy_requires_internal_backend(self):
        self.raw["cover"][0]["internal"] = False
        self.assert_invalid("internal: true")

    def test_native_proxy_requires_distinct_name(self):
        self.raw["cover"][1]["name"] = self.raw["cover"][0]["name"]
        self.assert_invalid("different name")

    def test_native_proxy_requires_mapped_backend(self):
        self.raw["matter"]["endpoints"]["1"] = {"on_off_light_switch": {}}
        self.assert_invalid("mapped|mapping")

    def test_cancellation_rejects_native_proxy_id(self):
        self.raw["script"][0]["then"][0]["matter.cover.cancel_pending"]["cover_id"] = (
            "native_venetian_blind"
        )
        self.assert_invalid("backend")

    def test_cancellation_rejects_unmapped_backend(self):
        self.raw["cover"].append(
            {"platform": "template", "id": "unmapped_cover", "internal": True}
        )
        self.raw["script"][0]["then"][0]["matter.cover.cancel_pending"]["cover_id"] = (
            "unmapped_cover"
        )
        self.assert_invalid("mapped|mapping")

    def test_nested_cancellation_rejects_native_proxy_id(self):
        self.raw["script"][0]["then"] = [
            {
                "if": {
                    "condition": {"script.is_running": "local_cover_stop"},
                    "then": [
                        {
                            "matter.cover.cancel_pending": {
                                "cover_id": "native_venetian_blind"
                            }
                        }
                    ],
                }
            }
        ]
        self.assert_invalid("backend")

    def test_cancellation_rejects_unknown_matter_parent(self):
        self.raw["script"][0]["then"][0]["matter.cover.cancel_pending"]["id"] = (
            "missing_matter"
        )
        self.assert_invalid("missing_matter")

    def test_unrelated_json_keys_are_not_interpreted_as_actions(self):
        self.raw["http_request"] = {"verify_ssl": False}
        self.raw["script"].append(
            {
                "id": "send_application_payload",
                "then": [
                    {
                        "http_request.post": {
                            "url": "http://example.invalid",
                            "json": {
                                "matter.cover.cancel_pending": "ordinary application payload"
                            },
                        }
                    }
                ],
            }
        )
        self.assert_valid()

    def test_pairing_platform_requires_at_least_one_sensor(self):
        self.raw["text_sensor"] = [{"platform": "matter"}]
        self.assert_invalid("at least one")

    def test_duplicate_pairing_sensor_kind_is_rejected(self):
        for key in ("manual_pairing_code", "qr_code"):
            with self.subTest(key=key):
                raw = copy.deepcopy(self.raw)
                raw["text_sensor"].append(
                    {"platform": "matter", key: {"name": "Duplicate code"}}
                )
                self.assert_invalid("duplicate|only one|already configured", raw)

    def test_pairing_sensor_kinds_can_use_separate_platform_entries(self):
        self.raw["text_sensor"] = [
            {"platform": "matter", "manual_pairing_code": {"name": "Setup code"}},
            {"platform": "matter", "qr_code": {"name": "QR payload"}},
        ]
        self.assert_valid()

    def test_unknown_product_type_is_rejected(self):
        self.window_config()["end_product_type"] = "typo_blind"
        self.assert_invalid("end_product_type")

    def test_legacy_features_key_is_rejected(self):
        self.window_config()["features"] = self.window_config().pop("with_features")
        self.assert_invalid("features")

    def test_camel_case_features_are_rejected(self):
        self.window_config()["with_features"] = ["Lift", "PositionAwareLift"]
        self.assert_invalid("lift")

    def test_lift_only_venetian_metadata_is_rejected(self):
        self.window_config()["with_features"] = LIFT_FEATURES
        self.assert_invalid("roller_shade")

    def test_lift_and_tilt_roller_metadata_is_rejected(self):
        self.window_config()["end_product_type"] = "roller_shade"
        self.assert_invalid("venetian")


if __name__ == "__main__":
    unittest.main()
