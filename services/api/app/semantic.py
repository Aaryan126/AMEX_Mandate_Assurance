from __future__ import annotations

from typing import Protocol

from .schemas import CartEvidence, Constraint, ConstraintType, SemanticResult


class SemanticScorer(Protocol):
    version: str

    def score(self, constraints: list[Constraint], cart: CartEvidence) -> list[SemanticResult]: ...


class HeuristicSemanticScorer:
    """Deterministic, offline scorer used by the default demo and test suite."""

    version = "heuristic-nli-v1"

    def score(self, constraints: list[Constraint], cart: CartEvidence) -> list[SemanticResult]:
        results: list[SemanticResult] = []
        combined_description = " ".join(item.description.lower() for item in cart.line_items)
        attributes = [item.attributes for item in cart.line_items]
        for constraint in constraints:
            if constraint.type != ConstraintType.SEMANTIC_ATTRIBUTE:
                continue
            required = str(constraint.value).lower()
            values = [attrs.get(required) for attrs in attributes if required in attrs]
            if required == "economy" and not values:
                values = [attrs.get("cabin") == "economy" for attrs in attributes if "cabin" in attrs]
            if required == "nonstop" and not values:
                values = [attrs.get("stops") == 0 for attrs in attributes if "stops" in attrs]

            if any(value is False for value in values) or f"non-{required}" in combined_description:
                contradiction, entailment, neutral = 0.97, 0.01, 0.02
            elif any(value is True for value in values) or required in combined_description:
                contradiction, entailment, neutral = 0.01, 0.97, 0.02
            else:
                contradiction, entailment, neutral = 0.05, 0.05, 0.90
            results.append(
                SemanticResult(
                    constraint_id=constraint.constraint_id,
                    contradiction=contradiction,
                    entailment=entailment,
                    neutral=neutral,
                    evidence_reference=cart.evidence_reference,
                )
            )
        return results


class UnavailableSemanticScorer:
    version = "semantic-unavailable"

    def score(self, constraints: list[Constraint], cart: CartEvidence) -> list[SemanticResult]:
        return [
            SemanticResult(
                constraint_id=constraint.constraint_id,
                contradiction=0.0,
                entailment=0.0,
                neutral=1.0,
                evidence_reference=cart.evidence_reference,
            )
            for constraint in constraints
            if constraint.type == ConstraintType.SEMANTIC_ATTRIBUTE
        ]

