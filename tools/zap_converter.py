import re
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


def camel_case_to_snake_case(name: str) -> str:
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
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


# Also used for bitmaps
@dataclass
class Enum:
    name: str  # CamelCase
    type: str  # e.g.: enum8
    cluster_code: int | None = None
    items: dict[str, int] = field(default_factory=dict)


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
class Struct:
    name: str  # CamelCase
    fabric_scoped = bool = False
    cluster_code: int | None = None
    items: list[CommandArg] = field(default_factory=list)


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
    description: str
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


def parse_command_arg_elem(elem) -> CommandArg:
    for key in elem.attrib:
        command_arg_attrs[key] += 1
    id_ = int(v, 0) if (v := elem.get("id")) else None
    if id_ is None:
        id_ = int(v, 0) if (v := elem.get("field_id")) else None

    # Translate Matter bullshit types to actual types. We can't deduce meaningful information from
    # these types anyway because Matter is very inconsistant in naming types...
    arg_type = elem.get("type")
    arg_type = {
        "power_mw": "int64s",
        "amperage_ma": "int64s",
        "voltage_mv": "int64s",
        "percent": "int8u",
        "percent100ths": "int16u",
        "epoch_us": "int64u",
        "epoch_s": "int32u",
        "posix_ms": "int64u",
        "systime_us": "int64u",
        "systime_ms": "int64u",
        "elapsed_s": "int32u",
        "temperature": "int16s",
        "status": "int8u",
        "group_id": "int16u",
        "endpoint_no": "int16u",
        "vendor_id": "int16u",
        "fabric_idx": "int8u",
        "attrib_id": "int32u",
        "node_id": "int64u",
    }.get(arg_type.lower(), arg_type)

    return CommandArg(
        id=id_,
        name=elem.get("name"),
        type=arg_type,
        min=int(v, 0) if (v := elem.get("min")) else None,
        max=int(v, 0) if (v := elem.get("max")) else None,
        optional=elem.get("optional") == "true",
        default=elem.get("default"),
    )


def parse_cluster_elem(elem) -> Cluster:
    cluster = Cluster(
        id=int(elem.findtext("code"), 0),
        name=camel_case(elem.findtext("name")),
        description=elem.findtext("description"),
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
            args.append(parse_command_arg_elem(arg_elem))

        commands.append(
            Command(
                source=command_elem.get("source"),
                code=int(command_elem.get("code"), 0),
                name=command_elem.get("name"),
                description=command_elem.findtext("description").strip(),
                args=args,
            )
        )
    cluster.commands = commands

    return cluster


def parse_enum_elem(elem) -> Enum:
    enum = Enum(name=elem.get("name"), type=elem.get("type"))
    cluster_elem = elem.find("./cluster")
    if cluster_elem is not None:
        enum.cluster_code = int(cluster_elem.get("code"), 0)
    for item_elem in elem.findall("./item"):
        value_str = item_elem.get("value")
        if "x" not in value_str:
            # Fucking window-cover.xml not adhering to the standard...
            value_str = value_str.lstrip("0")
            if value_str == "":
                value_str = "0"
        enum.items[item_elem.get("name")] = int(value_str, 0)
    return enum


def parse_bitmap_elem(elem) -> Enum:
    bitmap = Enum(name=elem.get("name"), type=elem.get("type"))
    cluster_elem = elem.find("./cluster")
    if cluster_elem is not None:
        bitmap.cluster_code = int(cluster_elem.get("code"), 0)
    for field_item in elem.findall("./field"):
        bitmap.items[field_item.get("name")] = int(field_item.get("mask"), 0)
    return bitmap


def parse_struct_elem(elem) -> Struct:
    struct = Struct(name=elem.get("name"))
    cluster_elem = elem.find("./cluster")
    if cluster_elem is not None:
        struct.cluster_code = int(cluster_elem.get("code"), 0)
    for item_elem in elem.findall("./item"):
        struct.items.append(parse_command_arg_elem(item_elem))
    return struct


def parse_data_model(
    data_model_dir: Path,
) -> tuple[list[DeviceType], list, list, list, list]:
    device_types = []
    clusters = []
    enums = []
    bitmaps = []
    structs = []

    for xml_file in data_model_dir.glob("*.xml"):
        root = ElementTree.parse(xml_file).getroot()

        for elem in root.findall("./deviceType"):
            device_types.append(parse_device_type_elem(elem))

        for elem in root.findall("./cluster"):
            clusters.append(parse_cluster_elem(elem))

        # Also includes the global enums.
        for elem in root.findall("./enum"):
            enums.append(parse_enum_elem(elem))
        for elem in root.findall("./bitmap"):
            bitmaps.append(parse_bitmap_elem(elem))
        for elem in root.findall("./struct"):
            structs.append(parse_struct_elem(elem))

    print("attribute attrs:   ", format_counter(attribute_attrs))
    # print("attribute types:   ", format_counter(attribute_types))
    print("command attrs:     ", format_counter(command_attrs))
    print("command arg attrs: ", format_counter(command_arg_attrs))

    return device_types, clusters, enums, bitmaps, structs


def post_process_commands(
    clusters: list[Cluster],
    enums: list[Enum],
    bitmaps: list[Enum],
    structs: list[Struct],
) -> dict:
    global_enums = {}
    cluster_enums = defaultdict(dict)
    for enum in enums:
        if enum.cluster_code is not None:
            cluster_enums[enum.cluster_code][enum.name] = enum
        else:
            global_enums[enum.name] = enum

    cluster_bitmaps = defaultdict(dict)
    for bitmap in bitmaps:
        if bitmap.cluster_code is not None:
            cluster_bitmaps[bitmap.cluster_code][bitmap.name] = bitmap
        # No need to parse global bitmaps

    global_structs = {}
    cluster_structs = defaultdict(dict)
    for struct in structs:
        if struct.cluster_code is not None:
            cluster_structs[struct.cluster_code][struct.name] = struct
        else:
            global_structs[struct.name] = struct

    def resolve_arg(arg: CommandArg):
        arg_type = arg.type

        enum = cluster_enums.get(cluster.id, {}).get(arg_type)
        enum_values = None
        if not enum:
            enum = global_enums.get(arg_type)
        if enum:
            arg_type = enum.type
            enum_values = enum.items
        if enum_values:
            enum_values = {
                camel_case_to_snake_case(k): v for k, v in enum_values.items()
            }

        bitmap_masks = None
        if (bitmap := cluster_bitmaps.get(cluster.id, {}).get(arg_type)) is not None:
            arg_type = bitmap.type
            bitmap_masks = bitmap.items
        if bitmap_masks:
            bitmap_masks = {
                camel_case_to_snake_case(k): v for k, v in bitmap_masks.items()
            }

        struct = cluster_structs.get(cluster.id, {}).get(arg_type)
        struct_values = None
        if not struct:
            struct = global_structs.get(arg_type)
        if struct:
            arg_type = "struct"
            struct_values = [resolve_arg(a) for a in struct.items]

        return filter_none(
            {
                "id": arg.id,
                "name": arg.name,
                "type": arg_type.lower(),
                "min": arg.min,
                "max": arg.max,
                "default": arg.default,
                "optional": True if arg.optional else None,
                "enum_values": enum_values,
                "bitmap_masks": bitmap_masks,
                "struct": struct_values,
            }
        )

    commands = {}
    for cluster in sorted(clusters, key=lambda c: c.id):
        if cluster.commands:
            commands[cluster.name] = {}
        for command in sorted(cluster.commands, key=lambda c: c.code):
            if command.source != "client":
                continue
            args = []
            for arg in command.args:
                args.append(resolve_arg(arg))
            commands[cluster.name][command.name] = filter_none(
                {
                    "id": command.code,
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
                filter_none(
                    {
                        "id": cluster.id,
                        "name": cluster_config.name,
                        "revision": cluster.revision,
                        "client": True if cluster_config.client else None,
                        "server": True if cluster_config.server else None,
                        "attributes": attributes,
                        "commands": [
                            c.name for c in cluster.commands
                        ],  # TODO: process required
                    }
                )
            )
        device_clusters.sort(key=lambda c: c["id"])
        device_type["clusters"] = device_clusters
        device_types.append(device_type)

    device_types.sort(key=lambda d: d["id"])
    return device_types


def fixup(device_types):
    # TODO: doorbell revision is missing
    ...


def sanitize_description(description: str) -> str:
    lines = []
    for line in description.split("\n"):
        line = line.strip()
        # remove duplicate spaces
        line = re.sub(r" +", " ", line)
        lines.append(line)
    return "\n".join(lines)


def command_arg_to_doc(arg: CommandArg, command_args: list[dict]) -> str:
    arg_dict = None
    for command_arg in command_args:
        if command_arg["name"] == arg.name:
            arg_dict = command_arg

    optional = arg.optional
    comment_str = ""
    extra_lines = []

    if "bitmap_masks" in arg_dict:
        optional = True
        comment_str = "bitmap: " + ", ".join(arg_dict["bitmap_masks"])

    if "enum_values" in arg_dict:
        comment_str = "enum: " + ", ".join(arg_dict["enum_values"])

    optional_str = "# " if optional else ""
    if "default" in arg_dict:
        comment_str = f"default: {arg_dict['default']} "
    comment_str = f"# {comment_str}" if comment_str else ""
    return "\n".join(
        [
            f"  {optional_str}{camel_case_to_snake_case(arg.name)}: {comment_str}".rstrip()
        ]
        + extra_lines
    )


def generate_documentation(
    clusters: list[Cluster], processed_commands: list[dict]
) -> str:
    lines = [
        "This file is automatically generated by tools/zap_converter.py. Don't edit it.\n"
    ]
    for cluster in sorted(clusters, key=lambda c: c.id):
        client_commands = [c for c in cluster.commands if c.source == "client"]
        if not client_commands:
            continue
        lines.append(
            f"# {cluster.name}\n\n{sanitize_description(cluster.description)}\n\n```yaml"
        )
        yaml_lines = []
        for command in sorted(client_commands, key=lambda c: c.code):
            command_dict = processed_commands[cluster.name][command.name]
            command_lines = []
            if command.description:
                command_lines.append(
                    "# "
                    + sanitize_description(command.description).replace("\n", "\n# ")
                )
            command_lines.append(
                f"matter.{camel_case_to_snake_case(cluster.name)}.{camel_case_to_snake_case(command.name)}:"
            )
            for arg in command.args:
                command_lines.append(command_arg_to_doc(arg, command_dict["args"]))
            yaml_lines.append("\n".join(command_lines))
        lines.append("\n\n".join(yaml_lines))
        lines.append("```\n")
    return "\n".join(lines)


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
    parser.add_argument(
        "documentation_path",
        nargs="?",
        type=Path,
        default=Path("../docs"),
        help=f"output path",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    raw_device_types, raw_clusters, enums, bitmaps, structs = parse_data_model(
        args.data_model_path
    )

    commands = post_process_commands(raw_clusters, enums, bitmaps, structs)
    device_types = post_process_device_types(raw_device_types, raw_clusters)
    fixup(device_types)

    with open(args.output_path / "device_types.json", "w") as file:
        json.dump(device_types, file, indent=2)

    with open(args.output_path / "commands.json", "w") as file:
        json.dump(commands, file, indent=2)

    with open(args.documentation_path / "commands-full.md", "w") as file:
        file.write(generate_documentation(raw_clusters, commands))

    arg_types = defaultdict(int)
    for cl in commands.values():
        for c in cl.values():
            for arg in c["args"]:
                arg_types[arg["type"]] += 1
    print("command arg types: ", format_counter(arg_types))


if __name__ == "__main__":
    main()
