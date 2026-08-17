from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ml.data.schema import AceDatasetExample, SemanticLabel

LABEL_IDS = {
    SemanticLabel.CONTRADICTION: 0,
    SemanticLabel.NEUTRAL: 1,
    SemanticLabel.ENTAILMENT: 2,
}
ID_LABELS = {value: key.value for key, value in LABEL_IDS.items()}


@dataclass(frozen=True)
class NliTrainingRow:
    example_id: str
    group_id: str
    constraint_id: str
    split: str
    premise: str
    hypothesis: str
    label: int


def nli_rows(example: AceDatasetExample) -> list[NliTrainingRow]:
    annotations = {
        value.constraint_id: value.label for value in example.labels.semantic
    }
    evidence = "\n".join(
        value.evidence_text or value.description for value in example.cart.line_items
    ).strip()
    output: list[NliTrainingRow] = []
    for constraint in example.mandate.constraints:
        label = annotations.get(constraint.constraint_id)
        if constraint.type != "semantic_attribute" or label is None:
            continue
        output.append(
            NliTrainingRow(
                example_id=example.identity.example_id,
                group_id=example.identity.group_id,
                constraint_id=constraint.constraint_id,
                split=example.split.name,
                premise=evidence,
                hypothesis=f"The proposed purchase satisfies this requirement: {constraint.value}.",
                label=LABEL_IDS[label],
            )
        )
    return output


def load_nli_rows(path: Path) -> list[NliTrainingRow]:
    rows: list[NliTrainingRow] = []
    with path.open() as source:
        for line in source:
            if line.strip():
                rows.extend(nli_rows(AceDatasetExample.model_validate_json(line)))
    return rows


def fold_for_group(group_id: str, folds: int, seed: int = 2026) -> int:
    if folds < 2:
        raise ValueError("semantic cross-fitting requires at least two folds")
    digest = hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()
    return int(digest[:16], 16) % folds
