"""
monitor.py
Background monitoring - runs on a timer inside the main loop.

  - Hash-checks fan site pages for content changes
  - Saves newly detected codes to database
  - Broadcasts ONLY new codes to all subscribers
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

# Balance patch keywords
BALANCE_KEYWORDS = [
    "balance adjustment", "balance change", "hero adjustment",
    "artifact adjustment", "buff", "nerf", "skill change"
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _next_check_time() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")


def _format_new_codes_alert(game_key: str, game: dict, new_codes: list[dict]) -> str:
    """Format an alert message for newly detected codes only."""
    lines = [
        f"\U0001f381 New {game['name']} Codes Detected!\n",
        f"{len(new_codes)} new code(s) found:\n",
    ]

    for entry in new_codes:
        lines.append(f"\u2022 {entry['code']}")
        lines.append(f"  \u21b3 {entry['reward']}")
        if entry.get("expiry"):
            lines.append(f"  \u23f0 Expires: {entry['expiry']}")
        lines.append("")

    lines.append(f"\U0001f517 Redeem: {game['redeem_url']}")
    lines.append(f"\n\U0001f550 Detected: {_now()}")

    return "\n".join(lines)


def _check_expiring_codes() -> None:
    """Warn subscribers 24hrs before a code expires."""
    for game_key, game in config.GAMES.items():
        codes = scrapers.get_codes(game_key)
        expiring_soon = []

        for entry in codes:
            expiry = entry.get("expiry")
            if not expiry:
                continue
            for fmt in ("%d %b %Y", "%Y-%m-%d", "%B %d, %Y", "%d/%m/%Y"):
                try:
                    expiry_date = datetime.strptime(expiry.strip(), fmt)
                    delta = expiry_date - datetime.utcnow()
                    if 0 <= delta.total_seconds() <= 86400:
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
    Only broadcast if genuinely NEW codes are detected.
    """
    for game_key, game in config.GAMES.items():
        url = game["codes_url"]
        try:
            r = requests.get(url, headers=config.SCRAPE_HEADERS, timeout=15)
            r.raise_for_status()
            current_hash = hashlib.md5(r.text.encode()).hexdigest()
            _fail_counts[url] = 0

        except Exception as e:
            _fail_counts[url] = _fail_counts.get(url, 0) + 1
            print(f"[Monitor] Fetch failed for {url} ({_fail_counts[url]}/{MAX_FAILS}): {e}")
            if _fail_counts[url] >= MAX_FAILS:
                telegram_client.send_admin(
                    f"\u26a0\ufe0f Source down: {game['name']} codes page\n\n"
                    f"Failed {MAX_FAILS} checks in a row.\n"
                    f"\U0001f517 {url}"
                )
                _fail_counts[url] = 0
            continue

        if url in _page_hashes and _page_hashes[url] != current_hash:
            print(f"[Monitor] {game['name']} page changed - checking for new codes...")

            # Scrape current codes
            all_codes = scrapers.get_codes(game_key)

            if all_codes:
                # Save to DB — returns only codes not seen before
                new_codes = database.save_detected_codes(game_key, all_codes)

                if new_codes:
                    print(f"[Monitor] {len(new_codes)} new codes found for {game['name']}")
                    alert = _format_new_codes_alert(game_key, game, new_codes)
                    subscribers = database.get_all_subscribers()
                    if subscribers:
                        ok, fail = telegram_client.broadcast(subscribers, alert)
                        print(f"[Monitor] Broadcast to {ok} subscribers ({fail} failed)")
                    else:
                        telegram_client.send_admin(alert)
                else:
                    print(f"[Monitor] Page changed but no new codes detected for {game['name']}")

        _page_hashes[url] = current_hash

        database.update_monitor_state(
            key        = f"{game_key}_codes",
            last_check = _now(),
            next_check = _next_check_time(),
            status     = "ok"
        )

    _check_expiring_codes()

    # Clean up old codes weekly
    database.clear_old_codes(days=7)


def _check_patches(game_key: str) -> None:
    """Generic patch checker — works for any game in config.GAMES."""
    game      = config.GAMES.get(game_key, {})
    patch_url = game.get("patch_url")
    name      = game.get("name", game_key)
    if not patch_url:
        return

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
        _fail_counts[patch_url] = 0

    except Exception as e:
        _fail_counts[patch_url] = _fail_counts.get(patch_url, 0) + 1
        print(f"[Monitor] Patch fetch failed for {name} ({_fail_counts[patch_url]}/{MAX_FAILS}): {e}")
        if _fail_counts[patch_url] >= MAX_FAILS:
            telegram_client.send_admin(
                f"\u26a0\ufe0f Source down: {name} patch notes\n\n"
                f"Failed {MAX_FAILS} checks in a row.\n"
                f"\U0001f517 {patch_url}"
            )
            _fail_counts[patch_url] = 0
        return

    soup      = BeautifulSoup(r.text, "html.parser")
    posts     = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href  = a["href"]
        title = a.get_text(strip=True)
        if ("/news/" in href or "/archives/" in href) and href != patch_url:
            if href.startswith("/"):
                from urllib.parse import urlparse
                base = urlparse(patch_url)
                href = f"{base.scheme}://{base.netloc}{href}"
            if title and len(title) > 5 and href not in seen_urls:
                seen_urls.add(href)
                posts.append((title, href))

    current_hash = hashlib.md5(r.text.encode()).hexdigest()
    patch_key_db = f"{game_key}_patches"

    if patch_key_db in _page_hashes and _page_hashes[patch_key_db] != current_hash:
        # Page changed — alert on the first relevant post title
        if posts:
            title, url = posts[0]
            alert = (
                f"\u2696\ufe0f {name} Patch Notes Updated!\n\n"
                f"\U0001f4cc {title}\n"
                f"\U0001f517 {url}\n\n"
                f"Full list: {patch_url}"
            )
            subscribers = database.get_all_subscribers()
            if subscribers:
                ok, fail = telegram_client.broadcast(subscribers, alert)
                print(f"[Monitor] Patch alert sent to {ok} subscribers ({fail} failed)")
            else:
                telegram_client.send_admin(alert)

    _page_hashes[patch_key_db] = current_hash

    database.update_monitor_state(
        key        = patch_key_db,
        last_check = _now(),
        next_check = _next_check_time(),
        status     = "ok"
    )


def check_epic7_patches() -> None:
    _check_patches("epic7")


def check_czn_patches() -> None:
    _check_patches("czn")
