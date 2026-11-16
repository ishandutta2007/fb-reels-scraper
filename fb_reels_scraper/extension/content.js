(() => {
  let socket = null;
  let isConnected = false;
  let reconnectTimer = null;

  function updateStatus(status, connected = false) {
    chrome.runtime.sendMessage({
      type: "STATUS_UPDATE",
      status: status,
      connected: connected
    }).catch(() => {});
  }

  // Request background script to focus window and activate this tab
  async function focusCurrentTab() {
    return new Promise(resolve => {
      chrome.runtime.sendMessage({ type: "FOCUS_TAB" }, response => {
        resolve(response);
      });
    });
  }

  // Collect reel links from the reels grid/listing page
  function extractReelLinks() {
    const urls = new Set();
    const links = document.querySelectorAll("a[href*='/reel/']");

    links.forEach(link => {
      try {
        const href = link.href;
        if (!href) return;
        const match = href.match(/https?:\/\/(?:www\.)?facebook\.com\/reel\/(\d+)/i);
        if (match) {
          urls.add(`https://www.facebook.com/reel/${match[1]}/`);
        } else if (href.includes("/reel/")) {
          // Fallback to cleaned URL without tracking params
          const cleanUrl = href.split("?")[0].replace(/\/+$/, "") + "/";
          urls.add(cleanUrl);
        }
      } catch (_) {}
    });

    return Array.from(urls);
  }

  // Extract full description from a single reel viewer page
  async function extractSingleReelDescription() {
    // 1. Expand "See more" or "more" buttons if present
    const clickableButtons = Array.from(
      document.querySelectorAll('div[role="button"], span[role="button"], a[role="button"]')
    );
    for (const btn of clickableButtons) {
      const text = (btn.innerText || "").trim().toLowerCase();
      if (text === "see more" || text === "… more" || text === "...more" || text === "more") {
        try {
          btn.click();
        } catch (_) {}
      }
    }

    // Wait a brief moment for dynamic text expansion
    await new Promise(res => setTimeout(res, 500));

    // 2. Select potential description containers
    // Facebook reel captions are typically rendered in dir="auto" elements or within data-ad-preview="message"
    const selectors = [
      'div[data-ad-preview="message"]',
      'div[dir="auto"]',
      'span[dir="auto"]'
    ];

    const blacklistedPrefixes = [
      "like", "comment", "share", "follow", "remix", "audio", "reels",
      "watch more reels", "send in whatsapp", "save video", "copy link",
      "original audio", "suggested for you"
    ];

    const candidates = [];

    document.querySelectorAll(selectors.join(", ")).forEach(el => {
      // Ignore if element is inside action buttons or navigation header
      if (el.closest('header, nav, ul, [role="navigation"]')) return;

      const txt = (el.innerText || "").trim();
      if (!txt || txt.length < 5) return;

      const lower = txt.toLowerCase();
      // Skip common UI button strings and view counters
      const isBlacklisted = blacklistedPrefixes.some(prefix => lower.startsWith(prefix) || lower === prefix);
      if (isBlacklisted) return;

      // Skip pure numeric / timestamp strings like "2d", "1.2K views"
      if (/^(\d+(\.\d+)?[KM]?\s*(views|likes|shares|comments)?|\d+[smhdw])$/i.test(lower)) return;

      candidates.push(txt);
    });

    // Remove duplicates while keeping order
    const uniqueCandidates = Array.from(new Set(candidates));

    // Longest element text block in the reel info column is usually the full description
    uniqueCandidates.sort((a, b) => b.length - a.length);

    return uniqueCandidates.length > 0 ? uniqueCandidates[0] : "";
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      socket = new WebSocket("ws://127.0.0.1:8765");

      socket.onopen = () => {
        isConnected = true;
        updateStatus("Connected to Python scraper", true);
        socket.send(JSON.stringify({
          action: "handshake",
          url: window.location.href,
          title: document.title
        }));
      };

      socket.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.action === "scroll_and_collect_links") {
            // Bring browser window to foreground and switch to this FB tab before scrolling
            await focusCurrentTab();
            await new Promise(r => setTimeout(r, 400));

            const reelUrls = extractReelLinks();

            // Scroll down to trigger Facebook lazy-loading more reels
            window.scrollTo(0, document.body.scrollHeight);

            socket.send(JSON.stringify({
              action: "collect_links_result",
              urls: reelUrls,
              currentScroll: message.scrollIndex,
              maxScrolls: message.maxScrolls,
              url: window.location.href
            }));
          } else if (message.action === "navigate") {
            if (message.url && window.location.href !== message.url) {
              window.location.href = message.url;
            }
          } else if (message.action === "extract_reel_description") {
            const description = await extractSingleReelDescription();
            socket.send(JSON.stringify({
              action: "extract_reel_result",
              url: window.location.href,
              requestedUrl: message.url,
              description: description
            }));
          }
        } catch (err) {
          console.error("Error processing websocket message:", err);
        }
      };

      socket.onclose = () => {
        isConnected = false;
        updateStatus("Disconnected (reconnecting...)", false);
        scheduleReconnect();
      };

      socket.onerror = (err) => {
        isConnected = false;
        updateStatus("Connection error (check if python script is running)", false);
        try { socket.close(); } catch (_) {}
      };
    } catch (e) {
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 3000);
  }

  // Connect on Facebook pages
  connect();

  // Listen for queries from popup
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "GET_STATUS") {
      sendResponse({
        connected: isConnected,
        url: window.location.href
      });
    }
    return true;
  });
})();
