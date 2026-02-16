# Shopee Scraper

REST API for scraping Shopee.co.id product data. Supports headless browser and Chrome Extension execution modes.

```
docker pull jogiia/shopee-scraper
```

## Quick Start

```bash
cp .env.example .env        # configure API_KEYS, proxy, etc.
docker-compose up -d api redis
curl http://localhost:8000/health
```

## API Endpoints

Base URL: `/api/v1`

### Products

| Method | Path | Description |
|--------|------|-------------|
| POST | `/products/scrape-list` | Scrape product list by keyword (async, returns `job_id`) |
| POST | `/products/scrape-list-and-details` | Scrape products + full details (async, returns `job_id`) |
| GET | `/products/{shop_id}/{item_id}` | Get single product detail (sync) |
| GET | `/products/{shop_id}/{item_id}/reviews` | Get product reviews |
| GET | `/products/{shop_id}/{item_id}/reviews/overview` | Aggregated review statistics |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs` | List all jobs (filter by `?status=`) |
| GET | `/jobs/{job_id}` | Job detail + results |
| GET | `/jobs/{job_id}/download` | Download results as JSON file |
| DELETE | `/jobs/{job_id}` | Cancel a pending/running job |
| WebSocket | `/ws/jobs/{job_id}` | Real-time job progress |

### Session

| Method | Path | Description |
|--------|------|-------------|
| POST | `/session/cookie-upload` | Upload cookies from browser extension |
| GET | `/session/cookie-status` | Check cookie validity |

### Extension

| Method | Path | Description |
|--------|------|-------------|
| GET | `/extension/status` | List connected extensions |
| WebSocket | `/extension/connect` | Extension WebSocket gateway |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Full health check |
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe |

## Chrome Extension

The Chrome Extension lets the API scrape through a real browser session, bypassing anti-bot detection entirely.

**Install:**

1. Open `chrome://extensions` and enable Developer mode
2. Click "Load unpacked" and select the `extension/` directory
3. Click the extension icon, set backend URL to `ws://localhost:8000/api/v1/extension/connect`
4. Click Connect

**How it works:**

1. Extension connects to backend via WebSocket
2. Backend dispatches scraping tasks (search, product, reviews)
3. Extension navigates Shopee pages in your real Chrome
4. A MAIN world content script intercepts Shopee's internal API responses
5. Raw JSON is sent back to the backend and transformed into structured output

The API supports an `execution_mode` parameter on scrape jobs: `"auto"` (default, prefers extension), `"extension"` (requires connection), or `"browser"` (headless only).

## Configuration

Key environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPEE_ENV` | `development` | `development` or `production` |
| `API_AUTH_ENABLED` | `true` (prod) | Enable API key auth |
| `API_KEYS` | — | Comma-separated API keys |
| `CORS_ALLOW_ORIGINS` | `*` | Allowed CORS origins |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `JOB_QUEUE_MAX_CONCURRENT` | `3` | Max concurrent scrape jobs |
| `JOB_QUEUE_HANDLER_TIMEOUT_SECONDS` | `3600` | Job timeout (seconds) |
| `PROXY_ENABLED` | `false` | Enable residential proxy |
| `PROXY_HOST` | — | Proxy hostname |
| `CAPTCHA_ENABLED` | `false` | Enable CAPTCHA solver |
| `CAPTCHA_API_KEY` | — | SadCaptcha / 2Captcha key |

## Development

```bash
uv sync                              # install dependencies
uv run ruff check src tests           # lint
uv run ruff format src tests          # format
uv run mypy src                       # type check
uv run pytest tests -v                # run all tests
uv run pytest tests/unit -v           # unit tests only
uv run pytest tests/integration -v    # integration tests
```

Run the API locally:

```bash
uv run uvicorn shopee_scraper.api.main:app --reload
```

## Docker

Build and push for `linux/amd64`:

```bash
make docker-build    # build image
make docker-tag      # tag as jogiia/shopee-scraper:v{VERSION} + :latest
make docker-push     # push to Docker Hub
```

## License

MIT
