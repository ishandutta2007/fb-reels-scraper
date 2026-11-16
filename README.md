# FB Reels Scraper Bridge

Scrapes Facebook Reels descriptions using your **existing browser session** (preserving logins, cookies, and avoiding bot detection) via a lightweight Chrome/Edge extension bridge communicating with Python over WebSocket.

---

## Setup & Usage

### 1. Load the Browser Extension
1. Open your browser (Chrome, Brave, Edge, etc.) where you are already logged in to Facebook.
2. Go to `chrome://extensions/` (or `edge://extensions/`).
3. Toggle on **Developer mode** (top-right corner).
4. Click **Load unpacked** and select the [extension/](file:///C:/Users/ishan/Documents/Projects/fb-reels-scraper/extension) directory.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Scraper
1. Make sure you have a Facebook tab open in your browser (e.g., navigated to Facebook or the reels page).
2. Start the scraper script:
   ```bash
   python fb-reels-scraper.py
   ```
3. The script connects directly to your active browser session, navigates or scrolls the reels page, extracts descriptions, and prints the results.
