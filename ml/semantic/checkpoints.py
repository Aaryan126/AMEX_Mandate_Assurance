from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.semantic.dataset import NliTrainingRow, fold_for_group

STATE_SCHEMA_VERSION = 1


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_sha256(directory: Path) -> str:
    """Hash a bootstrapped model tree without its self-referential manifest."""
    digest = hashlib.sha256()
    for path in sorted(value for value in directory.rglob("*") if value.is_file()):
        relative = path.relative_to(directory)
        if relative.name == "ace-artifact-manifest.json":
            continue
        digest.update(str(relative).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def row_key(row: NliTrainingRow) -> str:
    return f"{row.example_id}\x1f{row.constraint_id}"


def keys_sha256(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()


def base_model_binding(base_model: Path) -> dict[str, Any]:
    manifest_path = base_model / "ace-artifact-manifest.json"
    if not manifest_path.exists():
        raise ValueError("base model must be created by the immutable semantic bootstrap")
    manifest = json.loads(manifest_path.read_text())
    if len(str(manifest.get("revision", ""))) < 20:
        raise ValueError("base model manifest does not contain an immutable revision")
    actual_tree_sha256 = source_tree_sha256(base_model)
    if manifest.get("tree_sha256") != actual_tree_sha256:
        raise ValueError("base model tree does not match its immutable manifest")
    return {
        "path": str(base_model),
        "manifest_sha256": file_sha256(manifest_path),
        "repository": manifest["repository"],
        "revision": manifest["revision"],
        "tree_sha256": actual_tree_sha256,
    }


def _expected_state(
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    rows: list[NliTrainingRow],
    *,
    folds: int,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    training = [row for row in rows if row.split == "train"]
    split_counts = dict(sorted(Counter(row.split for row in rows).items()))
    if not training or not split_counts.get("validation") or not split_counts.get(
        "calibration"
    ):
        raise ValueError(
            "semantic training requires labeled train, validation, and calibration rows"
        )
    all_keys = [row_key(row) for row in rows]
    if len(all_keys) != len(set(all_keys)):
        raise ValueError("semantic rows contain duplicate example/constraint keys")
    assignments = {
        row_key(row): fold_for_group(row.group_id, folds) for row in training
    }
    fold_states: dict[str, Any] = {}
    for fold in range(folds):
        holdout = [row for row in training if assignments[row_key(row)] == fold]
        fold_training = [row for row in training if assignments[row_key(row)] != fold]
        if not holdout or not fold_training:
            raise ValueError(f"semantic fold {fold} is empty; reduce --folds")
        holdout_keys = [row_key(row) for row in holdout]
        holdout_groups = sorted({row.group_id for row in holdout})
        training_groups = {row.group_id for row in fold_training}
        if training_groups.intersection(holdout_groups):
            raise ValueError(f"semantic fold {fold} contains group leakage")
        fold_states[str(fold)] = {
            "status": "pending",
            "attempts": 0,
            "training_rows": len(fold_training),
            "holdout_rows": len(holdout),
            "holdout_groups": len(holdout_groups),
            "holdout_keys_sha256": keys_sha256(holdout_keys),
            "predictions_path": str(
                output_dir / "folds" / f"fold-{fold}.predictions.jsonl"
            ),
        }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "status": "prepared",
        "dataset": {
            "path": str(dataset_path),
            "sha256": file_sha256(dataset_path),
            "semantic_rows": len(rows),
            "split_counts": split_counts,
            "keys_sha256": keys_sha256(all_keys),
        },
        "base_model": base_model_binding(base_model),
        "output_dir": str(output_dir),
        "configuration": configuration,
        "fold_assignment_sha256": hashlib.sha256(
            "\n".join(f"{key}:{assignments[key]}" for key in sorted(assignments)).encode()
        ).hexdigest(),
        "folds": fold_states,
        "final": {"status": "pending", "attempts": 0},
    }


def _validate_fold_predictions(
    path: Path,
    expected_fold: int,
    expected_rows: int,
    expected_keys_sha256: str,
) -> None:
    keys: list[str] = []
    predicted_labels: set[int] = set()
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if value.get("fold") != expected_fold:
                raise ValueError(f"fold checkpoint has wrong fold at line {line_number}")
            logits = value.get("logits")
            if (
                not isinstance(logits, list)
                or len(logits) != 3
                or not all(isinstance(item, (int, float)) for item in logits)
                or not all(math.isfinite(item) for item in logits)
            ):
                raise ValueError(f"fold checkpoint has invalid logits at line {line_number}")
            predicted_labels.add(max(range(3), key=logits.__getitem__))
            keys.append(f"{value['example_id']}\x1f{value['constraint_id']}")
    if len(keys) != expected_rows or len(keys) != len(set(keys)):
        raise ValueError("fold checkpoint row count or uniqueness mismatch")
    if keys_sha256(keys) != expected_keys_sha256:
        raise ValueError("fold checkpoint does not cover the expected holdout keys")
    if len(predicted_labels) < 2:
        raise ValueError("fold checkpoint failed quality gate: predictions collapsed to one class")


def validate_training_state(
    state_path: Path,
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    rows: list[NliTrainingRow],
    *,
    folds: int,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    expected = _expected_state(
        dataset_path,
        base_model,
        output_dir,
        rows,
        folds=folds,
        configuration=configuration,
    )
    for key in (
        "schema_version",
        "dataset",
        "base_model",
        "output_dir",
        "configuration",
        "fold_assignment_sha256",
    ):
        if state.get(key) != expected[key]:
            raise ValueError(f"semantic training state binding mismatch: {key}")
    if set(state.get("folds", {})) != set(expected["folds"]):
        raise ValueError("semantic training state fold coverage mismatch")
    allowed_statuses = {"pending", "running", "failed", "completed"}
    for fold_key, expected_fold in expected["folds"].items():
        actual = state["folds"][fold_key]
        for key in (
            "training_rows",
            "holdout_rows",
            "holdout_groups",
            "holdout_keys_sha256",
            "predictions_path",
        ):
            if actual.get(key) != expected_fold[key]:
                raise ValueError(f"semantic fold {fold_key} binding mismatch: {key}")
        if actual.get("status") not in allowed_statuses:
            raise ValueError(f"semantic fold {fold_key} has an invalid status")
        if actual["status"] == "completed":
            prediction_path = Path(actual["predictions_path"])
            if not prediction_path.exists():
                raise ValueError(f"semantic fold {fold_key} checkpoint is missing")
            if actual.get("predictions_sha256") != file_sha256(prediction_path):
                raise ValueError(f"semantic fold {fold_key} checkpoint checksum mismatch")
            _validate_fold_predictions(
                prediction_path,
                int(fold_key),
                actual["holdout_rows"],
                actual["holdout_keys_sha256"],
            )
    final = state.get("final", {})
    if final.get("status") not in allowed_statuses:
        raise ValueError("semantic final stage has an invalid status")
    if final["status"] == "completed":
        for name in ("manifest", "predictions"):
            artifact = final.get(name, {})
            artifact_path = Path(str(artifact.get("path", "")))
            if not artifact_path.is_file():
                raise ValueError(f"semantic final {name} artifact is missing")
            if artifact.get("sha256") != file_sha256(artifact_path):
                raise ValueError(f"semantic final {name} checksum mismatch")
    return state


def prepare_training_state(
    state_path: Path,
    dataset_path: Path,
    base_model: Path,
    output_dir: Path,
    rows: list[NliTrainingRow],
    *,
    folds: int,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    if state_path.exists():
        return validate_training_state(
            state_path,
            dataset_path,
            base_model,
            output_dir,
            rows,
            folds=folds,
            configuration=configuration,
        )
    state = _expected_state(
        dataset_path,
        base_model,
        output_dir,
        rows,
        folds=folds,
        configuration=configuration,
    )
    now = _timestamp()
    state["created_at"] = now
    state["updated_at"] = now
    _atomic_json(state_path, state)
    return state


def mark_fold_running(state_path: Path, fold: int) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    value = state["folds"][str(fold)]
    if value["status"] == "completed":
        return state
    value["status"] = "running"
    value["attempts"] = int(value.get("attempts", 0)) + 1
    value["started_at"] = _timestamp()
    value.pop("error", None)
    state["status"] = "running"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state


def mark_fold_failed(state_path: Path, fold: int, error: Exception) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    value = state["folds"][str(fold)]
    value["status"] = "failed"
    value["failed_at"] = _timestamp()
    value["error"] = f"{type(error).__name__}: {error}"[:500]
    state["status"] = "failed"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state


def mark_fold_completed(state_path: Path, fold: int) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    value = state["folds"][str(fold)]
    prediction_path = Path(value["predictions_path"])
    _validate_fold_predictions(
        prediction_path,
        fold,
        value["holdout_rows"],
        value["holdout_keys_sha256"],
    )
    value["status"] = "completed"
    value["completed_at"] = _timestamp()
    value["predictions_sha256"] = file_sha256(prediction_path)
    value.pop("error", None)
    statuses = {item["status"] for item in state["folds"].values()}
    state["status"] = "ready_to_finalize" if statuses == {"completed"} else "running"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state


def load_oof_logits(state: dict[str, Any]) -> dict[tuple[str, str], list[float]]:
    output: dict[tuple[str, str], list[float]] = {}
    for fold_key, value in state["folds"].items():
        if value["status"] != "completed":
            raise ValueError(f"semantic fold {fold_key} is not complete")
        path = Path(value["predictions_path"])
        if value["predictions_sha256"] != file_sha256(path):
            raise ValueError(f"semantic fold {fold_key} checkpoint checksum mismatch")
        with path.open() as source:
            for line in source:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = (str(row["example_id"]), str(row["constraint_id"]))
                if key in output:
                    raise ValueError("semantic fold checkpoints overlap")
                output[key] = [float(item) for item in row["logits"]]
    return output


def mark_final_running(state_path: Path) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    if {value["status"] for value in state["folds"].values()} != {"completed"}:
        raise ValueError("all semantic folds must complete before final training")
    final = state["final"]
    if final["status"] == "completed":
        return state
    final["status"] = "running"
    final["attempts"] = int(final.get("attempts", 0)) + 1
    final["started_at"] = _timestamp()
    final.pop("error", None)
    state["status"] = "finalizing"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state


def mark_final_failed(state_path: Path, error: Exception) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    final = state["final"]
    final["status"] = "failed"
    final["failed_at"] = _timestamp()
    final["error"] = f"{type(error).__name__}: {error}"[:500]
    state["status"] = "failed"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state


def mark_final_completed(
    state_path: Path,
    manifest_path: Path,
    predictions_path: Path,
) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    final = state["final"]
    final["status"] = "completed"
    final["completed_at"] = _timestamp()
    final["manifest"] = {
        "path": str(manifest_path),
        "sha256": file_sha256(manifest_path),
    }
    final["predictions"] = {
        "path": str(predictions_path),
        "sha256": file_sha256(predictions_path),
    }
    final.pop("error", None)
    state["status"] = "completed"
    state["updated_at"] = _timestamp()
    _atomic_json(state_path, state)
    return state
