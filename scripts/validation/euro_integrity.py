"""
euro_integrity.py — refuse to publish DP World Tour predictions built on broken inputs.
======================================================================================
The PGA gate (prediction_integrity.py) checks that DataGolf's per-event
files belong to this event. The euro model has a different weak point:
it builds every player's form from ~55 archived events fetched one by
one, and a failed fetch used to print a warning while every player's
history silently thinned.

predict_euro.py calls check() right before writing. Any failure: nothing
is written, the site keeps the last good board, the Actions run shows an
::error:: annotation, and the watchdog re-dispatches if the event has no
board at all.

Thresholds come from a walk-forward backtest over 208 clean events,
2021–2026 (Oct 13):
                                  min    p1    p5   p10  median
  model top 10 with history      100%  100%  100%  100%   100%
  field share with history        29%   62%   80%   87%    96%
  rank corr, model vs market     0.28  0.44  0.49  0.52   0.66
The first never fails on a clean week, so it can block. The other two
dip low on legitimate weeks (co-sanctioned events full of non-euro
players; weeks the market disagrees with form), so as hard blocks they
would cry wolf. They are printed as notes for a human to read.

`out` columns used: player_name, win_prob, season_sg_total (= sg_last20,
NaN when a player has no rounds in the window), vegas_prob (absent when
the odds merge was skipped).
`history` keys: events_expected, events_fetched, events_failed (names),
newest_round (Timestamp or None), last_finished_event_end (Timestamp or
None: the most recent euro event in the schedule that ended 2+ days ago).
"""

from __future__ import annotations


import pandas as pd


TOP_N = 10
# Notes only (see the table above) — printed, never blocking.
NOTE_COVERAGE = 0.80          # p5 of clean events
NOTE_MARKET_AGREEMENT = 0.49  # p5 of clean events; pre-event only


def check(out: pd.DataFrame, history: dict, pre_event: bool) -> tuple[list[str], list[str]]:
    """Return (failures, notes) for one euro predictions board."""
    failures: list[str] = []
    notes: list[str] = []
    if out.empty or "win_prob" not in out.columns:
        return ["predictions table is empty or has no win_prob"], notes

    # Blocking: no history at all; a top-10 player without history (never
    # happens on a clean week); any failed history fetch; last week's event
    # not yet in DataGolf's archive. Notes: thin field coverage, and
    # pre-event model/market disagreement — both dip low on clean weeks.
    top = out.sort_values("win_prob", ascending=False).head(TOP_N)
    if history["events_fetched"] == 0:
        failures.append("no history fetched at all") 
    if top["season_sg_total"].isna().any():
        missing = top[top["season_sg_total"].isna()]["player_name"].tolist()
        failures.append(f"top {TOP_N} have missing history: {', '.join(missing)}")
    
    coverage = out["season_sg_total"].notna().mean()
    if coverage < NOTE_COVERAGE:
        notes.append(f"only {coverage:.0%} of the field has rounds in the window (clean weeks: "
                     f"≥{NOTE_COVERAGE:.0%} 95% of the time) — normal for co-sanctioned events")
        
        
    if pre_event and "vegas_prob" in out.columns:
        if len(out) > 0 and out["vegas_prob"].notna().sum() / len(out) >= 0.8:
            spearman_corr = out["win_prob"].rank().corr(out["vegas_prob"].rank())
            if spearman_corr < NOTE_MARKET_AGREEMENT:
                notes.append(f"model and market disagree more than usual (rank correlation {spearman_corr:.2f}, clean weeks are ≥{NOTE_MARKET_AGREEMENT:.2f} 95% of the time) — worth a look, not blocked")
    
    if history['newest_round'] is not None and history['last_finished_event_end'] is not None:
        if history['newest_round'] < history['last_finished_event_end']:
            failures.append(f"history is stale: newest round {history['newest_round'].date()}, but an event "
                            f"finished {history['last_finished_event_end'].date()} — DataGolf hasn't posted it yet; "
                            "the next run retries")
    
    if history["events_failed"]:
        # I want to block on any failed event, because the model is trained on full history and a missing event thins the history for all players who played it. 
        failures.append(f"history fetch failed for {', '.join(history['events_failed'])} — players who played there would be scored without that week")
        
 
    return failures, notes
