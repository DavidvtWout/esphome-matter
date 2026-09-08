from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Conformance:
    type: str
    name: str | None = None
    value: Any = None
    choice: str | None = None
    more: bool = False
    min: int | None = None
    max: int | None = None
    children: tuple["Conformance", ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict | None, *, optional: bool = False):
        if data is None:
            return cls("optional" if optional else "mandatory")
        return cls(
            type=data["type"],
            name=data.get("name"),
            value=data.get("value"),
            choice=data.get("choice"),
            more=data.get("more", False),
            min=data.get("min"),
            max=data.get("max"),
            children=tuple(cls.from_dict(child) for child in data.get("children", ())),
        )

    def _expression(self, features: frozenset[str], revision: int | None) -> bool:
        if self.type == "feature":
            return self.name in features
        if self.type == "revision":
            return revision is not None and revision >= int(self.value)
        if self.type == "literal":
            return bool(self.value)
        if self.type == "not_term":
            return not self.children[0]._expression(features, revision)
        if self.type == "and_term":
            return all(child._expression(features, revision) for child in self.children)
        if self.type == "or_term":
            return any(child._expression(features, revision) for child in self.children)
        if self.type in {"greater_term", "greater_or_equal_term"}:
            left, right = (
                child._numeric_expression(features, revision) for child in self.children
            )
            return left > right if self.type == "greater_term" else left >= right
        # Attribute, command and named conditions require endpoint state which the
        # ESPHome configuration model does not currently expose.
        return False

    def _numeric_expression(
        self, features: frozenset[str], revision: int | None
    ) -> int:
        if self.type == "revision":
            return revision or 0
        if self.type == "literal":
            return int(self.value)
        return int(self._expression(features, revision))

    def decision(
        self, features: frozenset[str] = frozenset(), revision: int | None = None
    ) -> str | None:
        if self.type == "otherwise":
            # Matter XML is not consistent about placing the unconditional
            # fallback first or last. Evaluate conditional alternatives first.
            ordered_children = sorted(
                self.children, key=lambda child: not child.children
            )
            for child in ordered_children:
                if (decision := child.decision(features, revision)) is not None:
                    return decision
            return None
        if self.type in {
            "mandatory",
            "optional",
            "provisional",
            "deprecate",
            "disallow",
            "described",
        }:
            if not self.children or all(
                child._expression(features, revision) for child in self.children
            ):
                return self.type
            return None
        return None

    def is_mandatory(
        self, features: frozenset[str] = frozenset(), revision: int | None = None
    ) -> bool:
        return self.decision(features, revision) == "mandatory"
