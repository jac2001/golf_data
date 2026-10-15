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

In training (merge_all_historical_data.py, the form block and the
field-relative block) they are:
  1. per player, per stat: that player's form_stats rows from events
     played BEFORE this one (by event DATE; until 2026-10-15 training
     compared tournament_id strings, which put later events in "prior";
     see event_dates.py), sorted by date, the last 5 rows (tail(5)),
     stat_value parsed to a number, NaNs dropped, then the mean
                                       → recent_par3_scoring, etc.
  2. within the event's field: rank(ascending=False, pct=True)
     lower scoring is better, so the LOWEST average gets 1.0
                                       → recent_par3_scoring_field_pct
  A player with no prior rows stays NaN in both steps (rank skips NaN).

At serving the model must receive the same numbers, so this module must
reproduce that exactly; test_serving_form.py checks it against values
frozen from the verified date-ordered training table
(fixtures/par_scoring_date_order.csv).
"""

from __future__ import annotations

import glob
from pathlib import Path

import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.features.event_dates import load_events, load_overrides, training_event_date  # noqa: E402

# training's STAT_IDS (merge_all_historical_data.py), as strings
PAR_STATS = {
    "recent_par3_scoring": "299",
    "recent_par4_scoring": "142",
    "recent_par5_scoring": "143",
}
N_EVENTS = 5


def load_form_stats(hist_dir: Path = ROOT / "data" / "historical") -> pd.DataFrame:
    """Every form_stats_{year}.csv (committed, so this works on CI with no
    DuckDB), plus each row's event_date. Rows whose event can't be dated
    are dropped, exactly as training drops them (with_order_key).
    stat_id and player_id as strings: the classic type-mismatch bug class
    in this project."""
    files = sorted(glob.glob(str(hist_dir / "form_stats_20*.csv")))
    df = pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)
    df["stat_id"] = df["stat_id"].astype(str)
    df["player_id"] = df["player_id"].astype(str)
    events, overrides = load_events(), load_overrides()
    names = df.drop_duplicates("tournament_id").set_index("tournament_id")["tournament_name"]
    dates = {t: training_event_date(str(t), str(n), events, overrides) for t, n in names.items()}
    df["event_date"] = df["tournament_id"].map(dates)
    return df[df["event_date"].notna()].reset_index(drop=True)


"""
The field-relative par-scoring features are the only ones that need
the whole field's form_stats rows to compute. The others are per-player
and can be computed in a single pass over the player's prior rounds. The
field-relative features are computed in training by merge_all_historical_data.py
and in serving by recent_par_scoring_field_pct() below. The tests check
that the serving function reproduces the exact numbers in the DATE-ORDERED
training table (frozen in fixtures/par_scoring_date_order.csv from the
verified rebuild of Oct 15; in those events 91-99% of rows differ from
the old id-ordered values).
"""

def recent_par_scoring_field_pct(form_stats: pd.DataFrame, field_ids: list[str],
                                 before_date: pd.Timestamp) -> pd.DataFrame:
    prior = form_stats[form_stats['event_date'] < before_date]
    prior = prior.sort_values(['event_date', 'tournament_id'])
    out = pd.DataFrame({'player_id': field_ids})
    for col, stat_id in PAR_STATS.items():
        s = prior[prior['stat_id'] == stat_id]
        last5 = s.groupby("player_id").tail(N_EVENTS)
        values = pd.to_numeric(last5['stat_value'], errors='coerce')
        avg = values.groupby(last5['player_id']).apply(lambda v: v.mean()) 
        # Per-player Series.mean(), the same summation training's get_recent_stat_avg
        # uses. groupby().mean() adds in a different order and can differ in the last
        # bit, which reorders tied players in the percentile rank (found by the parity
        # test, Oct 15).
        out[col] = out['player_id'].map(avg)
        out[f"{col}_field_pct"] = out[col].rank(ascending=False, pct=True)
    return out
  
  
