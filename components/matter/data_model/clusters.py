import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import esphome.config_validation as cv

from ..const import CONF_WITH_FEATURES
from ..util import snake_case
from .attributes import Attribute
from .conformance import Conformance

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Feature:
    code: str
    name: str  # CamelCase
    conformance: Conformance | None = field(default=None, compare=False, hash=False)

    @classmethod
    def from_dict(cls, code: str, data: dict):
        name = data["name"].replace("/", "").replace(" ", "").replace("-", "")
        return cls(
            code=code,
            name=name,
            conformance=Conformance.from_dict(data.get("conformance")),
        )

    @property
    def namespace(self) -> str:
        """Feature name in esp_matter::cluster::<cluster>::feature::<feature> namespace."""
        return snake_case(self.name)

    @property
    def conf_key(self):
        return snake_case(self.name)


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
    server_attributes: tuple[Attribute, ...]
    # ----------------------------------- #
    # Derived attributes                  #
    # ----------------------------------- #
    conf_key: str
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

        _features = []
        for code, feature_data in data.get("features", {}).items():
            _features.append(Feature.from_dict(code, feature_data))

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

        espm_namespace = data.get(
            "esp_matter_namespace",
            name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "")
            .replace(".", "")
            .lower(),
        )

        return cls(
            id=data["id"],
            _name=name,
            name=camel_case_name,
            conf_key=snake_case(name),
            # Some lack a revision. Assuming it's 1...
            revision=data.get("revision", 1),
            features=tuple(_features),
            server_attributes=tuple(
                Attribute.from_dict(camel_case_name, a)
                for a in data.get("server_attributes", ())
            ),
            sdkconfig_option=sdkconfig_option,
            chip_fqn=chip_fqn,
            chip_include=chip_include,
            espm_namespace=espm_namespace,
        )

    def get_attribute(self, name: str) -> Attribute | None:
        for attribute in self.server_attributes:
            if name in (attribute.name, attribute.conf_key, attribute.id):
                return attribute
        return None

    def get_feature(self, name_or_code: str) -> Feature | None:
        for feature in self.features:
            if name_or_code in (feature.name, feature.code, feature.namespace):
                return feature
        return None

    @property
    def schema_key(self):
        return cv.Optional(self.conf_key)

    def schema(self):
        schema = {}
        if self.features:
            # Features must be given in snake_case. e.g.: "average_measurement"
            schema[cv.Optional(CONF_WITH_FEATURES, default=list)] = cv.ensure_list(
                cv.one_of(*(feature.conf_key for feature in self.features))
            )
        return schema


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
CLUSTERS_BY_CONF_KEY: dict[str, Cluster] = {
    cluster.conf_key: cluster for cluster in CLUSTERS
}
