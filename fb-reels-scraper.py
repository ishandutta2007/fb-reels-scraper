import asyncio
import json
import websockets

# Global variables to manage active client connection and incoming messages
active_connection = None
connection_event = asyncio.Event()
response_queue = asyncio.Queue()


async def ws_handler(websocket):
    global active_connection
    active_connection = websocket
    connection_event.set()
    print(f"\n[+] Connected to browser extension session!")

    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")
            if action == "handshake":
                print(f"[+] Attached to tab: {data.get('url')}")
            else:
                # Deliver any other responses (e.g. scrape_result) to the consumer
                await response_queue.put(data)
    except websockets.exceptions.ConnectionClosed:
        print("\n[-] Browser extension disconnected.")
    finally:
        active_connection = None
        connection_event.clear()


async def start_server(host="127.0.0.1", port=8765):
    server = await websockets.serve(ws_handler, host, port)
    print(f"[*] WebSocket bridge listening on ws://{host}:{port}")
    print("[*] Waiting for Facebook tab with the bridge extension active...")
    return server


async def scrape_fb_reels_descriptions(target_url: str = None, max_scrolls: int = 5):
    descriptions = set()

    # Wait for the browser extension to connect
    await connection_event.wait()
    websocket = active_connection

    if target_url:
        print(f"[*] Sending target URL to browser: {target_url}")
        await websocket.send(json.dumps({"action": "navigate", "url": target_url}))
        print("[*] Waiting 5 seconds for page load...")
        await asyncio.sleep(5)

    print(f"[*] Starting scrape across {max_scrolls} scrolls on existing session...")

    for i in range(max_scrolls):
        print(f"[*] Requesting scroll & scrape ({i + 1}/{max_scrolls})...")
        await websocket.send(
            json.dumps(
                {
                    "action": "scroll_and_scrape",
                    "scrollIndex": i + 1,
                    "maxScrolls": max_scrolls,
                }
            )
        )

        # Wait for reply from the extension via queue
        response_data = await asyncio.wait_for(response_queue.get(), timeout=20.0)

        if response_data.get("action") == "scrape_result":
            new_items = response_data.get("descriptions", [])
            for item in new_items:
                descriptions.add(item)
            print(
                f"    -> Extracted {len(new_items)} items on page (Total unique: {len(descriptions)})"
            )

        # Sleep between scrolls to allow dynamic content rendering
        await asyncio.sleep(3)

    return list(descriptions)


async def main():
    server = await start_server()

    target_url = "https://www.facebook.com/nadeemkhancyber/reels/"
    max_scrolls = 5

    try:
        results = await scrape_fb_reels_descriptions(
            target_url=target_url, max_scrolls=max_scrolls
        )
        print(f"\nFound {len(results)} unique reel descriptions:\n")
        for idx, desc in enumerate(results, 1):
            print(f"{idx}. {desc}\n" + "-" * 40)
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
