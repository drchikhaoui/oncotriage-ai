.PHONY: install build dev test ci lint seed clean

install:
	npm install
	uv sync --extra dev

build:
	npm install
	npm run build:css
	uv sync --extra dev

dev:
	@trap 'kill 0' EXIT; \
	npm run build:css -- --watch & \
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -v

ci:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest tests/

lint:
	uv run ruff check app/ tests/ --fix

seed:
	uv run python scripts/seed_demo_data.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	rm -f oncotriage.db
