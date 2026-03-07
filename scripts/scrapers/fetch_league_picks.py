"""
Scrape ProTour Fantasy Golf league data for the Louisiana/Delaware Connection.

Saves:
  data/fantasy/league_standings.csv       — season standings all 28 teams
  data/fantasy/league_weekly_picks.csv    — current week picks + earnings per team
  data/fantasy/league_player_usage.csv    — player usage history across all teams

Usage:
    python3 scripts/scrapers/fetch_league_picks.py
"""

from __future__ import annotations

import os
import re
import json
import sys
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = "https://connection.protourfantasygolf.com"
OUT_DIR  = PROJECT_ROOT / "data" / "fantasy"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROJECTED_RESULTS_PATH = None  # auto-detected from nav


def _session() -> requests.Session:
    """Login and return an authenticated session."""
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.get(f"{BASE_URL}/login", timeout=15)
    r = s.post(
        f"{BASE_URL}/login",
        data={
            "user[login]":    os.environ["PTFG_EMAIL"],
            "user[password]": os.environ["PTFG_PASSWORD"],
            "remember_me":    "1",
        },
        allow_redirects=True,
        timeout=15,
    )
    if "/login" in r.url:
        print("Login failed — check .env credentials", file=sys.stderr)
        sys.exit(1)
    print(f"Logged in as {os.environ['PTFG_EMAIL']}")
    return s


def fetch_standings(s: requests.Session) -> pd.DataFrame:
    """Fetch season standings table."""
    r = s.get(f"{BASE_URL}/standings/individual/2026", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", id="standingsTable")
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 6 and cells[0] not in ("Place", ""):
            rows.append({
                "place":          cells[0],
                "team_name":      cells[3],
                "owner":          cells[4],
                "earnings":       cells[5],
                "earnings_back":  cells[6] if len(cells) > 6 else "",
            })
    df = pd.DataFrame(rows)
    # Parse earnings as numeric
    for col in ("earnings", "earnings_back"):
        df[col + "_num"] = (
            df[col].str.replace(r"[\$,]", "", regex=True)
                   .str.replace("---", "0")
                   .pipe(pd.to_numeric, errors="coerce")
                   .fillna(0)
                   .astype(int)
        )
    return df


def _get_results_url(s: requests.Session) -> str:
    """Auto-detect the current week projected results URL from the nav."""
    r = s.get(f"{BASE_URL}/", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "/projected_results/index/" in a["href"]:
            return BASE_URL + a["href"]
    # Fallback: check the Results page itself for "Current Week" link
    for a in soup.find_all("a", href=True):
        if "result" in a["href"].lower():
            r2 = s.get(BASE_URL + a["href"], timeout=15)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            for a2 in soup2.find_all("a", href=True):
                if "Current Week" in a2.get_text() or "/projected_results/index/" in a2["href"]:
                    if "/projected_results/index/" in a2["href"]:
                        return BASE_URL + a2["href"]
    raise RuntimeError("Could not find projected results URL")


def fetch_weekly_picks(s: requests.Session) -> pd.DataFrame:
    """Fetch current week projected results — all teams, picks + earnings."""
    url = _get_results_url(s)
    print(f"  Results URL: {url}")
    r = s.get(url, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    rows = []
    for i, tr in enumerate(table.find_all("tr")):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if i == 0 or len(cells) < 9:
            continue
        # Strip asterisk (alternate pick marker) from player names
        def clean(name):
            return name.rstrip("*").strip()

        def parse_earnings(s):
            return int(s.replace("$", "").replace(",", "")) if s.startswith("$") else 0

        rows.append({
            "weekly_rank":    cells[0],
            "season_rank":    cells[1],
            "team_name":      cells[2],
            "player_1":       clean(cells[3]),
            "earnings_1":     parse_earnings(cells[4]),
            "player_2":       clean(cells[5]),
            "earnings_2":     parse_earnings(cells[6]),
            "player_3":       clean(cells[7]),
            "earnings_3":     parse_earnings(cells[8]),
            "total_earnings": parse_earnings(cells[9]) if len(cells) > 9 else 0,
            "week":           "current",
        })
    return pd.DataFrame(rows)


def fetch_player_usage(s: requests.Session) -> pd.DataFrame:
    """Fetch golfer usage history for all 28 teams via AJAX."""
    # Get team list from dropdown
    r = s.get(f"{BASE_URL}/golfers_used_compare/by_team", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    teams = [
        (o.get("value"), o.get_text(strip=True))
        for o in soup.select("select option")
        if o.get("value")
    ]
    print(f"Found {len(teams)} teams")

    pattern = re.compile(
        r'addUsagesColumnJsonParse\("(.+?)",\s*"(.+?)",\s*(true|false)\)',
        re.DOTALL,
    )
    rows = []
    for team_id, team_name in teams:
        resp = s.post(
            f"{BASE_URL}/golfers_used_compare/by_team",
            data={"object[id]": team_id},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        m = pattern.search(resp.text)
        if not m:
            print(f"  No data for {team_name}")
            continue
        try:
            picks = json.loads(m.group(2).replace('\\"', '"').replace('\\\\', '\\'))
        except Exception as e:
            print(f"  JSON error for {team_name}: {e}")
            continue
        for player, earnings_list in picks.items():
            rows.append({
                "team_id":    team_id,
                "team_name":  team_name,
                "player":     player,
                "times_used": len(earnings_list),
                "uses_left":  3 - len(earnings_list),
                "total_earned": sum(earnings_list),
                "earnings_by_use": str(earnings_list),
            })
        print(f"  {team_name}: {len(picks)} players")

    return pd.DataFrame(rows)


def main():
    s = _session()

    print("\nFetching standings...")
    standings = fetch_standings(s)
    standings.to_csv(OUT_DIR / "league_standings.csv", index=False)
    print(f"  Saved {len(standings)} teams → league_standings.csv")

    print("\nFetching current week picks...")
    weekly = fetch_weekly_picks(s)
    weekly.to_csv(OUT_DIR / "league_weekly_picks.csv", index=False)
    print(f"  Saved {len(weekly)} teams → league_weekly_picks.csv")

    print("\nFetching player usage history...")
    usage = fetch_player_usage(s)
    usage.to_csv(OUT_DIR / "league_player_usage.csv", index=False)
    print(f"  Saved {len(usage)} rows → league_player_usage.csv")

    # Quick summary
    print("\n--- WEEK PICKS SUMMARY ---")
    print(weekly[["weekly_rank", "team_name", "player_1", "player_2", "player_3", "total_earnings"]]
          .sort_values("total_earnings", ascending=False).to_string(index=False))

    print("\n--- PLAYER OWNERSHIP THIS WEEK ---")
    all_picks = (
        pd.concat([
            weekly[["player_1"]].rename(columns={"player_1": "player"}),
            weekly[["player_2"]].rename(columns={"player_2": "player"}),
            weekly[["player_3"]].rename(columns={"player_3": "player"}),
        ])
        .query("player != 'VACANT'")
        ["player"].value_counts()
    )
    print(all_picks.head(15).to_string())


if __name__ == "__main__":
    main()
