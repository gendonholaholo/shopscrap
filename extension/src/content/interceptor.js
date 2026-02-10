/**
 * Content Script: Shopee API interception via fetch/XHR monkey-patching.
 *
 * Injected into Shopee pages at document_start. Intercepts API responses
 * by monkey-patching window.fetch() and XMLHttpRequest.
 *
 * Communication flow:
 *   Page context (injected script) → window.postMessage →
 *   Content script → chrome.runtime.sendMessage → Service Worker
 */

// API patterns to intercept
const API_PATTERNS = [
  '/api/v4/search/search_items',
  '/api/v4/pdp/get_pc',
  '/api/v4/item/get',
  '/api/v2/item/get_ratings',
  '/api/v4/pdp/get_rw',
];

// Storage for captured API responses
const capturedResponses = new Map(); // pattern → latest response data
let activeTask = null; // current task being executed

// ============================================================================
// Inject interceptor script into page context
// ============================================================================

function injectInterceptor() {
  const script = document.createElement('script');
  script.textContent = `
    (function() {
      'use strict';

      const API_PATTERNS = ${JSON.stringify(API_PATTERNS)};

      function matchesPattern(url) {
        return API_PATTERNS.find(pattern => url.includes(pattern));
      }

      // ---- Monkey-patch fetch() ----
      const originalFetch = window.fetch;
      window.fetch = async function(...args) {
        const response = await originalFetch.apply(this, args);
        const url = (typeof args[0] === 'string') ? args[0] : args[0]?.url || '';
        const pattern = matchesPattern(url);

        if (pattern) {
          try {
            const cloned = response.clone();
            const data = await cloned.json();
            window.postMessage({
              type: '__SHOPEE_SCRAPER_API__',
              pattern: pattern,
              url: url,
              data: data,
            }, '*');
          } catch(e) {
            // Ignore parse errors
          }
        }

        return response;
      };

      // ---- Monkey-patch XMLHttpRequest ----
      const originalOpen = XMLHttpRequest.prototype.open;
      const originalSend = XMLHttpRequest.prototype.send;

      XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this._shopeeUrl = url;
        this._shopeePattern = matchesPattern(url);
        return originalOpen.call(this, method, url, ...rest);
      };

      XMLHttpRequest.prototype.send = function(...args) {
        if (this._shopeePattern) {
          this.addEventListener('load', function() {
            try {
              const data = JSON.parse(this.responseText);
              window.postMessage({
                type: '__SHOPEE_SCRAPER_API__',
                pattern: this._shopeePattern,
                url: this._shopeeUrl,
                data: data,
              }, '*');
            } catch(e) {
              // Ignore parse errors
            }
          });
        }
        return originalSend.apply(this, args);
      };
    })();
  `;
  (document.head || document.documentElement).appendChild(script);
  script.remove();
}

// Inject as early as possible
injectInterceptor();

// ============================================================================
// Listen for intercepted API responses from page context
// ============================================================================

window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== '__SHOPEE_SCRAPER_API__') return;

  const { pattern, data } = event.data;
  capturedResponses.set(pattern, data);

  // If we have an active task waiting for this pattern, resolve it
  if (activeTask && activeTask.expectedPattern) {
    if (pattern.includes(activeTask.expectedPattern)) {
      resolveActiveTask(data);
    }
  }
});

// ============================================================================
// Task Execution (from Service Worker)
// ============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action !== 'executeTask') return false;

  const { taskId, taskType, params } = message;

  executeTask(taskId, taskType, params)
    .then((data) => {
      sendResponse({ success: true, data });
    })
    .catch((error) => {
      sendResponse({ success: false, error: error.message });
    });

  return true; // Keep channel open for async response
});

async function executeTask(taskId, taskType, params) {
  // Determine which API pattern we're waiting for
  let expectedPattern;
  switch (taskType) {
    case 'search':
      expectedPattern = '/api/v4/search/search_items';
      break;
    case 'product':
      expectedPattern = '/api/v4/pdp/get_pc';
      break;
    case 'reviews':
      expectedPattern = '/api/v2/item/get_ratings';
      break;
    default:
      throw new Error(`Unknown task type: ${taskType}`);
  }

  // Clear previous captures for this pattern
  capturedResponses.delete(expectedPattern);

  // Check if we already have fresh data (race condition: page loaded before task)
  const existing = capturedResponses.get(expectedPattern);
  if (existing && isRelevantData(existing, taskType, params)) {
    return existing;
  }

  // Set up active task and wait for the API response
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      activeTask = null;
      reject(new Error(`Timeout waiting for API response: ${expectedPattern}`));
    }, 60_000); // 60 second timeout for page-level capture

    activeTask = {
      taskId,
      expectedPattern,
      resolve: (data) => {
        clearTimeout(timeout);
        activeTask = null;
        resolve(data);
      },
      reject: (error) => {
        clearTimeout(timeout);
        activeTask = null;
        reject(error);
      },
    };

    // The page should already be navigating (service worker handled that).
    // We just need to wait for the API interception to fire.
    // If the page is already loaded and no API call happened,
    // try scrolling to trigger lazy-loaded content.
    setTimeout(() => {
      if (activeTask && activeTask.taskId === taskId) {
        window.scrollTo(0, document.body.scrollHeight / 2);
        setTimeout(() => {
          window.scrollTo(0, document.body.scrollHeight);
        }, 1000);
      }
    }, 3000);
  });
}

function resolveActiveTask(data) {
  if (activeTask && activeTask.resolve) {
    activeTask.resolve(data);
  }
}

function isRelevantData(data, taskType, params) {
  // Basic relevance check — ensure the data matches what we're looking for
  if (!data) return false;

  switch (taskType) {
    case 'search':
      return data.items && data.items.length > 0;
    case 'product':
      return data.data || data.item;
    case 'reviews':
      return data.data && data.data.ratings;
    default:
      return false;
  }
}
