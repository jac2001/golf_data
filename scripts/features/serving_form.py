"""
serving_form.py — form features computed at PREDICTION time, the same way
training computed them.
======================================================================
The Oct 14 pandas check found the PGA model getting 8 of its trained
features as 0 every week (make_predictions fills absent columns with
0.0). Three of them are the par-scoring field percentiles:

  recent_par3_scoring_field_pct   (stat 299 — values 59–74, so it's really
  recent_par4_scoring_field_pct    a round-score average; the name came
  recent_par5_scoring_field_pct    from training and is kept for parity)

In training (merge_all_historical_data.py, ~L877 and ~L1015) they are:
  1. per player, per stat: that player's form_stats rows from events
     BEFORE this one (tournament_id < this tid), sorted by tournament_id,
     the last 5 rows (tail(5)), stat_value parsed to a number, NaNs
     dropped, then the mean           → recent_par3_scoring, etc.
  2. within the event's field: rank(ascending=False, pct=True)
     lower scoring is better, so the LOWEST average gets 1.0
                                       → recent_par3_scoring_field_pct
  A player with no prior rows stays NaN in both steps (rank skips NaN).

At serving the model must receive the same numbers, so this module must
reproduce that exactly; test_serving_form.py checks it against the
training table itself.
"""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# training's STAT_IDS (merge_all_historical_data.py), as strings
PAR_STATS = {
    "recent_par3_scoring": "299",
    "recent_par4_scoring": "142",
    "recent_par5_scoring": "143",
}
N_EVENTS = 5


def load_form_stats(hist_dir: Path = ROOT / "data" / "historical") -> pd.DataFrame:
    """Every form_stats_{year}.csv (committed, so this works on CI with no
    DuckDB). stat_id and player_id as strings: the classic type-mismatch
    bug class in this project."""
    files = sorted(glob.glob(str(hist_dir / "form_stats_20*.csv")))
    df = pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)
    df["stat_id"] = df["stat_id"].astype(str)
    df["player_id"] = df["player_id"].astype(str)
    return df


# ── TODO(Jack): recent_par_scoring_field_pct ────────────────────────────────
# form_stats:  load_form_stats()'s output (every year)
# field_ids:   this event's player_ids, as strings
# before_tid:  this event's tournament_id; only rows with a SMALLER
#              tournament_id count (string compare works: 'R2025...' <
#              'R2026...', and within a year the number orders events)
#
# Return a DataFrame with one row per field player: player_id, then for
# each of the three PAR_STATS columns the raw average AND the
# "_field_pct" percentile (6 columns + player_id).
#
# Follow training's order of operations EXACTLY (the docstring above):
# tail(N_EVENTS) comes BEFORE dropping NaNs, so a NaN in the last 5 rows
# leaves only 4 to average; it doesn't reach back for a 6th. Parity is
# the point: a "better" version that differs from training is a new
# train/serve skew.
#
# Hints: filter to prior rows once, outside the loop. groupby("player_id")
# per stat. pd.to_numeric(..., errors="coerce") parses. .map() puts the
# per-player averages onto the field.
#
# Done when: python3 scripts/features/test_serving_form.py → all pass,
# including the parity tests against the real training table.

def recent_par_scoring_field_pct(form_stats: pd.DataFrame, field_ids: list[str],
                                 before_tid: str) -> pd.DataFrame:
    raise NotImplementedError("Jack: recent_par_scoring_field_pct")
