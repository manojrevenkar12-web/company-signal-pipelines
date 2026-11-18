PY ?= python
export PYTHONPATH := src:.
DBT ?= $(if $(wildcard .dbtvenv/bin/dbt),.dbtvenv/bin/dbt,dbt)

.PHONY: install test lint eval heldout report demo dbt api dagster web

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m venv .dbtvenv && .dbtvenv/bin/pip install -q dbt-core==1.12.7 dbt-postgres==1.11.0

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src evals world tests scripts
	$(PY) -m mypy

eval:
	$(PY) -m evals.run

heldout:
	$(PY) -m evals.run --heldout

report:
	$(PY) -m evals.readme

demo:
	$(PY) -m evals.demo --reset
	cd dbt && ../$(DBT) build --profiles-dir .

dbt:
	cd dbt && ../$(DBT) build --profiles-dir .

api:
	uvicorn signals.service.api:app --reload --port 8000

dagster:
	dagster dev -m signals.orchestration

web:
	cd web && npm install && npm run dev
