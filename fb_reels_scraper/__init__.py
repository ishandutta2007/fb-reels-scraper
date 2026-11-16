"""Facebook Reels Scraper Bridge

Scrape Facebook Reels descriptions using an existing browser session via a WebSocket bridge.
"""

from .scraper import scrape_fb_reels, start_server

__version__ = "1.0.0"
__all__ = ["scrape_fb_reels", "start_server"]
