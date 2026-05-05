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
import re
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

COURSE_WEIGHTS_FILE = DATA_DIR / "course_sg_weights.csv"
DG_DEFAULT_WEIGHTS = {
    "ott_sg": 0.020,
    "app_sg": 0.020,
    "arg_sg": 0.025,
    "putt_sg": 0.005,
}

# Course-weights naming normalizer mirrors prediction feature engineering.
DG_ALIAS_MAP = {
    "shriners hospitals for children open": "shriners children s open",
    "mexico open at vidantaworld": "mexico open at vidanta",
    "oneflight myrtle beach classic": "myrtle beach classic",
    "atandt byron nelson": "the cj cup byron nelson",
    "rocket classic": "rocket mortgage classic",
    "safeway open": "fortinet championship",
    "sentry tournament of champions": "the sentry",
    "texas children s houston open": "cadence bank houston open",
    "hewlett packard enterprise houston open": "cadence bank houston open",
    "vivint houston open": "cadence bank houston open",
    "waste management phoenix open": "wm phoenix open",
    "the honda classic": "cognizant classic in the palm beaches",
    "the memorial tournament presented by nationwide": "the memorial tournament",
    "houston open": "cadence bank houston open",
}


def normalize_tournament_name(name: str) -> str:
    """Normalize tournament names for course-weight lookups."""
    if not isinstance(name, str):
        return ""
    cleaned = re.sub(r"\(\s*\d{4}\s*\)", "", name)
    cleaned = cleaned.replace("&", "and").lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return DG_ALIAS_MAP.get(cleaned, cleaned)


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
    season_sg_ott: float = 0.0
    season_sg_app: float = 0.0
    season_sg_arg: float = 0.0
    season_sg_putt: float = 0.0


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
    dg_fit_score: float = 50.0
    dg_fit_predictability: float = 1.0
    fit_confidence: float = 0.0

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
        self.course_label_to_type: Dict[str, str] = {}
        self._course_type_fit_cache: Dict[Tuple[str, str], Tuple[float, str]] = {}
        self._player_course_baseline_cache: Dict[str, float] = {}
        self.course_weight_lookup: Dict[str, Dict[str, float]] = {}
        self._dg_weight_sum_avg: float = sum(DG_DEFAULT_WEIGHTS.values())
        self._dg_fit_cache: Dict[Tuple[str, str], Tuple[float, float, str]] = {}
        self.target_tournament = tournament
        self.ml_scores: Dict[str, float] = {}  # player -> ML percentile score (0-100)

        self._load_data()

    def _load_data(self):
        """Load all data sources."""
        self._load_schedule()
        self._load_tournament_courses()
        self._load_course_weights()
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
            self.course_label_to_type = {}
            for info in self.tournament_courses.values():
                ctype = str(info.get("course_type", "")).strip().lower()
                if not ctype:
                    continue
                labels = [
                    info.get("course", ""),
                    info.get("course_full", ""),
                    *info.get("aliases", []),
                ]
                for label in labels:
                    norm = self._normalize_course_label(str(label))
                    if norm:
                        self.course_label_to_type[norm] = ctype

        # Update tournament info with course data
        for name, info in self.tournament_courses.items():
            if name in self.tournaments:
                self.tournaments[name].course = info.get('course', '')
                self.tournaments[name].course_type = info.get('course_type', '')

    def _load_course_weights(self):
        """Load DataGolf-style course demand weights."""
        self.course_weight_lookup = {}
        if not COURSE_WEIGHTS_FILE.exists():
            print(f"Warning: Course SG weights not found at {COURSE_WEIGHTS_FILE}")
            self._dg_weight_sum_avg = sum(DG_DEFAULT_WEIGHTS.values())
            return

        with open(COURSE_WEIGHTS_FILE, "r") as f:
            reader = csv.DictReader(f)
            weight_sums = []
            for row in reader:
                t_name = row.get("tournament_name", "")
                key = normalize_tournament_name(t_name)
                if not key:
                    continue
                try:
                    w = {
                        "ott_sg": float(row.get("ott_sg", DG_DEFAULT_WEIGHTS["ott_sg"]) or DG_DEFAULT_WEIGHTS["ott_sg"]),
                        "app_sg": float(row.get("app_sg", DG_DEFAULT_WEIGHTS["app_sg"]) or DG_DEFAULT_WEIGHTS["app_sg"]),
                        "arg_sg": float(row.get("arg_sg", DG_DEFAULT_WEIGHTS["arg_sg"]) or DG_DEFAULT_WEIGHTS["arg_sg"]),
                        "putt_sg": float(row.get("putt_sg", DG_DEFAULT_WEIGHTS["putt_sg"]) or DG_DEFAULT_WEIGHTS["putt_sg"]),
                    }
                except Exception:
                    continue
                self.course_weight_lookup[key] = w
                weight_sums.append(sum(w.values()))

        if weight_sums:
            self._dg_weight_sum_avg = sum(weight_sums) / len(weight_sums)
        else:
            self._dg_weight_sum_avg = sum(DG_DEFAULT_WEIGHTS.values())
        print(f"  Loaded DataGolf course weights for {len(self.course_weight_lookup)} tournaments")

    def _get_course_weights(self, tournament_name: str) -> Dict[str, float]:
        """Fetch course demand weights with normalized name lookup."""
        key = normalize_tournament_name(tournament_name)
        if key in self.course_weight_lookup:
            return self.course_weight_lookup[key]
        return DG_DEFAULT_WEIGHTS.copy()

    def _course_predictability_factor(self, tournament_name: str) -> float:
        """
        Estimate course predictability from total SG explanatory power.
        <1 means more random (shrink adjustments), >1 means more predictable.
        """
        w = self._get_course_weights(tournament_name)
        total = sum(w.values())
        if self._dg_weight_sum_avg <= 0:
            return 1.0
        factor = total / self._dg_weight_sum_avg
        return max(0.70, min(1.25, factor))

    def _get_player_dg_fit(self, player: str, tournament_name: str) -> Tuple[float, float, str]:
        """
        DataGolf-style skill-demand score (0-100) for player × tournament.
        Returns (fit_score_0_100, predictability_factor, reason_note).
        """
        cache_key = (player.lower().strip(), normalize_tournament_name(tournament_name))
        if cache_key in self._dg_fit_cache:
            return self._dg_fit_cache[cache_key]

        form = self.predictions.get(player)
        if not form:
            out = (50.0, 1.0, "DG: neutral")
            self._dg_fit_cache[cache_key] = out
            return out

        # Build raw DG fit values for the whole field to rank as percentile.
        weights = self._get_course_weights(tournament_name)
        scale = 10.0
        raw_values: Dict[str, float] = {}
        for pname, pf in self.predictions.items():
            raw = (
                float(pf.season_sg_ott) * weights["ott_sg"] +
                float(pf.season_sg_app) * weights["app_sg"] +
                float(pf.season_sg_arg) * weights["arg_sg"] +
                float(pf.season_sg_putt) * weights["putt_sg"]
            ) * scale
            raw_values[pname] = raw

        # Convert raw fit to percentile score in current field.
        vals = sorted(raw_values.values())
        target_raw = raw_values.get(player, 0.0)
        n = len(vals)
        if n <= 1:
            pct = 50.0
        else:
            # Mid-rank percentile
            lower = sum(1 for v in vals if v < target_raw)
            equal = sum(1 for v in vals if v == target_raw)
            rank = lower + 0.5 * equal
            pct = (rank / n) * 100.0

        # Random courses shrink toward neutral 50.
        predictability = self._course_predictability_factor(tournament_name)
        adjusted = 50.0 + (pct - 50.0) * predictability
        adjusted = max(0.0, min(100.0, adjusted))

        note = f"DG fit p{pct:.0f} (x{predictability:.2f})"
        out = (adjusted, predictability, note)
        self._dg_fit_cache[cache_key] = out
        return out

    def _normalize_course_label(self, value: str) -> str:
        """Normalize course labels for fuzzy matching."""
        if not value:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()

    def _course_type_tokens(self, value: str) -> set:
        """Tokenize course type strings for approximate matching."""
        if not value:
            return set()
        stop = {
            "course", "style", "club", "resort", "golf", "the", "and",
            "at", "in", "of", "with", "to", "for",
        }
        tokens = self._normalize_course_label(value).split()
        return {t for t in tokens if t and t not in stop}

    def _course_type_matches(self, actual: str, target: str) -> bool:
        """Return True when course types are semantically compatible."""
        a = str(actual or "").strip().lower()
        b = str(target or "").strip().lower()
        if not a or not b:
            return False
        if a == b:
            return True
        ta = self._course_type_tokens(a)
        tb = self._course_type_tokens(b)
        if not ta or not tb:
            return False
        overlap = ta.intersection(tb)
        return len(overlap) >= max(1, min(len(ta), len(tb)) // 2)

    def _infer_course_type_from_course_name(self, course_name: str) -> str:
        """Infer course type label from tournament course alias map."""
        key = self._normalize_course_label(course_name)
        if not key:
            return ""
        if key in self.course_label_to_type:
            return self.course_label_to_type[key]
        # Fuzzy fallback: exact token containment.
        for label, ctype in self.course_label_to_type.items():
            if key in label or label in key:
                return ctype
        return ""

    def _player_course_baseline_fit(self, player: str) -> Optional[float]:
        """
        Player-specific neutral course fit from all known course history.
        Used when exact/tournament-type history is unavailable.
        """
        cache_key = player.lower().strip()
        if cache_key in self._player_course_baseline_cache:
            return self._player_course_baseline_cache[cache_key]
        if not self.course_db:
            return None
        all_courses = self.course_db.get_player_all_courses(player)
        if not all_courses:
            return None
        fits = []
        for stats in all_courses.values():
            if stats.times_played < 1:
                continue
            fits.append(self.course_db.calculate_course_fit_score(stats))
        if not fits:
            return None
        baseline = float(sum(fits) / len(fits))
        self._player_course_baseline_cache[cache_key] = baseline
        return baseline

    def _estimate_course_type_fit(self, player: str, target_course_type: str) -> Optional[Tuple[float, str]]:
        """
        Estimate player fit for a course type using all known course history.
        Provides player-specific differentiation when no exact venue history exists.
        """
        if not self.course_db or not target_course_type:
            return None

        cache_key = (player.lower().strip(), str(target_course_type).strip().lower())
        if cache_key in self._course_type_fit_cache:
            return self._course_type_fit_cache[cache_key]

        all_courses = self.course_db.get_player_all_courses(player)
        if not all_courses:
            return None

        matched = []
        for stats in all_courses.values():
            inferred_type = self._infer_course_type_from_course_name(stats.course_name)
            if not inferred_type:
                continue
            if not self._course_type_matches(inferred_type, target_course_type):
                continue
            fit = self.course_db.calculate_course_fit_score(stats)
            weight = max(1, int(stats.times_played))
            matched.append((fit, weight))

        if not matched:
            return None

        weighted_fit = sum(f * w for f, w in matched) / sum(w for _, w in matched)
        confidence = min(1.0, sum(w for _, w in matched) / 8.0)
        adjusted_fit = 45.0 * (1.0 - confidence) + weighted_fit * confidence
        note = f"Type fit ({target_course_type})"
        out = (max(0.0, min(100.0, adjusted_fit)), note)
        self._course_type_fit_cache[cache_key] = out
        return out

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

        def _to_float(value, default=0.0):
            try:
                if value in (None, "", "nan"):
                    return float(default)
                return float(value)
            except Exception:
                return float(default)

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
                        owgr_rank=int(_to_float(row.get('world_rank', row.get('owgr_rank', 999)), 999)),
                        win_prob=_to_float(row.get('win_prob', 0), 0),
                        top5_prob=_to_float(row.get('top5_prob', row.get('top_5_prob', 0)), 0),
                        top10_prob=_to_float(row.get('top10_prob', row.get('top_10_prob', 0)), 0),
                        form_trend=form_trend,
                        hot_hand_score=_to_float(row.get('hot_hand_score', 0), 0),
                        model_edge=_to_float(row.get('expected_value', row.get('model_vs_vegas_edge', 0)), 0),
                        season_sg_ott=_to_float(row.get('season_sg_ott', row.get('sg_ott', 0)), 0),
                        season_sg_app=_to_float(row.get('season_sg_app', row.get('sg_app', 0)), 0),
                        season_sg_arg=_to_float(row.get('season_sg_arg', row.get('sg_arg', 0)), 0),
                        season_sg_putt=_to_float(row.get('season_sg_putt', row.get('sg_putt', 0)), 0),
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
        matched_exact = False
        history_confidence = 0.20

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
                    matched_exact = True
                    history_confidence = min(0.90, 0.55 + 0.10 * min(int(stats.times_played), 4))
                    break

            if not matched_exact:
                # Fallback 1: same course-type fit (player-specific)
                target_type = str(course_info.get("course_type", "")).strip()
                type_fit = self._estimate_course_type_fit(player, target_type)
                if type_fit is not None:
                    score.course_fit = type_fit[0]
                    score.course_history_note = type_fit[1]
                    history_confidence = 0.55
                else:
                    # Fallback 2: player's global course baseline (still player-specific)
                    baseline = self._player_course_baseline_fit(player)
                    if baseline is not None:
                        score.course_fit = 40.0 + 0.5 * (baseline - 45.0)
                        score.course_fit = max(0.0, min(100.0, score.course_fit))
                        score.course_history_note = "General course form"
                        history_confidence = 0.35
                    else:
                        score.course_fit = 40.0  # Neutral default
                        score.course_history_note = "No history"
                        history_confidence = 0.20

        # DataGolf-style event-demand fit (skill profile × course weights).
        dg_fit, dg_predictability, dg_note = self._get_player_dg_fit(player, tournament)
        score.dg_fit_score = dg_fit
        score.dg_fit_predictability = dg_predictability

        # Blend historical/course-type fit with DG fit.
        # Exact course history gets more weight than modeled fit; no-history relies more on DG fit.
        base_fit = score.course_fit if score.course_fit > 0 else 45.0
        dg_weight = 0.30 if matched_exact else 0.55
        score.course_fit = (1.0 - dg_weight) * base_fit + dg_weight * dg_fit
        score.course_fit = max(0.0, min(100.0, score.course_fit))

        if score.course_history_note and score.course_history_note != "No history":
            score.course_history_note = f"{score.course_history_note} + {dg_note}"
        else:
            score.course_history_note = dg_note

        # Confidence-aware reweighting:
        # when player-course signal is strong, shift weight away from generic event prestige
        # toward true player-event fit (course + form).
        fit_signal = min(1.0, abs(score.course_fit - 50.0) / 35.0)
        fit_conf = max(
            0.0,
            min(1.0, 0.45 * history_confidence + 0.30 * dg_predictability + 0.25 * fit_signal),
        )
        score.fit_confidence = fit_conf

        w = score.weights.copy()
        shift = min(0.08, 0.02 + 0.10 * fit_conf)  # max 8 points moved from importance
        imp0 = w.get("importance", 0.15)
        course0 = w.get("course_fit", 0.20)
        form0 = w.get("form", 0.05)

        moved = min(shift, max(0.0, imp0 - 0.06))
        w["importance"] = imp0 - moved
        w["course_fit"] = min(0.38, course0 + moved * 0.75)
        w["form"] = min(0.15, form0 + moved * 0.25)

        # Normalize to keep total score scale stable.
        total_w = sum(float(v) for v in w.values() if v is not None and v > 0)
        if total_w > 0:
            for k in list(w.keys()):
                w[k] = float(w[k]) / total_w
            score.weights = w

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
        from datetime import timedelta
        today = datetime.now().strftime('%Y-%m-%d')

        for name, t in self.tournaments.items():
            # Check if today falls within tournament week (start to start+3 days)
            if t.start_date <= today:
                try:
                    start_dt = datetime.strptime(t.start_date, '%Y-%m-%d')
                    end_date = (start_dt + timedelta(days=3)).strftime('%Y-%m-%d')
                    if today <= end_date:
                        return name
                except Exception:
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

    print(f"\n  {'#':<3} {'Tournament':<31} {'Date':<12} {'Score':>6} {'Rating':<7} {'Course':>7} {'DG':>5} {'Form':>6}  Signal")
    print(f"  {'-'*128}")

    for i, score in enumerate(tournaments, 1):
        t = engine.tournaments.get(score.tournament)
        date = t.start_date if t else "?"
        signal = score.course_history_note or "—"
        print(f"  {i:<3} {score.tournament:<31} {date:<12} {score.total_score:>5.0f}  "
              f"{score.value_rating:<7} {score.course_fit:>6.0f} {score.dg_fit_score:>5.0f} {score.current_form:>5.0f}  {signal}")


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
