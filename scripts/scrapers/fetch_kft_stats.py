#!/usr/bin/env python3
"""
Korn Ferry Tour Stats Scraper
==============================
Fetches traditional stats (scoring avg, driving, GIR, scrambling, etc.)
for KFT players using the PGA Tour GraphQL API (tourCode: H).

No SG data is available for KFT, so we derive an estimated SG:Total proxy
from relative scoring average: a player scoring 0.5 strokes/round better
than KFT field average ≈ ~+0.3 estimated SG (PGA Tour adjusted).

Stats fetched (tourCode=H):
  108  Scoring Average
  101  Driving Distance
  102  Driving Accuracy %
  103  GIR %
  130  Scrambling %
  111  Sand Save %
  119  Putts Per Round
  138  Top 10 Finishes
  109  Money Leaders (used to identify top finishers / graduates)

Output:
  data/historical/kft_stats_{year}.csv       — full season stat table
  data/historical/kft_player_profiles.csv    — one row per player (latest season)

Usage:
    python3 scripts/scrapers/fetch_kft_stats.py              # 2022-2025
    python3 scripts/scrapers/fetch_kft_stats.py --year 2024  # single year
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

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/korn-ferry-tour/stats",
}

# KFT stat IDs → (column_name, value_key_in_stats_array, higher_is_better)
KFT_STATS = {
    "108": ("scoring_avg",    "Avg",              False),  # lower = better
    "101": ("drv_distance",   "Avg",              True),
    "102": ("drv_accuracy",   "%",                True),
    "103": ("gir_pct",        "%",                True),
    "130": ("scrambling",     "%",                True),
    "111": ("sand_save",      "%",                True),
    "119": ("putts_per_rnd",  "Avg",              False),  # lower = better
    "138": ("top10s",         "Top 10",           True),
    "109": ("money",          "Money",            True),
}

STAT_QUERY = """
query StatDetails($tourCode: TourCode!, $statId: String!, $year: Int) {
  statDetails(tourCode: $tourCode, statId: $statId, year: $year) {
    statTitle
    rows {
      ... on StatDetailsPlayer {
        playerId
        playerName
        rank
        stats { statName statValue }
      }
    }
  }
}
"""


def _post(payload: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if not data.get("errors"):
                    return data
        except requests.RequestException:
            pass
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    return {}


def _fetch_stat(stat_id: str, col_name: str, value_key: str, year: int) -> pd.DataFrame:
    payload = {
        "operationName": "StatDetails",
        "variables": {"tourCode": "H", "statId": stat_id, "year": year},
        "query": STAT_QUERY,
    }
    data = _post(payload)
    rows = (data.get("data") or {}).get("statDetails") or {}
    rows = rows.get("rows", [])
    if not rows:
        return pd.DataFrame()

    records = []
    for row in rows:
        if not isinstance(row, dict) or "playerName" not in row:
            continue
        val = None
        for s in row.get("stats", []):
            if s.get("statName") == value_key:
                raw = str(s.get("statValue", "")).replace(",", "").replace("$", "").strip()
                try:
                    val = float(raw)
                except ValueError:
                    pass
                break
        if val is not None:
            records.append({
                "player_id":   str(row.get("playerId", "")),
                "player_name": row["playerName"],
                "kft_rank":    int(row.get("rank", 999)),
                col_name:      val,
            })

    return pd.DataFrame(records)


def _normalize_name(name: str) -> str:
    """Convert 'FIRST LAST' (all-caps KFT format) to 'First Last'."""
    return " ".join(w.capitalize() for w in str(name).split())


def fetch_kft_season(year: int) -> pd.DataFrame:
    """Fetch all KFT stats for a given season and merge into one row per player."""
    print(f"\n  KFT {year}:")
    player_dfs: dict[str, pd.DataFrame] = {}

    for stat_id, (col_name, value_key, _) in KFT_STATS.items():
        df = _fetch_stat(stat_id, col_name, value_key, year)
        if not df.empty:
            player_dfs[col_name] = df[["player_id", "player_name", col_name]]
            print(f"    ✓  {col_name:<18} ({len(df)} players)")
        else:
            print(f"    –  {col_name:<18} (no data)")
        time.sleep(0.25)

    if not player_dfs:
        print(f"  No data for {year}")
        return pd.DataFrame()

    # Merge all stats
    merged = None
    for col_name, df in player_dfs.items():
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on=["player_id", "player_name"], how="outer")

    if merged is None or merged.empty:
        return pd.DataFrame()

    # Normalize names (KFT uses ALL CAPS on some years)
    merged["player_name"] = merged["player_name"].apply(_normalize_name)

    # Compute estimated SG proxy from scoring average relative to field
    if "scoring_avg" in merged.columns:
        sc = pd.to_numeric(merged["scoring_avg"], errors="coerce")
        field_avg = sc.mean()
        # Each stroke/round below field avg ≈ +0.6 SG (KFT→PGA Tour conversion factor)
        # Based on: KFT avg player ≈ -0.5 SG on PGA Tour; top KFT ≈ +0.0 to +0.3
        merged["kft_sg_proxy"] = ((field_avg - sc) * 0.6).round(3)

    merged["kft_year"] = year
    merged["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return merged


def build_player_profiles(all_years: list[pd.DataFrame]) -> pd.DataFrame:
    """
    One row per player: use the most recent KFT season.
    Add a 'kft_best_season' column referencing the year with best scoring avg.
    """
    if not all_years:
        return pd.DataFrame()

    combined = pd.concat(all_years, ignore_index=True)

    # For each player take the most recent year's stats
    profiles = (
        combined.sort_values("kft_year", ascending=False)
        .groupby("player_id", as_index=False)
        .first()
    )

    # Add best season indicator (year with lowest scoring_avg)
    if "scoring_avg" in combined.columns:
        best_idx = (
            combined.dropna(subset=["scoring_avg"])
            .groupby("player_id")["scoring_avg"]
            .idxmin()
        )
        best_years = combined.loc[best_idx, ["player_id", "kft_year"]].rename(
            columns={"kft_year": "kft_best_year"}
        )
        profiles = profiles.merge(best_years, on="player_id", how="left")

    return profiles


def main():
    parser = argparse.ArgumentParser(description="Fetch Korn Ferry Tour stats")
    parser.add_argument("--year", "-y", type=int, default=None,
                        help="Single year to fetch (default: 2022–current)")
    parser.add_argument("--years-back", type=int, default=4,
                        help="How many seasons to fetch (default 4)")
    args = parser.parse_args()

    current_year = datetime.now().year
    if args.year:
        years = [args.year]
    else:
        years = list(range(current_year - args.years_back + 1, current_year + 1))

    print(f"\n{'='*60}")
    print(f"  KORN FERRY TOUR STATS SCRAPER")
    print(f"  Years: {years}")
    print(f"{'='*60}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_dfs = []
    for year in years:
        df = fetch_kft_season(year)
        if not df.empty:
            out = OUTPUT_DIR / f"kft_stats_{year}.csv"
            df.to_csv(out, index=False)
            print(f"  ✅ Saved {len(df)} players → {out.name}")
            all_dfs.append(df)

    # Build combined profile file
    if all_dfs:
        profiles = build_player_profiles(all_dfs)
        profile_path = DATA_DIR / "historical" / "kft_player_profiles.csv"
        profiles.to_csv(profile_path, index=False)
        print(f"\n  ✅ Player profiles: {len(profiles)} players → {profile_path.name}")

        # Preview
        print(f"\n  Top 10 KFT players by SG proxy (most recent season):")
        disp = [c for c in ["player_name", "kft_year", "scoring_avg",
                             "kft_sg_proxy", "top10s", "gir_pct"] if c in profiles.columns]
        print(profiles.nlargest(10, "kft_sg_proxy")[disp].to_string(index=False))

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
