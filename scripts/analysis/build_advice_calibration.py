"""
Build the dataset for calibrating the advice constants
(scripts/predictions/advice_values.py: PLAY_RATE, DECAY_PER_WEEK).

One row per (golfer, event A, later event B):
  - A is an event with a Tuesday prediction archive (the "now" week)
  - B is any later 2026 PGA event within the advice horizon (15 events)
    that has results

Columns
  player, tid_a, tid_b, name_b, type_b, restricted_b, weeks_apart,
  world_rank          at A
  ev_now              expected prize money at A (calibrated probs × A's purse)
  ev_extrap           what advice_values would predict at B BEFORE the two
                      constants: ev_now × purse ratio × field-strength ratio
  played_b            did he tee it up at B (in B's results)
  ev_b_model          the model's own Tuesday EV for him at B (if B has an
                      archive and he was in it) — the "truth" for decay
  earnings_b          what he actually earned at B (0 if missed cut / didn't play)

Output: data/analysis/advice_calibration_pairs.csv
Run:    python3 scripts/analysis/build_advice_calibration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "predictions"))
from advice_values import (  # noqa: E402
    ELITE_RANK, HORIZON, K_ELITE, K_REST, _is_restricted, _strength,
)
from season_strategy import _name_key, _parse_purse, _player_expected_prize  # noqa: E402

PRED_DIR = ROOT / "data" / "prediction_tracking"
OUT = ROOT / "data" / "analysis" / "advice_calibration_pairs.csv"
PROB_COLS = {  # archive column → probs key (calibrated where available)
    "win_prob": "win_prob", "top5_prob": "top5_prob", "top10_prob": "top10_prob",
    "top20_prob": "top20_prob", "cut_prob": "cut_prob",
}


def _ev_table(tid: str, purse: float) -> dict[str, tuple[float, float | None]]:
    """name_key → (expected prize money, world_rank) from one Tuesday archive."""
    path = PRED_DIR / f"pred_{tid}.csv"
    if not path.exists() or purse <= 0:
        return {}
    df = pd.read_csv(path)
    out = {}
    for _, r in df.iterrows():
        probs = {k: float(r.get(c) or 0) for c, k in PROB_COLS.items()}
        rank = r.get("world_rank")
        rank = float(rank) if pd.notna(rank) else None
        out[_name_key(str(r["player_name"]))] = (_player_expected_prize(0, purse, 1.0, probs=probs), rank)
    return out


def main() -> None:
    sched = pd.read_csv(ROOT / "data" / "raw" / "schedule_2026.csv")
    sched["purse_num"] = sched["purse"].apply(_parse_purse)
    sched = sched.sort_values("start_date").reset_index(drop=True)

    lb = pd.read_csv(ROOT / "data" / "historical" / "leaderboards_2026.csv")
    lb["key"] = lb["player_name"].map(lambda n: _name_key(str(n)))
    lb["earn"] = lb["earnings"].map(_parse_purse).fillna(0.0)   # missed cut → no money
    results = {tid: dict(zip(g["key"], g["earn"])) for tid, g in lb.groupby("tournament_id")}

    ev_cache: dict[str, dict] = {}
    def evs(tid: str, purse: float) -> dict:
        if tid not in ev_cache:
            ev_cache[tid] = _ev_table(tid, purse)
        return ev_cache[tid]

    rows = []
    for i, a in sched.iterrows():
        table_a = evs(a["tournament_id"], a["purse_num"])
        if not table_a:
            continue
        later = sched.iloc[i + 1: i + 1 + HORIZON]
        start_a = pd.to_datetime(a["start_date"])
        s_a = _strength(a["tournament_type"])
        for _, b in later.iterrows():
            res_b = results.get(b["tournament_id"])
            if res_b is None or b["purse_num"] <= 0:
                continue
            weeks = (pd.to_datetime(b["start_date"]) - start_a).days / 7
            s_b = _strength(b["tournament_type"])
            table_b = evs(b["tournament_id"], b["purse_num"])
            for key, (ev_now, rank) in table_a.items():
                k = K_ELITE if (rank is not None and rank <= ELITE_RANK) else K_REST
                ev_extrap = ev_now * (b["purse_num"] / a["purse_num"]) * (s_a / s_b) ** k
                rows.append({
                    "player": key, "tid_a": a["tournament_id"], "tid_b": b["tournament_id"],
                    "name_b": b["tournament_name"], "type_b": b["tournament_type"],
                    "restricted_b": _is_restricted(b["tournament_type"], b["purse_num"]),
                    "weeks_apart": round(weeks, 1), "world_rank": rank,
                    "ev_now": round(ev_now), "ev_extrap": round(ev_extrap),
                    "played_b": key in res_b,
                    "ev_b_model": round(table_b[key][0]) if key in table_b else None,
                    "earnings_b": round(res_b.get(key, 0.0)),
                })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"{len(df):,} pairs · {df['tid_a'].nunique()} 'now' weeks · {df['tid_b'].nunique()} later events → {OUT.relative_to(ROOT)}")
    print(f"played_b rate overall: {df['played_b'].mean():.2f} · "
          f"rows with a model EV at B: {df['ev_b_model'].notna().sum():,}")


if __name__ == "__main__":
    main()
