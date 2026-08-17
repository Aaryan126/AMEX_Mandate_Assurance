from __future__ import annotations

from ml.data.generate_dataset import generate_rows
from ml.features.schema import FEATURE_NAMES, compute_features, feature_vector


def test_feature_order_is_versioned_and_stable() -> None:
    row = generate_rows()[0]
    features = compute_features(row)
    assert list(features) == FEATURE_NAMES
    assert feature_vector(row) == [features[name] for name in FEATURE_NAMES]


def test_missing_history_is_not_an_adverse_feature() -> None:
    row = generate_rows()[0]
    features = compute_features(row)
    assert "merchant_history" not in features
    assert features["missing_evidence_count"] == 0
