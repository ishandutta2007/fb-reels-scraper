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

## 💻 Usage & CLI Options

1. Open a Facebook tab in your browser where you are logged in.
2. Run the script from your terminal:

```bash
# Run with default fallback values (default target profile + 20 scrolls)
python fb-reels-scraper.py

# Custom target profile or page
python fb-reels-scraper.py --user "<target_user_or_page>"

# Custom target and scroll count (short flags)
python fb-reels-scraper.py -u "<target_user_or_page>" -s 15

# View all CLI options
python fb-reels-scraper.py --help
```

### Command-Line Arguments Reference

| Flag | Short | Default | Description |
|---|---|---|---|
| `--user` | `-u` | `nadeemkhancyber` | Facebook reels page URL to scrape |
| `--scrolls` | `-s` | `20` | Number of scroll cycles on the grid to harvest links |
| `--help` | `-h` | — | Display help text and usage instructions |

### Execution Flow:
1. The Python script starts a local WebSocket server at `ws://127.0.0.1:8765`.
2. The browser extension connects automatically from your active Facebook tab.
3. The tab navigates to the target reels URL and scrolls `-s` times to discover reel links.
4. The script checks discovered URLs against [reels_cache.json](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/reels_cache.json).
5. Uncached links are visited one-by-one to expand and extract the full description.
6. New descriptions are immediately written to cache and printed to the console.

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
