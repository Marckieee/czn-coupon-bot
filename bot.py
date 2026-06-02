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


# ---------------------------
# COMMAND HANDLERS
# ---------------------------

def handle_help() -> str:
    return (
        "🎮 Game Monitor Bot\n\n"
        "Available commands:\n\n"
        "  /epic7codes — Latest Epic Seven gift codes\n"
        "  /czncodes   — Latest CZN gift codes\n"
        "  /patch      — Latest Epic Seven balance patch notes\n"
        "  /help       — Show this menu\n\n"
        "💡 Tip: Tap the / button at the bottom of the chat to see all commands!"
    )


def handle_codes(game_key: str) -> str:
    game = config.GAMES.get(game_key)
    if not game:
        return "❓ Unknown game."

    codes = scrapers.get_codes(game_key)
    if not codes:
        return (
            f"😔 No active codes for {game['name']} right now.\n\n"
            f"Codes are released during events and updates — "
            f"the bot will alert you as soon as new ones appear!\n\n"
            f"🔗 Check manually: {game['codes_url']}"
        )

    lines = [f"🎁 {game['name']} Codes\n"]
    for code, reward in codes[:15]:
        lines.append(f"• {code}")
        lines.append(f"  ↳ {reward}\n")
    lines.append(f"🔗 Redeem here: {game['redeem_url']}")
    if len(codes) > 15:
        lines.append(f"\n+{len(codes) - 15} more → {game['codes_url']}")

    return "\n".join(lines)


def handle_patch() -> str:
    """Fetch and display the latest Epic Seven patch notes."""
    patch_url = config.GAMES["epic7"].get("patch_url")

    try:
        r = requests.get(patch_url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return f"⚠️ Could not fetch patch notes.\nCheck manually: {patch_url}"

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")

    posts = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href:
            title = a.get_text(strip=True)
            full_url = href if href.startswith("http") else "https://epic7db.com" + href
            if title and len(title) > 5 and full_url not in seen:
                seen.add(full_url)
                posts.append((title, full_url))

    if not posts:
        return f"⚠️ No patch notes found.\nCheck manually: {patch_url}"

    lines = ["⚖️ Latest Epic Seven Patch Notes\n"]
    for title, url in posts[:8]:
        lines.append(f"• {title}")
        lines.append(f"  {url}\n")

    return "\n".join(lines)


# ---------------------------
# COMMAND ROUTER
# ---------------------------

def route_command(text: str) -> str | None:
    """Parse a command string and return the response, or None if not a command."""
    cmd = text.strip().lower().split()[0] if text.strip() else ""

    if cmd in ("/start", "/help"):
        return handle_help()

    if cmd == "/epic7codes":
        return handle_codes("epic7")

    if cmd == "/czncodes":
        return handle_codes("czn")

    if cmd == "/patch":
        return handle_patch()

    return None


# ---------------------------
# STARTUP
# ---------------------------
print("=" * 40)
print("  Game Monitor Bot starting up")
print("=" * 40)

config.validate()

# Flush pending updates so we don't reprocess old messages on restart
print("[Bot] Flushing pending Telegram updates...")
_pending = telegram_client.get_updates(offset=-1)
if _pending:
    last_update_id = _pending[-1]["update_id"] + 1
    print(f"[Bot] Skipped {len(_pending)} old update(s).")
else:
    last_update_id = None

telegram_client.send_admin("🤖 Game Monitor Bot started!\n\nSend /help to see commands.")

# ---------------------------
# MAIN LOOP
# ---------------------------
loop_count = 0

print("\n[Bot] Running. Press Ctrl+C to stop.\n")

while True:
    # --- Handle incoming Telegram messages ---
    updates = telegram_client.get_updates(last_update_id)
    for update in updates:
        last_update_id = update["update_id"] + 1

        if "message" not in update:
            continue

        chat_id = update["message"]["chat"]["id"]
        text    = update["message"].get("text", "")
        print(f"[Telegram] {chat_id}: {text!r}")

        lower = text.strip().lower()
        if any(lower.startswith(c) for c in ("/epic7codes", "/czncodes", "/patch", "/start", "/help")):
            telegram_client.send(chat_id, "🔍 Fetching... please wait.")

        response = route_command(text)
        if response:
            telegram_client.send(chat_id, response)
        elif text.strip():
            # Any unrecognised message → show the command menu
            telegram_client.send(chat_id, handle_help())

    loop_count += 1

    # --- Background: Page hash check every 15 minutes ---
    if loop_count % config.SCRAPE_CHECK_INTERVAL == 0:
        print("[Monitor] Checking codes pages for updates...")
        monitor.check_pages()
        print("[Monitor] Checking Epic Seven patch notes...")
        monitor.check_epic7_patches()
        loop_count = 0

    time.sleep(60)
