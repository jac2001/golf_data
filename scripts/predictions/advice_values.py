"""
advice_values.py — what every golfer in this week's field is worth now,
and at each upcoming event on the same tour.

Feeds /api/advice/values → web/lib/advice.ts (golferVerdict decides
spend / save per member). The table is the same for every member, so the
API caches it per event.

Why anchor on this week's calibrated probabilities
---------------------------------------------------
season_strategy.py prices FUTURE events with a rank proxy
(win ≈ 0.6/√rank, capped at 18%) that gives a world #25 ~12% to win
anywhere, while the calibrated model gives him ~2% this week. Comparing a
calibrated "now" with a proxy "later" makes everyone look worth saving.
So future EV starts from THIS week's expected prize money and adjusts:

    ev_future = ev_now
              × purse_future / purse_now               bigger pot, same odds
              × (S_now / S_future) ** k                tougher field, lower odds
              × course_mult_future / course_mult_now   venue fit (PGA)
              × qual_mult                              likely not in a restricted field

S = field-strength index by event type. k = 0.6 for the world top 10
(elite odds hold up better against strong fields) and 1.0 otherwise.
Both are v1 judgment calls, documented so they can be calibrated
against settled results later.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from season_strategy import (
    COURSE_FIT_MAX, COURSE_FIT_MIN, COURSE_FIT_SCALE,
    _load_course_fit, _load_historical_fields, _name_key,
    _normalize_tournament_name, _parse_purse, _player_expected_prize,
)

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# Field-strength index: how hard it is to finish high, relative to a major.
FIELD_STRENGTH = {
    "major": 1.00, "playoff": 0.95, "signature": 0.90,
    "standard": 0.55, "team": 0.50, "opposite": 0.30,
}
ELITE_RANK = 10
K_ELITE, K_REST = 0.6, 1.0
NOT_QUALIFIED_MULT = 0.15   # premium event, not in last year's field
QUALIFY_RANK = 60           # restricted event with no history (new event): world top 60 assumed in
HORIZON = 15


def _strength(event_type: str) -> float:
    t = str(event_type).lower()
    return next((v for k, v in FIELD_STRENGTH.items() if k in t), FIELD_STRENGTH["standard"])


def _is_restricted(event_type: str, purse: float) -> bool:
    t = str(event_type).lower()
    return any(k in t for k in ("major", "playoff", "signature")) or purse >= 18_000_000


@lru_cache(maxsize=2)
def _schedule(tour: str) -> pd.DataFrame:
    """Every season file for one tour, one row per event, sorted by date."""
    pattern = "schedule_euro_2*.csv" if tour == "euro" else "schedule_2*.csv"
    frames = []
    for path in sorted(RAW_DIR.glob(pattern)):
        try:
            frames.append(pd.read_csv(path))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=["tournament_id", "tournament_name", "start_date", "purse", "tournament_type"])
    df = pd.concat(frames, ignore_index=True).drop_duplicates("tournament_id")
    if "tournament_type" not in df.columns:
        df["tournament_type"] = "standard"
    df["tournament_type"] = df["tournament_type"].fillna("standard")
    df["purse_num"] = df["purse"].apply(_parse_purse)
    return df.sort_values("start_date").reset_index(drop=True)


@lru_cache(maxsize=1)
def _pga_lookups():
    """Course fit + last year's fields — loaded once per process (8 MB CSVs)."""
    sched = _schedule("pga")
    tid_to_course, fit_map, _ = _load_course_fit(sched)
    return tid_to_course, fit_map, _load_historical_fields()


def _course_mult(key: str, tid: str, tid_to_course: dict, fit_map: dict) -> float:
    ck = tid_to_course.get(tid, "")
    sg = fit_map.get((key, ck), 0.0) if ck else 0.0
    return max(COURSE_FIT_MIN, min(COURSE_FIT_MAX, 1.0 + COURSE_FIT_SCALE * sg))


def golfer_values(tournament_id: str, players: list[dict], limit: int = 60) -> dict:
    """
    players: this event's predictions — dicts with player_name, world_rank,
             win_prob, top5_prob, top10_prob, top20_prob, cut_prob.
    Returns {tournament_id, tour, event, horizon: [...], golfers: [...]}.
    """
    tid = tournament_id.upper()
    tour = "euro" if tid.startswith("E") else "pga"
    sched = _schedule(tour)
    row = sched[sched["tournament_id"] == tid]
    if row.empty:
        return {"tournament_id": tid, "tour": tour, "error": "event not on the schedule", "golfers": []}
    ev = row.iloc[0]
    purse_now = float(ev["purse_num"]) or 0.0
    s_now = _strength(ev["tournament_type"])

    upcoming = sched[sched["start_date"] > ev["start_date"]].head(HORIZON)
    horizon = [{
        "tid": str(u["tournament_id"]), "name": str(u["tournament_name"]),
        "start_date": str(u["start_date"]), "purse": float(u["purse_num"]),
        "type": str(u["tournament_type"]),
    } for _, u in upcoming.iterrows() if float(u["purse_num"]) > 0]

    if tour == "pga":
        tid_to_course, fit_map, hist_fields = _pga_lookups()
    else:
        tid_to_course, fit_map, hist_fields = {}, {}, {}

    out = []
    for p in players:
        name = str(p.get("player_name", "")).strip()
        if not name or purse_now <= 0:
            continue
        probs = {k: float(p.get(k) or 0) for k in ("win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob")}
        # type_weight=1.0: Let It Ride scores real prize money, no event weighting.
        now_ev = _player_expected_prize(0, purse_now, 1.0, probs=probs)
        rank = p.get("world_rank")
        k = K_ELITE if (rank is not None and rank <= ELITE_RANK) else K_REST
        key = _name_key(name)
        cm_now = _course_mult(key, tid, tid_to_course, fit_map)

        future = []
        for h in horizon:
            mult = (h["purse"] / purse_now) * (s_now / _strength(h["type"])) ** k
            mult *= _course_mult(key, h["tid"], tid_to_course, fit_map) / cm_now
            if tour == "pga" and _is_restricted(h["type"], h["purse"]):
                field = hist_fields.get(_normalize_tournament_name(h["name"]), set())
                qualified = (key in field) if field else (rank is not None and rank <= QUALIFY_RANK)
                if not qualified:
                    mult *= NOT_QUALIFIED_MULT
            future.append({"tid": h["tid"], "name": h["name"], "start_date": h["start_date"],
                           "purse": h["purse"], "ev": round(now_ev * mult)})
        # No key here: the site keys uses with its own nameKey (keeps accents
        # and punctuation; _name_key strips them), so it derives the key.
        out.append({"player_name": name, "world_rank": rank,
                    "now_ev": round(now_ev), "future": future})

    out.sort(key=lambda g: g["now_ev"], reverse=True)
    return {
        "tournament_id": tid, "tour": tour,
        "event": {"name": str(ev["tournament_name"]), "purse": purse_now, "type": str(ev["tournament_type"])},
        "horizon": horizon, "golfers": out[:limit],
    }
