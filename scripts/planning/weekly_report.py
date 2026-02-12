#!/usr/bin/env python3
"""
Weekly Report Generator for Fantasy Golf

Generates a markdown report with:
- Tournament overview
- Top recommended picks with reasoning
- Usage status for key players
- Value plays to consider
- Strategy notes

Usage:
    python weekly_report.py                    # Report for current week
    python weekly_report.py --week 5           # Report for specific week
    python weekly_report.py --save             # Save to file
    python weekly_report.py --tournament "The Masters"  # Specific tournament
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import json

from scoring_engine import ScoringEngine, TournamentInfo, TournamentScore
from course_history import CourseHistoryDB


# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path(__file__).parent.parent.parent / "data"
REPORTS_DIR = DATA_DIR / "fantasy" / "reports"
USAGE_TRACKER_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"


# ============================================================================
# REPORT GENERATOR
# ============================================================================

class WeeklyReportGenerator:
    """Generates weekly fantasy golf reports."""

    def __init__(self):
        self.engine = ScoringEngine()
        self.usage_data = self._load_usage()

    def _load_usage(self) -> dict:
        """Load usage tracker data."""
        if not USAGE_TRACKER_FILE.exists():
            return {"picks": {}, "weekly_lineups": {}}

        with open(USAGE_TRACKER_FILE, 'r') as f:
            return json.load(f)

    def get_tournament_for_week(self, week: int) -> Optional[str]:
        """Get tournament name for a specific week."""
        for name, t in self.engine.tournaments.items():
            if t.week == week:
                return name
        return None

    def generate_report(self, tournament: str = None, week: int = None) -> str:
        """Generate the full weekly report as markdown."""

        # Determine tournament
        if tournament:
            if tournament not in self.engine.tournaments:
                return f"Tournament not found: {tournament}"
            t = self.engine.tournaments[tournament]
        elif week:
            tournament = self.get_tournament_for_week(week)
            if not tournament:
                return f"No tournament found for week {week}"
            t = self.engine.tournaments[tournament]
        else:
            tournament = self.engine.get_current_week_tournament()
            if not tournament:
                return "No current tournament found"
            t = self.engine.tournaments[tournament]

        # Build report sections
        sections = []

        # Header
        sections.append(self._generate_header(tournament, t))

        # Tournament Overview
        sections.append(self._generate_tournament_overview(tournament, t))

        # Top Recommendations
        sections.append(self._generate_recommendations(tournament, t))

        # Value Picks
        sections.append(self._generate_value_picks(tournament, t))

        # Course Specialists
        sections.append(self._generate_course_specialists(tournament))

        # Usage Status
        sections.append(self._generate_usage_status())

        # Players to Avoid
        sections.append(self._generate_avoid_list(tournament))

        # Strategy Notes
        sections.append(self._generate_strategy_notes(tournament, t))

        # Footer
        sections.append(self._generate_footer())

        return "\n".join(sections)

    def _generate_header(self, tournament: str, t: TournamentInfo) -> str:
        """Generate report header."""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""# Weekly Fantasy Golf Report
## {tournament}

**Week {t.week}** | **{t.start_date}** | **{t.course or t.location}**

*Generated: {today}*

---
"""

    def _generate_tournament_overview(self, tournament: str, t: TournamentInfo) -> str:
        """Generate tournament overview section."""
        # Get course info
        course_info = self.engine.tournament_courses.get(tournament, {})
        course_type = course_info.get("course_type", "Unknown")
        notes = course_info.get("notes", "")

        return f"""## Tournament Overview

| Attribute | Value |
|-----------|-------|
| **Purse** | ${t.purse/1e6:.1f}M |
| **Type** | {t.tournament_type} |
| **Importance Score** | {t.importance_score:.0f}/100 |
| **Course** | {t.course or 'TBD'} |
| **Course Type** | {course_type} |
| **Location** | {t.location} |

{f"**Course Notes:** {notes}" if notes else ""}

---
"""

    def _generate_recommendations(self, tournament: str, t: TournamentInfo) -> str:
        """Generate top recommendations section."""
        recommendations = self.engine.get_tournament_recommendations(tournament, top_n=10)

        lines = ["## 🎯 Top Recommendations\n"]
        lines.append("Players with the best combination of course fit, form, and strategic value.\n")
        lines.append("| Rank | Player | Score | Course Fit | Form | Uses Left | Notes |")
        lines.append("|------|--------|-------|------------|------|-----------|-------|")

        for i, score in enumerate(recommendations, 1):
            warning = ""
            if score.remaining_uses == 1:
                warning = "⚠️ Last use"
            elif score.remaining_uses == 0:
                warning = "❌ No uses"
            elif score.owgr_rank <= 10 and t.importance_score < 50:
                warning = "💡 Save?"

            notes = score.course_history_note or "No history"
            if warning:
                notes = f"{warning} - {notes}"

            lines.append(f"| {i} | **{score.player}** | {score.total_score:.0f} | "
                        f"{score.course_fit:.0f} | {score.current_form:.0f} | "
                        f"{score.remaining_uses}/3 | {notes} |")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_value_picks(self, tournament: str, t: TournamentInfo) -> str:
        """Generate value picks section."""
        min_score = 45 if t.importance_score >= 40 else 35
        value_picks = self.engine.get_value_picks(tournament, rank_min=20, rank_max=80, min_score=min_score)

        lines = ["## 💎 Value Picks\n"]
        lines.append("Lower-ranked players (20-80) with strong course fits or form.\n")

        if not value_picks:
            lines.append("*No value picks meeting criteria for this event.*\n")
        else:
            lines.append("| Rank | Player | Score | Course Fit | Why Consider |")
            lines.append("|------|--------|-------|------------|--------------|")

            for score in value_picks[:7]:
                reason = []
                if score.course_fit >= 70:
                    reason.append(f"Strong course history ({score.course_history_note})")
                elif score.course_fit >= 50:
                    reason.append(f"Decent course fit")
                if score.current_form >= 50:
                    reason.append("Good current form")

                lines.append(f"| #{score.owgr_rank} | {score.player} | {score.total_score:.0f} | "
                            f"{score.course_fit:.0f} | {', '.join(reason) or 'Scoring well'} |")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_course_specialists(self, tournament: str) -> str:
        """Generate course specialists section."""
        lines = ["## 🏌️ Course Specialists\n"]
        lines.append("Players with exceptional history at this venue.\n")

        # Get specialists from course history
        course_info = self.engine.tournament_courses.get(tournament, {})
        aliases = course_info.get("aliases", [])

        specialists = []
        if self.engine.course_db:
            for alias in aliases:
                specs = self.engine.course_db.get_course_specialists(alias, min_plays=2)
                for player, stats, fit_score in specs[:10]:
                    if fit_score >= 60:
                        specialists.append({
                            "player": player,
                            "plays": stats.times_played,
                            "wins": stats.wins,
                            "top5s": stats.top_5s,
                            "avg": stats.avg_finish,
                            "fit": fit_score
                        })
                if specialists:
                    break

        if not specialists:
            lines.append("*No significant course history data available.*\n")
        else:
            # Dedupe and sort
            seen = set()
            unique_specs = []
            for s in sorted(specialists, key=lambda x: -x["fit"]):
                if s["player"].lower() not in seen:
                    seen.add(s["player"].lower())
                    unique_specs.append(s)

            lines.append("| Player | Plays | Wins | Top 5s | Avg Finish | Fit Score |")
            lines.append("|--------|-------|------|--------|------------|-----------|")

            for s in unique_specs[:8]:
                lines.append(f"| {s['player'].title()} | {s['plays']} | {s['wins']} | "
                            f"{s['top5s']} | {s['avg']:.1f} | {s['fit']:.0f} |")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_usage_status(self) -> str:
        """Generate usage status section."""
        lines = ["## 📊 Usage Status\n"]
        lines.append("Current usage for players you've picked this season.\n")

        picks = self.usage_data.get("picks", {})

        if not picks:
            lines.append("*No picks recorded yet.*\n")
        else:
            # Group by remaining uses
            by_remaining = {0: [], 1: [], 2: [], 3: []}
            for player, info in picks.items():
                remaining = info.get("remaining_uses", 3)
                by_remaining[remaining].append({
                    "player": player,
                    "used": info.get("times_used", 0),
                    "points": info.get("total_points", 0),
                    "tournaments": [t.get("tournament", "?") for t in info.get("tournaments_used", [])]
                })

            lines.append("| Player | Used | Remaining | Points | Tournaments Used |")
            lines.append("|--------|------|-----------|--------|------------------|")

            for remaining in [0, 1, 2]:
                for p in by_remaining[remaining]:
                    status = "⚠️" if remaining == 1 else "❌" if remaining == 0 else ""
                    tourneys = ", ".join(p["tournaments"][:2])
                    if len(p["tournaments"]) > 2:
                        tourneys += f" +{len(p['tournaments'])-2}"
                    lines.append(f"| {status} {p['player']} | {p['used']}/3 | {remaining} | "
                                f"{p['points']} | {tourneys} |")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_avoid_list(self, tournament: str) -> str:
        """Generate players to avoid section."""
        lines = ["## ⚠️ Players to Avoid\n"]

        avoid_reasons = []

        # Get all scores for this tournament
        recommendations = self.engine.get_tournament_recommendations(tournament, top_n=100)

        for score in recommendations:
            reasons = []

            # No uses left
            if score.remaining_uses == 0:
                reasons.append("No uses remaining")

            # Poor course history
            if score.course_fit < 30 and "plays" in score.course_history_note:
                reasons.append(f"Poor course history ({score.course_history_note})")

            # Elite player at weak event
            if score.owgr_rank <= 5 and score.tournament_importance < 40:
                reasons.append("Elite player - save for major/signature")

            if reasons and len(avoid_reasons) < 5:
                avoid_reasons.append({
                    "player": score.player,
                    "reasons": reasons
                })

        if not avoid_reasons:
            lines.append("*No specific players to avoid this week.*\n")
        else:
            for item in avoid_reasons:
                lines.append(f"- **{item['player']}**: {'; '.join(item['reasons'])}")
            lines.append("")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_strategy_notes(self, tournament: str, t: TournamentInfo) -> str:
        """Generate strategy notes section."""
        lines = ["## 💡 Strategy Notes\n"]

        # Tournament-type specific advice
        if t.tournament_type == "Major":
            lines.append("- **Major Alert**: This is a major championship - prioritize your best players")
            lines.append("- Consider using elite players you've been saving")
            lines.append("- Course history matters more at majors - trust the specialists")
        elif t.tournament_type == "Signature":
            lines.append("- **Signature Event**: Strong field, good points opportunity")
            lines.append("- Worth using a top player if you have uses to spare")
        elif t.tournament_type == "Standard":
            lines.append("- **Standard Event**: Consider value picks and course specialists")
            lines.append("- Good week to save elite players for upcoming majors/signatures")
            lines.append("- Course fit is especially important at standard events")
        elif t.tournament_type == "Playoff":
            lines.append("- **Playoff Event**: Only top players eligible - concentrated field")
            lines.append("- Strong fields make picks more volatile")

        # Upcoming events to consider
        lines.append("\n### Upcoming Key Events")
        today = datetime.now().strftime('%Y-%m-%d')
        upcoming_majors = []
        for name, tourney in self.engine.tournaments.items():
            if tourney.start_date > today and tourney.importance_score >= 60:
                upcoming_majors.append((name, tourney))

        upcoming_majors.sort(key=lambda x: x[1].start_date)
        for name, tourney in upcoming_majors[:4]:
            lines.append(f"- **Week {tourney.week}**: {name} ({tourney.tournament_type})")

        lines.append("\n---\n")
        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return f"""## Summary

**Key Takeaways:**
1. Focus on players with strong course history at this venue
2. Balance value picks with reliable performers
3. Consider your remaining uses for each player
4. Save elite players for major championships when possible

---

*Generated by Golf Fantasy Planning System*
*Report Date: {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""

    def save_report(self, report: str, tournament: str) -> Path:
        """Save report to file."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # Generate filename
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = tournament.lower().replace(" ", "_").replace("'", "")[:30]
        filename = f"weekly_report_{safe_name}_{date_str}.md"

        filepath = REPORTS_DIR / filename
        with open(filepath, 'w') as f:
            f.write(report)

        return filepath


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate weekly fantasy golf report",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--tournament', '-t', metavar='NAME',
                        help='Generate report for specific tournament')
    parser.add_argument('--week', '-w', type=int,
                        help='Generate report for specific week number')
    parser.add_argument('--save', '-s', action='store_true',
                        help='Save report to file')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Only show file path when saving (no console output)')

    args = parser.parse_args()

    generator = WeeklyReportGenerator()

    # Determine tournament
    tournament = args.tournament
    if args.week and not tournament:
        tournament = generator.get_tournament_for_week(args.week)

    # Generate report
    report = generator.generate_report(tournament=tournament, week=args.week)

    # Output
    if args.save:
        # Determine tournament name for filename
        if not tournament:
            tournament = generator.engine.get_current_week_tournament()

        filepath = generator.save_report(report, tournament or "unknown")

        if args.quiet:
            print(filepath)
        else:
            print(report)
            print(f"\n{'='*60}")
            print(f"Report saved to: {filepath}")
    else:
        print(report)


if __name__ == "__main__":
    main()
