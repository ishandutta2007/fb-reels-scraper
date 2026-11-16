import asyncio
import json
import os
from typing import Dict
import websockets

CACHE_FILE = "reels_cache.json"

# Global connection management
active_connection = None
connection_event = asyncio.Event()
response_queue = asyncio.Queue()


def load_cache() -> Dict[str, str]:
    """Loads cached reel descriptions: { reel_url: description }"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Warning reading cache file: {e}")
            return {}
    return {}


def save_cache(cache: Dict[str, str]):
    """Saves cached reel descriptions."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error writing to cache file: {e}")


async def ws_handler(websocket):
    global active_connection
    active_connection = websocket
    connection_event.set()
    print("\n[+] Connected to browser extension session!")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except Exception:
                continue

            action = data.get("action")
            if action == "handshake":
                print(f"[+] Attached to tab: {data.get('url')}")
            else:
                await response_queue.put(data)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if active_connection == websocket:
            active_connection = None
            connection_event.clear()
            print("[-] Extension disconnected (tab navigating / reloading).")


async def get_active_connection(timeout: float = 20.0):
    """Waits for an open and active connection."""
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        if active_connection is not None:
            # Check if socket is open
            try:
                # websockets 11+ has .closed or .state
                if not getattr(active_connection, "closed", False):
                    return active_connection
            except Exception:
                pass
        try:
            await asyncio.wait_for(connection_event.wait(), timeout=1.0)
            if active_connection is not None and not getattr(
                active_connection, "closed", False
            ):
                return active_connection
        except asyncio.TimeoutError:
            continue
    raise TimeoutError("Timed out waiting for browser extension to connect/reconnect.")


async def safe_send(payload: dict, timeout: float = 15.0):
    """Safely sends payload, ensuring connection is alive or reconnects."""
    ws = await get_active_connection(timeout=timeout)
    await ws.send(json.dumps(payload))


async def start_server(host="127.0.0.1", port=8765):
    server = await websockets.serve(ws_handler, host, port)
    print(f"[*] WebSocket bridge listening on ws://{host}:{port}")
    print("[*] Waiting for Facebook tab with the bridge extension active...")
    return server


async def scrape_fb_reels(target_url: str = None, max_scrolls: int = 5):
    cache = load_cache()
    print(f"[*] Loaded {len(cache)} cached reel descriptions from {CACHE_FILE}")

    # Wait for initial extension handshake
    await get_active_connection()

    # Step 1: Navigate to the reels profile/page if provided
    if target_url:
        print(f"[*] Navigating to reels grid: {target_url}")
        # Clear connection event before navigating to wait cleanly for the new page handshake
        connection_event.clear()
        try:
            await safe_send({"action": "navigate", "url": target_url})
        except Exception:
            pass

        print("[*] Waiting for reels tab to load and connect...")
        try:
            await get_active_connection(timeout=15.0)
            await asyncio.sleep(4)
        except Exception:
            print("[!] Tab taking long to reconnect, will continue...")

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
    print(
        f"[*] {cached_count} reels already in cache. {len(uncached_urls)} remaining to visit & extract."
    )

    # Step 3: Visit each uncached reel link and extract the full description
    if uncached_urls:
        print(
            "\n[*] Phase 2: Visiting individual reel pages to extract full descriptions..."
        )

    for idx, reel_url in enumerate(uncached_urls, 1):
        print(f"\n[{idx}/{len(uncached_urls)}] Visiting {reel_url}...")

        try:
            # Signal extension to navigate
            # In single-page applications or standard navigation, we clear event so we wait for the next page
            connection_event.clear()
            await safe_send({"action": "navigate", "url": reel_url})

            # Wait for extension to reconnect from the new page
            print("    [*] Waiting for reel page to load...")
            await get_active_connection(timeout=15.0)

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
                    save_cache(cache)
                    print(
                        f"    -> [SUCCESS] Extracted ({len(desc)} chars): {desc[:80]}..."
                    )
                else:
                    cache[reel_url] = "[No description found]"
                    save_cache(cache)
                    print("    -> [INFO] No description found on this reel.")
        except asyncio.TimeoutError:
            print(f"    [!] Timeout waiting for response on {reel_url}")
        except websockets.exceptions.ConnectionClosed:
            print(f"    [!] Connection closed while handling {reel_url}")
        except Exception as e:
            print(f"    [!] Error extracting {reel_url}: {e}")

        await asyncio.sleep(2)

    return cache


async def main():
    server = await start_server()

    target_url = "https://www.facebook.com/nadeemkhancyber/reels/"
    max_scrolls = 5

    try:
        cache = await scrape_fb_reels(target_url=target_url, max_scrolls=max_scrolls)
        print(f"\n================ Scrape Complete ================")
        print(f"Total Cached Reels: {len(cache)}\n")
        for idx, (url, desc) in enumerate(cache.items(), 1):
            print(f"[{idx}] {url}\n{desc}\n" + "-" * 50)
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
