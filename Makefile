.PHONY: install test test-integration lint format types serve-api serve-mcp ingest-crop clean

install:
	uv sync --extra dev --extra jupyter

test:
	uv run pytest -m "not integration" --tb=short -q

test-integration:
	uv run pytest -m integration --tb=short -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

types:
	uv run mypy src/ontomcp/

serve-api:
	uv run ontomcp-api

serve-mcp:
	uv run ontomcp-mcp

# Ingest a Crop Ontology's terms into the FTS cache so search_terms finds them
# (AgroPortal serves CO classes by CURIE but never search-indexed some, e.g. rice).
# Usage: make ingest-crop CO=CO_320   |   make ingest-crop ALL=1
ingest-crop:
	uv run ontomcp-ingest-crop $(if $(ALL),--all,$(CO))

clean:
	rm -rf .venv dist build __pycache__ .pytest_cache .mypy_cache .ruff_cache
