"""
monitor.py
Background monitoring — runs on a timer inside the main loop.
Hash-checks fan site pages for any content change and alerts admin.
"""

import hashlib
import requests

import config
import telegram_client

# Tracks MD5 hashes of codes pages to detect updates
_page_hashes: dict[str, str] = {}

# Keywords that indicate a balance adjustment patch
BALANCE_KEYWORDS = [
    "balance adjustment", "balance change", "hero adjustment",
    "artifact adjustment", "buff", "nerf", "skill change"
]


def check_pages() -> None:
    """
    Hash-check each codes page.
    Alert admin if the page content has changed since last check.
    """
    for game_key, game in config.GAMES.items():
        url = game["codes_url"]
        try:
            r = requests.get(url, headers=config.SCRAPE_HEADERS, timeout=15)
            r.raise_for_status()
            current_hash = hashlib.md5(r.text.encode()).hexdigest()
        except Exception as e:
            print(f"[Monitor] Could not fetch {url}: {e}")
            continue

        if url in _page_hashes and _page_hashes[url] != current_hash:
            telegram_client.send_admin(
                f"📋 {game['name']} codes page updated!\n\n"
                f"Run /codes {game_key} to see the latest codes.\n"
                f"🔗 {url}"
            )

        _page_hashes[url] = current_hash


def check_epic7_patches() -> None:
    """
    Scrape epic7db.com/news/patch-notes for new posts.
    Alert admin if a new balance adjustment patch is detected.
    """
    game = config.GAMES["epic7"]
    patch_url = game.get("patch_url")
    if not patch_url:
        return

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[Monitor] Could not fetch patch notes: {e}")
        return

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")

    # Each post is an <a> tag linking to /news/...
    posts = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href and href != patch_url:
            title = a.get_text(strip=True)
            full_url = href if href.startswith("http") else "https://epic7db.com" + href
            if title and len(title) > 5:
                posts.append((title, full_url))

    # Deduplicate
    seen_urls = set()
    unique_posts = []
    for title, url in posts:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_posts.append((title, url))

    # Check for new balance-related posts
    current_hash = hashlib.md5(r.text.encode()).hexdigest()
    patch_key = "epic7_patches"

    if patch_key in _page_hashes and _page_hashes[patch_key] != current_hash:
        # Page changed — check if any post titles mention balance adjustments
        for title, url in unique_posts[:5]:
            title_lower = title.lower()
            if any(kw in title_lower for kw in BALANCE_KEYWORDS):
                telegram_client.send_admin(
                    f"⚖️ Epic Seven Balance Adjustment Detected!\n\n"
                    f"📌 {title}\n"
                    f"🔗 {url}\n\n"
                    f"Check the full patch notes at:\n{patch_url}"
                )
                break  # Only alert once per check

    _page_hashes[patch_key] = current_hash
