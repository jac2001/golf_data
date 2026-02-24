#!/usr/bin/env python3
"""
Scoring Engine for Fantasy Golf - Season 2026

Combines multiple factors to score player-tournament combinations:
- Tournament Importance (25%): Purse, prestige, major status
- Course Fit (35%): Historical performance at venue
- Current Form (25%): Recent results, predictions, hot hand
- Field Strength (15%): Weaker field = easier path

Usage:
    # Score players for a specific tournament
    python scoring_engine.py --tournament "Waste Management Phoenix Open"

    # Score a specific player across upcoming tournaments
    python scoring_engine.py --player "Scottie Scheffler"

    # Find best value picks (rank 20-60 with good scores)
    python scoring_engine.py --value

    # Show top recommendations for this week
    python scoring_engine.py --this-week
"""

import csv
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from datetime import datetime

# Import our modules
from course_history import CourseHistoryDB


# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"
TOURNAMENT_COURSES_FILE = DATA_DIR / "reference" / "tournament_courses.json"
USAGE_TRACKER_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
CALIBRATION_FILE = DATA_DIR / "prediction_tracking" / "calibration_factors.json"

# Default weights (should sum to 1.0)
# Updated 2026-02-23: ML model win_prob now primary driver (merged systems)
DEFAULT_WEIGHTS = {
    'ml_prediction': 0.50,  # ML model win probability rank (primary signal)
    'course_fit':    0.20,  # Historical course performance
    'importance':    0.15,  # Tournament importance / purse
    'field':         0.10,  # Field strength (inverse)
    'form':          0.05,  # Momentum/trend boost
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TournamentInfo:
    """Information about a tournament."""
    name: str
    week: int
    start_date: str
    tournament_type: str  # Major, Signature, Standard, Playoff, Team
    location: str
    purse: float
    course: str = ""
    course_type: str = ""
    importance_score: float = 0.0


@dataclass
class PlayerForm:
    """Current form data for a player."""
    player_name: str
    owgr_rank: int = 999
    win_prob: float = 0.0
    top5_prob: float = 0.0
    top10_prob: float = 0.0
    form_trend: str = "NEUTRAL"  # COLD, NEUTRAL, WARM, HOT
    hot_hand_score: float = 0.0
    model_edge: float = 0.0  # model vs vegas edge


@dataclass
class TournamentScore:
    """Complete scoring for a player at a tournament."""
    player: str
    tournament: str

    # Component scores (0-100 each)
    tournament_importance: float = 0.0
    course_fit: float = 0.0
    current_form: float = 0.0
    field_strength: float = 0.0
    ml_prediction: float = 50.0  # ML model win_prob percentile rank (0-100)

    # Context
    owgr_rank: int = 999
    remaining_uses: int = 3
    course_history_note: str = ""
    form_trend: str = "NEUTRAL"
    win_prob: float = 0.0        # Raw ML win probability (for display)
    expected_value: float = 0.0  # Raw ML expected value (for display)

    # Weights
    weights: Dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())

    @property
    def total_score(self) -> float:
        return (
            self.ml_prediction       * self.weights.get('ml_prediction', 0.50) +
            self.tournament_importance * self.weights.get('importance', 0.15) +
            self.course_fit          * self.weights.get('course_fit', 0.20) +
            self.current_form        * self.weights.get('form', 0.05) +
            self.field_strength      * self.weights.get('field', 0.10)
        )

    @property
    def value_rating(self) -> str:
        """Human-readable rating."""
        score = self.total_score
        if score >= 80:
            return "ELITE"
        if score >= 65:
            return "STRONG"
        if score >= 50:
            return "SOLID"
        if score >= 35:
            return "FAIR"
        return "FADE"

    @property
    def usage_warning(self) -> str:
        """Warning if using elite player at lesser event."""
        if self.remaining_uses == 1:
            return "⚠️ LAST USE"
        if self.remaining_uses == 0:
            return "❌ NO USES LEFT"
        if self.owgr_rank <= 10 and self.tournament_importance < 60:
            return "💡 Save for bigger event?"
        return ""


# ============================================================================
# SCORING ENGINE
# ============================================================================

class ScoringEngine:
    """Engine for scoring player-tournament combinations."""

    def __init__(self, weights: Dict[str, float] = None, tournament: str = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.tournaments: Dict[str, TournamentInfo] = {}
        self.predictions: Dict[str, PlayerForm] = {}
        self.usage: Dict[str, int] = {}  # player -> remaining uses
        self.course_db: Optional[CourseHistoryDB] = None
        self.tournament_courses: Dict[str, dict] = {}
        self.target_tournament = tournament
        self.ml_scores: Dict[str, float] = {}  # player -> ML percentile score (0-100)

        self._load_data()

    def _load_data(self):
        """Load all data sources."""
        self._load_schedule()
        self._load_tournament_courses()
        self._load_predictions()
        self._load_usage()
        self._load_course_history()
        self._compute_ml_scores()

    def _normalize_name(self, name: str) -> str:
        """Normalize 'Last, First' to 'First Last' format."""
        if not name:
            return name
        name = name.strip().strip('"')
        if "," in name:
            parts = name.split(",", 1)
            if len(parts) == 2:
                return f"{parts[1].strip()} {parts[0].strip()}"
        return name

    def _load_schedule(self):
        """Load tournament schedule."""
        if not SCHEDULE_FILE.exists():
            print(f"Warning: Schedule not found at {SCHEDULE_FILE}")
            return

        with open(SCHEDULE_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                purse_str = row['purse'].replace('$', '').replace(',', '')
                purse = float(purse_str) if purse_str else 0

                tournament = TournamentInfo(
                    name=row['tournament_name'],
                    week=int(row['week']),
                    start_date=row['start_date'],
                    tournament_type=row['tournament_type'],
                    location=row['location'],
                    purse=purse
                )

                # Calculate importance score
                tournament.importance_score = self._calculate_importance(tournament)
                self.tournaments[tournament.name] = tournament

    def _load_tournament_courses(self):
        """Load tournament-to-course mappings."""
        if not TOURNAMENT_COURSES_FILE.exists():
            print(f"Warning: Tournament courses not found at {TOURNAMENT_COURSES_FILE}")
            return

        with open(TOURNAMENT_COURSES_FILE, 'r') as f:
            data = json.load(f)
            self.tournament_courses = data.get('tournaments', {})

        # Update tournament info with course data
        for name, info in self.tournament_courses.items():
            if name in self.tournaments:
                self.tournaments[name].course = info.get('course', '')
                self.tournaments[name].course_type = info.get('course_type', '')

    def _load_predictions(self):
        """Load current predictions/form data from outputs folder."""
        if not OUTPUTS_DIR.exists():
            print(f"Warning: Outputs directory not found at {OUTPUTS_DIR}")
            return

        # Find prediction files
        prediction_files = list(OUTPUTS_DIR.glob("*_predictions.csv"))

        if not prediction_files:
            print(f"Warning: No prediction files found in {OUTPUTS_DIR}")
            return

        # Sort by modification time, most recent first
        prediction_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # If tournament specified, try to find matching file
        predictions_file = prediction_files[0]  # default to most recent

        if self.target_tournament:
            tournament_slug = self.target_tournament.lower().replace(" ", "_").replace("'", "").replace("-", "_")
            for f in prediction_files:
                if tournament_slug in f.name.lower() or any(word in f.name.lower() for word in tournament_slug.split("_")[:2]):
                    predictions_file = f
                    break

        print(f"  Loading predictions from: {predictions_file.name}")

        with open(predictions_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Normalize player name from "Last, First" to "First Last"
                    raw_name = row.get('player_name', row.get('player', ''))
                    player_name = self._normalize_name(raw_name)

                    # Parse form trend - handle numeric values
                    form_trend_raw = row.get('form_trend', 'NEUTRAL')
                    if form_trend_raw in ['0.0', '0', '', None, '0.0']:
                        form_trend = 'NEUTRAL'
                    elif isinstance(form_trend_raw, str) and form_trend_raw.upper() in ['HOT', 'WARM', 'NEUTRAL', 'COLD']:
                        form_trend = form_trend_raw.upper()
                    else:
                        try:
                            trend_val = float(form_trend_raw)
                            if trend_val > 0.5:
                                form_trend = 'HOT'
                            elif trend_val > 0:
                                form_trend = 'WARM'
                            elif trend_val < -0.5:
                                form_trend = 'COLD'
                            else:
                                form_trend = 'NEUTRAL'
                        except (ValueError, TypeError):
                            form_trend = 'NEUTRAL'

                    form = PlayerForm(
                        player_name=player_name,
                        owgr_rank=int(float(row.get('world_rank', row.get('owgr_rank', 999)) or 999)),
                        win_prob=float(row.get('win_prob', 0) or 0),
                        top5_prob=float(row.get('top5_prob', row.get('top_5_prob', 0)) or 0),
                        top10_prob=float(row.get('top10_prob', row.get('top_10_prob', 0)) or 0),
                        form_trend=form_trend,
                        hot_hand_score=float(row.get('hot_hand_score', 0) or 0),
                        model_edge=float(row.get('expected_value', row.get('model_vs_vegas_edge', 0)) or 0)
                    )
                    self.predictions[player_name] = form
                except (ValueError, KeyError) as e:
                    continue
                
        print(f"  Loaded {len(self.predictions)} players from predictions")
        calibration = self._load_calibration_factors()
        if calibration:
            for player_name, form in self.predictions.items():
                self.predictions[player_name] = self._apply_calibration(form, calibration)
            print(f"  Applied calibration factors to predictions")

    def _load_usage(self):
        """Load usage tracker data."""
        if not USAGE_TRACKER_FILE.exists():
            return

        with open(USAGE_TRACKER_FILE, 'r') as f:
            data = json.load(f)

        for player, info in data.get('picks', {}).items():
            self.usage[player] = info.get('remaining_uses', 3)

    def _load_course_history(self):
        """Load course history database."""
        self.course_db = CourseHistoryDB()
        count = self.course_db.load_from_betting_profiles()
        print(f"  Loaded course history for {len(self.course_db.history)} players")



    def _load_calibration_factors(self)-> Dict: 
        """Load calibration factors for probability adjustment."""
        if not CALIBRATION_FILE.exists():
            return {}
        with open(CALIBRATION_FILE, 'r') as f:
            return json.load(f)
    def _apply_calibration(self, form: PlayerForm, calibration: Dict) -> PlayerForm:                                  
        """Apply calibration factors to reduce overconfident probabilities."""                                        
        global_cal = calibration.get('global', {})                                                                    
                                                                                                                    
        # Apply scale factors (model is ~2x overconfident)                                                            
        if 'win_prob' in global_cal:                                                                                  
            form.win_prob *= global_cal['win_prob'].get('scale_factor', 1.0)                                          
        if 'top5_prob' in global_cal:                                                                                 
            form.top5_prob *= global_cal['top5_prob'].get('scale_factor', 1.0)                                        
        if 'top10_prob' in global_cal:                                                                                
            form.top10_prob *= global_cal['top10_prob'].get('scale_factor', 1.0)                                      
                                                                                                                    
        return form 
        
        
        
    
    



    def _compute_ml_scores(self):
        """
        Normalize ML model win_prob across the field to a 0-100 percentile score.
        The player with the highest win_prob gets 100, lowest gets 0.
        This becomes the primary ranking signal in total_score.
        """
        if not self.predictions:
            return

        players = list(self.predictions.keys())
        win_probs = [self.predictions[p].win_prob for p in players]

        min_wp = min(win_probs) if win_probs else 0
        max_wp = max(win_probs) if win_probs else 1
        rng = max_wp - min_wp

        for player, wp in zip(players, win_probs):
            if rng > 0:
                self.ml_scores[player] = round((wp - min_wp) / rng * 100, 2)
            else:
                self.ml_scores[player] = 50.0

    def _calculate_importance(self, tournament: TournamentInfo) -> float:
        """Calculate tournament importance score (0-100)."""
        score = 0.0

        # Type-based scoring
        type_scores = {
            'Major': 40,
            'Playoff': 35,
            'Signature': 25,
            'Standard': 10,
            'Team': 5
        }
        score += type_scores.get(tournament.tournament_type, 10)

        # Purse-based scoring (0-30 points)
        # $25M = 30 pts, $8M = 10 pts
        purse_millions = tournament.purse / 1_000_000
        purse_score = min(30, max(0, (purse_millions - 8) * (30 / 17)))
        score += purse_score

        # Specific tournament bonuses
        prestige_bonuses = {
            'The Masters': 15,
            'U.S. Open': 15,
            'The Open Championship': 15,
            'PGA Championship': 15,
            'THE PLAYERS Championship': 12,
            'The Memorial Tournament': 8,
            'Arnold Palmer Invitational': 8,
            'The Genesis Invitational': 8,
            'TOUR Championship': 10
        }
        score += prestige_bonuses.get(tournament.name, 0)

        return min(100, score)

    def _calculate_form_score(self, player: str) -> Tuple[float, str]:                                                
        """                                                                                                           
        Calculate current form score (0-100) and trend.                                                               
        Uses dynamic form windows based on player consistency/tier.                                                   
        """                                                                                                           
        if player not in self.predictions:                                                                            
            return 50.0, "NEUTRAL"  # Default for unknown players                                                     
                                                                                                                    
        form = self.predictions[player]                                                                               
        score = 0.0                                                                                                   
                                                                                                                    
        # === Dynamic form weighting based on player tier ===                                                         
        # Top players = more stable, use longer window (reflected in lower rank bonus)                                
        # Lower ranked players = more volatile, recent form matters more                                              
        rank = form.owgr_rank                                                                                         
                                                                                                                    
        # OWGR rank component (0-35 points)                                                                           
        # Adjusted: Top 10 players get slightly less rank bonus                                                       
        # because we want to weight their recent form more equally                                                    
        if rank <= 10:                                                                                                
            rank_score = 30 + (11 - rank) * 0.5  # 30-35 for top 10                                                   
            form_multiplier = 1.0  # Standard form weight                                                             
        elif rank <= 30:                                                                                              
            rank_score = 20 + (31 - rank) * 0.5  # 20-30 for ranks 11-30                                              
            form_multiplier = 1.1  # Slightly boost form importance                                                   
        elif rank <= 60:                                                                                              
            rank_score = 10 + (61 - rank) * 0.33  # 10-20 for ranks 31-60                                             
            form_multiplier = 1.2  # Form matters more for mid-tier                                                   
        else:                                                                                                         
            rank_score = max(0, 10 - (rank - 60) * 0.1)  # 0-10 for ranks 61+                                         
            form_multiplier = 1.4  # Recent form is critical for lower ranked                                         
                                                                                                                    
        score += rank_score                                                                                           
                                                                                                                    
        # Win probability (0-25 points) - already calibrated                                                          
        win_score = min(25, form.win_prob * 125)                                                                      
        score += win_score                                                                                            
                                                                                                                    
        # Form trend (0-20 points) - apply dynamic multiplier                                                         
        trend_scores = {'HOT': 20, 'WARM': 12, 'NEUTRAL': 6, 'COLD': 0}                                               
        base_trend_score = trend_scores.get(form.form_trend, 6)                                                       
        score += base_trend_score * form_multiplier                                                                   
                                                                                                                    
        # Hot hand momentum (0-10 points) - boost for lower ranked players                                            
        hot_hand = min(10, form.hot_hand_score * 10 * form_multiplier)                                                
        score += hot_hand                                                                                             
                                                                                                                    
        # Model edge component (0-15 points with penalties)                                                           
        if form.model_edge > 0.05:  # 5%+ edge = strong value                                                         
            edge_score = min(15, form.model_edge * 150)                                                               
        elif form.model_edge > 0:  # Small positive edge                                                              
            edge_score = min(10, form.model_edge * 100)                                                               
        elif form.model_edge < -0.05:  # Vegas significantly lower = fade                                             
            edge_score = -5  # Penalty for overvalued by model                                                        
        else:                                                                                                         
            edge_score = 0                                                                                            
        score += edge_score                                                                                           
                                                                                                                    
        return min(100, max(0, score)), form.form_trend 






    def _calculate_field_strength(self, tournament: str) -> float:                                                    
        """                                                                                                           
        Calculate inverse field strength (0-100).                                                                     
        Higher score = weaker field = easier path.                                                                    
        Uses actual field average rank when available.                                                                
        """                                                                                                           
        if tournament not in self.tournaments:                                                                        
            return 50.0                                                                                               
                                                                                                                    
        t = self.tournaments[tournament]                                                                              
                                                                                                                    
        # Base scores by tournament type                                                                              
        type_field = {                                                                                                
            'Major': 10,      # Strongest fields                                                                      
            'Signature': 20,                                                                                          
            'Playoff': 15,                                                                                            
            'Standard': 60,   # Weaker fields                                                                         
            'Team': 70                                                                                                
        }                                                                                                             
        base = type_field.get(t.tournament_type, 50)                                                                  
                                                                                                                    
        # Dynamic adjustment based on actual field strength                                                           
        # Calculate average OWGR of players in predictions (proxy for field)                                          
        if self.predictions:                                                                                          
            ranks = [p.owgr_rank for p in self.predictions.values() if p.owgr_rank < 500]                             
            if ranks:                                                                                                 
                avg_rank = sum(ranks) / len(ranks)                                                                    
                # Adjust based on field quality                                                                       
                # avg_rank 30 = elite field, subtract 15                                                              
                # avg_rank 60 = typical field, no change                                                              
                # avg_rank 90 = weak field, add 15                                                                    
                field_adjustment = (avg_rank - 60) / 2  # -15 to +15 range                                            
                base = max(5, min(85, base + field_adjustment))                                                       
                                                                                                                    
        return base











    def get_remaining_uses(self, player: str) -> int:
        """Get remaining uses for a player."""
        return self.usage.get(player, 3)

    def score_player_tournament(self, player: str, tournament: str) -> TournamentScore:
        """Generate complete score for a player at a tournament."""
        score = TournamentScore(
            player=player,
            tournament=tournament,
            weights=self.weights.copy()
        )

        # Tournament importance
        if tournament in self.tournaments:
            score.tournament_importance = self.tournaments[tournament].importance_score

        # Course fit
        if self.course_db and tournament in self.tournament_courses:
            course_info = self.tournament_courses[tournament]
            aliases = course_info.get('aliases', [])

            # Try each alias to find course history
            for alias in aliases:
                stats = self.course_db.get_player_course_stats(player, alias)
                if stats and stats.times_played > 0:
                    score.course_fit = self.course_db.calculate_course_fit_score(stats)
                    # Build history note
                    notes = []
                    if stats.wins > 0:
                        notes.append(f"{stats.wins}W")
                    if stats.top_5s > 0:
                        notes.append(f"{stats.top_5s} T5s")
                    notes.append(f"{stats.times_played} plays")
                    score.course_history_note = ", ".join(notes)
                    break
            else:
                score.course_fit = 40.0  # Default for no history
                score.course_history_note = "No history"

        # Current form
        form_score, trend = self._calculate_form_score(player)
        score.current_form = form_score
        score.form_trend = trend

        # Field strength
        score.field_strength = self._calculate_field_strength(tournament)

        # ML model prediction (primary signal)
        score.ml_prediction = self.ml_scores.get(player, 50.0)

        # Context
        if player in self.predictions:
            form = self.predictions[player]
            score.owgr_rank = form.owgr_rank
            score.win_prob = form.win_prob
            score.expected_value = form.model_edge  # stored as expected_value $
        score.remaining_uses = self.get_remaining_uses(player)

        return score

    def get_tournament_recommendations(self, tournament: str,
                                        top_n: int = 15,
                                        min_uses: int = 1) -> List[TournamentScore]:
        """Get top player recommendations for a tournament."""
        scores = []

        # Only score players in predictions (they're the tournament field)
        for player in self.predictions.keys():
            remaining = self.get_remaining_uses(player)
            if remaining < min_uses:
                continue

            score = self.score_player_tournament(player, tournament)
            scores.append(score)

        # Sort by total score
        scores.sort(key=lambda x: x.total_score, reverse=True)

        return scores[:top_n]

    def get_value_picks(self, tournament: str,
                        rank_min: int = 20,
                        rank_max: int = 60,
                        min_score: float = 45) -> List[TournamentScore]:
        """Find value picks - lower ranked players with good scores."""
        scores = []

        for player, form in self.predictions.items():
            if not (rank_min <= form.owgr_rank <= rank_max):
                continue

            remaining = self.get_remaining_uses(player)
            if remaining < 1:
                continue

            score = self.score_player_tournament(player, tournament)
            if score.total_score >= min_score:
                scores.append(score)

        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores

    def get_player_best_tournaments(self, player: str,
                                     upcoming_only: bool = True,
                                     top_n: int = 10) -> List[TournamentScore]:
        """Find best tournaments for a specific player."""
        scores = []
        today = datetime.now().strftime('%Y-%m-%d')

        for tournament_name, tournament in self.tournaments.items():
            if upcoming_only and tournament.start_date < today:
                continue

            score = self.score_player_tournament(player, tournament_name)
            scores.append(score)

        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores[:top_n]

    def get_current_week_tournament(self) -> Optional[str]:
        """Get the tournament for the current week."""
        today = datetime.now().strftime('%Y-%m-%d')

        for name, t in self.tournaments.items():
            # Check if today falls within tournament week (start to start+3 days)
            if t.start_date <= today:
                try:
                    end_day = int(t.start_date[8:10]) + 3
                    end_date = t.start_date[:8] + str(end_day).zfill(2)
                    if today <= end_date:
                        return name
                except:
                    pass

        # Find next upcoming
        upcoming = [(name, t) for name, t in self.tournaments.items() if t.start_date >= today]
        if upcoming:
            upcoming.sort(key=lambda x: x[1].start_date)
            return upcoming[0][0]

        return None

    def get_player_usage_details(self, player: str) -> dict:
        """
        Get detailed usage information for a player from the usage tracker.

        Returns:
            dict with keys: times_used, remaining_uses, tournaments_used, total_points
        """
        if not USAGE_TRACKER_FILE.exists():
            return {
                "times_used": 0,
                "remaining_uses": 3,
                "tournaments_used": [],
                "total_points": 0
            }

        with open(USAGE_TRACKER_FILE, 'r') as f:
            data = json.load(f)

        # Try exact match first
        if player in data.get("picks", {}):
            return data["picks"][player]

        # Try normalized name match
        player_lower = player.lower().strip()
        for name, info in data.get("picks", {}).items():
            if name.lower().strip().rstrip(',') == player_lower:
                return info

        # Not found - player hasn't been used
        return {
            "times_used": 0,
            "remaining_uses": 3,
            "tournaments_used": [],
            "total_points": 0
        }

    def get_optimized_recommendations(self, player: str, top_n: int = 10) -> Tuple[dict, List[dict]]:
        """
        Get optimized tournament recommendations for a player's remaining uses.

        Considers:
        - Tournament importance (majors/signatures prioritized)
        - Course fit
        - Strategic value of each use

        Returns:
            Tuple of (usage_details, list of recommendation dicts)
        """
        usage = self.get_player_usage_details(player)
        remaining = usage.get("remaining_uses", 3)

        if remaining <= 0:
            return usage, []

        # Get all upcoming tournaments with scores
        today = datetime.now().strftime('%Y-%m-%d')
        recommendations = []

        for tournament_name, tournament in self.tournaments.items():
            if tournament.start_date < today:
                continue

            # Check if already used at this tournament
            already_used = any(
                t.get("tournament") == tournament_name
                for t in usage.get("tournaments_used", [])
            )
            if already_used:
                continue

            score = self.score_player_tournament(player, tournament_name)

            # Calculate strategic value based on remaining uses
            strategic_notes = []
            use_priority = "RECOMMENDED"

            if remaining == 1:
                # Last use - be very selective
                if tournament.importance_score >= 70:
                    strategic_notes.append("Major/Top Signature - IDEAL for last use")
                    use_priority = "IDEAL"
                elif tournament.importance_score >= 50:
                    strategic_notes.append("Good event for last use")
                    use_priority = "GOOD"
                elif tournament.importance_score >= 30:
                    strategic_notes.append("Consider saving for bigger event")
                    use_priority = "CONSIDER"
                else:
                    strategic_notes.append("Save for a major/signature!")
                    use_priority = "AVOID"

            elif remaining == 2:
                # Two uses left - moderate selectivity
                if tournament.importance_score >= 60:
                    strategic_notes.append("Strong event - good use")
                    use_priority = "IDEAL"
                elif tournament.importance_score >= 40:
                    strategic_notes.append("Decent event")
                    use_priority = "GOOD"
                else:
                    strategic_notes.append("Consider bigger events")
                    use_priority = "CONSIDER"

            else:
                # 3 uses - can be more flexible
                if tournament.importance_score >= 50:
                    strategic_notes.append("Premium event")
                    use_priority = "IDEAL"
                elif score.course_fit >= 80:
                    strategic_notes.append("Strong course fit")
                    use_priority = "GOOD"
                else:
                    use_priority = "OPTIONAL"

            # Add course fit note
            if score.course_fit >= 90:
                strategic_notes.append(f"Elite course fit ({score.course_history_note})")
            elif score.course_fit >= 70:
                strategic_notes.append(f"Good course history ({score.course_history_note})")

            recommendations.append({
                "tournament": tournament_name,
                "date": tournament.start_date,
                "week": tournament.week,
                "type": tournament.tournament_type,
                "importance": tournament.importance_score,
                "course_fit": score.course_fit,
                "total_score": score.total_score,
                "course_note": score.course_history_note,
                "strategic_notes": strategic_notes,
                "use_priority": use_priority
            })

        # Sort by strategic priority, then by total score
        priority_order = {"IDEAL": 0, "GOOD": 1, "RECOMMENDED": 2, "CONSIDER": 3, "OPTIONAL": 4, "AVOID": 5}
        recommendations.sort(key=lambda x: (priority_order.get(x["use_priority"], 5), -x["total_score"]))

        return usage, recommendations[:top_n]


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def print_tournament_recommendations(engine: ScoringEngine, tournament: str, top_n: int = 15):
    """Print recommendations for a tournament."""
    if tournament not in engine.tournaments:
        print(f"Tournament not found: {tournament}")
        return

    t = engine.tournaments[tournament]
    recommendations = engine.get_tournament_recommendations(tournament, top_n=top_n)

    print(f"\n{'='*90}")
    print(f"  WHO TO USE AT: {tournament.upper()}")
    print(f"  Week {t.week} | {t.start_date} | {t.course or t.location} | ${t.purse/1e6:.1f}M purse")
    print(f"  Tournament Importance: {t.importance_score:.0f}/100 ({t.tournament_type})")
    print(f"{'='*90}")

    print(f"\n  {'#':<3} {'Player':<24} {'Score':>6} {'Rating':<7} {'Win%':>6} {'Course':>7} {'Form':>6} {'Trend':<8} {'Uses':<10} Notes")
    print(f"  {'-'*110}")

    for i, score in enumerate(recommendations, 1):
        warning = score.usage_warning
        uses_str = f"{score.remaining_uses}/3"
        if warning:
            uses_str = f"{uses_str} {warning}"

        print(f"  {i:<3} {score.player:<24} {score.total_score:>5.0f}  {score.value_rating:<7} "
              f"{score.win_prob*100:>5.1f}%  {score.course_fit:>6.0f}  {score.current_form:>5.0f}  {score.form_trend:<8} "
              f"{uses_str:<15} {score.course_history_note}")

    # Value picks section - lower threshold for weaker events
    min_value_score = 45 if t.importance_score >= 40 else 35
    print(f"\n  VALUE PICKS (Rank 20-60 with score >= {min_value_score}):")
    print(f"  {'-'*70}")
    value_picks = engine.get_value_picks(tournament, min_score=min_value_score)
    if value_picks:
        for score in value_picks[:5]:
            print(f"    #{score.owgr_rank:<3} {score.player:<24} Score: {score.total_score:.0f}  "
                  f"Form: {score.form_trend:<8} ({score.course_history_note})")
    else:
        print(f"    No value picks meeting criteria")


def print_player_outlook(engine: ScoringEngine, player: str):
    """Print best tournaments for a player."""
    tournaments = engine.get_player_best_tournaments(player)
    remaining = engine.get_remaining_uses(player)

    print(f"\n{'='*80}")
    print(f"  TOURNAMENT OUTLOOK: {player.upper()}")
    print(f"  Remaining Uses: {remaining}/3")
    print(f"{'='*80}")

    if not tournaments:
        print(f"\n  No upcoming tournaments found.")
        return

    print(f"\n  {'#':<3} {'Tournament':<35} {'Date':<12} {'Score':>6} {'Rating':<7} {'Course':>7} {'Form':>6}")
    print(f"  {'-'*85}")

    for i, score in enumerate(tournaments, 1):
        t = engine.tournaments.get(score.tournament)
        date = t.start_date if t else "?"
        print(f"  {i:<3} {score.tournament:<35} {date:<12} {score.total_score:>5.0f}  "
              f"{score.value_rating:<7} {score.course_fit:>6.0f}  {score.current_form:>5.0f}")


def print_this_week(engine: ScoringEngine):
    """Print recommendations for current week."""
    tournament = engine.get_current_week_tournament()
    if tournament:
        print_tournament_recommendations(engine, tournament)
    else:
        print("No current tournament found.")


def print_strategy_dashboard(engine: ScoringEngine):
    """Print unified strategy dashboard with all key information."""
    today = datetime.now().strftime('%Y-%m-%d')

    print(f"\n{'='*90}")
    print(f"  ⛳ FANTASY GOLF STRATEGY DASHBOARD - 2026 SEASON")
    print(f"  Generated: {today}")
    print(f"{'='*90}")

    # === THIS WEEK ===
    tournament = engine.get_current_week_tournament()
    if tournament and tournament in engine.tournaments:
        t = engine.tournaments[tournament]
        print(f"\n  📅 THIS WEEK: {tournament}")
        print(f"  Week {t.week} | {t.start_date} | {t.course or t.location} | ${t.purse/1e6:.1f}M | {t.tournament_type}")
        print(f"  {'-'*80}")

        # Top 5 picks
        recommendations = engine.get_tournament_recommendations(tournament, top_n=5)
        print(f"\n  TOP PICKS:")
        for i, score in enumerate(recommendations, 1):
            uses = f"{score.remaining_uses}/3"
            warning = ""
            if score.owgr_rank <= 10 and t.importance_score < 50:
                warning = " 💡"
            print(f"    {i}. {score.player:<22} Score: {score.total_score:.0f}  "
                  f"Course: {score.course_fit:.0f}  Uses: {uses}{warning}")

        # Value picks
        min_score = 35 if t.importance_score < 40 else 45
        value_picks = engine.get_value_picks(tournament, min_score=min_score)
        if value_picks:
            print(f"\n  VALUE PLAYS (Rank 20-60):")
            for score in value_picks[:3]:
                print(f"    • #{score.owgr_rank} {score.player:<20} Score: {score.total_score:.0f}  "
                      f"({score.course_history_note})")

    # === USAGE STATUS ===
    print(f"\n  {'─'*80}")
    print(f"  📊 USAGE STATUS")
    print(f"  {'-'*80}")

    if USAGE_TRACKER_FILE.exists():
        with open(USAGE_TRACKER_FILE, 'r') as f:
            usage_data = json.load(f)

        picks = usage_data.get("picks", {})
        if picks:
            # Group by remaining
            exhausted = []
            last_use = []
            available = []

            for player, info in picks.items():
                remaining = info.get("remaining_uses", 3)
                if remaining == 0:
                    exhausted.append(player)
                elif remaining == 1:
                    last_use.append(player)
                else:
                    available.append(player)

            if exhausted:
                print(f"    ❌ Exhausted: {', '.join(exhausted)}")
            if last_use:
                print(f"    ⚠️  Last Use: {', '.join(last_use)}")
            if available:
                print(f"    ✓  Available: {', '.join(available)} ({len(available)} players, 2 uses each)")

            # Summary
            total_picks = sum(p.get("times_used", 0) for p in picks.values())
            total_points = sum(p.get("total_points", 0) for p in picks.values())
            print(f"\n    Season: {total_picks} picks made | {total_points} points earned")
        else:
            print(f"    No picks recorded yet this season.")
    else:
        print(f"    No usage tracker found.")

    # === UPCOMING KEY EVENTS ===
    print(f"\n  {'─'*80}")
    print(f"  🗓️  UPCOMING KEY EVENTS")
    print(f"  {'-'*80}")

    upcoming = []
    for name, t in engine.tournaments.items():
        if t.start_date >= today and t.importance_score >= 40:
            upcoming.append((name, t))

    upcoming.sort(key=lambda x: x[1].start_date)
    for name, t in upcoming[:6]:
        type_icon = "⭐" if t.tournament_type == "Major" else "★" if t.tournament_type == "Signature" else "🏆"
        print(f"    {type_icon} Week {t.week:>2}: {name:<40} {t.tournament_type}")

    # === PLAYERS TO WATCH ===
    print(f"\n  {'─'*80}")
    print(f"  👀 PLAYERS TO WATCH (Best upcoming course fits)")
    print(f"  {'-'*80}")

    # Find players with elite course fits at upcoming events
    player_opportunities = {}
    for tourney_name, tourney in engine.tournaments.items():
        if tourney.start_date < today:
            continue
        if tourney.importance_score < 40:
            continue

        # Check top players for course fit
        for player in list(engine.predictions.keys())[:50]:
            score = engine.score_player_tournament(player, tourney_name)
            if score.course_fit >= 80:
                if player not in player_opportunities:
                    player_opportunities[player] = []
                player_opportunities[player].append({
                    "tournament": tourney_name,
                    "week": tourney.week,
                    "fit": score.course_fit,
                    "note": score.course_history_note
                })

    # Sort by number of opportunities and show top ones
    sorted_players = sorted(player_opportunities.items(),
                           key=lambda x: max(o["fit"] for o in x[1]), reverse=True)

    for player, opps in sorted_players[:5]:
        best = max(opps, key=lambda x: x["fit"])
        remaining = engine.get_remaining_uses(player)
        print(f"    {player:<24} Week {best['week']:>2}: {best['tournament'][:30]:<30} "
              f"Fit: {best['fit']:.0f} ({remaining}/3 uses)")

    # === STRATEGY TIPS ===
    print(f"\n  {'─'*80}")
    print(f"  💡 STRATEGY TIPS")
    print(f"  {'-'*80}")

    if tournament and tournament in engine.tournaments:
        t = engine.tournaments[tournament]
        if t.tournament_type == "Standard":
            print(f"    • Standard event - good week to use value picks")
            print(f"    • Save elite players (top 10) for majors/signatures")
        elif t.tournament_type == "Major":
            print(f"    • MAJOR WEEK - consider using your best remaining players")
            print(f"    • Course history is critical at majors")
        elif t.tournament_type == "Signature":
            print(f"    • Signature event - strong field, good points opportunity")

    # Count upcoming majors
    majors_left = sum(1 for name, t in engine.tournaments.items()
                      if t.start_date >= today and t.tournament_type == "Major")
    print(f"    • {majors_left} majors remaining this season")

    print(f"\n{'='*90}\n")


def print_usage_optimizer(engine: ScoringEngine, player: str):
    """Print optimized usage recommendations for a player."""
    usage, recommendations = engine.get_optimized_recommendations(player, top_n=15)

    remaining = usage.get("remaining_uses", 3)
    times_used = usage.get("times_used", 0)
    tournaments_used = usage.get("tournaments_used", [])
    total_points = usage.get("total_points", 0)

    print(f"\n{'='*90}")
    print(f"  USAGE OPTIMIZER: {player.upper()}")
    print(f"  Uses: {times_used}/3 | Remaining: {remaining} | Points Earned: {total_points}")
    print(f"{'='*90}")

    # Show where already used
    if tournaments_used:
        print(f"\n  ALREADY USED AT:")
        print(f"  {'-'*70}")
        for t in tournaments_used:
            result = t.get("result", "In Progress")
            points = t.get("points", "-")
            week = t.get("week", "?")
            print(f"    Week {week}: {t.get('tournament', 'Unknown'):<40} {result:<10} {points} pts")
    else:
        print(f"\n  Not yet used this season.")

    if remaining <= 0:
        print(f"\n  ❌ NO USES REMAINING - Player fully utilized for 2026 season")
        return

    # Show recommendations
    print(f"\n  BEST OPTIONS FOR {'FINAL USE' if remaining == 1 else f'REMAINING {remaining} USES'}:")
    print(f"  {'-'*85}")

    # Group by priority
    priority_groups = {}
    for rec in recommendations:
        priority = rec["use_priority"]
        if priority not in priority_groups:
            priority_groups[priority] = []
        priority_groups[priority].append(rec)

    priority_order = ["IDEAL", "GOOD", "RECOMMENDED", "CONSIDER", "OPTIONAL", "AVOID"]
    priority_labels = {
        "IDEAL": "🎯 IDEAL USES",
        "GOOD": "✓ GOOD OPTIONS",
        "RECOMMENDED": "📋 RECOMMENDED",
        "CONSIDER": "🤔 CONSIDER",
        "OPTIONAL": "📝 OPTIONAL",
        "AVOID": "⚠️ NOT RECOMMENDED"
    }

    shown = 0
    max_show = 12

    for priority in priority_order:
        if priority not in priority_groups or shown >= max_show:
            continue

        recs = priority_groups[priority]
        if not recs:
            continue

        print(f"\n  {priority_labels.get(priority, priority)}:")

        for rec in recs:
            if shown >= max_show:
                break

            # Format tournament type indicator
            type_indicator = ""
            if rec["type"] == "Major":
                type_indicator = "⭐"
            elif rec["type"] == "Signature":
                type_indicator = "★"
            elif rec["type"] == "Playoff":
                type_indicator = "🏆"

            print(f"    {type_indicator} {rec['tournament']:<38} Week {rec['week']:<2} | "
                  f"Score: {rec['total_score']:.0f} | Course: {rec['course_fit']:.0f} | "
                  f"Imp: {rec['importance']:.0f}")

            # Show strategic notes
            if rec["strategic_notes"]:
                for note in rec["strategic_notes"][:2]:
                    print(f"       └─ {note}")

            shown += 1

    # Strategy summary
    print(f"\n  {'─'*85}")
    if remaining == 1:
        print(f"  💡 STRATEGY: Save for a Major (Masters, US Open, Open, PGA) or top Signature event")
        print(f"     Best remaining options: Major = max points potential, Signature = strong field")
    elif remaining == 2:
        print(f"  💡 STRATEGY: Use one at a strong course fit event, save one for a Major")
    else:
        print(f"  💡 STRATEGY: Can be flexible - consider course fit for early uses")


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Score player-tournament combinations for fantasy golf",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--tournament', '-t', metavar='NAME',
                        help='Get recommendations for a specific tournament')
    parser.add_argument('--player', '-p', metavar='NAME',
                        help='Get best tournaments for a specific player')
    parser.add_argument('--optimize', '-o', metavar='NAME',
                        help='Optimize remaining uses for a player')
    parser.add_argument('--this-week', action='store_true',
                        help='Show recommendations for current week')
    parser.add_argument('--strategy', action='store_true',
                        help='Show unified strategy dashboard')
    parser.add_argument('--value', action='store_true',
                        help='Show value picks for current week')
    parser.add_argument('--top', type=int, default=15,
                        help='Number of recommendations to show (default: 15)')

    # Weight customization
    parser.add_argument('--w-importance', type=float, default=0.25,
                        help='Weight for tournament importance (default: 0.25)')
    parser.add_argument('--w-course', type=float, default=0.35,
                        help='Weight for course fit (default: 0.35)')
    parser.add_argument('--w-form', type=float, default=0.25,
                        help='Weight for current form (default: 0.25)')
    parser.add_argument('--w-field', type=float, default=0.15,
                        help='Weight for field strength (default: 0.15)')

    args = parser.parse_args()

    # Build custom weights if specified
    weights = {
        'importance': args.w_importance,
        'course_fit': args.w_course,
        'form': args.w_form,
        'field': args.w_field
    }

    # Normalize weights to sum to 1.0
    total = sum(weights.values())
    weights = {k: v/total for k, v in weights.items()}

    # Initialize engine with tournament context for loading correct predictions
    target_tournament = args.tournament
    if not target_tournament and (args.this_week or args.value):
        # Pre-load schedule to find current week tournament
        temp_engine = ScoringEngine.__new__(ScoringEngine)
        temp_engine.tournaments = {}
        temp_engine._load_schedule = lambda: None
        # Quick schedule load
        if SCHEDULE_FILE.exists():
            with open(SCHEDULE_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    purse_str = row['purse'].replace('$', '').replace(',', '')
                    temp_engine.tournaments[row['tournament_name']] = TournamentInfo(
                        name=row['tournament_name'],
                        week=int(row['week']),
                        start_date=row['start_date'],
                        tournament_type=row['tournament_type'],
                        location=row['location'],
                        purse=float(purse_str) if purse_str else 0
                    )
            today = datetime.now().strftime('%Y-%m-%d')
            for name, t in temp_engine.tournaments.items():
                if t.start_date <= today:
                    try:
                        end_day = int(t.start_date[8:10]) + 3
                        end_date = t.start_date[:8] + str(end_day).zfill(2)
                        if today <= end_date:
                            target_tournament = name
                            break
                    except:
                        pass
            if not target_tournament:
                upcoming = [(name, t) for name, t in temp_engine.tournaments.items() if t.start_date >= today]
                if upcoming:
                    upcoming.sort(key=lambda x: x[1].start_date)
                    target_tournament = upcoming[0][0]

    engine = ScoringEngine(weights=weights, tournament=target_tournament)

    # Handle commands
    if args.tournament:
        print_tournament_recommendations(engine, args.tournament, top_n=args.top)
    elif args.player:
        print_player_outlook(engine, args.player)
    elif args.optimize:
        print_usage_optimizer(engine, args.optimize)
    elif args.strategy:
        print_strategy_dashboard(engine)
    elif args.this_week:
        print_this_week(engine)
    elif args.value:
        tournament = engine.get_current_week_tournament()
        if tournament:
            print(f"\n  VALUE PICKS FOR: {tournament}")
            print(f"  {'-'*60}")
            values = engine.get_value_picks(tournament)
            for score in values[:10]:
                print(f"    #{score.owgr_rank:<3} {score.player:<24} Score: {score.total_score:.0f}")
        else:
            print("No current tournament found.")
    else:
        # Default: show this week
        print_this_week(engine)


if __name__ == "__main__":
    main()
