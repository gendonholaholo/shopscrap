# Shopee Scraper - End-to-End Flow

## Prerequisites: Login Session

**PENTING:** Shopee memerlukan login session untuk scraping yang reliable. Tanpa session, scraping akan gagal atau diblokir.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  LANGKAH WAJIB (Sekali, atau saat session expired ~7 hari)                 │
│                                                                            │
│  Terminal:                                                                 │
│  $ uv run shopee-scraper login -u "email" -p "pass" --no-headless         │
│                                                                            │
│  Browser terbuka → Login manual → Solve CAPTCHA jika ada → Session saved  │
│                                                                            │
│  Output: ./data/sessions/default_cookies.json                              │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│                              USER INPUT                                         │
│                                  │                                              │
│                 ┌────────────────┴────────────────┐                             │
│                 │                                 │                             │
│                 ▼                                 ▼                             │
│  ┌──────────────────────────┐      ┌──────────────────────────────────┐        │
│  │      CLI (Terminal)      │      │         REST API (HTTP)          │        │
│  │                          │      │                                  │        │
│  │  shopee-scraper search   │      │  POST /products/scrape-list      │        │
│  │  shopee-scraper product  │      │  POST /products/scrape-list-and- │        │
│  │  shopee-scraper reviews  │      │       details                    │        │
│  │  shopee-scraper scrape   │      │  GET  /products/{id}/{id}        │        │
│  │  shopee-scraper login    │      │  GET  /products/.../reviews      │        │
│  └────────────┬─────────────┘      └───────────────┬──────────────────┘        │
│               │                                    │                            │
│               │                    ┌───────────────┴───────────────┐            │
│               │                    │                               │            │
│               │                    ▼                               ▼            │
│               │         ┌──────────────────┐            ┌──────────────────┐   │
│               │         │   MIDDLEWARE     │            │  BACKGROUND JOB  │   │
│               │         │                  │            │                  │   │
│               │         │  1. CORS Check   │            │  JobQueue        │   │
│               │         │  2. Rate Limit   │            │  └── Workers     │   │
│               │         │  3. Auth Check   │            │      process     │   │
│               │         │                  │            │      async       │   │
│               │         └────────┬─────────┘            └────────┬─────────┘   │
│               │                  │                               │              │
│               └──────────────────┼───────────────────────────────┘              │
│                                  │                                              │
│                                  ▼                                              │
│               ┌──────────────────────────────────────────┐                      │
│               │            SESSION CHECK                 │                      │
│               │                                          │                      │
│               │  Load: ./data/sessions/default_cookies   │                      │
│               │                                          │                      │
│               │  ┌─────────────┐      ┌──────────────┐   │                      │
│               │  │Session Valid│      │Session Expired│  │                      │
│               │  │  (< 7 days) │      │  or Missing   │  │                      │
│               │  └──────┬──────┘      └──────┬───────┘   │                      │
│               │         │                    │           │                      │
│               │         │                    ▼           │                      │
│               │         │         ┌──────────────────┐   │                      │
│               │         │         │ ⚠ LOGIN REQUIRED │   │                      │
│               │         │         │ via CLI first!   │   │                      │
│               │         │         └──────────────────┘   │                      │
│               │         │                                │                      │
│               └─────────┼────────────────────────────────┘                      │
│                         │                                                       │
│                         ▼                                                       │
│               ┌──────────────────────────────────────────┐                      │
│               │           SHOPEE SCRAPER                 │                      │
│               │                                          │                      │
│               │  ShopeeScraper (orchestrator)            │                      │
│               │  └── BrowserManager (Camoufox)           │                      │
│               │      └── Anti-detect browser             │                      │
│               │      └── Human-like behavior             │                      │
│               │      └── Proxy support (optional)        │                      │
│               │                                          │                      │
│               └─────────────────┬────────────────────────┘                      │
│                                 │                                               │
│                                 ▼                                               │
│               ┌──────────────────────────────────────────┐                      │
│               │           EXTRACTORS                     │                      │
│               │                                          │                      │
│               │  Pilih berdasarkan operasi:              │                      │
│               │                                          │                      │
│               │  ┌─────────────────────────────────────┐ │                      │
│               │  │ SearchExtractor                     │ │                      │
│               │  │ - Navigate: shopee.co.id/search?... │ │                      │
│               │  │ - Intercept: /api/v4/search/...     │ │                      │
│               │  │ - Parse: list of products           │ │                      │
│               │  └─────────────────────────────────────┘ │                      │
│               │                                          │                      │
│               │  ┌─────────────────────────────────────┐ │                      │
│               │  │ ProductExtractor                    │ │                      │
│               │  │ - Navigate: shopee.co.id/product/.. │ │                      │
│               │  │ - Intercept: /api/v4/pdp/get_pc     │ │                      │
│               │  │ - Parse: product details            │ │                      │
│               │  └─────────────────────────────────────┘ │                      │
│               │                                          │                      │
│               │  ┌─────────────────────────────────────┐ │                      │
│               │  │ ReviewExtractor                     │ │                      │
│               │  │ - Navigate: product page            │ │                      │
│               │  │ - Scroll to reviews section         │ │                      │
│               │  │ - Intercept: /api/v4/pdp/get_rw     │ │                      │
│               │  │ - Parse: list of reviews            │ │                      │
│               │  └─────────────────────────────────────┘ │                      │
│               │                                          │                      │
│               └─────────────────┬────────────────────────┘                      │
│                                 │                                               │
│                                 ▼                                               │
│               ┌──────────────────────────────────────────┐                      │
│               │           DATA PROCESSING                │                      │
│               │                                          │                      │
│               │  Raw Shopee Data:                        │                      │
│               │  { "price": 15000000000 }  ← x100000     │                      │
│               │                                          │                      │
│               │  Parsers (utils/parsers.py):             │                      │
│               │  - parse_price("Rp 150.000") → 150000    │                      │
│               │  - parse_sold_count("1,2rb") → 1200      │                      │
│               │  - price / PRICE_DIVISOR → actual IDR    │                      │
│               │                                          │                      │
│               │  Normalized Output:                      │                      │
│               │  { "price": 150000 }  ← actual IDR       │                      │
│               │                                          │                      │
│               └─────────────────┬────────────────────────┘                      │
│                                 │                                               │
│                                 ▼                                               │
│               ┌──────────────────────────────────────────┐                      │
│               │              OUTPUT                      │                      │
│               │                                          │                      │
│               │  CLI:                                    │                      │
│               │  ├── Console table (Rich)                │                      │
│               │  └── JSON file: ./data/output/*.json     │                      │
│               │                                          │                      │
│               │  API:                                    │                      │
│               │  └── JSON Response:                      │                      │
│               │      {                                   │                      │
│               │        "success": true,                  │                      │
│               │        "data": [...],                    │                      │
│               │        "meta": { "total_count": 120 }    │                      │
│               │      }                                   │                      │
│               │                                          │                      │
│               └──────────────────────────────────────────┘                      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

### Entry Points

| Method | Command/Endpoint | Output |
|--------|------------------|--------|
| CLI | `shopee-scraper search "keyword"` | Console + JSON file |
| CLI | `shopee-scraper product {shop_id} {item_id}` | Console + JSON file |
| CLI | `shopee-scraper reviews {shop_id} {item_id}` | Console + JSON file |
| CLI | `shopee-scraper login -u "email" -p "pass"` | Session cookies |
| API | `POST /api/v1/products/scrape-list` | Job ID (async) |
| API | `POST /api/v1/products/scrape-list-and-details` | Job ID (async) |
| API | `GET /api/v1/products/{shop_id}/{item_id}` | JSON response |
| API | `GET /api/v1/products/.../reviews` | JSON response |
| API | `GET /api/v1/products/.../reviews/overview` | JSON response |

### API Flow (Async Scraping)

```
1. Submit Job
   POST /api/v1/products/scrape-list
   Body: { "keyword": "laptop", "max_pages": 3 }
   → { "data": { "id": "job_abc123", "status": "pending" } }

2. Poll Status
   GET /api/v1/jobs/job_abc123/status
   → { "data": { "status": "processing", "progress": 45 } }
   ... (repeat until completed)

3. Get Result
   GET /api/v1/jobs/job_abc123
   → { "data": { "status": "completed", "result": [...] } }
```

### Middleware (API Only)

```
Request → CORS → Rate Limit → Auth → Handler → Response
              │            │       │
              │            │       └── 401 if invalid API key
              │            └── 429 if over limit
              └── Blocked if origin not allowed
```

### Key Files

| Component | File |
|-----------|------|
| CLI | `cli.py` |
| API | `api/main.py` |
| Core | `core/scraper.py` |
| Browser | `core/browser.py` |
| Session | `core/session.py` |
| Extractors | `extractors/search.py`, `product.py`, `review.py` |
| Storage | `storage/json_storage.py` |
| Config | `utils/config.py` |
| Constants | `utils/constants.py` |
| Parsers | `utils/parsers.py` |

### Session Management

```bash
# Login (wajib, sekali atau saat expired)
uv run shopee-scraper login -u "email" -p "pass" --no-headless

# Check session
ls -la ./data/sessions/

# Clear session
uv run shopee-scraper clear-session
```

Session berlaku ~7 hari. Jika muncul error "Cookies expired", login ulang.
