import re

import esphome.config_validation as cv


def snake_case(name: str) -> str:
    """Converts CamelCase to snake_case."""
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def maybe_empty(*validators):
    """Allow an empty config section instead of requiring an empty {}."""
    return cv.All(lambda v: {} if v is None else v, *validators)
