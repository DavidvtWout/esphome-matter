from dataclasses import dataclass
from typing import Any


class ConformanceError(ValueError):
    pass


class AmbiguousConformanceError(ConformanceError):
    pass


@dataclass(frozen=True, slots=True)
class Requirement:
    required_features: frozenset[str] = frozenset()
    prohibited_features: frozenset[str] = frozenset()

    def merge(self, other: "Requirement") -> "Requirement":
        required = self.required_features | other.required_features
        prohibited = self.prohibited_features | other.prohibited_features
        conflict = required & prohibited
        if conflict:
            names = ", ".join(sorted(conflict))
            raise ConformanceError(f"Conformance both requires and prohibits: {names}")
        return Requirement(required, prohibited)


@dataclass(frozen=True, slots=True)
class Conformance:
    rule: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict | None) -> "Conformance | None":
        return cls(data) if data is not None else None

    def alternatives(self) -> tuple[Requirement, ...]:
        return tuple(_rule_alternatives(self.rule))


def _combine(left: list[Requirement], right: list[Requirement]) -> list[Requirement]:
    combined = []
    for left_requirement in left:
        for right_requirement in right:
            combined.append(left_requirement.merge(right_requirement))
    return combined


def _term_alternatives(term: Any) -> list[Requirement]:
    if term is True:
        return [Requirement()]
    if not isinstance(term, dict) or len(term) != 1:
        raise ConformanceError(f"Unsupported conformance term: {term!r}")

    operator, value = next(iter(term.items()))
    if operator == "feature":
        return [Requirement(required_features=frozenset((value,)))]
    if operator == "and":
        alternatives = [Requirement()]
        for child in value:
            alternatives = _combine(alternatives, _term_alternatives(child))
        return alternatives
    if operator == "or":
        return [
            alternative for child in value for alternative in _term_alternatives(child)
        ]
    if operator == "not":
        if not isinstance(value, dict) or set(value) != {"feature"}:
            raise ConformanceError(
                f"Only negated feature references can currently be resolved: {value!r}"
            )
        return [Requirement(prohibited_features=frozenset((value["feature"],)))]
    raise ConformanceError(f"Unsupported conformance term operator: {operator}")


def _conform_payload_alternatives(payload: Any) -> list[Requirement]:
    if payload is True:
        return [Requirement()]
    if isinstance(payload, dict) and "term" in payload:
        return _term_alternatives(payload["term"])
    # Choice metadata without a term does not constrain feature availability.
    if isinstance(payload, dict) and set(payload) <= {"choice", "min", "max", "more"}:
        return [Requirement()]
    return _term_alternatives(payload)


def _rule_alternatives(rule: Any) -> list[Requirement]:
    if not isinstance(rule, dict) or len(rule) != 1:
        raise ConformanceError(f"Unsupported conformance rule: {rule!r}")

    rule_type, payload = next(iter(rule.items()))
    if rule_type in ("mandatory", "optional"):
        return _conform_payload_alternatives(payload)
    if rule_type == "otherwise":
        return [
            alternative
            for child in payload
            for alternative in _rule_alternatives(child)
        ]
    if rule_type == "all":
        alternatives = [Requirement()]
        for child in payload:
            alternatives = _combine(alternatives, _rule_alternatives(child))
        return alternatives
    if rule_type == "disallowed":
        return []
    if rule_type in ("deprecated", "provisional"):
        return [Requirement()]
    raise ConformanceError(f"Unsupported conformance rule type: {rule_type}")


def _select_requirement(
    alternatives: tuple[Requirement, ...], enabled_features: set[str]
) -> Requirement:
    compatible = [
        requirement
        for requirement in alternatives
        if not requirement.prohibited_features & enabled_features
    ]
    if not compatible:
        raise ConformanceError(
            "No conformance alternative is compatible with enabled features"
        )
    if len(compatible) == 1:
        return compatible[0]

    satisfied = [
        requirement
        for requirement in compatible
        if requirement.required_features <= enabled_features
    ]
    if len(satisfied) == 1:
        return satisfied[0]

    best_score = max(
        len(requirement.required_features & enabled_features)
        for requirement in compatible
    )
    best = [
        requirement
        for requirement in compatible
        if len(requirement.required_features & enabled_features) == best_score
    ]
    if best_score and len(best) == 1:
        return best[0]

    choices = " or ".join(
        "+".join(sorted(requirement.required_features)) or "no additional features"
        for requirement in compatible
    )
    raise AmbiguousConformanceError(
        f"Conformance requires an explicit choice: {choices}"
    )


def resolve_feature_requirements(
    requirements: list[Conformance],
    feature_conformance: dict[str, Conformance | None],
    enabled_features: set[str],
) -> set[str]:
    """Resolve unambiguous feature dependencies to a fixed point."""
    enabled = set(enabled_features)
    pending = list(requirements)
    resolved_features = set()
    deferred = 0

    while pending:
        conformance = pending.pop(0)
        try:
            requirement = _select_requirement(conformance.alternatives(), enabled)
        except AmbiguousConformanceError:
            pending.append(conformance)
            deferred += 1
            if deferred >= len(pending):
                raise
            continue
        deferred = 0
        conflict = requirement.prohibited_features & enabled
        if conflict:
            names = ", ".join(sorted(conflict))
            raise ConformanceError(f"Conformance prohibits enabled features: {names}")

        for feature_code in requirement.required_features - enabled:
            enabled.add(feature_code)
            resolved_features.add(feature_code)
            dependency = feature_conformance.get(feature_code)
            if dependency is not None:
                pending.append(dependency)

    return resolved_features
