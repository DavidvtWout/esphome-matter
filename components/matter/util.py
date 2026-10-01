import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import esphome.config_validation as cv
from esphome.types import ConfigFragmentType


def load_data_model_json(path: Path, data_type):
    items = []
    with open(path, "r") as file:
        contents = json.load(file)
    for cluster_name, commands_data in contents.items():
        for name, data in commands_data.items():
            items.append(data_type.from_dict(cluster_name, name, data))
    return tuple(items)


def iter_matter_actions(
    config: ConfigFragmentType,
) -> Iterator[tuple[str, Mapping]]:
    """Yield all Matter actions from a configuration fragment."""
    if isinstance(config, Mapping):
        for key, value in config.items():
            if isinstance(key, str) and key.startswith("matter."):
                yield key, value
            yield from iter_matter_actions(value)
    elif isinstance(config, Sequence) and not isinstance(config, (str, bytes)):
        for value in config:
            yield from iter_matter_actions(value)


def snake_case(name: str) -> str:
    """Converts CamelCase to snake_case."""
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def maybe_empty(*validators):
    """Allow an empty config section instead of requiring an empty {}."""
    return cv.All(lambda v: {} if v is None else v, *validators)
