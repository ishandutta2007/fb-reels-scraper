// Background service worker for window and tab focus management
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "FOCUS_TAB") {
    const tabId = sender.tab ? sender.tab.id : null;
    const windowId = sender.tab ? sender.tab.windowId : null;

    if (tabId !== null && windowId !== null) {
      // 1. Bring the browser window to foreground and focus it
      chrome.windows.update(windowId, { focused: true }, () => {
        // 2. Switch to this specific Facebook tab
        chrome.tabs.update(tabId, { active: true }, () => {
          sendResponse({ success: true });
        });
      });
      return true; // Keep message channel open for async response
    } else {
      sendResponse({ success: false, error: "Tab/Window not identifiable" });
    }
  }
});
