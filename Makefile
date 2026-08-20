.PHONY: install test test-api test-web test-e2e dev docker-up docker-down seed data-esci data-option1 data-option2 data-option2-uci data-option2-db1b data-option2-usaspending data-option2-amazon data-fast-track-option1 data-fast-track-option2 data-validate annotate-api llm-prepare llm-submit-a llm-submit-b llm-fast-track-prepare llm-fast-track-validate llm-fast-track-submit-a llm-fast-track-submit-b llm-fast-track-validate-submissions llm-fast-track-status llm-fast-track-wait llm-fast-track-download llm-fast-track-validate-outputs llm-fast-track-import llm-fast-track-prepare-adjudication llm-fast-track-validate-adjudication llm-fast-track-submit-adjudication llm-fast-track-adjudication-status llm-fast-track-adjudication-wait llm-fast-track-adjudication-download llm-fast-track-validate-adjudication-output llm-fast-track-prepare-adjudication-retry llm-fast-track-submit-adjudication-retry llm-fast-track-adjudication-retry-status llm-fast-track-adjudication-retry-wait llm-fast-track-adjudication-retry-download llm-fast-track-validate-adjudication-retry-output llm-fast-track-merge-adjudication-retry llm-fast-track-import-adjudication llm-fast-track-export-reviewed llm-fast-track-validate-reviewed semantic-domain-fast-track-prepare semantic-domain-fast-track-train semantic-fast-track-prepare semantic-fast-track-fold semantic-fast-track-finalize export-reviews features train-v2 evaluate-v2 promote-v2
.PHONY: semantic-fast-track-complete-predictions features-fast-track train-fast-track-v2 train-fast-track-v3-no-semantic train-fast-track-v3-semantic select-fast-track-v3 replacement-holdout-semantic-inference replacement-holdout-features evaluate-fast-track-v3-replacement diagnose-step24-failure human-audit-prepare human-audit-validate human-audit-status human-audit-report human-audit-api human-audit-assisted-prepare human-audit-assisted-submit human-audit-assisted-status data-option1-v3 data-development-v3
.PHONY: v4-pool-freeze v4-pool-semantic v4-pool-features v4-review-select v4-review-prepare v4-review-validate v4-review-submit v4-review-status v4-review-wait v4-review-download v4-review-validate-outputs v4-review-import v4-adjudication-prepare v4-adjudication-validate v4-adjudication-submit v4-adjudication-status v4-adjudication-wait v4-adjudication-download v4-adjudication-validate-output v4-adjudication-import v4-review-export v4-data-build
.PHONY: v4-dataset-semantic v4-features-v3 v4-train-stage-a v4-evaluate-stage-a
.PHONY: stage-b-pool-freeze stage-b-review-select stage-b-review-prepare stage-b-review-validate stage-b-review-submit stage-b-review-status stage-b-review-wait stage-b-review-download stage-b-review-validate-outputs stage-b-review-import stage-b-adjudication-prepare stage-b-adjudication-validate stage-b-adjudication-submit stage-b-adjudication-status stage-b-adjudication-wait stage-b-adjudication-download stage-b-adjudication-validate-output stage-b-adjudication-import stage-b-review-export stage-b-semantic-corpus stage-b-semantic-base stage-b-semantic-baseline-prepare stage-b-semantic-baseline-fold stage-b-semantic-baseline-finalize stage-b-semantic-jtt-weights stage-b-semantic-jtt-prepare stage-b-semantic-jtt-fold stage-b-semantic-jtt-finalize stage-b-data-build stage-b-semantic-inference stage-b-semantic-merge stage-b-features stage-b-train stage-b-evaluate stage-c0-diagnose stage-c1-group-weights stage-c1-prepare stage-c1-fold stage-c1-finalize stage-c1-dev-data stage-c1-semantic-inference stage-c1-features stage-c1-evaluate

FAST_TRACK_SEMANTIC_DATASET ?= ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl
FAST_TRACK_SEMANTIC_BASE_MODEL ?= artifacts/models/semantic-domain-fast-track
FAST_TRACK_SEMANTIC_OUTPUT ?= artifacts/models/semantic-fast-track
FAST_TRACK_SEMANTIC_ARGS = --dataset $(FAST_TRACK_SEMANTIC_DATASET) --base-model $(FAST_TRACK_SEMANTIC_BASE_MODEL) --output $(FAST_TRACK_SEMANTIC_OUTPUT) --folds 5 --epochs 2 --batch-size 16 --gradient-accumulation-steps 1 --gradient-checkpointing --prediction-batch-size 32
FAST_TRACK_DOMAIN_ARGS = --dataset ml/data/generated/fast-track/option2/ace-fast-track.jsonl --base-model artifacts/base-models/english-nli --output $(FAST_TRACK_SEMANTIC_BASE_MODEL) --epochs 1 --batch-size 16 --learning-rate 5e-6 --gradient-accumulation-steps 1
FAST_TRACK_COMPLETE_PREDICTIONS ?= $(FAST_TRACK_SEMANTIC_OUTPUT)/semantic-predictions.complete.jsonl
FAST_TRACK_FEATURE_DATASET ?= ml/data/generated/fast-track/features-v2.jsonl
FAST_TRACK_FUSION_OUTPUT ?= artifacts/models/fast-track-fusion-v2
FAST_TRACK_REMEDIATION_OUTPUT ?= artifacts/models/fast-track-remediation-v3
FAST_TRACK_REMEDIATION_SELECTION ?= artifacts/reports/step22-remediation-selection.json
REPLACEMENT_HOLDOUT_DIR ?= ml/data/generated/fast-track/replacement-holdout
REPLACEMENT_HOLDOUT_DATASET ?= $(REPLACEMENT_HOLDOUT_DIR)/replacement-holdout.blinded.jsonl
REPLACEMENT_REVIEW_DIR ?= ml/data/annotations/replacement-holdout
REPLACEMENT_REVIEW_OUTPUTS ?= $(REPLACEMENT_REVIEW_DIR)/outputs
REPLACEMENT_REVIEW_VALIDATED_OUTPUTS ?= $(REPLACEMENT_REVIEW_DIR)/validated-outputs
REPLACEMENT_REVIEW_RETRY ?= $(REPLACEMENT_REVIEW_DIR)/review-a.retry-01.jsonl
REPLACEMENT_REVIEW_RETRY_STATE ?= $(REPLACEMENT_REVIEW_DIR)/review-a.retry-01.state.json
REPLACEMENT_REVIEW_RETRY_OUTPUT ?= $(REPLACEMENT_REVIEW_DIR)/review-a.retry-01.output.jsonl
REPLACEMENT_REVIEWS ?= $(REPLACEMENT_REVIEW_DIR)/reviews.sqlite3
REPLACEMENT_ADJUDICATION ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.jsonl
REPLACEMENT_ADJUDICATION_STATE ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.state.json
REPLACEMENT_ADJUDICATION_OUTPUT ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.output.jsonl
REPLACEMENT_ADJUDICATION_RETRY ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.retry-01.jsonl
REPLACEMENT_ADJUDICATION_RETRY_STATE ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.retry-01.state.json
REPLACEMENT_ADJUDICATION_RETRY_OUTPUT ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.retry-01.output.jsonl
REPLACEMENT_ADJUDICATION_VALIDATED ?= $(REPLACEMENT_REVIEW_DIR)/adjudication.validated.jsonl
REPLACEMENT_REVIEWED_DATASET ?= $(REPLACEMENT_HOLDOUT_DIR)/replacement-holdout.reviewed.jsonl
REPLACEMENT_HOLDOUT_SEMANTIC_PREDICTIONS ?= $(REPLACEMENT_HOLDOUT_DIR)/semantic-predictions.jsonl
REPLACEMENT_HOLDOUT_FEATURE_DATASET ?= $(REPLACEMENT_HOLDOUT_DIR)/features-v2.jsonl
STEP23_EVALUATION_REPORT ?= artifacts/reports/step23-replacement-holdout-evaluation.json
HUMAN_AUDIT_DIR ?= ml/data/annotations/human-audit-v1
HUMAN_AUDIT_REPORT ?= artifacts/reports/human-audit-v1.json
HUMAN_AUDIT_ASSISTED_DIR ?= $(HUMAN_AUDIT_DIR)/assisted
V4_ROOT ?= ml/data/generated/development-v4
V4_POOL ?= $(V4_ROOT)/pool/unused-pool.jsonl
V4_POOL_SEMANTIC ?= $(V4_ROOT)/pool/semantic-predictions.jsonl
V4_POOL_FEATURES ?= $(V4_ROOT)/pool/features-v2.jsonl
V4_REVIEW_QUEUE ?= $(V4_ROOT)/review/review-queue.jsonl
V4_SELECTION_LEDGER ?= $(V4_ROOT)/review/selection-ledger.jsonl
V4_REVIEW_DIR ?= ml/data/annotations/development-v4
V4_REVIEW_OUTPUTS ?= $(V4_REVIEW_DIR)/outputs
V4_REVIEW_STATES ?= $(V4_REVIEW_DIR)/states
V4_REVIEWS ?= $(V4_REVIEW_DIR)/reviews.sqlite3
V4_REVIEWED ?= $(V4_ROOT)/review/reviewed.jsonl
V4_ADJUDICATION ?= $(V4_REVIEW_DIR)/adjudication.jsonl
V4_ADJUDICATION_STATE ?= $(V4_REVIEW_DIR)/adjudication.state.json
V4_ADJUDICATION_OUTPUT ?= $(V4_REVIEW_DIR)/adjudication.output.jsonl
STAGE_B_ROOT ?= ml/data/generated/development-v4-semantic
STAGE_B_POOL ?= $(STAGE_B_ROOT)/pool/unused-pool.jsonl
STAGE_B_POOL_FEATURES ?= $(STAGE_B_ROOT)/pool/features-v2.jsonl
STAGE_B_REVIEW_QUEUE ?= $(STAGE_B_ROOT)/review/review-queue.jsonl
STAGE_B_SELECTION_LEDGER ?= $(STAGE_B_ROOT)/review/selection-ledger.jsonl
STAGE_B_REVIEW_DIR ?= ml/data/annotations/development-v4-semantic
STAGE_B_REVIEW_OUTPUTS ?= $(STAGE_B_REVIEW_DIR)/outputs
STAGE_B_REVIEW_STATES ?= $(STAGE_B_REVIEW_DIR)/states
STAGE_B_REVIEWS ?= $(STAGE_B_REVIEW_DIR)/reviews.sqlite3
STAGE_B_REVIEWED ?= $(STAGE_B_ROOT)/review/reviewed.jsonl
STAGE_B_ADJUDICATION ?= $(STAGE_B_REVIEW_DIR)/adjudication.jsonl
STAGE_B_ADJUDICATION_STATE ?= $(STAGE_B_REVIEW_DIR)/adjudication.state.json
STAGE_B_ADJUDICATION_OUTPUT ?= $(STAGE_B_REVIEW_DIR)/adjudication.output.jsonl
STAGE_B_SEMANTIC_CORPUS ?= $(STAGE_B_ROOT)/semantic/semantic-v4-replay.jsonl
STAGE_B_SEMANTIC_BASE ?= artifacts/base-models/semantic-v3-locked-copy
STAGE_B_SEMANTIC_BASELINE ?= artifacts/models/semantic-v4-baseline
STAGE_B_SEMANTIC_BASELINE_ARGS = --dataset $(STAGE_B_SEMANTIC_CORPUS) --base-model $(STAGE_B_SEMANTIC_BASE) --output $(STAGE_B_SEMANTIC_BASELINE) --folds 5 --epochs 1 --batch-size 16 --learning-rate 5e-6 --gradient-accumulation-steps 1 --gradient-checkpointing --prediction-batch-size 32
STAGE_B_JTT_WEIGHTS ?= $(STAGE_B_ROOT)/semantic/jtt-weights.json
STAGE_B_SEMANTIC_JTT ?= artifacts/models/semantic-v4-jtt
STAGE_B_SEMANTIC_JTT_ARGS = --dataset $(STAGE_B_SEMANTIC_CORPUS) --base-model $(STAGE_B_SEMANTIC_BASE) --output $(STAGE_B_SEMANTIC_JTT) --sample-weights $(STAGE_B_JTT_WEIGHTS) --folds 5 --epochs 1 --batch-size 16 --learning-rate 5e-6 --gradient-accumulation-steps 1 --gradient-checkpointing --prediction-batch-size 32
STAGE_B_DATASET ?= $(STAGE_B_ROOT)/dataset/ace-development-v4-semantic.jsonl
STAGE_B_SEMANTIC_PREDICTIONS ?= $(STAGE_B_ROOT)/dataset/semantic-predictions.jsonl
STAGE_B_SEMANTIC_MERGED ?= $(STAGE_B_ROOT)/dataset/semantic-predictions.oof.jsonl
STAGE_B_FEATURES ?= $(STAGE_B_ROOT)/dataset/features-v3.jsonl
STAGE_B_TABULAR ?= artifacts/models/development-v4-semantic-stage-b
STAGE_B_EVALUATION ?= artifacts/reports/development-v4-semantic-stage-b-evaluation.json
STAGE_C0_DIAGNOSIS ?= artifacts/reports/stage-c0-diagnosis.json
STAGE_C1_WEIGHTS ?= $(STAGE_B_ROOT)/semantic/stage-c1-group-weights.json
STAGE_C1_MODEL ?= artifacts/models/semantic-stage-c1-group-robust
STAGE_C1_ARGS = --dataset $(STAGE_B_SEMANTIC_CORPUS) --base-model $(STAGE_B_SEMANTIC_BASE) --output $(STAGE_C1_MODEL) --sample-weights $(STAGE_C1_WEIGHTS) --folds 2 --epochs 1 --batch-size 16 --learning-rate 5e-6 --gradient-accumulation-steps 1 --gradient-checkpointing --prediction-batch-size 32
STAGE_C1_DEV_ROOT ?= $(STAGE_B_ROOT)/stage-c1
STAGE_C1_DEV_DATASET ?= $(STAGE_C1_DEV_ROOT)/development-policy.jsonl
STAGE_C1_DEV_SEMANTIC ?= $(STAGE_C1_DEV_ROOT)/semantic-predictions.jsonl
STAGE_C1_DEV_FEATURES ?= $(STAGE_C1_DEV_ROOT)/features-v3.jsonl
STAGE_C1_EVALUATION ?= artifacts/reports/stage-c1-evaluation.json

stage-c0-diagnose:
	python3 -m ml.evaluation.diagnose_stage_c \
		--features $(STAGE_B_FEATURES) --dataset $(STAGE_B_DATASET) \
		--stage-b-report $(STAGE_B_EVALUATION) \
		--stage-b-policy $(STAGE_B_TABULAR)/policy-locked-v3-routed.json \
		--v3-model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--v3-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--v3-calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib \
		--output $(STAGE_C0_DIAGNOSIS)

stage-c1-group-weights:
	python3 -m ml.semantic.group_robust \
		--dataset $(STAGE_B_SEMANTIC_CORPUS) --output $(STAGE_C1_WEIGHTS)

stage-c1-prepare:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_C1_ARGS) --stage prepare

stage-c1-fold:
	@test -n "$(FOLD)" || (echo "FOLD is required" && exit 2)
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_C1_ARGS) --stage fold --fold-index "$(FOLD)"

stage-c1-finalize:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_C1_ARGS) --stage finalize

stage-c1-dev-data:
	python3 -m ml.data.build_stage_c \
		--source $(STAGE_B_DATASET) --output $(STAGE_C1_DEV_DATASET)

stage-c1-semantic-inference:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.infer_external \
		--dataset $(STAGE_C1_DEV_DATASET) \
		--semantic-manifest $(STAGE_C1_MODEL)/manifest.json \
		--model $(STAGE_C1_MODEL)/model \
		--output $(STAGE_C1_DEV_SEMANTIC) --batch-size 32

stage-c1-features:
	python3 -m ml.features.build_features_v3 \
		--dataset $(STAGE_C1_DEV_DATASET) \
		--semantic-predictions $(STAGE_C1_DEV_SEMANTIC) \
		--output $(STAGE_C1_DEV_FEATURES)

stage-c1-evaluate:
	python3 -m ml.evaluation.evaluate_stage_c1 \
		--c1-features $(STAGE_C1_DEV_FEATURES) --stage-b-features $(STAGE_B_FEATURES) \
		--baseline-semantic $(STAGE_B_SEMANTIC_BASELINE)/semantic-predictions.jsonl \
		--c1-semantic $(STAGE_C1_MODEL)/semantic-predictions.jsonl \
		--stage-b-policy $(STAGE_B_TABULAR)/policy-locked-v3-routed.json \
		--v3-model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--v3-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--v3-calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib \
		--output $(STAGE_C1_EVALUATION)

stage-b-pool-freeze:
	python3 -m ml.data.build_stage_b freeze-pool \
		--stage-a-pool $(V4_POOL) \
		--stage-a-dataset $(V4_ROOT)/dataset/ace-development-v4.jsonl \
		--stage-a-features $(V4_POOL_FEATURES) \
		--output-pool $(STAGE_B_POOL) \
		--output-features $(STAGE_B_POOL_FEATURES)

stage-b-review-select:
	python3 -m ml.data.build_stage_b select-review \
		--pool $(STAGE_B_POOL) \
		--features $(STAGE_B_POOL_FEATURES) \
		--model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--model-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib \
		--output $(STAGE_B_REVIEW_QUEUE) \
		--ledger $(STAGE_B_SELECTION_LEDGER)

stage-b-review-prepare:
	python3 -m ml.data.llm_annotations prepare \
		--dataset $(STAGE_B_REVIEW_QUEUE) \
		--output $(STAGE_B_REVIEW_DIR)/requests \
		--locale en-US --max-examples 1500 --chunk-size 500 \
		--seed 2031 --blind-provenance --prompt-profile policy-v3

stage-b-review-validate:
	python3 -m ml.data.llm_annotations validate-prepared \
		--input $(STAGE_B_REVIEW_DIR)/requests

stage-b-review-submit:
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(STAGE_B_REVIEW_DIR)/requests --states $(STAGE_B_REVIEW_STATES) \
		--role a --key-file .env.annotation
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(STAGE_B_REVIEW_DIR)/requests --states $(STAGE_B_REVIEW_STATES) \
		--role b --key-file .env.annotation

stage-b-review-status:
	python3 -m ml.data.llm_annotations status-shards \
		--states $(STAGE_B_REVIEW_STATES) --key-file .env.annotation

stage-b-review-wait:
	python3 -m ml.data.llm_annotations wait-shards \
		--states $(STAGE_B_REVIEW_STATES) --key-file .env.annotation --interval-seconds 30

stage-b-review-download:
	python3 -m ml.data.llm_annotations download-shards \
		--states $(STAGE_B_REVIEW_STATES) --outputs $(STAGE_B_REVIEW_OUTPUTS) \
		--key-file .env.annotation

stage-b-review-validate-outputs:
	python3 -m ml.data.llm_annotations validate-outputs \
		--input $(STAGE_B_REVIEW_DIR)/requests --outputs $(STAGE_B_REVIEW_OUTPUTS)

stage-b-review-import:
	python3 -m ml.data.llm_annotations import-shards \
		--dataset $(STAGE_B_REVIEW_QUEUE) --reviews $(STAGE_B_REVIEWS) \
		--input $(STAGE_B_REVIEW_DIR)/requests --outputs $(STAGE_B_REVIEW_OUTPUTS)

stage-b-adjudication-prepare:
	python3 -m ml.data.llm_annotations prepare-adjudication \
		--dataset $(STAGE_B_REVIEW_QUEUE) --reviews $(STAGE_B_REVIEWS) \
		--output $(STAGE_B_ADJUDICATION) --blind-provenance --prompt-profile policy-v3

stage-b-adjudication-validate:
	python3 -m ml.data.llm_annotations validate-adjudication \
		--dataset $(STAGE_B_REVIEW_QUEUE) --reviews $(STAGE_B_REVIEWS) \
		--input $(STAGE_B_ADJUDICATION) \
		--manifest $(STAGE_B_REVIEW_DIR)/adjudication.manifest.json

stage-b-adjudication-submit:
	python3 -m ml.data.llm_annotations submit --input $(STAGE_B_ADJUDICATION) \
		--state $(STAGE_B_ADJUDICATION_STATE) --key-file .env.annotation

stage-b-adjudication-status:
	python3 -m ml.data.llm_annotations status --state $(STAGE_B_ADJUDICATION_STATE) \
		--key-file .env.annotation

stage-b-adjudication-wait:
	python3 -m ml.data.llm_annotations wait --state $(STAGE_B_ADJUDICATION_STATE) \
		--key-file .env.annotation --interval-seconds 30

stage-b-adjudication-download:
	python3 -m ml.data.llm_annotations download --state $(STAGE_B_ADJUDICATION_STATE) \
		--output $(STAGE_B_ADJUDICATION_OUTPUT) --key-file .env.annotation

stage-b-adjudication-validate-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output \
		--input $(STAGE_B_ADJUDICATION) --output $(STAGE_B_ADJUDICATION_OUTPUT) \
		--state $(STAGE_B_ADJUDICATION_STATE)

stage-b-adjudication-import:
	python3 -m ml.data.llm_annotations import-adjudication \
		--dataset $(STAGE_B_REVIEW_QUEUE) --reviews $(STAGE_B_REVIEWS) \
		--input $(STAGE_B_ADJUDICATION) --output $(STAGE_B_ADJUDICATION_OUTPUT)

stage-b-review-export:
	python3 -m ml.data.export_annotations --dataset $(STAGE_B_REVIEW_QUEUE) \
		--reviews $(STAGE_B_REVIEWS) --output $(STAGE_B_REVIEWED)

stage-b-semantic-corpus:
	python3 -m ml.data.build_semantic_v4 \
		--stage-b-reviewed $(STAGE_B_REVIEWED) \
		--stage-a-reviewed $(V4_REVIEWED) \
		--replay-source $(FAST_TRACK_SEMANTIC_DATASET) \
		--output $(STAGE_B_SEMANTIC_CORPUS) --replay-target 2100

stage-b-semantic-base:
	python3 -m ml.semantic.freeze_base \
		--source-model $(FAST_TRACK_SEMANTIC_OUTPUT)/model \
		--source-manifest $(FAST_TRACK_SEMANTIC_OUTPUT)/manifest.json \
		--output $(STAGE_B_SEMANTIC_BASE)

stage-b-semantic-baseline-prepare:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_BASELINE_ARGS) --stage prepare

stage-b-semantic-baseline-fold:
	@test -n "$(FOLD)" || (echo "FOLD is required" && exit 2)
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_BASELINE_ARGS) --stage fold --fold-index "$(FOLD)"

stage-b-semantic-baseline-finalize:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_BASELINE_ARGS) --stage finalize

stage-b-semantic-jtt-weights:
	python3 -m ml.semantic.jtt \
		--predictions $(STAGE_B_SEMANTIC_BASELINE)/semantic-predictions.jsonl \
		--output $(STAGE_B_JTT_WEIGHTS) --error-weight 4

stage-b-semantic-jtt-prepare:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_JTT_ARGS) --stage prepare

stage-b-semantic-jtt-fold:
	@test -n "$(FOLD)" || (echo "FOLD is required" && exit 2)
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_JTT_ARGS) --stage fold --fold-index "$(FOLD)"

stage-b-semantic-jtt-finalize:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual \
		$(STAGE_B_SEMANTIC_JTT_ARGS) --stage finalize

stage-b-data-build:
	python3 -m ml.data.build_stage_b_dataset \
		--v3-dataset ml/data/generated/development-v3/ace-development-v3.jsonl \
		--stage-b-reviewed $(STAGE_B_REVIEWED) \
		--stage-b-pool $(STAGE_B_POOL) \
		--output $(STAGE_B_DATASET)

stage-b-semantic-inference:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.infer_external \
		--dataset $(STAGE_B_DATASET) \
		--semantic-manifest $(STAGE_B_SEMANTIC_BASELINE)/manifest.json \
		--model $(STAGE_B_SEMANTIC_BASELINE)/model \
		--output $(STAGE_B_SEMANTIC_PREDICTIONS) --batch-size 32

stage-b-semantic-merge:
	python3 -m ml.semantic.merge_stage_b_predictions \
		--dataset $(STAGE_B_DATASET) \
		--external $(STAGE_B_SEMANTIC_PREDICTIONS) \
		--oof $(STAGE_B_SEMANTIC_BASELINE)/semantic-predictions.jsonl \
		--output $(STAGE_B_SEMANTIC_MERGED) --expected-replacements 805

stage-b-features:
	python3 -m ml.features.build_features_v3 \
		--dataset $(STAGE_B_DATASET) \
		--semantic-predictions $(STAGE_B_SEMANTIC_MERGED) \
		--output $(STAGE_B_FEATURES)

stage-b-train:
	python3 -m ml.tabular.train_stage_b \
		--features $(STAGE_B_FEATURES) --output $(STAGE_B_TABULAR) \
		--v3-model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--v3-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--v3-calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib

stage-b-evaluate:
	python3 -m ml.evaluation.evaluate_stage_b \
		--features $(STAGE_B_FEATURES) \
		--selection-ledger $(STAGE_B_SELECTION_LEDGER) \
		--artifacts $(STAGE_B_TABULAR) \
		--v3-model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--v3-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--v3-calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib \
		--v3-baseline artifacts/models/development-v3-baselines/baseline-report.json \
		--output $(STAGE_B_EVALUATION)

v4-pool-freeze:
	python3 -m ml.data.build_dataset_v4 freeze-pool \
		--source ml/data/generated/option1-en-v3/ace-esci-en-hybrid.jsonl \
		--exclude ml/data/generated/development-v3/ace-development-v3.jsonl \
		--exclude ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl \
		--exclude ml/data/generated/fast-track/replacement-holdout/replacement-holdout.reviewed.jsonl \
		--output $(V4_POOL)

v4-pool-semantic:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.infer_external \
		--dataset $(V4_POOL) \
		--semantic-manifest $(FAST_TRACK_SEMANTIC_OUTPUT)/manifest.json \
		--model $(FAST_TRACK_SEMANTIC_OUTPUT)/model \
		--output $(V4_POOL_SEMANTIC) \
		--batch-size 32

v4-pool-features:
	python3 -m ml.features.build_features \
		--dataset $(V4_POOL) \
		--semantic-predictions $(V4_POOL_SEMANTIC) \
		--output $(V4_POOL_FEATURES)

v4-review-select:
	python3 -m ml.data.build_dataset_v4 select-review \
		--pool $(V4_POOL) \
		--features $(V4_POOL_FEATURES) \
		--model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--model-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--baseline-report artifacts/models/development-v3-baselines/baseline-report.json \
		--output $(V4_REVIEW_QUEUE) \
		--ledger $(V4_SELECTION_LEDGER)

v4-review-prepare:
	python3 -m ml.data.llm_annotations prepare \
		--dataset $(V4_REVIEW_QUEUE) \
		--output $(V4_REVIEW_DIR)/requests \
		--locale en-US --max-examples 1200 --chunk-size 600 \
		--seed 2030 --blind-provenance --prompt-profile policy-v3

v4-review-validate:
	python3 -m ml.data.llm_annotations validate-prepared \
		--input $(V4_REVIEW_DIR)/requests

v4-review-submit:
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(V4_REVIEW_DIR)/requests --states $(V4_REVIEW_STATES) \
		--role a --key-file .env.annotation
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(V4_REVIEW_DIR)/requests --states $(V4_REVIEW_STATES) \
		--role b --key-file .env.annotation

v4-review-status:
	python3 -m ml.data.llm_annotations status-shards \
		--states $(V4_REVIEW_STATES) --key-file .env.annotation

v4-review-wait:
	python3 -m ml.data.llm_annotations wait-shards \
		--states $(V4_REVIEW_STATES) --key-file .env.annotation --interval-seconds 30

v4-review-download:
	python3 -m ml.data.llm_annotations download-shards \
		--states $(V4_REVIEW_STATES) --outputs $(V4_REVIEW_OUTPUTS) \
		--key-file .env.annotation

v4-review-validate-outputs:
	python3 -m ml.data.llm_annotations validate-outputs \
		--input $(V4_REVIEW_DIR)/requests --outputs $(V4_REVIEW_OUTPUTS)

v4-review-import:
	python3 -m ml.data.llm_annotations import-shards \
		--dataset $(V4_REVIEW_QUEUE) --reviews $(V4_REVIEWS) \
		--input $(V4_REVIEW_DIR)/requests --outputs $(V4_REVIEW_OUTPUTS)

v4-adjudication-prepare:
	python3 -m ml.data.llm_annotations prepare-adjudication \
		--dataset $(V4_REVIEW_QUEUE) --reviews $(V4_REVIEWS) \
		--output $(V4_ADJUDICATION) --blind-provenance --prompt-profile policy-v3

v4-adjudication-validate:
	python3 -m ml.data.llm_annotations validate-adjudication \
		--dataset $(V4_REVIEW_QUEUE) --reviews $(V4_REVIEWS) \
		--input $(V4_ADJUDICATION) \
		--manifest $(V4_REVIEW_DIR)/adjudication.manifest.json

v4-adjudication-submit:
	python3 -m ml.data.llm_annotations submit --input $(V4_ADJUDICATION) \
		--state $(V4_ADJUDICATION_STATE) --key-file .env.annotation

v4-adjudication-status:
	python3 -m ml.data.llm_annotations status --state $(V4_ADJUDICATION_STATE) \
		--key-file .env.annotation

v4-adjudication-wait:
	python3 -m ml.data.llm_annotations wait --state $(V4_ADJUDICATION_STATE) \
		--key-file .env.annotation --interval-seconds 30

v4-adjudication-download:
	python3 -m ml.data.llm_annotations download --state $(V4_ADJUDICATION_STATE) \
		--output $(V4_ADJUDICATION_OUTPUT) --key-file .env.annotation

v4-adjudication-validate-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output \
		--input $(V4_ADJUDICATION) --output $(V4_ADJUDICATION_OUTPUT) \
		--state $(V4_ADJUDICATION_STATE)

v4-adjudication-import:
	python3 -m ml.data.llm_annotations import-adjudication \
		--dataset $(V4_REVIEW_QUEUE) --reviews $(V4_REVIEWS) \
		--input $(V4_ADJUDICATION) --output $(V4_ADJUDICATION_OUTPUT)

v4-review-export:
	python3 -m ml.data.export_annotations --dataset $(V4_REVIEW_QUEUE) \
		--reviews $(V4_REVIEWS) --output $(V4_REVIEWED)

v4-data-build:
	python3 -m ml.data.build_dataset_v4 build --pool $(V4_POOL) \
		--reviewed $(V4_REVIEWED) --selection-ledger $(V4_SELECTION_LEDGER) \
		--output $(V4_ROOT)/dataset

v4-dataset-semantic:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.infer_external \
		--dataset $(V4_ROOT)/dataset/ace-development-v4.jsonl \
		--semantic-manifest $(FAST_TRACK_SEMANTIC_OUTPUT)/manifest.json \
		--model $(FAST_TRACK_SEMANTIC_OUTPUT)/model \
		--output $(V4_ROOT)/dataset/semantic-predictions.jsonl --batch-size 32

v4-features-v3:
	python3 -m ml.features.build_features_v3 \
		--dataset $(V4_ROOT)/dataset/ace-development-v4.jsonl \
		--semantic-predictions $(V4_ROOT)/dataset/semantic-predictions.jsonl \
		--output $(V4_ROOT)/dataset/features-v3.jsonl

v4-train-stage-a:
	python3 -m ml.tabular.train_v4 \
		--features $(V4_ROOT)/dataset/features-v3.jsonl \
		--output artifacts/models/development-v4-data-policy

v4-evaluate-stage-a:
	python3 -m ml.evaluation.evaluate_v4 \
		--features $(V4_ROOT)/dataset/features-v3.jsonl \
		--selection-ledger $(V4_SELECTION_LEDGER) \
		--v4-artifacts artifacts/models/development-v4-data-policy \
		--v3-model artifacts/models/development-v3-catboost/catboost-v1.cbm \
		--v3-manifest artifacts/models/development-v3-catboost/catboost-v1.manifest.json \
		--v3-calibrator artifacts/models/development-v3-baselines/platt-calibrator-v3.joblib \
		--v3-baseline artifacts/models/development-v3-baselines/baseline-report.json \
		--output artifacts/reports/development-v4-stage-a-evaluation.json

human-audit-prepare:
	python3 -m ml.data.human_audit prepare \
		--development ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl \
		--holdout ml/data/generated/fast-track/replacement-holdout/replacement-holdout.reviewed.jsonl \
		--output $(HUMAN_AUDIT_DIR) \
		--rows 400

human-audit-validate:
	python3 -m ml.data.human_audit validate --output $(HUMAN_AUDIT_DIR)

human-audit-status:
	python3 -m ml.data.human_audit status --output $(HUMAN_AUDIT_DIR)

human-audit-report:
	python3 -m ml.data.human_audit report \
		--output $(HUMAN_AUDIT_DIR) \
		--report $(HUMAN_AUDIT_REPORT)

human-audit-api:
	ACE_ANNOTATION_ENABLED=1 \
	ACE_ANNOTATION_DATASET=$(HUMAN_AUDIT_DIR)/review-queue.jsonl \
	ACE_ANNOTATION_DATABASE=$(HUMAN_AUDIT_DIR)/human-reviews.sqlite3 \
	uvicorn app.main:app --app-dir services/api --reload --port 8000

human-audit-assisted-prepare:
	python3 -m ml.data.human_audit prepare-assisted --output $(HUMAN_AUDIT_DIR)
	python3 -m ml.data.llm_annotations prepare \
		--dataset $(HUMAN_AUDIT_ASSISTED_DIR)/assisted-review-dataset.jsonl \
		--supplemental-context $(HUMAN_AUDIT_ASSISTED_DIR)/assisted-context.jsonl \
		--output $(HUMAN_AUDIT_ASSISTED_DIR)/requests \
		--locale en-US --max-examples 400 --chunk-size 400 --blind-provenance \
		--prompt-profile policy-v3
	python3 -m ml.data.llm_annotations validate-prepared \
		--input $(HUMAN_AUDIT_ASSISTED_DIR)/requests

human-audit-assisted-submit:
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(HUMAN_AUDIT_ASSISTED_DIR)/requests \
		--states $(HUMAN_AUDIT_ASSISTED_DIR)/states --role a --key-file .env.annotation
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(HUMAN_AUDIT_ASSISTED_DIR)/requests \
		--states $(HUMAN_AUDIT_ASSISTED_DIR)/states --role b --key-file .env.annotation

human-audit-assisted-status:
	python3 -m ml.data.llm_annotations status-shards \
		--states $(HUMAN_AUDIT_ASSISTED_DIR)/states --key-file .env.annotation

data-option1-v3:
	python3 -m ml.data.build_option1 --source ml/data/raw/esci \
		--output ml/data/generated/option1-en-v3 --size 60000 --locale en-US

data-development-v3:
	python3 -m ml.data.build_dataset_v3 \
		--source ml/data/generated/option1-en-v3/ace-esci-en-hybrid.jsonl \
		--consumed-holdout ml/data/generated/fast-track/replacement-holdout/replacement-holdout.reviewed.jsonl \
		--audit-reviewed $(HUMAN_AUDIT_ASSISTED_DIR)/assisted-reviewed.jsonl \
		--audit-ledger $(HUMAN_AUDIT_DIR)/audit-ledger.jsonl \
		--output ml/data/generated/development-v3

install:
	python3 -m pip install -e 'services/api[dev,ml]'
	npm --prefix apps/web install

test: test-api test-web

test-api:
	python3 -m pytest services/api/tests -q
	python3 -m pytest tests -q --rootdir=.

test-web:
	npm --prefix apps/web test -- --run

test-e2e:
	npm --prefix apps/web run test:e2e

dev:
	docker compose up --build

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

seed:
	python3 ml/data/generate_dataset.py

data-esci:
	python3 -m ml.data.acquire_esci

data-option1:
	python3 -m ml.data.build_option1

data-option2:
	python3 -m ml.data.build_option2

data-option2-uci:
	python3 -m ml.data.acquire_option2 uci

data-option2-db1b:
	python3 -m ml.data.acquire_option2 db1b

data-option2-usaspending:
	python3 -m ml.data.acquire_option2 usaspending

data-option2-amazon:
	python3 -m ml.data.acquire_option2 amazon-m2 --amazon-source "$(AMAZON_SOURCE)"

data-fast-track-option1:
	python3 -m ml.data.select_fast_track \
		--dataset ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl \
		--source-manifest ml/data/generated/option1-en/manifest.json \
		--output ml/data/generated/fast-track/option1 \
		--train-rows 4000

data-fast-track-option2:
	python3 -m ml.data.select_fast_track \
		--dataset ml/data/generated/option2/ace-public-benchmark.jsonl \
		--source-manifest ml/data/generated/option2/manifest.json \
		--output ml/data/generated/fast-track/option2 \
		--train-rows 10000

data-validate:
	python3 -m ml.data.validate_dataset "$(DATASET)" --manifest "$(MANIFEST)"

annotate-api:
	ACE_ANNOTATION_ENABLED=1 uvicorn app.main:app --app-dir services/api --reload --port 8000

llm-prepare:
	python3 -m ml.data.llm_annotations prepare --dataset ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl --output ml/data/annotations/llm-option1-en --locale en-US

llm-submit-a:
	python3 -m ml.data.llm_annotations submit-shards --input ml/data/annotations/llm-option1-en --states ml/data/annotations/llm-option1-en/states --role a --key-file .env.annotation

llm-submit-b:
	python3 -m ml.data.llm_annotations submit-shards --input ml/data/annotations/llm-option1-en --states ml/data/annotations/llm-option1-en/states --role b --key-file .env.annotation

llm-fast-track-prepare:
	python3 -m ml.data.llm_annotations prepare --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --output ml/data/annotations/fast-track --locale en-US --max-examples 2500 --chunk-size 1000 --seed 2026

llm-fast-track-validate:
	python3 -m ml.data.llm_annotations validate-prepared --input ml/data/annotations/fast-track

llm-fast-track-submit-a:
	python3 -m ml.data.llm_annotations submit-shards --input ml/data/annotations/fast-track --states ml/data/annotations/fast-track/states --role a --key-file .env.annotation

llm-fast-track-submit-b:
	python3 -m ml.data.llm_annotations submit-shards --input ml/data/annotations/fast-track --states ml/data/annotations/fast-track/states --role b --key-file .env.annotation

llm-fast-track-validate-submissions:
	python3 -m ml.data.llm_annotations validate-submissions --input ml/data/annotations/fast-track --states ml/data/annotations/fast-track/states

llm-fast-track-status:
	python3 -m ml.data.llm_annotations status-shards --states ml/data/annotations/fast-track/states --key-file .env.annotation

llm-fast-track-wait:
	python3 -m ml.data.llm_annotations wait-shards --states ml/data/annotations/fast-track/states --key-file .env.annotation --interval-seconds 30

llm-fast-track-download:
	python3 -m ml.data.llm_annotations download-shards --states ml/data/annotations/fast-track/states --outputs ml/data/annotations/fast-track/outputs --key-file .env.annotation

llm-fast-track-validate-outputs:
	python3 -m ml.data.llm_annotations validate-outputs --input ml/data/annotations/fast-track --outputs ml/data/annotations/fast-track/outputs

llm-fast-track-import:
	python3 -m ml.data.llm_annotations import-shards --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --reviews ml/data/annotations/fast-track/reviews.sqlite3 --input ml/data/annotations/fast-track --outputs ml/data/annotations/fast-track/outputs

llm-fast-track-prepare-adjudication:
	python3 -m ml.data.llm_annotations prepare-adjudication --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --reviews ml/data/annotations/fast-track/reviews.sqlite3 --output ml/data/annotations/fast-track/adjudication.jsonl

llm-fast-track-validate-adjudication:
	python3 -m ml.data.llm_annotations validate-adjudication --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --reviews ml/data/annotations/fast-track/reviews.sqlite3 --input ml/data/annotations/fast-track/adjudication.jsonl --manifest ml/data/annotations/fast-track/adjudication.manifest.json

llm-fast-track-submit-adjudication:
	python3 -m ml.data.llm_annotations submit --input ml/data/annotations/fast-track/adjudication.jsonl --state ml/data/annotations/fast-track/adjudication.state.json --key-file .env.annotation

llm-fast-track-adjudication-status:
	python3 -m ml.data.llm_annotations status --state ml/data/annotations/fast-track/adjudication.state.json --key-file .env.annotation

llm-fast-track-adjudication-wait:
	python3 -m ml.data.llm_annotations wait --state ml/data/annotations/fast-track/adjudication.state.json --key-file .env.annotation --interval-seconds 30

llm-fast-track-adjudication-download:
	python3 -m ml.data.llm_annotations download --state ml/data/annotations/fast-track/adjudication.state.json --output ml/data/annotations/fast-track/adjudication.output.jsonl --key-file .env.annotation

llm-fast-track-validate-adjudication-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output --input ml/data/annotations/fast-track/adjudication.jsonl --output ml/data/annotations/fast-track/adjudication.output.jsonl --state ml/data/annotations/fast-track/adjudication.state.json

llm-fast-track-prepare-adjudication-retry:
	python3 -m ml.data.llm_annotations prepare-adjudication-retry --input ml/data/annotations/fast-track/adjudication.jsonl --output ml/data/annotations/fast-track/adjudication.output.jsonl --retry ml/data/annotations/fast-track/adjudication.retry-01.jsonl --max-output-tokens 1000

llm-fast-track-submit-adjudication-retry:
	python3 -m ml.data.llm_annotations submit --input ml/data/annotations/fast-track/adjudication.retry-01.jsonl --state ml/data/annotations/fast-track/adjudication.retry-01.state.json --key-file .env.annotation

llm-fast-track-adjudication-retry-status:
	python3 -m ml.data.llm_annotations status --state ml/data/annotations/fast-track/adjudication.retry-01.state.json --key-file .env.annotation

llm-fast-track-adjudication-retry-wait:
	python3 -m ml.data.llm_annotations wait --state ml/data/annotations/fast-track/adjudication.retry-01.state.json --key-file .env.annotation --interval-seconds 30

llm-fast-track-adjudication-retry-download:
	python3 -m ml.data.llm_annotations download --state ml/data/annotations/fast-track/adjudication.retry-01.state.json --output ml/data/annotations/fast-track/adjudication.retry-01.output.jsonl --key-file .env.annotation

llm-fast-track-validate-adjudication-retry-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output --input ml/data/annotations/fast-track/adjudication.retry-01.jsonl --output ml/data/annotations/fast-track/adjudication.retry-01.output.jsonl --state ml/data/annotations/fast-track/adjudication.retry-01.state.json

llm-fast-track-merge-adjudication-retry:
	python3 -m ml.data.llm_annotations merge-adjudication-retry --input ml/data/annotations/fast-track/adjudication.jsonl --output ml/data/annotations/fast-track/adjudication.output.jsonl --retry-input ml/data/annotations/fast-track/adjudication.retry-01.jsonl --retry-output ml/data/annotations/fast-track/adjudication.retry-01.output.jsonl --merged ml/data/annotations/fast-track/adjudication.validated.jsonl

llm-fast-track-import-adjudication:
	python3 -m ml.data.llm_annotations import-adjudication --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --reviews ml/data/annotations/fast-track/reviews.sqlite3 --input ml/data/annotations/fast-track/adjudication.jsonl --output ml/data/annotations/fast-track/adjudication.validated.jsonl

llm-fast-track-export-reviewed:
	python3 -m ml.data.export_annotations --dataset ml/data/generated/fast-track/option1/ace-fast-track.jsonl --reviews ml/data/annotations/fast-track/reviews.sqlite3 --output ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl

llm-fast-track-validate-reviewed:
	python3 -m ml.data.validate_dataset ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl --manifest ml/data/generated/fast-track/option1/ace-fast-track-reviewed.manifest.json

semantic-domain-fast-track-prepare:
	python3 -m ml.semantic.train_domain $(FAST_TRACK_DOMAIN_ARGS) --stage prepare

semantic-domain-fast-track-train:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_domain $(FAST_TRACK_DOMAIN_ARGS) --stage train

semantic-fast-track-prepare:
	python3 -m ml.semantic.train_multilingual $(FAST_TRACK_SEMANTIC_ARGS) --stage prepare

semantic-fast-track-fold:
	test -n "$(FOLD)"
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual $(FAST_TRACK_SEMANTIC_ARGS) --stage fold --fold-index "$(FOLD)"

semantic-fast-track-finalize:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.train_multilingual $(FAST_TRACK_SEMANTIC_ARGS) --stage finalize

semantic-fast-track-complete-predictions:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.complete_predictions \
		--dataset $(FAST_TRACK_SEMANTIC_DATASET) \
		--source-predictions $(FAST_TRACK_SEMANTIC_OUTPUT)/semantic-predictions.jsonl \
		--semantic-manifest $(FAST_TRACK_SEMANTIC_OUTPUT)/manifest.json \
		--model $(FAST_TRACK_SEMANTIC_OUTPUT)/model \
		--output $(FAST_TRACK_COMPLETE_PREDICTIONS) \
		--batch-size 32

features-fast-track:
	python3 -m ml.features.build_features \
		--dataset $(FAST_TRACK_SEMANTIC_DATASET) \
		--semantic-predictions $(FAST_TRACK_COMPLETE_PREDICTIONS) \
		--output $(FAST_TRACK_FEATURE_DATASET)

export-reviews:
	python3 -m ml.data.export_annotations --dataset "$(DATASET)" --reviews "$(REVIEWS)" --output "$(OUTPUT)"

features:
	python3 -m ml.features.build_features --dataset "$(DATASET)" --semantic-predictions "$(SEMANTIC_PREDICTIONS)" --output "$(FEATURE_DATASET)"

.PHONY: train evaluate evaluate-fast-track-v2 diagnose-fast-track-remediation train-fast-track-v3-no-semantic train-fast-track-v3-semantic replacement-holdout-freeze replacement-holdout-prepare-reviews replacement-holdout-validate-reviews replacement-holdout-submit-a replacement-holdout-submit-b replacement-holdout-validate-submissions replacement-holdout-status replacement-holdout-wait replacement-holdout-download replacement-holdout-validate-outputs replacement-holdout-prepare-review-retry replacement-holdout-submit-review-retry replacement-holdout-review-retry-status replacement-holdout-review-retry-wait replacement-holdout-review-retry-download replacement-holdout-validate-review-retry-output replacement-holdout-merge-review-retry replacement-holdout-validate-merged-outputs replacement-holdout-import replacement-holdout-import-merged replacement-holdout-prepare-adjudication replacement-holdout-validate-adjudication replacement-holdout-submit-adjudication replacement-holdout-adjudication-status replacement-holdout-adjudication-wait replacement-holdout-adjudication-download replacement-holdout-validate-adjudication-output replacement-holdout-prepare-adjudication-retry replacement-holdout-submit-adjudication-retry replacement-holdout-adjudication-retry-status replacement-holdout-adjudication-retry-wait replacement-holdout-adjudication-retry-download replacement-holdout-validate-adjudication-retry-output replacement-holdout-merge-adjudication-retry replacement-holdout-import-adjudication replacement-holdout-export-reviewed replacement-holdout-validate-reviewed

replacement-holdout-freeze:
	python3 -m ml.data.freeze_replacement_holdout \
		--source ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl \
		--exclude ml/data/generated/fast-track/option1/ace-fast-track.jsonl \
		--output $(REPLACEMENT_HOLDOUT_DIR) \
		--rows 4000 \
		--seed 2027

replacement-holdout-prepare-reviews:
	python3 -m ml.data.llm_annotations prepare \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--output $(REPLACEMENT_REVIEW_DIR) \
		--locale en-US \
		--chunk-size 1000 \
		--seed 2027 \
		--blind-provenance

replacement-holdout-validate-reviews:
	python3 -m ml.data.llm_annotations validate-prepared \
		--input $(REPLACEMENT_REVIEW_DIR)

replacement-holdout-submit-a:
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--states $(REPLACEMENT_REVIEW_DIR)/states \
		--role a \
		--key-file .env.annotation

replacement-holdout-submit-b:
	python3 -m ml.data.llm_annotations submit-shards \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--states $(REPLACEMENT_REVIEW_DIR)/states \
		--role b \
		--key-file .env.annotation

replacement-holdout-validate-submissions:
	python3 -m ml.data.llm_annotations validate-submissions \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--states $(REPLACEMENT_REVIEW_DIR)/states

replacement-holdout-status:
	python3 -m ml.data.llm_annotations status-shards \
		--states $(REPLACEMENT_REVIEW_DIR)/states \
		--key-file .env.annotation

replacement-holdout-wait:
	python3 -m ml.data.llm_annotations wait-shards \
		--states $(REPLACEMENT_REVIEW_DIR)/states \
		--key-file .env.annotation \
		--interval-seconds 30

replacement-holdout-download:
	python3 -m ml.data.llm_annotations download-shards \
		--states $(REPLACEMENT_REVIEW_DIR)/states \
		--outputs $(REPLACEMENT_REVIEW_OUTPUTS) \
		--key-file .env.annotation

replacement-holdout-validate-outputs:
	python3 -m ml.data.llm_annotations validate-outputs \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_OUTPUTS)

replacement-holdout-prepare-review-retry:
	python3 -m ml.data.llm_annotations prepare-review-retry \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_OUTPUTS) \
		--retry $(REPLACEMENT_REVIEW_RETRY) \
		--role a \
		--max-output-tokens 1000

replacement-holdout-submit-review-retry:
	python3 -m ml.data.llm_annotations submit \
		--input $(REPLACEMENT_REVIEW_RETRY) \
		--state $(REPLACEMENT_REVIEW_RETRY_STATE) \
		--key-file .env.annotation

replacement-holdout-review-retry-status:
	python3 -m ml.data.llm_annotations status \
		--state $(REPLACEMENT_REVIEW_RETRY_STATE) \
		--key-file .env.annotation

replacement-holdout-review-retry-wait:
	python3 -m ml.data.llm_annotations wait \
		--state $(REPLACEMENT_REVIEW_RETRY_STATE) \
		--key-file .env.annotation \
		--interval-seconds 30

replacement-holdout-review-retry-download:
	python3 -m ml.data.llm_annotations download \
		--state $(REPLACEMENT_REVIEW_RETRY_STATE) \
		--output $(REPLACEMENT_REVIEW_RETRY_OUTPUT) \
		--key-file .env.annotation

replacement-holdout-validate-review-retry-output:
	python3 -m ml.data.llm_annotations validate-batch-output \
		--input $(REPLACEMENT_REVIEW_RETRY) \
		--output $(REPLACEMENT_REVIEW_RETRY_OUTPUT) \
		--state $(REPLACEMENT_REVIEW_RETRY_STATE) \
		--reviewer-id llm-a-gpt-5.4-mini-2026-03-17

replacement-holdout-merge-review-retry:
	python3 -m ml.data.llm_annotations merge-review-retry \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_OUTPUTS) \
		--retry-input $(REPLACEMENT_REVIEW_RETRY) \
		--retry-output $(REPLACEMENT_REVIEW_RETRY_OUTPUT) \
		--merged-outputs $(REPLACEMENT_REVIEW_VALIDATED_OUTPUTS)

replacement-holdout-validate-merged-outputs:
	python3 -m ml.data.llm_annotations validate-outputs \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_VALIDATED_OUTPUTS)

replacement-holdout-import:
	python3 -m ml.data.llm_annotations import-shards \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_OUTPUTS)

replacement-holdout-import-merged:
	python3 -m ml.data.llm_annotations import-shards \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--input $(REPLACEMENT_REVIEW_DIR) \
		--outputs $(REPLACEMENT_REVIEW_VALIDATED_OUTPUTS)

replacement-holdout-prepare-adjudication:
	python3 -m ml.data.llm_annotations prepare-adjudication \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--output $(REPLACEMENT_ADJUDICATION) \
		--blind-provenance

replacement-holdout-validate-adjudication:
	python3 -m ml.data.llm_annotations validate-adjudication \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--input $(REPLACEMENT_ADJUDICATION) \
		--manifest $(REPLACEMENT_REVIEW_DIR)/adjudication.manifest.json

replacement-holdout-submit-adjudication:
	python3 -m ml.data.llm_annotations submit \
		--input $(REPLACEMENT_ADJUDICATION) \
		--state $(REPLACEMENT_ADJUDICATION_STATE) \
		--key-file .env.annotation

replacement-holdout-adjudication-status:
	python3 -m ml.data.llm_annotations status \
		--state $(REPLACEMENT_ADJUDICATION_STATE) \
		--key-file .env.annotation

replacement-holdout-adjudication-wait:
	python3 -m ml.data.llm_annotations wait \
		--state $(REPLACEMENT_ADJUDICATION_STATE) \
		--key-file .env.annotation \
		--interval-seconds 30

replacement-holdout-adjudication-download:
	python3 -m ml.data.llm_annotations download \
		--state $(REPLACEMENT_ADJUDICATION_STATE) \
		--output $(REPLACEMENT_ADJUDICATION_OUTPUT) \
		--key-file .env.annotation

replacement-holdout-validate-adjudication-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output \
		--input $(REPLACEMENT_ADJUDICATION) \
		--output $(REPLACEMENT_ADJUDICATION_OUTPUT) \
		--state $(REPLACEMENT_ADJUDICATION_STATE)

replacement-holdout-prepare-adjudication-retry:
	python3 -m ml.data.llm_annotations prepare-adjudication-retry \
		--input $(REPLACEMENT_ADJUDICATION) \
		--output $(REPLACEMENT_ADJUDICATION_OUTPUT) \
		--retry $(REPLACEMENT_ADJUDICATION_RETRY) \
		--max-output-tokens 1000

replacement-holdout-submit-adjudication-retry:
	python3 -m ml.data.llm_annotations submit \
		--input $(REPLACEMENT_ADJUDICATION_RETRY) \
		--state $(REPLACEMENT_ADJUDICATION_RETRY_STATE) \
		--key-file .env.annotation

replacement-holdout-adjudication-retry-status:
	python3 -m ml.data.llm_annotations status \
		--state $(REPLACEMENT_ADJUDICATION_RETRY_STATE) \
		--key-file .env.annotation

replacement-holdout-adjudication-retry-wait:
	python3 -m ml.data.llm_annotations wait \
		--state $(REPLACEMENT_ADJUDICATION_RETRY_STATE) \
		--key-file .env.annotation \
		--interval-seconds 30

replacement-holdout-adjudication-retry-download:
	python3 -m ml.data.llm_annotations download \
		--state $(REPLACEMENT_ADJUDICATION_RETRY_STATE) \
		--output $(REPLACEMENT_ADJUDICATION_RETRY_OUTPUT) \
		--key-file .env.annotation

replacement-holdout-validate-adjudication-retry-output:
	python3 -m ml.data.llm_annotations validate-adjudication-output \
		--input $(REPLACEMENT_ADJUDICATION_RETRY) \
		--output $(REPLACEMENT_ADJUDICATION_RETRY_OUTPUT) \
		--state $(REPLACEMENT_ADJUDICATION_RETRY_STATE)

replacement-holdout-merge-adjudication-retry:
	python3 -m ml.data.llm_annotations merge-adjudication-retry \
		--input $(REPLACEMENT_ADJUDICATION) \
		--output $(REPLACEMENT_ADJUDICATION_OUTPUT) \
		--retry-input $(REPLACEMENT_ADJUDICATION_RETRY) \
		--retry-output $(REPLACEMENT_ADJUDICATION_RETRY_OUTPUT) \
		--merged $(REPLACEMENT_ADJUDICATION_VALIDATED)

replacement-holdout-import-adjudication:
	python3 -m ml.data.llm_annotations import-adjudication \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--input $(REPLACEMENT_ADJUDICATION) \
		--output $(REPLACEMENT_ADJUDICATION_VALIDATED)

replacement-holdout-export-reviewed:
	python3 -m ml.data.export_annotations \
		--dataset $(REPLACEMENT_HOLDOUT_DATASET) \
		--reviews $(REPLACEMENT_REVIEWS) \
		--output $(REPLACEMENT_REVIEWED_DATASET)

replacement-holdout-validate-reviewed:
	python3 -m ml.data.validate_dataset $(REPLACEMENT_REVIEWED_DATASET) \
		--manifest $(REPLACEMENT_REVIEWED_DATASET:.jsonl=.manifest.json)

train: seed
	python3 -m ml.tabular.train_catboost
	python3 -m ml.fusion.train_fusion

evaluate: train
	python3 -m ml.evaluation.evaluate --dataset ml/data/generated/mandate-cart-pairs.jsonl

train-v2:
	python3 -m ml.tabular.train_catboost --dataset "$(FEATURE_DATASET)"
	python3 -m ml.fusion.train_fusion --dataset "$(FEATURE_DATASET)"

train-fast-track-v2:
	python3 -m ml.tabular.train_catboost \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_FUSION_OUTPUT)
	python3 -m ml.fusion.train_fusion \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_FUSION_OUTPUT)

evaluate-v2:
	python3 -m ml.evaluation.evaluate --dataset "$(FEATURE_DATASET)"

evaluate-fast-track-v2:
	python3 -m ml.evaluation.evaluate \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_FUSION_OUTPUT) \
		--output artifacts/reports/fast-track-v2-golden-evaluation.json

diagnose-fast-track-remediation:
	python3 -m ml.fusion.diagnose_remediation \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_FUSION_OUTPUT) \
		--output artifacts/reports/step20-remediation-diagnosis.json

train-fast-track-v3-no-semantic:
	python3 -m ml.tabular.train_catboost \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/no-semantic \
		--feature-profile shortcut-safe-no-semantic-v2 \
		--target-mode policy_intervention
	python3 -m ml.fusion.train_fusion \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/no-semantic \
		--feature-profile shortcut-safe-no-semantic-v2 \
		--target-mode policy_intervention

train-fast-track-v3-semantic:
	python3 -m ml.tabular.train_catboost \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/with-semantic \
		--feature-profile shortcut-safe-v2 \
		--target-mode policy_intervention
	python3 -m ml.fusion.train_fusion \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/with-semantic \
		--feature-profile shortcut-safe-v2 \
		--target-mode policy_intervention

select-fast-track-v3:
	python3 -m ml.fusion.select_remediation \
		--dataset $(FAST_TRACK_FEATURE_DATASET) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT) \
		--output $(FAST_TRACK_REMEDIATION_SELECTION)

replacement-holdout-semantic-inference:
	PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m ml.semantic.infer_external \
		--dataset $(REPLACEMENT_REVIEWED_DATASET) \
		--semantic-manifest $(FAST_TRACK_SEMANTIC_OUTPUT)/manifest.json \
		--model $(FAST_TRACK_SEMANTIC_OUTPUT)/model \
		--output $(REPLACEMENT_HOLDOUT_SEMANTIC_PREDICTIONS) \
		--batch-size 32

replacement-holdout-features:
	python3 -m ml.features.build_features \
		--dataset $(REPLACEMENT_REVIEWED_DATASET) \
		--semantic-predictions $(REPLACEMENT_HOLDOUT_SEMANTIC_PREDICTIONS) \
		--output $(REPLACEMENT_HOLDOUT_FEATURE_DATASET)

evaluate-fast-track-v3-replacement:
	python3 -m ml.evaluation.evaluate \
		--dataset $(REPLACEMENT_HOLDOUT_FEATURE_DATASET) \
		--training-dataset $(FAST_TRACK_FEATURE_DATASET) \
		--selection-report $(FAST_TRACK_REMEDIATION_SELECTION) \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/with-semantic \
		--output $(STEP23_EVALUATION_REPORT)

diagnose-step24-failure:
	python3 -m ml.fusion.diagnose_step24 \
		--development $(FAST_TRACK_FEATURE_DATASET) \
		--holdout $(REPLACEMENT_HOLDOUT_FEATURE_DATASET) \
		--source ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl \
		--artifacts $(FAST_TRACK_REMEDIATION_OUTPUT)/with-semantic \
		--evaluation-report $(STEP23_EVALUATION_REPORT) \
		--output artifacts/reports/step24-failure-diagnosis.json

promote-v2:
	python3 -m ml.fusion.promote
