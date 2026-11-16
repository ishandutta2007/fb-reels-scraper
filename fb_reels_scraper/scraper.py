import asyncio
import json
import os
import platform
import subprocess
import webbrowser
from typing import Dict
import websockets

DATA_DIR = "scraped_data"
CACHE_FILE = os.path.join(DATA_DIR, "reels_cache.json")

# Store connected tab websockets: websocket -> tab_url
tab_connections: Dict[websockets.WebSocketServerProtocol, str] = {}
bg_connections = set()
tab_connected_event = asyncio.Event()
bg_connected_event = asyncio.Event()
response_queue = asyncio.Queue()


def restore_browser_window_os():
    """Restores minimized browser windows to foreground."""
    if platform.system() != "Windows":
        return

    ps_script = """
Add-Type @"
  using System;
  using System.Runtime.InteropServices;
  public class Win32 {
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
  }
"@ -ErrorAction SilentlyContinue

$browsers = @('chrome', 'msedge', 'brave', 'opera', 'firefox')
Get-Process | Where-Object { $browsers -contains $_.ProcessName } | ForEach-Object {
    if ($_.MainWindowHandle -ne 0) {
        if ([Win32]::IsIconic($_.MainWindowHandle)) {
            [Win32]::ShowWindowAsync($_.MainWindowHandle, 9)
        }
        [Win32]::SetForegroundWindow($_.MainWindowHandle)
    }
}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=3,
        )
    except Exception:
        pass


def load_cache(cache_file: str = CACHE_FILE) -> Dict[str, str]:
    """Loads cached reel descriptions: { reel_url: description }"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Warning reading cache file: {e}")
            return {}
    return {}


def save_cache(cache: Dict[str, str], cache_file: str = CACHE_FILE):
    """Saves cached reel descriptions."""
    try:
        parent_dir = os.path.dirname(cache_file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error writing to cache file: {e}")


def is_url_match(tab_url: str, target_url: str) -> bool:
    """Checks if a tab's URL matches the target Facebook reels URL."""
    if not tab_url or not target_url:
        return False
    norm_tab = tab_url.split("?")[0].rstrip("/").lower()
    norm_target = target_url.split("?")[0].rstrip("/").lower()
    return norm_tab == norm_target or norm_tab.endswith(norm_target.replace("https://www.facebook.com", ""))


async def ws_handler(websocket):
    global tab_connections, bg_connections
    tab_url = ""
    is_bg = False

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except Exception:
                continue

            action = data.get("action")
            if action == "bg_handshake":
                is_bg = True
                bg_connections.add(websocket)
                bg_connected_event.set()
                print("[+] Extension background service worker connected!")
            elif action == "handshake":
                tab_url = data.get("url", "")
                tab_connections[websocket] = tab_url
                tab_connected_event.set()
                print(f"[+] Attached to tab: {tab_url}")
            else:
                await response_queue.put(data)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if is_bg or websocket in bg_connections:
            bg_connections.discard(websocket)
            if not bg_connections:
                bg_connected_event.clear()
        if websocket in tab_connections:
            closed_url = tab_connections.pop(websocket)
            print(f"[-] Tab closed/navigated away: {closed_url}")
        if not tab_connections:
            tab_connected_event.clear()


async def get_target_tab_connection(target_url: str = None, timeout: float = 30.0):
    """Finds a live WebSocket connection specifically matching target_url."""
    end_time = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < end_time:
        for ws, url in list(tab_connections.items()):
            if not getattr(ws, "closed", False):
                if target_url is None or is_url_match(url, target_url):
                    return ws

        try:
            await asyncio.wait_for(tab_connected_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    for ws in list(tab_connections.keys()):
        if not getattr(ws, "closed", False):
            return ws

    raise TimeoutError(f"Timed out waiting for connection on target URL: {target_url}")


async def get_any_tab_connection(timeout: float = 25.0):
    """Waits for any open Facebook tab connection."""
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        for ws in list(tab_connections.keys()):
            if not getattr(ws, "closed", False):
                return ws
        try:
            await asyncio.wait_for(tab_connected_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass
    raise TimeoutError("Timed out waiting for any Facebook tab to connect.")


async def safe_send(ws, payload: dict):
    """Safely sends payload on a websocket connection."""
    await ws.send(json.dumps(payload))


async def start_server(host="127.0.0.1", port=8765):
    server = await websockets.serve(ws_handler, host, port)
    print(f"[*] WebSocket bridge listening on ws://{host}:{port}")
    return server


async def scrape_fb_reels(target_url: str = None, max_scrolls: int = 5, cache_file: str = CACHE_FILE):
    cache = load_cache(cache_file)
    print(f"[*] Loaded {len(cache)} cached reel descriptions from {cache_file}")

    # Un-minimize browser window
    restore_browser_window_os()

    # Step 1: Check if an extension background or tab is already connected
    print("[*] Checking for browser extension connection...")
    
    # Wait up to 2 seconds to see if anything connects
    try:
        await asyncio.wait_for(tab_connected_event.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        pass

    # If background worker is connected, tell it to focus and open target_url
    told_bg = False
    for bg_ws in list(bg_connections):
        if not getattr(bg_ws, "closed", False):
            print(f"[*] Requesting background worker to focus and navigate to: {target_url}")
            await safe_send(bg_ws, {"action": "ensure_tab_focus", "url": target_url})
            told_bg = True
            break

    # If no background worker or tab responded, open directly via default browser
    if not told_bg and not tab_connections:
        print(f"[*] Opening {target_url or 'https://www.facebook.com/'} in browser...")
        webbrowser.open(target_url or "https://www.facebook.com/")
        restore_browser_window_os()

    # Step 2: Now wait for the Facebook tab to attach
    print(f"[*] Waiting for Facebook tab to attach ({target_url or 'any'})...")
    tab_ws = await get_target_tab_connection(target_url=target_url, timeout=30.0)
    print(f"[+] Successfully attached to tab: {tab_connections.get(tab_ws, '')}")

    print("[*] Target reels page active. Waiting 4 seconds for video grid to settle...")
    await asyncio.sleep(4)

    # Step 3: Scroll and collect reel links
    all_reel_urls = set()
    no_new_links_count = 0
    print(f"\n[*] Phase 1: Collecting reel links across {max_scrolls} scrolls on {target_url or 'active tab'}...")

    for i in range(max_scrolls):
        prev_count = len(all_reel_urls)
        print(f"[*] Requesting scroll & collect links ({i + 1}/{max_scrolls})...")
        try:
            tab_ws = await get_target_tab_connection(target_url=target_url, timeout=10.0)
            await safe_send(
                tab_ws,
                {
                    "action": "scroll_and_collect_links",
                    "scrollIndex": i + 1,
                    "maxScrolls": max_scrolls,
                }
            )

            response_data = await asyncio.wait_for(response_queue.get(), timeout=20.0)
            if response_data.get("action") == "collect_links_result":
                found_urls = response_data.get("urls", [])
                for u in found_urls:
                    all_reel_urls.add(u)
                new_discovered = len(all_reel_urls) - prev_count
                print(
                    f"    -> Collected {len(found_urls)} links on page (+{new_discovered} new, total unique: {len(all_reel_urls)})"
                )

                if new_discovered == 0:
                    no_new_links_count += 1
                    print(f"    [!] No new reel links found on this scroll ({no_new_links_count}/3 consecutive scrolls).")
                else:
                    no_new_links_count = 0

                if no_new_links_count >= 3:
                    print(f"[*] No new reel links discovered for 3 consecutive scrolls. Reached the end of the reels feed or dynamic loading finished. Skipping remaining scrolls.")
                    break
        except asyncio.TimeoutError:
            print("[!] Timeout waiting for scroll response from browser.")
        except Exception as e:
            print(f"[!] Error during scroll phase: {e}")

        await asyncio.sleep(3)

    print(f"\n[*] Total unique reel URLs found: {len(all_reel_urls)}")

    # Filter out already cached URLs
    uncached_urls = [u for u in all_reel_urls if u not in cache or not cache[u]]
    cached_count = len(all_reel_urls) - len(uncached_urls)
    print(f"[*] {cached_count} reels already in cache. {len(uncached_urls)} remaining to visit & extract.")

    # Step 4: Visit each uncached reel link and extract the full description
    if uncached_urls:
        print("\n[*] Phase 2: Visiting individual reel pages to extract full descriptions...")

    for idx, reel_url in enumerate(uncached_urls, 1):
        print(f"\n[{idx}/{len(uncached_urls)}] Visiting {reel_url}...")

        try:
            tab_ws = await get_any_tab_connection(timeout=15.0)
            await safe_send(tab_ws, {"action": "navigate", "url": reel_url})

            # Wait for extension to reconnect from the new reel page
            print("    [*] Waiting for reel page to load...")
            tab_ws = await get_target_tab_connection(target_url=reel_url, timeout=15.0)

            # Extra buffer for Facebook video player + comments to render
            await asyncio.sleep(4)

            # Clear old queued messages
            while not response_queue.empty():
                response_queue.get_nowait()

            # Request description extraction
            await safe_send(tab_ws, {"action": "extract_reel_description", "url": reel_url})

            resp = await asyncio.wait_for(response_queue.get(), timeout=15.0)
            if resp.get("action") == "extract_reel_result":
                desc = (resp.get("description") or "").strip()
                if desc:
                    cache[reel_url] = desc
                    save_cache(cache, cache_file)
                    print(f"    -> [SUCCESS] Extracted ({len(desc)} chars): {desc[:80]}...")
                else:
                    cache[reel_url] = "[No description found]"
                    save_cache(cache, cache_file)
                    print("    -> [INFO] No description found on this reel.")
        except asyncio.TimeoutError:
            print(f"    [!] Timeout waiting for response on {reel_url}")
        except websockets.exceptions.ConnectionClosed:
            print(f"    [!] Connection closed while handling {reel_url}")
        except Exception as e:
            print(f"    [!] Error extracting {reel_url}: {e}")

        await asyncio.sleep(2)

    return cache
