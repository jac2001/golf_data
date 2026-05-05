#!/usr/bin/env python3
"""
Usage Tracker for Fantasy Golf - Season 2026

Tracks player usage across the season for "Let It Ride" fantasy league.
- 3 uses per player maximum
- 3 players per weekly lineup
- 30 tournaments in the season

Usage:
    # Add a pick (before tournament starts)
    python usage_tracker.py --add "Scottie Scheffler" --tournament "Waste Management Phoenix Open"

    # Add multiple picks at once
    python usage_tracker.py --add "Scottie Scheffler" "Rory McIlroy" "Jon Rahm" --tournament "Waste Management Phoenix Open"

    # Record result after tournament
    python usage_tracker.py --result "Scottie Scheffler" --tournament "Waste Management Phoenix Open" --finish "T3" --earnings 485000

    # Check a player's usage
    python usage_tracker.py --check "Scottie Scheffler"

    # Show all usage summary
    python usage_tracker.py --summary

    # Show weekly lineups
    python usage_tracker.py --lineups

    # Show players with uses remaining
    python usage_tracker.py --available

    # Undo a pick (if you made a mistake)
    python usage_tracker.py --remove "Scottie Scheffler" --tournament "Waste Management Phoenix Open"
"""

import json
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
import csv


_LATIN_MAP = str.maketrans({
    # Nordic / Scandinavian
    'ø': 'o', 'ö': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o',
    'æ': 'ae',
    'å': 'a', 'ä': 'a', 'á': 'a', 'à': 'a', 'â': 'a',
    'ð': 'd',
    'þ': 'th',
    # Spanish / French / other
    'ñ': 'n',
    'ü': 'u', 'ú': 'u', 'ù': 'u', 'û': 'u',
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ç': 'c',
    'ß': 'ss',
})


def _normalize_name(name: str) -> str:
    """Lowercase + transliterate accented/Nordic chars for fuzzy name matching.

    "Nicolai Hojgaard" and "Nicolai Højgaard" both normalize to
    "nicolai hojgaard" because ø → o in the transliteration table.
    NFKD alone is insufficient because ø has no Unicode decomposition.
    """
    s = str(name).strip().lower()
    # Explicit transliteration first (ø→o, æ→ae, å→a, etc.)
    s = s.translate(_LATIN_MAP)
    # Then NFKD + combining-char strip for anything remaining (é→e, etc.)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path(__file__).parent.parent.parent / "data"
FANTASY_DIR = DATA_DIR / "fantasy"
TRACKER_FILE = FANTASY_DIR / "usage_tracker_2026.json"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"

MAX_USES_PER_PLAYER = 3
PLAYERS_PER_LINEUP = 3
SEASON = "2026"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TournamentUse:
    """Record of a player being used at a tournament."""
    tournament: str
    week: int
    date: str
    result: Optional[str] = None  # e.g., "1st", "T3", "MC" (missed cut)
    earnings: Optional[int] = None

    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        if "earnings" in data:
            data["points"] = data["earnings"]  # legacy compatibility
        return data


@dataclass
class PlayerUsage:
    """Track all uses for a single player."""
    player_name: str
    times_used: int
    tournaments_used: List[TournamentUse]

    @property
    def remaining_uses(self) -> int:
        return MAX_USES_PER_PLAYER - self.times_used

    @property
    def total_earnings(self) -> int:
        return sum(t.earnings or 0 for t in self.tournaments_used)

    @property
    def total_points(self) -> int:
        return self.total_earnings

    def to_dict(self) -> dict:
        return {
            "times_used": self.times_used,
            "tournaments_used": [t.to_dict() for t in self.tournaments_used],
            "remaining_uses": self.remaining_uses,
            "total_earnings": self.total_earnings,
            "total_points": self.total_earnings,
        }


def _fmt_money(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return f"${int(value):,}"


# ============================================================================
# USAGE TRACKER CLASS
# ============================================================================

class UsageTracker:
    """Manages fantasy golf player usage for the season."""

    def __init__(self):
        self.season = SEASON
        self.max_uses = MAX_USES_PER_PLAYER
        self.players_per_lineup = PLAYERS_PER_LINEUP
        self.picks: Dict[str, PlayerUsage] = {}  # player_name -> PlayerUsage
        self.weekly_lineups: Dict[int, dict] = {}  # week -> lineup info
        self.schedule: Dict[str, dict] = {}  # tournament_name -> schedule info

        self._load_schedule()

    def _find_player_key(self, player_name: str) -> Optional[str]:
        """Return the canonical dict key for a player using accent-normalized comparison.

        If "Nicolai Hojgaard" is passed but the tracker stores "Nicolai Højgaard",
        this returns "Nicolai Højgaard" so we update the right record.
        Returns None if the player has never been tracked.
        """
        norm_input = _normalize_name(player_name)
        for key in self.picks:
            if _normalize_name(key) == norm_input:
                return key
        return None

    def _load_schedule(self):
        """Load tournament schedule for week/date lookups."""
        if not SCHEDULE_FILE.exists():
            print(f"Warning: Schedule file not found at {SCHEDULE_FILE}")
            return

        with open(SCHEDULE_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.schedule[row['tournament_name']] = {
                    'week': int(row['week']),
                    'start_date': row['start_date'],
                    'tournament_type': row['tournament_type'],
                    'purse': row['purse']
                }

    def _get_tournament_info(self, tournament: str) -> dict:
        """Get week and date for a tournament."""
        if tournament in self.schedule:
            return self.schedule[tournament]

        # Try partial match (either direction so both
        # "Cognizant Classic" and "Cognizant Classic in The Palm Beaches" resolve)
        t_lower = tournament.lower()
        for name, info in self.schedule.items():
            n_lower = name.lower()
            if t_lower in n_lower or n_lower in t_lower:
                return info

        # Default if not found
        return {'week': 0, 'start_date': 'Unknown'}

    def load(self) -> bool:
        """Load usage data from JSON file."""
        if not TRACKER_FILE.exists():
            return False

        with open(TRACKER_FILE, 'r') as f:
            data = json.load(f)

        # Load player picks — handle both current format (times_used/tournaments_used)
        # and legacy format (uses/weeks) that was produced by an older tracker version.
        for player_name, player_data in data.get('picks', {}).items():
            if 'times_used' in player_data:
                # Current format
                tournaments = [
                    TournamentUse(
                        tournament=t['tournament'],
                        week=t['week'],
                        date=t.get('date', ''),
                        result=t.get('result'),
                        earnings=t.get('earnings', t.get('points'))
                    )
                    for t in player_data.get('tournaments_used', [])
                ]
                times_used = player_data['times_used']
            else:
                # Legacy format: {uses, remaining_uses, weeks: [11, ...]}
                # Reconstruct minimal TournamentUse objects from week numbers.
                times_used = player_data.get('uses', 0)
                week_nums = player_data.get('weeks', [])
                sched_by_week = {v['week']: k for k, v in self.schedule.items()}
                tournaments = [
                    TournamentUse(
                        tournament=sched_by_week.get(w, f'Week {w}'),
                        week=w,
                        date='',
                    )
                    for w in week_nums
                ]
            self.picks[player_name] = PlayerUsage(
                player_name=player_name,
                times_used=times_used,
                tournaments_used=tournaments
            )

        # Load weekly lineups
        self.weekly_lineups = data.get('weekly_lineups', {})
        for lineup in self.weekly_lineups.values():
            earnings = lineup.get("earnings_earned", lineup.get("points_earned"))
            lineup["earnings_earned"] = earnings
            lineup["points_earned"] = earnings

        return True

    def save(self):
        """Save usage data to JSON file."""
        FANTASY_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "season": self.season,
            "max_uses_per_player": self.max_uses,
            "players_per_lineup": self.players_per_lineup,
            "last_updated": datetime.now().isoformat(),
            "picks": {
                name: usage.to_dict()
                for name, usage in self.picks.items()
            },
            "weekly_lineups": self.weekly_lineups,
            "summary": {
                "total_players_used": len(self.picks),
                "total_picks_made": sum(p.times_used for p in self.picks.values()),
                "total_earnings": sum(p.total_earnings for p in self.picks.values()),
                "total_points": sum(p.total_earnings for p in self.picks.values()),
            }
        }

        with open(TRACKER_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def add_pick(self, player_name: str, tournament: str) -> tuple[bool, str]:
        """
        Add a player pick for a tournament.
        Returns (success, message).
        """
        # Get tournament info
        info = self._get_tournament_info(tournament)
        week = info['week']
        date = info['start_date']

        # Resolve to canonical player key (accent-normalized lookup).
        # This ensures "Nicolai Hojgaard" updates the same record as
        # "Nicolai Højgaard" rather than creating a second entry.
        canonical_key = self._find_player_key(player_name)
        if canonical_key:
            player_name = canonical_key  # use the spelling already in tracker
        else:
            self.picks[player_name] = PlayerUsage(
                player_name=player_name,
                times_used=0,
                tournaments_used=[]
            )

        player = self.picks[player_name]

        # Check if player has uses remaining
        if player.remaining_uses <= 0:
            return False, f"❌ {player_name} has no uses remaining (used {player.times_used}/{self.max_uses})"

        # Check if already used this week.
        # Match on week number (not tournament name) so "Cognizant Classic"
        # and "Cognizant Classic in The Palm Beaches" are treated as the same
        # event and don't get double-counted.
        for t in player.tournaments_used:
            if week != 0 and t.week == week:
                return False, f"❌ {player_name} already used this week (Week {week}: {t.tournament})"
            if t.tournament == tournament:  # exact-name fallback (week=0 edge case)
                return False, f"❌ {player_name} already used at {tournament}"

        # Add the pick
        player.tournaments_used.append(TournamentUse(
            tournament=tournament,
            week=week,
            date=date
        ))
        player.times_used += 1

        # Update weekly lineup
        week_key = f"week_{week}"
        if week_key not in self.weekly_lineups:
            self.weekly_lineups[week_key] = {
                "tournament": tournament,
                "week": week,
                "date": date,
                "lineup": [],
                "earnings_earned": None,
                "points_earned": None,
            }

        if player_name not in self.weekly_lineups[week_key]["lineup"]:
            self.weekly_lineups[week_key]["lineup"].append(player_name)

        return True, f"✓ Added {player_name} for {tournament} (Week {week}) - {player.remaining_uses} uses remaining"

    def remove_pick(self, player_name: str, tournament: str) -> tuple[bool, str]:
        """Remove a pick (undo mistake)."""
        canonical_key = self._find_player_key(player_name)
        if not canonical_key:
            return False, f"❌ {player_name} not found in tracker"
        player_name = canonical_key
        if player_name not in self.picks:
            return False, f"❌ {player_name} not found in tracker"

        player = self.picks[player_name]

        # Find and remove the tournament
        for i, t in enumerate(player.tournaments_used):
            if t.tournament == tournament:
                # Don't allow removing if result already recorded
                if t.result is not None:
                    return False, f"❌ Cannot remove - result already recorded for {tournament}"

                player.tournaments_used.pop(i)
                player.times_used -= 1

                # Remove from weekly lineup
                info = self._get_tournament_info(tournament)
                week_key = f"week_{info['week']}"
                if week_key in self.weekly_lineups:
                    if player_name in self.weekly_lineups[week_key]["lineup"]:
                        self.weekly_lineups[week_key]["lineup"].remove(player_name)

                # Clean up empty player records
                if player.times_used == 0:
                    del self.picks[player_name]

                return True, f"✓ Removed {player_name} from {tournament}"

        return False, f"❌ {player_name} not used at {tournament}"

    def _recompute_week_earnings(self, tournament: str, week: int):
        week_key = f"week_{week}"
        if week_key not in self.weekly_lineups:
            return
        lineup = self.weekly_lineups[week_key]
        total = 0
        has_any = False
        for player_name in lineup.get("lineup", []):
            player = self.picks.get(player_name)
            if not player:
                continue
            for t in player.tournaments_used:
                if t.tournament == tournament:
                    if t.earnings is not None:
                        total += t.earnings
                        has_any = True
                    break
        lineup["earnings_earned"] = total if has_any else None
        lineup["points_earned"] = lineup["earnings_earned"]

    def record_result(self, player_name: str, tournament: str,
                      result: str, earnings: int) -> tuple[bool, str]:
        """Record the result after a tournament finishes."""
        player_name = self._find_player_key(player_name) or player_name
        if player_name not in self.picks:
            return False, f"❌ {player_name} not found in tracker"

        player = self.picks[player_name]

        for t in player.tournaments_used:
            if t.tournament == tournament:
                t.result = result
                t.earnings = earnings
                self._recompute_week_earnings(tournament, t.week)
                return True, f"✓ Recorded {player_name}: {result} ({_fmt_money(earnings)}) at {tournament}"

        return False, f"❌ {player_name} not used at {tournament}"

    def get_player_status(self, player_name: str) -> Optional[PlayerUsage]:
        """Get usage status for a player (accent-normalized lookup)."""
        key = self._find_player_key(player_name) or player_name
        return self.picks.get(key)

    def get_available_players(self, used_players: List[str] = None) -> Dict[str, int]:
        """
        Get players with uses remaining.
        If used_players provided, shows remaining uses for those players.
        Otherwise shows all tracked players.
        """
        result = {}

        if used_players:
            for player in used_players:
                if player in self.picks:
                    result[player] = self.picks[player].remaining_uses
                else:
                    result[player] = self.max_uses  # Never used
        else:
            for player, usage in self.picks.items():
                if usage.remaining_uses > 0:
                    result[player] = usage.remaining_uses

        return result


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def print_player_status(tracker: UsageTracker, player_name: str):
    """Print detailed status for a player."""
    usage = tracker.get_player_status(player_name)

    print(f"\n{'='*60}")
    print(f"  PLAYER STATUS: {player_name.upper()}")
    print(f"{'='*60}")

    if not usage:
        print(f"\n  {player_name} has not been used yet.")
        print(f"  Uses remaining: {MAX_USES_PER_PLAYER}/{MAX_USES_PER_PLAYER}")
        return

    print(f"\n  Uses: {usage.times_used}/{MAX_USES_PER_PLAYER}")
    print(f"  Remaining: {usage.remaining_uses}")
    print(f"  Total Earnings: {_fmt_money(usage.total_earnings)}")

    if usage.tournaments_used:
        print(f"\n  Tournament History:")
        print(f"  {'-'*50}")
        for t in usage.tournaments_used:
            result_str = t.result if t.result else "In Progress" if t.week > 0 else "Pending"
            earnings_str = _fmt_money(t.earnings)
            print(f"  Week {t.week:2}: {t.tournament[:30]:<30} {result_str:<8} {earnings_str}")


def print_summary(tracker: UsageTracker):
    """Print overall usage summary."""
    print(f"\n{'='*70}")
    print(f"  USAGE TRACKER SUMMARY - SEASON {tracker.season}")
    print(f"{'='*70}")

    total_picks = sum(p.times_used for p in tracker.picks.values())
    total_earnings = sum(p.total_earnings for p in tracker.picks.values())

    print(f"\n  Players Used: {len(tracker.picks)}")
    print(f"  Total Picks Made: {total_picks}")
    print(f"  Total Earnings: {_fmt_money(total_earnings)}")

    # Show players by remaining uses
    print(f"\n  PLAYERS BY REMAINING USES:")
    print(f"  {'-'*60}")

    # Group by remaining uses
    by_remaining = {3: [], 2: [], 1: [], 0: []}
    for player, usage in sorted(tracker.picks.items()):
        by_remaining[usage.remaining_uses].append((player, usage))

    for remaining in [0, 1, 2]:
        if by_remaining[remaining]:
            status = "⚠️ EXHAUSTED" if remaining == 0 else f"{remaining} left"
            print(f"\n  {status}:")
            for player, usage in by_remaining[remaining]:
                earned = f"({_fmt_money(usage.total_earnings)})" if usage.total_earnings else ""
                print(f"    - {player} {earned}")


def print_lineups(tracker: UsageTracker):
    """Print weekly lineups."""
    print(f"\n{'='*70}")
    print(f"  WEEKLY LINEUPS - SEASON {tracker.season}")
    print(f"{'='*70}")

    if not tracker.weekly_lineups:
        print("\n  No lineups recorded yet.")
        return

    for week_key in sorted(tracker.weekly_lineups.keys(), key=lambda x: int(x.split('_')[1])):
        lineup = tracker.weekly_lineups[week_key]
        week = lineup.get('week', week_key)
        tournament = lineup.get('tournament', 'Unknown')
        players = lineup.get('lineup', [])
        earnings = lineup.get('earnings_earned', lineup.get('points_earned'))

        print(f"\n  Week {week}: {tournament}")
        print(f"  {'-'*50}")

        if players:
            for player in players:
                # Get player's result for this tournament
                usage = tracker.picks.get(player)
                result_str = ""
                if usage:
                    for t in usage.tournaments_used:
                        if t.tournament == tournament and t.result:
                            result_str = f" → {t.result} ({_fmt_money(t.earnings)})"
                            break
                print(f"    - {player}{result_str}")
        else:
            print(f"    (No players)")

        if earnings is not None:
            print(f"  Total: {_fmt_money(earnings)}")


def print_available(tracker: UsageTracker):
    """Print players with uses remaining, sorted by uses left."""
    print(f"\n{'='*60}")
    print(f"  PLAYERS WITH USES REMAINING")
    print(f"{'='*60}")

    if not tracker.picks:
        print("\n  No players tracked yet.")
        return

    # Sort by remaining uses (ascending) then by total earnings (descending)
    players = [(name, usage) for name, usage in tracker.picks.items() if usage.remaining_uses > 0]
    players.sort(key=lambda x: (x[1].remaining_uses, -x[1].total_earnings))

    current_remaining = None
    for player, usage in players:
        if usage.remaining_uses != current_remaining:
            current_remaining = usage.remaining_uses
            indicator = "⚠️ " if current_remaining == 1 else ""
            print(f"\n  {indicator}{current_remaining} USE{'S' if current_remaining > 1 else ''} REMAINING:")

        earned = f"({_fmt_money(usage.total_earnings)})" if usage.total_earnings else ""
        print(f"    - {player} {earned}")


# ============================================================================
# MAIN CLI
# ============================================================================

def _rebuild_season_log_from_tracker(tracker: "UsageTracker") -> None:
    """Rebuild outputs/season_log.csv after any pick change so the Live tab stays in sync."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from planning.auto_record_results import _rebuild_season_log
        data = {
            "picks": {name: usage.to_dict() for name, usage in tracker.picks.items()},
            "weekly_lineups": tracker.weekly_lineups,
        }
        _rebuild_season_log(data)
    except Exception as e:
        print(f"  (season_log rebuild skipped: {e})")


def main():
    parser = argparse.ArgumentParser(
        description="Track fantasy golf player usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add picks for a tournament
  python usage_tracker.py --add "Scottie Scheffler" "Rory McIlroy" "Jon Rahm" --tournament "Waste Management Phoenix Open"

  # Record results
  python usage_tracker.py --result "Scottie Scheffler" --tournament "Waste Management Phoenix Open" --finish "T3" --earnings 485000

  # Check player status
  python usage_tracker.py --check "Scottie Scheffler"

  # View summary
  python usage_tracker.py --summary
        """
    )

    # Actions
    parser.add_argument('--add', nargs='+', metavar='PLAYER',
                        help='Add player(s) to a tournament lineup')
    parser.add_argument('--remove', metavar='PLAYER',
                        help='Remove a player from a tournament (undo)')
    parser.add_argument('--result', metavar='PLAYER',
                        help='Record result for a player')
    parser.add_argument('--check', metavar='PLAYER',
                        help='Check usage status for a player')

    # Tournament context
    parser.add_argument('--tournament', '-t', metavar='NAME',
                        help='Tournament name (required for --add, --remove, --result)')

    # Result details
    parser.add_argument('--finish', metavar='POSITION',
                        help='Finish position (e.g., "1st", "T3", "MC")')
    parser.add_argument('--earnings', type=int, metavar='USD',
                        help='Official earnings in dollars')
    parser.add_argument('--points', type=int, metavar='PTS',
                        help=argparse.SUPPRESS)

    # Views
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Show usage summary')
    parser.add_argument('--lineups', '-l', action='store_true',
                        help='Show weekly lineups')
    parser.add_argument('--available', '-a', action='store_true',
                        help='Show players with uses remaining')

    args = parser.parse_args()

    # Initialize tracker
    tracker = UsageTracker()
    tracker.load()

    # Handle actions
    if args.add:
        if not args.tournament:
            print("Error: --tournament required with --add")
            return

        for player in args.add:
            success, message = tracker.add_pick(player, args.tournament)
            print(message)

        tracker.save()
        _rebuild_season_log_from_tracker(tracker)
        print(f"\nSaved to {TRACKER_FILE}")

    elif args.remove:
        if not args.tournament:
            print("Error: --tournament required with --remove")
            return

        success, message = tracker.remove_pick(args.remove, args.tournament)
        print(message)

        if success:
            tracker.save()
            _rebuild_season_log_from_tracker(tracker)

    elif args.result:
        if not args.tournament:
            print("Error: --tournament required with --result")
            return
        if not args.finish:
            print("Error: --finish required with --result")
            return
        earnings_value = args.earnings if args.earnings is not None else args.points
        if earnings_value is None:
            print("Error: --earnings required with --result")
            return

        success, message = tracker.record_result(
            args.result, args.tournament, args.finish, earnings_value
        )
        print(message)

        if success:
            tracker.save()
            _rebuild_season_log_from_tracker(tracker)

    elif args.check:
        print_player_status(tracker, args.check)

    elif args.summary:
        print_summary(tracker)

    elif args.lineups:
        print_lineups(tracker)

    elif args.available:
        print_available(tracker)

    else:
        # Default: show summary if data exists, otherwise show help
        if tracker.picks:
            print_summary(tracker)
        else:
            parser.print_help()
            print("\n" + "="*60)
            print("  No usage data yet. Start by adding picks:")
            print('  python usage_tracker.py --add "Player Name" --tournament "Tournament Name"')
            print("="*60)


if __name__ == "__main__":
    main()
