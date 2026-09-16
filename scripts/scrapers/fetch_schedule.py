#!/usr/bin/env python3
"""
PGA Tour Schedule Fetcher (DataGolf)
====================================
Pulls a season's schedule from DataGolf /get-schedule (season= param) and
writes data/raw/schedule_{year}.csv in the same format as schedule_2026.csv,
plus course columns — course is a first-class key from 2027 on (events move
venues, e.g. The Sentry to Torrey Pines), and course_key joins directly to
player_tournament_course_form.csv for the fit tilt.

DG's schedule carries no purse or event type, so both are carried forward
from the prior season's CSV by event number (`purse_source` flags it);
majors are recognized by name; new events default to Standard.

Usage:
    python3 scripts/scrapers/fetch_schedule.py --year 2027
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dg_client import dg_get  # noqa: E402

MAJORS = {"masters", "pga championship", "u.s. open", "us open",
          "the open championship", "open championship"}

# Events with no prior-year CSV row (the 2026 CSV starts in February, and new
# events have no history anywhere). Purse/type set manually from announcements;
# purse_source is marked 'manual' so downstream code knows these are estimates.
MANUAL_OVERRIDES = {
    "the sentry":                    {"type": "Signature", "purse": 20_000_000},
    "the american express":          {"type": "Standard",  "purse": 8_800_000},
    "oneflight myrtle beach classic": {"type": "Standard", "purse": 4_000_000},
    "isco championship":             {"type": "Standard",  "purse": 4_000_000},
    "corales puntacana championship": {"type": "Standard", "purse": 4_000_000},
    "sompo championship":            {"type": "Standard",  "purse": 8_000_000},
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_prior_year_maps(year: int) -> tuple[dict, dict]:
    """event number -> (purse_str, tournament_type) from the prior season CSV."""
    prior = RAW_DIR / f"schedule_{year - 1}.csv"
    if not prior.exists():
        return {}, {}
    df = pd.read_csv(prior)
    df["enum"] = df["tournament_id"].astype(str).str[5:].str.lstrip("0")
    return (dict(zip(df["enum"], df["purse"])),
            dict(zip(df["enum"], df["tournament_type"])))


def main():
    ap = argparse.ArgumentParser(description="Fetch PGA Tour season schedule from DataGolf")
    ap.add_argument("--year", type=int, required=True)
    args = ap.parse_args()

    data = dg_get("/get-schedule", {"tour": "pga", "season": str(args.year),
                                    "upcoming_only": "no", "file_format": "json"})
    sched = data.get("schedule", data) if isinstance(data, dict) else data
    print(f"Fetched {len(sched)} events for {args.year} from DataGolf")

    purse_map, type_map = load_prior_year_maps(args.year)

    rows = []
    for ev in sched:
        enum_raw = str(ev["event_id"])
        tid = f"R{args.year}{int(enum_raw):03d}"
        start = date.fromisoformat(ev["start_date"])

        name_l = ev["event_name"].lower()
        override = MANUAL_OVERRIDES.get(name_l)

        purse_str = purse_map.get(enum_raw, "")
        purse_source = "carried_forward" if purse_str else "unknown"
        try:
            purse_val = float(str(purse_str).replace("$", "").replace(",", ""))
        except ValueError:
            purse_val = None
        if purse_val is None and override:
            purse_val = override["purse"]
            purse_str, purse_source = f"${purse_val:,.2f}", "manual"

        if any(mj in name_l for mj in MAJORS):
            ttype = "Major"
        elif override:
            ttype = override["type"]
        elif pd.notna(type_map.get(enum_raw, None)):
            ttype = type_map[enum_raw]
        else:
            ttype = "Standard"

        rows.append({
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=3)).isoformat(),
            "tournament_name": ev["event_name"],
            "tournament_type": ttype,
            "location": ev.get("location", ""),
            "course": ev.get("course", ""),
            "course_key": ev.get("course_key", ""),
            "latitude": ev.get("latitude"),
            "longitude": ev.get("longitude"),
            "purse": purse_str,
            "purse_source": purse_source,
            "winner_share": f"${purse_val * 0.18:,.2f}" if purse_val else "",
            "tournament_id": tid,
            "power_slug": _slug(ev["event_name"]),
        })

    df = pd.DataFrame(rows).sort_values("start_date").reset_index(drop=True)
    df.insert(0, "week", range(1, len(df) + 1))

    out = RAW_DIR / f"schedule_{args.year}.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} events -> {out.relative_to(PROJECT_ROOT)}")
    print(f"  purse carried forward: {(df['purse_source'] == 'carried_forward').sum()}, "
          f"unknown: {(df['purse_source'] == 'unknown').sum()}")
    print(f"  types: {df['tournament_type'].value_counts().to_dict()}")
    new_events = df[df["purse_source"] == "unknown"]["tournament_name"].tolist()
    if new_events:
        print(f"  NEW/unmatched events (need manual purse/type): {new_events}")


if __name__ == "__main__":
    main()
