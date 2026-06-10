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
    """Return the active PGA Tour season year from the schedule CSV, or calendar year."""
    sched_candidates = sorted(DATA_DIR.glob("raw/schedule_*.csv"), reverse=True)
    for path in sched_candidates:
        # e.g. schedule_2026.csv → 2026
        stem = path.stem  # "schedule_2026"
        parts = stem.split("_")
        for part in parts:
            if part.isdigit() and len(part) == 4:
                return int(part)
    # Last-resort fallback
    return date.today().year


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
