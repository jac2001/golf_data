#!/usr/bin/env python3
"""
Probability Calibration Module
==============================
Applies learned calibration corrections to model predictions.

Based on empirical calibration analysis, the model tends to be:
- Well-calibrated for win probabilities (ECE ~1.7%)
- Overconfident for top-5 probabilities (ECE ~5%)
- Overconfident for top-10 probabilities (ECE ~7.5%)

This module applies correction factors to improve calibration.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from typing import Dict, Optional


# Default calibration factors based on American Express analysis
# These should be updated as more tournament data is collected
DEFAULT_CALIBRATION = {
    "win_prob": {
        "scale_factor": 1.0,  # Well calibrated
        "buckets": {}  # No bucket-level adjustments needed
    },
    "top5_prob": {
        "scale_factor": 0.70,  # Reduce by 30% overall
        "buckets": {
            # Fine-grained adjustments by probability bucket
            "0.00-0.05": 0.60,  # Players at 0-5% -> scale to 60% of predicted
            "0.05-0.10": 0.65,  # Players at 5-10% -> scale to 65%
            "0.10-0.20": 0.70,  # Players at 10-20% -> scale to 70%
            "0.20-0.30": 0.65,  # Players at 20-30% -> scale to 65%
            "0.30-0.50": 0.75,  # Players at 30-50% -> scale to 75%
            "0.50-1.00": 0.85,  # Elite players -> less adjustment needed
        }
    },
    "top10_prob": {
        "scale_factor": 0.65,  # Reduce by 35% overall
        "buckets": {
            "0.00-0.10": 0.70,
            "0.10-0.20": 0.60,  # Most overconfident bucket
            "0.20-0.30": 0.50,  # Very overconfident
            "0.30-0.50": 0.60,
            "0.50-1.00": 0.80,
        }
    },
    "top20_prob": {
        "scale_factor": 0.75,
        "buckets": {
            "0.00-0.10": 0.80,
            "0.10-0.20": 0.70,
            "0.20-0.30": 0.65,
            "0.30-0.50": 0.70,
            "0.50-1.00": 0.85,
        }
    }
}


class ProbabilityCalibrator:
    """Apply calibration corrections to model predictions."""

    def __init__(self, calibration_file: Optional[Path] = None):
        """
        Initialize calibrator.

        Args:
            calibration_file: Optional JSON file with custom calibration factors.
                             If not provided, uses DEFAULT_CALIBRATION.
        """
        self.calibration_dir = Path("/Users/jacklegnon/Desktop/golf_data/data/prediction_tracking")
        self.calibration_file = calibration_file or self.calibration_dir / "calibration_factors.json"

        # Load calibration factors
        if self.calibration_file.exists():
            with open(self.calibration_file, "r") as f:
                self.calibration = json.load(f)
            print(f"  Loaded calibration factors from {self.calibration_file}")
        else:
            self.calibration = DEFAULT_CALIBRATION
            print("  Using default calibration factors")

    # Maximum win probability cap — prevents single player from dominating.
    # Set relative to field size: full field (144) ~= 0.18, signature (70) ~= 0.22,
    # but we use a flat 0.20 as a reasonable guardrail across tournament types.
    MAX_WIN_PROB = 0.20

    def calibrate_predictions(
        self,
        df: pd.DataFrame,
        method: str = "bucket",
        tournament_type: Optional[str] = None,
        max_win_prob: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Apply calibration to prediction DataFrame.

        Args:
            df: DataFrame with win_prob, top5_prob, top10_prob columns
            method: "simple" (single scale factor) or "bucket" (per-bucket adjustment)
            tournament_type: Optional tournament type (Standard/Signature/Major/Playoff)
            max_win_prob: Hard cap on calibrated win probability (default: MAX_WIN_PROB=0.20)

        Returns:
            DataFrame with calibrated probabilities added
        """
        df = df.copy()
        cal_config = self._select_calibration(tournament_type)
        _max_win = max_win_prob if max_win_prob is not None else self.MAX_WIN_PROB

        for prob_col in ["win_prob", "top5_prob", "top10_prob", "top20_prob"]:
            if prob_col not in df.columns:
                continue

            prob_config = cal_config.get(prob_col, {"scale_factor": 1.0})

            if method == "simple":
                # Simple scaling
                scale = prob_config.get("scale_factor", 1.0)
                df[f"{prob_col}_calibrated"] = df[prob_col] * scale
            else:
                # Bucket-based calibration
                df[f"{prob_col}_calibrated"] = df.apply(
                    lambda row: self._calibrate_value(row[prob_col], prob_config),
                    axis=1
                )

            # Ensure probabilities stay in [0, 1]
            df[f"{prob_col}_calibrated"] = df[f"{prob_col}_calibrated"].clip(0, 1)

            # Hard cap on win_prob to prevent single-player over-concentration
            if prob_col == "win_prob" and _max_win is not None:
                n_capped = (df[f"{prob_col}_calibrated"] > _max_win).sum()
                if n_capped > 0:
                    df[f"{prob_col}_calibrated"] = df[f"{prob_col}_calibrated"].clip(0, _max_win)
                    print(f"  Win prob capped at {_max_win:.0%} for {n_capped} player(s)")

        return df

    def _select_calibration(self, tournament_type: Optional[str]) -> Dict:
        """Select calibration config (global or per tournament type)."""
        def _meta_counts() -> tuple[int, Dict[str, int], int]:
            meta = self.calibration.get("metadata", {}) if isinstance(self.calibration, dict) else {}
            min_tournaments = int(meta.get("min_tournaments", 3) or 3)
            raw_counts = meta.get("tournaments_by_type", {}) if isinstance(meta, dict) else {}
            counts: Dict[str, int] = {}
            if isinstance(raw_counts, dict):
                for k, v in raw_counts.items():
                    try:
                        counts[str(k).strip().title()] = int(v)
                    except Exception:
                        continue
            total = int(sum(max(0, c) for c in counts.values()))
            return min_tournaments, counts, total

        # Backward compatibility: old format is flat with win_prob/top5_prob/top10_prob
        if "by_tournament_type" not in self.calibration:
            min_t, _, total = _meta_counts()
            if total > 0 and total < min_t:
                print(f"  Calibration data sparse ({total} tournament(s) < min {min_t}); using default calibration.")
                return DEFAULT_CALIBRATION
            return self.calibration

        min_t, counts, total = _meta_counts()
        by_type = self.calibration.get("by_tournament_type", {})

        if tournament_type:
            t_key = str(tournament_type).strip().title()
            t_count = counts.get(t_key, 0)
            if t_key in by_type and t_count >= min_t:
                return by_type[t_key]
            if t_key in by_type and t_count < min_t:
                print(
                    f"  Calibration for {t_key} has only {t_count} tournament(s) "
                    f"(min {min_t}); falling back to global/default."
                )

        if total >= min_t:
            return self.calibration.get("global", DEFAULT_CALIBRATION)

        if total > 0:
            print(f"  Global calibration data sparse ({total} tournament(s) < min {min_t}); using default calibration.")
        return DEFAULT_CALIBRATION

    def _calibrate_value(self, value: float, config: Dict) -> float:
        """Apply bucket-based calibration to a single probability value."""
        buckets = config.get("buckets", {})

        if not buckets:
            # No bucket config, use simple scaling
            return value * config.get("scale_factor", 1.0)

        # Find matching bucket
        for bucket_range, scale in buckets.items():
            low, high = map(float, bucket_range.split("-"))
            if low <= value < high:
                return value * scale

        # Default: use overall scale factor
        return value * config.get("scale_factor", 1.0)

    def update_calibration_from_analysis(self, analysis: Dict) -> None:
        """
        Update calibration factors based on calibration analysis results.

        Args:
            analysis: Dict from PredictionTracker.compare_predictions_to_results()
        """
        if "calibration" not in analysis:
            print("  No calibration data in analysis")
            return

        cal = analysis["calibration"]

        # Choose target config (global if tournament-specific is present)
        if "by_tournament_type" in self.calibration:
            target = self.calibration.setdefault("global", {})
        else:
            target = self.calibration

        for prob_type in ["win_prob", "top5_prob", "top10_prob", "top20_prob"]:
            if prob_type not in cal or "buckets" not in cal[prob_type]:
                continue

            buckets = cal[prob_type]["buckets"]

            # Calculate adjustment factors from calibration errors
            new_buckets = {}
            for bucket_data in buckets:
                bucket_name = bucket_data["bucket"]
                avg_pred = bucket_data["avg_predicted"]
                actual_rate = bucket_data["actual_rate"]
                n_samples = bucket_data["n_samples"]

                # Only adjust if we have enough samples
                if n_samples < 5:
                    continue

                # Calculate scale factor to match actual rate
                # If actual is 0, use a floor to avoid zeroing out completely
                if avg_pred > 0:
                    if actual_rate > 0:
                        scale = actual_rate / avg_pred
                    else:
                        # Actual rate is 0, but we don't want to set to 0
                        # Use a conservative reduction
                        scale = 0.3
                else:
                    scale = 1.0

                # Convert bucket name (e.g., "10-20%") to range format
                bucket_range = self._bucket_name_to_range(bucket_name)
                if bucket_range:
                    new_buckets[bucket_range] = round(min(1.5, max(0.1, scale)), 2)

            if new_buckets:
                if prob_type not in target:
                    target[prob_type] = {}
                target[prob_type]["buckets"] = new_buckets

                # Also update overall scale factor (weighted average)
                total_samples = sum(b["n_samples"] for b in buckets)
                overall_scale = sum(
                    new_buckets.get(self._bucket_name_to_range(b["bucket"]), 1.0) * b["n_samples"] / total_samples
                    for b in buckets if b["n_samples"] > 0
                )
                target[prob_type]["scale_factor"] = round(overall_scale, 2)

        # Save updated calibration
        self.save_calibration()

    def _bucket_name_to_range(self, name: str) -> Optional[str]:
        """Convert bucket name like '10-20%' to '0.10-0.20'."""
        try:
            # Remove % and split
            parts = name.replace("%", "").split("-")
            low = float(parts[0]) / 100
            high = float(parts[1]) / 100 if len(parts) > 1 else 1.0
            return f"{low:.2f}-{high:.2f}"
        except:
            return None

    def save_calibration(self, path: Optional[Path] = None):
        """Save calibration factors to JSON file."""
        save_path = path or self.calibration_file
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(self.calibration, f, indent=2)

        print(f"  Saved calibration factors to {save_path}")

    def get_calibration_summary(self) -> str:
        """Get human-readable summary of calibration factors."""
        lines = ["Calibration Factors:"]

        if "by_tournament_type" in self.calibration:
            lines.append("\n  Global:")
            lines.append(self._format_summary_block(self.calibration.get("global", {})))
            for t_key, t_cfg in self.calibration.get("by_tournament_type", {}).items():
                lines.append(f"\n  {t_key}:")
                lines.append(self._format_summary_block(t_cfg))
        else:
            lines.append(self._format_summary_block(self.calibration))

        return "\n".join(lines)

    def _format_summary_block(self, cfg: Dict) -> str:
        lines = []
        for prob_type in ["win_prob", "top5_prob", "top10_prob", "top20_prob"]:
            if prob_type not in cfg:
                continue
            config = cfg[prob_type]
            lines.append(f"    {prob_type}:")
            lines.append(f"      Overall scale: {config.get('scale_factor', 1.0):.0%}")
            if config.get("buckets"):
                lines.append("      Buckets:")
                for bucket, scale in config["buckets"].items():
                    lines.append(f"        {bucket}: {scale:.0%}")
        return "\n".join(lines)


def apply_calibration(
    predictions_df: pd.DataFrame,
    method: str = "bucket",
    tournament_type: Optional[str] = None,
) -> pd.DataFrame:
    """
    Convenience function to apply calibration to predictions.

    Args:
        predictions_df: DataFrame with win_prob, top5_prob, top10_prob
        method: "simple" or "bucket"

    Returns:
        DataFrame with calibrated_* columns added
    """
    calibrator = ProbabilityCalibrator()
    return calibrator.calibrate_predictions(
        predictions_df,
        method=method,
        tournament_type=tournament_type,
    )


if __name__ == "__main__":
    # Test calibration
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "show":
        calibrator = ProbabilityCalibrator()
        print(calibrator.get_calibration_summary())
    else:
        print("Usage: python calibration.py show")
        print("\nTo apply calibration in predictions:")
        print("  from scripts.predictions.calibration import apply_calibration")
        print("  calibrated_df = apply_calibration(predictions_df)")
