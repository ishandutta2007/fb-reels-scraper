import time
from playwright.sync_api import sync_playwright

def scrape_fb_reels_descriptions(profile_url: str, max_scrolls: int = 10):
    descriptions = set()

    with sync_playwright() as p:
        # Launch visible browser (headless=False helps avoid immediate bot detection)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"Navigating to {profile_url}...")
        page.goto(profile_url, wait_until="networkidle")

        # Pause to allow manual login or closing the login popup if it appears
        input("Log in or close any login popups in the browser, then press Enter here to start scraping...")

        for i in range(max_scrolls):
            print(f"Scrolling ({i + 1}/{max_scrolls})...")
            
            # Facebook Reel links typically contain '/reel/' in their href attribute
            reel_links = page.locator("a[href*='/reel/']").all()
            
            for link in reel_links:
                # Facebook often places the caption/description inside aria-label or inner text
                aria_label = link.get_attribute("aria-label")
                inner_text = link.inner_text().strip()
                
                # Filter out short UI labels like "Reels" or view counts
                text_content = aria_label if aria_label else inner_text
                if text_content and len(text_content) > 15:
                    # Clean up newlines
                    clean_text = " ".join(text_content.split())
                    descriptions.add(clean_text)

            # Scroll down to trigger loading of more reels
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)  # Wait for new content to load

        browser.close()

    return list(descriptions)

if __name__ == "__main__":
    target_url = "https://www.facebook.com/nadeemkhancyber/reels/"
    
    # Increase max_scrolls to fetch more reels from the page
    results = scrape_fb_reels_descriptions(target_url, max_scrolls=5)
    
    print(f"\nFound {len(results)} unique reel descriptions:\n")
    for idx, desc in enumerate(results, 1):
        print(f"{idx}. {desc}\n" + "-"*40)
