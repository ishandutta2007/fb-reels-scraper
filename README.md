# FB Reels Scraper Bridge 🎬

A robust, two-stage Facebook Reels scraper that operates through your **existing browser session** via a lightweight Chrome/Edge extension and a local Python WebSocket bridge.

By utilizing your real browser session, you completely bypass login hurdles, 2FA prompts, fingerprinting, and bot-detection challenges without needing credentials or headless automation drivers.

---

## ✨ Features

- **No Bot Detection / Captchas**: Works directly inside your logged-in browser tab.
- **Two-Phase Architecture**:
  1. **Phase 1 (Discovery & Harvest)**: Scrolls target profile or page reels feeds (`/reels/`) to collect reel permalinks.
  2. **Phase 2 (Deep Extraction)**: Navigates to individual reel view pages, automatically clicks **"See more"** / **"...more"** to un-truncate descriptions, and extracts the full caption text.
- **Local Smart Caching (`reels_cache.json`)**: Automatically saves extracted reels on the fly. Re-running the script skips previously scraped URLs to save time and bandwidth.
- **Resilient WebSocket Bridge**: Gracefully handles page transitions, DOM reloads, and tab navigation events without throwing disconnect exceptions.

---

## 📁 Project Structure

```text
fb-reels-scraper/
├── extension/
│   ├── manifest.json       # Chrome Extension (Manifest V3) definition
│   ├── content.js          # Injected DOM script (handles scrolling, clicks & extraction)
│   ├── popup.html          # Extension popup UI
│   └── popup.js            # Status check for popup
├── fb-reels-scraper.py     # Main Python script with WebSocket server & scraping loop
├── reels_cache.json        # Auto-generated cache file storing scraped descriptions
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.8+
- Any Chromium-based browser (Google Chrome, Brave, Microsoft Edge, Opera, etc.)

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Load the Browser Extension
1. Open your browser and navigate to `chrome://extensions/` (or `edge://extensions/`).
2. Toggle on **Developer mode** (in the top-right corner).
3. Click **Load unpacked** and select the [extension/](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/extension) directory from this repository.
4. Pin the **FB Reels Scraper Bridge** icon if desired to view connection status.

---

## 💻 Usage

1. Open a Facebook tab in your browser where you are logged in.
2. Open [fb-reels-scraper.py](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/fb-reels-scraper.py) and configure your target URL and scroll count in `main()`:
   ```python
   target_url = "https://www.facebook.com/<target_user_or_page>/reels/"
   max_scrolls = 5  # Number of scroll increments on the grid
   ```
3. Run the script:
   ```bash
   python fb-reels-scraper.py
   ```
4. **Execution Flow**:
   - The Python script spins up a local WebSocket server at `ws://127.0.0.1:8765`.
   - The extension connects automatically from your Facebook tab.
   - The browser scrolls through the reels grid and gathers links.
   - Any links not found in [reels_cache.json](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/reels_cache.json) are visited sequentially to expand and extract full descriptions.
   - Results are printed to stdout and saved in [reels_cache.json](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/reels_cache.json).

---

## 💾 Cache Format

Descriptions are continuously saved to `reels_cache.json` in UTF-8 format:

```json
{
  "https://www.facebook.com/reel/123456789012345/": "Here is the full description and caption of the reel...",
  "https://www.facebook.com/reel/987654321098765/": "[No description found]"
}
```

If you ever wish to re-scrape everything from scratch, simply delete `reels_cache.json`.

---

## 🛡️ License

This project is licensed under the [MIT License](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/LICENSE).
