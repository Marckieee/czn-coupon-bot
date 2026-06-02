"""
monitor.py
Background monitoring - runs on a timer inside the main loop.

  - Hash-checks fan site pages for content changes
  - Alerts admin with actual codes when codes page updates
  - Alerts admin when a balance adjustment patch is detected
"""

import hashlib
import requests
from bs4 import BeautifulSoup

import config
import scrapers
import telegram_client

# Tracks MD5 hashes of pages to detect updates
_page_hashes: dict[str, str] = {}

# Keywords that indicate a balance adjustment patch
BALANCE_KEYWORDS = [
    "balance adjustment", "balance change", "hero adjustment",
    "artifact adjustment", "buff", "nerf", "skill change"
]


def _format_codes_alert(game_key: str, game: dict) -> str:
    """
    Scrape and format codes into an alert message including
    rewards, expiry dates and last-checked timestamp.
    """
    codes = scrapers.get_codes(game_key)

    if not codes:
        return (
            f"\U0001f4cb {game['name']} page updated but no active codes found.\n\n"
            f"\U0001f517 {game['codes_url']}"
        )

    checked_at = codes[0].get("checked_at", "unknown")
    lines = [
        f"\U0001f381 New {game['name']} Codes Detected!\n",
        f"Found {len(codes)} active code(s):\n",
    ]

    for entry in codes[:15]:
        lines.append(f"\u2022 {entry['code']}")
        lines.append(f"  \u21b3 {entry['reward']}")
        if entry.get("expiry"):
            lines.append(f"  \u23f0 Expires: {entry['expiry']}")
        lines.append("")

    lines.append(f"\U0001f517 Redeem: {game['redeem_url']}")
    lines.append(f"\n\U0001f550 Last checked: {checked_at}")

    return "\n".join(lines)


def check_pages() -> None:
    """
    Hash-check each codes page.
    Alert admin with actual codes if the page content has changed.
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
            print(f"[Monitor] {game['name']} codes page changed - scraping codes...")
            alert = _format_codes_alert(game_key, game)
            telegram_client.send_admin(alert)

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

    soup = BeautifulSoup(r.text, "html.parser")

    # Collect post links
    posts = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href and href != patch_url:
            title    = a.get_text(strip=True)
            full_url = href if href.startswith("http") else "https://epic7db.com" + href
            if title and len(title) > 5 and full_url not in seen_urls:
                seen_urls.add(full_url)
                posts.append((title, full_url))

    current_hash = hashlib.md5(r.text.encode()).hexdigest()
    patch_key    = "epic7_patches"

    if patch_key in _page_hashes and _page_hashes[patch_key] != current_hash:
        for title, url in posts[:5]:
            if any(kw in title.lower() for kw in BALANCE_KEYWORDS):
                telegram_client.send_admin(
                    f"\u2696\ufe0f Epic Seven Balance Adjustment Detected!\n\n"
                    f"\U0001f4cc {title}\n"
                    f"\U0001f517 {url}\n\n"
                    f"Check the full patch notes at:\n{patch_url}"
                )
                break

    _page_hashes[patch_key] = current_hash
