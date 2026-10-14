"""
event_dates.py — the real start date of every PGA TOUR event in training.
==========================================================================
Training orders a player's "prior" events by tournament_id string, but
ids are not in calendar order (~25% of 2024-26 event pairs), so form
features include later events. The fix is to order by DATE, which needs
every training event's date. This module provides it.

Source: data/raw/dg_pga_event_list.csv (DataGolf's historical-raw-data
event list, PGA rows 2014+; committed so this works offline and on CI).

The catch is SEASON vs CALENDAR year. Our ids use the PGA TOUR season:
R{season}{event_id:03d}. DataGolf uses the calendar year. Until 2024 a
season began in the fall of the PREVIOUS calendar year:

    R2016464  Frys.com Open      played 2015-10-18   (DG calendar 2015)
    R2022464  Fortinet Champ.    played 2021-09-19   (DG calendar 2021)
    R2023464  Fortinet Champ.    played 2022-09-18   (DG calendar 2022)

so matching id + same calendar year silently gives a date a YEAR off for
every fall event. And there's no fixed month boundary: the 2020 TOUR
Championship (Sept 7, 2020) is season 2020, the Sept 20, 2020 U.S. Open
is season 2021. What ends a season is its TOUR Championship (event 60).
2023 was the TRANSITION season: it began in fall 2022 and also took in
the fall 2023 events (R2023543 Fortinet, Sept 2023 — DG lists the same
id as "Fortinet Championship #2"), then 2024 started calendar seasons
(the FedEx Fall events, e.g. R2024464 on 2024-09-15, belong to the
season they're played in). Two Fortinets in one season, a year apart:
R2023464 = Sept 2022 (Max Homa), R2023543 = Sept 2023 (Sahith Theegala).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = ROOT / "data" / "raw" / "dg_pga_event_list.csv"
TOUR_CHAMPIONSHIP = 60
CALENDAR_SEASONS_FROM = 2024


def load_events(path: Path = EVENTS_PATH) -> pd.DataFrame:
    """columns: calendar_year, event_id (int), date (Timestamp), event_name."""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["event_id"] = df["event_id"].astype(int)
    return df


# ── TODO(Jack): event_date ───────────────────────────────────────────────────
# tid:        our id, e.g. "R2021026"   → season 2021, event_id 26
# our_name:   the training table's tournament_name for it (a tiebreaker)
# events:     load_events()'s output
#
# Return the event's start date as a pd.Timestamp, or None when you can't
# be sure (the caller decides what None means; don't guess a date).
#
# Suggested shape:
#   1. season window: the date range season `season` covers.
#        season >= CALENDAR_SEASONS_FROM: Jan 1 .. Dec 31 of that year.
#        earlier: (TOUR Championship date of season-1, TOUR Championship
#                  date of season]  ← the day AFTER last season's finale
#                  through this season's finale, inclusive.
#        2023 (transition): starts the same way, but ENDS Dec 31, 2023.
#      The TOUR Championship for season S is the event_id 60 row in
#      calendar year S (it's always played in its own season's year).
#   2. candidates: rows with this event_id whose date is in the window.
#   3. exactly one → its date.
#
# Decisions that are yours (reason in a comment):
#   a. Zero candidates: e.g. R2016018 (Zurich Classic) isn't in DG's list
#      under that id. Try a NAME match inside the window (your
#      whole-word idea from resolve_event), or return None?
#   b. Two candidates in one window: R2021's window holds two U.S. Opens
#      (Sept 2020, id 26; June 2021, DG id 535 "U.S. Open #2"). By id
#      they're separate, but what if a season held the same id twice?
#      Pick by name, or None?
#
# Done when: python3 scripts/features/test_event_dates.py → all pass.

def event_date(tid: str, our_name: str, events: pd.DataFrame) -> pd.Timestamp | None:
    raise NotImplementedError("Jack: event_date")
