"""
euro_schedule.py — the DP World Tour schedule, every season, one resolver.
==========================================================================
DataGolf publishes the whole euro calendar, but gives most events an
event_id of "TBD" until ~2 weeks out. We used to drop those rows, so the
schedule only reached two weeks ahead (advice never said "save"), and
the 2026 file ended Oct 25 (after which predict_euro found no event).

Now:
  - every event is written; TBD events get a PROVISIONAL id,
    E{season}T{MMDD}{n}, replaced by DG's real id on the next refresh.
    The "T" means no provisional id can ever equal a DG id.
  - provisional events never open for picks (picks store the id).
  - two seasons are fetched (this year's and next): DG's season 2027
    starts Nov 26, 2026.
  - every reader loads ALL season files through load(), and finds "the
    event a feed is serving" through resolve_event().

Why the resolver matters: across two seasons every event name appears
twice (Abu Dhabi Nov 2026 and Nov 2027), and event_guard.names_match
is loose enough that 'DP World Tour Championship' matches 'DP World
India Championship' — four weeks apart in the same season.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PROVISIONAL_MARK = "T"


def is_provisional(tid: str) -> bool:
    """E2027T01211 → True; E2026140 → False."""
    return len(str(tid)) > 5 and str(tid)[5] == PROVISIONAL_MARK


def fold(name: str) -> str:
    """Accent-fold, lowercase, collapse spaces: 'Open de España' →
    'open de espana'. DG's feeds disagree on accents (2026-10-12)."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def load(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Every schedule_euro_{season}.csv, concatenated, dates parsed."""
    files = sorted(raw_dir.glob("schedule_euro_2*.csv"))
    if not files:
        return pd.DataFrame(columns=["start_date", "end_date", "tournament_name", "tournament_id"])
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    return df.sort_values("start_date").reset_index(drop=True)


# ── TODO(Jack): resolve_event ────────────────────────────────────────────────
# A DG feed (field, in-play, results, predictions) says "I'm serving
# <name>". Which schedule row is that?
#
#   sched: load()'s output (both seasons: names repeat a year apart)
#   name:  the feed's event_name, as DG spelled it this time
#   today: the run date (a Timestamp; tests pass fixed dates)
#
# Return the matching row (a pd.Series), or None when you can't be sure.
# None makes the caller refuse to write; that's the safe failure.
#
# The feeds only ever serve an event near today: the field feed rolls to
# next week's event Mon/Tue, in-play runs Thu–Sun, results settle on the
# Monday after. So the right row is close to today in date.
#
# Decisions that are yours (write the reason in a comment):
#   1. Name match: exact fold(name) == fold(row name)? Or
#      event_guard.names_match (token overlap)? Exact misses DG renames
#      ('Open de Espana' → 'Open de Espana presented by Madrid'); loose
#      matches 'DP World Tour Championship' to 'DP World India
#      Championship'. Maybe exact first, loose only as a fallback?
#   2. Date: how far from today can the right row be? Too tight and the
#      Monday settle of last week's event fails; too loose and last
#      year's edition could match.
#   3. Two rows still qualify: pick one, or return None?
#
# Done when: python3 scripts/scrapers/test_euro_schedule.py → all pass.

def resolve_event(sched: pd.DataFrame, name: str, today: pd.Timestamp) -> pd.Series | None:
    # Date first: only events within a week of today (either side) are
    # candidates. That covers the Monday settle and the Tue field
    # rollover, and rules out last year's edition of the same name.
    # Then the name: exact (accent-folded) match first. The fallback,
    # for DG renames, is whole-word containment of at least two words:
    # names_match (token overlap) crossed 'DP World India' with 'DP World
    # Tour Championship', and a plain substring check accepted
    # 'Championship' as Abu Dhabi.
    # Two rows still qualify → None: the caller refuses to write.
    if not fold(name):
        return None
    latest_start = today + pd.Timedelta(days=7)
    earliest_end = today - pd.Timedelta(days=7)
    near_rows = sched[(sched["start_date"] <= latest_start) & (sched["end_date"] >= earliest_end)]
    exact = near_rows[near_rows["tournament_name"].apply(lambda n: fold(n) == fold(name))]
    if len(exact) == 1:
        return exact.iloc[0]
    if len(exact) > 1:
        return None

    candidates = near_rows[near_rows["tournament_name"].apply(lambda n: _contains_words(name, n))]
    if len(candidates) == 1:
        return candidates.iloc[0]
    return None


MIN_FALLBACK_WORDS = 2


def _words(name: str) -> list[str]:
    """'Capital.com Australian Open' → ['capital', 'com', 'australian', 'open']."""
    return re.findall(r"[a-z0-9]+", fold(name))


def _contains_words(a: str, b: str) -> bool:
    """Does the shorter name appear, as consecutive WHOLE words, inside
    the longer one, and is it at least MIN_FALLBACK_WORDS long?
    'Open de Espana' in 'Open de Espana presented by Madrid' → True (a
    rename). 'Championship' → False (one word sits inside half the
    calendar; on Nov 3, 2026 a plain substring check accepted it as Abu
    Dhabi). 'Open de Esp' → False ('esp' is not a whole word)."""
    short, long_ = sorted((_words(a), _words(b)), key=len)
    if len(short) < MIN_FALLBACK_WORDS:
        return False
    k = len(short)
    return any(long_[i:i + k] == short for i in range(len(long_) - k + 1))


def row_for_write(name: str, feed: str, today: pd.Timestamp | None = None) -> pd.Series:
    """The schedule row a DG feed's OWN label refers to, for code about to
    WRITE something under its id. Raises SystemExit (no write) when no
    row near today matches, or when the match only has a provisional id:
    anything written under E2027T... is orphaned when DG assigns the real
    id. The feed's label decides, never our assumption."""
    today = pd.Timestamp.now().normalize() if today is None else today
    row = resolve_event(load(), name, today)
    if row is None:
        raise SystemExit(f"{feed} event '{name}' matches no euro schedule row near today "
                         "— refusing to write (refetch --schedule?)")
    tid = str(row["tournament_id"])
    if is_provisional(tid):
        raise SystemExit(f"{feed} event '{name}' only has provisional id {tid} — run "
                         "fetch_euro_events --schedule first; refusing to write under an id that will change")
    return row
