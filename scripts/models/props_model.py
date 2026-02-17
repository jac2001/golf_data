#!/usr/bin/env python3
"""
Props Model - Sportsbook-style prop generation
==============================================

Generates betting props similar to DraftKings:
- Head-to-head matchups
- Position props (Top 5, Top 10, Top 20, Make Cut)
- Round score over/unders
- Parlay calculations
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# =============================================================================
# ODDS CONVERSION UTILITIES
# =============================================================================

def prob_to_american(prob: float) -> int:
    """
    Convert probability to American odds.

    Examples:
        0.60 (60%) -> -150  (favorite)
        0.40 (40%) -> +150  (underdog)
        0.50 (50%) -> -100 / +100
    """
    if prob <= 0:
        return 0
    if prob >= 1:
        return -10000

    if prob >= 0.5:
        # Favorite: negative odds
        return int(-100 * prob / (1 - prob))
    else:
        # Underdog: positive odds
        return int(100 * (1 - prob) / prob)


def american_to_prob(odds: int) -> float:
    """
    Convert American odds to implied probability.

    Examples:
        -150 -> 0.60 (60%)
        +150 -> 0.40 (40%)
    """
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def format_american_odds(odds: int) -> str:
    """Format American odds with +/- prefix."""
    if odds >= 0:
        return f"+{odds}"
    return str(odds)


def calculate_edge(model_prob: float, book_odds: int) -> float:
    """
    Calculate edge (expected value) given model probability and book odds.

    Returns percentage edge (positive = value bet).
    """
    implied_prob = american_to_prob(book_odds)
    edge = (model_prob - implied_prob) * 100
    return round(edge, 1)


def calculate_fair_odds(prob: float, vig_pct: float = 4.5) -> Tuple[int, int]:
    """
    Calculate fair odds with vig built in (like a real sportsbook).

    Returns (favorite_odds, underdog_odds) for a two-way market.
    """
    # Apply vig to both sides
    vig_mult = 1 + (vig_pct / 100)

    favorite_prob = prob * vig_mult / (prob * vig_mult + (1 - prob))
    underdog_prob = (1 - prob) * vig_mult / ((1 - prob) * vig_mult + prob)

    fav_odds = prob_to_american(min(0.95, favorite_prob))
    dog_odds = prob_to_american(max(0.05, 1 - underdog_prob))

    return fav_odds, dog_odds


# =============================================================================
# HEAD-TO-HEAD MATCHUP MODEL
# =============================================================================

@dataclass
class MatchupResult:
    """Result of a head-to-head matchup analysis."""
    player_a: str
    player_b: str
    prob_a_wins: float
    prob_b_wins: float
    odds_a: int
    odds_b: int
    confidence: str  # "High", "Medium", "Low"
    factors: Dict[str, str]  # Key factors driving the prediction


def calculate_matchup_probability(
    player_a_data: Dict,
    player_b_data: Dict,
    weights: Optional[Dict] = None
) -> float:
    """
    Calculate probability that Player A finishes higher than Player B.

    Uses multiple factors:
    - Model rank / expected value
    - Strokes gained total
    - Recent form trend
    - Course fit (if available)
    - Historical head-to-head (if available)
    """
    if weights is None:
        weights = {
            "model_rank": 0.30,
            "sg_total": 0.25,
            "form_trend": 0.20,
            "course_fit": 0.15,
            "world_rank": 0.10
        }

    scores = {"a": 0, "b": 0}
    factors = {}

    # Model rank comparison
    rank_a = player_a_data.get("model_rank") or player_a_data.get("rank", 999)
    rank_b = player_b_data.get("model_rank") or player_b_data.get("rank", 999)

    if rank_a < rank_b:
        scores["a"] += weights["model_rank"]
        factors["Model Rank"] = f"{player_a_data.get('player_name', 'A')} ranked higher"
    elif rank_b < rank_a:
        scores["b"] += weights["model_rank"]
        factors["Model Rank"] = f"{player_b_data.get('player_name', 'B')} ranked higher"
    else:
        scores["a"] += weights["model_rank"] / 2
        scores["b"] += weights["model_rank"] / 2

    # SG Total comparison
    sg_a = player_a_data.get("sg_total", 0) or 0
    sg_b = player_b_data.get("sg_total", 0) or 0

    if sg_a > sg_b + 0.1:  # Meaningful difference
        scores["a"] += weights["sg_total"]
        factors["Strokes Gained"] = f"{player_a_data.get('player_name', 'A')} +{sg_a:.2f} vs +{sg_b:.2f}"
    elif sg_b > sg_a + 0.1:
        scores["b"] += weights["sg_total"]
        factors["Strokes Gained"] = f"{player_b_data.get('player_name', 'B')} +{sg_b:.2f} vs +{sg_a:.2f}"
    else:
        scores["a"] += weights["sg_total"] / 2
        scores["b"] += weights["sg_total"] / 2
        factors["Strokes Gained"] = "Even"

    # Form trend comparison
    form_a = player_a_data.get("form_trend", 0) or 0
    form_b = player_b_data.get("form_trend", 0) or 0

    if form_a > form_b + 0.15:
        scores["a"] += weights["form_trend"]
        factors["Recent Form"] = f"{player_a_data.get('player_name', 'A')} trending up"
    elif form_b > form_a + 0.15:
        scores["b"] += weights["form_trend"]
        factors["Recent Form"] = f"{player_b_data.get('player_name', 'B')} trending up"
    else:
        scores["a"] += weights["form_trend"] / 2
        scores["b"] += weights["form_trend"] / 2

    # Course fit comparison (if available)
    fit_a = player_a_data.get("dg_fit_total", 0) or player_a_data.get("course_fit", 0) or 0
    fit_b = player_b_data.get("dg_fit_total", 0) or player_b_data.get("course_fit", 0) or 0

    if fit_a > fit_b + 0.2:
        scores["a"] += weights["course_fit"]
        factors["Course Fit"] = f"{player_a_data.get('player_name', 'A')} better fit"
    elif fit_b > fit_a + 0.2:
        scores["b"] += weights["course_fit"]
        factors["Course Fit"] = f"{player_b_data.get('player_name', 'B')} better fit"
    else:
        scores["a"] += weights["course_fit"] / 2
        scores["b"] += weights["course_fit"] / 2

    # World rank comparison
    wrank_a = player_a_data.get("world_rank", 999) or 999
    wrank_b = player_b_data.get("world_rank", 999) or 999

    if wrank_a < wrank_b:
        scores["a"] += weights["world_rank"]
    elif wrank_b < wrank_a:
        scores["b"] += weights["world_rank"]
    else:
        scores["a"] += weights["world_rank"] / 2
        scores["b"] += weights["world_rank"] / 2

    # Calculate final probability
    total = scores["a"] + scores["b"]
    if total == 0:
        prob_a = 0.5
    else:
        prob_a = scores["a"] / total

    # Add some regression toward 50% to avoid extreme predictions
    # (real golf has high variance)
    prob_a = 0.5 + (prob_a - 0.5) * 0.85

    return prob_a, factors


def generate_matchup(
    player_a_data: Dict,
    player_b_data: Dict
) -> MatchupResult:
    """Generate a full matchup result with odds and analysis."""

    prob_a, factors = calculate_matchup_probability(player_a_data, player_b_data)
    prob_b = 1 - prob_a

    # Determine confidence based on probability spread
    spread = abs(prob_a - 0.5)
    if spread > 0.15:
        confidence = "High"
    elif spread > 0.08:
        confidence = "Medium"
    else:
        confidence = "Low"

    # Calculate odds with small vig
    odds_a = prob_to_american(prob_a)
    odds_b = prob_to_american(prob_b)

    return MatchupResult(
        player_a=player_a_data.get("player_name", "Player A"),
        player_b=player_b_data.get("player_name", "Player B"),
        prob_a_wins=prob_a,
        prob_b_wins=prob_b,
        odds_a=odds_a,
        odds_b=odds_b,
        confidence=confidence,
        factors=factors
    )


# =============================================================================
# POSITION PROPS
# =============================================================================

@dataclass
class PositionProp:
    """A position-based prop bet."""
    player_name: str
    prop_type: str  # "winner", "top5", "top10", "top20", "make_cut"
    probability: float
    odds: int
    display_name: str


def generate_position_props(player_data: Dict) -> List[PositionProp]:
    """Generate position props for a player from their model predictions."""

    props = []
    name = player_data.get("player_name", "Unknown")

    # Winner
    win_prob = player_data.get("win_prob", 0) or 0
    if win_prob > 0:
        props.append(PositionProp(
            player_name=name,
            prop_type="winner",
            probability=win_prob,
            odds=prob_to_american(win_prob),
            display_name="To Win Tournament"
        ))

    # Top 5
    top5_prob = player_data.get("top5_prob", 0) or 0
    if top5_prob > 0:
        props.append(PositionProp(
            player_name=name,
            prop_type="top5",
            probability=top5_prob,
            odds=prob_to_american(top5_prob),
            display_name="Top 5 Finish"
        ))

    # Top 10
    top10_prob = player_data.get("top10_prob", 0) or 0
    if top10_prob > 0:
        props.append(PositionProp(
            player_name=name,
            prop_type="top10",
            probability=top10_prob,
            odds=prob_to_american(top10_prob),
            display_name="Top 10 Finish"
        ))

    # Top 20
    top20_prob = player_data.get("top20_prob", 0) or 0
    if top20_prob > 0:
        props.append(PositionProp(
            player_name=name,
            prop_type="top20",
            probability=top20_prob,
            odds=prob_to_american(top20_prob),
            display_name="Top 20 Finish"
        ))

    # Make Cut (estimate from top probabilities if not available)
    cut_prob = player_data.get("make_cut_prob", 0)
    if not cut_prob and top20_prob:
        # Rough estimate: if top20 prob is X, cut prob is roughly X * 1.5 (capped at 95%)
        cut_prob = min(0.95, top20_prob * 1.5 + 0.2)
    if cut_prob > 0:
        props.append(PositionProp(
            player_name=name,
            prop_type="make_cut",
            probability=cut_prob,
            odds=prob_to_american(cut_prob),
            display_name="Make Cut"
        ))

    return props


# =============================================================================
# ROUND SCORE PROPS
# =============================================================================

@dataclass
class RoundScoreProp:
    """A round score over/under prop."""
    player_name: str
    round_num: int
    line: float  # e.g., 69.5
    expected_score: float
    over_prob: float
    under_prob: float
    over_odds: int
    under_odds: int
    recommendation: str  # "OVER", "UNDER", or "PASS"


def estimate_expected_round_score(
    player_data: Dict,
    course_par: int = 72,
    course_scoring_avg: float = 71.0,
    round_num: int = 1
) -> Tuple[float, float]:
    """
    Estimate a player's expected round score and standard deviation.

    Uses SG total as the primary driver.
    """
    sg_total = player_data.get("sg_total", 0) or 0
    form_trend = player_data.get("form_trend", 0) or 0

    # Base expected score is course average
    # SG total adjusts this (negative SG = above average scores)
    expected = course_scoring_avg - sg_total

    # Form adjustment (hot players trend lower)
    expected -= form_trend * 0.3

    # Round adjustments (players typically score higher in R1/R2 due to nerves)
    if round_num == 1:
        expected += 0.3
    elif round_num == 4:
        expected -= 0.2  # Pressure can go either way, but leaders often shoot lower

    # Standard deviation for golf rounds (typically 2.5-3.5 strokes)
    std_dev = 3.0

    # Inconsistent players have higher variance
    consistency = player_data.get("finish_consistency", 0.5) or 0.5
    std_dev += consistency * 0.5

    return expected, std_dev


def generate_round_score_prop(
    player_data: Dict,
    line: float = None,
    round_num: int = 1,
    course_par: int = 72,
    course_scoring_avg: float = 71.0
) -> RoundScoreProp:
    """Generate a round score over/under prop."""
    from scipy import stats

    expected, std_dev = estimate_expected_round_score(
        player_data, course_par, course_scoring_avg, round_num
    )

    # Auto-generate line if not provided (round to nearest 0.5)
    if line is None:
        line = round(expected * 2) / 2

    # Calculate probabilities using normal distribution
    # Over means scoring higher than line (worse)
    # Under means scoring lower than line (better)
    under_prob = stats.norm.cdf(line, expected, std_dev)
    over_prob = 1 - under_prob

    # Calculate odds with vig
    over_odds = prob_to_american(over_prob * 1.02)  # Slight vig
    under_odds = prob_to_american(under_prob * 1.02)

    # Recommendation based on edge
    if over_prob > 0.55:
        recommendation = "OVER"
    elif under_prob > 0.55:
        recommendation = "UNDER"
    else:
        recommendation = "PASS"

    return RoundScoreProp(
        player_name=player_data.get("player_name", "Unknown"),
        round_num=round_num,
        line=line,
        expected_score=expected,
        over_prob=over_prob,
        under_prob=under_prob,
        over_odds=over_odds,
        under_odds=under_odds,
        recommendation=recommendation
    )


# =============================================================================
# PARLAY CALCULATOR
# =============================================================================

@dataclass
class ParlayLeg:
    """A single leg of a parlay."""
    description: str
    probability: float
    odds: int


@dataclass
class Parlay:
    """A parlay bet combining multiple legs."""
    legs: List[ParlayLeg]
    combined_prob: float
    combined_odds: int
    payout_per_unit: float  # e.g., $10 pays $X


def calculate_parlay(legs: List[ParlayLeg]) -> Parlay:
    """Calculate combined probability and odds for a parlay."""

    # Combined probability is product of individual probs
    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg.probability

    # Convert to odds
    combined_odds = prob_to_american(combined_prob)

    # Calculate payout
    if combined_odds > 0:
        payout = 10 + (10 * combined_odds / 100)
    else:
        payout = 10 + (10 * 100 / abs(combined_odds))

    return Parlay(
        legs=legs,
        combined_prob=combined_prob,
        combined_odds=combined_odds,
        payout_per_unit=round(payout, 2)
    )


def generate_suggested_parlays(
    players_df: pd.DataFrame,
    num_parlays: int = 3
) -> List[Dict]:
    """Generate suggested parlay cards based on model predictions."""

    suggested = []

    if players_df.empty:
        return suggested

    # Parlay 1: "Chalk Attack" - Top 3 favorites to finish Top 20
    if "top20_prob" in players_df.columns:
        top3 = players_df.head(3)
        legs = []
        for _, p in top3.iterrows():
            prob = p.get("top20_prob", 0.5) or 0.5
            legs.append(ParlayLeg(
                description=f"{p['player_name']} Top 20",
                probability=prob,
                odds=prob_to_american(prob)
            ))
        if legs:
            parlay = calculate_parlay(legs)
            suggested.append({
                "name": "Chalk Attack",
                "description": "Top 3 favorites all finish Top 20",
                "parlay": parlay
            })

    # Parlay 2: "Value Hunters" - Mid-tier players to make cut
    if len(players_df) > 20:
        mid_tier = players_df.iloc[15:25]
        legs = []
        for _, p in mid_tier.head(3).iterrows():
            prob = min(0.85, (p.get("top20_prob", 0.3) or 0.3) * 1.5 + 0.2)
            legs.append(ParlayLeg(
                description=f"{p['player_name']} Make Cut",
                probability=prob,
                odds=prob_to_american(prob)
            ))
        if legs:
            parlay = calculate_parlay(legs)
            suggested.append({
                "name": "Value Hunters",
                "description": "Mid-tier players all make the cut",
                "parlay": parlay
            })

    # Parlay 3: "Hot Hands" - Players with best form to finish Top 10
    if "form_trend" in players_df.columns and "top10_prob" in players_df.columns:
        hot_players = players_df.nlargest(5, "form_trend").head(3)
        legs = []
        for _, p in hot_players.iterrows():
            prob = p.get("top10_prob", 0.2) or 0.2
            if prob > 0.1:
                legs.append(ParlayLeg(
                    description=f"{p['player_name']} Top 10",
                    probability=prob,
                    odds=prob_to_american(prob)
                ))
        if len(legs) >= 2:
            parlay = calculate_parlay(legs)
            suggested.append({
                "name": "Hot Hands",
                "description": "Hottest players all finish Top 10",
                "parlay": parlay
            })

    return suggested[:num_parlays]
