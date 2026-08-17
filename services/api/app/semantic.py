from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path
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


class ArtifactSemanticScorer:
    def __init__(self, artifact_dir: Path) -> None:
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install services/api[semantic] to serve the NLI artifact") from exc
        manifest = json.loads((artifact_dir / "manifest.json").read_text())
        model_dir = artifact_dir / "model"
        digest = hashlib.sha256()
        for path in sorted(value for value in model_dir.rglob("*") if value.is_file()):
            digest.update(str(path.relative_to(model_dir)).encode())
            digest.update(path.read_bytes())
        if digest.hexdigest() != manifest["model_tree_sha256"]:
            raise RuntimeError("semantic model checksum does not match its manifest")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True)
        self.temperature = float(manifest["temperature"])
        self.version = str(manifest["model_version"])

    def score(self, constraints: list[Constraint], cart: CartEvidence) -> list[SemanticResult]:
        import torch

        semantic_constraints = [value for value in constraints if value.type == ConstraintType.SEMANTIC_ATTRIBUTE]
        if not semantic_constraints:
            return []
        evidence = "\n".join(value.description for value in cart.line_items)
        hypotheses = [
            f"The proposed purchase satisfies this requirement: {value.value}." for value in semantic_constraints
        ]
        encoded = self.tokenizer(
            [evidence] * len(hypotheses),
            hypotheses,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        with torch.inference_mode():
            logits = self.model(**encoded).logits.tolist()
        results: list[SemanticResult] = []
        for constraint, row in zip(semantic_constraints, logits, strict=True):
            scaled = [value / self.temperature for value in row]
            offset = max(scaled)
            values = [math.exp(value - offset) for value in scaled]
            probabilities = [value / sum(values) for value in values]
            results.append(
                SemanticResult(
                    constraint_id=constraint.constraint_id,
                    contradiction=probabilities[0],
                    entailment=probabilities[2],
                    neutral=probabilities[1],
                    evidence_reference=cart.evidence_reference,
                )
            )
        return results


@lru_cache(maxsize=1)
def configured_semantic_scorer() -> SemanticScorer:
    if os.getenv("ACE_MODEL_MODE") == "unavailable":
        return UnavailableSemanticScorer()
    artifact_value = os.getenv("ACE_SEMANTIC_ARTIFACT")
    artifact = Path(artifact_value) if artifact_value else None
    if os.getenv("ACE_MODEL_MODE") == "artifact" and artifact is not None and (artifact / "manifest.json").exists():
        return ArtifactSemanticScorer(artifact)
    return HeuristicSemanticScorer()
