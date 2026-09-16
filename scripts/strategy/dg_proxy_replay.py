#!/usr/bin/env python3
"""
DG-Proxy Replay — 4-season robustness check for the rolling design
==================================================================
The 2026 ladder showed live-model Tuesdays beat a static preseason plan
by +34%. One season could be luck. Here we replay 2022-2025 using
DataGolf's archived pre-tournament probabilities as the "live model"
(the only point-in-time model we have for those years), on the DG-covered
events only (11-14 per season).

Per season: static plan vs rolling replay vs hindsight ceiling, all on
identical weeks, scored by actual (imputed) earnings. The claim being
tested is only the LIFT: replay > static, season after season.

Usage:
    python3 scripts/strategy/dg_proxy_replay.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "strategy"))
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_preseason_projection import load_leaderboards, WINNER_SHARE  # noqa: E402
from season_optimizer import solve_season, USES_PER_PLAYER  # noqa: E402
from scripts.predictions.prize_distributions import STANDARD_DISTRIBUTION  # noqa: E402

DG_ARCHIVE = PROJECT_ROOT / "data" / "datagolf" / "dg_archive_all.csv"

# Purse share per finish band, from the standard distribution
_S = STANDARD_DISTRIBUTION
SHARE_2_5 = sum(_S[p] for p in range(2, 6)) / 4
SHARE_6_10 = sum(_S[p] for p in range(6, 11)) / 5
SHARE_11_20 = sum(_S[p] for p in range(11, 21)) / 10


def dg_ev(row: pd.Series, purse: float) -> float:
    """DG probabilities -> expected earnings via the prize curve."""
    p_win, p5, p10, p20 = row["dg_win"], row["dg_top5"], row["dg_top10"], row["dg_top20"]
    return purse * (p_win * _S[1]
                    + max(p5 - p_win, 0) * SHARE_2_5
                    + max(p10 - p5, 0) * SHARE_6_10
                    + max(p20 - p10, 0) * SHARE_11_20
                    + max(row.get("dg_make_cut", p20) - p20, 0) * 0.005)


# Season-parameterized projection (the backtest versions hardcode 2026)
def proj_ev(train: pd.DataFrame, pid: str, event: str, overall: float,
            target_year: int) -> float:
    p_rows = train[train["player_id"] == pid]
    recent = p_rows[p_rows["year"] >= target_year - 4]
    if recent[recent["year"] >= target_year - 2].empty:
        return 0.0
    played = recent[recent["event"] == event]["year"].nunique()
    p_field = (played + 1) / 6
    if p_field < 0.30:
        return 0.0
    at_event = p_rows[(p_rows["event"] == event) & (p_rows["year"] >= target_year - 8)]
    n = len(at_event)
    e_earn = overall if n == 0 else (n * at_event["earn"].mean() + 3 * overall) / (n + 3)
    return p_field * e_earn


def season_ladder(year: int, lb: pd.DataFrame, dg: pd.DataFrame) -> dict:
    train = lb[lb["year"] < year]
    actual = lb[lb["year"] == year]
    overall = (train[train["year"] >= year - 4]
               .groupby("player_id")["earn"].mean().to_dict())

    dgy = dg[dg["year"] == year].copy()
    dgy["event"] = dgy["event_id"].apply(lambda e: f"{int(e):03d}")
    weeks = sorted(dgy["event"].unique())

    # Purse per event from that season's winner earnings
    purse = {}
    for ev in weeks:
        w = actual[(actual["event"] == ev) & (actual["earn"] > 0)]
        purse[ev] = float(w["earn"].max()) / WINNER_SHARE if len(w) else 8_000_000

    # Projection grid over DG weeks (static plan + replay future weeks)
    pids = train[train["year"].isin([year - 1, year - 2])]["player_id"].unique()
    proj_rows = [{"player_id": pid, "event": ev,
                  "projected_ev": proj_ev(train, pid, ev, overall.get(pid, 0.0), year)}
                 for pid in pids for ev in weeks]
    grid = pd.DataFrame(proj_rows)
    grid = grid[grid["projected_ev"] > 0]

    def score(chosen: pd.DataFrame) -> float:
        m = chosen.merge(actual[["player_id", "event", "earn"]],
                         on=["player_id", "event"], how="left")
        return float(m["earn"].fillna(0).sum())

    static = score(solve_season(grid))

    # Rolling replay: DG EV for current week (its actual archive field),
    # projection for the future, lock and advance
    uses_left: dict = {}
    locked = []
    # DG ids differ from ours — match by name key into that week's actual field
    def _key(n): return " ".join(sorted(str(n).lower().replace(",", " ").split()))
    for k, ev in enumerate(weeks):
        wk_dg = dgy[dgy["event"] == ev].copy()
        fld = actual[actual["event"] == ev].copy()
        fld["_k"] = fld["player_name"].apply(_key)
        wk_dg["_k"] = wk_dg["player_name"].apply(_key)
        cur = wk_dg.merge(fld[["_k", "player_id"]], on="_k", how="inner")
        cur = pd.DataFrame({
            "player_id": cur["player_id"],
            "event": ev,
            "projected_ev": cur.apply(lambda r: dg_ev(r, purse[ev]), axis=1),
        })
        fut = grid[grid["event"].isin(weeks[k + 1:])]
        ev_frame = pd.concat([cur, fut], ignore_index=True)
        ev_frame = ev_frame[ev_frame["projected_ev"] > 0]
        chosen = solve_season(ev_frame, uses_left=uses_left)
        picks = chosen[chosen["event"] == ev]
        for pid in picks["player_id"]:
            uses_left[pid] = uses_left.get(pid, USES_PER_PLAYER) - 1
        locked.append(picks)
    replay = score(pd.concat(locked, ignore_index=True))

    hind = actual[actual["event"].isin(weeks)].rename(
        columns={"earn": "projected_ev"})[["player_id", "event", "projected_ev"]]
    ceiling = float(solve_season(hind)["projected_ev"].sum())

    return {"year": year, "weeks": len(weeks), "static": static,
            "replay": replay, "ceiling": ceiling,
            "lift_pct": (replay - static) / static * 100 if static else float("nan")}


def main():
    lb = load_leaderboards()
    dg = pd.read_csv(DG_ARCHIVE)
    print(f"\n{'='*66}")
    print("  DG-PROXY ROBUSTNESS — replay vs static, per season (DG weeks)")
    print(f"{'='*66}")
    print(f"  {'year':<6}{'weeks':>6}{'static':>14}{'replay':>14}{'ceiling':>14}{'lift':>8}")
    for year in (2022, 2023, 2024, 2025):
        r = season_ladder(year, lb, dg)
        print(f"  {r['year']:<6}{r['weeks']:>6}"
              f"{r['static']:>14,.0f}{r['replay']:>14,.0f}"
              f"{r['ceiling']:>14,.0f}{r['lift_pct']:>7.0f}%")


if __name__ == "__main__":
    main()
