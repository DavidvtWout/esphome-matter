import json
from pathlib import Path

import pytest

DATA_MODEL_DIR = Path(__file__).parents[2] / "components" / "matter" / "data_model"


@pytest.fixture(scope="module")
def data_model() -> tuple[dict, dict]:
    with open(DATA_MODEL_DIR / "clusters.json") as file:
        clusters = json.load(file)
    with open(DATA_MODEL_DIR / "device_types.json") as file:
        device_types = json.load(file)
    return clusters, device_types


def test_device_type_cluster_references(data_model: tuple[dict, dict]) -> None:
    clusters, device_types = data_model

    for device_type_id, device_type in device_types.items():
        for cluster_id, cluster_reference in device_type["clusters"].items():
            cluster = clusters.get(cluster_id)
            assert cluster is not None, (
                f"Device type {device_type['name']} ({device_type_id}) references unknown cluster {cluster_reference['name']} ({cluster_id})"
            )


@pytest.mark.xfail(reason="Not all required attributes are available yet")
def test_device_type_required_attributes(data_model: tuple[dict, dict]) -> None:
    clusters, device_types = data_model

    for device_type_id, device_type in device_types.items():
        for cluster_id, cluster_reference in device_type["clusters"].items():
            cluster = clusters.get(cluster_id)
            if cluster is None:
                continue
            attributes = {
                attribute.get("define")
                for attribute in cluster.get("attributes", {}).values()
            }
            for required_attribute in cluster_reference.get("required_attributes", ()):
                assert required_attribute in attributes, (
                    f"Device type {device_type['name']} ({device_type_id}) requires "
                    f"unknown attribute {required_attribute} on cluster "
                    f"{cluster['name']} ({cluster_id})"
                )


@pytest.mark.xfail(reason="Not all required commands are available yet")
def test_device_type_required_commands(data_model: tuple[dict, dict]) -> None:
    clusters, device_types = data_model

    for device_type_id, device_type in device_types.items():
        for cluster_id, cluster_reference in device_type["clusters"].items():
            cluster = clusters.get(cluster_id)
            if cluster is None:
                continue
            commands = cluster.get("commands", {})
            for required_command in cluster_reference.get("required_commands", ()):
                assert required_command in commands, (
                    f"Device type {device_type['name']} ({device_type_id}) requires "
                    f"unknown command {required_command} on cluster "
                    f"{cluster['name']} ({cluster_id})"
                )
