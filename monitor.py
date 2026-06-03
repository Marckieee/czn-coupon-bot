"""
monitor.py
Background monitoring - runs on a timer inside the main loop.

  - Hash-checks fan site pages for content changes
  - Broadcasts alerts with actual codes to all subscribers
  - Alerts admin when a balance adjustment patch is detected
  - Tracks last/next check times in the database
"""

import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

import config
import scrapers
import telegram_client
import database

# Tracks MD5 hashes of pages to detect updates
_page_hashes: dict[str, str] = {}

# Consecutive failure counts per URL
_fail_counts: dict[str, int] = {}
MAX_FAILS = 3

# Keywords that indicate a balance adjustment patch
BALANCE_KEYWORDS = [
    "balance adjustment", "balance change", "hero adjustment",
    "artifact adjustment", "buff", "nerf", "skill change"
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _next_check_time() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")


def _format_codes_alert(game_key: str, game: dict) -> str:
    """
    Scrape and format codes into an alert message including
    rewards, expiry dates and last-checked timestamp.
    """
    codes = scrapers.get_codes(game_key)

    if not codes:
        return (
            f"\U0001f4cb {game['name']} page updated but no active codes found yet.\n\n"
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


def _check_expiring_codes() -> None:
    """
    Check if any codes are expiring within 24 hours.
    Broadcast a reminder to all subscribers if so.
    """
    from datetime import datetime
    import re

    for game_key, game in config.GAMES.items():
        codes = scrapers.get_codes(game_key)
        expiring_soon = []

        for entry in codes:
            expiry = entry.get("expiry")
            if not expiry:
                continue
            # Try to parse common date formats
            for fmt in ("%d %b %Y", "%Y-%m-%d", "%B %d, %Y", "%d/%m/%Y"):
                try:
                    expiry_date = datetime.strptime(expiry.strip(), fmt)
                    delta = expiry_date - datetime.utcnow()
                    if 0 <= delta.total_seconds() <= 86400:  # within 24 hours
                        expiring_soon.append(entry)
                    break
                except ValueError:
                    continue

        if expiring_soon:
            lines = [f"\u23f0 Expiring Soon \u2014 {game['name']} Codes!\n"]
            for entry in expiring_soon:
                lines.append(f"\u2022 {entry['code']}")
                lines.append(f"  \u21b3 {entry['reward']}")
                lines.append(f"  \u23f0 Expires: {entry['expiry']}\n")
            lines.append(f"\U0001f517 Redeem now: {game['redeem_url']}")

            alert = "\n".join(lines)
            subscribers = database.get_all_subscribers()
            if subscribers:
                telegram_client.broadcast(subscribers, alert)


def check_pages() -> None:
    """
    Hash-check each codes page.
    Broadcast actual codes to all subscribers if the page changed.
    Alert admin if a source keeps failing.
    """
    for game_key, game in config.GAMES.items():
        url = game["codes_url"]
        try:
            r = requests.get(url, headers=config.SCRAPE_HEADERS, timeout=15)
            r.raise_for_status()
            current_hash = hashlib.md5(r.text.encode()).hexdigest()
            _fail_counts[url] = 0  # reset on success

        except Exception as e:
            _fail_counts[url] = _fail_counts.get(url, 0) + 1
            print(f"[Monitor] Fetch failed for {url} ({_fail_counts[url]}/{MAX_FAILS}): {e}")

            if _fail_counts[url] >= MAX_FAILS:
                telegram_client.send_admin(
                    f"\u26a0\ufe0f Source down: {game['name']} codes page\n\n"
                    f"Failed {MAX_FAILS} checks in a row.\n"
                    f"\U0001f517 {url}"
                )
                _fail_counts[url] = 0  # reset so we don't spam
            continue

        if url in _page_hashes and _page_hashes[url] != current_hash:
            print(f"[Monitor] {game['name']} codes page changed - broadcasting...")
            alert = _format_codes_alert(game_key, game)

            # Broadcast to all subscribers
            subscribers = database.get_all_subscribers()
            if subscribers:
                ok, fail = telegram_client.broadcast(subscribers, alert)
                print(f"[Monitor] Broadcast sent to {ok} subscribers ({fail} failed)")
            else:
                # No subscribers yet - just alert admin
                telegram_client.send_admin(alert)

        _page_hashes[url] = current_hash

        # Update monitor state in DB
        database.update_monitor_state(
            key        = f"{game_key}_codes",
            last_check = _now(),
            next_check = _next_check_time(),
            status     = "ok"
        )

    # Also check for expiring codes
    _check_expiring_codes()


def check_epic7_patches() -> None:
    """
    Scrape epic7db.com/news/patch-notes for new posts.
    Broadcast to all subscribers if a balance adjustment is detected.
    """
    game      = config.GAMES["epic7"]
    patch_url = game.get("patch_url")
    if not patch_url:
        return

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
        _fail_counts[patch_url] = 0

    except Exception as e:
        _fail_counts[patch_url] = _fail_counts.get(patch_url, 0) + 1
        print(f"[Monitor] Patch fetch failed ({_fail_counts[patch_url]}/{MAX_FAILS}): {e}")

        if _fail_counts[patch_url] >= MAX_FAILS:
            telegram_client.send_admin(
                f"\u26a0\ufe0f Source down: Epic Seven patch notes page\n\n"
                f"Failed {MAX_FAILS} checks in a row.\n"
                f"\U0001f517 {patch_url}"
            )
            _fail_counts[patch_url] = 0
        return

    soup = BeautifulSoup(r.text, "html.parser")

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
                alert = (
                    f"\u2696\ufe0f Epic Seven Balance Adjustment Detected!\n\n"
                    f"\U0001f4cc {title}\n"
                    f"\U0001f517 {url}\n\n"
                    f"Check the full patch notes at:\n{patch_url}"
                )

                # Broadcast to all subscribers
                subscribers = database.get_all_subscribers()
                if subscribers:
                    ok, fail = telegram_client.broadcast(subscribers, alert)
                    print(f"[Monitor] Patch alert sent to {ok} subscribers ({fail} failed)")
                else:
                    telegram_client.send_admin(alert)
                break

    _page_hashes[patch_key] = current_hash

    # Update monitor state in DB
    database.update_monitor_state(
        key        = "epic7_patches",
        last_check = _now(),
        next_check = _next_check_time(),
        status     = "ok"
    )
