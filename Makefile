# CloudDash — common dev tasks
# Run `make help` for the menu.

.PHONY: help install install-dev ingest run cli test eval lint format typecheck clean deploy-render

PYTHON := python3.13
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

install: $(VENV)/bin/activate  ## Install runtime dependencies
	$(PIP) install -e .

install-dev: $(VENV)/bin/activate  ## Install dev dependencies (pytest, ruff, mypy)
	$(PIP) install -e ".[dev]"

ingest:  ## Ingest the knowledge base into ChromaDB
	$(PY) -m clouddash.scripts.ingest_kb

run:  ## Run the FastAPI server (with hot reload)
	$(VENV)/bin/uvicorn clouddash.api.app:app --reload --host 0.0.0.0 --port 8020

cli:  ## Run the interactive CLI chat
	$(PY) -m clouddash.cli.main chat

test:  ## Run the test suite
	$(VENV)/bin/pytest

test-fast:  ## Run only fast tests (skip integration/slow)
	$(VENV)/bin/pytest -m "not slow and not integration"

eval:  ## Run the LLM-as-judge eval harness on the 4 official scenarios
	$(PY) -m clouddash.evals.run

lint:  ## Lint with ruff
	$(VENV)/bin/ruff check src/ tests/

format:  ## Format with ruff
	$(VENV)/bin/ruff format src/ tests/

typecheck:  ## Type-check with mypy
	$(VENV)/bin/mypy src/

check: lint typecheck test-fast  ## Run all quality checks

clean:  ## Remove build artifacts and caches
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-all: clean  ## Also wipe the virtualenv and ChromaDB
	rm -rf $(VENV) data/chroma logs/*.jsonl

# --- Demo helpers ----
demo-scenario-1:  ## Demo: single-agent (alerts after AWS update)
	$(PY) -m clouddash.scripts.demo --scenario 1

demo-scenario-2:  ## Demo: cross-agent handover (SSO + upgrade)
	$(PY) -m clouddash.scripts.demo --scenario 2

demo-scenario-3:  ## Demo: escalation (double charge)
	$(PY) -m clouddash.scripts.demo --scenario 3

demo-scenario-4:  ## Demo: KB miss (Datadog)
	$(PY) -m clouddash.scripts.demo --scenario 4

demo-add-agent:  ## Live demo: add an Onboarding Agent in 60s
	$(PY) -m clouddash.scripts.demo_add_agent
