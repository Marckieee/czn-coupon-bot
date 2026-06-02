"""
scrapers.py
Scrapes gift/redeem codes from fan sites.

  Epic Seven -> ucngame.com  (plain HTML table, no JS)
  CZN        -> pocketgamer.com (plain HTML list, no JS)

Returns list of dicts:
  {
    "code":       str,
    "reward":     str,
    "expiry":     str | None,   # expiry date string if available
    "checked_at": str,          # timestamp of when we scraped
  }
"""

import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import config


def _now() -> str:
    """Return current UTC time as a readable string."""
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _fetch(url: str) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on error."""
    try:
        r = requests.get(url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"[Scraper] Error fetching {url}: {e}")
        return None


def _find_code_table(soup: BeautifulSoup, section_keyword: str | None = None):
    """
    Find the first <table> that has a 'code' column header.
    If section_keyword is given, prefer the table after a heading
    containing that keyword.
    """
    if section_keyword:
        heading = soup.find(
            lambda tag: tag.name in ("h2", "h3", "h4")
            and section_keyword.lower() in tag.get_text(strip=True).lower()
        )
        if heading:
            table = heading.find_next("table")
            if table:
                return table

    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("code" in h for h in headers):
            return table

    return None


def scrape_epic7_codes() -> list[dict]:
    """
    Scrape Epic Seven codes from ucngame.com.
    Returns list of code dicts with code, reward, expiry, checked_at.
    ucngame tables often have 3 columns: CODE | REWARDS | EXPIRY DATE
    """
    soup = _fetch(config.GAMES["epic7"]["codes_url"])
    if not soup:
        return []

    table = _find_code_table(soup)
    if not table:
        print("[Scraper] Epic7: Could not find codes table.")
        return []

    # Detect column positions from header row
    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    code_idx   = next((i for i, h in enumerate(headers) if "code" in h), 0)
    reward_idx = next((i for i, h in enumerate(headers) if "reward" in h or "item" in h), 1)
    expiry_idx = next((i for i, h in enumerate(headers) if "expir" in h or "date" in h or "valid" in h), None)

    codes = []
    checked = _now()

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        code   = re.sub(r"\*+", "", cells[code_idx].get_text(strip=True)).strip()
        reward = cells[reward_idx].get_text(strip=True)[:100] if len(cells) > reward_idx else ""
        expiry = cells[expiry_idx].get_text(strip=True) if expiry_idx and len(cells) > expiry_idx else None

        if code:
            codes.append({
                "code":       code,
                "reward":     reward,
                "expiry":     expiry,
                "checked_at": checked,
            })

    print(f"[Scraper] Epic7: Found {len(codes)} codes.")
    return codes


def scrape_czn_codes() -> list[dict]:
    """
    Scrape CZN codes from pocketgamer.com.
    Returns list of code dicts with code, reward, expiry, checked_at.
    """
    soup = _fetch(config.GAMES["czn"]["codes_url"])
    if not soup:
        return []

    codes = []
    checked = _now()

    active_heading = soup.find(
        lambda tag: tag.name in ("h2", "h3", "h4")
        and "active" in tag.get_text(strip=True).lower()
    )

    if active_heading:
        ul = active_heading.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                code = li.get_text(strip=True)
                if code and code.upper() not in ("N/A", "NONE", ""):
                    codes.append({
                        "code":       code,
                        "reward":     "Check in-game mail for rewards",
                        "expiry":     None,
                        "checked_at": checked,
                    })

    print(f"[Scraper] CZN: Found {len(codes)} active codes.")
    return codes


def get_codes(game_key: str) -> list[dict]:
    """Dispatch to the right scraper based on game_key."""
    if game_key == "epic7":
        return scrape_epic7_codes()
    if game_key == "czn":
        return scrape_czn_codes()
    return []
