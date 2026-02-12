#!/usr/bin/env python3
"""
Fantasy Golf Usage Optimizer
=============================
Strategic optimizer for 3-use player allocation across a season.

The core insight: Scottie Scheffler might be the best pick every week,
but you only get 3 uses. This module helps decide WHEN to use elite players.

Key Features:
- Tracks remaining uses per player
- Scores tournaments by importance and purse
- Recommends optimal usage timing
- Identifies "must use" vs "save" weeks

Usage:
    optimizer = UsageOptimizer()
    recommendation = optimizer.should_use_player("Scottie Scheffler", "The American Express")
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

# Project paths
PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


class TournamentCalendar:
    """PGA Tour tournament calendar with payout-based importance scores."""

    # Schedule file path
    SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"

    # Cache for schedule data
    _schedule_df = None

    # Fallback importance for tournaments not in schedule (based on type keywords)
    TYPE_IMPORTANCE = {
        "major": 10,
        "playoff": 9,
        "signature": 8,
        "standard": 5,
        "opposite": 3,
        "team": 4,
    }

    @classmethod
    def _load_schedule(cls) -> pd.DataFrame:
        """Load and cache the schedule data."""
        if cls._schedule_df is None:
            if cls.SCHEDULE_FILE.exists():
                df = pd.read_csv(cls.SCHEDULE_FILE)
                # Parse money columns
                for col in ['purse', 'winner_share']:
                    if col in df.columns:
                        df[col] = df[col].apply(cls._parse_money)
                # Create lookup key
                df['name_key'] = df['tournament_name'].str.lower().str.strip()
                cls._schedule_df = df
            else:
                cls._schedule_df = pd.DataFrame()
        return cls._schedule_df

    @staticmethod
    def _parse_money(val) -> float:
        """Convert money strings like '$9,600,000.00' to float."""
        if pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        return float(str(val).replace("$", "").replace(",", ""))

    @classmethod
    def get_tournament_info(cls, tournament_name: str) -> Dict:
        """Get full tournament info from schedule."""
        schedule = cls._load_schedule()
        if schedule.empty:
            return {}

        name_lower = tournament_name.lower().strip()

        # Try exact match first
        match = schedule[schedule['name_key'] == name_lower]

        # Try partial match
        if match.empty:
            match = schedule[
                schedule['name_key'].str.contains(name_lower[:15], na=False) |
                schedule['tournament_name'].str.lower().str.contains(name_lower[:15], na=False)
            ]

        if not match.empty:
            row = match.iloc[0]
            return {
                "name": row['tournament_name'],
                "week": int(row.get('week', 0)),
                "purse": float(row.get('purse', 0)),
                "winner_share": float(row.get('winner_share', 0)),
                "tournament_type": row.get('tournament_type', 'Standard'),
                "start_date": row.get('start_date'),
            }
        return {}

    @classmethod
    def get_importance(cls, tournament_name: str) -> int:
        """
        Get importance score for a tournament (1-10) based on winner's share payout.

        Scale:
        - $4M+ winner share = 10 (Majors, big signatures)
        - $3.5M+ = 9 (Playoffs, Players)
        - $3M+ = 8 (Signature events)
        - $2M+ = 7
        - $1.5M+ = 5 (Standard events)
        - <$1.5M = 3 (Opposite field)
        """
        info = cls.get_tournament_info(tournament_name)

        if info and info.get('winner_share', 0) > 0:
            winner_share = info['winner_share']

            if winner_share >= 4_000_000:
                return 10
            elif winner_share >= 3_500_000:
                return 9
            elif winner_share >= 3_000_000:
                return 8
            elif winner_share >= 2_000_000:
                return 7
            elif winner_share >= 1_500_000:
                return 5
            else:
                return 3

        # Fallback: check tournament type from name or info
        t_type = info.get('tournament_type', '').lower() if info else ''
        name_lower = tournament_name.lower()

        # Check for major keywords
        if any(m in name_lower for m in ['masters', 'pga championship', 'u.s. open', 'us open', 'open championship', 'players championship']):
            return 10

        # Check type
        for type_key, importance in cls.TYPE_IMPORTANCE.items():
            if type_key in t_type or type_key in name_lower:
                return importance

        return 5  # Default

    @classmethod
    def get_tournament_tier(cls, tournament_name: str) -> str:
        """Get the tier name for a tournament based on payout."""
        importance = cls.get_importance(tournament_name)

        if importance >= 10:
            return "MAJOR"
        elif importance >= 9:
            return "ELITE"
        elif importance >= 7:
            return "SIGNATURE"
        elif importance >= 5:
            return "STANDARD"
        else:
            return "OPPOSITE"

    @classmethod
    def get_payout_info(cls, tournament_name: str) -> Dict:
        """Get purse and winner share for a tournament."""
        info = cls.get_tournament_info(tournament_name)
        return {
            "purse": info.get('purse', 0),
            "winner_share": info.get('winner_share', 0),
            "tournament_type": info.get('tournament_type', 'Unknown'),
        }

    @classmethod
    def count_remaining_majors(cls, current_tournament: str) -> int:
        """Count remaining high-value events (importance >= 10) in the season."""
        schedule = cls._load_schedule()
        if schedule.empty:
            return 4  # Default assumption

        current_info = cls.get_tournament_info(current_tournament)
        current_week = current_info.get('week', 1) if current_info else 1

        # Count tournaments with importance >= 10 after current week
        remaining = 0
        for _, row in schedule.iterrows():
            if row.get('week', 0) > current_week:
                winner_share = row.get('winner_share', 0)
                if winner_share >= 4_000_000:
                    remaining += 1

        return remaining

    @classmethod
    def get_upcoming_important_events(cls, current_tournament: str, look_ahead: int = 5) -> List[Dict]:
        """Get upcoming important events (sorted by payout) to inform usage decisions."""
        schedule = cls._load_schedule()
        if schedule.empty:
            return []

        current_info = cls.get_tournament_info(current_tournament)
        current_week = current_info.get('week', 1) if current_info else 1

        upcoming = []
        for _, row in schedule.iterrows():
            week = row.get('week', 0)
            if week > current_week:
                winner_share = row.get('winner_share', 0)
                upcoming.append({
                    "name": row['tournament_name'],
                    "week": week,
                    "winner_share": winner_share,
                    "importance": cls.get_importance(row['tournament_name']),
                    "tier": cls.get_tournament_tier(row['tournament_name']),
                })

        # Sort by winner_share descending, take top look_ahead
        upcoming.sort(key=lambda x: x['winner_share'], reverse=True)
        return upcoming[:look_ahead]

    @classmethod
    def get_schedule_from_current(cls, current_tournament: str) -> List[Dict]:
        """Get remaining schedule from current tournament onwards."""
        schedule = cls._load_schedule()
        if schedule.empty:
            return []

        current_info = cls.get_tournament_info(current_tournament)
        current_week = current_info.get('week', 1) if current_info else 1

        remaining = []
        for _, row in schedule.iterrows():
            if row.get('week', 0) >= current_week:
                remaining.append({
                    "name": row['tournament_name'],
                    "week": row['week'],
                    "winner_share": row.get('winner_share', 0),
                    "purse": row.get('purse', 0),
                    "importance": cls.get_importance(row['tournament_name']),
                    "tier": cls.get_tournament_tier(row['tournament_name']),
                })

        return remaining


class UsageTracker:
    """Tracks player usage across the season."""

    def __init__(self, tracker_file: Optional[Path] = None):
        self.tracker_file = tracker_file or OUTPUTS_DIR / "player_usage_tracker.json"
        self.usage_data = self._load()

    def _load(self) -> Dict:
        """Load usage data from file."""
        if self.tracker_file.exists():
            with open(self.tracker_file) as f:
                return json.load(f)
        return {"players": {}, "tournaments_used": []}

    def save(self):
        """Save usage data to file."""
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tracker_file, 'w') as f:
            json.dump(self.usage_data, f, indent=2, default=str)

    def record_usage(self, player_name: str, tournament_name: str, tournament_date: str = None):
        """Record that a player was used in a tournament."""
        player_key = player_name.lower().strip()

        if player_key not in self.usage_data["players"]:
            self.usage_data["players"][player_key] = {
                "name": player_name,
                "uses": [],
                "total_uses": 0,
            }

        # Add this usage
        self.usage_data["players"][player_key]["uses"].append({
            "tournament": tournament_name,
            "date": tournament_date or datetime.now().isoformat(),
        })
        self.usage_data["players"][player_key]["total_uses"] += 1

        # Track tournament
        if tournament_name not in self.usage_data["tournaments_used"]:
            self.usage_data["tournaments_used"].append(tournament_name)

        self.save()

    def get_remaining_uses(self, player_name: str, max_uses: int = 3) -> int:
        """Get remaining uses for a player."""
        player_key = player_name.lower().strip()

        if player_key not in self.usage_data["players"]:
            return max_uses

        return max_uses - self.usage_data["players"][player_key]["total_uses"]

    def get_usage_history(self, player_name: str) -> List[Dict]:
        """Get usage history for a player."""
        player_key = player_name.lower().strip()

        if player_key not in self.usage_data["players"]:
            return []

        return self.usage_data["players"][player_key]["uses"]

    def get_all_usage(self) -> Dict[str, int]:
        """Get usage counts for all players."""
        return {
            data["name"]: data["total_uses"]
            for data in self.usage_data["players"].values()
        }

    def get_players_with_uses(self, min_remaining: int = 1, max_uses: int = 3) -> List[str]:
        """Get players with at least min_remaining uses left."""
        players = []

        for player_key, data in self.usage_data["players"].items():
            remaining = max_uses - data["total_uses"]
            if remaining >= min_remaining:
                players.append(data["name"])

        return players


class UsageOptimizer:
    """
    Strategic usage optimizer for fantasy golf.

    Decides WHEN to use elite players based on:
    - Tournament importance
    - Remaining uses
    - Upcoming schedule
    - Player's course fit
    - Elite player protection rules
    """

    # Elite player protection rules matrix
    # Format: (max_world_rank, min_tournament_tier_for_uses)
    # Uses = [3 uses left, 2 uses left, 1 use left]
    # Tier values: MAJOR=10, ELITE=9, SIGNATURE=7, STANDARD=5, OPPOSITE=3
    ELITE_PROTECTION_RULES = {
        # Top 5 OWGR: Sig+ only (3 uses), Major+ only (2 uses), Major only (1 use)
        5: {"uses_3": 7, "uses_2": 9, "uses_1": 10},
        # Top 15 OWGR: Standard OK (3 uses), Sig+ only (2 uses), Major+ only (1 use)
        15: {"uses_3": 5, "uses_2": 7, "uses_1": 9},
        # Top 30 OWGR: Any (3 uses), Standard OK (2 uses), Sig+ only (1 use)
        30: {"uses_3": 0, "uses_2": 5, "uses_1": 7},
        # Others: Any (3 uses), Any (2 uses), Standard OK (1 use)
        999: {"uses_3": 0, "uses_2": 0, "uses_1": 5},
    }

    def __init__(self, max_uses: int = 3):
        """
        Initialize the optimizer.

        Args:
            max_uses: Maximum uses per player per season
        """
        self.max_uses = max_uses
        self.tracker = UsageTracker()
        self.calendar = TournamentCalendar()

        # Load current predictions if available
        self.predictions = None
        self._load_predictions()

    def _load_predictions(self):
        """Load most recent predictions, preferring latest_predictions.csv."""
        # Prefer latest_predictions.csv if it exists (always most recent)
        latest_path = OUTPUTS_DIR / "latest_predictions.csv"
        if latest_path.exists():
            self.predictions = pd.read_csv(latest_path)
            self.current_tournament = "Latest"
        else:
            # Fall back to sorting by name (most recent dated file)
            prediction_files = sorted(OUTPUTS_DIR.glob("*_predictions.csv"), reverse=True)
            if prediction_files:
                self.predictions = pd.read_csv(prediction_files[0])
                self.current_tournament = prediction_files[0].stem.replace("_predictions", "").replace("_", " ").title()

            # Check if predictions are calibrated (calibrated files have *_raw columns)
            self.is_calibrated = 'win_prob_raw' in self.predictions.columns
            if not self.is_calibrated:
                print("  ⚠️ Warning: Predictions may not be calibrated (no *_raw columns found)")
                print("     Re-run predict_tournament.py to get calibrated probabilities")

    def _get_elite_tier(self, world_rank: int) -> int:
        """Get the elite tier threshold for a world rank."""
        if world_rank is None or pd.isna(world_rank):
            return 999
        for threshold in sorted(self.ELITE_PROTECTION_RULES.keys()):
            if world_rank <= threshold:
                return threshold
        return 999

    def check_elite_protection(
        self,
        world_rank: int,
        remaining_uses: int,
        tournament_importance: int
    ) -> Tuple[bool, str]:
        """
        Check if using an elite player at this tournament violates protection rules.

        Returns:
            Tuple of (is_allowed, reason_string)
        """
        tier = self._get_elite_tier(world_rank)
        rules = self.ELITE_PROTECTION_RULES.get(tier, self.ELITE_PROTECTION_RULES[999])

        uses_key = f"uses_{remaining_uses}"
        min_importance = rules.get(uses_key, 0)

        if tournament_importance < min_importance:
            tier_names = {10: "MAJOR", 9: "ELITE", 7: "SIGNATURE", 5: "STANDARD"}
            min_tier_name = tier_names.get(min_importance, f"importance {min_importance}+")
            return False, f"Top-{tier} player with {remaining_uses} use(s) left should only play {min_tier_name} events"

        return True, ""


    def _compute_future_value_penalty(
        self,
        remaining_uses: int,
        current_importance: int,
        upcoming_events: List[Dict],
    ) -> Tuple[float, List[str]]:
        """
        Penalize using a player now if there are more valuable events ahead and not enough
        remaining uses.
        """
        higher_events = [e for e in upcoming_events if e.get("importance", 0) > current_importance]
        if not higher_events:
            return 0.0, []

        # If remaining uses are scarce relative to better events, apply penalty
        if remaining_uses <= len(higher_events):
            gaps = [e["importance"] - current_importance for e in higher_events]
            avg_gap = float(np.mean(gaps)) if gaps else 0.0
            penalty = 5 + (avg_gap * 3)
            names = [e.get("name", "") for e in higher_events[:3]]
            return penalty, names

        return 0.0, []



    def get_player_value(self, player_name: str) -> Optional[Dict]:
        """Get player's value metrics from current predictions."""
        if self.predictions is None:
            return None

        # Fuzzy match player
        matches = self.predictions[
            self.predictions['player_name'].str.lower().str.contains(player_name.lower(), na=False)
        ]

        if len(matches) == 0:
            return None

        player = matches.iloc[0]

        return {
            "name": player['player_name'],
            "win_prob": player.get('win_prob', 0),
            "top5_prob": player.get('top5_prob', 0),
            "top10_prob": player.get('top10_prob', 0),
            "expected_value": player.get('expected_value', 0),
            "world_rank": player.get('world_rank'),
            "course_fit": player.get('dg_fit_total', 0),
            "cut_prob": player.get('cut_prob', 0.5),
            "cut_risk": player.get('cut_risk', 'UNKNOWN'),
            # Momentum / hot hand features
            "hot_hand_flag": player.get('hot_hand_flag', False),
            "hot_hand_score": player.get('hot_hand_score', 0),
            "momentum_trend": player.get('momentum_trend', 'NEUTRAL'),
            "consecutive_top10s": player.get('consecutive_top10s', 0),
            "consecutive_cuts": player.get('consecutive_cuts', 0),
        }

    def should_use_player(
        self,
        player_name: str,
        tournament_name: str,
        force_analysis: bool = False
    ) -> Dict[str, Any]:
        """
        Determine if you should use a player in this tournament.

        Returns a recommendation with reasoning.

        Args:
            player_name: Player to evaluate
            tournament_name: Current tournament
            force_analysis: Analyze even if player not in field

        Returns:
            Dict with recommendation, score, and reasoning
        """
        # Get player stats
        player_value = self.get_player_value(player_name)
        if player_value is None and not force_analysis:
            return {
                "recommendation": "UNKNOWN",
                "score": 0,
                "reasoning": [f"Player '{player_name}' not found in current predictions"],
            }

        # Get usage info
        remaining_uses = self.tracker.get_remaining_uses(player_name, self.max_uses)
        usage_history = self.tracker.get_usage_history(player_name)

        # Get tournament info (now payout-based)
        tournament_importance = self.calendar.get_importance(tournament_name)
        tournament_tier = self.calendar.get_tournament_tier(tournament_name)
        payout_info = self.calendar.get_payout_info(tournament_name)
        remaining_majors = self.calendar.count_remaining_majors(tournament_name)
        upcoming = self.calendar.get_upcoming_important_events(tournament_name)

        # Build reasoning
        reasoning = []
        score = 0

        # === Factor 1: Remaining Uses ===
        if remaining_uses == 0:
            return {
                "recommendation": "CANNOT USE",
                "score": -100,
                "reasoning": [f"No uses remaining for {player_name}. Used at: {[u['tournament'] for u in usage_history]}"],
                "remaining_uses": 0,
            }

        if remaining_uses == 1:
            reasoning.append(f"⚠️ LAST USE - Only 1 use remaining for {player_name}")
            # Heavily weight toward only using at majors/elite events
            if tournament_importance >= 10:
                score += 30
                reasoning.append("✅ This is a MAJOR - perfect for last use")
            elif tournament_importance >= 9:
                score += 20
                reasoning.append("✅ Elite event - good for last use")
            elif tournament_importance >= 7:
                score += 5
                reasoning.append("⚠️ Signature event - consider saving for a major")
            else:
                score -= 20
                reasoning.append("❌ Standard event - SAVE this use for majors")

        elif remaining_uses == 2:
            reasoning.append(f"2 uses remaining for {player_name}")
            if tournament_importance >= 10:
                score += 25
                reasoning.append("✅ Major championship - definitely use")
            elif tournament_importance >= 8:
                score += 15
                reasoning.append("✅ High importance event - good to use")
            elif tournament_importance >= 5:
                score += 5
                reasoning.append("Standard event - OK to use if strong fit")

        else:  # 3 uses
            reasoning.append(f"Full 3 uses remaining for {player_name}")
            score += 5  # Slight bonus for flexibility

        # === Factor 2: Tournament Importance (Payout-Based) ===
        winner_share = payout_info.get('winner_share', 0)
        if winner_share > 0:
            reasoning.append(f"Tournament: {tournament_name} ({tournament_tier}, winner share: ${winner_share:,.0f})")
        else:
            reasoning.append(f"Tournament: {tournament_name} ({tournament_tier}, importance: {tournament_importance}/10)")
        score += tournament_importance * 2  # 2-20 points based on importance

        # === Factor 2.5: Elite Player Protection Rules ===
        if player_value:
            world_rank = player_value.get('world_rank')
            if world_rank:
                is_allowed, protection_reason = self.check_elite_protection(
                    world_rank, remaining_uses, tournament_importance
                )
                if not is_allowed:
                    score -= 25  # Heavy penalty for violating protection rules
                    reasoning.append(f"🛡️ PROTECTION RULE: {protection_reason}")

        # === Factor 3: Player Value This Week ===
        if player_value:
            world_rank = player_value.get('world_rank')
            win_prob = player_value.get('win_prob', 0)
            top10_prob = player_value.get('top10_prob', 0)
            course_fit = player_value.get('course_fit', 0)
            ev = player_value.get('expected_value', 0)

            # Is this an elite player?
            is_elite = world_rank and world_rank <= 15

            if is_elite:
                reasoning.append(f"🌟 Elite player (World #{world_rank})")
                if tournament_tier not in ["MAJOR", "ELITE", "SIGNATURE"] and remaining_uses <= 2:
                    score -= 15
                    reasoning.append("⚠️ Consider saving elite player for bigger events")

            # Win probability impact
            if win_prob >= 0.10:
                score += 15
                reasoning.append(f"🎯 Very strong win probability ({win_prob*100:.1f}%)")
            elif win_prob >= 0.05:
                score += 8
                reasoning.append(f"Good win probability ({win_prob*100:.1f}%)")

            # Course fit - DISABLED from scoring (r=-0.10, not predictive)
            # Keeping for display only - does NOT affect usage score
            if course_fit > 0.5:
                reasoning.append(f"📍 Course fit: +{course_fit:.2f} (not used in scoring)")
            elif course_fit > 0.2:
                reasoning.append(f"Course fit: +{course_fit:.2f} (not used in scoring)")
            elif course_fit < -0.3:
                reasoning.append(f"Course fit: {course_fit:.2f} (not used in scoring)")

            # Expected Value (EV) scoring for fantasy
            # Apply scarcity multiplier: fewer uses left = need higher EV to justify
            if ev and ev > 0:
                # Base score: $100k = 1 point, cap at 20
                base_ev_score = min(20, ev / 100000)

                # Scarcity adjustment: when uses are scarce, EV must be exceptional
                # 3 uses: full credit (1.0x)
                # 2 uses: need 1.5x better EV for same score
                # 1 use: need 2.5x better EV for same score
                scarcity_divisor = {3: 1.0, 2: 1.5, 1: 2.5}.get(remaining_uses, 1.0)
                adjusted_ev_score = base_ev_score / scarcity_divisor

                score += adjusted_ev_score
                if scarcity_divisor > 1:
                    reasoning.append(f"💰 EV: ${ev:,.0f} → adjusted score +{adjusted_ev_score:.1f} (scarcity: ÷{scarcity_divisor})")
                else:
                    reasoning.append(f"💰 EV: ${ev:,.0f} → score +{adjusted_ev_score:.1f}")

            # Cut risk penalty - don't waste picks on players who might miss the cut
            cut_risk = player_value.get('cut_risk', 'UNKNOWN')
            cut_prob = player_value.get('cut_prob', 0.5)
            if cut_risk == 'HIGH':
                score -= 20
                reasoning.append(f"⚠️ HIGH cut risk ({cut_prob*100:.0f}% to make cut) - RISKY PICK")
            elif cut_risk == 'ELEVATED':
                score -= 10
                reasoning.append(f"⚠️ Elevated cut risk ({cut_prob*100:.0f}% to make cut)")
            elif cut_risk == 'LOW':
                reasoning.append(f"✓ Low cut risk ({cut_prob*100:.0f}% to make cut)")

            # Hot hand / momentum bonus - players on streaks deserve extra consideration
            hot_hand_flag = player_value.get('hot_hand_flag', False)
            hot_hand_score = player_value.get('hot_hand_score', 0)
            momentum_trend = player_value.get('momentum_trend', 'NEUTRAL')
            consecutive_top10s = player_value.get('consecutive_top10s', 0)

            if hot_hand_flag:
                # 10-15% EV boost for hot players translates to ~8-12 score points
                hot_bonus = min(12, hot_hand_score * 1.5)
                score += hot_bonus
                if consecutive_top10s >= 3:
                    reasoning.append(f"🔥 HOT HAND: {consecutive_top10s} consecutive top-10s! (+{hot_bonus:.0f})")
                else:
                    reasoning.append(f"🔥 Hot streak detected (score: {hot_hand_score:.1f}) (+{hot_bonus:.0f})")
            elif momentum_trend == 'WARM':
                score += 4
                reasoning.append(f"📈 Warming up (momentum: {momentum_trend}, score: {hot_hand_score:.1f}) (+4)")
            elif momentum_trend == 'COLD':
                score -= 5
                reasoning.append(f"📉 Cold form (momentum: {momentum_trend}) (-5)")

        # === Factor 4: Upcoming Schedule ===
        upcoming_majors = [e for e in upcoming if e['tier'] == 'MAJOR']
        if remaining_uses <= len(upcoming_majors) and tournament_tier not in ['MAJOR', 'ELITE']:
            score -= 15
            upcoming_names = [m['name'] for m in upcoming_majors]
            reasoning.append(f"📅 Save uses! Upcoming majors: {', '.join(upcoming_names)}")

        # Apply future-value penalty only for elite players with scarce uses
        if player_value:
            world_rank = player_value.get('world_rank')
            is_elite = world_rank and world_rank <= 20
        else:
            is_elite = False

        if is_elite and remaining_uses <= 2 and tournament_importance < 8:
            penalty, higher_event_names = self._compute_future_value_penalty(
                remaining_uses, tournament_importance, upcoming
            )
            if penalty > 0:
                score -= penalty
                if higher_event_names:
                    reasoning.append(
                        f"⏳ Future value penalty (-{penalty:.1f}): better events ahead "
                        f"({', '.join(higher_event_names)})"
                    )



        # === Generate Recommendation ===
        if score >= 25:
            recommendation = "STRONG USE"
        elif score >= 15:
            recommendation = "USE"
        elif score >= 5:
            recommendation = "CONSIDER"
        elif score >= -5:
            recommendation = "SAVE"
        else:
            recommendation = "DEFINITELY SAVE"

        return {
            "player": player_name,
            "tournament": tournament_name,
            "recommendation": recommendation,
            "score": score,
            "remaining_uses": remaining_uses,
            "tournament_tier": tournament_tier,
            "reasoning": reasoning,
            "player_value": player_value,
            "upcoming_events": upcoming[:3],
            "predictions_calibrated": getattr(self, 'is_calibrated', False),
        }

    def get_optimal_usage_plan(
        self,
        players: List[str],
        tournament_name: str
    ) -> Dict[str, Any]:
        """
        Get optimal usage recommendations for multiple players.

        Args:
            players: List of player names to evaluate
            tournament_name: Current tournament

        Returns:
            Dict with categorized recommendations
        """
        results = {
            "strong_use": [],
            "use": [],
            "consider": [],
            "save": [],
            "cannot_use": [],
            "tournament": tournament_name,
            "tournament_tier": self.calendar.get_tournament_tier(tournament_name),
        }

        for player in players:
            analysis = self.should_use_player(player, tournament_name)

            category = analysis["recommendation"].lower().replace(" ", "_")
            if category == "definitely_save":
                category = "save"

            if category in results:
                results[category].append({
                    "player": player,
                    "score": analysis["score"],
                    "remaining_uses": analysis["remaining_uses"],
                    "key_reason": analysis["reasoning"][0] if analysis["reasoning"] else "",
                })

        # Sort each category by score
        for key in ["strong_use", "use", "consider", "save"]:
            results[key] = sorted(results[key], key=lambda x: x["score"], reverse=True)

        return results

    def get_season_usage_summary(self) -> Dict[str, Any]:
        """Get summary of usage across the season."""
        all_usage = self.tracker.get_all_usage()

        summary = {
            "total_players_used": len(all_usage),
            "tournaments_played": len(self.tracker.usage_data.get("tournaments_used", [])),
            "players_maxed_out": [],
            "players_with_1_use": [],
            "players_with_2_uses": [],
            "unused_elite_players": [],
        }

        for player, uses in all_usage.items():
            remaining = self.max_uses - uses
            if remaining == 0:
                summary["players_maxed_out"].append(player)
            elif remaining == 1:
                summary["players_with_1_use"].append(player)
            elif remaining == 2:
                summary["players_with_2_uses"].append(player)

        return summary


def main():
    """CLI for usage optimizer."""
    import argparse

    parser = argparse.ArgumentParser(description="Fantasy Golf Usage Optimizer")
    parser.add_argument("--player", "-p", help="Player to analyze")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name")
    parser.add_argument("--record-usage", action="store_true", help="Record that player was used")
    parser.add_argument("--summary", action="store_true", help="Show season usage summary")
    parser.add_argument("--top-picks", action="store_true", help="Analyze top predicted players")
    parser.add_argument("--plan-season", action="store_true", help="Generate a season plan from a schedule + predictions")
    parser.add_argument("--schedule", type=str, default=str(DATA_DIR / "raw" / "schedule_2026.csv"),
                        help="Path to schedule CSV (week,tournament_name,purse,winner_share)")
    parser.add_argument("--predictions-file", type=str, help="Path to predictions CSV with tournament_name and win/top5/top10 probs")

    args = parser.parse_args()

    optimizer = UsageOptimizer()

    # Season planner (uses schedule and per-week predictions)
    if args.plan_season:
        from usage_planner import SeasonUsagePlanner  # imported lazily to avoid circular deps

        schedule_path = Path(args.schedule)
        if not schedule_path.exists():
            print(f"Schedule file not found: {schedule_path}")
            return

        if not args.predictions_file:
            print("Provide --predictions-file pointing to a CSV with tournament_name/player_name/win_prob/top5_prob/top10_prob")
            return

        predictions_path = Path(args.predictions_file)
        if not predictions_path.exists():
            print(f"Predictions file not found: {predictions_path}")
            return

        current_usage = optimizer.tracker.get_all_usage()
        planner = SeasonUsagePlanner(
            schedule_path=schedule_path,
            max_uses=optimizer.max_uses,
            initial_usage=current_usage,
        )
        # If predictions file is single-tournament, pass current tournament name
        default_tournament = args.tournament
        plan = planner.build_plan(predictions_path, default_tournament=default_tournament)

        print("\n" + "="*70)
        print("  SEASON USAGE PLAN (Greedy EV by week, 3 uses/player, 3 starters/week)")
        print("="*70)
        for week in plan["weeks"]:
            print(f"\nWeek {week['week']}: {week['tournament_name']} ({week['tournament_type']})")
            print(f"  Purse: ${week['purse']:,.0f}  Winner Share: ${week['winner_share']:,.0f}")
            for slot, pick in enumerate(week["lineup"], start=1):
                print(f"   {slot}. {pick['player_name']}  EV: ${pick['expected_payout']:,.0f}  "
                      f"Uses left after: {pick['remaining_uses_after']}")

        print("\nPlayers maxed out:")
        for p, uses in sorted(plan["usage"].items(), key=lambda x: -x[1]):
            if uses >= optimizer.max_uses:
                print(f" - {p} (used {uses}/{optimizer.max_uses})")
        return

    if args.summary:
        summary = optimizer.get_season_usage_summary()
        print("\n" + "="*60)
        print("  SEASON USAGE SUMMARY")
        print("="*60)
        print(f"\nTotal players used: {summary['total_players_used']}")
        print(f"Tournaments played: {summary['tournaments_played']}")

        if summary['players_maxed_out']:
            print(f"\n❌ Players with no uses left: {', '.join(summary['players_maxed_out'])}")
        if summary['players_with_1_use']:
            print(f"\n⚠️ Players with 1 use left: {', '.join(summary['players_with_1_use'])}")

    elif args.record_usage and args.player:
        optimizer.tracker.record_usage(args.player, args.tournament)
        print(f"✓ Recorded usage: {args.player} at {args.tournament}")
        remaining = optimizer.tracker.get_remaining_uses(args.player)
        print(f"  {remaining} uses remaining")

    elif args.top_picks:
        if optimizer.predictions is not None:
            top_players = optimizer.predictions.nlargest(10, 'expected_value')['player_name'].tolist()

            print("\n" + "="*60)
            print(f"  USAGE ANALYSIS: {args.tournament}")
            print("="*60)

            results = optimizer.get_optimal_usage_plan(top_players, args.tournament)

            print(f"\nTournament Tier: {results['tournament_tier']}")

            if results['strong_use']:
                print("\n✅ STRONG USE:")
                for p in results['strong_use']:
                    print(f"   {p['player']} (score: {p['score']}, uses left: {p['remaining_uses']})")

            if results['use']:
                print("\n👍 USE:")
                for p in results['use']:
                    print(f"   {p['player']} (score: {p['score']}, uses left: {p['remaining_uses']})")

            if results['consider']:
                print("\n🤔 CONSIDER:")
                for p in results['consider']:
                    print(f"   {p['player']} (score: {p['score']}, uses left: {p['remaining_uses']})")

            if results['save']:
                print("\n💾 SAVE FOR LATER:")
                for p in results['save']:
                    print(f"   {p['player']} ({p['key_reason']})")
        else:
            print("No predictions loaded. Run predictions first.")

    elif args.player:
        result = optimizer.should_use_player(args.player, args.tournament)

        print("\n" + "="*60)
        print(f"  USAGE ANALYSIS: {args.player}")
        print("="*60)
        print(f"\nTournament: {args.tournament}")
        print(f"Recommendation: {result['recommendation']}")
        print(f"Score: {result['score']}")
        print(f"Uses Remaining: {result['remaining_uses']}/{optimizer.max_uses}")

        print("\nReasoning:")
        for reason in result['reasoning']:
            print(f"  {reason}")

        if result.get('upcoming_events'):
            print("\nUpcoming Important Events:")
            for event in result['upcoming_events']:
                print(f"  - {event['name']} ({event['tier']})")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
