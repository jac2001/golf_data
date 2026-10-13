"""
Euro (DPWT) training table — one row per player-event, 2017–2026.
=================================================================
Sources (local DuckDB, pulled 2026-09-22 by fetch_euro_history.py):
  euro_rounds  147,320 player-rounds (score, par, birdies/bogies/etc,
               sg_total 100% covered, fin_text)
  euro_odds    30,233 rows of bet365 win odds (open/close, outcomes)

Plumbing (done): targets from fin_text, per-event devigged market
prior from closing odds, chronological assembly with a HARD leakage
wall — a row's features may only see rounds strictly BEFORE its
event's date (Lesson 3: time only moves forward).

The interesting part (TODO Jack): rolling_form_features() — what a
player's recent rounds say about them. The plumbing hands you ONLY
legal history; everything you compute from it is leak-free by
construction.

Usage:
    python3 scripts/features/build_euro_training_table.py
Output:
    data/processed/euro_training_2017_2026.csv
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "golf_data.db"
OUT = PROJECT_ROOT / "data" / "processed" / "euro_training_2017_2026.csv"


# The furthest back any feature may look, in days before the event.
# Serving (predict_euro.py) only fetches HISTORY_DAYS of rounds and
# asserts HISTORY_DAYS >= this, so a feature that stays inside the
# window computes the same value in training and in production.
FEATURE_WINDOW_DAYS = 400


def parse_finish(fin: str) -> float:
    """'1' → 1, 'T5' → 5, 'CUT'/'WD'/'DQ'/'' → NaN (did not finish)."""
    s = str(fin).strip().upper().lstrip("T")
    try:
        return float(int(s))
    except ValueError:
        return np.nan


# ── TODO(Jack): the feature functions ────────────────────────────────────────
# prior_rounds: this player's rounds BEFORE the event, ascending by date,
# columns: date, event_id, sg_total, score, course_par, birdies, bogies,
# doubles_or_worse, pars, eagles_or_better, fin_text, round_num.
# Return a flat dict of numbers; None/NaN is fine when history is thin —
# the trainer will see it as missing rather than fake-zero (Lesson 2:
# what "missing" means is a per-feature decision you're making here).
#
# Suggested first set (mirror the PGA model's strongest family):
#   sg_last5 / sg_last20      — mean sg_total of last N rounds
#   sg_trend                  — last5 mean minus last20 mean
#   score_vs_par_last10       — mean (score - course_par)
#   birdie_rate_last10        — birdies per round
#   bogey_avoid_last10        — (bogies + doubles_or_worse) per round
#   rounds_played_365d        — activity/rust signal
# Watch: sample sizes (a 3-round history "mean" is noise — consider
# returning the count too, so the model can learn to distrust it).

# ── Window-bounded features (Oct 13 stats review) ───────────────────────────
# Training used to hand this function a player's whole career while
# serving fetched ~420 days, so prior_rounds_count was 648 in training
# and 82 live for the same player. Now every feature looks only inside
# FEATURE_WINDOW_DAYS, so the function can't tell training from serving.
# test_euro_features.py pins that: full career == serving slice.
# Decisions (Jack): average whatever rounds the window holds, and
# events_in_window (distinct dates; serving rows have no event_id)
# tells the model how far to trust those averages.

def rolling_form_features(prior_rounds: pd.DataFrame, event_date: pd.Timestamp) -> dict:
    # 1. The window: keep only rounds the serving side can also see.
    #    Use >= and FEATURE_WINDOW_DAYS, exactly like the tests cut.
    window_start = event_date - pd.Timedelta(days=FEATURE_WINDOW_DAYS)
    recent = prior_rounds[(prior_rounds["date"] >= window_start) & (prior_rounds["date"] < event_date)]

    # Newest first; round_num breaks ties inside an event (same date).
    recent = recent.sort_values(["date", "round_num"], ascending=False)


    # Averaging of what's there at least gives us a signal; of the sg. Yes, it is a smaller sample but it is a more recent sample. The model can learn to trust it less if the sample is small.
    sg5 = recent["sg_total"].head(5).mean()
    sg20 = recent["sg_total"].head(20).mean()

    return {
        # 3. Distinct events in the window. Not event_id: serving rows
        #    don't have it. One event per player per date, so count dates.
        "events_in_window": int(recent["date"].nunique()),
        "sg_last5": sg5,
        "sg_last20": sg20,
        "sg_trend": sg5 - sg20,
        "score_vs_par_last10": (recent["score"] - recent["course_par"]).head(10).mean(),
        "birdie_rate_last10": recent["birdies"].head(10).mean(),
        "bogey_rate_last10": (recent["bogies"] + recent["doubles_or_worse"]).head(10).mean(),
        "rounds_played_365d": int((recent["date"] >= event_date - pd.Timedelta(days=365)).sum()),
    }


# ── Plumbing ─────────────────────────────────────────────────────────────────

def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rounds = con.execute("""
        SELECT event_id, calendar_year, event_name, date, dg_id, player_name,
               fin_text, round_num, score, course_par, sg_total,
               birdies, bogies, doubles_or_worse, pars, eagles_or_better
        FROM euro_rounds ORDER BY date, event_id
    """).fetchdf()
    odds = con.execute("""
        SELECT event_id, calendar_year, dg_id, close_odds, open_odds
        FROM euro_odds WHERE market = 'win'
    """).fetchdf()
    con.close()

    rounds["date"] = pd.to_datetime(rounds["date"])

    # Market prior: per event, implied = 1/decimal, devigged so the
    # field sums to 1 (Lesson 4 of the ML sheet, euro edition).
    odds["implied"] = 1.0 / pd.to_numeric(odds["close_odds"], errors="coerce")
    odds["implied_open"] = 1.0 / pd.to_numeric(odds["open_odds"], errors="coerce")
    odds = odds.dropna(subset=["implied"])
    key = ["event_id", "calendar_year"]
    odds["market_prob"] = odds["implied"] / odds.groupby(key)["implied"].transform("sum")
    odds["odds_move"] = odds["implied"] - odds["implied_open"]
    market = odds.set_index(key + ["dg_id"])[["market_prob", "odds_move"]]

    # One row per player-event with targets.
    ev = (rounds.groupby(key + ["dg_id", "player_name", "event_name"], as_index=False)
          .agg(event_date=("date", "min"), fin_text=("fin_text", "first"),
               rounds_played=("round_num", "count")))
    ev["finish"] = ev["fin_text"].map(parse_finish)
    ev["made_cut"] = (ev["rounds_played"] >= 3).astype(int)  # euro cut after R2
    for name, k in [("won", 1), ("top5", 5), ("top10", 10), ("top20", 20)]:
        ev[name] = (ev["finish"] <= k).fillna(False).astype(int)

    # Per-player chronology → leak-free feature assembly.
    rounds_by_player = {pid: g.sort_values("date").reset_index(drop=True)
                        for pid, g in rounds.groupby("dg_id")}

    rows = []
    for _, r in ev.iterrows():
        history = rounds_by_player.get(r["dg_id"])
        prior = history[history["date"] < r["event_date"]] if history is not None else rounds.iloc[0:0]
        row = {
            "event_id": r["event_id"], "calendar_year": r["calendar_year"],
            "event_name": r["event_name"], "event_date": r["event_date"],
            "dg_id": r["dg_id"], "player_name": r["player_name"],
            "won": r["won"], "top5": r["top5"], "top10": r["top10"],
            "top20": r["top20"], "made_cut": r["made_cut"],
        }
        row.update(rolling_form_features(prior, r["event_date"]))
        mk = market.index.isin([(r["event_id"], r["calendar_year"], r["dg_id"])])
        if mk.any():
            m = market[mk].iloc[0]
            row["market_prob"] = m["market_prob"]
            row["odds_move"] = m["odds_move"]
        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["event_date", "event_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"{len(df)} player-event rows, {df['event_id'].nunique()} events, "
          f"{df['calendar_year'].min()}–{df['calendar_year'].max()}")
    print(f"targets — won: {df['won'].sum()}, cut rate: {df['made_cut'].mean():.2%}, "
          f"market coverage: {df['market_prob'].notna().mean():.1%}")
    print(f"-> {OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
