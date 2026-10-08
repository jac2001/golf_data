"""
data_freshness.py — model inputs that aren't tied to one event must still be recent.
===================================================================================
prediction_integrity.py catches event-specific files used under the wrong
event. Some inputs carry no event at all — DG skill ratings, DG approach
skill, the world ranking — so they go stale silently instead: on 2026-10-07
skill + approach were 9 days old (only the often-dropped Tuesday refresh
fetched them) and DG rankings had been frozen since April (its fetcher was
deleted).

Ages come from the date INSIDE each file, never the file's mtime: on CI a
git checkout stamps every file "now", so mtime says nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# (label, path, date column, max age in days) — inputs predict_tournament reads.
MODEL_INPUTS = [
    ("DG skill ratings", ROOT / "data/datagolf/dg_skill_ratings_latest.csv", "last_updated", 10),
    ("DG approach skill", ROOT / "data/datagolf/dg_approach_skill_latest.csv", "last_updated", 10),
    ("World ranking", ROOT / "data/rankings/owgr_2026.csv", "fetched_date", 10),
]


def file_age_days(path: Path, column: str, now: datetime | None = None) -> float | None:
    """Days since the newest date in `column`; None when unreadable."""
    try:
        s = pd.read_csv(path, usecols=[column])[column]
    except Exception:
        return None
    ts = pd.to_datetime(s.astype(str).str.replace(" UTC", "", regex=False), errors="coerce", utc=True).max()
    if pd.isna(ts):
        return None
    now = now or datetime.now(timezone.utc)
    return (now - ts.to_pydatetime()).total_seconds() / 86_400


def stale_inputs(inputs=MODEL_INPUTS, now: datetime | None = None) -> tuple[list[str], list[str]]:
    """(failures, notes) for every input older than its limit or unreadable."""
    failures, notes = [], []
    for label, path, col, max_days in inputs:
        age = file_age_days(path, col, now)
        if age is None:
            failures.append(f"{label}: can't read a date from {path.name} ({col})")
        elif age > max_days:
            failures.append(f"{label} is {age:.0f} days old (limit {max_days}) — {path.name}")
        else:
            notes.append(f"✓ {label}: {age:.1f} days old")
    return failures, notes
