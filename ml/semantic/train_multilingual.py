from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ml.semantic.dataset import ID_LABELS, NliTrainingRow, fold_for_group, load_nli_rows

MODEL_VERSION = "english-nli-v3"


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
) -> tuple[Any, Any]:
    torch, DataLoader, Dataset, AutoModel, AutoTokenizer = _dependencies()
    random.seed(2026)
    torch.manual_seed(2026)
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    model = AutoModel.from_pretrained(
        base_model,
        local_files_only=True,
        num_labels=3,
        id2label=ID_LABELS,
        label2id={value: key for key, value in ID_LABELS.items()},
    )
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

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
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    if gradient_accumulation_steps < 1:
        raise ValueError("gradient accumulation steps must be positive")
    loader = DataLoader(
        PairDataset(training),
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
    )
    for _ in range(epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(loader, 1):
            batch = {key: value.to(device) for key, value in batch.items()}
            loss = model(**batch).loss / gradient_accumulation_steps
            loss.backward()
            if step % gradient_accumulation_steps == 0 or step == len(loader):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
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
        output.extend(logits.cpu().tolist())
    return output


def _probabilities(logits: list[float], temperature: float) -> list[float]:
    scaled = [value / temperature for value in logits]
    offset = max(scaled)
    values = [math.exp(value - offset) for value in scaled]
    return [value / sum(values) for value in values]


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
    base_manifest_path = base_model / "ace-artifact-manifest.json"
    if not base_manifest_path.exists():
        raise ValueError(
            "base model must be created by the immutable semantic bootstrap"
        )
    base_manifest = json.loads(base_manifest_path.read_text())
    if len(str(base_manifest.get("revision", ""))) < 20:
        raise ValueError("base model manifest does not contain an immutable revision")
    rows = load_nli_rows(dataset_path)
    training = [value for value in rows if value.split == "train"]
    validation = [value for value in rows if value.split == "validation"]
    calibration = [value for value in rows if value.split == "calibration"]
    non_training = [value for value in rows if value.split != "train"]
    if not training or not validation or not calibration:
        raise ValueError(
            "semantic training requires labeled train, validation, and calibration rows"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    oof_logits: dict[tuple[str, str], list[float]] = {}
    for fold in range(folds):
        fold_training = [
            value for value in training if fold_for_group(value.group_id, folds) != fold
        ]
        fold_holdout = [
            value for value in training if fold_for_group(value.group_id, folds) == fold
        ]
        if not fold_training or not fold_holdout:
            raise ValueError(f"semantic fold {fold} is empty; reduce --folds")
        model, tokenizer = _train_model(
            fold_training,
            fold_holdout,
            base_model,
            None,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_checkpointing=gradient_checkpointing,
        )
        for value, logits in zip(
            fold_holdout,
            _predict(
                model,
                tokenizer,
                fold_holdout,
                batch_size=prediction_batch_size,
            ),
            strict=True,
        ):
            oof_logits[(value.example_id, value.constraint_id)] = logits
        del model, tokenizer
        gc.collect()
        torch, _, _, _, _ = _dependencies()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
    with predictions_path.open("w") as output:
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
    manifest = {
        "model_version": MODEL_VERSION,
        "base_model": str(base_model),
        "base_repository": base_manifest["repository"],
        "base_revision": base_manifest["revision"],
        "base_tree_sha256": base_manifest["tree_sha256"],
        "model_tree_sha256": tree_sha256(output_dir / "model"),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(predictions_path.read_bytes()).hexdigest(),
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
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


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
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--prediction-batch-size", type=int, default=32)
    args = parser.parse_args()
    print(
        json.dumps(
            train(
                args.dataset,
                args.base_model,
                args.output,
                folds=args.folds,
                epochs=args.epochs,
                batch_size=args.batch_size,
                gradient_accumulation_steps=args.gradient_accumulation_steps,
                gradient_checkpointing=args.gradient_checkpointing,
                prediction_batch_size=args.prediction_batch_size,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
