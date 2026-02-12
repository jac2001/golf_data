#!/usr/bin/env python3
"""
Fantasy Golf AI Assistant
==========================
An intelligent assistant that understands fantasy golf rules, has access to
predictions and historical data, and provides strategic advice.

Features:
- Knows fantasy golf rules (3-uses, salary caps, roster construction)
- Access to current predictions and historical performance
- Learns from past predictions vs results
- Provides pick recommendations with reasoning
- Answers strategic questions

Usage:
    # CLI mode
    python golf_assistant.py --tournament "The Masters"

    # Interactive chat
    python golf_assistant.py --chat

    # Single question
    python golf_assistant.py --question "Should I use Scottie Scheffler this week?"
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import re
import shlex
import subprocess

# Project paths - use relative path from this file
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Import UsageOptimizer for strategic recommendations
try:
    from scripts.predictions.usage_optimizer import UsageOptimizer, TournamentCalendar
except ImportError:
    try:
        from usage_optimizer import UsageOptimizer, TournamentCalendar
    except ImportError:
        UsageOptimizer = None
        TournamentCalendar = None

# Season usage planner (weekly allocation)
try:
    from scripts.predictions.usage_planner import SeasonUsagePlanner # type: ignore
except ImportError:
    try:
        from usage_planner import SeasonUsagePlanner # type: ignore
    except ImportError:
        SeasonUsagePlanner = None

# Import Season Planner for full-season optimization
try:
    from scripts.planning.season_planner import (
        recommend_tournaments_for_player,
        load_player_qualifications,
        get_player_tournament_schedule,
        TOURNAMENT_CALENDAR_2026,
    )
    SEASON_PLANNER_AVAILABLE = True
except ImportError:
    # Try relative import when running as a script
    try:
        import sys
        from pathlib import Path
        # Add project root to path if not already there
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from scripts.planning.season_planner import (
            recommend_tournaments_for_player,
            load_player_qualifications,
            get_player_tournament_schedule,
            TOURNAMENT_CALENDAR_2026,
        )
        SEASON_PLANNER_AVAILABLE = True
    except ImportError:
        SEASON_PLANNER_AVAILABLE = False

# Scoring engine (planning view)
try:
    from scripts.planning.scoring_engine import ScoringEngine
    SCORING_ENGINE_AVAILABLE = True
except ImportError:
    try:
        from scoring_engine import ScoringEngine
        SCORING_ENGINE_AVAILABLE = True
    except ImportError:
        SCORING_ENGINE_AVAILABLE = False

# Import Player ROI analytics
try:
    from scripts.analysis.player_roi import (
        load_roi_data,
        get_player_roi_summary,
        normalize_player_name as roi_normalize_name,
        PlayerROI,
    )
    ROI_DATA_AVAILABLE = True
except ImportError:
    try:
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from scripts.analysis.player_roi import (
            load_roi_data,
            get_player_roi_summary,
            normalize_player_name as roi_normalize_name,
            PlayerROI,
        )
        ROI_DATA_AVAILABLE = True
    except ImportError:
        ROI_DATA_AVAILABLE = False
        load_roi_data = None
        get_player_roi_summary = None


class QuestionParser:
    """Parse user questions to determine intent and extract entities."""

    # Intent patterns (regex, intent, required_entities)
    # NOTE: Patterns are checked in order - more specific patterns should come first
    INTENT_PATTERNS = [
        # Dashboard / help
        (r"(?:season optimizer dashboard|season dashboard|optimizer dashboard|season allocations|all tournaments with importance|season overview)", "season_dashboard", []),
        (r"(?:what can i ask|example questions|examples|help)", "help_questions", []),
        # Scoring engine - specific patterns BEFORE general ones
        (r"(?:scoring engine|planning)\s+(?:this week|current week|for this week)", "scoring_engine_this_week", []),
        (r"(?:scoring engine|planning)\s+value\s+(?:picks|plays)(?:\s+(?:for|this week))?", "scoring_engine_value", []),
        (r"(?:scoring engine|planning)\s+strategy\s+(?:dashboard|overview)", "scoring_engine_strategy", []),
        (r"(?:optimize|optimization)\s+(?:remaining\s+)?uses?\s+(?:for\s+)?(.+?)(?:\?|$)", "scoring_engine_optimize", ["player"]),
        (r"(?:scoring engine|planning)\s+(?:for|at)\s+(.+?)(?:\?|$)", "scoring_engine_tournament", ["tournament"]),
        (r"(?:scoring engine)\s+(?:for|on)\s+player\s+(.+?)(?:\?|$)", "scoring_engine_player", ["player"]),
        (r"(?:best)\s+tournaments?\s+for\s+(.+?)(?:\?|$)", "scoring_engine_player", ["player"]),
        # General scoring engine pattern (last)
        (r"(?:scoring engine|planning engine|planning picks|strategy scores|usage scores)$", "scoring_engine_recs", []),

        # Run predictions / pipeline helpers
        (r"(?:run|generate|make)\s+predictions?(?:\s+for\s+(.+?))?(?:\?|$)", "run_predictions", ["tournament"]),
        (r"(?:confirm|yes|go ahead|run it)\s+(?:predictions?|that)", "confirm_run_predictions", []),
        (r"(?:cancel|stop|nevermind|never mind)\s+(?:predictions?|that)", "cancel_run_predictions", []),

        # Season planning questions (check BEFORE player_decision)
        (r"(?:when should i use|best (?:time|tournaments?) to use)\s+(.+?)(?:\s+(?:this|next|last)\s+(?:season|year|week)|\?|$)", "player_usage_strategy", ["player"]),
        (r"(?:which tournaments?|what events?)\s+(?:should i use|to use)\s+(.+?)(?:\s+(?:this|next|last)\s+(?:season|year|week)|\?|$)", "player_usage_strategy", ["player"]),
        (r"(?:season plan|usage plan|usage strategy)\s+(?:for\s+)?(.+?)(?:\s+(?:this|next|last)\s+(?:season|year|week)|\?|$)", "player_usage_strategy", ["player"]),
        (r"(?:plan|optimize|schedule)\s+(?:my\s+)?(?:uses?|picks?)\s+(?:for\s+)?(.+?)(?:\s+(?:this|next|last)\s+(?:season|year|week)|\?|$)", "player_usage_strategy", ["player"]),

        # Player-specific questions (current week)
        (r"(?:should i|do i|can i).*(?:use|play|start|roster)\s+(.+?)(?:\?|$|this|at)", "player_decision", ["player"]),
        (r"(?:tell me about|analyze|analysis of|info on|what about)\s+(.+?)(?:\?|$)", "player_analysis", ["player"]),
        (r"why is\s+(.+?)\s+(?:ranked|rated|projected)\s+(?:so\s+)?(?:high|low|#?\d+)", "player_ranking_reason", ["player"]),
        (r"how (?:has|is|did)\s+(.+?)\s+(?:playing|performed|doing|been)", "player_form", ["player"]),

        # Comparison questions
        (r"(?:compare|vs|versus|or)\s+(.+?)\s+(?:vs|versus|or|and|compared to)\s+(.+?)(?:\?|$)", "compare_players", ["player1", "player2"]),
        (r"(?:who.?s|which is)\s+better[,:\s]+(.+?)\s+(?:vs|or|versus)\s+(.+?)(?:\?|$)", "compare_players", ["player1", "player2"]),
        (r"(.+?)\s+(?:vs|versus|or)\s+(.+?)(?:\?|$)", "compare_players", ["player1", "player2"]),

        # Value/strategy questions
        (r"(?:best|top)\s+(?:value|bargain|sleeper|cheap)(?:\s+(?:play|pick|player))?s?", "value_plays", []),
        (r"(?:who|which players?)\s+(?:has|have)\s+(?:the\s+)?best\s+(?:course\s+)?fit", "course_fit", []),
        (r"(?:who|which players?)\s+should i\s+(?:avoid|skip|fade)", "avoid_players", []),
        (r"(?:who|which players?)\s+(?:are|is)\s+(?:overrated|overvalued)", "avoid_players", []),
        (r"(?:best|optimal|recommended)\s+lineup", "lineup", []),
        (r"(?:give|show|get)\s+(?:me\s+)?(?:a\s+)?lineup", "lineup", []),

        # Betting/odds questions
        (r"(?:what|how).+(?:odds|betting|lines?)\s+(?:for|on)\s+(.+?)(?:\?|$)", "player_odds", ["player"]),
        (r"(?:odds|betting|lines?)\s+(?:for|on)\s+(.+?)(?:\?|$)", "player_odds", ["player"]),
        (r"(?:dds|odds)\s+(?:for|on)\s+(.+?)(?:\?|$)", "player_odds", ["player"]),
        # Power rankings
        (r"(?:power rankings?)\s+(?:for|on)\s+(.+?)(?:\?|$)", "power_rank_player", ["player"]),
        (r"(?:power rankings?|rankings)\s+(?:this week|current week|top\s+\d+)?(?:\?|$)", "power_rankings_list", []),
        (r"(?:who|which).+(?:odds|betting).+(?:moving|shortening|lengthening|up|down)", "odds_movement", []),
        (r"(?:sharps?|money|action).+(?:on|like|backing)", "sharp_action", []),
        (r"(?:odds|betting)\s+favorites?(?:\s+top\s+\d+)?", "odds_favorites", []),
        (r"(?:who|which).+(?:favorites?|chalk|longshots?|underdogs?)", "odds_favorites", []),
        (r"(?:model|our).+(?:vs|versus|agree|disagree).+(?:vegas|odds|betting)", "model_vs_odds", []),
        (r"(?:expert|experts).+(?:picks?|like|fade)", "expert_picks_question", []),

        # Stats/info questions
        (r"field\s+(?:strength|quality|size)", "field_info", []),
        (r"(?:what|how).+(?:purse|payout|prize|money)", "tournament_info", []),
        (r"(?:what|which)\s+(?:type|kind)\s+(?:of\s+)?(?:event|tournament)", "tournament_info", []),
        (r"course\s+(?:profile|characteristics|info|weights)", "course_info", []),
        (r"(?:course|venue)\s+(?:history|results?)\s+(?:for|of)\s+(.+?)(?:\?|$)", "course_history", ["player"]),
        (r"(?:how|what).+(?:played|performed|done)\s+(?:here|at this course|at tpc)", "course_history", []),

        # Usage questions
        (r"(?:who|which players?)\s+(?:have|has)\s+(?:uses?|picks?)\s+(?:left|remaining)", "usage_status", []),
        (r"(?:how many|what)\s+uses?\s+(?:does|do)\s+(.+?)\s+have", "player_usage", ["player"]),

        # General questions
        (r"(?:who|which)\s+(?:are\s+)?(?:the\s+)?top\s+(\d+)?", "top_players", ["count"]),
        (r"(?:give|show|list)\s+(?:me\s+)?(?:the\s+)?(?:top|best)\s+(\d+)?", "top_players", ["count"]),
    ]

    @classmethod
    def parse(cls, question: str) -> Dict[str, Any]:
        """
        Parse a question to extract intent and entities.

        Returns:
            Dict with 'intent', 'entities', and 'confidence'
        """
        question_lower = question.lower().strip()

        for pattern, intent, entity_names in cls.INTENT_PATTERNS:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                entities = {}
                for i, name in enumerate(entity_names):
                    if i < len(match.groups()):
                        value = match.group(i + 1)
                        if value:
                            # Clean up player names
                            value = value.strip().rstrip("?.,!").strip()
                            value = re.sub(r"\s+", " ", value)
                            value = cls._clean_player_entity(value)
                            entities[name] = value

                return {
                    "intent": intent,
                    "entities": entities,
                    "confidence": 0.8,
                    "raw_question": question
                }

        # Default: unknown intent
        return {
            "intent": "unknown",
            "entities": {},
            "confidence": 0.3,
            "raw_question": question
        }

    @staticmethod
    def _clean_player_entity(value: str) -> str:
        """Strip trailing season/week qualifiers from player entity."""
        if not value:
            return value
        # Remove common trailing qualifiers like "this season/year/week"
        value = re.sub(r"\b(this|next|last)\s+(season|year|week)\b.*$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(this season|this year|this week)\b", "", value, flags=re.IGNORECASE)
        return value.strip()

    @classmethod
    def extract_player_names(cls, text: str, known_players: List[str] = None) -> List[str]:
        """Extract player names from text using fuzzy matching."""
        if not known_players:
            return []

        text_lower = text.lower()
        found = []

        for player in known_players:
            player_lower = player.lower()
            # Check for full name
            if player_lower in text_lower:
                found.append(player)
                continue
            # Check for last name only
            parts = player_lower.split()
            if len(parts) >= 2:
                last_name = parts[-1]
                if len(last_name) > 3 and last_name in text_lower:
                    found.append(player)

        return found


class FantasyGolfRules:
    """Knowledge base for fantasy golf rules and strategy."""

    # Common fantasy golf formats
    FORMATS = {
        "earnings": {
            "name": "Season-Long Earnings League",
            "roster_size": 3,
            "salary_cap": None,
            "uses_per_player": 3,
            "season_tournaments": 30,
            "scoring": "actual_earnings",
            "scoring_description": "Players earn their actual PGA Tour prize money. Only players who make the cut earn money.",
            "strategy_notes": [
                "3 uses per player per season - CRITICAL constraint for elite players",
                "Save elite players (Scheffler, etc.) for MAJORS and high-purse signature events",
                "Expected Value (EV) = probability of finishing positions × prize money at those positions",
                "Higher purse tournaments = more valuable weeks to use top players",
                "Missed cuts earn $0 - consider cut probability when picking lower-ranked players",
                "With only 3 picks per week, focus on CEILING over floor",
                "Course fit can make mid-tier players outperform their ranking",
            ]
        }
       
    }

    # Tournament types and their strategic importance
    TOURNAMENT_TYPES = {
        "major": {
            "name": "Major Championship",
            "purse_range": "$15M-$20M",
            "importance": "HIGHEST",
            "strategy": "Use your best players - these are the most valuable weeks",
            "examples": ["The Masters", "PGA Championship", "US Open", "The Open"]
        },
        "signature": {
            "name": "Signature Event",
            "purse_range": "$20M+",
            "importance": "HIGH",
            "strategy": "Strong fields, big purses - worth using Tier 1 players",
            "examples": ["The Players", "Genesis Invitational", "Arnold Palmer Inv."]
        },
        "playoff": {
            "name": "FedEx Playoff",
            "purse_range": "$20M-$100M",
            "importance": "VERY HIGH",
            "strategy": "Smaller fields, elite players only - high EV opportunity",
            "examples": ["FedEx St. Jude", "BMW Championship", "Tour Championship"]
        },
        "standard": {
            "name": "Standard Event",
            "purse_range": "$8M-$10M",
            "importance": "MODERATE",
            "strategy": "Save elite players unless they have exceptional course fit",
            "examples": ["Most regular tour events"]
        },
        "opposite": {
            "name": "Opposite Field Event",
            "purse_range": "$7M-$9M",
            "importance": "LOWER",
            "strategy": "Weaker fields - good for value plays, avoid using elite uses",
            "examples": ["Puerto Rico Open", "Barbasol Championship"]
        }
    }

    # Player tier definitions
    PLAYER_TIERS = {
        "tier1": {
            "name": "Elite",
            "world_rank_range": "1-15",
            "strategy": "Reserve for majors and signature events. Max 1 per lineup for balance.",
            "expected_top10_rate": "40-50%"
        },
        "tier2": {
            "name": "Strong",
            "world_rank_range": "16-40",
            "strategy": "Good for course fits and current form. More flexible usage.",
            "expected_top10_rate": "25-35%"
        },
        "tier3": {
            "name": "Solid",
            "world_rank_range": "41-80",
            "strategy": "Value plays when form or course fit is strong.",
            "expected_top10_rate": "15-25%"
        },
        "tier4": {
            "name": "Value",
            "world_rank_range": "80+",
            "strategy": "High variance - use when specific edge exists.",
            "expected_top10_rate": "5-15%"
        }
    }

    @classmethod
    def get_format_rules(cls, format_name: str = "earnings") -> Dict:
        """Get rules for a specific fantasy format."""
        return cls.FORMATS.get(format_name.lower(), cls.FORMATS["earnings"])

    @classmethod
    def get_tournament_strategy(cls, tournament_type: str) -> Dict:
        """Get strategy for a tournament type."""
        return cls.TOURNAMENT_TYPES.get(tournament_type.lower(), cls.TOURNAMENT_TYPES["standard"])

    @classmethod
    def get_tier_strategy(cls, world_rank: int) -> Dict:
        """Get tier and strategy based on world ranking."""
        if world_rank <= 15:
            return cls.PLAYER_TIERS["tier1"]
        elif world_rank <= 40:
            return cls.PLAYER_TIERS["tier2"]
        elif world_rank <= 80:
            return cls.PLAYER_TIERS["tier3"]
        else:
            return cls.PLAYER_TIERS["tier4"]


class GolfAssistant:
    """AI-powered fantasy golf assistant."""

    def __init__(self, format_name: str = "earnings", predictions_path: str = None):
        """
        Initialize the golf assistant.

        Args:
            format_name: Fantasy format (earnings, draftkings, fanduel)
            predictions_path: Optional path to specific predictions file to load
        """
        self.format = FantasyGolfRules.get_format_rules(format_name)
        self.rules = FantasyGolfRules()

        # Load data sources
        self.predictions = None
        self.usage_tracker = None
        self.learnings = None
        self.course_weights = None
        self.betting_profiles = None  # Rich betting/form data from PGA Tour
        self.power_rankings = None    # Power rankings table (rank + analysis)
        self.article_blurbs = None  # Scraped betting-profile articles
        self.expert_picks = None     # Expert picks for comparison
        self.pga_expert_picks = None  # PGA Tour expert picks with lineups
        self.current_tournament = None
        self._predictions_path = predictions_path
        self._player_name_map: Dict[int, str] = {}
        self.historical_picks = None
        self.player_roi_data = None  # Historical ROI metrics from fantasy results
        self.scoring_engine = None
        self._pending_action: Optional[Dict[str, Any]] = None

        # Initialize usage optimizer for strategic recommendations
        self.usage_optimizer = None
        if UsageOptimizer is not None:
            try:
                self.usage_optimizer = UsageOptimizer(max_uses=self.format.get('uses_per_player', 3) or 3)
            except Exception:
                pass

        # Conversation history for multi-turn reasoning
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10

        self._load_data()

    def _intent_directives(self, intent: str) -> List[str]:
        """Intent-specific guidance for the LLM."""
        mapping = {
            "player_decision": [
                "- Make a clear yes/no recommendation and name 1-2 backups.",
                "- Emphasize upside vs. season-long uses; state whether to burn a use now.",
            ],
            "player_analysis": [
                "- Provide a concise scouting report: form, course fit, and risk flags.",
            ],
            "compare_players": [
                "- Pick a winner and explain why; only one answer.",
                "- State if differences are small (toss-up) or meaningful.",
            ],
            "value_plays": [
                "- Focus on under-the-radar/value options; avoid obvious chalk unless necessary.",
            ],
            "lineup": [
                "- Return a complete lineup with brief roles (stud/value/leverage).",
            ],
            "avoid_players": [
                "- List fades with reasons (injury, poor fit, form).",
            ],
            "player_odds": [
                "- Show current odds and movement direction (UP = sharps like, DOWN = fading).",
                "- Compare implied probability vs model probability to find value.",
                "- Mention any expert picks or fades for this player.",
            ],
            "odds_movement": [
                "- List players with significant odds movement this week.",
                "- Explain what movement typically signals (sharps vs public).",
            ],
            "odds_favorites": [
                "- List the betting favorites with odds and implied probabilities.",
                "- Note which favorites our model agrees/disagrees with.",
            ],
            "model_vs_odds": [
                "- Show where model and Vegas disagree significantly.",
                "- Highlight potential value plays (model higher than odds).",
                "- Note expert fades that conflict with model picks.",
            ],
            "expert_picks_question": [
                "- Summarize expert consensus picks and fades.",
                "- Compare expert picks with our model recommendations.",
                "- Note any disagreements and explain which side has merit.",
            ],
            "course_history": [
                "- Show detailed course history from PGA Tour data.",
                "- Include results, finishes, and earnings at this venue.",
                "- Note if player has won or consistently performed here.",
            ],
        }
        return mapping.get(intent, [])

    def _clean_tournament_name(self, filename: str) -> str:
        """Clean tournament name from filename."""
        name = filename.replace("_predictions", "").replace("_", " ")
        # Remove date suffixes (e.g., "20260123")
        name = re.sub(r"\s*\d{8}$", "", name)
        # Remove year suffixes
        name = re.sub(r"\s*20\d{2}$", "", name)
        return name.title()
    

    def _load_data(self):
        """Load available data sources."""
        # Load predictions - either from specified path or most recent file
        if self._predictions_path:
            pred_path = Path(self._predictions_path)
            if pred_path.exists():
                self.predictions = pd.read_csv(pred_path)
                self.current_tournament = self._clean_tournament_name(pred_path.stem)
        else:
            # First try consistent "latest" pointer
            latest_path = OUTPUTS_DIR / "latest_predictions.csv"
            if latest_path.exists():
                self.predictions = pd.read_csv(latest_path)
                self.current_tournament = self._clean_tournament_name(latest_path.stem.replace("_latest", ""))
            else:
                # Load most recent predictions (sorted by modification time, newest first)
                prediction_files = list(OUTPUTS_DIR.glob("*_predictions.csv"))
                if prediction_files:
                    prediction_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                    self.predictions = pd.read_csv(prediction_files[0])
                    self.current_tournament = self._clean_tournament_name(prediction_files[0].stem)

        # Normalize player names (replace placeholders like 'Player 57550')
        self._load_player_name_map()
        self._fix_prediction_names()

        # Load usage tracker
        tracker_file = OUTPUTS_DIR / "player_usage_tracker.csv"
        if tracker_file.exists():
            self.usage_tracker = pd.read_csv(tracker_file)

        # Load learnings
        learnings_file = DATA_DIR / "prediction_tracking" / "model_learnings.json"
        if learnings_file.exists():
            with open(learnings_file) as f:
                self.learnings = json.load(f)

        # Load course weights
        weights_file = DATA_DIR / "course_sg_weights.csv"
        if weights_file.exists():
            self.course_weights = pd.read_csv(weights_file)

        # Load betting profiles (rich PGA Tour data)
        self._load_betting_profiles()
        # Load power rankings if available
        self._load_power_rankings()
        # Load article blurbs (scraped betting-profile narratives)
        self._load_article_blurbs()
        # Load expert picks for comparison
        self._load_expert_picks()
        # Load PGA Tour expert picks (with full lineups)
        self._load_pga_expert_picks()
        # Load historical fantasy picks (for context only)
        self._load_historical_picks()
        # Load player ROI data (historical performance analytics)
        self._load_roi_data()
        # Load scoring engine (planning view)
        self._load_scoring_engine()

    def _load_scoring_engine(self):
        """Initialize scoring engine if available."""
        if not SCORING_ENGINE_AVAILABLE:
            return
        try:
            # Target current tournament so scoring engine loads matching predictions file
            self.scoring_engine = ScoringEngine(tournament=self.current_tournament)
        except Exception:
            self.scoring_engine = None

    def _load_player_name_map(self):
        """Build a player_id -> player_name lookup from players DB and OWGR files."""
        name_map: Dict[int, str] = {}

        # Players DB (latest files first)
        players_dir = DATA_DIR / "players"
        if players_dir.exists():
            player_files = sorted(players_dir.glob("pga_players_*.csv"),
                                  key=lambda f: f.stat().st_mtime,
                                  reverse=True)
            for pf in player_files:
                try:
                    df = pd.read_csv(pf, usecols=["player_id", "player_name"])
                    df = df.dropna(subset=["player_id"])
                    df["player_id"] = df["player_id"].astype(int)
                    name_map.update(dict(zip(df["player_id"], df["player_name"])))
                except Exception as e:
                    print(f"  Could not load player file {pf.name}: {e}")

        # OWGR rankings (secondary source)
        rankings_dir = DATA_DIR / "rankings"
        if rankings_dir.exists():
            ranking_files = sorted(rankings_dir.glob("owgr_*.csv"),
                                   key=lambda f: f.stat().st_mtime,
                                   reverse=True)
            for rf in ranking_files:
                try:
                    df = pd.read_csv(rf, usecols=["player_id", "player_name"])
                    df = df.dropna(subset=["player_id"])
                    df["player_id"] = df["player_id"].astype(int)
                    name_map.update(dict(zip(df["player_id"], df["player_name"])))
                except Exception as e:
                    print(f"  Could not load rankings file {rf.name}: {e}")

        self._player_name_map = name_map

    def _load_historical_picks(self):
        """Load historical fantasy picks (for context; does not affect usage tracking)."""
        hist_dir = DATA_DIR / "historical"
        if not hist_dir.exists():
            return
        files = sorted(hist_dir.glob("fantasy_results_*.csv"))
        if not files:
            return
        print(f"  Found historical fantasy picks: {len(files)} file(s)")

        records = []
        for f in files:
            try:
                df = pd.read_csv(f)
            except Exception:
                continue

            # Normalize column names
            cols = {c.lower().strip(): c for c in df.columns}
            tournament_col = cols.get("tournament", None)
            year_col = cols.get("year", None)

            starters = [
                (cols.get("starter #1"), cols.get("earnings")),
                (cols.get("starter #2"), cols.get("earnings.1")),
                (cols.get("starter #3"), cols.get("earnings.2")),
            ]

            for _, row in df.iterrows():
                tournament = row.get(tournament_col, "") if tournament_col else ""
                year = row.get(year_col, "") if year_col else ""
                for starter_col, earn_col in starters:
                    if not starter_col:
                        continue
                    name = row.get(starter_col, "")
                    if not name or pd.isna(name):
                        continue
                    earnings_raw = row.get(earn_col, "") if earn_col else ""
                    earnings = None
                    if isinstance(earnings_raw, str):
                        cleaned = earnings_raw.replace("$", "").replace(",", "").strip()
                        try:
                            earnings = float(cleaned)
                        except Exception:
                            earnings = None
                    elif pd.notna(earnings_raw):
                        earnings = float(earnings_raw)

                    records.append({
                        "player_name": str(name).strip(),
                        "tournament": str(tournament).strip(),
                        "year": year,
                        "earnings": earnings,
                    })

        if not records:
            return

        picks_df = pd.DataFrame(records)

        def _norm(n: str) -> str:
            n = str(n or "").lower().strip()
            n = n.replace(",", " ")
            n = re.sub(r"\\s+", " ", n)
            return n

        picks_df["name_key"] = picks_df["player_name"].apply(_norm)
        picks_df["last_name"] = picks_df["name_key"].apply(lambda x: x.split()[-1] if x else "")

        self.historical_picks = picks_df
        print(f"  Loaded historical fantasy picks: {len(picks_df):,} rows")

    def _append_picks_log(self, tournament_name: str, lineup: List[Dict[str, Any]], tournament_type: str = None):
        """Append finalized lineup picks to outputs/picks_log.csv."""
        try:
            log_path = OUTPUTS_DIR / "picks_log.csv"
            date_str = datetime.now().strftime("%Y-%m-%d")
            t_type = tournament_type or "standard"

            pred_lookup = {}
            if self.predictions is not None and 'player_name' in self.predictions.columns:
                for _, row in self.predictions.iterrows():
                    name_key = str(row.get('player_name', '')).strip().lower()
                    if name_key:
                        pred_lookup[name_key] = row

            rows = []
            for p in lineup:
                name = p.get("name", "")
                name_key = name.strip().lower()
                pred = pred_lookup.get(name_key)

                player_id = None
                top5_prob = None
                if pred is not None:
                    player_id = pred.get("player_id")
                    top5_prob = pred.get("top5_prob")
                    win_prob = pred.get("win_prob")
                    top10_prob = pred.get("top10_prob")
                    ev = pred.get("expected_value")
                    world_rank = pred.get("world_rank")
                else:
                    win_prob = p.get("win_prob")
                    top10_prob = p.get("top10_prob")
                    ev = p.get("ev")
                    world_rank = p.get("world_rank")

                rows.append({
                    "date": date_str,
                    "tournament_name": tournament_name,
                    "tournament_type": t_type,
                    "player_id": player_id,
                    "player_name": name,
                    "expected_value": ev,
                    "win_prob": win_prob,
                    "top5_prob": top5_prob,
                    "top10_prob": top10_prob,
                    "world_rank": world_rank,
                    "usage_recommendation": p.get("usage_recommendation"),
                    "uses_remaining": p.get("uses_remaining"),
                })

            if not rows:
                return

            df = pd.DataFrame(rows)
            if log_path.exists():
                existing = pd.read_csv(log_path)
                df = pd.concat([existing, df], ignore_index=True)

            log_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(log_path, index=False)
        except Exception as e:
            print(f"  Could not append picks log: {e}")

    def _load_roi_data(self):
        """Load player ROI analytics from historical fantasy results."""
        if not ROI_DATA_AVAILABLE or load_roi_data is None:
            return

        try:
            self.player_roi_data = load_roi_data()
            if self.player_roi_data:
                print(f"  Loaded player ROI data: {len(self.player_roi_data)} players")
        except Exception as e:
            print(f"  Could not load ROI data: {e}")

    def _get_player_roi(self, player_name: str) -> Optional[str]:
        """Get ROI summary for a player."""
        if not self.player_roi_data or not ROI_DATA_AVAILABLE:
            return None

        try:
            return get_player_roi_summary(player_name, self.player_roi_data)
        except Exception:
            return None

    def _get_historical_pick_info(self, player_name: str) -> Optional[Dict[str, Any]]:
        """Get historical fantasy pick context for a player (approximate)."""
        if self.historical_picks is None or not player_name:
            return None

        def _norm(n: str) -> str:
            n = str(n or "").lower().strip()
            n = n.replace(",", " ")
            n = re.sub(r"\\s+", " ", n)
            return n

        name_key = _norm(player_name)
        df = self.historical_picks

        exact = df[df["name_key"] == name_key]
        approx = False
        if exact.empty:
            last = name_key.split()[-1] if name_key else ""
            if not last:
                return None
            exact = df[df["last_name"] == last]
            approx = True

        if exact.empty:
            return None

        tournaments = exact["tournament"].dropna().astype(str).unique().tolist()
        earnings = exact["earnings"].dropna().tolist()
        total_earnings = sum(earnings) if earnings else None
        avg_earnings = (sum(earnings) / len(earnings)) if earnings else None

        return {
            "picks": len(exact),
            "tournaments": tournaments[:5],
            "total_earnings": total_earnings,
            "avg_earnings": avg_earnings,
            "approximate": approx,
        }

    def _fix_prediction_names(self):
        """Replace placeholder names in self.predictions using the lookup map."""
        if self.predictions is None or not self._player_name_map:
            return
        if "player_id" not in self.predictions.columns or "player_name" not in self.predictions.columns:
            return

        df = self.predictions
        try:
            df["_pid_int"] = df["player_id"].astype(int)
        except Exception:
            df["_pid_int"] = df["player_id"]

        mask = df["player_name"].isna() | df["player_name"].str.match(r"Player\s+\d+", na=False)
        if mask.any():
            df.loc[mask, "player_name"] = (
                df.loc[mask, "_pid_int"].map(self._player_name_map).fillna(df.loc[mask, "player_name"])
            )

        df.drop(columns=["_pid_int"], inplace=True, errors="ignore")

    def _load_betting_profiles(self):
        """Load betting profiles if available for current tournament."""
        profiles_dir = DATA_DIR / "betting_profiles"
        if not profiles_dir.exists():
            return

        # Try to find matching profile file
        profile_files = list(profiles_dir.glob("betting_profiles_*.csv"))
        if profile_files:
            # Sort by modification time, use most recent
            profile_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            try:
                self.betting_profiles = pd.read_csv(profile_files[0])
                print(f"  Loaded betting profiles: {profile_files[0].name}")
            except Exception as e:
                print(f"  Could not load betting profiles: {e}")

    def _load_article_blurbs(self):
        """Load betting-profile article blurbs if available."""
        blurbs_path_csv = DATA_DIR / "betting_profiles" / "article_blurbs.csv"
        blurbs_path_jsonl = DATA_DIR / "betting_profiles" / "article_blurbs.jsonl"

        try:
            if blurbs_path_csv.exists():
                df = pd.read_csv(blurbs_path_csv)
            elif blurbs_path_jsonl.exists():
                df = pd.read_json(blurbs_path_jsonl, lines=True)
            else:
                return
            # Normalize lookup key
            if "player_name" in df.columns:
                df["key"] = df["player_name"].str.lower().str.strip()
            self.article_blurbs = df
            print(f"  Loaded article blurbs: {blurbs_path_csv.name if blurbs_path_csv.exists() else blurbs_path_jsonl.name}")
        except Exception as e:
            print(f"  Could not load article blurbs: {e}")

    def _load_expert_picks(self):
        """Load expert picks for comparison with model predictions."""
        expert_dir = DATA_DIR / "expert_picks"
        if not expert_dir.exists():
            return

        # Try latest first, then tournament-specific
        latest_path = expert_dir / "expert_picks_latest.csv"
        if latest_path.exists():
            try:
                self.expert_picks = pd.read_csv(latest_path)
                if "player_name" in self.expert_picks.columns:
                    self.expert_picks["key"] = self.expert_picks["player_name"].str.lower().str.strip()
                print(f"  Loaded expert picks: {len(self.expert_picks)} picks")
            except Exception as e:
                print(f"  Could not load expert picks: {e}")

    def _load_pga_expert_picks(self):
        """Load PGA Tour expert picks with full lineup data."""
        expert_dir = DATA_DIR / "expert_picks"
        if not expert_dir.exists():
            return

        # Look for PGA expert picks file (ep_table format)
        pga_files = list(expert_dir.glob("expert_picks_ep_table*.csv"))
        if not pga_files:
            return

        try:
            # Use most recent file
            pga_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            df = pd.read_csv(pga_files[0])
            self.pga_expert_picks = df
            print(f"  Loaded PGA Tour expert picks: {len(df)} experts from {pga_files[0].name}")
        except Exception as e:
            print(f"  Could not load PGA expert picks: {e}")

    def _get_pga_expert_pick_info(self, player_name: str) -> Optional[Dict]:
        """Get PGA Tour expert pick info for a player (lineup, bench, winner)."""
        if self.pga_expert_picks is None:
            return None

        # Normalize player name for matching
        name_lower = player_name.lower().strip()
        # Handle "Last, First" format
        if ',' in name_lower:
            parts = name_lower.split(',')
            name_lower = f"{parts[1].strip()} {parts[0].strip()}"

        # Search through each expert's lineup, bench, and winner
        in_lineup = []
        on_bench = []
        picked_to_win = []

        for _, row in self.pga_expert_picks.iterrows():
            expert = row.get('expert_name', 'Unknown')
            expert_title = row.get('expert_title', '')
            comment = row.get('comment', '')

            # Check lineup
            try:
                lineup_names = json.loads(row.get('lineup_player_names', '[]'))
                if any(name_lower in n.lower() for n in lineup_names):
                    in_lineup.append({
                        'expert': expert,
                        'title': expert_title,
                        'comment': comment
                    })
            except (json.JSONDecodeError, TypeError):
                pass

            # Check bench
            try:
                bench_names = json.loads(row.get('bench_player_names', '[]'))
                if any(name_lower in n.lower() for n in bench_names):
                    on_bench.append({
                        'expert': expert,
                        'title': expert_title
                    })
            except (json.JSONDecodeError, TypeError):
                pass

            # Check winner pick
            winner_name = row.get('winner_name', '')
            if winner_name and name_lower in winner_name.lower():
                picked_to_win.append({
                    'expert': expert,
                    'title': expert_title,
                    'comment': comment
                })

        if not in_lineup and not on_bench and not picked_to_win:
            return None

        return {
            'in_lineup': in_lineup,
            'on_bench': on_bench,
            'picked_to_win': picked_to_win,
            'lineup_count': len(in_lineup),
            'bench_count': len(on_bench),
            'winner_count': len(picked_to_win),
            'total_experts': len(self.pga_expert_picks),
        }

    def _get_expert_pick_info(self, player_name: str) -> Optional[Dict]:
        """Get expert pick information for a player."""
        if self.expert_picks is None or "key" not in self.expert_picks.columns:
            return None

        key = player_name.lower().strip()
        # Handle "Last, First" format
        if ',' in key:
            parts = key.split(',')
            key = f"{parts[1].strip()} {parts[0].strip()}"

        df = self.expert_picks
        rows = df[df["key"] == key]
        if rows.empty:
            # Try partial match on last name
            last_name = key.split()[-1] if key else ""
            rows = df[df["key"].str.contains(last_name, na=False)]

        if rows.empty:
            return None

        # Aggregate info from all sources
        picks = []
        fades = []
        for _, r in rows.iterrows():
            pick_type = r.get("pick_type", "")
            source = r.get("source", "Unknown")
            note = r.get("note", "")

            if pick_type == "fade":
                fades.append({"source": source, "note": note})
            else:
                picks.append({"source": source, "type": pick_type, "note": note})

        return {
            "is_expert_pick": len(picks) > 0,
            "is_expert_fade": len(fades) > 0,
            "pick_sources": picks,
            "fade_sources": fades,
            "consensus_count": len(picks),
        }

    def _get_expert_comparison_summary(self) -> Optional[str]:
        """Get summary of model vs expert picks comparison."""
        if self.expert_picks is None or self.predictions is None:
            return None

        try:
            # Normalize names for matching
            def normalize(name):
                if pd.isna(name):
                    return ""
                name = str(name).lower().strip()
                if ',' in name:
                    parts = name.split(',')
                    name = f"{parts[1].strip()} {parts[0].strip()}"
                return name

            model_top = self.predictions.nlargest(15, 'expected_value')
            model_names = set(model_top['player_name'].apply(normalize).tolist())

            expert_picks_df = self.expert_picks[self.expert_picks['pick_type'] != 'fade']
            expert_fades_df = self.expert_picks[self.expert_picks['pick_type'] == 'fade']

            expert_names = set(expert_picks_df['key'].tolist())
            fade_names = set(expert_fades_df['key'].tolist())

            # Find overlaps
            agreements = model_names & expert_names
            model_faded = model_names & fade_names

            lines = ["## Expert Picks Comparison"]
            lines.append(f"- Model agrees with experts on: {len(agreements)} of top 15 picks")

            if model_faded:
                lines.append(f"- ⚠️ Model likes but experts FADE: {len(model_faded)} players")
                for name in list(model_faded)[:3]:
                    fade_info = expert_fades_df[expert_fades_df['key'] == name].iloc[0]
                    note = fade_info.get('note', '')
                    lines.append(f"  - {name.title()}: {note[:80]}...")

            return "\n".join(lines)
        except Exception:
            return None

    def _load_power_rankings(self):
        """Load power rankings table if available."""
        pr_dir = DATA_DIR / "power_rankings"
        if not pr_dir.exists():
            return

        # Filter out metadata files (paths.csv, etc.) and find actual rankings
        pr_files = [
            f for f in pr_dir.glob("*.csv")
            if f.name not in ("paths.csv",) and not f.name.startswith(".")
        ]
        if not pr_files:
            return

        # Sort by modification time, newest first
        pr_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Try to find a file with the current tournament, or fall back to most recent
        target_file = None
        if self.current_tournament:
            # Normalize tournament name for matching
            t_lower = self.current_tournament.lower().replace(" ", "_").replace("-", "_")
            for f in pr_files:
                if t_lower in f.name.lower().replace("-", "_"):
                    target_file = f
                    break

        if not target_file:
            target_file = pr_files[0]

        try:
            df = pd.read_csv(target_file)
            # Validate it has the expected columns
            if "player_name" in df.columns and "rank" in df.columns:
                self.power_rankings = df
                self.power_rankings["key"] = self.power_rankings["player_name"].str.lower().str.strip()
                print(f"  Loaded power rankings: {target_file.name} ({len(df)} players)")
            else:
                print(f"  Skipping {target_file.name}: missing required columns")
        except Exception as e:
            print(f"  Could not load power rankings: {e}")

    def _get_betting_profile(self, player_name: str) -> Optional[Dict]:
        """Get betting profile for a player."""
        if self.betting_profiles is None:
            return None

        # Fuzzy match
        matches = self.betting_profiles[
            self.betting_profiles['player_name'].str.lower().str.contains(
                player_name.lower(), na=False
            )
        ]
        if len(matches) > 0:
            row = matches.iloc[0]
            result = {
                "odds_to_win": row.get("odds_to_win", ""),
                "odds_swing": row.get("odds_swing", ""),
                "odds_rank": row.get("odds_rank"),
                "implied_prob": row.get("implied_prob"),
                "fedex_rank": row.get("fedex_rank"),
                "fedex_points": row.get("fedex_points"),
                "events_played": row.get("events_played", 0),
                "wins": row.get("wins", 0),
                "top_10s": row.get("top_10s", 0),
                "top_25s": row.get("top_25s", 0),
                "cuts_made": row.get("cuts_made", 0),
                "recent_form_summary": row.get("recent_form_summary", ""),
                "recent_results": row.get("recent_results", ""),
                # Strokes Gained stats
                "sg_total": row.get("sg_total"),
                "sg_total_rank": row.get("sg_total_rank"),
                "sg_ott": row.get("sg_ott"),
                "sg_ott_rank": row.get("sg_ott_rank"),
                "sg_app": row.get("sg_app"),
                "sg_app_rank": row.get("sg_app_rank"),
                "sg_arg": row.get("sg_arg"),
                "sg_arg_rank": row.get("sg_arg_rank"),
                "sg_putt": row.get("sg_putt"),
                "sg_putt_rank": row.get("sg_putt_rank"),
                "driving_distance": row.get("driving_distance"),
                "driving_accuracy": row.get("driving_accuracy"),
                "gir_pct": row.get("gir_pct"),
                "scrambling_pct": row.get("scrambling_pct"),
                # Course history
                "course_history": row.get("course_history", ""),
                "course_history_summary": row.get("course_history_summary", ""),
            }

            # Parse course history JSON for current tournament
            course_hist_raw = row.get("course_history", "")
            if course_hist_raw and pd.notna(course_hist_raw) and str(course_hist_raw) != "nan":
                try:
                    courses = json.loads(course_hist_raw) if isinstance(course_hist_raw, str) else course_hist_raw
                    result["parsed_course_history"] = self._parse_course_history(courses)
                except (json.JSONDecodeError, TypeError):
                    pass

            return result
        return None

    def _parse_course_history(self, courses: list) -> Dict:
        """Parse course history JSON into useful insights."""
        if not courses:
            return {}

        insights = {
            "total_courses": len(courses),
            "courses": [],
        }

        for course in courses[:5]:  # Limit to top 5 courses
            course_name = course.get("course_name", "Unknown")
            tournaments = course.get("tournaments", [])

            if not tournaments:
                continue

            # Calculate stats at this course
            positions = []
            earnings = []
            for t in tournaments:
                pos = t.get("position", "")
                if pos and pos not in ["CUT", "W/D", "WD", "DQ"]:
                    try:
                        pos_num = int(pos.replace("T", ""))
                        positions.append(pos_num)
                    except (ValueError, TypeError):
                        pass

                winnings = t.get("winnings", "")
                if winnings:
                    try:
                        win_num = float(str(winnings).replace("$", "").replace(",", ""))
                        earnings.append(win_num)
                    except (ValueError, TypeError):
                        pass

            if positions:
                course_info = {
                    "course_name": course_name,
                    "starts": len(tournaments),
                    "avg_finish": sum(positions) / len(positions) if positions else None,
                    "best_finish": min(positions) if positions else None,
                    "total_earnings": sum(earnings) if earnings else 0,
                    "recent_results": [t.get("position") for t in tournaments[:3]],
                }
                insights["courses"].append(course_info)

        return insights

    def _get_article_blurb(self, player_name: str) -> Optional[Dict]:
        """Get article blurb for a player."""
        if self.article_blurbs is None or "key" not in self.article_blurbs.columns:
            return None

        key = player_name.lower().strip()
        df = self.article_blurbs
        row = df[df["key"] == key]
        if row.empty:
            row = df[df["key"].str.startswith(key)]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "title": r.get("title", ""),
            "summary": r.get("summary", ""),
            "body": r.get("body_formatted", r.get("body", "")),
            "published_at": r.get("published_at", ""),
            "url": r.get("url", ""),
        }

    def _get_power_ranking(self, player_name: str) -> Optional[Dict]:
        """Get power rankings entry for a player."""
        if self.power_rankings is None or "key" not in self.power_rankings.columns:
            return None
        key = player_name.lower().strip()
        df = self.power_rankings
        row = df[df["key"] == key]
        if row.empty:
            row = df[df["key"].str.startswith(key)]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "rank": r.get("rank"),
            "analysis": r.get("analysis", ""),
            "source": getattr(self.power_rankings, "name", ""),
        }

    def _build_system_prompt(self, intent: str = "unknown") -> str:
        """Build the system prompt with all context."""
        prompt_parts = [
            "You are the Golf Decision Intelligence Assistant.",
            "You evaluate professional golfers using structured data and expert context to produce fantasy, betting, and strategic recommendations.",
            "",
            "## PERSONALITY & STYLE",
            "- Concise, confident, data-first; portfolio-manager mindset, not a fan.",
            "- Interpret numbers: explain what stats mean for THIS course/week.",
            "- Always classify risk (Low / Medium / High) for recommendations.",
            "- Avoid absolutes or guarantees.",
            "",
            "## REASONING HIERARCHY (must respect order)",
            "1) HARD CONSTRAINTS: fantasy rules, usage limits, roster size, tournament restrictions.",
            "2) PRIMARY SIGNALS: course-fit metrics, recent form stats, strokes-gained trends, surface/distance/scoring profile alignment.",
            "3) SECONDARY SIGNALS (calibration only): betting odds, market implied probabilities, ownership projections (if provided).",
            "4) CONTEXTUAL SIGNALS (support only): power rankings, expert commentary, article blurbs/narratives.",
            "- Contextual signals may NEVER override primary signals.",
            "- If expert/context conflicts with stats: flag conflict, reduce confidence, explain the disagreement.",
            "- If players are statistically similar, use odds and expert input as tiebreakers.",
            "",
            "## HOW TO ANSWER",
            "- Start by respecting hard constraints (uses, roster, format).",
            "- State recommendation + risk profile + decisive primary signals.",
            "- Use odds as calibration only; mention line movement briefly.",
            "- Use betting profiles, power rankings, and article blurbs as supporting context; cite source and date if available.",
            "- For 'why is player X ranked Y?': list the drivers (win/top5 prob, EV, SG trends, course fit) and headwinds.",
            "- For 'power rankings this week?': summarize the power_rankings table (rank + one-line rationale).",
            "- For article/betting questions: surface the relevant snippet and tie it back to primary signals.",
        ]

        intent_notes = self._intent_directives(intent)
        if intent_notes:
            prompt_parts.append("")
            prompt_parts.append("## QUESTION INTENT GUIDANCE")
            prompt_parts.extend(intent_notes)

        prompt_parts.extend([
            "",
            "## LEAGUE FORMAT (CRITICAL - READ CAREFULLY)",
            f"Format: {self.format['name']}",
            f"Weekly Roster: {self.format['roster_size']} golfers per week",
            f"Season Length: {self.format.get('season_tournaments', 30)} tournaments",
        ])

        if self.format.get('uses_per_player'):
            prompt_parts.append(f"Uses Per Player: {self.format['uses_per_player']} times per ENTIRE season")

        # Add scoring description
        if self.format.get('scoring') == 'actual_earnings':
            prompt_parts.extend([
                "",
                "## SCORING SYSTEM",
                "- Players earn their ACTUAL PGA TOUR PRIZE MONEY",
                "- Only players who MAKE THE CUT earn money (missed cut = $0)",
                "- Your weekly score = sum of your 3 golfers' earnings",
                "- Season score = total earnings across all 30 tournaments",
                "- Expected Value (EV) in predictions = probability-weighted expected earnings",
            ])

        if self.format.get('salary_cap'):
            prompt_parts.append(f"Salary Cap: ${self.format['salary_cap']:,}")

        prompt_parts.extend([
            "",
            "## STRATEGY PRINCIPLES",
        ])
        for note in self.format.get('strategy_notes', []):
            prompt_parts.append(f"- {note}")

        # Add tournament type knowledge
        prompt_parts.extend([
            "",
            "## TOURNAMENT TYPES",
        ])
        for t_type, info in FantasyGolfRules.TOURNAMENT_TYPES.items():
            prompt_parts.append(f"- {info['name']}: {info['strategy']}")

        # Add player tier knowledge
        prompt_parts.extend([
            "",
            "## PLAYER TIERS",
        ])
        for tier, info in FantasyGolfRules.PLAYER_TIERS.items():
            prompt_parts.append(f"- {info['name']} (Rank {info['world_rank_range']}): {info['strategy']}")

        # Add learnings from past predictions
        if self.learnings:
            prompt_parts.extend([
                "",
                "## LEARNINGS FROM PAST PREDICTIONS",
            ])

            if self.learnings.get('biases'):
                prompt_parts.append("Known model biases:")
                for bias in self.learnings['biases']:
                    prompt_parts.append(f"  - {bias}")

            if self.learnings.get('player_patterns'):
                overrated = [p for p in self.learnings['player_patterns'] if p['pattern'] == 'OVERRATED']
                underrated = [p for p in self.learnings['player_patterns'] if p['pattern'] == 'UNDERRATED']

                if overrated:
                    prompt_parts.append("Players we tend to OVERRATE (be cautious):")
                    for p in overrated[:5]:
                        prompt_parts.append(f"  - {p['player']}")

                if underrated:
                    prompt_parts.append("Players we tend to UNDERRATE (consider more):")
                    for p in underrated[:5]:
                        prompt_parts.append(f"  - {p['player']}")

        prompt_parts.extend([
            "",
            "## KEY STRATEGY PRINCIPLES",
            "1. USAGE MANAGEMENT: Only 3 uses per player ALL SEASON - save elite players for majors/big purses",
            "2. EXPECTED VALUE: Higher EV = better pick. EV factors in win%, top-5%, top-10%, and purse size",
            "3. CUT PROBABILITY: Missed cuts = $0. Consider cut % for risky picks",
            "4. TOURNAMENT IMPORTANCE: Majors/signatures have 2-3x higher purses = more valuable weeks",
            "5. COURSE FIT: Some players excel at specific courses regardless of world rank",
            "",
            "## HOW TO ANSWER QUESTIONS",
            "- Lead with your opinion/recommendation, then support with data",
            "- For 'should I use X?' - Give a YES/NO/WAIT recommendation with clear reasoning",
            "- Weave in the betting profile article insights naturally - these have expert analysis",
            "- Mention if odds are moving (UP = sharps like him, DOWN = fading)",
            "- Consider: Is this the RIGHT tournament to use this player? (purse, course fit, form)",
            "- Don't be afraid to be contrarian if the data supports it",
            "",
            "## EXAMPLE GOOD RESPONSE",
            "Question: 'Should I use Patrick Cantlay?'",
            "Good: 'I'd use Cantlay here. He's sitting at +2000 with odds shortening, which tells me",
            "sharps are on him. His approach game is elite and this course rewards precision off the tee.",
            "He's got 3 uses left so you have flexibility, and at #27 in the world he's not someone",
            "you NEED to save for majors. The $220K EV is solid for a standard event. Lock him in.'",
            "",
            "Bad: 'Patrick Cantlay stats: World Rank #27, EV $219,996, Win 2.4%, Top-10 30.6%...'",
            "",
            "## CRITICAL CONSTRAINT",
            "- ONLY discuss players who are IN THE CURRENT FIELD (listed in predictions)",
            "- If asked about a player not in the field, say: '[Player] is not in this week's field.'",
        ])

        # Add list of players in the field
        if self.predictions is not None:
            field_players = self.predictions['player_name'].tolist()
            prompt_parts.extend([
                "",
                f"## PLAYERS IN THIS WEEK'S FIELD ({len(field_players)} total)",
                "The following players are IN the field and can be discussed:",
                ", ".join(field_players[:50]),  # First 50 for context
                "..." if len(field_players) > 50 else "",
            ])

        return "\n".join(prompt_parts)

    def _build_context(self, tournament_name: Optional[str] = None) -> str:
        """Build context about current predictions and player data."""
        context_parts = []

        # Current predictions
        if self.predictions is not None:
            context_parts.append(f"## CURRENT PREDICTIONS: {self.current_tournament}")
            context_parts.append("")

            # Top 15 by EV
            top_15 = self.predictions.nlargest(15, 'expected_value')
            context_parts.append("Top 15 Players by Expected Value:")
            context_parts.append("| Player | Win% | Top5% | Top10% | EV | Rank | Momentum | Cut Risk |")
            context_parts.append("|--------|------|-------|--------|-----|------|----------|----------|")

            for _, row in top_15.iterrows():
                name = row.get('player_name', 'Unknown')
                win = row.get('win_prob', 0) * 100
                top5 = row.get('top5_prob', 0) * 100
                top10 = row.get('top10_prob', 0) * 100
                ev = row.get('expected_value', 0)
                rank = int(row.get('world_rank', 999)) if pd.notna(row.get('world_rank')) else 'N/A'
                momentum = row.get('momentum_trend', 'N/A')
                cut_risk = row.get('cut_risk', 'N/A')

                context_parts.append(
                    f"| {name} | {win:.1f}% | {top5:.1f}% | {top10:.1f}% | ${ev:,.0f} | {rank} | {momentum} | {cut_risk} |"
                )

        # Betting profiles summary (odds calibration)
        if self.betting_profiles is not None and "player_name" in self.betting_profiles.columns:
            bp = self.betting_profiles.copy()
            if "odds_rank" in bp.columns:
                bp = bp[pd.notna(bp["odds_rank"])]
                bp = bp.nsmallest(12, "odds_rank")
            else:
                bp = bp.head(12)

            context_parts.append("")
            context_parts.append("## BETTING PROFILES (calibration only)")
            context_parts.append("| Player | Odds | Implied Prob | Odds Rank | Notes |")
            context_parts.append("|--------|------|--------------|-----------|-------|")
            for _, row in bp.iterrows():
                name = row.get("player_name", "Unknown")
                odds = row.get("odds_to_win", "")
                prob = row.get("implied_prob", "")
                prob = f"{prob:.1%}" if pd.notna(prob) else ""
                odds_rank = int(row.get("odds_rank")) if pd.notna(row.get("odds_rank")) else ""
                swing = row.get("odds_swing", "")
                notes = f"Line {str(swing).lower()}" if swing and pd.notna(swing) else ""
                context_parts.append(f"| {name} | {odds} | {prob} | {odds_rank} | {notes} |")

        # Power rankings summary (context only)
        if self.power_rankings is not None and "player_name" in self.power_rankings.columns:
            pr = self.power_rankings.copy()
            if "rank" in pr.columns:
                pr = pr.sort_values("rank").head(15)
            else:
                pr = pr.head(15)

            context_parts.append("")
            context_parts.append("## POWER RANKINGS (supporting context)")
            context_parts.append("| Rank | Player | Blurb | Source |")
            context_parts.append("|------|--------|-------|--------|")
            for _, row in pr.iterrows():
                rank = int(row.get("rank")) if pd.notna(row.get("rank")) else ""
                name = row.get("player_name", "Unknown")
                analysis = row.get("analysis", "")
                if isinstance(analysis, str):
                    analysis = analysis.strip()
                    if len(analysis) > 80:
                        analysis = analysis[:77] + "..."
                source = row.get("source", "")
                context_parts.append(f"| {rank} | {name} | {analysis} | {source} |")

        # Expert picks comparison
        if self.expert_picks is not None:
            expert_summary = self._get_expert_comparison_summary()
            if expert_summary:
                context_parts.append("")
                context_parts.append(expert_summary)

            # Show consensus expert picks
            if "consensus_count" in self.expert_picks.columns:
                consensus = self.expert_picks[self.expert_picks['consensus_count'] >= 2]
                if len(consensus) > 0:
                    context_parts.append("")
                    context_parts.append("## EXPERT CONSENSUS PICKS (2+ sources)")
                    for _, row in consensus.drop_duplicates('player_name').iterrows():
                        name = row['player_name']
                        sources = row.get('consensus_count', 0)
                        pick_type = row.get('pick_type', '')
                        context_parts.append(f"- {name} ({sources} sources, type: {pick_type})")

            # Show expert fades (warnings)
            fades = self.expert_picks[self.expert_picks['pick_type'] == 'fade']
            if len(fades) > 0:
                context_parts.append("")
                context_parts.append("## EXPERT FADES (players to avoid)")
                for _, row in fades.iterrows():
                    name = row['player_name']
                    source = row.get('source', 'Unknown')
                    note = row.get('note', '')
                    context_parts.append(f"- {name} ({source}): {note[:60]}...")

        # Player usage (if tracking)
        if self.usage_tracker is not None:
            context_parts.append("")
            context_parts.append("## PLAYER USAGE STATUS")

            # Show players with limited uses
            low_uses = self.usage_tracker[self.usage_tracker['uses_remaining'] <= 1].copy()
            if len(low_uses) > 0:
                context_parts.append("Players with 1 or fewer uses remaining:")
                for _, row in low_uses.iterrows():
                    context_parts.append(f"  - {row['player_name']}: {int(row['uses_remaining'])} uses left")

            # Show recently used
            recently_used = self.usage_tracker[self.usage_tracker['uses_remaining'] < 3].head(10)
            if len(recently_used) > 0:
                context_parts.append("")
                context_parts.append("Recently used players:")
                for _, row in recently_used.iterrows():
                    tournaments = row.get('tournaments_used', 'N/A')
                    context_parts.append(f"  - {row['player_name']}: {int(row['uses_remaining'])}/3 uses, used at: {tournaments}")

        # Scoring engine planning context (optional)
        if self.scoring_engine is not None:
            try:
                # Use scoring_engine's tournament (it knows actual tournament from schedule)
                # Only use tournament_name if explicitly provided
                tourney = tournament_name or self.scoring_engine.get_current_week_tournament()
                if tourney:
                    context_parts.append("")
                    context_parts.append("## SCORING ENGINE (planning view)")
                    context_parts.append(f"Current tournament: {tourney}")

                    top_scores = self.scoring_engine.get_tournament_recommendations(tourney, top_n=8)
                    if top_scores:
                        context_parts.append("Top 8 by Scoring Engine:")
                        for s in top_scores:
                            context_parts.append(
                                f"- {s.player}: {s.total_score:.1f} "
                                f"(Imp {s.tournament_importance:.0f}, "
                                f"Fit {s.course_fit:.0f}, Form {s.current_form:.0f})"
                            )

                    value_scores = self.scoring_engine.get_value_picks(
                        tourney, rank_min=20, rank_max=60, min_score=45
                    )
                    if value_scores:
                        context_parts.append("Value Picks (rank 20-60):")
                        for s in value_scores[:6]:
                            context_parts.append(f"- {s.player}: {s.total_score:.1f} ({s.form_trend})")
            except Exception:
                pass

        # Course weights for current tournament
        if self.course_weights is not None and tournament_name:
            match = self.course_weights[
                self.course_weights['tournament_name'].str.lower().str.contains(
                    tournament_name.lower()[:15], na=False
                )
            ]
            if len(match) > 0:
                row = match.iloc[0]
                context_parts.append("")
                context_parts.append(f"## COURSE PROFILE: {row['tournament_name']}")
                context_parts.append(f"- Driving (OTT) importance: {row['ott_sg']:.3f}")
                context_parts.append(f"- Approach importance: {row['app_sg']:.3f}")
                context_parts.append(f"- Short Game (ARG) importance: {row['arg_sg']:.3f}")
                context_parts.append(f"- Putting importance: {row['putt_sg']:.3f}")

                # Interpret
                weights = [
                    ('Driving', row['ott_sg']),
                    ('Approach', row['app_sg']),
                    ('Short Game', row['arg_sg']),
                    ('Putting', row['putt_sg'])
                ]
                weights.sort(key=lambda x: x[1], reverse=True)
                context_parts.append(f"- Primary skill: {weights[0][0]}, Secondary: {weights[1][0]}")

        return "\n".join(context_parts)

    def get_player_analysis(self, player_name: str) -> Dict[str, Any]:
        """Get detailed analysis for a specific player."""
        if self.predictions is None:
            return {"error": "No predictions loaded"}

        # Find player (fuzzy match)
        matches = self.predictions[
            self.predictions['player_name'].str.lower().str.contains(player_name.lower(), na=False)
        ]

        if len(matches) == 0:
            return {"error": f"Player '{player_name}' not found in current predictions"}

        player = matches.iloc[0]

        analysis = {
            "name": player['player_name'],
            "world_rank": int(player.get('world_rank', 999)) if pd.notna(player.get('world_rank')) else None,
            "probabilities": {
                "win": f"{player.get('win_prob', 0)*100:.1f}%",
                "top5": f"{player.get('top5_prob', 0)*100:.1f}%",
                "top10": f"{player.get('top10_prob', 0)*100:.1f}%",
            },
            "expected_value": f"${player.get('expected_value', 0):,.0f}",
            "course_fit": player.get('dg_fit_total', 0),
            "recent_form": {
                "sg_total": player.get('sg_total', 0),
                "recent_top10s": int(player.get('recent_top10s', 0)),
                "cuts_pct": player.get('recent_cuts_pct', 0),
                "scoring_avg": player.get('recent_scoring_avg', None),
                "birdie_avg": player.get('recent_birdie_avg', None),
                "bogey_avg": player.get('recent_bogey_avg', None),
                "form_trend": player.get('form_trend', 0),
                "finish_consistency": player.get('finish_consistency', 0.5),
            },
            "course_history": {
                "times_played": int(player.get('hist_times_played', 0)),
                "avg_finish": player.get('hist_avg_finish'),
                "has_won": bool(player.get('has_won_here', 0)),
            }
        }

        # Add historical fantasy pick context (for guidance, not constraints)
        hist = self._get_historical_pick_info(player['player_name'])
        if hist:
            analysis["historical_picks"] = hist

        # Add usage info
        if self.usage_tracker is not None:
            usage = self.usage_tracker[
                self.usage_tracker['player_name'].str.lower() == player['player_name'].lower()
            ]
            if len(usage) > 0:
                analysis["usage"] = {
                    "remaining": int(usage.iloc[0]['uses_remaining']),
                    "tournaments_used": usage.iloc[0].get('tournaments_used', '')
                }

        # Add tier strategy
        if analysis['world_rank']:
            tier = FantasyGolfRules.get_tier_strategy(analysis['world_rank'])
            analysis['tier'] = tier['name']
            analysis['tier_strategy'] = tier['strategy']

        # Add momentum/hot hand features
        if player.get('hot_hand_flag') or player.get('momentum_trend'):
            analysis["momentum"] = {
                "hot_hand_flag": bool(player.get('hot_hand_flag', False)),
                "hot_hand_score": player.get('hot_hand_score', 0),
                "momentum_trend": player.get('momentum_trend', 'NEUTRAL'),
                "consecutive_top10s": int(player.get('consecutive_top10s', 0)),
                "consecutive_cuts": int(player.get('consecutive_cuts', 0)),
            }

        # Add cut risk
        if 'cut_prob' in player.index:
            analysis["cut_risk"] = {
                "cut_prob": player.get('cut_prob', 0.5),
                "cut_risk_level": player.get('cut_risk', 'UNKNOWN'),
            }

        # Add expert pick info
        expert_info = self._get_expert_pick_info(player['player_name'])
        if expert_info:
            analysis["expert_picks"] = expert_info

        return analysis

    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})
        # Trim history if too long
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2:]

    def get_history_context(self) -> str:
        """Build context from conversation history."""
        if not self.conversation_history:
            return ""

        lines = ["## CONVERSATION HISTORY"]
        for msg in self.conversation_history[-6:]:  # Last 3 exchanges
            role = "User" if msg["role"] == "user" else "Assistant"
            # Truncate long responses
            content = msg["content"][:500] + "..." if len(msg["content"]) > 500 else msg["content"]
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

    def _extract_player_data_for_llm(self, question: str) -> str:
        """
        Extract relevant player data from the question to inject into LLM prompt.
        This ensures the LLM has accurate data about players mentioned.
        """
        if self.predictions is None:
            return ""

        # Get list of known players
        known_players = self.predictions['player_name'].tolist()

        # Try to find mentioned players in the question
        found_players = QuestionParser.extract_player_names(question, known_players)

        # Also try parsing the question for player entities
        parsed = QuestionParser.parse(question)
        entities = parsed.get("entities", {})

        # Check for player names in entities
        for key in ["player", "player1", "player2"]:
            if key in entities:
                player = self._find_player(entities[key])
                if player is not None and player['player_name'] not in found_players:
                    found_players.append(player['player_name'])

        if not found_players:
            return ""

        # Build player data context
        lines = ["## PLAYER DATA (from predictions)"]

        for player_name in found_players[:5]:  # Limit to 5 players
            player = self._find_player(player_name)
            if player is not None:
                lines.append(f"\n### {player['player_name']} - IN THE FIELD")
                lines.append(f"- World Rank: #{int(player.get('world_rank', 999)) if pd.notna(player.get('world_rank')) else 'N/A'}")
                lines.append(f"- Win Probability: {player.get('win_prob', 0)*100:.2f}%")
                lines.append(f"- Top 5 Probability: {player.get('top5_prob', 0)*100:.2f}%")
                lines.append(f"- Top 10 Probability: {player.get('top10_prob', 0)*100:.2f}%")
                lines.append(f"- Expected Value: ${player.get('expected_value', 0):,.0f}")
                lines.append(f"- Course Fit: {player.get('dg_fit_total', 0):+.3f}")
                lines.append(f"- SG Total: {player.get('sg_total', 0):+.3f}")
                lines.append(f"- Recent Top 10s (weighted): {player.get('recent_top10s', 0)}")
                lines.append(f"- Course History: {int(player.get('hist_times_played', 0))} starts")
                if player.get('hist_avg_finish'):
                    lines.append(f"- Avg Finish at Course: {player.get('hist_avg_finish'):.1f}")
                if player.get('has_won_here', 0):
                    lines.append("- HAS WON AT THIS COURSE")
                if pd.notna(player.get('form_trend')):
                    lines.append(f"- Form Trend (SG slope): {player.get('form_trend', 0):+.3f}")
                if pd.notna(player.get('recent_scoring_avg')):
                    lines.append(f"- Scoring Avg: {player.get('recent_scoring_avg', 0):.2f}")

                hist = self._get_historical_pick_info(player['player_name'])
                if hist:
                    approx_note = " (approx.)" if hist.get("approximate") else ""
                    lines.append(f"- Historical picks: {hist.get('picks', 0)}{approx_note}")

                # Add betting profile data if available
                betting = self._get_betting_profile(player['player_name'])
                if betting:
                    lines.append("")
                    lines.append("**Betting & Form Data (from PGA Tour):**")
                    if betting.get('odds_to_win'):
                        swing = betting.get('odds_swing', '')
                        swing_icon = "↑" if swing == "UP" else "↓" if swing == "DOWN" else ""
                        lines.append(f"- Betting Odds: {betting['odds_to_win']} {swing_icon}")
                    if betting.get('odds_rank') and pd.notna(betting.get('odds_rank')):
                        lines.append(f"- Odds Rank: #{int(betting['odds_rank'])} in field")
                    if betting.get('fedex_rank') and pd.notna(betting.get('fedex_rank')):
                        lines.append(f"- FedEx Rank: #{int(betting['fedex_rank'])}")
                    events = betting.get('events_played', 0)
                    if events and pd.notna(events) and events > 0:
                        wins = int(betting.get('wins', 0)) if pd.notna(betting.get('wins')) else 0
                        top10s = int(betting.get('top_10s', 0)) if pd.notna(betting.get('top_10s')) else 0
                        lines.append(f"- Season Stats: {int(events)} events, {wins} wins, {top10s} top-10s")
                    form_summary = betting.get('recent_form_summary', '')
                    if form_summary and pd.notna(form_summary) and str(form_summary).lower() != 'nan':
                        lines.append(f"- Recent Form: {form_summary}")

                    # Add Strokes Gained breakdown
                    sg_total = betting.get('sg_total')
                    if sg_total and pd.notna(sg_total):
                        lines.append("")
                        lines.append("**Strokes Gained Breakdown:**")
                        sg_rank = betting.get('sg_total_rank')
                        rank_str = f" (#{int(sg_rank)})" if sg_rank and pd.notna(sg_rank) else ""
                        lines.append(f"- SG Total: {sg_total}{rank_str}")

                        # Individual SG components
                        for sg_key, sg_label in [
                            ('sg_ott', 'SG Off-the-Tee'),
                            ('sg_app', 'SG Approach'),
                            ('sg_arg', 'SG Around-the-Green'),
                            ('sg_putt', 'SG Putting')
                        ]:
                            val = betting.get(sg_key)
                            if val and pd.notna(val):
                                rank = betting.get(f'{sg_key}_rank')
                                rank_str = f" (#{int(rank)})" if rank and pd.notna(rank) else ""
                                lines.append(f"- {sg_label}: {val}{rank_str}")

                        # Other stats
                        driving = betting.get('driving_distance')
                        if driving and pd.notna(driving):
                            lines.append(f"- Driving Distance: {driving}")
                        gir = betting.get('gir_pct')
                        if gir and pd.notna(gir):
                            lines.append(f"- Greens in Regulation: {gir}")
                        scrambling = betting.get('scrambling_pct')
                        if scrambling and pd.notna(scrambling):
                            lines.append(f"- Scrambling: {scrambling}")

                    # Add course history
                    course_summary = betting.get('course_history_summary', '')
                    if course_summary and pd.notna(course_summary) and str(course_summary).lower() != 'nan':
                        lines.append("")
                        lines.append("**Course History (PGA Tour data):**")
                        lines.append(f"- {course_summary}")

                    # Add parsed detailed course history if available
                    parsed_history = betting.get('parsed_course_history')
                    if parsed_history and parsed_history.get('courses'):
                        lines.append("")
                        lines.append("**Detailed Course Results:**")
                        for course in parsed_history['courses'][:3]:
                            course_name = course.get('course_name', 'Unknown')
                            starts = course.get('starts', 0)
                            avg_finish = course.get('avg_finish')
                            best = course.get('best_finish')
                            earnings = course.get('total_earnings', 0)
                            recent = course.get('recent_results', [])

                            avg_str = f", Avg: {avg_finish:.1f}" if avg_finish else ""
                            best_str = f", Best: {best}" if best else ""
                            recent_str = f" | Recent: {', '.join(str(r) for r in recent[:3])}" if recent else ""

                            lines.append(f"- {course_name}: {starts} starts{avg_str}{best_str}{recent_str}")
                            if earnings > 0:
                                lines.append(f"  Total earnings: ${earnings:,.0f}")

                # Add article blurb if available
                blurb = self._get_article_blurb(player['player_name'])
                if blurb:
                    lines.append("")
                    lines.append("**Article Blurb (PGA betting profile):**")
                    if blurb.get("summary"):
                        lines.append(f"- Summary: {blurb['summary']}")
                    elif blurb.get("body"):
                        lines.append(f"- Summary: {blurb['body'][:240]}...")
                    if blurb.get("published_at"):
                        lines.append(f"- Published: {blurb['published_at']}")
                    if blurb.get("url"):
                        lines.append(f"- Source: {blurb['url']}")

                # Add ROI data from historical fantasy picks
                roi_summary = self._get_player_roi(player['player_name'])
                if roi_summary:
                    lines.append("")
                    lines.append("**Fantasy Pick History (2022-2025):**")
                    lines.append(roi_summary)

        return "\n".join(lines)

    def _extract_season_planning_context(self, player_name: str) -> str:
        """
        Extract season planning recommendations for a player to inject into LLM prompt.
        This gives the LLM the data it needs to answer "when should I use X?" questions.
        """
        if not SEASON_PLANNER_AVAILABLE:
            return ""

        try:
            qualifications = load_player_qualifications()
            recommendations = recommend_tournaments_for_player(
                player_name,
                num_uses=3,
                qualifications=qualifications
            )

            if not recommendations:
                return f"\n## SEASON PLANNING DATA\nNo tournament recommendations found for {player_name}.\n"

            lines = [f"\n## SEASON PLANNING DATA FOR {player_name.upper()}"]
            lines.append("Use this data to recommend when to use this player across the season.")
            lines.append("")
            lines.append("### TOP 3 RECOMMENDED TOURNAMENTS (use player here):")

            for i, rec in enumerate(recommendations[:3], 1):
                lines.append(f"\n**{i}. {rec.tournament_name}** ({rec.tournament_date})")
                lines.append(f"   - Tournament Type: {rec.tournament_type}")
                lines.append(f"   - Purse: ${rec.purse:,}")
                lines.append(f"   - Expected Value: ${rec.expected_value:,.0f}")
                lines.append(f"   - Course History: {rec.course_history}")
                lines.append(f"   - Rating: {rec.rating}/5 stars")
                lines.append(f"   - Reasoning: {rec.reasoning}")

            if len(recommendations) > 3:
                lines.append("")
                lines.append("### BACKUP OPTIONS (if top 3 don't work out):")
                for rec in recommendations[3:6]:
                    lines.append(f"- {rec.tournament_name}: ${rec.expected_value:,.0f} EV ({rec.tournament_type})")

            if len(recommendations) > 6:
                lines.append("")
                lines.append("### TOURNAMENTS TO SKIP (save uses for above):")
                for rec in recommendations[6:9]:
                    lines.append(f"- {rec.tournament_name}: ${rec.expected_value:,.0f} EV")

            lines.append("")
            lines.append("NOTE: Player has 3 uses for the entire season. Recommend saving uses for the tournaments listed above.")

            return "\n".join(lines)

        except Exception:
            return ""

    def ask(
        self,
        question: str,
        tournament_name: Optional[str] = None,
        use_ollama: bool = True,
        ollama_model: str = "llama3.2"
    ) -> str:
        """
        Ask the assistant a question.

        Args:
            question: The question to ask
            tournament_name: Optional tournament context
            use_ollama: Whether to use Ollama (True) or return structured response
            ollama_model: Ollama model to use

        Returns:
            Response string
        """
        # Add question to history
        self.add_to_history("user", question)

        # Enforce "in field" constraint before calling LLM
        # EXCEPTION: Season planning questions don't require player to be in current field
        parsed = QuestionParser.parse(question)
        intent = parsed.get("intent", "")
        entities = parsed.get("entities", {})
        skip_field_check = intent in ["player_usage_strategy", "player_usage", "season_dashboard", "help_questions"]

        # For season planning, return structured plan to ensure deterministic output
        if intent == "player_usage_strategy":
            answer = self._handle_player_usage_strategy(entities.get("player", ""))
            self.add_to_history("assistant", answer)
            return answer
        if intent == "season_dashboard":
            answer = self._handle_season_dashboard()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "help_questions":
            answer = self._handle_help_questions()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_recs":
            answer = self._handle_scoring_engine_recs()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_this_week":
            answer = self._handle_scoring_engine_this_week()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_value":
            answer = self._handle_scoring_engine_value()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_tournament":
            answer = self._handle_scoring_engine_tournament(entities.get("tournament", ""), question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_player":
            answer = self._handle_scoring_engine_player(entities.get("player", ""), question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_strategy":
            answer = self._handle_scoring_engine_strategy(question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "scoring_engine_optimize":
            answer = self._handle_scoring_engine_optimize(entities.get("player", ""), question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "power_rankings_list":
            answer = self._handle_power_rankings_list(question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "power_rank_player":
            answer = self._handle_power_rank_player(entities.get("player", ""))
            self.add_to_history("assistant", answer)
            return answer
        if intent == "player_odds":
            answer = self._handle_player_odds(entities.get("player", ""))
            self.add_to_history("assistant", answer)
            return answer
        if intent == "odds_favorites":
            answer = self._handle_odds_list(question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "run_predictions":
            answer = self._handle_run_predictions(entities.get("tournament", ""), question)
            self.add_to_history("assistant", answer)
            return answer
        if intent == "confirm_run_predictions":
            answer = self._handle_confirm_run_predictions()
            self.add_to_history("assistant", answer)
            return answer
        if intent == "cancel_run_predictions":
            answer = self._handle_cancel_run_predictions()
            self.add_to_history("assistant", answer)
            return answer

        if self.predictions is not None and not skip_field_check:
            known_players = self.predictions['player_name'].tolist()
            found_players = QuestionParser.extract_player_names(question, known_players)
            for key in ["player", "player1", "player2"]:
                if key in entities and entities[key]:
                    if self._find_player(entities[key]) is None:
                        return f"**{entities[key]}** is not in this week's field."
            for name in found_players:
                if self._find_player(name) is None:
                    return f"**{name}** is not in this week's field."

        # Build full context
        system_prompt = self._build_system_prompt()
        context = self._build_context(tournament_name or self.current_tournament)
        history_context = self.get_history_context()

        # Extract player-specific data to inject (ensures LLM has accurate info)
        player_data_context = self._extract_player_data_for_llm(question)

        # For season planning questions, add season planning data
        season_planning_context = ""
        if intent == "player_usage_strategy":
            player_name = entities.get("player", "")
            if player_name:
                season_planning_context = self._extract_season_planning_context(player_name)

        if use_ollama:
            try:
                import requests
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": ollama_model,
                        "system": system_prompt,  # Separate system message for better adherence
                        "prompt": f"""{context}

{player_data_context}

{season_planning_context}

{history_context}

Question: {question}

.""",
                        "stream": False,
                        "options": {
                            "temperature": 0.8,  # Slightly higher for more natural responses
                            "num_predict": 1500,  # Shorter, more focused responses
                            "top_p": 0.9,  # Nucleus sampling for variety
                        }
                    },
                    timeout=180,
                )

                if response.status_code == 200:
                    answer = response.json().get("response", "No response generated")
                    self.add_to_history("assistant", answer)
                    return answer
                else:
                    return f"Error: Ollama returned status {response.status_code}"

            except Exception as e:
                return f"Error connecting to Ollama: {e}\n\nMake sure Ollama is running: `ollama serve`"
        else:
            # Return structured response without LLM
            answer = self._generate_simple_response(question)
            self.add_to_history("assistant", answer)
            return answer

    def _generate_simple_response(self, question: str) -> str:
        """Generate a structured response without LLM using intent parsing."""
        if self.predictions is None:
            return "I don't have predictions loaded. Please run predictions first."

        # Parse the question
        parsed = QuestionParser.parse(question)
        intent = parsed["intent"]
        entities = parsed["entities"]

        # Get list of known players for fuzzy matching
        known_players = self.predictions['player_name'].tolist()

        # Route to appropriate handler
        if intent == "player_decision":
            return self._handle_player_decision(entities.get("player", ""), question)

        elif intent == "player_analysis":
            return self._handle_player_analysis(entities.get("player", ""))

        elif intent == "player_ranking_reason":
            return self._handle_ranking_reason(entities.get("player", ""))

        elif intent == "player_form":
            return self._handle_player_form(entities.get("player", ""))

        elif intent == "compare_players":
            return self._handle_comparison(entities.get("player1", ""), entities.get("player2", ""))

        elif intent == "value_plays":
            return self._handle_value_plays()

        elif intent == "course_fit":
            return self._handle_course_fit()

        elif intent == "avoid_players":
            return self._handle_avoid_players()

        elif intent == "lineup":
            result = self.get_lineup_recommendation()
            return self._format_lineup_response(result)

        elif intent == "field_info":
            return self._handle_field_info()

        elif intent == "tournament_info":
            return self._handle_tournament_info()

        elif intent == "course_info":
            return self._handle_course_info()

        elif intent == "usage_status":
            return self._handle_usage_status()

        elif intent == "player_usage":
            return self._handle_player_usage(entities.get("player", ""))

        elif intent == "player_usage_strategy":
            return self._handle_player_usage_strategy(entities.get("player", ""))

        elif intent == "top_players":
            count = int(entities.get("count", 5)) if entities.get("count") else 5
            return self._handle_top_players(count)

        elif intent == "expert_picks_question":
            return self._handle_expert_picks()
        elif intent == "scoring_engine_recs":
            return self._handle_scoring_engine_recs()
        elif intent == "scoring_engine_this_week":
            return self._handle_scoring_engine_this_week()
        elif intent == "scoring_engine_value":
            return self._handle_scoring_engine_value()
        elif intent == "scoring_engine_tournament":
            return self._handle_scoring_engine_tournament(entities.get("tournament", ""), question)
        elif intent == "scoring_engine_player":
            return self._handle_scoring_engine_player(entities.get("player", ""), question)
        elif intent == "scoring_engine_strategy":
            return self._handle_scoring_engine_strategy(question)
        elif intent == "scoring_engine_optimize":
            return self._handle_scoring_engine_optimize(entities.get("player", ""), question)
        elif intent == "power_rankings_list":
            return self._handle_power_rankings_list(question)
        elif intent == "power_rank_player":
            return self._handle_power_rank_player(entities.get("player", ""))
        elif intent == "player_odds":
            return self._handle_player_odds(entities.get("player", ""))
        elif intent == "odds_favorites":
            return self._handle_odds_list(question)
        elif intent == "run_predictions":
            return self._handle_run_predictions(entities.get("tournament", ""), question)
        elif intent == "confirm_run_predictions":
            return self._handle_confirm_run_predictions()
        elif intent == "cancel_run_predictions":
            return self._handle_cancel_run_predictions()

        # Unknown intent - try to extract player names and show analysis
        found_players = QuestionParser.extract_player_names(question, known_players)
        if found_players:
            return self._handle_player_analysis(found_players[0])

        # Default: show top picks
        return self._handle_top_players(5)

    def _find_player(self, player_name: str) -> Optional[pd.Series]:
        """Find a player by name (fuzzy match)."""
        if not player_name or self.predictions is None:
            return None

        player_lower = player_name.lower().strip()

        # Try exact match first
        matches = self.predictions[
            self.predictions['player_name'].str.lower() == player_lower
        ]
        if len(matches) > 0:
            return matches.iloc[0]

        # Try contains match
        matches = self.predictions[
            self.predictions['player_name'].str.lower().str.contains(player_lower, na=False, regex=False)
        ]
        if len(matches) > 0:
            return matches.iloc[0]

        # Try "First Last" -> "Last, First" conversion
        # (e.g., "akshay bhatia" -> "bhatia, akshay")
        if " " in player_lower:
            parts = player_lower.split()
            if len(parts) == 2:
                reversed_name = f"{parts[1]}, {parts[0]}"
                matches = self.predictions[
                    self.predictions['player_name'].str.lower() == reversed_name
                ]
                if len(matches) > 0:
                    return matches.iloc[0]

                # Try contains with reversed
                matches = self.predictions[
                    self.predictions['player_name'].str.lower().str.contains(reversed_name, na=False, regex=False)
                ]
                if len(matches) > 0:
                    return matches.iloc[0]

        # Try last name match - look for "lastname," pattern (Last, First format)
        last_name = player_lower.split()[-1] if " " in player_lower else player_lower
        matches = self.predictions[
            self.predictions['player_name'].str.lower().str.startswith(f"{last_name},")
        ]
        if len(matches) == 1:
            return matches.iloc[0]

        # Fallback: Try endswith for "Last, First" format
        if " " not in player_lower:
            matches = self.predictions[
                self.predictions['player_name'].str.lower().str.endswith(player_lower)
            ]
            if len(matches) == 1:
                return matches.iloc[0]

        return None

    def _handle_player_decision(self, player_name: str, question: str) -> str:
        """Handle 'Should I use X?' type questions."""
        player = self._find_player(player_name)
        if player is None:
            return f"I couldn't find '{player_name}' in the current field. They may not be playing this week."

        analysis = self.get_player_analysis(player['player_name'])
        world_rank = analysis.get('world_rank', 999)
        ev = player.get('expected_value', 0)
        win_prob = player.get('win_prob', 0)
        top5_prob = player.get('top5_prob', 0)
        top10_prob = player.get('top10_prob', 0)
        course_fit = player.get('dg_fit_total', 0)

        # Calculate EV rank in field
        ev_rank = (self.predictions['expected_value'] > ev).sum() + 1
        total_field = len(self.predictions)

        # Get tournament importance
        tournament_importance = 5
        winner_share = 0
        purse = 0
        if TournamentCalendar is not None:
            tournament_importance = TournamentCalendar.get_importance(self.current_tournament or "")
            payout_info = TournamentCalendar.get_payout_info(self.current_tournament or "")
            winner_share = payout_info.get('winner_share', 0)
            purse = payout_info.get('purse', 0)

        # Get betting profile
        betting = self._get_betting_profile(player['player_name'])

        # Build recommendation
        lines = [f"## Should you use {player['player_name']}?"]
        lines.append(f"**Tournament:** {self.current_tournament}")
        if purse > 0:
            lines.append(f"**Purse:** ${purse:,.0f} (Winner: ${winner_share:,.0f})")
        lines.append("")

        # Key stats section
        lines.append("### Player Stats")
        lines.append(f"- **World Rank:** #{world_rank}")
        lines.append(f"- **EV Rank:** #{ev_rank} of {total_field} in field")
        lines.append(f"- **Expected Value:** ${ev:,.0f}")
        lines.append(f"- **Win %:** {win_prob*100:.1f}% | **Top-5:** {top5_prob*100:.1f}% | **Top-10:** {top10_prob*100:.1f}%")
        lines.append(f"- **Course Fit:** {course_fit:+.3f}")
        lines.append(f"- **Recent Top-10s (weighted):** {analysis['recent_form'].get('recent_top10s', 0)} | **Cut Rate:** {analysis['recent_form'].get('cuts_pct', 0)*100:.0f}%")
        if analysis['recent_form'].get('form_trend') is not None:
            lines.append(f"- **Form Trend (SG slope):** {analysis['recent_form'].get('form_trend', 0):+.3f}")

        # Betting data if available
        if betting and betting.get('odds_to_win'):
            swing = betting.get('odds_swing', '')
            swing_text = " (odds improving)" if swing == "UP" else " (odds dropping)" if swing == "DOWN" else ""
            lines.append(f"- **Betting Odds:** {betting['odds_to_win']}{swing_text}")

        # Usage status
        uses_left = 3
        if analysis.get('usage'):
            uses_left = analysis['usage']['remaining']
        lines.append(f"- **Uses Remaining:** {uses_left}/3")

        # Course history
        if analysis['course_history']['times_played'] > 0:
            lines.append("")
            lines.append("### Course History")
            lines.append(f"- Played here: {analysis['course_history']['times_played']} times")
            avg_finish = analysis['course_history']['avg_finish']
            if avg_finish:
                lines.append(f"- Avg Finish: {avg_finish:.1f}")
            if analysis['course_history']['has_won']:
                lines.append(f"- **PREVIOUS WINNER HERE**")

        lines.append("")

        # Decision logic
        is_elite = world_rank <= 15
        is_major = tournament_importance >= 10
        is_signature = tournament_importance >= 8
        is_standard = tournament_importance < 8

        # Tournament type description
        if is_major:
            tourney_type = "MAJOR"
        elif is_signature:
            tourney_type = "SIGNATURE EVENT"
        else:
            tourney_type = "STANDARD EVENT"

        recommendation = "USE"
        reasoning = []

        if uses_left == 0:
            recommendation = "CANNOT USE"
            reasoning.append("No uses remaining this season")
        elif is_elite:
            if uses_left == 1:
                if is_major:
                    recommendation = "YES - USE"
                    reasoning.append(f"Last use on a {tourney_type} - this is the right spot")
                elif is_signature:
                    recommendation = "CONSIDER"
                    reasoning.append(f"Last use at {tourney_type} - decent, but majors are better")
                else:
                    recommendation = "SAVE"
                    reasoning.append(f"Last use at {tourney_type} - save for a major or signature event")
            elif uses_left == 2:
                if is_major or is_signature:
                    recommendation = "YES - USE"
                    reasoning.append(f"Elite player at {tourney_type} - good use")
                else:
                    recommendation = "CONSIDER"
                    reasoning.append(f"2 uses left at {tourney_type} - only use if course fit is strong")
            else:
                if is_standard and course_fit < 0.3:
                    recommendation = "SAVE"
                    reasoning.append(f"{tourney_type} with average course fit - save for better spots")
                else:
                    recommendation = "YES - USE"
                    reasoning.append("Good opportunity to use elite player")
        else:
            # Non-elite player - always more flexible with uses
            if ev_rank <= 5:
                recommendation = "YES - USE"
                reasoning.append(f"Top 5 EV in field (#{ev_rank})")
            elif ev_rank <= 15:
                recommendation = "YES - USE"
                reasoning.append(f"Top 15 EV in field (#{ev_rank})")
            elif course_fit > 0.5:
                recommendation = "YES - USE"
                reasoning.append(f"Strong course fit ({course_fit:+.3f})")
            elif ev_rank <= 30:
                recommendation = "CONSIDER"
                reasoning.append(f"Solid EV (#{ev_rank} in field) - good supporting pick")
            else:
                recommendation = "SKIP"
                reasoning.append(f"Below average EV (#{ev_rank} in field) - better options available")

        # Add additional context
        if analysis['course_history']['has_won']:
            reasoning.append("Previous winner at this course!")
        elif analysis['course_history']['times_played'] > 2:
            avg_finish = analysis['course_history']['avg_finish']
            if avg_finish and avg_finish < 20:
                reasoning.append(f"Good course history (avg finish: {avg_finish:.0f})")

        if course_fit > 0.7:
            reasoning.append(f"Excellent course fit ({course_fit:+.3f})")
        elif course_fit < -0.2:
            reasoning.append(f"Poor course fit ({course_fit:+.3f}) - game doesn't suit this course")

        lines.append(f"### Recommendation: **{recommendation}**")
        lines.append(f"*Tournament Type: {tourney_type}*")
        lines.append("")
        for r in reasoning:
            lines.append(f"- {r}")

        return "\n".join(lines)





    def _handle_player_analysis(self, player_name: str) -> str:
        """Handle player analysis questions."""
        player = self._find_player(player_name)
        if player is None:
            return f"I couldn't find '{player_name}' in the current field."

        analysis = self.get_player_analysis(player['player_name'])
        lines = [f"## Player Analysis: {player['player_name']}\n"]

        lines.append(f"**World Rank:** #{analysis.get('world_rank', 'N/A')}")
        lines.append(f"**Tier:** {analysis.get('tier', 'Unknown')}")
        lines.append("")

        lines.append("### Probabilities")
        lines.append(f"- Win: {analysis['probabilities']['win']}")
        lines.append(f"- Top 5: {analysis['probabilities']['top5']}")
        lines.append(f"- Top 10: {analysis['probabilities']['top10']}")
        lines.append(f"- Expected Value: {analysis['expected_value']}")
        lines.append("")

        lines.append("### Recent Form")
        form = analysis['recent_form']
        lines.append(f"- SG Total: {form['sg_total']:+.3f}")
        lines.append(f"- Recent Top 10s (weighted): {form['recent_top10s']}")
        lines.append(f"- Cut Rate: {form['cuts_pct']*100:.0f}%")
        if form.get('scoring_avg') is not None and pd.notna(form.get('scoring_avg')):
            lines.append(f"- Scoring Avg: {form['scoring_avg']:.2f}")
        if form.get('form_trend') is not None and pd.notna(form.get('form_trend')):
            lines.append(f"- Form Trend (SG slope): {form['form_trend']:+.3f}")
        if form.get('finish_consistency') is not None and pd.notna(form.get('finish_consistency')):
            lines.append(f"- Finish Consistency: {form['finish_consistency']:.2f}")
        lines.append("")

        if analysis.get("historical_picks"):
            hist = analysis["historical_picks"]
            approx_note = " (approx.)" if hist.get("approximate") else ""
            lines.append("### Historical Fantasy Picks (context only)")
            lines.append(f"- Times picked: {hist.get('picks', 0)}{approx_note}")
            if hist.get("tournaments"):
                lines.append(f"- Recent tournaments: {', '.join(hist['tournaments'])}")
            if hist.get("avg_earnings") is not None:
                lines.append(f"- Avg earnings when picked: ${hist['avg_earnings']:,.0f}")
            lines.append("")

        # Add ROI data if available
        roi_summary = self._get_player_roi(player['player_name'])
        if roi_summary:
            lines.append("### Fantasy ROI History (2022-2025)")
            lines.append(roi_summary)
            lines.append("")

        lines.append("### Course History")
        hist = analysis['course_history']
        if hist['times_played'] > 0:
            lines.append(f"- Times Played: {hist['times_played']}")
            lines.append(f"- Avg Finish: {hist['avg_finish']:.1f}")
            lines.append(f"- Has Won Here: {'Yes' if hist['has_won'] else 'No'}")
        else:
            lines.append("- No previous starts at this course")
        lines.append("")

        lines.append(f"### Course Fit: {analysis['course_fit']:+.3f}")

        if analysis.get('usage'):
            lines.append(f"\n**Uses Remaining:** {analysis['usage']['remaining']}/3")

        # Add betting profile data if available
        betting = self._get_betting_profile(player['player_name'])
        if betting:
            lines.append("")
            lines.append("### Betting & Form Data (PGA Tour)")
            if betting.get('odds_to_win'):
                swing = betting.get('odds_swing', '')
                swing_icon = "↑" if swing == "UP" else "↓" if swing == "DOWN" else ""
                lines.append(f"- Betting Odds: {betting['odds_to_win']} {swing_icon}")
            if betting.get('odds_rank') and pd.notna(betting.get('odds_rank')):
                lines.append(f"- Odds Rank: #{int(betting['odds_rank'])} in field")
            if betting.get('fedex_rank') and pd.notna(betting.get('fedex_rank')):
                lines.append(f"- FedEx Rank: #{int(betting['fedex_rank'])}")

            # Season stats
            events = betting.get('events_played', 0)
            if events and pd.notna(events) and events > 0:
                wins = int(betting.get('wins', 0)) if pd.notna(betting.get('wins')) else 0
                top10s = int(betting.get('top_10s', 0)) if pd.notna(betting.get('top_10s')) else 0
                lines.append(f"- Season Stats: {int(events)} events, {wins} wins, {top10s} top-10s")

            form_summary = betting.get('recent_form_summary', '')
            if form_summary and pd.notna(form_summary) and str(form_summary).lower() != 'nan':
                lines.append(f"- Recent Form: {form_summary}")

            # Strokes Gained breakdown
            sg_total = betting.get('sg_total')
            if sg_total and pd.notna(sg_total):
                lines.append("")
                lines.append("**Strokes Gained (PGA Tour):**")
                sg_rank = betting.get('sg_total_rank')
                rank_str = f" (#{int(sg_rank)})" if sg_rank and pd.notna(sg_rank) else ""
                lines.append(f"- SG Total: {sg_total:+.3f}{rank_str}")

                for sg_key, sg_label in [
                    ('sg_ott', 'SG Off-the-Tee'),
                    ('sg_app', 'SG Approach'),
                    ('sg_arg', 'SG Around-the-Green'),
                    ('sg_putt', 'SG Putting')
                ]:
                    val = betting.get(sg_key)
                    if val and pd.notna(val):
                        rank = betting.get(f'{sg_key}_rank')
                        rank_str = f" (#{int(rank)})" if rank and pd.notna(rank) else ""
                        lines.append(f"- {sg_label}: {val:+.3f}{rank_str}")

            # Parsed course history from betting profile
            parsed_history = betting.get('parsed_course_history')
            if parsed_history and parsed_history.get('courses'):
                lines.append("")
                lines.append("**Detailed Course Results (PGA Tour):**")
                for course in parsed_history['courses'][:3]:
                    course_name = course.get('course_name', 'Unknown')
                    starts = course.get('starts', 0)
                    avg_finish = course.get('avg_finish')
                    best = course.get('best_finish')
                    recent = course.get('recent_results', [])
                    avg_str = f", avg {avg_finish:.1f}" if avg_finish else ""
                    best_str = f", best {best}" if best else ""
                    recent_str = f" | Recent: {', '.join(str(r) for r in recent[:3])}" if recent else ""
                    lines.append(f"- {course_name}: {starts} starts{avg_str}{best_str}{recent_str}")

        # Add expert pick info if available
        expert_info = self._get_expert_pick_info(player['player_name'])
        if expert_info:
            lines.append("")
            lines.append("### Expert Picks")
            if expert_info.get('is_expert_pick'):
                for p in expert_info.get('pick_sources', []):
                    note = f" - {p['note']}" if p.get('note') else ""
                    lines.append(f"- {p['source']} ({p['type']}){note}")
            if expert_info.get('is_expert_fade'):
                for f in expert_info.get('fade_sources', []):
                    note = f" - {f['note']}" if f.get('note') else ""
                    lines.append(f"- ⚠️ {f['source']} (FADE){note}")

        # Add PGA Tour expert picks info
        pga_info = self._get_pga_expert_pick_info(player['player_name'])
        if pga_info:
            lines.append("")
            lines.append("### PGA Tour Expert Picks")
            total = pga_info['total_experts']

            if pga_info['picked_to_win']:
                lines.append(f"**🏆 Winner Pick: {pga_info['winner_count']}/{total} experts**")
                for p in pga_info['picked_to_win'][:2]:  # Show top 2 with comments
                    comment = f" - \"{p['comment'][:100]}...\"" if p.get('comment') and len(p['comment']) > 100 else f" - \"{p['comment']}\"" if p.get('comment') else ""
                    lines.append(f"- {p['expert']}{comment}")

            if pga_info['in_lineup']:
                lines.append(f"**In Lineup: {pga_info['lineup_count']}/{total} experts**")
                experts = [p['expert'] for p in pga_info['in_lineup']]
                lines.append(f"- {', '.join(experts)}")

            if pga_info['on_bench']:
                lines.append(f"**On Bench: {pga_info['bench_count']}/{total} experts**")
                experts = [p['expert'] for p in pga_info['on_bench']]
                lines.append(f"- {', '.join(experts)}")

        return "\n".join(lines)

    def _handle_ranking_reason(self, player_name: str) -> str:
        """Explain why a player is ranked where they are."""
        player = self._find_player(player_name)
        if player is None:
            return f"I couldn't find '{player_name}' in the current field."

        ev = player.get('expected_value', 0)
        rank = (self.predictions['expected_value'] > ev).sum() + 1
        total = len(self.predictions)

        lines = [f"## Why is {player['player_name']} ranked #{rank}?\n"]

        # Get key contributing factors
        factors = []

        # Win probability impact
        win_prob = player.get('win_prob', 0)
        if win_prob > 0.05:
            factors.append(f"High win probability ({win_prob*100:.1f}%) - a major EV driver")
        elif win_prob < 0.01:
            factors.append(f"Low win probability ({win_prob*100:.2f}%) - limits upside")

        # World rank
        world_rank = player.get('world_rank', 999)
        if world_rank <= 15:
            factors.append(f"Elite world rank (#{world_rank}) - model trusts proven players")
        elif world_rank > 100:
            factors.append(f"Lower world rank (#{world_rank}) - reduced baseline expectations")

        # Course fit
        course_fit = player.get('dg_fit_total', 0)
        if course_fit > 0.5:
            factors.append(f"Strong course fit ({course_fit:+.3f}) - game suits this course")
        elif course_fit < -0.2:
            factors.append(f"Poor course fit ({course_fit:+.3f}) - game doesn't suit this course")

        # Recent form
        sg_total = player.get('sg_total', 0)
        if sg_total > 1.0:
            factors.append(f"Excellent recent form (SG: {sg_total:+.3f})")
        elif sg_total < 0:
            factors.append(f"Below average recent form (SG: {sg_total:+.3f})")

        # Course history
        if player.get('has_won_here', 0):
            factors.append("Previous winner at this course - major boost")
        elif player.get('hist_times_played', 0) > 3 and player.get('hist_avg_finish', 50) < 15:
            factors.append(f"Strong course history (avg finish: {player.get('hist_avg_finish'):.1f})")

        lines.append("### Key Factors:")
        for f in factors:
            lines.append(f"- {f}")

        lines.append(f"\n**Expected Value:** ${ev:,.0f}")
        lines.append(f"**Rank:** {rank} of {total}")

        return "\n".join(lines)

    def _handle_expert_picks(self) -> str:
        """Handle questions about expert picks."""
        has_regular = self.expert_picks is not None and not self.expert_picks.empty
        has_pga = self.pga_expert_picks is not None and not self.pga_expert_picks.empty

        if not has_regular and not has_pga:
            return "No expert picks data available for this tournament."

        lines = ["## Expert Picks Summary\n"]

        # Regular expert picks (legacy sources)
        if has_regular:
            df = self.expert_picks
            picks_df = df[~df['pick_type'].isin(['fade', ''])]
            fades_df = df[df['pick_type'] == 'fade']

            # Show picks
            if not picks_df.empty:
                lines.append("### Expert Picks")
                # Group by player and count consensus
                pick_counts = picks_df.groupby('player_name').agg({
                    'source': lambda x: list(x),
                    'pick_type': 'first',
                    'note': 'first',
                    'consensus_count': 'max'
                }).reset_index()
                pick_counts = pick_counts.sort_values('consensus_count', ascending=False)

                for _, row in pick_counts.head(10).iterrows():
                    player = row['player_name']
                    sources = row['source']
                    pick_type = row['pick_type']
                    note = row['note'] if pd.notna(row['note']) else ""

                    # Get model prediction for comparison
                    model_player = self._find_player(player)
                    if model_player is not None:
                        model_ev = model_player.get('expected_value', 0)
                        model_rank = int(model_player.get('prediction_rank', 999))
                        model_str = f" | Model rank #{model_rank}, EV ${model_ev:,.0f}"
                    else:
                        model_str = " | Not in model"

                    sources_str = ", ".join(sources) if isinstance(sources, list) else sources
                    note_str = f" - {note}" if note else ""
                    lines.append(f"- **{player}** ({pick_type}){note_str}")
                    lines.append(f"  Sources: {sources_str}{model_str}")

            # Show fades
            if not fades_df.empty:
                lines.append("")
                lines.append("### Expert Fades (players to avoid)")
                for _, row in fades_df.iterrows():
                    player = row['player_name']
                    source = row['source']
                    note = row.get('note', '')
                    note_str = f" - {note}" if note and pd.notna(note) else ""
                    lines.append(f"- ⚠️ **{player}** (FADE){note_str}")
                    lines.append(f"  Source: {source}")

        # Add PGA Tour expert picks section
        if self.pga_expert_picks is not None and not self.pga_expert_picks.empty:
            lines.append("")
            lines.append("### PGA Tour Expert Lineups")

            # Count winner picks
            winner_counts = {}
            lineup_counts = {}
            for _, row in self.pga_expert_picks.iterrows():
                expert = row.get('expert_name', 'Unknown')
                winner = row.get('winner_name', '')
                if winner:
                    winner_counts[winner] = winner_counts.get(winner, 0) + 1

                # Count lineup appearances
                try:
                    lineup_names = json.loads(row.get('lineup_player_names', '[]'))
                    for name in lineup_names:
                        if name:
                            lineup_counts[name] = lineup_counts.get(name, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass

            total_experts = len(self.pga_expert_picks)
            lines.append(f"*Based on {total_experts} PGA Tour experts*\n")

            # Top winner picks
            if winner_counts:
                lines.append("**Winner Picks:**")
                sorted_winners = sorted(winner_counts.items(), key=lambda x: x[1], reverse=True)
                for player, count in sorted_winners[:5]:
                    pct = count / total_experts * 100
                    model_player = self._find_player(player)
                    model_str = f" (Model EV: ${model_player.get('expected_value', 0):,.0f})" if model_player is not None else ""
                    lines.append(f"- {player}: {count}/{total_experts} experts ({pct:.0f}%){model_str}")

            # Most rostered
            if lineup_counts:
                lines.append("")
                lines.append("**Most Rostered (in lineup):**")
                sorted_lineup = sorted(lineup_counts.items(), key=lambda x: x[1], reverse=True)
                for player, count in sorted_lineup[:8]:
                    pct = count / total_experts * 100
                    lines.append(f"- {player}: {count}/{total_experts} ({pct:.0f}%)")

        # Add comparison with model
        lines.append("")
        comparison = self._get_expert_comparison_summary()
        if comparison:
            lines.append("### Model vs Expert Comparison")
            lines.append(comparison)

        return "\n".join(lines)

    def _handle_player_form(self, player_name: str) -> str:
        """Handle questions about player's recent form."""
        player = self._find_player(player_name)
        if player is None:
            return f"I couldn't find '{player_name}' in the current field."

        lines = [f"## Recent Form: {player['player_name']}\n"]

        sg_total = player.get('sg_total', 0)
        sg_ott = player.get('season_sg_ott', 0)
        sg_app = player.get('season_sg_app', 0)
        sg_putt = player.get('season_sg_putt', 0)

        lines.append("### Strokes Gained (Season)")
        lines.append(f"- Total: {sg_total:+.3f}")
        lines.append(f"- Off the Tee: {sg_ott:+.3f}")
        lines.append(f"- Approach: {sg_app:+.3f}")
        lines.append(f"- Putting: {sg_putt:+.3f}")
        lines.append("")

        recent_top10s = player.get('recent_top10s', 0)
        recent_cuts_pct = player.get('recent_cuts_pct', 0)
        form_trend = player.get('form_trend', 0)

        lines.append("### Results")
        lines.append(f"- Recent Top 10s: {int(recent_top10s)}")
        lines.append(f"- Cut Rate: {recent_cuts_pct*100:.0f}%")

        if form_trend > 0.5:
            lines.append(f"- Form Trend: **Improving** ({form_trend:+.2f})")
        elif form_trend < -0.5:
            lines.append(f"- Form Trend: **Declining** ({form_trend:+.2f})")
        else:
            lines.append(f"- Form Trend: Stable ({form_trend:+.2f})")

        return "\n".join(lines)

    def _handle_comparison(self, player1_name: str, player2_name: str) -> str:
        """Compare two players head-to-head."""
        player1 = self._find_player(player1_name)
        player2 = self._find_player(player2_name)

        if player1 is None:
            return f"I couldn't find '{player1_name}' in the current field."
        if player2 is None:
            return f"I couldn't find '{player2_name}' in the current field."

        lines = [f"## Comparison: {player1['player_name']} vs {player2['player_name']}\n"]

        # Create comparison table
        metrics = [
            ("World Rank", "world_rank", lambda x: f"#{int(x)}" if pd.notna(x) else "N/A", True),
            ("Expected Value", "expected_value", lambda x: f"${x:,.0f}", False),
            ("Win Prob", "win_prob", lambda x: f"{x*100:.1f}%", False),
            ("Top 10 Prob", "top10_prob", lambda x: f"{x*100:.1f}%", False),
            ("Course Fit", "dg_fit_total", lambda x: f"{x:+.3f}", False),
            ("SG Total", "sg_total", lambda x: f"{x:+.3f}", False),
            ("Recent Top 10s", "recent_top10s", lambda x: f"{int(x)}", False),
        ]

        lines.append(f"| Metric | {player1['player_name']} | {player2['player_name']} | Edge |")
        lines.append("|--------|----------|----------|------|")

        p1_advantages = 0
        p2_advantages = 0

        for name, col, fmt, lower_is_better in metrics:
            v1 = player1.get(col, 0) if pd.notna(player1.get(col)) else 0
            v2 = player2.get(col, 0) if pd.notna(player2.get(col)) else 0

            if lower_is_better:
                winner = player1['player_name'] if v1 < v2 else player2['player_name'] if v2 < v1 else "Tie"
            else:
                winner = player1['player_name'] if v1 > v2 else player2['player_name'] if v2 > v1 else "Tie"

            if winner == player1['player_name']:
                p1_advantages += 1
            elif winner == player2['player_name']:
                p2_advantages += 1

            lines.append(f"| {name} | {fmt(v1)} | {fmt(v2)} | {winner.split()[-1] if winner != 'Tie' else 'Tie'} |")

        lines.append("")

        # Summary
        if p1_advantages > p2_advantages:
            lines.append(f"### Edge: **{player1['player_name']}** ({p1_advantages}-{p2_advantages})")
        elif p2_advantages > p1_advantages:
            lines.append(f"### Edge: **{player2['player_name']}** ({p2_advantages}-{p1_advantages})")
        else:
            lines.append("### Edge: **Too close to call**")

        # EV difference
        ev_diff = player1['expected_value'] - player2['expected_value']
        if abs(ev_diff) > 10000:
            better = player1['player_name'] if ev_diff > 0 else player2['player_name']
            lines.append(f"\n**EV Difference:** ${abs(ev_diff):,.0f} in favor of {better}")

        return "\n".join(lines)

    def _handle_value_plays(self) -> str:
        """Find best value plays (high EV relative to world rank)."""
        df = self.predictions.copy()
        df['value_score'] = df['expected_value'] / (df['world_rank'].clip(lower=1) ** 0.5)

        # Best value among non-elite players (rank > 40)
        non_elite = df[df['world_rank'] > 40].nlargest(5, 'value_score')

        headers = ["#", "Player", "Rank", "EV", "Win", "Course Fit"]
        rows = []
        for i, (_, row) in enumerate(non_elite.iterrows(), 1):
            rows.append([
                i,
                row['player_name'],
                f"#{int(row['world_rank'])}",
                f"${row['expected_value']:,.0f}",
                f"{row['win_prob']*100:.1f}%",
                f"{row.get('dg_fit_total', 0):+.3f}",
            ])

        table = self._fmt_table(headers, rows)
        notes = self._fmt_notes(["Value = EV relative to world rank (rank > 40)."])
        return "\n".join(["## Best Value Plays", table, notes]).strip()

    def _handle_course_fit(self) -> str:
        """Find players with best course fit."""
        df = self.predictions.nlargest(10, 'dg_fit_total')

        headers = ["#", "Player", "Rank", "Course Fit", "EV"]
        rows = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            rank = int(row.get('world_rank', 999)) if pd.notna(row.get('world_rank')) else 'N/A'
            rows.append([
                i,
                row['player_name'],
                f"#{rank}" if rank != 'N/A' else "N/A",
                f"{row['dg_fit_total']:+.3f}",
                f"${row['expected_value']:,.0f}",
            ])
        table = self._fmt_table(headers, rows)
        return "\n".join(["## Best Course Fits", table]).strip()

    def _handle_avoid_players(self) -> str:
        """Find players to potentially avoid."""
        df = self.predictions.copy()

        lines = ["## Players to Consider Avoiding\n"]

        # Poor course fit among higher-ranked players
        poor_fit = df[(df['world_rank'] <= 50) & (df['dg_fit_total'] < -0.2)].nsmallest(5, 'dg_fit_total')
        if len(poor_fit) > 0:
            lines.append("### Poor Course Fit (Despite High Rank)")
            for _, row in poor_fit.iterrows():
                lines.append(f"- **{row['player_name']}** (#{int(row['world_rank'])}) - Fit: {row['dg_fit_total']:+.3f}")
            lines.append("")

        # Low EV relative to rank
        df['ev_vs_expected'] = df['expected_value'] / df['expected_value'].mean()
        df['rank_percentile'] = df['world_rank'].rank(pct=True)
        underperformers = df[(df['world_rank'] <= 30) & (df['ev_vs_expected'] < 0.8)].head(5)

        if len(underperformers) > 0:
            lines.append("### Underperforming Expectations")
            for _, row in underperformers.iterrows():
                lines.append(f"- **{row['player_name']}** (#{int(row['world_rank'])}) - EV: ${row['expected_value']:,.0f}")

        return "\n".join(lines)

    def _handle_field_info(self) -> str:
        """Show field strength information."""
        df = self.predictions

        lines = [f"## Field Information: {self.current_tournament}\n"]
        lines.append(f"**Field Size:** {len(df)} players")

        avg_rank = df['world_rank'].mean()
        median_rank = df['world_rank'].median()
        top_20_count = (df['world_rank'] <= 20).sum()

        lines.append(f"**Average World Rank:** {avg_rank:.1f}")
        lines.append(f"**Median World Rank:** {median_rank:.1f}")
        lines.append(f"**Top 20 Players:** {top_20_count}")
        lines.append("")

        # Top players in field
        top_5 = df.nsmallest(5, 'world_rank')
        lines.append("### Top Ranked Players in Field")
        for _, row in top_5.iterrows():
            lines.append(f"- #{int(row['world_rank'])} {row['player_name']}")

        return "\n".join(lines)

    def _handle_tournament_info(self) -> str:
        """Show tournament information."""
        lines = [f"## Tournament: {self.current_tournament}\n"]

        if TournamentCalendar is not None:
            info = TournamentCalendar.get_tournament_info(self.current_tournament or "")
            importance = TournamentCalendar.get_importance(self.current_tournament or "")
            payout = TournamentCalendar.get_payout_info(self.current_tournament or "")

            if payout:
                lines.append(f"**Purse:** ${payout.get('purse', 0):,.0f}")
                lines.append(f"**Winner's Share:** ${payout.get('winner_share', 0):,.0f}")

            lines.append(f"**Importance:** {importance}/10")
            tier = TournamentCalendar.get_tournament_tier(self.current_tournament or "")
            lines.append(f"**Category:** {tier}")

        return "\n".join(lines)

    def _handle_course_info(self) -> str:
        """Show course profile and weights."""
        lines = [f"## Course Profile: {self.current_tournament}\n"]

        if self.course_weights is not None:
            match = self.course_weights[
                self.course_weights['tournament_name'].str.lower().str.contains(
                    (self.current_tournament or "")[:15].lower(), na=False
                )
            ]
            if len(match) > 0:
                row = match.iloc[0]
                weights = [
                    ('Driving (OTT)', row['ott_sg']),
                    ('Approach', row['app_sg']),
                    ('Short Game (ARG)', row['arg_sg']),
                    ('Putting', row['putt_sg'])
                ]
                weights.sort(key=lambda x: x[1], reverse=True)

                lines.append("### Skill Importance")
                for skill, weight in weights:
                    bar = "█" * int(weight * 100)
                    lines.append(f"- {skill}: {weight:.3f} {bar}")

                lines.append(f"\n**Primary Skill:** {weights[0][0]}")
                lines.append(f"**Secondary Skill:** {weights[1][0]}")
            else:
                lines.append("Course weights not found for this tournament.")
        else:
            lines.append("Course weights data not loaded.")

        return "\n".join(lines)

    def _handle_help_questions(self) -> str:
        """Return example questions users can ask."""
        lines = ["## Example Questions\n"]
        lines.append("### Weekly / Picks")
        lines.append("- What are the power rankings this week?")
        lines.append("- Top 10 picks this week")
        lines.append("- Best value plays this week")
        lines.append("- Give me a lineup recommendation")
        lines.append("")
        lines.append("### Planning / Strategy Engine")
        lines.append("- Show the scoring engine picks")
        lines.append("- Planning picks this week")
        lines.append("- Scoring engine value picks")
        lines.append("- Scoring engine for Waste Management Phoenix Open")
        lines.append("- Best tournaments for Scottie Scheffler")
        lines.append("- Optimize remaining uses for Rory McIlroy")
        lines.append("- Strategy dashboard")
        lines.append("- Scoring engine top 20 for this week")
        lines.append("- Scoring engine weights: importance 0.3 course 0.4 form 0.2 field 0.1")
        lines.append("")
        lines.append("### Player Questions")
        lines.append("- Should I use Scottie Scheffler this week?")
        lines.append("- Why is Max Homa ranked #7?")
        lines.append("- Compare Xander vs Cantlay")
        lines.append("")
        lines.append("### Odds / Betting")
        lines.append("- Where does the model disagree with Vegas?")
        lines.append("- Which odds are moving the most?")
        lines.append("")
        lines.append("### Usage / Season Planning")
        lines.append("- When should I use Rory this season?")
        lines.append("- Season optimizer dashboard")
        lines.append("- What tournaments should I save Rahm for?")
        lines.append("")
        lines.append("### Course / Field")
        lines.append("- Best course fits this week?")
        lines.append("- Course profile for this tournament")
        return "\n".join(lines)

    def _handle_season_dashboard(self) -> str:
        """Show season optimizer dashboard with schedule + allocations."""
        schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
        if not schedule_path.exists():
            return "No schedule file found (data/raw/schedule_2026.csv)."

        schedule = pd.read_csv(schedule_path)
        # Normalize money
        for col in ["purse", "winner_share"]:
            if col in schedule.columns:
                schedule[col] = schedule[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
                schedule[col] = pd.to_numeric(schedule[col], errors="coerce")

        def importance_from_winner_share(w):
            if pd.isna(w):
                return 5
            if w >= 4_000_000:
                return 10
            if w >= 3_500_000:
                return 9
            if w >= 3_000_000:
                return 8
            if w >= 2_000_000:
                return 7
            if w >= 1_500_000:
                return 5
            return 3

        schedule["importance"] = schedule["winner_share"].apply(importance_from_winner_share)

        # Try to find season predictions file
        candidates = [
            OUTPUTS_DIR / "season_predictions.csv",
            OUTPUTS_DIR / "season_predictions_2026.csv",
            OUTPUTS_DIR / "weekly_predictions.csv",
        ]
        season_preds = next((p for p in candidates if p.exists()), None)

        plan = None
        if season_preds and SeasonUsagePlanner is not None:
            try:
                planner = SeasonUsagePlanner()
                plan = planner.build_plan(season_preds)
            except Exception:
                plan = None

        lines = ["## Season Optimizer Dashboard\n"]
        lines.append("### Schedule (Importance)")
        for _, row in schedule.head(30).iterrows():
            lines.append(
                f"- Week {int(row.get('week', 0))}: {row.get('tournament_name')} "
                f"(Importance: {int(row.get('importance', 5))}/10, Purse: ${int(row.get('purse', 0)):,})"
            )

        if plan and plan.get("weeks"):
            lines.append("\n### Recommended Allocations")
            for wk in plan["weeks"]:
                if not wk.get("lineup"):
                    lines.append(f"- Week {wk.get('week')}: {wk.get('tournament_name')} — No lineup")
                    continue
                players = ", ".join([p["player_name"] for p in wk["lineup"]])
                lines.append(f"- Week {wk.get('week')}: {wk.get('tournament_name')} → {players}")

            # When to use Scottie
            scottie_weeks = [
                f"Week {wk.get('week')}: {wk.get('tournament_name')}"
                for wk in plan["weeks"]
                if any("scheffler" in p["player_name"].lower() for p in wk.get("lineup", []))
            ]
            if scottie_weeks:
                lines.append("\n### When to use Scottie Scheffler")
                lines.extend([f"- {w}" for w in scottie_weeks])
        else:
            lines.append("\n### Recommended Allocations")
            if season_preds:
                lines.append("- Season predictions file found but planner could not build plan.")
            else:
                lines.append("- No season predictions file found in outputs/.")

        return "\n".join(lines)

    def _handle_scoring_engine_recs(self) -> str:
        """Return scoring engine recommendations (delegates to this_week handler)."""
        return self._handle_scoring_engine_this_week()

    def _handle_scoring_engine_this_week(self) -> str:
        """Return scoring engine recommendations for the current week."""
        if self.scoring_engine is None:
            return "Scoring engine not available."

        try:
            tourney = self.scoring_engine.get_current_week_tournament()
            if not tourney or tourney not in self.scoring_engine.tournaments:
                return "No current tournament found."

            t = self.scoring_engine.tournaments[tourney]
            lines = []

            # Header
            lines.append(f"## {tourney}")
            lines.append(f"**Week {t.week}** | {t.start_date} | {t.course or t.location} | ${t.purse/1e6:.1f}M | {t.tournament_type} | Importance: {t.importance_score:.0f}/100")
            lines.append("")

            # Main recommendations table (markdown)
            top_scores = self.scoring_engine.get_tournament_recommendations(tourney, top_n=15)
            headers = ["#", "Player", "Score", "Rating", "Course", "Form", "Uses", "Notes"]
            rows = []
            for i, s in enumerate(top_scores, 1):
                uses_str = f"{s.remaining_uses}/3"
                if s.usage_warning:
                    uses_str = s.usage_warning
                rows.append([
                    i, s.player, f"{s.total_score:.0f}", s.value_rating,
                    f"{s.course_fit:.0f}", f"{s.current_form:.0f}",
                    uses_str, s.course_history_note or ""
                ])
            lines.append(self._fmt_table(headers, rows))

            # Value picks section
            min_score = 35 if t.importance_score < 40 else 45
            value_scores = self.scoring_engine.get_value_picks(tourney, min_score=min_score)
            if value_scores:
                lines.append("")
                lines.append("### Value Picks (Rank 20-60)")
                v_headers = ["Rank", "Player", "Score", "Course", "Form", "History"]
                v_rows = []
                for s in value_scores[:5]:
                    v_rows.append([
                        f"#{s.owgr_rank}", s.player, f"{s.total_score:.0f}",
                        f"{s.course_fit:.0f}", s.form_trend, s.course_history_note
                    ])
                lines.append(self._fmt_table(v_headers, v_rows))

            return "\n".join(lines)
        except Exception as e:
            return f"Scoring engine error: {e}"

    def _handle_scoring_engine_value(self) -> str:
        """Return scoring engine value picks for the current tournament."""
        if self.scoring_engine is None:
            return "Scoring engine not available."

        try:
            tourney = self.scoring_engine.get_current_week_tournament()
            if not tourney or tourney not in self.scoring_engine.tournaments:
                return "No current tournament found."

            t = self.scoring_engine.tournaments[tourney]
            min_score = 35 if t.importance_score < 40 else 45

            lines = []
            lines.append(f"## Value Picks: {tourney}")
            lines.append(f"Players ranked 20-60 with score >= {min_score}")
            lines.append("")

            value_scores = self.scoring_engine.get_value_picks(
                tourney, rank_min=20, rank_max=60, min_score=min_score
            )
            if not value_scores:
                lines.append("No value picks meeting criteria.")
                return "\n".join(lines)

            headers = ["Rank", "Player", "Score", "Course", "Form", "Trend", "History"]
            rows = []
            for s in value_scores[:10]:
                rows.append([
                    f"#{s.owgr_rank}", s.player, f"{s.total_score:.0f}",
                    f"{s.course_fit:.0f}", f"{s.current_form:.0f}",
                    s.form_trend, s.course_history_note or ""
                ])
            lines.append(self._fmt_table(headers, rows))
            return "\n".join(lines)
        except Exception as e:
            return f"Scoring engine error: {e}"

    def _handle_scoring_engine_tournament(self, tournament_name: str, question: str = "") -> str:
        """Return scoring engine recommendations for a specific tournament."""
        if self.scoring_engine is None:
            return "Scoring engine not available. Please check scripts/planning/scoring_engine.py."
        if not tournament_name:
            return "Please provide a tournament name."

        try:
            engine = self._get_scoring_engine_for_question(question)
            # Use scoring engine's tournament list to find best match
            tourney = self._match_scoring_engine_tournament(tournament_name, engine)
            if not tourney:
                return f"Tournament not found: {tournament_name}"

            lines = [f"## Scoring Engine Picks: {tourney}"]
            top_n = self._parse_top_n(question, default=15)
            top_scores = engine.get_tournament_recommendations(tourney, top_n=top_n)
            headers = ["#", "Player", "Score", "Imp", "Fit", "Form"]
            rows = []
            for i, s in enumerate(top_scores, 1):
                rows.append([
                    i,
                    s.player,
                    f"{s.total_score:.1f}",
                    f"{s.tournament_importance:.0f}",
                    f"{s.course_fit:.0f}",
                    f"{s.current_form:.0f}",
                ])
            lines.append(self._fmt_table(headers, rows))
            return "\n".join(lines)
        except Exception:
            return "Scoring engine failed to generate recommendations."

    def _handle_scoring_engine_player(self, player_name: str, question: str = "") -> str:
        """Return scoring engine best tournaments for a player."""
        if self.scoring_engine is None:
            return "Scoring engine not available. Please check scripts/planning/scoring_engine.py."
        if not player_name:
            return "Please provide a player name."

        try:
            engine = self._get_scoring_engine_for_question(question)
            top_n = self._parse_top_n(question, default=8)
            recs = engine.get_player_best_tournaments(player_name, upcoming_only=True, top_n=top_n)
            if not recs:
                return f"No tournaments found for {player_name}."

            lines = [f"## Best Tournaments for {player_name} (Scoring Engine)"]
            headers = ["Tournament", "Date", "Importance", "Score", "Form"]
            rows = []
            for r in recs:
                t = engine.tournaments.get(r.tournament)
                date = t.start_date if t else ""
                rows.append([
                    r.tournament,
                    date,
                    f"{r.tournament_importance:.0f}",
                    f"{r.total_score:.1f}",
                    r.form_trend,
                ])
            lines.append(self._fmt_table(headers, rows))
            return "\n".join(lines)
        except Exception:
            return "Scoring engine failed to generate player recommendations."

    def _match_scoring_engine_tournament(self, name: str, engine: Optional[object] = None) -> Optional[str]:
        """Fuzzy match a tournament name against scoring engine schedule."""
        engine = engine or self.scoring_engine
        if engine is None:
            return None
        name_l = name.lower().strip()
        # exact match
        for t in engine.tournaments.keys():
            if t.lower() == name_l:
                return t
        # contains match
        for t in engine.tournaments.keys():
            if name_l in t.lower():
                return t
        # partial word match
        tokens = [tok for tok in re.split(r"\s+", name_l) if tok]
        best = None
        best_hits = 0
        for t in engine.tournaments.keys():
            tl = t.lower()
            hits = sum(1 for tok in tokens if tok in tl)
            if hits > best_hits:
                best_hits = hits
                best = t
        return best

    def _handle_scoring_engine_strategy(self, question: str = "") -> str:
        """Return unified strategy dashboard."""
        if self.scoring_engine is None:
            return "Scoring engine not available."

        try:
            engine = self._get_scoring_engine_for_question(question)
            today = datetime.now().strftime('%Y-%m-%d')
            lines = []

            lines.append("## Fantasy Golf Strategy Dashboard")
            lines.append(f"*Generated: {today}*")

            tourney = engine.get_current_week_tournament()
            if tourney and tourney in engine.tournaments:
                t = engine.tournaments[tourney]
                lines.append("")
                lines.append(f"### This Week: {tourney}")
                lines.append(f"**Week {t.week}** | {t.start_date} | {t.course or t.location} | ${t.purse/1e6:.1f}M | {t.tournament_type}")
                lines.append("")

                # Top picks table
                lines.append("**Top Picks:**")
                recommendations = engine.get_tournament_recommendations(tourney, top_n=5)
                headers = ["#", "Player", "Score", "Course", "Uses", "Note"]
                rows = []
                for i, score in enumerate(recommendations, 1):
                    warning = "Save?" if score.owgr_rank <= 10 and t.importance_score < 50 else ""
                    rows.append([i, score.player, f"{score.total_score:.0f}",
                                f"{score.course_fit:.0f}", f"{score.remaining_uses}/3", warning])
                lines.append(self._fmt_table(headers, rows))

                # Value plays
                min_score = 35 if t.importance_score < 40 else 45
                value_picks = engine.get_value_picks(tourney, min_score=min_score)
                if value_picks:
                    lines.append("")
                    lines.append("**Value Plays (Rank 20-60):**")
                    for score in value_picks[:3]:
                        lines.append(f"- #{score.owgr_rank} {score.player} — Score: {score.total_score:.0f} ({score.course_history_note})")

            # Usage status
            lines.append("")
            lines.append("### Usage Status")

            usage_file = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
            if usage_file.exists():
                with open(usage_file, 'r') as f:
                    usage_data = json.load(f)
                picks = usage_data.get("picks", {})
                if picks:
                    exhausted = [p for p, i in picks.items() if i.get("remaining_uses", 3) == 0]
                    last_use = [p for p, i in picks.items() if i.get("remaining_uses", 3) == 1]
                    if exhausted:
                        lines.append(f"- **Exhausted (0 uses):** {', '.join(exhausted)}")
                    if last_use:
                        lines.append(f"- **Last Use (1 remaining):** {', '.join(last_use)}")
                    lines.append(f"- **Total players used:** {len(picks)}")
                else:
                    lines.append("No picks recorded yet")
            else:
                lines.append("No usage data available")

            return "\n".join(lines)
        except Exception as e:
            return f"Strategy dashboard error: {e}"

    def _handle_scoring_engine_optimize(self, player_name: str, question: str = "") -> str:
        """Optimize remaining uses for a player."""
        if self.scoring_engine is None:
            return "Scoring engine not available. Please check scripts/planning/scoring_engine.py."
        if not player_name:
            return "Please provide a player name."

        try:
            engine = self._get_scoring_engine_for_question(question)
            usage, recs = engine.get_optimized_recommendations(player_name, top_n=8)
            if not recs:
                return f"No recommendations found for {player_name}."

            lines = [f"## Optimized Uses for {player_name} (Scoring Engine)"]
            lines.append(
                f"Uses remaining: {usage.get('remaining_uses', 3)} "
                f"(used {usage.get('times_used', 0)}x)"
            )
            headers = ["Tournament", "Date", "Score", "Type", "Priority"]
            rows = []
            for r in recs:
                rows.append([
                    r.get('tournament'),
                    r.get('date'),
                    f"{r.get('total_score', 0):.1f}",
                    r.get('type'),
                    r.get('use_priority'),
                ])
            lines.append(self._fmt_table(headers, rows))
            return "\n".join(lines)
        except Exception:
            return "Scoring engine failed to optimize uses."

    def _handle_power_rankings_list(self, question: str = "") -> str:
        """Show power rankings list."""
        if self.power_rankings is None or "player_name" not in self.power_rankings.columns:
            return "No power rankings loaded."

        df = self.power_rankings.copy()
        if "rank" in df.columns:
            df = df.sort_values("rank")
        top_n = self._parse_top_n(question, default=10)
        df = df.head(top_n)

        # Get tournament name from data if available
        tourney_name = df["tournament_name"].iloc[0] if "tournament_name" in df.columns else "This Week"

        lines = []
        lines.append(f"## Power Rankings: {tourney_name}")
        lines.append("")

        headers = ["Rank", "Player", "Analysis"]
        rows = []
        for _, row in df.iterrows():
            analysis = row.get("analysis", "")
            if isinstance(analysis, str) and len(analysis) > 80:
                analysis = analysis[:77] + "..."
            rows.append([
                int(row.get("rank")) if pd.notna(row.get("rank")) else "",
                row.get("player_name", "Unknown"),
                analysis,
            ])

        lines.append(self._fmt_table(headers, rows))
        return "\n".join(lines)

    def _handle_power_rank_player(self, player_name: str) -> str:
        """Show power ranking entry for a single player."""
        if not player_name:
            return "Please specify a player name."
        pr = self._get_power_ranking(player_name)
        if not pr:
            return f"No power ranking found for {player_name}."
        rank = pr.get("rank")
        analysis = pr.get("analysis", "")
        source = pr.get("source", "")
        lines = [f"## Power Ranking: {player_name}"]
        if rank is not None and pd.notna(rank):
            lines.append(f"- Rank: {int(rank)}")
        if analysis:
            lines.append(f"- Analysis: {analysis}")
        if source:
            lines.append(f"- Source: {source}")
        return "\n".join(lines)

    def _handle_player_odds(self, player_name: str) -> str:
        """Show betting odds for a single player."""
        if not player_name:
            return "Please specify a player name."
        if self.betting_profiles is None:
            return "No betting profiles loaded."

        df = self.betting_profiles
        key = player_name.lower().strip()
        row = df[df["player_name"].str.lower() == key]
        if row.empty:
            row = df[df["player_name"].str.lower().str.contains(key, na=False)]
        if row.empty:
            return f"No odds found for {player_name}."
        r = row.iloc[0]

        odds = r.get("odds_to_win", "")
        implied = r.get("implied_prob", "")
        implied_str = f"{implied:.1%}" if pd.notna(implied) else ""
        rank = r.get("odds_rank", "")
        swing = r.get("odds_swing", "")
        fedex = r.get("fedex_rank", "")

        lines = [f"## Odds: {r.get('player_name', player_name)}"]
        lines.append(f"- Odds: {odds}")
        if implied_str:
            lines.append(f"- Implied Prob: {implied_str}")
        if pd.notna(rank):
            lines.append(f"- Odds Rank: #{int(rank)}")
        if swing:
            lines.append(f"- Odds Move: {swing}")
        if pd.notna(fedex):
            lines.append(f"- FedEx Rank: #{int(fedex)}")
        return "\n".join(lines)

    def _handle_odds_list(self, question: str = "") -> str:
        """Show top betting favorites."""
        if self.betting_profiles is None or "odds_rank" not in self.betting_profiles.columns:
            return "No betting profiles loaded."

        df = self.betting_profiles.copy()
        df = df[pd.notna(df["odds_rank"])].sort_values("odds_rank")
        top_n = self._parse_top_n(question, default=10)
        df = df.head(top_n)

        lines = []
        lines.append(f"## Betting Favorites (Top {top_n})")
        lines.append("")

        headers = ["Rank", "Player", "Odds", "Implied", "Move"]
        rows = []
        for _, r in df.iterrows():
            implied = r.get("implied_prob", "")
            implied_str = f"{implied:.1%}" if pd.notna(implied) else ""
            rows.append([
                f"#{int(r.get('odds_rank'))}" if pd.notna(r.get("odds_rank")) else "",
                r.get("player_name", ""),
                r.get("odds_to_win", ""),
                implied_str,
                r.get("odds_swing", ""),
            ])

        lines.append(self._fmt_table(headers, rows))
        return "\n".join(lines)

    def _fmt_table(self, headers: List[str], rows: List[List[Any]]) -> str:
        """Render a compact markdown table."""
        if not rows:
            return ""
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        body_lines = [
            "| " + " | ".join("" if v is None else str(v) for v in row) + " |"
            for row in rows
        ]
        return "\n".join([header_line, sep_line] + body_lines)

    def _fmt_ascii_table(self, headers: List[str], rows: List[List[Any]], widths: List[int] = None) -> str:
        """Render a CLI-style ASCII table with fixed column widths."""
        if not rows:
            return ""
        # Calculate column widths if not provided
        if widths is None:
            widths = []
            for i, h in enumerate(headers):
                max_w = len(str(h))
                for row in rows:
                    if i < len(row):
                        max_w = max(max_w, len(str(row[i] or "")))
                widths.append(min(max_w + 1, 30))  # cap at 30 chars

        # Build header line
        header_parts = []
        for i, h in enumerate(headers):
            w = widths[i] if i < len(widths) else 10
            header_parts.append(f"{h:<{w}}")
        lines = ["  " + " ".join(header_parts)]
        lines.append("  " + "-" * (sum(widths) + len(widths) - 1))

        # Build data rows
        for row in rows:
            row_parts = []
            for i, val in enumerate(row):
                w = widths[i] if i < len(widths) else 10
                s = str(val) if val is not None else ""
                if len(s) > w:
                    s = s[:w-1] + "…"
                row_parts.append(f"{s:<{w}}")
            lines.append("  " + " ".join(row_parts))

        return "\n".join(lines)

    def _fmt_bullets(self, title: str, items: List[str]) -> str:
        """Render a bullet list with a title."""
        if not items:
            return ""
        lines = [f"### {title}"]
        lines.extend([f"- {item}" for item in items])
        return "\n".join(lines)

    def _fmt_notes(self, notes: List[str]) -> str:
        """Render a notes block."""
        if not notes:
            return ""
        lines = ["Notes:"]
        lines.extend([f"- {note}" for note in notes])
        return "\n".join(lines)

    def _parse_top_n(self, question: str, default: int = 15) -> int:
        """Parse a 'top N' request from question."""
        if not question:
            return default
        m = re.search(r"top\s+(\d+)", question.lower())
        if m:
            try:
                return max(1, min(50, int(m.group(1))))
            except Exception:
                return default
        return default

    def _parse_weights_from_question(self, question: str) -> Optional[Dict[str, float]]:
        """Parse weight overrides from question text."""
        if not question:
            return None
        q = question.lower()
        keys = {
            "importance": ["importance", "imp", "w-importance"],
            "course_fit": ["course", "course_fit", "w-course"],
            "form": ["form", "w-form"],
            "field": ["field", "w-field"],
        }
        found = {}
        for key, aliases in keys.items():
            for a in aliases:
                m = re.search(rf"{a}\\s*[:=]?\\s*([0-9]*\\.?[0-9]+)", q)
                if m:
                    val = float(m.group(1))
                    if val > 1:
                        val = val / 100.0 if val <= 100 else val
                    found[key] = val
                    break
        if not found:
            return None
        total = sum(found.values())
        if total > 0:
            found = {k: v / total for k, v in found.items()}
        return found

    def _get_scoring_engine_for_question(self, question: str):
        """Return scoring engine, optionally reweighted from question."""
        weights = self._parse_weights_from_question(question)
        if not weights:
            return self.scoring_engine
        try:
            return ScoringEngine(weights=weights, tournament=self.current_tournament)
        except Exception:
            return self.scoring_engine

    def _load_schedule(self) -> Optional[pd.DataFrame]:
        schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
        if not schedule_path.exists():
            return None
        try:
            return pd.read_csv(schedule_path)
        except Exception:
            return None

    def _match_schedule_tournament(self, name: str) -> Optional[dict]:
        """Fuzzy match tournament name in schedule."""
        schedule = self._load_schedule()
        if schedule is None or schedule.empty:
            return None
        name_l = name.lower().strip()
        schedule = schedule.copy()
        schedule["name_l"] = schedule["tournament_name"].str.lower()

        exact = schedule[schedule["name_l"] == name_l]
        if len(exact) > 0:
            return exact.iloc[0].to_dict()

        contains = schedule[schedule["name_l"].str.contains(name_l, na=False)]
        if len(contains) > 0:
            return contains.iloc[0].to_dict()

        tokens = [t for t in re.split(r"\s+", name_l) if t]
        best = None
        best_hits = 0
        for _, row in schedule.iterrows():
            tl = row["name_l"]
            hits = sum(1 for tok in tokens if tok in tl)
            if hits > best_hits:
                best_hits = hits
                best = row
        return best.to_dict() if best is not None and best_hits > 0 else None

    def _slugify(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return slug

    def _find_field_file(self, tournament_name: str) -> Optional[Path]:
        fields_dir = DATA_DIR / "fields"
        if not fields_dir.exists():
            return None
        slug = self._slugify(tournament_name)
        candidates = sorted(fields_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in candidates:
            fname = f.name.lower()
            if slug in fname:
                return f
        # fallback: partial match with first 2 words
        tokens = [t for t in slug.split("_") if t]
        for f in candidates:
            fname = f.name.lower()
            if any(tok in fname for tok in tokens[:2]):
                return f
        return None

    def _find_odds_file(self, tournament_id: str) -> Optional[Path]:
        if not tournament_id:
            return None
        odds_dir = DATA_DIR / "odds"
        if not odds_dir.exists():
            return None
        pattern = f"pga_odds_{tournament_id}.csv".lower()
        for f in odds_dir.glob("*.csv"):
            if f.name.lower() == pattern:
                return f
        return None

    def _handle_run_predictions(self, tournament_name: str, question: str = "") -> str:
        """Prepare a prediction run and ask for confirmation."""
        # Default to current tournament if not specified
        if not tournament_name:
            tournament_name = self.current_tournament or ""
        if not tournament_name:
            return "Please specify a tournament name."

        schedule_row = self._match_schedule_tournament(tournament_name)
        if not schedule_row:
            return f"Could not find tournament in schedule: {tournament_name}"

        tournament_id = schedule_row.get("tournament_id", "")
        purse_raw = schedule_row.get("purse", "")
        t_type = schedule_row.get("tournament_type", "Standard")
        try:
            purse = float(str(purse_raw).replace("$", "").replace(",", ""))
        except Exception:
            purse = None

        field_file = self._find_field_file(schedule_row.get("tournament_name", tournament_name))
        odds_file = self._find_odds_file(tournament_id)

        missing = []
        if purse is None:
            missing.append("purse")
        if field_file is None:
            missing.append("field file")

        if missing:
            return (
                f"Missing required inputs: {', '.join(missing)}. "
                "Please provide them or add to schedule/fields."
            )

        cmd = [
            "python3",
            "scripts/predictions/predict_tournament.py",
            "--tournament", schedule_row.get("tournament_name", tournament_name),
            "--tournament-id", tournament_id,
            "--purse", str(int(purse)),
            "--field", str(field_file),
            "--tournament-type", str(t_type),
            "--insights",
            "--calibrate",
            "--usage-strategy",
        ]
        if odds_file is not None:
            cmd.extend(["--odds", str(odds_file)])

        if "record" in question.lower() or "final" in question.lower():
            cmd.extend(["--record-lineup", "true"])

        self._pending_action = {"type": "run_predictions", "command": cmd}

        cmd_str = " ".join(shlex.quote(c) for c in cmd)
        return (
            "Ready to run predictions with:\n"
            f"`{cmd_str}`\n\n"
            "Reply **confirm predictions** to run or **cancel** to abort."
        )

    def _handle_confirm_run_predictions(self) -> str:
        """Execute the pending prediction command."""
        if not self._pending_action or self._pending_action.get("type") != "run_predictions":
            return "No pending prediction run. Ask me to run predictions first."

        cmd = self._pending_action.get("command")
        self._pending_action = None

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return f"Prediction run failed:\n{result.stderr.strip()}"
            return "Predictions complete. Check outputs for results."
        except Exception as e:
            return f"Failed to run predictions: {e}"

    def _handle_cancel_run_predictions(self) -> str:
        """Cancel the pending prediction command."""
        if self._pending_action:
            self._pending_action = None
            return "Canceled the pending prediction run."
        return "No pending prediction run to cancel."

    def _handle_usage_status(self) -> str:
        """Show usage status for all tracked players."""
        if self.usage_tracker is None:
            return "No usage tracking data available."

        lines = ["## Player Usage Status\n"]

        # Players with limited uses
        low = self.usage_tracker[self.usage_tracker['uses_remaining'] <= 1]
        if len(low) > 0:
            lines.append("### Low Uses Remaining")
            for _, row in low.iterrows():
                lines.append(f"- {row['player_name']}: {int(row['uses_remaining'])} uses left")
            lines.append("")

        # Recently used
        used = self.usage_tracker[self.usage_tracker['uses_remaining'] < 3]
        if len(used) > 0:
            lines.append("### All Used Players")
            for _, row in used.iterrows():
                lines.append(f"- {row['player_name']}: {int(row['uses_remaining'])}/3")

        return "\n".join(lines)

    def _handle_player_usage(self, player_name: str) -> str:
        """Show usage for specific player."""
        if self.usage_tracker is None:
            return f"No usage tracking data. {player_name} likely has 3/3 uses remaining."

        matches = self.usage_tracker[
            self.usage_tracker['player_name'].str.lower().str.contains(player_name.lower(), na=False)
        ]
        if len(matches) > 0:
            row = matches.iloc[0]
            return f"**{row['player_name']}**: {int(row['uses_remaining'])}/3 uses remaining"
        else:
            return f"**{player_name}**: 3/3 uses remaining (not yet used)"

    def _handle_player_usage_strategy(self, player_name: str) -> str:
        """Provide full-season usage recommendations for a player."""
        if not player_name:
            return "Please specify a player name."

        # Try the new season planner first
        if SEASON_PLANNER_AVAILABLE:
            try:
                qualifications = load_player_qualifications()
                recommendations = recommend_tournaments_for_player(
                    player_name,
                    num_uses=3,
                    qualifications=qualifications
                )

                if recommendations:
                    lines = [f"## Season Usage Plan: {player_name}"]
                    lines.append("")
                    lines.append("### Top 3 Tournaments to Use This Player:")
                    lines.append("")

                    for i, rec in enumerate(recommendations[:3], 1):
                        stars = "★" * rec.rating + "☆" * (5 - rec.rating)
                        lines.append(f"**{i}. {rec.tournament_name}** ({rec.tournament_date})")
                        lines.append(f"   - Type: {rec.tournament_type} | Purse: ${rec.purse:,}")
                        lines.append(f"   - Expected Value: ${rec.expected_value:,.0f}")
                        lines.append(f"   - Course History: {rec.course_history}")
                        lines.append(f"   - Rating: {stars}")
                        lines.append(f"   - Why: {rec.reasoning}")
                        lines.append("")

                    # Show backup options
                    if len(recommendations) > 3:
                        lines.append("### Backup Options:")
                        for rec in recommendations[3:6]:
                            lines.append(f"- {rec.tournament_name} - ${rec.expected_value:,.0f} EV ({rec.tournament_type})")

                    # Show what to skip
                    if len(recommendations) > 6:
                        lines.append("")
                        lines.append("### Skip These (save uses for above):")
                        for rec in recommendations[6:9]:
                            lines.append(f"- {rec.tournament_name} - ${rec.expected_value:,.0f} EV")

                    # Add scoring engine recommendations if available
                    if self.scoring_engine is not None:
                        try:
                            usage, recs = self.scoring_engine.get_optimized_recommendations(player_name, top_n=6)
                            if recs:
                                lines.append("")
                                lines.append("### Scoring Engine (usage optimization)")
                                lines.append(
                                    f"- Uses remaining: {usage.get('remaining_uses', 3)} "
                                    f"(used {usage.get('times_used', 0)}x)"
                                )
                                for r in recs[:5]:
                                    lines.append(
                                        f"- {r.get('tournament')} | "
                                        f"Score {r.get('total_score', 0):.1f} | "
                                        f"{r.get('type')} | {r.get('use_priority')}"
                                    )
                        except Exception:
                            pass

                    return "\n".join(lines)
            except Exception:
                # Fall back to old method
                pass

        # Fallback to old usage optimizer
        if self.usage_optimizer is None:
            return "Season planner not available. Please check installation."

        # Enforce "in field" constraint for current week questions
        if self.predictions is not None:
            in_field = self._find_player(player_name)
            if in_field is None:
                return f"**{player_name}** is not in this week's field."

        result = self.usage_optimizer.should_use_player(
            player_name, self.current_tournament or "Unknown Tournament"
        )

        lines = [f"## Usage Strategy: {player_name}"]
        rec = result.get("recommendation", "UNKNOWN")
        lines.append(f"**Recommendation:** {rec}")
        if result.get("score") is not None:
            lines.append(f"**Usage Score:** {result['score']:.1f}")

        remaining = result.get("remaining_uses")
        if remaining is not None:
            lines.append(f"**Uses Remaining:** {remaining}")

        tier = result.get("tournament_tier")
        if tier:
            lines.append(f"**Tournament Tier:** {tier}")

        if result.get("reasoning"):
            lines.append("")
            lines.append("### Reasoning")
            for r in result["reasoning"]:
                lines.append(f"- {r}")

        if result.get("upcoming_events"):
            lines.append("")
            lines.append("### Upcoming Important Events")
            for event in result["upcoming_events"]:
                lines.append(f"- {event.get('name')} (Tier: {event.get('tier')}, Winner: ${event.get('winner_share', 0):,.0f})")

        return "\n".join(lines)

    def _handle_top_players(self, count: int = 5) -> str:
        """Show top players by EV."""
        count = min(count, 20)
        top = self.predictions.nlargest(count, 'expected_value')

        headers = ["#", "Player", "Rank", "EV", "Win", "Top-10"]
        rows = []
        for i, (_, row) in enumerate(top.iterrows(), 1):
            rank = int(row.get('world_rank', 999)) if pd.notna(row.get('world_rank')) else 'N/A'
            rows.append([
                i,
                row['player_name'],
                f"#{rank}" if rank != 'N/A' else "N/A",
                f"${row['expected_value']:,.0f}",
                f"{row['win_prob']*100:.1f}%",
                f"{row['top10_prob']*100:.1f}%",
            ])

        table = self._fmt_table(headers, rows)
        return "\n".join([f"## Top {count} Picks This Week", table]).strip()

    def _format_lineup_response(self, result: Dict) -> str:
        """Format lineup recommendation as string."""
        lines = [f"## Lineup Recommendation: {result.get('tournament_name', 'Unknown')}"]

        reasoning = result.get('reasoning', [])
        if reasoning:
            lines.append(self._fmt_bullets("Rationale", reasoning))

        if result.get('strategic_notes'):
            lines.append(self._fmt_bullets("Strategic Notes", result['strategic_notes']))

        headers = ["#", "Player", "Rank", "EV", "Usage"]
        rows = []
        for i, p in enumerate(result.get('lineup', []), 1):
            rank = int(p.get('world_rank', 999)) if p.get('world_rank') else 'N/A'
            usage_rec = p.get('usage_recommendation')
            uses_remaining = p.get('uses_remaining')
            usage_text = ""
            if usage_rec:
                if uses_remaining is not None:
                    usage_text = f"{usage_rec} ({uses_remaining}/3)"
                else:
                    usage_text = usage_rec
            rows.append([
                i,
                p['name'],
                f"#{rank}" if rank != 'N/A' else "N/A",
                f"${p['ev']:,.0f}",
                usage_text,
            ])

        lines.append("### Recommended Lineup")
        lines.append(self._fmt_table(headers, rows))
        lines.append(f"**Total EV:** ${result.get('total_ev', 0):,.0f}")

        return "\n".join([ln for ln in lines if ln]).strip()

    def get_lineup_recommendation(
        self,
        tournament_name: str = None,
        tournament_type: str = None,
        exclude_players: List[str] = None,
        prioritize_value: bool = False,
        use_strategy: bool = True,
        save_log: bool = False
    ) -> Dict[str, Any]:
        """
        Get a full lineup recommendation with strategic usage optimization.

        Args:
            tournament_name: Name of the tournament (used for payout-based importance)
            tournament_type: Override tournament type (major, signature, etc.)
            exclude_players: Players to exclude (e.g., no uses left)
            prioritize_value: Whether to prioritize value over ceiling
            use_strategy: Whether to factor in usage strategy (save elite players for big events)

        Returns:
            Dict with recommended lineup and reasoning
        """
        if self.predictions is None:
            return {"error": "No predictions loaded"}

        tournament_name = tournament_name or self.current_tournament or "Unknown Tournament"
        exclude_players = exclude_players or []
        roster_size = self.format['roster_size']

        # Get tournament info from payout data
        payout_info = {}
        tournament_importance = 5
        if TournamentCalendar is not None:
            payout_info = TournamentCalendar.get_payout_info(tournament_name)
            tournament_importance = TournamentCalendar.get_importance(tournament_name)
            detected_tier = TournamentCalendar.get_tournament_tier(tournament_name)
        else:
            detected_tier = "STANDARD"

        # Use detected tier if tournament_type not explicitly provided
        if tournament_type is None:
            tournament_type = detected_tier.lower()

        # Filter available players
        available = self.predictions[
            ~self.predictions['player_name'].str.lower().isin([p.lower() for p in exclude_players])
        ].copy()

        # Get tournament strategy
        t_strategy = FantasyGolfRules.get_tournament_strategy(tournament_type)

        lineup = []
        reasoning = []
        strategic_notes = []

        # Add payout info to reasoning
        winner_share = payout_info.get('winner_share', 0)
        if winner_share > 0:
            reasoning.append(f"Tournament: {tournament_name} (Winner: ${winner_share:,.0f})")
        reasoning.append(f"Detected tier: {detected_tier} (importance: {tournament_importance}/10)")

        # Tier distribution based on tournament importance and roster size
        # For 3-player roster, we need different distributions than 6-player
        if roster_size <= 3:
            # 3-player lineup distributions
            if tournament_importance >= 10:  # Majors
                tier_targets = {"tier1": 1, "tier2": 1, "tier3": 1, "tier4": 0}
                reasoning.append("Strategy: Use 1 elite + balanced supporting cast - premium event")
            elif tournament_importance >= 8:  # Signatures
                tier_targets = {"tier1": 1, "tier2": 1, "tier3": 1, "tier4": 0}
                reasoning.append("Strategy: 1 elite player + solid supporting picks")
            elif tournament_importance >= 5:  # Standard
                tier_targets = {"tier1": 0, "tier2": 1, "tier3": 1, "tier4": 1}
                reasoning.append("Strategy: Save elite players - use mid-tier value")
            else:  # Opposite field
                tier_targets = {"tier1": 0, "tier2": 1, "tier3": 1, "tier4": 1}
                reasoning.append("Strategy: Value-heavy - not worth elite uses")
        else:
            # 6-player lineup distributions (DK/FD style)
            if tournament_importance >= 10:  # Majors ($4M+ winner share)
                tier_targets = {"tier1": 2, "tier2": 2, "tier3": 2, "tier4": 0}
                reasoning.append("Strategy: Load up on elite players - this is a premium event")
            elif tournament_importance >= 8:  # Signatures ($3M+ winner share)
                tier_targets = {"tier1": 1, "tier2": 2, "tier3": 2, "tier4": 1}
                reasoning.append("Strategy: Use 1 elite player, balance with value")
            elif tournament_importance >= 5:  # Standard ($1.5M+ winner share)
                tier_targets = {"tier1": 0, "tier2": 2, "tier3": 2, "tier4": 2}
                reasoning.append("Strategy: Save elite players for bigger payouts")
            else:  # Opposite field
                tier_targets = {"tier1": 0, "tier2": 1, "tier3": 2, "tier4": 3}
                reasoning.append("Strategy: Value-heavy lineup - not worth elite uses")

        # Assign tiers
        available['tier'] = available['world_rank'].apply(
            lambda x: 'tier1' if pd.notna(x) and x <= 15 else
                     'tier2' if pd.notna(x) and x <= 40 else
                     'tier3' if pd.notna(x) and x <= 80 else 'tier4'
        )

        # Note which elite players are being saved (if tier1 target is 0)
        if tier_targets.get("tier1", 0) == 0 and use_strategy:
            tier1_players = available[available['tier'] == 'tier1'].nlargest(3, 'expected_value')
            for _, player in tier1_players.iterrows():
                strategic_notes.append(
                    f"Saving {player['player_name']} (#{int(player['world_rank'])}) for bigger events - "
                    f"EV ${player['expected_value']:,.0f}"
                )

        # Get usage recommendations if optimizer available and strategy enabled
        usage_recommendations = {}
        if use_strategy and self.usage_optimizer is not None:
            top_players = available.nlargest(20, 'expected_value')['player_name'].tolist()
            for player in top_players:
                try:
                    rec = self.usage_optimizer.should_use_player(player, tournament_name)
                    usage_recommendations[player.lower()] = rec
                except Exception:
                    pass

        # Select from each tier, respecting usage strategy
        for tier, count in tier_targets.items():
            if count > 0:
                tier_players = available[available['tier'] == tier].nlargest(count * 3, 'expected_value')

                added_from_tier = 0
                for _, player in tier_players.iterrows():
                    if len(lineup) >= roster_size or added_from_tier >= count:
                        break

                    player_name = player['player_name']
                    player_key = player_name.lower()

                    # Check usage recommendation
                    usage_rec = usage_recommendations.get(player_key, {})
                    rec_action = usage_rec.get('recommendation', 'USE')
                    remaining_uses = usage_rec.get('remaining_uses', 3)

                    # Skip if player has no uses left
                    if remaining_uses == 0:
                        strategic_notes.append(f"Skipped {player_name}: no uses remaining")
                        continue

                    # For elite players (tier1), check if we should save them
                    if tier == 'tier1' and use_strategy:
                        if rec_action in ['SAVE', 'DEFINITELY SAVE']:
                            strategic_notes.append(
                                f"Skipped {player_name}: saving for bigger events "
                                f"({remaining_uses} uses left)"
                            )
                            continue
                        elif rec_action == 'CONSIDER' and remaining_uses <= 2:
                            # Only use if very high EV
                            if player['expected_value'] < available['expected_value'].quantile(0.9):
                                strategic_notes.append(
                                    f"Skipped {player_name}: only {remaining_uses} uses, saving for majors"
                                )
                                continue

                    lineup.append({
                        "name": player_name,
                        "tier": tier,
                        "ev": player['expected_value'],
                        "win_prob": player['win_prob'],
                        "top10_prob": player['top10_prob'],
                        "world_rank": player.get('world_rank'),
                        "uses_remaining": remaining_uses,
                        "usage_recommendation": rec_action,
                    })
                    available = available[available['player_name'] != player_name]
                    added_from_tier += 1

        # Fill remaining slots with highest EV (respecting usage)
        while len(lineup) < roster_size:
            if len(available) == 0:
                break

            # Sort by EV and find first usable player
            sorted_available = available.nlargest(10, 'expected_value')
            added = False

            for _, player in sorted_available.iterrows():
                player_name = player['player_name']
                player_key = player_name.lower()

                usage_rec = usage_recommendations.get(player_key, {})
                remaining_uses = usage_rec.get('remaining_uses', 3)

                if remaining_uses > 0:
                    lineup.append({
                        "name": player_name,
                        "tier": player['tier'],
                        "ev": player['expected_value'],
                        "win_prob": player['win_prob'],
                        "top10_prob": player['top10_prob'],
                        "world_rank": player.get('world_rank'),
                        "uses_remaining": remaining_uses,
                        "usage_recommendation": usage_rec.get('recommendation', 'USE'),
                    })
                    available = available[available['player_name'] != player_name]
                    added = True
                    break

            if not added:
                break

        # Calculate lineup stats
        total_ev = sum(p['ev'] for p in lineup)
        avg_top10 = np.mean([p['top10_prob'] for p in lineup]) if lineup else 0

        # Add tier distribution summary
        tier_counts = {}
        for p in lineup:
            tier_counts[p['tier']] = tier_counts.get(p['tier'], 0) + 1
        reasoning.append(f"Actual tier distribution: {tier_counts}")
        reasoning.append(f"Total Expected Value: ${total_ev:,.0f}")
        reasoning.append(f"Average Top-10 Probability: {avg_top10*100:.1f}%")

        result = {
            "tournament_name": tournament_name,
            "tournament_type": tournament_type,
            "tournament_importance": tournament_importance,
            "winner_share": winner_share,
            "strategy": t_strategy['strategy'],
            "lineup": lineup,
            "total_ev": total_ev,
            "avg_top10_prob": avg_top10,
            "reasoning": reasoning,
            "strategic_notes": strategic_notes,
        }

        if save_log:
            try:
                log_dir = OUTPUTS_DIR / "lineups"
                log_dir.mkdir(parents=True, exist_ok=True)
                date_str = datetime.now().strftime("%Y-%m-%d")
                safe_name = re.sub(r"[^a-z0-9]+", "_", tournament_name.lower()).strip("_")
                log_path = log_dir / f"lineup_log_{date_str}_{safe_name}.json"
                payload = {
                    "tournament_name": tournament_name,
                    "tournament_type": tournament_type,
                    "tournament_importance": tournament_importance,
                    "date": date_str,
                    "format": self.format,
                    "strategy": t_strategy['strategy'],
                    "constraints": {
                        "roster_size": self.format.get("roster_size"),
                        "uses_per_player": self.format.get("uses_per_player"),
                    },
                    "lineup": lineup,
                    "reasoning": reasoning,
                    "strategic_notes": strategic_notes,
                }
                with open(log_path, "w") as f:
                    json.dump(payload, f, indent=2, default=str)
            except Exception as e:
                print(f"  Could not save lineup log: {e}")
            # Also append to picks log for performance tracking
            self._append_picks_log(tournament_name, lineup, tournament_type=tournament_type)

        return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fantasy Golf AI Assistant")
    parser.add_argument("--tournament", default=None, help="Tournament name for context")
    parser.add_argument("--question", "-q", default=None, help="Ask a single question")
    parser.add_argument("--chat", action="store_true", help="Start interactive chat")
    parser.add_argument("--lineup", action="store_true", help="Get lineup recommendation")
    parser.add_argument("--examples", action="store_true", help="Show example questions")
    parser.add_argument("--tournament-type", default="standard",
                       choices=["major", "signature", "playoff", "standard", "opposite"])
    parser.add_argument("--format", default="earnings",
                       choices=["earnings"])
    parser.add_argument("--no-llm", action="store_true",
                       help="Use structured responses (recommended) - faster and more accurate than LLM")
    parser.add_argument("--no-strategy", action="store_true", help="Disable strategic usage optimization")
    parser.add_argument("--model", default="llama3.2", help="Ollama model to use")

    args = parser.parse_args()

    assistant = GolfAssistant(format_name=args.format)

    if args.lineup:
        # Get lineup recommendation with strategic usage
        result = assistant.get_lineup_recommendation(
            tournament_name=args.tournament,
            tournament_type=args.tournament_type if args.tournament_type != "standard" else None,
            use_strategy=not args.no_strategy,
            save_log=True
        )

        print("=" * 70)
        print(f"  LINEUP RECOMMENDATION: {result.get('tournament_name', 'Unknown')}")
        print("=" * 70)
        print()

        for reason in result['reasoning']:
            print(f"  {reason}")

        # Show strategic notes if any players were skipped
        if result.get('strategic_notes'):
            print()
            print("STRATEGIC NOTES:")
            for note in result['strategic_notes']:
                print(f"  - {note}")

        print()
        print("RECOMMENDED LINEUP:")
        print("-" * 70)

        for i, player in enumerate(result['lineup'], 1):
            print(f"  {i}. {player['name']}")
            rank = player.get('world_rank', 'N/A')
            rank_str = f"#{int(rank)}" if rank and rank != 'N/A' else 'N/A'
            uses = player.get('uses_remaining', '?')
            rec = player.get('usage_recommendation', '')
            print(f"     Tier: {player['tier']} | Rank: {rank_str} | Uses left: {uses}")
            print(f"     EV: ${player['ev']:,.0f} | Win: {player['win_prob']*100:.1f}% | Top-10: {player['top10_prob']*100:.1f}%")
            if rec and rec not in ['USE', 'STRONG USE']:
                print(f"     Usage note: {rec}")
            print()

    elif args.question:
        # Single question
        response = assistant.ask(
            args.question,
            tournament_name=args.tournament,
            use_ollama=not args.no_llm,
            ollama_model=args.model
        )
        print(response)

    elif args.examples:
        print(assistant._handle_help_questions())

    elif args.chat:
        # Interactive chat
        print("=" * 60)
        print("  FANTASY GOLF ASSISTANT")
        print("=" * 60)
        print(f"Format: {assistant.format['name']} ({assistant.format['roster_size']} picks/week)")
        if assistant.current_tournament:
            print(f"Tournament: {assistant.current_tournament}")
        print()
        print(assistant._handle_help_questions())
        print()
        print("Type 'quit' to exit")
        print("-" * 60)

        while True:
            try:
                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                if user_input.lower() == 'lineup':
                    result = assistant.get_lineup_recommendation(save_log=True)
                    print("\nAssistant:")
                    for player in result['lineup']:
                        print(f"  - {player['name']} (EV: ${player['ev']:,.0f})")
                    continue

                if user_input.lower().startswith('run predictions'):
                    # Run prediction script from chat
                    tokens = shlex.split(user_input)
                    if len(tokens) <= 2:
                        print("\nAssistant:")
                        print("Usage: run predictions --tournament \"Farmers Insurance Open\" --purse 9500000 --field data/fields/farmers_2026.csv --tournament-id R2026004 [--odds data/odds/pga_odds_R2026004.csv] [--sg-method last_5]")
                        continue

                    cmd_args = tokens[2:]
                    script_path = str(PROJECT_ROOT / "scripts/predictions/predict_tournament.py")
                    cmd = ["python3", script_path] + cmd_args
                    print("\nAssistant:")
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
                        if result.returncode == 0:
                            print(result.stdout.strip() or "Predictions complete.")
                            # Reload latest predictions so follow-up questions match the script output
                            latest_path = OUTPUTS_DIR / "latest_predictions.csv"
                            if latest_path.exists():
                                assistant._predictions_path = str(latest_path)
                                # If user passed a tournament name, prefer that for context
                                if "--tournament" in cmd_args:
                                    try:
                                        t_idx = cmd_args.index("--tournament")
                                        if t_idx + 1 < len(cmd_args):
                                            assistant.current_tournament = cmd_args[t_idx + 1]
                                    except ValueError:
                                        pass
                                assistant._load_data()
                        else:
                            print(f"Prediction run failed (code {result.returncode}).")
                            if result.stdout:
                                print(result.stdout.strip())
                            if result.stderr:
                                print(result.stderr.strip())
                    except Exception as e:
                        print(f"Error running predictions: {e}")
                    continue

                if user_input.lower().startswith('player '):
                    player_name = user_input[7:].strip()
                    analysis = assistant.get_player_analysis(player_name)
                    print("\nAssistant:")
                    print(json.dumps(analysis, indent=2, default=str))
                    continue

                # Regular question
                print("\nAssistant: ", end="")
                response = assistant.ask(
                    user_input,
                    tournament_name=args.tournament,
                    use_ollama=not args.no_llm,
                    ollama_model=args.model
                )
                print(response)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
