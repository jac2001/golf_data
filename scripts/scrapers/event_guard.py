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
    sched = PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv"
    try:
        df = pd.read_csv(sched, usecols=["tournament_id", "tournament_name"])
        hit = df[df["tournament_id"].astype(str).str.upper() == tournament_id.upper()]
        return str(hit.iloc[0]["tournament_name"]) if not hit.empty else ""
    except Exception:
        return ""


def _tokens(name: str) -> set[str]:
    toks = {t for t in str(name).lower().replace("-", " ").split() if t.isalnum()}
    return toks - _STOP


def names_match(payload_name: str, schedule_name: str) -> bool:
    """Do two event names plausibly describe the same tournament?

    Distinctive-token overlap: 'Bank of Utah Championship' vs
    'Presidents Cup' shares nothing; 'THE CJ CUP Byron Nelson' vs
    'CJ Cup Byron Nelson' overlaps fully. Unknown schedule name
    (missing tid) fails CLOSED — no label, no write.
    """
    a, b = _tokens(payload_name), _tokens(schedule_name)
    if not a or not b:
        return False
    overlap = len(a & b) / min(len(a), len(b))
    return overlap >= 0.5
