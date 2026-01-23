# ============================================================================
# Shopee Scraper - Production Dockerfile
# Using Camoufox (Firefox-based anti-detect browser)
# ============================================================================

# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source code and install project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Fetch Camoufox browser
RUN /app/.venv/bin/python -m camoufox fetch


# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Install system dependencies for Camoufox (Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Firefox dependencies
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libasound2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxss1 \
    libxcursor1 \
    libxfixes3 \
    libpango-1.0-0 \
    libcairo2 \
    # Virtual display for headless
    xvfb \
    # Utilities
    curl \
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user with home directory
RUN groupadd -r scraper && useradd -r -g scraper -m -d /home/scraper scraper

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy Camoufox browser from builder
COPY --from=builder /root/.cache/camoufox /home/scraper/.cache/camoufox

# Copy application code
COPY src ./src
COPY config ./config

# Create data directories and ensure proper ownership
RUN mkdir -p /app/data/output /app/data/sessions /app/logs \
    && chown -R scraper:scraper /app \
    && chown -R scraper:scraper /home/scraper

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Home directory for Camoufox browser profile
    HOME=/home/scraper \
    # Display for Xvfb
    DISPLAY=:99

# Switch to non-root user
USER scraper

# Expose API port
EXPOSE 8000

# Healthcheck - use liveness endpoint (only works when running API)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Default: run API server
# Override with: docker run ... shopee-scraper search "keyword"
CMD ["uvicorn", "shopee_scraper.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
