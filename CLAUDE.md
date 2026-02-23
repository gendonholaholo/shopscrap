# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shopee Scraper is a REST API for scraping Shopee.co.id. It supports two execution modes:
- **Browser mode**: Headless Chrome via `nodriver` (anti-detection)
- **Extension mode**: Chrome Extension connected via WebSocket, intercepting real browser sessions

Three interfaces are exposed: CLI, REST API, and gRPC.

## Common Commands

```bash
# Install dependencies
uv sync

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
                              ┌─────────┴──────────┐
                              │                    │
                         BrowserManager      ExtensionManager
                         (nodriver/Chrome)   (WebSocket gateway)
                                                   │
                                             ExtensionBridge
                                             (raw JSON → models)
```

### Key Components

- **`ShopeeScraper`** (`core/scraper.py`): Main orchestrator. Chooses between browser and extension execution based on `execution_mode` (`auto` | `browser` | `extension`).
- **`BrowserManager`** (`core/browser.py`): Manages Chrome via `nodriver` for anti-detection. Supports proxy pools and session persistence via user data directory.
- **`SessionManager`** (`core/session.py`): Cookie-based login state persistence.
- **Extractors** (`extractors/`): Navigate pages and intercept Shopee's internal API responses via CDP network interception.
- **`ExtensionManager`** (`extension/manager.py`): Manages Chrome Extension WebSocket connections and dispatches tasks to connected extension instances.
- **`ExtensionBridge`** (`extension/bridge.py`): Transforms raw Shopee API JSON captured by the extension into `ProductOutput` models using the same transformer pipeline as extractors.
- **`ScraperService`** (`services/scraper_service.py`): Service layer wrapper used by API/gRPC.

### Data Flow

Extractors intercept Shopee's internal API calls (e.g., `/api/v4/search/search_items`, `/api/v4/pdp/get_pc`) rather than parsing HTML. In extension mode, the Chrome Extension MAIN world content script intercepts these same responses and sends raw JSON back via WebSocket.

### Chrome Extension

Located in `extension/` (Chrome Manifest V3). It connects to the backend via WebSocket at `/api/v1/extension/connect`. The backend dispatches scrape tasks; the extension executes them in a real browser session and returns raw API JSON.

### API Structure

```
/api/v1/
├── session/
│   ├── cookie-upload        POST  # Upload cookies from browser extension
│   └── cookie-status        GET
├── products/
│   ├── scrape-list              POST → job_id  (async)
│   ├── scrape-list-and-details  POST → job_id  (async)
│   ├── {shop_id}/{item_id}      GET            (sync)
│   └── {shop_id}/{item_id}/reviews  GET        (sync)
│       └── /overview            GET            (aggregated stats)
├── jobs/
│   ├── (list)               GET
│   └── {job_id}/
│       ├── (detail)         GET
│       ├── download         GET   # Download results as JSON file
│       └── (cancel)         DELETE
├── extension/
│   ├── status               GET   # List connected extensions
│   └── connect              WS    # Extension WebSocket gateway
├── /ws/jobs/{job_id}        WS    # Real-time job progress
└── /health                  GET   # + /health/live, /health/ready
```

All scraping POST operations are async and return `job_id`. The `execution_mode` parameter (`auto` | `extension` | `browser`) controls which path is used; `auto` prefers extension if connected.

### Price Handling

Shopee returns prices multiplied by 100,000 (e.g., `15000000000` = Rp 150,000). Use `PRICE_DIVISOR` constant from `utils/constants.py` for conversion.

## Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPEE_ENV` | `development` | `development` or `production` |
| `API_AUTH_ENABLED` | `false` | Enable API key auth (always `true` in Docker prod) |
| `API_KEYS` | — | Comma-separated API keys (`sk_...`) |
| `JOB_QUEUE_REDIS_URL` | `redis://localhost:6379/1` | Redis for job queue (DB 1) |
| `RATE_LIMIT_STORAGE` | `memory` | `memory` or `redis` (rate limiter uses DB 0) |
| `PROXY_ENABLED` | `false` | Enable proxy; configure `PROXY_HOST`, `PROXY_PORT` |
| `CAPTCHA_ENABLED` | `false` | Enable CAPTCHA solver |
| `CAPTCHA_API_KEY` | — | SadCaptcha or 2Captcha API key |
| `HEADLESS` | `true` | Browser headless mode |

Session cookies are stored in `./data/sessions/`; output files in `./data/output/`.

## Testing Notes

- `pytest-asyncio` in `auto` mode — all async test functions run without explicit decorator
- Integration tests require `@pytest.mark.integration` marker; run with `uv run pytest tests/integration -v`
- Use `fakeredis` for Redis mocking in unit tests (no real Redis needed)
- Protobuf generated files (`*_pb2*.py`) are excluded from linting and mypy
