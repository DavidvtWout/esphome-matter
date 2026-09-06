import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv

from ..util import snake_case
from .attributes import Attribute
from .commands import Command

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Feature:
    code: str
    name: str  # CamelCase
    bit: int

    @classmethod
    def from_dict(cls, data: dict):
        return cls(code=data["code"], name=data["name"], bit=data["bit"])

    @property
    def namespace(self) -> str:
        """esp_matter::cluster::<cluster>::feature namespace."""
        return snake_case(self.name)


@dataclass
class ClusterConfig:
    create: bool = True
    # Keys are feature names.
    enabled_features: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Cluster:
    id: int
    name: str  # Name with spaces and special characters such as "/"
    revision: int
    required: bool = False
    features: tuple[Feature, ...] = ()
    server_attributes: tuple[Attribute, ...] = ()
    client_attributes: tuple[Attribute, ...] = ()
    commands: tuple[Command, ...] = ()
    responses: tuple[Command, ...] = ()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            # Some lack a revision. Assuming it's 1...
            revision=data.get("revision", 1),
            features=tuple(
                Feature.from_dict(feature) for feature in data.get("features", ())
            ),
            server_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("server_attributes", ())
            ),
            client_attributes=tuple(
                Attribute.from_dict(a) for a in data.get("client_attributes", ())
            ),
            commands=tuple(),  # TODO
            responses=tuple(),  # TODO
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
        """esp_matter::cluster:: namespace"""
        return (
            self.name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "")
            .replace(".", "")
            .lower()
        )

    def _config_expression(self, config: ClusterConfig):
        # TODO: some extra clusters don't support feature flags and need to be created with
        #       cg.RawExpression(f"esp_matter::cluster::{self.namespace}::config_t{{}}")

        lines = ["[] {", f"esp_matter::cluster::{self.namespace}::config_t config{{}};"]

        feature_flags = []
        features_by_name = {f.name: f for f in self.features}
        for feature_name, enabled in config.enabled_features.items():
            if not enabled:
                continue
            feature = features_by_name.get(feature_name)
            if not feature:
                raise cv.Invalid(f"Cluster {self.name} has no feature {feature_name}")
            feature_flags.append(
                f"esp_matter::cluster::{self.namespace}::feature::{feature.namespace}::get_id()"
            )
        if feature_flags:
            lines.append(f"config.feature_flags = {' | '.join(feature_flags)};")

        lines.append("return config;")
        lines.append("}()")
        return cg.RawExpression("\n".join(lines))

    def register(self, var, endpoint_id: int, config: ClusterConfig):
        if not config.create:
            return
        _LOGGER.debug(
            "[Matter] Registering cluster %s on endpoint %s",
            self.name,
            endpoint_id,
        )
        cluster_namespace = f"esp_matter::cluster::{self.namespace}"
        cg.add(
            var.register_cluster(
                cg.TemplateArguments(
                    self.id,
                    cg.RawExpression(f"{cluster_namespace}::config_t"),
                    cg.RawExpression(f"{cluster_namespace}::create"),
                ),
                endpoint_id,
                self.name,
                self._config_expression(config),
            )
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
