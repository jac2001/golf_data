#!/usr/bin/env python3
"""
Course History Database
=======================

Aggregates player course history from betting profiles to enable:
- Finding course specialists for any tournament
- Calculating course fit scores
- Identifying value plays based on historical performance

Usage:
    from scripts.planning.course_history import CourseHistoryDB

    db = CourseHistoryDB()
    db.load_from_betting_profiles()

    # Find players who perform well at TPC Scottsdale
    specialists = db.get_course_specialists("TPC Scottsdale")

    # Get a player's history at a course
    stats = db.get_player_course_stats("Scottie Scheffler", "Augusta National")
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import re


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BETTING_PROFILES_DIR = DATA_DIR / "betting_profiles"
TOURNAMENT_COURSES_PATH = DATA_DIR / "reference" / "tournament_courses.json"
LEADERBOARDS_PATH = DATA_DIR / "raw" / "tournament_leaderboards.csv"
HISTORICAL_DIR = DATA_DIR / "historical"


def normalize_player_name(name: str) -> str:
    """
    Normalize player name to 'First Last' format (lowercase for matching).

    Handles various formats:
    - 'Last, First' -> 'first last'
    - 'First Last' -> 'first last'
    - '"Last, First"' -> 'first last' (quoted)
    - 'FIRST LAST' -> 'first last' (uppercase)
    - Extra whitespace
    """
    if not name:
        return ""

    # Remove quotes and strip whitespace
    name = name.strip().strip('"').strip("'").strip()

    if not name:
        return ""

    # If name contains comma, it's likely "Last, First" format
    if "," in name:
        parts = name.split(",", 1)
        if len(parts) == 2:
            last = parts[0].strip()
            first = parts[1].strip()
            # Handle suffixes like "Jr." or "III" that might be after first name
            name = f"{first} {last}"

    # Normalize whitespace and case
    name = " ".join(name.split())  # Collapse multiple spaces

    return name


def normalize_name_for_matching(name: str) -> str:
    """
    Normalize name for dictionary key matching (lowercase).
    """
    normalized = normalize_player_name(name)
    return normalized.lower().strip() if normalized else ""


@dataclass
class CourseStats:
    """Statistics for a player at a specific course."""
    player_name: str
    course_name: str
    times_played: int = 0
    avg_finish: float = 0.0
    best_finish: int = 999
    worst_finish: int = 0
    wins: int = 0
    top_5s: int = 0
    top_10s: int = 0
    top_20s: int = 0
    cuts_made: int = 0
    missed_cuts: int = 0
    total_winnings: float = 0.0
    years_played: List[int] = field(default_factory=list)
    results: List[Dict] = field(default_factory=list)  # Raw result data

    @property
    def cut_rate(self) -> float:
        """Percentage of cuts made."""
        if self.times_played == 0:
            return 0.0
        return self.cuts_made / self.times_played

    @property
    def top_10_rate(self) -> float:
        """Percentage of top-10 finishes."""
        if self.times_played == 0:
            return 0.0
        return self.top_10s / self.times_played



    @property 
    def specialization_score(self) -> float:
        """
        Calculate specialization score - identfies true course specialists. 
        Higher = more specialized (multiple good finishes at same venue).
        Score = (wins * 5 + top5s * 2 + top10s * 1) / (plays * 2)
        """
        if self.times_played == 0:
            return 0.0 
        weighted_results = (self.wins * 5) + (self.top_5s * 2) + (self.top_10s * 1)
        return weighted_results / (self.times_played * 2)
    
    
    






    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "player_name": self.player_name,
            "course_name": self.course_name,
            "times_played": self.times_played,
            "avg_finish": round(self.avg_finish, 1),
            "best_finish": self.best_finish if self.best_finish < 999 else None,
            "wins": self.wins,
            "top_5s": self.top_5s,
            "top_10s": self.top_10s,
            "cut_rate": round(self.cut_rate * 100, 1),
            "top_10_rate": round(self.top_10_rate * 100, 1),
            "total_winnings": self.total_winnings,
            "years_played": sorted(self.years_played, reverse=True),
        }


class CourseHistoryDB:
    """
    Database of player course history aggregated from betting profiles.

    Structure:
        self.history = {
            "player_name_lower": {
                "course_name_lower": CourseStats,
                ...
            },
            ...
        }
    """

    # Normalize course names to canonical form to avoid duplicates
    COURSE_NAME_CANONICAL = {
        # Bay Hill variants
        "bay hill club & lodge": "arnold palmer's bay hill club & lodge",
        "bay hill": "arnold palmer's bay hill club & lodge",
        # Innisbrook variants
        "innisbrook resort (copperhead)": "innisbrook resort (copperhead course)",
        "copperhead course": "innisbrook resort (copperhead course)",
        "copperhead": "innisbrook resort (copperhead course)",
        # PGA National variants
        "pga national": "pga national resort (the champion course)",
        "pga national resort (champion course)": "pga national resort (the champion course)",
        "champion course": "pga national resort (the champion course)",
        # TPC Scottsdale variants
        "tpc scottsdale": "tpc scottsdale (stadium course)",
        "tpc scottsdale stadium": "tpc scottsdale (stadium course)",
        # TPC San Antonio variants
        "tpc san antonio": "tpc san antonio (oaks course)",
        "oaks course": "tpc san antonio (oaks course)",
        # East Lake variants
        "east lake": "east lake golf club",
        # Muirfield variants
        "muirfield village": "muirfield village golf club",
        # TPC Sawgrass variants
        "sawgrass": "tpc sawgrass (stadium course)",
        "tpc sawgrass": "tpc sawgrass (stadium course)",
    }

    def __init__(self):
        self.history: Dict[str, Dict[str, CourseStats]] = defaultdict(dict)
        self.tournament_courses: Dict = {}
        self._loaded = False

    def _normalize_course_name(self, course_name: str) -> str:
        """Normalize course name to canonical form."""
        course_lower = course_name.lower().strip()
        return self.COURSE_NAME_CANONICAL.get(course_lower, course_lower)

    def load_tournament_courses(self) -> None:
        """Load the tournament-to-course mapping."""
        if TOURNAMENT_COURSES_PATH.exists():
            with open(TOURNAMENT_COURSES_PATH) as f:
                data = json.load(f)
                self.tournament_courses = data.get("tournaments", {})

    def load_from_betting_profiles(self, profiles_dir: Path = None) -> int:
        """
        Load course history from all betting profile CSV files.

        Returns the number of player-course combinations loaded.
        """
        if profiles_dir is None:
            profiles_dir = BETTING_PROFILES_DIR

        if not profiles_dir.exists():
            print(f"Warning: Betting profiles directory not found: {profiles_dir}")
            return 0

        # Load tournament courses mapping
        self.load_tournament_courses()

        # Find all betting profile files
        profile_files = list(profiles_dir.glob("betting_profiles_*.csv"))

        if not profile_files:
            print(f"Warning: No betting profile files found in {profiles_dir}")
            return 0

        players_processed = set()

        for profile_path in profile_files:
            try:
                df = pd.read_csv(profile_path)

                if "course_history" not in df.columns:
                    continue

                for _, row in df.iterrows():
                    player_name_raw = row.get("player_name", "")
                    course_hist_raw = row.get("course_history", "")

                    if not player_name_raw or pd.isna(course_hist_raw) or not course_hist_raw:
                        continue

                    # Normalize player name to "First Last" format
                    player_name = normalize_player_name(player_name_raw)

                    # Skip if we've already processed this player
                    player_key = player_name.lower().strip()
                    if player_key in players_processed:
                        continue

                    try:
                        course_history = json.loads(course_hist_raw)
                        self._process_player_history(player_name, course_history)
                        players_processed.add(player_key)
                    except json.JSONDecodeError:
                        continue

            except Exception as e:
                print(f"Error processing {profile_path}: {e}")
                continue

        # Also load from tournament leaderboards for more complete history
        self._load_from_leaderboards()

        self._loaded = True

        # Count total player-course combinations
        total_combinations = sum(len(courses) for courses in self.history.values())
        print(f"Loaded course history for {len(self.history)} players, {total_combinations} player-course combinations")

        return total_combinations

    def _load_from_leaderboards(self) -> int:
        """
        Load course history from all leaderboard files to supplement betting profile data.
        Loads from:
        - data/raw/tournament_leaderboards.csv
        - data/historical/leaderboards_YYYY.csv (2020-2026)
        Maps tournament names to courses using tournament_courses.json.
        """
        # Collect all leaderboard files
        leaderboard_files = []

        # Main leaderboards file
        if LEADERBOARDS_PATH.exists():
            leaderboard_files.append(LEADERBOARDS_PATH)

        # Historical leaderboard files
        if HISTORICAL_DIR.exists():
            for f in HISTORICAL_DIR.glob("leaderboards_*.csv"):
                leaderboard_files.append(f)

        if not leaderboard_files:
            return 0

        # Build tournament name to course mapping
        tourney_to_course = {}
        for tourney_name, info in self.tournament_courses.items():
            course_name = info.get("course", "")
            if course_name:
                # Map the full tournament name
                tourney_to_course[tourney_name.lower()] = course_name
                # Also map aliases
                for alias in info.get("aliases", []):
                    tourney_to_course[alias.lower()] = course_name

        added = 0
        for leaderboard_path in leaderboard_files:
            try:
                df = pd.read_csv(leaderboard_path)
                file_added = self._process_leaderboard_df(df, tourney_to_course)
                added += file_added
            except Exception as e:
                print(f"Warning: Could not load {leaderboard_path.name}: {e}")
                continue

        # Recalculate averages after loading all files
        for player_courses in self.history.values():
            for stats in player_courses.values():
                if stats.results:
                    valid_positions = [r["position"] for r in stats.results if r["position"]]
                    if valid_positions:
                        stats.avg_finish = sum(valid_positions) / len(valid_positions)

        return added

    def _process_leaderboard_df(self, df: pd.DataFrame, tourney_to_course: Dict[str, str]) -> int:
        """Process a single leaderboard DataFrame."""
        added = 0

        for _, row in df.iterrows():
            tournament_name = str(row.get("tournament_name", ""))
            player_name_raw = str(row.get("player_name", ""))
            position_str = str(row.get("position", ""))
            year = row.get("year", 0)
            earnings_str = str(row.get("earnings", "$0"))

            if not tournament_name or not player_name_raw or player_name_raw == "nan":
                continue

            # Find course for this tournament
            course_name = self._match_tournament_to_course(tournament_name, tourney_to_course)

            if not course_name:
                continue

            # Normalize player name
            player_name = normalize_player_name(player_name_raw)
            if not player_name:
                continue

            player_key = player_name.lower().strip()
            course_key = self._normalize_course_name(course_name)

            # Initialize stats if needed
            if course_key not in self.history[player_key]:
                self.history[player_key][course_key] = CourseStats(
                    player_name=player_name,
                    course_name=course_key  # Use normalized name
                )

            stats = self.history[player_key][course_key]

            # Skip if we already have this year
            try:
                year_int = int(year)
            except (ValueError, TypeError):
                continue

            if year_int in stats.years_played:
                continue

            # Parse position and earnings
            position = self._parse_position(position_str)
            winnings = self._parse_winnings(earnings_str)

            stats.years_played.append(year_int)
            stats.times_played += 1

            if position is not None:
                stats.results.append({
                    "year": year_int,
                    "position": position,
                    "winnings": winnings
                })

                if position == 1:
                    stats.wins += 1
                if position <= 5:
                    stats.top_5s += 1
                if position <= 10:
                    stats.top_10s += 1
                if position <= 20:
                    stats.top_20s += 1

                stats.best_finish = min(stats.best_finish, position)
                stats.worst_finish = max(stats.worst_finish, position)
                stats.cuts_made += 1
            else:
                stats.missed_cuts += 1

            stats.total_winnings += winnings
            added += 1

        return added

    # Explicit mappings for tournaments NOT in tournament_courses.json
    # This prevents fuzzy matching from guessing wrong
    KNOWN_TOURNAMENT_COURSES = {
        # Myrtle Beach tournaments - NOT Pebble Beach!
        "myrtle beach classic": "Dunes Golf and Beach Club",
        "the myrtle beach classic": "Dunes Golf and Beach Club",
        # Corales tournament
        "corales puntacana championship": "Puntacana Resort & Club (Corales Golf Course)",
        "corales puntacana resort & club championship": "Puntacana Resort & Club (Corales Golf Course)",
        # Sony Open
        "sony open in hawaii": "Waialae Country Club",
        "sony open": "Waialae Country Club",
        # Sentry
        "the sentry": "Plantation Course at Kapalua",
        "sentry tournament of champions": "Plantation Course at Kapalua",
        # American Express
        "the american express": "PGA West (Stadium Course)",
        "american express": "PGA West (Stadium Course)",
        # Farmers Insurance
        "farmers insurance open": "Torrey Pines (South Course)",
        # Mexico Open
        "mexico open at vidanta": "Vidanta Vallarta",
        # Puerto Rico
        "puerto rico open": "Grand Reserve Golf Club",
    }

    def _match_tournament_to_course(self, tournament_name: str, tourney_to_course: Dict[str, str]) -> Optional[str]:
        """
        Match a tournament name to its course using the mapping.

        Matching priority:
        1. Direct exact match in tourney_to_course
        2. Explicit mapping in KNOWN_TOURNAMENT_COURSES (prevents false fuzzy matches)
        3. Partial substring match (tournament contains key or vice versa)
        4. Word-based match (requires 2+ significant words to match)
        """
        tourney_lower = tournament_name.lower().strip()

        # 1. Direct match
        if tourney_lower in tourney_to_course:
            return tourney_to_course[tourney_lower]

        # 2. Check explicit known mappings BEFORE fuzzy matching
        # This prevents tournaments like "Myrtle Beach Classic" from matching "Pebble Beach"
        if tourney_lower in self.KNOWN_TOURNAMENT_COURSES:
            return self.KNOWN_TOURNAMENT_COURSES[tourney_lower]

        # 3. Partial match - tournament name contains key or key contains tournament name
        # Only match if one fully contains the other (not just partial overlap)
        for key, course in tourney_to_course.items():
            if key in tourney_lower or tourney_lower in key:
                return course

        # 4. Word-based matching (STRICT - requires 2+ significant words)
        # IMPORTANT: This is the most error-prone matching, so we require strong evidence
        tourney_words = set(tourney_lower.replace("-", " ").split())

        # Words that are too common/generic to be reliable for matching
        excluded_words = {
            "the", "open", "championship", "classic", "invitational", "tournament",
            "pro", "am", "pro-am", "pga", "tour", "presented", "by", "at", "in", "of",
            # Geographic words that appear in multiple tournament/course names
            "beach", "golf", "club", "country", "links", "course", "national",
            "resort", "hills", "park", "memorial", "cup", "world", "international"
        }

        for key, course in tourney_to_course.items():
            key_words = set(key.replace("-", " ").split())
            # Require at least 2 significant matching words to reduce false positives
            common = tourney_words & key_words - excluded_words
            if len(common) >= 2:
                return course

        # No match found - return None rather than guess
        return None

    def _process_player_history(self, player_name: str, course_history: List[Dict]) -> None:
        """Process a player's course history JSON into CourseStats objects."""
        player_key = player_name.lower().strip()

        for course_entry in course_history:
            course_name = course_entry.get("course_name", "")
            tournaments = course_entry.get("tournaments", [])

            if not course_name or not tournaments:
                continue

            # Normalize course name to canonical form
            course_key = self._normalize_course_name(course_name)

            # Initialize or get existing stats
            if course_key not in self.history[player_key]:
                self.history[player_key][course_key] = CourseStats(
                    player_name=player_name,
                    course_name=course_key  # Use normalized name
                )

            stats = self.history[player_key][course_key]

            for tourney in tournaments:
                position_str = str(tourney.get("position", "MC"))
                year = tourney.get("year", 0)
                winnings_str = str(tourney.get("winnings", "$0"))

                # Parse position
                position = self._parse_position(position_str)

                # Parse winnings
                winnings = self._parse_winnings(winnings_str)

                # Only count if we have a valid year we haven't seen
                if year and year not in stats.years_played:
                    stats.years_played.append(year)
                    stats.times_played += 1

                    if position is not None:
                        # Update stats
                        stats.results.append({
                            "year": year,
                            "position": position,
                            "winnings": winnings
                        })

                        if position == 1:
                            stats.wins += 1
                        if position <= 5:
                            stats.top_5s += 1
                        if position <= 10:
                            stats.top_10s += 1
                        if position <= 20:
                            stats.top_20s += 1

                        if position < stats.best_finish:
                            stats.best_finish = position
                        if position > stats.worst_finish:
                            stats.worst_finish = position

                        stats.cuts_made += 1
                    else:
                        # Missed cut
                        stats.missed_cuts += 1

                    stats.total_winnings += winnings

            # Calculate average finish (only from made cuts)
            made_cut_results = [r["position"] for r in stats.results if r["position"] is not None]
            if made_cut_results:
                stats.avg_finish = sum(made_cut_results) / len(made_cut_results)

    def _parse_position(self, position_str: str) -> Optional[int]:
        """Parse position string to integer. Returns None for missed cuts."""
        if not position_str:
            return None

        position_str = str(position_str).upper().strip()

        # Missed cut indicators
        if position_str in ["MC", "CUT", "WD", "DQ", "W/D", "MDF"]:
            return None

        # Remove 'T' prefix for ties (T5 -> 5)
        position_str = position_str.lstrip("T")

        try:
            return int(position_str)
        except ValueError:
            return None

    def _parse_winnings(self, winnings_str: str) -> float:
        """Parse winnings string to float."""
        if not winnings_str:
            return 0.0

        # Remove $ and commas
        cleaned = str(winnings_str).replace("$", "").replace(",", "").strip()

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def get_player_course_stats(self, player_name: str, course_name: str) -> Optional[CourseStats]:
        """
        Get a player's statistics at a specific course.

        Args:
            player_name: Player's full name
            course_name: Course name (will try to match aliases)

        Returns:
            CourseStats object or None if no history
        """
        if not self._loaded:
            self.load_from_betting_profiles()

        player_key = player_name.lower().strip()

        if player_key not in self.history:
            return None

        # Try normalized match first (handles aliases like "bay hill" -> "arnold palmer's bay hill")
        course_key = self._normalize_course_name(course_name)
        if course_key in self.history[player_key]:
            return self.history[player_key][course_key]

        # Try matching with aliases from tournament_courses
        for tourney_name, tourney_info in self.tournament_courses.items():
            aliases = [tourney_info.get("course", "").lower()] + [a.lower() for a in tourney_info.get("aliases", [])]

            if course_name.lower() in aliases or course_key in aliases:
                # Found the tournament, now search player history for any matching alias
                # Also try normalized versions of aliases
                for alias in aliases:
                    normalized_alias = self._normalize_course_name(alias)
                    if normalized_alias in self.history[player_key]:
                        return self.history[player_key][normalized_alias]
                    if alias in self.history[player_key]:
                        return self.history[player_key][alias]

        # Try substring matching on course names (but be careful of false matches)
        # Only match if one completely contains the other
        for stored_course in self.history[player_key].keys():
            if course_key in stored_course or stored_course in course_key:
                return self.history[player_key][stored_course]

        return None

    def get_course_specialists(
        self,
        course_name: str,
        min_plays: int = 2,
        min_world_rank: int = None,
        max_world_rank: int = None
    ) -> List[Tuple[str, CourseStats, float]]:
        """
        Find players who perform well at a specific course.

        Args:
            course_name: Course name or alias
            min_plays: Minimum times played to qualify
            min_world_rank: Filter to players ranked at least this (e.g., 20 for rank 20+)
            max_world_rank: Filter to players ranked at most this (e.g., 50 for rank 1-50)

        Returns:
            List of (player_name, CourseStats, fit_score) sorted by fit_score descending
        """
        if not self._loaded:
            self.load_from_betting_profiles()

        specialists = []

        for player_key, courses in self.history.items():
            stats = self.get_player_course_stats(player_key, course_name)

            if stats is None or stats.times_played < min_plays:
                continue

            fit_score = self.calculate_course_fit_score(stats)
            specialists.append((stats.player_name, stats, fit_score))

        # Sort by fit score descending
        specialists.sort(key=lambda x: x[2], reverse=True)

        return specialists

    def calculate_course_fit_score(self, stats: CourseStats) -> float:                                                
        """                                                                                                           
        Calculate a 0-100 course fit score based on historical performance.                                           
                                                                                                                    
        Factors:                                                                                                      
        - Wins (huge bonus)                                                                                           
        - Top 5s and Top 10s                                                                                          
        - Average finish                                                                                              
        - Consistency (cut rate)                                                                                      
        - Recency (more recent = better)                                                                              
        - Specialization bonus for true course specialists                                                            
        """                                                                                                           
        if stats.times_played == 0:                                                                                   
            return 45.0  # Neutral score for no history (was 0, too harsh)                                            
                                                                                                                    
        score = 50.0  # Base score                                                                                    
                                                                                                                    
        # Win bonus (massive - 20 points per win, max 30)                                                             
        win_bonus = min(stats.wins * 20, 30)                                                                          
        score += win_bonus                                                                                            
                                                                                                                    
        # Top 5 bonus (5 points each, max 15)                                                                         
        top5_bonus = min((stats.top_5s - stats.wins) * 5, 15)  # Don't double count wins                              
        score += top5_bonus                                                                                           
                                                                                                                    
        # Top 10 bonus (2 points each beyond top 5s, max 10)                                                          
        top10_bonus = min((stats.top_10s - stats.top_5s) * 2, 10)                                                     
        score += top10_bonus                                                                                          
                                                                                                                    
        # Average finish adjustment (-0.5 per position above 20, +1 per position below 10)                            
        if stats.avg_finish > 0:                                                                                      
            if stats.avg_finish <= 10:                                                                                
                score += (10 - stats.avg_finish) * 1                                                                  
            elif stats.avg_finish > 20:                                                                               
                score -= (stats.avg_finish - 20) * 0.5                                                                
                                                                                                                    
        # Cut rate bonus/penalty                                                                                      
        if stats.cut_rate >= 0.9:                                                                                     
            score += 5                                                                                                
        elif stats.cut_rate < 0.5:                                                                                    
            score -= 10                                                                                               
                                                                                                                    
        # === NEW: Specialization bonus ===                                                                           
        # True specialists (multiple strong finishes) get 15-25 point boost                                           
        spec_score = stats.specialization_score                                                                       
        if spec_score > 0.6:  # Elite specialist (e.g., 2 wins in 4 plays)                                            
            score += 25                                                                                               
        elif spec_score > 0.4:  # Strong specialist                                                                   
            score += 15                                                                                               
        elif spec_score > 0.25:  # Moderate specialist                                                                
            score += 8                                                                                                
                                                                                                                    
        # Anti-specialist penalty (consistently poor at this course)                                                  
        if stats.times_played >= 3 and stats.avg_finish > 40 and stats.top_10s == 0:                                  
            score -= 15  # Fade players who struggle here                                                             
                                                                                                                    
        # Recency bonus (playing well recently at course matters more)                                                
        current_year = 2026                                                                                           
        if stats.years_played:                                                                                        
            most_recent = max(stats.years_played)                                                                     
            if most_recent >= current_year - 1:  # Played last year or this year                                      
                score += 5                                                                                            
            elif most_recent <= current_year - 4:  # Haven't played in 4+ years                                       
                score -= 5                                                                                            
                                                                                                                    
        return max(0, min(100, score))









    def get_player_all_courses(self, player_name: str) -> Dict[str, CourseStats]:
        """Get all course history for a player."""
        if not self._loaded:
            self.load_from_betting_profiles()

        player_key = player_name.lower().strip()
        return dict(self.history.get(player_key, {}))

    def find_best_course_for_player(self, player_name: str, min_plays: int = 2) -> List[Tuple[str, CourseStats, float]]:
        """
        Find the best courses for a specific player.

        Returns list of (course_name, stats, fit_score) sorted by fit_score.
        """
        if not self._loaded:
            self.load_from_betting_profiles()

        player_key = player_name.lower().strip()

        if player_key not in self.history:
            return []

        results = []
        for course_key, stats in self.history[player_key].items():
            if stats.times_played >= min_plays:
                fit_score = self.calculate_course_fit_score(stats)
                results.append((stats.course_name, stats, fit_score))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def get_tournament_specialists(
        self,
        tournament_name: str,
        min_plays: int = 2,
        top_n: int = 20
    ) -> List[Tuple[str, CourseStats, float]]:
        """
        Find course specialists for a tournament by looking up its course.

        Args:
            tournament_name: Name of the tournament (e.g., "Waste Management Phoenix Open")
            min_plays: Minimum times played to qualify
            top_n: Return top N specialists

        Returns:
            List of (player_name, CourseStats, fit_score)
        """
        if not self.tournament_courses:
            self.load_tournament_courses()

        # Find the course for this tournament
        tourney_info = self.tournament_courses.get(tournament_name, {})
        course_name = tourney_info.get("course", "")
        aliases = tourney_info.get("aliases", [])

        if not course_name:
            # Try partial match on tournament name
            for name, info in self.tournament_courses.items():
                if tournament_name.lower() in name.lower() or name.lower() in tournament_name.lower():
                    course_name = info.get("course", "")
                    aliases = info.get("aliases", [])
                    break

        if not course_name:
            print(f"Warning: Could not find course for tournament '{tournament_name}'")
            return []

        # Search for specialists using course name and all aliases
        all_specialists = {}

        search_terms = [course_name] + aliases
        for term in search_terms:
            specialists = self.get_course_specialists(term, min_plays=min_plays)
            for player, stats, score in specialists:
                player_key = player.lower()
                if player_key not in all_specialists or score > all_specialists[player_key][2]:
                    all_specialists[player_key] = (player, stats, score)

        # Sort and return top N
        results = sorted(all_specialists.values(), key=lambda x: x[2], reverse=True)
        return results[:top_n]


# Convenience functions
_db_instance = None

def get_course_history_db() -> CourseHistoryDB:
    """Get or create the singleton CourseHistoryDB instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = CourseHistoryDB()
        _db_instance.load_from_betting_profiles()
    return _db_instance


def get_course_specialists(tournament_name: str, min_plays: int = 2, top_n: int = 15) -> List:
    """Quick access to get course specialists for a tournament."""
    db = get_course_history_db()
    return db.get_tournament_specialists(tournament_name, min_plays=min_plays, top_n=top_n)


def get_player_course_fit(player_name: str, tournament_name: str) -> Tuple[Optional[CourseStats], float]:
    """Quick access to get a player's course fit for a tournament."""
    db = get_course_history_db()

    # Get course name for tournament
    tourney_info = db.tournament_courses.get(tournament_name, {})
    course_name = tourney_info.get("course", tournament_name)

    stats = db.get_player_course_stats(player_name, course_name)
    if stats:
        fit_score = db.calculate_course_fit_score(stats)
        return stats, fit_score
    return None, 0.0


def validate_course_history(db: CourseHistoryDB) -> List[str]:
    """
    Validate course history data to detect potential false matches.

    Returns a list of warning messages for suspicious data patterns.
    """
    warnings = []

    # Known course name variations (same course, different names in data)
    COURSE_ALIASES = {
        "bay hill club & lodge": "arnold palmer's bay hill club & lodge",
        "innisbrook resort (copperhead)": "innisbrook resort (copperhead course)",
        "pga national": "pga national resort (the champion course)",
        "tpc scottsdale": "tpc scottsdale (stadium course)",
        "tpc san antonio": "tpc san antonio (oaks course)",
        "east lake": "east lake golf club",
        "muirfield village": "muirfield village golf club",
    }

    # Check 1: Duplicate course entries for same player (data source inconsistency)
    duplicate_courses_found = set()
    for player_key, courses in db.history.items():
        course_names = set(courses.keys())
        for short_name, full_name in COURSE_ALIASES.items():
            if short_name in course_names and full_name in course_names:
                duplicate_courses_found.add((short_name, full_name))

    for short_name, full_name in duplicate_courses_found:
        warnings.append(
            f"DUPLICATE COURSE NAMES: '{short_name}' and '{full_name}' "
            f"appear to be the same course - consider normalizing"
        )

    # Check 2: Look for suspiciously identical stats that suggest false attribution
    # Only flag if: same stats, same years, AND courses share a word (like "beach")
    suspicious_words = {"beach", "pebble", "myrtle", "palm"}
    for player_key, courses in db.history.items():
        if len(courses) < 2:
            continue

        # Build signature for each course
        signatures = {}
        for course_name, stats in courses.items():
            if stats.times_played >= 2 and (stats.wins > 0 or stats.top_5s > 0):
                sig = (stats.times_played, stats.wins, stats.top_5s, tuple(sorted(stats.years_played)))
                if sig not in signatures:
                    signatures[sig] = []
                signatures[sig].append(course_name)

        # Flag if courses with same stats share suspicious words
        for sig, course_list in signatures.items():
            if len(course_list) > 1:
                course_words = set()
                for c in course_list:
                    course_words.update(c.lower().split())
                if course_words & suspicious_words:
                    warnings.append(
                        f"POSSIBLE FALSE MATCH: {db.history[player_key][course_list[0]].player_name} "
                        f"has identical stats ({sig[0]} plays, {sig[1]}W, {sig[2]} T5s) "
                        f"at: {', '.join(course_list)} - verify this is correct"
                    )

    # Check 3: Players who appear at Pebble Beach but not in known field
    # (Can add specific known fields as reference data if needed)

    return warnings


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Course History Database")
    parser.add_argument("--tournament", "-t", help="Show specialists for a tournament")
    parser.add_argument("--player", "-p", help="Show course history for a player")
    parser.add_argument("--course", "-c", help="Show specialists for a specific course")
    parser.add_argument("--top", type=int, default=15, help="Number of results to show")
    parser.add_argument("--validate", "-v", action="store_true", help="Validate data for potential issues")

    args = parser.parse_args()

    db = CourseHistoryDB()
    db.load_from_betting_profiles()

    if args.tournament:
        print(f"\n{'='*70}")
        print(f"  COURSE SPECIALISTS: {args.tournament.upper()}")
        print(f"{'='*70}\n")

        specialists = db.get_tournament_specialists(args.tournament, top_n=args.top)

        if not specialists:
            print("  No specialists found (check tournament name)")
        else:
            print(f"  {'Player':<25} {'Plays':<6} {'Avg':<6} {'Wins':<5} {'T5s':<5} {'T10s':<5} {'Score':<6}")
            print(f"  {'-'*64}")

            for player, stats, score in specialists:
                avg_str = f"{stats.avg_finish:.1f}" if stats.avg_finish > 0 else "-"
                print(f"  {player:<25} {stats.times_played:<6} {avg_str:<6} {stats.wins:<5} {stats.top_5s:<5} {stats.top_10s:<5} {score:.0f}/100")

    elif args.player:
        print(f"\n{'='*70}")
        print(f"  COURSE HISTORY: {args.player.upper()}")
        print(f"{'='*70}\n")

        best_courses = db.find_best_course_for_player(args.player, min_plays=1)

        if not best_courses:
            print(f"  No course history found for {args.player}")
        else:
            print(f"  {'Course':<30} {'Plays':<6} {'Avg':<6} {'Wins':<5} {'T5s':<5} {'Score':<6}")
            print(f"  {'-'*58}")

            for course, stats, score in best_courses[:args.top]:
                avg_str = f"{stats.avg_finish:.1f}" if stats.avg_finish > 0 else "-"
                print(f"  {course[:28]:<30} {stats.times_played:<6} {avg_str:<6} {stats.wins:<5} {stats.top_5s:<5} {score:.0f}/100")

    elif args.course:
        print(f"\n{'='*70}")
        print(f"  SPECIALISTS AT: {args.course.upper()}")
        print(f"{'='*70}\n")

        specialists = db.get_course_specialists(args.course, min_plays=2)

        if not specialists:
            print("  No specialists found")
        else:
            print(f"  {'Player':<25} {'Plays':<6} {'Avg':<6} {'Wins':<5} {'T5s':<5} {'Score':<6}")
            print(f"  {'-'*53}")

            for player, stats, score in specialists[:args.top]:
                avg_str = f"{stats.avg_finish:.1f}" if stats.avg_finish > 0 else "-"
                print(f"  {player:<25} {stats.times_played:<6} {avg_str:<6} {stats.wins:<5} {stats.top_5s:<5} {score:.0f}/100")

    elif args.validate:
        print(f"\n{'='*70}")
        print(f"  VALIDATING COURSE HISTORY DATA")
        print(f"{'='*70}\n")

        warnings = validate_course_history(db)

        if not warnings:
            print("  ✓ No issues detected!")
        else:
            print(f"  Found {len(warnings)} potential issues:\n")
            for i, warning in enumerate(warnings, 1):
                print(f"  {i}. {warning}\n")

    else:
        # Default: show summary
        print(f"\nCourse History Database loaded:")
        print(f"  - {len(db.history)} players with course history")
        print(f"  - {len(db.tournament_courses)} tournaments mapped to courses")
        print(f"\nUsage:")
        print(f"  --tournament 'Waste Management Phoenix Open'  # Find specialists")
        print(f"  --player 'Scottie Scheffler'                  # Show player's history")
        print(f"  --course 'TPC Scottsdale'                     # Find course specialists")
        print(f"  --validate                                     # Check for data issues")
