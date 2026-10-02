import re
from pathlib import Path

import pytest

from components.matter.data_model.clusters import CLUSTERS, Cluster
from components.matter.data_model.device_types import DEVICE_TYPES, DeviceType
from tests.integration.required_device_types import REQUIRED_DEVICE_TYPES

LEGACY_CLUSTER_HEADER = (
    Path("components")
    / "esp_matter"
    / "data_model"
    / "legacy"
    / "esp_matter_cluster_impl.h"
)
unknown_device_types = [
    name
    for name in REQUIRED_DEVICE_TYPES
    if not any(device_type.name == name for device_type in DEVICE_TYPES)
]
assert not unknown_device_types, (
    f"Unknown required device types: {', '.join(sorted(unknown_device_types))}"
)
REQUIRED_CLUSTER_IDS = [
    cluster.id
    for device_type in DEVICE_TYPES
    if device_type.name in REQUIRED_DEVICE_TYPES
    for cluster in device_type.clusters
]


def _required_or_allowed(value, name: str, required: bool):
    if required:
        return pytest.param(value, id=name)
    return pytest.param(
        value,
        id=name,
        marks=pytest.mark.allowed_to_fail(reason="Not required to be supported yet"),
    )


DEVICE_TYPE_PARAMS = tuple(
    _required_or_allowed(
        device_type,
        device_type.name,
        device_type.name in REQUIRED_DEVICE_TYPES,
    )
    for device_type in sorted(DEVICE_TYPES, key=lambda device_type: device_type.name)
)
CLUSTER_PARAMS = tuple(
    _required_or_allowed(cluster, cluster.conf_key, cluster.id in REQUIRED_CLUSTER_IDS)
    for cluster in sorted(CLUSTERS, key=lambda cluster: cluster.conf_key)
)


@pytest.mark.parametrize(
    "device_type",
    DEVICE_TYPE_PARAMS,
)
def test_device_type_is_defined_in_esp_matter(
    esp_matter_device_type_ids: set[int],
    device_type: DeviceType,
) -> None:
    assert device_type.id in esp_matter_device_type_ids, (
        f"esp-matter does not define {device_type.name} ({device_type.id:#06x})"
    )


def _chip_header_path(esp_matter_source: Path, cluster: Cluster) -> Path:
    include = re.fullmatch(r"#include <(.+)>", cluster.chip_include)
    assert include is not None, f"Invalid CHIP include: {cluster.chip_include}"
    return (
        esp_matter_source / "connectedhomeip" / "connectedhomeip" / "src" / include[1]
    )


@pytest.mark.parametrize(
    "cluster",
    CLUSTER_PARAMS,
)
def test_cluster_is_used_by_device_type(cluster: Cluster) -> None:
    assert any(
        device_type_cluster.id == cluster.id
        for device_type in DEVICE_TYPES
        for device_type_cluster in device_type.clusters
    ), f"No device type refers to {cluster.conf_key}"


@pytest.mark.parametrize(
    "cluster",
    CLUSTER_PARAMS,
)
def test_cluster_espm_namespace(
    esp_matter_source: Path,
    cluster: Cluster,
) -> None:
    esp_matter_header = esp_matter_source / LEGACY_CLUSTER_HEADER
    assert re.search(
        rf"^namespace {re.escape(cluster.espm_namespace)} \{{$",
        esp_matter_header.read_text(),
        re.MULTILINE,
    ), f"esp-matter does not define cluster namespace {cluster.espm_namespace}"


@pytest.mark.parametrize(
    "cluster",
    CLUSTER_PARAMS,
)
def test_cluster_chip_include(
    esp_matter_source: Path,
    cluster: Cluster,
) -> None:
    if cluster.chip_include is None:
        pytest.skip("CHIP include is not required")
    chip_header = _chip_header_path(esp_matter_source, cluster)
    assert chip_header.is_file(), f"Missing CHIP header: {cluster.chip_include}"


@pytest.mark.parametrize(
    "cluster",
    CLUSTER_PARAMS,
)
def test_cluster_chip_fqn(
    esp_matter_source: Path,
    cluster: Cluster,
) -> None:
    if cluster.chip_include is None or cluster.chip_fqn is None:
        pytest.skip("CHIP class is not required")
    chip_header = _chip_header_path(esp_matter_source, cluster)
    if not chip_header.is_file():
        pytest.skip("CHIP include test failed")

    *namespaces, chip_class = cluster.chip_fqn.split("::")
    contents = chip_header.read_text()
    for namespace in namespaces:
        assert re.search(
            rf"\bnamespace\s+(?:\w+::)*{re.escape(namespace)}(?:::\w+)*\s*\{{",
            contents,
        ), (
            f"Namespace {namespace} from {cluster.chip_fqn} is not declared by {cluster.chip_include}"
        )
    assert re.search(
        rf"\b(?:class|struct)\s+{re.escape(chip_class)}\b",
        contents,
    ), f"{cluster.chip_fqn} is not declared by {cluster.chip_include}"
