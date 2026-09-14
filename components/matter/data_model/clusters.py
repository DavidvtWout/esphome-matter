import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..util import snake_case
from .attributes import Attribute

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Feature:
    code: str
    name: str  # CamelCase
    # Can be set to True by DeviceType config
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(code=data["code"], name=data["name"])

    @property
    def namespace(self) -> str:
        """Feature name in esp_matter::cluster::<cluster>::feature::<feature> namespace."""
        return snake_case(self.name)


@dataclass(frozen=True, slots=True)
class FeatureChoice:
    min: int
    max: int | None
    features: tuple[Feature, ...]

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            min=data["min"],
            max=data.get("max"),
            features=tuple(Feature.from_dict(feature) for feature in data["features"]),
        )


def _dict_to_feature(data: dict) -> Feature | FeatureChoice:
    if data["type"] == "choice":
        return FeatureChoice.from_dict(data)
    else:
        return Feature.from_dict(data)


@dataclass(frozen=True, slots=True)
class Cluster:
    # ----------------------------------- #
    # Parsed directly from clusters.json  #
    # ----------------------------------- #
    id: int
    # Name with spaces and special characters such as "/"
    _name: str
    # CamelCase name that's used almost everywhere in esphome_matter
    name: str
    revision: int
    features: tuple[Feature, ...]
    choice_features: tuple[FeatureChoice, ...]
    server_attributes: tuple[Attribute, ...]
    # ----------------------------------- #
    # Derived attributes                  #
    # ----------------------------------- #
    sdkconfig_option: str
    # connectedhomeip fully qualified name. e.g.: chip::app::Clusters::TemperatureMeasurementCluster
    chip_fqn: str
    # connectedhomeip include. e.g.: #include <app/clusters/temperature-measure-server/TemperatureMeasurementCluster.h>
    chip_include: str
    # esp_matter class namespace. e.g.:
    espm_namespace: str
    # ----------------------------------- #
    # Set by DeviceType                   #
    # ----------------------------------- #
    required: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        name = data["name"]
        sdkconfig_option = _sdkconfig_option(name)
        camel_case_name = (
            name.replace("/", "").replace(" ", "").replace("-", "").replace(".", "")
        )

        all_features = tuple(_dict_to_feature(f) for f in data.get("features", ()))
        _features = []
        _choice_features = []
        for feature in all_features:
            if isinstance(feature, FeatureChoice):
                _choice_features.append(feature)
                _features.extend(feature.features)
            else:
                _features.append(feature)

        # TODO: are there more exceptions?
        if camel_case_name.endswith("ConcentrationMeasurement"):
            chip_fqn = "chip::app::Clusters::ConcentrationMeasurement::ConcentrationMeasurementCluster"
            chip_include = "#include <app/clusters/concentration-measurement-server/ConcentrationMeasurementCluster.h>"
        else:
            chip_class = f"{camel_case_name}Cluster"
            chip_fqn = f"chip::app::Clusters::{chip_class}"
            cluster_path = snake_case(camel_case_name).replace("_", "-")
            chip_include = (
                f"#include <app/clusters/{cluster_path}-server/{chip_class}.h>"
            )

        espm_namespace = (
            name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "")
            .replace(".", "")
            .lower()
        )

        return cls(
            id=data["id"],
            _name=name,
            name=camel_case_name,
            # Some lack a revision. Assuming it's 1...
            revision=data.get("revision", 1),
            features=tuple(_features),
            choice_features=tuple(_choice_features),
            server_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("server_attributes", ())
            ),
            sdkconfig_option=sdkconfig_option,
            chip_fqn=chip_fqn,
            chip_include=chip_include,
            espm_namespace=espm_namespace,
        )

    def get_attribute(self, name: str) -> Attribute:
        for attribute in self.server_attributes:
            if attribute.name == name:
                return attribute
        raise KeyError(f"Cluster {self.name} has no attribute {name}")

    def is_choice_feature(self, feature: Feature) -> bool:
        for choice in self.choice_features:
            for f in choice.features:
                if f.name == feature.name:
                    return True
        return False


def _sdkconfig_option(name: str) -> str:
    """sdkconfig option name to enable compilation of the cluster in esp_matter."""
    sdkconfig_name = (
        name.replace(" ", "_")
        .replace("/", "_")
        .replace(".", "_")
        .replace("-", "")
        .upper()
    )
    sdkconfig_name = sdkconfig_name.replace("WEBRTC", "WEB_RTC")
    sdkconfig_name = sdkconfig_name.replace("TOTAL_VOLATILE_ORGANIC_COMPOUNDS", "TVOC")
    sdkconfig_name = sdkconfig_name.replace("SCENES_MANAGEMENT", "SCENES")
    sdkconfig_name = sdkconfig_name.replace(
        "OVEN_CAVITY_OPERATIONAL_STATE", "OPERATIONAL_STATE_OVEN"
    )
    sdkconfig_name = sdkconfig_name.replace(
        "RVC_OPERATIONAL_STATE", "OPERATIONAL_STATE_RVC"
    )
    return f"CONFIG_SUPPORT_{sdkconfig_name}_CLUSTER"


def _load_clusters(
    clusters_file: Path = Path(__file__).resolve().parent / "clusters.json",
) -> tuple[Cluster, ...]:
    clusters: list[Cluster] = []
    with open(clusters_file, "r") as file:
        contents = json.load(file)
    for clusters_data in contents:
        clusters.append(Cluster.from_dict(clusters_data))
    return tuple(clusters)


CLUSTERS: tuple[Cluster, ...] = _load_clusters()
CLUSTERS_BY_ID: dict[int, Cluster] = {cluster.id: cluster for cluster in CLUSTERS}
CLUSTERS_BY_NAME: dict[str, Cluster] = {cluster.name: cluster for cluster in CLUSTERS}
