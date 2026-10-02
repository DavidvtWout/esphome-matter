import sys
import unittest
from pathlib import Path

import esphome.config_validation as cv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "components"))

from matter.const import (
    CONF_COVER_ID,
    CONF_END_PRODUCT_TYPE,
    CONF_FEATURES,
)
from matter.data_model.device_types import DEVICE_TYPES_BY_CONF_KEY


class WindowCoveringSchemaTest(unittest.TestCase):
    def setUp(self):
        self.device_type = DEVICE_TYPES_BY_CONF_KEY["window_covering"]

    def validate(self, features, **extra):
        config = {CONF_FEATURES: features, **extra}
        return self.device_type._validate_features(config)

    def test_unmapped_configuration_is_preserved(self):
        config = self.validate(["Lift"])
        self.assertNotIn(CONF_END_PRODUCT_TYPE, config)

    def test_lift_only_mapping_uses_roller_metadata(self):
        config = self.validate(
            ["Lift", "PositionAwareLift"], **{CONF_COVER_ID: "cover"}
        )
        self.assertEqual(config[CONF_END_PRODUCT_TYPE], "roller_shade")
        self.assertEqual(
            self.device_type.config_constructor_args(config), ["0x00"]
        )
        self.assertIn("type = 0x00", self.device_type.config_lines(config, "cfg")[0])

    def test_venetian_mapping_uses_lift_and_tilt_metadata(self):
        config = self.validate(
            ["Lift", "PositionAwareLift", "Tilt", "PositionAwareTilt"],
            **{CONF_COVER_ID: "cover"},
        )
        self.assertEqual(
            config[CONF_END_PRODUCT_TYPE], "interior_venetian_blind"
        )
        self.assertEqual(
            self.device_type.config_constructor_args(config), ["0x0C"]
        )
        self.assertIn("type = 0x08", self.device_type.config_lines(config, "cfg")[0])

    def test_exterior_venetian_mapping(self):
        config = self.validate(
            ["Lift", "PositionAwareLift", "Tilt", "PositionAwareTilt"],
            **{
                CONF_COVER_ID: "cover",
                CONF_END_PRODUCT_TYPE: "exterior_venetian_blind",
            },
        )
        self.assertEqual(
            self.device_type.config_constructor_args(config), ["0x0D"]
        )

    def assert_invalid(self, features, message, **extra):
        with self.assertRaisesRegex(cv.Invalid, message):
            self.validate(features, **extra)

    def test_position_aware_features_require_parent_axis(self):
        self.assert_invalid(
            ["PositionAwareLift"], "requires Lift", **{CONF_COVER_ID: "cover"}
        )
        self.assert_invalid(
            ["Lift", "PositionAwareLift", "PositionAwareTilt"],
            "requires Tilt",
            **{CONF_COVER_ID: "cover"},
        )

    def test_absolute_position_is_rejected_for_mapped_cover(self):
        self.assert_invalid(
            ["Lift", "PositionAwareLift", "AbsolutePosition"],
            "AbsolutePosition is not supported",
            **{CONF_COVER_ID: "cover"},
        )

    def test_partial_mapped_feature_sets_are_rejected(self):
        self.assert_invalid(
            ["Lift"], "must enable either", **{CONF_COVER_ID: "cover"}
        )
        self.assert_invalid(
            ["Lift", "PositionAwareLift", "Tilt"],
            "must enable either",
            **{CONF_COVER_ID: "cover"},
        )


if __name__ == "__main__":
    unittest.main()
