#!/usr/bin/env python3
"""
LLM-Assisted Betting Recommendations
=====================================

Uses computed edges from model vs sportsbook odds to generate
betting recommendations. The LLM serves as an explanation/recommendation
layer, NOT a probability engine.

Hard guardrails:
- Only choose from computed legs (never invent lines/odds)
- All probabilities come from the model
- All odds come from sportsbooks

Risk Profiles:
- conservative: Low variance, high confidence, small edges
- balanced: Mix of value and safety
- aggressive: Higher variance, chasing bigger edges
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
ODDS_DIR = PROJECT_ROOT / "data" / "odds"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LIVE_DIR = PROJECT_ROOT / "data" / "live"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class MarketType(str, Enum):
    WINNER = "winner"
    H2H = "h2h"
    ROUND_SCORE = "round_score"
    TOP5 = "top5"
    TOP10 = "top10"
    TOP20 = "top20"


@dataclass
class BettingLeg:
    """A single betting leg with edge calculation."""
    market: MarketType
    player_name: str
    selection: str  # e.g., "Win", "Over 69.5", "vs Player B"
    model_prob: float
    sportsbook_odds: int  # American odds
    implied_prob: float
    edge: float  # model_prob - implied_prob
    confidence: float  # 0-1 confidence in the edge
    book: str
    notes: str = ""
    player_b: str = ""  # For H2H
    line: Optional[float] = None  # For O/U

    @property
    def edge_pct(self) -> float:
        return self.edge * 100

    @property
    def ev(self) -> float:
        """Expected value per unit bet."""
        if self.sportsbook_odds > 0:
            profit = self.sportsbook_odds / 100
        else:
            profit = 100 / abs(self.sportsbook_odds)
        return (self.model_prob * profit) - ((1 - self.model_prob) * 1)

    def to_dict(self) -> Dict:
        return {
            "market": self.market.value,
            "player_name": self.player_name,
            "selection": self.selection,
            "model_prob": round(self.model_prob, 4),
            "sportsbook_odds": self.sportsbook_odds,
            "implied_prob": round(self.implied_prob, 4),
            "edge": round(self.edge, 4),
            "edge_pct": round(self.edge_pct, 2),
            "ev": round(self.ev, 4),
            "confidence": round(self.confidence, 2),
            "book": self.book,
            "notes": self.notes,
        }


@dataclass
class BettingSlip:
    """A recommended bet (single or parlay)."""
    legs: List[BettingLeg]
    risk_profile: RiskProfile
    combined_prob: float
    combined_odds: int
    combined_edge: float
    ev_per_unit: float
    reasoning: str
    risk_notes: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)

    @property
    def is_parlay(self) -> bool:
        return len(self.legs) > 1

    @property
    def leg_count(self) -> int:
        return len(self.legs)

    def to_dict(self) -> Dict:
        return {
            "legs": [leg.to_dict() for leg in self.legs],
            "is_parlay": self.is_parlay,
            "leg_count": self.leg_count,
            "risk_profile": self.risk_profile.value,
            "combined_prob": round(self.combined_prob, 4),
            "combined_odds": self.combined_odds,
            "combined_edge": round(self.combined_edge, 4),
            "ev_per_unit": round(self.ev_per_unit, 4),
            "reasoning": self.reasoning,
            "risk_notes": self.risk_notes,
            "alternatives": self.alternatives,
        }


def american_to_implied_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def implied_prob_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def calculate_parlay_odds(legs: List[BettingLeg]) -> Tuple[float, int]:
    """Calculate combined probability and American odds for parlay."""
    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg.model_prob

    combined_odds = implied_prob_to_american(combined_prob)
    return combined_prob, combined_odds


def load_model_predictions(tournament_id: str) -> Optional[pd.DataFrame]:
    """Load model predictions for tournament."""
    patterns = [
        OUTPUTS_DIR / f"{tournament_id}_predictions.csv",
        OUTPUTS_DIR / f"{tournament_id.lower()}_predictions.csv",
        OUTPUTS_DIR / "latest_predictions.csv",
    ]

    for f in OUTPUTS_DIR.glob("*_predictions.csv"):
        if tournament_id.lower() in f.stem.lower():
            patterns.insert(0, f)

    # Also check for tournament name-based files
    for f in OUTPUTS_DIR.glob("*_latest.csv"):
        patterns.append(f)

    for path in patterns:
        if path.exists():
            return pd.read_csv(path)

    return None


def load_sportsbook_lines(tournament_id: str) -> Optional[pd.DataFrame]:
    """Load sportsbook lines for tournament."""
    path = ODDS_DIR / f"prop_lines_{tournament_id}.csv"
    if path.exists():
        return pd.read_csv(path)
    return None


def load_live_leaderboard(tournament_id: str) -> Optional[pd.DataFrame]:
    """Load live leaderboard data for tournament state awareness."""
    patterns = [
        LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv",
        LIVE_DIR / f"leaderboard_{tournament_id}.csv",
    ]

    for path in patterns:
        if path.exists():
            try:
                df = pd.read_csv(path)
                return df
            except Exception:
                continue
    return None


def get_tournament_state(leaderboard: pd.DataFrame) -> Dict:
    """Analyze current tournament state from leaderboard."""
    if leaderboard is None or leaderboard.empty:
        return {
            "round": 1,
            "is_live": False,
            "leader_score": 0,
            "cut_made": False,
            "contender_threshold": 999,
        }

    current_round = int(leaderboard["current_round"].max()) if "current_round" in leaderboard.columns else 1

    # Get leader's score
    leader_score = leaderboard["total_numeric"].min() if "total_numeric" in leaderboard.columns else 0

    # Determine if cut has been made
    cut_made = current_round >= 3

    # Calculate contender threshold based on round
    # R1-R2: Anyone could win
    # R3: Within 6 shots of lead
    # R4: Within 5 shots with holes remaining consideration
    if current_round <= 2:
        contender_threshold = leader_score + 10
    elif current_round == 3:
        contender_threshold = leader_score + 6
    else:
        # R4 - tighter threshold
        contender_threshold = leader_score + 5

    # Check if tournament is actively in progress
    thru_col = leaderboard["thru"].astype(str) if "thru" in leaderboard.columns else pd.Series(["F"] * len(leaderboard))
    is_live = not all(t.upper() in ["F", "F*", "18", ""] for t in thru_col)

    return {
        "round": current_round,
        "is_live": is_live,
        "leader_score": leader_score,
        "cut_made": cut_made,
        "contender_threshold": contender_threshold,
    }


def get_contenders(leaderboard: pd.DataFrame, state: Dict) -> List[str]:
    """Get list of players who are realistic contenders based on current state."""
    if leaderboard is None or leaderboard.empty:
        return []

    # Filter to contenders
    threshold = state["contender_threshold"]
    contenders = leaderboard[leaderboard["total_numeric"] <= threshold].copy()

    # Sort by position
    contenders = contenders.sort_values("total_numeric")

    return contenders["player_name"].tolist()


def parse_american_odds(odds_str) -> Optional[int]:
    """Parse American odds from various formats."""
    if pd.isna(odds_str) or odds_str == "":
        return None

    odds_str = str(odds_str).strip()

    # Handle formats: "+150", "-110", "150", etc.
    odds_str = odds_str.replace(",", "")

    try:
        if odds_str.startswith("+"):
            return int(odds_str[1:])
        elif odds_str.startswith("-"):
            return int(odds_str)
        else:
            val = int(float(odds_str))
            return val if val != 0 else None
    except (ValueError, TypeError):
        return None


def normalize_name(name: str) -> str:
    """Normalize player name for matching.

    Handles both "First Last" and "Last, First" formats.
    """
    if pd.isna(name):
        return ""
    name = str(name).lower().strip()

    # Handle "Last, First" format
    if "," in name:
        parts = name.split(",", 1)
        if len(parts) == 2:
            name = f"{parts[1].strip()} {parts[0].strip()}"

    # Remove common suffixes
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        name = name.replace(suffix, "")
    # Remove special characters but keep spaces
    name = "".join(c for c in name if c.isalnum() or c.isspace())
    # Collapse multiple spaces
    name = " ".join(name.split())
    return name


def estimate_live_win_probability(
    position_str: str,
    total_numeric: float,
    leader_score: float,
    round_num: int,
    holes_remaining: int,
) -> float:
    """Estimate win probability based on current position and shots back.

    Uses empirical data approximations:
    - Leader going into final round: ~25-30% to win
    - 1 shot back: ~15-20%
    - 2 shots back: ~10-12%
    - 3 shots back: ~5-7%
    - 4+ shots back: exponential decay

    Adjusted for holes remaining in final round.
    """
    shots_back = total_numeric - leader_score

    # Base probabilities by shots back (going into final round)
    base_probs = {
        0: 0.28,  # Leader
        1: 0.18,
        2: 0.11,
        3: 0.06,
        4: 0.03,
        5: 0.015,
    }

    if shots_back <= 0:
        base_prob = base_probs[0]
    elif shots_back in base_probs:
        base_prob = base_probs[shots_back]
    else:
        # Exponential decay for 6+ back
        base_prob = 0.015 * (0.4 ** (shots_back - 5))

    # Adjust for round
    if round_num < 4:
        # Earlier rounds - more variance, normalize probabilities
        round_factor = 1.0 + (4 - round_num) * 0.2
        base_prob = base_prob * round_factor
    elif round_num == 4:
        # Final round - adjust for holes remaining
        # More holes = more variance = better chance for those behind
        if holes_remaining > 0:
            variance_factor = 1.0 + (holes_remaining / 18) * 0.3
            if shots_back > 0:
                base_prob = base_prob * variance_factor

    # Cap at reasonable bounds
    return max(0.001, min(0.5, base_prob))


def compute_winner_edges(
    predictions: pd.DataFrame,
    lines: pd.DataFrame,
    leaderboard: Optional[pd.DataFrame] = None,
    state: Optional[Dict] = None,
) -> List[BettingLeg]:
    """Compute edges for winner market, filtered by contenders if live."""
    legs = []

    # Get winner lines
    winner_lines = lines[lines["market"] == "winner"].copy()
    if winner_lines.empty:
        return legs

    # Normalize names
    predictions = predictions.copy()
    predictions["name_key"] = predictions["player_name"].apply(normalize_name)
    winner_lines["name_key"] = winner_lines["player_name"].apply(normalize_name)

    # If we have live leaderboard, use live odds and compute live probabilities
    live_data = {}
    contender_names = set()
    use_live_probs = False

    if leaderboard is not None and not leaderboard.empty and state:
        round_num = state.get("round", 1)
        leader_score = state.get("leader_score", 0)

        # Use live probabilities in Round 3+
        use_live_probs = round_num >= 3

        # Get contenders
        contenders = get_contenders(leaderboard, state)
        contender_names = {normalize_name(n) for n in contenders}

        # Get live data from leaderboard
        for _, row in leaderboard.iterrows():
            name_key = normalize_name(str(row.get("player_name", "")))
            odds = parse_american_odds(row.get("odds_to_win"))

            # Calculate holes remaining
            thru = str(row.get("thru", "")).upper()
            if thru in ["F", "F*", ""]:
                holes_remaining = 0
            else:
                try:
                    holes_remaining = 18 - int(thru)
                except (ValueError, TypeError):
                    holes_remaining = 9  # Assume mid-round

            total_numeric = float(row.get("total_numeric", 0))

            if name_key:
                live_data[name_key] = {
                    "odds": odds,
                    "position": row.get("position", ""),
                    "total": row.get("total", "E"),
                    "total_numeric": total_numeric,
                    "thru": row.get("thru", ""),
                    "holes_remaining": holes_remaining,
                    "movement": row.get("movement", ""),
                    "live_prob": estimate_live_win_probability(
                        str(row.get("position", "")),
                        total_numeric,
                        leader_score,
                        round_num,
                        holes_remaining,
                    ) if use_live_probs else None,
                }

    # Find prob column for pre-tournament baseline
    prob_col = None
    for col in ["win_prob", "win_probability", "predicted_win_prob", "ensemble_win_prob_normalized"]:
        if col in predictions.columns:
            prob_col = col
            break

    # Match and compute edges
    processed_names = set()

    for _, line in winner_lines.iterrows():
        name_key = line["name_key"]

        # Skip if already processed
        if name_key in processed_names:
            continue
        processed_names.add(name_key)

        # If we have contenders filter, apply it
        if contender_names and name_key not in contender_names:
            continue

        # Get live data if available
        player_live = live_data.get(name_key, {})

        # Determine model probability
        if use_live_probs and player_live.get("live_prob") is not None:
            model_prob = player_live["live_prob"]
            prob_source = "live_estimate"
        elif prob_col:
            match = predictions[predictions["name_key"] == name_key]
            if match.empty:
                continue
            model_prob = float(match.iloc[0][prob_col])
            prob_source = "pre_tournament"
        else:
            continue

        # Determine odds to use
        if player_live.get("odds"):
            odds = player_live["odds"]
            position = player_live["position"]
            total = player_live["total"]
            thru = player_live["thru"]
            movement = player_live["movement"]
            book = "FANDUEL_LIVE"
            notes = f"Pos: {position} ({total}) thru {thru}"
            if movement:
                notes += f" [{movement}]"
            if prob_source == "live_estimate":
                notes += " | Live prob estimate"
        else:
            odds = int(line["odds"]) if pd.notna(line.get("odds")) else None
            if odds is None:
                continue
            book = str(line.get("book", "DRAFTKINGS"))
            notes = "Pre-tournament odds"

        implied_prob = american_to_implied_prob(odds)
        edge = model_prob - implied_prob

        # Confidence calculation
        if prob_source == "live_estimate":
            # Higher confidence for live estimates in late rounds
            shots_back = player_live.get("total_numeric", 0) - state.get("leader_score", 0)
            if shots_back <= 0:
                confidence = 0.85  # Leader
            elif shots_back <= 2:
                confidence = 0.75
            elif shots_back <= 4:
                confidence = 0.60
            else:
                confidence = 0.45
        else:
            # Lower confidence for pre-tournament probs used live
            match = predictions[predictions["name_key"] == name_key]
            if not match.empty:
                rank = int(match.iloc[0].get("predicted_rank", match.iloc[0].get("rank", 50)))
                confidence = max(0.2, min(0.5, 1 - (rank / 100)))
            else:
                confidence = 0.3

        legs.append(BettingLeg(
            market=MarketType.WINNER,
            player_name=str(line["player_name"]),
            selection="To Win",
            model_prob=model_prob,
            sportsbook_odds=odds,
            implied_prob=implied_prob,
            edge=edge,
            confidence=confidence,
            book=book,
            notes=notes,
        ))

    return legs


def compute_h2h_edges(
    predictions: pd.DataFrame,
    lines: pd.DataFrame,
    leaderboard: Optional[pd.DataFrame] = None,
    state: Optional[Dict] = None,
) -> List[BettingLeg]:
    """Compute edges for head-to-head market, using live positions if available."""
    legs = []

    h2h_lines = lines[lines["market"] == "h2h"].copy()
    if h2h_lines.empty:
        return legs

    predictions = predictions.copy()
    predictions["name_key"] = predictions["player_name"].apply(normalize_name)

    # Build live position lookup if available
    live_positions = {}
    if leaderboard is not None and not leaderboard.empty:
        for _, row in leaderboard.iterrows():
            name_key = normalize_name(str(row.get("player_name", "")))
            if name_key:
                live_positions[name_key] = {
                    "position": row.get("position", ""),
                    "total_numeric": row.get("total_numeric", 0),
                    "thru": row.get("thru", ""),
                }

    # Get ranking column
    rank_col = None
    for col in ["predicted_rank", "rank", "model_rank"]:
        if col in predictions.columns:
            rank_col = col
            break

    if not rank_col:
        return legs

    for _, line in h2h_lines.iterrows():
        player_a = normalize_name(line.get("player_a", ""))
        player_b = normalize_name(line.get("player_b", ""))

        match_a = predictions[predictions["name_key"] == player_a]
        match_b = predictions[predictions["name_key"] == player_b]

        if match_a.empty or match_b.empty:
            continue

        # Use live positions if available, otherwise use model rank
        if player_a in live_positions and player_b in live_positions:
            # Use live score differential
            score_a = live_positions[player_a]["total_numeric"]
            score_b = live_positions[player_b]["total_numeric"]
            score_diff = score_b - score_a  # Positive = A is better (lower score)

            # Convert score diff to probability
            # Each stroke difference ~= 10-15% probability shift
            model_prob_a = 1 / (1 + np.exp(-score_diff * 0.3))

            notes = f"Live: {live_positions[player_a]['position']} vs {live_positions[player_b]['position']}"
        else:
            rank_a = float(match_a.iloc[0][rank_col])
            rank_b = float(match_b.iloc[0][rank_col])

            # Simple probability model: better rank = higher win prob
            rank_diff = rank_b - rank_a  # Positive = A is better
            model_prob_a = 1 / (1 + np.exp(-rank_diff * 0.1))

            notes = f"Model rank {int(rank_a)} vs {int(rank_b)}"

        odds_a = int(line.get("odds_a", 0)) if pd.notna(line.get("odds_a")) else 0
        if odds_a == 0:
            continue

        implied_prob_a = american_to_implied_prob(odds_a)
        edge_a = model_prob_a - implied_prob_a

        # Confidence based on how clear the edge is
        if player_a in live_positions and player_b in live_positions:
            confidence = min(1.0, abs(score_diff) / 3)  # 3 strokes = high confidence
        else:
            confidence = min(1.0, abs(model_prob_a - 0.5) * 2)

        if edge_a > 0.02:  # Min 2% edge for H2H
            legs.append(BettingLeg(
                market=MarketType.H2H,
                player_name=str(line.get("player_a", "")),
                selection=f"beats {line.get('player_b', '')}",
                model_prob=model_prob_a,
                sportsbook_odds=odds_a,
                implied_prob=implied_prob_a,
                edge=edge_a,
                confidence=confidence,
                book=str(line.get("book", "DRAFTKINGS")),
                player_b=str(line.get("player_b", "")),
                notes=notes,
            ))

        # Check player B side
        odds_b = int(line.get("odds_b", 0)) if pd.notna(line.get("odds_b")) else 0
        if odds_b != 0:
            model_prob_b = 1 - model_prob_a
            implied_prob_b = american_to_implied_prob(odds_b)
            edge_b = model_prob_b - implied_prob_b

            if edge_b > 0.02:
                legs.append(BettingLeg(
                    market=MarketType.H2H,
                    player_name=str(line.get("player_b", "")),
                    selection=f"beats {line.get('player_a', '')}",
                    model_prob=model_prob_b,
                    sportsbook_odds=odds_b,
                    implied_prob=implied_prob_b,
                    edge=edge_b,
                    confidence=confidence,
                    book=str(line.get("book", "DRAFTKINGS")),
                    player_b=str(line.get("player_a", "")),
                    notes=notes,
                ))

    return legs


def compute_all_edges(tournament_id: str) -> Tuple[List[BettingLeg], Dict]:
    """Compute all edges across markets, with tournament state awareness."""
    predictions = load_model_predictions(tournament_id)
    lines = load_sportsbook_lines(tournament_id)
    leaderboard = load_live_leaderboard(tournament_id)

    state = get_tournament_state(leaderboard) if leaderboard is not None else {}

    if predictions is None:
        return [], state

    # If no lines file, try to build edges from live odds only
    if lines is None or lines.empty:
        if leaderboard is not None and "odds_to_win" in leaderboard.columns:
            # Create synthetic lines from live leaderboard
            lines = pd.DataFrame({
                "market": "winner",
                "player_name": leaderboard["player_name"],
                "odds": leaderboard["odds_to_win"].apply(parse_american_odds),
                "book": "FANDUEL_LIVE",
            })
            lines = lines[lines["odds"].notna()]

    if lines is None or lines.empty:
        return [], state

    all_legs = []
    all_legs.extend(compute_winner_edges(predictions, lines, leaderboard, state))
    all_legs.extend(compute_h2h_edges(predictions, lines, leaderboard, state))

    # Sort by edge descending
    all_legs.sort(key=lambda x: x.edge, reverse=True)

    return all_legs, state


def filter_legs_by_profile(legs: List[BettingLeg], profile: RiskProfile) -> List[BettingLeg]:
    """Filter legs based on risk profile constraints."""
    if profile == RiskProfile.CONSERVATIVE:
        # High confidence, lower variance
        return [
            leg for leg in legs
            if leg.confidence >= 0.5
            and leg.edge >= 0.02  # Min 2% edge
            and leg.model_prob >= 0.15  # Not super longshots
        ]

    elif profile == RiskProfile.BALANCED:
        # Medium constraints
        return [
            leg for leg in legs
            if leg.confidence >= 0.3
            and leg.edge >= 0.03  # Min 3% edge
        ]

    else:  # AGGRESSIVE
        # Chase bigger edges, accept more variance
        return [
            leg for leg in legs
            if leg.edge >= 0.05  # Min 5% edge
            and leg.ev > 0  # Must be +EV
        ]


def generate_reasoning(leg: BettingLeg, profile: RiskProfile) -> str:
    """Generate human-readable reasoning for a pick."""
    parts = []

    # Edge explanation
    if leg.edge_pct >= 10:
        parts.append(f"Strong {leg.edge_pct:.1f}% edge over the book")
    elif leg.edge_pct >= 5:
        parts.append(f"Solid {leg.edge_pct:.1f}% edge")
    else:
        parts.append(f"Modest {leg.edge_pct:.1f}% edge")

    # Probability context
    if leg.model_prob >= 0.3:
        parts.append(f"Model gives {leg.model_prob*100:.0f}% chance (book implies {leg.implied_prob*100:.0f}%)")
    else:
        parts.append(f"Model: {leg.model_prob*100:.1f}% vs Book: {leg.implied_prob*100:.1f}%")

    # EV context
    if leg.ev > 0.1:
        parts.append(f"Excellent +{leg.ev*100:.0f}% EV")
    elif leg.ev > 0:
        parts.append(f"+{leg.ev*100:.1f}% EV")

    # Market specific
    if leg.notes:
        parts.append(leg.notes)

    return ". ".join(parts) + "."


def generate_risk_notes(leg: BettingLeg) -> List[str]:
    """Generate risk warnings for a pick."""
    notes = []

    if leg.model_prob < 0.1:
        notes.append("Low probability event - high variance")

    if leg.market == MarketType.WINNER:
        notes.append("Winner markets have highest variance")

    if leg.confidence < 0.4:
        notes.append("Lower confidence pick - edge may be smaller than calculated")

    if abs(leg.sportsbook_odds) > 1000:
        notes.append("Long odds - consider smaller stake")

    return notes


def generate_alternatives(leg: BettingLeg, all_legs: List[BettingLeg]) -> List[str]:
    """Suggest alternative picks."""
    alternatives = []

    # Find similar market alternatives
    same_market = [
        l for l in all_legs
        if l.market == leg.market
        and l.player_name != leg.player_name
        and l.edge > 0.02
    ][:2]

    for alt in same_market:
        alternatives.append(
            f"{alt.player_name} ({alt.selection}) - {alt.edge_pct:.1f}% edge @ {alt.sportsbook_odds:+d}"
        )

    return alternatives


def generate_recommendations(
    tournament_id: str,
    profile: RiskProfile = RiskProfile.BALANCED,
    max_slips: int = 5,
    include_parlays: bool = True,
    max_parlay_legs: int = 3,
) -> List[BettingSlip]:
    """Generate betting recommendations based on computed edges."""
    all_legs, state = compute_all_edges(tournament_id)

    if not all_legs:
        return []

    # Add state context to reasoning
    round_num = state.get("round", 1)
    is_live = state.get("is_live", False)

    # Filter by profile
    viable_legs = filter_legs_by_profile(all_legs, profile)

    if not viable_legs:
        # Fallback to best available
        viable_legs = [leg for leg in all_legs if leg.edge > 0][:10]

    recommendations = []

    # Generate single-bet recommendations
    for leg in viable_legs[:max_slips]:
        reasoning = generate_reasoning(leg, profile)
        risk_notes = generate_risk_notes(leg)
        alternatives = generate_alternatives(leg, all_legs)

        slip = BettingSlip(
            legs=[leg],
            risk_profile=profile,
            combined_prob=leg.model_prob,
            combined_odds=leg.sportsbook_odds,
            combined_edge=leg.edge,
            ev_per_unit=leg.ev,
            reasoning=reasoning,
            risk_notes=risk_notes,
            alternatives=alternatives,
        )
        recommendations.append(slip)

    # Generate parlays if requested
    if include_parlays and len(viable_legs) >= 2:
        # 2-leg parlay from best non-correlated legs
        parlay_candidates = []
        used_players = set()

        for leg in viable_legs:
            # Avoid same player in parlay (correlation)
            if leg.player_name not in used_players:
                parlay_candidates.append(leg)
                used_players.add(leg.player_name)
                if leg.player_b:
                    used_players.add(leg.player_b)

            if len(parlay_candidates) >= max_parlay_legs:
                break

        if len(parlay_candidates) >= 2:
            parlay_legs = parlay_candidates[:2]
            combined_prob, combined_odds = calculate_parlay_odds(parlay_legs)

            # Calculate parlay EV
            if combined_odds > 0:
                profit = combined_odds / 100
            else:
                profit = 100 / abs(combined_odds)
            ev = (combined_prob * profit) - ((1 - combined_prob) * 1)

            # Implied parlay prob from book
            implied_parlay = 1.0
            for leg in parlay_legs:
                implied_parlay *= leg.implied_prob
            combined_edge = combined_prob - implied_parlay

            parlay_slip = BettingSlip(
                legs=parlay_legs,
                risk_profile=profile,
                combined_prob=combined_prob,
                combined_odds=combined_odds,
                combined_edge=combined_edge,
                ev_per_unit=ev,
                reasoning=f"{len(parlay_legs)}-leg parlay combining best uncorrelated edges. Combined {combined_prob*100:.1f}% model probability vs {implied_parlay*100:.1f}% implied.",
                risk_notes=[
                    "Parlay variance is multiplicative - use smaller stakes",
                    "All legs must hit for payout",
                ],
                alternatives=[],
            )
            recommendations.append(parlay_slip)

    return recommendations


def format_slip_for_display(slip: BettingSlip) -> Dict:
    """Format slip for dashboard display."""
    return {
        "type": "Parlay" if slip.is_parlay else "Single",
        "legs": [
            {
                "player": leg.player_name,
                "selection": leg.selection,
                "odds": f"{leg.sportsbook_odds:+d}",
                "edge": f"{leg.edge_pct:.1f}%",
                "book": leg.book,
            }
            for leg in slip.legs
        ],
        "combined_odds": f"{slip.combined_odds:+d}",
        "combined_prob": f"{slip.combined_prob*100:.1f}%",
        "edge": f"{slip.combined_edge*100:.1f}%",
        "ev": f"{slip.ev_per_unit*100:.1f}%",
        "reasoning": slip.reasoning,
        "risk_notes": slip.risk_notes,
        "profile": slip.risk_profile.value,
    }


def get_edge_summary(tournament_id: str) -> Dict:
    """Get summary of available edges."""
    all_legs, state = compute_all_edges(tournament_id)

    if not all_legs:
        return {
            "total_legs": 0,
            "positive_edge_legs": 0,
            "best_edge": 0,
            "avg_edge": 0,
            "markets": {},
            "tournament_state": state,
        }

    positive = [leg for leg in all_legs if leg.edge > 0]

    by_market = {}
    for leg in positive:
        market = leg.market.value
        if market not in by_market:
            by_market[market] = {"count": 0, "best_edge": 0, "avg_edge": 0, "edges": []}
        by_market[market]["count"] += 1
        by_market[market]["edges"].append(leg.edge)
        by_market[market]["best_edge"] = max(by_market[market]["best_edge"], leg.edge)

    for market, data in by_market.items():
        data["avg_edge"] = np.mean(data["edges"]) if data["edges"] else 0
        del data["edges"]

    return {
        "total_legs": len(all_legs),
        "positive_edge_legs": len(positive),
        "best_edge": max(leg.edge for leg in all_legs) if all_legs else 0,
        "avg_edge": np.mean([leg.edge for leg in positive]) if positive else 0,
        "markets": by_market,
        "tournament_state": state,
    }


if __name__ == "__main__":
    import sys
    tournament_id = sys.argv[1] if len(sys.argv) > 1 else "R2026005"

    print(f"Generating recommendations for {tournament_id}...")

    # Get edge summary
    summary = get_edge_summary(tournament_id)

    # Show tournament state
    state = summary.get("tournament_state", {})
    if state:
        print(f"\nTournament State:")
        print(f"  Round: {state.get('round', '?')}")
        print(f"  Live: {'Yes' if state.get('is_live') else 'No'}")
        print(f"  Leader Score: {state.get('leader_score', '?')}")
        print(f"  Contender Threshold: {state.get('contender_threshold', '?')}")

    print(f"\nEdge Summary:")
    print(f"  Total legs scanned: {summary['total_legs']}")
    print(f"  Positive edge legs: {summary['positive_edge_legs']}")
    print(f"  Best edge: {summary['best_edge']*100:.1f}%")
    print(f"  Avg positive edge: {summary['avg_edge']*100:.1f}%")

    # Generate for each profile
    for profile in RiskProfile:
        print(f"\n{'='*50}")
        print(f"{profile.value.upper()} RECOMMENDATIONS")
        print("="*50)

        recs = generate_recommendations(tournament_id, profile, max_slips=3)

        if not recs:
            print("  No recommendations available")
            continue

        for i, slip in enumerate(recs, 1):
            display = format_slip_for_display(slip)
            print(f"\n#{i} {display['type']}")
            for leg in display['legs']:
                print(f"  • {leg['player']} {leg['selection']} @ {leg['odds']} ({leg['book']})")
                print(f"    Edge: {leg['edge']}")
            print(f"  Combined: {display['combined_odds']} | Edge: {display['edge']} | EV: {display['ev']}")
            print(f"  {display['reasoning']}")
            if display['risk_notes']:
                print(f"  ⚠️ {' | '.join(display['risk_notes'])}")
