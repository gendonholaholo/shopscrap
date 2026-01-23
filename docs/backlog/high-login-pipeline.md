# Backlog: Login Pipeline via Browser Extension

## Overview

Solusi untuk mengatasi masalah login manual ketika aplikasi di-deploy ke server.
User tidak perlu akses CLI server, cukup login ke Shopee seperti biasa di browser mereka.

---

## Problem Statement

```
MASALAH

1. Shopee memerlukan login session untuk scraping
2. Login memerlukan browser visible (untuk CAPTCHA)
3. Server biasanya headless (tidak ada GUI)
4. User tidak bisa/tidak mau akses CLI server

SOLUSI

Browser Extension yang bisa:
- Membaca cookies Shopee dari browser user
- Mengirim cookies ke server API
```

---

## Implementation Status

### API Endpoints - IMPLEMENTED

- [x] `POST /api/v1/session/cookie-upload` - Upload cookies dari extension
- [x] `GET /api/v1/session/cookie-status` - Check cookie status

### Browser Extension - PENDING

- [ ] Create `browser-extension/` folder structure
- [ ] `manifest.json` with correct permissions
- [ ] `popup.html` - simple UI
- [ ] `popup.css` - basic styling
- [ ] `popup.js` - cookie reading & sending logic
- [ ] Icons (16, 48, 128 px)
- [ ] README with installation instructions

---

## API Structure (Final)

```
/api/v1/
│
├── session/                              [PALING ATAS]
│   ├── cookie-upload           POST      → upload cookies
│   └── cookie-status           GET       → check cookie status
│
├── products/
│   │
│   │  # Scraping Operations (Async)
│   ├── scrape-list                    POST  → scrape list products
│   ├── scrape-list-and-details        POST  → scrape list + full details
│   │
│   │  # Direct Resource Access
│   └── {shop_id}/{item_id}/
│       ├── (root)                     GET   → single product detail
│       └── reviews/
│           ├── (root)                 GET   → reviews list
│           └── overview               GET   → review statistics
│
├── jobs/
│   │  # Job Management Only
│   ├── (root)                  GET     → list all jobs
│   └── {job_id}/
│       ├── (root)              GET     → job detail + result
│       ├── status              GET     → status only (polling)
│       └── (root)              DELETE  → cancel job
│
/health                                   [PALING BAWAH]
├── (root)                      GET     → full health check
├── live                        GET     → liveness probe
└── ready                       GET     → readiness probe
```

---

## Browser Extension Structure (Planned)

```
browser-extension/
├── manifest.json          # Extension config (Manifest V3)
├── popup/
│   ├── popup.html         # UI sederhana
│   ├── popup.css          # Styling
│   └── popup.js           # Logic: baca cookies, kirim ke server
├── icons/
│   ├── icon-16.png
│   ├── icon-48.png
│   └── icon-128.png
└── README.md              # Cara install & penggunaan
```

### manifest.json

```json
{
  "manifest_version": 3,
  "name": "Shopee Scraper - Cookie Sync",
  "version": "1.0.0",
  "description": "Sync Shopee cookies to your scraper server",
  "permissions": [
    "cookies",
    "storage"
  ],
  "host_permissions": [
    "https://*.shopee.co.id/*"
  ],
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon-16.png",
      "48": "icons/icon-48.png",
      "128": "icons/icon-128.png"
    }
  }
}
```

### popup.html (UI Sederhana)

```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="popup.css">
</head>
<body>
  <div class="container">
    <h1>Shopee Scraper</h1>

    <p>Kirim cookies ke server</p>

    <div class="input-group">
      <label>Server URL:</label>
      <input type="text" id="serverUrl" placeholder="https://your-api.com">
    </div>

    <div class="input-group">
      <label>API Key:</label>
      <input type="password" id="apiKey" placeholder="Your API key">
    </div>

    <button id="sendBtn">Kirim</button>

    <div id="status"></div>
  </div>

  <script src="popup.js"></script>
</body>
</html>
```

### popup.js (Logic)

```javascript
document.getElementById('sendBtn').addEventListener('click', async () => {
  const serverUrl = document.getElementById('serverUrl').value;
  const apiKey = document.getElementById('apiKey').value;
  const statusEl = document.getElementById('status');

  if (!serverUrl || !apiKey) {
    statusEl.textContent = 'Error: Server URL dan API Key wajib diisi';
    return;
  }

  statusEl.textContent = 'Mengambil cookies...';

  try {
    // Get all Shopee cookies
    const cookies = await chrome.cookies.getAll({ domain: '.shopee.co.id' });

    if (cookies.length === 0) {
      statusEl.textContent = 'Error: Tidak ada cookies. Sudah login ke Shopee?';
      return;
    }

    statusEl.textContent = `Mengirim ${cookies.length} cookies...`;

    // Send to server
    const response = await fetch(`${serverUrl}/api/v1/session/cookie-upload`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey
      },
      body: JSON.stringify({ cookies })
    });

    const result = await response.json();

    if (result.success) {
      statusEl.textContent = 'Berhasil dikirim!';
      // Save server URL for next time
      chrome.storage.local.set({ serverUrl, apiKey });
    } else {
      statusEl.textContent = `Gagal: ${result.error}`;
    }

  } catch (error) {
    statusEl.textContent = `Error: ${error.message}`;
  }
});

// Load saved settings
chrome.storage.local.get(['serverUrl', 'apiKey'], (data) => {
  if (data.serverUrl) document.getElementById('serverUrl').value = data.serverUrl;
  if (data.apiKey) document.getElementById('apiKey').value = data.apiKey;
});
```

---

## User Flow

```
1. LOGIN & UPLOAD COOKIES (sekali, atau saat expired)

   Browser: Login ke shopee.co.id
   Extension: Klik "Kirim" -> POST /api/v1/session/cookie-upload

2. CHECK SESSION (opsional)

   GET /api/v1/session/cookie-status
   -> { "valid": true, "days_remaining": 6 }

3. SCRAPE PRODUCTS

   POST /api/v1/products/scrape-list
   Body: { "keyword": "tas branded", "max_pages": 3 }
   -> { "job_id": "job_abc123" }

4. POLL STATUS

   GET /api/v1/jobs/job_abc123/status
   -> { "status": "running", "progress": 45 }
   ... (repeat until completed)
   -> { "status": "completed", "progress": 100 }

5. GET RESULT

   GET /api/v1/jobs/job_abc123
   -> { "status": "completed", "result": [ ...180 products... ] }
```

---

## Notes

- Extension menggunakan Manifest V3 (standar terbaru Chrome)
- Cookies Shopee biasanya expire dalam ~7 hari
- User perlu re-upload cookies ketika expired
- API Key tetap diperlukan untuk autentikasi ke server
