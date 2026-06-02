"""
scrapers.py
Scrapes gift/redeem codes from fan sites.

  Epic Seven → ucngame.com  (plain HTML table, no JS)
  CZN        → game8.co     (plain HTML table, no JS)
"""

import re
import requests
from bs4 import BeautifulSoup
import config


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
    If section_keyword is given, prefer the table that follows
    a heading containing that keyword.
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

    # Fallback: any table with a "code" column
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("code" in h for h in headers):
            return table

    return None


def scrape_epic7_codes() -> list[tuple[str, str]]:
    """
    Scrape Epic Seven codes from ucngame.com.
    Returns list of (code, reward) tuples.
    """
    soup = _fetch(config.GAMES["epic7"]["codes_url"])
    if not soup:
        return []

    table = _find_code_table(soup)
    if not table:
        print("[Scraper] Epic7: Could not find codes table.")
        return []

    codes = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        code   = re.sub(r"\*+", "", cells[0].get_text(strip=True)).strip()
        reward = cells[1].get_text(strip=True)[:100]
        if code:
            codes.append((code, reward))

    print(f"[Scraper] Epic7: Found {len(codes)} codes.")
    return codes


def scrape_czn_codes() -> list[tuple[str, str]]:
    """
    Scrape CZN codes from game8.co.
    Returns list of (code, reward) tuples.
    Only returns codes from the 'Active Coupons' section.
    """
    soup = _fetch(config.GAMES["czn"]["codes_url"])
    if not soup:
        return []

    table = _find_code_table(soup, section_keyword="active")
    if not table:
        print("[Scraper] CZN: Could not find active codes table.")
        return []

    codes = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        raw = cells[0].get_text(separator=" ", strip=True)
        raw = re.sub(r"(Copied|NEW|---|Duration:.*)", "", raw, flags=re.IGNORECASE)
        code   = raw.strip()
        reward = cells[1].get_text(separator=" ", strip=True)[:100]
        if code:
            codes.append((code, reward))

    print(f"[Scraper] CZN: Found {len(codes)} codes.")
    return codes


def get_codes(game_key: str) -> list[tuple[str, str]]:
    """Dispatch to the right scraper based on game_key."""
    if game_key == "epic7":
        return scrape_epic7_codes()
    if game_key == "czn":
        return scrape_czn_codes()
    return []
