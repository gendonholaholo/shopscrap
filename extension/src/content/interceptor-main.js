/**
 * MAIN world content script: Monkey-patches fetch/XHR to intercept Shopee API responses.
 *
 * Runs in the page's MAIN world (via manifest.json "world": "MAIN") so it can
 * directly patch window.fetch and XMLHttpRequest without injecting <script> elements.
 * This bypasses Content Security Policy restrictions that block inline scripts.
 *
 * Communication: Sends intercepted data via window.postMessage to the ISOLATED
 * world content script (interceptor.js).
 */
(function () {
  'use strict';

  const API_PATTERNS = [
    '/api/v4/search/search_items',
    '/api/v4/pdp/get_pc',
    '/api/v4/item/get',
    '/api/v2/item/get_ratings',
    '/api/v4/pdp/get_rw',
  ];

  function matchesPattern(url) {
    return API_PATTERNS.find((pattern) => url.includes(pattern));
  }

  // ---- Monkey-patch fetch() ----
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    const pattern = matchesPattern(url);

    if (pattern) {
      try {
        const cloned = response.clone();
        const data = await cloned.json();
        window.postMessage(
          {
            type: '__SHOPEE_SCRAPER_API__',
            pattern: pattern,
            url: url,
            data: data,
          },
          '*'
        );
      } catch (e) {
        // Ignore parse errors
      }
    }

    return response;
  };

  // ---- Monkey-patch XMLHttpRequest ----
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._shopeeUrl = url;
    this._shopeePattern = matchesPattern(url);
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (...args) {
    if (this._shopeePattern) {
      this.addEventListener('load', function () {
        try {
          const data = JSON.parse(this.responseText);
          window.postMessage(
            {
              type: '__SHOPEE_SCRAPER_API__',
              pattern: this._shopeePattern,
              url: this._shopeeUrl,
              data: data,
            },
            '*'
          );
        } catch (e) {
          // Ignore parse errors
        }
      });
    }
    return originalSend.apply(this, args);
  };
})();
