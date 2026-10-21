"""Tests for season_resolver.active_season — written before the code.
Run: python3 scripts/test_season_resolver.py"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_resolver import active_season  # noqa: E402

D = date
S2026 = [(D(2026, 2, 5), D(2026, 2, 8)), (D(2026, 10, 22), D(2026, 10, 25)), (D(2026, 12, 3), D(2026, 12, 6))]
S2027 = [(D(2027, 1, 21), D(2027, 1, 24)), (D(2027, 12, 2), D(2027, 12, 5))]
S2028 = [(D(2028, 1, 20), D(2028, 1, 23))]
BOTH = {2026: S2026, 2027: S2027}


def test_today_mid_season_with_a_future_schedule_present():
    # The Oct 20, 2026 bug: schedule_2027.csv exists, it's still 2026.
    assert active_season(D(2026, 10, 20), BOTH) == 2026
    assert active_season(D(2026, 10, 20), {**BOTH, 2028: S2028}) == 2026


def test_offseason_stays_with_the_season_that_just_ended():
    assert active_season(D(2026, 12, 20), BOTH) == 2026
    assert active_season(D(2027, 1, 5), BOTH) == 2026


def test_opener_tuesday_is_already_the_new_season():
    # Tuesday Jan 19, 2027: predictions for the Jan 21 opener.
    assert active_season(D(2027, 1, 19), BOTH) == 2027


def test_once_the_new_season_starts():
    assert active_season(D(2027, 1, 21), BOTH) == 2027
    assert active_season(D(2027, 6, 1), BOTH) == 2027


def test_order_of_events_and_seasons_does_not_matter():
    shuffled = {2027: list(reversed(S2027)), 2026: list(reversed(S2026))}
    assert active_season(D(2026, 10, 20), shuffled) == 2026
    assert active_season(D(2027, 1, 19), shuffled) == 2027


def test_before_every_known_season_is_the_earliest():
    assert active_season(D(2025, 6, 1), BOTH) == 2026


def test_no_schedules_falls_back_to_the_calendar_year():
    assert active_season(D(2031, 3, 1), {}) == 2031


def test_a_season_with_no_events_is_ignored():
    assert active_season(D(2026, 10, 20), {**BOTH, 2027: []}) == 2026
    assert active_season(D(2027, 6, 1), {2026: S2026, 2027: []}) == 2026


# TODO(Jack): one test pinning your LEAD_DAYS (the day before the window
# opens is still 2026; the day it opens is 2027).

def test_lead_days_window():
    assert active_season(D(2027, 1,13), BOTH) == 2026
    assert active_season(D(2027, 1,14), BOTH) == 2027

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except (AssertionError, NotImplementedError) as e:
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
