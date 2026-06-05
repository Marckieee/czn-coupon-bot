"""
bot.py
Entry point. Starts the bot, handles Telegram commands,
and runs background monitors on a timer.

Run with:
    python bot.py
"""

import requests
import time
import config
import telegram_client
import scrapers
import monitor
import youtube_monitor
import database


# ---------------------------
# KEYBOARD LAYOUTS
# ---------------------------

MAIN_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "\U0001f381 Epic7 Codes",   "callback_data": "epic7codes"},
            {"text": "\U0001f381 CZN Codes",      "callback_data": "czncodes"},
        ],
        [
            {"text": "\u2696\ufe0f E7 Patch Notes",  "callback_data": "epic7patch"},
            {"text": "\u2696\ufe0f CZN Patch Notes", "callback_data": "cznpatch"},
        ],
        [
            {"text": "\U0001f916 Status",             "callback_data": "status"},
        ],
        [
            {"text": "\U0001f3ac Epic7 Videos",   "callback_data": "epic7videos"},
            {"text": "\U0001f3ac CZN Videos",     "callback_data": "cznvideos"},
        ],
        [
            {"text": "\U0001f514 Subscribe",      "callback_data": "subscribe"},
            {"text": "\U0001f515 Unsubscribe",    "callback_data": "unsubscribe"},
        ],
        [
            {"text": "\u2139\ufe0f About",        "callback_data": "about"},
            {"text": "\u2753 Help",               "callback_data": "help"},
        ],
    ]
}


# ---------------------------
# COMMAND HANDLERS
# ---------------------------

def handle_welcome() -> str:
    return (
        "\U0001f44b Welcome to the E7 & CZN Game Monitor Bot!\n\n"

        "\U0001f916 What this bot does automatically:\n"
        "  \u2022 Checks for new gift codes every 15 minutes\n"
        "  \u2022 Alerts subscribers instantly when new codes drop\n"
        "  \u2022 Warns subscribers 24hrs before codes expire\n"
        "  \u2022 Monitors Epic Seven & CZN for balance patch notes\n"
        "  \u2022 Alerts subscribers when a balance adjustment drops\n"
        "  \u2022 Monitors official YouTube channels for new videos\n\n"

        "\U0001f3ae Games tracked:\n"
        "  \u2022 Epic Seven\n"
        "  \u2022 Chaos Zero Nightmare\n\n"

        "\U0001f4a1 Use the buttons below or tap / to see all commands!"
    )


def handle_help() -> str:
    return (
        "\U0001f3ae E7 & CZN Game Monitor Bot\n\n"

        "\U0001f916 What I do automatically:\n"
        "  \u2022 Check for new gift codes every 15 minutes\n"
        "  \u2022 Alert subscribers instantly when new codes drop\n"
        "  \u2022 Warn subscribers 24hrs before codes expire\n"
        "  \u2022 Monitor Epic Seven for balance patch notes\n"
        "  \u2022 Alert subscribers when a balance adjustment drops\n"
        "  \u2022 Monitor official YouTube channels for new videos\n\n"

        "\U0001f4ac Available commands:\n\n"
        "  /subscribe    \u2014 Get automatic alerts\n"
        "  /unsubscribe  \u2014 Stop automatic alerts\n"
        "  /epic7codes   \u2014 Latest Epic Seven gift codes\n"
        "  /czncodes     \u2014 Latest CZN gift codes\n"
        "  /epic7patch   \u2014 Latest Epic Seven balance patch notes\n"
        "  /cznpatch     \u2014 Latest CZN balance patch notes\n"
        "  /epic7videos  \u2014 Latest Epic Seven YouTube videos\n"
        "  /cznvideos    \u2014 Latest CZN YouTube videos\n"
        "  /status       \u2014 Bot monitoring status\n"
        "  /about        \u2014 About this bot\n"
        "  /help         \u2014 Show this menu\n\n"

        "\U0001f4a1 Tip: Use the buttons below for quick access!"
    )


def handle_about() -> str:
    return (
        "\u2139\ufe0f About This Bot\n\n"

        "\U0001f916 E7 & CZN Game Monitor Bot\n"
        "Version: 1.1.0\n\n"

        "\U0001f4cb What it tracks:\n"
        "  \u2022 Epic Seven gift codes\n"
        "  \u2022 Chaos Zero Nightmare gift codes\n"
        "  \u2022 Epic Seven balance patch notes\n"
        "  \u2022 Epic Seven & CZN official YouTube videos\n\n"

        "\U0001f517 Data sources:\n"
        "  \u2022 ucngame.com (Epic Seven codes)\n"
        "  \u2022 pocketgamer.com (CZN codes)\n"
        "  \u2022 epic7db.com (Patch notes)\n"
        "  \u2022 YouTube RSS feeds (New videos)\n\n"

        "\u23f1 Update frequency:\n"
        "  \u2022 Codes checked every 15 minutes\n"
        "  \u2022 Patch notes checked every 15 minutes\n"
        "  \u2022 YouTube videos checked every 15 minutes\n"
        "  \u2022 Expiry warnings sent 24hrs before codes expire\n\n"

        "\U0001f4e3 Alerts:\n"
        "  \u2022 Use /subscribe to receive automatic alerts\n"
        "  \u2022 Alerts are sent to all subscribers instantly\n\n"

        "Built with \u2764\ufe0f for Epic Seven & CZN players."
    )


def handle_subscribe(chat_id: int, username: str | None) -> str:
    added = database.add_subscriber(chat_id, username)
    if added:
        count = database.get_subscriber_count()
        return (
            "\u2705 You're subscribed!\n\n"
            "You will now automatically receive:\n"
            "  \U0001f381 New gift code alerts\n"
            "  \u23f0 Expiry warnings (24hrs before codes expire)\n"
            "  \u2696\ufe0f Epic Seven balance patch alerts\n"
            "  \U0001f3ac New YouTube video alerts\n\n"
            f"You're subscriber #{count}!\n\n"
            "Use /unsubscribe anytime to stop alerts."
        )
    else:
        return (
            "\u2139\ufe0f You're already subscribed!\n\n"
            "You'll receive alerts for codes, patches and new videos.\n"
            "Use /unsubscribe to stop alerts."
        )


def handle_unsubscribe(chat_id: int) -> str:
    removed = database.remove_subscriber(chat_id)
    if removed:
        return (
            "\u274c You've been unsubscribed.\n\n"
            "You will no longer receive automatic alerts.\n"
            "Use /subscribe anytime to turn them back on."
        )
    else:
        return (
            "\u2139\ufe0f You weren't subscribed.\n\n"
            "Use /subscribe to start receiving automatic alerts."
        )


def handle_status() -> str:
    states = database.get_all_monitor_states()
    count  = database.get_subscriber_count()

    lines = ["\U0001f916 Bot Monitoring Status\n"]

    labels = {
        "epic7_codes":   "Epic Seven codes",
        "czn_codes":     "CZN codes",
        "epic7_patches": "Epic Seven patches",
        "epic7_youtube": "Epic Seven YouTube",
        "czn_youtube":   "CZN YouTube",
    }

    if not states:
        lines.append("No checks run yet \u2014 first check in 15 minutes.\n")
    else:
        for state in states:
            label       = labels.get(state["key"], state["key"])
            status_icon = "\u2705" if state["status"] == "ok" else "\u26a0\ufe0f"
            lines.append(f"{status_icon} {label}")
            lines.append(f"   Last check:  {state['last_check']}")
            lines.append(f"   Next check:  {state['next_check']}\n")

    lines.append(f"\U0001f465 Subscribers: {count}")
    lines.append("\n\U0001f550 All checks run every 15 minutes automatically.")

    return "\n".join(lines)


def handle_codes(game_key: str) -> str:
    game = config.GAMES.get(game_key)
    if not game:
        return "\u2753 Unknown game."

    # Only show codes detected in the last 24 hours
    recent_codes = database.get_recent_codes(game_key, hours=24)

    if not recent_codes:
        return (
            f"\U0001f614 No new codes detected for {game['name']} in the last 24 hours.\n\n"
            f"Codes drop during events and updates \u2014 "
            f"use /subscribe to get an instant alert when new ones appear!\n\n"
            f"\U0001f517 Check manually: {game['codes_url']}"
        )

    lines = [
        f"\U0001f381 {game['name']} \u2014 Recent Codes (last 24hrs)\n",
        f"Found {len(recent_codes)} new code(s):\n",
    ]

    for entry in recent_codes:
        lines.append(f"\u2022 {entry['code']}")
        lines.append(f"  \u21b3 {entry['reward']}")
        if entry.get("expiry"):
            lines.append(f"  \u23f0 Expires: {entry['expiry']}")
        lines.append(f"  \U0001f550 Detected: {entry['detected_at']}")
        lines.append("")

    lines.append(f"\U0001f517 Redeem here: {game['redeem_url']}")

    return "\n".join(lines)


def _format_date(raw: str) -> str:
    """
    Normalise various date formats into "Wednesday, 04 Jun 2026".
    Handles:
      - "June 3, 2026"     -> "Wednesday, 03 Jun 2026"
      - "April 29"         -> "Tuesday, 29 Apr"
      - "6/4"              -> "Thursday, 04 Jun 2026"
      - "6/4 (Thu)"        -> "Thursday, 04 Jun 2026"
    """
    from datetime import datetime
    import re

    raw = raw.strip()
    if not raw:
        return ""

    # Try full formats first
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%A, %d %b %Y")
        except ValueError:
            pass

    # Month Day without year e.g. "April 29" or "Apr 29"
    for fmt in ("%B %d", "%b %d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%A, %d %b")
        except ValueError:
            pass

    # MM/DD or MM/DD (Day) e.g. "6/4" or "6/4 (Thu)"
    m = re.match(r"^(\d{1,2})/(\d{1,2})", raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            year = datetime.now().year
            return datetime(year, month, day).strftime("%A, %d %b %Y")
        except ValueError:
            pass

    return raw  # Return as-is if nothing matched


def _fetch_patch_posts(game_key: str) -> list[tuple[str, str, str]]:
    """
    Shared helper — scrapes patch post titles, links and dates.
    Returns list of (title, url, date) tuples.

    Date extraction:
      - CZN (game8): dates are in the table cell next to the title e.g. "(April 8, 2026)"
      - Epic7 (epic7db): dates are often in the title itself e.g. "5/28 Balance Adjustment"
    """
    game      = config.GAMES.get(game_key, {})
    patch_url = game.get("patch_url")
    if not patch_url:
        return []

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return []

    from bs4 import BeautifulSoup
    from urllib.parse import urlparse
    import re

    soup  = BeautifulSoup(r.text, "html.parser")
    posts = []
    seen  = set()
    base  = urlparse(patch_url)

    # --- CZN: game8.co has a proper <table> with date in the title cell ---
    if "game8.co" in patch_url:
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            a = cells[0].find("a", href=True)
            if not a:
                continue
            href  = a["href"]
            if href.startswith("/"):
                href = f"{base.scheme}://{base.netloc}{href}"
            if href in seen:
                continue

            # Title is the link text; date is usually in parentheses after it
            full_text = cells[0].get_text(separator=" ", strip=True)
            title     = a.get_text(strip=True)

            # Extract date from parentheses e.g. "(April 8, 2026)"
            date_match = re.search(r"\(([A-Za-z]+ \d{1,2},?\s*\d{4})\)", full_text)
            raw_date = date_match.group(1) if date_match else ""
            # Also try extracting date from title itself e.g. "April 29 Patch Note..."
            if not raw_date:
                title_date = re.match(r"^([A-Za-z]+ \d{1,2})", title)
                raw_date = title_date.group(1) if title_date else ""
            date = _format_date(raw_date)

            if title and len(title) > 5:
                seen.add(href)
                posts.append((title, href, date))

    # --- Epic7: epic7db.com — each <a> under /news/ contains
    #     "TITLE  DATE  snippet...  Read More" all as one text block.
    #     We only want the first line (the actual title).
    else:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/" in href and href != patch_url:
                if href.startswith("/"):
                    href = f"{base.scheme}://{base.netloc}{href}"
                if href in seen:
                    continue

                # Get all text lines, skip blanks
                lines = [l.strip() for l in a.get_text("\n").splitlines() if l.strip()]
                if not lines:
                    continue

                # First line = title  e.g. "6/4 (Thu) Maintenance Notice"
                title = lines[0]

                # Second line = date  e.g. "June 3, 2026"
                raw_date = lines[1] if len(lines) > 1 else ""

                # Clean and format the date
                date = _format_date(raw_date)

                # Skip navigation links like "Back", "Next", page numbers
                if title.lower() in ("back", "next") or title.isdigit():
                    continue

                if len(title) > 3:
                    seen.add(href)
                    posts.append((title, href, date))

    return posts


def handle_patch(game_key: str = "epic7") -> str:
    """Fetch and display patch note titles with release dates and links."""
    game      = config.GAMES.get(game_key, {})
    patch_url = game.get("patch_url", "")
    name      = game.get("name", game_key)

    posts = _fetch_patch_posts(game_key)

    if not posts:
        return (
            f"\u26a0\ufe0f Could not fetch patch notes for {name}.\n\n"
            f"\U0001f517 Check manually: {patch_url}"
        )

    lines = [f"\u2696\ufe0f {name} Patch Notes\n"]
    for title, url, date in posts[:8]:
        date_str = f" \U0001f4c5 {date}" if date else ""
        lines.append(f"\u2022 {title}{date_str}")
        lines.append(f"  \U0001f517 {url}\n")

    lines.append(f"\U0001f4cb Full list: {patch_url}")

    return "\n".join(lines)


def handle_debug() -> str:
    """Debug command to test YouTube API directly."""
    import os
    import requests as req

    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        return "ERROR: YOUTUBE_API_KEY not set in Railway variables!"

    results = [f"API key found: {api_key[:8]}...\n"]

    for game_key, channel in youtube_monitor.YOUTUBE_CHANNELS.items():
        channel_id  = channel["channel_id"]
        playlist_id = "UU" + channel_id[2:]
        results.append(f"Testing {channel['name']}:")
        results.append(f"  Channel ID:  {channel_id}")
        results.append(f"  Playlist ID: {playlist_id}")

        try:
            r = req.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params={
                    "key":        api_key,
                    "playlistId": playlist_id,
                    "part":       "snippet",
                    "maxResults": 3,
                },
                timeout=15,
            )
            data = r.json()
            if "error" in data:
                results.append(f"  ERROR: {data['error'].get('message')}")
            else:
                items = data.get("items", [])
                results.append(f"  Videos found: {len(items)}")
                for item in items[:2]:
                    title = item["snippet"].get("title", "?")
                    results.append(f"    - {title}")
        except Exception as e:
            results.append(f"  EXCEPTION: {e}")
        results.append("")

    return "\n".join(results)


def handle_videos(game_key: str) -> str:
    """Fetch and display the latest YouTube videos for a game."""
    channel = youtube_monitor.YOUTUBE_CHANNELS.get(game_key)
    if not channel:
        return "\u2753 Unknown game."

    videos = youtube_monitor.get_latest_videos(game_key, limit=5)
    if not videos:
        return (
            f"\u26a0\ufe0f Could not fetch videos for {channel['name']}.\n\n"
            f"\U0001f517 Visit the channel directly:\n"
            f"https://www.youtube.com/channel/{channel['channel_id']}"
        )

    lines = [f"\U0001f3ac Latest {channel['name']} Videos\n"]
    for v in videos:
        # Format published date nicely if possible
        published = v.get("published", "")
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            published = dt.strftime("%d %b %Y")
        except Exception:
            pass

        lines.append(f"\u2022 {v['title']}")
        if published:
            lines.append(f"  \U0001f4c5 {published}")
        lines.append(f"  \U0001f517 {v['url']}\n")

    return "\n".join(lines)


# ---------------------------
# COMMAND ROUTER
# ---------------------------

def get_response(cmd: str, chat_id: int, username: str | None) -> str | None:
    if cmd in ("/start", "start"):
        return handle_welcome()
    if cmd in ("/help", "help"):
        return handle_help()
    if cmd in ("/about", "about"):
        return handle_about()
    if cmd in ("/subscribe", "subscribe"):
        return handle_subscribe(chat_id, username)
    if cmd in ("/unsubscribe", "unsubscribe"):
        return handle_unsubscribe(chat_id)
    if cmd in ("/status", "status"):
        return handle_status()
    if cmd in ("/epic7codes", "epic7codes"):
        return handle_codes("epic7")
    if cmd in ("/czncodes", "czncodes"):
        return handle_codes("czn")
    if cmd in ("/epic7patch", "epic7patch", "/patch", "patch"):
        return handle_patch("epic7")
    if cmd in ("/cznpatch", "cznpatch"):
        return handle_patch("czn")
    if cmd in ("/epic7videos", "epic7videos"):
        return handle_videos("epic7")
    if cmd in ("/cznvideos", "cznvideos"):
        return handle_videos("czn")
    if cmd in ("/debug", "debug"):
        return handle_debug()
    return None


def is_slow_command(cmd: str) -> bool:
    return cmd in (
        "/epic7codes", "epic7codes",
        "/czncodes",   "czncodes",
        "/patch",      "patch",
        "/epic7patch", "epic7patch",
        "/cznpatch",   "cznpatch",
        "/epic7videos","epic7videos",
        "/cznvideos",  "cznvideos",
    )


def slow_command_message(cmd: str) -> str:
    if cmd in ("/epic7codes", "epic7codes"):
        return "\U0001f50d Scraping Epic Seven codes... please wait."
    if cmd in ("/czncodes", "czncodes"):
        return "\U0001f50d Scraping CZN codes... please wait."
    if cmd in ("/patch", "patch", "/epic7patch", "epic7patch"):
        return "\U0001f50d Fetching Epic Seven patch notes... please wait."
    if cmd in ("/cznpatch", "cznpatch"):
        return "\U0001f50d Fetching CZN patch notes... please wait."
    if cmd in ("/epic7videos", "epic7videos"):
        return "\U0001f50d Fetching latest Epic Seven videos... please wait."
    if cmd in ("/cznvideos", "cznvideos"):
        return "\U0001f50d Fetching latest CZN videos... please wait."
    return "\U0001f50d Fetching... please wait."


# ---------------------------
# TELEGRAM KEYBOARD HELPER
# ---------------------------

BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def send_with_keyboard(chat_id: int, text: str) -> None:
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id":      chat_id,
                "text":         text,
                "reply_markup": MAIN_KEYBOARD,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[Bot] Keyboard send error: {e}")
        telegram_client.send(chat_id, text)


def answer_callback(callback_query_id: str) -> None:
    try:
        requests.post(
            f"{BASE_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
            timeout=10,
        )
    except Exception as e:
        print(f"[Bot] answerCallbackQuery error: {e}")


# ---------------------------
# CHECK SCHEDULE
# All checks run every 60 minutes consistently
# ---------------------------

CHECK_INTERVAL_SECONDS = 60   # sleep 60s per loop
CHECK_INTERVAL_LOOPS   = 60   # 60 loops x 60s = 1 hour


def _get_sleep_interval() -> int:
    return CHECK_INTERVAL_SECONDS


def _get_check_interval() -> int:
    return CHECK_INTERVAL_LOOPS


# ---------------------------
# STARTUP
# ---------------------------
print("=" * 40)
print("  Game Monitor Bot starting up")
print("=" * 40)

config.validate()
database.init_db()
database.init_seen_items()

print("[Bot] Flushing pending Telegram updates...")
_pending = telegram_client.get_updates(offset=-1)
if _pending:
    last_update_id = _pending[-1]["update_id"] + 1
    print(f"[Bot] Skipped {len(_pending)} old update(s).")
else:
    last_update_id = None

youtube_monitor.preload_seen_videos()

sub_count = database.get_subscriber_count()
# Startup message removed to avoid spam on Railway restarts
# Use /status to check if the bot is running
print(f"[Bot] Ready! Subscribers: {sub_count}")

# ---------------------------
# MAIN LOOP
# ---------------------------
loop_count = 0

print("\n[Bot] Running. Press Ctrl+C to stop.\n")

while True:
    updates = telegram_client.get_updates(last_update_id)
    for update in updates:
        last_update_id = update["update_id"] + 1

        # --- Inline keyboard button presses ---
        if "callback_query" in update:
            cq       = update["callback_query"]
            cq_id    = cq["id"]
            chat_id  = cq["message"]["chat"]["id"]
            username = cq["from"].get("username")
            cmd      = cq["data"]

            answer_callback(cq_id)

            if is_slow_command(cmd):
                telegram_client.send(chat_id, slow_command_message(cmd))

            response = get_response(cmd, chat_id, username)
            if response:
                send_with_keyboard(chat_id, response)
            continue

        # --- Regular text messages ---
        if "message" not in update:
            continue

        chat_id  = update["message"]["chat"]["id"]
        text     = update["message"].get("text", "")
        username = update["message"]["from"].get("username")
        print(f"[Telegram] {chat_id} (@{username}): {text!r}")

        cmd = text.strip().lower().split()[0] if text.strip() else ""

        if is_slow_command(cmd):
            telegram_client.send(chat_id, slow_command_message(cmd))

        response = get_response(cmd, chat_id, username)
        if response:
            if cmd in ("/start", "start", "/help", "help", "/about", "about"):
                send_with_keyboard(chat_id, response)
            else:
                telegram_client.send(chat_id, response)
        elif text.strip():
            send_with_keyboard(chat_id, handle_help())

    loop_count += 1

    # Background checks — interval adapts to patch schedule
    sleep_secs = _get_sleep_interval()
    interval   = _get_check_interval()

    if loop_count % interval == 0:
        print("[Monitor] Running hourly checks...")
        monitor.check_pages()
        monitor.check_epic7_patches()
        monitor.check_czn_patches()
        youtube_monitor.check_youtube()
        loop_count = 0

    time.sleep(sleep_secs)
