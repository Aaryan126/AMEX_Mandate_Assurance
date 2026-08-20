from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import random
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ml.semantic.checkpoints import (
    file_sha256,
    load_oof_logits,
    mark_final_completed,
    mark_final_failed,
    mark_final_running,
    mark_fold_completed,
    mark_fold_failed,
    mark_fold_running,
    prepare_training_state,
    validate_training_state,
)
from ml.semantic.dataset import ID_LABELS, NliTrainingRow, fold_for_group, load_nli_rows

MODEL_VERSION = "english-nli-v3"
ADAMW_EPSILON = 1e-6
ADAMW_FOREACH = False
TRAINING_DTYPE = "float32"
CANONICAL_LABEL_NAMES = [ID_LABELS[index] for index in range(3)]


def tree_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in directory.rglob("*") if value.is_file()):
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def select_temperature(logits: list[list[float]], labels: list[int]) -> float:
    if not logits or len(logits) != len(labels):
        raise ValueError(
            "temperature selection requires aligned calibration logits and labels"
        )
    candidates = [0.5 + index * 0.05 for index in range(51)]

    def loss(temperature: float) -> float:
        total = 0.0
        for row, label in zip(logits, labels, strict=True):
            scaled = [value / temperature for value in row]
            offset = max(scaled)
            denominator = sum(math.exp(value - offset) for value in scaled)
            probability = math.exp(scaled[label] - offset) / denominator
            total -= math.log(max(probability, 1e-12))
        return total / len(labels)

    return min(candidates, key=loss)


def _dependencies():
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Install services/api[semantic] on the GPU training host"
        ) from exc
    return torch, DataLoader, Dataset, AutoModelForSequenceClassification, AutoTokenizer


def _sample_is_finite(torch: Any, tensor: Any, maximum_values: int = 4096) -> bool:
    """Check a bounded, evenly spaced tensor sample without a model-sized allocation."""
    flattened = tensor.detach().reshape(-1)
    stride = max(1, math.ceil(flattened.numel() / maximum_values))
    return bool(torch.isfinite(flattened[::stride]).all().item())


def canonical_label_indices(id2label: dict[Any, Any]) -> list[int]:
    native = {str(label).lower(): int(index) for index, label in id2label.items()}
    missing = [label for label in CANONICAL_LABEL_NAMES if label.lower() not in native]
    if missing:
        raise ValueError(f"base model is missing canonical NLI labels: {missing}")
    return [native[label.lower()] for label in CANONICAL_LABEL_NAMES]


def canonicalize_classifier(model: Any) -> list[int]:
    torch, _, _, _, _ = _dependencies()
    order = canonical_label_indices(model.config.id2label)
    classifier = getattr(model, "classifier", None)
    if classifier is None or not hasattr(classifier, "weight"):
        raise ValueError("semantic model does not expose a reorderable classifier")
    with torch.no_grad():
        classifier.weight.copy_(classifier.weight[order].clone())
        if classifier.bias is not None:
            classifier.bias.copy_(classifier.bias[order].clone())
    model.config.id2label = dict(ID_LABELS)
    model.config.label2id = {value: key for key, value in ID_LABELS.items()}
    return order


def _train_model(
    training: list[NliTrainingRow],
    validation: list[NliTrainingRow],
    base_model: Path,
    output_dir: Path | None,
    *,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    gradient_accumulation_steps: int,
    gradient_checkpointing: bool,
    freeze_classifier: bool = False,
    require_accelerator: bool = False,
    class_weights: list[float] | None = None,
) -> tuple[Any, Any]:
    torch, DataLoader, Dataset, AutoModel, AutoTokenizer = _dependencies()
    random.seed(2026)
    torch.manual_seed(2026)
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    model = AutoModel.from_pretrained(base_model, local_files_only=True)
    if model.config.num_labels != 3:
        raise ValueError("semantic base model must expose exactly three NLI labels")
    canonicalize_classifier(model)
    model.float()
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
    if freeze_classifier:
        classifier = getattr(model, "classifier", None)
        if classifier is None:
            raise ValueError("semantic model does not expose a classifier head to freeze")
        for parameter in classifier.parameters():
            parameter.requires_grad = False

    class PairDataset(Dataset):
        def __init__(self, values: list[NliTrainingRow]):
            self.values = values

        def __len__(self) -> int:
            return len(self.values)

        def __getitem__(self, index: int):
            return self.values[index]

    def collate(values: list[NliTrainingRow]):
        encoded = tokenizer(
            [value.premise for value in values],
            [value.hypothesis for value in values],
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt",
        )
        return {
            **encoded,
            "labels": torch.tensor([value.label for value in values]),
        }

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    if require_accelerator and device.type == "cpu":
        raise RuntimeError("accelerated training was required but neither MPS nor CUDA is available")
    model.to(device)
    weight_tensor = None
    if class_weights is not None:
        if len(class_weights) != 3 or not any(value > 0 for value in class_weights):
            raise ValueError("semantic class weights must contain three values with a positive weight")
        if any(not math.isfinite(value) or value < 0 for value in class_weights):
            raise ValueError("semantic class weights must be finite and non-negative")
        weight_tensor = torch.tensor(class_weights, dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=learning_rate,
        eps=ADAMW_EPSILON,
        foreach=ADAMW_FOREACH,
    )
    if gradient_accumulation_steps < 1:
        raise ValueError("gradient accumulation steps must be positive")
    loader = DataLoader(
        PairDataset(training),
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
    )
    started_at = time.monotonic()
    print(
        json.dumps(
            {
                "event": "training_started",
                "device": str(device),
                "epochs": epochs,
                "rows": len(training),
                "steps_per_epoch": len(loader),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(loader, 1):
            batch = {key: value.to(device) for key, value in batch.items()}
            if weight_tensor is None:
                loss = model(**batch).loss
            else:
                labels = batch.pop("labels")
                logits = model(**batch).logits
                loss = torch.nn.functional.cross_entropy(
                    logits, labels, weight=weight_tensor
                )
            loss = loss / gradient_accumulation_steps
            if not bool(torch.isfinite(loss).item()):
                raise FloatingPointError(
                    f"non-finite training loss at epoch {epoch + 1}, step {step}"
                )
            loss.backward()
            if step % gradient_accumulation_steps == 0 or step == len(loader):
                if epoch == 0 and step <= gradient_accumulation_steps:
                    for name, parameter in model.named_parameters():
                        if parameter.grad is not None and not _sample_is_finite(
                            torch, parameter.grad
                        ):
                            raise FloatingPointError(
                                f"non-finite gradient before first optimizer update: {name}"
                            )
                optimizer.step()
                if epoch == 0 and step <= gradient_accumulation_steps:
                    for name, parameter in model.named_parameters():
                        if not _sample_is_finite(torch, parameter):
                            raise FloatingPointError(
                                f"non-finite parameter after first optimizer update: {name}"
                            )
                optimizer.zero_grad(set_to_none=True)
            if step == 1 or step % 25 == 0 or step == len(loader):
                elapsed = max(time.monotonic() - started_at, 1e-9)
                completed_steps = epoch * len(loader) + step
                total_steps = epochs * len(loader)
                print(
                    json.dumps(
                        {
                            "event": "training_progress",
                            "epoch": epoch + 1,
                            "step": step,
                            "steps_per_epoch": len(loader),
                            "completed_steps": completed_steps,
                            "total_steps": total_steps,
                            "steps_per_second": round(completed_steps / elapsed, 4),
                            "elapsed_seconds": round(elapsed, 1),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
    return model, tokenizer


def _predict(
    model: Any,
    tokenizer: Any,
    rows: list[NliTrainingRow],
    *,
    batch_size: int,
) -> list[list[float]]:
    torch, _, _, _, _ = _dependencies()
    device = next(model.parameters()).device
    output: list[list[float]] = []
    model.eval()
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        encoded = tokenizer(
            [value.premise for value in batch],
            [value.hypothesis for value in batch],
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        with torch.inference_mode():
            logits = model(
                **{key: value.to(device) for key, value in encoded.items()}
            ).logits
        if not bool(torch.isfinite(logits).all().item()):
            raise FloatingPointError("semantic prediction produced non-finite logits")
        output.extend(logits.cpu().tolist())
    return output


def validate_prediction_quality(
    logits: list[list[float]], *, context: str
) -> dict[str, Any]:
    if len(logits) < 2 or any(len(row) != 3 for row in logits):
        raise ValueError(f"{context} quality gate requires at least two 3-class logits")
    if not all(math.isfinite(value) for row in logits for value in row):
        raise FloatingPointError(f"{context} contains non-finite logits")
    predicted_labels = {max(range(3), key=row.__getitem__) for row in logits}
    class_ranges = [
        max(row[index] for row in logits) - min(row[index] for row in logits)
        for index in range(3)
    ]
    if len(predicted_labels) < 2 or max(class_ranges) < 1e-3:
        raise ValueError(
            f"{context} collapsed: predicted_labels={sorted(predicted_labels)}, "
            f"maximum_logit_range={max(class_ranges):.6g}"
        )
    return {
        "predicted_labels": sorted(predicted_labels),
        "maximum_logit_range": max(class_ranges),
    }


def _probabilities(logits: list[float], temperature: float) -> list[float]:
    scaled = [value / temperature for value in logits]
    offset = max(scaled)
    values = [math.exp(value - offset) for value in scaled]
    return [value / sum(values) for value in values]


def training_configuration(
    *,
    folds: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    gradient_accumulation_steps: int,
    gradient_checkpointing: bool,
    prediction_batch_size: int,
) -> dict[str, Any]:
    if folds < 2:
        raise ValueError("semantic cross-fitting requires at least two folds")
    if epochs < 1 or batch_size < 1 or prediction_batch_size < 1:
        raise ValueError("epochs and batch sizes must be positive")
    if learning_rate <= 0 or gradient_accumulation_steps < 1:
        raise ValueError("learning rate and gradient accumulation must be positive")
    return {
        "folds": folds,
        "epochs": epochs,
        "micro_batch_size": batch_size,
        "learning_rate": learning_rate,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "effective_batch_size": batch_size * gradient_accumulation_steps,
        "gradient_checkpointing": gradient_checkpointing,
        "optimizer": {
            "name": "AdamW",
            "epsilon": ADAMW_EPSILON,
            "foreach": ADAMW_FOREACH,
        },
        "training_dtype": TRAINING_DTYPE,
        "canonical_label_order": CANONICAL_LABEL_NAMES,
        "class_weights": None,
        "prediction_batch_size": prediction_batch_size,
        "random_seed": 2026,
        "model_version": MODEL_VERSION,
    }


def _prepare_context(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    *,
    folds: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    gradient_accumulation_steps: int,
    gradient_checkpointing: bool,
    prediction_batch_size: int,
) -> tuple[list[NliTrainingRow], Path, dict[str, Any], dict[str, Any]]:
    rows = load_nli_rows(dataset_path)
    configuration = training_configuration(
        folds=folds,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        prediction_batch_size=prediction_batch_size,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "training-state.json"
    state = prepare_training_state(
        state_path,
        dataset_path,
        base_model,
        output_dir,
        rows,
        folds=folds,
        configuration=configuration,
    )
    return rows, state_path, state, configuration


def prepare_training_run(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    *,
    folds: int = 5,
    epochs: int = 2,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    gradient_accumulation_steps: int = 1,
    gradient_checkpointing: bool = False,
    prediction_batch_size: int = 32,
) -> dict[str, Any]:
    _, state_path, state, _ = _prepare_context(
        dataset_path,
        base_model,
        output_dir,
        folds=folds,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        prediction_batch_size=prediction_batch_size,
    )
    return {
        "state_path": str(state_path),
        "state_sha256": file_sha256(state_path),
        "status": state["status"],
        "folds": {
            key: value["status"] for key, value in state["folds"].items()
        },
    }


def _write_fold_predictions(
    path: Path,
    fold: int,
    rows: list[NliTrainingRow],
    logits: list[list[float]],
) -> None:
    if len(rows) != len(logits):
        raise ValueError("fold predictions do not align with holdout rows")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as output:
        for row, values in zip(rows, logits, strict=True):
            output.write(
                json.dumps(
                    {
                        "example_id": row.example_id,
                        "constraint_id": row.constraint_id,
                        "group_id": row.group_id,
                        "fold": fold,
                        "logits": values,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    temporary.replace(path)


def _release_model(model: Any, tokenizer: Any) -> None:
    del model, tokenizer
    gc.collect()
    torch, _, _, _, _ = _dependencies()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_semantic_fold(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    fold: int,
    *,
    folds: int = 5,
    epochs: int = 2,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    gradient_accumulation_steps: int = 1,
    gradient_checkpointing: bool = False,
    prediction_batch_size: int = 32,
) -> dict[str, Any]:
    rows, state_path, state, _ = _prepare_context(
        dataset_path,
        base_model,
        output_dir,
        folds=folds,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        prediction_batch_size=prediction_batch_size,
    )
    if not 0 <= fold < folds:
        raise ValueError(f"fold index must be between 0 and {folds - 1}")
    if state["folds"][str(fold)]["status"] == "completed":
        return {
            "fold": fold,
            "status": "completed",
            "skipped": True,
            "state_path": str(state_path),
            "state_sha256": file_sha256(state_path),
        }
    training = [
        row
        for row in rows
        if row.split == "train" and fold_for_group(row.group_id, folds) != fold
    ]
    holdout = [
        row
        for row in rows
        if row.split == "train" and fold_for_group(row.group_id, folds) == fold
    ]
    mark_fold_running(state_path, fold)
    model = None
    tokenizer = None
    try:
        model, tokenizer = _train_model(
            training,
            holdout,
            base_model,
            None,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_checkpointing=gradient_checkpointing,
        )
        logits = _predict(
            model,
            tokenizer,
            holdout,
            batch_size=prediction_batch_size,
        )
        validate_prediction_quality(logits, context=f"semantic fold {fold}")
        prediction_path = Path(
            json.loads(state_path.read_text())["folds"][str(fold)][
                "predictions_path"
            ]
        )
        _write_fold_predictions(prediction_path, fold, holdout, logits)
        state = mark_fold_completed(state_path, fold)
    except Exception as exc:
        mark_fold_failed(state_path, fold, exc)
        raise
    finally:
        if model is not None:
            _release_model(model, tokenizer)
    value = state["folds"][str(fold)]
    return {
        "fold": fold,
        "status": value["status"],
        "skipped": False,
        "attempts": value["attempts"],
        "holdout_rows": value["holdout_rows"],
        "predictions_path": value["predictions_path"],
        "predictions_sha256": value["predictions_sha256"],
        "state_path": str(state_path),
        "state_sha256": file_sha256(state_path),
    }


def train(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    *,
    folds: int = 5,
    epochs: int = 2,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    gradient_accumulation_steps: int = 1,
    gradient_checkpointing: bool = False,
    prediction_batch_size: int = 32,
) -> dict[str, Any]:
    rows, state_path, _, configuration = _prepare_context(
        dataset_path,
        base_model,
        output_dir,
        folds=folds,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        prediction_batch_size=prediction_batch_size,
    )
    training = [value for value in rows if value.split == "train"]
    validation = [value for value in rows if value.split == "validation"]
    calibration = [value for value in rows if value.split == "calibration"]
    non_training = [value for value in rows if value.split != "train"]
    for fold in range(folds):
        run_semantic_fold(
            dataset_path,
            base_model,
            output_dir,
            fold,
            folds=folds,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_checkpointing=gradient_checkpointing,
            prediction_batch_size=prediction_batch_size,
        )
    state = validate_training_state(
        state_path,
        dataset_path,
        base_model,
        output_dir,
        rows,
        folds=folds,
        configuration=configuration,
    )
    if state["final"]["status"] == "completed":
        return json.loads(Path(state["final"]["manifest"]["path"]).read_text())
    oof_logits = load_oof_logits(state)
    mark_final_running(state_path)
    model = None
    tokenizer = None
    try:
        model, tokenizer = _train_model(
            training,
            validation,
            base_model,
            output_dir / "model",
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_checkpointing=gradient_checkpointing,
        )
        heldout_logits = _predict(
            model,
            tokenizer,
            non_training,
            batch_size=prediction_batch_size,
        )
        by_key = {
            (value.example_id, value.constraint_id): logits
            for value, logits in zip(non_training, heldout_logits, strict=True)
        }
        calibration_logits = [
            by_key[(value.example_id, value.constraint_id)] for value in calibration
        ]
        temperature = select_temperature(
            calibration_logits, [value.label for value in calibration]
        )

        predictions_path = output_dir / "semantic-predictions.jsonl"
        temporary_predictions = predictions_path.with_suffix(".jsonl.tmp")
        with temporary_predictions.open("w") as output:
            for value in rows:
                logits = (oof_logits if value.split == "train" else by_key)[
                    (value.example_id, value.constraint_id)
                ]
                probabilities = _probabilities(logits, temperature)
                output.write(
                    json.dumps(
                        {
                            **asdict(value),
                            "contradiction": probabilities[0],
                            "entailment": probabilities[2],
                            "neutral": probabilities[1],
                            "prediction_origin": "cross_fit"
                            if value.split == "train"
                            else "held_out",
                            "model_version": MODEL_VERSION,
                        }
                    )
                    + "\n"
                )
        temporary_predictions.replace(predictions_path)
        base_binding = state["base_model"]
        manifest = {
            "model_version": MODEL_VERSION,
            "base_model": str(base_model),
            "base_repository": base_binding["repository"],
            "base_revision": base_binding["revision"],
            "base_tree_sha256": base_binding["tree_sha256"],
            "model_tree_sha256": tree_sha256(output_dir / "model"),
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "predictions_sha256": hashlib.sha256(
                predictions_path.read_bytes()
            ).hexdigest(),
            "rows": len(rows),
            "training_rows": len(training),
            "validation_rows": len(validation),
            "calibration_rows": len(calibration),
            "cross_fit_folds": folds,
            "micro_batch_size": batch_size,
            "gradient_accumulation_steps": gradient_accumulation_steps,
            "effective_batch_size": batch_size * gradient_accumulation_steps,
            "gradient_checkpointing": gradient_checkpointing,
            "prediction_batch_size": prediction_batch_size,
            "temperature": temperature,
            "random_seed": 2026,
            "training_state": str(state_path),
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        mark_final_completed(state_path, manifest_path, predictions_path)
        return manifest
    except Exception as exc:
        mark_final_failed(state_path, exc)
        raise
    finally:
        if model is not None:
            _release_model(model, tokenizer)


def finalize_semantic_run(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    **configuration: Any,
) -> dict[str, Any]:
    prepared = prepare_training_run(
        dataset_path, base_model, output_dir, **configuration
    )
    if set(prepared["folds"].values()) != {"completed"}:
        raise ValueError("all semantic fold checkpoints must complete before final training")
    return train(dataset_path, base_model, output_dir, **configuration)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/models/semantic-v2")
    )
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--prediction-batch-size", type=int, default=32)
    parser.add_argument(
        "--stage", choices=["all", "prepare", "fold", "finalize"], default="all"
    )
    parser.add_argument("--fold-index", type=int)
    args = parser.parse_args()
    configuration = {
        "folds": args.folds,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "gradient_checkpointing": args.gradient_checkpointing,
        "prediction_batch_size": args.prediction_batch_size,
    }
    if args.stage == "prepare":
        result = prepare_training_run(
            args.dataset, args.base_model, args.output, **configuration
        )
    elif args.stage == "fold":
        if args.fold_index is None:
            parser.error("--fold-index is required with --stage fold")
        result = run_semantic_fold(
            args.dataset,
            args.base_model,
            args.output,
            args.fold_index,
            **configuration,
        )
    elif args.stage == "finalize":
        result = finalize_semantic_run(
            args.dataset, args.base_model, args.output, **configuration
        )
    else:
        result = train(args.dataset, args.base_model, args.output, **configuration)
    print(
        json.dumps(result, indent=2)
    )


if __name__ == "__main__":
    main()
