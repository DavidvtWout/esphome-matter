import asyncio

import esphome.codegen as cg
from esphome.core import CORE

from components.matter.const import CONF_CLUSTERS, CONF_WITH_FEATURES
from components.matter.data_model.clusters import CLUSTERS_BY_NAME
from components.matter.data_model.conformance import resolve_feature_requirements
from components.matter.endpoints import Endpoint


def test_events_enable_features() -> None:
    """The switch.initial_press requires the momentary_switch feature and should automatically enable the momentary_switch_release feature."""
    cluster = CLUSTERS_BY_NAME["Switch"]
    event = cluster.get_event("initial_press")

    inferred_features = resolve_feature_requirements(
        [event.conformance],
        {feature.code: feature.conformance for feature in cluster.features},
        set(),
    )

    assert inferred_features == {"MS"}


def test_feature_cascading() -> None:
    """The switch.short_release requires the momentary_switch_release feature, which in turn requires the momentary_switch feature, so both should be enabled."""
    cluster = CLUSTERS_BY_NAME["Switch"]
    event = cluster.get_event("short_release")

    inferred_features = resolve_feature_requirements(
        [event.conformance],
        {feature.code: feature.conformance for feature in cluster.features},
        set(),
    )

    assert inferred_features == {"MS", "MSR"}


def test_Endpoint_feature_registration() -> None:
    """Test if features are actually registered on an endpoint."""
    cluster = CLUSTERS_BY_NAME["Switch"]
    event = cluster.get_event("short_release")
    assert event is not None

    endpoint = Endpoint(
        1,
        {
            CONF_CLUSTERS: {},
            "generic_switch": {CONF_WITH_FEATURES: []},
        },
    )
    endpoint.register_usage(cluster, event)
    endpoint.resolve()

    assert endpoint._cluster_configs["Switch"].enabled_features == {
        "MomentarySwitch": True,
        "MomentarySwitchRelease": True,
    }

    # "simulate" an esphome var with MockObj.
    asyncio.run(endpoint.register(cg.MockObj("matter", "->")))

    # momentary_switch is a "choice" feature and must be added to the feature_flags of the device config.
    assert (
        "switch_cluster.feature_flags = esp_matter::cluster::switch_cluster::feature::momentary_switch::get_id()"
        in CORE.cpp_main_section
    )
    # momentary_switch_release is optional and is added to the cluster after it has been created.
    assert (
        "esp_matter::cluster::switch_cluster::feature::momentary_switch_release::add"
        in CORE.cpp_main_section
    )
