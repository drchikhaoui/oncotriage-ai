.PHONY: install dev test ci lint seed clean

install:
	uv sync --extra dev

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -v

ci:
	uv run ruff check app/ tests/
	uv run pytest --tb=short -q

lint:
	uv run ruff check app/ tests/ --fix

seed:
	uv run python scripts/seed_demo_data.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	rm -f oncotriage.db
