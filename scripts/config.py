"""
Central configuration for season-dependent file paths and constants.

Import SEASON (int) and the path helpers instead of hardcoding _2026 everywhere.
The season is determined by the schedule CSV — whichever year has the most
upcoming/recent tournaments. Falls back to the current calendar year.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"


def _detect_season() -> int:
    """The active PGA TOUR season, from today's date and each PGA schedule's
    event dates (season_resolver.active_season, Jack's). Never "the newest
    schedule file": schedule_2027.csv appearing in October 2026 made every
    script think it was 2027 (audit finding 3). schedule_euro_* files have
    their own seasons and are left out."""
    import csv
    try:
        from season_resolver import active_season
    except ImportError:                          # imported as scripts.config
        from scripts.season_resolver import active_season

    schedules: dict[int, list[tuple[date, date]]] = {}
    for path in DATA_DIR.glob("raw/schedule_*.csv"):
        year = path.stem.split("_", 1)[1]
        if not (year.isdigit() and len(year) == 4):
            continue                             # schedule_euro_2026, ...
        events = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    events.append((date.fromisoformat(row["start_date"]),
                                   date.fromisoformat(row["end_date"])))
                except (KeyError, TypeError, ValueError):
                    continue
        schedules[int(year)] = events
    return active_season(date.today(), schedules)

SEASON: int = _detect_season()

# ── Canonical per-season file paths ──────────────────────────────────────────

def leaderboards_csv() -> Path:
    return DATA_DIR / "historical" / f"leaderboards_{SEASON}.csv"

def form_stats_csv() -> Path:
    return DATA_DIR / "historical" / f"form_stats_{SEASON}.csv"

def tournament_stats_csv() -> Path:
    return DATA_DIR / "historical" / f"tournament_stats_{SEASON}.csv"

def schedule_csv() -> Path:
    return DATA_DIR / "raw" / f"schedule_{SEASON}.csv"

def usage_tracker_json() -> Path:
    return DATA_DIR / "fantasy" / f"usage_tracker_{SEASON}.json"
