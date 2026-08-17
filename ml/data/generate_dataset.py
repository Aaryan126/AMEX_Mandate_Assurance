from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DATASET_VERSION = "synthetic-v1"


@dataclass(frozen=True)
class SeedMandate:
    seed_id: str
    domain: str
    objective: str
    budget_minor: int
    currency: str
    required_attribute: str
    prohibited_item: str
    merchant_category: str


def seed_mandates() -> list[SeedMandate]:
    domains = {
        "travel": [
            ("Singapore–Tokyo airfare", "refundable", "gift card", "AIRLINE"),
            ("Singapore–Sydney airfare", "economy", "insurance", "AIRLINE"),
            ("Tokyo hotel stay", "free cancellation", "spa package", "HOTEL"),
            ("Hong Kong hotel stay", "breakfast included", "room upgrade", "HOTEL"),
            ("Singapore airport transfer", "private transfer", "sightseeing", "TRANSPORT"),
            ("Tokyo rail pass", "seven day validity", "souvenir", "TRANSPORT"),
            ("Sydney conference flight", "changeable", "lounge pass", "AIRLINE"),
            ("Bangkok team hotel", "twin rooms", "minibar credit", "HOTEL"),
            ("Seoul client flight", "nonstop", "baggage bundle", "AIRLINE"),
            ("Manila airport hotel", "late arrival", "meal package", "HOTEL"),
        ],
        "retail": [
            ("office monitor", "27 inch", "warranty extension", "ELECTRONICS"),
            ("noise-cancelling headset", "wireless", "music subscription", "ELECTRONICS"),
            ("ergonomic chair", "adjustable lumbar", "assembly plan", "FURNITURE"),
            ("recycled notebooks", "A5 size", "gift wrap", "OFFICE_SUPPLIES"),
            ("USB-C docks", "dual display", "support plan", "ELECTRONICS"),
            ("travel adapter", "universal", "insurance", "ELECTRONICS"),
            ("team backpacks", "water resistant", "personalization", "APPAREL"),
            ("coffee machine", "automatic", "coffee subscription", "APPLIANCES"),
            ("document scanner", "duplex", "cloud subscription", "ELECTRONICS"),
            ("standing desks", "height adjustable", "installation", "FURNITURE"),
        ],
        "dining": [
            ("client dinner", "vegetarian options", "wine pairing", "RESTAURANT"),
            ("team lunch", "halal", "gift voucher", "RESTAURANT"),
            ("project breakfast", "gluten-free options", "delivery membership", "RESTAURANT"),
            ("customer catering", "nut-free", "equipment rental", "CATERING"),
            ("workshop refreshments", "individually packed", "decorations", "CATERING"),
            ("board dinner", "private room", "premium spirits", "RESTAURANT"),
            ("team tea", "dairy-free options", "merchandise", "RESTAURANT"),
            ("training lunch", "vegetarian", "service subscription", "CATERING"),
            ("launch catering", "local menu", "entertainment", "CATERING"),
            ("overnight team meal", "24-hour delivery", "membership", "RESTAURANT"),
        ],
        "recurring": [
            ("design software", "monthly billing", "training bundle", "SOFTWARE"),
            ("cloud backup", "data residency Singapore", "consulting", "SOFTWARE"),
            ("team news access", "ten seats", "event ticket", "DIGITAL_CONTENT"),
            ("domain renewal", "one year", "privacy add-on", "DIGITAL_SERVICES"),
            ("accounting software", "monthly cancellation", "payroll add-on", "SOFTWARE"),
            ("video meetings", "twenty seats", "hardware bundle", "SOFTWARE"),
            ("security scanner", "APAC region", "consulting", "SOFTWARE"),
            ("document signing", "annual cap", "template pack", "SOFTWARE"),
            ("translation service", "monthly quota", "rush credits", "DIGITAL_SERVICES"),
            ("stock image access", "commercial license", "asset bundle", "DIGITAL_CONTENT"),
        ],
        "procurement": [
            ("printer paper", "recycled content", "rush shipping", "OFFICE_SUPPLIES"),
            ("safety gloves", "chemical resistant", "training", "INDUSTRIAL_SUPPLIES"),
            ("shipping cartons", "double wall", "design service", "PACKAGING"),
            ("LED lamps", "energy efficient", "installation", "ELECTRICAL"),
            ("lab labels", "freezer safe", "printer rental", "LAB_SUPPLIES"),
            ("cleaning supplies", "low fragrance", "service contract", "JANITORIAL"),
            ("first aid kits", "workplace compliant", "training", "SAFETY"),
            ("network cables", "Cat6", "support plan", "ELECTRONICS"),
            ("warehouse shelving", "load rated", "installation", "INDUSTRIAL_SUPPLIES"),
            ("courier envelopes", "tamper evident", "tracking subscription", "PACKAGING"),
        ],
    }
    seeds: list[SeedMandate] = []
    for domain, entries in domains.items():
        for index, (item, attribute, prohibited, category) in enumerate(entries, start=1):
            budget = 20000 + (index * 7500)
            seed_id = f"seed_{domain}_{index:02d}"
            objective = (
                f"Purchase {item} that is {attribute}, total under SGD {budget / 100:.0f}. "
                f"Do not add {prohibited}."
            )
            seeds.append(
                SeedMandate(
                    seed_id=seed_id,
                    domain=domain,
                    objective=objective,
                    budget_minor=budget,
                    currency="SGD",
                    required_attribute=attribute,
                    prohibited_item=prohibited,
                    merchant_category=category,
                )
            )
    assert len(seeds) == 50
    return seeds


def split_for(seed_id: str) -> str:
    bucket = int(hashlib.sha256(seed_id.encode()).hexdigest()[:8], 16) % 100
    if bucket < 60:
        return "train"
    if bucket < 75:
        return "validation"
    if bucket < 85:
        return "calibration"
    return "golden"


def _row(seed: SeedMandate, family: str, index: int, **updates: Any) -> dict[str, Any]:
    base = {
        "dataset_version": DATASET_VERSION,
        "row_id": f"{seed.seed_id}_{index:02d}_{family}",
        "seed_id": seed.seed_id,
        "split": split_for(seed.seed_id),
        "domain": seed.domain,
        "objective_text": seed.objective,
        "merchant_category": seed.merchant_category,
        "cart_category": seed.merchant_category,
        "currency": seed.currency,
        "cart_currency": seed.currency,
        "budget_minor": seed.budget_minor,
        "cart_amount_minor": round(seed.budget_minor * 0.82),
        "fulfilled_amount_minor": 0,
        "fulfillment_count": 0,
        "max_fulfillments": 2,
        "line_item_count": 1,
        "missing_evidence_count": 0,
        "semantic_contradiction": 0.02,
        "semantic_neutral": 0.03,
        "hard_fail_count": 0,
        "soft_warning_count": 0,
        "attack_family": family,
        "difficulty": "medium",
        "evidence_sufficiency": "sufficient",
        "label": 0,
        "expected_treatment": "APPROVE",
    }
    base.update(updates)
    return base


def generate_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in seed_mandates():
        rows.extend(
            [
                _row(seed, "valid", 1),
                _row(
                    seed,
                    "amount_violation",
                    2,
                    cart_amount_minor=round(seed.budget_minor * 1.12),
                    hard_fail_count=1,
                    label=1,
                    expected_treatment="STEP_UP",
                ),
                _row(
                    seed,
                    "semantic_substitution",
                    3,
                    semantic_contradiction=0.96,
                    label=1,
                    expected_treatment="HOLD",
                ),
                _row(
                    seed,
                    "unrelated_add_on",
                    4,
                    line_item_count=2,
                    hard_fail_count=1,
                    label=1,
                    expected_treatment="HOLD",
                ),
                _row(
                    seed,
                    "missing_evidence",
                    5,
                    missing_evidence_count=1,
                    semantic_contradiction=0.04,
                    semantic_neutral=0.92,
                    soft_warning_count=1,
                    evidence_sufficiency="ambiguous",
                    label=None,
                    expected_treatment="STEP_UP",
                ),
                _row(
                    seed,
                    "cumulative_overspend",
                    6,
                    cart_amount_minor=round(seed.budget_minor * 0.58),
                    fulfilled_amount_minor=round(seed.budget_minor * 0.57),
                    fulfillment_count=1,
                    hard_fail_count=1,
                    label=1,
                    expected_treatment="HOLD",
                ),
            ]
        )
    return rows


def write_dataset(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    dataset_path = output_dir / "mandate-cart-pairs.jsonl"
    dataset_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    seeds = seed_mandates()
    (output_dir / "seed-mandates.json").write_text(
        json.dumps([asdict(seed) for seed in seeds], indent=2, sort_keys=True) + "\n"
    )
    split_manifest = {
        split: sorted(seed.seed_id for seed in seeds if split_for(seed.seed_id) == split)
        for split in ("train", "validation", "calibration", "golden")
    }
    manifest = {
        "dataset_version": DATASET_VERSION,
        "row_count": len(rows),
        "seed_count": len(seeds),
        "ambiguous_row_count": sum(row["label"] is None for row in rows),
        "splits": split_manifest,
        "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ml/data/generated"))
    args = parser.parse_args()
    manifest = write_dataset(args.output)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

