# Shopee Scraper

High-performance Shopee.co.id scraper using Camoufox anti-detect browser.

## Features

- **Anti-Detection**: Uses Camoufox with 0% detection rate on CreepJS
- **Search Products**: Search by keyword with pagination
- **Product Details**: Extract full product information
- **Reviews**: Get product reviews with pagination
- **Proxy Support**: Residential proxy rotation for Indonesia
- **Session Persistence**: Cookie-based login state management

## Installation

```bash
# Install dependencies
uv sync

# Install Camoufox browser
camoufox fetch
```

## Usage

```bash
# Login (required once)
uv run shopee-scraper login

# Search products
uv run shopee-scraper search "laptop gaming" --max-pages 2

# Get product detail
uv run shopee-scraper product <shop_id> <item_id>

# Get reviews
uv run shopee-scraper reviews <shop_id> <item_id> --max-pages 3
```

## Configuration

Set environment variables or create `.env` file:

```env
# Proxy (optional)
PROXY_HOST=your.proxy.com
PROXY_PORT=8080
PROXY_USERNAME=user
PROXY_PASSWORD=pass

# Shopee credentials
SHOPEE_USERNAME=your_username
SHOPEE_PASSWORD=your_password
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed architecture diagrams.

## License

MIT
