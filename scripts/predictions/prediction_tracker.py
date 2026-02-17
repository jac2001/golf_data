#!/usr/bin/env python3
"""
Prediction Tracker & Learning System
=====================================
Tracks model predictions vs actual results to:
1. Measure prediction accuracy over time
2. Identify systematic biases (overrating/underrating players)
3. Generate insights for model improvement
4. Feed learnings back to the LLM for better analysis

Usage:
    # Save predictions before tournament
    python prediction_tracker.py save --tournament "The Masters" --predictions outputs/masters_predictions.csv

    # After tournament, record results and analyze
    python prediction_tracker.py analyze --tournament "The Masters" --results data/results/masters_2025.csv

    # Generate learning report for LLM
    python prediction_tracker.py report --last-n 10
"""

import pandas as pd
import numpy as np
import json
import unicodedata
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import argparse
from scipy import stats


class PredictionTracker:
    """Track predictions and compare against actual results."""

    def __init__(self, data_dir: Optional[Path] = None, tracking_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("/Users/jacklegnon/Desktop/golf_data/data")
        self.tracking_dir = tracking_dir or (self.data_dir / "prediction_tracking")
        self.tracking_dir.mkdir(exist_ok=True)

        # Main tracking file
        self.tracking_file = self.tracking_dir / "prediction_history.csv"
        self.learnings_file = self.tracking_dir / "model_learnings.json"

    def save_predictions(
        self,
        predictions_df: pd.DataFrame,
        tournament_name: str,
        tournament_date: Optional[str] = None,
    ) -> str:
        """
        Save predictions before a tournament starts.

        Args:
            predictions_df: DataFrame with predictions
            tournament_name: Name of tournament
            tournament_date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Path to saved predictions file
        """
        tournament_date = tournament_date or datetime.now().strftime("%Y-%m-%d")

        # Create a clean ID for the tournament
        tournament_id = f"{tournament_date}_{tournament_name.replace(' ', '_').lower()}"

        # Save full predictions
        predictions_file = self.tracking_dir / f"pred_{tournament_id}.csv"
        predictions_df.to_csv(predictions_file, index=False)

        # Extract key predictions for tracking
        tracking_data = []
        for _, row in predictions_df.iterrows():
            tracking_data.append({
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "tournament_date": tournament_date,
                "player_name": row.get("player_name", "Unknown"),
                "player_id": row.get("player_id"),
                "predicted_win_prob": row.get("win_prob", 0),
                "predicted_top5_prob": row.get("top5_prob", 0),
                "predicted_top10_prob": row.get("top10_prob", 0),
                "predicted_top20_prob": row.get("top20_prob", 0),
                "predicted_ev": row.get("expected_value", 0),
                "world_rank": row.get("world_rank"),
                "course_fit": row.get("dg_fit_total", 0),
                # Actual results - to be filled after tournament
                "actual_position": None,
                "actual_won": None,
                "actual_top5": None,
                "actual_top10": None,
                "actual_top20": None,
                "result_recorded": False,
            })

        tracking_df = pd.DataFrame(tracking_data)

        # Append to main tracking file
        if self.tracking_file.exists():
            existing = pd.read_csv(self.tracking_file)
            # Remove any existing entries for this tournament
            existing = existing[existing["tournament_id"] != tournament_id]
            combined = pd.concat([existing, tracking_df], ignore_index=True)
        else:
            combined = tracking_df

        combined.to_csv(self.tracking_file, index=False)
        print(f"✓ Saved {len(tracking_data)} predictions for {tournament_name}")
        print(f"  File: {predictions_file}")

        return str(predictions_file)

    def record_results(
        self,
        tournament_name: str,
        results_df: pd.DataFrame,
        tournament_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record actual tournament results and compare to predictions.

        Args:
            tournament_name: Name of tournament
            results_df: DataFrame with actual results (player_name, position columns)
            tournament_date: Date to match predictions

        Returns:
            Dict with comparison metrics
        """
        if not self.tracking_file.exists():
            return {"error": "No predictions found. Run save_predictions first."}

        tracking_df = pd.read_csv(self.tracking_file)

        # Find matching tournament
        if tournament_date:
            tournament_id = f"{tournament_date}_{tournament_name.replace(' ', '_').lower()}"
            mask = tracking_df["tournament_id"] == tournament_id
        else:
            # Find most recent matching tournament name
            mask = tracking_df["tournament_name"].str.lower() == tournament_name.lower()

        if mask.sum() == 0:
            return {"error": f"No predictions found for {tournament_name}"}

        # Parse results
        def parse_position(pos):
            if pd.isna(pos):
                return 999
            pos_str = str(pos).upper().strip()
            if pos_str in ["CUT", "MC", "W/D", "WD", "DQ", "MDF"]:
                return 999
            if pos_str.startswith("T"):
                try:
                    return int(pos_str[1:])
                except:
                    return 999
            try:
                return int(pos_str)
            except:
                return 999

        results_df = results_df.copy()
        results_df["position_num"] = results_df["position"].apply(parse_position)

        # Match results to predictions
        results_lookup = {}
        for _, row in results_df.iterrows():
            name = row.get("player_name", "").strip().lower()
            results_lookup[name] = {
                "position": row["position_num"],
                "won": row["position_num"] == 1,
                "top5": row["position_num"] <= 5,
                "top10": row["position_num"] <= 10,
                "top20": row["position_num"] <= 20,
            }

        # Update tracking data
        matched = 0
        for idx in tracking_df[mask].index:
            player_name = tracking_df.loc[idx, "player_name"].strip().lower()
            if player_name in results_lookup:
                result = results_lookup[player_name]
                tracking_df.loc[idx, "actual_position"] = result["position"]
                tracking_df.loc[idx, "actual_won"] = result["won"]
                tracking_df.loc[idx, "actual_top5"] = result["top5"]
                tracking_df.loc[idx, "actual_top10"] = result["top10"]
                tracking_df.loc[idx, "actual_top20"] = result["top20"]
                tracking_df.loc[idx, "result_recorded"] = True
                matched += 1

        tracking_df.to_csv(self.tracking_file, index=False)

        # Calculate metrics
        metrics = self._calculate_metrics(tracking_df[mask & tracking_df["result_recorded"]])

        # Write a latest performance report for easy review
        try:
            report = self.generate_report(last_n=10)
            reports_dir = self.tracking_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            # Save rolling latest report
            (reports_dir / "report_latest.txt").write_text(report)
            # Save tournament-specific report
            if tournament_date:
                tournament_id = f"{tournament_date}_{tournament_name.replace(' ', '_').lower()}"
            else:
                tournament_id = tournament_name.replace(' ', '_').lower()
            (reports_dir / f"report_{tournament_id}.txt").write_text(report)
        except Exception as e:
            print(f"⚠️  Could not write performance report: {e}")

        print(f"✓ Recorded results for {matched} players in {tournament_name}")
        return metrics

    def _calculate_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate prediction accuracy metrics."""
        if len(df) == 0:
            return {"error": "No matched results"}

        metrics = {
            "n_predictions": len(df),
            "n_with_results": df["result_recorded"].sum() if "result_recorded" in df.columns else len(df),
        }

        # Brier scores (lower is better, 0 is perfect)
        for target in ["won", "top5", "top10", "top20"]:
            pred_col = f"predicted_{target}_prob"
            actual_col = f"actual_{target}"

            if pred_col in df.columns and actual_col in df.columns:
                valid = df[df[actual_col].notna()]
                if len(valid) > 0:
                    predictions = valid[pred_col].values
                    actuals = valid[actual_col].astype(float).values
                    brier = np.mean((predictions - actuals) ** 2)
                    metrics[f"brier_{target}"] = round(brier, 4)

                    # Calibration: predicted prob vs actual rate
                    metrics[f"predicted_rate_{target}"] = round(predictions.mean(), 4)
                    metrics[f"actual_rate_{target}"] = round(actuals.mean(), 4)

        # Top picks accuracy
        top_10_predicted = df.nsmallest(10, "predicted_win_prob", keep="first")
        if "actual_top10" in top_10_predicted.columns:
            top10_in_top10 = top_10_predicted["actual_top10"].sum()
            metrics["top10_picks_hit_rate"] = round(top10_in_top10 / 10, 2)

        # Course fit analysis
        if "course_fit" in df.columns and "actual_position" in df.columns:
            valid = df[df["actual_position"].notna() & (df["actual_position"] < 100)]
            if len(valid) > 0:
                correlation = valid["course_fit"].corr(valid["actual_position"])
                # Negative correlation is good (higher fit = lower position number = better)
                metrics["course_fit_correlation"] = round(correlation, 3)

        return metrics

    def get_learnings(self, last_n_tournaments: int = 10) -> Dict[str, Any]:
        """
        Analyze prediction history to generate learnings for the model.

        Args:
            last_n_tournaments: Number of recent tournaments to analyze

        Returns:
            Dict with learnings and insights
        """
        if not self.tracking_file.exists():
            return {"error": "No prediction history found"}

        df = pd.read_csv(self.tracking_file)
        df = df[df["result_recorded"] == True]

        if len(df) == 0:
            return {"error": "No results recorded yet"}

        # Get unique tournaments, sorted by date
        tournaments = df.groupby("tournament_id").first().reset_index()
        tournaments = tournaments.sort_values("tournament_date", ascending=False)
        recent_tournament_ids = tournaments.head(last_n_tournaments)["tournament_id"].tolist()

        recent_df = df[df["tournament_id"].isin(recent_tournament_ids)]

        learnings = {
            "summary": {
                "tournaments_analyzed": len(recent_tournament_ids),
                "total_predictions": len(recent_df),
            },
            "accuracy": {},
            "biases": [],
            "player_patterns": [],
            "course_fit_effectiveness": {},
        }

        # Overall accuracy metrics
        for target in ["won", "top5", "top10"]:
            pred_col = f"predicted_{target}_prob"
            actual_col = f"actual_{target}"

            if pred_col in recent_df.columns and actual_col in recent_df.columns:
                valid = recent_df[recent_df[actual_col].notna()]
                if len(valid) > 0:
                    predictions = valid[pred_col].values
                    actuals = valid[actual_col].astype(float).values

                    brier = np.mean((predictions - actuals) ** 2)
                    avg_pred = predictions.mean()
                    avg_actual = actuals.mean()

                    learnings["accuracy"][target] = {
                        "brier_score": round(brier, 4),
                        "avg_predicted": round(avg_pred, 4),
                        "avg_actual": round(avg_actual, 4),
                        "calibration_error": round(avg_pred - avg_actual, 4),
                    }

                    # Detect systematic bias
                    if avg_pred > avg_actual * 1.2:
                        learnings["biases"].append(
                            f"Model OVERESTIMATES {target} probability by {((avg_pred/avg_actual)-1)*100:.0f}%"
                        )
                    elif avg_pred < avg_actual * 0.8:
                        learnings["biases"].append(
                            f"Model UNDERESTIMATES {target} probability by {((avg_actual/avg_pred)-1)*100:.0f}%"
                        )

        # Player-specific patterns (who do we consistently over/underrate)
        player_stats = recent_df.groupby("player_name").agg({
            "predicted_top10_prob": "mean",
            "actual_top10": lambda x: x.astype(float).mean(),
            "tournament_id": "count",
        }).reset_index()
        player_stats.columns = ["player_name", "avg_pred_top10", "actual_top10_rate", "n_tournaments"]

        # Players we consistently overrate
        player_stats["error"] = player_stats["avg_pred_top10"] - player_stats["actual_top10_rate"]
        overrated = player_stats[
            (player_stats["n_tournaments"] >= 3) & (player_stats["error"] > 0.15)
        ].nlargest(5, "error")

        for _, row in overrated.iterrows():
            learnings["player_patterns"].append({
                "player": row["player_name"],
                "pattern": "OVERRATED",
                "predicted_top10": f"{row['avg_pred_top10']:.1%}",
                "actual_top10": f"{row['actual_top10_rate']:.1%}",
                "n_tournaments": int(row["n_tournaments"]),
            })

        # Players we consistently underrate
        underrated = player_stats[
            (player_stats["n_tournaments"] >= 3) & (player_stats["error"] < -0.15)
        ].nsmallest(5, "error")

        for _, row in underrated.iterrows():
            learnings["player_patterns"].append({
                "player": row["player_name"],
                "pattern": "UNDERRATED",
                "predicted_top10": f"{row['avg_pred_top10']:.1%}",
                "actual_top10": f"{row['actual_top10_rate']:.1%}",
                "n_tournaments": int(row["n_tournaments"]),
            })

        # Course fit effectiveness
        if "course_fit" in recent_df.columns:
            valid = recent_df[recent_df["actual_position"].notna() & (recent_df["actual_position"] < 100)]
            if len(valid) > 0:
                correlation = valid["course_fit"].corr(valid["actual_position"])
                learnings["course_fit_effectiveness"] = {
                    "correlation_with_finish": round(correlation, 3),
                    "interpretation": (
                        "Course fit is predictive" if correlation < -0.1
                        else "Course fit has weak signal" if correlation < 0.1
                        else "Course fit may need recalibration"
                    ),
                }

        # Save learnings
        self._save_learnings(learnings)

        return learnings

    def _save_learnings(self, learnings: Dict[str, Any]):
        """Save learnings to file for LLM context."""
        with open(self.learnings_file, "w") as f:
            json.dump(learnings, f, indent=2)
        print(f"✓ Saved learnings to {self.learnings_file}")

    def get_llm_context(self) -> str:
        """
        Get formatted learnings as context for LLM insights.

        Returns:
            String formatted for LLM prompt injection
        """
        if not self.learnings_file.exists():
            return ""

        with open(self.learnings_file, "r") as f:
            learnings = json.load(f)

        context_parts = ["## MODEL LEARNINGS FROM PAST PREDICTIONS\n"]

        # Summary
        if "summary" in learnings:
            s = learnings["summary"]
            context_parts.append(
                f"Based on {s.get('tournaments_analyzed', 0)} recent tournaments "
                f"({s.get('total_predictions', 0)} predictions):\n"
            )

        # Biases
        if learnings.get("biases"):
            context_parts.append("\n### Known Biases:")
            for bias in learnings["biases"]:
                context_parts.append(f"- {bias}")

        # Player patterns
        if learnings.get("player_patterns"):
            context_parts.append("\n### Player-Specific Patterns:")
            for p in learnings["player_patterns"]:
                context_parts.append(
                    f"- {p['player']}: {p['pattern']} "
                    f"(predicted {p['predicted_top10']} top-10, actual {p['actual_top10']})"
                )

        # Course fit
        if learnings.get("course_fit_effectiveness"):
            cfe = learnings["course_fit_effectiveness"]
            context_parts.append(f"\n### Course Fit: {cfe.get('interpretation', 'Unknown')}")

        return "\n".join(context_parts)

    def generate_report(self, last_n: int = 10) -> str:
        """Generate a human-readable report of prediction performance."""
        learnings = self.get_learnings(last_n)

        if "error" in learnings:
            return f"Error: {learnings['error']}"

        lines = [
            "=" * 70,
            "  PREDICTION PERFORMANCE REPORT",
            "=" * 70,
            "",
        ]

        # Summary
        s = learnings.get("summary", {})
        lines.append(f"Tournaments Analyzed: {s.get('tournaments_analyzed', 0)}")
        lines.append(f"Total Predictions: {s.get('total_predictions', 0)}")
        lines.append("")

        # Accuracy
        lines.append("ACCURACY METRICS:")
        lines.append("-" * 40)
        for target, metrics in learnings.get("accuracy", {}).items():
            lines.append(f"\n  {target.upper()}:")
            lines.append(f"    Brier Score: {metrics.get('brier_score', 'N/A')}")
            lines.append(f"    Avg Predicted: {metrics.get('avg_predicted', 0):.1%}")
            lines.append(f"    Avg Actual: {metrics.get('avg_actual', 0):.1%}")
            cal_error = metrics.get('calibration_error', 0)
            lines.append(f"    Calibration Error: {cal_error:+.1%}")

        # Biases
        if learnings.get("biases"):
            lines.append("\n\nKNOWN BIASES:")
            lines.append("-" * 40)
            for bias in learnings["biases"]:
                lines.append(f"  ⚠️  {bias}")

        # Player patterns
        if learnings.get("player_patterns"):
            lines.append("\n\nPLAYER PATTERNS:")
            lines.append("-" * 40)
            overrated = [p for p in learnings["player_patterns"] if p["pattern"] == "OVERRATED"]
            underrated = [p for p in learnings["player_patterns"] if p["pattern"] == "UNDERRATED"]

            if overrated:
                lines.append("\n  Players we OVERRATE:")
                for p in overrated:
                    lines.append(f"    - {p['player']}: pred {p['predicted_top10']}, actual {p['actual_top10']}")

            if underrated:
                lines.append("\n  Players we UNDERRATE:")
                for p in underrated:
                    lines.append(f"    - {p['player']}: pred {p['predicted_top10']}, actual {p['actual_top10']}")

        # Course fit
        cfe = learnings.get("course_fit_effectiveness", {})
        if cfe:
            lines.append("\n\nCOURSE FIT ANALYSIS:")
            lines.append("-" * 40)
            lines.append(f"  Correlation with finish: {cfe.get('correlation_with_finish', 'N/A')}")
            lines.append(f"  Assessment: {cfe.get('interpretation', 'Unknown')}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)

    def evaluate_picks_log(
        self,
        tournament_name: str,
        picks_log_path: Optional[Path] = None,
        results_path: Optional[Path] = None,
        year: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Evaluate logged picks against actual results."""
        outputs_dir = self.data_dir.parent / "outputs"
        picks_log_path = picks_log_path or (outputs_dir / "picks_log.csv")
        if not picks_log_path.exists():
            return {"error": f"Picks log not found: {picks_log_path}"}

        picks_df = pd.read_csv(picks_log_path)
        if picks_df.empty:
            return {"error": "Picks log is empty"}

        # Filter picks by tournament name
        mask = picks_df["tournament_name"].str.lower() == tournament_name.lower()
        if mask.sum() == 0:
            return {"error": f"No picks found for {tournament_name}"}
        picks = picks_df[mask].copy()

        # Load results
        if results_path:
            results_df = pd.read_csv(results_path)
        else:
            if year is None:
                years = []
                for p in (self.data_dir / "historical").glob("leaderboards_*.csv"):
                    try:
                        years.append(int(p.stem.split("_")[-1]))
                    except Exception:
                        continue
                year = max(years) if years else None
            if year is None:
                return {"error": "Could not determine results year. Provide --year or --results."}
            lb_path = self.data_dir / "historical" / f"leaderboards_{year}.csv"
            if not lb_path.exists():
                return {"error": f"Results file not found: {lb_path}"}
            results_df = pd.read_csv(lb_path)

        # Filter results to tournament (by name)
        if tournament_name and "tournament_name" in results_df.columns:
            name_mask = results_df["tournament_name"].str.lower().str.contains(
                tournament_name.lower(), na=False
            )
            results_df = results_df[name_mask].copy()

        # Normalize earnings
        def _parse_money(val):
            if pd.isna(val):
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            cleaned = str(val).replace("$", "").replace(",", "").strip()
            try:
                return float(cleaned)
            except Exception:
                return 0.0

        if "earnings" in results_df.columns:
            results_df["earnings_num"] = results_df["earnings"].apply(_parse_money)
        else:
            results_df["earnings_num"] = 0.0

        # Prefer match by player_id if available
        results_lookup = {}
        if "player_id" in results_df.columns:
            for _, row in results_df.iterrows():
                results_lookup[int(row["player_id"])] = row

        # Fallback name normalization
        def _norm(n: str) -> str:
            n = str(n or "").lower().strip()
            n = n.replace(",", " ")
            n = " ".join(n.split())
            return n

        name_lookup = {}
        for _, row in results_df.iterrows():
            name_lookup[_norm(row.get("player_name", ""))] = row

        # Join and compute metrics
        rows = []
        for _, p in picks.iterrows():
            pid = p.get("player_id")
            result = None
            if pd.notna(pid):
                try:
                    result = results_lookup.get(int(pid))
                except Exception:
                    result = None
            if result is None:
                result = name_lookup.get(_norm(p.get("player_name", "")))

            position = None
            earnings = 0.0
            if result is not None:
                position = result.get("position")
                earnings = float(result.get("earnings_num", 0.0))

            rows.append({
                "player_name": p.get("player_name"),
                "player_id": pid,
                "expected_value": p.get("expected_value", 0),
                "win_prob": p.get("win_prob", 0),
                "top5_prob": p.get("top5_prob", 0),
                "top10_prob": p.get("top10_prob", 0),
                "position": position,
                "earnings": earnings,
                "made_cut": False if position in ["CUT", "MC", "MDF", "DQ", "WD"] else True,
            })

        result_df = pd.DataFrame(rows)

        total_ev = result_df["expected_value"].fillna(0).sum()
        total_earnings = result_df["earnings"].fillna(0).sum()
        roi = (total_earnings - total_ev) / total_ev if total_ev > 0 else 0.0

        summary = {
            "tournament": tournament_name,
            "picks": len(result_df),
            "total_expected_value": total_ev,
            "total_earnings": total_earnings,
            "roi": roi,
            "top5_hits": (result_df["position"].astype(str).str.replace("T", "", regex=False).astype("Int64") <= 5).sum()
            if len(result_df) else 0,
            "top10_hits": (result_df["position"].astype(str).str.replace("T", "", regex=False).astype("Int64") <= 10).sum()
            if len(result_df) else 0,
        }

        if output_path:
            lines = [
                "=" * 70,
                f"PICKS PERFORMANCE REPORT: {tournament_name}",
                "=" * 70,
                f"Picks: {summary['picks']}",
                f"Total EV: ${summary['total_expected_value']:,.0f}",
                f"Total Earnings: ${summary['total_earnings']:,.0f}",
                f"ROI: {summary['roi']:.2%}",
                f"Top-5 Hits: {summary['top5_hits']}",
                f"Top-10 Hits: {summary['top10_hits']}",
                "",
            ]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n".join(lines))

        return summary

    def generate_calibration_factors(
        self,
        output_path: Optional[Path] = None,
        min_tournaments: int = 3,
    ) -> Dict[str, Any]:
        """
        Build data-driven calibration factors by tournament type from tracked results.

        Returns a dict with global + per-tournament-type scale factors.
        """
        if not self.tracking_file.exists():
            return {"error": "No prediction_history.csv found"}

        df = pd.read_csv(self.tracking_file)
        df = df[df["result_recorded"] == True].copy()
        
        
        
        if "actual_top20" not in df.columns:
            if "actual_position" in df.columns:
                df["actual_top20"] = df["actual_position"].apply(
                    lambda p: (p < 100) and (int(p) <= 20) if pd.notna(p) else False
                )
            else:
                df["actual_top20"] = False
        
        
        if "predicted_top20_prob" not in df.columns:
            if "predicted_top10_prob" in df.columns and "predicted_top5_prob" in df.columns:
                df["predicted_top20_prob"] = (
                    df["predicted_top10_prob"] +
                    (df["predicted_top10_prob"] - df["predicted_top5_prob"]) * 1.2
                ).clip(0, 0.95)
            else:
                df["predicted_top20_prob"] = 0.0
        
        
        
        
        if df.empty:
            return {"error": "No recorded results in prediction history"}

        # Determine tournament type using TournamentCalendar
        try:
            from scripts.predictions.usage_optimizer import TournamentCalendar
            calendar = TournamentCalendar()
        except Exception:
            calendar = None

        def get_tier(name: str) -> str:
            if not calendar:
                return "Standard"
            tier = calendar.get_tournament_tier(name or "")
            # Normalize to title case
            tier = tier.title() if isinstance(tier, str) else "Standard"
            return tier

        df["tournament_type"] = df["tournament_name"].apply(get_tier)

        # Field strength bucket by median world rank (lower = stronger field)
        def field_strength_bucket(median_rank: float) -> str:
            if pd.isna(median_rank):
                return "unknown"
            if median_rank <= 30:
                return "strong"
            if median_rank <= 60:
                return "medium"
            return "weak"

        med_by_tournament = (
            df.groupby("tournament_id")["world_rank"]
            .median()
            .rename("field_strength_median_rank")
        )
        df = df.join(med_by_tournament, on="tournament_id")
        df["field_strength_bucket"] = df["field_strength_median_rank"].apply(field_strength_bucket)

        # Aggregate by tournament (to count tournaments)
        tournament_counts = df[["tournament_id", "tournament_type"]].drop_duplicates()
        type_counts = tournament_counts["tournament_type"].value_counts().to_dict()

        def scale_factor(actual, predicted):
            if predicted <= 0:
                return 1.0
            scale = actual / predicted
            return float(max(0.1, min(1.5, scale)))

        factors = {
            "global": {},
            "by_tournament_type": {},
            "by_field_strength": {},
            "by_tournament_type_field_strength": {},
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "tournaments_by_type": type_counts,
                "field_strength_thresholds": {"strong": "<=30", "medium": "31-60", "weak": ">60"},
                "min_tournaments": min_tournaments,
            },
        }

        # Global factors
        for prob, actual_col in [
            ("win_prob", "actual_won"),
            ("top5_prob", "actual_top5"),
            ("top10_prob", "actual_top10"),
            ("top20_prob", "actual_top20")
        ]:
            avg_pred = df[f"predicted_{prob}"].mean()
            avg_actual = df[actual_col].mean()
            factors["global"][prob] = {"scale_factor": scale_factor(avg_actual, avg_pred), "buckets": {}}

        # Per tournament type
        for t_type, group in df.groupby("tournament_type"):
            # Skip if not enough tournaments
            if type_counts.get(t_type, 0) < min_tournaments:
                continue
            type_block = {}
            for prob, actual_col in [
                ("win_prob", "actual_won"),
                ("top5_prob", "actual_top5"),
                ("top10_prob", "actual_top10"),
            ]:
                avg_pred = group[f"predicted_{prob}"].mean()
                avg_actual = group[actual_col].mean()
                type_block[prob] = {"scale_factor": scale_factor(avg_actual, avg_pred), "buckets": {}}
            factors["by_tournament_type"][t_type] = type_block

        # Per field strength bucket
        for bucket, group in df.groupby("field_strength_bucket"):
            if group["tournament_id"].nunique() < min_tournaments:
                continue
            bucket_block = {}
            for prob, actual_col in [
                ("win_prob", "actual_won"),
                ("top5_prob", "actual_top5"),
                ("top10_prob", "actual_top10"),
                ("top20_prob", "actual_top20"),
            ]:
                avg_pred = group[f"predicted_{prob}"].mean()
                avg_actual = group[actual_col].mean()
                bucket_block[prob] = {"scale_factor": scale_factor(avg_actual, avg_pred), "buckets": {}}
            factors["by_field_strength"][bucket] = bucket_block

        # Combined tournament type + field strength
        for (t_type, bucket), group in df.groupby(["tournament_type", "field_strength_bucket"]):
            if group["tournament_id"].nunique() < min_tournaments:
                continue
            block = {}
            for prob, actual_col in [
                ("win_prob", "actual_won"),
                ("top5_prob", "actual_top5"),
                ("top10_prob", "actual_top10"),
                ("top20_prob", "actual_top20"),
            ]:
                avg_pred = group[f"predicted_{prob}"].mean()
                avg_actual = group[actual_col].mean()
                block[prob] = {"scale_factor": scale_factor(avg_actual, avg_pred), "buckets": {}}
            factors["by_tournament_type_field_strength"][f"{t_type}|{bucket}"] = block

        # Save to calibration_factors.json
        output_path = output_path or (self.tracking_dir / "calibration_factors.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(factors, f, indent=2)

        return factors

    def analyze_calibration(self, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Detailed probability calibration analysis.

        Analyzes whether predicted probabilities match actual outcomes.
        E.g., are players with 5% win probability actually winning ~5% of time?

        Returns:
            Dict with calibration metrics by probability bucket
        """
        if df is None:
            if not self.tracking_file.exists():
                return {"error": "No prediction history found"}
            df = pd.read_csv(self.tracking_file)
            df = df[df["result_recorded"] == True]








        if len(df) == 0:
            return {"error": "No results recorded yet"}

        calibration = {
            "win_prob": self._calibrate_probability_buckets(df, "predicted_win_prob", "actual_won"),
            "top5_prob": self._calibrate_probability_buckets(df, "predicted_top5_prob", "actual_top5"),
            "top10_prob": self._calibrate_probability_buckets(df, "predicted_top10_prob", "actual_top10"),
            "top20_prob": self._calibrate_probability_buckets(df, "predicted_top20_prob", "actual_top20")
        }

        # Overall calibration summary
        calibration["summary"] = self._calculate_calibration_summary(calibration)

        return calibration

    def _calibrate_probability_buckets(
        self,
        df: pd.DataFrame,
        pred_col: str,
        actual_col: str
    ) -> Dict[str, Any]:
        """Analyze calibration by probability buckets."""
        if pred_col not in df.columns or actual_col not in df.columns:
            return {"error": f"Missing columns: {pred_col} or {actual_col}"}

        valid = df[[pred_col, actual_col]].dropna()
        if len(valid) == 0:
            return {"error": "No valid data"}

        # Define buckets based on probability type
        if "win" in pred_col:
            # Win prob buckets: 0-1%, 1-2%, 2-5%, 5-10%, 10-20%, 20%+
            buckets = [0, 0.01, 0.02, 0.05, 0.10, 0.20, 1.0]
            bucket_names = ["0-1%", "1-2%", "2-5%", "5-10%", "10-20%", "20%+"]
        else:
            # Top5/Top10 buckets: 0-5%, 5-10%, 10-20%, 20-30%, 30-50%, 50%+
            buckets = [0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.0]
            bucket_names = ["0-5%", "5-10%", "10-20%", "20-30%", "30-50%", "50%+"]

        bucket_results = []
        for i in range(len(buckets) - 1):
            low, high = buckets[i], buckets[i + 1]
            mask = (valid[pred_col] >= low) & (valid[pred_col] < high)
            bucket_df = valid[mask]

            if len(bucket_df) > 0:
                avg_pred = bucket_df[pred_col].mean()
                actual_rate = bucket_df[actual_col].astype(float).mean()
                n_samples = len(bucket_df)

                # Calculate calibration error for this bucket
                calibration_error = avg_pred - actual_rate

                bucket_results.append({
                    "bucket": bucket_names[i],
                    "n_samples": n_samples,
                    "avg_predicted": round(avg_pred, 4),
                    "actual_rate": round(actual_rate, 4),
                    "calibration_error": round(calibration_error, 4),
                    "direction": "OVERCONFIDENT" if calibration_error > 0.02 else
                                 "UNDERCONFIDENT" if calibration_error < -0.02 else "CALIBRATED",
                })

        # Expected Calibration Error (ECE) - weighted average of absolute calibration errors
        total_samples = sum(b["n_samples"] for b in bucket_results)
        ece = sum(
            abs(b["calibration_error"]) * b["n_samples"] / total_samples
            for b in bucket_results
        ) if total_samples > 0 else 0

        return {
            "buckets": bucket_results,
            "expected_calibration_error": round(ece, 4),
            "total_samples": total_samples,
        }

    def _calculate_calibration_summary(self, calibration: Dict[str, Any]) -> Dict[str, Any]:
        """Generate overall calibration summary with recommendations."""
        summary = {
            "overall_assessment": "",
            "recommendations": [],
        }

        issues = []

        for prob_type in ["win_prob", "top5_prob", "top10_prob"]:
            if prob_type not in calibration or "error" in calibration[prob_type]:
                continue

            ece = calibration[prob_type].get("expected_calibration_error", 0)

            if ece > 0.05:
                issues.append(f"{prob_type}: poorly calibrated (ECE={ece:.1%})")
            elif ece > 0.02:
                issues.append(f"{prob_type}: moderately calibrated (ECE={ece:.1%})")

            # Check for systematic over/under confidence
            buckets = calibration[prob_type].get("buckets", [])
            overconfident = sum(1 for b in buckets if b.get("direction") == "OVERCONFIDENT")
            underconfident = sum(1 for b in buckets if b.get("direction") == "UNDERCONFIDENT")

            if overconfident > len(buckets) * 0.6:
                summary["recommendations"].append(
                    f"Reduce {prob_type} estimates - model is systematically overconfident"
                )
            elif underconfident > len(buckets) * 0.6:
                summary["recommendations"].append(
                    f"Increase {prob_type} estimates - model is systematically underconfident"
                )

        if not issues:
            summary["overall_assessment"] = "Model is well-calibrated across all probability types"
        elif len(issues) == 1:
            summary["overall_assessment"] = f"Model has minor calibration issues: {issues[0]}"
        else:
            summary["overall_assessment"] = f"Model needs calibration work: {'; '.join(issues)}"

        return summary

    def analyze_feature_importance(self, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Analyze which features are most predictive of actual results.

        Examines correlation between features (course_fit, world_rank, predicted_ev)
        and actual finishing position.

        Returns:
            Dict with feature importance rankings and correlations
        """
        if df is None:
            if not self.tracking_file.exists():
                return {"error": "No prediction history found"}
            df = pd.read_csv(self.tracking_file)
            df = df[df["result_recorded"] == True]

        if len(df) == 0:
            return {"error": "No results recorded yet"}

        # Filter to players who made the cut
        valid = df[df["actual_position"].notna() & (df["actual_position"] < 100)].copy()

        if len(valid) < 10:
            return {"error": "Not enough data for feature analysis"}

        feature_analysis = {}

        # Features to analyze (if available)
        features = {
            "course_fit": "Course Fit Score",
            "world_rank": "World Ranking",
            "predicted_ev": "Expected Value",
            "predicted_win_prob": "Win Probability",
            "predicted_top10_prob": "Top-10 Probability",
        }

        for feature, name in features.items():
            if feature not in valid.columns:
                continue

            feature_data = valid[[feature, "actual_position"]].dropna()
            if len(feature_data) < 10:
                continue

            # Calculate correlation (negative correlation means higher feature = better finish)
            correlation, p_value = stats.pearsonr(
                feature_data[feature],
                feature_data["actual_position"]
            )

            # For world_rank, positive correlation is expected (lower rank = better finish)
            is_predictive = (
                (feature == "world_rank" and correlation > 0.1 and p_value < 0.05) or
                (feature != "world_rank" and correlation < -0.1 and p_value < 0.05)
            )

            feature_analysis[feature] = {
                "name": name,
                "correlation": round(correlation, 3),
                "p_value": round(p_value, 4),
                "is_statistically_significant": p_value < 0.05,
                "is_predictive": is_predictive,
                "interpretation": self._interpret_feature_correlation(feature, correlation, p_value),
            }

        # Rank features by predictive power
        ranked = sorted(
            feature_analysis.items(),
            key=lambda x: abs(x[1]["correlation"]) if x[1]["is_statistically_significant"] else 0,
            reverse=True
        )

        return {
            "features": feature_analysis,
            "feature_ranking": [f[0] for f in ranked],
            "most_predictive": ranked[0][0] if ranked else None,
            "least_predictive": ranked[-1][0] if ranked else None,
            "n_samples": len(valid),
        }

    def _interpret_feature_correlation(self, feature: str, corr: float, p_value: float) -> str:
        """Generate human-readable interpretation of feature correlation."""
        if p_value >= 0.05:
            return "Not statistically significant - unreliable signal"

        abs_corr = abs(corr)

        if feature == "world_rank":
            # For world rank, positive correlation means higher rank (worse) = worse finish
            if corr > 0.3:
                return "Strong predictor - world ranking reliably predicts performance"
            elif corr > 0.15:
                return "Moderate predictor - world ranking has useful signal"
            else:
                return "Weak predictor - world ranking alone is insufficient"
        else:
            # For other features, negative correlation means higher score = better (lower) finish
            if abs_corr > 0.3:
                return f"Strong predictor - {'higher' if corr < 0 else 'lower'} {feature} = better finish"
            elif abs_corr > 0.15:
                return f"Moderate predictor - useful but not definitive"
            else:
                return "Weak predictor - consider reducing weight in model"

    def compare_predictions_to_results(
        self,
        predictions_file: str,
        results_df: pd.DataFrame,
        tournament_name: str,
    ) -> Dict[str, Any]:
        """
        Direct comparison of predictions file to tournament results.

        This is a convenience method to analyze a single tournament's predictions
        against actual results without requiring pre-saved tracking data.

        Args:
            predictions_file: Path to predictions CSV
            results_df: DataFrame with actual results
            tournament_name: Name for reporting

        Returns:
            Comprehensive analysis dict
        """
        predictions_df = pd.read_csv(predictions_file)

        # Filter results to the tournament (best effort)
        def normalize_tournament(name: str) -> str:
            name = str(name or "").lower().strip()
            name = name.replace("&", "and")
            name = re.sub(r"[^a-z0-9\\s]", "", name)
            name = re.sub(r"\\s+", " ", name)
            # remove leading "the"
            if name.startswith("the "):
                name = name[4:]
            return name

        if "tournament_name" in results_df.columns and tournament_name:
            t_key = normalize_tournament(tournament_name)
            results_df = results_df[
                results_df["tournament_name"].apply(normalize_tournament).str.contains(t_key, na=False)
            ].copy()

        # Normalize player names for matching
        def normalize_name(name: str) -> str:
            if pd.isna(name):
                return ""
            name = str(name).strip().lower()
            # Remove accents
            name = unicodedata.normalize('NFKD', name)
            name = ''.join(c for c in name if not unicodedata.combining(c))
            # Handle "Last, First" format
            if ", " in name:
                parts = name.split(", ", 1)
                name = f"{parts[1]} {parts[0]}"
            return name

        # Identify name/position columns (allow flexible input formats)
        name_cols = ["player_name", "player", "name", "golfer", "playerName"]
        pos_cols = ["position", "position_num", "pos", "finish", "result", "finishing_position"]

        name_col = next((c for c in name_cols if c in results_df.columns), None)
        pos_col = next((c for c in pos_cols if c in results_df.columns), None)

        if not name_col or not pos_col:
            return {
                "error": "Results file missing required columns",
                "details": {
                    "found_columns": list(results_df.columns),
                    "expected_name_columns": name_cols,
                    "expected_position_columns": pos_cols,
                },
            }

        # Build results lookup
        results_lookup = {}
        for _, row in results_df.iterrows():
            name = normalize_name(row.get(name_col, ""))
            pos = row.get(pos_col, 999)

            # Parse position
            if isinstance(pos, str):
                pos = pos.upper().strip()
                if pos in ["CUT", "MC", "W/D", "WD", "DQ", "MDF"]:
                    pos_num = 999
                elif pos.startswith("T"):
                    try:
                        pos_num = int(pos[1:])
                    except:
                        pos_num = 999
                else:
                    try:
                        pos_num = int(pos)
                    except:
                        pos_num = 999
            else:
                try:
                    pos_num = int(pos) if not pd.isna(pos) else 999
                except Exception:
                    pos_num = 999

            results_lookup[name] = {
                "position": pos_num,
                "won": pos_num == 1,
                "top5": pos_num <= 5,
                "top10": pos_num <= 10,
                "made_cut": pos_num < 100,
            }

        # Match predictions to results
        matched_data = []
        unmatched_predictions = []

        for _, pred_row in predictions_df.iterrows():
            pred_name = normalize_name(pred_row.get("player_name", ""))

            if pred_name in results_lookup:
                result = results_lookup[pred_name]
                matched_data.append({
                    "player_name": pred_row.get("player_name"),
                    "predicted_win_prob": pred_row.get("win_prob", 0),
                    "predicted_top5_prob": pred_row.get("top5_prob", 0),
                    "predicted_top10_prob": pred_row.get("top10_prob", 0),
                    "predicted_ev": pred_row.get("expected_value", 0),
                    "course_fit": pred_row.get("dg_fit_total", 0),
                    "world_rank": pred_row.get("world_rank"),
                    "actual_position": result["position"],
                    "actual_won": result["won"],
                    "actual_top5": result["top5"],
                    "actual_top10": result["top10"],
                    "made_cut": result["made_cut"],
                })
            else:
                unmatched_predictions.append(pred_row.get("player_name"))

        if len(matched_data) == 0:
            return {"error": "No predictions matched to results"}

        matched_df = pd.DataFrame(matched_data)

        # Calculate comprehensive metrics
        analysis = {
            "tournament": tournament_name,
            "matched_players": len(matched_data),
            "unmatched_predictions": len(unmatched_predictions),
            "unmatched_names": unmatched_predictions[:10],  # First 10 for debugging
        }

        # Basic metrics
        analysis["metrics"] = self._calculate_metrics(matched_df)

        # Calibration analysis
        analysis["calibration"] = self.analyze_calibration(matched_df)

        # Feature importance
        analysis["feature_importance"] = self.analyze_feature_importance(matched_df)

        # Top picks analysis
        analysis["top_picks_analysis"] = self._analyze_top_picks(matched_df)

        # Value bet analysis
        analysis["value_analysis"] = self._analyze_value_bets(matched_df)

        return analysis

    def _analyze_top_picks(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze how top predicted picks actually performed."""
        if len(df) == 0:
            return {"error": "No data"}

        # Sort by win probability (highest first)
        df_sorted = df.sort_values("predicted_win_prob", ascending=False)

        results = {}

        for n in [5, 10, 20]:
            if len(df_sorted) < n:
                continue

            top_n = df_sorted.head(n)

            results[f"top_{n}_picks"] = {
                "players": list(top_n["player_name"]),
                "positions": [int(p) if p < 100 else "CUT" for p in top_n["actual_position"]],
                "wins": int(top_n["actual_won"].sum()),
                "top5s": int(top_n["actual_top5"].sum()),
                "top10s": int(top_n["actual_top10"].sum()),
                "made_cuts": int(top_n["made_cut"].sum()),
                "avg_finish": round(top_n[top_n["made_cut"]]["actual_position"].mean(), 1)
                             if top_n["made_cut"].any() else None,
            }

        # Winner analysis
        winner = df[df["actual_won"] == True]
        if len(winner) > 0:
            winner_row = winner.iloc[0]
            win_prob_rank = (df["predicted_win_prob"] >= winner_row["predicted_win_prob"]).sum()
            results["winner_analysis"] = {
                "name": winner_row["player_name"],
                "predicted_win_prob": round(winner_row["predicted_win_prob"], 4),
                "win_prob_rank": int(win_prob_rank),
                "was_in_top_10_predicted": win_prob_rank <= 10,
                "was_in_top_5_predicted": win_prob_rank <= 5,
            }

        return results

    def _analyze_value_bets(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze value bet performance."""
        # This would require odds data in predictions
        # For now, analyze based on model predictions vs results

        # Identify "value" picks: high predicted prob, worse world rank
        df = df.copy()

        if "world_rank" not in df.columns:
            return {"note": "No world rank data for value analysis"}

        # Value = predicted top10 prob higher than rank would suggest
        median_rank = df["world_rank"].median()
        df["is_value_pick"] = (
            (df["predicted_top10_prob"] > df["predicted_top10_prob"].median()) &
            (df["world_rank"] > median_rank)
        )

        value_picks = df[df["is_value_pick"]]
        non_value = df[~df["is_value_pick"]]

        if len(value_picks) == 0:
            return {"note": "No value picks identified"}

        return {
            "n_value_picks": len(value_picks),
            "value_top10_rate": round(value_picks["actual_top10"].mean(), 3),
            "non_value_top10_rate": round(non_value["actual_top10"].mean(), 3) if len(non_value) > 0 else None,
            "value_outperformed": value_picks["actual_top10"].mean() > non_value["actual_top10"].mean()
                                 if len(non_value) > 0 else None,
        }

    def generate_calibration_report(self, tournament_analysis: Dict[str, Any]) -> str:
        """Generate a detailed calibration report from tournament analysis."""
        lines = [
            "=" * 70,
            f"  PREDICTION CALIBRATION REPORT: {tournament_analysis.get('tournament', 'Unknown')}",
            "=" * 70,
            "",
        ]

        # Match summary
        lines.append(f"Matched Players: {tournament_analysis.get('matched_players', 0)}")
        lines.append(f"Unmatched: {tournament_analysis.get('unmatched_predictions', 0)}")
        lines.append("")

        # Calibration analysis
        cal = tournament_analysis.get("calibration", {})
        if "summary" in cal:
            lines.append("CALIBRATION SUMMARY:")
            lines.append("-" * 40)
            lines.append(f"  {cal['summary'].get('overall_assessment', 'N/A')}")
            for rec in cal["summary"].get("recommendations", []):
                lines.append(f"  → {rec}")
            lines.append("")

        # Detailed bucket analysis
        for prob_type in ["win_prob", "top5_prob", "top10_prob"]:
            if prob_type not in cal or "error" in cal.get(prob_type, {}):
                continue

            prob_data = cal[prob_type]
            lines.append(f"\n{prob_type.upper().replace('_', ' ')} CALIBRATION:")
            lines.append("-" * 40)
            lines.append(f"  ECE (Expected Calibration Error): {prob_data.get('expected_calibration_error', 0):.2%}")
            lines.append("")
            lines.append("  Bucket        | N   | Predicted | Actual | Error    | Status")
            lines.append("  " + "-" * 60)

            for bucket in prob_data.get("buckets", []):
                lines.append(
                    f"  {bucket['bucket']:12} | {bucket['n_samples']:3} | "
                    f"{bucket['avg_predicted']:8.1%} | {bucket['actual_rate']:6.1%} | "
                    f"{bucket['calibration_error']:+7.1%} | {bucket['direction']}"
                )

        # Feature importance
        fi = tournament_analysis.get("feature_importance", {})
        if "features" in fi:
            lines.append("\n\nFEATURE IMPORTANCE:")
            lines.append("-" * 40)
            lines.append(f"  Most Predictive: {fi.get('most_predictive', 'N/A')}")
            lines.append(f"  Least Predictive: {fi.get('least_predictive', 'N/A')}")
            lines.append("")

            for feature, data in fi.get("features", {}).items():
                sig = "✓" if data.get("is_statistically_significant") else "✗"
                lines.append(f"  {data['name']:20} | r={data['correlation']:+.3f} | p={data['p_value']:.3f} [{sig}]")
                lines.append(f"    → {data['interpretation']}")

        # Top picks analysis
        top = tournament_analysis.get("top_picks_analysis", {})
        if "winner_analysis" in top:
            lines.append("\n\nWINNER ANALYSIS:")
            lines.append("-" * 40)
            w = top["winner_analysis"]
            lines.append(f"  Winner: {w['name']}")
            lines.append(f"  Predicted Win Prob: {w['predicted_win_prob']:.2%}")
            lines.append(f"  Win Prob Rank: #{w['win_prob_rank']}")
            lines.append(f"  Was in Top 10 Predicted: {'Yes ✓' if w['was_in_top_10_predicted'] else 'No ✗'}")

        for key in ["top_5_picks", "top_10_picks"]:
            if key in top:
                lines.append(f"\n  {key.upper().replace('_', ' ')}:")
                data = top[key]
                lines.append(f"    Top 10s: {data['top10s']}/{len(data['players'])}")
                lines.append(f"    Made Cuts: {data['made_cuts']}/{len(data['players'])}")
                if data.get("avg_finish"):
                    lines.append(f"    Avg Finish (made cut): {data['avg_finish']}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Track and analyze golf predictions")
    parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Save command
    save_parser = subparsers.add_parser("save", help="Save predictions before tournament")
    save_parser.add_argument("--tournament", required=True, help="Tournament name")
    save_parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    save_parser.add_argument("--date", default=None, help="Tournament date (YYYY-MM-DD)")
    save_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Record results and analyze")
    analyze_parser.add_argument("--tournament", required=True, help="Tournament name")
    analyze_parser.add_argument("--results", required=True, help="Path to results CSV")
    analyze_parser.add_argument("--date", default=None, help="Tournament date (YYYY-MM-DD)")
    analyze_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate performance report")
    report_parser.add_argument("--last-n", type=int, default=10, help="Number of tournaments to analyze")
    report_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    # Calibrate command - comprehensive calibration analysis
    calibrate_parser = subparsers.add_parser("calibrate", help="Run calibration analysis")
    calibrate_parser.add_argument("--predictions", required=True, help="Path to predictions CSV")
    calibrate_parser.add_argument("--results", required=True, help="Path to results CSV")
    calibrate_parser.add_argument("--tournament", required=True, help="Tournament name for report")
    calibrate_parser.add_argument("--output", default=None, help="Optional output file for report")
    calibrate_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    # Build calibration factors from tracked results
    factors_parser = subparsers.add_parser("calibration-factors", help="Build calibration_factors.json from tracked results")
    factors_parser.add_argument("--output", default=None, help="Optional output path for calibration_factors.json")
    factors_parser.add_argument("--min-tournaments", type=int, default=3, help="Minimum tournaments per type")
    factors_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    # Evaluate picks log against results
    picks_parser = subparsers.add_parser("evaluate-picks", help="Evaluate picks_log.csv against results")
    picks_parser.add_argument("--tournament", required=True, help="Tournament name")
    picks_parser.add_argument("--picks-log", default=None, help="Path to picks_log.csv (default: outputs/picks_log.csv)")
    picks_parser.add_argument("--results", default=None, help="Optional results CSV path")
    picks_parser.add_argument("--year", type=int, default=None, help="Year for leaderboards if results not provided")
    picks_parser.add_argument("--output", default=None, help="Optional output report path")
    picks_parser.add_argument("--tracking-dir", default=None, help="Override tracking directory")

    args = parser.parse_args()

    # Determine tracking dir (explicit flag > predictions file parent > default)
    tracking_dir = Path(args.tracking_dir) if getattr(args, "tracking_dir", None) else None
    if tracking_dir is None and hasattr(args, "predictions") and args.predictions:
        try:
            tracking_dir = Path(args.predictions).parent
        except Exception:
            tracking_dir = None
    tracker = PredictionTracker(tracking_dir=tracking_dir)

    if args.command == "save":
        predictions_df = pd.read_csv(args.predictions)
        tracker.save_predictions(predictions_df, args.tournament, args.date)

    elif args.command == "analyze":
        results_df = pd.read_csv(args.results)
        metrics = tracker.record_results(args.tournament, results_df, args.date)
        print("\nMetrics:")
        print(json.dumps(metrics, indent=2, default=str))

    elif args.command == "report":
        report = tracker.generate_report(args.last_n)
        print(report)

    elif args.command == "calibrate":
        results_df = pd.read_csv(args.results)
        analysis = tracker.compare_predictions_to_results(
            args.predictions,
            results_df,
            args.tournament
        )

        if "error" in analysis:
            print(f"Error: {analysis['error']}")
        else:
            report = tracker.generate_calibration_report(analysis)
            print(report)

            if args.output:
                with open(args.output, "w") as f:
                    f.write(report)
                print(f"\n✓ Report saved to {args.output}")

            # Also save full analysis as JSON
            json_output = args.output.replace(".txt", ".json") if args.output else None
            if json_output:
                with open(json_output, "w") as f:
                    # Convert non-serializable items
                    json.dump(analysis, f, indent=2, default=str)
                print(f"✓ Full analysis saved to {json_output}")

    elif args.command == "calibration-factors":
        output_path = Path(args.output) if args.output else None
        factors = tracker.generate_calibration_factors(
            output_path=output_path,
            min_tournaments=args.min_tournaments,
        )
        if "error" in factors:
            print(f"Error: {factors['error']}")
        else:
            save_path = output_path or (tracker.tracking_dir / "calibration_factors.json")
            print(f"✓ Calibration factors saved to {save_path}")

    elif args.command == "evaluate-picks":
        picks_log = Path(args.picks_log) if args.picks_log else None
        results_path = Path(args.results) if args.results else None
        output_path = Path(args.output) if args.output else None
        summary = tracker.evaluate_picks_log(
            tournament_name=args.tournament,
            picks_log_path=picks_log,
            results_path=results_path,
            year=args.year,
            output_path=output_path,
        )
        if "error" in summary:
            print(f"Error: {summary['error']}")
        else:
            print(json.dumps(summary, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
