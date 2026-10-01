.PHONY: test lint build deploy

test:
	uv run --project . pytest -q

lint:
	uv run --project . ruff check .

build:
	uv run --project . python -m hestia_agents.cli build

deploy:
	uv run --project . python -m hestia_agents.cli deploy
