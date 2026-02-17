#!/usr/bin/env python3
"""
Data QA report for golf_data datasets.

Outputs:
- outputs/data_qa_report.txt
- outputs/data_qa_report.json

Usage:
  python3 scripts/analysis/data_qa_report.py
  python3 scripts/analysis/data_qa_report.py --output-dir outputs/qa
  python3 scripts/analysis/data_qa_report.py --files data/processed/master_training_data_2020_2025.csv data/historical/leaderboards_2026.csv
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


DEFAULT_FILES = [
    "data/processed/master_training_data_2020_2025.csv",
    "data/historical/leaderboards_2026.csv",
    "data/historical/leaderboards_2025.csv",
    "data/historical/leaderboards_2024.csv",
    "data/historical/tournament_stats_2026.csv",
    "data/historical/tournament_stats_2025.csv",
    "data/historical/form_stats_2026.csv",
    "data/historical/form_stats_2025.csv",
]

KEY_COLUMNS = [
    "tournament_id",
    "year",
    "player_id",
    "player_name",
]

IMPORTANT_FEATURES = [
    "world_rank",
    "season_sg_total",
    "season_sg_t2g",
    "season_sg_app",
    "season_sg_ott",
    "season_sg_putt",
    "sg_total",
    "sg_t2g",
    "sg_app",
    "sg_ott",
    "sg_putt",
    "recent_top10s",
    "recent_cuts_pct",
]


@dataclass
class FileQA:
    path: str
    exists: bool
    rows: int = 0
    cols: int = 0
    missing_by_col: Dict[str, int] = None
    missing_pct_by_col: Dict[str, float] = None
    null_key_counts: Dict[str, int] = None
    duplicate_key_rows: Optional[int] = None
    duplicate_key_ratio: Optional[float] = None
    key_columns_used: Optional[List[str]] = None


def _safe_pct(n: int, d: int) -> float:
    return 0.0 if d == 0 else round((n / d) * 100.0, 2)


def _detect_key_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in KEY_COLUMNS if c in df.columns]


def _missing_stats(df: pd.DataFrame) -> tuple[Dict[str, int], Dict[str, float]]:
    missing = df.isna().sum().to_dict()
    missing_pct = {k: _safe_pct(v, len(df)) for k, v in missing.items()}
    return missing, missing_pct


def _duplicate_key_stats(df: pd.DataFrame, key_cols: List[str]) -> tuple[Optional[int], Optional[float]]:
    if not key_cols:
        return None, None
    dup = df.duplicated(subset=key_cols, keep=False).sum()
    return int(dup), _safe_pct(int(dup), len(df))


def analyze_file(path: str) -> FileQA:
    qa = FileQA(path=path, exists=os.path.exists(path))
    if not qa.exists:
        return qa

    df = pd.read_csv(path)

    qa.rows = len(df)
    qa.cols = df.shape[1]

    missing, missing_pct = _missing_stats(df)
    qa.missing_by_col = missing
    qa.missing_pct_by_col = missing_pct

    key_cols = _detect_key_columns(df)
    qa.key_columns_used = key_cols

    qa.null_key_counts = {k: int(df[k].isna().sum()) for k in key_cols}

    dup_count, dup_pct = _duplicate_key_stats(df, key_cols)
    qa.duplicate_key_rows = dup_count
    qa.duplicate_key_ratio = dup_pct

    return qa


def format_report(results: List[FileQA]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("DATA QA REPORT")
    lines.append("=" * 72)
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    for r in results:
        lines.append("-" * 72)
        lines.append(f"FILE: {r.path}")
        if not r.exists:
            lines.append("  Status: MISSING")
            lines.append("")
            continue

        lines.append(f"  Rows: {r.rows:,}")
        lines.append(f"  Cols: {r.cols:,}")
        if r.key_columns_used:
            lines.append(f"  Key columns: {', '.join(r.key_columns_used)}")
            lines.append(f"  Null keys: {r.null_key_counts}")
            if r.duplicate_key_rows is not None:
                lines.append(
                    f"  Duplicate key rows: {r.duplicate_key_rows:,} ({r.duplicate_key_ratio}%)"
                )
        else:
            lines.append("  Key columns: (none detected)")

        # Top missing
        miss = sorted(
            ((k, v, r.missing_pct_by_col.get(k, 0.0)) for k, v in r.missing_by_col.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        top_missing = [m for m in miss if m[1] > 0][:10]
        if top_missing:
            lines.append("  Top 10 Missing:")
            for col, cnt, pct in top_missing:
                lines.append(f"    - {col}: {cnt:,} ({pct}%)")
        else:
            lines.append("  Top 10 Missing: none")

        # Important features missing
        important = [c for c in IMPORTANT_FEATURES if c in r.missing_by_col]
        if important:
            lines.append("  Important Features Missing:")
            for c in important:
                lines.append(
                    f"    - {c}: {r.missing_by_col[c]:,} ({r.missing_pct_by_col[c]}%)"
                )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Data QA report")
    parser.add_argument("--files", nargs="*", default=None, help="Files to analyze")
    parser.add_argument(
        "--output-dir", default="outputs", help="Directory for report outputs"
    )
    args = parser.parse_args()

    files = args.files if args.files else DEFAULT_FILES
    results = [analyze_file(p) for p in files]

    os.makedirs(args.output_dir, exist_ok=True)

    report_txt = os.path.join(args.output_dir, "data_qa_report.txt")
    report_json = os.path.join(args.output_dir, "data_qa_report.json")

    with open(report_txt, "w") as f:
        f.write(format_report(results))

    with open(report_json, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    print(f"✓ Data QA report saved to: {report_txt}")
    print(f"✓ Data QA JSON saved to: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
