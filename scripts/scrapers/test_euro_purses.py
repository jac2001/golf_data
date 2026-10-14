"""
Tests for euro_schedule.purse_for — written before the code.
Run:  python3 scripts/scrapers/test_euro_purses.py

Names are DataGolf's real spellings from both seasons (Oct 13). The last
test runs every event in the real schedule files through the real table.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.scrapers.euro_schedule import load, load_purses, purse_for  # noqa: E402

TABLE = load_purses()


def p(name: str, table: pd.DataFrame = TABLE):
    return purse_for(name, table)


# ── the tests ────────────────────────────────────────────────────────────────

def test_sponsor_prefix():
    """DG adds the sponsor; the key is the event."""
    assert p("Hero Dubai Desert Classic") == 9_000_000
    assert p("Amgen Irish Open") == 6_000_000


def test_sponsor_changes_between_seasons():
    assert p("Crown Australian Open") == 1_300_000
    assert p("Capital.com Australian Open") == 1_300_000


def test_sponsor_suffix_and_punctuation():
    assert p("Open de Espana presented by Madrid") == 3_750_000
    assert p("DS Automobiles 84deg Open d'Italia") == 3_000_000
    assert p("Open de Portugal | Cascais - Lisboa") == 2_750_000


def test_links_is_not_the_championship():
    """Same sponsor, different events, 3x apart."""
    assert p("Alfred Dunhill Links Championship") == 5_000_000
    assert p("Alfred Dunhill Championship") == 1_730_000


def test_bmw_pga_is_not_the_australian_pga():
    """'BMW PGA Championship' is not consecutive inside 'BMW Australian
    PGA Championship': the Rolex event must not leak 6x its purse."""
    assert p("BMW PGA Championship") == 9_000_000
    assert p("BMW Australian PGA Championship") == 1_630_000


def test_two_tour_championships():
    assert p("DP World Tour Championship") == 10_000_000
    assert p("DP World India Championship") == 4_000_000


def test_abu_dhabi_under_its_full_name():
    """The 2026 event is also 'Abu Dhabi Aldar Championship': 'Aldar' sits
    mid-name, so the key is just 'Abu Dhabi' to survive DG adopting it."""
    assert p("Abu Dhabi Championship") == 9_000_000
    assert p("Abu Dhabi Aldar Championship") == 9_000_000


def test_unknown_event_is_none():
    assert p("Presidents Cup") is None
    assert p("") is None


def test_more_specific_key_wins():
    """Two keys inside one name: the longer, more specific one decides."""
    t = pd.DataFrame({"event": ["Australian Open", "Capital.com Australian Open"],
                      "purse_usd": [1_700_000, 2_000_000]})
    assert p("Capital.com Australian Open", t) == 2_000_000


def test_tied_keys_are_none():
    """The same key twice (a stale row left beside a new one): refuse to
    guess, so the miss surfaces instead of the old purse winning."""
    t = pd.DataFrame({"event": ["Irish Open", "Irish Open"],
                      "purse_usd": [6_000_000, 7_000_000]})
    assert p("Amgen Irish Open", t) is None


def test_every_real_event_is_priced():
    """Every event DG lists, both seasons, finds a row: a miss would
    silently fall back to the default. Lists any that don't."""
    missing = [n for n in load()["tournament_name"].unique() if p(n) is None]
    assert not missing, f"no purse row for: {missing}"


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
