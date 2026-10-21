"""
season_resolver.py — which PGA TOUR season is active today?
============================================================
config.SEASON used to be "the newest schedule_*.csv filename", so the day
someone added schedule_2027.csv (October 2026) the whole pipeline thought
it was 2027: no 2027 tracker, no 2027 leaderboard, blank lookups
(audit finding 3). A future schedule must not change today's season.

active_season() decides from the calendar and the schedules' event dates.
config.py feeds it the PGA schedule files (schedule_YYYY.csv; the Euro
schedules have their own seasons and are left out).
"""

from __future__ import annotations
from datetime import timedelta
from datetime import date


# ── TODO(Jack): active_season ─────────────────────────────────────────────────
#
# today:      the date to resolve for
# schedules:  season -> list of (start_date, end_date) for its events, in any
#             order, e.g. {2026: [(date(2026, 2, 5), date(2026, 2, 8)), ...],
#                          2027: [(date(2027, 1, 21), date(2027, 1, 24)), ...]}
#
# Return the season that's active on `today`.
#
# Facts the tests pin:
#   - During a season (between its first event and its last), that season.
#   - After a season's last event and before the next one begins, it's
#     still the season that just ended (results, standings, settlement).
#   - A season becomes active LEAD_DAYS before its first event starts, so
#     the opener's Tuesday prediction run (two days before round 1) already
#     uses the new season.
#   - A schedule for a later season (2027, 2028) changes nothing in 2026.
#   - Before every known season, the earliest one.
#   - No schedules at all: today's calendar year.
#   - A season with no events is ignored.
#
# Decision that's yours (reason in a comment):
#   LEAD_DAYS: how many days before its opener should a season take over?
#   It must be at least 2 (the opener's Tuesday run). Too long and the new
#   season takes over while the last one's results are still settling.
#
# Done when: python3 scripts/test_season_resolver.py passes, plus one test of
# your own that pins your LEAD_DAYS (the day before the window opens and the
# day it opens).

# A week is an acceptable gap give that there is a golf tournament usually each 
LEAD_DAYS = 7


def active_season(today: date, schedules: dict[int, list[tuple[date, date]]]) -> int:
    openers = {}
    for season, events in schedules.items():
        if events:
            openers[season] = min(start for start, end in events)
    
    if not openers:
        return today.year 
    
    started = [season for season, opener in openers.items() if today >= opener - timedelta(days=LEAD_DAYS)]
    
    if started:
        return max(started)
    return min(openers)

    
    


