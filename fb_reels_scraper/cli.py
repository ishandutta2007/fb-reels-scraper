import argparse
import asyncio
import os
import shutil
import sys
from .scraper import scrape_fb_reels, start_server


def get_extension_path() -> str:
    """Returns the absolute path to the bundled Chrome extension directory."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    ext_path = os.path.join(pkg_dir, "extension")
    if os.path.exists(ext_path):
        return ext_path
    # Fallback to repo root if run from source
    repo_root = os.path.dirname(pkg_dir)
    fallback_ext = os.path.join(repo_root, "extension")
    if os.path.exists(fallback_ext):
        return fallback_ext
    return ext_path


def get_default_cache_file(username: str) -> str:
    """Returns default cache path under scraped_data/ based on username."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in username.strip())
    if not safe_name:
        safe_name = "reels"
    return os.path.join("scraped_data", f"{safe_name}_reels.json")


def format_user_reels_url(user_input: str) -> str:
    """Constructs the Facebook reels URL from a username, page name, or URL."""
    cleaned = user_input.strip()
    # If the user already provided a full URL, ensure proper trailing structure
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        cleaned = cleaned.rstrip("/")
        if not cleaned.endswith("/reels"):
            cleaned += "/reels"
        return cleaned + "/"

    # Strip any leading '@' or extra slashes
    username = cleaned.lstrip("@").strip("/")
    return f"https://www.facebook.com/{username}/reels/"


async def async_main(args, target_url: str):
    server = await start_server(host=args.host, port=args.port)

    try:
        cache = await scrape_fb_reels(
            target_url=target_url,
            max_scrolls=args.max_scrolls,
            cache_file=args.cache_file,
        )
        print(f"\n================ Scrape Complete ================")
        print(f"Total Cached Reels: {len(cache)}\n")
        for idx, (url, desc) in enumerate(cache.items(), 1):
            print(f"[{idx}] {url}\n{desc}\n" + "-" * 50)
    finally:
        server.close()
        await server.wait_closed()


def main():
    parser = argparse.ArgumentParser(
        prog="fb-reels-scraper",
        description="Scrape Facebook Reels descriptions via browser extension WebSocket bridge.",
    )
    parser.add_argument(
        "--user",
        "-u",
        dest="user",
        type=str,
        default="nadeemkhancyber",
        help="Target Facebook username, page handle, or profile name (default: nadeemkhancyber)",
    )
    parser.add_argument(
        "--scrolls",
        "-s",
        dest="max_scrolls",
        type=int,
        default=20,
        help="Number of times to scroll down to collect reels links (default: 20)",
    )
    parser.add_argument(
        "--cache-file",
        "-c",
        dest="cache_file",
        type=str,
        default=None,
        help="Path to JSON cache file (default: scraped_data/<username>_reels.json)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="WebSocket bridge host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8765,
        help="WebSocket bridge port (default: 8765)",
    )
    parser.add_argument(
        "--install-extension",
        dest="export_extension_to",
        type=str,
        nargs="?",
        const="./fb_reels_extension",
        metavar="DIR",
        help="Export the bundled Chrome extension to a local directory for easy loading in browser (default: ./fb_reels_extension)",
    )
    parser.add_argument(
        "--extension-path",
        action="store_true",
        help="Print the installed path to the bundled Chrome extension directory and exit.",
    )

    args = parser.parse_args()

    if args.extension_path:
        path = get_extension_path()
        print(path)
        sys.exit(0)

    if args.export_extension_to:
        src = get_extension_path()
        dst = os.path.abspath(args.export_extension_to)
        if not os.path.exists(src):
            print(f"[!] Error: Extension source directory not found at {src}")
            sys.exit(1)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"[+] Successfully exported Chrome extension to: {dst}")
        print("[+] In your browser, visit chrome://extensions/ -> Load unpacked -> select this folder.")
        sys.exit(0)

    target_url = format_user_reels_url(args.user)
    if not args.cache_file:
        args.cache_file = get_default_cache_file(args.user)

    try:
        asyncio.run(async_main(args, target_url))
    except KeyboardInterrupt:
        print("\n[!] Scraping cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
