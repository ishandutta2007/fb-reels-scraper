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

  function extractReelDescriptions() {
    const descriptions = new Set();
    const links = document.querySelectorAll("a[href*='/reel/']");

    links.forEach(link => {
      const ariaLabel = link.getAttribute("aria-label");
      const innerText = link.innerText ? link.innerText.trim() : "";
      const textContent = ariaLabel || innerText;

      if (textContent && textContent.length > 15) {
        const cleanText = textContent.replace(/\s+/g, " ").trim();
        descriptions.add(cleanText);
      }
    });

    return Array.from(descriptions);
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

          if (message.action === "scroll_and_scrape") {
            const descriptions = extractReelDescriptions();
            
            // Scroll down
            window.scrollTo(0, document.body.scrollHeight);

            socket.send(JSON.stringify({
              action: "scrape_result",
              descriptions: descriptions,
              currentScroll: message.scrollIndex,
              maxScrolls: message.maxScrolls,
              url: window.location.href
            }));
          } else if (message.action === "navigate") {
            if (message.url && window.location.href !== message.url) {
              window.location.href = message.url;
            }
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
