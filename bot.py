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
        "Commands:\n"
        "  /codes epic7  — Latest Epic Seven gift codes\n"
        "  /codes czn    — Latest CZN gift codes\n"
        "  /patch        — Latest Epic Seven patch notes\n\n"
        "Auto-alerts:\n"
        "  • Notified when codes pages update\n"
        "  • Notified when a balance adjustment patch drops"
    )


def handle_codes(game_key: str) -> str:
    game = config.GAMES.get(game_key)
    if not game:
        return "Unknown game. Use /codes epic7 or /codes czn"

    codes = scrapers.get_codes(game_key)
    if not codes:
        return (
            f"😔 No active codes for {game['name']} right now.\n\n"
            f"Codes are released during events and updates — "
            f"the bot will alert you as soon as the page updates!\n\n"
            f"🔗 Check manually: {game['codes_url']}"
        )

    lines = [f"🎁 {game['name']} Codes\n"]
    for code, reward in codes[:15]:
        lines.append(f"• {code}")
        lines.append(f"  ↳ {reward}\n")
    lines.append(f"🔗 Redeem: {game['redeem_url']}")
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



    """Parse a command string and return the response, or None if not a command."""
    parts = text.strip().lower().split()
    if not parts:
        return None

    cmd = parts[0]

    if cmd in ("/start", "/help"):
        return handle_help()

    if cmd == "/patch":
        return handle_patch()

    if cmd == "/codes":
        if len(parts) < 2:
            return "Usage: /codes epic7  or  /codes czn"
        return handle_codes(parts[1])

    return None


# ---------------------------
# STARTUP
# ---------------------------
print("=" * 40)
print("  Game Monitor Bot starting up")
print("=" * 40)

config.validate()
telegram_client.send_admin("🤖 Game Monitor Bot started!\n\nSend /help to see commands.")

# ---------------------------
# MAIN LOOP
# ---------------------------
last_update_id: int | None = None
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
        if any(lower.startswith(c) for c in ("/codes", "/start", "/help", "/patch")):
            telegram_client.send(chat_id, "🔍 Fetching... please wait.")

        response = route_command(text)
        if response:
            telegram_client.send(chat_id, response)

    loop_count += 1

    # --- Background: Page hash check every 15 minutes ---
    if loop_count % config.SCRAPE_CHECK_INTERVAL == 0:
        print("[Monitor] Checking codes pages for updates...")
        monitor.check_pages()
        print("[Monitor] Checking Epic Seven patch notes...")
        monitor.check_epic7_patches()
        loop_count = 0

    time.sleep(60)
