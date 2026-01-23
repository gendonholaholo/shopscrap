# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shopee Scraper is a high-performance web scraper for Shopee.co.id using Camoufox anti-detect browser. It provides three interfaces: CLI, REST API, and gRPC.

## Common Commands

```bash
# Install dependencies
uv sync

# Install Camoufox browser (required)
camoufox fetch

# Run CLI
uv run shopee-scraper search "keyword" --max-pages 2
uv run shopee-scraper product <shop_id> <item_id>
uv run shopee-scraper reviews <shop_id> <item_id>
uv run shopee-scraper login  # Required for authenticated scraping

# Run API server
uv run uvicorn shopee_scraper.api.main:app --reload

# Linting and formatting
uv run ruff check src tests
uv run ruff format src tests
uv run ruff check --fix src tests

# Type checking
uv run mypy src

# Testing
uv run pytest tests -v                    # All tests
uv run pytest tests/unit -v               # Unit tests only
uv run pytest tests/integration -v        # Integration tests only
uv run pytest tests -k "test_name" -v     # Single test by name
uv run pytest tests --cov=src/shopee_scraper --cov-report=html  # With coverage

# Docker
docker-compose up -d api redis
```

## Architecture

### Layer Structure

```
CLI (cli.py) ─────────────────┐
                              ├──► ScraperService ──► ShopeeScraper ──► Extractors
REST API (api/) ──────────────┤         │                   │
                              │         │                   ├── SearchExtractor
gRPC (grpc/) ─────────────────┘         │                   ├── ProductExtractor
                                        │                   └── ReviewExtractor
                                        │
                                        └──► BrowserManager (Camoufox)
```

### Key Components

- **`ShopeeScraper`** (`core/scraper.py`): Main orchestrator that coordinates browser, session, and extractors
- **`BrowserManager`** (`core/browser.py`): Manages Camoufox anti-detect browser instances
- **`SessionManager`** (`core/session.py`): Cookie-based login state persistence
- **Extractors** (`extractors/`): Navigate pages and intercept Shopee's internal API responses
- **`ScraperService`** (`services/scraper_service.py`): Service layer wrapper used by API/gRPC

### Data Flow

Extractors work by intercepting Shopee's internal API calls (e.g., `/api/v4/search/search_items`, `/api/v4/pdp/get_pc`) rather than parsing HTML. This is more reliable as Shopee's API responses are structured JSON.

### API Structure

```
/api/v1/
├── session/           # Cookie management (browser extension upload)
│   ├── cookie-upload  POST
│   └── cookie-status  GET
├── products/          # Scraping operations (async)
│   ├── scrape-list              POST → returns job_id
│   ├── scrape-list-and-details  POST → returns job_id
│   └── {shop_id}/{item_id}      GET  → sync direct access
├── jobs/              # Job management
│   ├── (list)         GET
│   └── {job_id}/
│       ├── (detail)   GET
│       ├── status     GET
│       └── (cancel)   DELETE
└── /health            # Health checks
```

All scraping operations are async and return a `job_id`. Poll `/jobs/{job_id}/status` until completed.

### Price Handling

Shopee returns prices multiplied by 100,000 (e.g., `15000000000` = Rp 150,000). Use `PRICE_DIVISOR` constant from `utils/constants.py` for conversion.

## Configuration

Environment variables in `.env`:
- `SHOPEE_ENV`: development | production
- `API_AUTH_ENABLED`: Enable API key authentication
- `RATE_LIMIT_ENABLED`: Enable rate limiting
- Session cookies stored in `./data/sessions/`
- Output files in `./data/output/`

## Testing Notes

- Use `pytest-asyncio` for async tests (mode is set to "auto")
- Integration tests require `@pytest.mark.integration` marker
- Protobuf generated files (`*_pb2*.py`) are excluded from linting
