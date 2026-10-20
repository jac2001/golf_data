"""Tests for event_guard.names_match. Run: python3 scripts/scrapers/test_event_guard.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_guard import names_match  # noqa: E402


def test_same_event_different_wording():
    assert names_match("THE CJ CUP Byron Nelson", "CJ Cup Byron Nelson")
    assert names_match("Butterfield Bermuda Championship", "Bermuda Championship")


def test_accents_fold():
    assert names_match("Open de España", "Open de Espana")


def test_different_events_refused():
    assert not names_match("Presidents Cup", "Bank of Utah Championship")
    assert not names_match("Baycurrent Classic", "Butterfield Bermuda Championship")


def test_all_filler_names_match_only_themselves():
    # Every word is filler, so the distinctive-token overlap has nothing to
    # compare. Identical names are the same event; anything else is refused.
    assert names_match("The Open Championship", "The Open Championship")
    assert names_match("U.S. Open", "U.S. Open")
    assert names_match("U.S. Open", "US Open")
    assert not names_match("The Open Championship", "U.S. Open")
    assert not names_match("The Open", "The Open Championship")


def test_unknown_name_fails_closed():
    assert not names_match("Butterfield Bermuda Championship", "")
    assert not names_match("", "")


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print(f"\u2714 {f.__name__}")
    print(f"{len(fns)}/{len(fns)} passed")
