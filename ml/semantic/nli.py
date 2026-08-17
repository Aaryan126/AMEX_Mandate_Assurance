from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NliProbabilities:
    contradiction: float
    entailment: float
    neutral: float


class TemperatureScaler:
    def __init__(self, temperature: float = 1.0) -> None:
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        self.temperature = temperature

    def probabilities(self, logits: list[float]) -> list[float]:
        if len(logits) != 3:
            raise ValueError("NLI calibration requires exactly three logits")
        scaled = [value / self.temperature for value in logits]
        offset = max(scaled)
        exponents = [math.exp(value - offset) for value in scaled]
        total = sum(exponents)
        return [value / total for value in exponents]


def semantic_cache_key(
    premise: str,
    hypothesis: str,
    model_version: str,
    tokenizer_version: str,
) -> str:
    payload = {
        "premise": premise.strip(),
        "hypothesis": hypothesis.strip(),
        "model_version": model_version,
        "tokenizer_version": tokenizer_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class TransformersNliScorer:
    """Optional artifact-backed scorer; importing this module never downloads a model."""

    def __init__(
        self,
        model_path: str,
        *,
        temperature: float = 1.0,
        model_version: str = "nli-deberta-v1",
    ) -> None:
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install the semantic model dependencies before loading NLI") from exc
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_path, local_files_only=True
            )
        except Exception as exc:
            raise RuntimeError(
                "The local NLI artifact is unavailable. Run the checksum-verified model bootstrap first."
            ) from exc
        self.scaler = TemperatureScaler(temperature)
        self.model_version = model_version

    def score_batch(self, pairs: list[tuple[str, str]]) -> list[NliProbabilities]:
        import torch

        encoded = self.tokenizer(
            [pair[0] for pair in pairs],
            [pair[1] for pair in pairs],
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        with torch.inference_mode():
            logits = self.model(**encoded).logits.tolist()
        labels = {int(index): str(label).lower() for index, label in self.model.config.id2label.items()}
        output: list[NliProbabilities] = []
        for row in logits:
            probabilities = self.scaler.probabilities(row)
            by_label: dict[str, float] = {labels[index]: value for index, value in enumerate(probabilities)}
            output.append(
                NliProbabilities(
                    contradiction=_label_probability(by_label, "contradiction"),
                    entailment=_label_probability(by_label, "entailment"),
                    neutral=_label_probability(by_label, "neutral"),
                )
            )
        return output


def _label_probability(probabilities: dict[str, float], target: str) -> float:
    aliases: dict[str, tuple[str, ...]] = {
        "contradiction": ("contradiction", "label_0"),
        "entailment": ("entailment", "label_1", "label_2"),
        "neutral": ("neutral", "label_1"),
    }
    for alias in aliases[target]:
        if alias in probabilities:
            return probabilities[alias]
    raise ValueError(f"Model labels do not expose the required NLI class: {target}")


def pair_from_evidence(constraint: dict[str, Any], evidence_text: str) -> tuple[str, str]:
    value = str(constraint.get("value", "")).strip()
    if not value:
        raise ValueError("semantic constraint requires a value")
    return evidence_text.strip(), f"The proposed purchase is {value}."

