"""
Tests for euro_schedule.resolve_event — written before the code.
Run:  python3 scripts/scrapers/test_euro_schedule.py

The schedule below is real (DataGolf's 2026 and 2027 euro calendars,
Oct 13), trimmed to the rows that make this hard: names that repeat a
year apart, and names that differ by one word.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.scrapers.euro_schedule import is_provisional, purse_for, resolve_event  # noqa: E402

ROWS = [
    # start,       name,                                  tid
    ("2026-02-26", "Alfred Dunhill Championship",          "E2026111"),
    ("2026-10-01", "Alfred Dunhill Links Championship",    "E2026144"),
    ("2026-10-08", "Open de Espana",                       "E2026139"),
    ("2026-10-15", "DP World India Championship",          "E2026140"),
    ("2026-10-22", "Genesis Championship",                 "E2026141"),
    ("2026-11-05", "Abu Dhabi Championship",               "E2026T11051"),
    ("2026-11-12", "DP World Tour Championship",           "E2026T11121"),
    ("2026-12-03", "Capital.com Australian Open",          "E2027T12031"),
    ("2026-12-03", "Nedbank Golf Challenge in honour of Gary Player", "E2027T12032"),
    ("2027-10-07", "Open de Espana presented by Madrid",   "E2027T10071"),
    ("2027-10-14", "DP World India Championship",          "E2027T10141"),
    ("2027-11-04", "Abu Dhabi Championship",               "E2027T11041"),
    ("2027-11-11", "DP World Tour Championship",           "E2027T11111"),
]
SCHED = pd.DataFrame([{"start_date": pd.Timestamp(s), "end_date": pd.Timestamp(s) + pd.Timedelta(days=3),
                       "tournament_name": n, "tournament_id": t} for s, n, t in ROWS])
day = pd.Timestamp


def tid(name: str, today: str):
    row = resolve_event(SCHED, name, day(today))
    return None if row is None else row["tournament_id"]


# ── the tests ────────────────────────────────────────────────────────────────

def test_field_feed_rolls_over_on_tuesday():
    """Tuesday of India week: the field feed serves India."""
    assert tid("DP World India Championship", "2026-10-13") == "E2026140"


def test_monday_settle_of_last_weeks_event():
    """Monday after Spain: the results feed still serves Spain."""
    assert tid("Open de Espana", "2026-10-12") == "E2026139"


def test_feed_spells_it_with_an_accent():
    assert tid("Open de España", "2026-10-09") == "E2026139"


def test_same_name_next_year_picks_this_years():
    """Abu Dhabi is in both seasons; in Nov 2026 it's the 2026 one."""
    assert tid("Abu Dhabi Championship", "2026-11-03") == "E2026T11051"


def test_same_name_this_time_next_year():
    assert tid("Abu Dhabi Championship", "2027-11-02") == "E2027T11041"


def test_one_word_apart_names_dont_cross():
    """India week: 'DP World India' must not resolve to 'DP World Tour
    Championship', even though event_guard.names_match says they match."""
    assert tid("DP World India Championship", "2026-10-15") == "E2026140"
    assert tid("DP World Tour Championship", "2026-11-10") == "E2026T11121"


def test_links_vs_championship():
    """Alfred Dunhill Links (Oct) vs Alfred Dunhill Championship (Feb)."""
    assert tid("Alfred Dunhill Links Championship", "2026-09-29") == "E2026144"


def test_dg_renames_the_event():
    """2027's Spain is 'Open de Espana presented by Madrid'; the feed may
    say just 'Open de Espana'. Same event, same week."""
    assert tid("Open de Espana", "2027-10-05") == "E2027T10071"


def test_two_events_same_week():
    """Dec 3, 2026 has two co-sanctioned events: the name decides."""
    assert tid("Nedbank Golf Challenge in honour of Gary Player", "2026-12-01") == "E2027T12032"
    assert tid("Capital.com Australian Open", "2026-12-01") == "E2027T12031"


def test_right_name_wrong_time_is_none():
    """A feed serving 'Abu Dhabi' in July matches nothing near today:
    something upstream is wrong, so refuse instead of guessing."""
    assert tid("Abu Dhabi Championship", "2027-07-01") is None


def test_unknown_event_is_none():
    assert tid("Presidents Cup", "2026-10-13") is None
    
def test_right_name_wrong_time_is_none():
    assert tid("", "2026-10-13") is None
    assert tid("DP World Tour Championship", "2026-10-13") is None


def test_generic_fragment_does_not_resolve():
    """A one-word fragment sits inside many names. Abu Dhabi is the only
    event near Nov 3, so a plain substring fallback accepted
    'Championship' as Abu Dhabi."""
    assert tid("Championship", "2026-11-03") is None
    assert tid("Open", "2026-10-09") is None


def test_fallback_needs_whole_words():
    """'Open de Esp' is a substring of the 2027 name but not whole words."""
    assert tid("Open de Esp", "2027-10-05") is None


def test_provisional_ids():
    assert is_provisional("E2027T12031")
    assert not is_provisional("E2026140")
    
def test_tied_keys_are_none():
    """The same key twice (a stale row left beside a new one): refuse to guess."""
    t = pd.DataFrame({"event": ["Irish Open", "Irish Open"],
                      "purse_usd": [6_000_000, 7_000_000]})
    assert purse_for("Amgen Irish Open", t) is None

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
