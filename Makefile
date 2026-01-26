.PHONY: help install dev lint format test clean docker-build docker-up \
        version ci check release docker-push docker-tag git-sync git-tag

# Docker Hub configuration - override with: make docker-push DOCKER_REPO=yourusername/shopee-scraper
DOCKER_REPO ?= jogiia/shopee-scraper
VERSION := $(shell grep -m1 'version = ' pyproject.toml | cut -d'"' -f2)

help:
	@echo "Shopee Scraper - Available Commands"
	@echo "===================================="
	@echo ""
	@echo "Development:"
	@echo "  install      - Install production dependencies"
	@echo "  dev          - Install with dev dependencies"
	@echo "  lint         - Run ruff linter"
	@echo "  format       - Format code with ruff"
	@echo "  type-check   - Run mypy type checker"
	@echo "  test         - Run tests"
	@echo "  test-cov     - Run tests with coverage"
	@echo "  test-unit    - Run unit tests only"
	@echo "  clean        - Clean cache files"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-tag   - Tag image with version and latest"
	@echo "  docker-push  - Push to Docker Hub (requires docker login)"
	@echo "  docker-up    - Start Docker containers"
	@echo "  docker-dev   - Start dev container"
	@echo "  docker-down  - Stop containers"
	@echo ""
	@echo "CI/CD:"
	@echo "  version      - Show current version"
	@echo "  check        - Run all checks (lint + type-check + test)"
	@echo "  ci           - Full CI pipeline (format + check)"
	@echo "  git-sync     - Sync current branch with origin"
	@echo "  git-tag      - Create and push git tag for current version"
	@echo "  release      - Full release (ci + docker-build + docker-push + git-tag)"
	@echo ""
	@echo "Current version: $(VERSION)"
	@echo "Docker repo: $(DOCKER_REPO)"

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

# ============================================================================
# CI/CD Commands
# ============================================================================

version:
	@echo "$(VERSION)"

check: lint type-check test
	@echo "✓ All checks passed"

ci: format check
	@echo "✓ CI pipeline completed"

git-sync:
	@echo "→ Syncing with origin..."
	git fetch origin
	git pull origin $(shell git branch --show-current)
	@echo "✓ Branch synced"

git-tag:
	@echo "→ Creating tag v$(VERSION)..."
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	git push origin v$(VERSION)
	@echo "✓ Tag v$(VERSION) pushed"

docker-tag: docker-build
	@echo "→ Tagging Docker image..."
	docker tag shopee-scraper $(DOCKER_REPO):v$(VERSION)
	docker tag shopee-scraper $(DOCKER_REPO):latest
	@echo "✓ Tagged: $(DOCKER_REPO):v$(VERSION) and $(DOCKER_REPO):latest"

docker-push: docker-tag
	@echo "→ Pushing to Docker Hub..."
	docker push $(DOCKER_REPO):v$(VERSION)
	docker push $(DOCKER_REPO):latest
	@echo "✓ Pushed to Docker Hub: $(DOCKER_REPO)"

release: ci docker-push git-tag
	@echo ""
	@echo "============================================"
	@echo "✓ Release v$(VERSION) completed!"
	@echo "  - Docker: $(DOCKER_REPO):v$(VERSION)"
	@echo "  - Git tag: v$(VERSION)"
	@echo "============================================"
