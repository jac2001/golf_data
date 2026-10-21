"""
event_names.py — do two event names describe the same tournament?
==================================================================
event_guard.names_match is CLAUDE.md rule 1's guard: a feed whose
event_name doesn't match this week's schedule name is refused. It counts
the share of "distinctive" words two names have in common (>= 0.5), with
a fixed filler list. One shared sponsor word is enough to pass, and an
audit of every schedule + DataGolf name (Oct 21) found pairs like:

    "RBC Heritage"        == "RBC Canadian Open"
    "PGA Championship"    == "BMW PGA Championship"
    "Masters Tournament"  == "Qatar Masters"
    "Open de Espana"      == "FedEx Open de France"     (España shipped once)

PGA TOUR and DP World Tour events run the same weeks, so a feed still on
another event can carry exactly such a name.

same_event() is the replacement. When it passes test_event_names.py,
names_match delegates to it (and test_event_guard.py keeps passing).

    python3 scripts/scrapers/test_event_names.py
"""

from __future__ import annotations

import glob
from functools import lru_cache
from pathlib import Path

import pandas as pd

from event_guard import _STOP, _words  # noqa: F401  (accent folding + filler list)

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def schedule_names() -> tuple[str, ...]:
    """Every distinct tournament name in our PGA + DP World Tour schedules.

    Plumbing, in case your rule wants data (for example: a word that
    appears in several DIFFERENT events' names, like "bmw" or "masters",
    says less about identity than one that appears in one event's).
    """
    names: set[str] = set()
    for f in glob.glob(str(ROOT / "data" / "raw" / "schedule*_2*.csv")):
        try:
            col = pd.read_csv(f, usecols=["tournament_name"])["tournament_name"]
        except Exception:
            continue
        names |= set(col.dropna().astype(str))
    return tuple(sorted(names))


def same_event(payload_name: str, schedule_name: str) -> bool:
    """True when the two names plausibly describe the same tournament.

    TODO(Jack): implement. The tests in test_event_names.py are the spec:
    SAME pairs must match and DIFFERENT pairs must not, plus the old
    behaviour (accents fold, an empty name fails closed, names made only
    of filler match only themselves).

    Tools: _words(name) folds accents and punctuation and lowercases
    ("Open de España" -> ["open", "de", "espana"]); _STOP is the current
    filler set; schedule_names() is the corpus. Two directions people
    take, pick one and say why in a comment:
      - a hand list of sponsor / generic words that never count alone
      - data: weigh each word by how many different events use it
    Whatever the rule, it must fail CLOSED: when unsure, say different.
    A refused feed costs a re-fetch; an accepted wrong one is the bug.

    Two traps found while checking that the tests can all pass together:
      - If you count words per event, PGA ids keep their number across
        years (R2025010 / R2026010) but DP World Tour ids don't, so one
        renamed DPWT event looks like several.
      - _STOP mixes two kinds of word. "the", "presented", "by" never
        identify anything; "championship" vs "invitational" is the only
        difference between "Genesis Championship" and "Genesis
        Invitational".
    """
    raise NotImplementedError
