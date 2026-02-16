/**
 * Service Worker: WebSocket client, task routing, heartbeat.
 *
 * Connects to the Shopee Scraper backend via WebSocket.
 * Receives scraping tasks, forwards them to content scripts running
 * on Shopee tabs, and returns raw API JSON results to the backend.
 */

const DEFAULT_BACKEND_URL = 'ws://localhost:8002/api/v1/extension/connect';
const HEARTBEAT_INTERVAL_MS = 30_000;
const RECONNECT_DELAY_MS = 5_000;
const BASE_URL = 'https://shopee.co.id';

let ws = null;
let extensionId = null;
let heartbeatTimer = null;
let reconnectTimer = null;
let connected = false;
let pendingTasks = new Map(); // taskId -> timeout timer

// ============================================================================
// Extension ID Management
// ============================================================================

async function getExtensionId() {
  if (extensionId) return extensionId;

  const stored = await chrome.storage.local.get('extensionId');
  if (stored.extensionId) {
    extensionId = stored.extensionId;
    return extensionId;
  }

  // Generate new UUID
  extensionId = crypto.randomUUID();
  await chrome.storage.local.set({ extensionId });
  return extensionId;
}

// ============================================================================
// WebSocket Connection Management
// ============================================================================

async function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const stored = await chrome.storage.local.get('backendUrl');
  const url = stored.backendUrl || DEFAULT_BACKEND_URL;

  console.log('[SW] Connecting to backend:', url);

  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.error('[SW] WebSocket creation failed:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = async () => {
    console.log('[SW] WebSocket connected');
    connected = true;
    updateBadge('on');

    // Send registration
    const extId = await getExtensionId();
    const registerMsg = {
      type: 'register',
      payload: {
        extension_id: extId,
        user_agent: navigator.userAgent,
        version: chrome.runtime.getManifest().version,
      },
    };
    ws.send(JSON.stringify(registerMsg));

    // Start heartbeat
    startHeartbeat();

    // Notify popup
    broadcastStatus();
  };

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      handleBackendMessage(message);
    } catch (e) {
      console.error('[SW] Failed to parse message:', e);
    }
  };

  ws.onclose = (event) => {
    console.log('[SW] WebSocket closed:', event.code, event.reason);
    cleanup();
    scheduleReconnect();
  };

  ws.onerror = (error) => {
    console.error('[SW] WebSocket error:', error);
  };
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close(1000, 'User disconnected');
    ws = null;
  }
  cleanup();
}

function cleanup() {
  connected = false;
  stopHeartbeat();
  updateBadge('off');
  broadcastStatus();

  // Clear pending task timeouts
  for (const timer of pendingTasks.values()) {
    clearTimeout(timer);
  }
  pendingTasks.clear();
}

function scheduleReconnect() {
  if (reconnectTimer) return;

  // Check if auto-connect is enabled
  chrome.storage.local.get('autoConnect', (result) => {
    if (result.autoConnect === false) return;

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, RECONNECT_DELAY_MS);
  });
}

// ============================================================================
// Heartbeat
// ============================================================================

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'heartbeat',
        payload: { extension_id: extensionId },
      }));
    }
  }, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

// ============================================================================
// Backend Message Handling
// ============================================================================

function handleBackendMessage(message) {
  const { type, payload } = message;

  switch (type) {
    case 'registered':
      console.log('[SW] Registered with backend:', payload);
      break;

    case 'pong':
      // Heartbeat acknowledged
      break;

    case 'task':
      handleTask(payload);
      break;

    case 'cancel_task':
      handleCancelTask(payload);
      break;

    default:
      console.warn('[SW] Unknown message type:', type);
  }
}

// ============================================================================
// Task Handling
// ============================================================================

async function handleTask(payload) {
  const { task_id, task_type, params } = payload;
  console.log('[SW] Task received:', task_id, task_type, params);

  try {
    // Find or create a Shopee tab
    const tabId = await getOrCreateShopeeTab(task_type, params);

    // Set task timeout
    const timeoutTimer = setTimeout(() => {
      pendingTasks.delete(task_id);
      sendTaskError(task_id, 'Task timed out');
    }, 300_000); // 5 minutes
    pendingTasks.set(task_id, timeoutTimer);

    // Send task to content script
    chrome.tabs.sendMessage(tabId, {
      action: 'executeTask',
      taskId: task_id,
      taskType: task_type,
      params,
    }, (response) => {
      // Clear timeout
      const timer = pendingTasks.get(task_id);
      if (timer) {
        clearTimeout(timer);
        pendingTasks.delete(task_id);
      }

      if (chrome.runtime.lastError) {
        sendTaskError(task_id, `Content script error: ${chrome.runtime.lastError.message}`);
        return;
      }

      if (response && response.success) {
        sendTaskResult(task_id, response.data);
      } else {
        sendTaskError(task_id, response?.error || 'Unknown content script error');
      }
    });

  } catch (e) {
    console.error('[SW] Task execution failed:', e);
    sendTaskError(task_id, e.message);
  }
}

function handleCancelTask(payload) {
  const { task_id } = payload;
  const timer = pendingTasks.get(task_id);
  if (timer) {
    clearTimeout(timer);
    pendingTasks.delete(task_id);
  }
  console.log('[SW] Task cancelled:', task_id);
}

// ============================================================================
// Tab Management
// ============================================================================

async function getOrCreateShopeeTab(taskType, params) {
  // Build the target URL based on task type
  let targetUrl;
  switch (taskType) {
    case 'search':
      targetUrl = `${BASE_URL}/search?keyword=${encodeURIComponent(params.keyword)}`;
      if (params.sortBy && params.sortBy !== 'relevancy') {
        targetUrl += `&sortBy=${params.sortBy}`;
      }
      break;
    case 'product':
      targetUrl = `${BASE_URL}/product/${params.shopId}/${params.itemId}`;
      break;
    case 'reviews':
      targetUrl = `${BASE_URL}/product/${params.shopId}/${params.itemId}`;
      break;
    default:
      targetUrl = BASE_URL;
  }

  // Try to find existing Shopee tab
  const tabs = await chrome.tabs.query({ url: 'https://shopee.co.id/*' });

  if (tabs.length > 0) {
    // Reuse existing tab — navigate to target
    const tab = tabs[0];
    await chrome.tabs.update(tab.id, { url: targetUrl });
    // Wait for tab to load
    await waitForTabLoad(tab.id);
    return tab.id;
  }

  // Create new tab
  const tab = await chrome.tabs.create({ url: targetUrl, active: false });
  await waitForTabLoad(tab.id);
  return tab.id;
}

function waitForTabLoad(tabId) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Tab load timeout'));
    }, 30_000);

    const listener = (updatedTabId, changeInfo) => {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timeout);
        // Give the page a moment to initialize
        setTimeout(resolve, 1000);
      }
    };

    chrome.tabs.onUpdated.addListener(listener);
  });
}

// ============================================================================
// Result Sending
// ============================================================================

function sendTaskResult(taskId, rawData) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('[SW] Cannot send result: not connected');
    return;
  }

  ws.send(JSON.stringify({
    type: 'task_result',
    payload: {
      task_id: taskId,
      raw_data: rawData,
    },
  }));
  console.log('[SW] Task result sent:', taskId);
}

function sendTaskError(taskId, error) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('[SW] Cannot send error: not connected');
    return;
  }

  ws.send(JSON.stringify({
    type: 'task_error',
    payload: {
      task_id: taskId,
      error: error,
    },
  }));
  console.log('[SW] Task error sent:', taskId, error);
}

function sendProgress(taskId, percent, message) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({
    type: 'progress',
    payload: {
      task_id: taskId,
      percent,
      message: message || '',
    },
  }));
}

// ============================================================================
// Badge & Status
// ============================================================================

function updateBadge(state) {
  if (state === 'on') {
    chrome.action.setBadgeText({ text: 'ON' });
    chrome.action.setBadgeBackgroundColor({ color: '#22c55e' });
  } else {
    chrome.action.setBadgeText({ text: '' });
  }
}

function broadcastStatus() {
  chrome.runtime.sendMessage({
    action: 'statusUpdate',
    connected,
    pendingTasks: pendingTasks.size,
  }).catch(() => {
    // Popup may not be open
  });
}

// ============================================================================
// Message Listener (from popup and content scripts)
// ============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case 'connect':
      connect();
      sendResponse({ ok: true });
      break;

    case 'disconnect':
      disconnect();
      sendResponse({ ok: true });
      break;

    case 'getStatus':
      sendResponse({
        connected,
        extensionId,
        pendingTasks: pendingTasks.size,
      });
      break;

    case 'setBackendUrl':
      chrome.storage.local.set({ backendUrl: message.url });
      sendResponse({ ok: true });
      break;

    case 'apiCaptured':
      // Content script captured an API response for a pending task
      // This is handled via the executeTask callback instead
      break;

    default:
      break;
  }

  return true; // Keep message channel open for async responses
});

// ============================================================================
// Auto-connect on install/startup
// ============================================================================

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get('autoConnect', (result) => {
    if (result.autoConnect !== false) {
      connect();
    }
  });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.storage.local.get('autoConnect', (result) => {
    if (result.autoConnect !== false) {
      connect();
    }
  });
});
