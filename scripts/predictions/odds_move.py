"""
odds_move.py — did a golfer's betting odds really move this week?
=================================================================
This Week's "Move" column compares each golfer's OPENING line (the first
DataGolf consensus odds saved for the event, data/odds/odds_open_{tid}.csv)
with the CURRENT one (data/odds/odds_{tid}.csv). Both are implied win
probabilities: the chance the market's price says he wins (0.08 = 8%).

The judgment is noise. Books shade longshots all week: a 0.4% golfer
drifting to 0.35% is a big relative change but means nothing. A favorite
going from 8% to 9% is small in relative terms but real money moved.

Run the spec:  python3 scripts/predictions/test_odds_move.py
"""

from __future__ import annotations

from typing import Literal

# "DOWN" = odds shortened (his implied chance ROSE: the market warmed to him).
# "UP"   = odds lengthened (his implied chance FELL: the market cooled).
# None   = no real move, or not enough data to say.
Move = Literal["UP", "DOWN"] | None

# The thresholds the tests pin. Both must be met for a move to count.
MIN_RELATIVE = 0.10   # at least a 10% change relative to the opening chance
MIN_POINTS = 0.002    # and at least 0.2 percentage points in absolute terms


def odds_move(open_prob: float | None, now_prob: float | None) -> Move:
    """Which way the market moved on one golfer, or None.

    Jack's rule (Oct 21): a move counts only when the implied chance changed
    by at least MIN_RELATIVE of its opening value AND at least MIN_POINTS
    in absolute terms (exactly on a threshold counts, within 1e-9 for
    floating point). Missing, NaN, zero, negative or >1 inputs -> None.
    """
    if open_prob is None or now_prob is None:
        return None
    # NaN fails every comparison, so this range check also rejects NaN.
    if not (0 < open_prob <= 1) or not (0 < now_prob <= 1):
        return None

    change = now_prob - open_prob
    magnitude = abs(change)
    relative_change = magnitude / open_prob

    tolerance = 1e-9
    if magnitude + tolerance < MIN_POINTS or relative_change + tolerance < MIN_RELATIVE:
        return None
    return "DOWN" if change > 0 else "UP"
