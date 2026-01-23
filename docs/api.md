# Shopee Scraper API Documentation

## Overview

RESTful API for scraping product data from Shopee.co.id using Camoufox anti-detect browser.

**Base URL:** `http://localhost:8000/api/v1`

## Quick Start

### 1. Start the API Server

```bash
# Local development
uv run uvicorn shopee_scraper.api.main:app --reload

# Docker (production)
docker-compose up -d api
```

### 2. Access Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Authentication

### API Key (Optional)

When `API_AUTH_ENABLED=true`, all endpoints require an API key.

**Passing API Key:**

```bash
# Via Header (recommended)
curl -H "X-API-Key: sk_your_api_key" http://localhost:8000/api/v1/session/cookie-status

# Via Query Parameter
curl "http://localhost:8000/api/v1/session/cookie-status?api_key=sk_your_api_key"
```

**Generate API Key:**

```bash
python -c "import secrets; print(f'sk_{secrets.token_hex(24)}')"
```

---

## Rate Limiting

When `RATE_LIMIT_ENABLED=true`:

| Limit | Value |
|-------|-------|
| Per Minute | 60 requests |
| Per Hour | 1000 requests |

**Rate Limit Headers:**

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1704067200
```

---

## Endpoints

### Session (Cookie Management)

#### `POST /api/v1/session/cookie-upload`
Upload cookies from browser extension.

```bash
curl -X POST http://localhost:8000/api/v1/session/cookie-upload \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_your_api_key" \
  -d '{
    "cookies": [
      {"name": "SPC_EC", "value": "...", "domain": ".shopee.co.id"},
      {"name": "SPC_ST", "value": "...", "domain": ".shopee.co.id"}
    ]
  }'
```

**Response:**

```json
{
  "success": true,
  "message": "Cookies uploaded successfully",
  "data": {
    "cookies_count": 15,
    "uploaded_at": "2024-01-01T00:00:00",
    "expires_at": "2024-01-08T00:00:00"
  }
}
```

#### `GET /api/v1/session/cookie-status`
Check if uploaded cookies exist and are still valid.

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/session/cookie-status
```

**Response (Valid):**

```json
{
  "success": true,
  "data": {
    "has_session": true,
    "valid": true,
    "cookies_count": 15,
    "uploaded_at": "2024-01-01T00:00:00",
    "expires_at": "2024-01-08T00:00:00",
    "days_remaining": 6
  }
}
```

**Response (Expired):**

```json
{
  "success": true,
  "data": {
    "has_session": true,
    "valid": false,
    "expired_at": "2024-01-08T00:00:00",
    "message": "Session expired. Please re-login and upload new cookies."
  }
}
```

---

### Products (Scraping Operations)

#### `POST /api/v1/products/scrape-list`
Scrape product list by keyword (async job).

```bash
curl -X POST http://localhost:8000/api/v1/products/scrape-list \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_your_api_key" \
  -d '{
    "keyword": "laptop gaming",
    "max_pages": 3,
    "sort_by": "sales"
  }'
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| keyword | string | Yes | Search term |
| max_pages | int | No | Pages to scrape (1-10, default: 1) |
| sort_by | string | No | Sort order: relevancy, sales, price_asc, price_desc |

**Response (202 Accepted):**

```json
{
  "success": true,
  "message": "Job submitted successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "scrape_list",
    "status": "pending",
    "created_at": "2024-01-01T00:00:00"
  },
  "links": {
    "self": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
    "status": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/status"
  }
}
```

#### `POST /api/v1/products/scrape-list-and-details`
Scrape product list with full details (async job).

```bash
curl -X POST http://localhost:8000/api/v1/products/scrape-list-and-details \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_your_api_key" \
  -d '{
    "keyword": "laptop gaming",
    "max_products": 20,
    "include_reviews": true
  }'
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| keyword | string | Yes | Search term |
| max_products | int | No | Max products (1-100, default: 10) |
| include_reviews | bool | No | Include reviews (default: false) |

**Response (202 Accepted):**

```json
{
  "success": true,
  "message": "Job submitted successfully",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "type": "scrape_list_and_details",
    "status": "pending",
    "created_at": "2024-01-01T00:00:00"
  },
  "links": {
    "self": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440001",
    "status": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440001/status"
  }
}
```

#### `GET /api/v1/products/{shop_id}/{item_id}`
Get detailed product information (sync).

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/products/87654321/12345678
```

**Response:**

```json
{
  "success": true,
  "data": {
    "item_id": 12345678,
    "shop_id": 87654321,
    "name": "Product Name",
    "description": "Full description...",
    "price": 150000,
    "stock": 100,
    "sold": 500,
    "rating": 4.8,
    "images": ["https://..."],
    "variations": [...],
    "shop": {
      "name": "Shop Name",
      "rating": 4.9
    }
  },
  "links": {
    "self": "/api/v1/products/87654321/12345678",
    "reviews": "/api/v1/products/87654321/12345678/reviews"
  }
}
```

---

### Reviews

#### `GET /api/v1/products/{shop_id}/{item_id}/reviews`
Get product reviews.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| max_reviews | int | No | Max reviews (1-500, default: 100) |

**Example:**

```bash
curl -H "X-API-Key: sk_your_api_key" \
  "http://localhost:8000/api/v1/products/87654321/12345678/reviews?max_reviews=50"
```

**Response:**

```json
{
  "success": true,
  "message": "Found 50 reviews",
  "meta": {
    "shop_id": 87654321,
    "item_id": 12345678,
    "total_count": 50
  },
  "data": [
    {
      "rating": 5,
      "comment": "Great product!",
      "author": {
        "username": "user123"
      },
      "images": [],
      "likes": 10
    }
  ]
}
```

#### `GET /api/v1/products/{shop_id}/{item_id}/reviews/overview`
Get review statistics.

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/products/87654321/12345678/reviews/overview
```

**Response:**

```json
{
  "success": true,
  "data": {
    "total_reviews": 500,
    "average_rating": 4.7,
    "rating_distribution": {
      "5": 350,
      "4": 100,
      "3": 30,
      "2": 15,
      "1": 5
    }
  }
}
```

---

### Jobs (Management)

#### `GET /api/v1/jobs`
List all jobs.

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/jobs
```

#### `GET /api/v1/jobs/{job_id}`
Get job details and results.

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
```

**Response (Completed):**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "scrape_list",
    "status": "completed",
    "created_at": "2024-01-01T00:00:00",
    "completed_at": "2024-01-01T00:01:30",
    "result": {
      "products": [...],
      "total_count": 180
    }
  }
}
```

#### `GET /api/v1/jobs/{job_id}/status`
Quick status check (for polling).

```bash
curl -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/status
```

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "processing",
    "progress": 45
  }
}
```

#### `DELETE /api/v1/jobs/{job_id}`
Cancel pending job.

```bash
curl -X DELETE -H "X-API-Key: sk_your_api_key" \
  http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

### Health Check

#### `GET /health`
Comprehensive health check with component status.

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "scraper_ready": true,
  "browser_available": true,
  "components": [...]
}
```

#### `GET /health/live`
Kubernetes liveness probe.

#### `GET /health/ready`
Kubernetes readiness probe.

---

## Error Handling

### Error Response Format

```json
{
  "success": false,
  "error": "Error type",
  "detail": "Detailed error message"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 202 | Accepted (async job submitted) |
| 400 | Bad Request |
| 401 | Unauthorized (invalid API key) |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |

---

## Configuration

### Environment Variables

```bash
# General
SHOPEE_ENV=production        # development | production
SHOPEE_DEBUG=false

# Authentication
API_AUTH_ENABLED=true
API_KEYS=sk_key1,sk_key2

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_REQUESTS_PER_HOUR=1000
RATE_LIMIT_STORAGE=redis
RATE_LIMIT_REDIS_URL=redis://localhost:6379

# CORS
CORS_ENABLED=true
CORS_ALLOW_ORIGINS=https://yourdomain.com
CORS_ALLOW_CREDENTIALS=true
```

---

## Docker Deployment

### Quick Start

```bash
# Start API with Redis
docker-compose up -d api redis

# View logs
docker-compose logs -f api

# Stop
docker-compose down
```

### Production Setup

```bash
# Create .env file
cp .env.example .env

# Edit .env with your settings
nano .env

# Start with production settings
docker-compose up -d api redis
```

### Scaling

```bash
# Scale API instances (requires load balancer)
docker-compose up -d --scale api=3
```

---

## SDK Examples

### Python

```python
import httpx

API_URL = "http://localhost:8000/api/v1"
API_KEY = "sk_your_api_key"

headers = {"X-API-Key": API_KEY}

# Check session status
response = httpx.get(f"{API_URL}/session/cookie-status", headers=headers)
session = response.json()["data"]
print(f"Session valid: {session['valid']}")

# Submit scrape job
response = httpx.post(
    f"{API_URL}/products/scrape-list",
    json={"keyword": "laptop", "max_pages": 2},
    headers=headers,
)
job = response.json()["data"]
job_id = job["id"]

# Poll for completion
import time
while True:
    response = httpx.get(f"{API_URL}/jobs/{job_id}/status", headers=headers)
    status = response.json()["data"]["status"]
    if status == "completed":
        break
    time.sleep(2)

# Get results
response = httpx.get(f"{API_URL}/jobs/{job_id}", headers=headers)
result = response.json()["data"]["result"]
print(f"Found {len(result['products'])} products")
```

### JavaScript/TypeScript

```javascript
const API_URL = "http://localhost:8000/api/v1";
const API_KEY = "sk_your_api_key";
const headers = { "X-API-Key": API_KEY };

// Check session status
const sessionRes = await fetch(`${API_URL}/session/cookie-status`, { headers });
const { data: session } = await sessionRes.json();
console.log(`Session valid: ${session.valid}`);

// Submit scrape job
const jobRes = await fetch(`${API_URL}/products/scrape-list`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ keyword: "laptop", max_pages: 2 }),
});
const { data: job } = await jobRes.json();

// Poll for completion
let status = "pending";
while (status !== "completed") {
  await new Promise((r) => setTimeout(r, 2000));
  const statusRes = await fetch(`${API_URL}/jobs/${job.id}/status`, { headers });
  status = (await statusRes.json()).data.status;
}

// Get results
const resultRes = await fetch(`${API_URL}/jobs/${job.id}`, { headers });
const { data: result } = await resultRes.json();
console.log(`Found ${result.result.products.length} products`);
```

### cURL

```bash
# Check session status
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/session/cookie-status"

# Submit scrape-list job
curl -X POST \
  -H "X-API-Key: sk_your_key" \
  -H "Content-Type: application/json" \
  -d '{"keyword":"laptop","max_pages":2}' \
  "http://localhost:8000/api/v1/products/scrape-list"

# Check job status
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/jobs/{job_id}/status"

# Get job result
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/jobs/{job_id}"

# Get single product (sync)
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/products/87654321/12345678"

# Get reviews
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/products/87654321/12345678/reviews?max_reviews=50"

# Get review overview
curl -H "X-API-Key: sk_your_key" \
  "http://localhost:8000/api/v1/products/87654321/12345678/reviews/overview"
```

---

## Troubleshooting

### Common Issues

**401 Unauthorized**
- Check if `API_AUTH_ENABLED=true` and you provided valid API key
- Verify API key format: `sk_xxxx...`

**429 Too Many Requests**
- Rate limit exceeded
- Wait for `X-RateLimit-Reset` timestamp
- Consider reducing request frequency

**500 Internal Server Error**
- Check logs: `docker-compose logs api`
- Verify Camoufox browser is available
- Check network connectivity to Shopee

**CORS Errors**
- Add your domain to `CORS_ALLOW_ORIGINS`
- Check if `CORS_ALLOW_CREDENTIALS` matches your setup

### Debug Mode

```bash
# Enable debug mode for detailed errors
SHOPEE_DEBUG=true docker-compose up api
```

---

## Support

- GitHub Issues: https://github.com/yourusername/shopee-scraper/issues
- Documentation: https://github.com/yourusername/shopee-scraper/docs
