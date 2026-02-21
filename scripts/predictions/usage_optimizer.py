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
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FANTASY_USAGE_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
LEGACY_USAGE_JSON = OUTPUTS_DIR / "player_usage_tracker.json"
LEGACY_USAGE_CSV = OUTPUTS_DIR / "player_usage_tracker.csv"


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
        self.tracker_file = tracker_file or FANTASY_USAGE_FILE
        self.usage_data = self._load()

    @staticmethod
    def _name_key(name: str) -> str:
        """Normalize player names across 'First Last' and 'Last, First' forms."""
        if pd.isna(name):
            return ""
        s = str(name).strip().lower()
        if "," in s:
            parts = s.split(",", 1)
            if len(parts) == 2:
                s = f"{parts[1].strip()} {parts[0].strip()}"
        for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
            s = s.replace(suffix, "")
        s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
        return " ".join(s.split())

    def _merge_player_usage(self, target: Dict, player_name: str, uses: list, total_uses: int):
        """Merge usage entries into canonical internal structure."""
        key = self._name_key(player_name)
        if not key:
            return
        if key not in target["players"]:
            target["players"][key] = {
                "name": player_name,
                "uses": [],
                "total_uses": 0,
            }
        entry = target["players"][key]

        # Deduplicate by tournament (date may vary across sources for same event).
        existing = {
            str(u.get("tournament", "")).strip().lower()
            for u in entry.get("uses", [])
            if str(u.get("tournament", "")).strip()
        }
        for u in uses:
            t = str(u.get("tournament", "")).strip()
            d = str(u.get("date", "")).strip()
            tkey = t.lower()
            if t and tkey not in existing:
                entry["uses"].append({"tournament": t, "date": d})
                existing.add(tkey)

        # Keep highest observed count, but also never less than deduped uses length.
        entry["total_uses"] = max(int(entry.get("total_uses", 0)), int(total_uses), len(entry["uses"]))

    def _load_usage_file(self, path: Path) -> Dict:
        """Load one usage file and normalize to internal schema."""
        out = {"players": {}, "tournaments_used": []}
        if not path.exists():
            return out

        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception:
            return out

        # New fantasy tracker schema used by dashboard/planning tracker.
        if isinstance(raw, dict) and "picks" in raw:
            picks = raw.get("picks", {})
            for player_name, info in picks.items():
                t_used = info.get("tournaments_used", []) or []
                uses = [
                    {
                        "tournament": str(t.get("tournament", "")).strip(),
                        "date": str(t.get("date", "")).strip(),
                    }
                    for t in t_used
                    if t.get("tournament")
                ]
                self._merge_player_usage(
                    out,
                    player_name=player_name,
                    uses=uses,
                    total_uses=int(info.get("times_used", len(uses)) or 0),
                )
                for t in uses:
                    tname = t.get("tournament", "")
                    if tname and tname not in out["tournaments_used"]:
                        out["tournaments_used"].append(tname)
            return out

        # Legacy schema used by older usage optimizer.
        if isinstance(raw, dict) and "players" in raw:
            for _, info in raw.get("players", {}).items():
                pname = str(info.get("name", "")).strip()
                uses = info.get("uses", []) or []
                self._merge_player_usage(
                    out,
                    player_name=pname,
                    uses=uses,
                    total_uses=int(info.get("total_uses", len(uses)) or 0),
                )
            for tname in raw.get("tournaments_used", []) or []:
                t = str(tname).strip()
                if t and t not in out["tournaments_used"]:
                    out["tournaments_used"].append(t)

        return out

    def _load(self) -> Dict:
        """Load usage data from file."""
        merged = {"players": {}, "tournaments_used": []}
        # Prefer shared fantasy tracker, but merge legacy usage if present.
        for src in [self.tracker_file, LEGACY_USAGE_JSON]:
            data = self._load_usage_file(Path(src))
            for _, info in data.get("players", {}).items():
                self._merge_player_usage(
                    merged,
                    player_name=info.get("name", ""),
                    uses=info.get("uses", []) or [],
                    total_uses=int(info.get("total_uses", 0) or 0),
                )
            for tname in data.get("tournaments_used", []):
                t = str(tname).strip()
                if t and t not in merged["tournaments_used"]:
                    merged["tournaments_used"].append(t)
        return merged

    def save(self):
        """Save usage data to file."""
        self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
        prior = {}
        if self.tracker_file.exists():
            try:
                with open(self.tracker_file) as pf:
                    prior = json.load(pf)
            except Exception:
                prior = {}

        # Save using shared fantasy schema.
        picks = {}
        prior_picks = prior.get("picks", {}) if isinstance(prior, dict) else {}
        prior_by_key = {
            self._name_key(name): (name, info)
            for name, info in prior_picks.items()
            if isinstance(info, dict)
        }
        for _, info in self.usage_data.get("players", {}).items():
            name = str(info.get("name", "")).strip()
            if not name:
                continue
            uses = info.get("uses", []) or []
            total_uses = int(info.get("total_uses", len(uses)) or 0)
            key = self._name_key(name)
            prior_name, prior_info = prior_by_key.get(key, (name, {}))
            prior_tours = list(prior_info.get("tournaments_used", []) or [])

            # Keep richer prior fields (week/result/points) where possible.
            by_tournament = {
                str(t.get("tournament", "")).strip().lower(): dict(t)
                for t in prior_tours
                if isinstance(t, dict) and t.get("tournament")
            }
            merged_tours = []
            seen = set()
            for u in uses:
                tname = str(u.get("tournament", "")).strip()
                if not tname:
                    continue
                tkey = tname.lower()
                row = by_tournament.get(tkey, {})
                row["tournament"] = tname
                if "week" not in row:
                    row["week"] = 0
                if not row.get("date"):
                    row["date"] = str(u.get("date", "")).strip()
                merged_tours.append(row)
                seen.add(tkey)

            # Keep prior tournaments that weren't represented in internal uses.
            for t in prior_tours:
                if not isinstance(t, dict):
                    continue
                tname = str(t.get("tournament", "")).strip()
                if not tname:
                    continue
                tkey = tname.lower()
                if tkey not in seen:
                    merged_tours.append(dict(t))
                    seen.add(tkey)

            times_used = max(total_uses, int(prior_info.get("times_used", 0) or 0), len(merged_tours))
            total_points = int(prior_info.get("total_points", 0) or 0)

            picks[prior_name] = {
                "times_used": times_used,
                "tournaments_used": merged_tours,
                "remaining_uses": max(0, 3 - times_used),
                "total_points": total_points,
            }

        payload = {
            "season": "2026",
            "max_uses_per_player": 3,
            "players_per_lineup": 3,
            "last_updated": datetime.now().isoformat(),
            "picks": picks,
            # Preserve weekly lineup structure maintained by planning tracker.
            "weekly_lineups": prior.get("weekly_lineups", {}) if isinstance(prior, dict) else {},
            "summary": {
                "total_players_used": len(picks),
                "total_picks_made": int(sum(v.get("times_used", 0) for v in picks.values())),
                "total_points": int(sum(v.get("total_points", 0) for v in picks.values())),
            },
        }
        with open(self.tracker_file, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        # Backward compatibility: write legacy JSON + CSV used by older assistant code.
        LEGACY_USAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(LEGACY_USAGE_JSON, "w") as f:
            json.dump(self.usage_data, f, indent=2, default=str)

        rows = []
        for _, info in self.usage_data.get("players", {}).items():
            name = str(info.get("name", "")).strip()
            total_uses = int(info.get("total_uses", 0) or 0)
            rows.append(
                {
                    "player_name": name,
                    "uses_used": total_uses,
                    "uses_remaining": max(0, 3 - total_uses),
                    "tournaments_used": " | ".join(
                        [
                            str(u.get("tournament", "")).strip()
                            for u in (info.get("uses", []) or [])
                            if u.get("tournament")
                        ]
                    ),
                }
            )
        csv_df = pd.DataFrame(rows)
        if not csv_df.empty and "player_name" in csv_df.columns:
            csv_df = csv_df.sort_values("player_name")
        csv_df.to_csv(LEGACY_USAGE_CSV, index=False)

    def record_usage(self, player_name: str, tournament_name: str, tournament_date: str = None):
        """Record that a player was used in a tournament."""
        player_key = self._name_key(player_name)

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
        player_key = self._name_key(player_name)

        if player_key not in self.usage_data["players"]:
            return max_uses

        return max(0, max_uses - int(self.usage_data["players"][player_key]["total_uses"]))

    def get_usage_history(self, player_name: str) -> List[Dict]:
        """Get usage history for a player."""
        player_key = self._name_key(player_name)

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
        # Only penalize players who genuinely need to be saved for bigger events.
        # The threshold is tier-dependent:
        #   - Rank ≤ 10 (elite): save for majors aggressively — every use is precious
        #   - Rank 11-30 (good): only save last use for big events
        #   - Rank 30+ (mid/value): use freely — no major-save obligation
        if player_value:
            world_rank = player_value.get('world_rank')
            is_elite = world_rank and world_rank <= 10
            is_good = world_rank and 10 < world_rank <= 30
        else:
            world_rank = None
            is_elite = False
            is_good = False

        upcoming_majors = [e for e in upcoming if e['tier'] == 'MAJOR']
        if tournament_tier not in ['MAJOR', 'ELITE']:
            if is_elite and remaining_uses <= len(upcoming_majors):
                # Elite player — every remaining use should go to a top event
                score -= 15
                upcoming_names = [m['name'] for m in upcoming_majors[:3]]
                reasoning.append(f"📅 Save uses! Upcoming majors: {', '.join(upcoming_names)}")
            elif is_good and remaining_uses == 1:
                # Good player — last use should go somewhere meaningful
                score -= 10
                upcoming_names = [m['name'] for m in upcoming_majors[:2]]
                reasoning.append(f"📅 Last use — save for: {', '.join(upcoming_names)}")

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

    @staticmethod
    def _norm_01(series: pd.Series) -> pd.Series:
        """Min-max normalize series to [0, 1], robust to constants/NaN."""
        s = pd.to_numeric(series, errors="coerce")
        if s.isna().all():
            return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
        mn = float(s.min())
        mx = float(s.max())
        if np.isclose(mx, mn):
            return pd.Series(np.full(len(s), 0.5), index=s.index, dtype=float)
        out = (s - mn) / (mx - mn)
        return out.fillna(0.5).clip(0.0, 1.0)

    def _load_scoring_engine_scores(self, tournament_name: str) -> pd.DataFrame:
        """
        Optionally load scoring-engine features for this tournament.
        Returns empty DataFrame if unavailable, so lineup generation still works.
        """
        try:
            planning_dir = PROJECT_ROOT / "scripts" / "planning"
            if str(planning_dir) not in sys.path:
                sys.path.insert(0, str(planning_dir))

            from scoring_engine import ScoringEngine  # type: ignore

            engine = ScoringEngine(tournament=tournament_name)
            recs = engine.get_tournament_recommendations(
                tournament=tournament_name,
                top_n=max(30, len(engine.predictions)),
                min_uses=0,
            )
            rows = []
            for s in recs:
                rows.append(
                    {
                        "player_name_engine": str(getattr(s, "player", "")).strip(),
                        "engine_total_score": float(getattr(s, "total_score", 0.0)),
                        "engine_course_fit": float(getattr(s, "course_fit", 0.0)),
                        "engine_form_score": float(getattr(s, "current_form", 0.0)),
                        "engine_field_score": float(getattr(s, "field_strength", 0.0)),
                        "engine_importance_score": float(getattr(s, "tournament_importance", 0.0)),
                    }
                )

            if not rows:
                return pd.DataFrame()

            out = pd.DataFrame(rows)
            out["name_key"] = out["player_name_engine"].apply(UsageTracker._name_key)
            out = out.drop_duplicates(subset=["name_key"], keep="first")
            return out
        except Exception:
            return pd.DataFrame()

    def _build_lineup(
        self,
        pool_df: pd.DataFrame,
        score_col: str,
        lineup_size: int,
        prior_lineups: List[List[str]],
        max_overlap_between_lineups: int,
    ) -> List[str]:
        """Greedy lineup builder with overlap control across strategy profiles."""
        ranked = pool_df.sort_values(
            [score_col, "expected_value", "top10_prob", "cut_prob"],
            ascending=[False, False, False, False],
            na_position="last",
        )

        lineup: List[str] = []
        for row in ranked.itertuples(index=False):
            if len(lineup) >= lineup_size:
                break

            name = str(getattr(row, "player_name", "")).strip()
            if not name or name in lineup:
                continue
            if int(getattr(row, "uses_remaining", 0)) <= 0:
                continue

            valid_overlap = True
            for prior in prior_lineups:
                overlap_if_added = len(set(prior).intersection(set(lineup + [name])))
                if overlap_if_added > max_overlap_between_lineups:
                    valid_overlap = False
                    break

            if valid_overlap:
                lineup.append(name)

        # Fallback fill if overlap constraints are too tight.
        if len(lineup) < lineup_size:
            for row in ranked.itertuples(index=False):
                if len(lineup) >= lineup_size:
                    break
                name = str(getattr(row, "player_name", "")).strip()
                if not name or name in lineup:
                    continue
                if int(getattr(row, "uses_remaining", 0)) <= 0:
                    continue
                lineup.append(name)

        return lineup

    def build_strategy_lineups(
        self,
        predictions_df: pd.DataFrame,
        tournament_name: str,
        lineup_size: int = 3,
        candidate_pool_size: int = 45,
        max_overlap_between_lineups: int = 2,
    ) -> Dict[str, Any]:
        """
        Build three fantasy strategy lineups:
        - safe: cut safety and floor
        - balanced: mix of floor/upside/leverage
        - upside: ceiling and leverage
        """
        if predictions_df is None or predictions_df.empty or "player_name" not in predictions_df.columns:
            return {
                "tournament": tournament_name,
                "lineup_size": lineup_size,
                "profiles": {},
                "pool": pd.DataFrame(),
            }

        pool = predictions_df.copy()
        pool["player_name"] = pool["player_name"].fillna("").astype(str).str.strip()
        pool = pool[pool["player_name"] != ""].copy()
        if pool.empty:
            return {
                "tournament": tournament_name,
                "lineup_size": lineup_size,
                "profiles": {},
                "pool": pd.DataFrame(),
            }

        # Core probability/stat columns.
        pool["win_prob"] = pd.to_numeric(pool.get("win_prob"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
        pool["top5_prob"] = pd.to_numeric(pool.get("top5_prob"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
        pool["top10_prob"] = pd.to_numeric(pool.get("top10_prob"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
        pool["top20_prob"] = pd.to_numeric(pool.get("top20_prob"), errors="coerce")
        missing_top20 = pool["top20_prob"].isna()
        pool.loc[missing_top20, "top20_prob"] = (
            pool.loc[missing_top20, "top10_prob"] +
            (pool.loc[missing_top20, "top10_prob"] - pool.loc[missing_top20, "top5_prob"]) * 1.2
        ).clip(0.0, 0.95)
        pool["top20_prob"] = pool["top20_prob"].fillna(0.0).clip(0.0, 1.0)

        pool["cut_prob"] = pd.to_numeric(pool.get("cut_prob"), errors="coerce")
        missing_cut = pool["cut_prob"].isna()
        pool.loc[missing_cut, "cut_prob"] = (pool.loc[missing_cut, "top20_prob"] * 1.4 + 0.25).clip(0.0, 0.98)
        pool["cut_prob"] = pool["cut_prob"].fillna(0.5).clip(0.0, 1.0)
        pool["miss_cut_prob"] = (1.0 - pool["cut_prob"]).clip(0.0, 1.0)

        pool["expected_value"] = pd.to_numeric(pool.get("expected_value"), errors="coerce").fillna(0.0)
        pool["sg_total"] = pd.to_numeric(pool.get("sg_total"), errors="coerce").fillna(0.0)
        pool["sg_app"] = pd.to_numeric(pool.get("sg_app"), errors="coerce").fillna(0.0)
        pool["sg_putt"] = pd.to_numeric(pool.get("sg_putt"), errors="coerce").fillna(0.0)
        pool["dg_fit_total"] = pd.to_numeric(pool.get("dg_fit_total"), errors="coerce")
        if pool["dg_fit_total"].isna().all():
            pool["dg_fit_total"] = pd.to_numeric(pool.get("course_fit_score"), errors="coerce")
        pool["dg_fit_total"] = pool["dg_fit_total"].fillna(0.0)
        pool["recent_cuts_pct"] = pd.to_numeric(pool.get("recent_cuts_pct"), errors="coerce").fillna(pool["cut_prob"])
        pool["hot_hand_score"] = pd.to_numeric(pool.get("hot_hand_score"), errors="coerce").fillna(0.0)
        pool["form_trend_num"] = pd.to_numeric(pool.get("form_trend"), errors="coerce").fillna(0.0)

        # Popularity + leverage (use model-vs-market edge when present).
        world_rank = pd.to_numeric(pool.get("world_rank"), errors="coerce")
        rank_pop = 1.0 - self._norm_01(world_rank.fillna(world_rank.median() if world_rank.notna().any() else 80))
        vegas_prob = pd.to_numeric(pool.get("vegas_prob"), errors="coerce")
        if vegas_prob.notna().any():
            market_pop = self._norm_01(vegas_prob.fillna(vegas_prob.median()))
        else:
            market_pop = self._norm_01(pd.to_numeric(pool.get("odds_numeric"), errors="coerce").fillna(5000) * -1.0)
        pool["popularity_proxy"] = (0.55 * rank_pop + 0.45 * market_pop).clip(0.0, 1.0)

        raw_edge = pd.to_numeric(pool.get("model_vs_vegas_edge"), errors="coerce")
        if raw_edge.notna().any():
            pool["model_gap_raw"] = raw_edge.fillna(raw_edge.median())
        elif vegas_prob.notna().any():
            pool["model_gap_raw"] = (pool["win_prob"] - vegas_prob.fillna(vegas_prob.median()))
        else:
            pool["model_gap_raw"] = pool["win_prob"] - pool["win_prob"].median()

        pool["top10_norm"] = self._norm_01(pool["top10_prob"])
        pool["model_gap_norm"] = self._norm_01(pool["model_gap_raw"])
        pool["leverage_score"] = (0.65 * pool["model_gap_norm"] + 0.35 * (1.0 - pool["popularity_proxy"])).clip(0.0, 1.0)
        pool["leverage_raw"] = pool["model_gap_raw"]

        # Normalize stat features (pre-candidate selection for fair ranking).
        pool["sg_total_norm"] = self._norm_01(pool["sg_total"])
        pool["sg_app_norm"] = self._norm_01(pool["sg_app"])
        pool["sg_putt_norm"] = self._norm_01(pool["sg_putt"])
        pool["course_fit_norm"] = self._norm_01(pool["dg_fit_total"])
        pool["ev_norm"] = self._norm_01(pool["expected_value"])
        pool["recent_cuts_norm"] = self._norm_01(pool["recent_cuts_pct"])
        pool["hot_hand_norm"] = self._norm_01(pool["hot_hand_score"])
        pool["trend_norm"] = self._norm_01(pool["form_trend_num"])

        # Candidate pool mixing: don't rely only on top EV/top probability chalk.
        target_pool = max(int(candidate_pool_size), lineup_size * 10, 24)
        n_each = max(8, int(target_pool * 0.40))
        idx_set = set()
        for col in ["expected_value", "top10_prob", "course_fit_norm", "hot_hand_norm", "leverage_score"]:
            if col in pool.columns:
                idx_set.update(pool.nlargest(n_each, col).index.tolist())

        if len(idx_set) < target_pool:
            fill = pool.sort_values(["expected_value", "top10_prob", "win_prob"], ascending=[False, False, False])
            idx_set.update(fill.head(target_pool).index.tolist())

        candidate_pool = pool.loc[sorted(idx_set)].copy()
        if len(candidate_pool) > target_pool:
            candidate_pool["candidate_blend"] = (
                0.30 * candidate_pool["ev_norm"] +
                0.22 * candidate_pool["top10_norm"] +
                0.20 * candidate_pool["course_fit_norm"] +
                0.18 * candidate_pool["leverage_score"] +
                0.10 * candidate_pool["hot_hand_norm"]
            )
            candidate_pool = candidate_pool.sort_values("candidate_blend", ascending=False).head(target_pool).copy()
        pool = candidate_pool.reset_index(drop=True)

        # Usage signals from strategic optimizer.
        usage_scores = []
        usage_recs = []
        uses_left = []
        for name in pool["player_name"].tolist():
            analysis = self.should_use_player(name, tournament_name)
            usage_scores.append(float(analysis.get("score", 0.0)))
            usage_recs.append(str(analysis.get("recommendation", "UNKNOWN")))
            uses_left.append(int(analysis.get("remaining_uses", self.max_uses)))

        pool["usage_score"] = usage_scores
        pool["usage_recommendation"] = usage_recs
        pool["uses_remaining"] = uses_left
        pool["usage_norm"] = ((pool["usage_score"] + 25.0) / 60.0).clip(0.0, 1.0)

        # Optional scoring-engine integration.
        pool["name_key"] = pool["player_name"].apply(UsageTracker._name_key)
        engine_df = self._load_scoring_engine_scores(tournament_name)
        if not engine_df.empty and "name_key" in engine_df.columns:
            pool = pool.merge(
                engine_df[
                    [
                        "name_key",
                        "engine_total_score",
                        "engine_course_fit",
                        "engine_form_score",
                        "engine_field_score",
                        "engine_importance_score",
                    ]
                ],
                on="name_key",
                how="left",
            )
        for c in [
            "engine_total_score",
            "engine_course_fit",
            "engine_form_score",
            "engine_field_score",
            "engine_importance_score",
        ]:
            if c not in pool.columns:
                pool[c] = np.nan
        pool["engine_total_norm"] = self._norm_01(pool["engine_total_score"].fillna(50.0))
        pool["engine_course_norm"] = self._norm_01(pool["engine_course_fit"].fillna(pool["course_fit_norm"] * 100.0))
        pool["engine_form_norm"] = self._norm_01(pool["engine_form_score"].fillna(50.0))

        # Scarcity penalty: if uses are low, avoid burning on lower-importance events.
        tournament_importance = float(self.calendar.get_importance(tournament_name))
        scarcity_map = {
            1: 0.18 if tournament_importance <= 6 else (0.09 if tournament_importance <= 8 else 0.01),
            2: 0.07 if tournament_importance <= 6 else (0.03 if tournament_importance <= 8 else 0.0),
        }
        pool["scarcity_penalty"] = pool["uses_remaining"].map(lambda u: scarcity_map.get(int(u), 0.0)).fillna(0.0)
        pool.loc[pool["uses_remaining"] <= 0, "scarcity_penalty"] = 1.0

        # Composite profile scores (uses + stats + course fit + leverage + scoring engine).
        pool["safe_score"] = (
            0.22 * pool["cut_prob"] +
            0.15 * pool["top20_prob"] +
            0.10 * pool["top10_prob"] +
            0.12 * pool["usage_norm"] +
            0.09 * pool["recent_cuts_norm"] +
            0.10 * pool["course_fit_norm"] +
            0.08 * pool["sg_total_norm"] +
            0.08 * pool["engine_total_norm"] +
            0.06 * pool["engine_course_norm"] -
            0.10 * pool["scarcity_penalty"]
        )
        pool["balanced_score"] = (
            0.16 * pool["top10_prob"] +
            0.12 * pool["top20_prob"] +
            0.10 * pool["cut_prob"] +
            0.10 * pool["usage_norm"] +
            0.12 * pool["leverage_score"] +
            0.08 * pool["model_gap_norm"] +
            0.08 * pool["course_fit_norm"] +
            0.07 * pool["sg_total_norm"] +
            0.06 * pool["sg_app_norm"] +
            0.05 * pool["ev_norm"] +
            0.06 * pool["engine_total_norm"] -
            0.06 * pool["scarcity_penalty"]
        )
        pool["upside_score"] = (
            0.20 * pool["win_prob"] +
            0.16 * pool["top5_prob"] +
            0.07 * pool["top10_prob"] +
            0.18 * pool["leverage_score"] +
            0.12 * pool["model_gap_norm"] +
            0.07 * pool["hot_hand_norm"] +
            0.05 * pool["trend_norm"] +
            0.04 * pool["sg_app_norm"] +
            0.03 * pool["sg_putt_norm"] +
            0.05 * pool["engine_form_norm"] +
            0.05 * pool["usage_norm"] -
            0.13 * pool["miss_cut_prob"] -
            0.05 * pool["scarcity_penalty"]
        )

        # Profile constraints.
        cut_floor = float(max(0.86, pool["cut_prob"].quantile(0.60)))
        balanced_lev_thresh = float(max(0.52, pool["leverage_score"].quantile(0.60)))
        upside_lev_thresh = float(max(0.62, pool["leverage_score"].quantile(0.75)))
        chalk_thresh = float(min(0.80, pool["popularity_proxy"].quantile(0.75)))

        profiles = {
            "safe": {"score_col": "safe_score", "label": "Safe"},
            "balanced": {"score_col": "balanced_score", "label": "Balanced"},
            "upside": {"score_col": "upside_score", "label": "Upside"},
        }

        built_profiles: Dict[str, Any] = {}
        prior_lineups: List[List[str]] = []

        def _replace_player(lineup_players: List[str], drop_name: str, add_name: str) -> List[str]:
            return [add_name if p == drop_name else p for p in lineup_players]

        def _enforce_overlap_cap(lineup_players: List[str], score_col: str) -> List[str]:
            """Guarantee overlap cap after profile-specific replacements."""
            if not prior_lineups or not lineup_players:
                return lineup_players

            trial = list(lineup_players)
            for _ in range(16):
                overlap_counts = [len(set(trial).intersection(set(prev))) for prev in prior_lineups]
                max_seen = max(overlap_counts) if overlap_counts else 0
                if max_seen <= max_overlap_between_lineups:
                    break

                # Identify the prior lineup with highest overlap.
                worst_idx = int(np.argmax(overlap_counts))
                worst_prior = set(prior_lineups[worst_idx])
                overlap_players = [p for p in trial if p in worst_prior]
                if not overlap_players:
                    break

                # Drop the weakest overlapping player by current profile score.
                overlap_df = pool[pool["player_name"].isin(overlap_players)].copy()
                if overlap_df.empty:
                    break
                drop_name = str(overlap_df.sort_values(score_col, ascending=True).iloc[0]["player_name"]).strip()

                # Add best candidate that preserves overlap cap with all previous lineups.
                candidates = pool[
                    (pool["uses_remaining"] > 0) &
                    (~pool["player_name"].isin(trial))
                ].sort_values([score_col, "leverage_score"], ascending=[False, False])

                added = False
                for _, cand in candidates.iterrows():
                    add_name = str(cand["player_name"]).strip()
                    if not add_name:
                        continue
                    candidate_trial = _replace_player(trial, drop_name, add_name)
                    valid = all(
                        len(set(candidate_trial).intersection(set(prev))) <= max_overlap_between_lineups
                        for prev in prior_lineups
                    )
                    if valid:
                        trial = candidate_trial
                        added = True
                        break
                if not added:
                    break

            return trial

        for key in ["safe", "balanced", "upside"]:
            score_col = profiles[key]["score_col"]

            if key == "safe":
                lineup_pool = pool[
                    (pool["uses_remaining"] > 0) &
                    (pool["cut_prob"] >= cut_floor) &
                    (pool["scarcity_penalty"] <= 0.10)
                ].copy()
                if len(lineup_pool) < lineup_size * 2:
                    lineup_pool = pool[pool["uses_remaining"] > 0].copy()
            else:
                lineup_pool = pool[pool["uses_remaining"] > 0].copy()

            lineup_players = self._build_lineup(
                pool_df=lineup_pool,
                score_col=score_col,
                lineup_size=lineup_size,
                prior_lineups=prior_lineups,
                max_overlap_between_lineups=max_overlap_between_lineups,
            )

            # Balanced: enforce at least one leverage play.
            if key == "balanced" and lineup_players:
                current = pool[pool["player_name"].isin(lineup_players)].copy()
                has_balanced_lev = (current["leverage_score"] >= balanced_lev_thresh).any()
                if not has_balanced_lev:
                    candidates = pool[
                        (pool["leverage_score"] >= balanced_lev_thresh) &
                        (pool["uses_remaining"] > 0) &
                        (~pool["player_name"].isin(lineup_players))
                    ].sort_values([score_col, "model_gap_norm"], ascending=[False, False])
                    if not candidates.empty:
                        replacement = str(candidates.iloc[0]["player_name"]).strip()
                        drop_df = current.sort_values([score_col, "usage_score"], ascending=[True, True])
                        drop_name = str(drop_df.iloc[0]["player_name"]).strip()
                        lineup_players = _replace_player(lineup_players, drop_name, replacement)

            # Upside: enforce leverage and limit chalk concentration.
            if key == "upside" and lineup_players:
                current = pool[pool["player_name"].isin(lineup_players)].copy()
                has_upside_lev = (current["leverage_score"] >= upside_lev_thresh).any()
                if not has_upside_lev:
                    candidates = pool[
                        (pool["leverage_score"] >= upside_lev_thresh) &
                        (pool["uses_remaining"] > 0) &
                        (~pool["player_name"].isin(lineup_players))
                    ].sort_values([score_col, "win_prob"], ascending=[False, False])
                    if not candidates.empty:
                        replacement = str(candidates.iloc[0]["player_name"]).strip()
                        drop_df = current.sort_values([score_col, "leverage_score"], ascending=[True, True])
                        drop_name = str(drop_df.iloc[0]["player_name"]).strip()
                        lineup_players = _replace_player(lineup_players, drop_name, replacement)
                        current = pool[pool["player_name"].isin(lineup_players)].copy()

                # Max one chalk player in upside lineup.
                chalk = current[current["popularity_proxy"] >= chalk_thresh].sort_values(score_col, ascending=False)
                if len(chalk) > 1:
                    keep_name = str(chalk.iloc[0]["player_name"]).strip()
                    for _, row in chalk.iloc[1:].iterrows():
                        drop_name = str(row["player_name"]).strip()
                        candidates = pool[
                            (pool["uses_remaining"] > 0) &
                            (pool["leverage_score"] >= balanced_lev_thresh) &
                            (pool["popularity_proxy"] < chalk_thresh) &
                            (~pool["player_name"].isin(lineup_players))
                        ].sort_values([score_col, "leverage_score"], ascending=[False, False])
                        if candidates.empty:
                            continue
                        replacement = str(candidates.iloc[0]["player_name"]).strip()
                        if drop_name != keep_name:
                            lineup_players = _replace_player(lineup_players, drop_name, replacement)

            lineup_players = _enforce_overlap_cap(lineup_players, score_col)
            prior_lineups.append(lineup_players)

            lineup_df = pool[pool["player_name"].isin(lineup_players)].copy()
            if not lineup_df.empty:
                lineup_df["_order"] = lineup_df["player_name"].apply(lambda x: lineup_players.index(x))
                lineup_df = lineup_df.sort_values("_order").drop(columns=["_order"])

            built_profiles[key] = {
                "profile": profiles[key]["label"],
                "players": lineup_players,
                "summary": {
                    "avg_win_prob": float(lineup_df["win_prob"].mean()) if not lineup_df.empty else 0.0,
                    "avg_top10_prob": float(lineup_df["top10_prob"].mean()) if not lineup_df.empty else 0.0,
                    "avg_cut_prob": float(lineup_df["cut_prob"].mean()) if not lineup_df.empty else 0.0,
                    "avg_usage_score": float(lineup_df["usage_score"].mean()) if not lineup_df.empty else 0.0,
                    "avg_leverage_raw": float(lineup_df["leverage_raw"].mean()) if not lineup_df.empty else 0.0,
                    "avg_leverage_score": float(lineup_df["leverage_score"].mean()) if not lineup_df.empty else 0.0,
                    "avg_course_fit": float(lineup_df["course_fit_norm"].mean()) if not lineup_df.empty else 0.0,
                    "avg_engine_score": float(lineup_df["engine_total_score"].mean()) if not lineup_df.empty else 0.0,
                },
                "details": lineup_df[[
                    "player_name",
                    "uses_remaining",
                    "usage_recommendation",
                    "usage_score",
                    "win_prob",
                    "top5_prob",
                    "top10_prob",
                    "top20_prob",
                    "cut_prob",
                    "model_gap_raw",
                    "leverage_raw",
                    "leverage_score",
                    "course_fit_norm",
                    "sg_total_norm",
                    "sg_app_norm",
                    "hot_hand_norm",
                    "engine_total_score",
                    "engine_course_fit",
                    "scarcity_penalty",
                    score_col,
                ]].to_dict(orient="records") if not lineup_df.empty else [],
            }

        pool_view_cols = [
            "player_name",
            "uses_remaining",
            "usage_recommendation",
            "usage_score",
            "win_prob",
            "top5_prob",
            "top10_prob",
            "top20_prob",
            "cut_prob",
            "model_gap_raw",
            "popularity_proxy",
            "leverage_raw",
            "leverage_score",
            "course_fit_norm",
            "sg_total_norm",
            "sg_app_norm",
            "hot_hand_norm",
            "engine_total_score",
            "engine_course_fit",
            "scarcity_penalty",
            "safe_score",
            "balanced_score",
            "upside_score",
        ]
        pool_view_cols = [c for c in pool_view_cols if c in pool.columns]
        pool_view = pool.sort_values("balanced_score", ascending=False)[pool_view_cols].reset_index(drop=True)

        return {
            "tournament": tournament_name,
            "lineup_size": lineup_size,
            "profiles": built_profiles,
            "pool": pool_view,
        }

    def get_weekly_picks(
        self,
        tournament_name: str,
        n_picks: int = 3,
        top_n: int = 40,
    ) -> Dict[str, Any]:
        """
        Generate clean, usage-adjusted weekly pick recommendations.

        Answers: "Who should I actually pick this week given usage constraints?"
        Scheffler is #1 by EV every week — but if this is a Standard event,
        he should be SAVED for majors. This method makes that explicit.

        Returns dict with:
            picks        - DataFrame of top n_picks recommended players
            save_list    - DataFrame of players to save and why
            full_ranking - DataFrame of all top_n players with use/save labels
            tournament_tier - tier of current event
            tournament_importance - importance score (1-10)
            upcoming_events - next 5 high-value events
        """
        if self.predictions is None or self.predictions.empty:
            return {"error": "No predictions loaded"}

        tournament_importance = self.calendar.get_importance(tournament_name)
        tournament_tier = self.calendar.get_tournament_tier(tournament_name)
        upcoming = self.calendar.get_upcoming_important_events(tournament_name, look_ahead=8)
        upcoming_sig_plus = [e for e in upcoming if e.get("importance", 0) >= 8]

        # Get top N players by raw EV from predictions
        preds = self.predictions.copy()
        preds["ev_rank"] = preds["expected_value"].rank(ascending=False).astype(int)
        top_players = preds.nsmallest(top_n, "ev_rank")

        rows = []
        for _, player_row in top_players.iterrows():
            name = str(player_row["player_name"]).strip()
            analysis = self.should_use_player(name, tournament_name)

            rec = analysis["recommendation"]
            score = analysis["score"]
            remaining = analysis["remaining_uses"]
            world_rank = player_row.get("world_rank", 999)

            # Build save_for text: which upcoming events suit this player
            elite_tier = self._get_elite_tier(world_rank if not pd.isna(world_rank) else 999)
            rules = self.ELITE_PROTECTION_RULES.get(elite_tier, self.ELITE_PROTECTION_RULES[999])
            uses_key = f"uses_{remaining}"
            min_imp = rules.get(uses_key, 0)
            save_events = [e["name"] for e in upcoming if e.get("importance", 0) >= max(min_imp, 8)][:3]
            save_for = ", ".join(save_events) if save_events else "flexible"

            rows.append({
                "player_name": name,
                "world_rank": player_row.get("world_rank"),
                "ev_rank": int(player_row["ev_rank"]),
                "expected_value": round(float(player_row.get("expected_value", 0))),
                "win_prob": round(float(player_row.get("win_prob_calibrated", player_row.get("win_prob", 0))), 4),
                "top10_prob": round(float(player_row.get("top10_prob_calibrated", player_row.get("top10_prob", 0))), 4),
                "cut_risk": player_row.get("cut_risk", "UNKNOWN"),
                "uses_remaining": remaining,
                "usage_score": round(score, 1),
                "recommendation": rec,
                "save_for": save_for,
                "key_reason": analysis["reasoning"][2] if len(analysis["reasoning"]) > 2 else analysis["reasoning"][0] if analysis["reasoning"] else "",
            })

        full_df = pd.DataFrame(rows).sort_values("usage_score", ascending=False).reset_index(drop=True)
        full_df["pick_rank"] = full_df.index + 1

        # Picks: players the system says to USE (not SAVE or CANNOT USE)
        save_recs = {"SAVE", "DEFINITELY SAVE", "CANNOT USE"}
        picks_df = full_df[~full_df["recommendation"].isin(save_recs)].head(n_picks).reset_index(drop=True)
        save_df = full_df[full_df["recommendation"].isin(save_recs)].reset_index(drop=True)

        return {
            "tournament": tournament_name,
            "tournament_tier": tournament_tier,
            "tournament_importance": tournament_importance,
            "picks": picks_df,
            "save_list": save_df,
            "full_ranking": full_df,
            "upcoming_events": upcoming[:5],
        }

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
        # Imported lazily because this module may not exist in all setups.
        try:
            from scripts.predictions.usage_planner import SeasonUsagePlanner  # type: ignore
        except Exception:
            try:
                from usage_planner import SeasonUsagePlanner  # type: ignore
            except Exception:
                SeasonUsagePlanner = None

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
        if SeasonUsagePlanner is None:
            print("usage_planner module not found. Install/create scripts/predictions/usage_planner.py to use --plan-season.")
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
