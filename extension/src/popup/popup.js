/**
 * Popup logic: connection status, backend URL config, connect/disconnect.
 */

const DEFAULT_URL = 'ws://localhost:8000/api/v1/extension/connect';

// DOM elements
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const pendingCount = document.getElementById('pendingCount');
const pendingNum = document.getElementById('pendingNum');
const backendUrlInput = document.getElementById('backendUrl');
const saveUrlBtn = document.getElementById('saveUrl');
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const autoConnectCheckbox = document.getElementById('autoConnect');

// ============================================================================
// Initialize
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved settings
  const stored = await chrome.storage.local.get(['backendUrl', 'autoConnect']);
  backendUrlInput.value = stored.backendUrl || DEFAULT_URL;
  autoConnectCheckbox.checked = stored.autoConnect !== false;

  // Get current status
  refreshStatus();
});

// ============================================================================
// Status Updates
// ============================================================================

function refreshStatus() {
  chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
    if (chrome.runtime.lastError || !response) {
      updateUI(false, 0);
      return;
    }
    updateUI(response.connected, response.pendingTasks);
  });
}

function updateUI(isConnected, taskCount) {
  if (isConnected) {
    statusDot.classList.add('connected');
    statusText.textContent = 'Connected';
    connectBtn.style.display = 'none';
    disconnectBtn.style.display = 'block';
  } else {
    statusDot.classList.remove('connected');
    statusText.textContent = 'Disconnected';
    connectBtn.style.display = 'block';
    disconnectBtn.style.display = 'none';
  }

  if (taskCount > 0) {
    pendingCount.style.display = 'block';
    pendingNum.textContent = taskCount;
  } else {
    pendingCount.style.display = 'none';
  }
}

// Listen for status updates from service worker
chrome.runtime.onMessage.addListener((message) => {
  if (message.action === 'statusUpdate') {
    updateUI(message.connected, message.pendingTasks);
  }
});

// ============================================================================
// Event Handlers
// ============================================================================

connectBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'connect' });
  setTimeout(refreshStatus, 1000);
});

disconnectBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'disconnect' });
  setTimeout(refreshStatus, 500);
});

saveUrlBtn.addEventListener('click', () => {
  const url = backendUrlInput.value.trim();
  if (url) {
    chrome.runtime.sendMessage({ action: 'setBackendUrl', url });
    saveUrlBtn.textContent = 'Saved!';
    setTimeout(() => {
      saveUrlBtn.textContent = 'Save';
    }, 1500);
  }
});

autoConnectCheckbox.addEventListener('change', () => {
  chrome.storage.local.set({ autoConnect: autoConnectCheckbox.checked });
});
