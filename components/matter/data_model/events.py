from dataclasses import dataclass

from ..util import snake_case
from .commands import Field
from .conformance import Conformance

_PRIORITIES = {
    "debug": 0,
    "info": 1,
    "critical": 2,
}


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    name: str  # CamelCase
    conf_key: str  # snake_case
    priority: int
    fields: tuple[Field, ...] = ()
    conformance: Conformance | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict):
        return cls(
            id=data["id"],
            name=name,
            conf_key=snake_case(name),
            priority=_PRIORITIES[data.get("priority", "info")],
            fields=tuple(Field.from_dict(field) for field in data["fields"]),
            conformance=Conformance.from_dict(data.get("conformance")),
        )
