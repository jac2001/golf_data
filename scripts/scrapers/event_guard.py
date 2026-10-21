"""
Event-label guard for DataGolf feeds.
=====================================
DG's /field-updates and /betting-tools feeds serve THE CURRENT EVENT —
they take no tournament parameter. Every payload names its own event
(event_name), and writing it under whatever tid the caller requested is
how the Presidents Cup field ended up saved as Bank of Utah (and last
week's Biltmore odds as this week's market). Rule of the codebase:
data is keyed by its own payload's label, never the requester's.

Usage:
    from event_guard import expected_name, names_match
    if not names_match(payload["event_name"], expected_name(tid)):
        refuse to write
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Filler tokens that carry no identity ("the Open" vs "Open Championship").
_STOP = {"the", "at", "of", "presented", "by", "championship", "classic",
         "open", "invitational", "tournament", "cup"}


def expected_name(tournament_id: str) -> str:
    """The schedule's tournament_name for a tid ('' when unknown)."""
    for sched in sorted((PROJECT_ROOT / "data" / "raw").glob("schedule*_2*.csv")):
        try:
            df = pd.read_csv(sched, usecols=["tournament_id", "tournament_name"])
        except Exception:
            continue
        hit = df[df["tournament_id"].astype(str).str.upper() == tournament_id.upper()]
        if not hit.empty:
            return str(hit.iloc[0]["tournament_name"])
    return ""


def _words(name: str) -> list[str]:
    # Fold accents first: DG writes "Open de España", our schedule "Espana".
    # Punctuation inside a word goes ("U.S." -> "us"), hyphens split.
    import unicodedata
    folded = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    words = ("".join(c for c in w if c.isalnum()) for w in folded.lower().replace("-", " ").split())
    return [w for w in words if w]


def _tokens(name: str) -> set[str]:
    return set(_words(name)) - _STOP


def names_match(payload_name: str, schedule_name: str) -> bool:
    """Compare event labels using conservative normalization and known aliases."""
    # Import at call time: event_names imports our shared _words helper.
    from event_names import same_event

    return same_event(payload_name, schedule_name)
