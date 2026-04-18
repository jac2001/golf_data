#!/usr/bin/env python3
"""
FanDuel Golf Odds Scraper (Playwright)
=======================================
Uses a real Chromium browser to fetch outright winner odds from FanDuel.
Bypasses TLS/session restrictions that block direct API calls.

First run: opens a visible browser window so you can see it working.
Subsequent runs: headless (no window) — reuses saved session cookies.

Usage:
    python fetch_fanduel_odds.py --tournament-id R2026014
    python fetch_fanduel_odds.py --tournament-id R2026014 --headless
    python fetch_fanduel_odds.py --tournament-id R2026014 --reset-session
    python fetch_fanduel_odds.py --tournament-id R2026014 --test
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
ODDS_DIR     = DATA_DIR / "odds"
SESSION_FILE = ODDS_DIR / ".fanduel_session.json"   # saved browser cookies + storage

# Tournament hints for matching the right market in the FanDuel response
TOURNAMENT_HINTS = {
    "014": ["masters", "augusta national"],
    "026": ["u.s. open", "us open", "united states open"],
    "047": ["pga championship"],
    "100": ["the open", "british open", "open championship"],
    "011": ["the players", "players championship"],
    "020": ["memorial"],
    "005": ["arnold palmer", "bay hill"],
    "007": ["genesis", "riviera"],
    "033": ["valspar", "copperhead"],
    "041": ["valero", "texas open"],
    "475": ["zurich classic"],
}

# FanDuel golf page URL — navigating here triggers the content-managed-page API call
FD_GOLF_URL = "https://sportsbook.fanduel.com/golf"
# The API endpoint we're intercepting
FD_API_PATTERN = "content-managed-page"


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def load_session() -> dict:
    """Load saved browser cookies + localStorage from previous run."""
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    return {}


def save_session(cookies: list, storage: dict | None = None) -> None:
    """Persist browser session for reuse in headless runs."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    session = {"cookies": cookies, "storage": storage or {}, "saved_at": datetime.now(timezone.utc).isoformat()}
    SESSION_FILE.write_text(json.dumps(session, indent=2))


def has_valid_session() -> bool:
    """True if a saved session file exists (regardless of actual expiry)."""
    return SESSION_FILE.exists() and SESSION_FILE.stat().st_size > 100


# ---------------------------------------------------------------------------
# Market parsing (same logic as direct API scraper)
# ---------------------------------------------------------------------------

def _american_to_implied(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _find_markets(data, depth: int = 0) -> list[dict]:
    """Recursively find outright winner markets with runner odds."""
    found = []
    if depth > 10:
        return found
    if isinstance(data, dict):
        if (
            data.get("marketType") in ("OUTRIGHT_BETTING", "WINNER", "WIN_ONLY")
            and isinstance(data.get("runners"), list)
            and data["runners"]
            and isinstance(data["runners"][0], dict)
            and "winRunnerOdds" in data["runners"][0]
        ):
            found.append(data)
            return found
        for v in data.values():
            found.extend(_find_markets(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_markets(item, depth + 1))
    return found


def _score_market(market: dict, suffix: str) -> int:
    """Score how closely a market matches our target tournament."""
    score = 0
    hints = TOURNAMENT_HINTS.get(suffix, [])
    text = " ".join([
        str(market.get("marketName", "")),
        str(market.get("competitionName", "")),
        str(market.get("eventName", "")),
    ]).lower()

    for hint in hints:
        if hint in text:
            score += 10

    # Prefer larger fields (Masters ~89, regular events ~132)
    score += min(len(market.get("runners", [])), 90)
    if market.get("marketType") == "OUTRIGHT_BETTING":
        score += 5
    return score


def parse_winner_odds(data: dict, tournament_id: str) -> list[dict]:
    """Extract player names and American odds from the FanDuel API response."""
    suffix = tournament_id[-3:] if len(tournament_id) >= 3 else ""
    markets = _find_markets(data)

    if not markets:
        print("  No winner markets found in response")
        return []

    print(f"  Found {len(markets)} outright markets")
    scored = sorted(markets, key=lambda m: _score_market(m, suffix), reverse=True)
    best = scored[0]
    print(f"  Best match: '{best.get('marketName', '?')}' | "
          f"{len(best.get('runners', []))} runners | "
          f"eventId={best.get('eventId', '?')}")

    rows = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for runner in best.get("runners", []):
        if runner.get("runnerStatus") != "ACTIVE":
            continue
        pname = runner.get("runnerName", "").strip()
        if not pname:
            continue
        odds_val = (
            runner.get("winRunnerOdds", {})
                  .get("americanDisplayOdds", {})
                  .get("americanOdds")
        )
        if odds_val is None:
            continue
        american = int(odds_val)
        implied  = _american_to_implied(american)
        rows.append({
            "tournament_id":        tournament_id,
            "sportsbook":           "FanDuel",
            "market":               "outright",
            "player_name":          pname,
            "fanduel_odds":         f"+{american}" if american > 0 else str(american),
            "odds_numeric":         american,
            "fanduel_implied_prob": round(implied, 6),
            "selection_id":         runner.get("selectionId", ""),
            "sort_priority":        runner.get("sortPriority", 999),
            "fetched_at":           fetched_at,
        })

    rows.sort(key=lambda r: r["fanduel_implied_prob"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Playwright scraper
# ---------------------------------------------------------------------------

def fetch_with_playwright(
    tournament_id: str,
    headless: bool = False,
    timeout_ms: int = 45_000,
) -> list[dict]:
    """
    Launch Chromium, navigate to FanDuel golf page, intercept the
    content-managed-page API call, parse and return odds rows.

    headless=False  → visible browser (recommended for first run)
    headless=True   → no window (works once session is established)
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    session = load_session()
    captured: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # Restore previous session if available
        context_opts: dict = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
        }
        if session.get("storage"):
            context_opts["storage_state"] = session["storage"]

        context = browser.new_context(**context_opts)

        # Restore cookies from previous session
        if session.get("cookies"):
            try:
                context.add_cookies(session["cookies"])
                print("  Restored previous session cookies")
            except Exception as e:
                print(f"  Cookie restore failed: {e}")

        page = context.new_page()

        # Stealth: remove webdriver flag
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        # Log ALL responses to debug which URLs FanDuel actually calls
        api_urls_seen = []

        def on_response(response):
            url = response.url
            # Track any fanduel API calls for debugging
            if "fanduel.com" in url and response.status == 200:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        api_urls_seen.append(url)
                        # Check for any golf/market/odds data
                        if any(kw in url for kw in [
                            "content-managed", "customPageId", "event-page",
                            "pga", "golf", "outright", "market", "runner"
                        ]):
                            try:
                                data = response.json()
                                markets = _find_markets(data)
                                if markets:
                                    captured.append(data)
                                    print(f"  ✓ Captured market data from: {url[:100]}")
                            except Exception:
                                pass
                except Exception:
                    pass

        page.on("response", on_response)

        # Navigate to FanDuel golf section
        print(f"  Opening {FD_GOLF_URL} ...")
        try:
            page.goto(FD_GOLF_URL, wait_until="networkidle", timeout=timeout_ms)
        except PWTimeout:
            print("  Page load timed out — checking if we captured data anyway")

        # Print all API URLs seen for debugging
        if api_urls_seen:
            print(f"  API calls seen ({len(api_urls_seen)}):")
            for u in api_urls_seen[:10]:
                print(f"    {u[:120]}")

        # Wait up to 15s for market data
        deadline = time.time() + 15
        while not captured and time.time() < deadline:
            time.sleep(0.5)
            page.evaluate("window.scrollBy(0, 200)")

        # If still nothing, try a broader scan of any captured JSON
        if not captured:
            print("  No market data yet — trying broader JSON scan ...")
            def on_response_broad(response):
                url = response.url
                if "fanduel.com" in url and response.status == 200:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct and response.body():
                            data = response.json()
                            markets = _find_markets(data)
                            if markets:
                                captured.append(data)
                                print(f"  ✓ Found markets in: {url[:100]}")
                    except Exception:
                        pass
            page.on("response", on_response_broad)
            try:
                page.reload(wait_until="networkidle", timeout=30_000)
                time.sleep(5)
            except PWTimeout:
                pass

        # Save session for next run (enables headless mode)
        try:
            storage_state = context.storage_state()
            cookies = context.cookies()
            save_session(cookies, storage_state)
            print(f"  Session saved → {SESSION_FILE.name}")
        except Exception as e:
            print(f"  Session save failed: {e}")

        if not headless:
            # Give a moment for user to see the browser before closing
            time.sleep(1)

        browser.close()

    if not captured:
        print("  ERROR: No API response captured. Try running without --headless.")
        return []

    # Use the last captured response (most complete)
    return parse_winner_odds(captured[-1], tournament_id)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def save_odds(rows: list[dict], tournament_id: str) -> Path:
    """Save to data/odds/fanduel_odds_{tid}.csv"""
    out_path = ODDS_DIR / f"fanduel_odds_{tournament_id}.csv"
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return out_path


def update_multi_book_csv(rows: list[dict]) -> None:
    """
    Merge FanDuel odds into multi_book_odds_latest.csv so the chatbot
    picks them up automatically in the multi-book comparison block.
    """
    mb_path = ODDS_DIR / "multi_book_odds_latest.csv"
    if not mb_path.exists() or not rows:
        return
    try:
        mb = pd.read_csv(mb_path)
        fd_map = {r["player_name"].strip().lower(): r["odds_numeric"] for r in rows}

        def _lookup(name: str):
            key = str(name).strip().lower()
            last = key.split()[-1] if key.split() else ""
            return fd_map.get(key) or next(
                (v for k, v in fd_map.items() if k.split()[-1] == last), None
            )

        mb["odds_fanduel"] = mb["player_name"].apply(_lookup)
        mb.to_csv(mb_path, index=False)
        filled = mb["odds_fanduel"].notna().sum()
        print(f"  Updated {mb_path.name}: FanDuel odds for {filled}/{len(mb)} players")
    except Exception as e:
        print(f"  multi_book update failed: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch FanDuel golf odds via Playwright")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026014")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a browser window (requires saved session)")
    parser.add_argument("--reset-session", action="store_true",
                        help="Delete saved session and start fresh")
    parser.add_argument("--test", action="store_true",
                        help="Print top 15 players and exit without saving")
    parser.add_argument("--timeout", type=int, default=45,
                        help="Page load timeout in seconds (default: 45)")
    args = parser.parse_args()

    tid = args.tournament_id.upper().strip()
    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    if args.reset_session and SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print("Session reset.")

    # Auto-switch to headless if valid session exists and --headless not forced
    use_headless = args.headless
    if not use_headless and has_valid_session():
        print("  Valid session found — using headless mode (pass --reset-session to force visible)")
        use_headless = True

    if use_headless and not has_valid_session():
        print("  No saved session — switching to visible browser for first run")
        use_headless = False

    print(f"Fetching FanDuel odds for {tid} ({'headless' if use_headless else 'visible browser'}) ...")
    rows = fetch_with_playwright(tid, headless=use_headless, timeout_ms=args.timeout * 1000)

    if not rows:
        print("No odds fetched.")
        sys.exit(1)

    if args.test:
        print(f"\nTop 15 — {tid} (FanDuel):")
        for r in rows[:15]:
            print(f"  {r['player_name']:30s}  {r['fanduel_odds']:>7}  ({r['fanduel_implied_prob']*100:.1f}%)")
        return

    out = save_odds(rows, tid)
    print(f"\nSaved {len(rows)} players → {out.name}")

    # Merge into multi-book CSV so chatbot picks it up immediately
    update_multi_book_csv(rows)


if __name__ == "__main__":
    main()
