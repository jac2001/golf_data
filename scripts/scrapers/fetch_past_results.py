#!/usr/bin/env python3
"""
PGA Tour Past Results Scraper
==============================
Fetches historical tournament results from the PGA Tour past-results page.
Parses __NEXT_DATA__ JSON (same technique as fetch_live_leaderboard.py).

Works for any PGA Tour-listed tournament including the Masters (R*014).

Usage:
    python fetch_past_results.py --tournament-id R2026014 --year 2025
    python fetch_past_results.py --tournament-id R2026014              # all available years
    python fetch_past_results.py --tournament-id R2026014 --slug masters-tournament
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
HIST_DIR = DATA_DIR / "historical"
LIVE_DIR = DATA_DIR / 'live'

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})



def _live_winner_player_id(tid: str) -> Optional[str]:
    """ 
    Return the winning player_id from the live leaderboard CSV, or None if unavailable.
    Used to guard against fetch_past_results writing wrong-year data.
    """
    
    live_path = LIVE_DIR / f"leaderboard_{tid.lower()}.csv"
    
    if not live_path.exists():
        return None 
    
    
    try: 
        live = pd.read_csv(live_path)
        pos1 = live[live['position'] == '1']
        if not pos1.empty:
            return str(int(pos1.iloc[0]['player_id']))
        
        if not pos1.empty:
            return str(int(pos1.iloc[0]['player_id']))
        
        if "total_numeric" in live.columns:
            s = live.sort_values('total_numeric', ascending=True).dropna(subset=['total_numeric'])
            if not s.empty:
                return str(int(s.iloc[0]['player_id']))
            
        
        
        
    except Exception as e:
        pass   
    
    return None 
     
        
    
    


def _tournament_slug(tournament_id: str, slug_override: str = "") -> str:
    """Derive a URL slug from the tournament ID or a provided override."""
    if slug_override:
        return slug_override.strip("/")
    # Known mappings for tournaments not on pgatour.com's main schedule
    known = {
        "014": "masters-tournament",
        "026": "us-open",
        "100": "the-open-championship",
        "047": "pga-championship",
    }
    suffix = tournament_id[-3:] if len(tournament_id) >= 3 else ""
    if suffix in known:
        return known[suffix]
    # Generic: lowercase, hyphenate
    return re.sub(r"[^a-z0-9]+", "-", tournament_id.lower()).strip("-")


def _year_from_tid(tournament_id: str) -> Optional[int]:
    """Extract year from R2026014 → 2026."""
    m = re.search(r"R(\d{4})", tournament_id.upper())
    return int(m.group(1)) if m else None


def fetch_past_results_page(tournament_id: str, year: int, slug: str) -> Optional[dict]:
    """
    Fetch and parse the past-results page for one tournament + year.
    Returns the raw pastResults dict from __NEXT_DATA__, or None.
    """
    tid_for_year = f"R{year}{tournament_id[-3:]}"
    url = f"https://www.pgatour.com/tournaments/{year}/{slug}/{tid_for_year}/past-results"
    print(f"  GET {url}")

    try:
        resp = SESSION.get(url, timeout=30)
    except Exception as e:
        print(f"  Request error: {e}")
        return None

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        print("  No __NEXT_DATA__ found")
        return None

    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return None

    props = data.get("props", {}).get("pageProps", {})
    dehydrated = props.get("dehydratedState", {})
    queries = dehydrated.get("queries", [])

    for q in queries:
        qdata = q.get("state", {}).get("data")
        if not isinstance(qdata, dict):
            continue
        # pastResults query has a 'players' list where each has 'rounds'
        if "players" in qdata and isinstance(qdata["players"], list) and qdata["players"]:
            first = qdata["players"][0]
            if isinstance(first, dict) and "rounds" in first:
                return qdata

    print("  pastResults query not found in __NEXT_DATA__")
    return None


def parse_past_results(raw: dict, tournament_id: str, year: int) -> list[dict]:
    """Convert the raw pastResults dict into a list of row dicts matching leaderboards_*.csv format."""
    rows = []
    tid_for_year = f"R{year}{tournament_id[-3:]}"

    # Tournament name from outer keys, or derive from known suffix → name mapping
    _KNOWN_NAMES = {
        "014": "Masters Tournament",
        "026": "U.S. Open Championship",
        "100": "The Open Championship",
        "047": "PGA Championship",
    }
    t_name = (raw.get("tournamentName", "") or raw.get("displayName", "")).strip()
    if not t_name or re.match(r"^R\d{7}$", t_name):
        t_name = _KNOWN_NAMES.get(tournament_id[-3:], "")

    for p in raw.get("players", []):
        if not isinstance(p, dict):
            continue

        player = p.get("player", {})
        pid = str(player.get("id", "")).strip()
        pname = str(player.get("displayName", "")).strip()
        if not pid or not pname:
            continue

        position = str(p.get("position", "")).strip()
        total_str = str(p.get("total", "")).strip()
        to_par_str = str(p.get("parRelativeScore", "")).strip()

        # Convert par-relative score: "E" → 0, "-11" → -11, "+3" → 3
        def _to_par(s: str) -> Optional[float]:
            s = s.strip()
            if s in ("E", "e", ""):
                return 0.0
            try:
                return float(s)
            except ValueError:
                return None

        to_par = _to_par(to_par_str)

        # Total score
        try:
            total_score = float(total_str) if total_str else None
        except ValueError:
            total_score = None

        # Round scores — list of {"score": "72", "parRelativeScore": "-1"}
        rounds = p.get("rounds", [])
        r_scores = []
        r_to_par = []
        for r in rounds:
            if isinstance(r, dict):
                r_scores.append(r.get("score", ""))
                r_to_par.append(r.get("parRelativeScore", ""))

        def _score(s):
            try:
                return float(s) if s else None
            except ValueError:
                return None

        # additionalData: [fedex_points, earnings] — order varies; earnings has "$"
        add = p.get("additionalData", [])
        fedex = None
        earnings = None
        for item in add:
            s = str(item).strip()
            if "$" in s:
                earnings = s
            else:
                try:
                    fedex = float(s.replace(",", ""))
                except ValueError:
                    pass

        rounds_played = len([s for s in r_scores if s])

        rows.append({
            "tournament_id": tid_for_year,
            "year": year,
            "player_id": pid,
            "player_name": pname,
            "position": position,
            "total_score": total_score,
            "to_par": to_par,
            "fedex_points": fedex,
            "earnings": earnings,
            "rounds_played": rounds_played,
            "r1_score": _score(r_scores[0]) if len(r_scores) > 0 else None,
            "r2_score": _score(r_scores[1]) if len(r_scores) > 1 else None,
            "r3_score": _score(r_scores[2]) if len(r_scores) > 2 else None,
            "r4_score": _score(r_scores[3]) if len(r_scores) > 3 else None,
            "r1_to_par": _to_par(r_to_par[0]) if len(r_to_par) > 0 else None,
            "r2_to_par": _to_par(r_to_par[1]) if len(r_to_par) > 1 else None,
            "r3_to_par": _to_par(r_to_par[2]) if len(r_to_par) > 2 else None,
            "r4_to_par": _to_par(r_to_par[3]) if len(r_to_par) > 3 else None,
            "tournament_name": t_name,
        })

    return rows


def get_available_years(tournament_id: str, slug: str) -> list[int]:
    """
    Fetch the current year's page and extract availableSeasons from __NEXT_DATA__.
    Falls back to a reasonable range if not found.
    """
    current_year = _year_from_tid(tournament_id) or 2026
    tid_for_year = f"R{current_year}{tournament_id[-3:]}"
    url = f"https://www.pgatour.com/tournaments/{current_year}/{slug}/{tid_for_year}/past-results"

    print(f"  Probing available seasons from {url}")
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            tag = soup.find("script", id="__NEXT_DATA__")
            if tag and tag.string:
                data = json.loads(tag.string)
                props = data.get("props", {}).get("pageProps", {})
                dehydrated = props.get("dehydratedState", {})
                for q in dehydrated.get("queries", []):
                    qdata = q.get("state", {}).get("data")
                    if isinstance(qdata, dict) and "availableSeasons" in qdata:
                        seasons = qdata["availableSeasons"]
                        if isinstance(seasons, list):
                            years = []
                            for s in seasons:
                                if isinstance(s, dict):
                                    y = s.get("year") or s.get("displaySeason")
                                else:
                                    y = s
                                try:
                                    years.append(int(str(y)[:4]))
                                except (ValueError, TypeError):
                                    pass
                            if years:
                                print(f"  Found {len(years)} seasons: {min(years)}–{max(years)}")
                                return sorted(set(years), reverse=True)
    except Exception as e:
        print(f"  Season probe error: {e}")

    # Fallback: last 10 years
    return list(range(current_year - 1, max(current_year - 11, 2015), -1))

def append_to_leaderboard_csv(rows: list[dict], year: int) -> Path:
    """ 
    Merge new rows into data/historical/leaderboards_{year}.csv 
    Deduplicates by (tournament_id, player_id).
    Skips the write if the scraped winner does not match the live leaderboard winner
    (guards against PGA Tour returning prior-year data for a recently completed tournament).
    """
    
    out_path = HIST_DIR / f"leaderboards_{year}.csv"
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows)
    
    if new_df.empty:
        return out_path 
    
    tid = new_df['tournament_id'].iloc[0]
    
    # --- Validation: cross-check scraped winner against live leaderboard winner -- 
    live_winner = _live_winner_player_id(tid)
    if live_winner is not None:
        scraped_winners = {
            str(r['player_id'])
            for r in rows
            if str(r.get('position', '')).strip() == '1'
        }
        
        if scraped_winners and live_winner not in scraped_winners:
            print(
                f" SKIPPING for {tid}: scraped winner(s) {scraped_winners} " 
                f"do not match live leaderboard {live_winner}.\n"
                f" PGA Tour page is likely serving prior-year data. "
                f"Keeping existing {out_path.name} unchanged."
                
            )
            return out_path
        print(f" Validation OK: live winner {live_winner} confirmed in scraped data.")
    
    if out_path.exists():
        existing = pd.read_csv(out_path)
        existing = existing[existing['tournament_id'] != tid]
        combined = pd.concat([existing, new_df.astype(str)], ignore_index=True)
    else:
        combined = new_df.astype(str)
    
    combined.to_csv(out_path, index=False)
    return out_path 



def main():
    parser = argparse.ArgumentParser(description="Fetch PGA Tour past results (incl. Masters)")
    parser.add_argument("--tournament-id", required=True,
                        help="Tournament ID e.g. R2026014 (Masters)")
    parser.add_argument("--slug", default="",
                        help="URL slug e.g. masters-tournament (auto-detected for majors)")
    parser.add_argument("--year", type=int, default=None,
                        help="Single year to fetch (default: all available years)")
    parser.add_argument("--years-back", type=int, default=10,
                        help="How many years to fetch when --year is not set (default: 10)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds to wait between requests (default: 1.5)")
    args = parser.parse_args()

    tid = args.tournament_id.strip().upper()
    slug = _tournament_slug(tid, args.slug)
    print(f"Tournament: {tid}  Slug: {slug}")

    if args.year:
        years_to_fetch = [args.year]
    else:
        all_years = get_available_years(tid, slug)
        years_to_fetch = all_years[:args.years_back]
        print(f"Fetching {len(years_to_fetch)} years: {years_to_fetch}")

    total_rows = 0
    for year in years_to_fetch:
        print(f"\nYear {year}:")
        raw = fetch_past_results_page(tid, year, slug)
        if raw is None:
            print(f"  Skipping {year}")
            continue

        rows = parse_past_results(raw, tid, year)
        if not rows:
            print(f"  No rows parsed for {year}")
            continue

        out_path = append_to_leaderboard_csv(rows, year)
        print(f"  Saved {len(rows)} rows → {out_path.name}")
        total_rows += len(rows)

        if year != years_to_fetch[-1]:
            time.sleep(args.delay)

    print(f"\nDone. Total rows written: {total_rows}")


if __name__ == "__main__":
    main()
