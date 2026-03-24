#!/usr/bin/env python3
"""
Golf Prediction Pipeline Runner
================================
Single script to run the entire prediction pipeline end-to-end.

Stages:
1. DATA REFRESH - Fetch latest rankings, player database, form stats, tournament SG stats
2. FIELD FETCH - Get tournament field (from PGA TOUR or manual)
3. PREDICTIONS - Run the prediction model
4. INSIGHTS - Generate AI insights (optional)
5. LINEUP - Recommend optimal lineup with usage strategy

Usage:
    # Run everything for a tournament
    python scripts/run_pipeline.py --tournament "The American Express" --purse 8400000

    # Skip data refresh (use cached data)
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 --skip-refresh

    # With specific field file
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
        --field data/fields/masters_2026.csv

    # Full pipeline with insights and lineup
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
        --insights --lineup

    # Weekly automation mode
    python scripts/run_pipeline.py --weekly-refresh
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import json
import pandas as pd
import traceback
import re
from typing import Optional, Any, Dict, List

# ============================================================================
# Configuration
# ============================================================================

# Resolve project root dynamically from this file location so the
# pipeline can run on any machine/path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure project root is on path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = PROJECT_ROOT / "logs"
SCHEDULE_PATH = DATA_DIR / "raw" / "schedule_2026.csv"
PIPELINE_STATUS_PATH = LOGS_DIR / "pipeline_status_latest.json"
PIPELINE_HISTORY_PATH = LOGS_DIR / "pipeline_status_history.json"
PIPELINE_RUNS_DIR = LOGS_DIR / "pipeline_runs"

from scripts.utils.tournament_context import resolve_tournament_context

# Pipeline stages and their scripts
PIPELINE_STAGES = {
    "player_database": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_player_database.py",
        "description": "Fetch PGA Tour player database",
        "output": DATA_DIR / "players" / f"pga_players_{datetime.now().year}.csv",
    },
    "world_rankings": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_world_rankings.py",
        "description": "Fetch OWGR world rankings",
        "output": DATA_DIR / "rankings" / f"owgr_{datetime.now().year}.csv",
    },
    "form_stats": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_form_stats.py",
        "description": "Fetch recent form statistics",
        "output": DATA_DIR / "historical" / f"form_stats_{datetime.now().year}.csv",
    },
    "tournament_stats": {
        "script": SCRIPTS_DIR / "scrapers" / "multi_year_stats_scraper_fixed.py",
        "description": "Fetch tournament SG statistics",
        "output": DATA_DIR / "historical" / f"tournament_stats_{datetime.now().year}.csv",
    },
    "course_form_features": {
        "script": SCRIPTS_DIR / "features" / "consolidate_course_form_stats.py",
        "description": "Build player-course performance features",
        "output": DATA_DIR / "processed" / "player_course_performance.csv",
    },
    "course_similarity": {
        "script": SCRIPTS_DIR / "features" / "course_similarity.py",
        "description": "Build course similarity matrix and profiles",
        "output": DATA_DIR / "processed" / "course_similarity_matrix.csv",
    },
    "predictions": {
        "script": SCRIPTS_DIR / "predictions" / "predict_tournament.py",
        "description": "Generate tournament predictions",
    },
}

_ACTIVE_TRACKER = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tail_text(value: str, limit: int = 4000) -> str:
    if not value:
        return ""
    text = str(value)
    return text[-limit:] if len(text) > limit else text


class PipelineRunTracker:
    """Tracks per-command pipeline execution health for dashboard visibility."""

    def __init__(self, run_type: str, tournament_name: str = "", tournament_id: str = ""):
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.started_at = _now_iso()
        self.ended_at = ""
        self.status = "running"
        self.run_type = run_type
        self.tournament_name = str(tournament_name or "")
        self.tournament_id = str(tournament_id or "")
        self.steps: List[Dict[str, Any]] = []
        self._counter = 0

    def start_step(self, name: str, command: List[str], timeout: Optional[int] = None) -> int:
        self._counter += 1
        idx = len(self.steps)
        self.steps.append({
            "id": f"step_{self._counter:03d}",
            "name": str(name or "command"),
            "command": list(command or []),
            "command_str": " ".join([str(x) for x in (command or [])]),
            "timeout_seconds": int(timeout) if timeout else None,
            "status": "running",
            "started_at": _now_iso(),
            "ended_at": "",
            "duration_seconds": None,
            "return_code": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": "",
        })
        self._flush()
        return idx

    def end_step(
        self,
        idx: int,
        success: bool,
        return_code: Optional[int] = None,
        stdout: str = "",
        stderr: str = "",
        error: str = "",
    ) -> None:
        if idx < 0 or idx >= len(self.steps):
            return
        step = self.steps[idx]
        step["ended_at"] = _now_iso()
        try:
            started = datetime.fromisoformat(step["started_at"])
            ended = datetime.fromisoformat(step["ended_at"])
            step["duration_seconds"] = round((ended - started).total_seconds(), 3)
        except Exception:
            step["duration_seconds"] = None
        step["status"] = "success" if success else "failed"
        step["return_code"] = return_code
        step["stdout_tail"] = _tail_text(stdout)
        step["stderr_tail"] = _tail_text(stderr)
        step["error"] = _tail_text(error)
        self._flush()

    def finalize(self, success: bool, error: str = "") -> None:
        self.ended_at = _now_iso()
        self.status = "success" if success else "failed"
        if (not success) and error and (not any(s.get("status") == "failed" for s in self.steps)):
            self.record_manual_step(
                name="Pipeline exception",
                success=False,
                command=[],
                error=error,
            )
        payload = self.to_dict()
        if error:
            payload["error"] = _tail_text(error)
        self._write(payload, append_history=True)

    def record_manual_step(
        self,
        name: str,
        success: bool,
        command: Optional[List[str]] = None,
        error: str = "",
        stdout: str = "",
    ) -> None:
        idx = self.start_step(name=name, command=(command or []), timeout=None)
        self.end_step(
            idx=idx,
            success=success,
            return_code=0 if success else 1,
            stdout=stdout,
            stderr="",
            error=error,
        )

    def _flush(self) -> None:
        self._write(self.to_dict(), append_history=False)

    def to_dict(self) -> Dict[str, Any]:
        failed_steps = [s for s in self.steps if s.get("status") == "failed"]
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "tournament_name": self.tournament_name,
            "tournament_id": self.tournament_id,
            "step_count": len(self.steps),
            "failed_count": len(failed_steps),
            "failed_step_ids": [s.get("id", "") for s in failed_steps],
            "steps": self.steps,
        }

    def _write(self, payload: Dict[str, Any], append_history: bool) -> None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            PIPELINE_STATUS_PATH.write_text(json.dumps(payload, indent=2))
            PIPELINE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
            run_file = PIPELINE_RUNS_DIR / f"{payload.get('run_id', 'unknown')}.json"
            run_file.write_text(json.dumps(payload, indent=2))
            if append_history:
                history = []
                if PIPELINE_HISTORY_PATH.exists():
                    try:
                        history = json.loads(PIPELINE_HISTORY_PATH.read_text())
                        if not isinstance(history, list):
                            history = []
                    except Exception:
                        history = []
                history.append({
                    "run_id": payload.get("run_id", ""),
                    "run_file": str(run_file),
                    "run_type": payload.get("run_type", ""),
                    "status": payload.get("status", ""),
                    "started_at": payload.get("started_at", ""),
                    "ended_at": payload.get("ended_at", ""),
                    "tournament_name": payload.get("tournament_name", ""),
                    "tournament_id": payload.get("tournament_id", ""),
                    "step_count": payload.get("step_count", 0),
                    "failed_count": payload.get("failed_count", 0),
                    "failed_step_ids": payload.get("failed_step_ids", []),
                })
                history = history[-250:]
                PIPELINE_HISTORY_PATH.write_text(json.dumps(history, indent=2))
        except Exception:
            # Status logging should never fail the pipeline.
            pass


def slugify(name: str) -> str:
    """Basic slugify for filenames and optional power rankings slug."""
    import re
    slug = name.lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"\\s+", "-", slug.strip())
    return slug


def print_header(text: str, char: str = "="):
    """Print a formatted header."""
    print()
    print(char * 70)
    print(f"  {text}")
    print(char * 70)


def print_stage(stage_num: int, total: int, name: str):
    """Print stage progress."""
    print(f"\n[{stage_num}/{total}] {name}")
    print("-" * 50)


def run_command(
    cmd: list,
    description: str = "",
    check: bool = True,
    timeout: Optional[int] = None,
) -> bool:
    """Run a command and return success status."""
    label = description or " ".join([str(x) for x in cmd[:3]])
    print(f"  Running: {' '.join(cmd)}")

    step_idx = None
    if _ACTIVE_TRACKER is not None:
        step_idx = _ACTIVE_TRACKER.start_step(label, cmd, timeout=timeout)

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n")

        success = result.returncode == 0
        if step_idx is not None:
            _ACTIVE_TRACKER.end_step(
                step_idx,
                success=success,
                return_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                error=stderr if not success else "",
            )
        return success
    except subprocess.TimeoutExpired as e:
        msg = f"Timeout after {timeout}s"
        print(f"  Error: {msg}")
        if step_idx is not None:
            _ACTIVE_TRACKER.end_step(
                step_idx,
                success=False,
                return_code=None,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                error=msg,
            )
        return False
    except Exception as e:
        print(f"  Error: {e}")
        if step_idx is not None:
            _ACTIVE_TRACKER.end_step(
                step_idx,
                success=False,
                return_code=None,
                stdout="",
                stderr="",
                error=str(e),
            )
        return False


def check_file_fresh(filepath: Path, max_age_hours: int = 24) -> bool:
    """Check if a file exists and is recent enough."""
    if not filepath.exists():
        return False

    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    age_hours = (datetime.now() - mtime).total_seconds() / 3600

    return age_hours < max_age_hours


def load_schedule(path: Path = SCHEDULE_PATH) -> pd.DataFrame:
    """Load schedule CSV (expects columns: tournament_name, start_date, end_date, purse, tournament_type)."""
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # Normalize money columns
    for col in ["purse", "winner_share"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Normalize names for lookup
    if "tournament_name" in df.columns:
        df["name_key"] = df["tournament_name"].str.lower().str.strip()
    return df


def find_schedule_row(
    tournament_name: str = None,
    on_date: str = None,
    schedule_path: Path = SCHEDULE_PATH,
) -> Optional[dict]:
    """Find tournament row by name or by date via centralized context resolver."""
    ctx = resolve_tournament_context(
        tournament_name=tournament_name or "",
        on_date=on_date or "",
        schedule_path=schedule_path,
    )
    if not ctx.get("tournament_name"):
        return None
    return ctx


def refresh_data(force: bool = False, max_age_hours: int = 24):
    """Refresh all data sources."""
    print_header("DATA REFRESH")

    stages = ["player_database", "world_rankings", "form_stats", "tournament_stats", "course_form_features", "course_similarity"]
    total = len(stages)

    for i, stage_name in enumerate(stages, 1):
        stage = PIPELINE_STAGES[stage_name]
        print_stage(i, total, stage["description"])

        # Check if refresh needed
        output_file = stage.get("output")
        should_use_freshness = stage_name not in {"course_form_features", "tournament_stats"}
        if should_use_freshness and output_file and not force and check_file_fresh(output_file, max_age_hours):
            print(f"  Skipping - data is fresh ({output_file.name})")
            continue

        # Run the script
        script_path = stage["script"]
        if script_path.exists():
            cmd = ["python3", str(script_path)]
            if stage_name == "form_stats":
                cmd.extend(["--year", str(datetime.now().year)])
            elif stage_name == "tournament_stats":
                cmd.extend(["--year", str(datetime.now().year), "--refresh-latest", "3"])
            elif stage_name == "course_form_features":
                now_year = datetime.now().year
                # Use 5 years of history for better course performance data
                years = [str(now_year - i) for i in range(5, -1, -1)]  # 5 years back + current
                cmd.extend(["--years"] + years)
            timeout = 300 if stage_name in {"tournament_stats", "course_form_features"} else 180
            success = run_command(cmd, description=stage["description"], timeout=timeout)
            if success:
                print(f"  Done")
            else:
                print(f"  Warning: {stage_name} failed, continuing...")
        else:
            print(f"  Warning: Script not found: {script_path}")


def find_field_file(tournament_name: str, tournament_id: str = None) -> Path:
    """Try to find an existing field file for a tournament.

    Lookup order:
    1. Canonical ID-based file  data/fields/field_{tournament_id}.csv  (most reliable)
    2. Fuzzy name match inside data/fields/ and data/fields/archive/
    """
    import re

    # 1. Canonical ID-based lookup — guaranteed to be the right tournament
    if tournament_id:
        canonical = DATA_DIR / "fields" / f"field_{tournament_id}.csv"
        if canonical.exists():
            return canonical

    # 2. Fuzzy name-based fallback (first 10 chars of normalized name)
    name_clean = re.sub(r'[^\w\s]', '', tournament_name.lower()).replace(' ', '_')
    field_dirs = [
        DATA_DIR / "fields",
        DATA_DIR / "fields" / "archive",
    ]
    for field_dir in field_dirs:
        if not field_dir.exists():
            continue
        for f in field_dir.glob("*.csv"):
            if name_clean[:10] in f.stem.lower():
                return f

    return None


def fetch_field_from_pga(tournament_name: str, tournament_id: str = None) -> Path:
    """Fetch field from PGA TOUR if possible."""
    print("\n  Attempting to fetch field from PGA TOUR...")

    # If no tournament_id provided, we can't fetch
    if not tournament_id:
        print("  No PGA TOUR tournament ID provided, cannot auto-fetch field")
        return None

    # Always use canonical ID-based path to avoid stale name-based files
    output_path = DATA_DIR / "fields" / f"field_{tournament_id}.csv"

    script_path = SCRIPTS_DIR / "scrapers" / "fetch_field_from_pgatour.py"
    if script_path.exists():
        cmd = [
            "python3", str(script_path),
            "--pga-id", tournament_id,
            "--output", str(output_path),
            "--match-ids",
            "--name", tournament_name,
        ]
        success = run_command(cmd, description="Fetch tournament field from PGA TOUR", timeout=240)
        if success and output_path.exists():
            return output_path
        if _ACTIVE_TRACKER is not None:
            _ACTIVE_TRACKER.record_manual_step(
                name="Validate fetched field file",
                success=False,
                command=cmd,
                error=f"Field fetch command completed but output missing: {output_path}",
            )

    return None


def run_predictions(
    tournament_name: str,
    purse: int,
    field_path: Path,
    tournament_type: str = "Standard",
    sg_method: str = "last_5",
    insights: bool = False,
    insights_ollama: bool = False,
    save_tracking: bool = False,
    odds_path: Path = None,
    calibrate: bool = False,
) -> Path:
    """Run the prediction model."""
    print_header("GENERATING PREDICTIONS")

    # Build output path
    date_str = datetime.now().strftime("%Y%m%d")
    output_name = f"{tournament_name.lower().replace(' ', '_')}_{date_str}_predictions.csv"
    output_path = OUTPUTS_DIR / output_name

    # Build command
    cmd = [
        "python3", str(SCRIPTS_DIR / "predictions" / "predict_tournament.py"),
        "--tournament", tournament_name,
        "--purse", str(purse),
        "--field", str(field_path),
        "--tournament-type", tournament_type,
        "--sg-method", sg_method,
        "--course-adjust-strength", "0.12",
        "--course-adjust-max", "0.08",
        "--course-adjust-min-starts", "2",
        "--course-adjust-min-players", "5",
        "--output", str(output_path),
        "--top-n", "20",
        "--skip-bet-recs",
    ]

    if insights:
        cmd.append("--insights")

    if insights_ollama:
        cmd.append("--insights-ollama")

    if save_tracking:
        cmd.append("--save-tracking")

    if odds_path and odds_path.exists():
        cmd.extend(["--odds", str(odds_path)])

    if calibrate:
        cmd.append("--calibrate")

    success = run_command(cmd, description="Generate tournament predictions", timeout=900)

    if success and output_path.exists():
        print(f"\n  Predictions saved to: {output_path}")
        # Compute SHAP values immediately after predictions so the dashboard
        # always has fresh explainability data
        run_command(
            ["python3", str(SCRIPTS_DIR / "validation" / "compute_shap.py")],
            description="Compute SHAP feature importance",
            timeout=120,
        )
        run_command(
      ["python3", str(SCRIPTS_DIR / "validation" / "monte_carlo.py")],
      description="Run Monte Carlo simulation",
      timeout=60,
  )
        run_command(
      ["python3", str(SCRIPTS_DIR / "validation" / "player_similarity.py")],
      "Player Similarity",
      timeout=60,
  )
        return output_path

    if _ACTIVE_TRACKER is not None and success and (not output_path.exists()):
        _ACTIVE_TRACKER.record_manual_step(
            name="Validate predictions output file",
            success=False,
            command=cmd,
            error=f"Predictions command succeeded but output missing: {output_path}",
        )

    return None


def generate_calibration_report() -> bool:
    """
    Regenerate calibration diagnostics and a lightweight markdown summary.
    """
    print_header("CALIBRATION REPORT")
    success = run_command(
        ["python3", str(SCRIPTS_DIR / "validation" / "generate_calibration_data.py")],
        description="Generate calibration diagnostics",
        timeout=300,
    )
    if not success:
        print("  Warning: calibration report generation failed, continuing...")
        return False

    cal_path = OUTPUTS_DIR / "calibration_data.json"
    if not cal_path.exists():
        if _ACTIVE_TRACKER is not None:
            _ACTIVE_TRACKER.record_manual_step(
                name="Validate calibration output file",
                success=False,
                command=["python3", str(SCRIPTS_DIR / "validation" / "generate_calibration_data.py")],
                error=f"Calibration script succeeded but output missing: {cal_path}",
            )
        return True

    summary_path = OUTPUTS_DIR / "calibration_report_latest.md"
    try:
        data = json.loads(cal_path.read_text())
        lines = [
            "# Calibration Report",
            "",
            f"- Generated at: {data.get('generated_at', '')}",
            f"- Train rows: {data.get('n_train', '')}",
            f"- Test rows: {data.get('n_test', '')}",
            "",
            "| Model | AUC | Brier | Pred Avg | Actual Avg | Cal Ratio |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for key in ["win", "top5", "top10", "top20"]:
            md = (data.get("models") or {}).get(key, {})
            if not md:
                continue
            lines.append(
                f"| {md.get('display_name', key)} | "
                f"{float(md.get('auc', 0.0)):.4f} | "
                f"{float(md.get('brier', 0.0)):.4f} | "
                f"{float(md.get('pred_avg', 0.0)) * 100:.2f}% | "
                f"{float(md.get('actual_avg', 0.0)) * 100:.2f}% | "
                f"{float(md.get('cal_ratio', 0.0)):.2f}x |"
            )
        summary_path.write_text("\n".join(lines))
        print(f"  Calibration summary saved to: {summary_path}")
    except Exception as e:
        print(f"  Warning: failed writing calibration markdown summary: {e}")
    return True


def rerun_failed_step(step_id: str = "") -> bool:
    """
    Re-run one failed command from the latest pipeline status artifact.
    """
    if not PIPELINE_STATUS_PATH.exists():
        print(f"No pipeline status file found: {PIPELINE_STATUS_PATH}")
        return False

    try:
        status = json.loads(PIPELINE_STATUS_PATH.read_text())
    except Exception as e:
        print(f"Could not read pipeline status file: {e}")
        return False

    failed = [s for s in (status.get("steps") or []) if str(s.get("status", "")).lower() == "failed"]
    if not failed:
        print("No failed steps found in latest pipeline run.")
        return False

    target = None
    if step_id:
        for s in failed:
            if str(s.get("id", "")).strip() == str(step_id).strip():
                target = s
                break
        if target is None:
            print(f"Failed step id not found: {step_id}")
            print("Available failed step ids:", ", ".join([str(s.get("id", "")) for s in failed]))
            return False
    else:
        target = failed[-1]

    cmd = target.get("command") or []
    if not isinstance(cmd, list) or not cmd:
        print(f"Failed step {target.get('id', '')} has no runnable command.")
        return False

    print_header("RETRY FAILED STEP")
    print(f"  Run ID: {status.get('run_id', '')}")
    print(f"  Step:   {target.get('id', '')} - {target.get('name', '')}")
    print(f"  Cmd:    {' '.join([str(x) for x in cmd])}")
    timeout = target.get("timeout_seconds")
    return run_command(
        cmd,
        description=f"Retry failed step {target.get('id', '')}",
        timeout=int(timeout) if timeout else None,
    )


def run_lineup_recommendation(
    tournament_name: str,
    predictions_path: Path = None,
):
    """Run strategic lineup recommendation."""
    print_header("LINEUP RECOMMENDATION")

    # golf_assistant.py retired — use golf_chatbot.py via the dashboard assistant
    print("  Lineup recommendation is available in the dashboard Golf Assistant tab.")
    return

    if "error" in result:
        print(f"  Error: {result['error']}")
        return

    print(f"\n  Tournament: {result['tournament_name']}")
    print(f"  Tier: {result.get('tournament_importance', 'N/A')}/10 importance")
    print()

    for reason in result['reasoning']:
        print(f"  {reason}")

    if result.get('strategic_notes'):
        print("\n  Strategic Notes:")
        for note in result['strategic_notes']:
            print(f"    - {note}")

    print("\n  RECOMMENDED LINEUP:")
    print("  " + "-" * 60)

    for i, player in enumerate(result['lineup'], 1):
        uses = player.get('uses_remaining', '?')
        rec = player.get('usage_recommendation', '')
        print(f"  {i}. {player['name']}")
        print(f"     EV: ${player['ev']:,.0f} | Win: {player['win_prob']*100:.1f}% | Uses: {uses}")
        if rec and rec not in ['USE', 'STRONG USE']:
            print(f"     Note: {rec}")


def run_bet_recommendations(
    tournament_id: str,
    predictions_path: Optional[Path] = None,
):
    """Generate deterministic tracked betting recommendations."""
    if not tournament_id:
        print("\n  Skipping bet recommendations - no tournament ID provided")
        return False

    print_header("BET RECOMMENDATIONS")
    cmd = [
        "python3",
        str(SCRIPTS_DIR / "models" / "recommend_bets.py"),
        "--tournament-id",
        str(tournament_id).strip().upper(),
        "--min-confidence",
        "0.60",
        "--min-edge-points",
        "1.00",
        "--min-ev",
        "0.00",
    ]
    if predictions_path and Path(predictions_path).exists():
        cmd.extend(["--predictions", str(predictions_path)])

    success = run_command(cmd, description="Generate bet recommendations", timeout=300)
    if not success:
        print("  Warning: recommendation generation failed, continuing...")
    return success


def _artifact_age_hours(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    return (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0


def _file_updated_since(path: Path, run_started_at: datetime, grace_seconds: int = 120) -> bool:
    if not path.exists():
        return False
    return path.stat().st_mtime >= (run_started_at.timestamp() - grace_seconds)


def run_post_run_sanity_checks(
    tournament_name: str,
    tournament_id: str,
    field_file: Path,
    predictions_path: Path,
    run_started_at: datetime,
) -> tuple[bool, str]:
    """
    Validate that core artifacts exist and are usable for downstream dashboard pages.
    Returns (ok, details). On failure, details includes actionable reason(s).
    """
    print_header("POST-RUN SANITY CHECKS")

    tid = str(tournament_id or "").strip().upper()
    failures: List[str] = []
    notes: List[str] = []

    # 1) Field file must exist and be non-empty.
    if not field_file or not Path(field_file).exists():
        failures.append(f"Field file missing: {field_file}")
    else:
        try:
            _field_df = pd.read_csv(field_file)
            if _field_df.empty:
                failures.append(f"Field file is empty: {field_file}")
            else:
                notes.append(f"✓ Field: {field_file} ({len(_field_df)} players)")
        except Exception as e:
            failures.append(f"Field file unreadable: {field_file} ({e})")

    # 2) Predictions output must exist and be updated this run.
    pred_path = Path(predictions_path)
    if not pred_path.exists():
        failures.append(f"Predictions output missing: {pred_path}")
    else:
        try:
            _pred_df = pd.read_csv(pred_path)
            if _pred_df.empty:
                failures.append(f"Predictions output is empty: {pred_path}")
            else:
                notes.append(f"✓ Predictions output: {pred_path} ({len(_pred_df)} rows)")
            if not _file_updated_since(pred_path, run_started_at):
                failures.append(f"Predictions output not updated this run: {pred_path}")
        except Exception as e:
            failures.append(f"Predictions output unreadable: {pred_path} ({e})")

    # 3) latest_predictions.csv must also be updated this run (dashboard dependency).
    latest_preds = OUTPUTS_DIR / "latest_predictions.csv"
    if not latest_preds.exists():
        failures.append(f"Missing dashboard pointer file: {latest_preds}")
    elif not _file_updated_since(latest_preds, run_started_at):
        failures.append(f"Stale dashboard pointer file (not updated this run): {latest_preds}")
    else:
        notes.append(f"✓ Dashboard latest predictions updated: {latest_preds}")

    # 4) Tournament odds existence check (if tournament context available).
    if tid:
        pga_odds_file = DATA_DIR / "odds" / f"pga_odds_{tid}.csv"
        dk_props_file = DATA_DIR / "odds" / f"prop_lines_{tid}.csv"
        has_odds = pga_odds_file.exists() or dk_props_file.exists()
        if not has_odds:
            failures.append(
                f"No tournament odds files found for {tid} "
                f"(expected one of: {pga_odds_file.name}, {dk_props_file.name})"
            )
        else:
            if pga_odds_file.exists():
                age = _artifact_age_hours(pga_odds_file)
                notes.append(f"✓ PGA odds: {pga_odds_file.name} (age {age:.1f}h)")
            if dk_props_file.exists():
                age = _artifact_age_hours(dk_props_file)
                notes.append(f"✓ DK props: {dk_props_file.name} (age {age:.1f}h)")

    # 5) Tournament-scoped latest file should exist for the requested tournament.
    safe_tournament = re.sub(r"[^a-z0-9]+", "_", str(tournament_name).lower()).strip("_")
    scoped_latest = OUTPUTS_DIR / f"{safe_tournament}_latest.csv"
    if scoped_latest.exists():
        notes.append(f"✓ Tournament scoped predictions: {scoped_latest.name}")
    else:
        notes.append(f"ℹ Tournament scoped predictions not found: {scoped_latest.name}")

    for line in notes:
        print(f"  {line}")
    if failures:
        print("  ❌ Sanity checks failed:")
        for msg in failures:
            print(f"    - {msg}")
    else:
        print("  ✅ All sanity checks passed")

    details = "\n".join(notes + ([f"FAIL: {f}" for f in failures] if failures else []))
    ok = len(failures) == 0
    if _ACTIVE_TRACKER is not None:
        _ACTIVE_TRACKER.record_manual_step(
            name="Post-run artifact sanity checks",
            success=ok,
            command=[],
            error="\n".join(failures),
            stdout=details,
        )
    return ok, details


def fetch_tournament_assets(
    tournament_name: str,
    pga_id: str,
    field_path: Path,
    power_slug: str = None,
    odds_max_age_hours: float = 6.0,
    force_odds_refresh: bool = False,
    dk_props_max_age_hours: float = 6.0,
    force_dk_props_refresh: bool = False,
    fetch_expert_picks: bool = True,
    fetch_articles: bool = False,
    article_template: str = None,
):
    """Fetch tournament assets used by dashboard and betting workflow."""
    print_header("TOURNAMENT ASSETS")

    def _csv_has_rows(path: Path) -> bool:
        if not path or not path.exists():
            return False
        try:
            probe = pd.read_csv(path, nrows=1)
            return not probe.empty
        except Exception:
            return False

    total_stages = 5
    if fetch_expert_picks and pga_id:
        total_stages += 1
    if fetch_articles and article_template:
        total_stages += 1

    stage_idx = 1
    dk_props_path = None
    if pga_id:
        dk_props_path = DATA_DIR / "odds" / f"prop_lines_{pga_id}.csv"
        dk_cards_path = DATA_DIR / "odds" / f"dk_content_cards_{pga_id}.csv"
        print_stage(stage_idx, total_stages, "Fetch DraftKings props")
        props_fresh = check_file_fresh(dk_props_path, max_age_hours=dk_props_max_age_hours)
        cards_fresh = check_file_fresh(dk_cards_path, max_age_hours=dk_props_max_age_hours)
        cards_non_empty = _csv_has_rows(dk_cards_path)
        if (not force_dk_props_refresh) and props_fresh and cards_fresh and cards_non_empty:
            print(
                "  Skipping DraftKings props - fresh prop + content-card files exist "
                f"({dk_props_path.name}, {dk_cards_path.name}, <= {dk_props_max_age_hours:.1f}h old)"
            )
        else:
            run_command([
                "python3",
                str(SCRIPTS_DIR / "scrapers" / "fetch_draftkings_props.py"),
                "--tournament-id",
                pga_id,
                "--no-snapshot",
                "--fetch-profile",
                "fast",
            ], description="Fetch DraftKings props", timeout=45)
            if not dk_props_path.exists():
                print("  Info: DK odds not live yet — try again Wednesday/Thursday")
        stage_idx += 1

    odds_path = None
    if pga_id:
        odds_path = DATA_DIR / "odds" / f"pga_odds_{pga_id}.csv"
        print_stage(stage_idx, total_stages, "Fetch betting odds")
        if (not force_odds_refresh) and check_file_fresh(odds_path, max_age_hours=odds_max_age_hours):
            print(f"  Skipping odds fetch - fresh file exists ({odds_path.name}, <= {odds_max_age_hours:.1f}h old)")
        else:
            run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_pga_odds.py"),
                         "--tournament-id", pga_id,
                         "--output", str(odds_path)],
                        description="Fetch PGA odds", timeout=60)
        stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch betting profiles")
    bp_out = DATA_DIR / "betting_profiles" / f"betting_profiles_{pga_id}.csv"
    bp_fresh = check_file_fresh(bp_out, max_age_hours=12)
    if bp_fresh and _csv_has_rows(bp_out):
        print(f"  Skipping betting profiles - fresh file exists ({bp_out.name})")
    else:
        bp_cmd = [
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_betting_profiles.py"),
            "--tournament-id", pga_id,
            "--field", str(field_path),
            "--output", str(bp_out),
        ]
        if odds_path and odds_path.exists():
            bp_cmd.extend(["--odds-csv", str(odds_path)])
        run_command(bp_cmd, description="Fetch betting profiles", timeout=60)
    stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch power rankings")
    slug = power_slug or slugify(tournament_name)
    run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_power_rankings.py"),
                 "--slug", slug, "--allow-fail"],
                description="Fetch power rankings", timeout=45)
    stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch course characteristics")
    run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_course_characteristics.py"),
                 "--tournament-id", pga_id, "--profile"],
                description="Fetch course characteristics", timeout=45)
    stage_idx += 1

    if fetch_expert_picks and pga_id:
        print_stage(stage_idx, total_stages, "Fetch expert picks")
        success = run_command([
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_expert_picks_pga.py"),
            "--tournament-id", pga_id,
        ], description="Fetch expert picks", timeout=60)
        if not success:
            print("  Warning: expert picks fetch failed, continuing...")
        stage_idx += 1

    if fetch_articles and article_template:
        print_stage(stage_idx, total_stages, "Fetch betting profile articles")
        run_command([
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_betting_profile_articles.py"),
            "--field-csv", str(field_path),
            "--url-template", article_template,
            "--output", str(DATA_DIR / "betting_profiles" / "article_blurbs.csv"),
        ], description="Fetch betting profile articles", timeout=60)

    return odds_path


def run_full_pipeline(
    tournament_name: str,
    purse: int,
    field_path: str = None,
    pga_id: str = None,
    tournament_type: str = "Standard",
    skip_refresh: bool = False,
    insights: bool = False,
    insights_ollama: bool = False,
    recommend_lineup: bool = False,
    save_tracking: bool = False,
    power_slug: str = None,
    odds_max_age_hours: float = 6.0,
    force_odds_refresh: bool = False,
    dk_props_max_age_hours: float = 6.0,
    force_dk_props_refresh: bool = False,
    fetch_expert_picks: bool = True,
    fetch_articles: bool = False,
    article_template: str = None,
    calibrate: bool = False,
    generate_bet_recs: bool = True,
):
    """Run the full prediction pipeline."""
    global _ACTIVE_TRACKER
    tracker = PipelineRunTracker(
        run_type="full_pipeline",
        tournament_name=tournament_name,
        tournament_id=str(pga_id or ""),
    )
    _ACTIVE_TRACKER = tracker

    pipeline_success = False
    pipeline_error = ""

    try:
        print_header(f"GOLF PREDICTION PIPELINE: {tournament_name}", "=")
        print(f"  Purse: ${purse:,}")
        print(f"  Type: {tournament_type}")
        print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        run_started_at = datetime.now()

        # Stage 1: Data refresh
        if not skip_refresh:
            refresh_data(force=False, max_age_hours=24)
        else:
            print("\n  Skipping data refresh (--skip-refresh)")

        # Stage 2: Get field
        print_header("TOURNAMENT FIELD")

        if field_path:
            field_file = Path(field_path)
            if not field_file.exists():
                raise FileNotFoundError(f"Field file not found: {field_path}")
            print(f"  Using provided field: {field_file}")
        else:
            # Try to find existing field file (canonical ID lookup first, then fuzzy name)
            field_file = find_field_file(tournament_name, tournament_id=pga_id)

            if field_file:
                print(f"  Found existing field: {field_file}")
            elif pga_id:
                # Try to fetch from PGA TOUR
                field_file = fetch_field_from_pga(tournament_name, pga_id)

        if not field_file:
            raise RuntimeError(
                "No field file found. Provide --field or --pga-id so the pipeline can fetch one."
            )

        # Stage 2b: Fetch tournament assets (odds, profiles, rankings)
        odds_path = None
        if pga_id:
            odds_path = fetch_tournament_assets(
                tournament_name=tournament_name,
                pga_id=pga_id,
                field_path=field_file,
                power_slug=power_slug,
                odds_max_age_hours=odds_max_age_hours,
                force_odds_refresh=force_odds_refresh,
                dk_props_max_age_hours=dk_props_max_age_hours,
                force_dk_props_refresh=force_dk_props_refresh,
                fetch_expert_picks=fetch_expert_picks,
                fetch_articles=fetch_articles,
                article_template=article_template,
            )

        # Stage 3: Run predictions
        predictions_path = run_predictions(
            tournament_name=tournament_name,
            purse=purse,
            field_path=field_file,
            tournament_type=tournament_type,
            insights=insights,
            insights_ollama=insights_ollama,
            save_tracking=save_tracking,
            odds_path=odds_path,
            calibrate=calibrate,
        )
        if not predictions_path:
            raise RuntimeError("Prediction stage failed: no output file was created.")

        # Stage 4: Calibration report (always refresh after predictions).
        generate_calibration_report()

        # Stage 5: Deterministic tracked bet recommendations.
        if generate_bet_recs and pga_id:
            run_bet_recommendations(pga_id, predictions_path=predictions_path)

        # Stage 6: Lineup recommendation (if requested separately)
        if recommend_lineup:
            run_lineup_recommendation(tournament_name, predictions_path)

        # Stage 7: Validate expected artifacts for downstream consumers.
        sanity_ok, sanity_details = run_post_run_sanity_checks(
            tournament_name=tournament_name,
            tournament_id=str(pga_id or ""),
            field_file=Path(field_file),
            predictions_path=Path(predictions_path),
            run_started_at=run_started_at,
        )
        if not sanity_ok:
            raise RuntimeError(f"Post-run sanity checks failed:\n{sanity_details}")

        print_header("PIPELINE COMPLETE", "=")
        pipeline_success = True
    except Exception as e:
        pipeline_error = f"{e}\n{traceback.format_exc()}"
        print(f"\nPipeline failed: {e}")
    finally:
        if _ACTIVE_TRACKER is not None:
            _ACTIVE_TRACKER.finalize(success=pipeline_success, error=pipeline_error)
        _ACTIVE_TRACKER = None


def weekly_refresh():
    """Run weekly data refresh for all sources."""
    global _ACTIVE_TRACKER
    tracker = PipelineRunTracker(run_type="weekly_refresh")
    _ACTIVE_TRACKER = tracker

    ok = False
    err = ""
    try:
        print_header("WEEKLY DATA REFRESH")
        print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Force refresh all data
        refresh_data(force=True)

        # Update player database
        print("\n  Updating master player database...")
        script_path = SCRIPTS_DIR / "scrapers" / "fetch_player_database.py"
        if script_path.exists():
            run_command(["python3", str(script_path)], description="Weekly player database refresh")

        print_header("WEEKLY REFRESH COMPLETE")
        ok = True
    except Exception as e:
        err = f"{e}\n{traceback.format_exc()}"
        print(f"\nWeekly refresh failed: {e}")
    finally:
        if _ACTIVE_TRACKER is not None:
            _ACTIVE_TRACKER.finalize(success=ok, error=err)
        _ACTIVE_TRACKER = None


def main():
    parser = argparse.ArgumentParser(
        description='Golf Prediction Pipeline Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic prediction
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000

  # With existing field file
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
      --field data/fields/masters_2026.csv

  # Full pipeline with insights and lineup
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
      --insights-ollama --lineup

  # Skip data refresh (use cached)
  python scripts/run_pipeline.py --tournament "Phoenix Open" --purse 9600000 \\
      --skip-refresh

  # Weekly refresh only (no predictions)
  python scripts/run_pipeline.py --weekly-refresh
        """
    )

    # Tournament options
    parser.add_argument('--tournament', '-t', help='Tournament name')
    parser.add_argument('--purse', '-p', type=int, help='Tournament purse in dollars')
    parser.add_argument('--tournament-type', default='Standard',
                       choices=['Standard', 'Signature', 'Major', 'Playoff'],
                       help='Tournament type (default: Standard)')
    parser.add_argument('--use-schedule', action='store_true',
                       help='Override purse/type using data/raw/schedule_2026.csv')
    parser.add_argument('--schedule-path', type=str, default=str(SCHEDULE_PATH),
                       help='Schedule CSV path (default: data/raw/schedule_2026.csv)')
    parser.add_argument('--auto-weekly', action='store_true',
                       help='Auto-pick current week tournament from schedule and run pipeline')

    # Field options
    parser.add_argument('--field', '-f', help='Path to field CSV file')
    parser.add_argument('--pga-id', help='PGA TOUR tournament ID to fetch field')
    parser.add_argument('--power-slug', help='Power rankings slug (from data/power_rankings/paths.csv)')
    parser.add_argument('--odds-max-age-hours', type=float, default=6.0,
                       help='Skip PGA odds refresh if existing odds file is newer than this many hours (default: 6)')
    parser.add_argument('--force-odds-refresh', action='store_true',
                       help='Force PGA odds refresh even if cached odds are fresh')
    parser.add_argument('--dk-max-age-hours', type=float, default=6.0,
                       help='Skip DraftKings props refresh if existing props file is newer than this many hours (default: 6)')
    parser.add_argument('--force-dk-refresh', action='store_true',
                       help='Force DraftKings props refresh even if cached props are fresh')
    parser.add_argument('--skip-expert-picks', action='store_true',
                       help='Skip expert picks fetch in tournament assets stage')
    parser.add_argument('--skip-bet-recs', action='store_true',
                       help='Skip deterministic bet recommendation generation after predictions')
    parser.add_argument('--fetch-articles', action='store_true',
                       help='Fetch betting profile articles (requires --article-template)')
    parser.add_argument('--article-template', help='URL template for betting profile articles (with {name_slug})')

    # Pipeline control
    parser.add_argument('--skip-refresh', action='store_true',
                       help='Skip data refresh, use cached data')
    parser.add_argument('--refresh-only', action='store_true',
                       help='Only refresh data, no predictions')
    parser.add_argument('--weekly-refresh', action='store_true',
                       help='Run weekly data refresh')
    parser.add_argument('--rerun-failed-step', nargs='?', const='',
                       help='Re-run one failed command from logs/pipeline_status_latest.json (optional step id)')

    # Output options
    parser.add_argument('--insights', action='store_true',
                       help='Generate rule-based insights')
    parser.add_argument('--insights-ollama', action='store_true',
                       help='Generate LLM insights via Ollama')
    parser.add_argument('--lineup', action='store_true',
                       help='Generate strategic lineup recommendation')
    parser.add_argument('--save-tracking', action='store_true',
                       help='Save predictions to tracking system')
    parser.add_argument('--calibrate', action='store_true',
                       help='Apply probability calibration factors')

    args = parser.parse_args()

    # Ensure we're in the project directory
    os.chdir(PROJECT_ROOT)

    if args.rerun_failed_step is not None:
        rerun_failed_step(args.rerun_failed_step)
        return

    # Weekly refresh mode
    if args.weekly_refresh:
        weekly_refresh()
        return

    # Auto weekly pipeline from schedule
    if args.auto_weekly:
        row = find_schedule_row(on_date=datetime.now().strftime("%Y-%m-%d"),
                                schedule_path=Path(args.schedule_path))
        if not row:
            print("Error: Could not find a tournament for the current date in schedule.")
            return
        args.tournament = row.get("tournament_name")
        args.purse = int(row.get("purse") or 0)
        if row.get("tournament_type"):
            args.tournament_type = str(row.get("tournament_type")).title()
        if row.get("tournament_id"):
            args.pga_id = str(row.get("tournament_id"))
        if row.get("power_slug") and not args.power_slug:
            args.power_slug = str(row.get("power_slug"))


    # If schedule override requested (or purse missing), fill from schedule
    if (args.use_schedule or args.purse is None) and args.tournament:
        row = find_schedule_row(tournament_name=args.tournament,
                                schedule_path=Path(args.schedule_path))
        if row:
            if args.purse is None or args.use_schedule:
                _purse_raw = str(row.get("purse") or "0").replace("$", "").replace(",", "").strip()
                args.purse = int(float(_purse_raw)) if _purse_raw else 0
            if args.use_schedule and row.get("tournament_type"):
                args.tournament_type = str(row.get("tournament_type")).title()
            if args.use_schedule and row.get("tournament_id") and not args.pga_id:
                args.pga_id = str(row.get("tournament_id"))
            if args.use_schedule and row.get("power_slug") and not args.power_slug:
                args.power_slug = str(row.get("power_slug"))
        else:
            print("Warning: tournament not found in schedule; using provided values.")

    # Refresh only mode
    if args.refresh_only:
        global _ACTIVE_TRACKER
        tracker = PipelineRunTracker(run_type="refresh_only")
        _ACTIVE_TRACKER = tracker
        ok = False
        err = ""
        try:
            refresh_data(force=True)
            ok = True
        except Exception as e:
            err = f"{e}\n{traceback.format_exc()}"
            print(f"Refresh-only failed: {e}")
        finally:
            if _ACTIVE_TRACKER is not None:
                _ACTIVE_TRACKER.finalize(success=ok, error=err)
            _ACTIVE_TRACKER = None
        return

    # Require tournament and purse for predictions
    if not args.tournament or not args.purse:
        parser.print_help()
        print("\nError: --tournament and --purse are required for predictions")
        print("\nOr use --weekly-refresh for data updates only")
        return

    # Run full pipeline
    run_full_pipeline(
        tournament_name=args.tournament,
        purse=args.purse,
        field_path=args.field,
        pga_id=args.pga_id,
        tournament_type=args.tournament_type,
        skip_refresh=args.skip_refresh,
        insights=args.insights,
        insights_ollama=args.insights_ollama,
        recommend_lineup=args.lineup,
        save_tracking=args.save_tracking,
        power_slug=args.power_slug,
        odds_max_age_hours=args.odds_max_age_hours,
        force_odds_refresh=args.force_odds_refresh,
        dk_props_max_age_hours=args.dk_max_age_hours,
        force_dk_props_refresh=args.force_dk_refresh,
        fetch_expert_picks=(not args.skip_expert_picks),
        generate_bet_recs=(not args.skip_bet_recs),
        fetch_articles=args.fetch_articles,
        article_template=args.article_template,
        calibrate=args.calibrate,
    )


if __name__ == '__main__':
    main()
