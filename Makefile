.PHONY: install test test-api test-web test-e2e dev docker-up docker-down seed data-esci data-option1 data-option2 data-option2-uci data-option2-db1b data-option2-usaspending data-option2-amazon data-validate annotate-api llm-prepare llm-submit-a llm-submit-b export-reviews features train-v2 evaluate-v2 promote-v2

install:
	python3 -m pip install -e 'services/api[dev,ml]'
	npm --prefix apps/web install

test: test-api test-web

test-api:
	python3 -m pytest services/api/tests -q
	python3 -m pytest tests -q

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

export-reviews:
	python3 -m ml.data.export_annotations --dataset "$(DATASET)" --reviews "$(REVIEWS)" --output "$(OUTPUT)"

features:
	python3 -m ml.features.build_features --dataset "$(DATASET)" --semantic-predictions "$(SEMANTIC_PREDICTIONS)" --output "$(FEATURE_DATASET)"

.PHONY: train evaluate

train: seed
	python3 -m ml.tabular.train_catboost
	python3 -m ml.fusion.train_fusion

evaluate: train
	python3 -m ml.evaluation.evaluate --dataset ml/data/generated/mandate-cart-pairs.jsonl

train-v2:
	python3 -m ml.tabular.train_catboost --dataset "$(FEATURE_DATASET)"
	python3 -m ml.fusion.train_fusion --dataset "$(FEATURE_DATASET)"

evaluate-v2:
	python3 -m ml.evaluation.evaluate --dataset "$(FEATURE_DATASET)"

promote-v2:
	python3 -m ml.fusion.promote
