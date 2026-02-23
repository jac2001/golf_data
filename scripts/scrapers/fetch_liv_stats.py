#!/usr/bin/env python3
"""
LIV Golf Stats Scraper
======================
Fetches LIV Golf player results and statistics from the ESPN API.
Builds per-player scoring profiles used to supplement predictions when
LIV players appear in PGA Tour major championships or other eligible events.

No SG data is available for LIV Golf, so we derive an estimated SG:Total proxy
from relative scoring average: a player scoring 0.5 strokes/round better than
the LIV field average ≈ ~+0.5 estimated SG (adjusted for LIV field strength).

Output:
  data/historical/liv_stats_{year}.csv       — full season tournament-by-tournament
  data/historical/liv_player_profiles.csv    — one row per player (latest season)

Usage:
    python3 scripts/scrapers/fetch_liv_stats.py              # 2023-current
    python3 scripts/scrapers/fetch_liv_stats.py --year 2025  # single year
"""

import argparse
import time
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUT_DIR   = DATA_DIR / "historical"

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/v2/scoreboard/header"
ESPN_LEADERBOARD = "https://site.web.api.espn.com/apis/site/v2/sports/golf/leaderboard"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GolfDataBot/1.0)"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    return {}


def _fetch_event_ids(year: int) -> list[dict]:
    """Return list of {id, name, date, status} for all LIV events in a year."""
    start = f"{year}0101"
    end   = f"{year}1231"
    data  = _get(ESPN_SCOREBOARD, params={
        "sport": "golf", "league": "liv", "limit": 100,
        "dates": f"{start}-{end}",
    })
    events_raw = (
        data.get("sports", [{}])[0]
            .get("leagues", [{}])[0]
            .get("events", [])
    )
    events = []
    for e in events_raw:
        events.append({
            "event_id":   e["id"],
            "name":       e["name"],
            "date":       e.get("date", "")[:10],
            "status":     e.get("status", ""),
            "location":   e.get("location", ""),
            "purse":      e.get("purse", 0),
        })
    return events


def _fetch_event_results(event_id: str) -> pd.DataFrame:
    """Fetch all competitor results for a single LIV event."""
    data = _get(ESPN_LEADERBOARD, params={"event": event_id, "league": "liv"})
    events = data.get("events", [])
    if not events:
        return pd.DataFrame()

    competitions = events[0].get("competitions", [])
    if not competitions or not isinstance(competitions[0], dict):
        return pd.DataFrame()
    comps = competitions[0].get("competitors", [])
    if not comps:
        return pd.DataFrame()

    records = []
    for c in comps:
        athlete = c.get("athlete", {})
        name = athlete.get("displayName", "")
        player_id = str(athlete.get("id", ""))
        country = athlete.get("flag", {}).get("alt", "")

        # Score and position
        score_obj = c.get("score", {})
        total_score   = score_obj.get("value")        # raw total strokes
        score_display = score_obj.get("displayValue", "")  # e.g. "-14"

        status_obj = c.get("status", {})
        position = status_obj.get("position", {}).get("displayName", "")
        is_completed = status_obj.get("type", {}).get("completed", False)

        # Round-by-round linescores
        linescores = c.get("linescores", [])
        rounds_played = len(linescores)
        round_scores = [ls.get("value") for ls in linescores if ls.get("value") is not None]

        # Scoring average this event (strokes per round)
        scoring_avg = None
        if round_scores and rounds_played > 0:
            scoring_avg = round(sum(round_scores) / len(round_scores), 3)

        # Earnings
        earnings = c.get("earnings", 0) or 0

        if name:
            records.append({
                "player_id":     player_id,
                "player_name":   name,
                "country":       country,
                "position":      position,
                "total_score":   total_score,
                "score_vs_par":  score_display,
                "rounds_played": rounds_played,
                "scoring_avg":   scoring_avg,
                "earnings":      earnings,
                "completed":     is_completed,
            })

    return pd.DataFrame(records)


def fetch_liv_season(year: int) -> pd.DataFrame:
    """Fetch all completed LIV events for a season, return per-player-per-event data."""
    print(f"\n  LIV Golf {year}:")
    events = _fetch_event_ids(year)
    completed = [e for e in events if e["status"] in ("post", "complete", "Final")]
    print(f"  {len(events)} events found, {len(completed)} completed")

    if not completed:
        return pd.DataFrame()

    all_rows = []
    for ev in completed:
        eid = ev["event_id"]
        ename = ev["name"]
        df = _fetch_event_results(eid)
        if not df.empty:
            df["event_id"]   = eid
            df["event_name"] = ename
            df["event_date"] = ev["date"]
            df["year"]       = year
            all_rows.append(df)
            print(f"    ✓  {ename:<35} ({len(df)} players)")
        else:
            print(f"    –  {ename:<35} (no data)")
        time.sleep(0.3)

    if not all_rows:
        return pd.DataFrame()

    season_df = pd.concat(all_rows, ignore_index=True)

    # Compute SG proxy at season level: how much better than LIV field avg?
    # Sanity filter: valid golf scores are 60-90 per round
    valid = season_df.dropna(subset=["scoring_avg"])
    valid = valid[(valid["scoring_avg"] >= 60) & (valid["scoring_avg"] <= 90)]
    if not valid.empty:
        # Season-level scoring avg per player (weighted by rounds)
        player_avg = (
            valid.groupby(["player_id", "player_name"])
            .apply(lambda g: pd.Series({
                "liv_scoring_avg":   round(g["scoring_avg"].mean(), 3),
                "liv_events":        int(g["event_id"].nunique()),
                "liv_rounds":        int(g["rounds_played"].sum()),
                "liv_earnings":      int(g["earnings"].sum()),
                "liv_top10s":        int((g["position"].str.lstrip("T").str.extract(r"(\d+)", expand=False)
                                           .fillna("999").astype(int) <= 10).sum()),
            }), include_groups=False)
            .reset_index()
        )

        field_avg = float(valid["scoring_avg"].mean())
        # Each stroke/round below LIV field avg ≈ +0.5 SG on PGA Tour
        # (LIV field avg player ≈ -0.5 SG on PGA Tour; LIV top player ≈ 0.0 to +0.5)
        player_avg["liv_sg_proxy"] = ((field_avg - player_avg["liv_scoring_avg"]) * 0.5).round(3)
        player_avg["year"] = year
        return player_avg

    return pd.DataFrame()


def build_player_profiles(all_years: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per player: use most recent season, track best year."""
    if not all_years:
        return pd.DataFrame()

    combined = pd.concat(all_years, ignore_index=True)

    profiles = (
        combined.sort_values("year", ascending=False)
        .groupby("player_id", as_index=False)
        .first()
    )

    # Add best season (highest sg_proxy year)
    if "liv_sg_proxy" in combined.columns:
        best_idx = (
            combined.dropna(subset=["liv_sg_proxy"])
            .groupby("player_id")["liv_sg_proxy"]
            .idxmax()
        )
        best_yrs = combined.loc[best_idx, ["player_id", "year"]].rename(
            columns={"year": "liv_best_year"}
        )
        profiles = profiles.merge(best_yrs, on="player_id", how="left")

    profiles["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return profiles


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch LIV Golf stats via ESPN API")
    parser.add_argument("--year", "-y", type=int, default=None,
                        help="Single year to fetch (default: 2023–current)")
    parser.add_argument("--years-back", type=int, default=3,
                        help="How many seasons to fetch (default 3)")
    args = parser.parse_args()

    current_year = datetime.now().year
    if args.year:
        years = [args.year]
    else:
        years = list(range(current_year - args.years_back + 1, current_year + 1))

    print(f"\n{'='*60}")
    print(f"  LIV GOLF STATS SCRAPER (via ESPN API)")
    print(f"  Years: {years}")
    print(f"{'='*60}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_dfs = []
    for year in years:
        df = fetch_liv_season(year)
        if not df.empty:
            out = OUTPUT_DIR / f"liv_stats_{year}.csv"
            df.to_csv(out, index=False)
            print(f"  ✅ Saved {len(df)} players → {out.name}")
            all_dfs.append(df)

    if all_dfs:
        profiles = build_player_profiles(all_dfs)
        profile_path = OUTPUT_DIR / "liv_player_profiles.csv"
        profiles.to_csv(profile_path, index=False)
        print(f"\n  ✅ Player profiles: {len(profiles)} players → {profile_path.name}")

        print(f"\n  Top 15 LIV players by SG proxy (most recent season):")
        disp = [c for c in ["player_name", "year", "liv_scoring_avg",
                             "liv_sg_proxy", "liv_events", "liv_top10s"] if c in profiles.columns]
        print(profiles.nlargest(15, "liv_sg_proxy")[disp].to_string(index=False))

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
