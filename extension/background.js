// Background service worker for window, tab, and focus management
let bgSocket = null;
let bgReconnectTimer = null;

function log(...args) {
  console.log("[Background]", ...args);
}

// Bring a window to foreground and restore if minimized
async function restoreAndFocusWindow(windowId) {
  try {
    const win = await chrome.windows.get(windowId);
    if (win.state === "minimized") {
      await chrome.windows.update(windowId, { state: "normal" });
    }
    await chrome.windows.update(windowId, { focused: true });
    log("Window brought to focus successfully:", windowId);
  } catch (err) {
    log("Error focusing window:", err);
  }
}

// Ensure the target URL is open, active, and window is focused
async function handleEnsureTabAndFocus(targetUrl) {
  try {
    log("handleEnsureTabAndFocus requested for:", targetUrl);
    const allTabs = await chrome.tabs.query({});
    const normTarget = targetUrl ? targetUrl.split("?")[0].replace(/\/+$/, "").toLowerCase() : "";

    let exactMatch = null;
    let fbTab = null;

    for (const t of allTabs) {
      if (!t.url) continue;
      const normUrl = t.url.split("?")[0].replace(/\/+$/, "").toLowerCase();
      if (normTarget && normUrl === normTarget) {
        exactMatch = t;
        break;
      }
      if (t.url.includes("facebook.com")) {
        if (!fbTab) fbTab = t;
      }
    }

    if (exactMatch) {
      log("Found exact match tab:", exactMatch.id, exactMatch.url);
      await restoreAndFocusWindow(exactMatch.windowId);
      await chrome.tabs.update(exactMatch.id, { active: true });
      return { tabId: exactMatch.id, action: "focused" };
    } else if (fbTab && targetUrl) {
      log("Found existing FB tab:", fbTab.id, "- navigating to target:", targetUrl);
      await restoreAndFocusWindow(fbTab.windowId);
      await chrome.tabs.update(fbTab.id, { active: true, url: targetUrl });
      return { tabId: fbTab.id, action: "navigated" };
    } else if (targetUrl) {
      log("No FB tab found. Opening a new tab for:", targetUrl);
      const win = await chrome.windows.getLastFocused().catch(() => null);
      if (win) {
        await restoreAndFocusWindow(win.id);
        const newTab = await chrome.tabs.create({
          windowId: win.id,
          url: targetUrl,
          active: true
        });
        return { tabId: newTab.id, action: "created" };
      } else {
        const newWin = await chrome.windows.create({
          url: targetUrl,
          focused: true,
          state: "normal"
        });
        return { tabId: newWin.tabs && newWin.tabs[0] ? newWin.tabs[0].id : null, action: "created_win" };
      }
    }
  } catch (e) {
    log("Error in handleEnsureTabAndFocus:", e);
  }
  return { success: false };
}

// Background connects directly to Python WebSocket server as well!
function connectBackgroundBridge() {
  if (bgSocket && (bgSocket.readyState === WebSocket.OPEN || bgSocket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    bgSocket = new WebSocket("ws://127.0.0.1:8765");

    bgSocket.onopen = () => {
      log("Connected to Python bridge server");
      bgSocket.send(JSON.stringify({
        action: "bg_handshake",
        type: "service_worker"
      }));
    };

    bgSocket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.action === "ensure_tab_focus") {
          const res = await handleEnsureTabAndFocus(data.url);
          bgSocket.send(JSON.stringify({
            action: "ensure_tab_focus_result",
            result: res
          }));
        }
      } catch (err) {
        log("Error handling message in background:", err);
      }
    };

    bgSocket.onclose = () => {
      scheduleBgReconnect();
    };

    bgSocket.onerror = () => {
      try { bgSocket.close(); } catch (_) {}
    };
  } catch (e) {
    scheduleBgReconnect();
  }
}

function scheduleBgReconnect() {
  if (bgReconnectTimer) clearTimeout(bgReconnectTimer);
  bgReconnectTimer = setTimeout(connectBackgroundBridge, 1500);
}

connectBackgroundBridge();

// Handle runtime messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "ENSURE_FOCUS_AND_NAVIGATE") {
    handleEnsureTabAndFocus(request.targetUrl).then(result => {
      sendResponse(result);
    });
    return true; // Keep message channel open for async response
  } else if (request.type === "FOCUS_TAB") {
    const tabId = sender.tab ? sender.tab.id : null;
    const windowId = sender.tab ? sender.tab.windowId : null;
    if (windowId !== null) {
      restoreAndFocusWindow(windowId).then(() => {
        if (tabId !== null) {
          chrome.tabs.update(tabId, { active: true }).then(() => {
            sendResponse({ success: true });
          });
        } else {
          sendResponse({ success: true });
        }
      });
      return true;
    }
    sendResponse({ success: false });
  }
});
