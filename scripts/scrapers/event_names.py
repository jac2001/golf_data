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
    """True when the two names describe the same tournament.

    Jack's rule (Oct 21): exact match after normalizing (accents and
    punctuation folded, "the" dropped, anything from "presented by" on cut,
    DS Automobiles' year-numbered "NNdeg" token dropped), else a hand
    alias table for known rewordings. Fails closed: a new wording no alias
    covers is refused (a red run and a re-fetch, never another event's
    data). Spec: test_event_names.py.
    """
    
    # Explicit aliases preserve event identity; removing sponsors globally
    # would collapse PGA Championship and BMW PGA Championship, for example.
    aliases = {
        "butterfield bermuda championship": "bermuda championship",
        "abu dhabi aldar championship": "abu dhabi championship",
        "cognizant classic in palm beaches": "cognizant classic",
        "mexico open at vidantaworld": "vidantaworld mexico open",
        "waste management phoenix open": "wm phoenix open",
        "fedex st jude invitational": "fedex st jude championship",
        "masters tournament": "masters",
    }
    
    def normalize(name: str) -> list[str]:
        words = [word for word in _words(name) if word != "the"]
        if (
            len(words) == 5
            and words[:2] == ["ds", "automobiles"]
            and words[3:] == ["open", "ditalia"]
            and words[2].endswith("deg")
            and words[2][:-3].isdigit()
        ):
            words = words[:2] + words[3:]
        for i in range(len(words) - 1):
            if words[i:i + 2] == ['presented', 'by']:
                return words[:i]
        return words
    a = normalize(payload_name)
    b = normalize(schedule_name)
    if not a or not b:
        return False
    
    if a == b:
        return True
    
    a_name = " ".join(a)
    b_name = " ".join(b)
    a_name = aliases.get(a_name, a_name)
    b_name = aliases.get(b_name, b_name)
    return a_name == b_name
