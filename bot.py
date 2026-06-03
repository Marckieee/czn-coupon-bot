"""
bot.py
Entry point. Starts the bot, handles Telegram commands,
and runs background monitors on a timer.

Run with:
    python bot.py
"""

import requests
import json
import time
from datetime import datetime, timezone, timedelta
import config
import telegram_client
import scrapers
import monitor
import database


# ---------------------------
# KEYBOARD LAYOUTS
# ---------------------------

MAIN_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "\U0001f381 Epic7 Codes",  "callback_data": "epic7codes"},
            {"text": "\U0001f381 CZN Codes",     "callback_data": "czncodes"},
        ],
        [
            {"text": "\u2696\ufe0f Patch Notes", "callback_data": "patch"},
            {"text": "\U0001f916 Status",         "callback_data": "status"},
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
        "  \u2022 Monitors Epic Seven for balance patch notes\n"
        "  \u2022 Alerts subscribers when a balance adjustment drops\n\n"

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
        "  \u2022 Alert subscribers when a balance adjustment drops\n\n"

        "\U0001f4ac Available commands:\n\n"
        "  /subscribe    \u2014 Get automatic alerts\n"
        "  /unsubscribe  \u2014 Stop automatic alerts\n"
        "  /epic7codes   \u2014 Latest Epic Seven gift codes\n"
        "  /czncodes     \u2014 Latest CZN gift codes\n"
        "  /patch        \u2014 Latest Epic Seven balance patch notes\n"
        "  /status       \u2014 Bot monitoring status\n"
        "  /about        \u2014 About this bot\n"
        "  /help         \u2014 Show this menu\n\n"

        "\U0001f4a1 Tip: Use the buttons below for quick access!"
    )


def handle_about() -> str:
    return (
        "\u2139\ufe0f About This Bot\n\n"

        "\U0001f916 E7 & CZN Game Monitor Bot\n"
        "Version: 1.0.0\n\n"

        "\U0001f4cb What it tracks:\n"
        "  \u2022 Epic Seven gift codes\n"
        "  \u2022 Chaos Zero Nightmare gift codes\n"
        "  \u2022 Epic Seven balance patch notes\n\n"

        "\U0001f517 Data sources:\n"
        "  \u2022 ucngame.com (Epic Seven codes)\n"
        "  \u2022 pocketgamer.com (CZN codes)\n"
        "  \u2022 epic7db.com (Patch notes)\n\n"

        "\u23f1 Update frequency:\n"
        "  \u2022 Codes checked every 15 minutes\n"
        "  \u2022 Patch notes checked every 15 minutes\n"
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
            "  \u2696\ufe0f Epic Seven balance patch alerts\n\n"
            f"You're subscriber #{count}!\n\n"
            "Use /unsubscribe anytime to stop alerts."
        )
    else:
        return (
            "\u2139\ufe0f You're already subscribed!\n\n"
            "You'll receive alerts when new codes or patches drop.\n"
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
    }

    if not states:
        lines.append("No checks run yet \u2014 first check happens in 15 minutes.\n")
    else:
        for state in states:
            label       = labels.get(state["key"], state["key"])
            status_icon = "\u2705" if state["status"] == "ok" else "\u26a0\ufe0f"
            lines.append(f"{status_icon} {label}")
            lines.append(f"   Last check:  {state['last_check']}")
            lines.append(f"   Next check:  {state['next_check']}\n")

    lines.append(f"\U0001f465 Subscribers: {count}")
    lines.append("\n\U0001f550 Checks run every 15 minutes automatically.")

    return "\n".join(lines)


def handle_codes(game_key: str) -> str:
    game = config.GAMES.get(game_key)
    if not game:
        return "\u2753 Unknown game."

    codes = scrapers.get_codes(game_key)

    if not codes:
        return (
            f"\U0001f614 No active codes for {game['name']} right now.\n\n"
            f"Codes are released during events and updates \u2014 "
            f"use /subscribe to get alerted the moment new codes drop!\n\n"
            f"\U0001f517 Check manually: {game['codes_url']}"
        )

    checked_at = codes[0].get("checked_at", "unknown")
    lines = [
        f"\U0001f381 {game['name']} Codes\n",
        f"Found {len(codes)} active code(s):\n",
    ]

    for entry in codes[:15]:
        lines.append(f"\u2022 {entry['code']}")
        lines.append(f"  \u21b3 {entry['reward']}")
        if entry.get("expiry"):
            lines.append(f"  \u23f0 Expires: {entry['expiry']}")
        lines.append("")

    lines.append(f"\U0001f517 Redeem here: {game['redeem_url']}")
    lines.append(f"\n\U0001f550 Last checked: {checked_at}")

    if len(codes) > 15:
        lines.append(f"\n+{len(codes) - 15} more \u2192 {game['codes_url']}")

    return "\n".join(lines)


def handle_patch() -> str:
    patch_url = config.GAMES["epic7"].get("patch_url")

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return f"\u26a0\ufe0f Could not fetch patch notes.\nCheck manually: {patch_url}"

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")

    posts = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href:
            title    = a.get_text(strip=True)
            full_url = href if href.startswith("http") else "https://epic7db.com" + href
            if title and len(title) > 5 and full_url not in seen:
                seen.add(full_url)
                posts.append((title, full_url))

    if not posts:
        return f"\u26a0\ufe0f No patch notes found.\nCheck manually: {patch_url}"

    lines = ["\u2696\ufe0f Latest Epic Seven Patch Notes\n"]
    for title, url in posts[:8]:
        lines.append(f"\u2022 {title}")
        lines.append(f"  {url}\n")

    return "\n".join(lines)


# ---------------------------
# COMMAND ROUTER
# ---------------------------

def get_response(cmd: str, chat_id: int, username: str | None) -> str | None:
    """Map a command string to a response."""
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
    if cmd in ("/patch", "patch"):
        return handle_patch()
    return None


def is_slow_command(cmd: str) -> bool:
    """Returns True for commands that involve scraping."""
    return cmd in ("/epic7codes", "epic7codes", "/czncodes", "czncodes", "/patch", "patch")


def slow_command_message(cmd: str) -> str:
    """Return the appropriate waiting message for slow commands."""
    if cmd in ("/epic7codes", "epic7codes"):
        return "\U0001f50d Scraping Epic Seven codes... please wait."
    if cmd in ("/czncodes", "czncodes"):
        return "\U0001f50d Scraping CZN codes... please wait."
    if cmd in ("/patch", "patch"):
        return "\U0001f50d Fetching Epic Seven patch notes... please wait."
    return "\U0001f50d Fetching... please wait."


# ---------------------------
# TELEGRAM API HELPERS
# ---------------------------

BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def send_with_keyboard(chat_id: int, text: str) -> None:
    """Send a message with the main inline keyboard attached."""
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


def answer_callback(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a callback query to remove the loading spinner."""
    try:
        requests.post(
            f"{BASE_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[Bot] answerCallbackQuery error: {e}")


# ---------------------------
# STARTUP
# ---------------------------
print("=" * 40)
print("  Game Monitor Bot starting up")
print("=" * 40)

config.validate()
database.init_db()

print("[Bot] Flushing pending Telegram updates...")
_pending = telegram_client.get_updates(offset=-1)
if _pending:
    last_update_id = _pending[-1]["update_id"] + 1
    print(f"[Bot] Skipped {len(_pending)} old update(s).")
else:
    last_update_id = None

sub_count = database.get_subscriber_count()
telegram_client.send_admin(
    f"\U0001f916 Game Monitor Bot started!\n\n"
    f"\U0001f465 Current subscribers: {sub_count}\n\n"
    f"Send /help to see commands."
)

# ---------------------------
# MAIN LOOP
# ---------------------------
loop_count = 0

print("\n[Bot] Running. Press Ctrl+C to stop.\n")

while True:
    updates = telegram_client.get_updates(last_update_id)
    for update in updates:
        last_update_id = update["update_id"] + 1

        # --- Handle inline keyboard button presses ---
        if "callback_query" in update:
            cq       = update["callback_query"]
            cq_id    = cq["id"]
            chat_id  = cq["message"]["chat"]["id"]
            username = cq["from"].get("username")
            cmd      = cq["data"]  # e.g. "epic7codes", "subscribe"

            answer_callback(cq_id)  # remove spinner immediately

            if is_slow_command(cmd):
                telegram_client.send(chat_id, slow_command_message(cmd))

            response = get_response(cmd, chat_id, username)
            if response:
                # Show keyboard again after every button response
                send_with_keyboard(chat_id, response)
            continue

        # --- Handle regular text messages ---
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
            # Commands that show the keyboard
            if cmd in ("/start", "/help", "/about", "start", "help", "about"):
                send_with_keyboard(chat_id, response)
            else:
                telegram_client.send(chat_id, response)
        elif text.strip():
            send_with_keyboard(chat_id, handle_help())

    loop_count += 1

    # Background checks every 15 minutes (180 x 5s loops)
    if loop_count % 180 == 0:
        print("[Monitor] Checking codes pages for updates...")
        monitor.check_pages()
        print("[Monitor] Checking Epic Seven patch notes...")
        monitor.check_epic7_patches()
        loop_count = 0

    time.sleep(5)
