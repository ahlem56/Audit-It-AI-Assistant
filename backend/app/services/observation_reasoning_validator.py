from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.audit_input import AuditObservation
from app.models.observation_reasoning import ObservationReasoning


@dataclass(frozen=True)
class ReasoningValidation:
    ok: bool
    issues: list[str]


_NUM_RE = re.compile(r"\b\d+\b")


def _extract_numbers(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _has_evidence_keywords(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "echantillon",
            "sur l'echantillon",
            "sur l’echantillon",
            "aucun",
            "aucune",
            "absence",
            "0 ",
            "zero",
            "plusieurs",
            "total",
            "parmi",
        )
    )


def validate_reasoning(observation: AuditObservation, reasoning: ObservationReasoning) -> ReasoningValidation:
    issues: list[str] = []

    constat_numbers = _extract_numbers(observation.constat)
    justification_numbers = _extract_numbers(reasoning.priority_justification)

    # If the finding includes digits, we expect justification to reuse at least one of them.
    if constat_numbers and not (constat_numbers & justification_numbers):
        issues.append("priority_justification_missing_factual_numbers")

    # If there are no digits, still require explicit evidence language.
    if not constat_numbers and reasoning.priority_justification and not _has_evidence_keywords(reasoning.priority_justification):
        issues.append("priority_justification_missing_evidence_language")

    # If justification is empty, it is always weak (will be auto-generated downstream).
    if not (reasoning.priority_justification or "").strip():
        issues.append("priority_justification_empty")

    ok = not any(
        issue in issues
        for issue in (
            "priority_justification_missing_factual_numbers",
            "priority_justification_missing_evidence_language",
        )
    )
    return ReasoningValidation(ok=ok, issues=issues)

