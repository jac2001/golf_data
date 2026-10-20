"""Tests for fetch_dg_historical_results: names, ids, and the event check.
Run: python3 scripts/scrapers/test_dg_historical.py"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_dg_historical_results import (  # noqa: E402
    build_player_crosswalk, check_event, first_last, name_key, resolve_player_id,
)

D = pd.Timestamp


def test_name_key_matches_across_layouts():
    assert name_key("Potter, Jr., Ted") == name_key("Ted Potter, Jr.")
    assert name_key("Olesen, Thorbjorn") == name_key("Thorbjørn Olesen")
    assert name_key("Love III, Davis") == name_key("Davis Love III")
    assert name_key("Rahm, Jon") != name_key("Jon Rahmer")


def test_first_last_writes_our_layout():
    assert first_last("Rahm, Jon") == "Jon Rahm"
    assert first_last("Potter, Jr., Ted") == "Ted Potter, Jr."


def test_zero_padded_ids_are_one_player_newest_form_wins():
    lb = pd.DataFrame({"player_id": ["06567", "6567"], "player_name": ["Vijay Singh", "Vijay Singh"]})
    assert build_player_crosswalk(lb)[name_key("Vijay Singh")] == "6567"


def test_crosswalk_refuses_shared_names_and_synthetic_ids():
    lb = pd.DataFrame({"player_id": ["35139", "31109", "DG13412", "40098"],
                       "player_name": ["Richard Lee", "Richard Lee", "Olesen, Thorbjorn", "Matt Fitzpatrick"]})
    cw = build_player_crosswalk(lb)
    assert name_key("Richard Lee") not in cw          # two players, so neither
    assert name_key("Thorbjorn Olesen") not in cw     # never map onto a DG id
    assert resolve_player_id("Lee, Richard", 999, cw) == "DG999"
    assert resolve_player_id("Fitzpatrick, Matthew", 17646, cw) == "40098"   # alias by DG id


OURS = {
    "R2021014": {"name": "Masters Tournament", "date": D("2020-11-15"), "winner": "Dustin Johnson", "winner_id": "30925"},
    "R2021457": {"name": "World Wide Technology Championship at Mayakoba", "date": D("2020-12-06"),
                 "winner": "Viktor Hovland", "winner_id": "46717"},
}


def test_same_event_passes():
    assert check_event("R2021014", "The Masters", D("2020-11-15"), "Johnson, Dustin", OURS) is None


def test_wrong_date_or_winner_is_refused():
    assert "date" in check_event("R2021014", "The Masters", D("2021-04-11"), "Johnson, Dustin", OURS)
    assert "winner" in check_event("R2021014", "The Masters", D("2020-11-15"), "Matsuyama, Hideki", OURS)


def test_winner_compared_by_id_when_both_known():
    # Joohyung Kim (DataGolf) is Tom Kim (ours): the ids agree, the names don't.
    ours = {"R2022013": {"name": "Wyndham Championship", "date": D("2022-08-07"), "winner": "Tom Kim", "winner_id": "55182"}}
    assert check_event("R2022013", "Wyndham Championship", D("2022-08-07"), "Kim, Joohyung", ours, "55182") is None
    assert check_event("R2022013", "Wyndham Championship", D("2022-08-07"), "Kim, Joohyung", ours, "99999") is not None


def test_renamed_event_needs_date_and_winner():
    ok = check_event("R2021457", "Mayakoba Golf Classic presented by UNIFIN", D("2020-12-06"), "Hovland, Viktor", OURS, "46717")
    assert ok is None
    bad = check_event("R2021457", "Mayakoba Golf Classic presented by UNIFIN", D("2020-12-06"), "Someone, Else", OURS, "1")
    assert "name" in bad


def test_unknown_id_already_ours_elsewhere_is_refused():
    why = check_event("R2020014", "The Masters", D("2020-11-15"), "Johnson, Dustin", OURS)
    assert why and "R2021014" in why


def test_unknown_new_event_passes():
    assert check_event("R2025528", "Butterfield Bermuda Championship", D("2025-11-16"), "X, Y", OURS) is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
