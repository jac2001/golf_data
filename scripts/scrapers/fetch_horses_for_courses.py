#!/usr/bin/env python3
"""
Horses for Courses — Course-Specific Stats Scraper
====================================================
Pulls each player's historical SG and form stats at a specific PGA Tour
venue across the last N years, then blends them into a single per-player
course profile that powers the "Horses for Courses" dashboard section.

What it fetches (per player, at THIS course only):
  SG:Total, SG:OTT, SG:APP, SG:ARG, SG:PUTT
  Driving Accuracy, Proximity to Hole, Scrambling %, Scoring Avg

Also loads the Data Golf course importance weights so the dashboard
can highlight which stat actually separates contenders at this venue.

Output:
  data/horses_for_courses/{tournament_id}.csv

Usage:
    python3 scripts/scrapers/fetch_horses_for_courses.py --tournament-id R2026007
    python3 scripts/scrapers/fetch_horses_for_courses.py  # auto-detects current week
"""

import argparse
import time
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUT_DIR   = DATA_DIR / "horses_for_courses"
WEIGHTS_FILE = DATA_DIR / "course_sg_weights.csv"
SCHEDULE     = DATA_DIR / "raw" / "schedule_2026.csv"

# ── PGA Tour GraphQL ──────────────────────────────────────────────────────────
GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

STAT_QUERY = """
query StatDetails($tourCode: TourCode!, $statId: String!, $year: Int, $eventQuery: StatDetailEventQuery) {
  statDetails(tourCode: $tourCode, statId: $statId, year: $year, eventQuery: $eventQuery) {
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

# Stats to fetch: stat_id → (column_name, higher_is_better)
COURSE_STATS = {
    "02567": ("sg_total",     True),
    "02568": ("sg_ott",       True),
    "02569": ("sg_app",       True),
    "02570": ("sg_arg",       True),
    "02564": ("sg_putt",      True),
    "102":   ("drv_accuracy", True),
    "331":   ("proximity",    False),   # lower = closer to hole
    "130":   ("scrambling",   True),
    "120":   ("scoring_avg",  False),   # lower = better
}

YEARS_BACK = 4   # how many prior editions to collect


# ── Helpers ───────────────────────────────────────────────────────────────────
def _post(payload: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if not data.get("errors"):
                    return data
        except requests.RequestException:
            pass
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    return {}


def _base_id(tournament_id: str) -> str:
    """'R2026007' → '007'"""
    return tournament_id.lstrip("R").lstrip("0").zfill(3)[-3:]


def _historical_ids(tournament_id: str, current_year: int) -> list[tuple[int, str]]:
    """Generate (year, tid) pairs for prior editions."""
    base = _base_id(tournament_id)
    ids = []
    for yr in range(current_year - 1, current_year - 1 - YEARS_BACK, -1):
        ids.append((yr, f"R{yr}{base}"))
    return ids


def _fetch_stat_at_event(stat_id: str, year: int, tournament_id: str) -> pd.DataFrame:
    payload = {
        "operationName": "StatDetails",
        "variables": {
            "tourCode": "R",
            "statId": stat_id,
            "year": year,
            "eventQuery": {"queryType": "EVENT_ONLY", "tournamentId": tournament_id},
        },
        "query": STAT_QUERY,
    }
    data = _post(payload)
    rows = data.get("data", {}).get("statDetails", {}) or {}
    rows = rows.get("rows", [])
    if not rows:
        return pd.DataFrame()

    records = []
    for row in rows:
        if not isinstance(row, dict) or "playerName" not in row:
            continue
        stat_val = None
        for s in row.get("stats", []):
            if s.get("statName") == "Avg":
                try:
                    stat_val = float(s["statValue"].replace(",", ""))
                except (ValueError, AttributeError):
                    pass
                break
        if stat_val is not None:
            records.append({
                "player_id":   str(row.get("playerId", "")),
                "player_name": row["playerName"],
                "rank":        int(row.get("rank", 999)),
                "value":       stat_val,
                "year":        year,
            })
    return pd.DataFrame(records)


def _current_tournament_id() -> str | None:
    if not SCHEDULE.exists():
        return None
    sched = pd.read_csv(SCHEDULE)
    today = datetime.now().strftime("%Y-%m-%d")
    active = sched[(sched["start_date"] <= today) & (sched["end_date"] >= today)]
    if not active.empty:
        return str(active.iloc[0]["tournament_id"])
    upcoming = sched[sched["start_date"] > today].sort_values("start_date")
    if not upcoming.empty:
        return str(upcoming.iloc[0]["tournament_id"])
    return None


def _load_course_weights(tournament_name: str) -> dict:
    """Load DG SG importance weights for this venue."""
    if not WEIGHTS_FILE.exists():
        return {}
    dg = pd.read_csv(WEIGHTS_FILE)
    t_low = tournament_name.lower()
    dg_low = dg["tournament_name"].str.lower()

    # 1. Exact match
    matches = dg[dg_low == t_low]

    # 2. Meaningful-word match — skip short filler words that cause false positives
    _stop = {"the", "a", "an", "at", "in", "of", "by", "for", "and", "with",
             "presented", "from", "on", "to"}
    if matches.empty:
        for word in t_low.split():
            if len(word) > 4 and word not in _stop:
                matches = dg[dg_low.str.contains(word, na=False)]
                if not matches.empty:
                    break

    # 3. Last resort: longest overlapping word
    if matches.empty:
        for word in sorted(t_low.split(), key=len, reverse=True):
            if len(word) > 3:
                matches = dg[dg_low.str.contains(word, na=False)]
                if not matches.empty:
                    break

    if matches.empty:
        return {}
    row = matches.iloc[0]
    return {
        "course_name":       str(row.get("course_name", "")),
        "ott_weight":        float(row.get("ott_sg", 0)),
        "app_weight":        float(row.get("app_sg", 0)),
        "arg_weight":        float(row.get("arg_sg", 0)),
        "putt_weight":       float(row.get("putt_sg", 0)),
        "fw_width":          float(row.get("fw_width", 0)),
        "rough_difficulty":  float(row.get("rgh_diff", 0)),
        "miss_fw_penalty":   float(row.get("miss_fw_pen_frac", 0)),
        "yardage":           int(row.get("yardage", 0)),
        "par":               int(row.get("par", 72)),
    }


def fetch_horses_for_courses(tournament_id: str, tournament_name: str = "") -> pd.DataFrame:
    current_year = int(tournament_id[1:5])
    history_ids  = _historical_ids(tournament_id, current_year)

    print(f"\n  Tournament: {tournament_name or tournament_id}")
    print(f"  Fetching {len(COURSE_STATS)} stats across {len(history_ids)} prior editions: "
          f"{[tid for _, tid in history_ids]}\n")

    # Collect all raw data: {col_name: [{player_id, player_name, value, year}]}
    all_frames: dict[str, list[pd.DataFrame]] = {col_name: [] for col_name, _ in COURSE_STATS.values()}

    for stat_id, (col_name, _) in COURSE_STATS.items():
        for year, tid in history_ids:
            df = _fetch_stat_at_event(stat_id, year, tid)
            if not df.empty:
                all_frames[col_name].append(df)
                print(f"    ✓  {col_name:<14} {year}  ({len(df)} players)")
            else:
                print(f"    –  {col_name:<14} {year}  (no data)")
            time.sleep(0.3)   # be polite to the API

    # Aggregate: recency-weighted average (most recent year = highest weight)
    player_dfs: dict[str, pd.DataFrame] = {}

    for col_name, frames in all_frames.items():
        if not frames:
            continue
        combined = pd.concat(frames, ignore_index=True)
        # Recency weights: most recent year gets weight=YEARS_BACK, oldest gets 1
        max_year = combined["year"].max()
        combined["weight"] = combined["year"].apply(
            lambda y: max(1, YEARS_BACK - (max_year - y))
        )
        # Weighted mean per player
        def _weighted_mean(g):
            return (g["value"] * g["weight"]).sum() / g["weight"].sum()

        agg = (
            combined.groupby(["player_id", "player_name"])
            .apply(lambda g: pd.Series({
                col_name:              round(_weighted_mean(g), 3),
                f"{col_name}_years":   int(g["year"].nunique()),
                f"{col_name}_latest":  round(
                    g.loc[g["year"] == g["year"].max(), "value"].mean(), 3
                ),
            }), include_groups=False)
            .reset_index()
        )
        player_dfs[col_name] = agg

    if not player_dfs:
        print("\n  No data retrieved — check tournament ID and API availability.")
        return pd.DataFrame()

    # Merge all stats into one row per player
    base_cols = ["player_id", "player_name"]
    merged = None
    for col_name, df in player_dfs.items():
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on=base_cols, how="outer")

    if merged is None or merged.empty:
        return pd.DataFrame()

    # Compute course fit score using DG weights
    weights = _load_course_weights(tournament_name)
    if weights:
        w_ott  = weights.get("ott_weight",  0.025)
        w_app  = weights.get("app_weight",  0.025)
        w_arg  = weights.get("arg_weight",  0.010)
        w_putt = weights.get("putt_weight", 0.015)

        # Normalise weights to sum to 1
        total_w = w_ott + w_app + w_arg + w_putt
        if total_w > 0:
            w_ott /= total_w; w_app /= total_w
            w_arg /= total_w; w_putt /= total_w

        def _safe(row, col):
            v = row.get(col)
            return float(v) if pd.notna(v) else 0.0

        merged["course_fit_score"] = merged.apply(
            lambda r: round(
                _safe(r, "sg_ott")  * w_ott  +
                _safe(r, "sg_app")  * w_app  +
                _safe(r, "sg_arg")  * w_arg  +
                _safe(r, "sg_putt") * w_putt,
                3
            ),
            axis=1
        )

        # Rank by course fit
        merged["course_fit_rank"] = merged["course_fit_score"].rank(
            ascending=False, method="min"
        ).astype(int)

        # Add meta columns
        merged["dominant_skill"]  = _dominant_skill_label(weights)
        merged["course_name"]     = weights.get("course_name", "")
        merged["rough_difficulty"] = weights.get("rough_difficulty", 0)
        merged["fw_width"]        = weights.get("fw_width", 0)
        merged["course_yardage"]  = weights.get("yardage", 0)
        merged["course_par"]      = weights.get("par", 72)
    else:
        # Fallback: equal weight SG total
        merged["course_fit_score"] = merged.get("sg_total", pd.Series(dtype=float))
        merged["course_fit_rank"]  = merged["course_fit_score"].rank(
            ascending=False, method="min"
        ).astype(int)
        merged["dominant_skill"]  = "SG: Total"
        merged["course_name"]     = ""

    merged["tournament_id"]   = tournament_id
    merged["tournament_name"] = tournament_name
    merged["generated_at"]    = datetime.now().strftime("%Y-%m-%d %H:%M")

    merged = merged.sort_values("course_fit_rank")
    return merged


def _dominant_skill_label(weights: dict) -> str:
    """Return the most important skill at this venue."""
    skill_map = {
        "ott_weight":  "SG: Off-the-Tee",
        "app_weight":  "SG: Approach",
        "arg_weight":  "SG: Around Green",
        "putt_weight": "SG: Putting",
    }
    best_key = max(skill_map, key=lambda k: weights.get(k, 0))
    return skill_map[best_key]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch Horses for Courses data")
    parser.add_argument("--tournament-id", "-t", default=None,
                        help="Tournament ID (e.g. R2026007). Auto-detects if omitted.")
    args = parser.parse_args()

    t_id = args.tournament_id or _current_tournament_id()
    if not t_id:
        print("ERROR: Could not determine tournament ID.")
        sys.exit(1)

    # Look up tournament name from schedule
    t_name = ""
    if SCHEDULE.exists():
        sched = pd.read_csv(SCHEDULE)
        row = sched[sched["tournament_id"].astype(str) == str(t_id)]
        if not row.empty:
            t_name = str(row.iloc[0]["tournament_name"])

    print(f"\n{'='*60}")
    print(f"  HORSES FOR COURSES — {t_name or t_id}")
    print(f"{'='*60}")

    df = fetch_horses_for_courses(t_id, t_name)

    if df.empty:
        print("\n  No data returned.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{t_id}.csv"
    df.to_csv(out_path, index=False)

    print(f"\n  ✅ Saved {len(df)} players → {out_path}")
    print(f"\n  Top 10 by course fit:")
    disp_cols = [c for c in ["player_name", "course_fit_rank", "course_fit_score",
                              "sg_total", "sg_ott", "sg_app", "sg_putt"] if c in df.columns]
    print(df[disp_cols].head(10).to_string(index=False))
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
