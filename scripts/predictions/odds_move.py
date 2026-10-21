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

    TODO(Jack): implement.
    Facts the tests pin:
      - Chance up enough on BOTH thresholds -> "DOWN" (odds shortened).
      - Chance down enough on BOTH thresholds -> "UP" (odds lengthened).
      - Below either threshold -> None (noise, mostly longshots).
      - Missing (None or NaN), zero or negative, or above 1 on either side
        -> None. NaN is what pandas gives for a golfer missing from one file.
      - Exactly on a threshold counts as a move (>=, not >).
    Hints: math.isnan; relative change = (now - open) / open. Floating
    point: 0.022 - 0.02 is 0.0019999999999999983, not 0.002, so "exactly on
    a threshold" needs a tiny tolerance (e.g. 1e-9) in the comparison.
    """
    raise NotImplementedError("TODO(Jack): odds_move")
