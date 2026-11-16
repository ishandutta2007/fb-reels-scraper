import asyncio
import json
import os
from typing import Dict
import websockets

CACHE_FILE = "reels_cache.json"

# Global connection management
active_tab_connection = None
active_bg_connection = None
tab_connection_event = asyncio.Event()
bg_connection_event = asyncio.Event()
response_queue = asyncio.Queue()


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
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error writing to cache file: {e}")


async def ws_handler(websocket):
    global active_tab_connection, active_bg_connection
    is_bg_worker = False

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except Exception:
                continue

            action = data.get("action")
            if action == "background_handshake":
                is_bg_worker = True
                active_bg_connection = websocket
                bg_connection_event.set()
                print("\n[+] Extension background worker connected!")
            elif action == "handshake":
                active_tab_connection = websocket
                tab_connection_event.set()
                print(f"\n[+] Connected to browser tab: {data.get('url')}")
            else:
                await response_queue.put(data)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if is_bg_worker or active_bg_connection == websocket:
            active_bg_connection = None
            bg_connection_event.clear()
            print("[-] Background worker disconnected.")
        if active_tab_connection == websocket:
            active_tab_connection = None
            tab_connection_event.clear()
            print("[-] Tab disconnected (tab navigating / reloading).")


async def get_active_tab_connection(timeout: float = 25.0):
    """Waits for an open and active Facebook tab connection."""
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        if active_tab_connection is not None:
            try:
                if not getattr(active_tab_connection, "closed", False):
                    return active_tab_connection
            except Exception:
                pass
        try:
            await asyncio.wait_for(tab_connection_event.wait(), timeout=1.0)
            if active_tab_connection is not None and not getattr(active_tab_connection, "closed", False):
                return active_tab_connection
        except asyncio.TimeoutError:
            continue
    raise TimeoutError("Timed out waiting for Facebook tab to connect/reconnect.")


async def safe_send(payload: dict, timeout: float = 15.0):
    """Safely sends payload to active tab, ensuring connection is alive."""
    ws = await get_active_tab_connection(timeout=timeout)
    await ws.send(json.dumps(payload))


async def ensure_browser_and_tab(target_url: str):
    """Signals background worker to restore window from minimized, focus it, and activate/reload/open tab."""
    print("[*] Requesting browser window restore and tab focus...")
    # Give background worker up to 3 seconds to connect if not already
    if active_bg_connection is None:
        try:
            await asyncio.wait_for(bg_connection_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass

    if active_bg_connection is not None and not getattr(active_bg_connection, "closed", False):
        try:
            await active_bg_connection.send(
                json.dumps({"action": "ensure_tab_focus", "url": target_url})
            )
            print("[+] Sent focus & tab activation request to background worker.")
        except Exception as e:
            print(f"[!] Could not send focus request to background worker: {e}")
    else:
        # Fallback if background worker is not connected yet
        try:
            ws = await get_active_tab_connection(timeout=3.0)
            await ws.send(json.dumps({"action": "focus_current_tab"}))
        except Exception:
            pass


async def start_server(host="127.0.0.1", port=8765):
    server = await websockets.serve(ws_handler, host, port)
    print(f"[*] WebSocket bridge listening on ws://{host}:{port}")
    print("[*] Waiting for browser extension...")
    return server


async def scrape_fb_reels(target_url: str = None, max_scrolls: int = 5, cache_file: str = CACHE_FILE):
    cache = load_cache(cache_file)
    print(f"[*] Loaded {len(cache)} cached reel descriptions from {cache_file}")

    # Ensure browser window is un-minimized, brought to foreground, and Facebook tab is active/reloaded
    if target_url:
        await ensure_browser_and_tab(target_url)

    # Wait for the Facebook tab handshake
    print("[*] Waiting for Facebook tab to attach...")
    tab_connection_event.clear()
    await get_active_tab_connection(timeout=30.0)
    print("[*] Page attached! Waiting 5 seconds for page content to settle...")
    await asyncio.sleep(5)

    # Step 2: Scroll and collect reel links
    all_reel_urls = set()
    print(f"\n[*] Phase 1: Collecting reel links across {max_scrolls} scrolls...")

    for i in range(max_scrolls):
        print(f"[*] Requesting scroll & collect links ({i + 1}/{max_scrolls})...")
        try:
            await safe_send(
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
                print(
                    f"    -> Collected {len(found_urls)} links on page (Total unique: {len(all_reel_urls)})"
                )
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

    # Step 3: Visit each uncached reel link and extract the full description
    if uncached_urls:
        print("\n[*] Phase 2: Visiting individual reel pages to extract full descriptions...")

    for idx, reel_url in enumerate(uncached_urls, 1):
        print(f"\n[{idx}/{len(uncached_urls)}] Visiting {reel_url}...")

        try:
            tab_connection_event.clear()
            await safe_send({"action": "navigate", "url": reel_url})

            # Wait for extension to reconnect from the new page
            print("    [*] Waiting for reel page to load...")
            await get_active_tab_connection(timeout=15.0)

            # Extra buffer for Facebook video player + comments to render
            await asyncio.sleep(4)

            # Clear old queued messages
            while not response_queue.empty():
                response_queue.get_nowait()

            # Request description extraction
            await safe_send({"action": "extract_reel_description", "url": reel_url})

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
