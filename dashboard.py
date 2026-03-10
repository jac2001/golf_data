#!/usr/bin/env python3
"""
Golf Fantasy Dashboard
======================

Interactive dashboard for fantasy golf strategy and predictions.

Usage:
    streamlit run dashboard.py
    streamlit run dashboard.py --server.port 8501
"""

import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import ast
import plotly.graph_objects as go
import subprocess
import textwrap
import shlex
import time
from datetime import datetime
import plotly.express as px
import requests
import re
import plotly.graph_objects as go
import unicodedata

from scripts.predictions.refresh_odds import refresh_odds

try:
    from scripts.props.prop_odds_edges import (
        load_latest_prop_lines,
        score_book_props,
        score_parlay,
    )
    prop_edge_tools_available = True
except Exception:
    load_latest_prop_lines = None
    score_book_props = None
    score_parlay = None
    prop_edge_tools_available = False

# Market availability and betting recommendations
try:
    from scripts.models.market_availability import (
        scan_all_availability,
        load_availability,
        get_staleness_badge,
        get_source_label,
        MarketType,
        DataSource,
        Staleness,
    )
    market_availability_available = True
except Exception:
    market_availability_available = False

try:
    from scripts.models.betting_recommendations import (
        generate_recommendations,
        get_edge_summary,
        format_slip_for_display,
        RiskProfile,
    )
    betting_recs_available = True
except Exception:
    betting_recs_available = False

# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
PLANNING_DIR = PROJECT_ROOT / "scripts" / "planning"

# Add planning dir to path for imports
sys.path.insert(0, str(PLANNING_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))

# Page config
st.set_page_config(
    page_title="Golf Fantasy Dashboard",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS — dark navy golf theme
st.markdown("""
<style>
    /* ── Global ─────────────────────────────────────── */
    .stApp { background-color: #080f1e; }
    .main .block-container { padding-top: 1rem; padding-bottom: 2rem; }

    /* ── Sidebar nav panel ──────────────────────────── */
    [data-testid="stSidebar"] {
        background-color: #0d1a30;
        border-right: 1px solid #1c2f4a;
    }
    [data-testid="stSidebar"] .stMarkdown h2 {
        color: #00c44f;
        font-size: 1.1rem;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    /* Radio nav items in sidebar */
    [data-testid="stSidebar"] .stRadio > label { display: none; }
    [data-testid="stSidebar"] .stRadio > div {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    [data-testid="stSidebar"] .stRadio label {
        padding: 9px 14px;
        border-radius: 7px;
        font-size: 13px;
        font-weight: 500;
        color: #7a90b8;
        cursor: pointer;
        transition: all 0.15s;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(0,196,79,0.12);
        color: #dde6f5;
    }

    /* ── Metrics ─────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: #0d1a30;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        border: 1px solid #1c2f4a;
    }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.78rem; color: #7a90b8; text-transform: uppercase; letter-spacing: 0.5px; }

    /* ── Tabs ────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: #0d1a30;
        border-radius: 10px;
        padding: 4px;
        border: 1px solid #1c2f4a;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 7px 16px;
        border-radius: 7px;
        color: #7a90b8;
        font-size: 13px;
        font-weight: 500;
        border: none;
        background: transparent;
    }
    .stTabs [aria-selected="true"] {
        background: #00c44f !important;
        color: #fff !important;
        font-weight: 600;
    }

    /* ── Dataframes ──────────────────────────────────── */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

    /* ── Buttons ─────────────────────────────────────── */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.15s;
    }
    .stButton > button[kind="primary"] {
        background: #00c44f;
        border: none;
        color: #fff;
    }
    .stButton > button[kind="primary"]:hover { background: #00a843; }

    /* ── Chat ────────────────────────────────────────── */
    [data-testid="stChatMessage"] { padding: 0.75rem 1rem; }
    [data-testid="stChatMessage"] table { font-size: 0.85rem; }

    /* ── Tournament banner ───────────────────────────── */
    .tourney-banner {
        background: linear-gradient(135deg, #0d1a30 0%, #0a2240 100%);
        border: 1px solid #1c3a5e;
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .tourney-name {
        font-size: 1.6rem;
        font-weight: 800;
        color: #fff;
        letter-spacing: -0.3px;
        margin: 0 0 4px 0;
    }
    .tourney-meta { color: #6a84aa; font-size: 13px; margin: 0 0 14px 0; }
    .tourney-pills { display: flex; gap: 10px; flex-wrap: wrap; }
    .pill {
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    .pill-green  { background: rgba(0,196,79,0.15);  color: #00c44f;  border: 1px solid rgba(0,196,79,0.3); }
    .pill-gold   { background: rgba(244,196,48,0.15); color: #f4c430;  border: 1px solid rgba(244,196,48,0.3); }
    .pill-blue   { background: rgba(33,150,243,0.15); color: #4cb8ff;  border: 1px solid rgba(33,150,243,0.3); }
    .pill-red    { background: rgba(255,80,80,0.15);  color: #ff6060;  border: 1px solid rgba(255,80,80,0.3); }

    /* ── Lineup slot cards ───────────────────────────── */
    .lineup-section { margin: 16px 0 20px 0; }
    .lineup-label {
        font-size: 11px;
        font-weight: 700;
        color: #4a6080;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 10px;
    }
    .lineup-card {
        background: linear-gradient(160deg, #0d1f38 0%, #0a1828 100%);
        border: 1px solid #1c3a5e;
        border-radius: 14px;
        padding: 16px;
        text-align: center;
        position: relative;
        min-height: 170px;
    }
    .lineup-card.active { border-color: #00c44f; box-shadow: 0 0 14px rgba(0,196,79,0.15); }
    .lineup-card.empty  { border: 2px dashed #1c3a5e; opacity: 0.6; }
    .lc-rank { font-size: 11px; color: #4a6080; margin-bottom: 6px; }
    .lc-name { font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 4px; line-height: 1.2; }
    .lc-wr   { font-size: 12px; color: #7a90b8; margin-bottom: 12px; }
    .lc-stats { display: flex; justify-content: space-around; margin-bottom: 12px; }
    .lc-stat-val { font-size: 16px; font-weight: 700; color: #00c44f; }
    .lc-stat-label { font-size: 9px; color: #4a6080; text-transform: uppercase; letter-spacing: 0.5px; }
    .lc-uses { font-size: 12px; color: #5a7088; margin-bottom: 10px; }
    .lc-badge-use  { background: rgba(0,196,79,0.15); color: #00c44f; border: 1px solid rgba(0,196,79,0.4); border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: 700; display: inline-block; }
    .lc-badge-save { background: rgba(255,160,0,0.15); color: #ffa000; border: 1px solid rgba(255,160,0,0.4); border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: 700; display: inline-block; }

    /* ── Player pool cards ───────────────────────────── */
    .pool-card {
        background: #0d1a30;
        border: 1px solid #1c2f4a;
        border-radius: 12px;
        padding: 14px 12px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: border-color 0.15s;
    }
    .pool-card:hover { border-color: #00c44f; }
    .pool-card.save-card  { border-left: 3px solid #ffa000; opacity: 0.75; }
    .pool-card.cant-card  { border-left: 3px solid #e53935; opacity: 0.5; }
    .pool-card.use-card   { border-left: 3px solid #00c44f; }
    .pc-rank  { font-size: 11px; color: #4a6080; width: 28px; text-align: right; flex-shrink: 0; }
    .pc-name  { font-size: 14px; font-weight: 600; color: #dde6f5; flex: 1; }
    .pc-wr    { font-size: 11px; color: #4a6080; }
    .pc-stat  { font-size: 13px; font-weight: 700; color: #00c44f; min-width: 40px; text-align: right; }
    .pc-stat-label { font-size: 9px; color: #4a6080; text-transform: uppercase; }
    .pc-uses  { font-size: 11px; color: #5a7088; min-width: 36px; text-align: right; }
    .pc-badge { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 5px; min-width: 50px; text-align: center; }
    .badge-use  { background: rgba(0,196,79,0.15);  color: #00c44f; }
    .badge-save { background: rgba(255,160,0,0.12); color: #ffa000; }
    .badge-no   { background: rgba(229,57,53,0.12);  color: #e53935; }

    /* ── Legacy custom classes (kept for compatibility) ─ */
    .player-name  { font-size: 1.1rem; font-weight: 600; color: #00c44f; }
    .player-odds  { font-size: 1.3rem; font-weight: bold; color: #00c44f; }
    .prob-badge   { display: inline-block; padding: .25rem .75rem; border-radius: 20px; font-size: .85rem; font-weight: 600; }
    .prob-high    { background: rgba(0,196,79,.18);  color: #00c44f; }
    .prob-mid     { background: rgba(244,196,48,.18); color: #f4c430; }
    .prob-low     { background: rgba(122,144,184,.15); color: #7a90b8; }
    .odds-table   { width: 100%; border-collapse: collapse; }
    .odds-table th { background: #0d1a30; color: #00c44f; padding: .75rem; text-align: left; }
    .odds-table td { padding: .75rem; border-bottom: 1px solid #1c2f4a; }
    .odds-table tr:hover { background: rgba(255,255,255,0.03); }
    .best-odds    { font-weight: bold; color: #00c44f; }
    .odds-diff    { color: #ff6060; font-weight: bold; }
    .action-bar   { background: linear-gradient(90deg,#0d1a30,#0a2240); padding:1rem; border-radius:8px; margin-bottom:1rem; }
    .status-live  { color: #00c44f; font-weight: bold; }
    .status-updated { color: #5a7088; font-size: .85rem; }
    .expert-card  { background: #0d1a30; border-radius:10px; padding:1rem; margin:.5rem 0; border-left:4px solid #00c44f; }
    .expert-name  { font-weight:600; color:#00c44f; }
    .consensus-bar { background:#1c2f4a; border-radius:10px; height:8px; overflow:hidden; }
    .consensus-fill{ background:linear-gradient(90deg,#00c44f,#00a843); height:100%; border-radius:10px; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SCRIPT RUNNER
# ============================================================================

def run_script(script_name: str, *args) -> str:
    """Run a script and return its output."""
    script_path = PROJECT_ROOT / "scripts" / script_name
    cmd = ["python3", str(script_path)] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        output = result.stdout
        if result.stderr and not output:
            output = result.stderr
        return output.strip() if output else "No output"
    except subprocess.TimeoutExpired:
        return "⚠️ Script timed out after 30 seconds"
    except Exception as e:
        return f"⚠️ Error running script: {e}"


def run_scraper(cmd, timeout=120):
    """Run a scraper/pipeline command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "").strip()
        err    = (result.stderr or "").strip()
        if err:
            output = f"{output}\n{err}".strip() if output else err
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


WORKFLOW_TIMEOUTS = {
    "Tournament SG Stats": 1800,
    "Field": 300,
    "Course Info": 300,
    "Power Rankings": 300,
    "Expert Picks": 300,
    "Betting Profiles": 900,
    "DraftKings Odds": 45,
    "PGA Odds": 300,
    "Predictions": 900,
}


def workflow_timeout(step_name: str, default: int = 180) -> int:
    """Return timeout for a workflow step name."""
    return int(WORKFLOW_TIMEOUTS.get(step_name, default))


def _is_test_pipeline_run(payload: dict) -> bool:
    """Detect synthetic/test runs so they don't pollute pipeline health UI."""
    if not isinstance(payload, dict):
        return False
    run_type = str(payload.get("run_type", "")).strip().lower()
    run_id = str(payload.get("run_id", "")).strip().lower()
    tid = str(payload.get("tournament_id", "")).strip().upper()
    tname = str(payload.get("tournament_name", "")).strip().lower()
    if "test" in run_type:
        return True
    if run_id.startswith("test") or run_id.startswith("fake"):
        return True
    if tid.startswith("R999"):
        return True
    if "fake" in tname or "test" in tname:
        return True
    return False


def _latest_non_test_from_history(history_path: Path) -> dict:
    """Return the most recent non-test run from pipeline history."""
    if not history_path.exists():
        return {}
    try:
        hist = json.loads(history_path.read_text())
    except Exception:
        return {}
    if not isinstance(hist, list):
        return {}

    for entry in reversed(hist):
        if _is_test_pipeline_run(entry):
            continue
        run_file = str(entry.get("run_file", "")).strip()
        if run_file and Path(run_file).exists():
            try:
                run_data = json.loads(Path(run_file).read_text())
                if isinstance(run_data, dict) and not _is_test_pipeline_run(run_data):
                    run_data["_from_history"] = True
                    return run_data
            except Exception:
                pass
        return {
            "run_id": entry.get("run_id", ""),
            "run_type": entry.get("run_type", ""),
            "status": entry.get("status", ""),
            "started_at": entry.get("started_at", ""),
            "ended_at": entry.get("ended_at", ""),
            "tournament_name": entry.get("tournament_name", ""),
            "tournament_id": entry.get("tournament_id", ""),
            "step_count": entry.get("step_count", 0),
            "failed_count": entry.get("failed_count", 0),
            "failed_step_ids": entry.get("failed_step_ids", []),
            "steps": [],
            "_from_history": True,
        }
    return {}


def load_pipeline_status(preferred_tournament_id: str = "") -> dict:
    """Load run_pipeline status, preferring the latest run for the selected tournament."""
    status_path = LOGS_DIR / "pipeline_status_latest.json"
    history_path = LOGS_DIR / "pipeline_status_history.json"
    preferred_tid = str(preferred_tournament_id or "").strip().upper()

    latest = {}
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text())
            if isinstance(data, dict):
                latest = data
        except Exception:
            latest = {}
    if _is_test_pipeline_run(latest):
        latest = {}

    if not preferred_tid:
        if latest:
            return latest
        return _latest_non_test_from_history(history_path)

    latest_tid = str(latest.get("tournament_id", "")).strip().upper()
    if latest and latest_tid == preferred_tid:
        return latest

    # Try history for the most recent matching tournament run.
    if history_path.exists():
        try:
            hist = json.loads(history_path.read_text())
            if isinstance(hist, list):
                for entry in reversed(hist):
                    if _is_test_pipeline_run(entry):
                        continue
                    tid = str(entry.get("tournament_id", "")).strip().upper()
                    if tid != preferred_tid:
                        continue
                    run_file = str(entry.get("run_file", "")).strip()
                    if run_file and Path(run_file).exists():
                        try:
                            run_data = json.loads(Path(run_file).read_text())
                            if isinstance(run_data, dict) and (not _is_test_pipeline_run(run_data)):
                                run_data["_from_history"] = True
                                run_data["_latest_mismatch"] = True
                                run_data["_latest_run_id"] = latest.get("run_id", "")
                                run_data["_latest_tournament_id"] = latest.get("tournament_id", "")
                                run_data["_latest_tournament_name"] = latest.get("tournament_name", "")
                                return run_data
                        except Exception:
                            pass
                    # Fall back to summary entry if detailed run file is unavailable.
                    summary = {
                        "run_id": entry.get("run_id", ""),
                        "run_type": entry.get("run_type", ""),
                        "status": entry.get("status", ""),
                        "started_at": entry.get("started_at", ""),
                        "ended_at": entry.get("ended_at", ""),
                        "tournament_name": entry.get("tournament_name", ""),
                        "tournament_id": entry.get("tournament_id", ""),
                        "step_count": entry.get("step_count", 0),
                        "failed_count": entry.get("failed_count", 0),
                        "failed_step_ids": entry.get("failed_step_ids", []),
                        "steps": [],
                        "_from_history": True,
                        "_latest_mismatch": True,
                        "_no_selected_match": False,
                        "_latest_run_id": latest.get("run_id", ""),
                        "_latest_tournament_id": latest.get("tournament_id", ""),
                        "_latest_tournament_name": latest.get("tournament_name", ""),
                    }
                    return summary
        except Exception:
            pass

    # No matching history run; return latest but flag mismatch.
    if latest:
        latest["_latest_mismatch"] = (latest_tid != preferred_tid)
        latest["_no_selected_match"] = (latest_tid != preferred_tid)
    return latest


def _file_health(path: Path, stale_hours: float) -> dict:
    if not path.exists():
        return {"exists": False, "age_hours": None, "label": "missing", "ok": False}
    age_h = (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0
    if age_h <= stale_hours:
        return {"exists": True, "age_hours": age_h, "label": "fresh", "ok": True}
    return {"exists": True, "age_hours": age_h, "label": "stale", "ok": False}


def build_pipeline_health_snapshot(tournament_id: str = "") -> dict:
    """Build a compact health snapshot for pipeline diagnostics."""
    tid = str(tournament_id or "").strip().upper()
    files = [
        ("OWGR", DATA_DIR / "rankings" / "owgr_2026.csv", 48.0),
        ("Form Stats", DATA_DIR / "historical" / "form_stats_2026.csv", 48.0),
        ("Tournament SG", DATA_DIR / "historical" / "tournament_stats_2026.csv", 48.0),
        ("Predictions", OUTPUTS_DIR / "latest_predictions.csv", 36.0),
    ]
    if tid:
        files.extend([
            ("Field", DATA_DIR / "fields" / f"field_{tid}.csv", 48.0),
            ("DK Props", DATA_DIR / "odds" / f"prop_lines_{tid}.csv", 12.0),
            ("DK Cards", DATA_DIR / "odds" / f"dk_content_cards_{tid}.csv", 12.0),
            ("PGA Odds", DATA_DIR / "odds" / f"pga_odds_{tid}.csv", 12.0),
            ("Betting Profiles", DATA_DIR / "betting_profiles" / f"betting_profiles_{tid}.csv", 24.0),
            ("Expert Picks", DATA_DIR / "expert_picks" / f"expert_picks_{tid}.csv", 72.0),
        ])
    statuses = []
    for label, path, stale_h in files:
        stv = _file_health(path, stale_h)
        stv["label_name"] = label
        stv["path"] = str(path)
        statuses.append(stv)
    ok_count = sum(1 for s in statuses if s["ok"])
    return {
        "ok_count": ok_count,
        "total_count": len(statuses),
        "items": statuses,
    }


# ============================================================================
# DATA LOADING
# ============================================================================





def _scoring_engine_cache_key() -> tuple:
    """Cache key that refreshes scoring engine when key inputs/code change."""
    deps = [
        PROJECT_ROOT / "scripts" / "planning" / "scoring_engine.py",
        PROJECT_ROOT / "scripts" / "planning" / "course_history.py",
        OUTPUTS_DIR / "latest_predictions.csv",
        DATA_DIR / "fantasy" / "usage_tracker_2026.json",
        DATA_DIR / "reference" / "tournament_courses.json",
        DATA_DIR / "raw" / "schedule_2026.csv",
        DATA_DIR / "course_sg_weights.csv",
    ]

    # Include the newest betting profile file to refresh course-history-derived signals.
    bp_dir = DATA_DIR / "betting_profiles"
    if bp_dir.exists():
        bp_files = sorted(bp_dir.glob("betting_profiles_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if bp_files:
            deps.append(bp_files[0])

    key_parts = []
    for p in deps:
        try:
            key_parts.append((str(p), int(p.stat().st_mtime)))
        except Exception:
            key_parts.append((str(p), 0))
    return tuple(key_parts)


@st.cache_resource
def load_scoring_engine(cache_key: tuple):
    """Load the scoring engine with dependency-aware caching."""
    try:
        from scripts.planning.scoring_engine import ScoringEngine
        return ScoringEngine()
    except Exception as e:
        st.error(f"Failed to load scoring engine: {e}")
        return None



@st.cache_data(ttl=60)
def load_usage_data():
    """Load usage tracker data."""
    def _coerce_money(value):
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        text = text.replace("$", "").replace(",", "")
        try:
            return int(round(float(text)))
        except Exception:
            return None

    usage_file = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
    if usage_file.exists():
        with open(usage_file) as f:
            data = json.load(f)

        for player_data in data.get("picks", {}).values():
            for tournament_use in player_data.get("tournaments_used", []):
                earnings = _coerce_money(tournament_use.get("earnings", tournament_use.get("points")))
                tournament_use["earnings"] = earnings
                tournament_use["points"] = earnings
            total_earnings = _coerce_money(player_data.get("total_earnings", player_data.get("total_points")))
            if total_earnings is None:
                total_earnings = sum((t.get("earnings") or 0) for t in player_data.get("tournaments_used", []))
            player_data["total_earnings"] = total_earnings
            player_data["total_points"] = total_earnings

        for lineup in data.get("weekly_lineups", {}).values():
            earnings = _coerce_money(lineup.get("earnings_earned", lineup.get("points_earned")))
            lineup["earnings_earned"] = earnings
            lineup["points_earned"] = earnings

        summary = data.setdefault("summary", {})
        total_earnings = _coerce_money(summary.get("total_earnings", summary.get("total_points")))
        if total_earnings is None:
            total_earnings = sum(
                (player_data.get("total_earnings") or 0) for player_data in data.get("picks", {}).values()
            )
        summary["total_earnings"] = total_earnings
        summary["total_points"] = total_earnings
        return data
    return {"picks": {}, "weekly_lineups": {}, "summary": {}}


@st.cache_data(ttl=300)
def load_schedule():
    """Load tournament schedule."""
    schedule_file = DATA_DIR / "raw" / "schedule_2026.csv"
    if schedule_file.exists():
        return pd.read_csv(schedule_file)
    return pd.DataFrame()


def _resolve_master_training_data_path() -> Path | None:
    """Return canonical master training data path with fallback for legacy names."""
    processed_dir = DATA_DIR / "processed"
    preferred = processed_dir / "master_training_data.csv"
    if preferred.exists():
        return preferred

    legacy = processed_dir / "master_training_data_2020_2025.csv"
    if legacy.exists():
        return legacy

    candidates = sorted(processed_dir.glob("master_training_data*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None

@st.cache_data(ttl=3600)
def load_player_form_history(n_events: int = 8):
    """
    Load each player's last N tournament SG Total values from official
    per-event tournament stats when available.
    Returns dict keyed by player name:
    {
      "Scottie Scheffler": {
        "sg": [1.2, -0.3, 2.1, ...],
        "events": ["Sentry", "Pebble", ...],
        "event_ids": ["R2026005", ...],
      }
    }

    Falls back to master_training_data*.csv when tournament stats are missing.
    """
    hist_dir = DATA_DIR / "historical"
    sg_frames = []

    # Primary source: tournament SG per event (stat_id=2567, component=Avg).
    for p in sorted(hist_dir.glob("tournament_stats_*.csv")):
        try:
            _df = pd.read_csv(
                p,
                usecols=[
                    "player_name",
                    "year",
                    "tournament_id",
                    "tournament_name",
                    "stat_id",
                    "stat_component",
                    "stat_value",
                ],
            )
        except Exception:
            continue

        _df["stat_id"] = _df["stat_id"].astype(str)
        _df["stat_component"] = _df["stat_component"].astype(str).str.strip().str.lower()
        _df = _df[(_df["stat_id"] == "2567") & (_df["stat_component"] == "avg")].copy()
        if _df.empty:
            continue

        _df["sg_total"] = pd.to_numeric(_df["stat_value"], errors="coerce")
        _df = _df.dropna(subset=["sg_total"])
        _df = _df[["player_name", "year", "tournament_id", "tournament_name", "sg_total"]]
        sg_frames.append(_df)

    if sg_frames:
        df = pd.concat(sg_frames, ignore_index=True)
    else:
        # Fallback for older data setups.
        path = _resolve_master_training_data_path()
        if path is None or not path.exists():
            return {}
        df = pd.read_csv(path, usecols=["player_name", "year", "tournament_id", "tournament_name", "sg_total"])
        df = df.dropna(subset=["sg_total"])

    df = df.sort_values(["player_name", "year", "tournament_id"])
    out = {}

    for player, grp in df.groupby("player_name"):
        tail = grp.tail(n_events)
        short_names = tail["tournament_name"].apply(lambda s: " ".join(str(s).split()[:2])).tolist()
        out[player] = {
            "sg": tail["sg_total"].tolist(),
            "events": short_names,
            "event_ids": tail["tournament_id"].astype(str).tolist(),
        }
    return out


@st.cache_data(ttl=3600)
def load_player_recent_results(n_events: int = 8):
    """Load each player's last N recorded events from leaderboard history."""
    hist_dir = DATA_DIR / "historical"
    frames = []
    for p in sorted(hist_dir.glob("leaderboards_*.csv")):
        try:
            _df = pd.read_csv(
                p,
                usecols=["player_name", "year", "tournament_id", "tournament_name"],
            )
        except Exception:
            continue
        frames.append(_df)

    if not frames:
        return {}

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["player_name", "tournament_id"])
    df = df.sort_values(["player_name", "year", "tournament_id"])

    out = {}
    for player, grp in df.groupby("player_name"):
        tail = grp.tail(n_events)
        out[player] = {
            "event_ids": tail["tournament_id"].astype(str).tolist(),
            "events": tail["tournament_name"].astype(str).tolist(),
        }
    return out


def _normalize_tournament_key(name: str) -> str:
    """Normalize tournament names for simple cross-year matching."""
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


@st.cache_data(ttl=3600)
def load_tournament_course_lookup_keys() -> tuple[dict, dict]:
    """
    Return tournament_name_normalized -> course_key mapping from tournament_courses.json.
    Also returns course_key -> display course name.
    """
    mapping_path = DATA_DIR / "reference" / "tournament_courses.json"
    if not mapping_path.exists():
        return {}, {}
    try:
        payload = json.loads(mapping_path.read_text())
    except Exception:
        return {}, {}

    tournaments = payload.get("tournaments", {}) if isinstance(payload, dict) else {}
    tournament_to_course: dict[str, str] = {}
    course_labels: dict[str, str] = {}

    for tournament_name, details in tournaments.items():
        if not isinstance(details, dict):
            continue
        course_label = str(details.get("course_full") or details.get("course") or "").strip()
        if not course_label:
            continue
        course_key = _normalize_tournament_key(course_label)
        if not course_key:
            continue
        course_labels[course_key] = course_label

        candidate_names = [str(tournament_name)]
        candidate_names.extend([str(a) for a in details.get("aliases", []) if a])
        for cname in candidate_names:
            ckey = _normalize_tournament_key(cname)
            if ckey:
                tournament_to_course[ckey] = course_key

    return tournament_to_course, course_labels


def _position_to_finish_num(position) -> float:
    """Convert leaderboard position strings to sortable numeric finish."""
    if pd.isna(position):
        return np.nan
    s = str(position).strip().upper()
    if s.startswith("T"):
        s = s[1:]
    if s in {"CUT", "MC", "MDF", "WD", "W/D", "DQ"}:
        return 999.0
    try:
        return float(s)
    except Exception:
        return np.nan

@st.cache_data(ttl=1800)
def load_historical_player_event_results() -> pd.DataFrame:
    """
    Build event-level player history from leaderboard + SG tournament stats.
    Output rows are one player per tournament start.
    """
    hist_dir = DATA_DIR / "historical"

    lb_frames = []
    for p in sorted(hist_dir.glob("leaderboards_*.csv")):
        try:
            lb = pd.read_csv(
                p,
                usecols=[
                    "tournament_id",
                    "tournament_name",
                    "year",
                    "player_id",
                    "player_name",
                    "position",
                    "to_par",
                    "total_score",
                ],
            )
        except Exception:
            continue
        if lb.empty:
            continue
        lb_frames.append(lb)

    if not lb_frames:
        return pd.DataFrame()

    lb_all = pd.concat(lb_frames, ignore_index=True)
    lb_all["tournament_id"] = lb_all["tournament_id"].astype(str).str.strip().str.upper()
    lb_all["event_code"] = lb_all["tournament_id"].str.extract(r"(\d{3})$", expand=False)
    lb_all["tournament_key"] = lb_all["tournament_name"].apply(_normalize_tournament_key)
    _t2c, _ = load_tournament_course_lookup_keys()
    lb_all["course_key"] = lb_all["tournament_key"].map(_t2c).fillna("")
    lb_all["name_key"] = lb_all["player_name"].apply(_name_key)
    lb_all["player_id_num"] = pd.to_numeric(lb_all["player_id"], errors="coerce").astype("Int64")
    lb_all["finish_num"] = lb_all["position"].apply(_position_to_finish_num)
    lb_all["made_cut"] = lb_all["finish_num"].apply(lambda x: float(x) < 70.0 if pd.notna(x) else False)
    lb_all["top10"] = lb_all["finish_num"].apply(lambda x: float(x) <= 10.0 if pd.notna(x) else False)

    sg_frames = []
    for p in sorted(hist_dir.glob("tournament_stats_*.csv")):
        try:
            sg = pd.read_csv(
                p,
                usecols=["tournament_id", "player_id", "stat_id", "stat_component", "stat_value"],
            )
        except Exception:
            continue
        if sg.empty:
            continue
        sg["stat_id"] = sg["stat_id"].astype(str).str.strip()
        sg["stat_component"] = sg["stat_component"].astype(str).str.strip().str.lower()
        sg = sg[(sg["stat_id"] == "2567") & (sg["stat_component"] == "avg")].copy()
        if sg.empty:
            continue
        sg["tournament_id"] = sg["tournament_id"].astype(str).str.strip().str.upper()
        sg["player_id_num"] = pd.to_numeric(sg["player_id"], errors="coerce").astype("Int64")
        sg["sg_total_event"] = pd.to_numeric(sg["stat_value"], errors="coerce")
        sg = (
            sg.groupby(["tournament_id", "player_id_num"], as_index=False)["sg_total_event"]
            .mean()
        )
        sg_frames.append(sg)

    if sg_frames:
        sg_all = pd.concat(sg_frames, ignore_index=True)
        sg_all = sg_all.drop_duplicates(subset=["tournament_id", "player_id_num"], keep="last")
        merged = lb_all.merge(
            sg_all,
            on=["tournament_id", "player_id_num"],
            how="left",
        )
    else:
        merged = lb_all.copy()
        merged["sg_total_event"] = np.nan

    return merged


def _infer_tournament_id_from_field_overlap(preds_df: pd.DataFrame, min_overlap: float = 0.55) -> str:
    """
    Infer active tournament id by matching loaded predictions to field_{RYYYYNNN}.csv files.
    """
    if preds_df is None or preds_df.empty or "player_id" not in preds_df.columns:
        return ""

    pred_ids = set(pd.to_numeric(preds_df["player_id"], errors="coerce").dropna().astype(int).tolist())
    if not pred_ids:
        return ""

    fields_dir = DATA_DIR / "fields"
    if not fields_dir.exists():
        return ""

    candidates = sorted(fields_dir.glob("field_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:24]
    best_tid = ""
    best_overlap = 0.0
    for f in candidates:
        try:
            field_df = pd.read_csv(f, usecols=["player_id"])
        except Exception:
            continue
        field_ids = set(pd.to_numeric(field_df["player_id"], errors="coerce").dropna().astype(int).tolist())
        if not field_ids:
            continue

        overlap = len(pred_ids.intersection(field_ids)) / float(max(1, min(len(pred_ids), len(field_ids))))
        if overlap > best_overlap:
            best_overlap = overlap
            best_tid = _extract_tournament_id(f.stem)

    return best_tid if best_overlap >= float(min_overlap) else ""


def resolve_players_page_tournament_context(preds_df: pd.DataFrame) -> dict:
    """Resolve tournament id/name for player history panels."""
    tid = _infer_tournament_id_from_field_overlap(preds_df)
    if not tid:
        tid = _latest_tournament_id_from_prop_lines(max_age_hours=168.0)
    if not tid:
        status = load_pipeline_status()
        tid = _extract_tournament_id(status.get("tournament_id", ""))

    tname = ""
    schedule_df = load_schedule()
    if tid and not schedule_df.empty and "tournament_id" in schedule_df.columns:
        _sched = schedule_df.copy()
        _sched["tournament_id"] = _sched["tournament_id"].astype(str).str.strip().str.upper()
        row = _sched[_sched["tournament_id"] == tid]
        if not row.empty:
            tname = str(row.iloc[0].get("tournament_name", "")).strip()

    if not tname:
        status = load_pipeline_status(preferred_tournament_id=tid)
        tname = str(status.get("tournament_name", "")).strip()

    t2c, course_labels = load_tournament_course_lookup_keys()
    tkey = _normalize_tournament_key(tname)
    ckey = t2c.get(tkey, "") if tkey else ""
    course_name = course_labels.get(ckey, "")
    return {
        "tournament_id": tid,
        "tournament_name": tname,
        "course_key": ckey,
        "course_name": course_name,
    }


def get_player_history_for_current_event(player_name: str, preds_df: pd.DataFrame, max_rows: int = 12) -> tuple[pd.DataFrame, dict]:
    """Return player event history for the currently resolved tournament context."""
    context = resolve_players_page_tournament_context(preds_df)
    history = load_historical_player_event_results()
    if history.empty:
        return pd.DataFrame(), context

    name_key = _name_key(player_name)
    if not name_key:
        return pd.DataFrame(), context

    player_rows = history[history["name_key"] == name_key].copy()
    if player_rows.empty:
        return pd.DataFrame(), context

    target_course_key = str(context.get("course_key", "")).strip()
    if not target_course_key:
        # Exact-course mode: no course key means we cannot safely match.
        return pd.DataFrame(), context

    player_rows = player_rows[player_rows["course_key"] == target_course_key].copy()

    player_rows["year_num"] = pd.to_numeric(player_rows["year"], errors="coerce")
    player_rows = player_rows.sort_values(["year_num", "tournament_id"], ascending=[False, False], na_position="last")
    player_rows = player_rows.drop_duplicates(subset=["tournament_id"], keep="first").head(max_rows)

    return player_rows, context


def render_player_event_history_panel(player_name: str, preds_df: pd.DataFrame, panel_title: str = "History At This Course"):
    """Render per-player historical results for the exact course context."""
    if not player_name:
        st.info("Select a player to view exact-course history.")
        return

    _event_hist_df, _event_ctx = get_player_history_for_current_event(
        player_name,
        preds_df,
        max_rows=12,
    )
    _event_name = str(_event_ctx.get("tournament_name", "")).strip()
    _event_tid = str(_event_ctx.get("tournament_id", "")).strip().upper()
    _course_name = str(_event_ctx.get("course_name", "")).strip()

    st.markdown(f"#### {panel_title}")
    _label_parts = []
    if _event_name:
        _label_parts.append(_event_name)
    if _event_tid:
        _label_parts.append(_event_tid)
    if _course_name:
        _label_parts.append(_course_name)
    if _label_parts:
        st.caption("Exact-course historical results for: " + " • ".join(_label_parts))
    else:
        st.caption("Exact-course historical results for the currently inferred tournament context.")

    if _event_hist_df.empty:
        if not str(_event_ctx.get("course_key", "")).strip():
            st.info("Exact-course mapping is missing for this tournament in `data/reference/tournament_courses.json`.")
        else:
            st.info("No historical starts found for this player at the exact course.")
        return

    _starts = len(_event_hist_df)
    _made_cut_rate = float(pd.to_numeric(_event_hist_df["made_cut"], errors="coerce").fillna(False).mean() * 100.0)
    _top10s = int(pd.to_numeric(_event_hist_df["top10"], errors="coerce").fillna(False).sum())
    _valid_finishes = pd.to_numeric(_event_hist_df["finish_num"], errors="coerce")
    _valid_finishes = _valid_finishes[_valid_finishes < 900]
    _best_finish = int(_valid_finishes.min()) if not _valid_finishes.empty else None
    _avg_sg_event = pd.to_numeric(_event_hist_df["sg_total_event"], errors="coerce").mean()

    _hcol1, _hcol2, _hcol3, _hcol4, _hcol5 = st.columns(5)
    with _hcol1:
        st.metric("Starts", _starts)
    with _hcol2:
        st.metric("Made Cut", f"{_made_cut_rate:.0f}%")
    with _hcol3:
        st.metric("Top-10s", _top10s)
    with _hcol4:
        st.metric("Best Finish", f"T{_best_finish}" if _best_finish is not None else "—")
    with _hcol5:
        st.metric("Avg SG (Event)", f"{_avg_sg_event:+.2f}" if pd.notna(_avg_sg_event) else "—")

    _hist_table = _event_hist_df.copy()
    _hist_table["Year"] = pd.to_numeric(_hist_table["year"], errors="coerce").astype("Int64")
    _hist_table["Finish"] = _hist_table["position"].astype(str).str.strip()
    _hist_table["To Par"] = _hist_table["to_par"]
    _hist_table["SG: Total"] = pd.to_numeric(_hist_table["sg_total_event"], errors="coerce")
    _hist_table["Tournament"] = _hist_table["tournament_name"]

    _display_cols = ["Year", "Tournament", "Finish", "To Par", "SG: Total"]
    _hist_table = _hist_table[_display_cols]
    st.dataframe(
        _hist_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Year": st.column_config.NumberColumn("Year", format="%d"),
            "SG: Total": st.column_config.NumberColumn("SG: Total", format="%+.2f"),
        },
    )




def _safe_slug(name: str) -> str:
    """Create a file-safe slug."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")




@st.cache_data(ttl=120)
def load_lineup_strategies_bundle(
    preferred_tournament_name: str = "",
    preferred_tournament_id: str = "",
) -> tuple[dict, Path | None]:
    """
    Load lineup strategy JSON bundle with robust fallback:
    1) <tournament_slug>_lineup_strategies.json
    2) lineup_strategies_latest.json
    3) newest *_lineup_strategies.json
    """
    outputs_dir = PROJECT_ROOT / "outputs"
    if not outputs_dir.exists():
        return {}, None

    candidates: list[Path] = []
    tname = str(preferred_tournament_name or "").strip()
    if tname:
        slug = _safe_slug(tname)
        slug_variants = [slug]
        if slug.startswith("the_"):
            slug_variants.append(slug[4:])
        for s in slug_variants:
            if s:
                candidates.append(outputs_dir / f"{s}_lineup_strategies.json")

    latest = outputs_dir / "lineup_strategies_latest.json"
    if latest.exists():
        candidates.append(latest)

    scoped = sorted(outputs_dir.glob("*_lineup_strategies.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates.extend(scoped[:8])

    seen = set()
    ordered = []
    for p in candidates:
        if p.exists() and p not in seen:
            seen.add(p)
            ordered.append(p)

    for p in ordered:
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("profiles"), dict) and data.get("profiles"):
            return data, p

    # CSV fallback if JSON is unavailable.
    csv_candidates = []
    if tname:
        slug = _safe_slug(tname)
        csv_candidates.append(outputs_dir / f"{slug}_lineup_strategies.csv")
    csv_candidates.append(outputs_dir / "lineup_strategies_latest.csv")
    csv_candidates.extend(sorted(outputs_dir.glob("*_lineup_strategies.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:5])

    for p in csv_candidates:
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty or "profile" not in df.columns:
            continue
        profiles = {}
        for profile, g in df.groupby(df["profile"].astype(str).str.lower()):
            rows = g.to_dict(orient="records")
            profiles[str(profile)] = {
                "profile": str(profile).title(),
                "players": [str(r.get("player_name", "")).strip() for r in rows if str(r.get("player_name", "")).strip()],
                "summary": {},
                "details": rows,
            }
        if profiles:
            return {"tournament": tname, "profiles": profiles, "pool": []}, p

    return {}, None


def _format_percent_point(p: float | None, decimals: int = 1) -> str:
    """Format a percentage-point value with useful precision for small numbers."""
    if p is None or pd.isna(p):
        return "n/a"
    v = float(p)
    if v < 0.1:
        return "<0.1%"
    return f"{v:.{decimals}f}%"


def _file_updated_label(path: Path | None) -> str:
    """Format file modified timestamp for UI."""
    if path is None or not Path(path).exists():
        return "—"
    return datetime.fromtimestamp(Path(path).stat().st_mtime).strftime("%b %d %H:%M")


def _file_age_hours(path: Path | None) -> float | None:
    """Return file age in hours."""
    if path is None or not Path(path).exists():
        return None
    return (datetime.now().timestamp() - Path(path).stat().st_mtime) / 3600.0


def _freshness_status(age_hours: float | None) -> str:
    """Simple freshness status from age."""
    if age_hours is None:
        return "Missing"
    if age_hours <= 6:
        return "Fresh"
    if age_hours <= 24:
        return "Aging"
    return "Stale"




def build_player_pick_reason_text(row: pd.Series) -> str:
    """Deterministic player-level explanation for 'Why This Pick'."""
    def _num(v):
        n = pd.to_numeric(v, errors="coerce")
        return None if pd.isna(n) else float(n)

    name = str(row.get("player_name", "Player"))
    ev = _num(row.get("expected_value"))
    win = _num(row.get("win_prob"))
    top10 = _num(row.get("top10_prob"))
    top20 = _num(row.get("top20_prob"))
    cut = _num(row.get("cut_prob"))
    sg_total = _num(row.get("sg_total"))
    form_trend = _num(row.get("form_trend"))
    hist_starts = _num(row.get("hist_times_played"))
    hist_top10s = _num(row.get("hist_top10s"))
    hist_wins = _num(row.get("hist_wins"))
    hist_avg = _num(row.get("hist_avg_finish"))
    dg_fit = _num(row.get("dg_fit_total"))

    lines = [f"**{name}** is a strong pick this week because:"]
    if ev is not None:
        lines.append(f"- Expected value is **${ev:,.0f}**, which keeps him near the top of the model board.")
    if win is not None or top10 is not None or top20 is not None:
        w = f"{(win * 100):.2f}%" if win is not None else "n/a"
        t10 = f"{(top10 * 100):.1f}%" if top10 is not None else "n/a"
        t20 = f"{(top20 * 100):.1f}%" if top20 is not None else "n/a"
        lines.append(f"- Probabilities: **Win {w} | Top-10 {t10} | Top-20 {t20}**.")
    if cut is not None:
        lines.append(f"- Cut stability is **{(cut * 100):.1f}%** (miss-cut risk {(max(0.0, 1.0 - cut) * 100):.1f}%).")
    if sg_total is not None:
        lines.append(f"- Recent SG Total is **{sg_total:+.3f}** per round.")
    if form_trend is not None:
        trend = "improving" if form_trend > 0.15 else ("slipping" if form_trend < -0.15 else "stable")
        lines.append(f"- Form trend looks **{trend}** ({form_trend:+.3f}).")
    if hist_starts is not None and hist_starts > 0:
        bits = [f"{int(hist_starts)} starts"]
        if hist_top10s is not None and hist_top10s > 0:
            bits.append(f"{int(hist_top10s)} top-10" + ("" if int(hist_top10s) == 1 else "s"))
        if hist_wins is not None and hist_wins > 0:
            bits.append(f"{int(hist_wins)} win" + ("" if int(hist_wins) == 1 else "s"))
        if hist_avg is not None:
            bits.append(f"{hist_avg:.1f} avg finish")
        lines.append("- Course history: " + ", ".join(bits) + ".")
    elif dg_fit is not None:
        lines.append(f"- Course-fit signal is **{dg_fit:+.3f}**.")

    return "\n".join(lines)


def _lineup_reasoning_text(row: dict, profile_key: str, context_row: dict | None = None) -> str:
    """Build conversational reason text for why a player is in the lineup."""
    ctx = context_row or {}
    player_name = str(row.get("player_name") or ctx.get("player_name") or "This player")
    profile_label = {"safe": "Safe", "balanced": "Balanced", "upside": "Upside"}.get(profile_key, profile_key.title())

    reasons = []
    usage_rec = str(row.get("usage_recommendation", "")).strip()
    if usage_rec.lower() in {"none", "nan", "na", "n/a", "null"}:
        usage_rec = ""
    uses_left = pd.to_numeric(row.get("uses_remaining"), errors="coerce")
    if usage_rec and pd.notna(uses_left):
        reasons.append(f"the usage planner tags him as {usage_rec.lower()} with {int(uses_left)}/3 uses left")
    elif usage_rec:
        reasons.append(f"the usage planner tags him as {usage_rec.lower()}")

    top10_prob = pd.to_numeric(row.get("top10_prob"), errors="coerce")
    if pd.notna(top10_prob):
        reasons.append(f"the model gives him about {float(top10_prob) * 100:.1f}% Top-10 odds")

    lev_score = pd.to_numeric(row.get("leverage_score"), errors="coerce")
    lev_raw = pd.to_numeric(row.get("leverage_raw"), errors="coerce")
    if pd.notna(lev_score):
        if float(lev_score) >= 0.80:
            reasons.append("he carries strong leverage versus public build patterns")
        elif float(lev_score) >= 0.65:
            reasons.append("he gives above-average leverage")
    elif pd.notna(lev_raw) and float(lev_raw) > 0:
        reasons.append("our model is slightly higher than market on him")

    cut_prob = pd.to_numeric(row.get("cut_prob"), errors="coerce")
    if pd.notna(cut_prob):
        if float(cut_prob) >= 0.95:
            reasons.append("he projects as a very safe cut-maker")
        elif float(cut_prob) >= 0.88:
            reasons.append("he still projects as a solid cut-maker")

    course_fit = pd.to_numeric(row.get("course_fit_norm"), errors="coerce")
    if pd.notna(course_fit) and float(course_fit) >= 0.65:
        reasons.append("his stat profile matches this course well")

    if not reasons:
        reasons.append("his overall profile balances floor and ceiling")

    summary = f"{player_name} is in the {profile_label} lineup because " + ", ".join(reasons[:3]) + "."

    starts = pd.to_numeric(ctx.get("hist_times_played"), errors="coerce")
    top10s = pd.to_numeric(ctx.get("hist_top10s"), errors="coerce")
    wins = pd.to_numeric(ctx.get("hist_wins"), errors="coerce")
    avg_finish = pd.to_numeric(ctx.get("hist_avg_finish"), errors="coerce")

    history_bits = []
    if pd.notna(starts) and int(starts) > 0:
        history_bits.append(f"{int(starts)} starts")
    if pd.notna(top10s) and int(top10s) > 0:
        history_bits.append(f"{int(top10s)} top-10s")
    if pd.notna(wins) and int(wins) > 0:
        history_bits.append(f"{int(wins)} win" + ("" if int(wins) == 1 else "s"))
    if pd.notna(avg_finish):
        history_bits.append(f"{float(avg_finish):.1f} avg finish")

    if history_bits:
        summary += " Course history: " + ", ".join(history_bits[:4]) + "."

    return summary


def render_lineup_strategies_section(
    tournament_name: str = "",
    tournament_id: str = "",
    context_df: pd.DataFrame | None = None,
    output_mode: str = "Detailed",
):
    """Render Safe/Balanced/Upside lineups with player-level reasoning."""
    st.markdown("### 🧠 Fantasy Strategy Lineups")

    bundle, source_path = load_lineup_strategies_bundle(
        preferred_tournament_name=tournament_name,
        preferred_tournament_id=tournament_id,
    )
    if not bundle or not bundle.get("profiles"):
        st.info("No strategy lineup output found yet.")
        st.code(
            "python3 scripts/predictions/predict_tournament.py --tournament \"<name>\" --tournament-id RYYYYNNN "
            "--field data/fields/field_RYYYYNNN.csv --purse <amount> "
            "--course-adjust-strength 0.12 --course-adjust-max 0.08 "
            "--course-adjust-min-starts 2 --course-adjust-min-players 5 "
            "--lineup-strategies"
        )
        return

    if source_path and source_path.exists():
        updated = datetime.fromtimestamp(source_path.stat().st_mtime).strftime("%b %d %H:%M")

    profiles = bundle.get("profiles", {})
    context_lookup = {}
    if isinstance(context_df, pd.DataFrame) and not context_df.empty and "player_name" in context_df.columns:
        for _, prow in context_df.iterrows():
            context_lookup[_name_key(prow.get("player_name", ""))] = prow.to_dict()

    def _profile_details_map(profile_key: str) -> dict:
        info = profiles.get(profile_key, {})
        details = info.get("details", []) if isinstance(info.get("details", []), list) else []
        out = {}
        for d in details:
            pname = str(d.get("player_name", "")).strip()
            if pname:
                out[_name_key(pname)] = d
        return out

    def _to_num(v):
        n = pd.to_numeric(v, errors="coerce")
        return np.nan if pd.isna(n) else float(n)

    def _pick_primary_profile() -> str:
        for k in ["balanced", "safe", "upside"]:
            info = profiles.get(k, {})
            if isinstance(info, dict) and info.get("players"):
                return k
        for k, info in profiles.items():
            if isinstance(info, dict) and info.get("players"):
                return k
        return "balanced"

    def _player_context_row(name: str) -> dict:
        return context_lookup.get(_name_key(name), {})

    primary_key = _pick_primary_profile()
    primary_info = profiles.get(primary_key, {}) if isinstance(profiles, dict) else {}
    primary_players = [str(p).strip() for p in primary_info.get("players", []) if str(p).strip()]
    primary_details = _profile_details_map(primary_key)
    primary_score_col = f"{primary_key}_score"

    if not primary_players:
        st.info("No primary lineup players found in strategy output.")
        return

    st.markdown(f"#### ✅ Primary Lineup ({primary_info.get('profile', primary_key.title())})")

    rows = []
    for name in primary_players:
        row = dict(primary_details.get(_name_key(name), {}))
        if not row:
            row = {"player_name": name}
        ctx = _player_context_row(name)
        if "win_prob" not in row and "win_prob" in ctx:
            row["win_prob"] = ctx.get("win_prob")
        if "top10_prob" not in row and "top10_prob" in ctx:
            row["top10_prob"] = ctx.get("top10_prob")
        if "cut_prob" not in row and "cut_prob" in ctx:
            row["cut_prob"] = ctx.get("cut_prob")
        if "leverage_score" not in row and "leverage_score" in ctx:
            row["leverage_score"] = ctx.get("leverage_score")
        if "uses_remaining" not in row and "uses_remaining" in ctx:
            row["uses_remaining"] = ctx.get("uses_remaining")
        if "usage_recommendation" not in row and "usage_recommendation" in ctx:
            row["usage_recommendation"] = ctx.get("usage_recommendation")
        cut_prob = _to_num(row.get("cut_prob"))
        miss_cut_pct = (1.0 - cut_prob) * 100.0 if not np.isnan(cut_prob) else np.nan
        score = _to_num(row.get(primary_score_col))
        win_prob = _to_num(row.get("win_prob"))
        top10_prob = _to_num(row.get("top10_prob"))
        lev = _to_num(row.get("leverage_score"))
        uses_left = _to_num(row.get("uses_remaining"))
        reason_text = _lineup_reasoning_text(row, primary_key, context_row=ctx)
        if str(output_mode).lower() == "compact":
            compact = reason_text.split(". ")[0].strip()
            if compact and not compact.endswith("."):
                compact += "."
            reason_text = compact
        rows.append(
            {
                "Player": name,
                "Score": round(score, 3) if not np.isnan(score) else np.nan,
                "Win %": round(win_prob * 100, 2) if not np.isnan(win_prob) else np.nan,
                "Top10 %": round(top10_prob * 100, 2) if not np.isnan(top10_prob) else np.nan,
                "Miss Cut %": round(miss_cut_pct, 2) if not np.isnan(miss_cut_pct) else np.nan,
                "Uses": f"{int(uses_left)}/3" if not np.isnan(uses_left) else "—",
                "Leverage": round(lev, 3) if not np.isnan(lev) else np.nan,
                "Reasoning": reason_text,
            }
        )

    primary_df = pd.DataFrame(rows)
    st.dataframe(primary_df, hide_index=True, use_container_width=True)

    summary = primary_info.get("summary", {}) if isinstance(primary_info.get("summary"), dict) else {}
    if summary:
        avg_cut = pd.to_numeric(summary.get("avg_cut_prob", np.nan), errors="coerce")
        miss_cut_pp = (1.0 - float(avg_cut)) * 100 if pd.notna(avg_cut) else np.nan
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Avg Win %", f"{float(summary.get('avg_win_prob', 0.0))*100:.2f}%")
        with c2:
            st.metric("Avg Top10 %", f"{float(summary.get('avg_top10_prob', 0.0))*100:.2f}%")
        with c3:
            st.metric("Avg Miss Cut %", _format_percent_point(miss_cut_pp, decimals=2))
        with c4:
            st.metric("Avg Leverage", f"{float(summary.get('avg_leverage_score', summary.get('avg_leverage_raw', 0.0))):+.3f}")

    st.markdown("---")

    pool = bundle.get("pool", [])
    if isinstance(pool, list) and pool:
        pool_df = pd.DataFrame(pool)
    elif isinstance(pool, pd.DataFrame):
        pool_df = pool.copy()
    else:
        pool_df = pd.DataFrame()

    if not pool_df.empty:
        with st.expander("Candidate Pool Diagnostics", expanded=False):
            keep_cols = [
                "player_name", "uses_remaining", "usage_recommendation", "usage_score",
                "model_gap_raw", "leverage_score", "course_fit_norm",
                "safe_score", "balanced_score", "upside_score",
            ]
            keep_cols = [c for c in keep_cols if c in pool_df.columns]
            view = pool_df[keep_cols].copy()
            st.dataframe(view.head(30), hide_index=True, use_container_width=True)



def _name_key(name: str) -> str:
    """Normalize player name for loose matching across sources."""
    if pd.isna(name):
        return ""
    cleaned = unicodedata.normalize("NFKD", str(name))
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.replace(",", " ").replace(".", " ").replace("-", " ").lower().strip()
    tokens = [t for t in cleaned.split() if t]
    # Remove common suffixes.
    tokens = [t for t in tokens if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    tokens.sort()
    return " ".join(tokens)


def ensure_player_name_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a DataFrame has a usable `player_name` column.
    Handles common alternate column names and id-only rows.
    """
    out = df.copy()
    if "player_name" not in out.columns:
        alternatives = [
            "player",
            "Player",
            "name",
            "Name",
            "playerName",
            "displayName",
            "golfer",
            "PLAYER",
        ]
        source_col = next((c for c in alternatives if c in out.columns), None)
        if source_col:
            out["player_name"] = out[source_col]
        elif "player_id" in out.columns:
            out["player_name"] = out["player_id"].apply(
                lambda v: f"Player {int(v)}" if pd.notna(v) else ""
            )
        else:
            out["player_name"] = ""
    else:
        out["player_name"] = out["player_name"].fillna("")

    if "player_id" in out.columns:
        missing_mask = out["player_name"].astype(str).str.strip().eq("")
        if missing_mask.any():
            out.loc[missing_mask, "player_name"] = out.loc[missing_mask, "player_id"].apply(
                lambda v: f"Player {int(v)}" if pd.notna(v) else ""
            )

    out["player_name"] = out["player_name"].astype(str).str.strip()
    return out


# ============================================================================
# ODDS COMPARISON HELPERS
# ============================================================================

def load_odds_from_source(source: str) -> pd.DataFrame:
    """Load odds data from a specific source."""
    odds_dir = DATA_DIR / "odds"
    files = [odds_dir / "multi_book_odds_latest.csv"]

    if files:
        # Get most recent file
        latest = max(files, key=lambda f: f.stat().st_mtime)
        return pd.read_csv(latest)
    return pd.DataFrame()




def prob_to_badge_class(prob: float) -> str:
    """Get CSS class for probability badge."""
    if prob >= 0.10:
        return "prob-high"
    elif prob >= 0.03:
        return "prob-mid"
    return "prob-low"


def format_odds_display(odds: float, is_best: bool = False) -> str:
    """Format odds for display with optional highlighting."""
    if pd.isna(odds) or odds == 0:
        return "—"
    sign = "+" if odds > 0 else ""
    if is_best:
        return f"**{sign}{int(odds)}** ✓"
    return f"{sign}{int(odds)}"












def save_odds_snapshot():                                                                                                
    """Save current odds as a timestamped snapshot."""                                                                   
    snapshot_dir = DATA_DIR / "odds" / "snapshots"                                                                       
    snapshot_dir.mkdir(parents=True, exist_ok=True)                                                                      
                                                                                                                        
                                                                                                    
                                                                                                                        
    # Save with timestamp                                                                                                
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")                                                                   
    snapshot_path = snapshot_dir / f"odds_{timestamp}.csv"                                                               
                                                                                                                        
    return snapshot_path  








def _parse_american_odds(v):
    """Parse American odds string/number to numeric."""
    if pd.isna(v):
        return np.nan
    s = str(v).strip().replace("+", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return np.nan


TID_PATTERN = re.compile(r"(R\d{7})", re.IGNORECASE)


def _extract_tournament_id(value) -> str:
    """Extract normalized tournament id (e.g., R2026007) from text-like input."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    m = TID_PATTERN.search(str(value))
    return m.group(1).upper() if m else ""


def _tournament_id_from_df(df: pd.DataFrame) -> str:
    """Read tournament_id from dataframe if present."""
    if df is None or df.empty or "tournament_id" not in df.columns:
        return ""
    vals = df["tournament_id"].dropna().astype(str).str.strip()
    if vals.empty:
        return ""
    return _extract_tournament_id(vals.iloc[0])


def _is_recent_file(path: Path | None, max_age_hours: float = 30.0) -> bool:
    """Check if file is recent enough to be considered active context."""
    if path is None or not Path(path).exists():
        return False
    age_hours = (datetime.now().timestamp() - Path(path).stat().st_mtime) / 3600.0
    return age_hours <= max_age_hours


def _latest_tournament_id_from_prop_lines(max_age_hours: float = 30.0) -> str:
    """Get tournament id from the newest recent prop lines file."""
    files = sorted(
        (DATA_DIR / "odds").glob("prop_lines_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files:
        if _is_recent_file(f, max_age_hours=max_age_hours):
            tid = _extract_tournament_id(f.stem)
            if tid:
                return tid
    return ""


@st.cache_data(ttl=180)
def load_dk_content_cards_df(preferred_tournament_id: str = "") -> tuple[pd.DataFrame, Path | None]:
    """Load DraftKings preset content cards for a tournament (or latest fallback)."""
    odds_dir = DATA_DIR / "odds"
    if not odds_dir.exists():
        return pd.DataFrame(), None

    tid = str(preferred_tournament_id or "").strip().upper()
    candidates: list[Path] = []
    if tid:
        candidates.append(odds_dir / f"dk_content_cards_{tid}.csv")

    rid_files = sorted(odds_dir.glob("dk_content_cards_R*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    candidates.extend(rid_files[:5])

    latest_file = odds_dir / "dk_content_cards_latest.csv"
    if latest_file.exists():
        candidates.append(latest_file)

    seen = set()
    ordered = []
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            ordered.append(c)

    for p in ordered:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty:
            continue
        if "tournament_id" not in df.columns:
            df["tournament_id"] = ""
        if "title" not in df.columns:
            df["title"] = ""
        if "subtitle" not in df.columns:
            df["subtitle"] = ""
        if "selection_labels" not in df.columns and "selection_labels_json" in df.columns:
            def _labels_from_json(v):
                try:
                    arr = json.loads(v) if pd.notna(v) else []
                    if isinstance(arr, list):
                        return " | ".join([str(x).strip() for x in arr if str(x).strip()])
                except Exception:
                    return ""
                return ""
            df["selection_labels"] = df["selection_labels_json"].apply(_labels_from_json)
        if "odds_american" not in df.columns:
            df["odds_american"] = np.nan
        if "selection_count" not in df.columns:
            df["selection_count"] = np.nan
        if "bet_count" not in df.columns:
            df["bet_count"] = np.nan
        if "sort_order" in df.columns:
            df["sort_order"] = pd.to_numeric(df["sort_order"], errors="coerce")
            df = df.sort_values(["sort_order", "title"], na_position="last")
        return df.reset_index(drop=True), p

    return pd.DataFrame(), None


@st.cache_data(ttl=120)
def load_recommended_bets_df(preferred_tournament_id: str = "") -> tuple[pd.DataFrame, Path | None]:
    """Load v1 tracked recommendations for a tournament, with latest fallback."""
    odds_dir = DATA_DIR / "odds"
    if not odds_dir.exists():
        return pd.DataFrame(), None

    tid = str(preferred_tournament_id or "").strip().upper()
    candidates: list[Path] = []
    if tid:
        candidates.append(odds_dir / f"recommended_bets_{tid}.csv")

    rid_files = sorted(odds_dir.glob("recommended_bets_R*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    candidates.extend(rid_files[:5])

    latest_file = odds_dir / "recommended_bets_latest.csv"
    if latest_file.exists():
        candidates.append(latest_file)

    seen = set()
    ordered = []
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            ordered.append(c)

    for p in ordered:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty:
            continue
        if "recommendation_rank" in df.columns:
            df["recommendation_rank"] = pd.to_numeric(df["recommendation_rank"], errors="coerce")
            df = df.sort_values("recommendation_rank", na_position="last")
        return df.reset_index(drop=True), p

    return pd.DataFrame(), None


@st.cache_data(ttl=120)
def load_recommended_bet_results_df(preferred_tournament_id: str = "") -> pd.DataFrame:
    """Load settled recommendation results log, optionally filtered by tournament id."""
    path = DATA_DIR / "odds" / "recommended_bets_results.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df

    tid = str(preferred_tournament_id or "").strip().upper()
    if tid and "tournament_id" in df.columns:
        df = df[df["tournament_id"].astype(str).str.upper() == tid]
    return df.reset_index(drop=True)


def _format_american_odds(odds) -> str:
    if pd.isna(odds):
        return "-"
    try:
        val = int(float(odds))
    except Exception:
        return str(odds)
    return f"+{val}" if val > 0 else str(val)


def _american_to_prob(odds) -> float:
    v = pd.to_numeric(odds, errors="coerce")
    if pd.isna(v):
        return np.nan
    if v > 0:
        return 100.0 / (v + 100.0)
    return abs(v) / (abs(v) + 100.0)


def _american_to_decimal(odds) -> float:
    v = pd.to_numeric(odds, errors="coerce")
    if pd.isna(v):
        return np.nan
    if v > 0:
        return 1.0 + (v / 100.0)
    return 1.0 + (100.0 / abs(v))


def _extract_card_leg_labels(row: pd.Series) -> list[str]:
    labels = _safe_parse_name_list(row.get("selection_labels_json", ""))
    if labels:
        return labels
    raw = str(row.get("selection_labels", "")).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def _parse_card_leg_label(label: str) -> dict:
    s = str(label or "").strip()
    low = s.lower()

    m = re.match(r"^(.*?)\s+to\s+finish\s+top\s+(\d+)\b", s, flags=re.I)
    if m:
        return {"market": f"top{m.group(2)}", "player": m.group(1).strip(), "raw": s}

    m = re.match(r"^(.*?)\s+to\s+win\s+r([1-4])\s*\(vs\.?\s*(.*?)\)$", s, flags=re.I)
    if m:
        return {
            "market": "h2h_round",
            "player": m.group(1).strip(),
            "opponent": m.group(3).strip(),
            "round_num": int(m.group(2)),
            "raw": s,
        }

    if re.search(r"\bto\s+make\s+(?:the\s+)?cut\b", low):
        player = re.sub(r"\s+to\s+make\s+(?:the\s+)?cut.*$", "", s, flags=re.I).strip()
        return {"market": "make_cut", "player": player, "raw": s}

    if re.search(r"\bto\s+miss\s+(?:the\s+)?cut\b", low):
        player = re.sub(r"\s+to\s+miss\s+(?:the\s+)?cut.*$", "", s, flags=re.I).strip()
        return {"market": "miss_cut", "player": player, "raw": s}

    if re.search(r"\bto\s+win\b", low):
        player = re.sub(r"\s+to\s+win.*$", "", s, flags=re.I).strip()
        return {"market": "outright", "player": player, "raw": s}

    return {"market": "unknown", "player": "", "raw": s}


def _score_dk_content_cards(cards_df: pd.DataFrame, preds_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if cards_df.empty or preds_df.empty or "player_name" not in preds_df.columns:
        return pd.DataFrame(), pd.DataFrame()

    work = preds_df.copy()
    work["player_name"] = work["player_name"].fillna("").astype(str).str.strip()
    work = work[work["player_name"] != ""].copy()
    if work.empty:
        return pd.DataFrame(), pd.DataFrame()

    work["name_key"] = work["player_name"].apply(_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in work.iterrows() if r["name_key"]}

    last_name_map: dict[str, list[dict]] = {}
    for _, r in work.iterrows():
        pname = str(r["player_name"]).strip()
        toks = re.sub(r"[^a-z0-9, ]+", " ", pname.lower()).replace(",", " ").split()
        if toks:
            last_name_map.setdefault(toks[-1], []).append(r.to_dict())

    def resolve_player(name_text: str) -> dict | None:
        k = _name_key(name_text)
        if k in by_key:
            return by_key[k]
        toks = [t for t in re.sub(r"[^a-z0-9 ]+", " ", str(name_text).lower()).split() if t]
        if len(toks) == 1:
            cands = last_name_map.get(toks[0], [])
            if len(cands) == 1:
                return cands[0]
        return None

    def cut_prob_for_row(row: dict) -> float:
        for c in ["make_cut_prob", "cut_prob"]:
            v = pd.to_numeric(row.get(c), errors="coerce")
            if pd.notna(v):
                return float(np.clip(v, 0.0, 1.0))
        t20 = pd.to_numeric(row.get("top20_prob"), errors="coerce")
        if pd.notna(t20):
            return float(np.clip(min(0.95, float(t20) * 1.5 + 0.2), 0.0, 1.0))
        return np.nan

    def prob_for_market(player_row: dict, market: str) -> float:
        market = str(market or "").lower()
        col_map = {
            "outright": "win_prob",
            "top5": "top5_prob",
            "top10": "top10_prob",
            "top20": "top20_prob",
            "top30": "top30_prob",
        }
        if market in col_map:
            v = pd.to_numeric(player_row.get(col_map[market]), errors="coerce")
            if pd.notna(v):
                return float(np.clip(v, 0.0, 1.0))
            if market == "top30":
                t20 = pd.to_numeric(player_row.get("top20_prob"), errors="coerce")
                if pd.notna(t20):
                    return float(np.clip(min(0.985, float(t20) * 1.30 + 0.05), 0.0, 1.0))
            return np.nan
        if market == "make_cut":
            return cut_prob_for_row(player_row)
        if market == "miss_cut":
            cp = cut_prob_for_row(player_row)
            return float(np.clip(1.0 - cp, 0.0, 1.0)) if pd.notna(cp) else np.nan
        return np.nan

    card_rows = []
    leg_rows = []

    for _, card in cards_df.iterrows():
        legs = _extract_card_leg_labels(card)
        if not legs:
            continue

        leg_probs = []
        priced_legs = 0
        unpriced_legs = 0
        players_in_card = []
        markets_in_card = []

        for leg in legs:
            parsed = _parse_card_leg_label(leg)
            market = parsed.get("market", "unknown")
            player_txt = parsed.get("player", "")
            p_row = resolve_player(player_txt) if player_txt else None
            p_prob = np.nan
            note = ""

            if market == "h2h_round":
                # keep v1 simple: skip H2H card legs unless explicitly modeled in card engine
                note = "Unsupported market in card scorer"
            elif p_row is None:
                note = "Player not mapped"
            else:
                p_prob = prob_for_market(p_row, market)
                if pd.isna(p_prob):
                    note = "No model probability for market"
                else:
                    priced_legs += 1
                    leg_probs.append(float(p_prob))
                    players_in_card.append(str(p_row.get("player_name", player_txt)))
                    markets_in_card.append(market)

            if pd.isna(p_prob):
                unpriced_legs += 1

            leg_rows.append(
                {
                    "card_id": card.get("card_id", ""),
                    "title": card.get("title", ""),
                    "leg_label": leg,
                    "market": market,
                    "player_name": p_row.get("player_name") if isinstance(p_row, dict) else player_txt,
                    "model_prob": p_prob,
                    "priced": pd.notna(p_prob),
                    "note": note,
                }
            )

        total_legs = len(legs)
        book_odds = pd.to_numeric(card.get("odds_american"), errors="coerce")
        book_prob = _american_to_prob(book_odds)
        book_dec = pd.to_numeric(card.get("odds_decimal"), errors="coerce")
        if pd.isna(book_dec):
            book_dec = _american_to_decimal(book_odds)

        if priced_legs <= 0:
            model_prob = np.nan
            edge_pts = np.nan
            ev_per_1 = np.nan
            status = "unpriced"
        else:
            base_prob = float(np.prod(leg_probs))
            dup_players = max(0, len(players_in_card) - len(set(players_in_card)))
            dup_markets = max(0, len(markets_in_card) - len(set(markets_in_card)))
            corr_penalty = (0.92 ** dup_players) * (0.97 ** dup_markets) * (0.98 ** max(0, total_legs - 1))
            model_prob = float(np.clip(base_prob * corr_penalty, 0.0, 0.999))
            edge_pts = (model_prob - book_prob) * 100 if pd.notna(book_prob) else np.nan
            ev_per_1 = (model_prob * book_dec - 1.0) if pd.notna(book_dec) else np.nan
            status = "priced" if unpriced_legs == 0 else "partial"

        confidence = float(np.clip(priced_legs / max(1, total_legs), 0.0, 1.0))

        card_rows.append(
            {
                "tournament_id": card.get("tournament_id", ""),
                "card_id": card.get("card_id", ""),
                "title": card.get("title", ""),
                "subtitle": card.get("subtitle", ""),
                "selection_count": total_legs,
                "priced_legs": priced_legs,
                "unpriced_legs": unpriced_legs,
                "odds_american": book_odds,
                "book_prob": book_prob,
                "model_prob": model_prob,
                "edge_pts": edge_pts,
                "ev_per_1": ev_per_1,
                "confidence": confidence,
                "status": status,
                "selection_labels": card.get("selection_labels", ""),
            }
        )

    cards_scored = pd.DataFrame(card_rows)
    legs_scored = pd.DataFrame(leg_rows)
    if cards_scored.empty:
        return cards_scored, legs_scored

    cards_scored["edge_pts"] = pd.to_numeric(cards_scored["edge_pts"], errors="coerce")
    cards_scored["ev_per_1"] = pd.to_numeric(cards_scored["ev_per_1"], errors="coerce")
    cards_scored["confidence"] = pd.to_numeric(cards_scored["confidence"], errors="coerce")
    cards_scored = cards_scored.sort_values(
        ["status", "edge_pts", "ev_per_1"],
        ascending=[True, False, False],
        na_position="last",
    ).reset_index(drop=True)
    return cards_scored, legs_scored


def append_dk_card_recommendation_log(card_scores_df: pd.DataFrame, tournament_id: str = "") -> Path | None:
    if card_scores_df is None or card_scores_df.empty:
        return None

    out_dir = DATA_DIR / "odds"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dk_card_recommendations_log.csv"

    log_df = card_scores_df.copy()
    log_df["logged_at"] = datetime.now().isoformat()
    log_df["tournament_id"] = str(tournament_id or "").strip().upper() or log_df.get("tournament_id", "")
    cols = [
        "logged_at",
        "tournament_id",
        "card_id",
        "title",
        "selection_count",
        "priced_legs",
        "unpriced_legs",
        "odds_american",
        "book_prob",
        "model_prob",
        "edge_pts",
        "ev_per_1",
        "confidence",
        "status",
    ]
    cols = [c for c in cols if c in log_df.columns]
    log_df = log_df[cols].copy()

    if out_path.exists():
        try:
            prev = pd.read_csv(out_path)
            log_df = pd.concat([prev, log_df], ignore_index=True)
        except Exception:
            pass

    log_df.to_csv(out_path, index=False)
    return out_path


def _latest_tournament_id_from_live(max_age_hours: float = 18.0) -> str:
    """Get tournament id from newest recent live leaderboard file."""
    files = sorted(
        (DATA_DIR / "live").glob("leaderboard_r*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files:
        if _is_recent_file(f, max_age_hours=max_age_hours):
            tid = _extract_tournament_id(f.stem)
            if tid:
                return tid
    return ""


def load_latest_fanduel_odds_df() -> tuple:
    """
    Load latest FanDuel winner odds dataset.

    Priority:
    1. data/odds/fanduel_odds_*.csv
    2. data/odds/pga_odds_*.csv (fallback)
    """
    fd_files = sorted(
        (DATA_DIR / "odds").glob("fanduel_odds_*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    source = "fanduel_odds"
    odds_file = fd_files[0] if fd_files else None

    if odds_file is None:
        pga_files = sorted(
            (DATA_DIR / "odds").glob("pga_odds_*.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        source = "pga_odds"
        odds_file = pga_files[0] if pga_files else None

    if odds_file is None:
        return pd.DataFrame(), None, ""

    df = pd.read_csv(odds_file)
    if df.empty:
        return pd.DataFrame(), odds_file, source

    if "player_name" not in df.columns and "name" in df.columns:
        df["player_name"] = df["name"]

    if "odds_to_win" not in df.columns and "fanduel_odds" in df.columns:
        df["odds_to_win"] = df["fanduel_odds"]

    if "implied_prob" not in df.columns and "fanduel_implied_prob" in df.columns:
        df["implied_prob"] = df["fanduel_implied_prob"]

    if "odds_direction" not in df.columns:
        if "odds_movement_direction" in df.columns:
            df["odds_direction"] = df["odds_movement_direction"]
        elif "odds_swing" in df.columns:
            df["odds_direction"] = df["odds_swing"]
        else:
            df["odds_direction"] = ""

    if "odds_swing" not in df.columns and "odds_movement_swing" in df.columns:
        df["odds_swing"] = df["odds_movement_swing"]

    if "odds_numeric" not in df.columns:
        src_col = "odds_to_win" if "odds_to_win" in df.columns else None
        df["odds_numeric"] = df[src_col].apply(_parse_american_odds) if src_col else np.nan
    else:
        df["odds_numeric"] = pd.to_numeric(df["odds_numeric"], errors="coerce")

    if "implied_prob" not in df.columns:
        df["implied_prob"] = np.where(
            df["odds_numeric"] > 0,
            100.0 / (df["odds_numeric"] + 100.0),
            np.nan,
        )
    else:
        df["implied_prob"] = pd.to_numeric(df["implied_prob"], errors="coerce")

    return df, odds_file, source


def _safe_parse_name_list(value) -> list[str]:
    """Parse lineup name list stored as JSON-like string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]

    s = str(value).strip()
    if not s:
        return []

    parsed = None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(s)
            break
        except Exception:
            continue

    if isinstance(parsed, list):
        return [str(v).strip() for v in parsed if str(v).strip()]
    return []


def _name_tokens_for_match(value: str) -> set:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    if not cleaned:
        return set()
    stop = {
        "the", "and", "of", "at", "in", "to", "open", "championship",
        "classic", "invitational", "pro", "am", "presented", "by",
    }
    return {t for t in cleaned.split() if t and t not in stop}


def _tournament_names_match(actual: str, expected: str) -> bool:
    a = _name_tokens_for_match(actual)
    e = _name_tokens_for_match(expected)
    if not a or not e:
        return False
    overlap = len(a.intersection(e))
    return overlap >= max(1, min(2, len(e)))


def _expected_tournament_name_from_id(tournament_id: str) -> str:
    tid = str(tournament_id or "").strip().upper()
    if not tid:
        return ""
    schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
    if not schedule_path.exists():
        return ""
    try:
        sdf = pd.read_csv(schedule_path, dtype=str).fillna("")
    except Exception:
        return ""
    if "tournament_id" not in sdf.columns or "tournament_name" not in sdf.columns:
        return ""
    row = sdf[sdf["tournament_id"].astype(str).str.upper().str.strip() == tid]
    if row.empty:
        return ""
    return str(row.iloc[0].get("tournament_name", "")).strip()


@st.cache_data(ttl=300)
def load_expert_picks_df(preferred_tournament_id: str = "") -> tuple[pd.DataFrame, Path | None, str]:
    """
    Load expert picks with robust fallback order:
    1) expert_picks_<tournament_id>.csv
    2) latest expert_picks_R*.csv
    3) expert_picks_latest.csv
    4) expert_picks_ep_table.csv
    """
    ep_dir = DATA_DIR / "expert_picks"
    if not ep_dir.exists():
        return pd.DataFrame(), None, ""

    candidates: list[Path] = []
    tid = str(preferred_tournament_id or "").strip().upper()
    expected_tournament_name = _expected_tournament_name_from_id(tid) if tid else ""
    if tid:
        candidates.append(ep_dir / f"expert_picks_{tid}.csv")

    rid_files = sorted(ep_dir.glob("expert_picks_R*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    candidates.extend(rid_files[:5])

    latest_file = ep_dir / "expert_picks_latest.csv"
    if latest_file.exists():
        candidates.append(latest_file)

    ep_table_file = ep_dir / "expert_picks_ep_table.csv"
    if ep_table_file.exists():
        candidates.append(ep_table_file)

    seen = set()
    ordered = []
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            ordered.append(c)

    fallback_mismatch_df = None
    fallback_mismatch_path = None

    for p in ordered:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue

        if df.empty:
            continue

        # Column normalization.
        if "expert_name" not in df.columns and "expert" in df.columns:
            df["expert_name"] = df["expert"]
        if "winner_name" not in df.columns and "winner" in df.columns:
            df["winner_name"] = df["winner"]
        if "tournament_name" not in df.columns and "tournament" in df.columns:
            df["tournament_name"] = df["tournament"]
        if "lineup_player_names" not in df.columns:
            df["lineup_player_names"] = ""
        if "bench_player_names" not in df.columns:
            df["bench_player_names"] = ""
        if "comment" not in df.columns:
            df["comment"] = ""
        if "expert_title" not in df.columns:
            df["expert_title"] = ""
        if "source_url" not in df.columns:
            df["source_url"] = ""
        if "scraped_at" not in df.columns:
            df["scraped_at"] = ""

        df["expert_name"] = df["expert_name"].fillna("").astype(str).str.strip()
        df = df[df["expert_name"] != ""].copy()
        if df.empty:
            continue

        # If a target tournament_id was provided, skip files whose tournament_name
        # clearly maps to a different event (prevents stale previous-week picks).
        if tid and expected_tournament_name and "tournament_name" in df.columns:
            names = df["tournament_name"].dropna().astype(str).str.strip()
            found_name = names.iloc[0] if not names.empty else ""
            if found_name and not _tournament_names_match(found_name, expected_tournament_name):
                if fallback_mismatch_df is None:
                    fallback_mismatch_df = df.reset_index(drop=True)
                    fallback_mismatch_path = p
                continue

        source = "tournament_file" if p.name.startswith("expert_picks_R") else p.stem
        return df.reset_index(drop=True), p, source

    if fallback_mismatch_df is not None:
        # If a target tournament was requested, don't silently show stale prior-week picks.
        if tid:
            return pd.DataFrame(), fallback_mismatch_path, "no_match_for_tid"
        return fallback_mismatch_df, fallback_mismatch_path, "fallback_mismatch"

    return pd.DataFrame(), None, ""


def render_expert_picks_section(preds_df: pd.DataFrame, tournament_id: str = ""):
    """Render expert picks consensus + detail cards in Betting page."""
    st.markdown("### 📰 Expert Picks")

    expert_df, source_file, source_kind = load_expert_picks_df(tournament_id)
    if expert_df.empty:
        if source_kind == "no_match_for_tid":
            st.info(
                f"No expert picks published yet for **{tournament_id}**. "
                "Latest file is from a different tournament, so it is hidden to avoid mismatch."
            )
            return
        st.info("No expert picks file found. Run: `python3 scripts/scrapers/fetch_expert_picks_pga.py --tournament-id <RYYYYNNN>`")
        return

    file_name = source_file.name if source_file else "unknown"
    updated_str = (
        datetime.fromtimestamp(source_file.stat().st_mtime).strftime("%b %d %H:%M")
        if source_file and source_file.exists()
        else "unknown"
    )
    if source_kind == "fallback_mismatch":
        st.warning("Showing latest available expert picks file (tournament-name mismatch).")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Experts", int(expert_df["expert_name"].nunique()))
    with c2:
        uniq_winners = int(expert_df["winner_name"].fillna("").astype(str).str.strip().replace("", np.nan).dropna().nunique())
        st.metric("Unique Winners", uniq_winners)
    with c3:
        tname = ""
        if "tournament_name" in expert_df.columns and expert_df["tournament_name"].notna().any():
            tname = str(expert_df["tournament_name"].dropna().iloc[0]).strip()
        st.metric("Tournament", tname or "—")
    with c4:
        st.metric("Updated", updated_str)
    st.caption(f"Source: `{file_name}`")

    if "expert_name" not in expert_df.columns:
        st.info("Expert file loaded but missing expected columns.")
        return

    # Build model lookup once.
    model_lookup = pd.DataFrame()
    if preds_df is not None and not preds_df.empty and "player_name" in preds_df.columns:
        model_lookup = preds_df.copy()
        model_lookup["name_key"] = model_lookup["player_name"].apply(_name_key)
        rank_col = "expected_value" if "expected_value" in model_lookup.columns else "win_prob"
        model_lookup = model_lookup.sort_values(rank_col, ascending=False).reset_index(drop=True)
        model_lookup["Model Rank"] = np.arange(1, len(model_lookup) + 1)
        if "win_prob" in model_lookup.columns:
            model_lookup["Model Win %"] = (pd.to_numeric(model_lookup["win_prob"], errors="coerce") * 100).round(2)
        if "odds_to_win" not in model_lookup.columns:
            model_lookup["odds_to_win"] = np.nan
        model_lookup = model_lookup[["name_key", "Model Rank", "Model Win %", "odds_to_win"]].drop_duplicates("name_key")

    winners = expert_df["winner_name"].fillna("").astype(str).str.strip()
    winners = winners[winners != ""]
    winner_counts = pd.DataFrame(columns=["Player", "Winner Picks", "Winner Share %"])
    if not winners.empty:
        winner_counts = winners.value_counts().rename_axis("Player").reset_index(name="Winner Picks")
        winner_counts["Winner Share %"] = (winner_counts["Winner Picks"] / max(1, len(expert_df)) * 100).round(1)

    # Lineup consensus across expert lineups.
    lineup_counts = {}
    for _, row in expert_df.iterrows():
        for nm in _safe_parse_name_list(row.get("lineup_player_names", "")):
            lineup_counts[nm] = lineup_counts.get(nm, 0) + 1

    lineup_df = pd.DataFrame(columns=["Player", "Lineup Mentions", "Lineup Share %"])
    if lineup_counts:
        lineup_df = (
            pd.DataFrame({"Player": list(lineup_counts.keys()), "Lineup Mentions": list(lineup_counts.values())})
            .sort_values("Lineup Mentions", ascending=False)
            .reset_index(drop=True)
        )
        lineup_df["Lineup Share %"] = (lineup_df["Lineup Mentions"] / max(1, len(expert_df)) * 100).round(1)

    # Consensus board = winner + lineup in one table.
    consensus_df = pd.merge(
        lineup_df,
        winner_counts,
        on="Player",
        how="outer",
    )
    if consensus_df.empty and not winner_counts.empty:
        consensus_df = winner_counts.copy()
    if consensus_df.empty and not lineup_df.empty:
        consensus_df = lineup_df.copy()
    if consensus_df.empty:
        consensus_df = pd.DataFrame(columns=["Player", "Lineup Mentions", "Winner Picks"])

    if "Lineup Mentions" not in consensus_df.columns:
        consensus_df["Lineup Mentions"] = 0
    if "Winner Picks" not in consensus_df.columns:
        consensus_df["Winner Picks"] = 0
    if "Lineup Share %" not in consensus_df.columns:
        consensus_df["Lineup Share %"] = 0.0
    if "Winner Share %" not in consensus_df.columns:
        consensus_df["Winner Share %"] = 0.0

    consensus_df["Lineup Mentions"] = pd.to_numeric(consensus_df["Lineup Mentions"], errors="coerce").fillna(0).astype(int)
    consensus_df["Winner Picks"] = pd.to_numeric(consensus_df["Winner Picks"], errors="coerce").fillna(0).astype(int)
    consensus_df["Total Mentions"] = consensus_df["Lineup Mentions"] + consensus_df["Winner Picks"]
    consensus_df["name_key"] = consensus_df["Player"].apply(_name_key)

    if not model_lookup.empty:
        consensus_df = consensus_df.merge(model_lookup, on="name_key", how="left")

    consensus_df = consensus_df.sort_values(
        ["Winner Picks", "Lineup Mentions", "Total Mentions"],
        ascending=False,
    ).reset_index(drop=True)

    # Per-expert presentation data.
    expert_board = []
    for _, row in expert_df.iterrows():
        lineup_names = _safe_parse_name_list(row.get("lineup_player_names", ""))
        bench_names = _safe_parse_name_list(row.get("bench_player_names", ""))
        expert_board.append({
            "Expert": str(row.get("expert_name", "")).strip(),
            "Title": str(row.get("expert_title", "")).strip(),
            "Winner Pick": str(row.get("winner_name", "")).strip(),
            "Lineup": ", ".join(lineup_names),
            "Bench": ", ".join(bench_names),
            "Note": str(row.get("comment", "")).strip(),
            "Source URL": str(row.get("source_url", "")).strip(),
        })
    expert_board_df = pd.DataFrame(expert_board)

    tab1, tab2, tab3 = st.tabs(["🏆 Consensus Board", "👥 By Expert", "📝 Notes"])

    with tab1:
        if consensus_df.empty:
            st.info("No winner or lineup picks found in expert data.")
        else:
            show_cols = [
                c for c in [
                    "Player",
                    "Winner Picks",
                    "Lineup Mentions",
                    "Total Mentions",
                    "Winner Share %",
                    "Lineup Share %",
                    "Model Rank",
                    "Model Win %",
                    "odds_to_win",
                ]
                if c in consensus_df.columns
            ]
            board = consensus_df[show_cols].copy()
            if "odds_to_win" in board.columns:
                board = board.rename(columns={"odds_to_win": "Odds"})
            st.dataframe(
                board.head(25),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Winner Picks": st.column_config.NumberColumn(width="small"),
                    "Lineup Mentions": st.column_config.NumberColumn(width="small"),
                    "Total Mentions": st.column_config.NumberColumn(width="small"),
                    "Winner Share %": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                    "Lineup Share %": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                    "Model Win %": st.column_config.NumberColumn(format="%.2f%%", width="small"),
                },
            )

    with tab2:
        if expert_board_df.empty:
            st.info("No expert rows available.")
        else:
            expert_list = expert_board_df["Expert"].dropna().astype(str).str.strip().tolist()
            default_expert = expert_list[0] if expert_list else ""
            selected_expert = st.selectbox(
                "Expert",
                options=expert_list,
                index=0 if default_expert else None,
                key="expert_picks_expert_select",
            )
            row = expert_board_df[expert_board_df["Expert"] == selected_expert].head(1)
            if not row.empty:
                r = row.iloc[0]
                h1, h2 = st.columns([3, 1])
                with h1:
                    st.markdown(f"**{r.get('Expert', '')}**")
                    if str(r.get("Title", "")).strip():
                        st.caption(str(r.get("Title", "")).strip())
                with h2:
                    st.markdown(f"**Winner:** {str(r.get('Winner Pick', '—')).strip() or '—'}")

                if str(r.get("Lineup", "")).strip():
                    st.markdown(f"**Lineup:** {str(r.get('Lineup', '')).strip()}")
                if str(r.get("Bench", "")).strip():
                    st.markdown(f"**Bench:** {str(r.get('Bench', '')).strip()}")
                note = str(r.get("Note", "")).strip()
                if note:
                    st.markdown(f"**Note:** {note}")
                src = str(r.get("Source URL", "")).strip()
                if src:
                    st.markdown(f"[Open Source Article]({src})")

    with tab3:
        detail_df = expert_df[["expert_name", "expert_title", "winner_name", "comment"]].copy()
        detail_df = detail_df.rename(
            columns={
                "expert_name": "Expert",
                "expert_title": "Title",
                "winner_name": "Winner Pick",
                "comment": "Note",
            }
        )
        st.dataframe(detail_df, hide_index=True, use_container_width=True, height=420)


def render_tracked_bets_section(tournament_id: str = ""):
    """Render deterministic tracked-bets recommendations and settlement stats."""
    st.markdown("### ✅ Tracked Bet Recommendations")
    ("Rule-based +EV recommendations with audit log and settlement tracking")

    action_cols = st.columns([1.2, 1.2, 2.6])
    with action_cols[0]:
        if st.button("🔄 Refresh Recommendations", key="tracked_refresh_recs", use_container_width=True):
            cmd = [
                "python3",
                str(PROJECT_ROOT / "scripts" / "models" / "recommend_bets.py"),
            ]
            tid = str(tournament_id or "").strip().upper()
            if tid:
                cmd.extend(["--tournament-id", tid])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    cwd=PROJECT_ROOT,
                )
                if result.returncode == 0:
                    st.success("Recommendations refreshed")
                else:
                    st.warning("Recommendation refresh failed")
                msg = result.stdout.strip() if result.stdout.strip() else result.stderr.strip()
                if msg:
                    st.caption(msg[:900])
                load_recommended_bets_df.clear()
            except Exception as e:
                st.warning(f"Could not refresh recommendations: {e}")

    with action_cols[1]:
        if st.button("🧾 Grade Settled Bets", key="tracked_grade_recs", use_container_width=True):
            cmd = [
                "python3",
                str(PROJECT_ROOT / "scripts" / "models" / "grade_recommended_bets.py"),
            ]
            tid = str(tournament_id or "").strip().upper()
            if tid:
                cmd.extend(["--tournament-id", tid])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    cwd=PROJECT_ROOT,
                )
                if result.returncode == 0:
                    st.success("Grading run complete")
                else:
                    st.warning("Grading failed")
                msg = result.stdout.strip() if result.stdout.strip() else result.stderr.strip()
                if msg:
                    st.caption(msg[:900])
                load_recommended_bet_results_df.clear()
                load_recommended_bets_df.clear()
            except Exception as e:
                st.warning(f"Could not run grading: {e}")

    rec_df, rec_path = load_recommended_bets_df(tournament_id)
    if rec_df.empty:
        st.info("No tracked recommendations found yet. Run `python3 scripts/models/recommend_bets.py --tournament-id RYYYYNNN`.")
        return

    if rec_path and rec_path.exists():
        updated = datetime.fromtimestamp(rec_path.stat().st_mtime).strftime("%b %d %H:%M")

    metrics_cols = st.columns(4)
    with metrics_cols[0]:
        st.metric("Recommendations", int(len(rec_df)))
    with metrics_cols[1]:
        st.metric("Singles", int((rec_df["bet_type"] == "single").sum()) if "bet_type" in rec_df.columns else 0)
    with metrics_cols[2]:
        best_edge = pd.to_numeric(rec_df.get("edge_pts"), errors="coerce").max()
        st.metric("Best Edge", f"{best_edge:+.1f} pts" if pd.notna(best_edge) else "—")
    with metrics_cols[3]:
        avg_conf = pd.to_numeric(rec_df.get("confidence"), errors="coerce").mean()
        st.metric("Avg Confidence", f"{avg_conf:.2f}" if pd.notna(avg_conf) else "—")

    view_cols = [c for c in [
        "recommendation_rank",
        "bet_type",
        "market",
        "selection_label",
        "odds_american",
        "model_prob",
        "book_prob",
        "edge_pts",
        "ev_per_1",
        "confidence",
        "status",
    ] if c in rec_df.columns]
    view = rec_df[view_cols].copy()
    if "model_prob" in view.columns:
        view["model_prob"] = (pd.to_numeric(view["model_prob"], errors="coerce") * 100).round(2)
        view = view.rename(columns={"model_prob": "model_%"})
    if "book_prob" in view.columns:
        view["book_prob"] = (pd.to_numeric(view["book_prob"], errors="coerce") * 100).round(2)
        view = view.rename(columns={"book_prob": "book_%"})
    if "ev_per_1" in view.columns:
        view["ev_per_1"] = (pd.to_numeric(view["ev_per_1"], errors="coerce") * 100).round(2)
        view = view.rename(columns={"ev_per_1": "ev_%"})
    if "edge_pts" in view.columns:
        view["edge_pts"] = pd.to_numeric(view["edge_pts"], errors="coerce").round(2)
    if "odds_american" in view.columns:
        view["odds_american"] = pd.to_numeric(view["odds_american"], errors="coerce")

    st.dataframe(view.head(20), hide_index=True, use_container_width=True)

    results_df = load_recommended_bet_results_df(tournament_id)
    if results_df.empty:
        st.info("No settled tracked bets yet.")
        return

    if "outcome_status" in results_df.columns:
        status_series = results_df["outcome_status"].astype(str).str.lower()
    else:
        status_series = pd.Series(["pending"] * len(results_df), index=results_df.index, dtype=object)
    settled = results_df[status_series.isin(["won", "lost"])].copy()
    if settled.empty:
        st.info("Tracked bets found, but none are settled yet.")
        return

    settled["outcome_win"] = settled["outcome_status"].astype(str).str.lower().eq("won")
    settled["pnl_per_1"] = pd.to_numeric(settled.get("pnl_per_1"), errors="coerce")
    settled["clv_pts"] = pd.to_numeric(settled.get("clv_pts"), errors="coerce")

    perf_cols = st.columns(4)
    with perf_cols[0]:
        st.metric("Settled Bets", int(len(settled)))
    with perf_cols[1]:
        hit_rate = settled["outcome_win"].mean() * 100 if len(settled) else 0.0
        st.metric("Hit Rate", f"{hit_rate:.1f}%")
    with perf_cols[2]:
        roi = settled["pnl_per_1"].mean() * 100 if settled["pnl_per_1"].notna().any() else np.nan
        st.metric("Avg ROI / Bet", f"{roi:+.1f}%" if pd.notna(roi) else "—")
    with perf_cols[3]:
        clv = settled["clv_pts"].mean() if settled["clv_pts"].notna().any() else np.nan
        st.metric("Avg CLV (pts)", f"{clv:+.2f}" if pd.notna(clv) else "—")

    recent_cols = [c for c in [
        "graded_at",
        "bet_type",
        "market",
        "selection_label",
        "odds_american",
        "outcome_status",
        "pnl_per_1",
        "clv_pts",
    ] if c in settled.columns]
    recent_df = settled[recent_cols].copy()
    if "graded_at" in recent_df.columns:
        recent_df = recent_df.sort_values("graded_at", ascending=False)
    st.dataframe(recent_df.head(12), hide_index=True, use_container_width=True)








def render_longshots_view(min_odds: int = 5000, max_rows: int = 24):
    """Rich UI view for longshots from latest FanDuel/PGA odds file."""
    df, _, _ = load_latest_fanduel_odds_df()
    if df.empty:
        st.info("No odds file found. Run the odds fetch first.")
        return

    player_col = "player_name" if "player_name" in df.columns else "name"
    df = df[df[player_col].notna()].copy()
    df = df[df["odds_numeric"].notna()].copy()
    df = df[df["odds_numeric"] >= min_odds].copy()

    if df.empty:
        st.warning(f"No longshots found at +{min_odds} or longer.")
        return

    # Most likely longshots first (lower odds among longshots)
    df = df.sort_values("odds_numeric", ascending=True).head(max_rows).reset_index(drop=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Longshots", len(df))
    with c2:
        st.metric("Avg Implied %", f"{(df['implied_prob'].mean() * 100):.2f}%")
    with c3:
        st.metric("Cutoff", f"+{int(min_odds)}")

    st.markdown("#### Top Longshots")
    top3 = df.head(3)
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            edge_txt = ""
            if "edge_pct_points" in row and pd.notna(row.get("edge_pct_points")):
                edge_txt = f"  \nEdge: **{row['edge_pct_points']:+.2f} pts**"
            st.markdown(
                f"{medals[i]} **{row[player_col]}**\n\n"
                f"Odds: **+{int(row['odds_numeric'])}**  \n"
                f"Implied: **{row['implied_prob'] * 100:.2f}%**{edge_txt}"
            )

    view_df = pd.DataFrame(
        {
            "Rank": np.arange(1, len(df) + 1),
            "Player": df[player_col].astype(str),
            "Odds": df["odds_numeric"].round(0).astype("Int64").astype(str).radd("+"),
            "Implied %": (df["implied_prob"] * 100).round(2),
            "Model Win %": (
                (pd.to_numeric(df.get("model_win_prob"), errors="coerce") * 100).round(2)
                if "model_win_prob" in df.columns else np.nan
            ),
            "Edge (pts)": (
                pd.to_numeric(df.get("edge_pct_points"), errors="coerce").round(2)
                if "edge_pct_points" in df.columns else np.nan
            ),
        }
    )

    st.dataframe(
        view_df,
        hide_index=True,
        use_container_width=True,
        height=520,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="large"),
            "Odds": st.column_config.TextColumn(width="small"),
            "Implied %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Model Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Edge (pts)": st.column_config.NumberColumn(width="small", format="%.2f"),
        },
    )


def render_favorites_view(max_rows: int = 30):
    """Rich UI view for favorites from latest FanDuel/PGA odds file."""
    df, odds_file, _ = load_latest_fanduel_odds_df()
    if df.empty:
        st.info("No odds file found. Run the odds fetch first.")
        return

    player_col = "player_name" if "player_name" in df.columns else "name"
    df = df[df[player_col].notna()].copy()
    df = df[df["odds_numeric"].notna()].copy()

    if df.empty:
        st.warning("No odds data available.")
        return

    # Sort by shortest odds (favorites first)
    df = df.sort_values("odds_numeric", ascending=True).head(max_rows).reset_index(drop=True)

    # Summary metrics
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Favorites Listed", len(df))
    with c2:
        top_prob = df["implied_prob"].iloc[0] * 100 if not df.empty else 0
        st.metric("Top Favorite %", f"{top_prob:.1f}%")
    with c3:
        file_time = datetime.fromtimestamp(odds_file.stat().st_mtime) if odds_file else datetime.now()
        st.metric("Updated", file_time.strftime("%b %d %H:%M"))

    # Top 3 favorites as cards
    st.markdown("#### ⭐ Top Favorites")
    top3 = df.head(3)
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            with st.container():
                st.markdown(f"**{medals[i]} {row[player_col]}**")
                st.metric("Odds", f"+{int(row['odds_numeric'])}")
                st.caption(f"Win Prob: {row['implied_prob'] * 100:.1f}%")
                if "edge_pct_points" in row and pd.notna(row.get("edge_pct_points")):
                    st.caption(f"Model Edge: {row['edge_pct_points']:+.2f} pts")

    # Full table
    st.markdown("#### 📋 Full Favorites List")
    view_df = pd.DataFrame({
        "Rank": np.arange(1, len(df) + 1),
        "Player": df[player_col].astype(str),
        "Odds": df["odds_numeric"].round(0).astype("Int64").astype(str).radd("+"),
        "Win %": (df["implied_prob"] * 100).round(2),
        "Model Win %": (
            (pd.to_numeric(df.get("model_win_prob"), errors="coerce") * 100).round(2)
            if "model_win_prob" in df.columns else np.nan
        ),
        "Edge (pts)": (
            pd.to_numeric(df.get("edge_pct_points"), errors="coerce").round(2)
            if "edge_pct_points" in df.columns else np.nan
        ),
    })

    st.dataframe(
        view_df,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="large"),
            "Odds": st.column_config.TextColumn(width="small"),
            "Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Model Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Edge (pts)": st.column_config.NumberColumn(width="small", format="%.2f"),
        },
    )


# ============================================================================
# WEATHER HELPERS
# ============================================================================

COURSE_COORDINATES = {
    "pebble beach": (36.5675, -121.9486),
    "torrey pines": (32.9005, -117.2516),
    "augusta national": (33.5021, -82.0232),
    "tpc scottsdale": (33.6417, -111.9083),
    "riviera": (34.0489, -118.5003),
    "bay hill": (28.4603, -81.5053),
    "tpc sawgrass": (30.1975, -81.3964),
    "harbour town": (32.1363, -80.8090),
    "quail hollow": (35.1089, -80.8519),
    "southern hills": (36.0631, -95.9408),
    "bethpage black": (40.7445, -73.4533),
    "valhalla": (38.2527, -85.4938),
    "pinehurst": (35.1894, -79.4694),
    "royal troon": (55.5436, -4.8492),
    "st andrews": (56.3433, -2.8019),
    "muirfield": (56.0442, -2.8181),
    "kapalua": (21.0007, -156.6483),
    "waialae": (21.2769, -157.7559),
}

_PGA_GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

_PGA_WEATHER_QUERY = """
query Weather($tournamentId: ID!) {
  weather(tournamentId: $tournamentId) {
    title
    sponsorLink
    sponsorLogo
    sponsorLogoDark
    sponsorLogoAsset { imageOrg imagePath }
    sponsorLogoDarkAsset { imageOrg imagePath }
    modalSponsorLogoAsset { imageOrg imagePath }
    modalSponsorLogoDarkAsset { imageOrg imagePath }
    modalSponsorLogo
    modalSponsorLogoDark
    accessibilityText
    hourly {
      title
      condition
      windDirection
      windSpeedKPH
      windSpeedMPH
      humidity
      precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
    daily {
      title
      condition
      windDirection
      windSpeedKPH
      windSpeedMPH
      humidity
      precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
  }
}
"""


def _clean_weather_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    text = (
        text.replace("\u00b0F", "")
        .replace("°F", "")
        .replace("\u00b0C", "")
        .replace("°C", "")
        .replace("%", "")
    )
    try:
        return int(round(float(text)))
    except Exception:
        return value


def _normalize_weather_periods(periods):
    rows = []
    for period in periods or []:
        item = dict(period or {})
        temp = item.get("temperature") or {}
        if isinstance(temp, dict):
            item["temperature"] = {
                k: _clean_weather_number(v)
                for k, v in temp.items()
                if k in {"tempF", "tempC", "minTempF", "minTempC", "maxTempF", "maxTempC", "__typename"}
            }
        for key in ("windSpeedKPH", "windSpeedMPH", "humidity", "precipitation"):
            if key in item:
                item[key] = _clean_weather_number(item.get(key))
        rows.append(item)
    return rows


def get_course_coordinates(course_name: str) -> tuple:
    """Get lat/lon for a course, or default to Pebble Beach."""
    if not course_name:
        return COURSE_COORDINATES["pebble beach"]

    course_lower = course_name.lower()
    for key, coords in COURSE_COORDINATES.items():
        if key in course_lower:
            return coords

    return COURSE_COORDINATES["pebble beach"]


@st.cache_data(ttl=900)  # Cache for 15 minutes
def fetch_weather(lat: float, lon: float, tid: str = "") -> dict:
    """Fetch tournament weather forecast from PGA Tour GraphQL API.
    Falls back to open-meteo current conditions if tid not provided or API fails.
    Reads from data/weather/{tid}.json if fresh (<3h)."""
    import time
    import requests

    # Try saved snapshot first (avoids hitting API every page load)
    if tid:
        weather_file = DATA_DIR / "weather" / f"{tid}.json"
        if weather_file.exists() and (time.time() - weather_file.stat().st_mtime) < 10800:
            try:
                saved = json.loads(weather_file.read_text())
                # Only trust cached PGA daily forecast for tid-based event pages.
                # If the cached file is just the open-meteo fallback, keep going
                # so we can retry the official PGA endpoint.
                if saved.get("success") and saved.get("daily"):
                    return saved
                if not tid and saved.get("success") and saved.get("temp_f") is not None:
                    return saved
            except Exception:
                pass

    # Primary: PGA Tour GraphQL weather query — returns 7-day daily forecast + hourly
    if tid:
        try:
            resp = requests.post(
                "https://orchestrator.pgatour.com/graphql",
                json={
                    "query": _PGA_WEATHER_QUERY,
                    "variables": {"tournamentId": tid},
                    "operationName": "Weather",
                },
                headers=_PGA_GRAPHQL_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            _body = resp.json()
            if _body.get("errors"):
                raise RuntimeError(_body["errors"][0].get("message", "Weather query failed"))
            _w = _body.get("data", {}).get("weather")
            if _w and _w.get("daily"):
                result = {
                    "success": True,
                    "source": "pgatour",
                    "title": _w.get("title", ""),
                    "daily": _normalize_weather_periods(_w.get("daily", [])),
                    "hourly": _normalize_weather_periods(_w.get("hourly", [])),
                    "saved_at": datetime.now().isoformat(),
                }
                weather_dir = DATA_DIR / "weather"
                weather_dir.mkdir(parents=True, exist_ok=True)
                (weather_dir / f"{tid}.json").write_text(json.dumps(result, indent=2))
                return result
        except Exception:
            pass

    # Fallback: open-meteo current conditions (lat/lon required)
    if lat and lon:
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat, "longitude": lon, "current_weather": "true",
                "temperature_unit": "fahrenheit", "windspeed_unit": "mph",
                "timezone": "America/Los_Angeles",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            current = resp.json().get("current_weather", {})
            weather_codes = {
                0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
                45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle",
                55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
                71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 80: "Rain Showers",
                81: "Rain Showers", 82: "Heavy Showers", 95: "Thunderstorm",
            }
            code = current.get("weathercode", 0)
            result = {
                "temp_f": round(current.get("temperature", 0)),
                "wind_mph": round(current.get("windspeed", 0)),
                "wind_dir": current.get("winddirection", 0),
                "conditions": weather_codes.get(code, "Unknown"),
                "code": code,
                "is_windy": current.get("windspeed", 0) > 15,
                "success": True,
                "source": "openmeteo",
                "saved_at": datetime.now().isoformat(),
            }
            if tid:
                weather_dir = DATA_DIR / "weather"
                weather_dir.mkdir(parents=True, exist_ok=True)
                (weather_dir / f"{tid}.json").write_text(json.dumps(result, indent=2))
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "No weather data available"}


# Condition code → emoji (PGA Tour enum values)
_PGA_CONDITION_ICON = {
    "DAY_SUNNY": "☀️", "DAY_MOSTLY_SUNNY": "🌤️", "DAY_PARTLY_CLOUDY": "⛅",
    "DAY_MOSTLY_CLOUDY": "🌥️", "DAY_CLOUDY": "☁️", "DAY_OVERCAST": "☁️",
    "DAY_SCATTERED_SHOWERS": "🌦️", "DAY_ISOLATED_SHOWERS": "🌦️",
    "DAY_SHOWERS": "🌧️", "DAY_RAIN": "🌧️", "DAY_HEAVY_RAIN": "🌧️",
    "DAY_ISOLATED_THUNDERSTORMS": "⛈️", "DAY_SCATTERED_THUNDERSTORMS": "⛈️",
    "DAY_THUNDERSTORMS": "⛈️", "DAY_SNOW": "🌨️", "DAY_FOGGY": "🌫️",
    "DAY_WINDY": "💨", "DAY_HAZY": "🌫️",
    "NIGHT_CLEAR": "🌙", "NIGHT_MOSTLY_CLEAR": "🌙", "NIGHT_PARTLY_CLOUDY": "⛅",
    "NIGHT_MOSTLY_CLOUDY": "🌥️", "NIGHT_CLOUDY": "☁️", "NIGHT_OVERCAST": "☁️",
    "NIGHT_ISOLATED_CLOUDS": "🌙", "NIGHT_ISOLATED_SHOWERS": "🌦️",
    "NIGHT_SCATTERED_SHOWERS": "🌦️", "NIGHT_SHOWERS": "🌧️",
    "NIGHT_THUNDERSTORMS": "⛈️", "NIGHT_SNOW": "🌨️", "NIGHT_FOGGY": "🌫️",
}
# Wind direction enum → compass abbreviation
_PGA_WIND_DIR = {
    "NORTH": "N", "NORTH_NORTH_EAST": "NNE", "NORTH_EAST": "NE",
    "EAST_NORTH_EAST": "ENE", "EAST": "E", "EAST_SOUTH_EAST": "ESE",
    "SOUTH_EAST": "SE", "SOUTH_SOUTH_EAST": "SSE", "SOUTH": "S",
    "SOUTH_SOUTH_WEST": "SSW", "SOUTH_WEST": "SW", "WEST_SOUTH_WEST": "WSW",
    "WEST": "W", "WEST_NORTH_WEST": "WNW", "NORTH_WEST": "NW",
    "NORTH_NORTH_WEST": "NNW",
}


def render_weather_widget(course_name: str, tid: str = ""):
    """Render a weather widget for the tournament course."""
    lat, lon = get_course_coordinates(course_name)
    weather = fetch_weather(lat, lon, tid=tid)

    if not weather.get("success"):
        st.warning(f"Could not fetch weather: {weather.get('error', 'Unknown error')}")
        return

    # ── PGA Tour forecast format: 4-column round-day layout ──────────────────
    if weather.get("daily"):
        daily = weather["daily"]
        _ROUND_DAYS = {"Thu", "Fri", "Sat", "Sun"}
        round_days = [d for d in daily if d.get("title") in _ROUND_DAYS]
        if not round_days:
            round_days = daily[:4]

        st.markdown("#### Weather Forecast")
        cols = st.columns(len(round_days))
        for col, day in zip(cols, round_days):
            with col:
                icon = _PGA_CONDITION_ICON.get(day.get("condition", ""), "🌡️")
                temp = day.get("temperature", {})
                if "maxTempF" in temp:
                    hi = temp["maxTempF"]
                    lo = temp["minTempF"]
                    temp_str = f"{hi}° / {lo}°"
                elif "tempF" in temp:
                    temp_str = f"{temp['tempF']}°"
                else:
                    temp_str = "—"
                wind_dir = _PGA_WIND_DIR.get(day.get("windDirection", ""), day.get("windDirection", ""))
                wind_mph = day.get("windSpeedMPH", "—")
                precip = day.get("precipitation", "—")
                try:
                    is_windy = int(wind_mph) > 15
                except (ValueError, TypeError):
                    is_windy = False
                wind_color = "#ff9f43" if is_windy else "inherit"
                st.markdown(
                    f"<div style='text-align:center'>"
                    f"<div style='font-weight:600;font-size:0.85rem;letter-spacing:0.05em'>{day['title']}</div>"
                    f"<div style='font-size:1.9rem;line-height:1.3'>{icon}</div>"
                    f"<div style='font-size:0.9rem;font-weight:500'>{temp_str}</div>"
                    f"<div style='font-size:0.75rem;color:{wind_color};margin-top:2px'>{wind_mph} mph {wind_dir}</div>"
                    f"<div style='font-size:0.75rem;color:#7eb8f7;margin-top:1px'>&#128167; {precip}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        _saved = weather.get("saved_at", "")
        if _saved:
            try:
                _dt = datetime.fromisoformat(_saved)
                st.caption(f"Updated {_dt.strftime('%-I:%M %p')}")
            except Exception:
                pass
        return

    # ── Legacy fallback: open-meteo current conditions ────────────────────────
    weather_icons = {
        "Clear": "☀️", "Mainly Clear": "🌤️", "Partly Cloudy": "⛅",
        "Overcast": "☁️", "Foggy": "🌫️", "Light Drizzle": "🌦️",
        "Drizzle": "🌧️", "Heavy Drizzle": "🌧️", "Light Rain": "🌧️",
        "Rain": "🌧️", "Heavy Rain": "⛈️", "Rain Showers": "🌦️",
        "Thunderstorm": "⛈️", "Light Snow": "🌨️", "Snow": "❄️",
    }
    icon = weather_icons.get(weather["conditions"], "🌡️")

    def wind_direction_to_compass(degrees):
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return directions[round(degrees / 45) % 8]

    wind_compass = wind_direction_to_compass(weather.get("wind_dir", 0))

    st.markdown("#### Current Weather")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Temperature", f"{weather['temp_f']}°F")
    with col2:
        wind_label = f"{weather['wind_mph']} mph {wind_compass}"
        delta = "Windy" if weather["is_windy"] else None
        st.metric("Wind", wind_label, delta=delta)
    with col3:
        st.metric("Conditions", f"{icon} {weather['conditions']}")


                                                                                                                        
  # ============================================================================                                        
  # PREDICTION VISUALIZATION HELPERS                                                                                    
  # ============================================================================                                        
                                                                                                                        
def render_tier_list(predictions_df: pd.DataFrame):                                                                   
    """Render predictions as a tier list."""                                                                          
    st.markdown("#### 🏆 Player Tier List")                                                                           
                                                                                                                    
    if predictions_df.empty:                                                                                          
        st.info("No predictions available")                                                                           
        return                                                                                                        
                                                                                                                    
    rank_col = "expected_value" if "expected_value" in predictions_df.columns else "win_prob"                         
    df = predictions_df.sort_values(rank_col, ascending=False).reset_index(drop=True)                                 
                                                                                                                    
    tiers = {                                                                                                         
        "S": {"color": "#ffd700", "bg": "#fff9e6", "range": (0, 5)},                                                  
        "A": {"color": "#4caf50", "bg": "#e8f5e9", "range": (5, 15)},                                                 
        "B": {"color": "#2196f3", "bg": "#e3f2fd", "range": (15, 30)},                                                
        "C": {"color": "#9e9e9e", "bg": "#f5f5f5", "range": (30, 50)},                                                
    }                                                                                                                 
                                                                                                                    
    for tier, config in tiers.items():                                                                                
        start, end = config["range"]                                                                                  
        tier_players = df.iloc[start:end]                                                                             
                                                                                                                    
        if tier_players.empty:                                                                                        
            continue                                                                                                  
                                                                                                                    
        names = tier_players["player_name"].tolist()                                                                  
        chips = " ".join([f'<span style="background: white; padding: 0.25rem 0.5rem; border-radius: 15px; font-size:  0.85rem; margin: 2px;">{n}</span>' for n in names])                                                                   
                                                                                                                    
        st.markdown(f"""                                                                                              
        <div style="background: {config['bg']}; border-left: 4px solid {config['color']};                             
                    padding: 0.75rem; margin: 0.5rem 0; border-radius: 8px;">                                         
            <strong style="color: {config['color']}; font-size: 1.2rem;">{tier} Tier</strong>                         
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">                            
                {chips}                                                                                               
            </div>                                                                                                    
        </div>                                                                                                        
        """, unsafe_allow_html=True) 



















def render_tier_list(predictions_df: pd.DataFrame):
    """Render predictions as a visual tier list."""
    st.markdown("#### Player Tiers by Expected Value")

    # Define tiers based on percentiles
    if predictions_df.empty:
        st.warning("No predictions data available")
        return

    df = predictions_df.copy()
    df = df.sort_values("expected_value", ascending=False)

    # Calculate tier boundaries
    tier_configs = [
        ("S", "#FFD700", "Elite - Top 5", 5),
        ("A", "#C0C0C0", "Strong Contenders - Top 10", 10),
        ("B", "#CD7F32", "Solid Plays - Top 20", 20),
        ("C", "#4A90D9", "Value Picks - Top 35", 35),
        ("D", "#808080", "Longshots - Rest", 100),
    ]

    # Assign tiers
    df["tier"] = "D"
    df["tier_color"] = "#808080"
    for i, (tier, color, _, cutoff) in enumerate(tier_configs):
        if i == 0:
            mask = df.index.isin(df.head(cutoff).index)
        else:
            prev_cutoff = tier_configs[i-1][3]
            mask = df.index.isin(df.head(cutoff).index) & ~df.index.isin(df.head(prev_cutoff).index)
        df.loc[mask, "tier"] = tier
        df.loc[mask, "tier_color"] = color

    # Render each tier
    for tier, color, label, cutoff in tier_configs:
        tier_players = df[df["tier"] == tier]
        if tier_players.empty:
            continue

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {color}22, {color}11);
                    border-left: 4px solid {color}; padding: 12px; margin: 10px 0; border-radius: 8px;">
            <span style="font-size: 1.5em; font-weight: bold; color: {color};">
                {tier} Tier
            </span>
            <span style="color: #888; margin-left: 12px;">{label}</span>
        </div>
        """, unsafe_allow_html=True)

        # Display players in this tier as cards
        cols = st.columns(min(5, len(tier_players)))
        for idx, (_, player) in enumerate(tier_players.iterrows()):
            with cols[idx % 5]:
                ev = player.get("expected_value", 0)
                win_prob = player.get("win_prob", 0) * 100
                st.markdown(f"""
                <div style="background: {color}15; padding: 8px; border-radius: 6px;
                            margin: 4px 0; text-align: center; border: 1px solid {color}33;">
                    <div style="font-weight: bold; font-size: 0.9em;">
                        {player.get('player_name', 'Unknown')[:18]}
                    </div>
                    <div style="font-size: 0.8em; color: #666;">
                        EV: ${ev:,.0f} | {win_prob:.1f}%
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("")  # Spacing


def get_prediction_files():
    """Get available prediction files."""
    if OUTPUTS_DIR.exists():
        return sorted(OUTPUTS_DIR.glob("*_predictions.csv"),
                     key=lambda x: x.stat().st_mtime, reverse=True)
    return []


def _prediction_file_tournament_key(path: Path) -> str:
    stem = re.sub(r"_\d{8}_predictions$", "", path.stem)
    stem = re.sub(r"_predictions$", "", stem)
    return _normalize_tournament_key(stem.replace("_", " "))


def _prediction_file_date_token(path: Path) -> int | None:
    m = re.search(r"_(\d{8})_predictions$", path.stem)
    return int(m.group(1)) if m else None


def _resolve_prediction_file_for_tournament(tournament_name: str, event_date: str = "") -> Path | None:
    """Find the best saved prediction file for a historical tournament row."""
    target_key = _normalize_tournament_key(tournament_name)
    if not target_key:
        return None

    target_tokens = set(target_key.split())
    target_date = None
    if event_date:
        try:
            target_date = int(str(event_date).replace("-", "")[:8])
        except Exception:
            target_date = None

    candidates = []
    for path in get_prediction_files():
        if path.name == "latest_predictions.csv":
            continue
        file_key = _prediction_file_tournament_key(path)
        if not file_key:
            continue
        file_tokens = set(file_key.split())
        overlap = len(target_tokens & file_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(target_tokens | file_tokens), 1)
        if target_key in file_key or file_key in target_key:
            score = max(score, 0.95)
        if score < 0.45:
            continue

        fdate = _prediction_file_date_token(path)
        prior_fit = 1 if (target_date and fdate and fdate <= target_date) else 0
        gap = abs((fdate or 0) - (target_date or 0)) if target_date and fdate else 99999999
        candidates.append((score, prior_fit, -(fdate or 0), -int(path.stat().st_mtime), gap, path))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][-1]


@st.cache_data(ttl=900)
def load_prediction_rank_lookup_for_tournament(tournament_name: str, event_date: str = "") -> dict:
    """Load name_key -> model rank mapping for a saved tournament prediction file."""
    pred_path = _resolve_prediction_file_for_tournament(tournament_name, event_date)
    if pred_path is None or not pred_path.exists():
        return {}
    try:
        df = pd.read_csv(pred_path)
    except Exception:
        return {}
    if df.empty:
        return {}
    df = ensure_player_name_column(df)
    if "player_name" not in df.columns:
        return {}
    rank_col = None
    for candidate in ("expected_value", "win_prob", "top10_prob"):
        if candidate in df.columns:
            rank_col = candidate
            break
    if not rank_col:
        return {}
    df[rank_col] = pd.to_numeric(df[rank_col], errors="coerce")
    df = df.dropna(subset=[rank_col]).sort_values(rank_col, ascending=False).reset_index(drop=True)
    if df.empty:
        return {}
    df["model_rank"] = np.arange(1, len(df) + 1)
    df["name_key"] = df["player_name"].apply(_name_key)
    df = df[df["name_key"] != ""].drop_duplicates("name_key")
    return dict(zip(df["name_key"], df["model_rank"]))


@st.cache_data(ttl=300)
def load_betting_profiles(tournament_id: str = None):
    """Load betting profiles for current tournament."""
    profiles_dir = DATA_DIR / "betting_profiles"

    if tournament_id:
        # Try both naming conventions (canonical first, then articles)
        for prefix in ("betting_profiles_", "articles_"):
            specific_file = profiles_dir / f"{prefix}{tournament_id}.csv"
            if specific_file.exists():
                return pd.read_csv(specific_file)

    # Fallback order should prefer canonical betting profiles over article extracts.
    canonical_files = sorted(
        profiles_dir.glob("betting_profiles_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if canonical_files:
        return pd.read_csv(canonical_files[0])

    article_files = sorted(
        profiles_dir.glob("articles_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if article_files:
        return pd.read_csv(article_files[0])

    return pd.DataFrame()


def _resolve_betting_profiles_file(tournament_id: str = None) -> Path | None:
    """Resolve betting profiles file path using same priority as loader."""
    profiles_dir = DATA_DIR / "betting_profiles"
    if not profiles_dir.exists():
        return None

    tid = str(tournament_id or "").strip().upper()
    if tid:
        for prefix in ("betting_profiles_", "articles_"):
            p = profiles_dir / f"{prefix}{tid}.csv"
            if p.exists():
                return p

    canonical_files = sorted(
        profiles_dir.glob("betting_profiles_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if canonical_files:
        return canonical_files[0]

    article_files = sorted(
        profiles_dir.glob("articles_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if article_files:
        return article_files[0]

    return None


def get_player_profile(profiles_df: pd.DataFrame, player_name: str) -> dict:
    """Get betting profile for a specific player."""
    if profiles_df.empty:
        return None

    # Normalize player name for matching
    player_lower = player_name.lower().strip()

    for _, row in profiles_df.iterrows():
        profile_name = str(row.get('player_name', '')).lower().strip()
        if player_lower in profile_name or profile_name in player_lower:
            return row.to_dict()
        # Also check title
        title = str(row.get('title', '')).lower()
        if player_lower.split()[0] in title and player_lower.split()[-1] in title:
            return row.to_dict()

    return None


def render_betting_profiles_section(preds_df: pd.DataFrame, tournament_id: str = ""):
    """Render tournament betting profiles in the Betting page."""
    st.markdown("### 💼 Betting Profiles")

    tid = str(tournament_id or "").strip().upper()
    source_file = _resolve_betting_profiles_file(tid if tid else None)
    profiles_df = load_betting_profiles(tid if tid else None)

    if profiles_df.empty:
        st.info(
            "No betting profiles found. Run: "
            "`python3 scripts/scrapers/fetch_betting_profiles.py --tournament-id <RYYYYNNN> --field data/fields/field_<RYYYYNNN>.csv`"
        )
        return

    updated_str = (
        datetime.fromtimestamp(source_file.stat().st_mtime).strftime("%b %d %H:%M")
        if source_file and source_file.exists()
        else "unknown"
    )
    source_name = source_file.name if source_file else "unknown"

    tname = ""
    if "tournament_name" in profiles_df.columns:
        vals = profiles_df["tournament_name"].dropna().astype(str).str.strip()
        if not vals.empty:
            tname = vals.iloc[0]

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Profiles", int(len(profiles_df)))
    with m2:
        st.metric("Tournament", tname or "—")
    with m3:
        st.metric("Updated", updated_str)
    st.caption(f"Source: `{source_name}`")

    # Player picker
    player_options = sorted(profiles_df["player_name"].dropna().astype(str).str.strip().unique().tolist()) \
        if "player_name" in profiles_df.columns else []

    if not player_options:
        st.info("Profile file loaded, but it does not contain `player_name` rows.")
        return

    pick_default = 0
    if preds_df is not None and not preds_df.empty and "player_name" in preds_df.columns:
        pred_names = set(preds_df["player_name"].dropna().astype(str).str.strip().tolist())
        for i, nm in enumerate(player_options):
            if nm in pred_names:
                pick_default = i
                break

    selected_profile_player = st.selectbox(
        "Select player profile",
        options=player_options,
        index=pick_default,
        key="betting_profile_player_select",
    )

    profile = get_player_profile(profiles_df, selected_profile_player)
    if profile:
        render_player_profile_card(profile, show_full=True)
    else:
        st.warning(f"No profile details found for {selected_profile_player}.")

    with st.expander("All Profiles (table)", expanded=False):
        cols = [c for c in [
            "player_name", "odds_to_win", "world_rank", "sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt",
            "course_history_summary", "recent_form_summary"
        ] if c in profiles_df.columns]
        if cols:
            st.dataframe(profiles_df[cols], hide_index=True, use_container_width=True, height=320)
        else:
            st.dataframe(profiles_df, hide_index=True, use_container_width=True, height=320)


def format_bullets_as_list(bullets_str: str) -> list:
    """Convert pipe-separated bullets to list."""
    if not bullets_str or pd.isna(bullets_str):
        return []
    return [b.strip() for b in str(bullets_str).split('|') if b.strip()]


def clean_betting_profile_text(text: str) -> str:
    """Remove disclaimer and boilerplate from betting profile text."""
    import re

    if not text or pd.isna(text):
        return ""

    cleaned = str(text)

    # Remove the common disclaimer block that appears at end of summaries
    # This captures: "All stats in this article... HaveAGamePlan.org."
    disclaimer_block_pattern = r'All stats in this article are accurate for[^.]*\..*?HaveAGamePlan\.org\.?\s*'
    cleaned = re.sub(disclaimer_block_pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)

    # Also handle partial disclaimer patterns that might appear alone
    partial_disclaimers = [
        r'Responsible sports betting starts with a game plan[^.]*\.',
        r'Set a budget\. Keep it social\. Play with friends\.\s*',
        r'Learn the game and know the odds\.\s*',
        r'Play with trusted, licensed operators\.\s*',
        r'CLICK HERE to learn more at HaveAGamePlan\.org\.?\s*',
        r'Note: Using player performance data from ShotLink powered by CDW[^.]*\.',
        r'[^.]*PGA TOUR has created this story using AWS Gen AI technology[^.]*\.',
        r'While we strive for accuracy and quality[^.]*error-free[^.]*\.',
    ]

    for pattern in partial_disclaimers:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip()

    return cleaned

def parse_strokes_gained_from_bullets(bullets: list) -> dict:                                                         
    """Extract strokes gained stats from bullet points."""                                                            
    sg_stats = {                                                                                                      
        'sg_ott': None,  # Off the Tee                                                                                
        'sg_app': None,  # Approach                                                                                   
        'sg_atg': None,  # Around the Green                                                                           
        'sg_putt': None, # Putting                                                                                    
        'sg_total': None,                                                                                             
        'driving_dist': None,                                                                                         
        'gir': None,  # Greens in Regulation                                                                          
    }                                                                                                                 
                                                                                                                    
    for bullet in bullets:                                                                                            
        b_lower = bullet.lower()                                                                                      
                                                                                                                    
        # SG: Off-the-Tee                                                                                             
        if 'off-the-tee' in b_lower or 'off the tee' in b_lower:                                                      
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if match:                                                                                                 
                sg_stats['sg_ott'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Approach                                                                                                
        if 'approach' in b_lower and 'green' in b_lower:                                                              
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'sports a\s*(-?\d+\.?\d*)', b_lower)                                               
            if match:                                                                                                 
                sg_stats['sg_app'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Around the Green                                                                                        
        if 'around-the-green' in b_lower or 'around the green' in b_lower:                                            
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if match:                                                                                                 
                sg_stats['sg_atg'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Putting                                                                                                 
        if 'putting' in b_lower and 'strokes gained' in b_lower:                                                      
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'delivered a\s*(-?\d+\.?\d*)', b_lower)                                            
            if match:                                                                                                 
                sg_stats['sg_putt'] = float(match.group(1))                                                           
                                                                                                                    
        # SG: Total                                                                                                   
        if 'total' in b_lower and 'strokes gained' in b_lower:                                                        
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained: total', b_lower)                                      
            if not match:                                                                                             
                match = re.search(r'averaged\s*(-?\d+\.?\d*)\s*strokes gained: total', b_lower)                       
            if match:                                                                                                 
                sg_stats['sg_total'] = float(match.group(1))                                                          
                                                                                                                    
        # Driving Distance                                                                                            
        if 'driving distance' in b_lower:                                                                             
            import re                                                                                                 
            match = re.search(r'(\d+\.?\d*)\s*yards', b_lower)                                                        
            if match:                                                                                                 
                sg_stats['driving_dist'] = float(match.group(1))                                                      
                                                                                                                    
        # GIR                                                                                                         
        if 'greens in regulation' in b_lower:                                                                         
            import re                                                                                                 
            match = re.search(r'(\d+\.?\d*)%', b_lower)                                                               
            if match:                                                                                                 
                sg_stats['gir'] = float(match.group(1))                                                               
                                                                                                                    
    return sg_stats   




def render_player_profile_card(profile: dict, show_full: bool = True):                                                
    """Render an improved player profile card with stats table and formatted sections."""                             
    import re                                                                                                         
                                                                                                                    
    bullets = format_bullets_as_list(profile.get('bullets', ''))                                                      
    sg_stats = parse_strokes_gained_from_bullets(bullets)                                                             
                                                                                                                    
    # === SUMMARY CARD ===                                                                                            
    st.markdown(f"### {profile.get('player_name', 'Player')}")                                                        
                                                                                                                    
    if profile.get('published_at'):                                                                                   
        pub_date = str(profile.get('published_at', ''))[:10]                                                          
                                                                                                                    
    # Key metrics row                                                                                                 
    col1, col2, col3, col4 = st.columns(4)                                                                            
                                                                                                                    
    with col1:                                                                                                        
        sg_total = sg_stats.get('sg_total')                                                                           
        if sg_total is not None:                                                                                      
            color = "green" if sg_total > 0 else "red" if sg_total < 0 else "gray"                                    
            st.metric("SG: Total", f"{sg_total:+.2f}", delta_color="off")                                             
        else:                                                                                                         
            st.metric("SG: Total", "—")                                                                               
                                                                                                                    
    with col2:                                                                                                        
        gir = sg_stats.get('gir')                                                                                     
        if gir:                                                                                                       
            st.metric("GIR %", f"{gir:.1f}%")                                                                         
        else:                                                                                                         
            st.metric("GIR %", "—")                                                                                   
                                                                                                                    
    with col3:                                                                                                        
        dist = sg_stats.get('driving_dist')                                                                           
        if dist:                                                                                                      
            st.metric("Driving", f"{dist:.0f} yds")                                                                   
        else:                                                                                                         
            st.metric("Driving", "—")                                                                                 
                                                                                                                    
    with col4:                                                                                                        
        # Extract best recent finish                                                                                  
        best_finish = "—"                                                                                             
        for b in bullets:                                                                                             
            if 'best finish' in b.lower():                                                                            
                match = re.search(r'(tied for \d+|\d+)(?:st|nd|rd|th)?', b.lower())                                   
                if match:                                                                                             
                    best_finish = match.group(1).replace('tied for ', 'T')                                            
                    break                                                                                             
        st.metric("Best Recent", best_finish)                                                                         
                                                                                                                    
    # === STROKES GAINED TABLE ===                                                                                    
    if any(v is not None for v in [sg_stats['sg_ott'], sg_stats['sg_app'], sg_stats['sg_atg'], sg_stats['sg_putt']]): 
        st.markdown("#### 📊 Strokes Gained Breakdown")                                                               
                                                                                                                    
        sg_data = {                                                                                                   
            "Category": ["Off-the-Tee", "Approach", "Around Green", "Putting"],                                       
            "Value": [                                                                                                
                f"{sg_stats['sg_ott']:+.3f}" if sg_stats['sg_ott'] is not None else "—",                              
                f"{sg_stats['sg_app']:+.3f}" if sg_stats['sg_app'] is not None else "—",                              
                f"{sg_stats['sg_atg']:+.3f}" if sg_stats['sg_atg'] is not None else "—",                              
                f"{sg_stats['sg_putt']:+.3f}" if sg_stats['sg_putt'] is not None else "—",                            
            ],                                                                                                        
            "Rating": [                                                                                               
                "🟢" if sg_stats['sg_ott'] and sg_stats['sg_ott'] > 0.3 else "🟡" if sg_stats['sg_ott'] and           
sg_stats['sg_ott'] > 0 else "🔴" if sg_stats['sg_ott'] else "⚪",                                                     
                "🟢" if sg_stats['sg_app'] and sg_stats['sg_app'] > 0.3 else "🟡" if sg_stats['sg_app'] and           
sg_stats['sg_app'] > 0 else "🔴" if sg_stats['sg_app'] else "⚪",                                                     
                "🟢" if sg_stats['sg_atg'] and sg_stats['sg_atg'] > 0.3 else "🟡" if sg_stats['sg_atg'] and           
sg_stats['sg_atg'] > 0 else "🔴" if sg_stats['sg_atg'] else "⚪",                                                     
                "🟢" if sg_stats['sg_putt'] and sg_stats['sg_putt'] > 0.3 else "🟡" if sg_stats['sg_putt'] and        
sg_stats['sg_putt'] > 0 else "🔴" if sg_stats['sg_putt'] else "⚪",                                                   
            ]                                                                                                         
        }                                                                                                             
                                                                                                                    
        st.dataframe(                                                                                                 
            pd.DataFrame(sg_data),                                                                                    
            hide_index=True,                                                                                          
            use_container_width=True,                                                                                 
            column_config={                                                                                           
                "Category": st.column_config.TextColumn(width="medium"),                                              
                "Value": st.column_config.TextColumn(width="small"),                                                  
                "Rating": st.column_config.TextColumn(width="small"),                                                 
            }                                                                                                         
        )                                                                                                             
                                                                                                                    
    if not show_full:                                                                                                 
        return                                                                                                        
                                                                                                                    
    # === CATEGORIZED INSIGHTS ===                                                                                    
    st.markdown("#### 🎯 Key Insights")                                                                               
                                                                                                                    
    # Categorize bullets                                                                                              
    course_bullets = []                                                                                               
    form_bullets = []                                                                                                 
    ranking_bullets = []                                                                                              
                                                                                                                    
    for b in bullets:                                                                                                 
        b_lower = b.lower()                                                                                           
        # Skip SG bullets (already shown in table)                                                                    
        if 'strokes gained' in b_lower:                                                                               
            continue                                                                                                  
        if 'first time' in b_lower or 'competing' in b_lower or 'at the' in b_lower or 'won this' in b_lower:         
            course_bullets.append(b)                                                                                  
        elif 'finish' in b_lower or 'appearance' in b_lower or 'last ten' in b_lower:                                 
            form_bullets.append(b)                                                                                    
        elif 'ranks' in b_lower or 'ranking' in b_lower or 'fedex' in b_lower:                                        
            ranking_bullets.append(b)                                                                                 
                                                                                                                    
    col1, col2 = st.columns(2)                                                                                        
                                                                                                                    
    with col1:                                                                                                        
        if course_bullets:                                                                                            
            st.markdown("**🏟️ At This Tournament**")                                                                  
            for b in course_bullets[:3]:                                                                              
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
        if form_bullets:                                                                                              
            st.markdown("**📈 Recent Form**")                                                                         
            for b in form_bullets[:3]:                                                                                
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
    with col2:                                                                                                        
        if ranking_bullets:                                                                                           
            st.markdown("**🏆 Rankings & Stats**")                                                                    
            for b in ranking_bullets[:4]:                                                                             
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
    # === OVERVIEW (collapsible) ===
    if profile.get('summary'):
        cleaned_summary = clean_betting_profile_text(profile.get('summary', ''))
        if cleaned_summary:
            with st.expander("📖 Full Overview"):
                st.markdown(cleaned_summary)







def get_quick_insight(player_name: str, profiles_df: pd.DataFrame, score=None) -> str:
    """Generate a quick insight for a player from betting profiles and score data."""
    insights = []
    profile = get_player_profile(profiles_df, player_name) if not profiles_df.empty else None 
    
    if profile:
        bullets = format_bullets_as_list(profile.get('bullets', ''))
        for bullet in bullets[:5]:
            bullet_lower = bullet.lower()
            if 'strokes gained: total' in bullet_lower and 'average' in bullet_lower:                                 
                  # Extract SG:Total - e.g., "averaged 1.5 Strokes Gained: Total"                                       
                if 'averaged' in bullet_lower:                                                                        
                    insights.append(bullet.split('averaged')[1].split('Strokes')[0].strip() + " SG:T avg")            
                    break                                                                                             
                elif 'best finish' in bullet_lower:                                                                       
                    # Extract recent best finish                                                                          
                    insights.append(bullet[:50])                                                                          
                    break                                                                                                 
                elif 'wins' in bullet_lower or 'won' in bullet_lower:                                                     
                    insights.append(bullet[:50])                                                                          
                    break                                                                                                 
                                                                                                                        
            # Add course history from score if available                                                                      
            if score and score.course_history_note:                                                                           
                note = score.course_history_note                                                                              
                # Shorten common patterns                                                                                     
                note = note.replace(" plays", "p").replace(" play", "p")                                                      
                if note and note not in insights:                                                                             
                    insights.append(note[:30])                                                                                
                                                                                                                            
                # Add form indicator from score                                                                                   
                if score:                                                                                                         
                    if score.current_form >= 75:                                                                                  
                        insights.append("🔥 Hot")                                                                                 
                    elif score.current_form >= 60:                                                                                
                        insights.append("📈 Good form")                                                                           
                    elif score.current_form <= 30:                                                                                
                        insights.append("📉 Cold")                                                                                
                                                                                                                            
                return " | ".join(insights[:2]) if insights else "—"


# ============================================================================
# LIVE TOURNAMENT HELPERS
# ============================================================================

LIVE_DIR = DATA_DIR / "live"
PERFORMANCE_DIR = DATA_DIR / "performance"
ODDS_DIR = DATA_DIR / "odds"


def leaderboard_meta_path(csv_path: Path) -> Path:
    return csv_path.parent / f"{csv_path.stem}_meta.json"


def load_leaderboard_meta(meta_path: Path) -> dict:
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_historical_cut_line(tournament_id: str) -> dict:
    """Query the DB for the historical average cut line at this venue.

    Why this exists:
    Before round 2 begins the PGA Tour API returns projected_cut_score=999
    (a sentinel meaning "no data yet").  Instead of showing +999 we look up
    the past 5 years at the same course and display a typical range.

    How it works:
    - The event number (last 3 digits of the R-ID) stays the same every year.
      R2016009, R2020009, R2026009 are all the Arnold Palmer at Bay Hill.
    - Players who MISS the cut only play 2 rounds, so their `to_par` in the
      leaderboards table IS their 2-round score.
    - The cut line = (best score of any player who missed) - 1 stroke.
      E.g. if the best missed score was +3, the cut was at +2.
    """
    try:
        import duckdb as _ddb
        _conn = _ddb.connect(str(DATA_DIR / "golf_data.db"), read_only=True)
        event_num = tournament_id[-3:]   # e.g. "009" from "R2026009"
        df = _conn.execute(f"""
            WITH cut_scores AS (
                SELECT
                    year,
                    MIN(CAST(REPLACE(REPLACE(to_par, 'E', '0'), '+', '') AS INTEGER)) AS best_missed
                FROM leaderboards
                WHERE tournament_id LIKE '%{event_num}'
                  AND year < 2026
                  AND position = 'CUT'
                GROUP BY year
            )
            SELECT
                COUNT(*)            AS years,
                AVG(best_missed - 1)  AS avg_cut,
                MIN(best_missed - 1)  AS best_cut,
                MAX(best_missed - 1)  AS worst_cut
            FROM cut_scores
        """).fetchdf()
        _conn.close()
        if df.empty or df["years"].iloc[0] == 0:
            return {}
        row = df.iloc[0]
        return {
            "years": int(row["years"]),
            "avg": round(row["avg_cut"], 1),
            "best": int(row["best_cut"]),
            "worst": int(row["worst_cut"]),
        }
    except Exception:
        return {}


@st.cache_data(ttl=120)  # Cache for 2 minutes for live data
def fetch_live_leaderboard(tournament_id: str = None) -> tuple:
    """Fetch live leaderboard data."""
    import subprocess

    # Run the scraper
    cmd = ["python3", str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_live_leaderboard.py")]
    if tournament_id:
        cmd.extend(["--tournament-id", tournament_id])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
    except Exception as e:
        return None, None, str(e)

    # Load the resulting CSV and metadata
    if tournament_id:
        csv_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv"
        meta_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}_meta.json"
    else:
        # Find most recent
        csv_files = sorted(LIVE_DIR.glob("leaderboard_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
        if csv_files:
            csv_path = csv_files[0]
            meta_path = leaderboard_meta_path(csv_path)
        else:
            return None, None, "No leaderboard data found"

    if not csv_path.exists():
        return None, None, "Leaderboard file not found"

    df = pd.read_csv(csv_path)
    meta = load_leaderboard_meta(meta_path)

    return df, meta, None


def render_live_leaderboard(df: pd.DataFrame, meta: dict, my_picks: list | None = None):
    """Render the live leaderboard.

    my_picks: list of player name strings (e.g. ["Rory McIlroy", "Russell Henley"]).
    Pick rows are highlighted in the table and a compact summary is shown above it.
    """
    if df is None or df.empty:
        st.warning("No leaderboard data available")
        return

    tournament_name = meta.get("tournament_name", "Tournament")
    current_round   = meta.get("current_round", 1)
    round_status    = meta.get("round_status", "")
    cut_line        = meta.get("cut_line", {})
    cut_projection  = meta.get("cut_projection", {})
    _tid            = meta.get("tournament_id", "")

    # ── Tournament header ────────────────────────────────────────────────────
    st.markdown(f"## {tournament_name}")

    _status_color = "#2ecc71" if "progress" in round_status.lower() else "#888"
    _cut_score    = cut_line.get("cutScore", "—") if cut_line else "—"

    _h1, _h2, _h3, _h4 = st.columns(4)
    _h1.metric("Round",   f"{current_round} of 4")
    _h2.metric("Status",  round_status or "Upcoming")
    _h3.metric("Cut",     _cut_score)
    _h4.metric("Field",   len(df))

    # ── Cut projection ───────────────────────────────────────────────────────
    if cut_projection:
        _cp_score  = cut_projection.get("projected_cut_score")
        _cp_bubble = cut_projection.get("bubble_count", 0)
        _cp_in     = cut_projection.get("safely_in", 0)
        _cp_out    = cut_projection.get("safely_out", 0)
        _no_live_cut = (not isinstance(_cp_score, int)) or _cp_score == 999 or _cp_score > 50

        if _no_live_cut:
            _hist = get_historical_cut_line(_tid) if _tid else {}
            if _hist:
                _avg_str   = f"{_hist['avg']:+.0f}" if _hist["avg"] != 0 else "E"
                _range_str = f"{_hist['best']:+d} to {_hist['worst']:+d}"
                st.caption(f"Projected cut (historical avg): **{_avg_str}** · range {_range_str} · ~{len(df)//2} players advance")
        else:
            _score_str = f"{_cp_score:+d}" if _cp_score != 0 else "E"
            _ca, _cb, _cc, _cd = st.columns(4)
            _ca.metric("Projected Cut",  _score_str)
            _cb.metric("On the Bubble",  _cp_bubble, help="Within 1 shot of cut line")
            _cc.metric("Safely In",      _cp_in)
            _cd.metric("Safely Out",     _cp_out)

    st.markdown("---")

    # ── Top 3 leader cards ───────────────────────────────────────────────────
    top3 = df.head(3)
    _pos_colors  = ["#FFD700", "#C0C0C0", "#CD7F32"]
    _pos_labels  = ["1st", "2nd", "3rd"]
    _leader_cols = st.columns(3)

    for i, (_, player) in enumerate(top3.iterrows()):
        with _leader_cols[i]:
            name    = str(player.get("player_name", "Unknown"))
            country = str(player.get("country", ""))
            thru    = str(player.get("thru", "-"))
            _odds_raw = player.get("odds_to_win")
            try:
                odds = str(int(float(_odds_raw))) if _odds_raw else ""
            except (ValueError, TypeError):
                odds = str(_odds_raw) if _odds_raw else ""

            # Normalize total to-par: "-3.0" → "-3", "E" stays "E"
            _raw_total = player.get("total", "E")
            try:
                _tot_num = int(float(_raw_total))
                total = "E" if _tot_num == 0 else (f"+{_tot_num}" if _tot_num > 0 else str(_tot_num))
            except (ValueError, TypeError):
                _tot_num = 0
                total = str(_raw_total)

            # Current round score (bold) + previous rounds smaller
            _cur_r   = player.get(f"R{current_round}")
            _cur_str = f"{int(float(_cur_r))}" if pd.notna(_cur_r) else "—"
            _prev_parts = []
            for _pr in range(1, current_round):
                _v = player.get(f"R{_pr}")
                if pd.notna(_v):
                    _prev_parts.append(f"R{_pr}: {int(float(_v))}")
            _prev_str = " · ".join(_prev_parts)

            # Score color: negative = green, positive = red, even = white
            _score_color = "#2ecc71" if _tot_num < 0 else ("#e74c3c" if _tot_num > 0 else "#fff")

            # Movement arrow
            change = player.get("position_change", 0)
            if pd.notna(change) and change != 0:
                _mv_html = f"<span style='color:{'#2ecc71' if change > 0 else '#e74c3c'};font-size:0.8em'>{'↑' if change > 0 else '↓'}{abs(int(change))}</span>"
            else:
                _mv_html = ""

            st.markdown(f"""
<div style="background:#1a1a2e;border-radius:10px;padding:14px 16px;
            border:2px solid {_pos_colors[i]};margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <span style="color:{_pos_colors[i]};font-size:0.75em;font-weight:700;letter-spacing:1px">{_pos_labels[i].upper()}</span>
    {_mv_html}
  </div>
  <div style="font-weight:700;color:#fff;font-size:1.05em;margin-bottom:2px">{name}</div>
  <div style="color:#666;font-size:0.75em;margin-bottom:10px">{country}</div>
  <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">
    <span style="color:{_score_color};font-size:2em;font-weight:700;line-height:1">{total}</span>
    <span style="color:#888;font-size:0.8em">Thru {thru}</span>
  </div>
  <div style="border-top:1px solid #2a2a4a;padding-top:8px;display:flex;justify-content:space-between;align-items:center">
    <span style="color:#666;font-size:0.72em">{_prev_str}</span>
    <span style="color:#aaa;font-size:0.8em;font-weight:600">Rd: {_cur_str}</span>
  </div>
  {"<div style='color:#4CAF50;font-size:0.8em;font-weight:600;margin-top:6px'>" + odds + "</div>" if odds else ""}
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Leaderboard table with styling
    display_df = df.head(50).copy()

    # ── Round filter ─────────────────────────────────────────────────────────
    # Figure out which rounds actually have data (column exists and >50% filled)
    _rounds_with_data = []
    for _rn in [1, 2, 3, 4]:
        _col = f"R{_rn}"
        if _col in df.columns and df[_col].notna().sum() / max(len(df), 1) > 0.1:
            _rounds_with_data.append(_rn)

    # Default to current round; fall back to "All" if no round data yet
    _default_round = current_round if _rounds_with_data else None
    _round_options = ["All"] + [f"R{r}" for r in _rounds_with_data]
    _default_idx   = _round_options.index(f"R{_default_round}") if _default_round and f"R{_default_round}" in _round_options else 0

    _round_filter = st.segmented_control(
        "Round", _round_options,
        default=_round_options[_default_idx],
        key="lb_round_filter",
    )

    # Build column list based on selection
    if _round_filter and _round_filter != "All":
        # Single round: show that round's score as "Score", hide other rounds
        _rnum = int(_round_filter[1])
        cols_to_show = ["position", "player_name", f"R{_rnum}", "total", "thru"]
        if "odds_to_win" in display_df.columns:
            cols_to_show.append("odds_to_win")
        display_df = display_df[[c for c in cols_to_show if c in display_df.columns]]
        # Add move column before rename
        if "position_change" in df.columns:
            def format_change(row):
                change = row.get("position_change", 0)
                if pd.isna(change) or change == 0: return ""
                return f"↑{abs(int(change))}" if change > 0 else f"↓{abs(int(change))}"
            display_df["Move"] = df.head(50).apply(format_change, axis=1)
        display_df = display_df.rename(columns={
            "position": "Pos", "player_name": "Player",
            f"R{_rnum}": "Score", "total": "Total", "thru": "Thru",
            "odds_to_win": "Odds", "Move": "Move",
        })
    else:
        # All rounds
        cols_to_show = ["position", "player_name", "total", "thru", "R1", "R2", "R3", "R4"]
        if "odds_to_win" in display_df.columns:
            cols_to_show.append("odds_to_win")
        display_df = display_df[[c for c in cols_to_show if c in display_df.columns]]
        if "position_change" in df.columns:
            def format_change(row):
                change = row.get("position_change", 0)
                if pd.isna(change) or change == 0: return ""
                return f"↑{abs(int(change))}" if change > 0 else f"↓{abs(int(change))}"
            display_df["Move"] = df.head(50).apply(format_change, axis=1)
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]

    # Convert numeric display columns to whole-number strings
    _int_cols = [c for c in display_df.columns if c in ("Score", "Total", "R1", "R2", "R3", "R4", "Odds", "Odds To Win", "Thru")]
    for _ic in _int_cols:
        def _fmt_int(v, _col=_ic):
            s = str(v).strip()
            if s in ("", "nan", "E"): return s if s == "E" else ""
            try: return str(int(float(s)))
            except (ValueError, TypeError): return s
        display_df[_ic] = display_df[_ic].apply(_fmt_int)

    # Color-code score/total columns: under par = green, over par = red, E = default
    def _color_score(val):
        try:
            n = 0 if str(val).strip() == "E" else int(float(val))
        except (ValueError, TypeError):
            return ""
        if n < 0:   return "color:#2ecc71;font-weight:600"
        elif n > 0: return "color:#e74c3c;font-weight:600"
        return "color:#aaa"

    _score_style_cols = [c for c in display_df.columns if c in ("Score", "Total", "R1", "R2", "R3", "R4")]
    try:
        _styled = display_df.style.map(_color_score, subset=_score_style_cols)
    except Exception:
        _styled = display_df

    # ── My Picks summary + row highlighting ──────────────────────────────────
    # Helper: fuzzy last-name match between a pick string and a leaderboard name
    def _is_my_pick(lb_name: str, picks: list) -> bool:
        lb_lower = str(lb_name).lower()
        for p in picks:
            last = p.strip().split()[-1].lower()
            if last in lb_lower or lb_lower in p.strip().lower():
                return True
        return False

    if my_picks:
        # Build a compact "Your picks: Name Pos (Score) · ..." line from full df
        _pick_parts = []
        for _p in my_picks:
            _last = _p.strip().split()[-1].lower()
            _pmatch = df[df["player_name"].str.lower().str.contains(_last, na=False)]
            if not _pmatch.empty:
                _pr = _pmatch.iloc[0]
                _ptotal = str(_pr.get("total", "?"))
                _ppos   = str(_pr.get("position", "?"))
                _pick_parts.append(
                    f"<span style='color:#00c44f;font-weight:700;'>{_p.split()[0]} {_p.split()[-1]}</span>"
                    f"<span style='color:#dde6f5;'> {_ppos} ({_ptotal})</span>"
                )
            else:
                _pick_parts.append(f"<span style='color:#4a6080;'>{_p} (not found)</span>")
        st.markdown(
            "<div style='background:#0b1f0b;border:1px solid #1a4a1a;border-radius:8px;"
            "padding:8px 14px;margin-bottom:10px;font-size:13px;'>"
            "<span style='color:#4a6080;font-size:11px;font-weight:600;letter-spacing:.5px;"
            "margin-right:10px;'>YOUR PICKS</span>"
            + " &nbsp;·&nbsp; ".join(_pick_parts)
            + "</div>",
            unsafe_allow_html=True,
        )

        # Highlight pick rows in the styled dataframe with a green tint
        def _highlight_picks_row(row):
            player_col = "Player" if "Player" in row.index else "Player Name"
            if _is_my_pick(str(row.get(player_col, "")), my_picks):
                return [
                    "background-color:#0b2a0b;font-weight:700;border-left:3px solid #00c44f"
                ] * len(row)
            return [""] * len(row)

        try:
            _styled = _styled.apply(_highlight_picks_row, axis=1)
        except Exception:
            pass

    st.caption("Highlighted rows = your picks · Click a row to view scorecard")
    _lb_event = st.dataframe(
        _styled,
        hide_index=True,
        use_container_width=True,
        height=600,
        on_select="rerun",
        selection_mode="single-row",
    )
    # Store selected player name in session_state
    if _lb_event.selection.rows:
        _sel_idx  = _lb_event.selection.rows[0]
        _sel_row  = display_df.iloc[_sel_idx]
        _sel_name = _sel_row.get("Player Name") or _sel_row.get("Player", "")
        if _sel_name:
            st.session_state["live_selected_player"] = str(_sel_name)
    elif "live_selected_player" not in st.session_state:
        st.session_state["live_selected_player"] = None

    # ── Player Scorecard — appears directly below table when row is clicked ──
    _selected_sc_player = st.session_state.get("live_selected_player")
    if _selected_sc_player:
        _sc_lb_row = df[df["player_name"] == _selected_sc_player]
        if not _sc_lb_row.empty:
            _sc_r = _sc_lb_row.iloc[0]
            st.markdown("---")
            st.markdown(f"#### {_selected_sc_player}")

            # Summary metrics — round to whole numbers
            _sc_pos  = _sc_r.get("position", "—")
            _sc_odds = _sc_r.get("odds_to_win", "")
            _thru_raw = _sc_r.get("thru", "—")
            try:
                _sc_thru = str(int(float(_thru_raw)))
            except (ValueError, TypeError):
                _sc_thru = str(_thru_raw)
            try:
                _sc_tot_num = int(float(_sc_r.get("total", 0)))
                _sc_total   = "E" if _sc_tot_num == 0 else (f"+{_sc_tot_num}" if _sc_tot_num > 0 else str(_sc_tot_num))
            except (ValueError, TypeError):
                _sc_total = str(_sc_r.get("total", "E"))
            _sc_r1 = int(float(_sc_r["R1"])) if pd.notna(_sc_r.get("R1")) else "—"
            _sc_r2 = int(float(_sc_r["R2"])) if pd.notna(_sc_r.get("R2")) else "—"
            _sc_r3 = int(float(_sc_r["R3"])) if pd.notna(_sc_r.get("R3")) else "—"
            _sc_r4 = int(float(_sc_r["R4"])) if pd.notna(_sc_r.get("R4")) else "—"

            try:
                _sc_odds_disp = str(int(float(_sc_odds))) if _sc_odds else ""
            except (ValueError, TypeError):
                _sc_odds_disp = str(_sc_odds)
            _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
            _mc1.metric("Position", _sc_pos)
            _mc2.metric("Total",    _sc_total)
            _mc3.metric("Thru",     _sc_thru)
            _mc4.metric("Odds",     f"+{_sc_odds_disp}" if _sc_odds_disp else "—")
            _mc5.metric("Rounds",   f"{_sc_r1} · {_sc_r2} · {_sc_r3} · {_sc_r4}")

            # Load hole scores using tournament_id from meta
            _sc_tid = meta.get("tournament_id", "")
            # Determine if player is mid-round (thru < 18 and not finished)
            _thru_val = _sc_r.get("thru", "")
            try:
                _mid_round = 0 < int(float(_thru_val)) < 18
            except (ValueError, TypeError):
                _mid_round = False

            if _sc_tid:
                _hs3_path = LIVE_DIR / f"hole_scores_{_sc_tid.lower()}.csv"
                if _hs3_path.exists():
                    _hs3_df = pd.read_csv(_hs3_path)
                    try:
                        _pid3 = str(int(float(_sc_r.get("player_id", -1))))
                    except (ValueError, TypeError):
                        _pid3 = str(_sc_r.get("player_id", ""))
                    _hs3_player = _hs3_df[_hs3_df["player_id"].astype(str) == _pid3]

                    if not _hs3_player.empty:
                        _rounds3 = sorted(_hs3_player["round"].dropna().unique().tolist()) if "round" in _hs3_player.columns else [1]
                        def _round_tab_label(r):
                            label = f"Round {int(r)}"
                            if _mid_round and int(r) == current_round:
                                label += " (Live)"
                            return label
                        _rtabs3 = st.tabs([_round_tab_label(r) for r in _rounds3])

                        def _hole_cell3(stroke, rel):
                            if stroke is None:
                                return "<td style='padding:4px 6px;text-align:center;color:#555'>-</td>"
                            try:
                                s = int(stroke); r = int(rel) if rel is not None else 0
                            except (TypeError, ValueError):
                                return f"<td style='padding:4px 6px;text-align:center'>{stroke}</td>"
                            if r <= -2:
                                inner = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                                         f"width:22px;height:22px;border-radius:50%;border:2px solid #FFD700;"
                                         f"background:#7d6100;color:#FFD700;font-weight:700;font-size:12px'>{s}</span>")
                                return f"<td style='padding:3px 5px;text-align:center'>{inner}</td>"
                            elif r == -1:
                                inner = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                                         f"width:22px;height:22px;border-radius:50%;"
                                         f"background:#c0392b;color:#fff;font-weight:700;font-size:12px'>{s}</span>")
                                return f"<td style='padding:3px 5px;text-align:center'>{inner}</td>"
                            elif r == 0:
                                return f"<td style='padding:4px 6px;text-align:center;color:#ccc;font-size:13px'>{s}</td>"
                            elif r == 1:
                                inner = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                                         f"width:22px;height:22px;border:2px solid #4cb8ff;"
                                         f"background:transparent;color:#4cb8ff;font-size:12px'>{s}</span>")
                                return f"<td style='padding:3px 5px;text-align:center'>{inner}</td>"
                            else:
                                inner = (f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                                         f"width:22px;height:22px;background:#1a3a5c;color:#aaa;"
                                         f"font-weight:700;font-size:12px'>{s}</span>")
                                return f"<td style='padding:3px 5px;text-align:center'>{inner}</td>"

                        def _safe_sum3(vals):
                            t = 0
                            for v in vals:
                                try: t += int(v)
                                except (TypeError, ValueError): pass
                            return t

                        def _topar_str3(n):
                            return "E" if n == 0 else (f"+{n}" if n > 0 else str(n))

                        def _running_cell(val, border_left=False):
                            bl = "border-left:1px solid #333;" if border_left else ""
                            if val is None or str(val).strip() in ("", "nan"):
                                return f"<td style='padding:4px 6px;{bl}text-align:center;color:#444;font-size:11px'>-</td>"
                            v = str(val).strip()
                            try: n = 0 if v == "E" else int(v)
                            except ValueError: n = 0
                            color = "#2ecc71" if n < 0 else ("#e74c3c" if n > 0 else "#888")
                            return f"<td style='padding:4px 6px;{bl}text-align:center;color:{color};font-size:11px;font-weight:600'>{v}</td>"

                        for _rtab3, _rnum3 in zip(_rtabs3, _rounds3):
                            with _rtab3:
                                _rd3 = _hs3_player[_hs3_player["round"] == _rnum3].copy()
                                if _rd3.empty:
                                    continue
                                _row3     = _rd3.iloc[0]
                                _strokes3 = [_row3.get(f"h{i}")         for i in range(1, 19)]
                                _rels3    = [_row3.get(f"h{i}_rel")     for i in range(1, 19)]
                                _pars3    = [_row3.get(f"h{i}_par")     for i in range(1, 19)]
                                _running3 = [_row3.get(f"h{i}_running") for i in range(1, 19)]

                                if all(p is None for p in _pars3):
                                    _pars3 = []
                                    for _s3, _r3 in zip(_strokes3, _rels3):
                                        try: _pars3.append(int(_s3) - int(_r3))
                                        except (TypeError, ValueError): _pars3.append(None)

                                _f9s = _safe_sum3(_strokes3[:9]);  _b9s = _safe_sum3(_strokes3[9:]);  _tots = _f9s + _b9s
                                _f9p = _safe_sum3(_pars3[:9]);     _b9p = _safe_sum3(_pars3[9:]);     _totp = _f9p + _b9p
                                _f9r = _f9s - _f9p;                _b9r = _b9s - _b9p;                _totr = _tots - _totp

                                _td_hdr  = "style='padding:4px 8px;text-align:center;color:#888;font-size:11px;font-weight:600;border-bottom:1px solid #333'"
                                _td_par  = "style='padding:4px 8px;text-align:center;color:#666;font-size:12px;border-bottom:1px solid #222'"
                                _td_sum  = "style='padding:4px 8px;text-align:center;color:#fff;font-size:13px;font-weight:700;border-left:1px solid #333'"
                                _td_sump = "style='padding:4px 8px;text-align:center;color:#666;font-size:12px;border-left:1px solid #333;border-bottom:1px solid #222'"

                                _hdr_cells  = "".join(f"<th {_td_hdr}>{i}</th>" for i in range(1, 10))
                                _hdr_cells += f"<th {_td_hdr} style='border-left:1px solid #333'>OUT</th>"
                                _hdr_cells += "".join(f"<th {_td_hdr}>{i}</th>" for i in range(10, 19))
                                _hdr_cells += f"<th {_td_hdr} style='border-left:1px solid #333'>IN</th>"
                                _hdr_cells += f"<th {_td_hdr} style='border-left:1px solid #333'>TOT</th>"

                                _par_cells  = "".join(f"<td {_td_par}>{p if p else '-'}</td>" for p in _pars3[:9])
                                _par_cells += f"<td {_td_sump}>{_f9p}</td>"
                                _par_cells += "".join(f"<td {_td_par}>{p if p else '-'}</td>" for p in _pars3[9:])
                                _par_cells += f"<td {_td_sump}>{_b9p}</td>"
                                _par_cells += f"<td {_td_sump}>{_totp}</td>"

                                _score_cells  = "".join(_hole_cell3(_strokes3[i], _rels3[i]) for i in range(9))
                                _score_cells += f"<td {_td_sum}>{_f9s}<span style='font-size:10px;color:#888;margin-left:3px'>({_topar_str3(_f9r)})</span></td>"
                                _score_cells += "".join(_hole_cell3(_strokes3[i], _rels3[i]) for i in range(9, 18))
                                _score_cells += f"<td {_td_sum}>{_b9s}<span style='font-size:10px;color:#888;margin-left:3px'>({_topar_str3(_b9r)})</span></td>"
                                _score_cells += f"<td {_td_sum}>{_tots}<span style='font-size:10px;color:#888;margin-left:3px'>({_topar_str3(_totr)})</span></td>"

                                _out_run = next((r for r in reversed(_running3[:9])  if r is not None and str(r).strip() not in ("","nan")), None)
                                _in_run  = next((r for r in reversed(_running3[9:])  if r is not None and str(r).strip() not in ("","nan")), None)
                                _run_cells  = "".join(_running_cell(v) for v in _running3[:9])
                                _run_cells += _running_cell(_out_run, border_left=True)
                                _run_cells += "".join(_running_cell(v) for v in _running3[9:])
                                _run_cells += _running_cell(_in_run,  border_left=True)
                                _run_cells += _running_cell(_in_run,  border_left=True)

                                _last_name = _selected_sc_player.split()[-1]
                                st.markdown(f"""
<div style='overflow-x:auto'>
<table style='border-collapse:collapse;background:#111;width:100%;font-family:monospace'>
  <thead><tr>
    <th {_td_hdr} style='text-align:left;min-width:52px'>HOLE</th>{_hdr_cells}
  </tr></thead>
  <tbody>
    <tr><td style='padding:4px 8px;color:#666;font-size:11px;font-weight:600'>PAR</td>{_par_cells}</tr>
    <tr><td style='padding:4px 8px;color:#eee;font-size:12px;font-weight:600'>{_last_name}</td>{_score_cells}</tr>
    <tr><td style='padding:4px 8px;color:#555;font-size:10px;font-weight:600'>SCORE</td>{_run_cells}</tr>
  </tbody>
</table></div>
<div style='margin-top:8px;display:flex;gap:16px;font-size:11px;color:#888'>
  <span><span style='display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:#7d6100;color:#FFD700;font-size:9px;border:1.5px solid #FFD700'>&#x25CF;</span> Eagle</span>
  <span><span style='display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:#c0392b;color:#fff;font-size:9px'>&#x25CF;</span> Birdie</span>
  <span style='color:#aaa'>&#8212; Par</span>
  <span><span style='display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border:1.5px solid #4cb8ff;color:#4cb8ff;font-size:9px'>&#x25CF;</span> Bogey</span>
  <span><span style='display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;background:#1a3a5c;color:#aaa;font-size:9px'>&#x25CF;</span> Double+</span>
</div>""", unsafe_allow_html=True)
                    else:
                        if _mid_round:
                            st.caption(f"Round {current_round} is in progress (thru {_sc_thru}) — hole scores will appear after next refresh.")
                        else:
                            st.caption("Hole scores not yet available for this player.")
                else:
                    if _mid_round:
                        st.caption(f"Round {current_round} is in progress (thru {_sc_thru}) — hole scores load automatically during live refresh.")
                    else:
                        st.caption("Hole score data not yet fetched. Loads automatically during live refresh.")


def compare_live_vs_predictions(live_df: pd.DataFrame, tournament_id: str = None) -> pd.DataFrame:
    """Compare live leaderboard positions with pre-tournament model predictions."""
    # Find matching predictions file
    predictions_df = None
    if tournament_id:
        patterns = [
            OUTPUTS_DIR / f"{tournament_id}_predictions.csv",
            OUTPUTS_DIR / f"{tournament_id.lower()}_predictions.csv",
        ]
        for p in patterns:
            if p.exists():
                predictions_df = pd.read_csv(p)
                break

    # If not found, try most recent predictions
    if predictions_df is None:
        pred_files = get_prediction_files()
        if pred_files:
            predictions_df = pd.read_csv(pred_files[0])

    if predictions_df is None or predictions_df.empty:
        return pd.DataFrame()

    # Normalize names for matching
    live_df = ensure_player_name_column(live_df)
    predictions_df = ensure_player_name_column(predictions_df)

    live_df["name_key"] = live_df["player_name"].apply(_name_key)
    predictions_df["name_key"] = predictions_df["player_name"].apply(_name_key)
    live_df = live_df[live_df["name_key"] != ""].copy()
    predictions_df = predictions_df[predictions_df["name_key"] != ""].copy()

    if live_df.empty or predictions_df.empty:
        return pd.DataFrame()

    for col in ["expected_value", "win_prob", "top5_prob", "top10_prob"]:
        if col not in predictions_df.columns:
            predictions_df[col] = np.nan

    # Add model rank
    rank_col = "expected_value"
    if rank_col not in predictions_df.columns or predictions_df[rank_col].isna().all():
        rank_col = "win_prob" if "win_prob" in predictions_df.columns else None
    if rank_col:
        predictions_df = predictions_df.sort_values(rank_col, ascending=False, na_position="last")
    predictions_df["model_rank"] = range(1, len(predictions_df) + 1)

    # Parse live position to numeric
    def parse_pos(pos):
        if pd.isna(pos):
            return 999
        pos_str = str(pos).upper().replace("T", "")
        try:
            return int(pos_str)
        except ValueError:
            return 999

    if "position" in live_df.columns:
        live_df["live_pos_numeric"] = live_df["position"].apply(parse_pos)
    else:
        live_df["live_pos_numeric"] = 999

    # Merge — include live probability columns when available
    extra_live_cols = [c for c in [
        "live_win_prob", "live_win_prob_change", "live_top10_prob",
        "live_projected_score", "projected_score_vs_field", "rounds_complete"
    ] if c in predictions_df.columns]
    _merge_cols = ["name_key", "model_rank", "expected_value", "win_prob", "top5_prob", "top10_prob"] + extra_live_cols

    merged = live_df.merge(
        predictions_df[_merge_cols],
        on="name_key",
        how="left"
    )

    # Calculate performance vs prediction
    merged["rank_diff"] = merged["model_rank"] - merged["live_pos_numeric"]
    merged["outperforming"] = merged["rank_diff"] > 0  # Positive = doing better than predicted

    # Sort by live position
    merged = merged.sort_values("live_pos_numeric")

    return merged



def render_live_vs_predictions(live_df: pd.DataFrame, meta: dict):
    """Render comparison of live results vs model predictions."""
    tournament_id = meta.get("tournament_id", "")
    comparison = compare_live_vs_predictions(live_df, tournament_id)

    if comparison.empty:
        st.warning("No predictions found to compare")
        return

    st.markdown("### Model vs Reality")

    # Summary stats
    with_predictions = comparison[comparison["model_rank"].notna()]

    if with_predictions.empty:
        st.warning("No matching players found between predictions and leaderboard")
        return

    outperforming = with_predictions[with_predictions["rank_diff"] > 5]
    underperforming = with_predictions[with_predictions["rank_diff"] < -5]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Matched Players", len(with_predictions))
    with col2:
        st.metric("Outperforming Model", len(outperforming), help="Finishing better than predicted")
    with col3:
        st.metric("Underperforming", len(underperforming), help="Finishing worse than predicted")

    st.markdown("---")

    # ── Win Probability Movers (only when Monte Carlo data is available) ──
    _has_live_prob = "live_win_prob" in with_predictions.columns and with_predictions["live_win_prob"].notna().any()
    if _has_live_prob and "live_win_prob_change" in with_predictions.columns:
        st.markdown("#### Win Probability Movers")
        _prob_df = with_predictions[with_predictions["live_win_prob_change"].notna()].copy()

        _gain_col, _lose_col = st.columns(2)
        with _gain_col:
            st.markdown("**Biggest Gainers**")
            _gainers = _prob_df.nlargest(8, "live_win_prob_change")
            for _, _row in _gainers.iterrows():
                _pre  = float(_row.get("win_prob", 0) or 0) * 100
                _live = float(_row.get("live_win_prob", 0) or 0) * 100
                _chg  = float(_row.get("live_win_prob_change", 0) or 0) * 100
                if _chg < 0.1:
                    continue
                st.markdown(f"""
                <div style="background:#00c44f18; border-left:3px solid #00c44f; padding:7px 10px; border-radius:5px; margin:3px 0;">
                    <strong>{_row['player_name']}</strong> &nbsp;
                    <span style="color:#888; font-size:0.85em;">Pos: {_row.get('position','—')}</span><br>
                    <span style="color:#888;">Pre: {_pre:.1f}%</span>
                    <span style="color:#666;"> → </span>
                    <span style="color:#00c44f;">Live: {_live:.1f}%</span>
                    &nbsp;<span style="color:#00c44f; font-weight:700;">+{_chg:.1f}pp</span>
                </div>""", unsafe_allow_html=True)

        with _lose_col:
            st.markdown("**Biggest Losers**")
            _losers = _prob_df.nsmallest(8, "live_win_prob_change")
            for _, _row in _losers.iterrows():
                _pre  = float(_row.get("win_prob", 0) or 0) * 100
                _live = float(_row.get("live_win_prob", 0) or 0) * 100
                _chg  = float(_row.get("live_win_prob_change", 0) or 0) * 100
                if _chg > -0.1:
                    continue
                st.markdown(f"""
                <div style="background:#ff6b6b18; border-left:3px solid #ff6b6b; padding:7px 10px; border-radius:5px; margin:3px 0;">
                    <strong>{_row['player_name']}</strong> &nbsp;
                    <span style="color:#888; font-size:0.85em;">Pos: {_row.get('position','—')}</span><br>
                    <span style="color:#888;">Pre: {_pre:.1f}%</span>
                    <span style="color:#666;"> → </span>
                    <span style="color:#ff6b6b;">Live: {_live:.1f}%</span>
                    &nbsp;<span style="color:#ff6b6b; font-weight:700;">{_chg:.1f}pp</span>
                </div>""", unsafe_allow_html=True)

        st.markdown("---")

    # Top overperformers (position-based)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Exceeding Expectations")
        top_outperform = with_predictions.nlargest(10, "rank_diff")
        for _, row in top_outperform.iterrows():
            diff = int(row["rank_diff"])
            if diff > 0:
                st.markdown(f"""
                <div style="background: #00C85322; padding: 8px; border-radius: 6px; margin: 4px 0;">
                    <strong>{row['player_name']}</strong><br>
                    <span style="color: #00C853;">Live: {row['position']}</span> vs
                    <span style="color: #888;">Predicted: #{int(row['model_rank'])}</span>
                    <span style="color: #00C853; font-weight: bold;"> (+{diff} spots)</span>
                </div>
                """, unsafe_allow_html=True)

    with col2:
        st.markdown("#### Underperforming")
        top_underperform = with_predictions.nsmallest(10, "rank_diff")
        for _, row in top_underperform.iterrows():
            diff = int(row["rank_diff"])
            if diff < 0:
                st.markdown(f"""
                <div style="background: #FF525222; padding: 8px; border-radius: 6px; margin: 4px 0;">
                    <strong>{row['player_name']}</strong><br>
                    <span style="color: #FF5252;">Live: {row['position']}</span> vs
                    <span style="color: #888;">Predicted: #{int(row['model_rank'])}</span>
                    <span style="color: #FF5252; font-weight: bold;"> ({diff} spots)</span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # Full comparison table
    st.markdown("#### Full Comparison")

    if _has_live_prob and "live_win_prob" in with_predictions.columns:
        # Extended table with live probability columns
        _disp_cols = ["position", "player_name", "total", "model_rank", "win_prob", "live_win_prob", "live_win_prob_change"]
        display_df = with_predictions[[c for c in _disp_cols if c in with_predictions.columns]].copy()
        display_df["model_rank"] = display_df["model_rank"].fillna(999).astype(int)
        display_df["win_prob"]   = display_df["win_prob"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")
        display_df["live_win_prob"] = display_df["live_win_prob"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")
        def _fmt_chg(x):
            if pd.isna(x):
                return "-"
            pp = x * 100
            return f"+{pp:.1f}pp" if pp >= 0 else f"{pp:.1f}pp"
        display_df["live_win_prob_change"] = display_df["live_win_prob_change"].apply(_fmt_chg)
        display_df.columns = ["Live Pos", "Player", "Score", "Model Rank", "Pre Win%", "Live Win%", "Change"]
    else:
        display_df = with_predictions[[
            "position", "player_name", "total", "model_rank", "rank_diff", "expected_value", "win_prob"
        ]].copy()
        display_df["model_rank"] = display_df["model_rank"].fillna(999).astype(int)
        display_df["rank_diff"] = display_df["rank_diff"].fillna(0).astype(int)
        display_df["expected_value"] = display_df["expected_value"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "-")
        display_df["win_prob"] = display_df["win_prob"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")
        display_df.columns = ["Live Pos", "Player", "Score", "Model Rank", "Diff", "Pre-Tourn EV", "Win %"]

    st.dataframe(display_df.head(30), hide_index=True, use_container_width=True)

    st.markdown("---")

    # ── Predicted vs Actual scatter ───────────────────────────────────────────
    st.markdown("#### 📍 Predicted Rank vs Actual Position")
    st.caption("Points above the diagonal = outperforming predictions. Below = underperforming.")

    _scatter_df = with_predictions.copy()
    _scatter_df["model_rank_num"] = pd.to_numeric(_scatter_df["model_rank"], errors="coerce")
    _scatter_df["position_num"]   = pd.to_numeric(
        _scatter_df["position"].astype(str).str.replace("T", "", regex=False), errors="coerce"
    )
    _scatter_df = _scatter_df.dropna(subset=["model_rank_num", "position_num"])

    if not _scatter_df.empty:
        _max_rank = max(_scatter_df["model_rank_num"].max(), _scatter_df["position_num"].max()) + 5
        _scat_fig = px.scatter(
            _scatter_df,
            x="model_rank_num",
            y="position_num",
            text="player_name",
            color="rank_diff",
            color_continuous_scale=["#e74c3c", "#888", "#00c44f"],
            color_continuous_midpoint=0,
            labels={"model_rank_num": "Predicted Rank (pre-tournament)",
                    "position_num":   "Actual Current Position",
                    "rank_diff":      "Spots gained"},
            hover_data={"player_name": True, "rank_diff": True},
        )
        # Diagonal y = x reference line
        _scat_fig.add_shape(type="line", x0=1, y0=1, x1=_max_rank, y1=_max_rank,
                            line=dict(color="#4a6080", dash="dot", width=1))
        _scat_fig.update_traces(textposition="top center", textfont_size=9)
        _scat_fig.update_yaxes(autorange="reversed")
        _scat_fig.update_layout(
            height=400,
            margin=dict(t=10, b=40, l=50, r=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#dde6f5",
            coloraxis_showscale=False,
            xaxis=dict(gridcolor="#1c2f4a"),
            yaxis=dict(gridcolor="#1c2f4a", title="Actual Position (lower = better)"),
        )
        st.plotly_chart(_scat_fig, use_container_width=True)

    # ── Model's top-10 picks and how they're doing ───────────────────────────
    st.markdown("#### 🎯 Model's Top-10 Pre-Tournament Picks — Live Status")
    _top10_picks = with_predictions.nsmallest(10, "model_rank")[
        ["player_name", "model_rank", "position", "total", "win_prob", "rank_diff"]
    ].copy()
    _top10_picks["win_prob"]   = (_top10_picks["win_prob"] * 100).round(1).astype(str) + "%"
    _top10_picks["rank_diff"]  = _top10_picks["rank_diff"].apply(
        lambda x: f"+{int(x)}" if x > 0 else str(int(x)) if pd.notna(x) else "—"
    )
    _top10_picks["model_rank"] = _top10_picks["model_rank"].fillna(0).astype(int)
    _top10_picks = _top10_picks.rename(columns={
        "player_name": "Player",
        "model_rank":  "Model Rank",
        "position":    "Live Pos",
        "total":       "Score",
        "win_prob":    "Win%",
        "rank_diff":   "Spots Gained",
    })
    st.dataframe(_top10_picks, hide_index=True, use_container_width=True)




def render_fantasy_lineup_tracker(live_df: pd.DataFrame):
    """Track fantasy lineup performance in real-time."""
    live_df = ensure_player_name_column(live_df)
    live_df["name_key"] = live_df["player_name"].apply(_name_key)

    usage_data = load_usage_data()
    picks = usage_data.get("picks", {})
    lineups = usage_data.get("weekly_lineups", {})

    if not picks and not lineups:
        st.info("No fantasy lineup data found. Add your picks to track them live.")
        return

    st.markdown("### Your Fantasy Lineup - Live Tracking")

    # Find current week's lineup
    current_lineup = None
    for week_key in sorted(lineups.keys(), key=lambda x: int(x.split("_")[1]), reverse=True):
        lineup = lineups[week_key]
        current_lineup = lineup
        break

    if current_lineup:
        st.markdown(f"**Week {current_lineup.get('week', '?')}:** {current_lineup.get('tournament', 'Tournament')}")

        lineup_players = current_lineup.get("lineup", [])
        bench_players = current_lineup.get("bench", [])

        if lineup_players:
            st.markdown("#### Active Lineup")

            total_score = 0
            lineup_data = []

            for player in lineup_players:
                player_key = _name_key(player)
                match = live_df[live_df["name_key"] == player_key]

                if not match.empty:
                    row = match.iloc[0]
                    pos = row.get("position", "")
                    total = row.get("total", "")
                    thru = row.get("thru", "")

                    # Calculate fantasy points (simplified)
                    pos_numeric = int(str(pos).replace("T", "")) if pos and str(pos).replace("T", "").isdigit() else 999
                    if pos_numeric == 1:
                        pts = 30
                    elif pos_numeric <= 5:
                        pts = 20
                    elif pos_numeric <= 10:
                        pts = 15
                    elif pos_numeric <= 20:
                        pts = 10
                    elif pos_numeric <= 40:
                        pts = 5
                    else:
                        pts = 0

                    total_score += pts
                    status = "🟢" if pos_numeric <= 20 else "🟡" if pos_numeric <= 40 else "🔴"

                    lineup_data.append({
                        "Status": status,
                        "Player": player,
                        "Position": pos,
                        "Score": total,
                        "Thru": thru,
                        "Est Points": pts
                    })
                else:
                    lineup_data.append({
                        "Status": "⚪",
                        "Player": player,
                        "Position": "-",
                        "Score": "-",
                        "Thru": "-",
                        "Est Points": 0
                    })

            st.dataframe(pd.DataFrame(lineup_data), hide_index=True, use_container_width=True)
            st.metric("Estimated Total Points", total_score)

        if bench_players:
            st.markdown("#### Bench")
            bench_data = []
            for player in bench_players:
                player_key = _name_key(player)
                match = live_df[live_df["name_key"] == player_key]
                if not match.empty:
                    row = match.iloc[0]
                    bench_data.append({
                        "Player": player,
                        "Position": row["position"],
                        "Score": row["total"]
                    })
                else:
                    bench_data.append({"Player": player, "Position": "-", "Score": "-"})

            st.dataframe(pd.DataFrame(bench_data), hide_index=True, use_container_width=True)
    else:
        # Show all tracked players
        st.markdown("#### All Tracked Players")

        tracked_data = []
        for player_name in picks.keys():
            player_key = _name_key(player_name)
            match = live_df[live_df["name_key"] == player_key]

            if not match.empty:
                row = match.iloc[0]
                uses = picks[player_name].get("times_used", 0)
                tracked_data.append({
                    "Player": player_name,
                    "Position": row["position"],
                    "Score": row["total"],
                    "Uses": f"{uses}/3"
                })

        if tracked_data:
            st.dataframe(pd.DataFrame(tracked_data), hide_index=True, use_container_width=True)


def load_performance_history() -> dict:
    """Load performance tracking history."""
    history_path = PERFORMANCE_DIR / "performance_history.json"
    if not history_path.exists():
        return {"tournaments": []}
    with open(history_path) as f:
        return json.load(f)


def render_performance_dashboard():
    """Render the performance tracking dashboard."""
    history = load_performance_history()
    tournaments = history.get("tournaments", [])

    if not tournaments:
        st.info("No performance data recorded yet. Complete a tournament and record results to see stats.")
        st.code("python3 scripts/analysis/track_performance.py --record R2026005 --name 'Tournament Name'")
        return

    # Aggregate metrics
    st.markdown("### Overall Performance")

    winner_correct = sum(1 for t in tournaments if t.get("metrics", {}).get("winner_correct"))
    top5_total = sum(t.get("metrics", {}).get("top5_hits", 0) for t in tournaments)
    top10_total = sum(t.get("metrics", {}).get("top10_hits", 0) for t in tournaments)
    top20_total = sum(t.get("metrics", {}).get("top20_hits", 0) for t in tournaments)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Tournaments", len(tournaments))
    with col2:
        pct = (winner_correct / len(tournaments) * 100) if tournaments else 0
        st.metric("Winner Correct", f"{winner_correct}/{len(tournaments)}", f"{pct:.0f}%")
    with col3:
        pct = (top5_total / (len(tournaments) * 5) * 100) if tournaments else 0
        st.metric("Top-5 Hits", f"{top5_total}/{len(tournaments)*5}", f"{pct:.0f}%")
    with col4:
        pct = (top10_total / (len(tournaments) * 10) * 100) if tournaments else 0
        st.metric("Top-10 Hits", f"{top10_total}/{len(tournaments)*10}", f"{pct:.0f}%")
    with col5:
        pct = (top20_total / (len(tournaments) * 20) * 100) if tournaments else 0
        st.metric("Top-20 Hits", f"{top20_total}/{len(tournaments)*20}", f"{pct:.0f}%")

    st.markdown("---")

    # ROI section
    st.markdown("### ROI Analysis")

    total_profit = 0
    total_bet = 0
    for t in tournaments:
        roi = t.get("roi", {})
        if "top10_finish_strategy" in roi:
            total_profit += roi["top10_finish_strategy"].get("profit", 0)
            total_bet += roi["top10_finish_strategy"].get("total_bet", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Wagered", f"${total_bet:,.0f}")
    with col2:
        st.metric("Total Profit", f"${total_profit:,.0f}")
    with col3:
        roi_pct = (total_profit / total_bet * 100) if total_bet > 0 else 0
        st.metric("Overall ROI", f"{roi_pct:+.1f}%")

    st.markdown("---")

    # Per-tournament breakdown
    st.markdown("### Tournament Breakdown")

    table_data = []
    for t in tournaments:
        metrics = t.get("metrics", {})
        roi = t.get("roi", {}).get("top10_finish_strategy", {})

        table_data.append({
            "Tournament": t.get("tournament_name", t.get("tournament_id", "Unknown"))[:30],
            "Winner?": "Yes" if metrics.get("winner_correct") else "No",
            "Top-5": f"{metrics.get('top5_hits', 0)}/5",
            "Top-10": f"{metrics.get('top10_hits', 0)}/10",
            "Correlation": f"{metrics.get('rank_correlation', 0):.2f}" if metrics.get("rank_correlation") else "-",
            "ROI": f"{roi.get('roi_pct', 0):+.1f}%" if roi else "-",
        })

    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

    # Correlation chart
    correlations = [
        (t.get("tournament_name", "")[:15], t.get("metrics", {}).get("rank_correlation", 0))
        for t in tournaments
        if t.get("metrics", {}).get("rank_correlation") is not None
    ]

    if correlations:
        st.markdown("### Rank Correlation by Tournament")
        corr_df = pd.DataFrame(correlations, columns=["Tournament", "Correlation"])
        fig = px.bar(corr_df, x="Tournament", y="Correlation", title="Prediction Accuracy (higher = better)")
        fig.add_hline(y=0.5, line_dash="dash", line_color="green", annotation_text="Good")
        fig.add_hline(y=0.3, line_dash="dash", line_color="orange", annotation_text="Fair")
        st.plotly_chart(fig, use_container_width=True)


def render_course_fit_analysis():
    """Render enhanced course fit analysis."""
    st.markdown("### Course Fit Analysis")

    # Load predictions if available
    prediction_files = get_prediction_files()
    if not prediction_files:
        st.warning("No prediction files found")
        return

    file_options = {f.stem.replace('_predictions', '').replace('_', ' ').title(): f
                   for f in prediction_files[:10]}
    selected = st.selectbox("Select Tournament:", list(file_options.keys()), key="course_fit_select")
    df = pd.read_csv(file_options[selected])

    # SG Breakdown Analysis
    st.markdown("#### Strokes Gained Breakdown")

    sg_cols = [c for c in df.columns if c.startswith("sg_")]
    if sg_cols:
        # Top 20 players SG breakdown
        top20 = df.nlargest(20, "expected_value").copy()

        sg_data = []
        for _, row in top20.iterrows():
            for sg_col in sg_cols:
                sg_data.append({
                    "Player": row["player_name"][:20],
                    "Category": sg_col.replace("sg_", "").replace("_", " ").title(),
                    "Value": row.get(sg_col, 0)
                })

        if sg_data:
            sg_df = pd.DataFrame(sg_data)
            fig = px.bar(sg_df, x="Player", y="Value", color="Category", barmode="group",
                        title="Strokes Gained Breakdown - Top 20 Players")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    # Course History
    st.markdown("#### Course History")

    if "hist_times_played" in df.columns and "hist_avg_finish" in df.columns:
        with_history = df[df["hist_times_played"] > 0].copy()

        if not with_history.empty:
            # Sort by times played
            with_history = with_history.sort_values("hist_times_played", ascending=False).head(25)

            fig = px.scatter(
                with_history,
                x="hist_times_played",
                y="hist_avg_finish",
                size="expected_value",
                hover_data=["player_name"],
                title="Course Experience vs Average Finish"
            )
            fig.update_yaxes(autorange="reversed")  # Lower finish = better
            st.plotly_chart(fig, use_container_width=True)

            # Table
            history_df = with_history[["player_name", "hist_times_played", "hist_avg_finish", "expected_value"]].copy()
            history_df.columns = ["Player", "Times Played", "Avg Finish", "Expected Value"]
            history_df["Avg Finish"] = history_df["Avg Finish"].round(1)
            history_df["Expected Value"] = history_df["Expected Value"].apply(lambda x: f"${x:,.0f}")
            st.dataframe(history_df, hide_index=True, use_container_width=True)
    else:
        st.info("No course history data in predictions")

    # Player Radar Chart
    st.markdown("#### Player Comparison Radar")

    player_list = df["player_name"].tolist()
    selected_players = st.multiselect("Select players to compare (max 5):", player_list[:50], max_selections=5)

    if selected_players:
        radar_data = []
        categories = ["win_prob", "top5_prob", "top10_prob", "sg_total"]
        cat_labels = ["Win %", "Top-5 %", "Top-10 %", "SG Total"]

        for player in selected_players:
            player_row = df[df["player_name"] == player].iloc[0]
            values = []
            for cat in categories:
                val = player_row.get(cat, 0)
                if "prob" in cat:
                    val = val * 100  # Convert to percentage
                values.append(val)

            for i, (cat, val) in enumerate(zip(cat_labels, values)):
                radar_data.append({
                    "Player": player[:20],
                    "Category": cat,
                    "Value": val
                })

        if radar_data:
            radar_df = pd.DataFrame(radar_data)
            fig = px.line_polar(radar_df, r="Value", theta="Category", color="Player",
                               line_close=True, title="Player Comparison")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# STATS ANALYSIS HELPERS
# ============================================================================

# --- Enhanced UI Components ---

def create_progress_bar(value: float, max_val: float = 100, color: str = "#4CAF50") -> str:
    """
    Create an HTML progress bar.

    Args:
        value: Current value (0-100 scale works best)
        max_val: Maximum value for scaling
        color: Bar color (hex or CSS color name)

    Returns:
        HTML string for the progress bar
    """
    # Normalize to 0-100 percentage
    pct = min(100, max(0, (value / max_val) * 100)) if max_val > 0 else 0

    return (
        f'<div style="background: #e0e0e0; border-radius: 4px; height: 8px; width: 100%; overflow: hidden;">'
        f'<div style="background: {color}; height: 100%; width: {pct}%; border-radius: 4px;"></div>'
        f'</div>'
    )


def create_sg_bar(value: float, label: str) -> str:
    """
    Create a strokes gained bar that shows positive (green) or negative (red).

    SG typically ranges from -2 to +2, with 0 being average.
    """
    # Normalize: -2 to +2 range → 0 to 100 for display
    # 0 SG = 50% (middle), +2 = 100%, -2 = 0%
    normalized = ((value + 2) / 4) * 100
    normalized = min(100, max(0, normalized))

    # Color based on value
    if value >= 0.5:
        color = "#00C853"  # Strong green
    elif value >= 0:
        color = "#4CAF50"  # Light green
    elif value >= -0.5:
        color = "#FF9800"  # Orange
    else:
        color = "#F44336"  # Red

    # Format value with sign
    val_str = f"+{value:.2f}" if value >= 0 else f"{value:.2f}"

    return (
        f'<div style="display: flex; align-items: center; margin: 4px 0;">'
        f'<span style="width: 45px; font-size: 0.85em; color: #666;">{label}</span>'
        f'<div style="flex: 1; background: #e0e0e0; border-radius: 4px; height: 12px; margin: 0 8px; overflow: hidden;">'
        f'<div style="background: {color}; height: 100%; width: {normalized}%; border-radius: 4px;"></div>'
        f'</div>'
        f'<span style="width: 50px; font-size: 0.85em; font-weight: bold; color: {color};">{val_str}</span>'
        f'</div>'
    )


def get_trend_indicator(value: float, thresholds: tuple = (0.3, -0.3)) -> str:
    """
    Return a trend indicator emoji based on value.

    Args:
        value: The metric value
        thresholds: (positive_threshold, negative_threshold)
    """
    pos_thresh, neg_thresh = thresholds
    if value >= pos_thresh:
        return "🔥"  # Hot
    elif value <= neg_thresh:
        return "❄️"  # Cold
    else:
        return "➖"  # Neutral


def get_form_badge(form_trend: float, recent_top10s: int = 0) -> str:
    """
    Generate a form badge based on recent performance.
    """
    if form_trend >= 0.5 or recent_top10s >= 3:
        return '<span style="background: #00C853; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: bold;">HOT 🔥</span>'
    elif form_trend >= 0.2:
        return '<span style="background: #4CAF50; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">WARM</span>'
    elif form_trend <= -0.5:
        return '<span style="background: #F44336; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: bold;">COLD ❄️</span>'
    elif form_trend <= -0.2:
        return '<span style="background: #FF9800; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">COOL</span>'
    else:
        return '<span style="background: #9E9E9E; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">NEUTRAL</span>'


def get_situational_badges(player_data: dict) -> str:
    """
    Return HTML badge spans for narrative/situational features.
    Returns empty string if no notable situations apply.
    Defensive: all features are optional — safe to call before pipeline reruns them.
    """
    badges = []
    _b = lambda color, text: (
        f'<span style="background:{color};color:#fff;padding:2px 7px;'
        f'border-radius:10px;font-size:0.72em;font-weight:700;'
        f'margin-left:4px;white-space:nowrap;">{text}</span>'
    )

    if int(player_data.get("is_defending_champion", 0) or 0):
        badges.append(_b("#b8860b", "👑 DEFENDING"))

    streak = int(player_data.get("consecutive_top10s", 0) or 0)
    if streak >= 3:
        badges.append(_b("#00C853", f"🔥 {streak}-WEEK STREAK"))
    elif streak == 2:
        badges.append(_b("#4CAF50", f"▲ {streak} CONSEC T10"))

    if int(player_data.get("post_top5_last_start", 0) or 0):
        badges.append(_b("#1976D2", "▲ TOP-5 LAST"))

    if int(player_data.get("missed_cut_last_start", 0) or 0):
        badges.append(_b("#B71C1C", "✂ MC LAST"))

    if int(player_data.get("first_start_of_season", 0) or 0):
        badges.append(_b("#555", "◎ DEBUT"))

    return "".join(badges)


def render_player_stat_card(player_data: dict) -> str:
    """
    Render a visual player stat card with all key metrics.

    This creates a card-style display with:
    - Player name and form badge
    - Form score with progress bar
    - SG breakdown bars
    - Recent results
    - Key stats
    """
    name = player_data.get("player_name", "Unknown")

    # Form metrics
    form_trend = player_data.get("form_trend", 0) or 0
    recent_top10s = int(player_data.get("recent_top10s", 0) or 0)
    recent_top5s = int(player_data.get("recent_top5s", 0) or 0)
    cuts_pct = (player_data.get("recent_cuts_pct", 0) or 0) * 100

    # SG metrics
    sg_total = player_data.get("sg_total", 0) or 0
    sg_ott = player_data.get("sg_ott", 0) or 0
    sg_app = player_data.get("sg_app", 0) or 0
    sg_arg = player_data.get("sg_arg", 0) or 0
    sg_putt = player_data.get("sg_putt", 0) or 0

    # World rank
    world_rank = int(player_data.get("world_rank", 999) or 999)
    rank_display = f"#{world_rank}" if world_rank < 999 else "NR"

    # Form badge
    form_badge = get_form_badge(form_trend, recent_top10s)
    sit_badges = get_situational_badges(player_data)

    # SG Total formatted
    sg_total_str = f"+{sg_total:.2f}" if sg_total >= 0 else f"{sg_total:.2f}"
    sg_color = "#00C853" if sg_total >= 0.5 else "#4CAF50" if sg_total >= 0 else "#F44336"

    # Keep this as compact HTML (no leading indentation/blank blocks), otherwise
    # Streamlit markdown can interpret chunks as code blocks and show raw tags.
    card_html = (
        f'<div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);'
        f' border-radius: 12px; padding: 16px; margin: 8px 0;'
        f' border: 1px solid #2a2a4a; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">'
        f'<div>'
        f'<span style="font-size: 1.2em; font-weight: bold; color: #fff;">{name}</span>'
        f'<span style="color: #888; margin-left: 8px;">{rank_display}</span>'
        f'</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;">{form_badge}{sit_badges}</div>'
        f'</div>'
        f'<div style="display: flex; justify-content: space-between; margin-bottom: 12px;'
        f' padding: 8px; background: #2a2a4a; border-radius: 8px;">'
        f'<div style="text-align: center;"><div style="color: {sg_color}; font-weight: bold; font-size: 1.1em;">{sg_total_str}</div><div style="color: #888; font-size: 0.75em;">SG Total</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{recent_top10s}</div><div style="color: #888; font-size: 0.75em;">Top-10s</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{recent_top5s}</div><div style="color: #888; font-size: 0.75em;">Top-5s</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{cuts_pct:.0f}%</div><div style="color: #888; font-size: 0.75em;">Cuts</div></div>'
        f'</div>'
        f'<div style="color: #aaa; font-size: 0.85em; margin-bottom: 6px;">Strokes Gained Breakdown</div>'
        f'<div style="background: #2a2a4a; border-radius: 8px; padding: 10px;">'
        f'{create_sg_bar(sg_ott, "OTT")}'
        f'{create_sg_bar(sg_app, "APP")}'
        f'{create_sg_bar(sg_arg, "ARG")}'
        f'{create_sg_bar(sg_putt, "PUTT")}'
        f'</div>'
        f'</div>'
    )

    return card_html


def render_mini_player_card(player_data: dict, rank: int = 0) -> str:
    """
    Render a compact player card for list views.
    """
    name = player_data.get("player_name", "Unknown")[:22]
    form_trend = player_data.get("form_trend", 0) or 0
    sg_total = player_data.get("sg_total", 0) or 0
    recent_top10s = int(player_data.get("recent_top10s", 0) or 0)

    # Trend indicator (form + situational)
    trend = "🔥" if form_trend >= 0.3 else "❄️" if form_trend <= -0.3 else ""
    if int(player_data.get("is_defending_champion", 0) or 0):
        trend = "👑" + trend
    streak = int(player_data.get("consecutive_top10s", 0) or 0)
    if streak >= 2 and "🔥" not in trend:
        trend = "🔥" + trend  # hot streak overrides neutral trend icon

    # SG color
    sg_color = "#00C853" if sg_total >= 0.5 else "#4CAF50" if sg_total >= 0 else "#FF9800" if sg_total >= -0.5 else "#F44336"
    sg_str = f"+{sg_total:.2f}" if sg_total >= 0 else f"{sg_total:.2f}"

    # Form bar width
    form_width = int(min(100, max(0, (form_trend + 1) * 50)))

    return (
        f'<div style="display: flex; align-items: center; padding: 8px 12px; margin: 4px 0;'
        f' background: #1a1a2e; border-radius: 8px; border: 1px solid #2a2a4a;">'
        f'<span style="color: #666; width: 25px; font-size: 0.85em;">#{rank}</span>'
        f'<span style="flex: 1; color: #fff; font-weight: 500;">{name} {trend}</span>'
        f'<div style="width: 60px; background: #2a2a4a; border-radius: 4px; height: 6px; margin: 0 10px;">'
        f'<div style="background: {"#00C853" if form_trend > 0 else "#F44336"}; height: 100%; width: {form_width}%; border-radius: 4px;"></div>'
        f'</div>'
        f'<span style="color: {sg_color}; font-weight: bold; width: 50px; text-align: right;">{sg_str}</span>'
        f'<span style="color: #888; width: 40px; text-align: right; font-size: 0.85em;">{recent_top10s} T10</span>'
        f'</div>'
    )


def render_form_stats_section(df: pd.DataFrame):
    """
    Render enhanced form analysis using both model form + actual recent results.
    """
    st.markdown("### 🔥 Player Form Analysis")
    base_df = df.copy()
    if "player_name" not in base_df.columns:
        st.warning("No player names available for form analysis.")
        return
    base_df["name_key"] = base_df["player_name"].apply(_name_key)

    # ── Enhanced form block (same philosophy as enhanced course fit) ──────────
    st.markdown("#### Enhanced Form (Model + Actual Recent Results)")
    st.caption("Blends model form with actual recent SG/finishes, confidence-weighted by recent sample size.")

    ec1, ec2 = st.columns([1, 1])
    with ec1:
        lookback_events = st.slider("Recent events window", 5, 16, 10, key="form_actual_lookback")
    with ec2:
        min_actual_events = st.slider("Min actual events for display", 1, 8, 3, key="form_actual_min_events")

    enhanced_df = build_enhanced_recent_form_for_field(base_df, lookback_events=lookback_events)
    if enhanced_df.empty:
        st.info("Could not build enhanced form from historical results. Showing model form only below.")
    else:
        enhanced_view = enhanced_df.copy()
        enhanced_view["actual_events"] = pd.to_numeric(enhanced_view["actual_events"], errors="coerce").fillna(0)
        enhanced_view = enhanced_view[enhanced_view["actual_events"] >= min_actual_events]
        if enhanced_view.empty:
            enhanced_view = enhanced_df.copy()

        covered = int((pd.to_numeric(enhanced_df["actual_events"], errors="coerce").fillna(0) > 0).sum())
        avg_events = float(pd.to_numeric(enhanced_df["actual_events"], errors="coerce").fillna(0).mean())
        avg_sg_cov = float(pd.to_numeric(enhanced_df["actual_sg_coverage"], errors="coerce").fillna(0).mean())
        cut_delta = pd.to_numeric(enhanced_df["model_vs_actual_cut_delta_pts"], errors="coerce").dropna().abs()
        cut_delta_mae = float(cut_delta.mean()) if len(cut_delta) else np.nan

        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("Players With Actual Results", f"{covered}/{len(enhanced_df)}")
        with mc2:
            st.metric("Avg Events/Player", f"{avg_events:.1f}")
        with mc3:
            st.metric("SG Coverage", f"{avg_sg_cov*100:.0f}%")
        with mc4:
            st.metric("Cut-Rate Delta (MAE)", f"{cut_delta_mae:.1f} pts" if pd.notna(cut_delta_mae) else "—")

        top3 = enhanced_view.sort_values("enhanced_form_pct", ascending=False).head(3)
        if not top3.empty:
            tcols = st.columns(3)
            for i, (_, row) in enumerate(top3.iterrows()):
                with tcols[i]:
                    nm = str(row.get("player_name", "Unknown"))[:18]
                    ep = pd.to_numeric(row.get("enhanced_form_pct"), errors="coerce")
                    mp = pd.to_numeric(row.get("model_form_pct"), errors="coerce")
                    lift = pd.to_numeric(row.get("form_lift_pts"), errors="coerce")
                    evs = int(pd.to_numeric(row.get("actual_events"), errors="coerce") or 0)
                    conf = pd.to_numeric(row.get("actual_confidence"), errors="coerce")
                    sgt = pd.to_numeric(row.get("actual_sg_trend"), errors="coerce")

                    ep_s = f"{ep:.1f}%" if pd.notna(ep) else "—"
                    mp_s = f"{mp:.1f}%" if pd.notna(mp) else "—"
                    lift_s = f"{lift:+.1f}" if pd.notna(lift) else "—"
                    conf_s = f"{conf:.2f}" if pd.notna(conf) else "0.00"
                    sgt_s = f"{sgt:+.3f}" if pd.notna(sgt) else "—"

                    st.markdown(
                        f"""
                        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                                    border-radius: 12px; padding: 14px; margin: 4px 0;
                                    border: 1px solid #2a2a4a; text-align: center;">
                            <div style="font-weight: bold; color: #fff; font-size: 1.0em; margin-bottom: 6px;">{nm}</div>
                            <div style="color: #00C853; font-size: 1.3em; font-weight: bold;">{ep_s}</div>
                            <div style="color: #888; font-size: 0.75em;">Enhanced Form Percentile</div>
                            <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:0.78em;color:#c9d6ea;">
                                <span>Model: <b>{mp_s}</b></span>
                                <span>Lift: <b>{lift_s}</b></span>
                            </div>
                            <div style="display:flex;justify-content:space-between;margin-top:5px;font-size:0.75em;color:#9fb0c7;">
                                <span>Events: <b>{evs}</b></span>
                                <span>Conf: <b>{conf_s}</b></span>
                            </div>
                            <div style="display:flex;justify-content:space-between;margin-top:5px;font-size:0.75em;color:#9fb0c7;">
                                <span>SG Trend: <b>{sgt_s}</b></span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        plot_df = enhanced_view.copy()
        plot_df["model_form_pct"] = pd.to_numeric(plot_df["model_form_pct"], errors="coerce")
        plot_df["enhanced_form_pct"] = pd.to_numeric(plot_df["enhanced_form_pct"], errors="coerce")
        plot_df["form_lift_pts"] = pd.to_numeric(plot_df["form_lift_pts"], errors="coerce")
        plot_df["actual_events"] = pd.to_numeric(plot_df["actual_events"], errors="coerce").fillna(0)
        plot_df = plot_df[plot_df["model_form_pct"].notna() & plot_df["enhanced_form_pct"].notna()]
        if not plot_df.empty:
            fig_form = px.scatter(
                plot_df,
                x="model_form_pct",
                y="enhanced_form_pct",
                size="actual_events",
                color="form_lift_pts",
                hover_name="player_name",
                hover_data={
                    "actual_events": True,
                    "actual_avg_sg": ":.2f",
                    "actual_sg_trend": ":+.3f",
                    "actual_cut_rate": ":.2%",
                    "actual_top10_rate": ":.2%",
                    "actual_confidence": ":.2f",
                    "model_form_pct": ":.1f",
                    "enhanced_form_pct": ":.1f",
                    "form_lift_pts": ":+.1f",
                },
                color_continuous_scale="RdYlGn",
                labels={
                    "model_form_pct": "Model Form Percentile",
                    "enhanced_form_pct": "Enhanced Form Percentile",
                    "form_lift_pts": "Lift (pts)",
                },
                title="Enhanced vs Model-Only Form",
            )
            fig_form.add_shape(
                type="line",
                x0=0, y0=0, x1=100, y1=100,
                line=dict(color="#8093ad", width=1, dash="dot"),
            )
            fig_form.update_layout(
                height=340,
                margin=dict(t=40, b=10, l=10, r=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#dde6f5",
            )
            st.plotly_chart(fig_form, use_container_width=True)

        top_table = (
            enhanced_view.sort_values("enhanced_form_pct", ascending=False)
            .head(20)[
                [
                    "player_name",
                    "actual_events",
                    "actual_avg_sg",
                    "actual_sg_trend",
                    "actual_cut_rate",
                    "actual_top10_rate",
                    "actual_confidence",
                    "model_form_pct",
                    "enhanced_form_pct",
                    "form_lift_pts",
                ]
            ]
            .rename(
                columns={
                    "player_name": "Player",
                    "actual_events": "Events",
                    "actual_avg_sg": "Avg SG",
                    "actual_sg_trend": "SG Trend",
                    "actual_cut_rate": "Cut %",
                    "actual_top10_rate": "Top-10 %",
                    "actual_confidence": "Confidence",
                    "model_form_pct": "Model %",
                    "enhanced_form_pct": "Enhanced %",
                    "form_lift_pts": "Lift",
                }
            )
        )
        st.dataframe(
            top_table,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Avg SG": st.column_config.NumberColumn("Avg SG", format="%+.2f"),
                "SG Trend": st.column_config.NumberColumn("SG Trend", format="%+.3f"),
                "Cut %": st.column_config.ProgressColumn("Cut %", min_value=0.0, max_value=1.0, format="%.0f%%"),
                "Top-10 %": st.column_config.ProgressColumn("Top-10 %", min_value=0.0, max_value=1.0, format="%.0f%%"),
                "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                "Model %": st.column_config.NumberColumn("Model %", format="%.1f"),
                "Enhanced %": st.column_config.NumberColumn("Enhanced %", format="%.1f"),
                "Lift": st.column_config.NumberColumn("Lift", format="%+.1f"),
            },
        )

        # Carry enhanced columns into the board section below.
        keep_cols = [
            "name_key",
            "actual_events",
            "actual_sg_coverage",
            "actual_avg_sg",
            "actual_cut_rate",
            "actual_top10_rate",
            "actual_confidence",
            "enhanced_form_pct",
            "model_form_pct",
            "form_lift_pts",
        ]
        base_df = base_df.merge(
            enhanced_df[keep_cols].drop_duplicates(subset=["name_key"], keep="first"),
            on="name_key",
            how="left",
        )

    # ── Existing board (kept, now with enhanced sort options) ─────────────────
    st.markdown("---")
    st.markdown("#### Form Board")

    col1, col2, col3 = st.columns(3)
    with col1:
        show_filter = st.selectbox("Show:", ["All", "Hot Players", "Cold Players", "Most Consistent"], key="form_filter")
    with col2:
        sort_by = st.selectbox(
            "Sort by:",
            ["Enhanced Form %", "Form Lift", "Form Trend", "SG Total", "Actual SG (Recent)", "Recent Top-10s", "World Rank"],
            key="form_sort",
        )
    with col3:
        limit = st.slider("Players to show:", 5, 30, 15, key="form_limit")

    filtered_df = base_df.copy()
    if show_filter == "Hot Players":
        if "enhanced_form_pct" in filtered_df.columns and filtered_df["enhanced_form_pct"].notna().any():
            filtered_df = filtered_df[filtered_df["enhanced_form_pct"] >= 70]
        elif "form_trend" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["form_trend"] >= 0.2]
    elif show_filter == "Cold Players":
        if "enhanced_form_pct" in filtered_df.columns and filtered_df["enhanced_form_pct"].notna().any():
            filtered_df = filtered_df[filtered_df["enhanced_form_pct"] <= 30]
        elif "form_trend" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["form_trend"] <= -0.2]
    elif show_filter == "Most Consistent":
        if "finish_consistency" in filtered_df.columns:
            filtered_df = filtered_df.nsmallest(limit * 2, "finish_consistency")

    sort_map = {
        "Enhanced Form %": ("enhanced_form_pct", False),
        "Form Lift": ("form_lift_pts", False),
        "Form Trend": ("form_trend", False),
        "SG Total": ("sg_total", False),
        "Actual SG (Recent)": ("actual_avg_sg", False),
        "Recent Top-10s": ("recent_top10s", False),
        "World Rank": ("world_rank", True),
    }
    sort_col, ascending = sort_map.get(sort_by, ("enhanced_form_pct", False))
    if sort_col in filtered_df.columns:
        filtered_df = filtered_df.sort_values(sort_col, ascending=ascending, na_position="last")

    filtered_df = filtered_df.head(limit)
    if filtered_df.empty:
        st.warning("No players match the current filter")
        return

    display_mode = st.radio("Display:", ["Cards", "List", "Table"], horizontal=True, key="form_display")
    if display_mode == "Cards":
        cols = st.columns(2)
        for idx, (_, row) in enumerate(filtered_df.iterrows()):
            with cols[idx % 2]:
                st.markdown(render_player_stat_card(row.to_dict()), unsafe_allow_html=True)
    elif display_mode == "List":
        st.markdown('<div style="background: #0e0e1a; border-radius: 12px; padding: 12px;">', unsafe_allow_html=True)
        for idx, (_, row) in enumerate(filtered_df.iterrows(), 1):
            st.markdown(render_mini_player_card(row.to_dict(), idx), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        display_cols = [
            "player_name",
            "enhanced_form_pct",
            "form_lift_pts",
            "actual_events",
            "actual_avg_sg",
            "form_trend",
            "sg_total",
            "recent_top10s",
            "recent_top5s",
            "recent_cuts_pct",
        ]
        display_df = filtered_df[[c for c in display_cols if c in filtered_df.columns]].copy()
        if "form_trend" in display_df.columns:
            display_df["form_trend"] = pd.to_numeric(display_df["form_trend"], errors="coerce").round(2)
        if "sg_total" in display_df.columns:
            display_df["sg_total"] = pd.to_numeric(display_df["sg_total"], errors="coerce").round(2)
        if "actual_avg_sg" in display_df.columns:
            display_df["actual_avg_sg"] = pd.to_numeric(display_df["actual_avg_sg"], errors="coerce").round(2)
        if "enhanced_form_pct" in display_df.columns:
            display_df["enhanced_form_pct"] = pd.to_numeric(display_df["enhanced_form_pct"], errors="coerce").round(1)
        if "form_lift_pts" in display_df.columns:
            display_df["form_lift_pts"] = pd.to_numeric(display_df["form_lift_pts"], errors="coerce").round(1)
        if "recent_cuts_pct" in display_df.columns:
            display_df["recent_cuts_pct"] = (pd.to_numeric(display_df["recent_cuts_pct"], errors="coerce") * 100).round(0).astype("Int64").astype(str) + "%"
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
        st.dataframe(display_df, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Field Summary")
    s1, s2, s3, s4 = st.columns(4)

    if "form_trend" in base_df.columns:
        hot_count = len(base_df[pd.to_numeric(base_df["form_trend"], errors="coerce") >= 0.3])
        cold_count = len(base_df[pd.to_numeric(base_df["form_trend"], errors="coerce") <= -0.3])
        with s1:
            st.metric("🔥 Hot Players", hot_count)
        with s2:
            st.metric("❄️ Cold Players", cold_count)

    if "sg_total" in base_df.columns:
        avg_sg = pd.to_numeric(base_df["sg_total"], errors="coerce").mean()
        with s3:
            st.metric("Field Avg SG", f"{avg_sg:+.2f}" if pd.notna(avg_sg) else "—")

    if "recent_cuts_pct" in base_df.columns:
        avg_cuts = pd.to_numeric(base_df["recent_cuts_pct"], errors="coerce").mean() * 100
        with s4:
            st.metric("Avg Cut Rate", f"{avg_cuts:.0f}%" if pd.notna(avg_cuts) else "—")


def load_player_stats() -> pd.DataFrame:
    """
    Load compiled player stats from the latest predictions file.

    WHY: The predictions file contains pre-calculated stats for all players
    in the current tournament field, making it a convenient source for analysis.
    """
    pred_files = get_prediction_files()
    if not pred_files:
        return pd.DataFrame()

    # Load the most recent predictions file
    df = pd.read_csv(pred_files[0])
    return df


def render_strokes_gained_analysis(df: pd.DataFrame):
    """
    Render Strokes Gained deep dive analysis.

    WHAT IT SHOWS:
    - SG breakdown by category (OTT, APP, ARG, PUTT)
    - Comparison between recent form and season averages
    - Player rankings in each SG category
    - Visual breakdown charts
    """
    st.markdown("### Strokes Gained Breakdown")

    # Define the SG categories we want to analyze
    # These are the 4 main components that make up SG:Total
    sg_categories = {
        "sg_ott": "Off-the-Tee",      # Driving
        "sg_app": "Approach",          # Iron play
        "sg_arg": "Around Green",      # Short game
        "sg_putt": "Putting"           # Putting
    }

    # Check which columns exist in our data
    available_sg = [col for col in sg_categories.keys() if col in df.columns]

    if not available_sg:
        st.warning("No Strokes Gained data available")
        return

    # --- Section 0: Visual Top Performers Cards ---
    if "sg_total" in df.columns:
        st.markdown("#### 🏆 Top SG Performers")
        st.caption("Visual breakdown of the top strokes gained performers")

        # Get top 3 by SG Total for visual cards
        top3_sg = df.nlargest(3, "sg_total")

        cols = st.columns(3)
        for i, (_, player) in enumerate(top3_sg.iterrows()):
            with cols[i]:
                # Create visual card for each top performer
                card_html = render_player_stat_card(player.to_dict())
                st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("---")

    # --- Section 1: Top 10 by SG Total ---
    st.markdown("#### Top 10 by SG: Total")

    if "sg_total" in df.columns:
        # Get top 10 players by SG Total
        top10_sg = df.nlargest(10, "sg_total")[["player_name", "sg_total"] + available_sg].copy()

        # Round for display
        for col in ["sg_total"] + available_sg:
            if col in top10_sg.columns:
                top10_sg[col] = top10_sg[col].round(2)

        # Rename columns for display
        display_cols = {"player_name": "Player", "sg_total": "SG Total"}
        display_cols.update({k: v for k, v in sg_categories.items() if k in available_sg})
        top10_sg = top10_sg.rename(columns=display_cols)

        st.dataframe(top10_sg, hide_index=True, use_container_width=True)

    # --- Section 2: SG Breakdown Chart ---
    st.markdown("#### SG Category Breakdown - Top 20 Players")

    # Get top 20 players for the chart
    if "sg_total" in df.columns:
        top20 = df.nlargest(20, "sg_total").copy()
    else:
        top20 = df.head(20).copy()

    # Prepare data for stacked bar chart
    # We'll show each SG component stacked for each player
    chart_data = []
    for _, row in top20.iterrows():
        player = row["player_name"][:15]  # Truncate long names
        for sg_col, sg_name in sg_categories.items():
            if sg_col in df.columns:
                chart_data.append({
                    "Player": player,
                    "Category": sg_name,
                    "Value": row.get(sg_col, 0) or 0
                })

    if chart_data:
        chart_df = pd.DataFrame(chart_data)

        # Create grouped bar chart using Plotly
        fig = px.bar(
            chart_df,
            x="Player",
            y="Value",
            color="Category",
            barmode="group",  # Side-by-side bars
            title="SG Breakdown by Player",
            color_discrete_map={
                "Off-the-Tee": "#2196F3",   # Blue for driving
                "Approach": "#4CAF50",       # Green for approach
                "Around Green": "#FF9800",   # Orange for short game
                "Putting": "#9C27B0"         # Purple for putting
            }
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # --- Section 2.5: Category Leaders ---
    st.markdown("#### 🥇 Category Leaders")
    st.caption("Top performer in each strokes gained category")

    cat_cols = st.columns(4)
    cat_colors = {
        "sg_ott": ("#2196F3", "🎯", "Off-the-Tee"),
        "sg_app": ("#4CAF50", "⛳", "Approach"),
        "sg_arg": ("#FF9800", "🏌️", "Around Green"),
        "sg_putt": ("#9C27B0", "🕳️", "Putting")
    }

    for i, (sg_col, (color, emoji, label)) in enumerate(cat_colors.items()):
        if sg_col in df.columns:
            with cat_cols[i]:
                # Get top player in this category
                top_player = df.nlargest(1, sg_col).iloc[0]
                player_name = top_player["player_name"][:15]
                sg_value = top_player[sg_col]
                sg_str = f"+{sg_value:.2f}" if sg_value >= 0 else f"{sg_value:.2f}"

                # Create visual card for category leader
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, {color}22, {color}11);
                            border: 2px solid {color}; border-radius: 12px;
                            padding: 12px; text-align: center;">
                    <div style="font-size: 1.5em;">{emoji}</div>
                    <div style="color: #888; font-size: 0.8em; margin: 4px 0;">{label}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1em;">{player_name}</div>
                    <div style="color: {color}; font-weight: bold; font-size: 1.2em;">{sg_str}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # --- Section 3: Season vs Recent Form Comparison ---
    st.markdown("#### Season Average vs Recent Form")
    st.caption("Compare a player's season-long stats with their recent tournament form")

    # Check if we have both season and recent SG stats
    season_cols = ["season_sg_ott", "season_sg_app", "season_sg_arg", "season_sg_putt"]
    recent_cols = ["sg_ott", "sg_app", "sg_arg", "sg_putt"]

    has_season = any(col in df.columns for col in season_cols)
    has_recent = any(col in df.columns for col in recent_cols)

    if has_season and has_recent:
        # Let user select a player to analyze
        player_list = df["player_name"].dropna().tolist()
        selected_player = st.selectbox("Select Player:", player_list[:50], key="sg_player_select")

        if selected_player:
            player_row = df[df["player_name"] == selected_player].iloc[0]

            # Build comparison data
            comparison_data = []
            for i, (season_col, recent_col) in enumerate(zip(season_cols, recent_cols)):
                category = list(sg_categories.values())[i]
                season_val = player_row.get(season_col, 0) or 0
                recent_val = player_row.get(recent_col, 0) or 0

                comparison_data.append({"Category": category, "Type": "Season Avg", "Value": season_val})
                comparison_data.append({"Category": category, "Type": "Recent Form", "Value": recent_val})

            comp_df = pd.DataFrame(comparison_data)

            # Create comparison chart
            fig = px.bar(
                comp_df,
                x="Category",
                y="Value",
                color="Type",
                barmode="group",
                title=f"{selected_player} - Season vs Recent Form",
                color_discrete_map={"Season Avg": "#78909C", "Recent Form": "#00BCD4"}
            )
            st.plotly_chart(fig, use_container_width=True)

            # Show insight
            for i, (season_col, recent_col) in enumerate(zip(season_cols, recent_cols)):
                category = list(sg_categories.values())[i]
                season_val = player_row.get(season_col, 0) or 0
                recent_val = player_row.get(recent_col, 0) or 0
                diff = recent_val - season_val

                if abs(diff) > 0.3:  # Significant difference threshold
                    if diff > 0:
                        st.success(f"🔥 **{category}**: Recent form is {diff:.2f} strokes better than season average")
                    else:
                        st.warning(f"📉 **{category}**: Recent form is {abs(diff):.2f} strokes worse than season average")


def render_form_analysis(df: pd.DataFrame):
    """
    Render player form analysis.

    WHAT IT SHOWS:
    - Recent results (last 5-10 tournaments)
    - Form trends (hot/cold streaks)
    - Consistency metrics
    - Cut-making percentages
    """
    st.markdown("### Form Analysis")

    # --- Section 1: Form Metrics Overview ---
    form_cols = ["form_trend", "recent_top10s", "recent_top5s", "recent_cuts_pct", "finish_consistency"]
    available_form = [col for col in form_cols if col in df.columns]

    if not available_form:
        st.warning("No form data available")
        return

    # Hot players (high form trend)
    if "form_trend" in df.columns:
        st.markdown("#### 🔥 Hottest Players (Form Trend)")
        st.caption("Form trend measures recent performance vs expected - higher = playing above expectations")

        hot_players = df.nlargest(10, "form_trend")[["player_name", "form_trend", "recent_top10s", "recent_cuts_pct"]].copy()

        # Format for display
        hot_players["form_trend"] = hot_players["form_trend"].round(2)
        if "recent_top10s" in hot_players.columns:
            hot_players["recent_top10s"] = hot_players["recent_top10s"].fillna(0).astype(int)
        if "recent_cuts_pct" in hot_players.columns:
            hot_players["recent_cuts_pct"] = (hot_players["recent_cuts_pct"] * 100).round(0).astype(str) + "%"

        hot_players.columns = ["Player", "Form Trend", "Recent Top-10s", "Cut %"]
        st.dataframe(hot_players, hide_index=True, use_container_width=True)

    # Cold players
    if "form_trend" in df.columns:
        st.markdown("#### ❄️ Coldest Players")
        cold_players = df.nsmallest(10, "form_trend")[["player_name", "form_trend", "recent_top10s", "recent_cuts_pct"]].copy()

        cold_players["form_trend"] = cold_players["form_trend"].round(2)
        if "recent_top10s" in cold_players.columns:
            cold_players["recent_top10s"] = cold_players["recent_top10s"].fillna(0).astype(int)
        if "recent_cuts_pct" in cold_players.columns:
            cold_players["recent_cuts_pct"] = (cold_players["recent_cuts_pct"] * 100).round(0).astype(str) + "%"

        cold_players.columns = ["Player", "Form Trend", "Recent Top-10s", "Cut %"]
        st.dataframe(cold_players, hide_index=True, use_container_width=True)

    # --- Section 2: Form Distribution ---
    st.markdown("#### Form Distribution")

    if "form_trend" in df.columns:
        fig = px.histogram(
            df,
            x="form_trend",
            nbins=30,
            title="Field Form Trend Distribution",
            labels={"form_trend": "Form Trend"}
        )
        fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Average")
        st.plotly_chart(fig, use_container_width=True)

    # --- Section 3: Consistency Analysis ---
    st.markdown("#### Consistency vs Upside")
    st.caption("X-axis = consistency (lower = more consistent), Y-axis = recent form")

    if "finish_consistency" in df.columns and "form_trend" in df.columns:
        # Scatter plot of consistency vs form
        fig = px.scatter(
            df.head(50),  # Top 50 players
            x="finish_consistency",
            y="form_trend",
            hover_data=["player_name"],
            title="Consistency vs Form Trend",
            labels={
                "finish_consistency": "Finish Consistency (lower = more consistent)",
                "form_trend": "Form Trend (higher = hotter)"
            }
        )

        # Add quadrant labels
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_vline(x=df["finish_consistency"].median(), line_dash="dash", line_color="gray")

        st.plotly_chart(fig, use_container_width=True)

        st.info("""
        **How to read this chart:**
        - **Top-Left**: Hot AND consistent (ideal!)
        - **Top-Right**: Hot but inconsistent (boom-or-bust)
        - **Bottom-Left**: Cold but consistent (steady decline)
        - **Bottom-Right**: Cold and inconsistent (avoid)
        """)


def load_course_performance_data():
    """Load player course performance data."""
    path = DATA_DIR / "processed" / "player_course_performance.csv"
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_course_similarity_data():
    """Load course similarity matrix and profiles."""
    sim_path = DATA_DIR / "processed" / "course_similarity_matrix.csv"
    prof_path = DATA_DIR / "processed" / "course_profiles.csv"

    sim_matrix = None
    profiles = None

    if sim_path.exists():
        sim_matrix = pd.read_csv(sim_path, index_col=0)
    if prof_path.exists():
        profiles = pd.read_csv(prof_path)

    return sim_matrix, profiles


def get_similar_courses(course_key: str, sim_matrix: pd.DataFrame, profiles: pd.DataFrame, top_n: int = 5):
    """Get most similar courses to a given course."""
    if sim_matrix is None or course_key not in sim_matrix.index:
        # Try to find a fuzzy match
        if sim_matrix is not None:
            matches = [c for c in sim_matrix.index if course_key in c or c in course_key]
            if matches:
                course_key = matches[0]
            else:
                return []
        else:
            return []

    similarities = sim_matrix[course_key].sort_values(ascending=False)
    results = []

    for other_course, score in similarities.items():
        if other_course == course_key:
            continue
        if score < 0.5:  # Skip low similarity
            continue

        # Get profile info
        profile_row = profiles[profiles["course_key"] == other_course] if profiles is not None else None
        course_type = profile_row["course_type"].values[0] if profile_row is not None and len(profile_row) > 0 else "unknown"
        course_name = profile_row["course_name"].values[0] if profile_row is not None and len(profile_row) > 0 else other_course

        results.append({
            "course_key": other_course,
            "course_name": course_name,
            "course_type": course_type,
            "similarity": score,
        })

        if len(results) >= top_n:
            break

    return results


def load_tournament_course_mapping():
    """Load tournament-to-course mapping from JSON."""
    mapping_path = DATA_DIR / "reference" / "tournament_courses.json"
    if not mapping_path.exists():
        return {}
    with open(mapping_path, 'r') as f:
        data = json.load(f)
    return data.get("tournaments", {})


def normalize_course_key(text):
    """Normalize text for course key matching."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"\(\s*\d{4}\s*\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_course_for_tournament(tournament_name: str) -> dict:
    """Look up the course information for a tournament."""
    mapping = load_tournament_course_mapping()
    name_key = normalize_course_key(tournament_name)

    for tourn_name, details in mapping.items():
        if normalize_course_key(tourn_name) == name_key:
            return {
                "course_name": details.get("course", "Unknown"),
                "course_full_name": details.get("course_full", details.get("course", "Unknown")),
                "course_key": normalize_course_key(details.get("course_full", details.get("course", "Unknown"))),
                "course_type": details.get("course_type", "unknown"),
                "location": details.get("location", "Unknown"),
            }
        for alias in details.get("aliases", []):
            if normalize_course_key(alias) == name_key:
                return {
                    "course_name": details.get("course", "Unknown"),
                    "course_full_name": details.get("course_full", details.get("course", "Unknown")),
                    "course_key": normalize_course_key(details.get("course_full", details.get("course", "Unknown"))),
                    "course_type": details.get("course_type", "unknown"),
                    "location": details.get("location", "Unknown"),
                }

    return {"course_name": "Unknown", "course_full_name": "Unknown", "course_key": "unknown", "course_type": "unknown", "location": "Unknown"}


def _compute_course_perf_score(df: pd.DataFrame) -> pd.Series:
    """Composite course-performance score used for ranking."""
    base_score = (
        df["top_10_rate"].fillna(0) * 3.0 +
        df["made_cut_rate"].fillna(0) * 1.5 +
        df["win_rate"].fillna(0) * 5.0 +
        (1 - df["avg_finish"].fillna(40) / 60.0) * 2.0
    )
    if "course_sg_total_vs_avg" in df.columns:
        return base_score + df["course_sg_total_vs_avg"].fillna(0) * 2.0
    return base_score


def render_course_performance_profiles(tournament_name: str, field_player_ids: list = None):
    """
    Render course performance profiles for players at a tournament.

    Shows historical performance at the specific course including:
    - Made cut rate, top 10 rate, win rate
    - Average finish, best finish
    - Stats breakdown (driving, GIR, putting, etc.)
    """
    st.markdown("### 📊 Course Performance Profiles")

    course_info = get_course_for_tournament(tournament_name)
    course_key = course_info["course_key"]
    if course_key == "unknown":
        st.info(f"No course mapping found for '{tournament_name}'")
        return

    st.markdown(f"**Course:** {course_info['course_full_name']}")
    st.markdown(f"**Type:** {course_info['course_type'].title()} | **Location:** {course_info['location']}")

    sim_matrix, profiles = load_course_similarity_data()
    if sim_matrix is not None:
        similar = get_similar_courses(course_key, sim_matrix, profiles, top_n=4)
        if similar:
            similar_str = " | ".join([f"{s['course_name']} ({s['similarity']:.0%})" for s in similar])
            st.caption(f"Closest course comps: {similar_str}")

    st.markdown("---")

    course_perf = load_course_performance_data()
    if course_perf.empty:
        st.warning("Course performance data not available. Run the pipeline to generate it.")
        return

    course_data = course_perf[course_perf["course_key"] == course_key].copy()
    if course_data.empty:
        st.info(f"No historical data for {course_info['course_name']}")
        return

    field_ids_set = set()
    if field_player_ids:
        field_ids = pd.to_numeric(pd.Series(field_player_ids), errors="coerce").dropna().astype(int)
        field_ids_set = set(field_ids.tolist())

    in_field = pd.DataFrame()
    if field_ids_set:
        player_ids_num = pd.to_numeric(course_data["player_id"], errors="coerce").fillna(-1).astype(int)
        in_field = course_data[player_ids_num.isin(field_ids_set)].copy()

    has_sg_data = "course_sg_total_vs_avg" in course_data.columns
    key_base = f"course_perf_{re.sub(r'[^a-z0-9_]+', '_', course_key)}"

    control_col1, control_col2, control_col3, control_col4 = st.columns([1.4, 1.0, 1.0, 1.2])
    scope_options = ["Field Players", "All Players"] if not in_field.empty else ["All Players"]
    with control_col1:
        scope = st.radio("Scope", scope_options, horizontal=True, key=f"{key_base}_scope")
    with control_col2:
        min_starts = st.slider("Min starts", min_value=1, max_value=8, value=2, key=f"{key_base}_min_starts")
    with control_col3:
        top_n = st.slider("Top N", min_value=3, max_value=20, value=9, key=f"{key_base}_top_n")

    working_df = in_field if scope == "Field Players" else course_data
    starts_num = pd.to_numeric(working_df.get("starts"), errors="coerce").fillna(0)
    filtered = working_df[starts_num >= min_starts].copy()
    if filtered.empty:
        filtered = working_df.copy()
        st.info("No players met the minimum starts filter, showing all available records.")

    filtered["perf_score"] = _compute_course_perf_score(filtered)

    metric_map = {
        "Composite Score": ("perf_score", False),
        "SG Edge": ("course_sg_total_vs_avg", False),
        "Top-10 Rate": ("top_10_rate", False),
        "Cut Rate": ("made_cut_rate", False),
        "Average Finish": ("avg_finish", True),
        "Starts": ("starts", False),
    }
    available_metrics = [k for k, (col, _) in metric_map.items() if col in filtered.columns]
    if not available_metrics:
        available_metrics = ["Composite Score"]
    with control_col4:
        sort_label = st.selectbox("Rank by", available_metrics, key=f"{key_base}_sort")

    sort_col, sort_asc = metric_map.get(sort_label, ("perf_score", False))
    ranked = filtered.sort_values(sort_col, ascending=sort_asc, na_position="last").copy()

    # Summary metrics
    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    with metric_col1:
        st.metric("Players in View", f"{len(ranked)}")
    with metric_col2:
        st.metric("Median Starts", f"{pd.to_numeric(ranked['starts'], errors='coerce').median():.1f}")
    with metric_col3:
        st.metric("Avg Cut Rate", f"{(pd.to_numeric(ranked['made_cut_rate'], errors='coerce').mean() * 100):.0f}%")
    with metric_col4:
        leader_name = str(ranked.iloc[0]["player_name"]) if len(ranked) else "N/A"
        st.metric("Top Specialist", leader_name)

    st.markdown("#### 🏆 Ranked Course Specialists")
    st.caption(f"Sorted by {sort_label.lower()} ({'ascending' if sort_asc else 'descending'}).")
    render_course_performance_cards(
        ranked,
        top_n=top_n,
        sort_col=sort_col,
        ascending=sort_asc,
        metric_label=sort_label,
    )

    if has_sg_data:
        sg_df = ranked[pd.to_numeric(ranked["course_sg_total_vs_avg"], errors="coerce").notna()].copy()
        if len(sg_df) >= 4:
            st.markdown("#### 📈 SG Edge Diagnostics")
            diag_col1, diag_col2 = st.columns(2)

            with diag_col1:
                edge_top = sg_df.nlargest(min(10, len(sg_df)), "course_sg_total_vs_avg").sort_values("course_sg_total_vs_avg")
                fig_edge = px.bar(
                    edge_top,
                    x="course_sg_total_vs_avg",
                    y="player_name",
                    orientation="h",
                    color="course_sg_total_vs_avg",
                    color_continuous_scale="RdYlGn",
                    labels={"course_sg_total_vs_avg": "SG Edge", "player_name": "Player"},
                    title="Best SG Edge at This Course",
                )
                fig_edge.update_layout(showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig_edge, use_container_width=True)

            with diag_col2:
                scatter_df = sg_df.copy()
                scatter_df["bubble_size"] = (scatter_df["top_10_rate"].fillna(0.05).clip(0.05, 1.0) * 40.0)
                fig_scatter = px.scatter(
                    scatter_df,
                    x="starts",
                    y="course_sg_total_vs_avg",
                    size="bubble_size",
                    color="made_cut_rate",
                    hover_name="player_name",
                    color_continuous_scale="Viridis",
                    labels={
                        "starts": "Starts at Course",
                        "course_sg_total_vs_avg": "SG Edge",
                        "made_cut_rate": "Cut Rate",
                    },
                    title="Experience vs SG Edge",
                )
                fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("#### 📋 Full Course History")
    table_cols = [
        "player_name",
        "starts",
        "made_cut_rate",
        "top_10_rate",
        "win_rate",
        "avg_finish",
        "best_finish",
        "last_season",
        "course_sg_total_weighted",
        "course_sg_total_vs_avg",
        "perf_score",
    ]
    table_cols = [c for c in table_cols if c in ranked.columns]
    table_df = ranked[table_cols].head(30).copy()
    table_df = table_df.rename(
        columns={
            "player_name": "Player",
            "starts": "Starts",
            "made_cut_rate": "Cut %",
            "top_10_rate": "Top-10 %",
            "win_rate": "Win %",
            "avg_finish": "Avg Finish",
            "best_finish": "Best Finish",
            "last_season": "Last Season",
            "course_sg_total_weighted": "Course SG",
            "course_sg_total_vs_avg": "SG Edge",
            "perf_score": "Composite",
        }
    )

    for pct_col in ["Cut %", "Top-10 %", "Win %"]:
        if pct_col in table_df.columns:
            table_df[pct_col] = pd.to_numeric(table_df[pct_col], errors="coerce").fillna(0) * 100.0

    column_cfg = {
        "Cut %": st.column_config.ProgressColumn("Cut %", min_value=0.0, max_value=100.0, format="%.0f%%"),
        "Top-10 %": st.column_config.ProgressColumn("Top-10 %", min_value=0.0, max_value=100.0, format="%.0f%%"),
        "Win %": st.column_config.ProgressColumn("Win %", min_value=0.0, max_value=100.0, format="%.0f%%"),
        "Course SG": st.column_config.NumberColumn("Course SG", format="%.3f"),
        "SG Edge": st.column_config.NumberColumn("SG Edge", format="%+.3f"),
        "Composite": st.column_config.NumberColumn("Composite", format="%.2f"),
        "Avg Finish": st.column_config.NumberColumn("Avg Finish", format="%.1f"),
    }
    st.dataframe(table_df, hide_index=True, use_container_width=True, column_config=column_cfg)


def render_course_performance_cards(
    df: pd.DataFrame,
    top_n: int = 6,
    sort_col: str = "perf_score",
    ascending: bool = False,
    metric_label: str = "Composite Score",
):
    """Render compact visual cards for ranked course performers."""
    if df.empty:
        st.info("No data available")
        return

    work = df.copy()
    if sort_col not in work.columns:
        work["perf_score"] = _compute_course_perf_score(work)
        sort_col = "perf_score"
        ascending = False

    ranked = work.sort_values(sort_col, ascending=ascending, na_position="last").head(top_n)
    rows = [ranked.iloc[i:i + 3] for i in range(0, len(ranked), 3)]

    for row_df in rows:
        cols = st.columns(3)
        for i, (_, player) in enumerate(row_df.iterrows()):
            with cols[i]:
                name = str(player.get("player_name", "Unknown"))
                starts = int(pd.to_numeric(player.get("starts", 0), errors="coerce") or 0)
                cut_rate = float(pd.to_numeric(player.get("made_cut_rate", 0), errors="coerce") or 0)
                top10_rate = float(pd.to_numeric(player.get("top_10_rate", 0), errors="coerce") or 0)
                win_rate = float(pd.to_numeric(player.get("win_rate", 0), errors="coerce") or 0)
                best_finish = int(pd.to_numeric(player.get("best_finish", 0), errors="coerce") or 0)
                sg_edge = pd.to_numeric(player.get("course_sg_total_vs_avg"), errors="coerce")

                rank_val = pd.to_numeric(player.get(sort_col), errors="coerce")
                if pd.isna(rank_val):
                    metric_value = "N/A"
                elif sort_col in ["made_cut_rate", "top_10_rate", "win_rate"]:
                    metric_value = f"{rank_val * 100:.0f}%"
                elif sort_col == "avg_finish":
                    metric_value = f"{rank_val:.1f}"
                elif "sg_" in sort_col:
                    metric_value = f"{rank_val:+.2f}"
                else:
                    metric_value = f"{rank_val:.2f}"

                reason_parts = []
                if top10_rate >= 0.25:
                    reason_parts.append("strong top-10 rate")
                if cut_rate >= 0.8:
                    reason_parts.append("high cut reliability")
                if pd.notna(sg_edge) and sg_edge > 0.2:
                    reason_parts.append("positive SG edge")
                reason = ", ".join(reason_parts[:2]) if reason_parts else "balanced history profile"

                border_color = "#1e7f37" if (pd.notna(rank_val) and not ascending and rank_val > 0) else "#2d5f9a"
                if sort_col == "avg_finish":
                    border_color = "#1e7f37" if pd.notna(rank_val) and rank_val <= 25 else "#2d5f9a"

                sg_text = "N/A" if pd.isna(sg_edge) else f"{sg_edge:+.2f}"
                best_text = f"{best_finish}" if best_finish > 0 else "N/A"

                st.markdown(
                    f"""
                    <div style="background:#f8faf9;border-radius:10px;padding:14px 14px 12px 14px;
                                margin:4px 0;border-left:4px solid {border_color};border:1px solid #e4ece7;">
                        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                            <div style="font-weight:700;color:#163322;font-size:1.0rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                                {name}
                            </div>
                            <div style="font-weight:700;color:#1f2937;font-size:0.95rem;">
                                {metric_value}
                            </div>
                        </div>
                        <div style="font-size:0.72rem;color:#5f6b66;margin-top:2px;">{metric_label}</div>
                        <div style="display:flex;gap:14px;margin-top:10px;font-size:0.78rem;color:#334;">
                            <span><b>Cut:</b> {cut_rate * 100:.0f}%</span>
                            <span><b>Top-10:</b> {top10_rate * 100:.0f}%</span>
                            <span><b>Win:</b> {win_rate * 100:.0f}%</span>
                        </div>
                        <div style="display:flex;gap:14px;margin-top:4px;font-size:0.75rem;color:#4b5563;">
                            <span><b>SG Edge:</b> {sg_text}</span>
                            <span><b>Best:</b> {best_text}</span>
                            <span><b>Starts:</b> {starts}</span>
                        </div>
                        <div style="font-size:0.72rem;color:#6b7280;margin-top:8px;">Why: {reason}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _zscore_numeric(values: pd.Series) -> pd.Series:
    """Standard z-score with safe fallbacks for sparse/constant vectors."""
    s = pd.to_numeric(values, errors="coerce")
    if s.notna().sum() < 2:
        return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
    mu = s.mean()
    sigma = s.std(ddof=0)
    if not np.isfinite(sigma) or sigma < 1e-9:
        return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
    return (s - mu) / sigma


def build_enhanced_recent_form_for_field(field_df: pd.DataFrame, lookback_events: int = 10) -> pd.DataFrame:
    """
    Blend model form signals with actual recent historical performance.

    Returns one row per field player with confidence-adjusted actual form,
    model form baseline, enhanced form percentile, and diagnostic deltas.
    """
    if field_df is None or field_df.empty or "player_name" not in field_df.columns:
        return pd.DataFrame()

    lookback_events = int(max(4, min(20, lookback_events)))
    history = load_historical_player_event_results()
    if history.empty:
        return pd.DataFrame()

    work = field_df.copy()
    work["name_key"] = work["player_name"].apply(_name_key)
    work = work[work["name_key"] != ""].copy()
    if work.empty:
        return pd.DataFrame()

    field_keys = set(work["name_key"].tolist())
    hist = history[history["name_key"].isin(field_keys)].copy()
    if hist.empty:
        return pd.DataFrame()

    hist["year_num"] = pd.to_numeric(hist["year"], errors="coerce")
    hist["finish_num"] = pd.to_numeric(hist["finish_num"], errors="coerce")
    hist["finish_valid"] = hist["finish_num"].where(hist["finish_num"] < 900, np.nan)
    hist["sg_total_event"] = pd.to_numeric(hist["sg_total_event"], errors="coerce")
    hist["made_cut"] = pd.to_numeric(hist["made_cut"], errors="coerce")
    hist["top10"] = pd.to_numeric(hist["top10"], errors="coerce")

    rows = []
    for key, grp in hist.groupby("name_key"):
        recent = (
            grp.sort_values(["year_num", "tournament_id"], ascending=[False, False], na_position="last")
            .drop_duplicates(subset=["tournament_id"], keep="first")
            .head(lookback_events)
            .copy()
        )
        if recent.empty:
            continue

        sg_vals = pd.to_numeric(recent["sg_total_event"], errors="coerce").dropna()
        finish_vals = pd.to_numeric(recent["finish_valid"], errors="coerce").dropna()
        cut_vals = pd.to_numeric(recent["made_cut"], errors="coerce").dropna()
        top10_vals = pd.to_numeric(recent["top10"], errors="coerce").dropna()

        slope = np.nan
        trend_base = recent.sort_values(["year_num", "tournament_id"], ascending=[True, True], na_position="last")
        trend_sg = pd.to_numeric(trend_base["sg_total_event"], errors="coerce").dropna().values
        if len(trend_sg) >= 2:
            x = np.arange(len(trend_sg), dtype=float)
            try:
                slope = float(np.polyfit(x, trend_sg, 1)[0])
            except Exception:
                slope = np.nan

        rows.append(
            {
                "name_key": key,
                "actual_events": int(len(recent)),
                "actual_events_with_sg": int(len(sg_vals)),
                "actual_avg_sg": float(sg_vals.mean()) if len(sg_vals) else np.nan,
                "actual_sg_trend": slope,
                "actual_avg_finish": float(finish_vals.mean()) if len(finish_vals) else np.nan,
                "actual_finish_std": float(finish_vals.std(ddof=0)) if len(finish_vals) > 1 else np.nan,
                "actual_cut_rate": float(cut_vals.mean()) if len(cut_vals) else np.nan,
                "actual_top10_rate": float(top10_vals.mean()) if len(top10_vals) else np.nan,
            }
        )

    actual_df = pd.DataFrame(rows)
    if actual_df.empty:
        return pd.DataFrame()

    merged = work.merge(actual_df, on="name_key", how="left")

    merged["actual_events"] = pd.to_numeric(merged["actual_events"], errors="coerce").fillna(0)
    merged["actual_events_with_sg"] = pd.to_numeric(merged["actual_events_with_sg"], errors="coerce").fillna(0)
    merged["actual_sg_coverage"] = np.where(
        merged["actual_events"] > 0,
        merged["actual_events_with_sg"] / merged["actual_events"],
        0.0,
    ).clip(0.0, 1.0)
    merged["actual_confidence"] = (
        (np.log1p(merged["actual_events"]) / np.log1p(float(lookback_events)))
        * (0.6 + 0.4 * merged["actual_sg_coverage"])
    ).clip(0.0, 1.0)

    # Model-form baseline from existing prediction columns (dynamic by availability).
    model_components = [
        ("form_trend", 0.40, True),
        ("recent_top10s", 0.20, True),
        ("recent_cuts_pct", 0.20, True),
        ("hot_hand_score", 0.10, True),
        ("finish_consistency", 0.10, False),  # lower is better
    ]
    model_raw = pd.Series(np.zeros(len(merged)), index=merged.index, dtype=float)
    model_w = 0.0
    for col, weight, higher_is_better in model_components:
        if col not in merged.columns:
            continue
        z = _zscore_numeric(merged[col])
        model_raw += (z if higher_is_better else -z) * float(weight)
        model_w += float(weight)
    if model_w > 0:
        model_raw = model_raw / model_w
    merged["model_form_raw"] = model_raw

    # Actual recent-form signal.
    actual_components = [
        ("actual_avg_sg", 0.45, True),
        ("actual_sg_trend", 0.20, True),
        ("actual_top10_rate", 0.20, True),
        ("actual_cut_rate", 0.10, True),
        ("actual_avg_finish", 0.05, False),  # lower is better
    ]
    actual_raw = pd.Series(np.zeros(len(merged)), index=merged.index, dtype=float)
    actual_w = 0.0
    for col, weight, higher_is_better in actual_components:
        if col not in merged.columns:
            continue
        z = _zscore_numeric(merged[col])
        actual_raw += (z if higher_is_better else -z) * float(weight)
        actual_w += float(weight)
    if actual_w > 0:
        actual_raw = actual_raw / actual_w
    merged["actual_form_raw"] = actual_raw
    merged["actual_form_conf"] = merged["actual_form_raw"] * merged["actual_confidence"]

    merged["enhanced_form_raw"] = 0.65 * merged["model_form_raw"] + 0.35 * merged["actual_form_conf"]
    merged["model_form_pct"] = merged["model_form_raw"].rank(pct=True) * 100.0
    merged["enhanced_form_pct"] = merged["enhanced_form_raw"].rank(pct=True) * 100.0
    merged["form_lift_pts"] = merged["enhanced_form_pct"] - merged["model_form_pct"]

    # Diagnostic: model recent cut rate vs actual recent cut rate.
    if "recent_cuts_pct" in merged.columns:
        merged["model_vs_actual_cut_delta_pts"] = (
            (pd.to_numeric(merged["recent_cuts_pct"], errors="coerce") - pd.to_numeric(merged["actual_cut_rate"], errors="coerce"))
            * 100.0
        )
    else:
        merged["model_vs_actual_cut_delta_pts"] = np.nan

    return merged


def build_enhanced_course_fit_for_field(field_df: pd.DataFrame, course_key: str) -> pd.DataFrame:
    """
    Blend model course fit (dg_fit_total) with actual historical performance at the exact course.

    Returns one row per field player with:
    - actual course metrics (starts, cut rate, top-10 rate, avg finish, event SG)
    - confidence-adjusted actual signal
    - enhanced course-fit percentile and lift vs model-only fit
    """
    if field_df is None or field_df.empty or not course_key:
        return pd.DataFrame()

    if "player_name" not in field_df.columns:
        return pd.DataFrame()

    history = load_historical_player_event_results()
    if history.empty:
        return pd.DataFrame()

    out = field_df.copy()
    out["name_key"] = out["player_name"].apply(_name_key)
    out = out[out["name_key"] != ""].copy()
    if out.empty:
        return pd.DataFrame()

    field_keys = set(out["name_key"].tolist())
    hist = history[
        (history["course_key"] == str(course_key).strip())
        & (history["name_key"].isin(field_keys))
    ].copy()
    if hist.empty:
        return pd.DataFrame()

    hist["year_num"] = pd.to_numeric(hist["year"], errors="coerce")
    hist["finish_num"] = pd.to_numeric(hist["finish_num"], errors="coerce")
    hist["finish_valid"] = hist["finish_num"].where(hist["finish_num"] < 900, np.nan)
    hist["sg_total_event"] = pd.to_numeric(hist["sg_total_event"], errors="coerce")
    hist["made_cut"] = hist["made_cut"].astype(float)
    hist["top10"] = hist["top10"].astype(float)

    agg = (
        hist.groupby("name_key", as_index=False)
        .agg(
            actual_starts=("tournament_id", "nunique"),
            actual_made_cut_rate=("made_cut", "mean"),
            actual_top10_rate=("top10", "mean"),
            actual_avg_finish=("finish_valid", "mean"),
            actual_best_finish=("finish_valid", "min"),
            actual_sg_avg=("sg_total_event", "mean"),
            actual_sg_std=("sg_total_event", "std"),
            actual_last_year=("year_num", "max"),
        )
    )

    trend_rows = []
    for key, grp in hist.groupby("name_key"):
        g = grp.sort_values("year_num")
        vals = pd.to_numeric(g["sg_total_event"], errors="coerce").dropna().values
        slope = np.nan
        if len(vals) >= 2:
            x = np.arange(len(vals), dtype=float)
            try:
                slope = float(np.polyfit(x, vals, 1)[0])
            except Exception:
                slope = np.nan
        trend_rows.append({"name_key": key, "actual_sg_trend": slope})
    trend_df = pd.DataFrame(trend_rows)
    agg = agg.merge(trend_df, on="name_key", how="left")

    merged = out.merge(agg, on="name_key", how="left")
    merged["actual_starts"] = pd.to_numeric(merged["actual_starts"], errors="coerce").fillna(0)
    merged["actual_confidence"] = (
        np.log1p(merged["actual_starts"]) / np.log(6.0)
    ).clip(0.0, 1.0)

    z_sg = _zscore_numeric(merged["actual_sg_avg"])
    z_finish = -_zscore_numeric(merged["actual_avg_finish"])  # lower finish is better
    z_top10 = _zscore_numeric(merged["actual_top10_rate"])

    merged["actual_signal_raw"] = 0.55 * z_sg + 0.30 * z_finish + 0.15 * z_top10
    merged["actual_signal_conf"] = merged["actual_signal_raw"] * merged["actual_confidence"]

    if "dg_fit_total" in merged.columns:
        z_dg = _zscore_numeric(merged["dg_fit_total"])
        merged["dg_fit_pct"] = pd.to_numeric(merged["dg_fit_total"], errors="coerce").rank(pct=True) * 100.0
    else:
        z_dg = pd.Series(np.zeros(len(merged)), index=merged.index, dtype=float)
        merged["dg_fit_pct"] = np.nan

    merged["enhanced_fit_raw"] = 0.60 * z_dg + 0.40 * merged["actual_signal_conf"]
    merged["actual_fit_pct"] = merged["actual_signal_conf"].rank(pct=True) * 100.0
    merged["enhanced_fit_pct"] = merged["enhanced_fit_raw"].rank(pct=True) * 100.0
    merged["fit_lift_pts"] = merged["enhanced_fit_pct"] - merged["dg_fit_pct"]

    return merged


def render_course_specific_stats(df: pd.DataFrame):
    """
    Render course-specific statistics.

    WHAT IT SHOWS:
    - Historical performance at the current course
    - Similar courses analysis
    - Course fit metrics (how well player's game fits the course)
    """
    st.markdown("### Course-Specific Analysis")
    _ctx = resolve_players_page_tournament_context(df)
    _ctx_tname = str(_ctx.get("tournament_name", "")).strip()
    _ctx_tid = str(_ctx.get("tournament_id", "")).strip().upper()
    _ctx_cname = str(_ctx.get("course_name", "")).strip()
    _ctx_ckey = str(_ctx.get("course_key", "")).strip()
    if _ctx_cname:
        _ctx_bits = []
        if _ctx_tname:
            _ctx_bits.append(_ctx_tname)
        if _ctx_tid:
            _ctx_bits.append(_ctx_tid)
        _ctx_bits.append(_ctx_cname)
        st.caption("Resolved context: " + " • ".join(_ctx_bits))
    enhanced_df = build_enhanced_course_fit_for_field(df, _ctx_ckey) if _ctx_ckey else pd.DataFrame()

    # --- Section 0: Top Course Fits Visual Cards ---
    fit_cols = ["dg_fit_total", "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt"]
    if not enhanced_df.empty:
        st.markdown("#### 🎯 Best Course Fits")
        st.caption("Blended ranking: model course fit + actual exact-course results (confidence-weighted).")

        top3_fits = enhanced_df.sort_values("enhanced_fit_pct", ascending=False).head(3)
        fit_cols = st.columns(3)

        for i, (_, player) in enumerate(top3_fits.iterrows()):
            with fit_cols[i]:
                name = str(player.get("player_name", "Unknown"))[:18]
                enhanced_pct = pd.to_numeric(player.get("enhanced_fit_pct"), errors="coerce")
                model_pct = pd.to_numeric(player.get("dg_fit_pct"), errors="coerce")
                lift_pts = pd.to_numeric(player.get("fit_lift_pts"), errors="coerce")
                starts = int(pd.to_numeric(player.get("actual_starts"), errors="coerce") or 0)
                confidence = pd.to_numeric(player.get("actual_confidence"), errors="coerce")
                avg_sg = pd.to_numeric(player.get("actual_sg_avg"), errors="coerce")
                top10_rate = pd.to_numeric(player.get("actual_top10_rate"), errors="coerce")

                rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
                rank_labels = ["1st", "2nd", "3rd"]

                enhanced_str = f"{enhanced_pct:.1f}%" if pd.notna(enhanced_pct) else "—"
                model_str = f"{model_pct:.1f}%" if pd.notna(model_pct) else "—"
                lift_str = f"{lift_pts:+.1f}" if pd.notna(lift_pts) else "—"
                conf_str = f"{confidence:.2f}" if pd.notna(confidence) else "0.00"
                sg_str = f"{avg_sg:+.2f}" if pd.notna(avg_sg) else "—"
                t10_str = f"{(top10_rate * 100):.0f}%" if pd.notna(top10_rate) else "—"

                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px; padding: 16px; margin: 4px 0;
                            border: 2px solid {rank_colors[i]}; text-align: center;">
                    <div style="display: inline-block; background: {rank_colors[i]}; color: #000;
                                padding: 2px 10px; border-radius: 12px; font-size: 0.8em;
                                font-weight: bold; margin-bottom: 8px;">{rank_labels[i]}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1.1em; margin: 8px 0;">{name}</div>
                    <div style="color: #00C853; font-size: 1.35em; font-weight: bold;">{enhanced_str}</div>
                    <div style="color: #888; font-size: 0.75em; margin-top: 4px;">Enhanced Fit Percentile</div>
                    <div style="display:flex;justify-content:space-between;margin-top:10px;
                                padding-top:10px;border-top:1px solid #2a2a4a;font-size:0.78em;color:#c9d6ea;">
                        <span>Model: <b>{model_str}</b></span>
                        <span>Lift: <b>{lift_str}</b></span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:0.75em;color:#9fb0c7;">
                        <span>Starts: <b>{starts}</b></span>
                        <span>Conf: <b>{conf_str}</b></span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:0.75em;color:#9fb0c7;">
                        <span>Avg SG: <b>{sg_str}</b></span>
                        <span>Top-10: <b>{t10_str}</b></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
    elif "dg_fit_total" in df.columns:
        st.markdown("#### 🎯 Best Course Fits")
        st.caption("Players whose game best matches this course (model-only fallback).")

        top3_fits = df.nlargest(3, "dg_fit_total")
        fit_cols = st.columns(3)

        for i, (_, player) in enumerate(top3_fits.iterrows()):
            with fit_cols[i]:
                name = player.get("player_name", "Unknown")[:18]
                fit_total = player.get("dg_fit_total", 0) or 0
                fit_str = f"+{fit_total:.2f}" if fit_total >= 0 else f"{fit_total:.2f}"

                # Get individual fits
                ott_fit = player.get("dg_fit_ott", 0) or 0
                app_fit = player.get("dg_fit_app", 0) or 0
                arg_fit = player.get("dg_fit_arg", 0) or 0
                putt_fit = player.get("dg_fit_putt", 0) or 0

                # Ranking badge
                rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
                rank_labels = ["1st", "2nd", "3rd"]

                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px; padding: 16px; margin: 4px 0;
                            border: 2px solid {rank_colors[i]}; text-align: center;">
                    <div style="display: inline-block; background: {rank_colors[i]}; color: #000;
                                padding: 2px 10px; border-radius: 12px; font-size: 0.8em;
                                font-weight: bold; margin-bottom: 8px;">{rank_labels[i]}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1.1em; margin: 8px 0;">{name}</div>
                    <div style="color: #00C853; font-size: 1.4em; font-weight: bold;">{fit_str}</div>
                    <div style="color: #888; font-size: 0.75em; margin-top: 4px;">Course Fit Score</div>
                    <div style="display: flex; justify-content: space-around; margin-top: 10px;
                                padding-top: 10px; border-top: 1px solid #2a2a4a;">
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if ott_fit >= 0 else "#F44336"}; font-size: 0.9em;">{ott_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">OTT</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if app_fit >= 0 else "#F44336"}; font-size: 0.9em;">{app_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">APP</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if arg_fit >= 0 else "#F44336"}; font-size: 0.9em;">{arg_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">ARG</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if putt_fit >= 0 else "#F44336"}; font-size: 0.9em;">{putt_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">PUTT</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")


    # --- Section 2: Course Fit Analysis ---
    st.markdown("#### Course Fit Score")
    st.caption("How well does each player's game fit this course?")

    fit_cols = ["dg_fit_total", "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt"]
    available_fit = [col for col in fit_cols if col in df.columns]

    if available_fit and "dg_fit_total" in df.columns:
        # Top course fits
        top_fits = df.nlargest(15, "dg_fit_total")[["player_name"] + available_fit].copy()

        # Round values
        for col in available_fit:
            if col in top_fits.columns:
                top_fits[col] = top_fits[col].round(2)

        # Rename columns
        fit_names = {
            "player_name": "Player",
            "dg_fit_total": "Total Fit",
            "dg_fit_ott": "OTT Fit",
            "dg_fit_app": "APP Fit",
            "dg_fit_arg": "ARG Fit",
            "dg_fit_putt": "Putt Fit"
        }
        top_fits = top_fits.rename(columns={k: v for k, v in fit_names.items() if k in top_fits.columns})

        st.dataframe(top_fits, hide_index=True, use_container_width=True)

        # Explain course fit
        st.info("""
        **Course Fit Score** predicts how well a player's strengths match this course:
        - **Positive** = Player's game suits this course
        - **Negative** = Course exposes player's weaknesses
        - Based on historical correlations between SG categories and performance at this venue
        """)

    # --- Section 3: Enhanced Course Fit (Model + Actual Results) ---
    st.markdown("#### Enhanced Course Fit (Model + Actual Results)")
    st.caption("Blends model course-fit with actual historical results at this exact course.")

    if not _ctx_ckey:
        st.info("Exact-course mapping missing for this tournament. Add mapping in `data/reference/tournament_courses.json`.")
    else:
        if enhanced_df.empty:
            st.info("No historical exact-course results found for current field players.")
        else:
            _covered = int((pd.to_numeric(enhanced_df["actual_starts"], errors="coerce").fillna(0) > 0).sum())
            _avg_starts = float(pd.to_numeric(enhanced_df["actual_starts"], errors="coerce").fillna(0).mean())
            _best_row = enhanced_df.sort_values("enhanced_fit_pct", ascending=False).iloc[0]
            _lift_row = enhanced_df.sort_values("fit_lift_pts", ascending=False).iloc[0]

            _ec1, _ec2, _ec3, _ec4 = st.columns(4)
            with _ec1:
                st.metric("Players With Course Results", f"{_covered}/{len(enhanced_df)}")
            with _ec2:
                st.metric("Avg Starts (Field)", f"{_avg_starts:.1f}")
            with _ec3:
                st.metric("Top Enhanced Fit", str(_best_row.get("player_name", "—")))
            with _ec4:
                _lift_name = str(_lift_row.get("player_name", "—"))
                _lift_pts = pd.to_numeric(_lift_row.get("fit_lift_pts"), errors="coerce")
                st.metric("Biggest Positive Lift", f"{_lift_name}", f"{_lift_pts:+.1f} pts" if pd.notna(_lift_pts) else None)

            _plot_df = enhanced_df.copy()
            _plot_df["actual_starts"] = pd.to_numeric(_plot_df["actual_starts"], errors="coerce").fillna(0)
            _plot_df["enhanced_fit_pct"] = pd.to_numeric(_plot_df["enhanced_fit_pct"], errors="coerce")
            _plot_df["dg_fit_pct"] = pd.to_numeric(_plot_df["dg_fit_pct"], errors="coerce")
            _plot_df["fit_lift_pts"] = pd.to_numeric(_plot_df["fit_lift_pts"], errors="coerce")
            _plot_df = _plot_df[_plot_df["enhanced_fit_pct"].notna()]

            if not _plot_df.empty:
                fig_blend = px.scatter(
                    _plot_df,
                    x="dg_fit_pct",
                    y="enhanced_fit_pct",
                    size="actual_starts",
                    color="fit_lift_pts",
                    hover_name="player_name",
                    hover_data={
                        "actual_starts": True,
                        "actual_sg_avg": ":.2f",
                        "actual_avg_finish": ":.1f",
                        "actual_top10_rate": ":.2%",
                        "actual_confidence": ":.2f",
                        "dg_fit_pct": ":.1f",
                        "enhanced_fit_pct": ":.1f",
                        "fit_lift_pts": ":+.1f",
                    },
                    color_continuous_scale="RdYlGn",
                    labels={
                        "dg_fit_pct": "Model Course-Fit Percentile",
                        "enhanced_fit_pct": "Enhanced Course-Fit Percentile",
                        "fit_lift_pts": "Lift (pts)",
                    },
                    title="Enhanced vs Model-Only Course Fit",
                )
                fig_blend.add_shape(
                    type="line",
                    x0=0, y0=0, x1=100, y1=100,
                    line=dict(color="#8093ad", width=1, dash="dot"),
                )
                fig_blend.update_layout(
                    height=360,
                    margin=dict(t=40, b=10, l=10, r=10),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#dde6f5",
                )
                st.plotly_chart(fig_blend, use_container_width=True)

            _table = enhanced_df.copy()
            _table = _table.sort_values("enhanced_fit_pct", ascending=False)
            _table = _table[[
                "player_name",
                "actual_starts",
                "actual_made_cut_rate",
                "actual_top10_rate",
                "actual_avg_finish",
                "actual_sg_avg",
                "actual_sg_trend",
                "actual_confidence",
                "dg_fit_pct",
                "enhanced_fit_pct",
                "fit_lift_pts",
            ]].rename(columns={
                "player_name": "Player",
                "actual_starts": "Starts",
                "actual_made_cut_rate": "Cut %",
                "actual_top10_rate": "Top-10 %",
                "actual_avg_finish": "Avg Finish",
                "actual_sg_avg": "Avg SG",
                "actual_sg_trend": "SG Trend",
                "actual_confidence": "Confidence",
                "dg_fit_pct": "Model Fit %",
                "enhanced_fit_pct": "Enhanced Fit %",
                "fit_lift_pts": "Lift",
            })
            st.dataframe(
                _table,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Cut %": st.column_config.ProgressColumn("Cut %", min_value=0.0, max_value=1.0, format="%.0f%%"),
                    "Top-10 %": st.column_config.ProgressColumn("Top-10 %", min_value=0.0, max_value=1.0, format="%.0f%%"),
                    "Confidence": st.column_config.ProgressColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                    "Avg Finish": st.column_config.NumberColumn("Avg Finish", format="%.1f"),
                    "Avg SG": st.column_config.NumberColumn("Avg SG", format="%+.2f"),
                    "SG Trend": st.column_config.NumberColumn("SG Trend", format="%+.3f"),
                    "Model Fit %": st.column_config.NumberColumn("Model Fit %", format="%.1f"),
                    "Enhanced Fit %": st.column_config.NumberColumn("Enhanced Fit %", format="%.1f"),
                    "Lift": st.column_config.NumberColumn("Lift", format="%+.1f"),
                },
            )

    # --- Section 3: Course History vs Current Form ---
    st.markdown("#### Experience + Form Combo")
    st.caption("Best combination of course experience AND current form")

    if "hist_times_played" in df.columns and "form_trend" in df.columns:
        # Create combo score
        combo_df = df.copy()
        combo_df["has_history"] = combo_df["hist_times_played"] > 0

        # Filter to players with history
        experienced = combo_df[combo_df["has_history"]].copy()

        if not experienced.empty:
            # Scatter: experience vs form
            fig = px.scatter(
                experienced,
                x="hist_times_played",
                y="form_trend",
                size="hist_top10s" if "hist_top10s" in experienced.columns else None,
                hover_data=["player_name", "hist_avg_finish"],
                title="Course Experience vs Current Form",
                labels={
                    "hist_times_played": "Times Played at Course",
                    "form_trend": "Current Form Trend"
                }
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# SIDEBAR
# ============================================================================

# Sidebar header
st.sidebar.markdown("## ⛳ Golf Fantasy")
st.sidebar.markdown("---")

# Navigation (consolidated)
page = st.sidebar.radio(
    "📍 Navigation",
    ["🏆 This Week", "💬 Assistant", "🎰 Betting", "👤 Players", "📊 Predictions", "🔴 Live", "📋 My Picks", "⚙️ Pipeline"],
    label_visibility="collapsed"
)

# Quick stats in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Quick Stats")

usage_data = load_usage_data()
picks = usage_data.get("picks", {})
total_picks = sum(p.get("times_used", 0) for p in picks.values())
season_earnings = int(usage_data.get("summary", {}).get("total_earnings", 0) or 0)

# Pull accurate week count from season_log
_sl_path = OUTPUTS_DIR / "season_log.csv"
if _sl_path.exists():
    try:
        _sl = pd.read_csv(_sl_path)
        _current_week = int(_sl["week"].max()) if not _sl.empty else 0
        _logged_weeks = int(_sl["week"].nunique()) if "week" in _sl.columns and not _sl.empty else 0
    except Exception:
        _current_week = total_picks // 3
        _logged_weeks = int(len((usage_data.get("weekly_lineups") or {})))
else:
    _current_week = total_picks // 3
    _logged_weeks = int(len((usage_data.get("weekly_lineups") or {})))

st.sidebar.metric("Week", f"{_current_week} of 30")
st.sidebar.metric("Weeks Logged", _logged_weeks)
st.sidebar.metric("Season Earnings", f"${season_earnings:,.0f}")
st.sidebar.metric("Players Used", len(picks))
st.sidebar.metric("Picks Made", f"{total_picks}/90")

st.sidebar.markdown("---")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%b %d, %Y %H:%M')}")


# ============================================================================
# PAGE: THIS WEEK (consolidated from Strategy Dashboard + This Week + Scoring Engine)
# ============================================================================

if page == "🏆 This Week":

    engine = load_scoring_engine(_scoring_engine_cache_key())

    if engine:
        tournament = engine.get_current_week_tournament()

        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            course_info = engine.tournament_courses.get(tournament, {})

            # ── Determine event tier ──────────────────────────────────────
            _is_standard = t.purse < 9_000_000
            _is_major = t.tournament_type in ("Major", "Signature", "WGC", "Players")
            _tier_label = "MAJOR / SIGNATURE" if _is_major else "STANDARD EVENT"
            _tier_pill = "pill-gold" if _is_major else "pill-blue"
            _course_type = course_info.get("course_type", "") if course_info else ""
            _course_note = course_info.get("notes", "") if course_info else ""

            # ── Rich tournament banner ────────────────────────────────────
            st.markdown(f"""
<div class="tourney-banner">
  <p class="tourney-name">{tournament}</p>
  <p class="tourney-meta">{t.course or t.location or "TBA"} &nbsp;·&nbsp; {t.start_date or ""}</p>
  <div class="tourney-pills">
    <span class="pill pill-green">⛳ Week {t.week} of 30</span>
    <span class="pill {_tier_pill}">{_tier_label}</span>
    <span class="pill pill-blue">${t.purse/1_000_000:.1f}M Purse</span>
    {"<span class='pill pill-gold'>🏆 USE ELITE PLAYERS</span>" if _is_major else "<span class='pill pill-red'>⚡ SAVE ELITE PLAYERS</span>"}
    {f"<span class='pill pill-blue'>{_course_type}</span>" if _course_type else ""}
  </div>
  {f"<p style='color:#4a6080;font-size:12px;margin:10px 0 0 0;'>💡 {_course_note}</p>" if _course_note else ""}
</div>
""", unsafe_allow_html=True)
            
            
            
            
            # ── At-a-Glance Summary Strip ─────────────────────────────────
            # Four quick-read tiles: round status, your picks + live positions,
            # top recommended bet, and your season standing. Everything you need
            # to know at a glance before diving into the details below.
            # Note: _field_id is resolved later; we use None here and fill in below.
            _gl_meta_path = None

            # 1. Round status from meta JSON
            _gl_round_label  = "Pre-Tournament"
            _gl_status_label = "Not started"
            _gl_status_color = "#4a6080"
            if _gl_meta_path and Path(_gl_meta_path).exists():
                try:
                    _gl_meta = json.loads(Path(_gl_meta_path).read_text())
                    _gl_rnum = int(_gl_meta.get("current_round", 0))
                    _gl_rs   = _gl_meta.get("round_status", "")
                    if _gl_rnum > 0:
                        _gl_round_label = f"Round {_gl_rnum} of 4"
                    _gl_status_label = _gl_rs or "Scheduled"
                    _gl_status_color = (
                        "#00c44f" if "progress" in _gl_rs.lower()
                        else "#ffa726" if "official" in _gl_rs.lower()
                        else "#4a6080"
                    )
                except Exception:
                    pass

            # 2. My picks + live positions (last name + pos + score)
            _gl_picks_html = "<span style='color:#4a6080;'>No picks recorded</span>"
            _gl_tracker_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
            _gl_lb_path = None  # filled in after _field_id resolves below
            if _gl_tracker_path.exists():
                try:
                    _gl_td  = json.loads(_gl_tracker_path.read_text())
                    _gl_wks = _gl_td.get("weekly_lineups", {})
                    _gl_cur = _gl_wks.get(f"week_{max(int(k.split('_')[1]) for k in _gl_wks)}", {})
                    _gl_lineup = _gl_cur.get("lineup", [])
                    _gl_lb_df  = pd.read_csv(_gl_lb_path) if (_gl_lb_path and Path(_gl_lb_path).exists()) else pd.DataFrame()
                    _gl_parts  = []
                    for _gp in _gl_lineup:
                        _last = _gp.strip().split()[-1].lower()
                        _first_word = _gp.strip().split()[0]
                        if not _gl_lb_df.empty:
                            _m = _gl_lb_df[_gl_lb_df["player_name"].str.lower().str.contains(_last, na=False)]
                            if not _m.empty:
                                _mr = _m.iloc[0]
                                _gl_parts.append(
                                    f"<span style='color:#00c44f;font-weight:700'>{_last.title()}</span>"
                                    f" <span style='color:#dde6f5'>{_mr.get('position','?')} ({_mr.get('total','?')})</span>"
                                )
                                continue
                        _gl_parts.append(f"<span style='color:#dde6f5'>{_last.title()}</span>")
                    _gl_picks_html = " &nbsp;·&nbsp; ".join(_gl_parts) if _gl_parts else _gl_picks_html
                except Exception:
                    pass

            # 3. Top recommended bet (highest edge_pts)
            _gl_bet_label = "—"
            _gl_bets_path = DATA_DIR / "odds" / "recommended_bets_latest.csv"
            if _gl_bets_path.exists():
                try:
                    _gl_bets = pd.read_csv(_gl_bets_path)
                    if not _gl_bets.empty:
                        if "edge_pts" in _gl_bets.columns:
                            _gl_bets = _gl_bets.sort_values("edge_pts", ascending=False)
                        _tb = _gl_bets.iloc[0]
                        _pname = str(_tb.get("player_name", "?")).split(",")[0].strip()
                        _mkt   = str(_tb.get("market", "")).replace("top_", "Top ").replace("_", " ").title()
                        _odds  = _tb.get("book_odds", _tb.get("odds", ""))
                        _odds_str = f"+{int(_odds)}" if _odds and float(_odds) > 0 else str(int(_odds)) if _odds else ""
                        _gl_bet_label = f"{_pname} · {_mkt}" + (f" · {_odds_str}" if _odds_str else "")
                except Exception:
                    pass

            # 4. Season standing
            _gl_rank_label = "—"
            _gl_back_label = ""
            _gl_standings_path = DATA_DIR / "fantasy" / "league_standings.csv"
            if _gl_standings_path.exists():
                try:
                    _gl_st = pd.read_csv(_gl_standings_path)
                    _gl_me = _gl_st[_gl_st["team_name"] == "WineTime"]
                    if not _gl_me.empty:
                        _gl_rank_label = f"{_gl_me.iloc[0]['place']} of {len(_gl_st)}"
                        _gl_back_label = str(_gl_me.iloc[0].get("earnings_back", ""))
                except Exception:
                    pass

            st.markdown(
                f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;
            margin:12px 0 16px;padding:16px;
            background:#0b1929;border:1px solid #1a3050;border-radius:10px;">
  <div>
    <div style="font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;">ROUND STATUS</div>
    <div style="font-size:16px;font-weight:800;color:#dde6f5;">{_gl_round_label}</div>
    <div style="font-size:12px;color:{_gl_status_color};font-weight:600;">{_gl_status_label}</div>
  </div>
  <div>
    <div style="font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;">MY PICKS</div>
    <div style="font-size:13px;line-height:1.6;">{_gl_picks_html}</div>
  </div>
  <div>
    <div style="font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;">TOP BET</div>
    <div style="font-size:13px;font-weight:600;color:#dde6f5;">{_gl_bet_label}</div>
  </div>
  <div>
    <div style="font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;">SEASON RANK</div>
    <div style="font-size:16px;font-weight:800;color:#ffa726;">{_gl_rank_label}</div>
    <div style="font-size:11px;color:#4a6080;">{_gl_back_label} back</div>
  </div>
</div>""",
                unsafe_allow_html=True,
            )

            # Odds refresh button ------------
            _ref_col1, _ref_col2, _ref_col3 = st.columns([1, 1, 3])
            with _ref_col1:
                if st.button("🔄 Refresh Odds", use_container_width=True, type='primary'):
                    with st.spinner("Fetching latest odds from PGA Tour..."):
                        _ref_out = run_script("predictions/refresh_odds.py")
                    if "✅" in _ref_out:
                        st.success(_ref_out)
                        st.cache_data.clear()   # force reload of predictions on next render
                        st.rerun()
                    else:
                        st.error(_ref_out)
            with _ref_col2:
                # Show when odds were last refreshed
                _preds_check = OUTPUTS_DIR / "latest_predictions.csv"
                if _preds_check.exists():
                    try:
                        _last_odds = pd.read_csv(_preds_check, usecols=["odds_updated_at"]).iloc[0, 0]
                        st.caption(f"Last updated: {_last_odds}")
                    except Exception:
                        import os
                        from datetime import datetime as _dt
                        _mtime = _dt.fromtimestamp(os.path.getmtime(_preds_check)).strftime("%b %d %H:%M")
                        st.caption(f"File updated: {_mtime}")

            # ── Field status (compact, merged into odds bar) ───────────────
            _field_id = getattr(t, "tournament_id", None) or ""
            if not _field_id:
                try:
                    _sched_tmp = pd.read_csv(DATA_DIR / "raw" / "schedule_2026.csv")
                    _sched_row = _sched_tmp[_sched_tmp["tournament_name"] == tournament]
                    if not _sched_row.empty:
                        _field_id = str(_sched_row.iloc[0].get("tournament_id", "")).strip()
                except Exception:
                    pass
            # Fallback 2: partial name match against schedule CSV (normalize spaces/underscores)
            if not _field_id:
                try:
                    _sched_tmp2 = pd.read_csv(DATA_DIR / "raw" / "schedule_2026.csv")
                    _t_lower = tournament.lower().replace("_", " ")
                    for _, _row in _sched_tmp2.iterrows():
                        _sched_name = str(_row.get("tournament_name", "")).lower().replace("_", " ")
                        if _sched_name and (_sched_name in _t_lower or _t_lower in _sched_name):
                            _field_id = str(_row.get("tournament_id", "")).strip()
                            break
                except Exception:
                    pass
            # Fallback 3: most recently modified live meta file
            if not _field_id:
                import glob as _glob
                _metas = [Path(f) for f in _glob.glob(str(DATA_DIR / "live" / "leaderboard_r*_meta.json"))]
                if _metas:
                    _newest_meta = max(_metas, key=lambda f: f.stat().st_mtime)
                    try:
                        _meta_tid = json.loads(_newest_meta.read_text()).get("tournament_id", "")
                        if _meta_tid:
                            _field_id = _meta_tid
                    except Exception:
                        pass

            # Now that _field_id is resolved, fill in the at-a-glance paths
            if _field_id:
                _gl_meta_path = DATA_DIR / "live" / f"leaderboard_{_field_id.lower()}_meta.json"
                _gl_lb_path   = DATA_DIR / "live" / f"leaderboard_{_field_id.lower()}.csv"

            _field_file = None
            if _field_id:
                _canonical = DATA_DIR / "fields" / f"field_{_field_id}.csv"
                if _canonical.exists():
                    _field_file = _canonical

            # Build compact field status string for the odds bar
            import os as _os_fw
            from datetime import datetime as _dt_fw
            _field_status_str = ""
            _field_stale = False
            if _field_file and _field_file.exists():
                try:
                    _fw_n    = sum(1 for _ in open(_field_file)) - 1  # fast line count
                    _fw_age  = (_dt_fw.now().timestamp() - _os_fw.path.getmtime(_field_file)) / 3600
                    _field_stale = _fw_age > 72
                    _fw_age_str  = f"{int(_fw_age)}h ago" if _fw_age < 48 else f"{_fw_age/24:.0f}d ago"
                    _field_status_str = f"{'⚠️' if _field_stale else '✅'} {_fw_n} players · {_fw_age_str}"
                except Exception:
                    _field_status_str = "✅ Field loaded"
            else:
                _field_status_str = "⚠️ No field data"
                _field_stale = True

            with _ref_col3:
                _fc1, _fc2 = st.columns([2, 1])
                with _fc1:
                    st.caption(_field_status_str)
                    if _field_stale:
                        st.caption("Refresh recommended — predictions may be incomplete")
                with _fc2:
                    if _field_id and st.button("⛳ Fetch Field", use_container_width=True,
                                               help=f"Pull confirmed entry list for {_field_id}"):
                        with st.spinner("Fetching field..."):
                            _fw_out = run_script(
                                "scrapers/fetch_field_from_pgatour.py",
                                "--pga-id", _field_id, "--name", tournament,
                                "--output", f"data/fields/field_{_field_id}.csv",
                                "--match-ids",
                            )
                        if "Saved" in _fw_out or "✓" in _fw_out:
                            st.success("Updated")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed")

            # ── Withdrawal Alerts ─────────────────────────────────────────
            _wd_dir = DATA_DIR / "news"
            _wd_file = _wd_dir / f"withdrawals_{tournament}.json"
            if not _wd_file.exists():
                # Fallback to latest
                _wd_files = sorted(_wd_dir.glob("withdrawals_*.json"),
                                   key=lambda p: p.stat().st_mtime, reverse=True) if _wd_dir.exists() else []
                _wd_file = _wd_files[0] if _wd_files else None

            _wd_list = []
            if _wd_file and Path(_wd_file).exists():
                try:
                    with open(_wd_file) as _wdf:
                        _wd_list = json.load(_wdf)
                except Exception:
                    pass

            if _wd_list:
                _wd_names = [w["player_name"] for w in _wd_list]
                _pick_wds = [n for n in _wd_names if any(
                    n.lower() in str(p).lower() or str(p).lower() in n.lower()
                    for p in _this_week_picks
                )] if "_this_week_picks" in dir() else []

                for _pick_wd in _pick_wds:
                    st.error(f"🚨 Your pick **{_pick_wd}** has withdrawn from this event!")

                with st.expander(f"⚠️ Withdrawal Alerts — {len(_wd_names)} player(s)", expanded=bool(_pick_wds)):
                    for _wd in _wd_list:
                        _wd_src = "confirmed WD" if _wd.get("source") == "leaderboard" else "possible WD (missing from predictions)"
                        st.markdown(f"• **{_wd['player_name']}** — {_wd.get('status','WD')} ({_wd_src})")
                    _wd_col1, _wd_col2 = st.columns([3, 1])
                    with _wd_col2:
                        if st.button("🔄 Re-check WDs", key="wd_refresh_btn", use_container_width=True):
                            _wd_cmd = ["python3",
                                       str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_withdrawals.py"),
                                       "--tournament-id", str(tournament)]
                            import subprocess as _sp2
                            _sp2.run(_wd_cmd, capture_output=True, cwd=PROJECT_ROOT)
                            st.rerun()

            # ── Weather
            render_weather_widget(t.course or tournament, tid=str(_field_id))

            # ── Course Layout Charts ──────────────────────────────────────
            def _load_course_chars(tid_str: str, year: int) -> pd.DataFrame:
                chars_dir = DATA_DIR / "course_characteristics"
                # 1) Specific file for this year
                specific = chars_dir / f"r{tid_str.lower()}_{year}.csv"
                if specific.exists():
                    return pd.read_csv(specific)
                # 2) all_courses_{year}.csv filtered by tournament_id
                all_path = chars_dir / f"all_courses_{year}.csv"
                if all_path.exists():
                    df_all = pd.read_csv(all_path)
                    hit = df_all[df_all["tournament_id"].str.upper() == tid_str.upper()]
                    if not hit.empty:
                        return hit
                # 3) Fall back to previous year's same event number (same course)
                event_num = tid_str[-3:] if len(tid_str) >= 3 else ""
                if event_num:
                    for prev_year in range(year - 1, year - 4, -1):
                        prev_path = chars_dir / f"all_courses_{prev_year}.csv"
                        if prev_path.exists():
                            df_prev = pd.read_csv(prev_path)
                            hit = df_prev[df_prev["tournament_id"].str.endswith(event_num)]
                            if not hit.empty:
                                return hit
                return pd.DataFrame()

            _cc_tid = str(_field_id) if _field_id else ""
            try:
                _cc_year = int(_cc_tid[1:5]) if len(_cc_tid) >= 5 and _cc_tid[1:5].isdigit() else datetime.now().year
            except (ValueError, IndexError):
                _cc_year = datetime.now().year
            _cc_df = _load_course_chars(_cc_tid, _cc_year) if _cc_tid else pd.DataFrame()

            if not _cc_df.empty and "hole_num" in _cc_df.columns:
                with st.expander("Course Layout", expanded=False):
                    _cc_df = _cc_df.sort_values("hole_num").reset_index(drop=True).copy()
                    _cc_df["hole_num"] = _cc_df["hole_num"].astype(int)
                    for _c in ["hole_par", "hole_yards", "scoring_avg", "difficulty_rank"]:
                        if _c in _cc_df.columns:
                            _cc_df[_c] = pd.to_numeric(_cc_df[_c], errors="coerce")
                    _cc_df["scoring_diff"] = pd.to_numeric(
                        _cc_df["scoring_diff"].astype(str).str.replace("+", "", regex=False),
                        errors="coerce"
                    )
                    # Compute scoring distribution percentages
                    for _dc in ["eagles", "birdies", "pars", "bogeys", "double_bogeys"]:
                        if _dc in _cc_df.columns:
                            _cc_df[_dc] = pd.to_numeric(_cc_df[_dc], errors="coerce").fillna(0)
                    _has_dist = all(c in _cc_df.columns for c in ["birdies", "pars", "bogeys"])
                    if _has_dist:
                        _cc_df["_total"] = sum(_cc_df[c] for c in ["eagles","birdies","pars","bogeys","double_bogeys"] if c in _cc_df.columns).clip(lower=1)
                        for _dc, _lab in [("eagles","Eagle%"),("birdies","Birdie%"),("pars","Par%"),("bogeys","Bogey%"),("double_bogeys","Dbl+%")]:
                            if _dc in _cc_df.columns:
                                _cc_df[_lab] = (_cc_df[_dc] / _cc_df["_total"] * 100).round(1)

                    # Helper: value for a given hole number
                    def _cv(col, h):
                        rows = _cc_df[_cc_df["hole_num"] == h]
                        if rows.empty or col not in rows.columns:
                            return None
                        v = rows.iloc[0][col]
                        return None if pd.isna(v) else v

                    front9 = list(range(1, 10))
                    back9  = list(range(10, 19))
                    all18  = front9 + back9

                    # -- Difficulty rank color: rank 1 (hardest) = red, rank 18 (easiest) = green
                    def _rank_color(rank):
                        if rank is None: return "#2a3a4a"
                        r = max(1, min(18, int(rank)))
                        # 1=hardest→red, 18=easiest→green
                        pct = (r - 1) / 17.0
                        red = int(180 * (1 - pct))
                        grn = int(180 * pct)
                        return f"rgb({red+40},{grn+40},50)"

                    # -- Scoring diff color: negative=birdie-friendly (green), positive=bogey (red)
                    def _diff_color(diff):
                        if diff is None: return "#2a3a4a"
                        if diff < -0.15:   return "#1a4a2a"
                        elif diff < -0.05: return "#1e3a25"
                        elif diff < 0.05:  return "#1c2a3a"
                        elif diff < 0.15:  return "#3a1a1a"
                        else:              return "#4a1a1a"

                    def _diff_text_color(diff):
                        if diff is None: return "#6a84aa"
                        if diff < 0:  return "#4caf72"
                        elif diff > 0.05: return "#e57373"
                        else: return "#aabbcc"

                    # Build the scorecard HTML table
                    def _td(val, bg="#0d1a2e", color="#dde6f5", bold=False, small=False):
                        fw = "700" if bold else "400"
                        fs = "10px" if small else "12px"
                        return (f'<td style="text-align:center;padding:5px 2px;background:{bg};'
                                f'color:{color};font-weight:{fw};font-size:{fs};'
                                f'border:1px solid #0a1624;">{val}</td>')

                    def _th(val, bg="#060d1a", color="#4a6080"):
                        return (f'<td style="text-align:center;padding:5px 2px;background:{bg};'
                                f'color:{color};font-weight:700;font-size:10px;'
                                f'letter-spacing:.05em;border:1px solid #0a1624;">{val}</td>')

                    def _build_row(label, col, fmt_fn, sum_fn=None, label_col="#4a6080"):
                        cells = _th(label)
                        f9_vals = [_cv(col, h) for h in front9]
                        b9_vals = [_cv(col, h) for h in back9]
                        for h, v in zip(front9, f9_vals):
                            bg, tc = fmt_fn(v)
                            cells += _td("—" if v is None else (f"{v:.0f}" if v == int(v or 0) else f"{v:.1f}"), bg, tc)
                        # OUT summary
                        if sum_fn:
                            sv = sum_fn(f9_vals)
                            sbg, stc = fmt_fn(sv)
                            cells += _td("—" if sv is None else f"{sv:.0f}", sbg, stc, bold=True)
                        else:
                            cells += _th("OUT")
                        for h, v in zip(back9, b9_vals):
                            bg, tc = fmt_fn(v)
                            cells += _td("—" if v is None else (f"{v:.0f}" if v == int(v or 0) else f"{v:.1f}"), bg, tc)
                        # IN summary
                        if sum_fn:
                            sv = sum_fn(b9_vals)
                            sbg, stc = fmt_fn(sv)
                            cells += _td("—" if sv is None else f"{sv:.0f}", sbg, stc, bold=True)
                            # TOT
                            all_vals = f9_vals + b9_vals
                            tv = sum_fn(all_vals)
                            tbg, ttc = fmt_fn(tv)
                            cells += _td("—" if tv is None else f"{tv:.0f}", tbg, ttc, bold=True)
                        else:
                            cells += _th("IN")
                            cells += _th("TOT")
                        return f"<tr>{cells}</tr>"

                    # Header row
                    hdr = _th("HOLE", bg="#040a14", color="#6a84aa")
                    for h in front9:
                        hdr += _th(str(h), bg="#040a14", color="#dde6f5")
                    hdr += _th("OUT", bg="#040a14", color="#fff")
                    for h in back9:
                        hdr += _th(str(h), bg="#040a14", color="#dde6f5")
                    hdr += _th("IN", bg="#040a14", color="#fff")
                    hdr += _th("TOT", bg="#030810", color="#fff")

                    # PAR row
                    par_row = _th("PAR")
                    fp = [_cv("hole_par", h) for h in front9]
                    bp = [_cv("hole_par", h) for h in back9]
                    for v in fp:
                        par_row += _td("—" if v is None else int(v), "#0a1420", "#aabbcc")
                    par_row += _td(int(sum(v for v in fp if v)), "#060d1a", "#fff", bold=True)
                    for v in bp:
                        par_row += _td("—" if v is None else int(v), "#0a1420", "#aabbcc")
                    par_row += _td(int(sum(v for v in bp if v)), "#060d1a", "#fff", bold=True)
                    par_row += _td(int(sum(v for v in fp+bp if v)), "#030810", "#fff", bold=True)

                    # YARDS row
                    yds_row = _th("YDS")
                    fy = [_cv("hole_yards", h) for h in front9]
                    by = [_cv("hole_yards", h) for h in back9]
                    for v in fy:
                        yds_row += _td("—" if v is None else int(v), "#0a1420", "#7a90b8", small=True)
                    yds_row += _td(int(sum(v for v in fy if v)), "#060d1a", "#aabbcc", bold=True, small=True)
                    for v in by:
                        yds_row += _td("—" if v is None else int(v), "#0a1420", "#7a90b8", small=True)
                    yds_row += _td(int(sum(v for v in by if v)), "#060d1a", "#aabbcc", bold=True, small=True)
                    yds_row += _td(int(sum(v for v in fy+by if v)), "#030810", "#dde6f5", bold=True, small=True)

                    # AVG SCORE row
                    avg_row = _th("AVG")
                    for h in all18:
                        v = _cv("scoring_avg", h)
                        avg_row += _td("—" if v is None else f"{v:.2f}", "#0a1420", "#9aaabf", small=True)
                        if h == 9:
                            fa = [_cv("scoring_avg", hh) for hh in front9]
                            avg_row += _td(f"{sum(v for v in fa if v):.2f}", "#060d1a", "#aabbcc", bold=True, small=True)
                    ba = [_cv("scoring_avg", hh) for hh in back9]
                    avg_row += _td(f"{sum(v for v in ba if v):.2f}", "#060d1a", "#aabbcc", bold=True, small=True)
                    alls = [_cv("scoring_avg", hh) for hh in all18]
                    avg_row += _td(f"{sum(v for v in alls if v):.2f}", "#030810", "#dde6f5", bold=True, small=True)

                    # vs PAR row
                    diff_row = _th("vs PAR")
                    fd = [_cv("scoring_diff", h) for h in front9]
                    bd = [_cv("scoring_diff", h) for h in back9]
                    for v in fd:
                        bg = _diff_color(v); tc = _diff_text_color(v)
                        diff_row += _td("—" if v is None else f"{v:+.2f}", bg, tc, small=True)
                    fds = sum(v for v in fd if v is not None)
                    diff_row += _td(f"{fds:+.2f}", _diff_color(fds), _diff_text_color(fds), bold=True, small=True)
                    for v in bd:
                        bg = _diff_color(v); tc = _diff_text_color(v)
                        diff_row += _td("—" if v is None else f"{v:+.2f}", bg, tc, small=True)
                    bds = sum(v for v in bd if v is not None)
                    diff_row += _td(f"{bds:+.2f}", _diff_color(bds), _diff_text_color(bds), bold=True, small=True)
                    tds = fds + bds
                    diff_row += _td(f"{tds:+.2f}", _diff_color(tds), _diff_text_color(tds), bold=True, small=True)

                    # DIFFICULTY RANK row
                    rank_row = _th("RANK")
                    for h in all18:
                        v = _cv("difficulty_rank", h)
                        rank_row += _td("—" if v is None else int(v), _rank_color(v),
                                        "#fff" if v is not None else "#3a5070", small=True)
                        if h == 9:
                            rank_row += _th("")  # OUT spacer
                    rank_row += _th("")  # IN spacer
                    rank_row += _th("")  # TOT spacer

                    # BIRDIE% / BOGEY% rows (if distribution data available)
                    birdie_row = bogey_row = ""
                    if _has_dist:
                        birdie_row = _th("BIRDIE%")
                        bogey_row  = _th("BOGEY%")
                        fb = [_cv("Birdie%", h) for h in front9]
                        bb = [_cv("Birdie%", h) for h in back9]
                        fg = [_cv("Bogey%",  h) for h in front9]
                        bg2= [_cv("Bogey%",  h) for h in back9]
                        for v in fb:
                            birdie_row += _td("—" if v is None else f"{v:.0f}%", "#0d1a10", "#4caf72", small=True)
                        birdie_row += _th("")
                        for v in bb:
                            birdie_row += _td("—" if v is None else f"{v:.0f}%", "#0d1a10", "#4caf72", small=True)
                        birdie_row += _th("") + _th("")
                        for v in fg:
                            bogey_row += _td("—" if v is None else f"{v:.0f}%", "#1a0d0d", "#e57373", small=True)
                        bogey_row += _th("")
                        for v in bg2:
                            bogey_row += _td("—" if v is None else f"{v:.0f}%", "#1a0d0d", "#e57373", small=True)
                        bogey_row += _th("") + _th("")
                        birdie_row = f"<tr>{birdie_row}</tr>"
                        bogey_row  = f"<tr>{bogey_row}</tr>"

                    _sc_course = _cc_df.iloc[0].get("course_name", "") if not _cc_df.empty else ""
                    _sc_par    = _cc_df.iloc[0].get("course_par", "") if not _cc_df.empty else ""
                    _sc_yds    = _cc_df.iloc[0].get("course_yardage", "") if not _cc_df.empty else ""

                    st.markdown(f"""
<div style="overflow-x:auto;margin-bottom:8px;">
<div style="font-size:11px;color:#4a6080;margin-bottom:6px;">
  {_sc_course} &nbsp;·&nbsp; Par {_sc_par} &nbsp;·&nbsp; {_sc_yds} yds
</div>
<table style="border-collapse:collapse;width:100%;font-family:monospace;">
  <thead><tr>{hdr}</tr></thead>
  <tbody>
    <tr>{par_row}</tr>
    <tr>{yds_row}</tr>
    <tr>{avg_row}</tr>
    <tr>{diff_row}</tr>
    <tr>{rank_row}</tr>
    {birdie_row}
    {bogey_row}
  </tbody>
</table>
<div style="font-size:10px;color:#2e4060;margin-top:6px;">
  RANK: 1 = hardest &nbsp;·&nbsp; vs PAR: green = birdie-friendly, red = bogey-heavy
</div>
</div>
""", unsafe_allow_html=True)

            # ── Load predictions + usage data ────────────────────────────
            _preds_path = OUTPUTS_DIR / "latest_predictions.csv"
            _usage_path = OUTPUTS_DIR / "player_usage_tracker.csv"
            _preds = pd.DataFrame()
            _usage_dict = {}

            if _preds_path.exists():
                _preds = pd.read_csv(_preds_path)
                if _usage_path.exists():
                    _udf = pd.read_csv(_usage_path)
                    _usage_dict = dict(zip(_udf["player_name"], _udf["uses_remaining"]))
                _preds["uses_remaining"] = _preds["player_name"].map(lambda n: _usage_dict.get(n, 3))

            # ── Field Strength + Cut Line (combined expander) ─────────────
            if not _preds.empty and "world_rank" in _preds.columns:
                _wr_col = pd.to_numeric(_preds["world_rank"], errors="coerce").dropna()
                if len(_wr_col) >= 5:
                    _fa  = float(_wr_col.mean())
                    _fm  = float(_wr_col.median())
                    _t50 = int((_wr_col <= 50).sum())
                    if _fa < 30:   _fs_label, _fs_col = "Elite",   "#f1c40f"
                    elif _fa < 60: _fs_label, _fs_col = "Strong",  "#00c44f"
                    elif _fa < 90: _fs_label, _fs_col = "Average", "#4cb8ff"
                    else:          _fs_label, _fs_col = "Weak",    "#7f8c8d"

                    # Pre-calculate cut line for the expander label
                    _cut_str_lbl = ""
                    _cut_est_raw = None
                    if "recent_scoring_avg" in _preds.columns:
                        _sc_col = pd.to_numeric(_preds["recent_scoring_avg"], errors="coerce").dropna()
                        if len(_sc_col) >= 10:
                            _cut_est_raw = float(_sc_col.quantile(0.65))
                            _cut_vs_par  = round(_cut_est_raw - 72)
                            _cut_str_lbl = f" · Cut {_cut_vs_par:+d}"

                    
            # ── Tee Times ─────────────────────────────────────────────────
            try:
                # Load draw advantage + dedicated tee times CSVs (pre-tournament draw)
                _da_df = pd.DataFrame()
                _da_round = 1
                _tt_draw_df = pd.DataFrame()
                if _field_id:
                    for _r in [1, 2, 3, 4]:
                        _da_path = DATA_DIR / "live" / f"draw_advantage_{_field_id}_r{_r}.csv"
                        if _da_path.exists():
                            try:
                                _da_df = pd.read_csv(_da_path)
                                _da_round = _r
                            except Exception:
                                pass
                    for _r in [1, 2, 3, 4]:
                        _tt_draw_path = DATA_DIR / "live" / f"tee_times_{_field_id}_r{_r}.csv"
                        if _tt_draw_path.exists():
                            try:
                                _tt_draw_df = pd.read_csv(_tt_draw_path)
                                break
                            except Exception:
                                pass

                # Build _tt_valid: prefer dedicated tee_times CSV, fall back to leaderboard tee_time col
                _tt_valid = pd.DataFrame()
                if not _tt_draw_df.empty and "tee_time_str" in _tt_draw_df.columns:
                    _tt_valid = _tt_draw_df.rename(columns={"tee_time_str": "tee_time"}).copy()
                else:
                    _tt_files = sorted(
                        (DATA_DIR / "live").glob("leaderboard_r*.csv"),
                        key=lambda p: p.stat().st_mtime, reverse=True
                    ) if (DATA_DIR / "live").exists() else []
                    if _tt_files:
                        _tt_df = pd.read_csv(_tt_files[0])
                        if "tee_time" in _tt_df.columns and _tt_df["tee_time"].notna().any():
                            _tt_valid = _tt_df[_tt_df["tee_time"].astype(str).str.strip().ne("")].copy()

                if not _tt_valid.empty:
                    # Merge win_prob/world_rank from predictions
                    if not _preds.empty and "player_name" in _preds.columns and "win_prob" in _preds.columns:
                        _tt_valid = _tt_valid.merge(
                            _preds[["player_name", "win_prob", "world_rank"]],
                            on="player_name", how="left"
                        )

                    with st.expander("Tee Times", expanded=False):
                        # AM/PM summary banner if draw advantage available
                        if not _da_df.empty and "am_pm" in _da_df.columns and "window_avg_wind" in _da_df.columns:
                            _am_rows = _da_df[_da_df["am_pm"] == "AM"]["window_avg_wind"].dropna()
                            _pm_rows = _da_df[_da_df["am_pm"] == "PM"]["window_avg_wind"].dropna()
                            if not _am_rows.empty and not _pm_rows.empty:
                                _am_avg = _am_rows.mean()
                                _pm_avg = _pm_rows.mean()
                                _fav = "AM" if _am_avg < _pm_avg else "PM"
                                _fav_col = "#00c44f"
                                _dis_col = "#e74c3c"
                                _am_col = _fav_col if _fav == "AM" else _dis_col
                                _pm_col = _fav_col if _fav == "PM" else _dis_col
                                st.markdown(
                                    f"<div style='font-size:0.82rem;margin-bottom:8px;padding:6px 10px;"
                                    f"background:#1a1a2e;border-radius:6px;'>"
                                    f"<span style='color:{_am_col};font-weight:600;'>Morning (AM): {_am_avg:.0f} mph avg</span>"
                                    f"<span style='color:#888;margin:0 10px;'>|</span>"
                                    f"<span style='color:{_pm_col};font-weight:600;'>Afternoon (PM): {_pm_avg:.0f} mph avg</span>"
                                    f"<span style='color:#888;margin:0 10px;'>→</span>"
                                    f"<span style='color:{_fav_col};font-weight:700;'>{_fav} draw favored</span> (R{_da_round})"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                        # Merge draw advantage columns into display df
                        _has_da = (
                            not _da_df.empty
                            and "player_name" in _da_df.columns
                            and "draw_tier" in _da_df.columns
                        )
                        if _has_da:
                            _da_merge = _da_df[["player_name", "tee_time_str", "window_avg_wind", "draw_advantage", "draw_tier"]].copy()
                            _tt_valid = _tt_valid.merge(_da_merge, on="player_name", how="left")

                        _tt_groups = _tt_valid.groupby("tee_time", sort=True)
                        for _ttime, _tgroup in _tt_groups:
                            st.markdown(f"**{_ttime}**")
                            _tt_rows = []
                            for _, _tr in _tgroup.iterrows():
                                _pwin = float(_tr.get("win_prob", 0) or 0) * 100
                                _prank = _tr.get("world_rank")
                                _rank_s = f"#{int(_prank)}" if pd.notna(_prank) else "—"
                                _win_s  = f"{_pwin:.1f}%" if _pwin > 0 else "—"
                                _row = {
                                    "Player": str(_tr.get("player_name", "—")),
                                    "Rank":   _rank_s,
                                    "Win%":   _win_s,
                                }
                                if _has_da:
                                    _tier = str(_tr.get("draw_tier", "") or "")
                                    _wind = _tr.get("window_avg_wind")
                                    _wind_s = f"{_wind:.0f} mph" if pd.notna(_wind) else "—"
                                    _tier_display = {
                                        "Strong Adv": "++ Calm",
                                        "Adv": "+ Calm",
                                        "Neutral": "~",
                                        "Disadv": "- Wind",
                                        "Strong Disadv": "-- Wind",
                                    }.get(_tier, _tier or "—")
                                    _row["Wind"] = _wind_s
                                    _row["Draw"] = _tier_display
                                _tt_rows.append(_row)
                            st.dataframe(pd.DataFrame(_tt_rows), hide_index=True,
                                         use_container_width=True)
            except Exception:
                pass


            # ── Elite SAVE list ──────────────────────────────────────────
            _elite_save = []
            if _is_standard and not _preds.empty and "world_rank" in _preds.columns:
                _elite_save = (
                    _preds[(_preds["world_rank"] <= 20) & (_preds["uses_remaining"] > 0)]
                    .nsmallest(5, "world_rank")["player_name"].tolist()
                )

            # ── Identify top USE picks (model rank, exclude saves + maxed) ──
            _avail = _preds[_preds["uses_remaining"] > 0].copy() if not _preds.empty else pd.DataFrame()
            if _is_standard and _elite_save and not _avail.empty:
                _avail = _avail[~_avail["player_name"].isin(_elite_save)]
            _ev_col = "expected_value" if ("expected_value" in _avail.columns and not _avail.empty) else None
            _model_top3 = _avail.nlargest(3, _ev_col) if _ev_col else _avail.head(3)

            # ── Load actual picks this week from season log ──────────────
            _this_week_picks = []
            _log_path = OUTPUTS_DIR / "season_log.csv"
            if _log_path.exists():
                try:
                    _log = pd.read_csv(_log_path)
                    _week_row = _log[_log["week"] == t.week]
                    if not _week_row.empty:
                        _wr = _week_row.iloc[0]
                        for _pc in ["pick1", "pick2", "pick3"]:
                            if _pc in _wr and pd.notna(_wr[_pc]) and str(_wr[_pc]).strip():
                                _this_week_picks.append(str(_wr[_pc]).strip())
                except Exception:
                    pass

            # ── YOUR LINEUP ──────────────────────────────────────────────
            st.markdown("<div class='lineup-label'>⛳ YOUR LINEUP THIS WEEK</div>", unsafe_allow_html=True)

            _slot_cols = st.columns(3)
            for _si, _scol in enumerate(_slot_cols):
                with _scol:
                    # Check if pick is made for this slot
                    if _si < len(_this_week_picks):
                        _pname = _this_week_picks[_si]

                        # Name format mismatch: season_log stores "First Last"
                        # but predictions CSV uses "Last, First".
                        # Normalize both to lowercase "first last" for matching.
                        def _norm_name(n):
                            parts = str(n).split(",")
                            if len(parts) == 2:
                                return f"{parts[1].strip()} {parts[0].strip()}".lower()
                            return str(n).strip().lower()

                        if not _preds.empty:
                            _prow = _preds[_preds["player_name"].apply(_norm_name) == _norm_name(_pname)]
                        else:
                            _prow = pd.DataFrame()

                        # Safe defaults — set ALL variables before the if/else so
                        # nothing is ever undefined regardless of whether the player
                        # name matches a row in the predictions CSV
                        _wr_v   = "—"
                        _win_v  = 0.0
                        _t10_v  = 0.0
                        _ev_v   = 0.0
                        _uses_v = 3
                        _dots   = "🟢🟢🟢"
                        _odds   = "—"
                        _edge   = 0.0
                        _vprob  = 0.0
                        _drift  = ""
                        _dfs_own = 0.0

                        _sit_html = ""
                        if not _prow.empty:
                            _pr     = _prow.iloc[0]
                            _wr_v   = int(_pr["world_rank"]) if pd.notna(_pr.get("world_rank")) else "—"
                            _win_v  = (_pr.get("win_prob", 0) or 0) * 100
                            _t10_v  = (_pr.get("top10_prob", 0) or 0) * 100
                            _ev_v   = (_pr.get("expected_value", 0) or 0) / 1000
                            _uses_v = int(_pr.get("uses_remaining", 3))
                            _dots   = "🟢" * _uses_v + "⬜" * (3 - _uses_v)
                            _odds   = str(_pr.get("odds_to_win", "—") or "—")
                            _edge   = float(_pr.get("model_vs_vegas_edge", 0) or 0)
                            _vprob  = float(_pr.get("vegas_prob", 0) or 0) * 100
                            _drift  = str(_pr.get("odds_drift_level", "") or "").upper()
                            _dfs_own = float(_pr.get("dfs_ownership_proj", 0) or 0)
                            _sit_html = get_situational_badges(_pr.to_dict())

                        # Edge badge — only appears when model/market gap > 3 pts
                        _edge_badge = ""
                        if _edge > 0.03:
                            _edge_badge = (
                                f'<div style="background:rgba(0,196,79,0.15);border:1px solid '
                                f'rgba(0,196,79,0.4);border-radius:5px;padding:2px 8px;'
                                f'font-size:10px;color:#00c44f;font-weight:700;'
                                f'display:inline-block;margin-top:4px;">'
                                f'⚡ MODEL EDGE +{_edge*100:.1f}%</div>'
                            )
                        elif _edge < -0.03:
                            _edge_badge = (
                                f'<div style="background:rgba(229,57,53,0.1);border:1px solid '
                                f'rgba(229,57,53,0.3);border-radius:5px;padding:2px 8px;'
                                f'font-size:10px;color:#e57373;font-weight:700;'
                                f'display:inline-block;margin-top:4px;">'
                                f'⚠️ MARKET FAVORS {abs(_edge)*100:.1f}%</div>'
                            )

                        _drift_label = {
                            "SIGNIFICANT": "📈 Odds moving fast",
                            "MODERATE":    "📊 Odds drifting",
                        }.get(_drift, "")

                        st.markdown(f"""
<div class="lineup-card active">
  <div class="lc-rank">PICK {_si + 1}</div>
  <div class="lc-name">{_pname}</div>
  <div class="lc-wr">World Rank #{_wr_v}</div>
  <div class="lc-stats">
    <div><div class="lc-stat-val">{_win_v:.1f}%</div><div class="lc-stat-label">WIN</div></div>
    <div><div class="lc-stat-val" style="color:#4cb8ff;">{_t10_v:.0f}%</div><div class="lc-stat-label">TOP 10</div></div>
    <div><div class="lc-stat-val" style="color:#f4c430;">${_ev_v:.0f}k</div><div class="lc-stat-label">EXP VAL</div></div>
  </div>
  <hr style="border-color:#1c2f4a; margin:8px 0;">
  <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px;">
    <div><span style="color:#4a6080;">Vegas:</span> <span style="color:#dde6f5;font-weight:700;">{_odds}</span></div>
    <div><span style="color:#4a6080;">Mkt:</span> <span style="color:#dde6f5;font-weight:700;">{_vprob:.1f}%</span></div>
    <div><span style="color:#4a6080;">DFS Own:</span> <span style="color:#dde6f5;font-weight:700;">{_dfs_own:.1f}%</span></div>
  </div>
  {_edge_badge}
  <div style="font-size:10px;color:#4a6080;margin-top:4px;">{_drift_label}</div>
  {f'<div style="margin-top:6px;">{_sit_html}</div>' if _sit_html else ''}
  <div class="lc-uses">{_dots} ({_uses_v}/3 uses left)</div>
  <div class="lc-badge-use">✅ LOCKED IN</div>
</div>
""", unsafe_allow_html=True)
                    else:
                        # Empty slot — show model suggestion
                        if _si < len(_model_top3):
                            _sr = _model_top3.iloc[_si]
                            _wr_v = int(_sr["world_rank"]) if pd.notna(_sr.get("world_rank")) else "—"
                            _win_v = (_sr.get("win_prob", 0) or 0) * 100
                            _t10_v = (_sr.get("top10_prob", 0) or 0) * 100
                            _ev_v = (_sr.get("expected_value", 0) or 0) / 1000
                            _uses_v = int(_sr.get("uses_remaining", 3))
                            _dots = "🟢" * _uses_v + "⬜" * (3 - _uses_v)
                            st.markdown(f"""
<div class="lineup-card" style="border-color:#1c3a5e; border-style:dashed;">
  <div class="lc-rank">PICK {_si + 1} — SUGGESTED</div>
  <div class="lc-name" style="color:#7a90b8;">{_sr['player_name']}</div>
  <div class="lc-wr">World Rank #{_wr_v}</div>
  <div class="lc-stats">
    <div><div class="lc-stat-val" style="color:#5a8a6a;">{_win_v:.1f}%</div><div class="lc-stat-label">WIN</div></div>
    <div><div class="lc-stat-val" style="color:#4a7a9a;">{_t10_v:.0f}%</div><div class="lc-stat-label">TOP 10</div></div>
    <div><div class="lc-stat-val" style="color:#8a7a3a;">${_ev_v:.0f}k</div><div class="lc-stat-label">EXP VAL</div></div>
  </div>
  <div class="lc-uses">{_dots} ({_uses_v}/3 uses left)</div>
  <div class="lc-badge-save">↑ MODEL SUGGESTS</div>
</div>
""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
<div class="lineup-card empty">
  <div class="lc-rank">PICK {_si + 1}</div>
  <div class="lc-name" style="color:#2a3f58;">Empty Slot</div>
  <div class="lc-wr" style="margin-top:40px;color:#2a3f58;">Not yet selected</div>
</div>
""", unsafe_allow_html=True)

            # ── SAVE banner ──────────────────────────────────────────────
            if _elite_save:
                _save_names = " · ".join(_elite_save[:5])
                st.markdown(f"""
<div style="background:rgba(255,160,0,0.08); border:1px solid rgba(255,160,0,0.3);
     border-radius:10px; padding:12px 16px; margin:16px 0 8px 0;">
  <span style="color:#ffa000; font-weight:700; font-size:13px;">⚡ STANDARD EVENT — Save These Players for Majors & Signatures</span><br>
  <span style="color:#8a7040; font-size:12px; margin-top:4px; display:block;">{_save_names}</span>
</div>
""", unsafe_allow_html=True)

            # ── PLAYER POOL ──────────────────────────────────────────────
            if not _preds.empty:
                _pool_top_name = ""
                try:
                    _pool_top_name = _preds.nlargest(1, "expected_value").iloc[0]["player_name"]
                except Exception:
                    pass
                with st.expander(f"🏌️ Full Player Pool — Model Rankings{f'  ·  Top: {_pool_top_name}' if _pool_top_name else ''}", expanded=False):

                    # Sort: USE first (by EV), then SAVE, then CANNOT USE
                    def _pool_sort_key(row):
                        _uses = row.get("uses_remaining", 3)
                        _ev = row.get("expected_value", 0) or 0
                        _wr = row.get("world_rank", 999) or 999
                        if _uses == 0:
                            return (3, -_ev)
                        if _is_standard and row["player_name"] in _elite_save:
                            return (1, _wr)
                        return (0, -_ev)

                    _pool_df = _preds.copy()
                    # Filter to current field only (prevents stale players from appearing)
                    if _field_file and _field_file.exists():
                        try:
                            _field_df_pool = pd.read_csv(_field_file)
                            _field_ids_pool = set(_field_df_pool["player_id"].astype(str))
                            _pool_df = _pool_df[_pool_df["player_id"].astype(str).isin(_field_ids_pool)]
                        except Exception:
                            pass
                    _pool_df["_sort"] = [_pool_sort_key(r) for _, r in _pool_df.iterrows()]
                    _pool_df = _pool_df.sort_values("_sort").head(30)

                    _pool_html = []
                    _has_proj_score = "projected_score" in _pool_df.columns
                    for _rank_i, (_, _pr) in enumerate(_pool_df.iterrows(), 1):
                        _pn = _pr["player_name"]
                        _uses = int(_pr.get("uses_remaining", 3))
                        _wr_v = int(_pr["world_rank"]) if pd.notna(_pr.get("world_rank")) else "—"
                        _win_v = (_pr.get("win_prob", 0) or 0) * 100
                        _t10_v = (_pr.get("top10_prob", 0) or 0) * 100
                        _ev_v = (_pr.get("expected_value", 0) or 0) / 1000
                        _dfs_own_v = float(_pr.get("dfs_ownership_proj", 0) or 0)
                        _dots = "●" * _uses + "○" * (3 - _uses)

                        if _uses == 0:
                            _card_cls, _badge_cls, _badge_txt = "cant-card", "badge-no", "❌ MAXED"
                        elif _is_standard and _pn in _elite_save:
                            _card_cls, _badge_cls, _badge_txt = "save-card", "badge-save", "⚡ SAVE"
                        else:
                            _card_cls, _badge_cls, _badge_txt = "use-card", "badge-use", "✅ USE"

                        # Projected score stat box (only when model has run)
                        # Shows score vs field average (e.g. -5.8 = 5.8 strokes better than avg finisher)
                        _proj_score_html = ""
                        _has_proj_vsf = "projected_score_vs_field" in _pool_df.columns
                        _ps_col = "projected_score_vs_field" if _has_proj_vsf else ("projected_score" if _has_proj_score else None)
                        if _ps_col and pd.notna(_pr.get(_ps_col)):
                            _ps_v = float(_pr[_ps_col])
                            _ps_str = f"E" if _ps_v == 0 else (f"+{_ps_v:.1f}" if _ps_v > 0 else f"{_ps_v:.1f}")
                            _ps_color = "#ff6b6b" if _ps_v > 0 else ("#00c44f" if _ps_v < 0 else "#aaaaaa")
                            _ps_label = "vs FLD" if _has_proj_vsf else "PROJ"
                            _proj_score_html = f"""
      <div style="text-align:right; min-width:52px;">
        <div class="pc-stat" style="color:{_ps_color};">{_ps_str}</div>
        <div class="pc-stat-label">{_ps_label}</div>
      </div>"""

                        # Live win% delta badge (shown when Monte Carlo data is available)
                        _live_delta_html = ""
                        try:
                            _live_win = float(_pr.get("live_win_prob", float("nan")))
                            _pre_win  = float(_pr.get("win_prob", float("nan")))
                            if not (np.isnan(_live_win) or np.isnan(_pre_win)):
                                _delta_pp = (_live_win - _pre_win) * 100
                                if abs(_delta_pp) >= 0.5:
                                    _arrow = "↑" if _delta_pp > 0 else "↓"
                                    _d_col = "#00c44f" if _delta_pp > 0 else "#ff6b6b"
                                    _d_sign = "+" if _delta_pp > 0 else ""
                                    _live_delta_html = f"""
      <div style="text-align:right; min-width:52px;">
        <div class="pc-stat" style="color:{_d_col}; font-size:12px;">{_arrow}{_d_sign}{_delta_pp:.1f}pp</div>
        <div class="pc-stat-label">LIVE</div>
      </div>"""
                        except (TypeError, ValueError):
                            pass

                        _pool_html.append(f"""
    <div class="pool-card {_card_cls}">
      <div class="pc-rank">#{_rank_i}</div>
      <div style="flex:1;">
        <div class="pc-name">{_pn}</div>
        <div class="pc-wr">WR #{_wr_v} &nbsp;·&nbsp; {_dots} {_uses}/3</div>
      </div>
      <div style="text-align:right; min-width:50px;">
        <div class="pc-stat">{_win_v:.1f}%</div>
        <div class="pc-stat-label">WIN</div>
      </div>
      <div style="text-align:right; min-width:50px;">
        <div class="pc-stat" style="color:#4cb8ff;">{_t10_v:.0f}%</div>
        <div class="pc-stat-label">TOP 10</div>
      </div>
      <div style="text-align:right; min-width:50px;">
        <div class="pc-stat" style="color:#f4c430;">${_ev_v:.0f}k</div>
        <div class="pc-stat-label">EXP VAL</div>
      </div>
      <div style="text-align:right; min-width:50px;">
        <div class="pc-stat" style="color:#9b9bff;">{_dfs_own_v:.0f}%</div>
        <div class="pc-stat-label">DFS OWN</div>
      </div>{_proj_score_html}{_live_delta_html}
      <div class="pc-badge {_badge_cls}">{_badge_txt}</div>
    </div>""")

                    st.markdown("\n".join(_pool_html), unsafe_allow_html=True)

            st.markdown("---")
            # ── Optimal Lineup Finder ──────────────────────────────────────────
            with st.expander("🧮 Optimal Lineup Finder", expanded=False):
                st.caption(
                    "Deterministic combinatorial search with hard constraints. "
                    "Objective = EV + ceiling + leverage - risk - usage."
                )

                _profile_label = st.radio(
                    "Optimization Mode",
                    ["Safe", "Balanced", "Upside"],
                    horizontal=True,
                    key="opt_profile_mode",
                )
                _profile_key = str(_profile_label).lower()
                _profile_defaults = {
                    "safe": {
                        "desc": "Higher floor: stricter cut safety, fewer burn-now usage decisions.",
                        "top_n": 36,
                        "min_cut": 0.89,
                        "max_last_use": 0,
                        "min_lev_players": 0,
                        "lev_thresh": 0.70,
                        "w_ceiling": 0.06,
                        "w_lev": 0.02,
                        "w_risk": 0.30,
                        "w_usage": 1.20,
                        "last_use_penalty": 18000,
                    },
                    "balanced": {
                        "desc": "Best default for most users: balanced floor, upside, and usage discipline.",
                        "top_n": 45,
                        "min_cut": 0.84,
                        "max_last_use": 1,
                        "min_lev_players": 0,
                        "lev_thresh": 0.65,
                        "w_ceiling": 0.10,
                        "w_lev": 0.08,
                        "w_risk": 0.20,
                        "w_usage": 1.00,
                        "last_use_penalty": 15000,
                    },
                    "upside": {
                        "desc": "Tournament ceiling focus: accepts more volatility and leverage.",
                        "top_n": 55,
                        "min_cut": 0.78,
                        "max_last_use": 2,
                        "min_lev_players": 1,
                        "lev_thresh": 0.62,
                        "w_ceiling": 0.16,
                        "w_lev": 0.16,
                        "w_risk": 0.10,
                        "w_usage": 0.70,
                        "last_use_penalty": 12000,
                    },
                }
                _d = _profile_defaults.get(_profile_key, _profile_defaults["balanced"])
                st.caption(_d["desc"])

                _quick_cols = st.columns(2)
                with _quick_cols[0]:
                    st.metric("Lineup Size", "3", help="Fixed for this contest format.")
                    _opt_lineup_size = 3
                with _quick_cols[1]:
                    _opt_top_combos = st.slider(
                        "Combinations to show:",
                        5,
                        25,
                        10,
                        5,
                        key="opt_top_combos",
                    )

                _opt_top_n = int(_d["top_n"])
                _opt_min_cut = float(_d["min_cut"])
                _opt_max_last_use = int(_d["max_last_use"])
                _opt_min_lev_players = int(_d["min_lev_players"])
                _opt_lev_thresh = float(_d["lev_thresh"])
                _opt_w_ceiling = float(_d["w_ceiling"])
                _opt_w_lev = float(_d["w_lev"])
                _opt_w_risk = float(_d["w_risk"])
                _opt_w_usage = float(_d["w_usage"])
                _opt_last_use_penalty = int(_d["last_use_penalty"])

                _opt_run = st.button(
                    "▶ Run Optimizer", type="primary",
                    use_container_width=True, key="opt_run_btn",
                )

                if _opt_run:
                    try:
                        sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
                        from scripts.predictions.lineup_optimizer import run_optimizer

                        with st.spinner("Evaluating combinations..."):
                            _opt_df, _opt_elig, _opt_imp, _opt_tname = run_optimizer(
                                top_n=int(_opt_top_n),
                                top_combos=int(_opt_top_combos),
                                lineup_size=int(_opt_lineup_size),
                                min_avg_cut_prob=float(_opt_min_cut),
                                max_last_use_players=int(_opt_max_last_use),
                                min_leverage_players=int(_opt_min_lev_players),
                                leverage_threshold=float(_opt_lev_thresh),
                                ceiling_weight=float(_opt_w_ceiling),
                                leverage_weight=float(_opt_w_lev),
                                risk_weight=float(_opt_w_risk),
                                usage_weight=float(_opt_w_usage),
                                last_use_penalty=float(_opt_last_use_penalty),
                                locked_players=[],
                                excluded_players=[],
                                verbose=False,
                            )

                        _opt_meta = _opt_df.attrs.get("optimizer_meta", {})
                        st.caption(
                            f"Mode: {_profile_label} · "
                            f"Tournament: {_opt_tname or 'Unknown'} · Importance: {int(_opt_imp)}/10 · "
                            f"Candidates: {len(_opt_elig)} · "
                            f"Passed combos: {_opt_meta.get('scored_combos', 0):,}/{_opt_meta.get('total_combos', 0):,}"
                        )

                        if _opt_meta.get("unresolved_locked"):
                            st.warning("Unresolved lock names: " + ", ".join(_opt_meta["unresolved_locked"]))
                        if _opt_meta.get("unresolved_excluded"):
                            st.warning("Unresolved exclude names: " + ", ".join(_opt_meta["unresolved_excluded"]))

                        if _opt_df.empty:
                            st.warning(
                                "No lineups matched your constraints. Try lowering min avg cut %, "
                                "increasing max last-use players, or reducing min leverage players."
                            )
                        else:
                            for _rank, _row in _opt_df.iterrows():
                                _usage_pen = float(pd.to_numeric(_row.get("usage_penalty"), errors="coerce") or 0.0)
                                _risk_pen = float(pd.to_numeric(_row.get("risk_penalty"), errors="coerce") or 0.0)
                                _penalty = _usage_pen > 0 or _risk_pen > 0
                                _player_lines = []
                                for _idx in range(1, int(_opt_lineup_size) + 1):
                                    _p = str(_row.get(f"pick{_idx}", "")).strip()
                                    if not _p:
                                        continue
                                    _ev = float(pd.to_numeric(_row.get(f"ev{_idx}", 0), errors="coerce") or 0.0)
                                    _uses = int(pd.to_numeric(_row.get(f"uses{_idx}", 3), errors="coerce") or 0)
                                    _player_lines.append(f"{_p}  |  EV ${_ev:,.0f}  |  Uses {_uses}/3")

                                with st.container(border=True):
                                    _c1, _c2, _c3 = st.columns([0.6, 4, 1.4])
                                    with _c1:
                                        st.caption(f"#{_rank}")
                                    with _c2:
                                        st.text("\n".join(_player_lines))
                                    with _c3:
                                        st.metric("Score", f"${float(_row.get('score', 0)):,.0f}")
                                        st.caption(
                                            f"Cut {float(_row.get('avg_cut_prob', 0)):.1f}% · "
                                            f"Top-5 any {float(_row.get('p_top5_any', 0)):.1f}%"
                                        )
                                    if _penalty:
                                        st.caption("Includes risk/usage penalties.")

                        if _opt_meta:
                            st.caption(
                                f"Constraint rejections -> cut: {_opt_meta.get('skipped_by_cut', 0):,} | "
                                f"usage: {_opt_meta.get('skipped_by_usage', 0):,} | "
                                f"leverage: {_opt_meta.get('skipped_by_leverage', 0):,}"
                            )

                    except Exception as _opt_err:
                        st.error(f"Optimizer error: {_opt_err}")
                        st.caption("Make sure predictions are loaded (run full pipeline first).")

    # ── Power Rankings & Tools ────────────────────────────────────────────────
    _tw_pr_tab, _tw_tools_tab = st.tabs(["📈 Power Rankings", "🔧 Tools"])

    with _tw_pr_tab:
        st.markdown("### Power Rankings")
        st.caption("Editorial ranking feed with quick scanning, filtering, and full-table drill-down.")

        pr_dir = DATA_DIR / "power_rankings"
        if pr_dir.exists():
            pr_files = sorted(pr_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
            pr_files = [f for f in pr_files if f.name not in ("paths.csv",) and not f.name.startswith(".")]

            if pr_files:
                file_options = {
                    f"{f.stem.replace('_', ' ').title()} ({datetime.fromtimestamp(f.stat().st_mtime).strftime('%b %d %H:%M')})": f
                    for f in pr_files
                }
                selected_label = st.selectbox(
                    "Ranking file",
                    list(file_options.keys()),
                    index=0,
                    key="tw_pr_file",
                )
                selected_file = file_options[selected_label]
                df = pd.read_csv(selected_file)

                player_col = "player_name" if "player_name" in df.columns else "player" if "player" in df.columns else None
                if player_col is None:
                    st.warning("No player column found in selected ranking file.")
                else:
                    df[player_col] = df[player_col].fillna("").astype(str).str.strip()
                    df = df[df[player_col] != ""].copy()

                    if "rank" in df.columns:
                        df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
                        df = df.sort_values("rank", na_position="last")
                    else:
                        df = df.reset_index(drop=True)
                        df["rank"] = df.index + 1

                    tournament_name = (
                        str(df["tournament_name"].iloc[0]).strip()
                        if "tournament_name" in df.columns and not df.empty
                        else selected_file.stem.replace("_", " ").title()
                    )

                    last_updated = (
                        pd.to_datetime(df["scraped_at"], errors="coerce").max()
                        if "scraped_at" in df.columns
                        else pd.NaT
                    )
                    last_updated_str = (
                        last_updated.strftime("%Y-%m-%d %H:%M")
                        if pd.notna(last_updated)
                        else datetime.fromtimestamp(selected_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    )

                    st.success(f"{tournament_name} power rankings loaded")

                    top_player = df.iloc[0][player_col] if not df.empty else "—"
                    source_name = (
                        str(df["source"].iloc[0]).upper()
                        if "source" in df.columns and not df.empty and pd.notna(df["source"].iloc[0])
                        else "—"
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Players Ranked", len(df))
                    with m2:
                        st.metric("Top Ranked", str(top_player))
                    with m3:
                        st.metric("Source", source_name)
                    with m4:
                        st.metric("Updated", last_updated_str)

                    st.markdown("#### Top 3 Spotlight")
                    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                    top3 = df.head(3).copy()
                    spot_cols = st.columns(3)
                    for i in range(3):
                        with spot_cols[i]:
                            if i < len(top3):
                                row = top3.iloc[i]
                                rank = int(row.get("rank", i + 1)) if pd.notna(row.get("rank")) else i + 1
                                name = row.get(player_col, "Unknown")
                                country = str(row.get("country_flag", row.get("country", ""))).strip()
                                analysis = str(row.get("analysis", "") or "").strip()
                                st.markdown(f"### {medals.get(rank, f'#{rank}')}")
                                st.markdown(f"**{name}**")
                                if country:
                                    st.caption(country)
                                if analysis:
                                    st.caption(analysis[:140] + ("..." if len(analysis) > 140 else ""))
                            else:
                                st.markdown(" ")

                    st.markdown("#### Ranked Board")
                    board_col1, board_col2 = st.columns([2, 1])
                    with board_col1:
                        search_q = st.text_input("Search player", value="", key="tw_pr_search")
                    with board_col2:
                        board_size = st.slider("Show rows", min_value=10, max_value=40, value=15, step=5, key="tw_pr_rows")

                    board_df = df.copy()
                    if search_q.strip():
                        board_df = board_df[
                            board_df[player_col].str.contains(search_q.strip(), case=False, na=False)
                        ].copy()
                    board_df = board_df.head(board_size)

                    def _pr_border(rank_num):
                        if rank_num == 1:   return "#f1c40f"
                        if rank_num == 2:   return "#aaa"
                        if rank_num == 3:   return "#cd7f32"
                        if rank_num <= 10:  return "#3498db"
                        return "#2a3a50"

                    for _, row in board_df.iterrows():
                        rank_val = row.get("rank")
                        rank_num = int(rank_val) if pd.notna(rank_val) else None
                        rank_label = medals.get(rank_num, f"#{rank_num}" if rank_num else "•")
                        player   = str(row.get(player_col, "Unknown")).strip()
                        country  = str(row.get("country_flag", row.get("country", ""))).strip()
                        analysis = str(row.get("analysis", "") or "").strip()
                        border   = _pr_border(rank_num)

                        st.markdown(f"""
<div style="background:#0d1a30;border-left:3px solid {border};border-radius:6px;
            padding:12px 16px;margin-bottom:8px;">
  <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px;">
    <span style="font-size:1.05em;font-weight:700;color:{border};">{rank_label}</span>
    <span style="font-size:1.0em;font-weight:600;color:#dde6f5;">{player}</span>
    {"<span style='font-size:0.78em;color:#6b7fa3;'>" + country + "</span>" if country else ""}
  </div>
  {"<p style='margin:0;font-size:0.82em;color:#b0bec5;line-height:1.55;'>" + analysis + "</p>" if analysis else ""}
</div>
""", unsafe_allow_html=True)

                    with st.expander("Full Rankings Table"):
                        drop_cols = {"analysis"}
                        table_cols = [c for c in ["rank", player_col, "country_flag", "country", "player_id", "source", "scraped_at"] if c in df.columns]
                        table_cols += [c for c in df.columns if c not in set(table_cols) | drop_cols][:4]
                        st.dataframe(df[table_cols], hide_index=True, use_container_width=True, height=520)
            else:
                st.info("No power rankings available yet.")
        else:
            st.info("Power rankings directory not found.")

    with _tw_tools_tab:
        st.markdown("### Tools")
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            run_report = st.button("Generate Weekly Report", use_container_width=True, type="primary", key="tw_report")
        with action_col2:
            refresh_all = st.button("Refresh All Data", use_container_width=True, key="tw_refresh")

        if run_report:
            with st.spinner("Generating weekly report..."):
                output = run_script("planning/weekly_report.py")
            with st.expander("Weekly report output", expanded=False):
                st.code(output, language=None)

        if refresh_all:
            with st.spinner("Refreshing data..."):
                output = run_script("run_pipeline.py", "--auto-weekly", "--skip-refresh")
            with st.expander("Refresh output", expanded=False):
                st.code(output, language=None)
            st.cache_data.clear()


# ============================================================================
# PAGE: ASSISTANT (Groq-powered golf chat)
# ============================================================================

elif page == "💬 Assistant":
    import os as _os
    import time as _time
    from datetime import datetime as _dt

    st.markdown("## Golf Assistant")
    st.caption("Ask about lineups, bets, player form, live scores — powered by Groq (free).")

    _groq_key = _os.environ.get("GROQ_API_KEY", "") or st.session_state.get("groq_api_key", "")

    # --- Context cache: build once, refresh every 15 min or on demand ---
    _CTX_TTL = 15 * 60  # seconds
    _ctx_built_at = st.session_state.get("chat_context_built_at", 0)
    _ctx_stale = (_time.time() - _ctx_built_at) > _CTX_TTL
    _ctx_missing = "chat_context" not in st.session_state

    if _ctx_missing or _ctx_stale:
        with st.spinner("Loading tournament data..."):
            try:
                from scripts.chat.golf_chatbot import (
                    build_context as _build_context,
                    _detect_tournament_id,
                    _tournament_state,
                )
                _cur_tid = _detect_tournament_id()
                st.session_state["chat_context"] = _build_context(_cur_tid)
                _ts = _tournament_state(_cur_tid) if _cur_tid else {}
                st.session_state["chat_phase"] = _ts.get("phase", "pre_tournament")
            except Exception as _ctx_err:
                st.session_state["chat_context"] = (
                    f"You are a golf analytics assistant. Context unavailable: {_ctx_err}"
                )
                st.session_state["chat_phase"] = "pre_tournament"
            st.session_state["chat_context_built_at"] = _time.time()

    with st.sidebar:
        st.markdown("### Assistant Settings")
        _key_input = st.text_input(
            "Groq API Key", value=_groq_key, type="password", key="groq_api_key_input"
        )
        if _key_input:
            st.session_state["groq_api_key"] = _key_input
            _groq_key = _key_input
        if not _groq_key:
            st.warning("Enter your free Groq API key above.\nGet one at groq.com")

        # Context freshness indicator + refresh button
        if "chat_context_built_at" in st.session_state:
            _built_str = _dt.fromtimestamp(
                st.session_state["chat_context_built_at"]
            ).strftime("%I:%M %p")
            st.caption(f"Context built: {_built_str} (refreshes every 15 min)")
        if st.button("Refresh context", key="chat_refresh_ctx"):
            st.session_state.pop("chat_context", None)
            st.session_state.pop("chat_context_built_at", None)
            st.rerun()
        if st.button("Clear conversation", key="chat_clear"):
            st.session_state["chat_history"] = []
            st.rerun()

    # Phase-aware quick action buttons
    _PHASE_ACTIONS = {
        "pre_tournament": [
            ("Build my lineup", "Build my optimal lineup for this week. Consider my uses remaining, player form, and course fit. Give me 3 players and explain why each one makes sense."),
            ("Best bets", "What are the top 3 bets with the best value this week? Walk me through the odds and why each one makes sense."),
            ("Value plays", "Who are the best value plays for a win bet this week — players where the odds clearly underestimate their chances?"),
            ("Course breakdown", "Break down this week's course. What game wins here — ball-striking, putting, bombers? Who fits the course profile best?"),
        ],
        "round_1": [
            ("Round 1 update", "Give me a live update after Round 1. Who's leading, who surprised me, and who's already in trouble?"),
            ("Still a contender?", "Based on Round 1, who are the realistic winners and who is out of it?"),
            ("In-play value", "Given Round 1 results, are there any in-play betting opportunities where the live odds look out of line?"),
            ("Cut projection", "Where does the cut project right now and who's fighting to make the weekend?"),
        ],
        "round_2": [
            ("36-hole update", "Give me a live update through 2 rounds. Who's in the best position heading into the weekend?"),
            ("Weekend contenders", "Who are the realistic winners heading into Saturday? Who has the game and position to close?"),
            ("Cut projection", "Where does the cut project right now and who's on the bubble?"),
            ("In-play value", "Given the 36-hole leaderboard, any in-play betting angles worth considering for the weekend?"),
        ],
        "round_3": [
            ("Saturday recap", "Where does the tournament stand after Round 3? Who's in pole position and who's still alive?"),
            ("Who can win?", "Who can realistically win from their current position? Walk me through the contenders and what they need to shoot."),
            ("Cash out bets?", "Given Round 3 results, should I cash out any of my current bets or let them ride?"),
            ("Final round picks", "Who do you like in the final round based on current position, form, and course history?"),
        ],
        "round_4": [
            ("Live update", "Give me a live Round 4 update. Who's leading, who's charging, and who's fading?"),
            ("Who can still win?", "Who can still realistically win and what do they need to do in the remaining holes?"),
            ("Cash out bets?", "Based on current leaderboard positions, should I cash out any bets before the finish?"),
            ("Late drama", "Which holes are going to decide this tournament? What should I be watching?"),
        ],
        "complete": [
            ("Final results", "Walk me through the final results. Who won, how did it unfold, and what were the key moments?"),
            ("How did my picks do?", "How did my picks finish this week? Walk me through each player's result and what it means for my season standings."),
            ("Next week preview", "Give me a preview of next week's tournament. What should I know about the course and who are the early favorites?"),
            ("Season standings", "How did this week shake up the league standings? Who moved up, who fell back, and where does WineTime stand now?"),
        ],
    }
    _PHASE_FOLLOWUPS = {
        "pre_tournament": [
            "Who are the biggest risks in my lineup this week?",
            "Which players have the best course history here?",
            "Any players I should avoid at any price?",
        ],
        "round_1": [
            "Who's still a realistic winner from this position?",
            "Any surprise leaders I should know about?",
            "Who should I be watching closely in Round 2?",
        ],
        "round_2": [
            "Who has the best record of closing from this position?",
            "Who's the biggest threat to the current leader?",
            "Who do you like to make a big move this weekend?",
        ],
        "round_3": [
            "Who has the best closing record in the field?",
            "Any sleepers who could make a late charge?",
            "What does the winning score look like from here?",
        ],
        "round_4": [
            "Who tends to buckle under pressure at this stage?",
            "What does the winner need to shoot to close it out?",
            "Who's the best putter among the current leaders?",
        ],
        "complete": [
            "What should I prioritize in next week's lineup?",
            "Who outperformed their pre-tournament ranking?",
            "How did the recommended bets finish?",
        ],
    }

    _chat_phase = st.session_state.get("chat_phase", "pre_tournament")
    _quick_actions = _PHASE_ACTIONS.get(_chat_phase, _PHASE_ACTIONS["pre_tournament"])
    _qa_cols = st.columns(4)
    for _i, (_label, _prompt) in enumerate(_quick_actions):
        with _qa_cols[_i]:
            if st.button(_label, use_container_width=True, key=f"qa_{_i}"):
                st.session_state["chat_prefill"] = _prompt

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for _msg in st.session_state["chat_history"]:
        with st.chat_message(_msg["role"]):
            st.markdown(_msg["content"])

    # Follow-up chips — shown after the last assistant message
    if (
        st.session_state.get("chat_history")
        and st.session_state["chat_history"][-1]["role"] == "assistant"
    ):
        _followups = _PHASE_FOLLOWUPS.get(_chat_phase, _PHASE_FOLLOWUPS["pre_tournament"])
        st.caption("Follow up:")
        _fu_cols = st.columns(len(_followups))
        for _fi, _fq in enumerate(_followups):
            with _fu_cols[_fi]:
                if st.button(
                    _fq,
                    key=f"fu_{_fi}_{len(st.session_state['chat_history'])}",
                    use_container_width=True,
                ):
                    st.session_state["chat_prefill"] = _fq
                    st.rerun()

    _prefill = st.session_state.pop("chat_prefill", None)

    if _prompt := (st.chat_input("Ask about lineups, bets, players, live scores...") or _prefill):
        if not _groq_key:
            st.error("Please enter your Groq API key in the sidebar to use the assistant.")
        else:
            with st.chat_message("user"):
                st.markdown(_prompt)
            st.session_state["chat_history"].append({"role": "user", "content": _prompt})

            # Build query-aware context for this specific message
            try:
                from scripts.chat.golf_chatbot import build_context as _build_ctx, stream_response as _stream_response
                _cur_tid = _detect_tournament_id() if "_cur_tid" not in dir() else _cur_tid
                _context = _build_ctx(query=_prompt, tournament_id=_cur_tid)
            except Exception as _ctx_err:
                _context = st.session_state.get("chat_context", "You are a golf analytics assistant.")

            _messages = [{"role": "system", "content": _context}]
            _messages += st.session_state["chat_history"][-20:]

            with st.chat_message("assistant"):
                try:
                    _response_text = st.write_stream(_stream_response(_messages, _groq_key))
                except Exception as _err:
                    _response_text = f"Error: {_err}"
                    st.error(_response_text)

            if _response_text:
                st.session_state["chat_history"].append(
                    {"role": "assistant", "content": _response_text}
                )


# ============================================================================
# PAGE: MY PICKS (consolidated with Performance)
# ============================================================================

elif page == "📋 My Picks":
    st.markdown("## 📋 My Picks")
    st.caption("Track usage and manage your lineup")

    engine = load_scoring_engine(_scoring_engine_cache_key())
    all_players = sorted(engine.predictions.keys()) if engine and engine.predictions else []

    # Current tournament banner
    if engine:
        tournament = engine.get_current_week_tournament()
        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            st.success(f"📍 **This Week:** {tournament} — Week {t.week} • {t.tournament_type}")

    st.markdown("---")

    # ── This Week's Results ────────────────────────────────────────────────────
    _wkly_picks_path = DATA_DIR / "fantasy" / "league_weekly_picks.csv"
    _tracker_path    = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
    _my_wk           = pd.DataFrame()  # shared between the two blocks below
    _wk_total        = 0

    if _wkly_picks_path.exists():
        try:
            import json as _json
            _wkly_df = pd.read_csv(_wkly_picks_path)
            _my_wk = _wkly_df[_wkly_df["team_name"] == "WineTime"]
            if not _my_wk.empty:
                _wr = _my_wk.iloc[0]
                _wk_rank   = _wr.get("weekly_rank", "?")
                _wk_total  = int(_wr.get("total_earnings", 0))
                _p1, _e1   = _wr.get("player_1", ""), int(_wr.get("earnings_1", 0))
                _p2, _e2   = _wr.get("player_2", ""), int(_wr.get("earnings_2", 0))
                _p3, _e3   = _wr.get("player_3", ""), int(_wr.get("earnings_3", 0))

                # League average this week
                _all_earn  = _wkly_df["total_earnings"].replace(0, pd.NA).dropna()
                _lg_avg    = int(_all_earn.mean()) if not _all_earn.empty else 0
                _lg_max    = int(_all_earn.max()) if not _all_earn.empty else 0
                _vs_avg    = _wk_total - _lg_avg
                _vs_avg_str = (f"+${_vs_avg:,}" if _vs_avg >= 0 else f"-${abs(_vs_avg):,}")
                _vs_avg_col = "#00c44f" if _vs_avg >= 0 else "#e74c3c"

                st.markdown("### This Week's Results")
                _rc1, _rc2, _rc3, _rc4 = st.columns(4)
                with _rc1:
                    st.metric("Weekly Rank", f"#{_wk_rank}")
                with _rc2:
                    st.metric("Total Earned", f"${_wk_total:,}")
                with _rc3:
                    st.metric("vs League Avg", _vs_avg_str)
                with _rc4:
                    st.metric("League Best", f"${_lg_max:,}")

                # Player cards
                _pc1, _pc2, _pc3 = st.columns(3)
                for _col, _pname, _earn in [(_pc1, _p1, _e1), (_pc2, _p2, _e2), (_pc3, _p3, _e3)]:
                    _pc = "#00c44f" if _earn > _lg_avg / 3 else ("#f39c12" if _earn > 0 else "#e74c3c")
                    with _col:
                        st.markdown(
                            f"<div style='background:{_pc}11;border:1px solid {_pc}44;"
                            f"border-radius:8px;padding:12px;text-align:center;'>"
                            f"<div style='font-size:0.85em;color:#dde6f5;font-weight:600;"
                            f"margin-bottom:6px;'>{_pname}</div>"
                            f"<div style='font-size:1.3em;font-weight:700;color:{_pc};'>"
                            f"${_earn:,}</div></div>",
                            unsafe_allow_html=True,
                        )
        except Exception:
            pass

    # ── Season Earnings Trajectory ─────────────────────────────────────────────
    if _tracker_path.exists():
        try:
            import json as _json
            import plotly.graph_objects as _pgo
            with open(_tracker_path) as _tf:
                _tracker = _json.load(_tf)

            _wk_lineups = _tracker.get("weekly_lineups", {})
            _hist_rows = []
            for _wk_key in sorted(_wk_lineups.keys()):
                _wkd = _wk_lineups[_wk_key]
                _earn = _wkd.get("earnings_earned") or 0
                _hist_rows.append({
                    "Week": f"Wk {_wkd.get('week', '?')}",
                    "Tournament": _wkd.get("tournament", ""),
                    "Earnings": _earn,
                })
            if _hist_rows:
                _hist_df = pd.DataFrame(_hist_rows)
                _hist_df["Cumulative"] = _hist_df["Earnings"].cumsum()

                # Pull current week league earnings from weekly picks (in actual $)
                if not _my_wk.empty and _hist_df["Earnings"].iloc[-1] == 0:
                    _hist_df.loc[_hist_df.index[-1], "Earnings"] = _wk_total
                    _hist_df["Cumulative"] = _hist_df["Earnings"].cumsum()

                st.markdown("### Season Earnings by Week")
                _fig = _pgo.Figure()
                _fig.add_trace(_pgo.Bar(
                    x=_hist_df["Week"],
                    y=_hist_df["Earnings"],
                    name="Weekly Earnings",
                    marker_color="#4cb8ff",
                    text=_hist_df["Earnings"].apply(lambda v: f"${v:,}"),
                    textposition="outside",
                    hovertext=_hist_df["Tournament"],
                ))
                _fig.add_trace(_pgo.Scatter(
                    x=_hist_df["Week"],
                    y=_hist_df["Cumulative"],
                    name="Cumulative",
                    mode="lines+markers",
                    line=dict(color="#00c44f", width=2),
                    marker=dict(size=6),
                    yaxis="y2",
                ))
                _fig.update_layout(
                    height=320,
                    margin=dict(t=20, b=20, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#dde6f5"),
                    legend=dict(orientation="h", y=1.08),
                    xaxis=dict(gridcolor="#2a3a5c"),
                    yaxis=dict(title="Weekly Earnings ($)", gridcolor="#2a3a5c", tickprefix="$"),
                    yaxis2=dict(
                        title="Cumulative ($)",
                        overlaying="y",
                        side="right",
                        gridcolor="rgba(0,0,0,0)",
                        tickprefix="$",
                    ),
                )
                st.plotly_chart(_fig, use_container_width=True)
        except Exception:
            pass

    st.markdown("---")

    # ── Player Usage Grid ──────────────────────────────────────────────────────
    st.markdown("### Player Usage Grid")
    st.caption("All players used this season — color-coded by uses remaining")

    if picks:
        _sorted_picks = sorted(picks.items(), key=lambda x: x[1].get("remaining_uses", 3))

        def _use_color(remaining):
            return {0: "#e74c3c", 1: "#f39c12", 2: "#f1c40f"}.get(remaining, "#00c44f")

        _groups = {0: [], 1: [], 2: [], 3: []}
        for _gn, _gd in _sorted_picks:
            _groups.get(_gd.get("remaining_uses", 3), []).append((_gn, _gd))

        _group_labels = {
            0: "Maxed Out — 0 uses left",
            1: "1 use remaining",
            2: "2 uses remaining",
            3: "3 uses remaining",
        }

        for _rem in [0, 1, 2, 3]:
            if not _groups[_rem]:
                continue
            _gc = _use_color(_rem)
            st.markdown(
                f"<div style='color:{_gc};font-weight:600;font-size:0.82em;"
                f"letter-spacing:0.05em;margin:14px 0 5px;'>"
                f"● {_group_labels[_rem].upper()}</div>",
                unsafe_allow_html=True,
            )
            _gcols = st.columns(min(4, len(_groups[_rem])))
            for _gi, (_gname, _gdata) in enumerate(_groups[_rem]):
                _grem   = _gdata.get("remaining_uses", 3)
                _gtotal = _gdata.get("total_earnings", _gdata.get("total_points", 0))
                _gdots  = "🟢" * _grem + "⬜" * (3 - _grem)
                _gweeks = [str(t.get("week", "")) for t in _gdata.get("tournaments_used", [])]
                _gwk_str = ("Wk " + ", ".join(_gweeks)) if _gweeks else ""
                with _gcols[_gi % 4]:
                    st.markdown(f"""
                    <div style="background:{_gc}0d;border:1px solid {_gc}44;
                                border-radius:8px;padding:10px 12px;margin:3px 0;">
                        <div style="font-weight:600;font-size:0.85em;color:#dde6f5;
                                    white-space:nowrap;overflow:hidden;
                                    text-overflow:ellipsis;margin-bottom:4px;">
                            {_gname[:22]}
                        </div>
                        <div style="font-size:1.05em;margin-bottom:3px;">{_gdots}</div>
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75em;color:{_gc};font-weight:600;">
                                ${int(_gtotal or 0):,}
                            </span>
                            <span style="font-size:0.72em;color:#6b7fa3;">{_gwk_str}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.info("No players tracked yet this season.")

    st.markdown("---")

    # Manage Picks
    st.markdown("### ✏️ Manage Picks")

    manage_tab1, manage_tab2, manage_tab3 = st.tabs(["➕ Add Picks", "📝 Record Result", "🗑️ Remove Pick"])

    # Get tournaments
    current_tourney = ""
    upcoming_tourneys = []
    past_tourneys = []
    if engine:
        current_tourney = engine.get_current_week_tournament() or ""
        today = datetime.now().strftime("%Y-%m-%d")

        # Helper to get end date (start + 3 days for standard tournaments)
        def get_end_date(t):
            try:
                end_day = int(t.start_date[8:10]) + 3
                return t.start_date[:8] + str(end_day).zfill(2)
            except:
                return t.start_date

        # Include current + upcoming tournaments (end_date >= today means still playable)
        upcoming_tourneys = [name for name, t in engine.tournaments.items() if get_end_date(t) >= today]
        upcoming_tourneys.sort(key=lambda x: engine.tournaments[x].start_date)
        # Past tournaments are those that have ended
        past_tourneys = [name for name, t in engine.tournaments.items() if get_end_date(t) < today]
        past_tourneys.sort(key=lambda x: engine.tournaments[x].start_date, reverse=True)

    with manage_tab1:
        st.markdown("**Add players to your lineup**")

        tourney_for_pick = st.selectbox(
            "Tournament:",
            upcoming_tourneys,
            index=upcoming_tourneys.index(current_tourney) if current_tourney in upcoming_tourneys else 0,
            key="add_pick_tourney"
        )

        st.caption("Select up to 3 players:")
        col1, col2, col3 = st.columns(3)
        with col1:
            pick1 = st.selectbox("Player 1:", [""] + all_players, key="pick1")
        with col2:
            pick2 = st.selectbox("Player 2:", [""] + all_players, key="pick2")
        with col3:
            pick3 = st.selectbox("Player 3:", [""] + all_players, key="pick3")

        add_picks_btn = st.button("✅ Add Picks", type="primary", key="add_picks_btn")

        if add_picks_btn:
            selected = [p for p in [pick1, pick2, pick3] if p]
            if not selected:
                st.warning("Please select at least one player")
            elif not tourney_for_pick:
                st.warning("Please select a tournament")
            else:
                args = ["planning/usage_tracker.py", "--add"] + selected + ["--tournament", tourney_for_pick]
                with st.spinner(f"Adding {len(selected)} pick(s) to {tourney_for_pick}..."):
                    output = run_script(*args)
                st.code(output, language=None)
                if "Added" in output or "✓" in output:
                    st.success("Picks added! Reloading...")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Check output above for any issues.")

    with manage_tab2:
        st.markdown("**Record tournament result**")

        # Get players from tracker (picks) who need results recorded
        tracked_players = list(picks.keys()) if picks else []

        # Get tournaments where we have picks (only if lineup has players)
        lineups = usage_data.get("weekly_lineups", {})
        tourneys_with_picks = []
        for week_key, lineup in lineups.items():
            tourney_name = lineup.get("tournament", "")
            lineup_players = lineup.get("lineup", [])
            if tourney_name and lineup_players and tourney_name not in tourneys_with_picks:
                tourneys_with_picks.append(tourney_name)

        if not tracked_players:
            st.info("No players in tracker yet. Add picks first using the 'Add Picks' tab.")
        else:
            result_tourney = st.selectbox(
                "Tournament:",
                tourneys_with_picks if tourneys_with_picks else past_tourneys[:10],
                key="result_tourney"
            )

            # Filter to players who were picked for this tournament
            players_in_tourney = []
            for week_key, lineup in lineups.items():
                if lineup.get("tournament") == result_tourney:
                    players_in_tourney.extend(lineup.get("lineup", []))

            player_options = players_in_tourney if players_in_tourney else tracked_players
            result_player = st.selectbox("Player:", [""] + player_options, key="result_player")

            col1, col2 = st.columns(2)
            with col1:
                finish_pos = st.text_input("Finish position:", placeholder="e.g., 1st, T3, T15, MC", key="finish_pos")
            with col2:
                earnings_earned = st.number_input("Earnings ($):", min_value=0, max_value=10000000, value=0, step=1000, key="earnings_earned")

            record_result_btn = st.button("📝 Record Result", type="primary", key="record_result_btn")

            if record_result_btn:
                if not result_player:
                    st.warning("Please select a player")
                elif not finish_pos:
                    st.warning("Please enter finish position")
                else:
                    with st.spinner(f"Recording result for {result_player}..."):
                        output = run_script(
                            "planning/usage_tracker.py",
                            "--result", result_player,
                            "--tournament", result_tourney,
                            "--finish", finish_pos,
                            "--earnings", str(earnings_earned)
                        )
                    st.code(output, language=None)
                    if "recorded" in output.lower() or "updated" in output.lower():
                        st.success(f"Result recorded for {result_player}!")
                        st.cache_data.clear()

    with manage_tab3:
        st.markdown("**Remove a pick (undo mistake)**")

        remove_tourney = st.selectbox(
            "Tournament:",
            upcoming_tourneys[:10] if upcoming_tourneys else ["No tournaments"],
            key="remove_tourney"
        )

        remove_player = st.selectbox("Player to remove:", [""] + all_players, key="remove_player")

        remove_btn = st.button("🗑️ Remove Pick", type="secondary", key="remove_btn")

        if remove_btn:
            if not remove_player:
                st.warning("Please select a player")
            else:
                with st.spinner(f"Removing {remove_player} from {remove_tourney}..."):
                    output = run_script(
                        "planning/usage_tracker.py",
                        "--remove", remove_player,
                        "--tournament", remove_tourney
                    )
                st.code(output, language=None)

    st.markdown("---")

    # Auto-Record Results
    st.markdown("### 🤖 Auto-Record Results")
    st.caption("Automatically fetch results and official earnings from leaderboard data when available")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("👁️ Preview Results (Dry Run)", use_container_width=True):
            with st.spinner("Checking leaderboard for results..."):
                output = run_script("planning/auto_record_results.py", "--dry-run")
            st.code(output, language=None)
    with col2:
        if st.button("✅ Record All Results", use_container_width=True, type="primary"):
            with st.spinner("Recording results..."):
                output = run_script("planning/auto_record_results.py")
            st.code(output, language=None)
            st.cache_data.clear()

    st.markdown("---")

    # ----------------------------------------------------------------
    # SEASON LOG — Visual Summary
    # ----------------------------------------------------------------
    st.markdown("### 📅 Season Log")
    st.caption("Your picks and results, week by week")

    _log_path = OUTPUTS_DIR / "season_log.csv"
    _tracker_path = PROJECT_ROOT / "data" / "fantasy" / "usage_tracker_2026.json"
    _wk_player_res: dict = {}

    # Load season log; fall back to empty frame if file is missing
    _log = pd.read_csv(_log_path) if _log_path.exists() else pd.DataFrame(
        columns=["week", "date", "tournament", "pick1", "pick2", "pick3",
                 "result1", "result2", "result3", "earnings", "league_rank",
                 "notes", "rank1", "rank2", "rank3", "avg_model_rank"])
    if "earnings" not in _log.columns and "points" in _log.columns:
        _log["earnings"] = _log["points"]

    # Augment from usage_tracker for any weeks not yet written to season_log.csv
    if _tracker_path.exists():
        try:
            _tracker = json.loads(_tracker_path.read_text())
            _log_weeks = set(pd.to_numeric(_log["week"], errors="coerce").dropna().astype(int).tolist())
            _wk_lineups = _tracker.get("weekly_lineups", {})
            _wk_totals: dict[int, float] = {}
            for _wk_key, _wd in _wk_lineups.items():
                _wk_num = pd.to_numeric(_wd.get("week"), errors="coerce")
                _wk_earnings = pd.to_numeric(_wd.get("earnings_earned", _wd.get("points_earned")), errors="coerce")
                if pd.notna(_wk_num) and pd.notna(_wk_earnings):
                    _wk_totals[int(_wk_num)] = float(_wk_earnings)
            # Build per-week player → result / earnings lookup
            for _pname, _pdata in _tracker.get("picks", {}).items():
                for _tu in _pdata.get("tournaments_used", []):
                    _wk = _tu.get("week")
                    if _wk is not None:
                        _wk_player_res.setdefault(int(_wk), {})[_name_key(_pname)] = {
                            "result": _tu.get("result", ""),
                            "earnings": pd.to_numeric(_tu.get("earnings", _tu.get("points")), errors="coerce"),
                            "source": str(_tu.get("result_source", "")).strip(),
                        }
            # Hydrate any existing season_log rows with tracker results/earnings + saved model ranks.
            for _idx in _log.index:
                _wk_n = pd.to_numeric(_log.at[_idx, "week"], errors="coerce")
                if pd.isna(_wk_n):
                    continue
                _wk_n = int(_wk_n)
                _wr = _wk_player_res.get(_wk_n, {})
                _tournament_name = str(_log.at[_idx, "tournament"]).strip() if "tournament" in _log.columns else ""
                _event_date = str(_log.at[_idx, "date"]).strip() if "date" in _log.columns else ""
                _rank_lookup = load_prediction_rank_lookup_for_tournament(_tournament_name, _event_date)
                _rank_vals = []
                _has_non_cut_finish = False
                for _pi in range(1, 4):
                    _pick_col = f"pick{_pi}"
                    _result_col = f"result{_pi}"
                    _rank_col = f"rank{_pi}"
                    _pname = str(_log.at[_idx, _pick_col]).strip() if _pick_col in _log.columns and pd.notna(_log.at[_idx, _pick_col]) else ""
                    if not _pname:
                        continue
                    _pinfo = _wr.get(_name_key(_pname), {})
                    _existing_result = str(_log.at[_idx, _result_col]).strip() if _result_col in _log.columns and pd.notna(_log.at[_idx, _result_col]) else ""
                    if _result_col in _log.columns and (not _existing_result or _existing_result.lower() == "nan") and _pinfo.get("result"):
                        _log.at[_idx, _result_col] = _pinfo.get("result", "")
                    _final_result = str(_log.at[_idx, _result_col]).strip() if _result_col in _log.columns and pd.notna(_log.at[_idx, _result_col]) else ""
                    if _final_result and _final_result.upper() not in {"CUT", "MC", "WD", "DQ", "MDF", "W/D", "0"}:
                        _has_non_cut_finish = True
                    _rk = pd.to_numeric(_log.at[_idx, _rank_col], errors="coerce") if _rank_col in _log.columns else np.nan
                    if pd.isna(_rk):
                        _rk = _rank_lookup.get(_name_key(_pname), np.nan)
                        if pd.notna(_rk):
                            _log.at[_idx, _rank_col] = int(_rk)
                    if pd.notna(_rk):
                        _rank_vals.append(float(_rk))

                _existing_earnings = pd.to_numeric(_log.at[_idx, "earnings"], errors="coerce") if "earnings" in _log.columns else np.nan
                _week_total = _wk_totals.get(_wk_n)
                if "earnings" in _log.columns and pd.notna(_week_total) and (pd.isna(_existing_earnings) or float(_existing_earnings) <= 0):
                    _log.at[_idx, "earnings"] = int(_week_total)
                elif "earnings" in _log.columns and pd.notna(_existing_earnings) and float(_existing_earnings) <= 0 and _has_non_cut_finish:
                    _log.at[_idx, "earnings"] = np.nan
                if "avg_model_rank" in _log.columns and _rank_vals and pd.isna(pd.to_numeric(_log.at[_idx, "avg_model_rank"], errors="coerce")):
                    _log.at[_idx, "avg_model_rank"] = round(float(np.mean(_rank_vals)), 1)

            _new_rows = []
            for _wk_key in sorted(_wk_lineups.keys()):
                _wd = _wk_lineups[_wk_key]
                _wk_n = int(_wd.get("week", 0))
                if _wk_n > 0 and _wk_n not in _log_weeks:
                    _lp = (_wd.get("lineup") or [])[:3]
                    _lp = (_lp + ["", "", ""])[:3]
                    _wr = _wk_player_res.get(_wk_n, {})
                    _rs = [_wr.get(_name_key(_lp[i]), {}).get("result", "") for i in range(3)]
                    _tp = _wk_totals.get(_wk_n)
                    _rank_lookup = load_prediction_rank_lookup_for_tournament(_wd.get("tournament", ""), _wd.get("date", ""))
                    _ranks = [_rank_lookup.get(_name_key(_lp[i]), np.nan) for i in range(3)]
                    _new_rows.append({
                        "week": _wk_n, "date": _wd.get("date", ""),
                        "tournament": _wd.get("tournament", ""),
                        "pick1": _lp[0], "pick2": _lp[1], "pick3": _lp[2],
                        "result1": _rs[0], "result2": _rs[1], "result3": _rs[2],
                        "earnings": int(_tp) if pd.notna(_tp) else None,
                        "league_rank": None, "notes": "",
                        "rank1": _ranks[0] if pd.notna(_ranks[0]) else None,
                        "rank2": _ranks[1] if pd.notna(_ranks[1]) else None,
                        "rank3": _ranks[2] if pd.notna(_ranks[2]) else None,
                        "avg_model_rank": round(float(np.nanmean(_ranks)), 1) if any(pd.notna(x) for x in _ranks) else None,
                    })
            if _new_rows:
                _log = pd.concat([_log, pd.DataFrame(_new_rows)], ignore_index=True)
                _log = _log.sort_values("week").reset_index(drop=True)
        except Exception:
            pass

    if not _log.empty:
        _result_cols = [c for c in ["result1", "result2", "result3"] if c in _log.columns]
        if _result_cols:
            _completed = _log[
                _log[_result_cols]
                .astype(str)
                .apply(lambda col: col.str.strip().str.lower().replace("nan", ""))
                .ne("")
                .any(axis=1)
            ]
        else:
            _completed = pd.DataFrame()

        if not _completed.empty:
            
            # Pick Quality — per-pick breakdown table (all weeks)
            st.markdown("**Pick Quality — How closely did picks follow the model?**")

            _pq_rows = []
            for _, _slrow in _log.iterrows():
                _wk   = _slrow.get("week")
                _t    = str(_slrow.get("tournament", "")).strip()
                _note = str(_slrow.get("notes", "")).strip() if pd.notna(_slrow.get("notes")) else ""
                for _pi in range(1, 4):
                    _pn = _slrow.get(f"pick{_pi}")
                    _pr = _slrow.get(f"result{_pi}")
                    _rk = pd.to_numeric(_slrow.get(f"rank{_pi}"), errors="coerce")
                    if pd.notna(_pn) and str(_pn).strip() not in ("", "nan"):
                        _pinfo = _wk_player_res.get(int(_wk), {}).get(_name_key(str(_pn).strip()), {}) if pd.notna(_wk) else {}
                        _result_str = str(_pr).strip() if pd.notna(_pr) and str(_pr).strip() not in ("", "nan") else "—"
                        _fin = None
                        if _result_str not in ("—", "MC", "CUT", "WD", "DQ"):
                            try:
                                _fin = int(_result_str.replace("T", "").replace("t", ""))
                            except Exception:
                                pass
                        # Build finish label with emoji badge
                        if _fin is not None:
                            if _fin == 1:   _badge = "🏆"
                            elif _fin <= 5: _badge = "🟢"
                            elif _fin <= 10: _badge = "🟡"
                            elif _fin <= 20: _badge = "🔵"
                            else:           _badge = "⚪"
                            _result_disp = f"{_badge} {_result_str}"
                        elif _result_str in ("MC", "CUT"):
                            _result_disp = "❌ MC"
                        elif _result_str == "—":
                            _result_disp = "⏳ Pending"
                        else:
                            _result_disp = _result_str

                        _vs = ""
                        if pd.notna(_rk) and _fin is not None:
                            _diff = int(_rk) - _fin
                            if _diff > 5:   _vs = f"▲ +{_diff}"
                            elif _diff < -5: _vs = f"▼ {_diff}"
                            else:           _vs = f"~ {_diff:+d}"
                        elif pd.notna(_rk) and _result_str in ("MC", "CUT", "WD", "DQ"):
                            _vs = f"▼ {_result_str}"

                        # Per-pick FedEx Cup points from tracker
                        _pick_pts = _pinfo.get("earnings")
                        _pick_pts_v = int(_pick_pts) if pd.notna(_pick_pts) else "—"
                        # Weekly total from _wk_totals
                        _wk_total = _wk_totals.get(int(_wk)) if pd.notna(_wk) else None
                        _wk_pts_v = int(_wk_total) if _wk_total is not None and pd.notna(_wk_total) else "—"

                        _pq_rows.append({
                            "Wk":            int(_wk) if pd.notna(_wk) else "—",
                            "Tournament":    _t,
                            "Player":        str(_pn).strip(),
                            "Result":        _result_disp,
                            "FedEx Pts":     _pick_pts_v,
                            "Wk Total":      _wk_pts_v,
                            "Model Rank":    int(_rk) if pd.notna(_rk) else "—",
                            "vs Prediction": _vs,
                        })

            if _pq_rows:
                _pq_df = pd.DataFrame(_pq_rows)
                # Keep nullable integer dtypes so Arrow conversion is stable (avoid mixed int/"—" objects).
                for _num_col in ("Wk", "FedEx Pts", "Wk Total", "Model Rank"):
                    if _num_col in _pq_df.columns:
                        _pq_df[_num_col] = pd.to_numeric(_pq_df[_num_col], errors="coerce").astype("Int64")
                st.dataframe(
                    _pq_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Wk":         st.column_config.NumberColumn("Wk", width="small"),
                        "FedEx Pts":  st.column_config.NumberColumn("FedEx Pts", width="small",
                                        help="FedEx Cup points earned by this player"),
                        "Wk Total":   st.column_config.NumberColumn("Wk Total", width="small",
                                        help="Total FedEx Cup points for the week (all 3 picks combined)"),
                        "Model Rank": st.column_config.NumberColumn("Model Rank", width="small"),
                    },
                )
                st.caption("🏆 Win  🟢 Top 5  🟡 Top 10  🔵 Top 20  ⚪ Outside 20  ❌ Missed Cut  |  **vs Prediction**: ▲ outperformed model rank, ▼ underperformed")

            # Parse finish positions — handles "T28" → 28, "1" → 1, "MC" → None
            def _parse_finish(r):
                if pd.isna(r) or str(r).strip().upper() in ("MC", "CUT", "WD", "DQ", ""):
                    return None
                try:
                    return int(str(r).replace("T", "").replace("t", "").strip())
                except Exception:
                    return None

            # Build per-pick flat table from season log
            _pick_rows = []
            for _, _slrow in _completed.iterrows():
                for _pi in range(1, 4):
                    _pn = _slrow.get(f"pick{_pi}")
                    _pr = _slrow.get(f"result{_pi}")
                    _rk = _slrow.get(f"rank{_pi}")
                    if pd.notna(_pn) and str(_pn).strip():
                        _pick_rows.append({
                            "week":       _slrow["week"],
                            "tournament": _slrow["tournament"],
                            "player":     _pn,
                            "result":     _pr,
                            "finish":     _parse_finish(_pr),
                            "model_rank": pd.to_numeric(_rk, errors="coerce"),
                        })

        else:
            # Pending weeks only
            st.info("No completed weeks yet. Results will appear here after each tournament.")
            _display_cols = ["week", "tournament", "pick1", "pick2", "pick3", "notes"]
            _display_cols = [c for c in _display_cols if c in _log.columns]
            if not _log.empty:
                st.dataframe(_log[_display_cols], hide_index=True, use_container_width=True)
    else:
        st.info("Season log not found. It will appear here once picks are recorded.")

    # ── 2025 Season Review ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📚 2025 Season Review")
    st.caption("Reference from last year's winning season — use this to benchmark your 2026 strategy.")

    _h25_path = PROJECT_ROOT / "data" / "historical" / "Fantasy_Results_2025.csv"
    if _h25_path.exists():
        def _pm25(v):
            try: return float(str(v).replace("$","").replace(",","").strip())
            except: return 0.0

        _h25 = pd.read_csv(_h25_path)
        _h25["_total"]  = _h25["Total Earnings"].apply(_pm25)
        _h25["_e1"]     = _h25["Earnings"].apply(_pm25)
        _h25["_e2"]     = _h25["Earnings.1"].apply(_pm25)
        _h25["_e3"]     = _h25["Earnings.2"].apply(_pm25)
        _h25["_max"]    = _h25[["_e1","_e2","_e3"]].max(axis=1)
        _h25["_win_wk"] = _h25["_max"] >= 3_000_000   # winner on roster

        _s_total   = _h25["_total"].sum()
        _n_played  = (_h25["_total"] > 0).sum()
        _n_wins    = int(_h25["_win_wk"].sum())
        _win_earn  = _h25[_h25["_win_wk"]]["_total"].sum()
        _avg_wk    = _h25[_h25["_total"] > 0]["_total"].mean()
        _win_pct   = _win_earn / _s_total * 100 if _s_total > 0 else 0

        _hc1, _hc2, _hc3, _hc4 = st.columns(4)
        with _hc1: st.metric("Season Total",   f"${_s_total/1_000_000:.1f}M")
        with _hc2: st.metric("Win Weeks",      f"{_n_wins}",              help="Weeks where a picked player won the tournament")
        with _hc3: st.metric("Avg / Week",     f"${_avg_wk/1_000:.0f}K")
        with _hc4: st.metric("From Win Weeks", f"{_win_pct:.0f}%",        help="Share of total earnings generated by the 4 weeks a pick won")

        st.caption(
            f"**Key insight:** {_n_wins} win weeks generated ${_win_earn/1_000_000:.1f}M "
            f"({_win_pct:.0f}% of the season). The other {_n_played - _n_wins} weeks averaged "
            f"${(_s_total - _win_earn) / max(1, _n_played - _n_wins) / 1_000:.0f}K. "
            f"**This format is won by having a winner on your roster — not by floor/consistency.**"
        )

        # Bar chart: weekly earnings, green = win week
        _hfig = go.Figure()

        _nw = _h25[~_h25["_win_wk"]]
        _ww = _h25[_h25["_win_wk"]]

        _h25_hover = _h25[["Tournament","Starter #1","Starter #2","Starter #3"]].values

        _hfig.add_trace(go.Bar(
            x=_nw["Week"], y=_nw["_total"],
            name="Regular week",
            marker_color="#3498db",
            customdata=_nw[["Tournament","Starter #1","Starter #2","Starter #3"]].values,
            hovertemplate="<b>Wk %{x} — %{customdata[0]}</b><br>$%{y:,.0f}<br>"
                          "%{customdata[1]} | %{customdata[2]} | %{customdata[3]}<extra></extra>",
        ))
        _hfig.add_trace(go.Bar(
            x=_ww["Week"], y=_ww["_total"],
            name="Win week 🏆",
            marker_color="#00c44f",
            customdata=_ww[["Tournament","Starter #1","Starter #2","Starter #3"]].values,
            hovertemplate="<b>Wk %{x} — %{customdata[0]}</b><br>$%{y:,.0f}<br>"
                          "%{customdata[1]} | %{customdata[2]} | %{customdata[3]}<extra></extra>",
        ))
        _hfig.update_layout(
            barmode="overlay",
            title="2025 Weekly Earnings (hover for picks)",
            xaxis_title="Week", yaxis_title="Earnings ($)",
            height=280,
            margin=dict(t=40, b=20, l=0, r=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="#ccc",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(_hfig, use_container_width=True)

        with st.expander("📋 Full 2025 Week-by-Week Results"):
            _htable = _h25[["Week","Tournament","WRP","Starter #1","Starter #2","Starter #3","Total Earnings"]].copy()
            st.dataframe(_htable, hide_index=True, use_container_width=True)
    else:
        st.info("Historical data not found at `data/historical/Fantasy_Results_2025.csv`.")


# ============================================================================
# PAGE: PLAYERS (consolidated from Player Stats + Stats Deep Dive)
# ============================================================================

elif page == "👤 Players":
    st.markdown("## 👤 Players")
    st.caption("Player lookup, strokes gained analysis, and statistical deep dive")

    engine = load_scoring_engine(_scoring_engine_cache_key())
    all_players = sorted(engine.predictions.keys()) if engine and engine.predictions else []
    # Tabs for different views
    player_tab1, player_tab2, player_tab3 = st.tabs(["🔍 Player Lookup", "📊 Stats Deep Dive", "⚔️ Head-to-Head"])

    with player_tab1:
        st.markdown("### 🔍 Player Lookup")
        st.caption("Player event fit and usage optimization")

        col1, col2 = st.columns([3, 1])
        with col1:
            player_search = st.selectbox("Select a player:", [""] + all_players, key="quick_player")
        with col2:
            run_optimize = st.button("⚡ Optimize Uses", use_container_width=True, help="--optimize")

        if run_optimize and player_search:
            with st.spinner(f"Running: scoring_engine.py --optimize '{player_search}'"):
                output = run_script("planning/scoring_engine.py", "--optimize", player_search)
            st.code(output, language=None)

        # Show comprehensive player stats when selected
        if player_search:
            st.markdown("---")
            st.markdown(f"### 📊 {player_search}")

            # Load player data from predictions
            preds_path = OUTPUTS_DIR / "latest_predictions.csv"
            player_data = {}
            if preds_path.exists():
                preds_df = pd.read_csv(preds_path)
                player_row = preds_df[preds_df["player_name"].apply(_name_key) == _name_key(player_search)]
                if not player_row.empty:
                    player_data = player_row.iloc[0].to_dict()

            if player_data:
                _n_field = len(preds_df) if not preds_df.empty else 0
                _name_key_self = _name_key(player_search)
                _preds_ranked = preds_df.copy() if not preds_df.empty else pd.DataFrame()

                def _rank_in_field(col: str) -> int | None:
                    if _preds_ranked.empty or col not in _preds_ranked.columns:
                        return None
                    _tmp = _preds_ranked[["player_name", col]].copy()
                    _tmp[col] = pd.to_numeric(_tmp[col], errors="coerce")
                    _tmp = _tmp.sort_values(col, ascending=False, na_position="last").reset_index(drop=True)
                    _tmp["rank"] = np.arange(1, len(_tmp) + 1)
                    _m = _tmp[_tmp["player_name"].apply(_name_key) == _name_key_self]
                    if _m.empty:
                        return None
                    return int(_m.iloc[0]["rank"])

                _win_rank = _rank_in_field("win_prob")
                _top10_rank = _rank_in_field("top10_prob")
                _ev_rank = _rank_in_field("expected_value")

                def _fmt_pct(v, dec=1):
                    if v is None or pd.isna(v):
                        return "—"
                    return f"{float(v)*100:.{dec}f}%"

                def _fmt_ord(n):
                    if n is None:
                        return "—"
                    n = int(n)
                    if 10 <= (n % 100) <= 20:
                        s = "th"
                    else:
                        s = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                    return f"{n}{s}"

                win_prob = player_data.get("win_prob", 0) or 0
                top5 = player_data.get("top5_prob", 0) or 0
                top10 = player_data.get("top10_prob", 0) or 0
                ev = player_data.get("expected_value", 0) or 0
                sg = player_data.get("sg_total", 0) or 0
                owgr = player_data.get("owgr_rank", player_data.get("world_rank", None))
                hist_plays = player_data.get("hist_times_played", 0)
                hist_avg = player_data.get("hist_avg_finish", None)
                cut_prob = player_data.get("cut_prob", None)
                model_edge = player_data.get("model_vs_vegas_edge", None)
                usage_label = str(player_data.get("usage_recommendation", "") or "").strip()

                # Header context line under player name
                _context_bits = []
                if _ev_rank and _n_field:
                    _context_bits.append(f"EV {_fmt_ord(_ev_rank)}/{_n_field}")
                if _win_rank and _n_field:
                    _context_bits.append(f"Win {_fmt_ord(_win_rank)}/{_n_field}")
                if owgr is not None and pd.notna(owgr):
                    _context_bits.append(f"OWGR #{int(float(owgr))}")
                if usage_label:
                    _context_bits.append(f"Usage: {usage_label}")
                if _context_bits:
                    st.caption(" • ".join(_context_bits))

                # Course history compact line
                if hist_plays and int(hist_plays) > 0:
                    hist_best = player_data.get("hist_best_finish")
                    hist_wins_ct = int(player_data.get("hist_wins", 0) or 0)
                    hist_top10_ct = int(player_data.get("hist_top10s", 0) or 0)
                    hist_cut_r = player_data.get("hist_cut_rate")
                    _hparts = [f"{int(hist_plays)} starts at this course"]
                    if pd.notna(hist_best) and float(hist_best) < 40:
                        _hparts.append("best: Win" if float(hist_best) <= 1 else f"best: T{int(float(hist_best))}")
                    if hist_wins_ct > 0:
                        _hparts.append(f"{hist_wins_ct} win{'s' if hist_wins_ct > 1 else ''}")
                    elif hist_top10_ct > 0:
                        _hparts.append(f"{hist_top10_ct} top-10{'s' if hist_top10_ct > 1 else ''}")
                    if pd.notna(hist_cut_r):
                        _hparts.append(f"{float(hist_cut_r)*100:.0f}% cuts made")
                    st.caption(" · ".join(_hparts))

                # ── SNAPSHOT CARDS (grouped, less "floating") ───────────────────────
                with st.container(border=True):
                    st.markdown("#### Snapshot")
                    st.caption("Model outputs and market context for this week")

                    ensemble_win = player_data.get("ensemble_win_prob", None)
                    vegas_prob = player_data.get("vegas_prob", None)
                    top20 = player_data.get("top20_prob", None)
                    _edge_pp = (float(model_edge) * 100.0) if model_edge is not None and pd.notna(model_edge) else None
                    _ensemble_edge = None
                    if ensemble_win is not None and vegas_prob is not None and pd.notna(ensemble_win) and pd.notna(vegas_prob):
                        _ensemble_edge = (float(ensemble_win) - float(vegas_prob)) * 100.0

                    row1 = st.columns(4)
                    with row1[0]:
                        st.metric("Win %", _fmt_pct(win_prob, 2), f"#{_win_rank}" if _win_rank else None)
                    with row1[1]:
                        st.metric("Top 10 %", _fmt_pct(top10, 1), f"#{_top10_rank}" if _top10_rank else None)
                    with row1[2]:
                        st.metric("Cut %", _fmt_pct(cut_prob, 1) if cut_prob is not None else "—")
                    with row1[3]:
                        st.metric("Exp. Value", f"${ev:,.0f}", f"#{_ev_rank}" if _ev_rank else None)

                    row2 = st.columns(4)
                    with row2[0]:
                        st.metric("SG Total", f"{sg:.2f}")
                    with row2[1]:
                        st.metric("Model Edge", f"{_edge_pp:+.2f} pts" if _edge_pp is not None else "—")
                    with row2[2]:
                        st.metric("Model vs Vegas", f"{_ensemble_edge:+.2f} pts" if _ensemble_edge is not None else "—")
                    with row2[3]:
                        _hist_delta = f"{int(hist_plays)} starts" if pd.notna(hist_plays) else None
                        st.metric("Avg Finish (Course)", f"{hist_avg:.1f}" if pd.notna(hist_avg) else "—", _hist_delta)

                    row3 = st.columns(4)
                    with row3[0]:
                        st.metric("Top 5 %", _fmt_pct(top5, 1))
                    with row3[1]:
                        st.metric("Top 20 %", _fmt_pct(top20, 1) if top20 is not None else "—")
                    with row3[2]:
                        st.metric("Ensemble Win %", _fmt_pct(ensemble_win, 2) if ensemble_win is not None else "—")
                    with row3[3]:
                        st.metric("Vegas Win %", _fmt_pct(vegas_prob, 2) if vegas_prob is not None else "—")

                # ── RECENT FORM SPARKLINE ───────────────────────────────────────────
                # Shows per-event SG Total bars + decay-weighted form signal.
                # Complements the full form chart lower on the page — this gives
                # an immediate at-a-glance read without scrolling.
                with st.container(border=True):
                    st.markdown("#### Recent Form")
                    st.caption("SG Total per event (green = positive, red = negative) · Decay-weighted avg gives more weight to recent events")

                    _spark_form = load_player_form_history(n_events=8)
                    # Names may be "Last, First" — flip for lookup
                    _spark_name = player_search
                    if "," in str(player_search):
                        _sp = str(player_search).split(",", 1)
                        _spark_name = f"{_sp[1].strip()} {_sp[0].strip()}"

                    _spark_sg = _spark_form.get(_spark_name, {}).get("sg", [])
                    _spark_ev = _spark_form.get(_spark_name, {}).get("events", [])
                    _rsw      = player_data.get("recent_sg_weighted")
                    _rst      = player_data.get("recent_sg_trend")

                    _sp_col1, _sp_col2 = st.columns([3, 1])
                    with _sp_col1:
                        if _spark_sg:
                            _sp_colors = ["#00c44f" if v >= 0 else "#e74c3c" for v in _spark_sg]
                            _sfig = go.Figure()
                            _sfig.add_trace(go.Bar(
                                x=_spark_ev, y=_spark_sg,
                                marker_color=_sp_colors,
                                hovertemplate="%{x}<br>SG: %{y:+.2f}<extra></extra>",
                            ))
                            _sfig.add_hline(y=0, line_color="#4a6080", line_width=1)
                            _sfig.update_layout(
                                height=150,
                                margin=dict(t=4, b=4, l=0, r=0),
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="#dde6f5",
                                showlegend=False,
                                xaxis=dict(tickfont=dict(size=9), gridcolor="rgba(0,0,0,0)"),
                                yaxis=dict(gridcolor="#1c2f4a", zeroline=False),
                            )
                            st.plotly_chart(_sfig, use_container_width=True)
                        else:
                            st.caption("No per-event SG data available.")

                    with _sp_col2:
                        if _rsw is not None and pd.notna(_rsw):
                            st.metric(
                                "Weighted SG",
                                f"{float(_rsw):+.3f}",
                                help="Exponential decay avg of last 8 SG Total events. Most recent event = full weight, each prior event × 0.85."
                            )
                        if _rst is not None and pd.notna(_rst):
                            _rst_f = float(_rst)
                            _trend_label = "Heating up" if _rst_f > 0.05 else ("Cooling off" if _rst_f < -0.05 else "Stable")
                            _trend_color = "#00c44f" if _rst_f > 0.05 else ("#e74c3c" if _rst_f < -0.05 else "#7f8c8d")
                            st.metric(
                                "Trend",
                                f"{_rst_f:+.3f}",
                                help="(Avg last 3 events) − (avg events 4–8). Positive = form improving."
                            )
                            st.markdown(
                                f'<span style="color:{_trend_color};font-size:0.82em;font-weight:600;">{_trend_label}</span>',
                                unsafe_allow_html=True
                            )

                # ── PGA TOUR-STYLE STAT SHEET ───────────────────────────────────────
                with st.container(border=True):
                    st.markdown("#### 📋 PGA TOUR-Style Stat Sheet")
                    st.caption("Season values with field average context, rank, and percentile.")

                    def _num(v):
                        return pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]

                    def _pct100(v):
                        if pd.isna(v):
                            return np.nan
                        out = float(v)
                        if out <= 1.0:
                            out *= 100.0
                        return float(np.clip(out, 0.0, 100.0))

                    def _fmt_stat(v, kind):
                        if pd.isna(v):
                            return "—"
                        if kind == "sg":
                            return f"{float(v):+.3f}"
                        if kind == "pct":
                            return f"{float(v):.1f}%"
                        if kind == "distance":
                            return f"{float(v):.1f}"
                        if kind == "score":
                            return f"{float(v):.2f}"
                        return f"{float(v):.2f}"

                    def _fmt_adv(v, kind):
                        if pd.isna(v):
                            return "—"
                        arrow = "▲" if v > 0.0 else ("▼" if v < 0.0 else "•")
                        if kind == "sg":
                            return f"{arrow} {float(v):+.3f}"
                        if kind == "pct":
                            return f"{arrow} {float(v):+.1f} pts"
                        if kind == "distance":
                            return f"{arrow} {float(v):+.1f}"
                        return f"{arrow} {float(v):+.2f}"

                    def _rank_text(rank, pct):
                        if rank is None or pd.isna(rank):
                            return "—"
                        r = int(rank)
                        if _n_field:
                            return f"{_fmt_ord(r)} / {_n_field} ({pct:.0f}th pct)" if not pd.isna(pct) else f"{_fmt_ord(r)} / {_n_field}"
                        return _fmt_ord(r)

                    def _build_stat_row(
                        category: str,
                        label: str,
                        value_col: str,
                        avg_col: str | None,
                        rank_col: str | None,
                        pct_col: str | None,
                        kind: str,
                        higher_is_better: bool = True,
                    ) -> dict:
                        val = _num(player_data.get(value_col))
                        avg = _num(player_data.get(avg_col)) if avg_col else np.nan
                        if pd.isna(avg) and not _preds_ranked.empty and value_col in _preds_ranked.columns:
                            avg = pd.to_numeric(_preds_ranked[value_col], errors="coerce").mean()

                        rank_raw = _num(player_data.get(rank_col)) if rank_col else _rank_in_field(value_col)
                        rank = int(rank_raw) if not pd.isna(rank_raw) else None

                        pct = _pct100(_num(player_data.get(pct_col))) if pct_col else np.nan
                        if pd.isna(pct) and rank is not None and _n_field:
                            pct = ((float(_n_field) - float(rank) + 1.0) / float(_n_field)) * 100.0

                        # Positive "adv" always means better than field average.
                        adv = np.nan
                        if not pd.isna(val) and not pd.isna(avg):
                            adv = (val - avg) if higher_is_better else (avg - val)

                        return {
                            "Category": category,
                            "Stat": label,
                            "Player": _fmt_stat(val, kind),
                            "Field Avg": _fmt_stat(avg, kind),
                            "Adv vs Field": _fmt_adv(adv, "pct" if kind == "pct" else kind),
                            "Field %": float(pct) if not pd.isna(pct) else np.nan,
                            "Field Rank": _rank_text(rank, pct),
                        }

                    sg_rows = [
                        _build_stat_row("Strokes Gained", "SG: Off-the-Tee", "season_sg_ott", "field_avg_season_sg_ott", "season_sg_ott_field_rank", "season_sg_ott_field_pct", "sg", True),
                        _build_stat_row("Strokes Gained", "SG: Approach", "season_sg_app", "field_avg_season_sg_app", "season_sg_app_field_rank", "season_sg_app_field_pct", "sg", True),
                        _build_stat_row("Strokes Gained", "SG: Around Green", "season_sg_arg", "field_avg_season_sg_arg", "season_sg_arg_field_rank", "season_sg_arg_field_pct", "sg", True),
                        _build_stat_row("Strokes Gained", "SG: Putting", "season_sg_putt", "field_avg_season_sg_putt", "season_sg_putt_field_rank", "season_sg_putt_field_pct", "sg", True),
                        _build_stat_row("Strokes Gained", "SG: Total", "season_sg_total", "field_avg_season_sg_total", None, None, "sg", True),
                        _build_stat_row("Strokes Gained", "Course Fit (DG)", "dg_fit_total", None, None, None, "score", True),
                    ]

                    scoring_rows = [
                        _build_stat_row("Scoring/Ball-Striking", "Driving Distance", "driving_dist_val", "driving_dist_field_avg", "driving_dist_field_rank", "driving_dist_field_pct", "distance", True),
                        _build_stat_row("Scoring/Ball-Striking", "GIR %", "gir_pct_val", "gir_pct_field_avg", "gir_pct_field_rank", "gir_pct_field_pct", "pct", True),
                        _build_stat_row("Scoring/Ball-Striking", "Scrambling %", "scrambling_val", "scrambling_field_avg", "scrambling_field_rank", "scrambling_field_pct", "pct", True),
                        _build_stat_row("Scoring/Ball-Striking", "Bogey Avoidance %", "bogey_avoid_val", "bogey_avoid_field_avg", "bogey_avoid_field_rank", "bogey_avoid_field_pct", "pct", True),
                        _build_stat_row("Scoring/Ball-Striking", "Birdie Average", "birdie_avg_val", "birdie_avg_field_avg", "birdie_avg_field_rank", "birdie_avg_field_pct", "score", True),
                        _build_stat_row("Scoring/Ball-Striking", "Putts / Round", "putts_per_round_val", "putts_per_round_field_avg", "putts_per_round_field_rank", "putts_per_round_field_pct", "score", False),
                    ]

                    _sg_df = pd.DataFrame(sg_rows)
                    _scoring_df = pd.DataFrame(scoring_rows)
                    _stat_col1, _stat_col2 = st.columns(2)
                    with _stat_col1:
                        st.markdown("**Strokes Gained / Fit**")
                        st.dataframe(
                            _sg_df,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Field %": st.column_config.ProgressColumn("Field %", min_value=0.0, max_value=100.0, format="%.0f%%"),
                            },
                        )
                    with _stat_col2:
                        st.markdown("**Scoring / Ball-Striking**")
                        st.dataframe(
                            _scoring_df,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Field %": st.column_config.ProgressColumn("Field %", min_value=0.0, max_value=100.0, format="%.0f%%"),
                            },
                        )


                # ── RECENT FORM TREND (line + rolling average) ───────────────────────
                st.markdown("---")
                st.markdown("#### 📈 Recent Form — SG: Total")
                st.caption(
                    "Trajectory of SG:Total over recent events with rolling trend line. "
                    "Above 0 = gaining on field."
                )

                _form_col1, _form_col2, _form_col3 = st.columns([1.2, 1.4, 1.4])
                with _form_col1:
                    _form_window = st.slider("Events", 6, 16, 10, 1, key="player_form_window")
                with _form_col2:
                    _rolling_n = st.slider("Rolling Avg", 2, 6, 3, 1, key="player_form_roll")
                with _form_col3:
                    _compare_name = st.selectbox(
                        "Compare (optional)",
                        options=["None"] + [p for p in all_players if p != player_search],
                        index=0,
                        key="player_form_compare",
                    )

                form_data = load_player_form_history(n_events=_form_window)
                recent_results = load_player_recent_results(n_events=_form_window)

                # Predictions store names as "Last, First" while training data uses "First Last".
                # Flip format for lookup in form history map.
                def _flip_name(n):
                    text = str(n).strip()
                    if "," in text:
                        last, first = text.split(",", 1)
                        return f"{first.strip()} {last.strip()}"
                    return text

                _lookup = _flip_name(player_search)
                if _lookup in form_data:
                    _fd = form_data[_lookup]
                    _sg = _fd["sg"]
                    _ev = _fd["events"]
                    _sg_event_ids = set(_fd.get("event_ids", []))

                    _res = recent_results.get(_lookup, {})
                    _res_ids = _res.get("event_ids", [])
                    _res_names = _res.get("events", [])
                    _missing = [(tid, name) for tid, name in zip(_res_ids, _res_names) if tid not in _sg_event_ids]
                    if _missing:
                        _latest_missing = ", ".join([f"{name} ({tid})" for tid, name in _missing[:3]])
                        st.warning(
                            f"Official SG feed is available for {len(_sg_event_ids)} of your last {len(_res_ids)} starts. "
                            f"Missing latest event(s): {_latest_missing}. "
                            "This is why the recent SG chart may not include the last one or two starts."
                        )

                    _avg = float(np.mean(_sg)) if _sg else 0.0
                    _roll = pd.Series(_sg, dtype=float).rolling(window=_rolling_n, min_periods=1).mean().tolist()
                    _trend_slope = 0.0
                    if len(_sg) >= 2:
                        _x = np.arange(len(_sg), dtype=float)
                        _trend_slope = float(np.polyfit(_x, np.array(_sg, dtype=float), 1)[0])
                    _trend_label = "📈 Rising trend" if _trend_slope > 0 else "📉 Cooling trend"

                    st.caption(
                        f"Last {len(_sg)} events  ·  Avg SG: {_avg:+.2f}  ·  "
                        f"Trend slope: {_trend_slope:+.3f}/event  ·  {_trend_label}"
                    )

                    _fig = go.Figure()
                    _fig.add_trace(go.Scatter(
                        x=_ev, y=_sg, mode="lines+markers",
                        name=player_search,
                        line=dict(color="#00c44f", width=2.5),
                        marker=dict(size=7, color="#00c44f"),
                        hovertemplate="%{x}<br>SG: %{y:+.2f}<extra></extra>",
                    ))
                    _fig.add_trace(go.Scatter(
                        x=_ev, y=_roll, mode="lines",
                        name=f"{player_search} {_rolling_n}-event avg",
                        line=dict(color="#4cb8ff", width=2, dash="dash"),
                        hovertemplate="%{x}<br>Rolling: %{y:+.2f}<extra></extra>",
                    ))

                    if _compare_name != "None":
                        _cmp_lookup = _flip_name(_compare_name)
                        if _cmp_lookup in form_data:
                            _cfd = form_data[_cmp_lookup]
                            _csg = _cfd["sg"]
                            _cev = _cfd["events"]
                            _croll = pd.Series(_csg, dtype=float).rolling(window=_rolling_n, min_periods=1).mean().tolist()
                            _fig.add_trace(go.Scatter(
                                x=_cev, y=_csg, mode="lines+markers",
                                name=_compare_name,
                                line=dict(color="#f59e0b", width=2),
                                marker=dict(size=6, color="#f59e0b"),
                                hovertemplate="%{x}<br>SG: %{y:+.2f}<extra></extra>",
                            ))
                            _fig.add_trace(go.Scatter(
                                x=_cev, y=_croll, mode="lines",
                                name=f"{_compare_name} {_rolling_n}-event avg",
                                line=dict(color="#ffcc66", width=2, dash="dot"),
                                hovertemplate="%{x}<br>Rolling: %{y:+.2f}<extra></extra>",
                            ))

                    _fig.add_hline(y=0, line_dash="dot", line_color="#4a6080", line_width=1)
                    _fig.update_layout(
                        height=290,
                        margin=dict(t=10, b=10, l=0, r=0),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#dde6f5",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                        xaxis=dict(tickfont=dict(size=9), gridcolor="#1c2f4a"),
                        yaxis=dict(gridcolor="#1c2f4a", zeroline=False, title="SG: Total"),
                    )
                    st.plotly_chart(_fig, use_container_width=True)
                else:
                    _res = recent_results.get(_lookup, {})
                    if _res:
                        st.caption(
                            f"Recent starts exist for **{player_search}** ({len(_res.get('event_ids', []))} events), "
                            "but SG:Total is not available yet in tournament stats."
                        )
                    else:
                        st.caption(f"Historical SG data not found for **{player_search}**.")


                
                
                # ── SKILL PROFILE (DataGolf-style percentile bars) ────────────────────
                st.markdown("#### Skill Profile (Field Percentile)")
                st.caption(
                    "Percentile rank within this week's field (0-100). "
                    "Color scale: red (low) → yellow (mid) → green (high)."
                )

                _n_field = len(preds_df) if not preds_df.empty else None

                def _ordinal(n):
                    n = int(n)
                    if 10 <= (n % 100) <= 20:
                        suffix = "th"
                    else:
                        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                    return f"{n}{suffix}"

                def _pct_from_value(v):
                    if v is None or pd.isna(v):
                        return np.nan
                    out = float(v)
                    if out <= 1.0:
                        out *= 100.0
                    return float(np.clip(out, 0.0, 100.0))

                def _pct_color(pct):
                    if pct is None or pd.isna(pct):
                        return "#4a6080"
                    p = float(np.clip(pct, 0.0, 100.0))
                    if p <= 50.0:
                        # red -> yellow
                        t = p / 50.0
                        r = int(229 + (240 - 229) * t)
                        g = int(57 + (180 - 57) * t)
                        b = int(53 + (66 - 53) * t)
                    else:
                        # yellow -> green
                        t = (p - 50.0) / 50.0
                        r = int(240 + (0 - 240) * t)
                        g = int(180 + (196 - 180) * t)
                        b = int(66 + (79 - 66) * t)
                    return f"rgb({r},{g},{b})"

                def _build_skill_rows(group_name, defs):
                    rows = []
                    for label, pct_key, rank_key in defs:
                        pct = _pct_from_value(player_data.get(pct_key))
                        rank_raw = player_data.get(rank_key)
                        rank = int(rank_raw) if rank_raw is not None and not pd.isna(rank_raw) else None

                        if pct is not None and not pd.isna(pct):
                            pct_label = f"{_ordinal(int(round(pct)))} pct"
                        else:
                            pct_label = "N/A pct"

                        if rank is not None and _n_field:
                            rank_label = f"{_ordinal(rank)} / {_n_field}"
                        elif rank is not None:
                            rank_label = _ordinal(rank)
                        else:
                            rank_label = "—"

                        rows.append({
                            "group": group_name,
                            "label": label,
                            "pct": pct if pct is not None and not pd.isna(pct) else 0.0,
                            "has_pct": pct is not None and not pd.isna(pct),
                            "rank": rank,
                            "text": f"{pct_label}  |  {rank_label}",
                            "color": _pct_color(pct),
                        })
                    return rows

                _sg_skill_defs = [
                    ("Off The Tee", "season_sg_ott_field_pct", "season_sg_ott_field_rank"),
                    ("Approach", "season_sg_app_field_pct", "season_sg_app_field_rank"),
                    ("Around Green", "season_sg_arg_field_pct", "season_sg_arg_field_rank"),
                    ("Putting", "season_sg_putt_field_pct", "season_sg_putt_field_rank"),
                ]
                _non_sg_skill_defs = [
                    ("Driving Dist", "driving_dist_field_pct", "driving_dist_field_rank"),
                    ("GIR %", "gir_pct_field_pct", "gir_pct_field_rank"),
                    ("Scrambling", "scrambling_field_pct", "scrambling_field_rank"),
                    ("Bogey Avoid", "bogey_avoid_field_pct", "bogey_avoid_field_rank"),
                    ("Birdie Rate", "birdie_avg_field_pct", "birdie_avg_field_rank"),
                ]

                _skill_rows = _build_skill_rows("SG Skills", _sg_skill_defs) + _build_skill_rows("Non-SG Skills", _non_sg_skill_defs)
                _skill_df = pd.DataFrame(_skill_rows)

                def _render_skill_group(df_group, title):
                    if df_group.empty:
                        return
                    st.markdown(f"**{title}**")

                    fig = go.Figure()
                    fig.add_trace(
                        go.Bar(
                            x=df_group["pct"].tolist(),
                            y=df_group["label"].tolist(),
                            orientation="h",
                            marker=dict(
                                color=df_group["color"].tolist(),
                                line=dict(color="#223248", width=1),
                            ),
                            text=df_group["text"].tolist(),
                            textposition="outside",
                            cliponaxis=False,
                            hovertemplate="%{y}<br>%{x:.1f}th pct<extra></extra>",
                        )
                    )

                    fig.add_vline(x=50, line_dash="dot", line_color="#4a6080", line_width=1)
                    fig.update_layout(
                        height=max(220, 48 * len(df_group)),
                        margin=dict(t=8, b=8, l=6, r=150),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#dde6f5",
                        showlegend=False,
                        xaxis=dict(
                            range=[0, 108],
                            tickvals=[0, 50, 100],
                            ticksuffix="%",
                            gridcolor="#1c2f4a",
                            title="",
                        ),
                        yaxis=dict(
                            title="",
                            gridcolor="rgba(0,0,0,0)",
                            categoryorder="array",
                            categoryarray=list(reversed(df_group["label"].tolist())),
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                st.caption("0% low skill in this field · 50% field median · 100% elite for this field")
                _render_skill_group(_skill_df[_skill_df["group"] == "SG Skills"], "SG Skills")
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                _render_skill_group(_skill_df[_skill_df["group"] == "Non-SG Skills"], "Non-SG Skills")

                if not _skill_df.empty:
                    _valid = _skill_df[_skill_df["has_pct"]]
                    if not _valid.empty:
                        _best = _valid.sort_values("pct", ascending=False).iloc[0]
                        _worst = _valid.sort_values("pct", ascending=True).iloc[0]
                        st.caption(
                            f"Best relative skill: **{_best['label']}** ({_best['text']})  ·  "
                            f"Weakest relative skill: **{_worst['label']}** ({_worst['text']})"
                        )

                # ── SKILL FINGERPRINT (Radar / Spider) ──────────────────────────────
                st.markdown("#### 🕸️ Skill Fingerprint")
                st.caption(
                    "Radar profile (0–100 field percentile): OTT, APP, ARG, PUTT, and Course Fit. "
                    "Use this for quick archetype + H2H shape comparison. "
                    "Dashed gray ring = tour-average reference level."
                )

                def _field_pct_for_row(row_dict: dict, col_name: str) -> float:
                    """Resolve percentile value from row (supports 0-1 or 0-100 formats)."""
                    val = row_dict.get(col_name, np.nan)
                    if pd.isna(val):
                        return np.nan
                    out = float(val)
                    if out <= 1.0:
                        out *= 100.0
                    return float(np.clip(out, 0.0, 100.0))

                def _series_percentile(df_in: pd.DataFrame, row_dict: dict, col_name: str, higher_is_better: bool = True) -> float:
                    """Compute row percentile against field for a numeric column."""
                    if df_in.empty or col_name not in df_in.columns:
                        return np.nan
                    series = pd.to_numeric(df_in[col_name], errors="coerce")
                    if series.notna().sum() < 5:
                        return np.nan
                    row_val = pd.to_numeric(pd.Series([row_dict.get(col_name, np.nan)]), errors="coerce").iloc[0]
                    if pd.isna(row_val):
                        return np.nan
                    pct = float((series <= row_val).mean() * 100.0) if higher_is_better else float((series >= row_val).mean() * 100.0)
                    return float(np.clip(pct, 0.0, 100.0))

                def _percentile_of_raw(df_in: pd.DataFrame, col_name: str, raw_val: float = 0.0, higher_is_better: bool = True) -> float:
                    """Percentile of a raw baseline value against field distribution for one stat."""
                    if df_in.empty or col_name not in df_in.columns:
                        return np.nan
                    series = pd.to_numeric(df_in[col_name], errors="coerce").dropna()
                    if len(series) < 5:
                        return np.nan
                    pct = float((series <= raw_val).mean() * 100.0) if higher_is_better else float((series >= raw_val).mean() * 100.0)
                    return float(np.clip(pct, 0.0, 100.0))

                def _build_radar_vector(row_dict: dict) -> tuple[list[str], list[float]]:
                    labels = ["Off The Tee", "Approach", "Around Green", "Putting", "Course Fit"]
                    ott = _field_pct_for_row(row_dict, "season_sg_ott_field_pct")
                    app = _field_pct_for_row(row_dict, "season_sg_app_field_pct")
                    arg = _field_pct_for_row(row_dict, "season_sg_arg_field_pct")
                    putt = _field_pct_for_row(row_dict, "season_sg_putt_field_pct")

                    # Course fit percentile fallback order
                    fit = _series_percentile(preds_df, row_dict, "dg_fit_total", higher_is_better=True)
                    if pd.isna(fit):
                        fit = _series_percentile(preds_df, row_dict, "course_fit_score", higher_is_better=True)
                    if pd.isna(fit):
                        fit = _series_percentile(preds_df, row_dict, "course_perf_score", higher_is_better=True)

                    values = [ott, app, arg, putt, fit]
                    # Replace missing with neutral midpoint for polygon continuity.
                    values = [50.0 if pd.isna(v) else float(v) for v in values]
                    return labels, values

                _radar_labels, _radar_vals = _build_radar_vector(player_data)
                _rfig = go.Figure()

                # Tour-average baseline in this field:
                # SG categories use raw 0.0 as tour-average SG.
                # Course Fit uses dg_fit_total (0.0 baseline) when available.
                _tour_axis_vals = [
                    _percentile_of_raw(preds_df, "season_sg_ott", raw_val=0.0, higher_is_better=True),
                    _percentile_of_raw(preds_df, "season_sg_app", raw_val=0.0, higher_is_better=True),
                    _percentile_of_raw(preds_df, "season_sg_arg", raw_val=0.0, higher_is_better=True),
                    _percentile_of_raw(preds_df, "season_sg_putt", raw_val=0.0, higher_is_better=True),
                    _percentile_of_raw(preds_df, "dg_fit_total", raw_val=0.0, higher_is_better=True),
                ]
                _tour_axis_vals = [50.0 if pd.isna(v) else float(v) for v in _tour_axis_vals]
                _tour_ring = float(np.mean(_tour_axis_vals)) if _tour_axis_vals else 50.0

                # Circular ring around chart (requested): average tour baseline level.
                _rfig.add_trace(go.Scatterpolar(
                    r=[_tour_ring] * len(_radar_labels),
                    theta=_radar_labels,
                    mode="lines",
                    name=f"Tour Avg Ring ({_tour_ring:.0f}th pct)",
                    line=dict(color="#8fa1ba", width=1.5, dash="dash"),
                    hovertemplate="Tour Avg Ring<br>%{r:.1f}th pct<extra></extra>",
                ))

                # By-stat tour baseline (subtle) so each axis also has explicit reference.
                _rfig.add_trace(go.Scatterpolar(
                    r=_tour_axis_vals,
                    theta=_radar_labels,
                    mode="lines+markers",
                    name="Tour Avg by Stat",
                    line=dict(color="#6f7f96", width=1.2, dash="dot"),
                    marker=dict(size=5, color="#6f7f96"),
                    hovertemplate="%{theta}<br>Tour Avg: %{r:.1f}th pct<extra></extra>",
                ))

                _rfig.add_trace(go.Scatterpolar(
                    r=_radar_vals,
                    theta=_radar_labels,
                    fill="toself",
                    name=player_search,
                    line=dict(color="#00c44f", width=2),
                    fillcolor="rgba(0,196,79,0.22)",
                    hovertemplate="%{theta}<br>%{r:.1f}th pct<extra></extra>",
                ))

                if _compare_name != "None" and not preds_df.empty:
                    _cmp_row = preds_df[preds_df["player_name"].apply(_name_key) == _name_key(_compare_name)]
                    if not _cmp_row.empty:
                        _cmp_data = _cmp_row.iloc[0].to_dict()
                        _c_labels, _c_vals = _build_radar_vector(_cmp_data)
                        _rfig.add_trace(go.Scatterpolar(
                            r=_c_vals,
                            theta=_c_labels,
                            fill="toself",
                            name=_compare_name,
                            line=dict(color="#4cb8ff", width=2),
                            fillcolor="rgba(76,184,255,0.20)",
                            hovertemplate="%{theta}<br>%{r:.1f}th pct<extra></extra>",
                        ))

                _rfig.update_layout(
                    height=380,
                    margin=dict(t=8, b=8, l=8, r=8),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#dde6f5",
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[0, 100],
                            tickvals=[0, 25, 50, 75, 100],
                            ticksuffix="%",
                            gridcolor="#1c2f4a",
                            linecolor="#1c2f4a",
                        ),
                        angularaxis=dict(
                            gridcolor="#1c2f4a",
                            linecolor="#1c2f4a",
                        ),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                st.plotly_chart(_rfig, use_container_width=True)

                
                


                                                                
                                
                
                
                
                
                
                
                
                
                
                
                                           

            # Betting profile if available
            _profiles_tid = _tournament_id_from_df(preds_df)
            if not _profiles_tid:
                _profiles_tid = _latest_tournament_id_from_prop_lines()
            profiles_df = load_betting_profiles(_profiles_tid if _profiles_tid else None)
            if not profiles_df.empty:
                profile = get_player_profile(profiles_df, player_search)
                if profile:
                    st.markdown("#### 🎰 Betting Profile")
                    render_player_profile_card(profile, show_full=True)

            # ── Strokes Gained ─────────────────────────────────────────────────
            # Pulled from latest_predictions.csv — season SG vs field average.
            # This is the single most predictive stat category in golf.
            _preds_path = OUTPUTS_DIR / "latest_predictions.csv"
            if _preds_path.exists():
                try:
                    _sg_df = pd.read_csv(_preds_path)
                    # Normalize names for matching
                    def _norm_name(n):
                        s = str(n).strip()
                        if ", " in s:
                            last, first = s.split(", ", 1)
                            return f"{first} {last}"
                        return s
                    _sg_df["_norm"] = _sg_df["player_name"].apply(_norm_name)
                    _sg_last = player_search.strip().split()[-1].lower()
                    _sg_row = _sg_df[_sg_df["_norm"].str.lower().str.contains(_sg_last, na=False)]
                    if _sg_row.empty:
                        _sg_row = _sg_df[_sg_df["player_name"].str.lower().str.contains(_sg_last, na=False)]

                    if not _sg_row.empty:
                        _sg = _sg_row.iloc[0]
                        st.markdown("---")
                        st.markdown("#### Strokes Gained")
                        st.caption("Season SG vs field average for this week's field · Positive = better than field · Rank = position among players in this event's field")

                        _SG_DEFS = [
                            ("sg_total",  "SG: Total",     "season_sg_total_vs_field",  None),
                            ("sg_ott",    "SG: Off Tee",   "season_sg_ott_vs_field",    "season_sg_ott_field_rank"),
                            ("sg_app",    "SG: Approach",  "season_sg_app_vs_field",    "season_sg_app_field_rank"),
                            ("sg_arg",    "SG: Arg Green", "season_sg_arg_vs_field",    "season_sg_arg_field_rank"),
                            ("sg_putt",   "SG: Putting",   "season_sg_putt_vs_field",   "season_sg_putt_field_rank"),
                        ]

                        def _sg_rank_color(rank):
                            try:
                                r = int(rank)
                                if r <= 5:   return "#00c44f"
                                if r <= 15:  return "#6ddb9a"
                                if r <= 35:  return "#dde6f5"
                                if r <= 60:  return "#ffa726"
                                return "#e53935"
                            except Exception:
                                return "#4a6080"

                        _sg_cols = st.columns(5)
                        for _sci, (_col, _label, _vs_col, _rank_col) in enumerate(_SG_DEFS):
                            _sg_val = _sg.get(_vs_col) if _vs_col and pd.notna(_sg.get(_vs_col, float("nan"))) else _sg.get(_col)
                            _sg_rank = _sg.get(_rank_col) if _rank_col else None
                            _sg_num = float(_sg_val) if pd.notna(_sg_val) else None
                            _sg_rank_num = int(_sg_rank) if _sg_rank and pd.notna(_sg_rank) else None

                            _sg_color = _sg_rank_color(_sg_rank_num) if _sg_rank_num else ("#00c44f" if (_sg_num or 0) > 0 else "#e53935")
                            _sg_val_str = f"{_sg_num:+.2f}" if _sg_num is not None else "—"
                            _sg_rank_str = f"#{_sg_rank_num}" if _sg_rank_num else "—"

                            with _sg_cols[_sci]:
                                st.markdown(
                                    f"<div style='background:#0b1929;border:1px solid #1a3050;"
                                    f"border-top:3px solid {_sg_color};border-radius:8px;"
                                    f"padding:10px 12px;text-align:center;'>"
                                    f"<div style='font-size:10px;color:#4a6080;margin-bottom:6px;"
                                    f"font-weight:700;letter-spacing:.6px;text-transform:uppercase;'>{_label}</div>"
                                    f"<div style='font-size:22px;font-weight:800;color:#dde6f5;'>{_sg_val_str}</div>"
                                    f"<div style='font-size:12px;color:{_sg_color};margin-top:2px;font-weight:700;'>"
                                    f"Field rank {_sg_rank_str}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                except Exception:
                    pass

            # ── Recent Form Stats ──────────────────────────────────────────────
            # Loads actual PGA Tour stat data from form_stats_2026.csv.
            # Shows all 19 tracked stats grouped by category, with field rank
            # (colored by percentile) and a trend arrow based on rank over the
            # last 3 tournaments — so you can see if a player is improving or fading.
            _fs_path = DATA_DIR / "historical" / "form_stats_2026.csv"
            if _fs_path.exists():
                try:
                    _fs_all = pd.read_csv(_fs_path)
                    # Fuzzy match: try exact name first, then last-name substring
                    _fs_player = _fs_all[_fs_all["player_name"] == player_search]
                    if _fs_player.empty:
                        _fs_last = player_search.strip().split()[-1].lower()
                        _fs_player = _fs_all[
                            _fs_all["player_name"].str.lower().str.contains(_fs_last, na=False)
                        ]

                    if not _fs_player.empty:
                        st.markdown("---")
                        st.markdown("#### Recent Form Stats")
                        st.caption("PGA Tour stats from this season · Rank = position among all players in that tournament · Trend = rank change over last 3 events")

                        # Group stats into categories for readability
                        # 2419=Bogey Avg/Rnd, 2414=Bogey Avoid% (scraper had wrong labels)
                        # 2675/2567/2568/2569/2564 = SG stats (display only, from extended scrape)
                        _FS_GROUPS = {
                            "Strokes Gained": [2675, 2567, 2568, 2569, 2564],
                            "Scoring":        [120, 156, 108, 160],
                            "Driving":        [101, 102, 2401],
                            "Approach":       [103, 331, 130, 299, 142, 143],
                            "Putting":        [104, 119, 413],
                            "Consistency":    [352, 2414, 2419, 111],
                        }
                        # Override display names for mislabeled or verbose stat names
                        _FS_NAME_OVERRIDE = {
                            2419: "Bogey Avg/Rnd",
                            2414: "Bogey Avoid%",
                            2675: "SG: Total",
                            2567: "SG: Off Tee",
                            2568: "SG: Approach",
                            2569: "SG: Arg Green",
                            2564: "SG: Putting",
                            2401: "Club Hd Spd",
                        }
                        # Which stats are "lower is better" (rank 1 = best = lowest value)
                        _LOWER_BETTER = {104, 413, 142, 143, 299, 120, 2419, 2414}

                        def _rank_color(rank):
                            try:
                                r = int(rank)
                                if r <= 10:  return "#00c44f"
                                if r <= 30:  return "#6ddb9a"
                                if r <= 60:  return "#dde6f5"
                                if r <= 100: return "#ffa726"
                                return "#e53935"
                            except Exception:
                                return "#4a6080"

                        def _trend_arrow(stat_id):
                            """▲ improving / ▼ declining / → stable based on rank over last 3 events."""
                            _sid_rows = _fs_player[_fs_player["stat_id"] == stat_id].sort_values("tournament_id")
                            if len(_sid_rows) < 2:
                                return "—", "#4a6080"
                            ranks = pd.to_numeric(_sid_rows["rank"], errors="coerce").dropna().tolist()
                            if len(ranks) < 2:
                                return "—", "#4a6080"
                            # Rank improving = number going down
                            delta = ranks[-1] - ranks[-2]
                            if delta <= -3:   return "▲", "#00c44f"
                            elif delta >= 3:  return "▼", "#e53935"
                            else:             return "→", "#4a6080"

                        for _grp_name, _stat_ids in _FS_GROUPS.items():
                            _grp_rows = []
                            for _sid in _stat_ids:
                                _sid_data = _fs_player[_fs_player["stat_id"] == _sid]
                                if _sid_data.empty:
                                    continue
                                # Most recent tournament entry
                                _latest = _sid_data.sort_values("tournament_id", ascending=False).iloc[0]
                                _trend, _tcolor = _trend_arrow(_sid)
                                _grp_rows.append({
                                    "Stat":       _FS_NAME_OVERRIDE.get(_sid, _latest["stat_name"]),
                                    "Value":      _latest["stat_value"],
                                    "Rank":       int(_latest["rank"]) if pd.notna(_latest["rank"]) else "—",
                                    "_rank_num":  _latest["rank"],
                                    "Trend":      _trend,
                                    "_tcolor":    _tcolor,
                                    "Tournament": _latest["tournament_name"],
                                })

                            if not _grp_rows:
                                continue

                            st.markdown(
                                f"<div style='font-size:11px;font-weight:700;color:#4a6080;"
                                f"letter-spacing:.8px;text-transform:uppercase;"
                                f"margin:14px 0 6px;'>{_grp_name}</div>",
                                unsafe_allow_html=True,
                            )

                            # Render as a compact card grid (up to 3 per row)
                            _row_items = _grp_rows
                            _cols_per_row = min(3, len(_row_items))
                            for _chunk_start in range(0, len(_row_items), _cols_per_row):
                                _chunk = _row_items[_chunk_start:_chunk_start + _cols_per_row]
                                _fcols = st.columns(len(_chunk))
                                for _fc, _item in zip(_fcols, _chunk):
                                    _rc = _rank_color(_item["Rank"])
                                    with _fc:
                                        st.markdown(
                                            f"<div style='background:#0b1929;border:1px solid #1a3050;"
                                            f"border-left:3px solid {_rc};border-radius:8px;"
                                            f"padding:10px 12px;'>"
                                            f"<div style='font-size:11px;color:#4a6080;margin-bottom:4px;"
                                            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                                            f"{_item['Stat']}</div>"
                                            f"<div style='display:flex;justify-content:space-between;"
                                            f"align-items:baseline;'>"
                                            f"<span style='font-size:17px;font-weight:800;color:#dde6f5;'>"
                                            f"{_item['Value']}</span>"
                                            f"<span style='font-size:13px;font-weight:700;color:{_rc};'>"
                                            f"#{_item['Rank']}</span>"
                                            f"</div>"
                                            f"<div style='font-size:12px;color:{_item['_tcolor']};margin-top:2px;'>"
                                            f"{_item['Trend']}</div>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )
                except Exception:
                    pass

            # Extra report action
            st.markdown("---")
            if st.button("📊 Full Stats Report", use_container_width=True, key="player_full_stats"):
                with st.spinner(f"Getting full stats for {player_search}..."):
                    output = run_script("planning/player_stats.py", player_search, "--recent", "10")
                st.code(output, language=None)

    with player_tab2:
        st.markdown("### 📊 Stats Deep Dive")
        st.caption("Detailed statistical analysis for smarter picks")

        # Load player stats from predictions
        stats_df = load_player_stats()

        if stats_df.empty:
            st.warning("No stats data available. Run predictions first to generate player stats.")
        else:
            st.success(f"Loaded stats for {len(stats_df)} players")

            # Sub-tabs for each analysis type
            deep_tab1, deep_tab2, deep_tab3, deep_tab4 = st.tabs(
                ["⛳ Strokes Gained", "🔥 Form Analysis", "🏌️ Course Fit", "📈 Tour Stats"]
            )

            with deep_tab1:
                render_strokes_gained_analysis(stats_df)

            with deep_tab2:
                render_form_stats_section(stats_df)

            with deep_tab3:
                render_course_specific_stats(stats_df)
                st.markdown("---")
                st.markdown("### Player Exact-Course History")
                st.caption("Select a player to view past starts/results at this exact course.")

                _deep_default_player = str(st.session_state.get("quick_player", "")).strip()
                _deep_player_options = [""] + all_players
                _deep_index = _deep_player_options.index(_deep_default_player) if _deep_default_player in _deep_player_options else 0
                _deep_player = st.selectbox(
                    "Player",
                    options=_deep_player_options,
                    index=_deep_index,
                    key="deep_course_history_player",
                )
                render_player_event_history_panel(_deep_player, stats_df, panel_title="History At This Course")

            with deep_tab4:
                st.markdown("### PGA Tour Stats — Full Field Rankings")
                st.caption("Most recent available rank and value for each stat, across all players in the dataset. Click any column header to sort.")

                _fs4_path = DATA_DIR / "historical" / "form_stats_2026.csv"
                if not _fs4_path.exists():
                    st.info("No form stats data found. Run the form stats scraper first.")
                else:
                    _fs4_df = pd.read_csv(_fs4_path)

                    # For each player × stat, keep the row from the most recent tournament
                    _tid_order = (
                        _fs4_df[["tournament_id"]]
                        .drop_duplicates()
                        .assign(_sort=lambda d: d["tournament_id"].str.extract(r"(\d+)").astype(int))
                        .sort_values("_sort", ascending=False)["tournament_id"]
                        .tolist()
                    )
                    _tid_rank = {tid: i for i, tid in enumerate(_tid_order)}
                    _fs4_df["_tid_rank"] = _fs4_df["tournament_id"].map(_tid_rank)
                    _fs4_latest = (
                        _fs4_df.sort_values("_tid_rank")
                        .groupby(["player_name", "stat_id"], as_index=False)
                        .first()
                    )

                    # Stat category groupings for column ordering
                    # 2414=Bogey Avoidance%, 2419=Bogey Avg/Rnd (scraper mislabels fixed)
                    # 2675/2567/2568/2569/2564 = SG stats (show when scraper re-run)
                    _stat_categories = {
                        "Strokes Gained": [2675, 2567, 2568, 2569, 2564],
                        "Scoring":        [120, 156, 108, 160],
                        "Driving":        [101, 102, 2401],
                        "Approach":       [103, 331, 130, 299, 142, 143],
                        "Putting":        [104, 119, 413],
                        "Consistency":    [352, 2414, 2419, 111],
                    }
                    _ordered_stat_ids = []
                    for _cat_ids in _stat_categories.values():
                        _ordered_stat_ids.extend(_cat_ids)

                    # Build stat_id → short display name
                    _stat_labels = {
                        101: "Drive Dist",    102: "Drive Acc%",   103: "GIR%",
                        104: "Putts/Rnd",     108: "Birdie+%",     111: "Sand Save%",
                        119: "1-Putt%",       120: "Scoring Avg",  130: "Scrambling%",
                        142: "Par4 Avg",      143: "Par5 Avg",     156: "Birdies/Rnd",
                        160: "Bounce Back%",  299: "Par3 Avg",     331: "Proximity(ft)",
                        352: "Bogey Avoid%",  413: "3-Putt Avoid%",
                        2414: "Bogey Avoid%2", 2419: "Bogey Avg/Rnd",
                        2675: "SG: Total",    2567: "SG: OTT",     2568: "SG: APP",
                        2569: "SG: ARG",      2564: "SG: Putt",    2401: "Club Hd Spd",
                    }

                    # Pivot: rank table (lower rank = better)
                    _rank_pivot = _fs4_latest.pivot(
                        index="player_name", columns="stat_id", values="rank"
                    )
                    _rank_pivot.columns = [_stat_labels.get(int(c), str(c)) for c in _rank_pivot.columns]

                    # Pivot: value table
                    _val_pivot = _fs4_latest.pivot(
                        index="player_name", columns="stat_id", values="stat_value_numeric"
                    )
                    _val_pivot.columns = [_stat_labels.get(int(c), str(c)) for c in _val_pivot.columns]

                    # Display mode toggle
                    _fs4_mode = st.radio(
                        "Display",
                        ["Field Rank", "Stat Value"],
                        horizontal=True,
                        key="fs4_display_mode",
                    )

                    # Category filter
                    _fs4_cat = st.selectbox(
                        "Category",
                        ["All"] + list(_stat_categories.keys()),
                        key="fs4_category",
                    )

                    _display_df = _rank_pivot if _fs4_mode == "Field Rank" else _val_pivot

                    # Filter to selected category columns
                    if _fs4_cat != "All":
                        _cat_ids = _stat_categories[_fs4_cat]
                        _cat_cols = [_stat_labels.get(sid, str(sid)) for sid in _cat_ids if _stat_labels.get(sid) in _display_df.columns]
                        _display_df = _display_df[[c for c in _cat_cols if c in _display_df.columns]]

                    # Reorder columns by category order where possible
                    _ordered_labels = [_stat_labels.get(sid, str(sid)) for sid in _ordered_stat_ids]
                    _final_cols = [c for c in _ordered_labels if c in _display_df.columns]
                    _extra_cols = [c for c in _display_df.columns if c not in _final_cols]
                    _display_df = _display_df[_final_cols + _extra_cols]

                    # Color rank cells: green=top10, yellow=top30, grey=top60, orange=top100, red=rest
                    def _color_rank_cell(val):
                        if pd.isna(val):
                            return "color: #555"
                        v = float(val)
                        if v <= 10:
                            return "color: #00c44f; font-weight:600"
                        elif v <= 30:
                            return "color: #6ddb9a"
                        elif v <= 60:
                            return "color: #dde6f5"
                        elif v <= 100:
                            return "color: #ffa726"
                        else:
                            return "color: #e53935"

                    _display_df.index.name = "Player"
                    _display_df = _display_df.reset_index()
                    _display_df = _display_df.sort_values(_display_df.columns[1], ascending=True if _fs4_mode == "Field Rank" else False).reset_index(drop=True)

                    st.caption(
                        f"{len(_display_df)} players · {len(_display_df.columns)-1} stats · "
                        f"Most recent: {_tid_order[0] if _tid_order else 'N/A'}"
                    )

                    if _fs4_mode == "Field Rank":
                        _styled = (
                            _display_df.style
                            .applymap(_color_rank_cell, subset=[c for c in _display_df.columns if c != "Player"])
                            .format(lambda x: f"{int(x)}" if pd.notna(x) and x == int(x) else ("" if pd.isna(x) else f"{x:.0f}"), subset=[c for c in _display_df.columns if c != "Player"])
                        )
                        st.dataframe(_styled, use_container_width=True, height=600, hide_index=True)
                    else:
                        st.dataframe(
                            _display_df.style.format(
                                {c: "{:.3f}" for c in _display_df.columns if c != "Player"},
                                na_rep="—",
                            ),
                            use_container_width=True,
                            height=600,
                            hide_index=True,
                        )

    with player_tab3:
        st.markdown("### ⚔️ Head-to-Head Comparison")
        st.caption("Select two players — comparison updates automatically")

        _h2h_c1, _h2h_c2 = st.columns(2)
        with _h2h_c1:
            h2h_player1 = st.selectbox("Player 1:", [""] + all_players, key="h2h_player1")
        with _h2h_c2:
            h2h_player2 = st.selectbox("Player 2:", [""] + all_players, key="h2h_player2")

        if h2h_player1 and h2h_player2 and h2h_player1 != h2h_player2:
            _h2h_path = OUTPUTS_DIR / "latest_predictions.csv"
            _h2h_upath = OUTPUTS_DIR / "player_usage_tracker.csv"

            if not _h2h_path.exists():
                st.info("Run predictions first via ⚙️ Pipeline.")
            else:
                _h2h_df = pd.read_csv(_h2h_path)
                _h2h_usage = {}
                if _h2h_upath.exists():
                    _u = pd.read_csv(_h2h_upath)
                    _h2h_usage = dict(zip(_u["player_name"], _u["uses_remaining"]))

                def _h2h_norm(n):
                    p = str(n).split(",")
                    return f"{p[1].strip()} {p[0].strip()}".lower() if len(p) == 2 else str(n).strip().lower()

                def _h2h_get(name):
                    row = _h2h_df[_h2h_df["player_name"] == name]
                    if row.empty:
                        row = _h2h_df[_h2h_df["player_name"].apply(_h2h_norm) == _h2h_norm(name)]
                    return row.iloc[0] if not row.empty else None

                _r1 = _h2h_get(h2h_player1)
                _r2 = _h2h_get(h2h_player2)

                if _r1 is None or _r2 is None:
                    st.warning("Prediction data not found for one or both players. Try refreshing predictions.")
                else:
                    # Short display names (first name only from "Last, First" format)
                    def _short(n):
                        p = str(n).split(",")
                        return p[1].strip() if len(p) == 2 else str(n).strip()

                    _n1, _n2 = _short(h2h_player1), _short(h2h_player2)

                    # ── PLAYER HEADER CARDS ──────────────────────────────
                    _hc1, _vs_mid, _hc2 = st.columns([5, 1, 5])

                    for _col, _row, _full_name, _accent in [
                        (_hc1, _r1, h2h_player1, "#00c44f"),
                        (_hc2, _r2, h2h_player2, "#4cb8ff"),
                    ]:
                        _wr   = int(_row["world_rank"]) if pd.notna(_row.get("world_rank")) else "—"
                        _win  = (_row.get("win_prob",  0) or 0) * 100
                        _t10  = (_row.get("top10_prob", 0) or 0) * 100
                        _ev   = (_row.get("expected_value", 0) or 0) / 1000
                        _odds = str(_row.get("odds_to_win", "—") or "—")
                        _cut  = str(_row.get("cut_risk", "—") or "—").upper()
                        _cut_c = {"LOW": "#00c44f", "MEDIUM": "#f4c430",
                                  "ELEVATED": "#ff9800", "HIGH": "#e53935"}.get(_cut, "#7a90b8")
                        _uses = int(_h2h_usage.get(_full_name,
                                    _row.get("uses_remaining", 3) or 3))
                        _dots = "●" * _uses + "○" * (3 - _uses)
                        _hot  = bool(_row.get("hot_hand_flag", False))

                        with _col:
                            st.markdown(f"""
<div style="background:#0d1a30;border:2px solid {_accent}33;border-radius:14px;
     padding:18px;text-align:center;">
  <div style="font-size:17px;font-weight:800;color:#fff;margin-bottom:2px;">
    {_short(_full_name)}</div>
  <div style="font-size:11px;color:#4a6080;margin-bottom:12px;">
    World Rank #{_wr}{"&nbsp; 🔥" if _hot else ""}</div>
  <div style="display:flex;justify-content:space-around;margin-bottom:12px;">
    <div>
      <div style="font-size:22px;font-weight:800;color:{_accent};">{_win:.1f}%</div>
      <div style="font-size:10px;color:#4a6080;text-transform:uppercase;">WIN</div>
    </div>
    <div>
      <div style="font-size:22px;font-weight:800;color:{_accent};">{_t10:.0f}%</div>
      <div style="font-size:10px;color:#4a6080;text-transform:uppercase;">TOP 10</div>
    </div>
    <div>
      <div style="font-size:22px;font-weight:800;color:{_accent};">${_ev:.0f}k</div>
      <div style="font-size:10px;color:#4a6080;text-transform:uppercase;">EXP VAL</div>
    </div>
  </div>
  <div style="font-size:12px;color:#7a90b8;margin-bottom:6px;">
    Vegas: {_odds}&nbsp;·&nbsp;
    <span style="color:{_cut_c};">Cut risk: {_cut}</span>
  </div>
  <div style="font-size:12px;color:#4a6080;">{_dots} ({_uses}/3 uses)</div>
</div>
""", unsafe_allow_html=True)

                    with _vs_mid:
                        st.markdown(
                            "<div style='text-align:center;padding-top:65px;"
                            "font-size:18px;font-weight:900;color:#2a3f58;'>VS</div>",
                            unsafe_allow_html=True
                        )

                    # ── PGA-STYLE COMPARISON GRID ────────────────────────
                    st.markdown("---")

                    # Load form_stats fallback for any non-SG stat columns missing
                    # from predictions.csv (e.g. driving_acc, sand_save, one_putt_pct
                    # added to NON_SG_STATS but pipeline not yet re-run).
                    _h2h_fs_extra: dict = {}
                    _h2h_fs_map = {
                        "102": "driving_acc_val",
                        "111": "sand_save_val",
                        "119": "one_putt_pct_val",
                    }
                    _missing_fs = {sid: col for sid, col in _h2h_fs_map.items()
                                   if col not in _h2h_df.columns}
                    if _missing_fs:
                        _fs_hist = DATA_DIR / "historical"
                        _fs_year_path = next(
                            (_fs_hist / f"form_stats_{y}.csv"
                             for y in [datetime.now().year, datetime.now().year - 1]
                             if (_fs_hist / f"form_stats_{y}.csv").exists()),
                            None
                        )
                        if _fs_year_path:
                            try:
                                _fs_raw = pd.read_csv(_fs_year_path)
                                _fs_raw["stat_id"] = _fs_raw["stat_id"].astype(str)
                                _fs_raw["player_id"] = _fs_raw["player_id"].astype(str)
                                for _fsid, _fscol in _missing_fs.items():
                                    _fs_rows = _fs_raw[_fs_raw["stat_id"] == _fsid]
                                    if not _fs_rows.empty:
                                        _fs_latest = (
                                            _fs_rows.sort_values("tournament_id")
                                            .groupby("player_id")
                                            .tail(1)
                                        )
                                        _h2h_fs_extra[_fscol] = dict(
                                            zip(_fs_latest["player_id"],
                                                _fs_latest["stat_value_numeric"])
                                        )
                            except Exception:
                                pass

                    def _hg(row, k):
                        v = row.get(k)
                        try:
                            if v is not None and pd.notna(v):
                                return float(v)
                        except (TypeError, ValueError):
                            pass
                        # Fallback: look up in form_stats extra dict keyed by player_id
                        if k in _h2h_fs_extra:
                            try:
                                pid = str(int(float(row.get("player_id") or 0)))
                                fv = _h2h_fs_extra[k].get(pid)
                                if fv is not None and pd.notna(fv):
                                    return float(fv)
                            except (TypeError, ValueError):
                                pass
                        return None

                    def _h2h_bar(fa, fb):
                        if fa is None or fb is None:
                            return 50, 50
                        mn = min(fa, fb)
                        if mn < 0:
                            fa -= mn; fb -= mn
                        t = fa + fb
                        if t == 0:
                            return 50, 50
                        return max(2, fa / t * 100), max(2, fb / t * 100)

                    def _h2h_row(label, va, vb, higher_better=True, fmt=".1f", suffix=""):
                        fa = va if isinstance(va, (int, float)) and pd.notna(va) else None
                        fb = vb if isinstance(vb, (int, float)) and pd.notna(vb) else None
                        if fa is None and fb is None:
                            a_str = b_str = "—"
                            a_col = b_col = "#3a5070"; a_w = b_w = "400"
                            bar_a = "#112230"; bar_b = "#0d1a2e"; fill_a = fill_b = 50
                        else:
                            a_better = b_better = False
                            if fa is not None and fb is not None:
                                a_better = (fa > fb) if higher_better else (fa < fb)
                                b_better = (fb > fa) if higher_better else (fb < fa)
                            try:
                                a_str = f"{fa:{fmt}}{suffix}" if fa is not None else "—"
                            except Exception:
                                a_str = str(fa) if fa is not None else "—"
                            try:
                                b_str = f"{fb:{fmt}}{suffix}" if fb is not None else "—"
                            except Exception:
                                b_str = str(fb) if fb is not None else "—"
                            a_col = "#00c44f" if a_better else ("#8899aa" if b_better else "#dde6f5")
                            b_col = "#4cb8ff" if b_better else ("#8899aa" if a_better else "#dde6f5")
                            a_w = "700" if a_better else "400"
                            b_w = "700" if b_better else "400"
                            fill_a, fill_b = _h2h_bar(fa, fb)
                            # Winner side: bright; losing side: dim but colored so bar always shows both
                            bar_a = "#00c44f" if a_better else "#0d2e18"
                            bar_b = "#4cb8ff" if b_better else "#0d1e30"
                        return (
                            # Stat label — its own centered row
                            f'<div style="text-align:center;font-size:0.67em;color:#2e4870;'
                            f'text-transform:uppercase;letter-spacing:.09em;padding:10px 24px 0;">{label}</div>'
                            # Values flanking a prominent bar
                            f'<div style="display:grid;grid-template-columns:auto 1fr auto;'
                            f'align-items:center;gap:12px;padding:5px 24px 12px;'
                            f'border-bottom:1px solid #0a1624;">'
                            f'<div style="font-size:1.05em;font-weight:{a_w};color:{a_col};'
                            f'min-width:52px;text-align:right;">{a_str}</div>'
                            f'<div style="display:grid;grid-template-columns:{fill_a:.1f}fr {fill_b:.1f}fr;'
                            f'height:8px;border-radius:5px;overflow:hidden;">'
                            f'<div style="background:{bar_a};"></div>'
                            f'<div style="background:{bar_b};"></div>'
                            f'</div>'
                            f'<div style="font-size:1.05em;font-weight:{b_w};color:{b_col};'
                            f'min-width:52px;text-align:left;">{b_str}</div>'
                            f'</div>'
                        )

                    def _h2h_sec(title):
                        return (
                            f'<div style="background:#060d1a;padding:8px 24px;margin-top:2px;'
                            f'border-top:2px solid #0e1c2e;">'
                            f'<span style="font-size:0.7em;font-weight:700;color:#3a5878;'
                            f'text-transform:uppercase;letter-spacing:.12em;">{title}</span></div>'
                        )

                    # Compute head-to-head win probability
                    _wp1 = _hg(_r1, "win_prob") or 0
                    _wp2 = _hg(_r2, "win_prob") or 0
                    _wp_total = _wp1 + _wp2 if _wp1 + _wp2 > 0 else 1
                    _h2h_p1 = _wp1 / _wp_total * 100
                    _h2h_p2 = _wp2 / _wp_total * 100

                    if _h2h_p1 > 55:
                        _vname = _n1; _vdiff = f"+{_h2h_p1 - _h2h_p2:.1f} pp edge"; _vcol = "#00c44f"
                    elif _h2h_p2 > 55:
                        _vname = _n2; _vdiff = f"+{_h2h_p2 - _h2h_p1:.1f} pp edge"; _vcol = "#4cb8ff"
                    else:
                        _vname = "TOO CLOSE TO CALL"; _vdiff = "< 5 pp difference"; _vcol = "#f39c12"

                    _rows = ""
                    _rows += _h2h_sec("Model Probabilities")
                    _rows += _h2h_row("Head-to-Head Win", _h2h_p1, _h2h_p2, fmt=".1f", suffix="%")
                    _rows += _h2h_row("Win %", (_hg(_r1,"win_prob") or 0)*100, (_hg(_r2,"win_prob") or 0)*100, fmt=".1f", suffix="%")
                    _rows += _h2h_row("Top 5 %", (_hg(_r1,"top5_prob") or 0)*100, (_hg(_r2,"top5_prob") or 0)*100, fmt=".1f", suffix="%")
                    _rows += _h2h_row("Top 10 %", (_hg(_r1,"top10_prob") or 0)*100, (_hg(_r2,"top10_prob") or 0)*100, fmt=".1f", suffix="%")
                    _rows += _h2h_row("Top 20 %", (_hg(_r1,"top20_prob") or 0)*100, (_hg(_r2,"top20_prob") or 0)*100, fmt=".1f", suffix="%")
                    _rows += _h2h_row("Expected Value", _hg(_r1,"expected_value"), _hg(_r2,"expected_value"), fmt=",.0f")

                    _rows += _h2h_sec("Strokes Gained · Season")
                    _rows += _h2h_row("Total", _hg(_r1,"season_sg_total"), _hg(_r2,"season_sg_total"), fmt="+.2f")
                    _rows += _h2h_row("Off the Tee", _hg(_r1,"season_sg_ott"), _hg(_r2,"season_sg_ott"), fmt="+.2f")
                    _rows += _h2h_row("Approach", _hg(_r1,"season_sg_app"), _hg(_r2,"season_sg_app"), fmt="+.2f")
                    _rows += _h2h_row("Around Green", _hg(_r1,"season_sg_arg"), _hg(_r2,"season_sg_arg"), fmt="+.2f")
                    _rows += _h2h_row("Putting", _hg(_r1,"season_sg_putt"), _hg(_r2,"season_sg_putt"), fmt="+.2f")
                    _rows += _h2h_row("Tee to Green", _hg(_r1,"season_sg_t2g"), _hg(_r2,"season_sg_t2g"), fmt="+.2f")

                    _rows += _h2h_sec("Recent Form")
                    _rows += _h2h_row("Form Trend", _hg(_r1,"form_trend"), _hg(_r2,"form_trend"), fmt="+.2f")
                    _rows += _h2h_row("Scoring Avg", _hg(_r1,"recent_scoring_avg"), _hg(_r2,"recent_scoring_avg"), higher_better=False, fmt=".2f")
                    _rows += _h2h_row("Top 5s", _hg(_r1,"recent_top5s"), _hg(_r2,"recent_top5s"), fmt=".0f")
                    _rows += _h2h_row("Top 10s", _hg(_r1,"recent_top10s"), _hg(_r2,"recent_top10s"), fmt=".0f")
                    _rows += _h2h_row("Cuts Made %", (_hg(_r1,"recent_cuts_pct") or 0)*100, (_hg(_r2,"recent_cuts_pct") or 0)*100, fmt=".0f", suffix="%")
                    _rows += _h2h_row("Final Round SG", _hg(_r1,"recent_final_round"), _hg(_r2,"recent_final_round"), fmt="+.2f")
                    _rows += _h2h_row("Consistency (σ)", _hg(_r1,"finish_consistency"), _hg(_r2,"finish_consistency"), higher_better=False, fmt=".1f")

                    _rows += _h2h_sec("Course History")
                    _rows += _h2h_row("Avg Finish", _hg(_r1,"hist_avg_finish"), _hg(_r2,"hist_avg_finish"), higher_better=False, fmt=".0f")
                    _rows += _h2h_row("Best Finish", _hg(_r1,"hist_best_finish"), _hg(_r2,"hist_best_finish"), higher_better=False, fmt=".0f")
                    _rows += _h2h_row("Wins Here", _hg(_r1,"hist_wins"), _hg(_r2,"hist_wins"), fmt=".0f")
                    _rows += _h2h_row("Top 5s Here", _hg(_r1,"hist_top5s"), _hg(_r2,"hist_top5s"), fmt=".0f")
                    _rows += _h2h_row("Top 10s Here", _hg(_r1,"hist_top10s"), _hg(_r2,"hist_top10s"), fmt=".0f")
                    _rows += _h2h_row("Cut Rate", (_hg(_r1,"hist_cut_rate") or 0)*100, (_hg(_r2,"hist_cut_rate") or 0)*100, fmt=".0f", suffix="%")
                    _rows += _h2h_row("Times Played", _hg(_r1,"hist_times_played"), _hg(_r2,"hist_times_played"), fmt=".0f")

                    _rows += _h2h_sec("Ball Striking")
                    _rows += _h2h_row("Driving Distance", _hg(_r1,"driving_dist_val"), _hg(_r2,"driving_dist_val"), fmt=".0f", suffix=" yds")
                    _rows += _h2h_row("Driving Accuracy", _hg(_r1,"driving_acc_val"), _hg(_r2,"driving_acc_val"), fmt=".1f", suffix="%")
                    _rows += _h2h_row("GIR %", _hg(_r1,"gir_pct_val"), _hg(_r2,"gir_pct_val"), fmt=".1f", suffix="%")
                    _rows += _h2h_row("Scrambling %", _hg(_r1,"scrambling_val"), _hg(_r2,"scrambling_val"), fmt=".1f", suffix="%")
                    _rows += _h2h_row("Sand Save %", _hg(_r1,"sand_save_val"), _hg(_r2,"sand_save_val"), fmt=".1f", suffix="%")

                    _rows += _h2h_sec("Scoring")
                    _rows += _h2h_row("Birdie Avg", _hg(_r1,"birdie_avg_val"), _hg(_r2,"birdie_avg_val"), fmt=".2f")
                    _rows += _h2h_row("Bogey Avoidance", _hg(_r1,"bogey_avoid_val"), _hg(_r2,"bogey_avoid_val"), fmt=".1f", suffix="%")
                    _rows += _h2h_row("Putts / Round", _hg(_r1,"putts_per_round_val"), _hg(_r2,"putts_per_round_val"), higher_better=False, fmt=".2f")
                    _rows += _h2h_row("1-Putt %", _hg(_r1,"one_putt_pct_val"), _hg(_r2,"one_putt_pct_val"), fmt=".1f", suffix="%")

                    _rows += _h2h_sec("Market")
                    _rows += _h2h_row("World Rank", _hg(_r1,"world_rank"), _hg(_r2,"world_rank"), higher_better=False, fmt=".0f")
                    _me1 = _hg(_r1,"model_vs_vegas_edge"); _me2 = _hg(_r2,"model_vs_vegas_edge")
                    if _me1 is not None or _me2 is not None:
                        _rows += _h2h_row("Model vs Market Edge", (_me1 or 0)*100, (_me2 or 0)*100, fmt="+.1f", suffix=" pp")

                    _ps1 = _hg(_r1, "projected_score_vs_field"); _ps2 = _hg(_r2, "projected_score_vs_field")
                    if _ps1 is not None or _ps2 is not None:
                        _rows += _h2h_sec("Score Projection")
                        _rows += _h2h_row("vs Field Avg (mean)", _ps1, _ps2, higher_better=False, fmt="+.1f")
                        _rows += _h2h_row("Ceiling (best 10%)", _hg(_r1,"proj_ceiling"), _hg(_r2,"proj_ceiling"), higher_better=False, fmt="+.1f")
                        _rows += _h2h_row("Floor (worst 10%)", _hg(_r1,"proj_floor"), _hg(_r2,"proj_floor"), higher_better=False, fmt="+.1f")
                        _rows += _h2h_row("Score Rank", _hg(_r1,"score_rank"), _hg(_r2,"score_rank"), higher_better=False, fmt=".0f")

                    st.markdown(f"""
                    <div style="background:#0d1a30;border-radius:12px;overflow:hidden;border:1px solid #1a2e4a;">
                    <div style="background:#040a14;padding:9px 20px;text-align:center;border-bottom:2px solid #0e1c2e;">
                        <span style="font-size:0.68em;color:#2a4060;text-transform:uppercase;letter-spacing:.08em;">
                        Model Verdict · </span>
                        <span style="font-size:0.88em;font-weight:700;color:{_vcol};">{_vname}</span>
                        <span style="font-size:0.72em;color:#3a5070;"> · {_vdiff}</span>
                    </div>
                    {_rows}
                    </div>
                    """, unsafe_allow_html=True)

                                

                    # ── FORM SPARKLINES (overlaid line chart) ────────────
                    st.markdown("---")
                    st.markdown("#### 📈 Recent Form — SG: Total")

                    def _flip_name(n):
                        p = str(n).split(",")
                        return f"{p[1].strip()} {p[0].strip()}" if len(p) == 2 else str(n)

                    _form_data = load_player_form_history()
                    _spark_rows = []
                    for _pname_full, _pshort, in [(h2h_player1, _n1), (h2h_player2, _n2)]:
                        _lookup = _flip_name(_pname_full)
                        if _lookup in _form_data:
                            for _ev, _sg in zip(_form_data[_lookup]["events"],
                                                _form_data[_lookup]["sg"]):
                                _spark_rows.append({"Player": _pshort, "Event": _ev, "SG": _sg})

                    if _spark_rows:
                        _sp_fig = px.line(
                            pd.DataFrame(_spark_rows),
                            x="Event", y="SG", color="Player", markers=True,
                            color_discrete_map={_n1: "#00c44f", _n2: "#4cb8ff"},
                            labels={"SG": "SG: Total", "Event": ""},
                        )
                        _sp_fig.add_hline(y=0, line_dash="dot", line_color="#4a6080", line_width=1)
                        _sp_fig.update_layout(
                            height=230,
                            margin=dict(t=10, b=10, l=0, r=0),
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            font_color="#dde6f5",
                            legend=dict(orientation="h", y=1.12),
                            xaxis=dict(tickfont=dict(size=9), gridcolor="#1c2f4a"),
                            yaxis=dict(gridcolor="#1c2f4a", zeroline=False),
                        )
                        st.plotly_chart(_sp_fig, use_container_width=True)
                    else:
                        st.caption("Form history not available for one or both players.")


        elif h2h_player1 and h2h_player2 and h2h_player1 == h2h_player2:
            st.warning("Select two different players.")


# ============================================================================
# PAGE: BETTING (consolidated from Props Lab + Odds & Experts)
# ============================================================================

elif page == "🎰 Betting":
    st.markdown("## 🎰 Betting")
    st.caption("Sportsbook-style props powered by model predictions")

    # =========================================================================
    # ODDS REFRESH PANEL
    # =========================================================================
    with st.container():
        # ── Auto-detect current / next tournament ────────────────────────────
        _bet_sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
        _bet_sched_df   = pd.DataFrame()
        _bet_tid_options: list = []
        if _bet_sched_path.exists():
            _bet_sched_df = pd.read_csv(_bet_sched_path, dtype=str)
            _bet_today = datetime.now().strftime("%Y-%m-%d")
            # Active first, then upcoming (up to 6 weeks out)
            _bet_active = _bet_sched_df[
                (_bet_sched_df["start_date"] <= _bet_today) &
                (_bet_sched_df["end_date"]   >= _bet_today)
            ]
            _bet_upcoming = _bet_sched_df[
                _bet_sched_df["start_date"] > _bet_today
            ].sort_values("start_date").head(6)
            _bet_pool = pd.concat([_bet_active, _bet_upcoming], ignore_index=True)
            _bet_tid_options = [
                f"{row['tournament_id']} — {row['tournament_name']} ({row['start_date']})"
                for _, row in _bet_pool.iterrows()
            ]

        # ── Data freshness check ─────────────────────────────────────────────
        _odds_dir   = DATA_DIR / "odds"
        _prop_files = sorted(_odds_dir.glob("prop_lines_R*.csv"),
                             key=lambda p: p.stat().st_mtime, reverse=True)
        _latest_prop_file = _prop_files[0] if _prop_files else None
        _prop_age_str, _prop_tid_str = "Never fetched", "—"
        if _latest_prop_file:
            import os as _os_bet
            _prop_mtime = _latest_prop_file.stat().st_mtime
            _prop_age_hours = (datetime.now().timestamp() - _prop_mtime) / 3600
            if _prop_age_hours < 1:
                _prop_age_str = f"{int(_prop_age_hours*60)}m ago"
            elif _prop_age_hours < 24:
                _prop_age_str = f"{_prop_age_hours:.1f}h ago"
            else:
                _prop_age_str = f"{_prop_age_hours/24:.1f}d ago"
            _prop_tid_str = _latest_prop_file.stem.replace("prop_lines_", "")
            # Map ID → name
            if not _bet_sched_df.empty and "tournament_id" in _bet_sched_df.columns:
                _nm_row = _bet_sched_df[_bet_sched_df["tournament_id"] == _prop_tid_str]
                if not _nm_row.empty:
                    _prop_tid_str = _nm_row.iloc[0].get("tournament_name", _prop_tid_str)

        # ── Staleness color ──────────────────────────────────────────────────
        if _latest_prop_file:
            if _prop_age_hours < 6:
                _fresh_color, _fresh_icon = "#00c44f", "🟢"
            elif _prop_age_hours < 24:
                _fresh_color, _fresh_icon = "#f39c12", "🟡"
            else:
                _fresh_color, _fresh_icon = "#e74c3c", "🔴"
        else:
            _fresh_color, _fresh_icon = "#e74c3c", "🔴"

        # ── Layout ───────────────────────────────────────────────────────────
        st.markdown(f"""
<div style="background:#0d1a30;border:1px solid #1e3050;border-radius:8px;
            padding:14px 18px 10px 18px;margin-bottom:16px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
    <span style="font-size:1.0em;font-weight:700;color:#dde6f5;">📡 DraftKings Odds Feed</span>
    <span style="font-size:0.78em;color:{_fresh_color};font-weight:600;">
      {_fresh_icon} {_prop_age_str} &nbsp;·&nbsp; {_prop_tid_str}
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

        _rp_col1, _rp_col2, _rp_col3, _rp_col4 = st.columns([2.5, 1.2, 1.2, 2])

        with _rp_col1:
            if _bet_tid_options:
                # Default to first active/upcoming tournament
                _rp_sel = st.selectbox(
                    "Tournament", _bet_tid_options, index=0,
                    key="bet_page_tournament_sel", label_visibility="collapsed"
                )
                _rp_tid = _rp_sel.split(" — ")[0].strip()
            else:
                _rp_tid = st.text_input(
                    "Tournament ID", placeholder="e.g. R2026010",
                    key="bet_page_tid_manual", label_visibility="collapsed"
                ).strip().upper()

        with _rp_col2:
            _rp_fetch = st.button(
                "⬇ Fetch DK Odds", key="bet_fetch_dk", use_container_width=True, type="primary"
            )

        with _rp_col3:
            _rp_score = st.button(
                "⚡ Score Bets", key="bet_score_bets", use_container_width=True
            )

        with _rp_col4:
            with st.expander("🔧 Advanced Options"):
                _dk_override_id = st.text_input(
                    "DraftKings eventgroup ID",
                    placeholder="e.g. 89343  (leave blank for auto-detect)",
                    key="bet_dk_eg_override",
                )
                st.caption("Find it in the DK URL: sportsbook.draftkings.com/leagues/golf/**{id}**")
                st.markdown("---")
                _dk_har_path = st.text_input(
                    "HAR file path (for props: round score, birdies, matchups)",
                    placeholder="e.g. data/odds/dk_props.har",
                    key="bet_dk_har_path",
                )
                st.caption(
                    "Export from Chrome DevTools → Network tab → right-click → **Save all as HAR**. "
                    "Browse to Round Props, Birdies, Matchups, Group Winner tabs before exporting."
                )

        # ── Background fetch status files ─────────────────────────────────────
        _DK_STATUS_FILE = _odds_dir / ".dk_fetch_status"
        _DK_LOG_FILE    = _odds_dir / ".dk_fetch_log.txt"

        def _run_dk_bg(cmd):
            """Run DK scraper in a daemon thread; write status to file when done."""
            import threading as _thr
            def _worker():
                _DK_STATUS_FILE.write_text("running")
                try:
                    _r = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=600, cwd=PROJECT_ROOT)
                    _DK_LOG_FILE.write_text((_r.stdout or "") + (_r.stderr or ""))
                    _DK_STATUS_FILE.write_text(f"done:{_r.returncode}")
                except subprocess.TimeoutExpired:
                    _DK_STATUS_FILE.write_text("timeout")
                except Exception as _ex:
                    _DK_STATUS_FILE.write_text(f"error:{_ex}")
            _thr.Thread(target=_worker, daemon=True).start()

        # ── Check if a fetch is already in progress ───────────────────────────
        _dk_running = False
        _dk_status  = ""
        if _DK_STATUS_FILE.exists():
            _dk_status = _DK_STATUS_FILE.read_text().strip()
            _dk_running = (_dk_status == "running")

        # ── Run fetch ─────────────────────────────────────────────────────────
        if _rp_fetch and _rp_tid and not _dk_running:
            _dk_cmd = [
                "python3",
                str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_draftkings_props.py"),
                "--tournament-id", _rp_tid,
                "--fetch-profile", "targeted",
            ]
            _dk_eg = st.session_state.get("bet_dk_eg_override", "").strip()
            if _dk_eg:
                _dk_cmd.extend(["--eventgroup-id", _dk_eg])
            _dk_har = st.session_state.get("bet_dk_har_path", "").strip()
            if _dk_har:
                # Resolve relative to project root if not absolute
                _har_p = Path(_dk_har) if Path(_dk_har).is_absolute() else PROJECT_ROOT / _dk_har
                if _har_p.exists():
                    _dk_cmd.extend(["--input-json", str(_har_p)])
                else:
                    st.warning(f"HAR file not found: {_dk_har}")
            _run_dk_bg(_dk_cmd)
            _dk_running = True
            _dk_status  = "running"
            st.rerun()

        # ── Status feedback (shown on every page load while running) ──────────
        if _dk_running:
            import time as _time_bet
            st.info("⏳ Fetching DraftKings odds in background… page will refresh when done.")
            _time_bet.sleep(4)
            # Re-read status after sleeping
            _dk_status = _DK_STATUS_FILE.read_text().strip() if _DK_STATUS_FILE.exists() else ""
            if _dk_status != "running":
                st.rerun()  # Fetch finished — reload page to show results
            else:
                st.rerun()  # Still running — keep polling

        elif _dk_status.startswith("done:0"):
            st.success("✅ DraftKings odds fetched successfully!")
            _DK_STATUS_FILE.unlink(missing_ok=True)
            load_recommended_bets_df.clear()
            load_dk_content_cards_df.clear()
            st.cache_data.clear()
            if _DK_LOG_FILE.exists():
                with st.expander("Scraper output"):
                    st.code(_DK_LOG_FILE.read_text()[-2000:])

        elif _dk_status == "timeout":
            st.error(
                "Scraper timed out after 10 min. DraftKings may be slow or blocking. "
                "Try pasting the DK Event Group ID in the override field and retry."
            )
            _DK_STATUS_FILE.unlink(missing_ok=True)

        elif _dk_status.startswith("done:") or _dk_status.startswith("error:"):
            st.error(f"Fetch failed: {_dk_status}")
            _DK_STATUS_FILE.unlink(missing_ok=True)
            if _DK_LOG_FILE.exists():
                with st.expander("Scraper output"):
                    st.code(_DK_LOG_FILE.read_text()[-2000:])

        # ── Run score ────────────────────────────────────────────────────────
        if _rp_score and _rp_tid:
            _sc_cmd = [
                "python3",
                str(PROJECT_ROOT / "scripts" / "models" / "recommend_bets.py"),
                "--tournament-id", _rp_tid,
            ]
            with st.spinner("Scoring bets against model probabilities..."):
                try:
                    _sc_res = subprocess.run(
                        _sc_cmd, capture_output=True, text=True,
                        timeout=60, cwd=PROJECT_ROOT
                    )
                    if _sc_res.returncode == 0:
                        st.success("✅ Bets scored — Value Bets tab updated")
                        load_recommended_bets_df.clear()
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Scoring failed — see details below")
                    _sc_out = (_sc_res.stdout or _sc_res.stderr or "").strip()
                    if _sc_out:
                        with st.expander("Scorer output"):
                            st.code(_sc_out[-1500:])
                except subprocess.TimeoutExpired:
                    st.error("Scorer timed out after 60s.")
                except Exception as _sc_e:
                    st.error(f"Error: {_sc_e}")

    st.markdown("---")

    # =========================================================================
    # VALUE BET TRACKER
    # =========================================================================
    st.markdown("### ⚡ Value Bet Tracker")
    st.caption("Players where the model's win probability exceeds the market-implied probability")

    _vb_path = OUTPUTS_DIR / "latest_predictions.csv"
    if _vb_path.exists():
        _vb_raw = pd.read_csv(_vb_path)

        # Build cut-player exclusion set (same logic as Value Bets tab)
        _vb_cut_names: set = set()
        _vb_lb_files = sorted((DATA_DIR / "live").glob("leaderboard_r*.csv"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
        if _vb_lb_files:
            try:
                _vb_lb = pd.read_csv(_vb_lb_files[0])
                if "made_cut" in _vb_lb.columns and "player_name" in _vb_lb.columns:
                    _vb_mc = _vb_lb["made_cut"].astype(str).str.lower()
                    _vb_st = _vb_lb.get("status", pd.Series(dtype=str)).astype(str).str.lower()
                    _vb_cut_mask = (_vb_mc == "false") | (_vb_st.isin(["cut","wd","withdrawn","mc"]))
                    _vb_cut_names = set(_vb_lb.loc[_vb_cut_mask, "player_name"].str.strip().str.lower())
            except Exception:
                pass

        if _vb_cut_names and "player_name" in _vb_raw.columns:
            _vb_raw = _vb_raw[~_vb_raw["player_name"].str.strip().str.lower().isin(_vb_cut_names)]

        _vb_need = ["model_vs_vegas_edge", "win_prob", "vegas_prob",
                    "player_name", "odds_to_win", "odds_drift_level", "expected_value",
                    "dfs_ownership_proj"]
        if all(c in _vb_raw.columns for c in ["model_vs_vegas_edge", "win_prob", "vegas_prob"]):
            _vb_raw["model_vs_vegas_edge"] = pd.to_numeric(
                _vb_raw["model_vs_vegas_edge"], errors="coerce"
            )

            _vb_thresh_pct = st.slider(
                "Minimum edge threshold (%):", 0.0, 10.0, 2.0, 0.5,
                key="vb_thresh_slider",
            )
            _vb_thresh = _vb_thresh_pct / 100.0

            _vb_hits = _vb_raw[_vb_raw["model_vs_vegas_edge"] >= _vb_thresh].sort_values(
                "model_vs_vegas_edge", ascending=False
            )

            if not _vb_hits.empty:
                _vb_s1, _vb_s2, _vb_s3, _vb_s4 = st.columns(4)
                with _vb_s1:
                    st.metric("Value Bets Found", len(_vb_hits))
                with _vb_s2:
                    st.metric("Avg Edge",
                              f"+{_vb_hits['model_vs_vegas_edge'].mean()*100:.1f}%")
                with _vb_s3:
                    _vb_best = _vb_hits.iloc[0]
                    st.metric(
                        "Top Edge",
                        f"+{_vb_best['model_vs_vegas_edge']*100:.1f}%",
                        help=str(_vb_best.get("player_name", "")),
                    )
                with _vb_s4:
                    _vb_strong = int((_vb_hits["model_vs_vegas_edge"] > 0.05).sum())
                    st.metric("Strong Edges (>5%)", _vb_strong)

                # Build display table
                _vb_disp_cols = [c for c in _vb_need if c in _vb_hits.columns]
                _vb_disp = _vb_hits.head(25)[_vb_disp_cols].copy()

                if "win_prob" in _vb_disp.columns:
                    _vb_disp["win_prob"] = (
                        pd.to_numeric(_vb_disp["win_prob"], errors="coerce") * 100
                    ).round(1).astype(str) + "%"
                if "vegas_prob" in _vb_disp.columns:
                    _vb_disp["vegas_prob"] = (
                        pd.to_numeric(_vb_disp["vegas_prob"], errors="coerce") * 100
                    ).round(1).astype(str) + "%"
                if "model_vs_vegas_edge" in _vb_disp.columns:
                    _vb_disp["model_vs_vegas_edge"] = (
                        "+"
                        + (pd.to_numeric(_vb_disp["model_vs_vegas_edge"], errors="coerce") * 100)
                        .round(1)
                        .astype(str)
                        + "%"
                    )
                if "expected_value" in _vb_disp.columns:
                    _vb_disp["expected_value"] = _vb_disp["expected_value"].apply(
                        lambda x: f"${float(x):,.0f}" if pd.notna(x) else "—"
                    )
                if "dfs_ownership_proj" in _vb_disp.columns:
                    _vb_disp["dfs_ownership_proj"] = (
                        pd.to_numeric(_vb_disp["dfs_ownership_proj"], errors="coerce")
                        .round(1).astype(str) + "%"
                    )

                _vb_disp = _vb_disp.rename(columns={
                    "player_name":         "Player",
                    "win_prob":            "Model Win%",
                    "vegas_prob":          "Vegas Implied%",
                    "model_vs_vegas_edge": "Edge",
                    "odds_to_win":         "Odds",
                    "odds_drift_level":    "Signal",
                    "expected_value":      "EV ($)",
                    "dfs_ownership_proj":  "DFS Own%",
                })
                st.dataframe(_vb_disp, hide_index=True, use_container_width=True)

                _vb_ts = _vb_raw.get("odds_updated_at", pd.Series(dtype=str)).dropna()
                if not _vb_ts.empty:
                    st.caption(f"Odds last refreshed: {_vb_ts.iloc[0]}")
            else:
                st.info(
                    f"No players found with edge ≥ {_vb_thresh_pct:.1f}%. "
                    "Try lowering the threshold or refreshing odds."
                )
        else:
            st.info("Run **Refresh Odds** (Pipeline page) to generate model vs. market edge data.")
    else:
        st.info("No predictions file found. Run the full pipeline first.")

    st.markdown("---")

    # =========================================================================
    # MARKET AVAILABILITY SUMMARY STRIP
    # =========================================================================
    # ── Market Availability (data-driven from actual prop_lines files) ─────────
    with st.expander("📊 Market Availability Details", expanded=False):
        _ma_odds_dir = DATA_DIR / "odds"
        _ma_prop_files = sorted(_ma_odds_dir.glob("prop_lines_R*.csv"),
                                key=lambda p: p.stat().st_mtime, reverse=True)
        if not _ma_prop_files:
            st.info("No prop lines fetched yet. Use the refresh panel above.")
        else:
            _ma_rows = []
            for _ma_f in _ma_prop_files[:3]:   # show latest 3 files
                try:
                    _ma_df = pd.read_csv(_ma_f)
                    _ma_age_h = (datetime.now().timestamp() - _ma_f.stat().st_mtime) / 3600
                    _ma_tid   = _ma_f.stem.replace("prop_lines_", "")
                    if _ma_age_h < 6:
                        _ma_icon = "🟢"
                    elif _ma_age_h < 24:
                        _ma_icon = "🟡"
                    else:
                        _ma_icon = "🔴"
                    _ma_age_str = (f"{int(_ma_age_h*60)}m" if _ma_age_h < 1
                                   else f"{_ma_age_h:.1f}h" if _ma_age_h < 24
                                   else f"{_ma_age_h/24:.1f}d")
                    for _ma_mkt, _ma_grp in _ma_df.groupby("market"):
                        _ma_players = int(_ma_grp["player_name"].nunique()) if "player_name" in _ma_grp.columns else len(_ma_grp)
                        _ma_lbl = {"outright":"Win","top5":"Top 5","top10":"Top 10",
                                   "top20":"Top 20","h2h":"H2H","make_cut":"Make Cut",
                                   "round_score":"Round Score","birdies":"Birdies",
                                   "bogeys":"Bogeys"}.get(str(_ma_mkt), str(_ma_mkt).title())
                        _ma_rows.append({
                            "Tournament": _ma_tid,
                            "Market":     _ma_lbl,
                            "Players":    _ma_players,
                            "Source":     "🎰 DraftKings",
                            "Age":        f"{_ma_icon} {_ma_age_str} ago",
                        })
                except Exception:
                    continue
            if _ma_rows:
                st.dataframe(pd.DataFrame(_ma_rows), hide_index=True, use_container_width=True)
            else:
                st.info("Could not parse prop line files.")

    st.markdown("---")

    # Import props model
    try:
        from scripts.models.props_model import (
            generate_matchup, calculate_matchup_probability,
            generate_position_props, generate_round_score_prop,
            calculate_parlay, generate_suggested_parlays,
            prob_to_american, format_american_odds, calculate_edge,
            ParlayLeg
        )
        props_available = True
    except ImportError as e:
        st.error(f"Props model not available: {e}")
        props_available = False

    if props_available:
        # Load predictions data
        preds_df = pd.DataFrame()
        preds_path = OUTPUTS_DIR / "latest_predictions.csv"
        if preds_path.exists():
            preds_df = pd.read_csv(preds_path)

        if preds_df.empty:
            # Try to find any predictions file
            pred_files = get_prediction_files()
            if pred_files:
                preds_df = pd.read_csv(pred_files[0])

        if preds_df.empty:
            st.warning("No predictions available. Run predictions first to generate props.")
        else:
            preds_df = preds_df.copy()
            winner_edges_df = pd.DataFrame()

            prop_lines_df = pd.DataFrame()
            book_edges_df = pd.DataFrame()
            prop_lines_source = "none"
            # Prefer actively selected tournament on Betting page.
            prop_tournament_id = str(_rp_tid or "").strip().upper() if '_rp_tid' in locals() else ""
            if not prop_tournament_id:
                prop_tournament_id = _tournament_id_from_df(preds_df)
            dk_content_cards_df = pd.DataFrame()
            dk_content_cards_file = None

            if not prop_tournament_id:
                prop_tournament_id = _latest_tournament_id_from_prop_lines(max_age_hours=48.0)

            if prop_edge_tools_available and load_latest_prop_lines and score_book_props:
                prop_lines_df = load_latest_prop_lines(prop_tournament_id if prop_tournament_id else None)
                if not prop_lines_df.empty:
                    prop_lines_source = "file"
                else:
                    # Build a model-based baseline so the Book Edges tab stays usable
                    # before sportsbook prop ingestion is set up.
                    prop_lines_source = "model_baseline"
                    rank_col = "expected_value" if "expected_value" in preds_df.columns else "win_prob"
                    seed_df = preds_df.sort_values(rank_col, ascending=False).head(20).copy()
                    baseline_rows = []

                    # H2H baseline lines from model matchups
                    pair_count = min(6, len(seed_df) // 2)
                    for i in range(pair_count):
                        a = seed_df.iloc[i * 2].to_dict()
                        b = seed_df.iloc[i * 2 + 1].to_dict()
                        matchup = generate_matchup(a, b)
                        baseline_rows.append({
                            "market": "h2h",
                            "player_a": matchup.player_a,
                            "player_b": matchup.player_b,
                            "odds_a": matchup.odds_a,
                            "odds_b": matchup.odds_b,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                    # Round-score + birdies baseline lines from model stats
                    for _, prow in seed_df.head(12).iterrows():
                        p = prow.to_dict()
                        rs = generate_round_score_prop(
                            p,
                            round_num=1,
                            course_par=72,
                            course_scoring_avg=71.0,
                        )
                        baseline_rows.append({
                            "market": "round_score",
                            "player_name": p["player_name"],
                            "line": rs.line,
                            "over_odds": rs.over_odds,
                            "under_odds": rs.under_odds,
                            "round_num": 1,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                        sg_app = p.get("sg_app", 0) or 0
                        sg_putt = p.get("sg_putt", 0) or 0
                        form = p.get("form_trend", 0) or 0
                        over_prob = float(np.clip(0.5 + 0.12 * (sg_app + sg_putt) + 0.08 * form, 0.08, 0.92))
                        under_prob = 1 - over_prob
                        baseline_rows.append({
                            "market": "birdies",
                            "player_name": p["player_name"],
                            "line": 4.5,
                            "over_odds": prob_to_american(over_prob),
                            "under_odds": prob_to_american(under_prob),
                            "round_num": 1,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                    if baseline_rows:
                        prop_lines_df = pd.DataFrame(baseline_rows)

                if not prop_lines_df.empty:
                    book_edges_df = score_book_props(
                        preds_df,
                        prop_lines_df,
                        course_par=72,
                        course_avg=71.0,
                    )

            dk_content_cards_df, dk_content_cards_file = load_dk_content_cards_df(
                prop_tournament_id if prop_tournament_id else ""
            )

            # Add winner market edges to unified edge table.
            if not winner_edges_df.empty:
                if book_edges_df.empty:
                    book_edges_df = winner_edges_df.copy()
                else:
                    book_edges_df = pd.concat([winner_edges_df, book_edges_df], ignore_index=True)

            def _has_live_prop_market(market_name: str) -> bool:
                if prop_lines_df.empty or "market" not in prop_lines_df.columns:
                    return False
                mdf = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == market_name.lower()
                ].copy()
                if mdf.empty:
                    return False
                if "book" in mdf.columns:
                    return (mdf["book"].astype(str).str.upper() != "MODEL_BASELINE").any()
                return prop_lines_source == "file"

            has_live_h2h = _has_live_prop_market("h2h")
            has_live_round_score = _has_live_prop_market("round_score")
            has_live_birdies = _has_live_prop_market("birdies")
            current_live_markets = []
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                live_m = prop_lines_df.copy()
                if "book" in live_m.columns:
                    live_m = live_m[live_m["book"].astype(str).str.upper() != "MODEL_BASELINE"]
                current_live_markets = sorted(live_m["market"].dropna().astype(str).str.lower().unique().tolist())

            # Build robust player-name matching for sportsbook prop lines.
            model_players = preds_df["player_name"].dropna().astype(str).str.strip().tolist()
            model_player_set = set(model_players)
            exact_name_map = {}
            short_name_map = {}

            def _short_name_key(name: str) -> str:
                if pd.isna(name):
                    return ""
                cleaned = (
                    str(name)
                    .replace(",", " ")
                    .replace(".", " ")
                    .replace("-", " ")
                    .lower()
                    .strip()
                )
                toks = [t for t in cleaned.split() if t]
                toks = [t for t in toks if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
                if not toks:
                    return ""
                first = toks[0]
                last = toks[-1]
                if not first or not last:
                    return ""
                return f"{last} {first[0]}"

            for nm in model_players:
                k = _name_key(nm)
                if k and k not in exact_name_map:
                    exact_name_map[k] = nm
                sk = _short_name_key(nm)
                if sk:
                    short_name_map.setdefault(sk, []).append(nm)

            def _resolve_model_player(name: str) -> str:
                k = _name_key(name)
                if k in exact_name_map:
                    return exact_name_map[k]
                sk = _short_name_key(name)
                cands = short_name_map.get(sk, [])
                if len(cands) == 1:
                    return cands[0]
                return str(name).strip()

            round_lines_live_df = pd.DataFrame()
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                round_lines_live_df = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == "round_score"
                ].copy()
                if not round_lines_live_df.empty:
                    if "player_name" not in round_lines_live_df.columns:
                        round_lines_live_df["player_name"] = ""
                    round_lines_live_df["player_name"] = round_lines_live_df["player_name"].fillna("").astype(str).str.strip()
                    round_lines_live_df["round_num"] = pd.to_numeric(round_lines_live_df.get("round_num"), errors="coerce").fillna(1).astype(int)
                    round_lines_live_df["line"] = pd.to_numeric(round_lines_live_df.get("line"), errors="coerce")
                    round_lines_live_df["over_odds"] = pd.to_numeric(round_lines_live_df.get("over_odds"), errors="coerce")
                    round_lines_live_df["under_odds"] = pd.to_numeric(round_lines_live_df.get("under_odds"), errors="coerce")
                    round_lines_live_df["model_player"] = round_lines_live_df["player_name"].apply(_resolve_model_player)
                    round_lines_live_df["is_player_match"] = round_lines_live_df["model_player"].isin(model_player_set)

            h2h_lines_live_df = pd.DataFrame()
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                h2h_lines_live_df = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == "h2h"
                ].copy()
                if not h2h_lines_live_df.empty:
                    for c in ["player_a", "player_b"]:
                        if c not in h2h_lines_live_df.columns:
                            h2h_lines_live_df[c] = ""
                        h2h_lines_live_df[c] = h2h_lines_live_df[c].fillna("").astype(str).str.strip()
                    h2h_lines_live_df["odds_a"] = pd.to_numeric(h2h_lines_live_df.get("odds_a"), errors="coerce")
                    h2h_lines_live_df["odds_b"] = pd.to_numeric(h2h_lines_live_df.get("odds_b"), errors="coerce")
                    h2h_lines_live_df["model_player_a"] = h2h_lines_live_df["player_a"].apply(_resolve_model_player)
                    h2h_lines_live_df["model_player_b"] = h2h_lines_live_df["player_b"].apply(_resolve_model_player)
                    h2h_lines_live_df["is_match_a"] = h2h_lines_live_df["model_player_a"].isin(model_player_set)
                    h2h_lines_live_df["is_match_b"] = h2h_lines_live_df["model_player_b"].isin(model_player_set)
                    h2h_lines_live_df["is_full_match"] = h2h_lines_live_df["is_match_a"] & h2h_lines_live_df["is_match_b"]

            # =========================================================================
            # LOAD LIVE TOURNAMENT DATA FOR FILTERING
            # =========================================================================
            live_leaderboard_df = pd.DataFrame()
            live_contenders = set()
            live_contenders_normalized = set()
            tournament_round = 1
            is_tournament_live = False
            is_tournament_over = False
            leader_score = 0
            tournament_winner = ""

            live_dir = DATA_DIR / "live"
            live_tid = (prop_tournament_id or "").strip()
            live_path = live_dir / f"leaderboard_{live_tid.lower()}.csv" if live_tid else None

            if live_path and live_path.exists():
                try:
                    live_leaderboard_df = pd.read_csv(live_path)
                    if not live_leaderboard_df.empty:
                        tournament_round = int(live_leaderboard_df["current_round"].max()) if "current_round" in live_leaderboard_df.columns else 1
                        leader_score = int(live_leaderboard_df["total_numeric"].min()) if "total_numeric" in live_leaderboard_df.columns else 0

                        # Check if live (not all finished)
                        if "thru" in live_leaderboard_df.columns:
                            thru_vals = live_leaderboard_df["thru"].astype(str).str.upper()
                            all_finished = all(t in ["F", "F*", "18", ""] for t in thru_vals)
                            is_tournament_live = not all_finished

                            # Tournament is over if R4 and all finished
                            is_tournament_over = (tournament_round == 4 and all_finished)

                            if is_tournament_over:
                                # Get winner
                                winner_row = live_leaderboard_df[live_leaderboard_df["total_numeric"] == leader_score]
                                if not winner_row.empty:
                                    tournament_winner = winner_row.iloc[0].get("player_name", "Unknown")

                        # Get contenders (within 5 shots in R4, 7 in R3, all in R1-2)
                        if tournament_round >= 3 and not is_tournament_over:
                            threshold = leader_score + (5 if tournament_round == 4 else 7)
                            contenders_df = live_leaderboard_df[live_leaderboard_df["total_numeric"] <= threshold]
                        else:
                            contenders_df = live_leaderboard_df[live_leaderboard_df["made_cut"] == True] if "made_cut" in live_leaderboard_df.columns else live_leaderboard_df

                        live_contenders = set(contenders_df["player_name"].dropna().astype(str).str.strip().tolist())

                        # Also add by normalized name for matching
                        live_contenders_normalized = {_name_key(n) for n in live_contenders}
                except Exception as e:
                    st.caption(f"Could not load live data: {e}")

            def is_contender(player_name: str) -> bool:
                """Check if player is still a contender in the tournament."""
                if not live_contenders:
                    return True  # No live data, assume all are contenders
                if player_name in live_contenders:
                    return True
                return _name_key(player_name) in live_contenders_normalized

            def get_live_position(player_name: str) -> str:
                """Get player's current position from live leaderboard."""
                if live_leaderboard_df.empty:
                    return ""
                key = _name_key(player_name)
                match = live_leaderboard_df[live_leaderboard_df["player_name"].apply(_name_key) == key]
                if not match.empty:
                    row = match.iloc[0]
                    pos = row.get("position", "")
                    total = row.get("total", "")
                    thru = row.get("thru", "")
                    return f"{pos} ({total}) thru {thru}"
                return ""

            # Show tournament status
            if is_tournament_over:
                st.warning(f"🏁 **Tournament Complete** | Winner: {tournament_winner} ({leader_score:+d})")
                st.info("This tournament has finished. Betting recommendations are no longer available. Check back when the next tournament begins.")

            elif tournament_round >= 3 and live_contenders:
                st.info(f"🔴 **Round {tournament_round}** | Leader: {leader_score:+d} | Showing {len(live_contenders)} contenders")

            # Main tabs (consolidated)
            props_tab1, props_tab2, props_tab3, props_tab4, props_tab5 = st.tabs([
                "⚡ Value Bets",
                "📈 DraftKings Odds",
                "⚔️ Matchups",
                "🎲 Parlay Builder",
                "📰 Expert Picks",
            ])

            # =================================================================
            # TAB 0: VALUE BETS
            # =================================================================
            with props_tab1:

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. No active betting recommendations.")
                    st.info(f"**Winner:** {tournament_winner} finished at {leader_score:+d}")
                else:
                    # ── Load data ───────────────────────────────────────────
                    _vb_rec_df, _vb_rec_path = load_recommended_bets_df(prop_tournament_id)
                    _vb_preds_df = pd.DataFrame()
                    _preds_path_vb = OUTPUTS_DIR / "latest_predictions.csv"
                    if _preds_path_vb.exists():
                        _vb_preds_df = pd.read_csv(_preds_path_vb)

                    if _vb_rec_df.empty:
                        st.info(
                            "No value bets generated yet. Click **Refresh** below to score "
                            "the current DraftKings lines against the model."
                        )
                    else:
                        # ── Merge world_rank + form_trend from predictions ──
                        if not _vb_preds_df.empty:
                            _extra = _vb_preds_df[
                                [c for c in ["player_name","world_rank","form_trend","top20_prob",
                                             "cut_prob","dfs_ownership_proj","dk_odds_direction"]
                                 if c in _vb_preds_df.columns]
                            ].copy()
                            def _flip_name(n):
                                # "Last, First" → "first last" for matching rec file "First Last"
                                s = str(n).strip().lower()
                                if "," in s:
                                    parts = s.split(",", 1)
                                    s = f"{parts[1].strip()} {parts[0].strip()}"
                                return s
                            _extra["_pname_norm"] = _extra["player_name"].apply(_flip_name)
                            _vb_rec_df["_pname_norm"] = _vb_rec_df["player_name"].str.strip().str.lower()
                            _vb_rec_df = _vb_rec_df.merge(_extra.drop(columns=["player_name"]),
                                                          on="_pname_norm", how="left")
                            _vb_rec_df = _vb_rec_df.drop(columns=["_pname_norm"])

                        # Numeric coerce
                        for _col in ["edge_pts","model_prob","book_prob","ev_per_1",
                                     "odds_american","confidence"]:
                            if _col in _vb_rec_df.columns:
                                _vb_rec_df[_col] = pd.to_numeric(_vb_rec_df[_col], errors="coerce")

                        # ── Market filter ───────────────────────────────────
                        _mkts_avail = sorted(_vb_rec_df["market"].dropna().unique()) \
                            if "market" in _vb_rec_df.columns else []
                        _mkt_labels = {
                            "outright":"Win","top5":"Top 5","top10":"Top 10","top20":"Top 20",
                            "make_cut":"Make Cut","h2h":"Matchup","h2h_r1":"Matchup R1",
                            "h2h_r2":"Matchup R2","h2h_r3":"Matchup R3","h2h_r4":"Matchup R4",
                            "group_winner":"Group Winner","r2_leader":"Lead After R2",
                            "nationality_group":"Nationality",
                        }
                        _mkt_opts = ["All"] + [_mkt_labels.get(m, m.title()) for m in _mkts_avail]
                        _mkt_raw   = ["All"] + list(_mkts_avail)

                        _vb_filter_col, _vb_thresh_col, _vb_bankroll_col, _vb_spacer = st.columns([2, 2, 2, 1])
                        with _vb_filter_col:
                            _sel_mkt_label = st.selectbox(
                                "Market", _mkt_opts, key="vb_market_filter"
                            )
                        with _vb_thresh_col:
                            _vb_min_edge = st.slider(
                                "Min Edge (pts)", 0.0, 8.0, 1.5, 0.5, key="vb_edge_thresh"
                            )
                        with _vb_bankroll_col:
                            _vb_bankroll = st.number_input(
                                "Bankroll ($)", min_value=100, max_value=100000,
                                value=1000, step=100, key="vb_bankroll",
                                help="Used to compute Kelly dollar amounts on each bet card"
                            )

                        # ── Auto-refresh odds control ───────────────────────────
                        _ar_c1, _ar_c2, _ar_c3, _ar_c4 = st.columns([1, 1, 1, 2])
                        with _ar_c1:
                            _auto_on = st.toggle(
                                "Auto-refresh", value=False, key="vb_auto_on",
                                help="Automatically refresh odds + recommendations on a timer"
                            )
                        with _ar_c2:
                            _auto_interval = st.selectbox(
                                "Interval", [15, 30, 60],
                                format_func=lambda x: f"{x} min",
                                key="vb_auto_interval",
                                label_visibility="collapsed",
                                disabled=not _auto_on,
                            )
                        with _ar_c3:
                            if st.button("Refresh Now", key="vb_refresh_now", use_container_width=True):
                                with st.spinner("Refreshing odds..."):
                                    run_scraper(
                                        ["python3", "scripts/predictions/refresh_odds.py"],
                                        timeout=120
                                    )
                                    run_scraper(
                                        ["python3", "scripts/models/recommend_bets.py",
                                         "--tournament-id", prop_tournament_id],
                                        timeout=120
                                    )
                                st.session_state["_vb_auto_last"] = time.time()
                                st.cache_data.clear()
                                st.rerun()

                        # Auto-refresh timer logic
                        if _auto_on:
                            _now_ts   = time.time()
                            _last_ts  = st.session_state.get("_vb_auto_last", 0)
                            _interval_sec = _auto_interval * 60
                            _remaining    = _interval_sec - (_now_ts - _last_ts)

                            if _remaining <= 0:
                                with st.spinner("Auto-refreshing odds + bets..."):
                                    run_scraper(
                                        ["python3", "scripts/predictions/refresh_odds.py"],
                                        timeout=120
                                    )
                                    run_scraper(
                                        ["python3", "scripts/models/recommend_bets.py",
                                         "--tournament-id", prop_tournament_id],
                                        timeout=120
                                    )
                                st.session_state["_vb_auto_last"] = time.time()
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                _m = int(_remaining // 60)
                                _s = int(_remaining % 60)
                                with _ar_c4:
                                    st.caption(f"Next refresh in {_m}:{_s:02d}")
                                time.sleep(min(10, _remaining))
                                st.rerun()

                        # ── Build cut-player exclusion set from live leaderboard ──
                        _cut_names: set = set()
                        _lb_dir = DATA_DIR / "live"
                        _lb_files = sorted(_lb_dir.glob("leaderboard_r*.csv"),
                                           key=lambda p: p.stat().st_mtime, reverse=True)
                        if _lb_files:
                            try:
                                _lb = pd.read_csv(_lb_files[0])
                                if "made_cut" in _lb.columns and "player_name" in _lb.columns:
                                    # False = missed cut, or status == 'cut'/'wd'
                                    _mc = _lb["made_cut"].astype(str).str.lower()
                                    _st = _lb.get("status", pd.Series(dtype=str)).astype(str).str.lower()
                                    _cut_mask = (_mc == "false") | (_st.isin(["cut","wd","withdrawn","mc"]))
                                    _cut_names = set(
                                        _lb.loc[_cut_mask, "player_name"].str.strip().str.lower()
                                    )
                            except Exception:
                                pass

                        _sel_mkt = _mkt_raw[_mkt_opts.index(_sel_mkt_label)]
                        _filtered = _vb_rec_df.copy()

                        # Remove cut/WD players
                        if _cut_names and "player_name" in _filtered.columns:
                            _before = len(_filtered)
                            _filtered = _filtered[
                                ~_filtered["player_name"].str.strip().str.lower().isin(_cut_names)
                            ]
                            _n_cut = _before - len(_filtered)
                            if _n_cut > 0:
                                st.caption(f"ℹ️ {_n_cut} player{'s' if _n_cut>1 else ''} removed — missed cut or WD")

                        if _sel_mkt != "All":
                            _filtered = _filtered[_filtered["market"] == _sel_mkt]
                        _filtered = _filtered[
                            _filtered["edge_pts"].fillna(0) >= _vb_min_edge
                        ].sort_values("edge_pts", ascending=False)

                        # ── Hero metrics bar ────────────────────────────────
                        _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
                        with _mc1:
                            st.metric("Value Bets", len(_filtered))
                        with _mc2:
                            _best_e = _filtered["edge_pts"].max() if not _filtered.empty else 0
                            st.metric("Best Edge", f"+{_best_e:.1f} pts")
                        with _mc3:
                            _avg_ev = _filtered["ev_per_1"].mean() if "ev_per_1" in _filtered.columns and not _filtered.empty else 0
                            st.metric("Avg EV / $1", f"${_avg_ev:.2f}" if pd.notna(_avg_ev) else "—")
                        with _mc4:
                            if not _filtered.empty and "ev_per_1" in _filtered.columns:
                                _stakes = pd.to_numeric(
                                    _filtered.get("stake_units", pd.Series([1.0]*len(_filtered))),
                                    errors="coerce"
                                ).fillna(1.0)
                                _total_ev = (_filtered["ev_per_1"] * _stakes).sum()
                                st.metric("Total Slate EV", f"${_total_ev:.2f}",
                                          help="Sum of (EV per $1 × stake units) across all qualifying bets")
                            else:
                                st.metric("Total Slate EV", "—")
                        with _mc5:
                            _upd = ""
                            if _vb_rec_path and _vb_rec_path.exists():
                                _upd = datetime.fromtimestamp(_vb_rec_path.stat().st_mtime).strftime("%b %d %H:%M")
                            st.metric("Last Run", _upd or "—")

                        st.markdown("---")

                        # ── Bet cards ───────────────────────────────────────
                        _CARD_MKT_COLOR = {
                            "outright":     "#f1c40f",
                            "top5":         "#3498db",
                            "top10":        "#00c44f",
                            "top20":        "#9b59b6",
                            "make_cut":     "#1abc9c",
                            "h2h":          "#e67e22",
                            "h2h_r1":       "#e67e22",
                            "h2h_r2":       "#e67e22",
                            "h2h_r3":       "#e67e22",
                            "h2h_r4":       "#e67e22",
                            "group_winner":      "#e74c3c",
                            "r2_leader":         "#16a085",
                            "nationality_group": "#8e44ad",
                        }
                        _CONF_BADGE = {
                            (0.80, 2.0):  ("HIGH",     "#00c44f"),
                            (0.70, 0.80): ("MODERATE", "#f39c12"),
                            (0.00, 0.70): ("LEAN",     "#7f8c8d"),
                        }
                        def _conf_badge(c):
                            c = float(c) if pd.notna(c) else 0
                            if c >= 0.80: return "HIGH",     "#00c44f"
                            if c >= 0.70: return "MODERATE", "#f39c12"
                            return "LEAN", "#7f8c8d"

                        def _fmt_odds(v):
                            try:
                                n = int(float(v))
                                return f"+{n}" if n >= 0 else str(n)
                            except Exception:
                                return str(v)

                        _top_cards = _filtered.head(8)
                        if _top_cards.empty:
                            st.info("No bets meet the current filters. Try lowering the edge threshold.")
                        else:
                            _n_cols = 2
                            for _ci in range(0, len(_top_cards), _n_cols):
                                _card_cols = st.columns(_n_cols)
                                for _cj, (_, _row) in enumerate(
                                    _top_cards.iloc[_ci:_ci + _n_cols].iterrows()
                                ):
                                    with _card_cols[_cj]:
                                        _mkt      = str(_row.get("market", "")).lower()
                                        _border   = _CARD_MKT_COLOR.get(_mkt, "#444")
                                        _mkt_lbl  = _mkt_labels.get(_mkt, _mkt.title())
                                        _player   = str(_row.get("player_name", "—"))
                                        _odds_str = _fmt_odds(_row.get("odds_american", ""))
                                        _edge     = float(_row.get("edge_pts", 0) or 0)
                                        _model_p  = float(_row.get("model_prob", 0) or 0) * 100
                                        _book_p   = float(_row.get("book_prob", 0) or 0) * 100
                                        _ev       = float(_row.get("ev_per_1", 0) or 0)
                                        _conf_lbl, _conf_color = _conf_badge(_row.get("confidence"))
                                        _rank     = _row.get("world_rank")
                                        _rank_str = f"Rank #{int(_rank)}" if pd.notna(_rank) else ""
                                        _form     = _row.get("form_trend")
                                        _form_str = ""
                                        if pd.notna(_form):
                                            _fv = float(_form)
                                            _form_str = f"Form {_fv:+.2f}"

                                        # Cut risk for top5/top10 bets
                                        _cut_p = _row.get("cut_prob")
                                        _cut_warn = ""
                                        if _mkt in ("top5", "top10", "make_cut") and pd.notna(_cut_p):
                                            _cp = float(_cut_p)
                                            if _cp < 0.65:
                                                _cut_warn = (
                                                    f'<div style="margin-top:7px;padding:4px 8px;'
                                                    f'background:rgba(229,57,53,0.12);border:1px solid rgba(229,57,53,0.3);'
                                                    f'border-radius:5px;font-size:0.70em;color:#e57373;">'
                                                    f'⚠️ Cut risk: {(1-_cp)*100:.0f}% miss-cut probability</div>'
                                                )
                                            elif _cp < 0.80:
                                                _cut_warn = (
                                                    f'<div style="margin-top:7px;padding:4px 8px;'
                                                    f'background:rgba(243,156,18,0.10);border:1px solid rgba(243,156,18,0.25);'
                                                    f'border-radius:5px;font-size:0.70em;color:#f39c12;">'
                                                    f'Cut risk: {(1-_cp)*100:.0f}% miss-cut probability</div>'
                                                )

                                        # DFS ownership
                                        _dfs_own = _row.get("dfs_ownership_proj")
                                        _dfs_str = f"{float(_dfs_own):.1f}%" if pd.notna(_dfs_own) else "—"

                                        # DK movement direction arrow
                                        _dk_dir = str(_row.get("dk_odds_direction", "") or "")
                                        if _dk_dir == "UP":
                                            _dir_arrow = "▲"; _dir_color = "#00c44f"
                                        elif _dk_dir == "DOWN":
                                            _dir_arrow = "▼"; _dir_color = "#e74c3c"
                                        else:
                                            _dir_arrow = "→"; _dir_color = "#7f8c8d"

                                        # Group members (H2H / 3-ball / group bets)
                                        _group_members = str(_row.get("group_members", "") or "").strip()
                                        _group_members_html = ""
                                        if _group_members and _mkt in ("h2h","h2h_r1","h2h_r2","h2h_r3","h2h_r4","group_winner","nationality_group"):
                                            # Replace pipe separators with middle dots to prevent
                                            # Streamlit's markdown parser from treating them as table columns
                                            _gm_display = _group_members.replace(" | ", " &middot; ")
                                            _group_members_html = (
                                                f'<div style="margin-top:5px;font-size:0.72em;color:#8a9bbf;'
                                                f'background:rgba(255,255,255,0.04);padding:3px 7px;border-radius:4px;">'
                                                f'{_gm_display}</div>'
                                            )

                                        # Corroboration badge
                                        _corr_score = int(_row.get("corroboration_score", 0) or 0)
                                        _corroborated = bool(_row.get("corroborated", False))
                                        _corr_badge = ""
                                        if _corroborated and _corr_score >= 2:
                                            _corr_badge = (
                                                f'<span style="font-size:0.65em;font-weight:700;color:#f39c12;'
                                                f'background:rgba(243,156,18,0.15);padding:2px 6px;border-radius:4px;'
                                                f'margin-left:6px;">★ {_corr_score} markets</span>'
                                            )

                                        # Kelly stake
                                        _kelly_f = pd.to_numeric(_row.get("kelly_fraction"), errors="coerce")
                                        if pd.notna(_kelly_f) and _kelly_f > 0:
                                            _kelly_dollar = _kelly_f * _vb_bankroll
                                            _kelly_str = f"{_kelly_f*100:.1f}% · ${_kelly_dollar:.0f}"
                                        else:
                                            _kelly_str = "—"

                                        # Edge bar (0–10 pt scale)
                                        _bar_pct = min(int(_edge / 10 * 100), 100)

                                        _card_html = re.sub(r'\n[ \t]*\n', '\n', f"""
<div style="background:#0d1a30;border-left:4px solid {_border};border-radius:8px;
            padding:14px 16px;margin-bottom:4px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <span style="font-size:0.72em;font-weight:600;color:{_border};text-transform:uppercase;
                   letter-spacing:.06em;">{_mkt_lbl}</span>{_corr_badge}
      <div style="font-size:1.1em;font-weight:700;color:#dde6f5;margin-top:2px;">{_player}</div>
      <div style="font-size:0.75em;color:#7f8c8d;margin-top:1px;">{_rank_str}{"  ·  " if _rank_str and _form_str else ""}{_form_str}</div>
      {_group_members_html}
    </div>
    <div style="text-align:right;">
      <div style="font-size:1.6em;font-weight:800;color:{_border};line-height:1;">
        {_odds_str} <span style="font-size:0.55em;color:{_dir_color};vertical-align:middle;">{_dir_arrow}</span>
      </div>
      <span style="font-size:0.68em;font-weight:700;color:{_conf_color};background:rgba(255,255,255,.07);
                   padding:2px 6px;border-radius:4px;">{_conf_lbl}</span>
    </div>
  </div>
  <div style="margin-top:10px;display:flex;gap:18px;flex-wrap:wrap;">
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">MODEL</div>
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_model_p:.1f}%</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">MARKET</div>
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_book_p:.1f}%</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">EDGE</div>
      <div style="font-size:0.92em;font-weight:700;color:{_border};">+{_edge:.1f} pts</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">EV / $1</div>
      <div style="font-size:0.92em;font-weight:700;color:#00c44f;">${_ev:.2f}</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">KELLY (½K)</div>
      <div style="font-size:0.92em;font-weight:600;color:#f39c12;">{_kelly_str}</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">DFS OWN</div>
      <div style="font-size:0.92em;font-weight:600;color:#9b9bff;">{_dfs_str}</div>
    </div>
  </div>
  <div style="margin-top:8px;background:#1a2a40;border-radius:4px;height:4px;">
    <div style="width:{_bar_pct}%;height:4px;background:{_border};border-radius:4px;"></div>
  </div>
  {_cut_warn}
</div>
""")
                                        st.markdown(_card_html, unsafe_allow_html=True)

                        # ── Full sortable table ──────────────────────────────
                        if len(_filtered) > 8:
                            st.markdown("---")
                            st.markdown("#### All qualifying bets")

                        with st.expander(
                            f"Full table — {len(_filtered)} bets",
                            expanded=len(_filtered) <= 8
                        ):
                            _tbl_cols = [c for c in [
                                "market","player_name","odds_american",
                                "model_prob","book_prob","edge_pts",
                                "ev_per_1","kelly_fraction","confidence",
                            ] if c in _filtered.columns]
                            _tbl = _filtered[_tbl_cols].copy()
                            _tbl["market"]       = _tbl["market"].map(_mkt_labels).fillna(_tbl["market"])
                            _tbl["odds_american"] = _tbl["odds_american"].apply(
                                lambda x: _fmt_odds(x) if pd.notna(x) else "—"
                            )
                            _tbl["model_prob"] = (_tbl["model_prob"] * 100).round(1).astype(str) + "%"
                            _tbl["book_prob"]  = (_tbl["book_prob"]  * 100).round(1).astype(str) + "%"
                            _tbl["edge_pts"]   = _tbl["edge_pts"].round(2)
                            _tbl["ev_per_1"]   = _tbl["ev_per_1"].round(3)
                            _tbl["confidence"] = _tbl["confidence"].round(2)
                            if "kelly_fraction" in _tbl.columns:
                                _tbl["kelly_fraction"] = pd.to_numeric(
                                    _tbl["kelly_fraction"], errors="coerce"
                                )
                                _tbl["kelly_fraction"] = _tbl["kelly_fraction"].apply(
                                    lambda x: f"{x*100:.1f}%" if pd.notna(x) and x > 0 else "—"
                                )
                            _tbl = _tbl.rename(columns={
                                "market":         "Market",
                                "player_name":    "Player",
                                "odds_american":  "Odds",
                                "model_prob":     "Model%",
                                "book_prob":      "Market%",
                                "edge_pts":       "Edge (pts)",
                                "ev_per_1":       "EV/$1",
                                "kelly_fraction": "Kelly (½K)",
                                "confidence":     "Conf",
                            })
                            st.dataframe(_tbl, hide_index=True, use_container_width=True)

                    st.markdown("---")

                    # ── Refresh / Grade controls ─────────────────────────────
                    _ctrl_c1, _ctrl_c2, _ctrl_c3 = st.columns([1.5, 1.5, 4])
                    with _ctrl_c1:
                        if st.button("🔄 Refresh Bets", key="vb_refresh_btn", use_container_width=True):
                            _cmd = ["python3",
                                    str(PROJECT_ROOT / "scripts" / "models" / "recommend_bets.py")]
                            _tid = str(prop_tournament_id or "").strip().upper()
                            if _tid:
                                _cmd.extend(["--tournament-id", _tid])
                            try:
                                _res = subprocess.run(_cmd, capture_output=True, text=True,
                                                      timeout=90, cwd=PROJECT_ROOT)
                                if _res.returncode == 0:
                                    st.success("Refreshed!")
                                else:
                                    st.warning("Refresh failed — check pipeline logs.")
                                _msg = (_res.stdout or _res.stderr or "").strip()
                                if _msg:
                                    st.caption(_msg[:600])
                                load_recommended_bets_df.clear()
                                st.rerun()
                            except Exception as _e:
                                st.warning(f"Error: {_e}")
                    with _ctrl_c2:
                        if st.button("🧾 Grade Settled", key="vb_grade_btn", use_container_width=True):
                            _cmd = ["python3",
                                    str(PROJECT_ROOT / "scripts" / "models" / "grade_recommended_bets.py")]
                            _tid = str(prop_tournament_id or "").strip().upper()
                            if _tid:
                                _cmd.extend(["--tournament-id", _tid])
                            try:
                                _res = subprocess.run(_cmd, capture_output=True, text=True,
                                                      timeout=90, cwd=PROJECT_ROOT)
                                if _res.returncode == 0:
                                    st.success("Grading complete!")
                                else:
                                    st.warning("Grading failed.")
                                load_recommended_bets_df.clear()
                                st.rerun()
                            except Exception as _e:
                                st.warning(f"Error: {_e}")

            # =================================================================
            # TAB 1b: FADE LIST (inside props_tab1 as expander)
            # =================================================================
            with props_tab1:
                st.markdown("---")
                with st.expander("📉 Fade List — Vegas >> Model", expanded=False):
                    st.caption("Players the market prices higher than our model suggests — potential fades or backs-of-field targets.")

                    _fade_df = preds_df.copy() if not preds_df.empty else pd.DataFrame()
                    _fade_ready = (
                        not _fade_df.empty
                        and "model_vs_vegas_edge" in _fade_df.columns
                        and "player_name" in _fade_df.columns
                    )

                    if not _fade_ready:
                        st.info("Predictions with odds data required. Run the full pipeline with odds refresh first.")
                    else:
                        _fade_df["model_vs_vegas_edge"] = pd.to_numeric(
                            _fade_df["model_vs_vegas_edge"], errors="coerce"
                        )
                        _fade_thresh_pct = st.slider(
                            "Min fade magnitude (%):", 0.5, 10.0, 2.0, 0.5,
                            key="fade_thresh_slider",
                        )
                        _fade_thresh = _fade_thresh_pct / 100.0

                        _fades = _fade_df[
                            _fade_df["model_vs_vegas_edge"] <= -_fade_thresh
                        ].sort_values("model_vs_vegas_edge", ascending=True)

                        if _fades.empty:
                            st.info("No strong fades at this threshold. Try lowering the minimum.")
                        else:
                            _f1, _f2, _f3, _f4 = st.columns(4)
                            with _f1:
                                st.metric("Fades Found", len(_fades))
                            with _f2:
                                st.metric("Avg Fade",
                                          f"{_fades['model_vs_vegas_edge'].mean()*100:.1f}%")
                            with _f3:
                                _worst = _fades.iloc[0]
                                st.metric("Biggest Fade",
                                          f"{float(_worst['model_vs_vegas_edge'])*100:.1f}%",
                                          help=str(_worst.get("player_name", "")))
                            with _f4:
                                _strong_fades = int((_fades["model_vs_vegas_edge"] < -0.05).sum())
                                st.metric("Strong Fades (>5%)", _strong_fades)

                            st.markdown("#### Top Fades")
                            _n_cols = 2
                            for _fi in range(0, min(len(_fades), 8), _n_cols):
                                _fade_cols = st.columns(_n_cols)
                                for _fj, (_, _frow) in enumerate(
                                    _fades.iloc[_fi:_fi + _n_cols].iterrows()
                                ):
                                    with _fade_cols[_fj]:
                                        _fp      = str(_frow.get("player_name", "—"))
                                        _fedge   = float(_frow.get("model_vs_vegas_edge", 0) or 0)
                                        _fodds   = _frow.get("odds_to_win", "—")
                                        _fmodel  = float(_frow.get("win_prob", 0) or 0) * 100
                                        _fvegas  = float(_frow.get("vegas_prob", 0) or 0) * 100
                                        _frank   = _frow.get("world_rank")
                                        _frank_s = f"Rank #{int(_frank)}" if pd.notna(_frank) else ""
                                        _fbar    = min(int(abs(_fedge) / 0.10 * 100), 100)
                                        st.markdown(f"""
<div style="background:#0d1a30;border-left:4px solid #e74c3c;border-radius:8px;
            padding:14px 16px;margin-bottom:4px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <span style="font-size:0.72em;font-weight:600;color:#e74c3c;text-transform:uppercase;
                   letter-spacing:.06em;">FADE</span>
      <div style="font-size:1.1em;font-weight:700;color:#dde6f5;margin-top:2px;">{_fp}</div>
      <div style="font-size:0.75em;color:#7f8c8d;margin-top:1px;">{_frank_s}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:1.6em;font-weight:800;color:#e74c3c;line-height:1;">{_fodds}</div>
      <span style="font-size:0.68em;font-weight:700;color:#e74c3c;background:rgba(231,76,60,.12);
                   padding:2px 6px;border-radius:4px;">VEGAS&gt;&gt;MODEL</span>
    </div>
  </div>
  <div style="margin-top:10px;display:flex;gap:18px;">
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">MODEL</div>
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_fmodel:.1f}%</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">MARKET</div>
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_fvegas:.1f}%</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">FADE EDGE</div>
      <div style="font-size:0.92em;font-weight:700;color:#e74c3c;">{_fedge*100:.1f}%</div>
    </div>
  </div>
  <div style="margin-top:8px;background:#1a2a40;border-radius:4px;height:4px;">
    <div style="width:{_fbar}%;height:4px;background:#e74c3c;border-radius:4px;"></div>
  </div>
</div>
""", unsafe_allow_html=True)

                            # Full sortable fade table (no nested expander — use markdown header)
                            if len(_fades) > 8:
                                st.markdown(f"---\n**All {len(_fades)} fades**")
                                _ftbl_cols = [c for c in [
                                    "player_name", "odds_to_win", "win_prob",
                                    "vegas_prob", "model_vs_vegas_edge", "world_rank",
                                ] if c in _fades.columns]
                                _ftbl = _fades[_ftbl_cols].copy()
                                if "win_prob"  in _ftbl.columns:
                                    _ftbl["win_prob"]  = (_ftbl["win_prob"]  * 100).round(1).astype(str) + "%"
                                if "vegas_prob" in _ftbl.columns:
                                    _ftbl["vegas_prob"] = (_ftbl["vegas_prob"] * 100).round(1).astype(str) + "%"
                                if "model_vs_vegas_edge" in _ftbl.columns:
                                    _ftbl["model_vs_vegas_edge"] = (
                                        _ftbl["model_vs_vegas_edge"] * 100
                                    ).round(1).astype(str) + "%"
                                _ftbl = _ftbl.rename(columns={
                                    "player_name":         "Player",
                                    "odds_to_win":         "Odds",
                                    "win_prob":            "Model%",
                                    "vegas_prob":          "Market%",
                                    "model_vs_vegas_edge": "Edge",
                                    "world_rank":          "Rank",
                                })
                                st.dataframe(_ftbl, hide_index=True, use_container_width=True)

            # =================================================================
            # TAB 2: DRAFTKINGS ODDS
            # =================================================================
            with props_tab2:
                st.markdown("### 📈 DraftKings Odds")
                st.caption("Winner markets plus props: round score, birdies, bogeys, and cut")

                dk_odds_df = pd.DataFrame()
                if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                    dk_odds_df = prop_lines_df.copy()

                if dk_odds_df.empty:
                    st.info("No DraftKings odds available. Run the scraper to fetch latest odds.")
                    st.code("python3 scripts/scrapers/fetch_draftkings_props.py --tournament-id R2026007")
                else:
                    market_labels = {
                        "outright": "🏆 Outright Winner",
                        "top5": "🔝 Top 5",
                        "top10": "🎯 Top 10",
                        "top20": "📍 Top 20",
                        "make_cut": "✅ Make Cut",
                        "miss_cut": "❌ Miss Cut",
                        "h2h": "⚔️ Head-to-Head",
                        "group_winner": "👥 Group Winner",
                        "round_score": "📊 Round Score O/U",
                        "birdies": "🐦 Birdies O/U",
                        "bogeys": "🟥 Bogeys O/U",
                    }
                    preferred_order = [
                        "outright", "top5", "top10", "top20",
                        "make_cut", "miss_cut",
                        "h2h", "group_winner",
                        "round_score", "birdies", "bogeys",
                    ]
                    all_markets = (
                        dk_odds_df["market"].dropna().astype(str).str.lower().drop_duplicates().tolist()
                    )
                    market_options = [m for m in preferred_order if m in all_markets] + [
                        m for m in all_markets if m not in preferred_order
                    ]

                    selected_market = st.selectbox(
                        "Market Type",
                        options=market_options,
                        format_func=lambda x: market_labels.get(x, x),
                        key="dk_market_select"
                    )

                    market_df = dk_odds_df[
                        dk_odds_df["market"].astype(str).str.lower() == selected_market
                    ].copy()

                    search = st.text_input("Search player", key="dk_search", placeholder="Type to filter...")
                    if search:
                        search_l = search.lower()
                        if "player_name" in market_df.columns:
                            market_df = market_df[
                                market_df["player_name"].fillna("").astype(str).str.lower().str.contains(search_l)
                            ]
                        elif "player_a" in market_df.columns and "player_b" in market_df.columns:
                            market_df = market_df[
                                market_df["player_a"].fillna("").astype(str).str.lower().str.contains(search_l)
                                | market_df["player_b"].fillna("").astype(str).str.lower().str.contains(search_l)
                            ]

                    if market_df.empty:
                        st.info("No rows for that market after filters.")
                    elif selected_market in {"outright", "top5", "top10", "top20", "make_cut", "miss_cut", "group_winner"}:
                        market_df["odds_num"] = pd.to_numeric(market_df.get("odds"), errors="coerce")
                        market_df["implied_prob"] = pd.to_numeric(market_df.get("implied_prob"), errors="coerce")
                        market_df = market_df.sort_values("odds_num", ascending=True, na_position="last")

                        display_df = pd.DataFrame({
                            "Player": market_df.get("player_name", ""),
                            "Odds": market_df["odds_num"].apply(_format_american_odds),
                            "Implied %": (market_df["implied_prob"] * 100).round(2).astype(str) + "%",
                            "Market": market_df.get("market_name", ""),
                        })
                        st.caption(f"Showing {len(display_df)} rows")
                        st.dataframe(display_df, hide_index=True, use_container_width=True, height=500)

                        if selected_market in {"outright", "top5", "top10", "group_winner"}:
                            st.markdown("---")
                            label = "👥 Group Players" if selected_market == "group_winner" else "🔥 Top Favorites"
                            n_show = len(market_df) if selected_market == "group_winner" else 5
                            st.markdown(f"#### {label}")
                            top5_df = market_df.head(n_show)
                            cols = st.columns(min(n_show, 5))
                            for i, (_, row) in enumerate(top5_df.iterrows()):
                                with cols[i % len(cols)]:
                                    player = str(row.get("player_name", "")).strip()
                                    st.metric(
                                        player.split()[-1] if player else "—",
                                        _format_american_odds(row.get("odds_num")),
                                        f"{(row.get('implied_prob', np.nan) * 100):.1f}%" if pd.notna(row.get("implied_prob")) else "—",
                                    )

                    elif selected_market in {"round_score", "birdies", "bogeys"}:
                        market_df["line"] = pd.to_numeric(market_df.get("line"), errors="coerce")
                        market_df["over_odds"] = pd.to_numeric(market_df.get("over_odds"), errors="coerce")
                        market_df["under_odds"] = pd.to_numeric(market_df.get("under_odds"), errors="coerce")
                        market_df["round_num"] = pd.to_numeric(market_df.get("round_num"), errors="coerce")
                        market_df = market_df.sort_values(["round_num", "player_name"], na_position="last")
                        display_df = pd.DataFrame({
                            "Player": market_df.get("player_name", ""),
                            "Line": market_df["line"],
                            "Over": market_df["over_odds"].apply(_format_american_odds),
                            "Under": market_df["under_odds"].apply(_format_american_odds),
                            "Round": market_df["round_num"].fillna(1).astype(int),
                            "Market": market_df.get("market_name", ""),
                        })
                        st.caption(f"Showing {len(display_df)} rows")
                        st.dataframe(display_df, hide_index=True, use_container_width=True, height=500)

                    elif selected_market == "h2h":
                        market_df["odds_a"] = pd.to_numeric(market_df.get("odds_a"), errors="coerce")
                        market_df["odds_b"] = pd.to_numeric(market_df.get("odds_b"), errors="coerce")
                        market_df = market_df.sort_values(["player_a", "player_b"], na_position="last")
                        display_df = pd.DataFrame({
                            "Player A": market_df.get("player_a", ""),
                            "Odds A": market_df["odds_a"].apply(_format_american_odds),
                            "Player B": market_df.get("player_b", ""),
                            "Odds B": market_df["odds_b"].apply(_format_american_odds),
                            "Market": market_df.get("market_name", ""),
                        })
                        st.caption(f"Showing {len(display_df)} matchups")
                        st.dataframe(display_df, hide_index=True, use_container_width=True, height=500)

                    if "fetched_at" in market_df.columns:
                        fetched_vals = market_df["fetched_at"].dropna().astype(str)
                        if not fetched_vals.empty:
                            st.caption(f"Source snapshot: {fetched_vals.iloc[0]}")

                    # ── Odds Movement / Drift tracker ────────────────────────
                    st.markdown("---")
                    with st.expander("📊 Odds Movement — Recent Drift", expanded=False):
                        _snap_dir = DATA_DIR / "odds" / "snapshots"
                        _snaps = sorted(
                            _snap_dir.glob("odds_snapshot_*.csv"),
                            key=lambda p: p.stat().st_mtime, reverse=True
                        ) if _snap_dir.exists() else []

                        if len(_snaps) < 2:
                            st.info("Need at least 2 odds snapshots to show movement. "
                                    "Snapshots are saved automatically each time you refresh odds.")
                        else:
                            try:
                                _snap_new = pd.read_csv(_snaps[0])
                                _snap_old = pd.read_csv(_snaps[1])
                                _snap_new["odds_numeric"] = pd.to_numeric(
                                    _snap_new["odds_numeric"], errors="coerce")
                                _snap_old["odds_numeric"] = pd.to_numeric(
                                    _snap_old["odds_numeric"], errors="coerce")

                                _snap_new_t = _snap_new["snapshot_at"].iloc[0] if "snapshot_at" in _snap_new.columns else "latest"
                                _snap_old_t = _snap_old["snapshot_at"].iloc[0] if "snapshot_at" in _snap_old.columns else "previous"
                                st.caption(f"Comparing: **{_snap_old_t}** → **{_snap_new_t}**")

                                _join_col = "player_id" if "player_id" in _snap_new.columns and "player_id" in _snap_old.columns else "player_name"
                                _drift = _snap_new[[_join_col, "player_name", "odds_numeric", "odds_to_win"]].merge(
                                    _snap_old[[_join_col, "odds_numeric"]].rename(columns={"odds_numeric": "odds_prev"}),
                                    on=_join_col, how="inner"
                                )
                                _drift["delta"] = _drift["odds_numeric"] - _drift["odds_prev"]
                                _drift = _drift[_drift["delta"].abs() > 0].sort_values("delta")

                                if _drift.empty:
                                    st.success("No odds movement detected between the two most recent snapshots.")
                                else:
                                    # Summary metrics
                                    _d1, _d2, _d3 = st.columns(3)
                                    with _d1:
                                        st.metric("Players Moved", len(_drift))
                                    with _d2:
                                        _shortened = (_drift["delta"] < 0)
                                        st.metric("Shortened (more favored)", int(_shortened.sum()))
                                    with _d3:
                                        _lengthened = (_drift["delta"] > 0)
                                        st.metric("Lengthened (less favored)", int(_lengthened.sum()))

                                    def _mv_arrow(d):
                                        if d < -20:  return "▼▼"
                                        if d < 0:    return "▼"
                                        if d > 20:   return "▲▲"
                                        return "▲"

                                    _drift["Move"]    = _drift["delta"].apply(_mv_arrow)
                                    _drift["Current"] = _drift["odds_to_win"]
                                    _drift["Change"]  = _drift["delta"].apply(
                                        lambda x: f"{x:+.0f}" if pd.notna(x) else "—"
                                    )
                                    _drift_disp = _drift[["player_name", "Current", "Change", "Move"]].rename(
                                        columns={"player_name": "Player"}
                                    )
                                    st.dataframe(_drift_disp, hide_index=True, use_container_width=True)
                            except Exception as _de:
                                st.warning(f"Could not compute drift: {_de}")

            # =================================================================
            # TAB 3: HEAD-TO-HEAD MATCHUPS
            # =================================================================
            with props_tab3:
                st.markdown("### ⚔️ Head-to-Head Matchups")
                st.caption("DraftKings matchup lines scored against model win probabilities.")

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. Matchups are no longer active.")

                # ── DK Matchup Lines with Edge ────────────────────────────────
                _dk_h2h = pd.DataFrame()
                if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                    _dk_h2h = prop_lines_df[
                        prop_lines_df["market"].astype(str).str.lower() == "h2h"
                    ].copy()

                if not _dk_h2h.empty:
                    # Compute model edge for each side using win_prob
                    def _h2h_win_prob(name, _pl=preds_df):
                        _k = str(name).strip().lower()
                        for _, _r in _pl.iterrows():
                            if str(_r.get("player_name","")).strip().lower() == _k:
                                return pd.to_numeric(_r.get("win_prob"), errors="coerce")
                        # last-name fallback
                        _last = _k.split()[-1] if _k.split() else ""
                        _cands = [_r for _, _r in _pl.iterrows()
                                  if str(_r.get("player_name","")).strip().lower().split()[-1:] == [_last]]
                        if len(_cands) == 1:
                            return pd.to_numeric(_cands[0].get("win_prob"), errors="coerce")
                        return np.nan

                    _h2h_rows = []
                    for _, _h in _dk_h2h.iterrows():
                        _pa = str(_h.get("player_a","") or "").strip()
                        _pb = str(_h.get("player_b","") or "").strip()
                        _oa = pd.to_numeric(_h.get("odds_a"), errors="coerce")
                        _ob = pd.to_numeric(_h.get("odds_b"), errors="coerce")
                        if not _pa or not _pb or pd.isna(_oa) or pd.isna(_ob):
                            continue
                        _wp_a = _h2h_win_prob(_pa)
                        _wp_b = _h2h_win_prob(_pb)
                        _denom = (_wp_a if pd.notna(_wp_a) else 0) + (_wp_b if pd.notna(_wp_b) else 0)
                        if _denom > 0 and pd.notna(_wp_a) and pd.notna(_wp_b):
                            _mp_a = _wp_a / _denom
                            _mp_b = _wp_b / _denom
                            _bp_a = 100/(_oa+100) if _oa >= 0 else abs(_oa)/(abs(_oa)+100)
                            _bp_b = 100/(_ob+100) if _ob >= 0 else abs(_ob)/(abs(_ob)+100)
                            _edge_a = (_mp_a - _bp_a) * 100
                            _edge_b = (_mp_b - _bp_b) * 100
                        else:
                            _mp_a = _mp_b = _edge_a = _edge_b = np.nan

                        _rn = _h.get("round_num")
                        _rn_str = f"R{int(_rn)}" if pd.notna(_rn) else "Tournament"
                        _h2h_rows.append({
                            "Round":    _rn_str,
                            "Player A": _pa,
                            "Odds A":   f"{int(_oa):+d}",
                            "Edge A":   round(_edge_a, 1) if pd.notna(_edge_a) else None,
                            "Player B": _pb,
                            "Odds B":   f"{int(_ob):+d}",
                            "Edge B":   round(_edge_b, 1) if pd.notna(_edge_b) else None,
                            "Model A%": f"{_mp_a*100:.0f}%" if pd.notna(_mp_a) else "—",
                            "Model B%": f"{_mp_b*100:.0f}%" if pd.notna(_mp_b) else "—",
                        })

                    if _h2h_rows:
                        _h2h_disp = pd.DataFrame(_h2h_rows)
                        # Sort by best edge (max of |edge_a|, |edge_b|)
                        _h2h_disp["_best"] = _h2h_disp[["Edge A","Edge B"]].apply(
                            pd.to_numeric, errors="coerce"
                        ).abs().max(axis=1)
                        _h2h_disp = _h2h_disp.sort_values("_best", ascending=False).drop(columns=["_best"])

                        _m1, _m2, _m3 = st.columns(3)
                        with _m1: st.metric("DK Matchups", len(_h2h_rows))
                        with _m2:
                            _edges = [r["Edge A"] for r in _h2h_rows if r["Edge A"] is not None and r["Edge A"] > 1]
                            _edges += [r["Edge B"] for r in _h2h_rows if r["Edge B"] is not None and r["Edge B"] > 1]
                            st.metric("Positive Edges (>1pt)", len(_edges))
                        with _m3:
                            _best = max((_e for _e in _edges), default=0)
                            st.metric("Best Edge", f"+{_best:.1f} pts" if _best else "—")

                        st.dataframe(_h2h_disp, hide_index=True, use_container_width=True, height=420)
                    st.markdown("---")
                else:
                    st.info("No DraftKings H2H lines loaded yet. Fetch odds to populate matchup edge table.")
                    st.markdown("---")

                st.markdown("#### 🔍 Individual Matchup Explorer")
                rank_col = "expected_value" if "expected_value" in preds_df.columns else "win_prob"
                preds_ranked = preds_df.copy()
                preds_ranked["model_rank"] = preds_ranked[rank_col].rank(ascending=False, method="min").astype(int)
                player_list = (
                    preds_ranked.sort_values("model_rank")["player_name"]
                    .dropna().astype(str).drop_duplicates().tolist()
                )
                player_lookup = {str(r["player_name"]): r.to_dict()
                                 for _, r in preds_ranked.iterrows()
                                 if pd.notna(r.get("player_name"))}

                player_a = None
                player_b = None
                live_h2h_row = None

                col1, col2 = st.columns(2)
                with col1:
                    player_a = st.selectbox("Player A:", player_list, index=0, key="h2h_a")
                with col2:
                    default_b = 1 if len(player_list) > 1 else 0
                    player_b = st.selectbox("Player B:", player_list, index=default_b, key="h2h_b")

                if player_a and player_b and player_a != player_b:
                    # Get player data
                    if player_a not in player_lookup or player_b not in player_lookup:
                        st.warning("One or both selected players were not found in model predictions.")
                        player_a_data = None
                        player_b_data = None
                    else:
                        player_a_data = player_lookup[player_a]
                        player_b_data = player_lookup[player_b]

                    # Generate matchup
                    if player_a_data is None or player_b_data is None:
                        matchup = None
                    else:
                        matchup = generate_matchup(player_a_data, player_b_data)

                    if matchup is not None:

                        # ── Helpers ──────────────────────────────────────────
                        def _g(d, k):
                            v = d.get(k)
                            try:
                                return float(v) if pd.notna(v) else None
                            except (TypeError, ValueError):
                                return None

                        def _bar_split(fa, fb):
                            """Shift both values to ≥0 then compute proportional fill."""
                            if fa is None or fb is None:
                                return 50, 50
                            mn = min(fa, fb)
                            if mn < 0:
                                fa -= mn
                                fb -= mn
                            total = fa + fb
                            if total == 0:
                                return 50, 50
                            return max(2, fa / total * 100), max(2, fb / total * 100)

                        def _cmp_row(label, va, vb, higher_better=True,
                                     fmt=".1f", suffix=""):
                            fa = va if isinstance(va, (int, float)) and pd.notna(va) else None
                            fb = vb if isinstance(vb, (int, float)) and pd.notna(vb) else None
                            na_str = "—"

                            if fa is None and fb is None:
                                a_str = b_str = na_str
                                a_col = b_col = "#3a5070"
                                a_w = b_w = "400"
                                bar_a = bar_b = "#111e33"
                                fill_a = fill_b = 50
                            else:
                                a_better = b_better = False
                                if fa is not None and fb is not None:
                                    a_better = (fa > fb) if higher_better else (fa < fb)
                                    b_better = (fb > fa) if higher_better else (fb < fa)
                                try:
                                    a_str = f"{fa:{fmt}}{suffix}" if fa is not None else na_str
                                except Exception:
                                    a_str = str(fa) if fa is not None else na_str
                                try:
                                    b_str = f"{fb:{fmt}}{suffix}" if fb is not None else na_str
                                except Exception:
                                    b_str = str(fb) if fb is not None else na_str
                                a_col = "#00c44f" if a_better else ("#8899aa" if b_better else "#dde6f5")
                                b_col = "#00c44f" if b_better else ("#8899aa" if a_better else "#dde6f5")
                                a_w = "700" if a_better else "400"
                                b_w = "700" if b_better else "400"
                                fill_a, fill_b = _bar_split(fa, fb)
                                bar_a = "#00c44f" if a_better else "#111e33"
                                bar_b = "#00c44f" if b_better else "#111e33"

                            return (
                                f'<div style="display:grid;grid-template-columns:1fr auto 1fr;'
                                f'align-items:center;padding:9px 20px;border-bottom:1px solid #0e1c2e;">'
                                f'<div style="text-align:right;font-size:1.0em;font-weight:{a_w};color:{a_col};">{a_str}</div>'
                                f'<div style="text-align:center;font-size:0.7em;color:#4a6080;padding:0 18px;'
                                f'min-width:155px;text-transform:uppercase;letter-spacing:.06em;">{label}</div>'
                                f'<div style="text-align:left;font-size:1.0em;font-weight:{b_w};color:{b_col};">{b_str}</div>'
                                f'</div>'
                                f'<div style="display:grid;grid-template-columns:{fill_a:.0f}fr {fill_b:.0f}fr;'
                                f'height:2px;margin:0 20px;">'
                                f'<div style="background:{bar_a};border-radius:2px 0 0 2px;"></div>'
                                f'<div style="background:{bar_b};border-radius:0 2px 2px 0;"></div>'
                                f'</div>'
                            )

                        def _sec(title):
                            return (
                                f'<div style="background:#070f1c;padding:7px 20px;margin-top:1px;">'
                                f'<span style="font-size:0.68em;font-weight:700;color:#2a4060;'
                                f'text-transform:uppercase;letter-spacing:.1em;">{title}</span></div>'
                            )

                        # ── Data ─────────────────────────────────────────────
                        pa, pb = player_a_data, player_b_data
                        prob_a = matchup.prob_a_wins * 100
                        prob_b = matchup.prob_b_wins * 100
                        rank_a = pa.get("model_rank", "—")
                        rank_b = pb.get("model_rank", "—")
                        odds_a_str = format_american_odds(matchup.odds_a)
                        odds_b_str = format_american_odds(matchup.odds_b)
                        win_col_a = "#00c44f" if prob_a > prob_b else "#dde6f5"
                        win_col_b = "#00c44f" if prob_b > prob_a else "#dde6f5"
                        conf_txt = str(matchup.confidence).upper()

                        if matchup.prob_a_wins > 0.55:
                            verdict_name = player_a
                            verdict_diff = f"+{(matchup.prob_a_wins - matchup.prob_b_wins)*100:.1f} pp edge"
                            verdict_col = "#00c44f"
                        elif matchup.prob_b_wins > 0.55:
                            verdict_name = player_b
                            verdict_diff = f"+{(matchup.prob_b_wins - matchup.prob_a_wins)*100:.1f} pp edge"
                            verdict_col = "#00c44f"
                        else:
                            verdict_name = "TOO CLOSE TO CALL"
                            verdict_diff = "less than 5 pp difference"
                            verdict_col = "#f39c12"

                        # ── Stat rows ─────────────────────────────────────────
                        rows = ""

                        rows += _sec("Model Probabilities")
                        rows += _cmp_row("Win", prob_a, prob_b, fmt=".1f", suffix="%")
                        rows += _cmp_row("Top 5", (_g(pa,"top5_prob") or 0)*100, (_g(pb,"top5_prob") or 0)*100, fmt=".1f", suffix="%")
                        rows += _cmp_row("Top 10", (_g(pa,"top10_prob") or 0)*100, (_g(pb,"top10_prob") or 0)*100, fmt=".1f", suffix="%")
                        rows += _cmp_row("Top 20", (_g(pa,"top20_prob") or 0)*100, (_g(pb,"top20_prob") or 0)*100, fmt=".1f", suffix="%")
                        rows += _cmp_row("Expected Value", _g(pa,"expected_value"), _g(pb,"expected_value"), fmt=",.0f")

                        rows += _sec("Strokes Gained · Season")
                        rows += _cmp_row("Total", _g(pa,"season_sg_total"), _g(pb,"season_sg_total"), fmt="+.2f")
                        rows += _cmp_row("Off the Tee", _g(pa,"season_sg_ott"), _g(pb,"season_sg_ott"), fmt="+.2f")
                        rows += _cmp_row("Approach", _g(pa,"season_sg_app"), _g(pb,"season_sg_app"), fmt="+.2f")
                        rows += _cmp_row("Around Green", _g(pa,"season_sg_arg"), _g(pb,"season_sg_arg"), fmt="+.2f")
                        rows += _cmp_row("Putting", _g(pa,"season_sg_putt"), _g(pb,"season_sg_putt"), fmt="+.2f")
                        rows += _cmp_row("Tee to Green", _g(pa,"season_sg_t2g"), _g(pb,"season_sg_t2g"), fmt="+.2f")

                        rows += _sec("Recent Form")
                        rows += _cmp_row("Form Trend", _g(pa,"form_trend"), _g(pb,"form_trend"), fmt="+.2f")
                        rows += _cmp_row("Scoring Avg", _g(pa,"recent_scoring_avg"), _g(pb,"recent_scoring_avg"), higher_better=False, fmt=".2f")
                        rows += _cmp_row("Top 5s", _g(pa,"recent_top5s"), _g(pb,"recent_top5s"), fmt=".0f")
                        rows += _cmp_row("Top 10s", _g(pa,"recent_top10s"), _g(pb,"recent_top10s"), fmt=".0f")
                        rows += _cmp_row("Cuts Made %", (_g(pa,"recent_cuts_pct") or 0)*100, (_g(pb,"recent_cuts_pct") or 0)*100, fmt=".0f", suffix="%")
                        rows += _cmp_row("Final Round SG", _g(pa,"recent_final_round"), _g(pb,"recent_final_round"), fmt="+.2f")
                        rows += _cmp_row("Consistency (σ)", _g(pa,"finish_consistency"), _g(pb,"finish_consistency"), higher_better=False, fmt=".1f")

                        rows += _sec("Course History")
                        rows += _cmp_row("Avg Finish", _g(pa,"hist_avg_finish"), _g(pb,"hist_avg_finish"), higher_better=False, fmt=".0f")
                        rows += _cmp_row("Best Finish", _g(pa,"hist_best_finish"), _g(pb,"hist_best_finish"), higher_better=False, fmt=".0f")
                        rows += _cmp_row("Wins Here", _g(pa,"hist_wins"), _g(pb,"hist_wins"), fmt=".0f")
                        rows += _cmp_row("Top 5s Here", _g(pa,"hist_top5s"), _g(pb,"hist_top5s"), fmt=".0f")
                        rows += _cmp_row("Top 10s Here", _g(pa,"hist_top10s"), _g(pb,"hist_top10s"), fmt=".0f")
                        rows += _cmp_row("Cut Rate", (_g(pa,"hist_cut_rate") or 0)*100, (_g(pb,"hist_cut_rate") or 0)*100, fmt=".0f", suffix="%")
                        rows += _cmp_row("Times Played", _g(pa,"hist_times_played"), _g(pb,"hist_times_played"), fmt=".0f")

                        rows += _sec("Market")
                        rows += _cmp_row("World Rank", _g(pa,"world_rank"), _g(pb,"world_rank"), higher_better=False, fmt=".0f")
                        _ea = _g(pa,"model_vs_vegas_edge")
                        _eb = _g(pb,"model_vs_vegas_edge")
                        if _ea is not None or _eb is not None:
                            rows += _cmp_row("Model vs Market Edge", (_ea or 0)*100, (_eb or 0)*100, fmt="+.1f", suffix=" pp")

                        # ── Render ────────────────────────────────────────────
                        st.markdown(f"""
<div style="background:#0d1a30;border-radius:12px;overflow:hidden;margin-top:16px;
            border:1px solid #1a2e4a;">
  <div style="display:grid;grid-template-columns:1fr 90px 1fr;
              background:#060f1c;padding:28px 20px;">
    <div style="text-align:center;">
      <div style="font-size:0.68em;color:#2a4060;font-weight:700;letter-spacing:.12em;
                  text-transform:uppercase;margin-bottom:8px;">PLAYER A</div>
      <div style="font-size:1.45em;font-weight:800;color:#dde6f5;">{player_a}</div>
      <div style="font-size:0.78em;color:#3a5070;margin:4px 0 12px;">
        Model Rank #{rank_a}</div>
      <div style="font-size:2.8em;font-weight:900;color:{win_col_a};line-height:1;">
        {prob_a:.1f}%</div>
      <div style="font-size:0.62em;color:#2a4060;text-transform:uppercase;
                  letter-spacing:.1em;margin-top:5px;">Win Probability</div>
      <div style="font-size:1.1em;font-weight:700;color:#7a90b8;margin-top:12px;">
        {odds_a_str}</div>
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;
                justify-content:center;gap:10px;">
      <div style="font-size:1.1em;font-weight:900;color:#1a3050;">VS</div>
      <div style="font-size:0.58em;color:#2a4060;text-align:center;
                  text-transform:uppercase;letter-spacing:.07em;line-height:1.4;">
        {conf_txt}</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:0.68em;color:#2a4060;font-weight:700;letter-spacing:.12em;
                  text-transform:uppercase;margin-bottom:8px;">PLAYER B</div>
      <div style="font-size:1.45em;font-weight:800;color:#dde6f5;">{player_b}</div>
      <div style="font-size:0.78em;color:#3a5070;margin:4px 0 12px;">
        Model Rank #{rank_b}</div>
      <div style="font-size:2.8em;font-weight:900;color:{win_col_b};line-height:1;">
        {prob_b:.1f}%</div>
      <div style="font-size:0.62em;color:#2a4060;text-transform:uppercase;
                  letter-spacing:.1em;margin-top:5px;">Win Probability</div>
      <div style="font-size:1.1em;font-weight:700;color:#7a90b8;margin-top:12px;">
        {odds_b_str}</div>
    </div>
  </div>
  <div style="background:#040a14;padding:9px 20px;text-align:center;
              border-top:1px solid #0e1c2e;border-bottom:2px solid #0e1c2e;">
    <span style="font-size:0.68em;color:#2a4060;text-transform:uppercase;
                 letter-spacing:.08em;">Model Verdict · </span>
    <span style="font-size:0.88em;font-weight:700;color:{verdict_col};">
      {verdict_name}</span>
    <span style="font-size:0.72em;color:#3a5070;"> · {verdict_diff}</span>
  </div>
  {rows}
</div>
""", unsafe_allow_html=True)

                elif player_a == player_b:
                    st.warning("Please select two different players")


            # =================================================================
            # TAB 4: PARLAY BUILDER
            # =================================================================
            with props_tab4:
                st.markdown("### 🎲 Parlay Builder")
                st.caption("Combine multiple props into a parlay")

                st.markdown("#### 🧾 DraftKings Preset Cards")
                if dk_content_cards_df.empty:
                    st.caption("No preset cards found in latest DraftKings payloads.")
                else:
                    cards_df = dk_content_cards_df.copy()
                    cards_df["odds_american"] = pd.to_numeric(cards_df.get("odds_american"), errors="coerce")
                    cards_df["selection_count"] = pd.to_numeric(cards_df.get("selection_count"), errors="coerce")
                    cards_df["bet_count"] = pd.to_numeric(cards_df.get("bet_count"), errors="coerce")
                    scored_cards_df, scored_legs_df = _score_dk_content_cards(cards_df, preds_df)

                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Cards", int(len(cards_df)))
                    with m2:
                        priced_count = int((scored_cards_df["status"] == "priced").sum()) if not scored_cards_df.empty else 0
                        st.metric("Fully Priced", priced_count)
                    with m3:
                        best_edge = pd.to_numeric(scored_cards_df.get("edge_pts"), errors="coerce").max() if not scored_cards_df.empty else np.nan
                        st.metric("Best Edge", f"{best_edge:+.1f} pts" if pd.notna(best_edge) else "—")
                    with m4:
                        best_ev = pd.to_numeric(scored_cards_df.get("ev_per_1"), errors="coerce").max() if not scored_cards_df.empty else np.nan
                        st.metric("Best EV", f"{best_ev*100:+.1f}%" if pd.notna(best_ev) else "—")

                    if scored_cards_df.empty:
                        st.info("Cards loaded, but none could be priced against current model outputs.")
                    else:
                        f1, f2, f3 = st.columns([1.2, 1, 1])
                        with f1:
                            min_conf = st.slider("Min confidence", 0.0, 1.0, 0.6, 0.05, key="card_min_conf")
                        with f2:
                            include_partial = st.checkbox("Include partial cards", value=True, key="card_include_partial")
                        with f3:
                            top_n_cards = st.slider("Top cards", 3, 20, 8, 1, key="card_top_n")

                        view_df = scored_cards_df.copy()
                        view_df = view_df[view_df["confidence"] >= min_conf]
                        if not include_partial:
                            view_df = view_df[view_df["status"] == "priced"]

                        view_df = view_df.sort_values(["edge_pts", "ev_per_1"], ascending=[False, False], na_position="last")
                        view_df = view_df.head(top_n_cards).copy()

                        if view_df.empty:
                            st.caption("No cards meet current filter thresholds.")
                        else:
                            rec_df = pd.DataFrame({
                                "Title": view_df.get("title", ""),
                                "Odds": view_df.get("odds_american").apply(_format_american_odds),
                                "Legs": view_df.get("selection_count", 0).fillna(0).astype(int),
                                "Priced": view_df.get("priced_legs", 0).fillna(0).astype(int),
                                "Status": view_df.get("status", ""),
                                "Model %": (pd.to_numeric(view_df.get("model_prob"), errors="coerce") * 100).round(2),
                                "Book %": (pd.to_numeric(view_df.get("book_prob"), errors="coerce") * 100).round(2),
                                "Edge (pts)": pd.to_numeric(view_df.get("edge_pts"), errors="coerce").round(2),
                                "EV %": (pd.to_numeric(view_df.get("ev_per_1"), errors="coerce") * 100).round(2),
                                "Confidence": pd.to_numeric(view_df.get("confidence"), errors="coerce").round(2),
                            })
                            st.dataframe(rec_df, hide_index=True, use_container_width=True, height=280)

                            selected_title = st.selectbox(
                                "Card Details",
                                options=view_df["title"].fillna("").astype(str).tolist(),
                                key="card_detail_title",
                            )
                            sel_row = view_df[view_df["title"].fillna("").astype(str) == selected_title].head(1)
                            if not sel_row.empty:
                                sel_row = sel_row.iloc[0]
                                st.caption(
                                    f"Selected: {_format_american_odds(sel_row.get('odds_american'))} • "
                                    f"Edge {pd.to_numeric(sel_row.get('edge_pts'), errors='coerce'):+.2f} pts • "
                                    f"EV {(pd.to_numeric(sel_row.get('ev_per_1'), errors='coerce') * 100):+.1f}%"
                                )
                                details = scored_legs_df[scored_legs_df["title"].fillna("").astype(str) == selected_title].copy()
                                if not details.empty:
                                    details["model_prob_pct"] = (pd.to_numeric(details.get("model_prob"), errors="coerce") * 100).round(2)
                                    details_display = details[["leg_label", "market", "player_name", "priced", "model_prob_pct", "note"]].copy()
                                    details_display.columns = ["Leg", "Market", "Player", "Priced", "Model %", "Note"]
                                    st.dataframe(details_display, hide_index=True, use_container_width=True, height=220)

                            if st.button("📝 Log Card Recommendations", key="log_card_recs"):
                                log_path = append_dk_card_recommendation_log(view_df, tournament_id=prop_tournament_id)
                                if log_path:
                                    st.success(f"Logged card recommendations → {log_path}")
                                else:
                                    st.warning("No card recommendations to log.")

                    with st.expander("Raw Card Feed", expanded=False):
                        preview_df = pd.DataFrame({
                            "Title": cards_df.get("title", ""),
                            "Subtitle": cards_df.get("subtitle", ""),
                            "Odds": cards_df["odds_american"].apply(_format_american_odds),
                            "Legs": cards_df["selection_count"].fillna(0).astype(int),
                            "Bets": cards_df["bet_count"].fillna(0).astype(int),
                            "Ends": cards_df.get("end_date", ""),
                        })
                        st.dataframe(preview_df, hide_index=True, use_container_width=True, height=220)
                    if dk_content_cards_file:
                        st.caption(f"Preset cards source: {dk_content_cards_file.name}")

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. Parlays are no longer active.")

                # Contender filter for late rounds
                parlay_contenders_only = st.checkbox(
                    "Show contenders only",
                    value=(tournament_round >= 3),
                    key="parlay_contenders"
                )
                parlay_df = preds_df.copy()
                if parlay_contenders_only and live_contenders:
                    parlay_df = parlay_df[parlay_df["player_name"].apply(is_contender)]
                    st.caption(f"Showing {len(parlay_df)} contenders (within {5 if tournament_round == 4 else 7} shots of lead)")

                st.markdown("---")

                # Custom parlay builder
                st.markdown("#### 🔧 Build Custom Parlay")

                # Initialize session state for parlay legs
                if "parlay_legs" not in st.session_state:
                    st.session_state.parlay_legs = []

                # Add leg form
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    leg_player = st.selectbox("Player:", parlay_df["player_name"].tolist()[:30], key="parlay_player")
                with col2:
                    leg_type = st.selectbox("Prop:", ["Top 5", "Top 10", "Top 20", "Make Cut"], key="parlay_type")
                with col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_leg = st.button("Add Leg", type="primary")

                if add_leg and leg_player:
                    # Get probability for this prop
                    player_data = preds_df[preds_df["player_name"] == leg_player].iloc[0].to_dict()
                    prop_map = {
                        "Top 5": player_data.get("top5_prob", 0.15),
                        "Top 10": player_data.get("top10_prob", 0.25),
                        "Top 20": player_data.get("top20_prob", 0.40),
                        "Make Cut": min(0.85, (player_data.get("top20_prob", 0.40) or 0.40) * 1.5 + 0.2)
                    }
                    prob = prop_map.get(leg_type, 0.5) or 0.5

                    new_leg = ParlayLeg(
                        description=f"{leg_player} {leg_type}",
                        probability=prob,
                        odds=prob_to_american(prob)
                    )
                    st.session_state.parlay_legs.append(new_leg)
                    st.rerun()

                # Display current parlay
                if st.session_state.parlay_legs:
                    st.markdown("**Current Parlay:**")
                    for i, leg in enumerate(st.session_state.parlay_legs):
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.markdown(f"{i+1}. {leg.description}")
                        with col2:
                            st.caption(format_american_odds(leg.odds))
                        with col3:
                            if st.button("❌", key=f"remove_{i}"):
                                st.session_state.parlay_legs.pop(i)
                                st.rerun()

                    # Calculate parlay
                    if len(st.session_state.parlay_legs) >= 2:
                        parlay = calculate_parlay(st.session_state.parlay_legs)
                        st.markdown("---")

                        _mp = parlay.combined_prob  # model hit probability

                        # Convert American odds to implied probability
                        def _a2p(o):
                            try:
                                o = float(o)
                                return 100/(o+100) if o >= 0 else abs(o)/(abs(o)+100)
                            except Exception:
                                return None

                        # Fair odds = what this parlay would pay at true model probability
                        _fair_odds_str = format_american_odds(prob_to_american(_mp)) if _mp > 0 else "—"

                        # Optional: user enters actual sportsbook odds for comparison
                        _dk_odds_raw = st.text_input(
                            "Enter actual DraftKings parlay odds (optional):",
                            placeholder="e.g. +850",
                            key="parlay_dk_odds",
                        )
                        _dk_implied = None
                        if _dk_odds_raw.strip().lstrip("+"):
                            try:
                                _dk_implied = _a2p(float(_dk_odds_raw.strip().replace("+","")))
                            except Exception:
                                pass

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Model Hit %", f"{_mp*100:.2f}%",
                                      help="Product of individual leg model probabilities")
                        with col2:
                            st.metric("Fair Odds", _fair_odds_str,
                                      help="Break-even American odds based on model probability")
                        with col3:
                            st.metric("$10 Pays", f"${parlay.payout_per_unit:.2f}")
                        with col4:
                            if _dk_implied is not None:
                                _edge = (_mp - _dk_implied) * 100
                                _edge_col = "normal" if _edge >= 0 else "inverse"
                                st.metric("Model Edge vs DK",
                                          f"{_edge:+.1f} pp",
                                          delta=f"{'VALUE' if _edge > 0 else 'OVERPRICED'}",
                                          delta_color=_edge_col)
                            else:
                                st.metric("Avg Leg Prob",
                                          f"{(_mp ** (1/len(st.session_state.parlay_legs)))*100:.1f}%",
                                          help="Geometric mean of individual leg model probabilities")

                    # Clear button
                    if st.button("Clear Parlay"):
                        st.session_state.parlay_legs = []
                        st.rerun()
                else:
                    st.info("Add at least 2 legs to build a parlay")

            # =================================================================
            # TAB 5: EXPERT PICKS
            # =================================================================
            with props_tab5:
                render_expert_picks_section(preds_df, prop_tournament_id)


# ============================================================================
# PAGE: PREDICTIONS
# ============================================================================

elif page == "📊 Predictions":
    st.markdown("## 📊 Prediction Results")

    # ── Run Predictions ───────────────────────────────────────────────────────
    with st.expander("🔮 Run Predictions", expanded=False):
        st.caption("Generate fresh predictions for any upcoming tournament")

        _sched_path_pred = DATA_DIR / "raw" / "schedule_2026.csv"
        _pred_run_options = {}
        if _sched_path_pred.exists():
            _sched_pred = pd.read_csv(_sched_path_pred)
            _today_str  = datetime.now().strftime("%Y-%m-%d")
            # Upcoming or current tournaments only
            _upcoming = _sched_pred[_sched_pred["end_date"] >= _today_str].sort_values("start_date")
            for _, _sr in _upcoming.iterrows():
                _label = f"{_sr['tournament_name']} ({_sr['start_date'][:10]})"
                _pred_run_options[_label] = {
                    "name":   str(_sr["tournament_name"]),
                    "id":     str(_sr.get("tournament_id", "")),
                    "purse":  int(float(str(_sr.get("purse", 8500000)).replace("$", "").replace(",", ""))),
                    "type":   str(_sr.get("tournament_type", "Standard")),
                }

        _rp_col1, _rp_col2 = st.columns([3, 1])
        with _rp_col1:
            if _pred_run_options:
                _rp_selected_label = st.selectbox(
                    "Tournament", list(_pred_run_options.keys()), key="pred_run_select"
                )
                _rp_info = _pred_run_options[_rp_selected_label]
            else:
                st.info("No schedule data found. Add data/raw/schedule_2026.csv or use the Pipeline page.")
                _rp_info = None
        with _rp_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            _rp_btn = st.button("🔮 Run Predictions", type="primary",
                                use_container_width=True, key="pred_run_btn",
                                disabled=_rp_info is None)

        if _rp_btn and _rp_info:
            with st.spinner(f"Generating predictions for {_rp_info['name']}…"):
                _rp_cmd = [
                    "python3", "scripts/run_pipeline.py",
                    "--tournament", _rp_info["name"],
                    "--use-schedule", "--skip-refresh", "--calibrate", "--lineup",
                ]
                _rp_success, _rp_output = run_scraper(_rp_cmd, timeout=300)
            if _rp_success:
                st.success(f"✅ Predictions generated for {_rp_info['name']}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ Prediction run failed")
            if _rp_output:
                with st.expander("Output", expanded=not _rp_success):
                    st.code(_rp_output, language=None)

    st.markdown("---")

    prediction_files = get_prediction_files()

    if not prediction_files:
        st.warning("No prediction files found. Run predictions first!")
    else:
        # File selector
        file_options = {f.stem.replace('_predictions', '').replace('_', ' ').title(): f
                       for f in prediction_files[:10]}

        selected = st.selectbox("Select Tournament:", list(file_options.keys()))
        df = pd.read_csv(file_options[selected])

        # Summary row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Players", len(df))
        with col2:
            st.metric("Avg EV", f"${df['expected_value'].mean():,.0f}")
        with col3:
            st.metric("Max EV", f"${df['expected_value'].max():,.0f}")
        with col4:
            with_history = df['hist_times_played'].notna().sum()
            st.metric("With History", f"{with_history}/{len(df)}")

        # ── Field strength ──────────────────────────────────────────────────
        if "world_rank" in df.columns:
            _wr_all  = pd.to_numeric(df["world_rank"], errors="coerce").dropna()
            _wr_real = _wr_all[_wr_all < 400]  # exclude 500-placeholder for LIV/injured
            _avg_wr  = _wr_real.mean() if not _wr_real.empty else None
            _t10  = int((_wr_all <= 10).sum())
            _t25  = int((_wr_all <= 25).sum())
            _t50  = int((_wr_all <= 50).sum())
            # Use projected_score_vs_field for winner/cut context.
            # e.g. "Leader: -5.7 vs avg" means the top pick is projected
            # 5.7 strokes better than the average field finisher.
            _proj_winner_str = "—"
            _proj_cut_str    = "—"
            if "projected_score_vs_field" in df.columns and "score_rank" in df.columns:
                _ps_df = df[["projected_score_vs_field", "score_rank"]].copy()
                _ps_df["projected_score_vs_field"] = pd.to_numeric(_ps_df["projected_score_vs_field"], errors="coerce")
                _ps_df["score_rank"]               = pd.to_numeric(_ps_df["score_rank"],               errors="coerce")
                _ps_df = _ps_df.dropna()
                if not _ps_df.empty:
                    def _ps_fmt(v):
                        return "E" if v == 0 else (f"+{v:.1f}" if v > 0 else f"{v:.1f}")
                    _winner_row = _ps_df[_ps_df["score_rank"] == _ps_df["score_rank"].min()]
                    if not _winner_row.empty:
                        _proj_winner_str = _ps_fmt(float(_winner_row["projected_score_vs_field"].iloc[0]))
                    # Cut bubble: median projected score vs field (half above, half below)
                    _cut_approx = _ps_df["projected_score_vs_field"].median()
                    _proj_cut_str = _ps_fmt(float(_cut_approx))
            _fs1, _fs2, _fs3, _fs4, _fs5 = st.columns(5)
            _fs1.metric("Avg World Rank",  f"#{_avg_wr:.0f}" if _avg_wr else "—")
            _fs2.metric("Top-10 Players",  _t10)
            _fs3.metric("Top-25 Players",  _t25)
            _fs4.metric("Leader vs Avg",   _proj_winner_str, help="Top-ranked player's projected strokes vs field average (negative = better than field)")
            _fs5.metric("Cut vs Avg",      _proj_cut_str,    help="Median projected score vs field — players at or below this line are projected to make the cut")

        st.markdown("---")

        selected_tournament_id = _tournament_id_from_df(df)

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["🏆 Top Picks", "🎖️ Tier List", "⚔️ Head-to-Head", "💡 Value Picks"])

        with tab1:
            top_20 = df.nlargest(20, 'expected_value').copy()

            # Build 2025 earnings lookup keyed by last name (lowercase)
            _p25_path = PROJECT_ROOT / "data" / "historical" / "Fantasy_Results_2025.csv"
            _p25_lookup = {}
            if _p25_path.exists():
                def _pm_p25(v):
                    try: return float(str(v).replace("$","").replace(",","").strip())
                    except: return 0.0
                _p25df = pd.read_csv(_p25_path)
                for _, _p25r in _p25df.iterrows():
                    for _sc, _ec in [("Starter #1","Earnings"),("Starter #2","Earnings.1"),("Starter #3","Earnings.2")]:
                        _pn = str(_p25r.get(_sc,"")).strip()
                        if not _pn or _pn in ("VACANT","nan"): continue
                        _last = _pn.split(",")[0].strip().lower()
                        _earn = _pm_p25(_p25r.get(_ec, 0))
                        _p25_lookup[_last] = _p25_lookup.get(_last, 0) + _earn

            def _fmt_2025(name):
                last = str(name).split(",")[0].strip().lower()
                if last not in _p25_lookup: return "—"
                e = _p25_lookup[last]
                if e == 0: return "✓ $0"
                return f"✓ ${e/1_000:.0f}K" if e < 1_000_000 else f"✓ ${e/1_000_000:.1f}M"

            # Build LIV lookup: player_name_norm → proxy string
            _liv_preds_path = DATA_DIR / "historical" / "liv_player_profiles.csv"
            _liv_pred_lookup = {}
            if _liv_preds_path.exists():
                try:
                    _liv_pred_df = pd.read_csv(_liv_preds_path)
                    for _, _lr in _liv_pred_df.iterrows():
                        _ln = str(_lr.get("player_name", "")).strip().lower()
                        _lp = _lr.get("liv_sg_proxy")
                        _ly = _lr.get("year", "")
                        if _ln and pd.notna(_lp):
                            _liv_pred_lookup[_ln] = f"⛳ {float(_lp):+.2f} ({int(_ly)})" if _ly else f"⛳ {float(_lp):+.2f}"
                except Exception:
                    pass

            def _fmt_liv(name):
                n = str(name).strip()
                if ", " in n:
                    parts = n.split(", ", 1)
                    n = f"{parts[1]} {parts[0]}"
                return _liv_pred_lookup.get(n.lower(), "—")

            # Build KFT lookup: player_name_norm → proxy string
            _kft_preds_path = DATA_DIR / "historical" / "kft_player_profiles.csv"
            _kft_pred_lookup = {}
            if _kft_preds_path.exists():
                try:
                    _kft_pred_df = pd.read_csv(_kft_preds_path)
                    for _, _kr in _kft_pred_df.iterrows():
                        _kn = str(_kr.get("player_name", "")).strip().lower()
                        _proxy = _kr.get("kft_sg_proxy")
                        _yr = _kr.get("kft_year", "")
                        if _kn and pd.notna(_proxy):
                            _kft_pred_lookup[_kn] = f"🎓 {float(_proxy):+.2f} ({int(_yr)})" if _yr else f"🎓 {float(_proxy):+.2f}"
                except Exception:
                    pass

            def _fmt_kft(name):
                n = str(name).strip()
                if ", " in n:
                    parts = n.split(", ", 1)
                    n = f"{parts[1]} {parts[0]}"
                return _kft_pred_lookup.get(n.lower(), "—")

            _base_cols   = ['player_name', 'expected_value', 'win_prob', 'top5_prob',
                            'top10_prob', 'sg_total', 'hist_times_played']
            # Use projected_score_vs_field (strokes vs field average) rather than
            # projected_score (absolute to-par). The model predicts a conditional mean
            # so absolute scores are compressed — but the relative ranking is accurate.
            # "vs Avg" reads as: -5.7 = projected 5.7 strokes better than avg finisher.
            # proj_ceiling / proj_floor: Q10/Q90 quantile models — realistic upside/downside range.
            _extra_cols  = [c for c in ['projected_score_vs_field', 'proj_ceiling', 'proj_floor', 'model_vs_vegas_edge'] if c in df.columns]
            display_cols = _base_cols + _extra_cols

            display_df = top_20[display_cols].copy()
            display_df['2025'] = top_20['player_name'].apply(_fmt_2025)
            display_df['kft'] = top_20['player_name'].apply(_fmt_kft)
            display_df['liv'] = top_20['player_name'].apply(_fmt_liv)
            display_df['expected_value'] = display_df['expected_value'].apply(lambda x: f"${x:,.0f}")
            display_df['win_prob'] = (display_df['win_prob'] * 100).round(2)
            display_df['top5_prob'] = (display_df['top5_prob'] * 100).round(1)
            display_df['top10_prob'] = (display_df['top10_prob'] * 100).round(1)
            display_df['sg_total'] = display_df['sg_total'].round(3)
            display_df['hist_times_played'] = display_df['hist_times_played'].fillna(0).astype(int)

            def _fmt_vsf(v):
                try:
                    n = float(v)
                    return "E" if n == 0 else (f"+{n:.1f}" if n > 0 else f"{n:.1f}")
                except (TypeError, ValueError):
                    return "—"

            if 'projected_score_vs_field' in display_df.columns:
                display_df['projected_score_vs_field'] = display_df['projected_score_vs_field'].apply(_fmt_vsf)
            if 'proj_ceiling' in display_df.columns:
                display_df['proj_ceiling'] = display_df['proj_ceiling'].apply(_fmt_vsf)
            if 'proj_floor' in display_df.columns:
                display_df['proj_floor'] = display_df['proj_floor'].apply(_fmt_vsf)
            if 'model_vs_vegas_edge' in display_df.columns:
                display_df['model_vs_vegas_edge'] = display_df['model_vs_vegas_edge'].round(1)

            _col_rename = {
                'player_name': 'Player', 'expected_value': 'Expected Value',
                'win_prob': 'Win %', 'top5_prob': 'Top-5 %', 'top10_prob': 'Top-10 %',
                'sg_total': 'SG Total', 'hist_times_played': 'Course Plays',
                'projected_score_vs_field': 'vs Avg', 'proj_ceiling': 'Ceiling',
                'proj_floor': 'Floor', 'model_vs_vegas_edge': 'Edge %',
            }
            display_df.columns = (
                [_col_rename.get(c, c) for c in display_cols] + ['2025 Earnings', 'KFT History', 'LIV History']
            )

            st.dataframe(display_df, hide_index=True, use_container_width=True)
            st.caption("**vs Avg** — mean projected score vs field (negative = better). **Ceiling** — best 10% of weeks (Q10). **Floor** — worst 10% of weeks (Q90). All vs field average. **2025 Earnings** — prize money in your 2025 lineup.")

            st.markdown("#### 🔎 Why This Pick")
            why_cols = st.columns([2.2, 1.0])
            with why_cols[0]:
                selected_player = st.selectbox(
                    "Choose player",
                    options=top_20["player_name"].tolist(),
                    key=f"why_pick_player_{selected_tournament_id or selected}",
                )
            with why_cols[1]:
                st.markdown("<br>", unsafe_allow_html=True)
                explain_click = st.button(
                    "Explain Pick",
                    use_container_width=True,
                    key=f"why_pick_btn_{selected_tournament_id or selected}",
                )

            why_key = f"why_pick_text_{selected_tournament_id or selected}"
            if explain_click and selected_player:
                selected_row = top_20[top_20["player_name"] == selected_player].iloc[0]
                st.session_state[why_key] = build_player_pick_reason_text(selected_row)
            if why_key in st.session_state:
                st.markdown(st.session_state[why_key])

        with tab2:
            render_tier_list(df)

        with tab3:
            st.markdown("""
            <div style="background: #0d1a30; border: 1px solid #1e3a5f; border-left: 4px solid #00c44f;
                        padding: 20px 24px; border-radius: 10px; margin: 20px 0;">
                <div style="font-size: 1.1em; font-weight: 600; color: #dde6f5; margin-bottom: 6px;">
                    ⚔️ Head-to-Head has moved
                </div>
                <div style="color: #8ba0b8; font-size: 0.95em;">
                    The full H2H comparison tool — with SG breakdown, recent form sparklines, and
                    a 15-row stats matchup — lives in the <strong style="color:#00c44f;">Players</strong>
                    page under the <strong style="color:#00c44f;">Head-to-Head</strong> tab.
                </div>
            </div>
            """, unsafe_allow_html=True)

        with tab4:
            st.caption("Players where the model probability is meaningfully higher than the market's implied probability — sorted by edge.")
            if "model_vs_vegas_edge" not in df.columns:
                st.info("Edge data not available. Run odds refresh and predictions to generate edge values.")
            else:
                _val_df = df.copy()
                _val_df["model_vs_vegas_edge"] = pd.to_numeric(_val_df["model_vs_vegas_edge"], errors="coerce")
                _val_df = _val_df[_val_df["model_vs_vegas_edge"].notna()]
                _val_df = _val_df.sort_values("model_vs_vegas_edge", ascending=False)

                _min_edge = st.slider("Minimum edge (%)", min_value=0, max_value=20, value=5, step=1, key="val_min_edge")
                _val_df = _val_df[_val_df["model_vs_vegas_edge"] >= _min_edge]

                if _val_df.empty:
                    st.info(f"No players with edge ≥ {_min_edge}%. Try lowering the threshold.")
                else:
                    _val_show_cols = ["player_name", "win_prob", "top10_prob", "model_vs_vegas_edge", "world_rank", "sg_total"]
                    for _qc in ["projected_score_vs_field", "proj_ceiling", "proj_floor"]:
                        if _qc in _val_df.columns:
                            _val_show_cols.append(_qc)
                    if "odds_to_win" in _val_df.columns:
                        _val_show_cols.append("odds_to_win")
                    _val_show_cols = [c for c in _val_show_cols if c in _val_df.columns]
                    _val_disp = _val_df[_val_show_cols].copy()
                    _val_disp["win_prob"]   = (_val_disp["win_prob"] * 100).round(1)
                    _val_disp["top10_prob"] = (_val_disp["top10_prob"] * 100).round(1)
                    _val_disp["sg_total"]   = _val_disp["sg_total"].round(2)
                    _val_disp["model_vs_vegas_edge"] = _val_disp["model_vs_vegas_edge"].round(1)
                    for _qc in ["projected_score_vs_field", "proj_ceiling", "proj_floor"]:
                        if _qc in _val_disp.columns:
                            _val_disp[_qc] = _val_disp[_qc].apply(
                                lambda v: ("E" if float(v) == 0 else (f"+{float(v):.1f}" if float(v) > 0 else f"{float(v):.1f}"))
                                if pd.notna(v) else "—"
                            )
                    if "world_rank" in _val_disp.columns:
                        _val_disp["world_rank"] = pd.to_numeric(_val_disp["world_rank"], errors="coerce").apply(
                            lambda x: int(x) if pd.notna(x) else "—"
                        )
                    _val_rename = {
                        "player_name": "Player", "win_prob": "Win %", "top10_prob": "Top-10 %",
                        "model_vs_vegas_edge": "Edge %", "world_rank": "WR",
                        "sg_total": "SG Total", "projected_score_vs_field": "vs Avg",
                        "proj_ceiling": "Ceiling", "proj_floor": "Floor", "odds_to_win": "DK Odds",
                    }
                    _val_disp.columns = [_val_rename.get(c, c) for c in _val_show_cols]
                    st.dataframe(_val_disp, hide_index=True, use_container_width=True)
                    st.caption(f"Showing {len(_val_disp)} players with model edge ≥ {_min_edge}%. **Ceiling** = best 10% of weeks (Q10), **Floor** = worst 10% (Q90), all vs field avg.")

        # ── Model Calibration ────────────────────────────────────────────────
        _cal_path = OUTPUTS_DIR / "calibration_data.json"
        if _cal_path.exists():
            with st.expander("📐 Model Calibration", expanded=False):
                try:
                    _cal = json.loads(_cal_path.read_text())
                    _cal_models = _cal.get("models", {})
                    st.caption(f"Generated: {_cal.get('generated_at', '—')[:16]}  ·  Train: {_cal.get('n_train', '—'):,} rows  ·  Test: {_cal.get('n_test', '—'):,} rows")

                    _cm_cols = st.columns(len(_cal_models))
                    for _ci, (_mk, _mv) in enumerate(_cal_models.items()):
                        with _cm_cols[_ci]:
                            _auc   = float(_mv.get("auc", 0))
                            _brier = float(_mv.get("brier", 0))
                            _ratio = float(_mv.get("cal_ratio", 1))
                            _name  = _mv.get("display_name", _mk)
                            # cal_ratio: 1.0 = perfect, >1 = overconfident, <1 = underconfident
                            _ratio_color = "#2ecc71" if 0.85 <= _ratio <= 1.15 else ("#f4c430" if 0.7 <= _ratio <= 1.3 else "#e74c3c")
                            _ratio_label = "Well calibrated" if 0.85 <= _ratio <= 1.15 else ("Overconfident" if _ratio > 1 else "Underconfident")
                            st.markdown(f"**{_name}**")
                            st.metric("AUC",   f"{_auc:.3f}",   help="1.0 = perfect ranking, 0.5 = random")
                            st.metric("Brier",  f"{_brier:.4f}", help="Lower = better; 0 = perfect")
                            st.markdown(
                                f"<span style='color:{_ratio_color};font-size:0.85em'>"
                                f"Cal ratio: {_ratio:.2f} — {_ratio_label}</span>",
                                unsafe_allow_html=True,
                            )

                    # Feature importance top 10 (list of dicts with feature + *_importance keys)
                    _fi = _cal.get("feature_importance", [])
                    if _fi and isinstance(_fi, list):
                        st.markdown("**Top Features (Win Model)**")
                        _fi_sorted = sorted(_fi, key=lambda x: x.get("win_importance", 0), reverse=True)[:10]
                        _fi_df = pd.DataFrame([
                            {"Feature": r["feature"], "Win %": round(r.get("win_importance", 0) * 100, 1),
                             "Avg %": round(r.get("avg_importance", 0) * 100, 1)}
                            for r in _fi_sorted
                        ])
                        st.dataframe(_fi_df, hide_index=True, use_container_width=True, height=250)
                except Exception as _e:
                    st.warning(f"Could not load calibration data: {_e}")


# ============================================================================
# PAGE: LIVE
# ============================================================================

elif page == "🔴 Live":

    # ── AUTO-REFRESH while a round is in progress ──────────────────────────
    _LIVE_AUTO_SECS = 300  # re-read files every 5 minutes
    if "live_auto_refresh_at" not in st.session_state:
        st.session_state.live_auto_refresh_at = time.time() + _LIVE_AUTO_SECS
    _secs_left = int(st.session_state.live_auto_refresh_at - time.time())
    if _secs_left <= 0:
        st.session_state.live_auto_refresh_at = time.time() + _LIVE_AUTO_SECS
        st.rerun()
    _min_left, _sec_left = divmod(max(_secs_left, 0), 60)
    st.caption(f"Auto-refresh in {_min_left}m {_sec_left:02d}s · background scraper updates data every 10m during active rounds")

    # ── YOUR PICKS THIS WEEK (live positions) ─────────────────────────────
    st.markdown("### 🏌️  Your Picks — Live Positions")

    # Load current week's picks from season log
    _picks_this_week = []
    _log_path = OUTPUTS_DIR / "season_log.csv"
    _engine_live = load_scoring_engine(_scoring_engine_cache_key())
    _current_week_num = None

    if _engine_live:
        _tw = _engine_live.get_current_week_tournament()
        if _tw and _tw in _engine_live.tournaments:
            _current_week_num = _engine_live.tournaments[_tw].week

    if _log_path.exists() and _current_week_num:
        try:
            _log = pd.read_csv(_log_path)
            _wrow = _log[_log["week"] == _current_week_num]
            if not _wrow.empty:
                _r = _wrow.iloc[0]
                for _pc in ["pick1", "pick2", "pick3"]:
                    if _pc in _r and pd.notna(_r[_pc]) and str(_r[_pc]).strip():
                        _picks_this_week.append(str(_r[_pc]).strip())
        except Exception:
            pass

    # Find the most recently modified leaderboard file in data/live/
    _live_dir = DATA_DIR / "live"
    _lb_df = pd.DataFrame()

    if _live_dir.exists():
        _lb_files = sorted(
            _live_dir.glob("leaderboard_*.csv"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if _lb_files:
            _lb_df = pd.read_csv(_lb_files[0])
            # Show which file we loaded + when
            _lb_age = datetime.fromtimestamp(_lb_files[0].stat().st_mtime).strftime("%b %d %H:%M")
            st.caption(f"Leaderboard: `{_lb_files[0].name}` · Updated {_lb_age}")

    # Load cut projection + current round from accompanying meta JSON
    _cut_proj_score = None
    _current_round_live = 1
    if _live_dir.exists():
        _meta_candidates = sorted(
            _live_dir.glob("leaderboard_*_meta.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if _meta_candidates:
            try:
                with open(_meta_candidates[0]) as _mf:
                    _live_meta = json.load(_mf)
                _cut_proj_score = _live_meta.get("cut_projection", {}).get("projected_cut_score")
                _current_round_live = int(_live_meta.get("current_round", 1))
            except Exception:
                pass

    if _picks_this_week and not _lb_df.empty:
        # Normalize names for matching — leaderboard uses "First Last",
        # season_log stores what you typed ("Matsuyama" or "Hideki Matsuyama")
        def _name_match(lb_name, pick_name):
            """Fuzzy name match: check if pick appears anywhere in leaderboard name."""
            return (pick_name.lower() in lb_name.lower() or
                    lb_name.lower() in pick_name.lower())

        _pick_rows = []
        for _pick in _picks_this_week:
            _match = _lb_df[_lb_df["player_name"].apply(
                lambda n: _name_match(str(n), _pick)
            )]
            if not _match.empty:
                _pick_rows.append(_match.iloc[0])

        if _pick_rows:
            _pc_cols = st.columns(len(_pick_rows))
            for _col, _row in zip(_pc_cols, _pick_rows):
                _pos        = _row.get("position", "—")
                _pname      = _row.get("player_name", "—")
                _total      = _row.get("total", "E")
                _thru       = str(_row.get("thru", "—"))
                _r1         = int(_row["R1"]) if pd.notna(_row.get("R1")) else "—"
                _r2         = int(_row["R2"]) if pd.notna(_row.get("R2")) else "—"
                _r3         = int(_row["R3"]) if pd.notna(_row.get("R3")) else "—"
                _r4         = int(_row["R4"]) if pd.notna(_row.get("R4")) else "—"
                _status     = str(_row.get("status", "")).lower()
                _cut_color  = "#e53935" if _status == "cut" else "#00c44f"

                # Position change (numeric ±N, from API movementAmount)
                _pos_change = 0
                try:
                    _pc_raw = _row.get("position_change", 0)
                    if pd.notna(_pc_raw):
                        _pos_change = int(_pc_raw)
                except Exception:
                    pass
                if _pos_change > 0:
                    _move_icon = f"🔼 +{_pos_change}"
                    _move_color = "#00c44f"
                elif _pos_change < 0:
                    _move_icon = f"🔽 {_pos_change}"
                    _move_color = "#e53935"
                else:
                    _move_icon = "➡️"
                    _move_color = "#4a6080"

                # Cut status badge (rounds 1-2 only, when cut projection available)
                _cut_badge_html = ""
                if _cut_proj_score is not None and _current_round_live <= 2 and _status != "cut":
                    try:
                        _total_num = float(_row.get("total_numeric", 0) or 0)
                        _gap = _total_num - float(_cut_proj_score)
                        if _gap <= -2:
                            _badge_color = "#00c44f"
                            _badge_label = f"SAFE ({int(-_gap):+d})"
                        elif _gap <= 1:
                            _badge_color = "#ffa726"
                            _badge_label = "BUBBLE"
                        else:
                            _badge_color = "#e53935"
                            _badge_label = f"AT RISK (+{int(_gap)})"
                        _cut_badge_html = (
                            f'<div style="margin:6px auto 0; display:inline-block; '
                            f'background:{_badge_color}22; border:1px solid {_badge_color}; '
                            f'border-radius:6px; padding:2px 8px; font-size:10px; '
                            f'color:{_badge_color}; font-weight:700; letter-spacing:1px;">'
                            f'{_badge_label}</div>'
                        )
                    except Exception:
                        pass

                # Score color: green under par, red over, white even
                def _sc(total):
                    s = str(total).strip()
                    if s.startswith("-"): return "#00c44f"
                    if s in ("E", "0"):   return "#dde6f5"
                    return "#e53935"

                # Round score color relative to par 72
                def _rc(val):
                    if val == "—": return "#3a5270"
                    try:
                        v = int(val)
                        if v <= 69:   return "#00c44f"
                        elif v <= 71: return "#6ddb9a"
                        elif v == 72: return "#dde6f5"
                        elif v <= 74: return "#ffa726"
                        else:         return "#e53935"
                    except Exception:
                        return "#3a5270"

                _score_color  = _sc(_total)
                _border_color = _score_color if _status != "cut" else "#e53935"

                _move_str = (
                    f"▲ +{_pos_change}" if _pos_change > 0
                    else (f"▼ {_pos_change}" if _pos_change < 0 else "—")
                )

                # Build round score cells
                _rnd_cells = "".join(
                    f'<div><div style="font-size:16px;font-weight:800;color:{_rc(v)};">{v}</div>'
                    f'<div style="font-size:10px;color:#3a5270;font-weight:600;letter-spacing:.5px;">R{i}</div></div>'
                    for i, v in enumerate([_r1, _r2, _r3, _r4], 1)
                )

                with _col:
                    st.markdown(
                        f"""
<div style="background:#0b1929;border:1px solid #1a3050;
            border-top:3px solid {_border_color};border-radius:12px;
            padding:18px 16px 14px;box-sizing:border-box;">

  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <span style="background:#132840;color:#dde6f5;font-size:13px;font-weight:800;
                 padding:3px 11px;border-radius:20px;">{_pos}</span>
    <span style="font-size:12px;font-weight:700;color:{_move_color};">{_move_str}</span>
  </div>

  <div style="font-size:15px;font-weight:700;color:#e8eef8;margin-bottom:10px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_pname}</div>

  <div style="margin-bottom:8px;">
    <span style="font-size:40px;font-weight:900;color:{_score_color};line-height:1;">{_total}</span>
    <span style="font-size:12px;color:#5a7a9a;margin-left:8px;">Thru {_thru}</span>
  </div>

  {_cut_badge_html}

  <div style="border-top:1px solid #1a3050;margin-top:12px;padding-top:10px;
              display:grid;grid-template-columns:repeat(4,1fr);gap:4px;text-align:center;">
    {_rnd_cells}
  </div>
</div>""",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Picks not found in leaderboard yet — try refreshing live data first.")
    elif not _picks_this_week:
        st.info("No picks recorded for this week yet. Add picks in My Picks → Add Picks.")
    elif _lb_df.empty:
        st.info("No live leaderboard data found. Run the leaderboard scraper from ⚙️  Pipeline.")

    st.markdown("---")


    
    
    
    st.markdown("## 🔴 Live Tournament Tracking")
    
    
    
    
    
    

    # Load leaderboard data first
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(LIVE_DIR.glob("leaderboard_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)

    # Tournament selector and refresh
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        if existing:
            file_options = {}
            for f in existing[:10]:
                meta_path = leaderboard_meta_path(f)
                name = f.stem.replace("leaderboard_", "").upper()
                meta = load_leaderboard_meta(meta_path)
                if meta:
                    name = meta.get("tournament_name", name)
                file_options[name] = f
            selected = st.selectbox("Tournament:", list(file_options.keys()), key="live_select")
        else:
            selected = None
            st.info("No leaderboard data. Fetch or upload below.")

    with col2:
        fetch_id = st.text_input("Fetch Tournament ID:", placeholder="R2026005", key="fetch_id")

    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            with st.spinner("Fetching..."):
                tid = fetch_id if fetch_id else None
                df, meta, error = fetch_live_leaderboard(tid)
                if not error and df is not None:
                    st.success("Updated!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(error or "Failed to fetch")

    # Load selected data
    live_df = None
    live_meta = {}
    if selected and existing:
        live_df = pd.read_csv(file_options[selected])
        meta_path = leaderboard_meta_path(file_options[selected])
        live_meta = load_leaderboard_meta(meta_path)

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Leaderboard",
        "🎯 vs Predictions",
        "💰 vs Market Odds",
        "🏆 My Lineup"
    ])

    with tab1:
        if live_df is not None:
            render_live_leaderboard(live_df, live_meta, my_picks=_picks_this_week)
        else:
            st.info("Select a tournament or fetch live data to view leaderboard")

    with tab2:
        if live_df is not None:
            render_live_vs_predictions(live_df, live_meta)
        else:
            st.info("Load leaderboard data first")

    with tab3:
        if live_df is not None:

            # ── ODDS MOVEMENT CHART ───────────────────────────────────────────
            # Each time the scraper runs, it saves a snapshot of every player's
            # current odds to data/odds/snapshots/odds_snapshot_YYYYMMDD_HHMM.csv
            # This section loads all those snapshots and charts how odds moved.
            #
            # HOW TO READ THE CHART:
            #   Y-axis = American odds (e.g., 500 means +500)
            #   FALLING line = odds shortening (money coming in, market likes this player)
            #   RISING line  = odds drifting out (market betting against this player)
            st.markdown("### Odds Movement")
            st.caption("Falling line = market shortening (money in) · Rising = drifting out")

            _snap_dir = DATA_DIR / "odds" / "snapshots"
            _snap_files = sorted(_snap_dir.glob("odds_snapshot_*.csv")) if _snap_dir.exists() else []

            if len(_snap_files) >= 2:
                # Load every snapshot file and stack them into one big DataFrame
                _snaps = []
                for _sf in _snap_files:
                    try:
                        _sdf = pd.read_csv(_sf)
                        _snaps.append(_sdf)
                    except Exception:
                        pass

                if _snaps:
                    _all_snaps = pd.concat(_snaps, ignore_index=True)

                    # Parse the timestamp column so Plotly can put it on a time axis
                    _all_snaps["snapshot_at"] = pd.to_datetime(
                        _all_snaps["snapshot_at"], errors="coerce"
                    )
                    _all_snaps = _all_snaps.dropna(subset=["snapshot_at", "odds_numeric"])

                    # Only show snapshots from the last 7 days (current tournament week)
                    # Older snapshots are from last week's tournament and would clutter the chart
                    _cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
                    _all_snaps = _all_snaps[_all_snaps["snapshot_at"] >= _cutoff]

                    if not _all_snaps.empty:
                        # Find the 20 players with the best (lowest) odds at any point
                        # These are the players worth watching for movement
                        _top_players = (
                            _all_snaps.groupby("player_name")["odds_numeric"]
                            .min()
                            .nsmallest(20)
                            .index.tolist()
                        )

                        # Multiselect so the user can pick which players to show
                        # Default to top 8 — showing all 20 makes the chart unreadable
                        _sel_players = st.multiselect(
                            "Players to show:",
                            options=_top_players,
                            default=_top_players[:8],
                            key="odds_chart_players"
                        )

                        if _sel_players:
                            _chart_df = _all_snaps[_all_snaps["player_name"].isin(_sel_players)]

                            # Build a Plotly line chart
                            # One line per player, x=time, y=American odds number
                            import plotly.graph_objects as go
                            fig = go.Figure()

                            for _pname in _sel_players:
                                _pdf = _chart_df[
                                    _chart_df["player_name"] == _pname
                                ].sort_values("snapshot_at")

                                fig.add_trace(go.Scatter(
                                    x=_pdf["snapshot_at"],
                                    y=_pdf["odds_numeric"],
                                    mode="lines+markers",
                                    # Show just last name to save legend space
                                    name=_pname.split(",")[0],
                                    hovertemplate=(
                                        "%{fullData.name}<br>"
                                        "%{x|%a %H:%M}<br>"
                                        "+%{y:,.0f}<extra></extra>"
                                    )
                                ))

                            fig.update_layout(
                                template="plotly_dark",
                                plot_bgcolor="#0a1628",
                                paper_bgcolor="#0a1628",
                                height=420,
                                margin=dict(l=0, r=0, t=30, b=0),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                xaxis_title="",
                                # Higher y = longer odds = player drifting out
                                # Favorites stay near the bottom of the chart
                                yaxis=dict(
                                    title="American Odds",
                                    autorange=True,
                                    tickformat=",d",
                                    tickprefix="+",
                                ),
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            # Summary table: opening odds → current odds → change
                            st.markdown("**Opening → Current**")
                            _summary_rows = []
                            for _pname in _sel_players:
                                _pdf = _all_snaps[
                                    _all_snaps["player_name"] == _pname
                                ].sort_values("snapshot_at")
                                if len(_pdf) >= 1:
                                    _open_odds = _pdf.iloc[0]["odds_numeric"]
                                    _curr_odds = _pdf.iloc[-1]["odds_numeric"]
                                    _change    = _curr_odds - _open_odds
                                    _summary_rows.append({
                                        "Player":   _pname.split(",")[0],
                                        "Open":     f"+{int(_open_odds):,}",
                                        "Current":  f"+{int(_curr_odds):,}",
                                        # Negative change = odds shortened = GOOD (player being backed)
                                        # Positive change = odds drifted = BAD (market fading them)
                                        "Change":   f"{int(_change):+,}",
                                        "_raw":     _change,
                                    })

                            if _summary_rows:
                                _sum_df = pd.DataFrame(_summary_rows)

                                def _color_odds_change(val):
                                    """Green when odds shortened, red when drifted out."""
                                    try:
                                        n = int(str(val).replace("+", "").replace(",", ""))
                                    except ValueError:
                                        return ""
                                    if n < -500:  return "color:#00c44f; font-weight:700"
                                    if n < 0:     return "color:#4caf50"
                                    if n > 500:   return "color:#e53935; font-weight:700"
                                    if n > 0:     return "color:#ef9a9a"
                                    return ""

                                _sum_styled = (
                                    _sum_df[["Player", "Open", "Current", "Change"]]
                                    .style.map(_color_odds_change, subset=["Change"])
                                )
                                st.dataframe(
                                    _sum_styled, hide_index=True, use_container_width=True
                                )
                    else:
                        st.info("No snapshots within the last 7 days.")
            else:
                st.info(
                    f"Need at least 2 snapshots to show movement. "
                    f"Found {len(_snap_files)}. Snapshots save automatically each live refresh."
                )

            st.markdown("---")
            render_fantasy_lineup_tracker(live_df)
        else:
            st.info("Load leaderboard data first")




# =============================================================================
# PAGE: PIPELINE CONTROL
# =============================================================================
elif page == "⚙️ Pipeline":
    st.markdown("## ⚙️ Pipeline Control")
    st.caption("Smart weekly workflow - run the right scrapers at the right time")

    def normalize_file_slug(name: str) -> str:
        """Create filesystem-safe slug for generated filenames."""
        if not name:
            return "tournament"
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return slug or "tournament"

    def resolve_power_rankings_slug(t_id: str, schedule_slug: str, tournament_name: str) -> str:
        """
        Resolve a slug that exists in data/power_rankings/paths.csv.
        Priority:
        1) direct tournament_id match in paths.csv
        2) schedule slug / normalized variants if present in paths.csv
        """
        paths_file = DATA_DIR / "power_rankings" / "paths.csv"
        if not paths_file.exists():
            return ""

        try:
            paths_df = pd.read_csv(paths_file, dtype=str).fillna("")
        except Exception:
            return ""

        tid = str(t_id or "").strip().upper()
        if tid and "pga_id" in paths_df.columns:
            tid_rows = paths_df[paths_df["pga_id"].str.upper().str.strip() == tid]
            if not tid_rows.empty:
                slug_val = str(tid_rows.iloc[0].get("slug", "")).strip()
                if slug_val:
                    return slug_val

        available = set(paths_df.get("slug", pd.Series(dtype=str)).astype(str).str.strip().tolist())
        if not available:
            return ""

        candidates = []
        sched = str(schedule_slug or "").strip()
        if sched:
            candidates.extend([sched, sched.replace("-", "_"), f"{sched.replace('-', '_')}_2026"])

        hyphen_name = re.sub(r"[^a-z0-9]+", "-", str(tournament_name or "").lower()).strip("-")
        if hyphen_name:
            under_name = hyphen_name.replace("-", "_")
            candidates.extend([hyphen_name, under_name, f"{under_name}_2026"])

        for c in candidates:
            if c in available:
                return c

        return ""

    def build_tournament_page_url(t_id: str, schedule_slug: str) -> str:
        """Build PGA TOUR tournament page URL used as fallback for PR discovery."""
        tid = str(t_id or "").strip().upper()
        slug = str(schedule_slug or "").strip().strip("/")
        if not tid or not slug:
            return ""
        # Tournament IDs are RYYYYNNN; year is chars 1:5.
        year = tid[1:5] if len(tid) >= 5 and tid.startswith("R") else ""
        if not year.isdigit():
            return ""
        return f"https://www.pgatour.com/tournaments/{year}/{slug}/{tid}"

    def build_power_rankings_fragment_paths(start_date: str) -> list[str]:
        """
        Build likely PR fragment paths from tournament start date.
        Typical structure:
        /content/dam/pga-tour/fragments/tours/pga-tour/news/power-rankings/YYYY/MM/DD/pr-folder/pr-table
        """
        dt = pd.to_datetime(start_date, errors="coerce")
        if pd.isna(dt):
            return []

        # PRs are usually published on Monday of tournament week.
        monday = dt - pd.Timedelta(days=int(dt.weekday()))
        candidates = [
            monday,                           # most likely
            monday - pd.Timedelta(days=7),   # previous week fallback
            monday + pd.Timedelta(days=7),   # next week fallback
        ]

        paths = []
        for c in candidates:
            y = int(c.year)
            m = int(c.month)
            d = int(c.day)
            paths.append(
                f"/content/dam/pga-tour/fragments/tours/pga-tour/news/power-rankings/"
                f"{y:04d}/{m:02d}/{d:02d}/pr-folder/pr-table"
            )
        return list(dict.fromkeys(paths))

    def run_power_rankings_scraper(
        resolved_slug: str,
        output_slug: str,
        start_date: str,
        fallback_url: str = "",
    ) -> tuple[bool, str]:
        """
        Run PR scraper with layered fallbacks:
        1) configured slug
        2) guessed direct fragment paths (date-based)
        3) tournament page URL discovery
        """
        attempts = []

        if resolved_slug:
            ok, out = run_scraper(
                ["python3", "scripts/scrapers/fetch_power_rankings.py", "--slug", resolved_slug, "--allow-fail"],
                timeout=180,
            )
            attempts.append(f"[slug:{resolved_slug}]\n{out}")
            if ok:
                return True, "\n\n".join(attempts)

        for frag_path in build_power_rankings_fragment_paths(start_date):
            ok, out = run_scraper(
                [
                    "python3", "scripts/scrapers/fetch_power_rankings.py",
                    "--path", frag_path, "--slug", output_slug, "--allow-fail",
                ],
                timeout=180,
            )
            attempts.append(f"[path:{frag_path}]\n{out}")
            if ok:
                return True, "\n\n".join(attempts)

        if fallback_url:
            ok, out = run_scraper(
                [
                    "python3", "scripts/scrapers/fetch_power_rankings.py",
                    "--path", fallback_url, "--slug", output_slug, "--allow-fail",
                ],
                timeout=180,
            )
            attempts.append(f"[url:{fallback_url}]\n{out}")
            if ok:
                return True, "\n\n".join(attempts)

        return False, "\n\n".join(attempts) if attempts else "No power rankings candidates to try."

    # Load schedule for tournament selection
    schedule_df = pd.DataFrame()
    schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
    if schedule_path.exists():
        schedule_df = pd.read_csv(schedule_path)
        if "purse" in schedule_df.columns:
            schedule_df["purse"] = schedule_df["purse"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
            schedule_df["purse"] = pd.to_numeric(schedule_df["purse"], errors="coerce")

    # Determine current day and tournament status
    today = datetime.now()
    day_of_week = today.strftime("%A")
    today_str = today.strftime("%Y-%m-%d")

    current_tournament = None
    next_tournament = None
    last_tournament = None
    tournament_in_progress = False

    if not schedule_df.empty:
        schedule_df["start_dt"] = pd.to_datetime(schedule_df["start_date"])
        schedule_df["end_dt"] = pd.to_datetime(schedule_df["end_date"])
        today_dt = pd.to_datetime(today_str)

        # Current tournament (in progress)
        current = schedule_df[(schedule_df["start_dt"] <= today_dt) & (schedule_df["end_dt"] >= today_dt)]
        if not current.empty:
            current_tournament = current.iloc[0]
            tournament_in_progress = True

        # Next upcoming tournament
        upcoming = schedule_df[schedule_df["start_dt"] > today_dt].sort_values("start_dt")
        if not upcoming.empty:
            next_tournament = upcoming.iloc[0]

        # Last completed tournament
        past = schedule_df[schedule_df["end_dt"] < today_dt].sort_values("end_dt", ascending=False)
        if not past.empty:
            last_tournament = past.iloc[0]

    # Smart Schedule Banner
    st.markdown("### 📅 Today's Schedule")

    if day_of_week == "Monday":
        st.info("📊 **Monday** — Post-tournament day. Update rankings and record last week's results.")
        recommended_action = "monday"
    elif day_of_week == "Tuesday":
        st.info("📋 **Tuesday** — Prep day. Fetch field, betting profiles, and run initial predictions.")
        recommended_action = "tuesday"
    elif day_of_week == "Wednesday":
        st.info("🎯 **Wednesday** — Final prep. Refresh odds and finalize picks before tournament starts.")
        recommended_action = "wednesday"
    elif day_of_week in ["Thursday", "Friday", "Saturday"]:
        st.info(f"🔴 **{day_of_week}** — Tournament in progress. Fetch live leaderboard and updated odds.")
        recommended_action = "live"
    else:  # Sunday
        st.info("🏁 **Sunday** — Final round. Record results after tournament ends.")
        recommended_action = "sunday"

    # Tournament Status
    col1, col2 = st.columns(2)
    with col1:
        if tournament_in_progress and current_tournament is not None:
            st.success(f"🏌️ **In Progress:** {current_tournament['tournament_name']}")
            active_tournament = current_tournament
        elif next_tournament is not None:
            days_until = (next_tournament["start_dt"] - today_dt).days
            st.warning(f"📆 **Next:** {next_tournament['tournament_name']} ({days_until} days)")
            active_tournament = next_tournament
        else:
            active_tournament = None
            st.warning("No upcoming tournament found")

    with col2:
        if last_tournament is not None:
            st.caption(f"Last week: {last_tournament['tournament_name']}")

    # ── Tournament Override ────────────────────────────────────────────────────
    # Allow user to manually select any upcoming tournament instead of auto-detect
    _override_options = ["(auto-detect)"]
    _override_rows = {}
    if not schedule_df.empty:
        _fut = schedule_df[schedule_df["end_dt"] >= today_dt].sort_values("start_dt")
        for _, _sr in _fut.iterrows():
            _lbl = f"{_sr.get('tournament_name','')} ({_sr.get('tournament_id','')})"
            _override_options.append(_lbl)
            _override_rows[_lbl] = _sr

    _override_sel = st.selectbox(
        "Tournament override (leave auto-detect unless wrong):",
        _override_options,
        key="pipeline_tournament_override",
    )

    if _override_sel != "(auto-detect)" and _override_sel in _override_rows:
        active_tournament = _override_rows[_override_sel]

    # Get active tournament details
    if active_tournament is not None:
        tournament_id = str(active_tournament.get("tournament_id", ""))
        power_slug = str(active_tournament.get("power_slug", ""))
        selected_tournament = str(active_tournament.get("tournament_name", ""))
        active_start_date = str(active_tournament.get("start_date", ""))
        purse = active_tournament.get("purse", 0)
        tournament_type = str(active_tournament.get("tournament_type", "Standard"))

        st.caption(f"ID: {tournament_id} | Purse: ${purse:,.0f} | Type: {tournament_type}")
    else:
        tournament_id = ""
        power_slug = ""
        selected_tournament = ""
        active_start_date = ""
        purse = 0
        tournament_type = "Standard"

    # ─── Weekly Status Checklist ───────────────────────────────────────────────
    st.markdown("### 📋 This Week at a Glance")
    if tournament_id:
        import time as _time

        def _chk_file_fresh(path_str: str, hours: float = 24.0) -> str:
            p = Path(path_str)
            if not p.exists():
                return "missing"
            age_h = (_time.time() - p.stat().st_mtime) / 3600
            return "ok" if age_h <= hours else "stale"

        def _chk_any_file(path_str: str) -> str:
            return "ok" if Path(path_str).exists() else "missing"

        def _chk_season_log_has(t_id: str) -> str:
            """Check if season_log has a non-empty result for this tournament."""
            t_name = selected_tournament
            if not schedule_df.empty and t_id:
                sched_row = schedule_df[
                    schedule_df["tournament_id"].astype(str).str.upper() == t_id.upper()
                ]
                if not sched_row.empty:
                    t_name = str(sched_row.iloc[0].get("tournament_name", selected_tournament))
            slog = OUTPUTS_DIR / "season_log.csv"
            if not slog.exists() or not t_name:
                return "missing"
            try:
                sdf = pd.read_csv(slog, dtype=str)
                sdf = sdf[sdf["tournament"].str.strip().str.lower() == t_name.strip().lower()]
                if sdf.empty:
                    return "missing"
                for col in ["result1", "result2", "result3"]:
                    if col in sdf.columns:
                        vals = sdf[col].dropna()
                        if not vals.empty and (vals.str.strip() != "").any():
                            return "ok"
                return "missing"
            except Exception:
                return "missing"

        bp_dir = DATA_DIR / "betting_profiles"
        bp_state = (
            "ok"
            if (bp_dir / f"betting_profiles_{tournament_id}.csv").exists()
            or (bp_dir / f"articles_{tournament_id}.csv").exists()
            else "missing"
        )

        _wk_checks = [
            ("Field",       _chk_any_file(str(DATA_DIR / "fields" / f"field_{tournament_id}.csv"))),
            ("Predictions", _chk_file_fresh(str(OUTPUTS_DIR / "latest_predictions.csv"), hours=96)),
            ("DK Odds",     _chk_any_file(str(DATA_DIR / "odds" / f"prop_lines_{tournament_id}.csv"))),
            ("Profiles",    bp_state),
            ("Results",     _chk_season_log_has(tournament_id)),
        ]
        _status_icon = {"ok": "✅", "stale": "⚠️", "missing": "❌"}
        _wk_cols = st.columns(len(_wk_checks) + 1)
        with _wk_cols[0]:
            _lbl = selected_tournament or tournament_id
            st.markdown(f"**{_lbl}**")
        for _col, (_lbl, _state) in zip(_wk_cols[1:], _wk_checks):
            with _col:
                st.markdown(f"{_status_icon[_state]} {_lbl}")
    else:
        st.caption("Select a tournament above to see weekly prep status.")



    # =========================================================================
    # SMART WORKFLOW TABS
    # =========================================================================
    workflow_tabs = st.tabs([
        "📊 Monday",
        "📋 Tuesday",
        "🎯 Wednesday",
        "🔴 Live",
        "🏁 Record Results",
        "🔧 Manual",
        "⏰ Scheduler"
    ])

    # -------------------------------------------------------------------------
    # MONDAY TAB - Post-Tournament
    # -------------------------------------------------------------------------
    with workflow_tabs[0]:
        st.markdown("### 📊 Monday — Post-Tournament Refresh")
        st.caption("Run after tournament ends to update rankings and stats")

        mon_col1, mon_col2 = st.columns([2, 1])
        with mon_col1:
            st.markdown("""
            **What this does:**
            - 🌍 Updates OWGR world rankings (changes Monday)
            - 📈 Refreshes player form stats with weekend results
            - 📊 Refreshes tournament SG stats (per-event SG feed)
            - 👥 Updates player database
            - 📜 Records historical leaderboard
            """)

        with mon_col2:
            if st.button("🚀 Run Monday Refresh", type="primary", use_container_width=True, key="mon_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("World Rankings", ["python3", "scripts/scrapers/fetch_world_rankings.py"]),
                    ("Player Database", ["python3", "scripts/scrapers/fetch_player_database.py"]),
                    ("Form Stats", ["python3", "scripts/scrapers/fetch_form_stats.py", "--year", "2026"]),
                    ("Tournament SG Stats", ["python3", "scripts/scrapers/multi_year_stats_scraper_fixed.py", "--year", "2026", "--refresh-latest", "3"]),
                ]

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    _timeout = workflow_timeout(name, 120)
                    success, output = run_scraper(cmd, timeout=_timeout)
                    results.append((name, success, output))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success, output in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")
                        if output:
                            with st.expander(f"{name} error output", expanded=False):
                                st.code(output, language=None)

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # TUESDAY TAB - Tournament Prep
    # -------------------------------------------------------------------------
    with workflow_tabs[1]:
        st.markdown("### 📋 Tuesday — Tournament Prep")
        st.caption("Run to prepare for the new tournament week")

        tues_col1, tues_col2 = st.columns([2, 1])
        with tues_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 🏌️ Fetches tournament field from PGA Tour
            - ⛳ Gets course characteristics and history
            - 📰 Fetches PGA TOUR expert picks
            - 💼 Fetches betting profiles with course history
            - 📊 Fetches power rankings
            - 🎰 Attempts DraftKings odds (info if not live yet)
            - 🎯 Generates initial predictions
            """)

        with tues_col2:
            if tournament_id:
                if st.button("🚀 Run Tuesday Prep", type="primary", use_container_width=True, key="tues_run"):
                    progress = st.progress(0)
                    status = st.empty()

                    field_path = f"data/fields/field_{tournament_id}.csv"
                    pr_slug = resolve_power_rankings_slug(tournament_id, power_slug, selected_tournament)
                    pr_fallback_url = build_tournament_page_url(tournament_id, power_slug)
                    pr_output_slug = (power_slug or selected_tournament).replace("-", "_").replace(" ", "_").lower()

                    tasks = [
                        ("Field", ["python3", "scripts/scrapers/fetch_field_from_pgatour.py",
                                   "--pga-id", tournament_id, "--name", selected_tournament,
                                   "--output", field_path, "--match-ids"]),
                        ("Course Info", ["python3", "scripts/scrapers/fetch_course_characteristics.py",
                                         "--tournament-id", tournament_id, "--profile"]),
                        ("Expert Picks", ["python3", "scripts/scrapers/fetch_expert_picks_pga.py",
                                          "--tournament-id", tournament_id]),
                        ("Betting Profiles", ["python3", "scripts/scrapers/fetch_betting_profiles.py",
                                              "--tournament-id", tournament_id, "--field", field_path]),
                        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                                      "--tournament-id", tournament_id]),
                        ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                             "--tournament-id", tournament_id,
                                             "--max-age-hours", "2",
                                             "--fetch-profile", "fast",
                                             "--no-snapshot"]),
                    ]
                    tasks.insert(2, ("Power Rankings", "__AUTO_PR__"))

                    results = []
                    for i, (name, cmd) in enumerate(tasks):
                        status.text(f"Running: {name}...")
                        if cmd == "__AUTO_PR__":
                            success, output = run_power_rankings_scraper(
                                resolved_slug=pr_slug,
                                output_slug=pr_output_slug,
                                start_date=active_start_date,
                                fallback_url=pr_fallback_url,
                            )
                        else:
                            success, output = run_scraper(cmd, timeout=workflow_timeout(name, 180))
                        results.append((name, success, output))
                        progress.progress((i + 1) / len(tasks))

                    # Run predictions
                    status.text("Generating predictions...")
                    pred_cmd = [
                        "python3", "scripts/run_pipeline.py",
                        "--tournament", selected_tournament,
                        "--pga-id", tournament_id,
                        "--field", field_path,
                        "--use-schedule", "--skip-refresh", "--calibrate", "--lineup"
                    ]
                    success, output = run_scraper(pred_cmd, timeout=workflow_timeout("Predictions", 300))
                    results.append(("Predictions", success, output))
                    progress.progress(1.0)

                    status.empty()
                    progress.empty()

                    for name, success, output in results:
                        if success:
                            st.success(f"✅ {name}")
                        elif name == "DraftKings Odds":
                            st.info("DK odds not live yet — will retry on Wednesday")
                            if output:
                                with st.expander("DraftKings Odds output", expanded=False):
                                    st.code(output, language=None)
                        else:
                            st.error(f"❌ {name}")
                            if output:
                                with st.expander(f"{name} error output", expanded=False):
                                    st.code(output, language=None)

                    st.cache_data.clear()
            else:
                st.warning("Select a tournament first")

    # -------------------------------------------------------------------------
    # WEDNESDAY TAB - Final Prep
    # -------------------------------------------------------------------------
    with workflow_tabs[2]:
        st.markdown("### 🎯 Wednesday — Final Prep")
        st.caption("Refresh odds and finalize picks before tournament starts")

        wed_col1, wed_col2 = st.columns([2, 1])
        with wed_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 🎰 Refreshes DraftKings odds (lines move daily)
            - 🏆 Refreshes PGA Tour odds
            - 📊 Updates power rankings
            - 🎯 Re-runs predictions with latest data
            """)

        with wed_col2:
            if tournament_id:
                if st.button("🚀 Run Wednesday Refresh", type="primary", use_container_width=True, key="wed_run"):
                    progress = st.progress(0)
                    status = st.empty()

                    # DK odds: check cache before fetching (odds go live ~Wednesday)
                    import time as _time_wed
                    _dk_cache = DATA_DIR / "odds" / f"prop_lines_{tournament_id}.csv"
                    _dk_cache_age_h = (
                        (_time_wed.time() - _dk_cache.stat().st_mtime) / 3600
                        if _dk_cache.exists() else None
                    )
                    _dk_cache_msg = None
                    if _dk_cache_age_h is not None and _dk_cache_age_h < 12:
                        _dk_task = None
                        _dk_cache_msg = f"DK odds cached ({_dk_cache_age_h:.1f}h ago) — skipping re-fetch"
                    else:
                        _dk_task = ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                                         "--tournament-id", tournament_id,
                                                         "--max-age-hours", "2",
                                                         "--fetch-profile", "fast",
                                                         "--no-snapshot"])

                    tasks = []
                    if _dk_task:
                        tasks.append(_dk_task)
                    tasks.append(("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                                               "--tournament-id", tournament_id]))

                    results = []
                    for i, (name, cmd) in enumerate(tasks):
                        status.text(f"Running: {name}...")
                        success, output = run_scraper(cmd, timeout=workflow_timeout(name, 120))
                        results.append((name, success, output))
                        progress.progress((i + 1) / len(tasks))

                    # Re-run predictions
                    status.text("Updating predictions...")
                    field_path = f"data/fields/field_{tournament_id}.csv"
                    pred_cmd = [
                        "python3", "scripts/run_pipeline.py",
                        "--tournament", selected_tournament,
                        "--pga-id", tournament_id,
                        "--field", field_path,
                        "--use-schedule", "--skip-refresh", "--calibrate", "--lineup"
                    ]
                    success, output = run_scraper(pred_cmd, timeout=workflow_timeout("Predictions", 300))
                    results.append(("Predictions", success, output))
                    progress.progress(1.0)

                    status.empty()
                    progress.empty()

                    if _dk_cache_msg:
                        st.info(_dk_cache_msg)

                    for name, success, output in results:
                        if success:
                            st.success(f"✅ {name}")
                        elif name == "DraftKings Odds":
                            st.warning("DK odds not live yet — try again Wednesday or Thursday")
                            if output:
                                with st.expander("DraftKings Odds output", expanded=False):
                                    st.code(output, language=None)
                        else:
                            st.error(f"❌ {name}")
                            if output:
                                with st.expander(f"{name} error output", expanded=False):
                                    st.code(output, language=None)

                    st.cache_data.clear()
            else:
                st.warning("Select a tournament first")

    # -------------------------------------------------------------------------
    # LIVE TAB - During Tournament
    # -------------------------------------------------------------------------
    with workflow_tabs[3]:
        st.markdown("### 🔴 Live — Tournament Updates")
        st.caption("Run during tournament to get live scores and odds")

        live_col1, live_col2 = st.columns([2, 1])
        with live_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 📊 Fetches live leaderboard scores
            - 🎰 Updates DraftKings live odds
            """)

        with live_col2:
            if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True, key="live_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("Live Leaderboard", ["python3", "scripts/scrapers/fetch_live_leaderboard.py"]),
                ]
                if tournament_id:
                    tasks.append(("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                                      "--tournament-id", tournament_id,
                                                      "--max-age-hours", "0.5",
                                                      "--fetch-profile", "fast",
                                                      "--no-snapshot"]))

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    success, output = run_scraper(cmd, timeout=120)
                    results.append((name, success))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # RECORD RESULTS TAB
    # -------------------------------------------------------------------------
    with workflow_tabs[4]:
        st.markdown("### 🏁 Record Results")
        st.caption("Run after tournament ends to record results and update tracking")

        rec_col1, rec_col2 = st.columns([2, 1])
        with rec_col1:
            last_tourn_name = last_tournament["tournament_name"] if last_tournament is not None else "N/A"
            st.markdown(f"""
            **Last Tournament:** {last_tourn_name}

            **What this does:**
            - 📊 Fetches final leaderboard
            - ✅ Auto-records your picks' results
            - 📈 Updates season tracking
            """)

        with rec_col2:
            if st.button("🏁 Record Results", type="primary", use_container_width=True, key="record_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("Final Leaderboard", ["python3", "scripts/scrapers/fetch_leaderboard.py"]),
                    ("Auto Record", ["python3", "scripts/planning/auto_record_results.py"]),
                ]

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    success, output = run_scraper(cmd, timeout=120)
                    results.append((name, success))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # MANUAL TAB - Individual Scrapers
    # -------------------------------------------------------------------------
    with workflow_tabs[5]:
        st.markdown("### 🔧 Manual — Individual Scrapers")
        st.caption("Run individual scrapers as needed")

        # Tournament selector for manual tab
        if not schedule_df.empty:
            manual_tournament = st.selectbox(
                "Select Tournament",
                options=schedule_df["tournament_name"].tolist(),
                index=0 if active_tournament is None else schedule_df["tournament_name"].tolist().index(selected_tournament) if selected_tournament in schedule_df["tournament_name"].tolist() else 0,
                key="manual_tournament"
            )
            manual_row = schedule_df[schedule_df["tournament_name"] == manual_tournament].iloc[0]
            manual_id = str(manual_row.get("tournament_id", ""))
            manual_slug = str(manual_row.get("power_slug", ""))
            manual_start_date = str(manual_row.get("start_date", ""))
        else:
            manual_tournament = ""
            manual_id = ""
            manual_slug = ""
            manual_start_date = ""

        power_override = st.text_input(
            "Power Rankings Path/URL Override (optional)",
            value="",
            key="manual_power_override",
            help="Paste the exact working fragment path or article URL from terminal command. "
                 "If blank, dashboard uses auto resolution.",
        ).strip()

        scraper_col1, scraper_col2, scraper_col3 = st.columns(3)

        with scraper_col1:
            st.markdown("**Core Data**")
            if st.button("🌍 World Rankings", use_container_width=True, key="m_owgr"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_world_rankings.py"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("👥 Player Database", use_container_width=True, key="m_players"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_player_database.py"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("📈 Form Stats", use_container_width=True, key="m_form"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_form_stats.py", "--year", "2026"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("📊 Tournament SG Stats", use_container_width=True, key="m_tournament_sg"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(
                        ["python3", "scripts/scrapers/multi_year_stats_scraper_fixed.py", "--year", "2026", "--refresh-latest", "3"],
                        timeout=workflow_timeout("Tournament SG Stats", 300)
                    )
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("🎓 KFT Data", use_container_width=True, key="m_kft"):
                with st.spinner("Fetching KFT stats (2022–current)…"):
                    success, output = run_scraper(["python3", "scripts/scrapers/fetch_kft_stats.py"], timeout=120)
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")
                    if output:
                        with st.expander("KFT output", expanded=not success):
                            st.code(output, language=None)

            if st.button("⛳ LIV Data", use_container_width=True, key="m_liv"):
                with st.spinner("Fetching LIV Golf stats (2023–current)…"):
                    success, output = run_scraper(["python3", "scripts/scrapers/fetch_liv_stats.py"], timeout=180)
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")
                    if output:
                        with st.expander("LIV output", expanded=not success):
                            st.code(output, language=None)

        with scraper_col2:
            st.markdown("**Tournament Data**")
            if st.button("🏌️ Field", use_container_width=True, key="m_field"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        field_path = f"data/fields/field_{manual_id}.csv"
                        success, output = run_scraper([
                            "python3", "scripts/scrapers/fetch_field_from_pgatour.py",
                            "--pga-id", manual_id, "--name", manual_tournament,
                            "--output", field_path, "--match-ids"
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Field output", expanded=not success):
                                st.code(output, language=None)
                else:
                    st.warning("Need tournament ID")

            if st.button("⛳ Course Info", use_container_width=True, key="m_course"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, output = run_scraper([
                            "python3", "scripts/scrapers/fetch_course_characteristics.py",
                            "--tournament-id", manual_id, "--profile"
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Course info output", expanded=not success):
                                st.code(output, language=None)
                else:
                    st.warning("Need tournament ID")

            if st.button("📊 Power Rankings", use_container_width=True, key="m_power"):
                resolved_slug = resolve_power_rankings_slug(manual_id, manual_slug, manual_tournament)
                fallback_url = build_tournament_page_url(manual_id, manual_slug)
                fallback_slug = (manual_slug or manual_tournament).replace("-", "_").replace(" ", "_").lower()

                if power_override:
                    cmd = [
                        "python3", "scripts/scrapers/fetch_power_rankings.py",
                        "--path", power_override, "--slug", fallback_slug, "--allow-fail"
                    ]
                else:
                    cmd = None

                if cmd is not None:
                    with st.spinner("Fetching..."):
                        success, output = run_scraper(cmd)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Power rankings output", expanded=not success):
                                st.code(output, language=None)
                else:
                    with st.spinner("Fetching..."):
                        success, output = run_power_rankings_scraper(
                            resolved_slug=resolved_slug,
                            output_slug=fallback_slug,
                            start_date=manual_start_date,
                            fallback_url=fallback_url,
                        )
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Power rankings output", expanded=not success):
                                st.code(output, language=None)

            if st.button("📰 Expert Picks", use_container_width=True, key="m_expert"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, output = run_scraper([
                            "python3", "scripts/scrapers/fetch_expert_picks_pga.py",
                            "--tournament-id", manual_id
                        ], timeout=180)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Expert picks output", expanded=not success):
                                st.code(output, language=None)
                else:
                    st.warning("Need tournament ID")

        with scraper_col3:
            st.markdown("**Odds & Betting**")
            if st.button("🎰 DraftKings Odds", use_container_width=True, key="m_dk"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_draftkings_props.py",
                            "--tournament-id", manual_id,
                            "--max-age-hours", "2",
                            "--fetch-profile", "fast",
                            "--no-snapshot",
                        ], timeout=180)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

            if st.button("🏆 PGA Tour Odds", use_container_width=True, key="m_pga"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_pga_odds.py",
                            "--tournament-id", manual_id
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

            if st.button("💼 Betting Profiles", use_container_width=True, key="m_betting"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        field_path = f"data/fields/field_{manual_id}.csv"
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_betting_profiles.py",
                            "--tournament-id", manual_id, "--field", field_path
                        ], timeout=180)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

    # -------------------------------------------------------------------------
    # SCHEDULER TAB - Automated Schedule
    # -------------------------------------------------------------------------
    with workflow_tabs[6]:
        st.markdown("### ⏰ Automated Scheduler")
        st.caption("Set up automatic data refresh on a schedule")

        st.markdown("""
        **Weekly Schedule:**

        | Day | Time | Task |
        |-----|------|------|
        | Monday | 6:00 AM | Post-tournament: OWGR, form stats, tournament SG stats, player DB |
        | Tuesday | 6:00 AM | Tournament prep: field, course info, profiles, predictions |
        | Tuesday | 6:00 PM | Odds refresh: DraftKings, PGA odds |
        | Wednesday | 6:00 AM | Final prep: odds refresh, re-run predictions |
        | Wednesday | 6:00 PM | Final odds refresh |
        | Thu-Sun | 8 AM, 2 PM, 8 PM | Live: leaderboard, live odds |
        | Sunday | 11:00 PM | Record: final results, auto-record picks |
        """)

        st.markdown("---")

        # Check scheduler status
        st.markdown("#### Scheduler Status")

        scheduler_history_path = PROJECT_ROOT / "logs" / "scheduler_history.json"

        if scheduler_history_path.exists():
            try:
                history = json.loads(scheduler_history_path.read_text())
                if history:
                    st.success(f"✅ Scheduler has run {len(history)} times")

                    # Show last 5 runs
                    st.markdown("**Recent Runs:**")
                    recent = history[-5:]
                    for entry in reversed(recent):
                        ts = entry.get("timestamp", "")[:16].replace("T", " ")
                        sched = entry.get("schedule", "")
                        success = entry.get("success_count", 0)
                        total = entry.get("total_count", 0)
                        status = "✓" if success == total else "⚠️"
                        st.caption(f"{status} {ts} — {sched}: {success}/{total} tasks")
                else:
                    st.info("No scheduler history yet")
            except:
                st.info("No scheduler history yet")
        else:
            st.info("Scheduler has not run yet")

        st.markdown("---")

        # ── Watch Log ────────────────────────────────────────────────────────
        st.markdown("#### Live Refresh Log")
        _watch_log_path = PROJECT_ROOT / "logs" / "watch.log"
        if _watch_log_path.exists():
            try:
                _watch_lines = _watch_log_path.read_text().splitlines()
                # Show last 50 lines, newest at top
                _watch_tail = _watch_lines[-50:][::-1]

                # Color-code lines: ✓ = green, ✗ = red, headers = blue, rest = grey
                _log_html_lines = []
                for _wl in _watch_tail:
                    if "✓" in _wl or "Done" in _wl or "Saved" in _wl:
                        color = "#2ecc71"
                    elif "✗" in _wl or "Failed" in _wl or "Error" in _wl:
                        color = "#e74c3c"
                    elif "LIVE REFRESH" in _wl or "Watch mode" in _wl:
                        color = "#4cb8ff"
                    elif "Sleeping" in _wl or "next check" in _wl:
                        color = "#888"
                    else:
                        color = "#ccc"
                    _escaped = _wl.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    _log_html_lines.append(
                        f"<div style='color:{color};font-size:12px;font-family:monospace;"
                        f"padding:1px 0;white-space:pre'>{_escaped}</div>"
                    )

                _log_mtime = datetime.fromtimestamp(_watch_log_path.stat().st_mtime)
                _log_age   = (datetime.now() - _log_mtime).total_seconds()
                _log_age_str = f"{int(_log_age // 60)}m ago" if _log_age >= 60 else f"{int(_log_age)}s ago"
                st.caption(f"Last updated: {_log_mtime.strftime('%H:%M:%S')} ({_log_age_str}) — showing last {len(_watch_tail)} lines")

                st.markdown(
                    f"<div style='background:#0e0e0e;border:1px solid #2a2a2a;border-radius:6px;"
                    f"padding:10px 14px;max-height:320px;overflow-y:auto'>"
                    + "".join(_log_html_lines)
                    + "</div>",
                    unsafe_allow_html=True,
                )
            except Exception as _e:
                st.warning(f"Could not read watch log: {_e}")
        else:
            st.caption("No watch log found. Start the live watcher to see refresh activity here.")

        st.markdown("---")

        # Manual run buttons
        st.markdown("#### Run Scheduled Task Now")

        sched_col1, sched_col2 = st.columns(2)

        with sched_col1:
            schedule_option = st.selectbox(
                "Select Schedule",
                options=[
                    "monday",
                    "tuesday-morning",
                    "tuesday-evening",
                    "wednesday-morning",
                    "live",
                    "record"
                ],
                format_func=lambda x: {
                    "monday": "📊 Monday - Post-Tournament",
                    "tuesday-morning": "📋 Tuesday AM - Tournament Prep",
                    "tuesday-evening": "🎰 Tuesday PM - Odds Refresh",
                    "wednesday-morning": "🎯 Wednesday AM - Final Prep",
                    "live": "🔴 Live - Tournament Updates",
                    "record": "🏁 Record - Results"
                }.get(x, x),
                key="sched_select"
            )

        with sched_col2:
            if st.button("▶️ Run Now", type="primary", use_container_width=True, key="run_sched"):
                with st.spinner(f"Running {schedule_option} schedule..."):
                    success, output = run_scraper([
                        "python3", "scripts/scheduled_refresh.py",
                        "--schedule", schedule_option
                    ], timeout=600)

                    if success:
                        st.success("✅ Schedule completed!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Schedule failed")
                        with st.expander("Details"):
                            st.code(output[:2000] if output else "No output")

        st.markdown("---")

        # Setup instructions
        st.markdown("#### Setup Automated Schedule")

        st.markdown("""
        **Option 1: macOS launchd (Recommended)**

        Run this in Terminal to install automated scheduling:
        ```bash
        cd /Users/jacklegnon/Desktop/golf_data
        ./scripts/setup_scheduler.sh install
        ```

        To check status:
        ```bash
        ./scripts/setup_scheduler.sh status
        ```

        To uninstall:
        ```bash
        ./scripts/setup_scheduler.sh uninstall
        ```

        **Option 2: Cron (Linux/macOS)**

        Add to crontab (`crontab -e`):
        ```
        # Monday 6am
        0 6 * * 1 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule monday

        # Tuesday 6am & 6pm
        0 6 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-morning
        0 18 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-evening

        # Wednesday 6am
        0 6 * * 3 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule wednesday-morning

        # Thu-Sun 8am, 2pm, 8pm
        0 8,14,20 * * 4-7 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule live

        # Sunday 11pm
        0 23 * * 0 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule record
        ```
        """)

    # Data Status Section
    st.markdown("---")
    st.markdown("### 📁 Data Status")

    def check_file_age(filepath):
        """Get file age in hours and formatted string."""
        if not filepath.exists():
            return None, "Not found"
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600
        if age_hours < 1:
            return age_hours, f"{int(age_hours * 60)} min ago"
        elif age_hours < 24:
            return age_hours, f"{age_hours:.1f} hrs ago"
        else:
            return age_hours, f"{age_hours/24:.1f} days ago"

    status_col1, status_col2, status_col3 = st.columns(3)

    with status_col1:
        st.markdown("**Core Data**")
        files = [
            ("OWGR Rankings", DATA_DIR / "rankings" / "owgr_2026.csv"),
            ("Player Database", DATA_DIR / "players" / "pga_players_2026.csv"),
            ("Form Stats", DATA_DIR / "historical" / "form_stats_2026.csv"),
            ("Tournament SG Stats", DATA_DIR / "historical" / "tournament_stats_2026.csv"),
            ("Course History", DATA_DIR / "processed" / "course_history_2026.csv"),
        ]
        for name, path in files:
            age, age_str = check_file_age(path)
            if age is None:
                st.caption(f"❌ {name}: {age_str}")
            elif age < 24:
                st.caption(f"✅ {name}: {age_str}")
            else:
                st.caption(f"⚠️ {name}: {age_str}")

    with status_col2:
        st.markdown("**Tournament Data**")
        if tournament_id:
            files = [
                ("Field", DATA_DIR / "fields" / f"field_{tournament_id}.csv"),
                ("PGA Odds", DATA_DIR / "odds" / f"pga_odds_{tournament_id}.csv"),
                ("DK Odds", DATA_DIR / "odds" / f"prop_lines_{tournament_id}.csv"),
                ("Betting Profiles", DATA_DIR / "betting_profiles" / f"betting_profiles_{tournament_id}.csv"),
            ]
            for name, path in files:
                age, age_str = check_file_age(path)
                if age is None:
                    st.caption(f"❌ {name}: {age_str}")
                elif age < 24:
                    st.caption(f"✅ {name}: {age_str}")
                else:
                    st.caption(f"⚠️ {name}: {age_str}")
        else:
            st.caption("Select a tournament to see status")

    with status_col3:
        st.markdown("**Predictions**")
        pred_files = sorted(OUTPUTS_DIR.glob("*_predictions.csv"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        if pred_files:
            for f in pred_files:
                age, age_str = check_file_age(f)
                st.caption(f"📄 {f.stem[:30]}... ({age_str})")
        else:
            st.caption("No prediction files found")
