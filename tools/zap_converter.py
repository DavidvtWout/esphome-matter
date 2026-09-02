from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

import argparse
import json
from dataclasses import dataclass, field
from typing import Any


def snake_case(name: str) -> str:
    name = name.replace(" ", "_").replace("-", "_").replace("/", "_")
    return name.lower()


def camel_case(name: str) -> str:
    return name.replace("/", "").replace(" ", "").replace("-", "")


def filter_none(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None}


def format_counter(data: dict[str, int]) -> str:
    return " ".join(
        f"{key}:{count}"
        for key, count in sorted(data.items(), key=lambda x: x[1], reverse=True)
    )


@dataclass
class Attribute:
    code: int
    side: str  # clent, server, either
    type: str
    define: str
    name: str | None = None  # CamelCase
    min: int | None = None
    max: int | None = None
    is_nullable: bool = False
    writable: bool = False
    optional: bool = False
    default: Any | None = None
    length: int | None = None
    # entryType
    # apiMaturity
    # minLength


@dataclass
class CommandArg:
    id: int | None  # Also named fieldId on some args...
    name: str  # CamelCase
    type: str
    min: int | None = None
    max: int | None = None
    default: int | None = None
    is_nullable: bool = False
    optional: bool = False
    # array
    # minLength
    # apiMaturity


@dataclass
class Command:
    source: str  # client, server
    code: int
    name: str  # CamelCase
    optional: bool = False
    # response
    # disableDefaultResponse
    # cli
    # isFabricScoped
    # apiMaturity
    # mustUseTimedInvoke
    description: str | None = None
    args: list[CommandArg] = field(default_factory=list)


@dataclass
class Cluster:
    id: int
    name: str  # CamelCase
    revision: int | None = None
    # features: list
    attributes: list[Attribute] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)


@dataclass
class DeviceCluster:
    """As defined on deviceType. Refers to a cluster element (see Cluster dataclass)."""

    name: str
    client: bool
    server: bool
    client_locked: bool
    server_locked: bool
    # features: list
    required_attributes: list
    required_commands: list


@dataclass
class DeviceType:
    name: str
    device_id: int
    revision: int | None = None
    clusters: list[DeviceCluster] = field(default_factory=list)


# globals for ease of use
attribute_attrs = defaultdict(int)
attribute_types = defaultdict(int)
command_attrs = defaultdict(int)
command_arg_attrs = defaultdict(int)


def parse_device_type_elem(elem) -> DeviceType:
    device_clusters = []
    for cluster_elem in elem.findall("./clusters/include"):
        cluster = DeviceCluster(
            name=camel_case(cluster_elem.attrib["cluster"]),
            client=cluster_elem.get("client") == "true",
            server=cluster_elem.get("server") == "true",
            client_locked=cluster_elem.get("clientLocked") == "true",
            server_locked=cluster_elem.get("serverLocked") == "true",
            # "features= [e.attrib["code"] for e in cluster_elem.findall("./features/feature")],
            required_attributes=[
                e.text for e in cluster_elem.findall("./requireAttribute")
            ],  # Refers to "define" attr in cluster attributes
            required_commands=[
                e.text for e in cluster_elem.findall("./requireCommand")
            ],  # CamelCase command names
        )
        device_clusters.append(cluster)

    device_type = DeviceType(
        device_id=int(elem.findtext("deviceId"), 0),
        name=snake_case(elem.findtext("typeName")),
        clusters=device_clusters,
    )
    if revision_text := elem.findtext("revision"):
        device_type.revision = int(revision_text)
    return device_type


def parse_cluster_elem(elem) -> Cluster:
    cluster = Cluster(
        id=int(elem.findtext("code"), 0), name=camel_case(elem.findtext("name"))
    )
    if (rev_elem := elem.find('globalAttribute[@code="0xFFFD"]')) is not None:
        cluster.revision = int(rev_elem.attrib["value"])

    # TODO: features

    attributes: list[Attribute] = []
    for attribute_elem in elem.findall("./attribute"):
        attribute_types[attribute_elem.attrib["type"]] += 1
        for key in attribute_elem.attrib:
            attribute_attrs[key] += 1

        attribute = Attribute(
            code=int(attribute_elem.get("code"), 0),
            name=attribute_elem.get("name"),  # Somehow name is optional...
            side=attribute_elem.get("side"),
            type=attribute_elem.get("type"),
            define=attribute_elem.get("define"),
        )
        attribute.min = int(v, 0) if (v := attribute_elem.get("min")) else None
        attribute.max = int(v, 0) if (v := attribute_elem.get("max")) else None
        attribute.is_nullable = attribute_elem.get("isNullable") == "true"
        attribute.writable = attribute_elem.get("writable") == "true"
        attribute.optional = attribute_elem.get("optional") == "true"
        attribute.default = attribute_elem.get("default")
        attribute.length = int(v, 0) if (v := attribute_elem.get("length")) else None

        attributes.append(attribute)
    cluster.attributes = attributes

    commands = []
    for command_elem in elem.findall("./command"):
        for key in command_elem.attrib:
            command_attrs[key] += 1

        args = []
        for arg_elem in command_elem.findall("./arg"):
            for key in arg_elem.attrib:
                command_arg_attrs[key] += 1
            id_ = int(v, 0) if (v := arg_elem.get("id")) else None
            if id_ is None:
                id_ = int(v, 0) if (v := arg_elem.get("field_id")) else None
            args.append(
                CommandArg(
                    id=id_,
                    name=arg_elem.get("name"),
                    type=arg_elem.get("type"),
                    min=int(v, 0) if (v := arg_elem.get("min")) else None,
                    max=int(v, 0) if (v := arg_elem.get("max")) else None,
                    optional=arg_elem.get("optional") == "true",
                    default=arg_elem.get("default"),
                )
            )

        commands.append(
            Command(
                source=command_elem.get("source"),
                code=int(command_elem.get("code"), 0),
                name=command_elem.get("name"),
                args=args,
            )
        )
    cluster.commands = commands

    return cluster


def parse_data_model(data_model_dir: Path) -> tuple[list[DeviceType], list]:
    device_types = []
    clusters = []

    for xml_file in data_model_dir.glob("*.xml"):
        root = ElementTree.parse(xml_file).getroot()

        for elem in root.findall("./deviceType"):
            device_types.append(parse_device_type_elem(elem))

        for elem in root.findall("./cluster"):
            clusters.append(parse_cluster_elem(elem))

    print("attribute attrs:   ", format_counter(attribute_attrs))
    # print("attribute types:   ", format_counter(attribute_types))
    print("command attrs:     ", format_counter(command_attrs))
    print("command arg attrs: ", format_counter(command_arg_attrs))

    return device_types, clusters


def post_process_commands(clusters: list[Cluster]) -> dict:
    commands = {}

    for cluster in sorted(clusters, key=lambda c: c.id):
        if cluster.commands:
            commands[cluster.name] = {}
        for command in sorted(cluster.commands, key=lambda c: c.code):
            args = [
                filter_none(
                    {
                        "id": arg.id,
                        "name": arg.name,
                        "type": arg.type,
                        "min": arg.min,
                        "max": arg.max,
                        "default": arg.default,
                        "optional": arg.optional,
                    }
                )
                for arg in command.args
            ]
            commands[cluster.name][command.name] = filter_none(
                {
                    "id": command.code,
                    "client": command.source == "client",
                    "server": command.source == "server",
                    "args": args,
                }
            )

    return commands


def post_process_device_types(
    raw_device_types: list[DeviceType], raw_clusters: list[Cluster]
) -> list[dict]:
    device_types = []

    raw_clusters_by_name = {c.name: c for c in raw_clusters}

    for raw_device_type in raw_device_types:
        device_type: dict[str, ...] = {
            "id": raw_device_type.device_id,
            "name": raw_device_type.name,
            "revision": raw_device_type.revision,
        }
        device_clusters = []
        for cluster_config in raw_device_type.clusters:
            cluster = raw_clusters_by_name.get(cluster_config.name)
            if not cluster:
                print(f"WARNING: {cluster_config.name} cluster not found!")
                continue

            # TODO: use required_attributes and features
            attributes = []
            for attribute in cluster.attributes:
                attributes.append(
                    {
                        "id": attribute.code,
                        "name": attribute.name,
                        "type": attribute.type,  # TODO: resolve enum types
                    }
                )

            device_clusters.append(
                {
                    "id": cluster.id,
                    "name": cluster_config.name,
                    "revision": cluster.revision,
                    "client": cluster_config.client,
                    "server": cluster_config.server,
                    "attributes": attributes,
                    "commands": [
                        c.name for c in cluster.commands
                    ],  # TODO: process required
                }
            )
        device_clusters.sort(key=lambda c: c["id"])
        device_type["clusters"] = device_clusters
        device_types.append(device_type)

    device_types.sort(key=lambda d: d["id"])
    return device_types


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the Matter ZAP data model for use by esphome-matter."
    )
    parser.add_argument(
        "data_model_path",
        nargs="?",
        type=Path,
        default=Path("../../connectedhomeip/src/app/zap-templates/zcl/data-model/chip"),
        help=f"path to the ZAP data model",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        type=Path,
        default=Path("../components/matter/data_model"),
        help=f"output path",
    )
    return parser.parse_args()


def fixup(device_types):
    # TODO: doorbell revision is missing
    ...


def main():
    args = parse_args()
    raw_device_types, raw_clusters = parse_data_model(args.data_model_path)

    commands = post_process_commands(raw_clusters)
    device_types = post_process_device_types(raw_device_types, raw_clusters)
    fixup(device_types)

    with open(args.output_path / "device_types.json", "w") as file:
        json.dump(device_types, file, indent=2)

    with open(args.output_path / "commands.json", "w") as file:
        json.dump(commands, file, indent=2)


if __name__ == "__main__":
    main()
