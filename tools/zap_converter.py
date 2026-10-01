import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


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


def filter_empty(data: dict) -> dict:
    return {k: v for k, v in data.items() if v}


def format_counter(data: dict[str, int]) -> str:
    return " ".join(
        f"{key}:{count}"
        for key, count in sorted(data.items(), key=lambda x: x[1], reverse=True)
    )


CONFORMANCE_TYPES = {
    "deprecateConform": "deprecated",
    "describedConform": "described",
    "disallowConform": "disallowed",
    "mandatoryConform": "mandatory",
    "optionalConform": "optional",
    "otherwiseConform": "otherwise",
    "provisionalConform": "provisional",
}
CONFORMANCE_TERMS = {
    "andTerm": "and",
    "orTerm": "or",
    "notTerm": "not",
    "greaterTerm": "greater",
    "greaterOrEqualTerm": "greater_or_equal",
}
CONFORMANCE_REFERENCES = {
    "attribute",
    "command",
    "condition",
    "feature",
    "revision",
}


def _conformance_scalar(value: str) -> str | int | bool:
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value, 0)
    except ValueError:
        return value


def _parse_conformance_node(elem, context: str) -> dict | None:
    if elem.tag in CONFORMANCE_REFERENCES:
        attribute = "value" if elem.tag == "revision" else "name"
        value = elem.get(attribute)
        if value is None or list(elem):
            print(
                f"WARNING: Unsupported conformance reference in {context}: {elem.tag}"
            )
            return None
        return {elem.tag: _conformance_scalar(value)}

    if elem.tag == "literal":
        value = elem.get("value")
        if value is None or list(elem):
            print(f"WARNING: Unsupported conformance literal in {context}")
            return None
        return {"literal": _conformance_scalar(value)}

    if elem.tag in CONFORMANCE_TERMS:
        children = []
        for child in elem:
            parsed = _parse_conformance_node(child, context)
            if parsed is None:
                return None
            children.append(parsed)
        operator = CONFORMANCE_TERMS[elem.tag]
        expected_children = (
            1
            if operator == "not"
            else 2
            if operator
            in (
                "greater",
                "greater_or_equal",
            )
            else None
        )
        if not children or (
            expected_children is not None and len(children) != expected_children
        ):
            print(
                f"WARNING: Unsupported {elem.tag} child count in {context}: "
                f"{len(children)}"
            )
            return None
        return {operator: children[0] if operator == "not" else children}

    if elem.tag in CONFORMANCE_TYPES:
        children = []
        for child in elem:
            parsed = _parse_conformance_node(child, context)
            if parsed is None:
                return None
            children.append(parsed)
        rule_type = CONFORMANCE_TYPES[elem.tag]
        attributes = {
            key: _conformance_scalar(value) for key, value in elem.attrib.items()
        }
        if rule_type == "otherwise":
            if attributes or not children:
                print(f"WARNING: Unsupported otherwiseConform in {context}")
                return None
            return {rule_type: children}
        if len(children) > 1:
            print(f"WARNING: Unsupported {elem.tag} child count in {context}")
            return None
        if attributes:
            if children:
                attributes["term"] = children[0]
            return {rule_type: attributes}
        return {rule_type: children[0] if children else True}

    print(f"WARNING: Unsupported conformance element in {context}: {elem.tag}")
    return None


def parse_conformance(elem, context: str) -> dict | None:
    conform_elements = [child for child in elem if child.tag.endswith("Conform")]
    bare_terms = [
        child
        for child in elem
        if child.tag in CONFORMANCE_TERMS
        or child.tag in CONFORMANCE_REFERENCES
        or child.tag == "literal"
    ]
    for bare_term in bare_terms:
        print(
            f"WARNING: Unsupported top-level conformance term in {context}: "
            f"{bare_term.tag}"
        )
    if not conform_elements:
        return None
    rules = []
    for conform_elem in conform_elements:
        parsed = _parse_conformance_node(conform_elem, context)
        if parsed is None:
            return None
        rules.append(parsed)
    return rules[0] if len(rules) == 1 else {"all": rules}


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
    conformance: dict | None = None
    # entryType
    # apiMaturity
    # minLength


@dataclass
class CommandArg:
    id: int  # Also named fieldId on some args...
    name: str  # CamelCase
    type: str
    min: int | None = None
    max: int | None = None
    default: int | None = None
    is_nullable: bool = False
    optional: bool = False
    array: bool = False
    length: int | None = None
    min_length: int | None = None
    conformance: dict | None = None
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
    conformance: dict | None = None


@dataclass
class Event:
    code: int
    name: str  # CamelCase
    priority: str
    api_maturity: str | None = None
    description: str | None = None
    fields: list[CommandArg] = field(default_factory=list)
    conformance: dict | None = None


@dataclass
class Feature:
    bit: int
    code: str
    name: str
    summary: str | None = None
    conformance: dict | None = None


@dataclass
class FeatureChoice:
    name: str
    min: int
    max: int | None
    features: list[Feature] = field(default_factory=list)


@dataclass
class Cluster:
    id: int
    name: str  # CamelCase
    description: str
    revision: int | None = None
    features: list[Feature | FeatureChoice] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


@dataclass
class DeviceCluster:
    """As defined on deviceType. Refers to a cluster element (see Cluster dataclass)."""

    name: str
    client: bool
    server: bool
    client_locked: bool
    server_locked: bool
    features: dict[str, str]
    feature_conformance: dict[str, dict]
    ignored_features: list[str]
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
event_attrs = defaultdict(int)
event_field_attrs = defaultdict(int)


def parse_device_type_elem(elem) -> DeviceType | None:
    name = snake_case(elem.findtext("typeName"))
    if name in (
        "all_clusters_app_server_example",
        "ambient_context_sensor",
        "basic_video_player",
        "camera_controller",
        "casting_video_client",
        "casting_video_player",
        "content_app",
        "door_lock_controller",
        "electrical_circuit_breaker",
        "electrical_distribution_enclosure",
        "floodlight_camera",
        "humidifier_dehumidifier",
        "intercom",
        "joint_fabric_administrator",
        "meter_reference_point",
        "network_infrastructure_manager",
        "on_off_sensor",
        "orphan_clusters",
        "proximity_ranger",
        "snapshot_camera",
        "speaker",
        "video_remote_control",
        "window_covering_controller",
    ):
        # Not actually supported by esp_matter...
        return None

    device_clusters = []
    for cluster_elem in elem.findall("./clusters/include"):
        features = {}
        feature_conformance = {}
        ignored_features = []
        for feature_elem in cluster_elem.findall("./features/feature"):
            feature_code = feature_elem.attrib["code"]
            context = (
                f"device type {name}.{cluster_elem.attrib['cluster']}.{feature_code}"
            )
            if conformance := parse_conformance(feature_elem, context):
                feature_conformance[feature_code] = conformance
            conform_elements = list(feature_elem)
            if not conform_elements:
                # Assuming no conform means mandatory, but I'm not entire sure...
                # Seems to apply mostly to irrelevant device types anyway.
                features[feature_code] = "mandatory"
            elif (
                len(conform_elements) == 1
                and conform_elements[0].tag == "mandatoryConform"
            ):
                features[feature_code] = "mandatory"
            elif (
                len(conform_elements) == 1
                and conform_elements[0].tag == "disallowConform"
            ):
                features[feature_code] = "disallowed"
            elif (
                len(conform_elements) == 1
                and conform_elements[0].tag == "optionalConform"
            ):
                features[feature_code] = "optional"
            else:
                ignored_features.append(
                    camel_case_to_snake_case(camel_case(feature_elem.attrib["name"]))
                )
                print(
                    "Ignoring device type feature with complicated conform rule: "
                    f"{name}.{cluster_elem.attrib['cluster']}.{feature_code}"
                )

        cluster = DeviceCluster(
            name=cluster_elem.attrib["cluster"],
            client=cluster_elem.get("client") == "true",
            server=cluster_elem.get("server") == "true",
            client_locked=cluster_elem.get("clientLocked") == "true",
            server_locked=cluster_elem.get("serverLocked") == "true",
            features=features,
            feature_conformance=feature_conformance,
            ignored_features=ignored_features,
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
        name=name,
        clusters=device_clusters,
    )
    if revision_text := elem.findtext("revision"):
        device_type.revision = int(revision_text)
    return device_type


def parse_field_elem(
    elem, attrs_counter=None, context: str | None = None
) -> CommandArg:
    if attrs_counter is not None:
        for key in elem.attrib:
            attrs_counter[key] += 1
    id_ = int(v, 0) if (v := elem.get("id")) else None
    if id_ is None:
        id_ = int(v, 0) if (v := elem.get("fieldId")) else None

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
        is_nullable=elem.get("isNullable") == "true",
        array=elem.get("array") == "true",
        length=int(v, 0) if (v := elem.get("length")) else None,
        min_length=int(v, 0) if (v := elem.get("minLength")) else None,
        conformance=parse_conformance(
            elem, context or f"{elem.tag} {elem.get('name', '<unnamed>')}"
        ),
    )


def parse_cluster_elem(elem) -> Cluster:
    cluster = Cluster(
        id=int(elem.findtext("code"), 0),
        name=elem.findtext("name"),
        description=elem.findtext("description"),
    )
    if (rev_elem := elem.find('globalAttribute[@code="0xFFFD"]')) is not None:
        cluster.revision = int(rev_elem.attrib["value"])

    features: list[Feature | FeatureChoice] = []
    choices: dict[str, FeatureChoice] = {}
    for feature_elem in elem.findall("./features/feature"):
        optional_conform = feature_elem.find("./optionalConform")
        feature = Feature(
            bit=int(feature_elem.get("bit"), 0),
            code=feature_elem.get("code"),
            name=feature_elem.get("name"),
            summary=feature_elem.get("summary"),
            conformance=parse_conformance(
                feature_elem,
                f"cluster {cluster.name} feature {feature_elem.get('code')}",
            ),
        )
        choice_name = (
            optional_conform.get("choice") if optional_conform is not None else None
        )
        if choice_name is None:
            features.append(feature)
            continue

        if choice_name not in choices:
            minimum = int(optional_conform.get("min", 1))
            maximum = optional_conform.get("max")
            choice = FeatureChoice(
                name=choice_name,
                min=minimum,
                max=(
                    int(maximum)
                    if maximum is not None
                    else None
                    if optional_conform.get("more") == "true"
                    else 1
                ),
            )
            choices[choice_name] = choice
            features.append(choice)
        choices[choice_name].features.append(feature)
    cluster.features = features

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
            conformance=parse_conformance(
                attribute_elem,
                f"cluster {cluster.name} attribute {attribute_elem.get('name')}",
            ),
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
            args.append(
                parse_field_elem(
                    arg_elem,
                    command_arg_attrs,
                    f"cluster {cluster.name} command {command_elem.get('name')} "
                    f"argument {arg_elem.get('name')}",
                )
            )

        commands.append(
            Command(
                source=command_elem.get("source"),
                code=int(command_elem.get("code"), 0),
                name=command_elem.get("name"),
                description=command_elem.findtext("description").strip(),
                args=args,
                conformance=parse_conformance(
                    command_elem,
                    f"cluster {cluster.name} command {command_elem.get('name')}",
                ),
            )
        )
    cluster.commands = commands

    events = []
    for event_elem in elem.findall("./event"):
        for key in event_elem.attrib:
            event_attrs[key] += 1
        events.append(
            Event(
                code=int(event_elem.get("code"), 0),
                name=event_elem.get("name"),
                priority=event_elem.get("priority", "info"),
                api_maturity=event_elem.get("apiMaturity"),
                description=(
                    description.strip()
                    if (description := event_elem.findtext("description"))
                    else None
                ),
                fields=[
                    parse_field_elem(
                        field_elem,
                        event_field_attrs,
                        f"cluster {cluster.name} event {event_elem.get('name')} "
                        f"field {field_elem.get('name')}",
                    )
                    for field_elem in event_elem.findall("./field")
                ],
                conformance=parse_conformance(
                    event_elem,
                    f"cluster {cluster.name} event {event_elem.get('name')}",
                ),
            )
        )
    cluster.events = events

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
        struct.items.append(
            parse_field_elem(
                item_elem,
                context=f"struct {struct.name} item {item_elem.get('name')}",
            )
        )
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
            if device_type := parse_device_type_elem(elem):
                device_types.append(device_type)

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
    print("event attrs:       ", format_counter(event_attrs))
    print("event field attrs: ", format_counter(event_field_attrs))

    return device_types, clusters, enums, bitmaps, structs


class FieldResolver:
    """Resolve ZAP field types shared by commands, events, and structs."""

    def __init__(self, enums: list[Enum], bitmaps: list[Enum], structs: list[Struct]):
        self.global_enums = {}
        self.cluster_enums = defaultdict(dict)
        for enum in enums:
            target = (
                self.cluster_enums[enum.cluster_code]
                if enum.cluster_code is not None
                else self.global_enums
            )
            target[enum.name] = enum

        self.cluster_bitmaps = defaultdict(dict)
        for bitmap in bitmaps:
            if bitmap.cluster_code is not None:
                self.cluster_bitmaps[bitmap.cluster_code][bitmap.name] = bitmap

        self.global_structs = {}
        self.cluster_structs = defaultdict(dict)
        for struct in structs:
            target = (
                self.cluster_structs[struct.cluster_code]
                if struct.cluster_code is not None
                else self.global_structs
            )
            target[struct.name] = struct

    def resolve(self, cluster_id: int, item: CommandArg) -> dict:
        item_type = item.type
        enum = self.cluster_enums.get(cluster_id, {}).get(item_type)
        if not enum:
            enum = self.global_enums.get(item_type)
        enum_values = None
        if enum:
            item_type = enum.type
            enum_values = {
                camel_case_to_snake_case(name): value
                for name, value in enum.items.items()
            }

        bitmap_masks = None
        bitmap = self.cluster_bitmaps.get(cluster_id, {}).get(item_type)
        if bitmap is not None:
            item_type = bitmap.type
            bitmap_masks = {
                camel_case_to_snake_case(name): value
                for name, value in bitmap.items.items()
            }

        struct = self.cluster_structs.get(cluster_id, {}).get(item_type)
        if not struct:
            struct = self.global_structs.get(item_type)
        struct_values = None
        if struct:
            item_type = "struct"
            struct_values = [self.resolve(cluster_id, field) for field in struct.items]

        return filter_none(
            {
                "id": item.id,
                "name": item.name,
                "type": item_type.lower(),
                "min": item.min,
                "max": item.max,
                "default": item.default,
                "optional": True if item.optional else None,
                "nullable": True if item.is_nullable else None,
                "array": True if item.array else None,
                "length": item.length,
                "min_length": item.min_length,
                "enum_values": enum_values,
                "bitmap_masks": bitmap_masks,
                "struct": struct_values,
                "conformance": item.conformance,
            }
        )


def post_process_commands(clusters: list[Cluster], resolver: FieldResolver) -> dict:
    commands = {}
    for cluster in sorted(clusters, key=lambda c: c.id):
        cluster_name = camel_case(cluster.name)
        if cluster.commands:
            commands[cluster_name] = {}
        for command in sorted(cluster.commands, key=lambda c: c.code):
            if command.source != "client":
                continue
            args = []
            for arg in command.args:
                args.append(resolver.resolve(cluster.id, arg))
            # Some command args don't set an id at all...
            for i, arg in enumerate(args):
                if arg.get("id") is None:
                    arg["id"] = i
            commands[cluster_name][command.name] = filter_none(
                {
                    "id": command.code,
                    "args": args,
                    "conformance": command.conformance,
                }
            )

    return commands


def post_process_events(clusters: list[Cluster], resolver: FieldResolver) -> dict:
    events = {}
    for cluster in sorted(clusters, key=lambda c: c.id):
        cluster_events = {}
        for event in sorted(cluster.events, key=lambda e: e.code):
            if event.api_maturity == "provisional":
                continue
            fields = [resolver.resolve(cluster.id, item) for item in event.fields]
            # Some fields only specify fieldId, and some specify neither spelling.
            for index, event_field in enumerate(fields):
                if event_field.get("id") is None:
                    event_field["id"] = index
            cluster_events[event.name] = {
                "id": event.code,
                "priority": event.priority,
                "fields": fields,
                **(
                    {"conformance": event.conformance}
                    if event.conformance is not None
                    else {}
                ),
            }
        if cluster_events:
            events[camel_case(cluster.name)] = cluster_events
    return events


def apply_command_overrides(commands: dict, overrides: dict) -> None:
    for cluster_name, cluster_overrides in overrides.items():
        if cluster_name not in commands:
            raise ValueError(f"Unknown command override cluster: {cluster_name}")

        for command_name, command_overrides in cluster_overrides.items():
            if command_name not in commands[cluster_name]:
                raise ValueError(
                    f"Unknown command override: {cluster_name}.{command_name}"
                )

            command = commands[cluster_name][command_name]
            for key, value in command_overrides.items():
                if key != "args":
                    command[key] = value
                    continue

                args_by_name = {arg["name"]: arg for arg in command["args"]}
                for arg_override in value:
                    arg_name = arg_override["name"]
                    if arg_name not in args_by_name:
                        raise ValueError(
                            "Unknown command argument override: "
                            f"{cluster_name}.{command_name}.{arg_name}"
                        )
                    args_by_name[arg_name].update(arg_override)


def apply_cluster_overrides(clusters: list[dict], overrides: dict[str, dict]) -> None:
    clusters_by_name = {cluster["name"]: cluster for cluster in clusters}
    for cluster_name, override in overrides.items():
        if cluster_name not in clusters_by_name:
            raise ValueError(f"Unknown cluster override: {cluster_name}")
        clusters_by_name[cluster_name].update(override)


def post_process_clusters(raw_clusters: list[Cluster]) -> list[dict]:
    clusters = []
    for cluster in sorted(raw_clusters, key=lambda c: c.id):
        cluster_data: dict[str, ...] = {
            "id": cluster.id,
            "name": cluster.name,
            "revision": cluster.revision,
        }

        features = {}
        for feature in cluster.features:
            if isinstance(feature, FeatureChoice):
                features[f"choice {feature.name}"] = filter_none(
                    {
                        "min": feature.min,
                        "max": feature.max,
                        "features": {
                            choice_feature.code: {
                                "bit": choice_feature.bit,
                                "name": choice_feature.name,
                                **(
                                    {"conformance": choice_feature.conformance}
                                    if choice_feature.conformance is not None
                                    else {}
                                ),
                            }
                            for choice_feature in feature.features
                        },
                    }
                )
            else:
                features[feature.code] = {
                    "bit": feature.bit,
                    "name": feature.name,
                    **(
                        {"conformance": feature.conformance}
                        if feature.conformance is not None
                        else {}
                    ),
                }
        if features:
            cluster_data["features"] = features

        server_attributes = []
        client_attributes = []
        for attr in cluster.attributes:
            attribute_data = filter_none(
                {
                    "id": attr.code,
                    "define": attr.define,
                    "name": attr.name,
                    "type": attr.type,
                    "min": attr.min,
                    "max": attr.max,
                    "writable": attr.writable,
                    "optional": attr.optional,
                    "default": attr.default,
                    "conformance": attr.conformance,
                }
            )
            if attr.side in ("server", "either"):
                server_attributes.append(attribute_data)
            if attr.side in ("client", "either"):
                client_attributes.append(attribute_data)

        if server_attributes:
            cluster_data["server_attributes"] = server_attributes
        if client_attributes:
            cluster_data["client_attributes"] = client_attributes

        clusters.append(cluster_data)
    return clusters


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
        server_clusters = []
        client_clusters = []
        for cluster_config in raw_device_type.clusters:
            cluster = raw_clusters_by_name.get(cluster_config.name)
            if not cluster:
                print(f"WARNING: {cluster_config.name} cluster not found!")
                continue

            if cluster_config.server or not cluster_config.server_locked:
                server_clusters.append(
                    filter_empty(
                        {
                            "id": cluster.id,
                            "name": cluster_config.name,
                            "required": cluster_config.server
                            and cluster_config.server_locked,
                            "features": cluster_config.features,
                            "feature_conformance": cluster_config.feature_conformance,
                            "ignored_features": cluster_config.ignored_features,
                            "required_attributes": cluster_config.required_attributes,
                            "required_commands": cluster_config.required_commands,
                        }
                    )
                )
            if cluster_config.client or not cluster_config.client_locked:
                client_clusters.append(
                    filter_empty(
                        {
                            "id": cluster.id,
                            "name": cluster_config.name,
                            "required": cluster_config.client
                            and cluster_config.client_locked,
                            "features": cluster_config.features,
                            "feature_conformance": cluster_config.feature_conformance,
                            "ignored_features": cluster_config.ignored_features,
                            "required_attributes": cluster_config.required_attributes,
                            "required_commands": cluster_config.required_commands,
                        }
                    )
                )

        server_clusters.sort(key=lambda c: c["id"])
        device_type["server_clusters"] = server_clusters
        client_clusters.sort(key=lambda c: c["id"])
        device_type["client_clusters"] = client_clusters
        device_types.append(device_type)

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


def command_arg_to_doc(
    arg: CommandArg, command_args: list[dict], indent: int = 4
) -> str:
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

    if "default" in arg_dict:
        optional = True
        comment_str = f"default: {arg_dict['default']} "
    optional_str = "# " if optional else ""
    comment_str = f"# {comment_str}" if comment_str else ""
    return "\n".join(
        [
            f"{' ' * indent}{optional_str}"
            f"{camel_case_to_snake_case(arg.name)}: {comment_str}".rstrip()
        ]
        + extra_lines
    )


def generate_command_documentation(
    clusters: list[Cluster], processed_commands: dict
) -> str:
    lines = [
        "This file is automatically generated by tools/zap_converter.py. Don't edit it.\n\n"
        "Replace `some_endpoint` with a Matter endpoint id or the id assigned to an endpoint. "
        "The equivalent explicit `endpoint`, `cluster`, and `command` form is also supported.\n"
    ]
    for cluster in sorted(clusters, key=lambda c: c.id):
        cluster_name = camel_case(cluster.name)
        client_commands = [c for c in cluster.commands if c.source == "client"]
        if not client_commands:
            continue
        lines.append(
            f"# {cluster_name}\n\n{sanitize_description(cluster.description)}\n\n```yaml"
        )
        yaml_lines = []
        for command in sorted(client_commands, key=lambda c: c.code):
            command_dict = processed_commands[cluster_name][command.name]
            command_lines = []
            if command.description:
                command_lines.append(
                    "# "
                    + sanitize_description(command.description).replace("\n", "\n# ")
                )
            if command.args:
                command_lines.append("matter.send_command:")
                command_lines.append(
                    "  path: some_endpoint."
                    f"{camel_case_to_snake_case(cluster_name)}."
                    f"{camel_case_to_snake_case(command.name)}"
                )
                command_lines.append("  arguments:")
                for arg in command.args:
                    command_lines.append(command_arg_to_doc(arg, command_dict["args"]))
            else:
                command_lines.append(
                    "matter.send_command: some_endpoint."
                    f"{camel_case_to_snake_case(cluster_name)}."
                    f"{camel_case_to_snake_case(command.name)}"
                )
            yaml_lines.append("\n".join(command_lines))
        lines.append("\n\n".join(yaml_lines))
        lines.append("```\n")
    return "\n".join(lines)


def generate_attribute_documentation(clusters: list[Cluster]) -> str:
    lines = [
        "This file is automatically generated by tools/zap_converter.py. Don't edit it.\n\n"
        "Replace `some_endpoint` with a Matter endpoint id or the id assigned to an endpoint. "
        "The equivalent explicit `endpoint`, `cluster`, and `attribute` form is also supported.\n"
    ]
    for cluster in sorted(clusters, key=lambda c: c.id):
        attributes = [
            attribute
            for attribute in cluster.attributes
            if attribute.name is not None and attribute.side in ("server", "either")
        ]
        if not attributes:
            continue
        cluster_name = camel_case(cluster.name)
        lines.append(
            f"# {cluster_name}\n\n{sanitize_description(cluster.description)}\n\n```yaml"
        )
        yaml_lines = []
        for attribute in sorted(attributes, key=lambda a: a.code):
            yaml_lines.append(
                "\n".join(
                    [
                        "matter.set_attribute:",
                        "  path: some_endpoint."
                        f"{camel_case_to_snake_case(cluster_name)}."
                        f"{camel_case_to_snake_case(attribute.name)}",
                        f"  value:  # {attribute.type}",
                    ]
                )
            )
        lines.append("\n\n".join(yaml_lines))
        lines.append("```\n")
    return "\n".join(lines)


def generate_device_type_documentation(
    device_types: list[dict], clusters: list[Cluster]
) -> str:
    lines = [
        "This file is automatically generated by tools/zap_converter.py. Don't edit it.\n\n"
        "The following examples list every supported Matter device type. Optional features "
        "can be enabled with `with_features`. Features already required by a device type and "
        "features disallowed by it are omitted. Features inherited from required clusters "
        "are shown commented out unless they belong to an unresolved feature choice.\n"
    ]
    clusters_by_id = {cluster.id: cluster for cluster in clusters}
    for device_type in device_types:
        features: dict[str, str | None] = {}
        inherited_features: dict[str, str | None] = {}
        feature_choices: list[tuple[FeatureChoice, dict[str, str | None]]] = []
        feature_choice_keys: set[tuple[int, int | None, tuple[str, ...]]] = set()
        ignored_features: list[str] = []
        for cluster_config in device_type["server_clusters"]:
            cluster = clusters_by_id[cluster_config["id"]]
            conformance = cluster_config.get("features", {})
            for ignored_feature in cluster_config.get("ignored_features", ()):
                if ignored_feature not in ignored_features:
                    ignored_features.append(ignored_feature)

            if cluster_config.get("required", False) and cluster_config.get(
                "ignored_features"
            ):
                for cluster_feature in cluster.features:
                    cluster_feature_items = (
                        cluster_feature.features
                        if isinstance(cluster_feature, FeatureChoice)
                        else (cluster_feature,)
                    )
                    for omitted_feature in cluster_feature_items:
                        if conformance.get(omitted_feature.code) in (
                            "mandatory",
                            "optional",
                            "disallow",
                            "disallowed",
                        ):
                            continue
                        omitted_name = camel_case_to_snake_case(
                            camel_case(omitted_feature.name)
                        )
                        if omitted_name not in ignored_features:
                            ignored_features.append(omitted_name)

            def feature_source(feature: Feature) -> str | None:
                feature_name = camel_case_to_snake_case(camel_case(feature.name))
                if feature_name in cluster_config.get("ignored_features", ()):
                    return None
                feature_conformance = conformance.get(feature.code)
                if feature_conformance in (
                    "mandatory",
                    "disallow",
                    "disallowed",
                ):
                    return None
                # Device types refine the cluster's feature conformance. An
                # omitted feature keeps the availability defined by the cluster.
                # Features on optional clusters were already documented before
                # required clusters began inheriting their cluster features.
                if feature_conformance == "optional" or not cluster_config.get(
                    "required", False
                ):
                    return "explicit"
                return "inherited"

            def add_feature(feature: Feature) -> None:
                source = feature_source(feature)
                if source is None:
                    return
                feature_name = camel_case_to_snake_case(camel_case(feature.name))
                if source == "explicit":
                    inherited_features.pop(feature_name, None)
                    features.setdefault(feature_name, feature.summary)
                elif feature_name not in features:
                    inherited_features.setdefault(feature_name, feature.summary)

            for feature in cluster.features:
                if isinstance(feature, FeatureChoice):
                    mandatory_count = sum(
                        conformance.get(choice_feature.code) == "mandatory"
                        for choice_feature in feature.features
                    )
                    if feature.max is not None and mandatory_count >= feature.max:
                        continue
                    choice_features = {}
                    for choice_feature in feature.features:
                        if feature_source(choice_feature) is None:
                            continue
                        choice_name = camel_case_to_snake_case(
                            camel_case(choice_feature.name)
                        )
                        choice_features[choice_name] = choice_feature.summary
                        add_feature(choice_feature)
                    if choice_features:
                        if mandatory_count < feature.min:
                            # An unresolved choice requires user input, even when
                            # its features are inherited from a required cluster.
                            for choice_name, summary in choice_features.items():
                                inherited_features.pop(choice_name, None)
                                features.setdefault(choice_name, summary)
                            choice_key = (
                                feature.min,
                                feature.max,
                                tuple(choice_features),
                            )
                            if choice_key not in feature_choice_keys:
                                feature_choice_keys.add(choice_key)
                                feature_choices.append((feature, choice_features))
                    continue
                add_feature(feature)

        name = device_type["name"]
        lines.append(f"# {name}\n\n```yaml\nmatter:\n  endpoints:\n    1:")
        if features or inherited_features:
            lines.append(f"      {name}:\n        with_features:")
            if ignored_features:
                lines.append(
                    "          # Omitted because their conformance rules are not yet supported by esphome-matter:"
                )
                lines.extend(
                    f"          # - {ignored_feature}"
                    for ignored_feature in ignored_features
                )
            choice_feature_names = {
                feature_name
                for _, choice_features in feature_choices
                for feature_name in choice_features
            }
            for feature_name, summary in features.items():
                if feature_name in choice_feature_names:
                    continue
                comment = f" # {sanitize_description(summary)}" if summary else ""
                lines.append(f"          - {feature_name}{comment}")
            for choice, choice_features in feature_choices:
                feature_names = ", ".join(choice_features)
                explicit_choice_features = {
                    feature_name: summary
                    for feature_name, summary in choice_features.items()
                    if feature_name in features
                }
                if not explicit_choice_features:
                    continue
                if choice.min == 1 and choice.max == 1:
                    requirement = f"Exactly one of {feature_names} must be enabled."
                else:
                    requirement = f"At least one of {feature_names} must be enabled."
                lines.append(f"          # {requirement}")
                for feature_name, summary in explicit_choice_features.items():
                    comment = f" # {sanitize_description(summary)}" if summary else ""
                    lines.append(f"          - {feature_name}{comment}")
            for feature_name, summary in inherited_features.items():
                if feature_name in choice_feature_names:
                    continue
                comment = f" # {sanitize_description(summary)}" if summary else ""
                lines.append(f"          # - {feature_name}{comment}")
            for choice, choice_features in feature_choices:
                inherited_choice_features = {
                    feature_name: summary
                    for feature_name, summary in choice_features.items()
                    if feature_name in inherited_features
                }
                if not inherited_choice_features:
                    continue
                feature_names = ", ".join(choice_features)
                if choice.min == 1 and choice.max == 1:
                    requirement = f"Exactly one of {feature_names} must be enabled."
                else:
                    requirement = f"At least one of {feature_names} must be enabled."
                if not any(
                    feature_name in features for feature_name in choice_features
                ):
                    lines.append(f"          # {requirement}")
                for feature_name, summary in inherited_choice_features.items():
                    comment = f" # {sanitize_description(summary)}" if summary else ""
                    lines.append(f"          # - {feature_name}{comment}")
        elif ignored_features:
            lines.append(f"      {name}:")
            lines.append(
                "        # Omitted because their conformance rules are not yet supported by esphome-matter:"
            )
            lines.extend(
                f"        # - {ignored_feature}" for ignored_feature in ignored_features
            )
            lines.append("        with_features: []")
        else:
            lines.append(f"      {name}:")

        optional_server_clusters = [
            cluster_config
            for cluster_config in device_type["server_clusters"]
            if not cluster_config.get("required", False)
        ]
        optional_client_clusters = [
            cluster_config
            for cluster_config in device_type["client_clusters"]
            if not cluster_config.get("required", False)
        ]
        if optional_server_clusters:
            lines.append("      clusters:")
            lines.append(
                f"        # The following server clusters are optional to {name};"
            )
            for cluster_config in optional_server_clusters:
                cluster = clusters_by_id[cluster_config["id"]]
                cluster_name = camel_case_to_snake_case(camel_case(cluster.name))
                description = sanitize_description(cluster.description).replace(
                    "\n", " "
                )
                lines.append(f"        {cluster_name}: # {description}")
            if optional_client_clusters:
                lines.append(
                    "        # Client clusters aren't supported by esphome-matter yet."
                )
                for cluster_config in optional_client_clusters:
                    cluster = clusters_by_id[cluster_config["id"]]
                    cluster_name = camel_case_to_snake_case(camel_case(cluster.name))
                    description = sanitize_description(cluster.description).replace(
                        "\n", " "
                    )
                    lines.append(f"        # {cluster_name}: # {description}")
        elif optional_client_clusters:
            lines.append("      clusters:")
            lines.append(
                f"        # The following client clusters are optional to {name}, but "
                "client clusters aren't supported by esphome-matter yet;"
            )
            for cluster_config in optional_client_clusters:
                cluster = clusters_by_id[cluster_config["id"]]
                cluster_name = camel_case_to_snake_case(camel_case(cluster.name))
                description = sanitize_description(cluster.description).replace(
                    "\n", " "
                )
                lines.append(f"        # {cluster_name}: # {description}")
        lines.append("```\n")
    return "\n".join(lines)


def generate_event_documentation(
    clusters: list[Cluster], processed_events: dict
) -> str:
    lines = [
        "This file is automatically generated by tools/zap_converter.py. Don't edit it.\n\n"
        "Replace `some_endpoint` with a Matter endpoint id or the id assigned to an endpoint. "
        "The equivalent explicit `endpoint`, `cluster`, and `event` form is also supported.\n"
    ]
    for cluster in sorted(clusters, key=lambda c: c.id):
        cluster_name = camel_case(cluster.name)
        events = [e for e in cluster.events if e.api_maturity != "provisional"]
        if not events:
            continue
        lines.append(
            f"# {cluster_name}\n\n{sanitize_description(cluster.description)}\n\n```yaml"
        )
        yaml_lines = []
        for event in sorted(events, key=lambda e: e.code):
            event_dict = processed_events[cluster_name][event.name]
            event_lines = []
            if event.description:
                event_lines.append(
                    "# " + sanitize_description(event.description).replace("\n", "\n# ")
                )
            event_lines.append(
                "matter.send_event:\n  path: some_endpoint."
                f"{camel_case_to_snake_case(cluster_name)}."
                f"{camel_case_to_snake_case(event.name)}"
            )
            if event.fields:
                event_lines.append("  fields:")
                for event_field in event.fields:
                    event_lines.append(
                        command_arg_to_doc(event_field, event_dict["fields"], indent=4)
                    )
            yaml_lines.append("\n".join(event_lines))
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
    return parser.parse_args()


def main():
    args = parse_args()
    raw_device_types, raw_clusters, enums, bitmaps, structs = parse_data_model(
        args.data_model_path
    )

    field_resolver = FieldResolver(enums, bitmaps, structs)
    commands = post_process_commands(raw_clusters, field_resolver)
    events = post_process_events(raw_clusters, field_resolver)
    clusters = post_process_clusters(raw_clusters)
    device_types = post_process_device_types(raw_device_types, raw_clusters)
    fixup(device_types)

    with open(args.output_path / "overrides" / "clusters.json") as file:
        cluster_overrides = json.load(file)
    apply_cluster_overrides(clusters, cluster_overrides)

    with open(args.output_path / "device_types.json", "w") as file:
        json.dump(sorted(device_types, key=lambda d: d["id"]), file, indent=2)

    with open(args.output_path / "clusters.json", "w") as file:
        json.dump(clusters, file, indent=2)

    with open(args.output_path / "overrides" / "commands.json") as file:
        command_overrides = json.load(file)
    apply_command_overrides(commands, command_overrides)
    with open(args.output_path / "commands.json", "w") as file:
        json.dump(commands, file, indent=2)

    with open(args.output_path / "events.json", "w") as file:
        json.dump(events, file, indent=2)

    documentation_path = Path(__file__).resolve().parent.parent / "docs" / "generated"
    documentation_path.mkdir(parents=True, exist_ok=True)
    with open(documentation_path / "commands.md", "w") as file:
        file.write(generate_command_documentation(raw_clusters, commands))
    # with open(documentation_path / "attributes.md", "w") as file:
    #     file.write(generate_attribute_documentation(raw_clusters))
    with open(documentation_path / "device_types.md", "w") as file:
        file.write(generate_device_type_documentation(device_types, raw_clusters))
    with open(documentation_path / "events.md", "w") as file:
        file.write(generate_event_documentation(raw_clusters, events))

    arg_types = defaultdict(int)
    for cl in commands.values():
        for c in cl.values():
            for arg in c["args"]:
                arg_types[arg["type"]] += 1
    print("command arg types: ", format_counter(arg_types))


if __name__ == "__main__":
    main()
