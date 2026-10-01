from dataclasses import dataclass

from ..util import snake_case
from .commands import CommandArg
from .conformance import Conformance

_PRIORITIES = {
    "debug": 0,
    "info": 1,
    "critical": 2,
}


@dataclass(frozen=True, slots=True)
class Event:
    cluster_name: str  # CamelCase
    name: str  # CamelCase
    conf_key: str  # snake_case
    id: int
    priority: int
    fields: tuple[CommandArg, ...] = ()
    conformance: Conformance | None = None

    @classmethod
    def from_dict(cls, cluster_name: str, name: str, data: dict):
        return cls(
            cluster_name=cluster_name,
            name=name,
            conf_key=snake_case(name),
            id=data["id"],
            priority=_PRIORITIES[data.get("priority", "info")],
            fields=tuple(CommandArg.from_dict(field) for field in data["fields"]),
            conformance=Conformance.from_dict(data.get("conformance")),
        )
