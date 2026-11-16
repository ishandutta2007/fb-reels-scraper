// Background service worker for window, tab, and focus management
let socket = null;
let reconnectTimer = null;

function connectBridge() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket("ws://127.0.0.1:8765");

    socket.onopen = () => {
      console.log("[Background] Connected to Python bridge server");
      socket.send(JSON.stringify({
        action: "background_handshake",
        type: "service_worker"
      }));
    };

    socket.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.action === "ensure_tab_focus") {
          const targetUrl = msg.url;
          await handleEnsureTabAndFocus(targetUrl);
          socket.send(JSON.stringify({
            action: "ensure_tab_focus_result",
            status: "ready",
            url: targetUrl
          }));
        }
      } catch (e) {
        console.error("[Background] Error handling websocket message:", e);
      }
    };

    socket.onclose = () => {
      scheduleReconnect();
    };

    socket.onerror = () => {
      try { socket.close(); } catch (_) {}
    };
  } catch (e) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectBridge, 3000);
}

// Ensure the browser window is restored from minimized state and brought to foreground
async function restoreAndFocusWindow(windowId) {
  try {
    const win = await chrome.windows.get(windowId);
    const updateInfo = { focused: true };
    if (win.state === "minimized") {
      updateInfo.state = "normal";
    }
    await chrome.windows.update(windowId, updateInfo);
  } catch (err) {
    console.warn("[Background] Could not update window state:", err);
  }
}

// Bring tab to focus, un-minimize window, or open new tab if not present
async function handleEnsureTabAndFocus(targetUrl) {
  try {
    // 1. Find all open tabs
    const allTabs = await chrome.tabs.query({});
    
    // Look for tab matching targetUrl or any facebook.com tab
    let matchingTab = null;
    let fallbackFbTab = null;

    for (const tab of allTabs) {
      if (!tab.url) continue;
      if (targetUrl && tab.url.includes(targetUrl.replace(/\/+$/, ""))) {
        matchingTab = tab;
        break;
      }
      if (tab.url.includes("facebook.com")) {
        fallbackFbTab = tab;
      }
    }

    const tabToUse = matchingTab || fallbackFbTab;

    if (tabToUse) {
      // Restore window from minimized state and focus it
      await restoreAndFocusWindow(tabToUse.windowId);

      // Activate tab and reload it
      await chrome.tabs.update(tabToUse.id, { active: true, url: targetUrl || tabToUse.url });
      await chrome.tabs.reload(tabToUse.id);
    } else {
      // No Facebook tab found, open a new one in the current or newly created window
      const currentWin = await chrome.windows.getLastFocused().catch(() => null);
      if (currentWin) {
        await restoreAndFocusWindow(currentWin.id);
        await chrome.tabs.create({
          windowId: currentWin.id,
          url: targetUrl || "https://www.facebook.com/",
          active: true
        });
      } else {
        await chrome.windows.create({
          url: targetUrl || "https://www.facebook.com/",
          focused: true,
          state: "normal"
        });
      }
    }
  } catch (e) {
    console.error("[Background] Error in handleEnsureTabAndFocus:", e);
  }
}

// Listen to requests from content.js as well
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "FOCUS_TAB") {
    const tabId = sender.tab ? sender.tab.id : null;
    const windowId = sender.tab ? sender.tab.windowId : null;

    if (tabId !== null && windowId !== null) {
      (async () => {
        await restoreAndFocusWindow(windowId);
        await chrome.tabs.update(tabId, { active: true });
        sendResponse({ success: true });
      })();
      return true;
    } else {
      sendResponse({ success: false, error: "Tab/Window not identifiable" });
    }
  }
});

// Start WebSocket connection in background service worker
connectBridge();
