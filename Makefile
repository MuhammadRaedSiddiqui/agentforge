.PHONY: lint typecheck test test-all lock install

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy --ignore-missing-imports adapters/ orchestrator/ shared/ agents/ cli/

test:
	pytest -m "unit or contract" --timeout=30 -q

test-all:
	pytest --timeout=60

lock:
	pip-compile --generate-hashes --output-file=requirements-lock.txt pyproject.toml

install:
	pip install -e ".[dev]"
