.PHONY: install test test-api test-web test-e2e dev docker-up docker-down seed

install:
	python3 -m pip install -e 'services/api[dev,ml]'
	npm --prefix apps/web install

test: test-api test-web

test-api:
	python3 -m pytest services/api/tests tests -q

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

.PHONY: train evaluate

train: seed
	python3 -m ml.tabular.train_catboost
	python3 -m ml.fusion.train_fusion

evaluate: train
	python3 -m ml.evaluation.evaluate
