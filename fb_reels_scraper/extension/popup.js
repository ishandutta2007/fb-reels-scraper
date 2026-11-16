document.addEventListener("DOMContentLoaded", async () => {
  const badge = document.getElementById("badge");
  const statusEl = document.getElementById("status");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || !tab.url.includes("facebook.com")) {
      badge.textContent = "Not on Facebook";
      badge.className = "badge disconnected";
      statusEl.textContent = "Please navigate to a Facebook reels page in this tab.";
      return;
    }

    chrome.tabs.sendMessage(tab.id, { type: "GET_STATUS" }, (response) => {
      if (chrome.runtime.lastError || !response) {
        badge.textContent = "Script Not Loaded";
        badge.className = "badge disconnected";
        statusEl.textContent = "Refresh the Facebook page to load the bridge script.";
        return;
      }

      if (response.connected) {
        badge.textContent = "Connected to Python";
        badge.className = "badge connected";
        statusEl.textContent = "Ready to scrape reels via Python script.";
      } else {
        badge.textContent = "Waiting for Python";
        badge.className = "badge disconnected";
        statusEl.textContent = "Ensure 'python fb-reels-scraper.py' is running on port 8765.";
      }
    });
  } catch (e) {
    badge.textContent = "Error";
    badge.className = "badge disconnected";
  }
});
