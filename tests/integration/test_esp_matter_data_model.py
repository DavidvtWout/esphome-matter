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


LEGACY_FEATURE_HEADER = (
    Path("components")
    / "esp_matter"
    / "data_model"
    / "legacy"
    / "esp_matter_feature_impl.h"
)
FEATURE_HEADER = (
    Path("components") / "esp_matter" / "data_model" / "esp_matter_feature.h"
)


def _feature_header(esp_matter_source: Path) -> Path:
    """esp_matter_feature.h includes the legacy header unless the generated model is enabled."""
    legacy_header = esp_matter_source / LEGACY_FEATURE_HEADER
    if legacy_header.is_file():
        return legacy_header
    header = esp_matter_source / FEATURE_HEADER
    assert header.is_file(), f"Missing esp-matter feature header: {header}"
    return header


def _declared_feature_namespaces(header_text: str) -> dict[str, set[str]]:
    text = re.sub(r"/\*.*?\*/", "", header_text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    features: dict[str, set[str]] = {}
    aliases: dict[str, str] = {}
    stack: list[tuple[str, int]] = []
    depth = 0
    index = 0
    while index < len(text):
        if text.startswith("namespace ", index):
            match = re.match(
                r"namespace\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*([A-Za-z0-9_:]+)\s*)?",
                text[index:],
            )
            if match is None:
                index += 1
                continue
            name, alias = match.group(1), match.group(2)
            index += match.end()
            while index < len(text) and text[index].isspace():
                index += 1
            if alias and (index >= len(text) or text[index] != "{"):
                if stack and name == "feature":
                    aliases[stack[-1][0]] = alias.split("::")[0]
                continue
            if index < len(text) and text[index] == "{":
                depth += 1
                if len(stack) >= 2 and stack[-1][0] == "feature":
                    cluster_namespace = stack[-2][0]
                    if cluster_namespace not in ("esp_matter", "cluster"):
                        features.setdefault(cluster_namespace, set()).add(name)
                stack.append((name, depth))
                index += 1
                continue
            continue
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if stack and stack[-1][1] == depth + 1:
                stack.pop()
        index += 1

    resolved = {namespace: set(names) for namespace, names in features.items()}
    for cluster_namespace, target in aliases.items():
        if target in features:
            resolved[cluster_namespace] = set(features[target])
    return resolved


def _normalized_feature_name(name: str) -> str:
    return name.replace("_", "").replace("and", "")


def _feature_namespace_looks_renamed(
    generated: str, declared: str, cluster_namespace: str
) -> bool:
    if _normalized_feature_name(generated) == _normalized_feature_name(declared):
        return True
    if {generated + "ing", declared + "ing"} & {generated, declared}:
        return True
    generated_parts = generated.split("_")
    declared_parts = declared.split("_")
    if len(generated_parts) == len(declared_parts):
        differences = [
            (left, right)
            for left, right in zip(generated_parts, declared_parts)
            if left != right
        ]
        if len(differences) == 1:
            left, right = differences[0]
            if (
                left.rstrip("s") == right.rstrip("s")
                and abs(len(left) - len(right)) == 1
            ):
                return True
    # `namespace auto` is illegal C++, so esp-matter prefixes that feature.
    if generated == "auto" and declared.endswith("_auto"):
        return True
    if declared == f"{cluster_namespace}_{generated}":
        return True
    return False


def test_feature_namespaces_match_esp_matter(esp_matter_source: Path) -> None:
    """A spec feature name must not be emitted when esp-matter declares a different identifier.

    `with_features: [hue_and_saturation]` used to generate
    `feature::hue_and_saturation`, which does not exist. esp-matter declares
    `feature::hue_saturation`.
    """
    declared_by_cluster = _declared_feature_namespaces(
        _feature_header(esp_matter_source).read_text()
    )
    mismatches = []
    for cluster in CLUSTERS:
        declared = declared_by_cluster.get(cluster.espm_namespace)
        if not declared:
            continue
        for feature in cluster.features:
            if feature.namespace in declared:
                continue
            close = sorted(
                name
                for name in declared
                if _feature_namespace_looks_renamed(
                    feature.namespace, name, cluster.espm_namespace
                )
            )
            if close:
                mismatches.append(
                    f"{cluster.espm_namespace}::{feature.namespace} "
                    f"(YAML key {feature.conf_key}) looks like {', '.join(close)}"
                )
    assert not mismatches, (
        "esp-matter feature namespaces differ from the generated identifiers:\n"
        + "\n".join(mismatches)
    )
