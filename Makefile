.PHONY: help install dev lint format test clean docker-build docker-up

help:
	@echo "Shopee Scraper - Available Commands"
	@echo "===================================="
	@echo "install     - Install production dependencies"
	@echo "dev         - Install with dev dependencies"
	@echo "lint        - Run ruff linter"
	@echo "format      - Format code with ruff"
	@echo "test        - Run tests"
	@echo "test-cov    - Run tests with coverage"
	@echo "clean       - Clean cache files"
	@echo "docker-build - Build Docker image"
	@echo "docker-up   - Start Docker containers"
	@echo "docker-dev  - Start dev container"

install:
	uv sync --frozen --no-dev

dev:
	uv sync --frozen
	uv run pre-commit install

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

type-check:
	uv run mypy src

test:
	uv run pytest tests -v

test-cov:
	uv run pytest tests --cov=src/shopee_scraper --cov-report=html

test-unit:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v -m integration

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build -t shopee-scraper .

docker-up:
	docker-compose up -d scraper

docker-dev:
	docker-compose up -d dev
	docker-compose exec dev bash

docker-down:
	docker-compose down
