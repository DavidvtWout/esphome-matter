import json
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandArg

_PRIORITIES = {
    "debug": 0,
    "info": 1,
    "critical": 2,
}


@dataclass(frozen=True, slots=True)
class Event:
    cluster_name: str  # CamelCase
    name: str  # CamelCase
    id: int
    priority: int
    fields: tuple[CommandArg, ...] = ()

    @classmethod
    def from_dict(cls, cluster_name: str, name: str, data: dict):
        return cls(
            cluster_name=cluster_name,
            name=name,
            id=data["id"],
            priority=_PRIORITIES[data.get("priority", "info")],
            fields=tuple(CommandArg.from_dict(field) for field in data["fields"]),
        )


def _load_events(
    events_file: Path = Path(__file__).resolve().parent / "events.json",
) -> tuple[Event, ...]:
    events = []
    with open(events_file, "r") as file:
        contents = json.load(file)
    for cluster_name, events_data in contents.items():
        for name, data in events_data.items():
            events.append(Event.from_dict(cluster_name, name, data))
    return tuple(events)


EVENTS: tuple[Event, ...] = _load_events()
