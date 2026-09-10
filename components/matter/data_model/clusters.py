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


@dataclass(frozen=True, slots=True)
class Cluster:
    id: int
    name: str  # Name with spaces and special characters such as "/"
    revision: int
    required: bool = False
    features: tuple[Feature | FeatureChoice, ...] = ()
    server_attributes: tuple[Attribute, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            # Some lack a revision. Assuming it's 1...
            revision=data.get("revision", 1),
            features=tuple(
                FeatureChoice.from_dict(feature)
                if feature.get("type") == "choice"
                else Feature.from_dict(feature)
                for feature in data.get("features", ())
            ),
            server_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("server_attributes", ())
            ),
        )

    def get_attribute(self, name: str) -> Attribute:
        for attribute in self.server_attributes:
            if attribute.name == name:
                return attribute
        raise KeyError(f"Cluster {self.camel_case_name} has no attribute {name}")

    @property
    def all_features(self) -> tuple[Feature, ...]:
        return tuple(
            feature
            for item in self.features
            for feature in (
                item.features if isinstance(item, FeatureChoice) else (item,)
            )
        )

    @property
    def choice_features(self) -> tuple[Feature, ...]:
        return tuple(
            feature
            for item in self.features
            if isinstance(item, FeatureChoice)
            for feature in item.features
        )

    @property
    def sdkconfig_option(self) -> str:
        """sdkconfig option name to enable compilation of the cluster in esp_matter."""
        sdkconfig_name = (
            self.name.replace(" ", "_")
            .replace("/", "_")
            .replace(".", "_")
            .replace("-", "")
            .upper()
        )
        sdkconfig_name = sdkconfig_name.replace("WEBRTC", "WEB_RTC")
        sdkconfig_name = sdkconfig_name.replace(
            "TOTAL_VOLATILE_ORGANIC_COMPOUNDS", "TVOC"
        )
        sdkconfig_name = sdkconfig_name.replace("SCENES_MANAGEMENT", "SCENES")
        sdkconfig_name = sdkconfig_name.replace(
            "OVEN_CAVITY_OPERATIONAL_STATE", "OPERATIONAL_STATE_OVEN"
        )
        sdkconfig_name = sdkconfig_name.replace(
            "RVC_OPERATIONAL_STATE", "OPERATIONAL_STATE_RVC"
        )
        return f"CONFIG_SUPPORT_{sdkconfig_name}_CLUSTER"

    @property
    def camel_case_name(self) -> str:
        return (
            self.name.replace("/", "")
            .replace(" ", "")
            .replace("-", "")
            .replace(".", "")
        )

    @property
    def namespace(self) -> str:
        """esp_matter::cluster::<cluster_name> namespace"""
        return (
            self.name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "")
            .replace(".", "")
            .lower()
        )


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
CLUSTERS_BY_NAME: dict[str, Cluster] = {
    cluster.camel_case_name: cluster for cluster in CLUSTERS
}
CLUSTERS_BY_CONF_KEY: dict[str, Cluster] = {
    snake_case(cluster.camel_case_name): cluster for cluster in CLUSTERS
}
