/**
 * Content Script (ISOLATED world): Receives intercepted API data and handles tasks.
 *
 * The fetch/XHR monkey-patching runs in a separate MAIN world script
 * (interceptor-main.js) to bypass CSP restrictions. This script receives
 * the intercepted data via window.postMessage and coordinates with the
 * service worker for task execution.
 *
 * Communication flow:
 *   interceptor-main.js (MAIN world) → window.postMessage →
 *   This script (ISOLATED world) → chrome.runtime.sendMessage → Service Worker
 */

// Storage for captured API responses
const capturedResponses = new Map(); // pattern → latest response data
let activeTask = null; // current task being executed

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

  // Check if we already have fresh data (page loaded before task was dispatched)
  const existing = capturedResponses.get(expectedPattern);
  if (existing) {
    capturedResponses.delete(expectedPattern);
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
    case 'search': {
      const items = data.items || data.data?.items;
      return Array.isArray(items) && items.length > 0;
    }
    case 'product':
      return data.data || data.item;
    case 'reviews':
      return data.data && data.data.ratings;
    default:
      return false;
  }
}
