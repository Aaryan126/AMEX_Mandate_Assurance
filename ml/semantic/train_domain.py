from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.semantic.checkpoints import (
    base_model_binding,
    file_sha256,
    keys_sha256,
    row_key,
    source_tree_sha256,
)
from ml.semantic.dataset import NliTrainingRow, load_nli_rows
from ml.semantic.train_multilingual import (
    ADAMW_EPSILON,
    ADAMW_FOREACH,
    CANONICAL_LABEL_NAMES,
    TRAINING_DTYPE,
    _predict,
    _release_model,
    _train_model,
    canonical_label_indices,
    validate_prediction_quality,
)

DOMAIN_MODEL_VERSION = "english-nli-option2-domain-v3"

CONTRADICTION_PROBES = [
    NliTrainingRow(
        example_id=f"preservation-{index}",
        group_id=f"preservation-{index}",
        constraint_id="contradiction",
        split="validation",
        premise=premise,
        hypothesis=hypothesis,
        label=0,
    )
    for index, (premise, hypothesis) in enumerate(
        [
            ("The transfer amount is 50 dollars.", "The transfer amount is 500 dollars."),
            ("The delivery address is Singapore.", "The delivery address is London."),
            ("The card must remain active.", "The card must be closed."),
            ("The purchase must be under 100 dollars.", "The purchase costs 900 dollars."),
            ("The customer requested a red jacket.", "The jacket is blue."),
            ("The booking is for Monday.", "The booking is for Friday."),
            ("The payment currency is USD.", "The payment currency is EUR."),
            ("International transfers are permitted.", "International transfers are forbidden."),
        ]
    )
]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def state_path_for(output_dir: Path) -> Path:
    return Path(f"{output_dir}.state.json")


def staging_path_for(output_dir: Path) -> Path:
    return Path(f"{output_dir}.staging")


def _configuration(
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    gradient_accumulation_steps: int,
    gradient_checkpointing: bool,
    freeze_classifier: bool,
    class_weights: list[float],
) -> dict[str, Any]:
    if epochs < 1 or batch_size < 1 or gradient_accumulation_steps < 1:
        raise ValueError("domain epochs and batch parameters must be positive")
    if learning_rate <= 0:
        raise ValueError("domain learning rate must be positive")
    if not freeze_classifier:
        raise ValueError(
            "Option 2 domain adaptation requires a frozen classifier to preserve the absent contradiction class"
        )
    return {
        "epochs": epochs,
        "micro_batch_size": batch_size,
        "learning_rate": learning_rate,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "effective_batch_size": batch_size * gradient_accumulation_steps,
        "gradient_checkpointing": gradient_checkpointing,
        "freeze_classifier": freeze_classifier,
        "optimizer": {
            "name": "AdamW",
            "epsilon": ADAMW_EPSILON,
            "foreach": ADAMW_FOREACH,
        },
        "training_dtype": TRAINING_DTYPE,
        "canonical_label_order": CANONICAL_LABEL_NAMES,
        "class_weighting": "inverse_frequency_observed_labels",
        "class_weights": class_weights,
        "random_seed": 2026,
        "model_version": DOMAIN_MODEL_VERSION,
    }


def _rows_binding(rows: list[NliTrainingRow]) -> dict[str, Any]:
    selected = [row for row in rows if row.split in {"train", "validation"}]
    training = [row for row in selected if row.split == "train"]
    validation = [row for row in selected if row.split == "validation"]
    if not training or not validation:
        raise ValueError("domain adaptation requires train and validation semantic rows")
    keys = [row_key(row) for row in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("domain semantic rows contain duplicate keys")
    training_labels = dict(sorted(Counter(row.label for row in training).items()))
    if len(training_labels) < 2:
        raise ValueError("domain adaptation requires at least two observed training labels")
    return {
        "semantic_rows": len(selected),
        "keys_sha256": keys_sha256(keys),
        "training_rows": len(training),
        "training_groups": len({row.group_id for row in training}),
        "training_labels": {str(key): value for key, value in training_labels.items()},
        "validation_rows": len(validation),
        "validation_groups": len({row.group_id for row in validation}),
        "validation_labels": {
            str(key): value
            for key, value in sorted(Counter(row.label for row in validation).items())
        },
    }


def inverse_frequency_class_weights(rows: list[NliTrainingRow]) -> list[float]:
    counts = Counter(row.label for row in rows)
    if len(counts) < 2:
        raise ValueError("class weighting requires at least two observed labels")
    total = sum(counts.values())
    return [
        total / (len(counts) * counts[label]) if label in counts else 0.0
        for label in range(3)
    ]


def _expected_state(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    rows: list[NliTrainingRow],
    configuration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "prepared",
        "dataset": {
            "path": str(dataset_path),
            "sha256": file_sha256(dataset_path),
            **_rows_binding(rows),
        },
        "base_model": base_model_binding(base_model),
        "output_dir": str(output_dir),
        "staging_dir": str(staging_path_for(output_dir)),
        "configuration": configuration,
        "attempts": 0,
    }


def _validate_completed_output(state: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(state["output_dir"])
    manifest_path = output_dir / "ace-artifact-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("completed domain checkpoint manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    if state.get("output_manifest_sha256") != file_sha256(manifest_path):
        raise ValueError("completed domain checkpoint manifest checksum mismatch")
    tree_sha256 = source_tree_sha256(output_dir)
    if manifest.get("tree_sha256") != tree_sha256:
        raise ValueError("completed domain checkpoint tree checksum mismatch")
    if state.get("output_tree_sha256") != tree_sha256:
        raise ValueError("domain state output-tree checksum mismatch")
    return manifest


def _validate_saved_domain_model(base_model: Path, output_dir: Path) -> None:
    try:
        import torch
        from safetensors import safe_open
    except ImportError as exc:
        raise RuntimeError("Install services/api[semantic] on the training host") from exc

    base_weights = base_model / "model.safetensors"
    output_weights = output_dir / "model.safetensors"
    base_config = json.loads((base_model / "config.json").read_text())
    classifier_order = canonical_label_indices(base_config["id2label"])
    with safe_open(base_weights, framework="pt", device="cpu") as base, safe_open(
        output_weights, framework="pt", device="cpu"
    ) as output:
        classifier_keys = sorted(
            key for key in output.keys() if "classifier" in key  # noqa: SIM118
        )
        if not classifier_keys:
            raise ValueError("saved domain model does not contain a classifier")
        for key in output.keys():  # noqa: SIM118
            tensor = output.get_tensor(key)
            if tensor.is_floating_point() and not bool(torch.isfinite(tensor).all()):
                raise FloatingPointError(f"saved domain model contains non-finite tensor: {key}")
        for key in classifier_keys:
            if key not in base.keys():  # noqa: SIM118
                raise ValueError(f"base model is missing classifier tensor: {key}")
            expected = base.get_tensor(key)
            if expected.shape[0] == len(classifier_order):
                expected = expected[classifier_order]
            if not torch.equal(expected, output.get_tensor(key)):
                raise ValueError(f"frozen classifier tensor changed: {key}")


def prepare_domain_training(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    *,
    epochs: int = 1,
    batch_size: int = 16,
    learning_rate: float = 5e-6,
    gradient_accumulation_steps: int = 1,
    gradient_checkpointing: bool = True,
    freeze_classifier: bool = True,
) -> dict[str, Any]:
    rows = load_nli_rows(dataset_path)
    class_weights = inverse_frequency_class_weights(
        [row for row in rows if row.split == "train"]
    )
    configuration = _configuration(
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        freeze_classifier=freeze_classifier,
        class_weights=class_weights,
    )
    expected = _expected_state(
        dataset_path, base_model, output_dir, rows, configuration
    )
    state_path = state_path_for(output_dir)
    if state_path.exists():
        state = json.loads(state_path.read_text())
        for key in (
            "schema_version",
            "dataset",
            "base_model",
            "output_dir",
            "staging_dir",
            "configuration",
        ):
            if state.get(key) != expected[key]:
                raise ValueError(f"domain training state binding mismatch: {key}")
        if state.get("status") == "completed":
            _validate_completed_output(state)
        elif output_dir.exists():
            raise ValueError("incomplete domain state cannot adopt an existing output")
        return state
    if output_dir.exists():
        raise ValueError("domain output exists without a bound training state")
    now = _timestamp()
    expected["created_at"] = now
    expected["updated_at"] = now
    _atomic_json(state_path, expected)
    return expected


def train_domain(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    *,
    epochs: int = 1,
    batch_size: int = 16,
    learning_rate: float = 5e-6,
    gradient_accumulation_steps: int = 1,
    gradient_checkpointing: bool = True,
    freeze_classifier: bool = True,
) -> dict[str, Any]:
    state = prepare_domain_training(
        dataset_path,
        base_model,
        output_dir,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        freeze_classifier=freeze_classifier,
    )
    state_path = state_path_for(output_dir)
    if state["status"] == "completed":
        return _validate_completed_output(state)
    state["status"] = "running"
    state["attempts"] = int(state.get("attempts", 0)) + 1
    state["started_at"] = _timestamp()
    state["updated_at"] = _timestamp()
    state.pop("error", None)
    _atomic_json(state_path, state)

    staging_dir = staging_path_for(output_dir)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    rows = load_nli_rows(dataset_path)
    training = [row for row in rows if row.split == "train"]
    validation = [row for row in rows if row.split == "validation"]
    model = None
    tokenizer = None
    try:
        model, tokenizer = _train_model(
            training,
            validation,
            base_model,
            staging_dir,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_checkpointing=gradient_checkpointing,
            freeze_classifier=freeze_classifier,
            require_accelerator=True,
            class_weights=state["configuration"]["class_weights"],
        )
        by_label: dict[int, list[NliTrainingRow]] = {}
        for row in validation:
            if len(by_label.setdefault(row.label, [])) < 16:
                by_label[row.label].append(row)
        smoke_rows = [row for label in sorted(by_label) for row in by_label[label]]
        smoke_logits = _predict(model, tokenizer, smoke_rows, batch_size=16)
        validate_prediction_quality(smoke_logits, context="domain model")
        preservation_logits = _predict(
            model, tokenizer, CONTRADICTION_PROBES, batch_size=8
        )
        preserved = sum(
            max(range(3), key=logits.__getitem__) == 0
            for logits in preservation_logits
        )
        if preserved < 6:
            raise ValueError(
                f"domain model lost contradiction capability: {preserved}/8 probes passed"
            )
        _release_model(model, tokenizer)
        model = None
        tokenizer = None
        _validate_saved_domain_model(base_model, staging_dir)
        tree_sha256 = source_tree_sha256(staging_dir)
        base_binding = state["base_model"]
        manifest = {
            "model_version": DOMAIN_MODEL_VERSION,
            "repository": "ace/option2-domain-adapted-english-nli",
            "revision": tree_sha256,
            "tree_sha256": tree_sha256,
            "base_repository": base_binding["repository"],
            "base_revision": base_binding["revision"],
            "base_tree_sha256": base_binding["tree_sha256"],
            "dataset": state["dataset"],
            "configuration": state["configuration"],
            "labeling_notice": (
                "Option 2 labels are weak public-evidence supervision; inverse-frequency loss weighting "
                "balances observed labels, while the frozen classifier and preservation probes protect "
                "the contradiction class absent from this sampled training split."
            ),
        }
        (staging_dir / "ace-artifact-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        staging_dir.replace(output_dir)
        manifest_path = output_dir / "ace-artifact-manifest.json"
        state["status"] = "completed"
        state["completed_at"] = _timestamp()
        state["updated_at"] = _timestamp()
        state["output_tree_sha256"] = tree_sha256
        state["output_manifest_sha256"] = file_sha256(manifest_path)
        _atomic_json(state_path, state)
        return manifest
    except Exception as exc:
        state = json.loads(state_path.read_text())
        state["status"] = "failed"
        state["failed_at"] = _timestamp()
        state["updated_at"] = _timestamp()
        state["error"] = f"{type(exc).__name__}: {exc}"[:500]
        _atomic_json(state_path, state)
        raise
    finally:
        if model is not None:
            _release_model(model, tokenizer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=5e-6)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--no-gradient-checkpointing", action="store_true")
    parser.add_argument("--stage", choices=["prepare", "train"], default="train")
    args = parser.parse_args()
    function = prepare_domain_training if args.stage == "prepare" else train_domain
    result = function(
        args.dataset,
        args.base_model,
        args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        gradient_checkpointing=not args.no_gradient_checkpointing,
        freeze_classifier=True,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
