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
    python usage_tracker.py --result "Scottie Scheffler" --tournament "Waste Management Phoenix Open" --finish "T3" --points 85

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
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
import csv


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
    points: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


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
    def total_points(self) -> int:
        return sum(t.points or 0 for t in self.tournaments_used)

    def to_dict(self) -> dict:
        return {
            "times_used": self.times_used,
            "tournaments_used": [t.to_dict() for t in self.tournaments_used],
            "remaining_uses": self.remaining_uses,
            "total_points": self.total_points
        }


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

        # Try partial match
        for name, info in self.schedule.items():
            if tournament.lower() in name.lower():
                return info

        # Default if not found
        return {'week': 0, 'start_date': 'Unknown'}

    def load(self) -> bool:
        """Load usage data from JSON file."""
        if not TRACKER_FILE.exists():
            return False

        with open(TRACKER_FILE, 'r') as f:
            data = json.load(f)

        # Load player picks
        for player_name, player_data in data.get('picks', {}).items():
            tournaments = [
                TournamentUse(
                    tournament=t['tournament'],
                    week=t['week'],
                    date=t.get('date', ''),
                    result=t.get('result'),
                    points=t.get('points')
                )
                for t in player_data.get('tournaments_used', [])
            ]
            self.picks[player_name] = PlayerUsage(
                player_name=player_name,
                times_used=player_data['times_used'],
                tournaments_used=tournaments
            )

        # Load weekly lineups
        self.weekly_lineups = data.get('weekly_lineups', {})

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
                "total_points": sum(p.total_points for p in self.picks.values())
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

        # Check if player exists in tracker
        if player_name not in self.picks:
            self.picks[player_name] = PlayerUsage(
                player_name=player_name,
                times_used=0,
                tournaments_used=[]
            )

        player = self.picks[player_name]

        # Check if player has uses remaining
        if player.remaining_uses <= 0:
            return False, f"❌ {player_name} has no uses remaining (used {player.times_used}/{self.max_uses})"

        # Check if already used at this tournament
        for t in player.tournaments_used:
            if t.tournament == tournament:
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
                "points_earned": None
            }

        if player_name not in self.weekly_lineups[week_key]["lineup"]:
            self.weekly_lineups[week_key]["lineup"].append(player_name)

        return True, f"✓ Added {player_name} for {tournament} (Week {week}) - {player.remaining_uses} uses remaining"

    def remove_pick(self, player_name: str, tournament: str) -> tuple[bool, str]:
        """Remove a pick (undo mistake)."""
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

    def record_result(self, player_name: str, tournament: str,
                      result: str, points: int) -> tuple[bool, str]:
        """Record the result after a tournament finishes."""
        if player_name not in self.picks:
            return False, f"❌ {player_name} not found in tracker"

        player = self.picks[player_name]

        for t in player.tournaments_used:
            if t.tournament == tournament:
                t.result = result
                t.points = points
                return True, f"✓ Recorded {player_name}: {result} ({points} pts) at {tournament}"

        return False, f"❌ {player_name} not used at {tournament}"

    def get_player_status(self, player_name: str) -> Optional[PlayerUsage]:
        """Get usage status for a player."""
        return self.picks.get(player_name)

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
    print(f"  Total Points: {usage.total_points}")

    if usage.tournaments_used:
        print(f"\n  Tournament History:")
        print(f"  {'-'*50}")
        for t in usage.tournaments_used:
            result_str = t.result if t.result else "In Progress" if t.week > 0 else "Pending"
            points_str = f"{t.points} pts" if t.points else "-"
            print(f"  Week {t.week:2}: {t.tournament[:30]:<30} {result_str:<8} {points_str}")


def print_summary(tracker: UsageTracker):
    """Print overall usage summary."""
    print(f"\n{'='*70}")
    print(f"  USAGE TRACKER SUMMARY - SEASON {tracker.season}")
    print(f"{'='*70}")

    total_picks = sum(p.times_used for p in tracker.picks.values())
    total_points = sum(p.total_points for p in tracker.picks.values())

    print(f"\n  Players Used: {len(tracker.picks)}")
    print(f"  Total Picks Made: {total_picks}")
    print(f"  Total Points: {total_points}")

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
                pts = f"({usage.total_points} pts)" if usage.total_points else ""
                print(f"    - {player} {pts}")


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
        points = lineup.get('points_earned')

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
                            result_str = f" → {t.result} ({t.points} pts)"
                            break
                print(f"    - {player}{result_str}")
        else:
            print(f"    (No players)")

        if points is not None:
            print(f"  Total: {points} pts")


def print_available(tracker: UsageTracker):
    """Print players with uses remaining, sorted by uses left."""
    print(f"\n{'='*60}")
    print(f"  PLAYERS WITH USES REMAINING")
    print(f"{'='*60}")

    if not tracker.picks:
        print("\n  No players tracked yet.")
        return

    # Sort by remaining uses (ascending) then by total points (descending)
    players = [(name, usage) for name, usage in tracker.picks.items() if usage.remaining_uses > 0]
    players.sort(key=lambda x: (x[1].remaining_uses, -x[1].total_points))

    current_remaining = None
    for player, usage in players:
        if usage.remaining_uses != current_remaining:
            current_remaining = usage.remaining_uses
            indicator = "⚠️ " if current_remaining == 1 else ""
            print(f"\n  {indicator}{current_remaining} USE{'S' if current_remaining > 1 else ''} REMAINING:")

        pts = f"({usage.total_points} pts)" if usage.total_points else ""
        print(f"    - {player} {pts}")


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Track fantasy golf player usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add picks for a tournament
  python usage_tracker.py --add "Scottie Scheffler" "Rory McIlroy" "Jon Rahm" --tournament "Waste Management Phoenix Open"

  # Record results
  python usage_tracker.py --result "Scottie Scheffler" --tournament "Waste Management Phoenix Open" --finish "T3" --points 85

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
    parser.add_argument('--points', type=int, metavar='PTS',
                        help='Points earned')

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
        print(f"\nSaved to {TRACKER_FILE}")

    elif args.remove:
        if not args.tournament:
            print("Error: --tournament required with --remove")
            return

        success, message = tracker.remove_pick(args.remove, args.tournament)
        print(message)

        if success:
            tracker.save()

    elif args.result:
        if not args.tournament:
            print("Error: --tournament required with --result")
            return
        if not args.finish:
            print("Error: --finish required with --result")
            return
        if args.points is None:
            print("Error: --points required with --result")
            return

        success, message = tracker.record_result(
            args.result, args.tournament, args.finish, args.points
        )
        print(message)

        if success:
            tracker.save()

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
