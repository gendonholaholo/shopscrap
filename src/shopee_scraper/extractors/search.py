"""Search results extractor for Shopee."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from shopee_scraper.extractors.base import BaseExtractor
from shopee_scraper.utils.constants import (
    BASE_URL,
    PRICE_DIVISOR,
    SEARCH_API,
    SEARCH_API_PATTERNS,
)
from shopee_scraper.utils.logging import get_logger
from shopee_scraper.utils.network_interceptor import NetworkInterceptor
from shopee_scraper.utils.parsers import parse_price, parse_sold_count


if TYPE_CHECKING:
    from shopee_scraper.core.browser import BrowserManager, Page
    from shopee_scraper.utils.captcha_solver import CaptchaSolver

logger = get_logger(__name__)


class SearchExtractor(BaseExtractor):
    """
    Extract search results from Shopee.

    Uses a two-tier extraction strategy:
    1. Primary: Network interception (CDP) - captures Shopee's internal API responses
    2. Fallback: DOM extraction - parses page elements when API interception fails

    Network interception is more reliable as API response structures change
    less frequently than DOM selectors.
    """

    def __init__(
        self,
        browser: BrowserManager,
        captcha_solver: CaptchaSolver | None = None,
    ) -> None:
        """
        Initialize search extractor.

        Args:
            browser: BrowserManager instance
            captcha_solver: Optional CaptchaSolver for auto-solving captchas
        """
        self.browser = browser
        self.captcha_solver = captcha_solver
        self._use_network_interception = True  # Primary strategy

    async def search(
        self,
        keyword: str,
        max_pages: int = 1,
        sort_by: str = "relevancy",
    ) -> list[dict[str, Any]]:
        """
        Search products by keyword.

        Uses network interception (CDP) as primary strategy to capture
        Shopee's internal API responses. Falls back to DOM extraction
        if network interception fails.

        Args:
            keyword: Search keyword
            max_pages: Maximum pages to scrape (60 items per page)
            sort_by: Sort order (relevancy, sales, price_asc, price_desc)

        Returns:
            List of product dictionaries
        """
        logger.info(
            "Starting search",
            keyword=keyword,
            max_pages=max_pages,
            sort_by=sort_by,
            strategy="network_interception"
            if self._use_network_interception
            else "dom",
        )

        all_products: list[dict[str, Any]] = []

        # Map sort options to Shopee URL params
        sort_url_map = {
            "relevancy": "relevancy",
            "sales": "ctime",
            "price_asc": "price",
            "price_desc": "price",
        }
        order_url = "asc" if sort_by == "price_asc" else "desc"

        page = await self.browser.new_page()
        interceptor: NetworkInterceptor | None = None

        try:
            # Setup network interception if enabled
            if self._use_network_interception:
                interceptor = NetworkInterceptor(page)
                await interceptor.start(SEARCH_API_PATTERNS)
                logger.debug("Network interception enabled")

            await self.browser.random_delay(1.0, 2.0)

            for page_num in range(max_pages):
                logger.info(f"Scraping page {page_num + 1}/{max_pages}")

                # Clear previous responses for new page
                if interceptor:
                    interceptor.clear_responses()

                search_url = (
                    f"{BASE_URL}/search?keyword={quote(keyword)}"
                    f"&page={page_num}"
                    f"&sortBy={sort_url_map.get(sort_by, 'relevancy')}"
                    f"&order={order_url}"
                )

                # Navigate to search page (with retry on verify redirect)
                products_loaded = await self._navigate_with_retry(
                    page, search_url, max_retries=3
                )
                if not products_loaded:
                    current_url = page.target.url or ""
                    if "/buyer/login" in current_url:
                        logger.error(
                            "Redirected to login - run 'shopee-scraper login' first."
                        )
                        break

                    # IMPORTANT: Try to extract from interceptor before giving up!
                    # Shopee sends API response BEFORE redirecting to verify page.
                    # The data might already be in the interceptor.
                    if interceptor:
                        logger.info(
                            "Navigate blocked by verification, but checking interceptor for data..."
                        )
                        salvaged_products = await self._extract_from_network(
                            interceptor, timeout=2.0
                        )
                        if salvaged_products:
                            logger.info(
                                f"Salvaged {len(salvaged_products)} products from interceptor despite verification block"
                            )
                            all_products.extend(salvaged_products)
                    break

                # Wait for page to load and API calls to complete
                await self.browser.scroll_page(page, scroll_count=3)
                await asyncio.sleep(2)

                # Extract products with verify redirect handling
                (
                    products,
                    should_stop,
                ) = await self._extract_products_with_verify_handling(
                    page, interceptor, search_url
                )

                if should_stop:
                    break

                all_products.extend(products)
                logger.info(
                    f"Extracted {len(products)} products from page {page_num + 1}",
                    method="network" if interceptor and products else "dom",
                )

                if len(products) < 30:
                    logger.info("Few results, may be last page")
                    if len(products) == 0:
                        break

                await self.browser.random_delay(2.0, 4.0)

        finally:
            if interceptor:
                await interceptor.stop()
            await self.browser.close_page(page)

        logger.info(f"Search completed: {len(all_products)} total products")
        return all_products

    async def _extract_from_network(
        self,
        interceptor: NetworkInterceptor,
        timeout: float = 10.0,
    ) -> list[dict[str, Any]]:
        """
        Extract products from intercepted API responses.

        Args:
            interceptor: Active NetworkInterceptor instance
            timeout: Max wait time for API response

        Returns:
            List of parsed products
        """
        # Wait for search API response
        response = await interceptor.wait_for_response(
            SEARCH_API,
            timeout=timeout,
        )

        if not response or not response.body_json:
            logger.debug("No search API response intercepted")
            return []

        # Parse API response
        products = self._parse_api_response(response.body_json)
        logger.debug(
            f"Network interception extracted {len(products)} products",
            api_url=response.url[:60] if response.url else "",
        )
        return products

    async def _extract_from_js_state(self, page: Page) -> list[dict[str, Any]]:
        """
        Extract products from Shopee's JavaScript global state (SSR hydration).

        Shopee uses SSR and stores data in global JS variables like:
        - window.__INITIAL_STATE__
        - window.__APOLLO_STATE__
        - window.__remixContext
        - Script tags with type="application/json"

        Args:
            page: nodriver Page instance

        Returns:
            List of parsed products
        """
        import json as _json

        # JavaScript to extract data from various Shopee hydration sources
        raw_data = await page.evaluate("""
            (() => {
                const products = [];

                // Try __INITIAL_STATE__ (Next.js/Nuxt pattern)
                if (window.__INITIAL_STATE__) {
                    try {
                        const state = window.__INITIAL_STATE__;
                        // Search results often in search, items, or products key
                        const searchData = state.search || state.searchResults ||
                                          state.items || state.products || {};
                        const items = searchData.items || searchData.products ||
                                     searchData.data?.items || [];
                        if (items.length > 0) {
                            return JSON.stringify({source: '__INITIAL_STATE__', items: items});
                        }
                    } catch(e) {}
                }

                // Try __APOLLO_STATE__ (Apollo GraphQL cache)
                if (window.__APOLLO_STATE__) {
                    try {
                        const apollo = window.__APOLLO_STATE__;
                        const keys = Object.keys(apollo);
                        for (const key of keys) {
                            if (key.includes('search') || key.includes('Item')) {
                                const data = apollo[key];
                                if (data && data.items) {
                                    return JSON.stringify({source: '__APOLLO_STATE__', items: data.items});
                                }
                            }
                        }
                    } catch(e) {}
                }

                // Try __remixContext (Remix pattern)
                if (window.__remixContext) {
                    try {
                        const ctx = window.__remixContext;
                        const loaderData = ctx.state?.loaderData || {};
                        for (const key of Object.keys(loaderData)) {
                            const data = loaderData[key];
                            if (data?.items || data?.products) {
                                return JSON.stringify({
                                    source: '__remixContext',
                                    items: data.items || data.products
                                });
                            }
                        }
                    } catch(e) {}
                }

                // Try script[type="application/json"] or script[id*="__NEXT_DATA__"]
                const scripts = document.querySelectorAll(
                    'script[type="application/json"], script[id*="__NEXT_DATA__"], script[id*="__NUXT__"]'
                );
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        const items = data.props?.pageProps?.items ||
                                     data.props?.pageProps?.searchResult?.items ||
                                     data.data?.items ||
                                     data.state?.search?.items ||
                                     data.items ||
                                     [];
                        if (items.length > 0) {
                            return JSON.stringify({source: 'script_json', items: items});
                        }
                    } catch(e) {}
                }

                // Try window.pageData (Shopee specific)
                if (window.pageData) {
                    try {
                        const items = window.pageData.items ||
                                     window.pageData.searchItems ||
                                     window.pageData.products || [];
                        if (items.length > 0) {
                            return JSON.stringify({source: 'pageData', items: items});
                        }
                    } catch(e) {}
                }

                // Last resort: scan all window properties for search data
                try {
                    for (const key of Object.keys(window)) {
                        if (key.startsWith('__') && typeof window[key] === 'object') {
                            const obj = window[key];
                            if (obj && obj.search && obj.search.items) {
                                return JSON.stringify({source: key, items: obj.search.items});
                            }
                        }
                    }
                } catch(e) {}

                return JSON.stringify({source: null, items: []});
            })()
        """)

        if not raw_data:
            return []

        try:
            parsed = _json.loads(raw_data) if isinstance(raw_data, str) else raw_data

            source = parsed.get("source")
            items = parsed.get("items", [])

            if not items:
                logger.debug("No products found in JS global state")
                return []

            logger.debug(f"JS state extraction found {len(items)} items", source=source)

            # Parse items using existing API parser
            products = []
            for item in items:
                # Handle both nested (item_basic) and flat structures
                item_data = item.get("item_basic", item)
                product = self.parse(item_data)
                if product:
                    products.append(product)

            logger.debug(f"JS state extraction parsed {len(products)} products")
            return products

        except _json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JS state data: {e}")
            return []

    async def _extract_products_with_verify_handling(
        self,
        page: Page,
        interceptor: NetworkInterceptor | None,
        search_url: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        """
        Extract products using multiple strategies with verify redirect handling.

        Returns:
            Tuple of (products list, should_stop flag)
        """
        products = await self._try_all_extraction_strategies(page, interceptor)

        # Check if redirected to verify page after extraction attempts
        current_url = page.target.url or ""
        if not products and "/verify/" in current_url:
            logger.warning(
                "Redirected to verification page during extraction",
                url=current_url,
            )
            # Try to solve captcha
            if await self._handle_verify_redirect(page, search_url):
                # Retry extraction after solving
                if interceptor:
                    interceptor.clear_responses()
                    await self.browser.scroll_page(page, scroll_count=3)
                    await asyncio.sleep(2)
                products = await self._try_all_extraction_strategies(page, interceptor)
            else:
                logger.error("Failed to resolve verification, stopping search")
                return [], True

        return products, False

    async def _try_all_extraction_strategies(
        self,
        page: Page,
        interceptor: NetworkInterceptor | None,
    ) -> list[dict[str, Any]]:
        """Try all extraction strategies in priority order."""
        products: list[dict[str, Any]] = []

        # Strategy 1: Network interception (most reliable)
        if interceptor:
            products = await self._extract_from_network(interceptor)

        # Strategy 2: JavaScript global state
        if not products:
            logger.debug("Trying JS global state extraction")
            products = await self._extract_from_js_state(page)

        # Strategy 3: DOM extraction fallback
        if not products:
            logger.debug("Falling back to DOM extraction")
            await self.browser.scroll_page(page, scroll_count=2)
            products = await self._extract_from_dom(page)

        return products

    def _parse_api_response(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse API response into product list."""
        products = []

        # Log response structure for debugging
        top_keys = list(data.keys()) if data else []
        logger.debug(f"API response keys: {top_keys}")

        # Check for error response
        if "error" in data:
            error_val = data.get("error")
            logger.warning(f"API response contains error: {error_val}")
            # Log first 200 chars of response for debugging
            import json

            response_preview = json.dumps(data)[:200]
            logger.debug(f"Error response preview: {response_preview}")

        items = data.get("items", [])
        if not items:
            # Try alternate structure
            items = data.get("data", {}).get("items", [])

        for item in items:
            item_basic = item.get("item_basic", item)
            product = self.parse(item_basic)
            if product:
                products.append(product)

        return products

    async def _extract_from_dom(self, page: Page) -> list[dict[str, Any]]:
        """Extract products from page DOM using JavaScript evaluation."""
        # Use JavaScript to extract all product data at once
        raw_products = await page.evaluate("""
            (() => {
                // Extended list of selectors - Shopee changes these frequently
                const containerSelectors = [
                    // Primary selectors
                    "[data-sqe='item']",
                    ".shopee-search-item-result__item",
                    // Card-based selectors
                    "[class*='product-card']",
                    "[class*='productCard']",
                    "[class*='ProductCard']",
                    "[class*='product-item']",
                    "[class*='productItem']",
                    // Grid-based selectors
                    "li[class*='col-xs']",
                    "[class*='grid'] > div[class*='item']",
                    "[class*='grid'] > a",
                    // Generic item containers
                    "[class*='search-item']",
                    "[class*='searchItem']",
                    "a[href*='-i.'][href*='.']",  // Direct link matching
                ];

                let items = [];

                // Try each selector
                for (const sel of containerSelectors) {
                    try {
                        items = document.querySelectorAll(sel);
                        if (items.length > 0) {
                            console.log('Found items with selector:', sel, 'count:', items.length);
                            break;
                        }
                    } catch(e) {}
                }

                // Fallback: find all links matching Shopee product URL pattern
                if (items.length === 0) {
                    const allLinks = document.querySelectorAll('a[href]');
                    const productLinks = [];
                    allLinks.forEach(a => {
                        const href = a.getAttribute('href') || '';
                        if (href.match(/-i\\.\\d+\\.\\d+/) && !productLinks.some(p => p.href === href)) {
                            productLinks.push(a);
                        }
                    });
                    items = productLinks;
                    console.log('Fallback: found product links:', items.length);
                }

                const products = [];
                const seenIds = new Set();

                items.forEach(item => {
                    try {
                        // Get product link - search in item or item itself is link
                        let href = '';
                        if (item.tagName === 'A') {
                            href = item.getAttribute('href') || '';
                        } else {
                            const links = item.querySelectorAll('a');
                            for (const l of links) {
                                const h = l.getAttribute('href') || '';
                                if (h.match(/-i\\.\\d+\\.\\d+/)) { href = h; break; }
                            }
                        }

                        // Extract shop_id and item_id from URL
                        const match = href.match(/-i\\.(\\d+)\\.(\\d+)/);
                        if (!match) return;

                        const itemId = match[2];
                        if (seenIds.has(itemId)) return;  // Skip duplicates
                        seenIds.add(itemId);

                        // Extract name from URL slug (most reliable)
                        const slug = href.split('-i.')[0].replace(/^\\//, '');
                        const nameFromSlug = slug.replace(/-/g, ' ').trim();

                        // Try DOM-based name extraction
                        const allText = (item.innerText || '').trim();
                        const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 3);
                        const nameFromDom = lines[0] || '';

                        // Price: find text matching Rp pattern (multiple formats)
                        let priceText = '0';
                        const pricePatterns = [
                            /Rp\\s*([\\d.,]+)/,
                            /([\\d.,]+)\\s*rb/i,
                            /IDR\\s*([\\d.,]+)/i,
                        ];
                        for (const pattern of pricePatterns) {
                            const priceMatch = allText.match(pattern);
                            if (priceMatch) {
                                priceText = priceMatch[0];
                                break;
                            }
                        }

                        // Sold: find "terjual" patterns
                        let soldText = '0';
                        const soldPatterns = [
                            /(\\d[\\d.,]*\\s*(?:rb|RB|Rb|k|K)?\\+?)\\s*[Tt]erjual/i,
                            /[Tt]erjual\\s*(\\d[\\d.,]*\\s*(?:rb|RB|Rb|k|K)?\\+?)/i,
                            /(\\d[\\d.,]*\\s*(?:rb|RB|k|K)?)\\+?\\s*sold/i,
                        ];
                        for (const pattern of soldPatterns) {
                            const soldMatch = allText.match(pattern);
                            if (soldMatch) {
                                soldText = soldMatch[0];
                                break;
                            }
                        }

                        // Get image - try multiple sources
                        let image = '';
                        const imgEl = item.querySelector('img');
                        if (imgEl) {
                            image = imgEl.src || imgEl.getAttribute('src') ||
                                   imgEl.getAttribute('data-src') || '';
                        }

                        products.push({
                            shop_id: parseInt(match[1]),
                            item_id: parseInt(match[2]),
                            name: nameFromDom || nameFromSlug,
                            price_text: priceText,
                            sold_text: soldText,
                            image: image,
                            href: href
                        });
                    } catch(e) {
                        console.error('Error extracting product:', e);
                    }
                });

                // Debug info
                console.log('Extracted products:', products.length);
                return JSON.stringify({
                    debug: {
                        url: window.location.href,
                        totalItems: items.length,
                        extractedProducts: products.length
                    },
                    products: products
                });
            })()
        """)

        # nodriver returns CDP serialized format; we use JSON.stringify
        # in JS and parse here to get plain dicts
        import json as _json

        if isinstance(raw_products, str):
            try:
                raw_products = _json.loads(raw_products)
            except _json.JSONDecodeError:
                raw_products = {"debug": {}, "products": []}

        # Extract debug info and products from new structure
        debug_info = (
            raw_products.get("debug", {}) if isinstance(raw_products, dict) else {}
        )
        raw_items = (
            raw_products.get("products", [])
            if isinstance(raw_products, dict)
            else raw_products
        )

        if debug_info:
            logger.debug(
                "DOM extraction debug",
                url=debug_info.get("url", "")[:60],
                total_items=debug_info.get("totalItems", 0),
                extracted=debug_info.get("extractedProducts", 0),
            )

        products = []
        for raw in raw_items or []:
            try:
                products.append(
                    {
                        "item_id": raw["item_id"],
                        "shop_id": raw["shop_id"],
                        "name": raw["name"],
                        "price": parse_price(raw.get("price_text", "0")),
                        "sold": parse_sold_count(raw.get("sold_text", "0")),
                        "image": raw.get("image", ""),
                        "url": f"{BASE_URL}{raw['href']}" if raw.get("href") else "",
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to parse product: {e}")

        logger.debug(f"DOM extraction found {len(products)} products")
        return products

    def parse(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and structure product data from API."""
        if not raw_data:
            return {}

        # Extract basic info
        item_id = raw_data.get("itemid", raw_data.get("item_id", 0))
        shop_id = raw_data.get("shopid", raw_data.get("shop_id", 0))

        if not item_id or not shop_id:
            return {}

        # Price (Shopee stores price * 100000)
        price_raw = raw_data.get("price", 0)
        price_min = raw_data.get("price_min", price_raw)
        price_max = raw_data.get("price_max", price_raw)

        # Convert price
        price = price_min / PRICE_DIVISOR if price_min else 0
        price_max_val = price_max / PRICE_DIVISOR if price_max else price

        # Images
        images = raw_data.get("images", [])
        image_url = ""
        if images:
            image_url = f"https://cf.shopee.co.id/file/{images[0]}"

        # Build product dict
        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": raw_data.get("name", ""),
            "price": price,
            "price_max": price_max_val,
            "price_before_discount": raw_data.get("price_before_discount", 0)
            / PRICE_DIVISOR,
            "discount": raw_data.get("raw_discount", 0),
            "stock": raw_data.get("stock", 0),
            "sold": raw_data.get("sold", raw_data.get("historical_sold", 0)),
            "rating": raw_data.get("item_rating", {}).get("rating_star", 0),
            "rating_count": sum(
                raw_data.get("item_rating", {}).get("rating_count", [0])
            ),
            "liked_count": raw_data.get("liked_count", 0),
            "shop_location": raw_data.get("shop_location", ""),
            "is_official_shop": raw_data.get("is_official_shop", False),
            "is_preferred_plus": raw_data.get("is_preferred_plus_seller", False),
            "image": image_url,
            "url": f"{BASE_URL}/product/{shop_id}/{item_id}",
            "category_id": raw_data.get("catid", 0),
        }

    async def extract(self, page: Page) -> dict[str, Any]:
        """Extract data from current page (interface compliance)."""
        products = await self._extract_from_dom(page)
        return {"products": products}
