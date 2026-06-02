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
