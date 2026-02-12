#!/usr/bin/env python3
"""
Golf Prediction Insights Generator
===================================
Uses Claude to analyze model predictions and generate narrative insights.

Provides:
- Player-specific analysis (why they're ranked high/low)
- Course fit explanations
- Form/momentum narratives
- Value picks identification
- Risk factors and caveats

Usage:
    from generate_insights import InsightsGenerator

    generator = InsightsGenerator(api_key="your-api-key")
    insights = generator.generate(predictions_df, tournament_name, course_weights)
"""

import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Any

# Import prediction tracker for learnings
try:
    from scripts.predictions.prediction_tracker import PredictionTracker
except ImportError:
    PredictionTracker = None


class InsightsGenerator:
    """Generate narrative insights from golf predictions using Claude."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the insights generator.

        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            print("Warning: No API key provided. Set ANTHROPIC_API_KEY or pass api_key parameter.")

        # Load learnings from prediction tracker
        self.learnings_context = ""
        if PredictionTracker:
            try:
                tracker = PredictionTracker()
                self.learnings_context = tracker.get_llm_context()
            except Exception:
                pass

        # Feature importance for context (from training)
        self.top_features = [
            ("world_rank", "World Ranking", 0.255),
            ("season_sg_t2g", "Tee-to-Green", 0.131),
            ("season_sg_arg", "Around the Green", 0.077),
            ("dg_fit_total", "Course Fit", 0.049),
            ("season_sg_putt", "Putting", 0.047),
            ("recent_top10s", "Recent Top-10s", 0.027),
        ]

        # Course characteristics descriptions
        self.course_profiles = {
            "high_ott": "rewards long, accurate driving",
            "high_app": "demands precise iron play",
            "high_arg": "requires excellent short game",
            "high_putt": "puts a premium on putting",
        }

    def _build_player_summary(self, row: pd.Series, course_weights: Dict[str, float]) -> Dict[str, Any]:
        """Build a structured summary of a player's key attributes."""

        # Determine course fit breakdown
        fit_components = []
        if 'dg_fit_ott' in row and pd.notna(row.get('dg_fit_ott')):
            if row['dg_fit_ott'] > 0.01:
                fit_components.append(f"driving (+{row['dg_fit_ott']:.3f})")
            elif row['dg_fit_ott'] < -0.01:
                fit_components.append(f"driving ({row['dg_fit_ott']:.3f})")

        if 'dg_fit_app' in row and pd.notna(row.get('dg_fit_app')):
            if row['dg_fit_app'] > 0.01:
                fit_components.append(f"approach (+{row['dg_fit_app']:.3f})")
            elif row['dg_fit_app'] < -0.01:
                fit_components.append(f"approach ({row['dg_fit_app']:.3f})")

        if 'dg_fit_arg' in row and pd.notna(row.get('dg_fit_arg')):
            if row['dg_fit_arg'] > 0.01:
                fit_components.append(f"short game (+{row['dg_fit_arg']:.3f})")
            elif row['dg_fit_arg'] < -0.01:
                fit_components.append(f"short game ({row['dg_fit_arg']:.3f})")

        if 'dg_fit_putt' in row and pd.notna(row.get('dg_fit_putt')):
            if row['dg_fit_putt'] > 0.01:
                fit_components.append(f"putting (+{row['dg_fit_putt']:.3f})")
            elif row['dg_fit_putt'] < -0.01:
                fit_components.append(f"putting ({row['dg_fit_putt']:.3f})")

        return {
            "name": row.get('player_name', 'Unknown'),
            "world_rank": int(row.get('world_rank', 999)) if pd.notna(row.get('world_rank')) else None,
            "win_prob": float(row.get('win_prob', 0)),
            "top5_prob": float(row.get('top5_prob', 0)),
            "top10_prob": float(row.get('top10_prob', 0)),
            "expected_value": float(row.get('expected_value', 0)),
            "sg_total": float(row.get('sg_total', 0)) if pd.notna(row.get('sg_total')) else None,
            "course_fit": float(row.get('dg_fit_total', 0)) if pd.notna(row.get('dg_fit_total')) else 0,
            "fit_components": fit_components,
            "course_history": {
                "times_played": int(row.get('hist_times_played', 0)),
                "avg_finish": float(row.get('hist_avg_finish', 40)) if pd.notna(row.get('hist_avg_finish')) else None,
                "best_finish": int(row.get('hist_best_finish', 40)) if pd.notna(row.get('hist_best_finish')) else None,
                "wins": int(row.get('hist_wins', 0)),
                "has_won": bool(row.get('has_won_here', 0)),
            },
            "recent_form": {
                "top10s_last_5": int(row.get('recent_top10s', 0)),
                "top5s_last_5": int(row.get('recent_top5s', 0)),
                "cuts_pct": float(row.get('recent_cuts_pct', 0.5)),
                "form_trend": float(row.get('form_trend', 0)),
            },
            "sg_breakdown": {
                "ott": float(row.get('season_sg_ott', 0)) if pd.notna(row.get('season_sg_ott')) else 0,
                "app": float(row.get('season_sg_app', 0)) if pd.notna(row.get('season_sg_app')) else 0,
                "arg": float(row.get('season_sg_arg', 0)) if pd.notna(row.get('season_sg_arg')) else 0,
                "putt": float(row.get('season_sg_putt', 0)) if pd.notna(row.get('season_sg_putt')) else 0,
            }
        }

    def _build_course_profile(self, course_weights: Dict[str, float], tournament_name: str) -> str:
        """Build a description of what the course rewards."""
        if not course_weights:
            return "Standard PGA Tour course with balanced skill requirements."

        # Sort weights to find primary characteristics
        weight_items = [
            ("driving", course_weights.get('ott_sg', 0.02)),
            ("approach play", course_weights.get('app_sg', 0.02)),
            ("short game", course_weights.get('arg_sg', 0.025)),
            ("putting", course_weights.get('putt_sg', 0.005)),
        ]
        weight_items.sort(key=lambda x: x[1], reverse=True)

        # Build description
        primary = weight_items[0]
        secondary = weight_items[1]

        if primary[1] > 0.05:
            emphasis = "heavily"
        elif primary[1] > 0.03:
            emphasis = "significantly"
        else:
            emphasis = "moderately"

        description = f"This course {emphasis} rewards {primary[0]}"
        if secondary[1] > 0.02:
            description += f" and {secondary[0]}"
        description += "."

        return description

    def _identify_value_picks(self, predictions_df: pd.DataFrame, top_n: int = 5) -> List[Dict]:
        """Identify players who may offer betting value."""
        value_picks = []

        # Sort by expected value
        if 'expected_value' not in predictions_df.columns:
            return value_picks

        sorted_df = predictions_df.sort_values('expected_value', ascending=False)

        for _, row in sorted_df.head(top_n * 2).iterrows():
            # Value pick criteria:
            # 1. High expected value
            # 2. World rank not top 10 (not obvious favorite)
            # 3. Good course fit or history

            world_rank = row.get('world_rank', 999)
            if pd.isna(world_rank):
                world_rank = 999

            course_fit = row.get('dg_fit_total', 0)
            if pd.isna(course_fit):
                course_fit = 0

            hist_times = row.get('hist_times_played', 0)
            hist_avg = row.get('hist_avg_finish', 40)

            # Skip obvious favorites
            if world_rank <= 10:
                continue

            # Check for value signals
            reasons = []
            if course_fit > 0.1:
                reasons.append("excellent course fit")
            if hist_times >= 3 and hist_avg < 25:
                reasons.append(f"strong course history (avg finish: {hist_avg:.0f})")
            if row.get('has_won_here', 0):
                reasons.append("previous winner here")
            if row.get('recent_top10s', 0) >= 2:
                reasons.append("hot recent form")

            if reasons:
                value_picks.append({
                    "name": row.get('player_name', 'Unknown'),
                    "world_rank": int(world_rank),
                    "win_prob": float(row.get('win_prob', 0)),
                    "expected_value": float(row.get('expected_value', 0)),
                    "reasons": reasons,
                })

            if len(value_picks) >= top_n:
                break

        return value_picks

    def _identify_fade_candidates(self, predictions_df: pd.DataFrame, top_n: int = 3) -> List[Dict]:
        """Identify players who may underperform expectations."""
        fade_candidates = []

        for _, row in predictions_df.iterrows():
            world_rank = row.get('world_rank', 999)
            if pd.isna(world_rank):
                continue

            # Look for highly ranked players with negative signals
            if world_rank > 30:
                continue

            concerns = []

            # Poor course fit
            course_fit = row.get('dg_fit_total', 0)
            if pd.notna(course_fit) and course_fit < -0.1:
                concerns.append(f"poor course fit ({course_fit:.3f})")

            # Poor course history
            hist_times = row.get('hist_times_played', 0)
            hist_avg = row.get('hist_avg_finish', 40)
            if hist_times >= 2 and hist_avg > 40:
                concerns.append(f"struggles here (avg: {hist_avg:.0f})")

            # Cold form
            if row.get('recent_cuts_pct', 1) < 0.6:
                concerns.append("missing cuts recently")
            if row.get('recent_top10s', 0) == 0 and row.get('recent_top5s', 0) == 0:
                concerns.append("no recent top-10s")

            if len(concerns) >= 2:
                fade_candidates.append({
                    "name": row.get('player_name', 'Unknown'),
                    "world_rank": int(world_rank),
                    "concerns": concerns,
                })

            if len(fade_candidates) >= top_n:
                break

        return fade_candidates

    def generate_local_insights(
        self,
        predictions_df: pd.DataFrame,
        tournament_name: str,
        course_weights: Optional[Dict[str, float]] = None,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """
        Generate insights without calling an external API.
        Uses rule-based analysis of the prediction data.

        Args:
            predictions_df: DataFrame with predictions (must include player features)
            tournament_name: Name of the tournament
            course_weights: Dict with ott_sg, app_sg, arg_sg, putt_sg weights
            top_n: Number of top players to analyze

        Returns:
            Dict with structured insights
        """
        course_weights = course_weights or {}

        # Build course profile
        course_profile = self._build_course_profile(course_weights, tournament_name)

        # Analyze top players (sorted by expected value)
        if 'expected_value' in predictions_df.columns:
            sorted_df = predictions_df.sort_values('expected_value', ascending=False)
        else:
            sorted_df = predictions_df
        top_players = sorted_df.head(top_n)
        player_analyses = []

        for _, row in top_players.iterrows():
            summary = self._build_player_summary(row, course_weights)

            # Build narrative for this player
            strengths = []
            concerns = []

            # World ranking
            if summary['world_rank'] and summary['world_rank'] <= 10:
                strengths.append(f"Elite world ranking (#{summary['world_rank']})")
            elif summary['world_rank'] and summary['world_rank'] <= 30:
                strengths.append(f"Strong world ranking (#{summary['world_rank']})")

            # Course fit
            if summary['course_fit'] > 0.15:
                strengths.append(f"Excellent course fit ({summary['course_fit']:.3f})")
            elif summary['course_fit'] > 0.05:
                strengths.append(f"Good course fit")
            elif summary['course_fit'] < -0.1:
                concerns.append(f"Poor course fit ({summary['course_fit']:.3f})")

            # Course history
            ch = summary['course_history']
            if ch['has_won']:
                strengths.append(f"Previous winner here")
            elif ch['times_played'] >= 3 and ch['avg_finish'] and ch['avg_finish'] < 20:
                strengths.append(f"Strong history (avg: {ch['avg_finish']:.0f} in {ch['times_played']} starts)")
            elif ch['times_played'] >= 2 and ch['avg_finish'] and ch['avg_finish'] > 45:
                concerns.append(f"Struggles here (avg: {ch['avg_finish']:.0f})")
            elif ch['times_played'] == 0:
                concerns.append("No course history")

            # Recent form
            rf = summary['recent_form']
            if rf['top10s_last_5'] >= 3:
                strengths.append(f"Hot form ({rf['top10s_last_5']} top-10s in last 5)")
            elif rf['top10s_last_5'] >= 2:
                strengths.append(f"Good recent form")
            elif rf['cuts_pct'] < 0.6:
                concerns.append("Inconsistent - missing cuts")

            # SG profile match to course
            sg = summary['sg_breakdown']
            if course_weights:
                # Check if player strengths match course demands
                if course_weights.get('app_sg', 0) > 0.03 and sg['app'] > 0.3:
                    strengths.append("Elite approach play suits this course")
                if course_weights.get('arg_sg', 0) > 0.04 and sg['arg'] > 0.2:
                    strengths.append("Strong short game fits course demands")
                if course_weights.get('ott_sg', 0) > 0.04 and sg['ott'] > 0.3:
                    strengths.append("Driving prowess matches course needs")

            player_analyses.append({
                "name": summary['name'],
                "probabilities": {
                    "win": f"{summary['win_prob']:.1%}",
                    "top5": f"{summary['top5_prob']:.1%}",
                    "top10": f"{summary['top10_prob']:.1%}",
                },
                "expected_value": f"${summary['expected_value']:,.0f}",
                "strengths": strengths,
                "concerns": concerns,
                "summary": summary,
            })

        # Identify value picks and fades
        value_picks = self._identify_value_picks(predictions_df)
        fade_candidates = self._identify_fade_candidates(predictions_df)

        return {
            "tournament": tournament_name,
            "course_profile": course_profile,
            "top_players": player_analyses,
            "value_picks": value_picks,
            "fade_candidates": fade_candidates,
            "methodology_note": (
                "Predictions based on strokes gained, course fit (Data Golf weights), "
                "course history, recent form, and world ranking. "
                "Course fit uses season SG stats × course importance weights."
            ),
        }

    def _build_prompt(
        self,
        tournament_name: str,
        local_insights: Dict[str, Any],
        course_weights: Dict[str, float],
        player_data: List[Dict],
        top_n: int,
    ) -> str:
        """Build the prompt for LLM insights generation."""
        # Include learnings from past predictions if available
        learnings_section = ""
        if self.learnings_context:
            learnings_section = f"""
{self.learnings_context}

IMPORTANT: Adjust your analysis based on these learnings. If a player is historically
overrated by the model, be more cautious. If underrated, consider boosting confidence.
"""

        return f"""You are a golf analytics expert providing insights for the {tournament_name}.
{learnings_section}
COURSE PROFILE:
{local_insights['course_profile']}

Course importance weights (higher = more important):
- Driving (OTT): {course_weights.get('ott_sg', 0.02):.3f}
- Approach: {course_weights.get('app_sg', 0.02):.3f}
- Short Game (ARG): {course_weights.get('arg_sg', 0.025):.3f}
- Putting: {course_weights.get('putt_sg', 0.005):.3f}

TOP {top_n} PLAYERS BY EXPECTED VALUE:
{json.dumps(player_data, indent=2)}

VALUE PICKS (outside top 10 world ranking but high EV):
{json.dumps(local_insights['value_picks'], indent=2)}

POTENTIAL FADES (ranked players with concerns):
{json.dumps(local_insights['fade_candidates'], indent=2)}

Please provide:
1. A 2-3 sentence tournament overview highlighting what type of players should thrive
2. Brief analysis of the top 3-5 favorites (2-3 sentences each) explaining their probability
3. 2-3 value picks with reasoning
4. 1-2 potential fades (highly ranked players who may underperform)
5. Key matchups or narratives to watch

Keep the analysis concise, data-driven, and actionable. Reference specific stats when making claims.
Avoid generic statements - be specific about why each player fits or doesn't fit this week."""

    def generate_ollama_insights(
        self,
        predictions_df: pd.DataFrame,
        tournament_name: str,
        course_weights: Optional[Dict[str, float]] = None,
        top_n: int = 10,
        model: str = "llama3.2",
    ) -> str:
        """
        Generate narrative insights using Ollama (free, local).

        Requires Ollama to be installed and running:
            brew install ollama
            ollama pull llama3.2
            ollama serve

        Args:
            predictions_df: DataFrame with predictions
            tournament_name: Name of the tournament
            course_weights: Course weight dict
            top_n: Number of players to analyze
            model: Ollama model to use (llama3.2, mistral, phi3, etc.)

        Returns:
            Natural language insights string
        """
        try:
            import requests
        except ImportError:
            return "Error: requests package not installed. Run: pip install requests"

        course_weights = course_weights or {}

        # Build context for the LLM
        local_insights = self.generate_local_insights(
            predictions_df, tournament_name, course_weights, top_n
        )

        # Build player data for context
        player_data = []
        for p in local_insights['top_players'][:top_n]:
            s = p['summary']
            player_data.append({
                "name": s['name'],
                "world_rank": s['world_rank'],
                "win_prob": f"{s['win_prob']:.2%}",
                "top5_prob": f"{s['top5_prob']:.2%}",
                "course_fit": f"{s['course_fit']:.3f}",
                "sg_total": s['sg_total'],
                "course_history": s['course_history'],
                "recent_form": s['recent_form'],
                "sg_breakdown": s['sg_breakdown'],
            })

        prompt = self._build_prompt(tournament_name, local_insights, course_weights, player_data, top_n)

        # Call Ollama API
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 1500,
                    }
                },
                timeout=120,
            )

            if response.status_code == 200:
                return response.json().get("response", "No response generated")
            else:
                return f"Error: Ollama returned status {response.status_code}. Is Ollama running? (ollama serve)"

        except requests.exceptions.ConnectionError:
            return (
                "Error: Cannot connect to Ollama. Make sure it's running:\n"
                "  1. Install: brew install ollama\n"
                "  2. Pull model: ollama pull llama3.2\n"
                "  3. Start server: ollama serve"
            )
        except Exception as e:
            return f"Error calling Ollama: {e}"

    def generate_llm_insights(
        self,
        predictions_df: pd.DataFrame,
        tournament_name: str,
        course_weights: Optional[Dict[str, float]] = None,
        top_n: int = 10,
        model: str = "claude-sonnet-4-20250514",
    ) -> str:
        """
        Generate narrative insights using Claude API.

        Args:
            predictions_df: DataFrame with predictions
            tournament_name: Name of the tournament
            course_weights: Course weight dict
            top_n: Number of players to analyze
            model: Claude model to use

        Returns:
            Natural language insights string
        """
        
        course_weights = course_weights or {}

        # Build context for the LLM
        local_insights = self.generate_local_insights(
            predictions_df, tournament_name, course_weights, top_n
        )

        # Build player data for context
        player_data = []
        for p in local_insights['top_players'][:top_n]:
            s = p['summary']
            player_data.append({
                "name": s['name'],
                "world_rank": s['world_rank'],
                "win_prob": f"{s['win_prob']:.2%}",
                "top5_prob": f"{s['top5_prob']:.2%}",
                "course_fit": f"{s['course_fit']:.3f}",
                "sg_total": s['sg_total'],
                "course_history": s['course_history'],
                "recent_form": s['recent_form'],
                "sg_breakdown": s['sg_breakdown'],
            })

        prompt = self._build_prompt(tournament_name, local_insights, course_weights, player_data, top_n)

        

        return prompt.content[0].text

    def format_insights_text(self, insights: Dict[str, Any]) -> str:
        """Format local insights as readable text."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"  INSIGHTS: {insights['tournament']}")
        lines.append("=" * 70)
        lines.append("")

        # Course profile
        lines.append("COURSE PROFILE:")
        lines.append(f"  {insights['course_profile']}")
        lines.append("")

        # Top players
        lines.append("TOP PLAYERS ANALYSIS:")
        lines.append("-" * 70)
        for i, player in enumerate(insights['top_players'][:5], 1):
            lines.append(f"\n{i}. {player['name']}")
            lines.append(f"   Probabilities: Win {player['probabilities']['win']}, "
                        f"Top-5 {player['probabilities']['top5']}, "
                        f"Top-10 {player['probabilities']['top10']}")
            lines.append(f"   Expected Value: {player['expected_value']}")

            if player['strengths']:
                lines.append(f"   ✓ Strengths: {', '.join(player['strengths'])}")
            if player['concerns']:
                lines.append(f"   ⚠ Concerns: {', '.join(player['concerns'])}")

        # Value picks
        if insights['value_picks']:
            lines.append("")
            lines.append("VALUE PICKS:")
            lines.append("-" * 70)
            for pick in insights['value_picks']:
                lines.append(f"  • {pick['name']} (#{pick['world_rank']}) - "
                           f"Win: {pick['win_prob']:.1%}, EV: ${pick['expected_value']:,.0f}")
                lines.append(f"    Reasons: {', '.join(pick['reasons'])}")

        # Fade candidates
        if insights['fade_candidates']:
            lines.append("")
            lines.append("POTENTIAL FADES:")
            lines.append("-" * 70)
            for fade in insights['fade_candidates']:
                lines.append(f"  • {fade['name']} (#{fade['world_rank']})")
                lines.append(f"    Concerns: {', '.join(fade['concerns'])}")

        lines.append("")
        lines.append("-" * 70)
        lines.append(f"Note: {insights['methodology_note']}")
        lines.append("")

        return "\n".join(lines)


def main():
    """Test the insights generator."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate golf prediction insights")
    parser.add_argument("--predictions", type=str, help="Path to predictions CSV")
    parser.add_argument("--tournament", type=str, default="Test Tournament")
    parser.add_argument("--use-llm", action="store_true", help="Use Claude API for insights")
    args = parser.parse_args()

    generator = InsightsGenerator()

    if args.predictions:
        df = pd.read_csv(args.predictions)
    else:
        # Demo with sample data
        print("No predictions file provided. Run with --predictions <file.csv>")
        return

    # Load course weights if available
    weights_file = Path(__file__).parent.parent.parent / "data" / "course_sg_weights.csv"
    course_weights = {}
    if weights_file.exists():
        weights_df = pd.read_csv(weights_file)
        match = weights_df[weights_df['tournament_name'].str.contains(args.tournament, case=False, na=False)]
        if len(match) > 0:
            row = match.iloc[0]
            course_weights = {
                'ott_sg': row['ott_sg'],
                'app_sg': row['app_sg'],
                'arg_sg': row['arg_sg'],
                'putt_sg': row['putt_sg'],
            }

    if args.use_llm:
        insights = generator.generate_llm_insights(df, args.tournament, course_weights)
        print(insights)
    else:
        insights = generator.generate_local_insights(df, args.tournament, course_weights)
        print(generator.format_insights_text(insights))


if __name__ == "__main__":
    main()
