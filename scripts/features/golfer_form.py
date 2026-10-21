"""
golfer_form.py — the facts behind the pick cards' "why" lines.
==============================================================
web/lib/whyLine.ts (Jack's) turns these into one plain sentence per golfer.
It may only say what's TRUE, so these come from real results, not from
model features:

  - The predictions file's `recent_top10s` is a decay-WEIGHTED score
    (0.64, 1.51...), not a count, so "top-10 in 4 of his last 5" can't be
    read off it.
  - Its `venue_avg_finish` is a filler value (489 for nearly everyone).

So: each golfer's last starts from our PGA leaderboard history, ordered by
the event's real date (event_dates.py; tournament_id order is NOT calendar
order), plus his record at past editions of this event.

Venues: we only know an edition's course for 2026+ (schedule files), so
this counts past editions of the EVENT, named `event_starts` /
`event_cuts`, not "course". Rotating majors move every year and get no
record at all. Some events changed venue under the same id (event 527:
the Zozo at Narashino through 2024, the Baycurrent at Yokohama from
2025), so a line must say "at this event", never "here". And "made the
cut" only means something where there IS a cut: editions with no CUT
rows (playoffs, signature events, the Sentry) don't count at all.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.features.event_dates import load_events, load_overrides, training_event_date

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "data" / "historical"

RECENT_STARTS = 5          # whyLine's "last 5"
COURSE_YEARS = 10          # an event's venue rarely stays put longer than this
FIRST_SEASON = 2016        # older files have no reliable event dates
# Events that move courses every year (event_id = tournament_id[5:]).
ROTATING_EVENTS = {"026", "033", "100"}   # U.S. Open, PGA Championship, The Open
# MDF ("made cut, didn't finish": the TOUR rule through 2019, Pebble Beach later) is NOT a
# missed cut: the player made it. It carries no place, so parse_finish
# returns None and the start is left out rather than called a miss.
MISSED = {"CUT", "MC", "WD", "W/D", "DQ", "RTD"}


def parse_finish(pos) -> int | str | None:
    """'T7' -> 7, '1' -> 1, CUT/WD/DQ -> 'MC' (didn't finish the event), junk -> None."""
    s = str(pos).strip().upper()
    if s in MISSED:
        return "MC"
    s = s.lstrip("T")
    try:
        return int(float(s))
    except ValueError:
        return None


def load_history(hist_dir: Path = HIST) -> pd.DataFrame:
    """PGA leaderboards with player_id (str), tournament_id, finish, and the
    event's real date. Rows whose date or finish can't be resolved are
    dropped rather than guessed."""
    def read(pattern: str, season_at: int) -> list[pd.DataFrame]:
        out = []
        for f in sorted(hist_dir.glob(pattern)):
            try:
                season = int(f.stem.split("_")[season_at])
            except ValueError:
                continue                                # leaderboards_euro_*.csv
            if season < FIRST_SEASON:
                continue
            out.append(pd.read_csv(f, usecols=["tournament_id", "player_id", "position", "tournament_name"],
                                   dtype={"player_id": str, "position": str}))
        return out

    frames = read("leaderboards_20*.csv", 1)
    # DataGolf's history (fetch_dg_historical_results.py) fills events the
    # PGA TOUR files never got (Bermuda, Puerto Rico, the fall swing, ...).
    # It only ADDS events: where both have one, the PGA TOUR rows stand.
    dg = read("leaderboards_dg_20*.csv", 2)
    if dg:
        have = set(pd.concat(frames)["tournament_id"]) if frames else set()
        dg_all = pd.concat(dg)
        frames.append(dg_all[~dg_all["tournament_id"].isin(have)])
    if not frames:
        return pd.DataFrame(columns=["tournament_id", "player_id", "finish", "date", "had_cut"])
    lb = pd.concat(frames, ignore_index=True)
    lb["player_id"] = lb["player_id"].str.replace(r"\.0$", "", regex=True)
    lb["finish"] = lb["position"].map(parse_finish)
    # An edition "had a cut" when anyone in it is listed CUT (WDs alone don't make one).
    had_cut = lb.assign(c=lb["position"].str.strip().str.upper().eq("CUT")).groupby("tournament_id")["c"].any()
    lb["had_cut"] = lb["tournament_id"].map(had_cut).fillna(False).astype(bool)

    ev, ov = load_events(), load_overrides()
    names = lb.drop_duplicates("tournament_id").set_index("tournament_id")["tournament_name"]
    dates = {tid: training_event_date(tid, str(name), ev, ov) for tid, name in names.items()}
    lb["date"] = lb["tournament_id"].map(dates)
    return lb.dropna(subset=["date", "finish"])[["tournament_id", "player_id", "finish", "date", "had_cut"]]


def golfer_facts(history: pd.DataFrame, player_ids: list[str], tournament_id: str,
                 before: pd.Timestamp | None = None) -> dict[str, dict]:
    """player_id -> {recent: [finish...] most recent first (<= RECENT_STARTS),
    event_starts, event_cuts}. Only starts BEFORE `before` (this event's
    date) count, and never this event itself, so a finished event's own
    result can't describe the golfer going into it."""
    tid = tournament_id.strip().upper()
    h = history[history["tournament_id"] != tid]
    if before is not None:
        h = h[h["date"] < before]
    h = h[h["player_id"].isin(set(player_ids))].sort_values("date", ascending=False).reset_index(drop=True)

    event_id = tid[5:]
    same_event = pd.Series(False, index=h.index)
    if event_id not in ROTATING_EVENTS:
        cutoff = (before or pd.Timestamp.now()) - pd.DateOffset(years=COURSE_YEARS)
        same_event = (h["tournament_id"].str[5:] == event_id) & (h["date"] >= cutoff)
        if "had_cut" in h.columns:
            same_event &= h["had_cut"]          # no cut → "made the cut" says nothing

    out: dict[str, dict] = {}
    for pid in player_ids:
        mine = h[h["player_id"] == pid]
        recent = mine["finish"].head(RECENT_STARTS).tolist()
        here = mine[same_event.loc[mine.index]]
        out[pid] = {
            "recent": [f if f == "MC" else int(f) for f in recent],
            "event_starts": int(len(here)),
            "event_cuts": int((here["finish"] != "MC").sum()),
        }
    return out
