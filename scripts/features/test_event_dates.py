"""
Tests for event_dates.event_date — written before the code.
Run:  python3 scripts/features/test_event_dates.py

Every case is a real event, checked against who won it (Oct 14): the
Nov 2020 Masters in our table is Dustin Johnson's, the Sept 2020 U.S.
Open is DeChambeau's.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.features.event_dates import event_date, load_events, load_overrides, training_event_date  # noqa: E402

EV = load_events()
OV = load_overrides()
day = pd.Timestamp


def d(tid, name=""):
    return event_date(tid, name, EV)


# ── the tests ────────────────────────────────────────────────────────────────

def test_fall_event_is_previous_calendar_year():
    """Season 2016 began in Oct 2015."""
    assert d("R2016464", "Frys.com Open") == day("2015-10-18")
    assert d("R2017464", "Safeway Open") == day("2016-10-16")


def test_same_id_same_calendar_year_is_the_wrong_season():
    """DG's calendar-2022 Fortinet (2022-09-18) is season 2023, not 2022.
    Matching id + calendar year gives R2022464 a date a year late."""
    assert d("R2022464", "Fortinet Championship") == day("2021-09-19")
    assert d("R2023464", "Fortinet Championship") == day("2022-09-18")


def test_tour_championship_ends_its_season():
    """Sept 7, 2020 is still season 2020: the finale closes the window."""
    assert d("R2020060", "TOUR Championship") == day("2020-09-07")
    assert d("R2019060", "TOUR Championship") == day("2019-08-25")


def test_covid_season_events_after_the_finale():
    """The Sept 2020 U.S. Open and Nov 2020 Masters belong to season 2021."""
    assert d("R2021026", "U.S. Open (2020)") == day("2020-09-20")
    assert d("R2021014", "Masters Tournament") == day("2020-11-15")


def test_2023_transition_season_runs_to_december():
    """Season 2023 began fall 2022 AND took in fall 2023: two Fortinets a
    year apart, different winners (Homa 2022, Theegala 2023)."""
    assert d("R2023464", "Fortinet Championship") == day("2022-09-18")
    assert d("R2023543", "Fortinet Championship") == day("2023-09-17")
    assert d("R2023549", "The RSM Classic") == day("2023-11-19")


def test_editions_get_distinct_dates():
    """No two training ids in a season may share a date AND a name: that's
    one event's date handed to two editions."""
    tr = pd.read_csv(Path(__file__).resolve().parents[2] / "data" / "processed"
                     / "master_training_data_2016_2026.csv",
                     usecols=["tournament_id", "tournament_name"], low_memory=False
                     ).drop_duplicates("tournament_id")
    seen, clash = {}, []
    for tid, name in tr.itertuples(index=False):
        got = d(tid, name)
        if got is not None:
            key = (got, str(name).lower())
            if key in seen:
                clash.append(f"{seen[key]} and {tid} both -> {got.date()} {name}")
            seen[key] = tid
    assert not clash, clash[:3]


def test_calendar_seasons_from_2024():
    """From 2024 the fall events belong to the year they're played."""
    assert d("R2024464", "Procore Championship") == day("2024-09-15")
    assert d("R2024060", "TOUR Championship") == day("2024-09-01")


def test_normal_mid_season_event():
    assert d("R2025060", "TOUR Championship") == day("2025-08-24")


def test_unknown_event_is_none():
    assert d("R2019999", "Made Up Invitational") is None


def _finale(season: int) -> pd.Timestamp:
    """That season's TOUR Championship (event 60, played in its own year)."""
    r = EV[(EV["event_id"] == 60) & (EV["calendar_year"] == season)]
    return r["date"].iloc[0]


def test_every_resolved_training_date_falls_in_its_season():
    """Run the real training table: every date you return must sit inside
    its season (through 2023: after the previous TOUR Championship, up to
    this season's, with 2023 running to December; 2024+: the calendar
    year), and at most a handful may be None.
    Prints the Nones so you can see what's left."""
    tr = pd.read_csv(Path(__file__).resolve().parents[2] / "data" / "processed"
                     / "master_training_data_2016_2026.csv",
                     usecols=["tournament_id", "tournament_name"], low_memory=False
                     ).drop_duplicates("tournament_id")
    nones, out_of_season = [], []
    for tid, name in tr.itertuples(index=False):
        got = d(tid, name)
        if got is None:
            nones.append(f"{tid} {name}")
            continue
        season = int(tid[1:5])
        if season >= 2024:                      # calendar seasons
            ok = got.year == season
        else:                                   # after last season's finale, up to this one's
            ok = _finale(season - 1) < got <= (pd.Timestamp("2023-12-31") if season == 2023
                                               else _finale(season))
        if not ok:
            out_of_season.append(f"{tid} {name} -> {got.date()}")
    if nones:
        print(f"      (None for {len(nones)}: {nones})")
    assert not out_of_season, f"dates outside their season: {out_of_season[:5]}"
    assert len(nones) <= 3, f"too many unresolved: {nones}"


def test_override_fills_the_gap():
    """The 2016 Zurich isn't in DG's list; the override file supplies it."""
    assert training_event_date("R2016018", "Zurich Classic of New Orleans", EV, OV) == day("2016-04-28")
    assert training_event_date("R2016464", "Frys.com Open", EV, OV) == day("2015-10-18")


def test_overrides_only_cover_what_the_data_cannot():
    """An override for an event the data CAN resolve hides a disagreement:
    drop it, or find out which date is wrong. And it must sit in its season."""
    for tid, date in OV.items():
        assert d(tid) is None, f"{tid}: data now resolves it; remove the override"
        season = int(tid[1:5])
        if season >= 2024:
            assert date.year == season, tid
        else:
            assert _finale(season - 1) < date <= _finale(season), tid


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
