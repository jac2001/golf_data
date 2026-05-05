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

from golf_data.scripts.analysis.track_performance import load_predictions
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



_DG_API_KEY = "299bc52db9d01131b23e9d299639"
_DG_BASE     = "https://feeds.datagolf.com"

@st.cache_data(ttl=300)
def load_dg_decompositions() -> pd.DataFrame:
    """Fetch DG player decompositions live from the API (5-min cache).

    Returns a DataFrame with one row per player. Falls back to the saved
    CSV if the API call fails.
    """
    try:
        resp = requests.get(
            f"{_DG_BASE}/preds/player-decompositions",
            params={"tour": "pga", "key": _DG_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        players     = data.get("players", [])
        event_name  = data.get("event_name", "")
        course_name = data.get("course_name", "")
        last_updated = data.get("last_updated", "")
        if not players:
            raise ValueError("Empty player list from API")
        records = []
        for p in players:
            fp = p.get("final_pred"); bp = p.get("baseline_pred")
            rec = {
                "player_name":   p.get("player_name", ""),
                "dg_id":         p.get("dg_id"),
                "age":           p.get("age"),
                "country":       p.get("country", ""),
                # Core prediction
                "baseline_pred": bp,
                "final_pred":    fp,
                "std_deviation": p.get("std_deviation"),
                "sample_size":   p.get("sample_size"),
                "course_fit_delta": round(float(fp) - float(bp), 5) if fp is not None and bp is not None else None,
                # Course history
                "course_history_adjustment":       p.get("course_history_adjustment"),
                "course_experience_adjustment":    p.get("course_experience_adjustment"),
                "total_course_history_adjustment": p.get("total_course_history_adjustment"),
                # Course fit (style)
                "driving_accuracy_adjustment":     p.get("driving_accuracy_adjustment"),
                "driving_distance_adjustment":     p.get("driving_distance_adjustment"),
                "cf_approach_comp":                p.get("cf_approach_comp"),
                "cf_short_comp":                   p.get("cf_short_comp"),
                "other_fit_adjustment":            p.get("other_fit_adjustment"),
                "total_fit_adjustment":            p.get("total_fit_adjustment"),
                # Form & skill
                "timing_adjustment":               p.get("timing_adjustment"),
                "strokes_gained_category_adjustment": p.get("strokes_gained_category_adjustment"),
                "true_sg_adjustments":             p.get("true_sg_adjustments"),
                # Other
                "age_adjustment":                  p.get("age_adjustment"),
                "country_adjustment":              p.get("country_adjustment"),
                # Metadata
                "event_name":    event_name,
                "course_name":   course_name,
                "last_updated":  last_updated,
            }
            records.append(rec)
        df = pd.DataFrame(records)
        return df.sort_values("final_pred", ascending=False).reset_index(drop=True)
    except Exception:
        # Fall back to saved CSV
        _csv = DATA_DIR / "datagolf" / "dg_decompositions_latest.csv"
        if _csv.exists():
            return pd.read_csv(_csv)
        return pd.DataFrame()


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

        # ── Normalise weekly lineup earnings ─────────────────────────────────
        for lineup in data.get("weekly_lineups", {}).values():
            earnings = _coerce_money(lineup.get("earnings_earned", lineup.get("points_earned")))
            lineup["earnings_earned"] = earnings or 0
            lineup["points_earned"]   = earnings or 0

        # ── Build per-player earnings from the leaderboard CSVs ──────────────
        # Load 2026 leaderboard once and build a lookup: (player_name, tid) → earnings
        _lb_path = DATA_DIR / "historical" / "leaderboards_2026.csv"
        _lb_earn: dict = {}
        if _lb_path.exists():
            try:
                _lb = pd.read_csv(_lb_path, usecols=["tournament_id","player_name","position","earnings"])
                for _, _row in _lb.iterrows():
                    _e = _coerce_money(_row.get("earnings"))
                    if _e:
                        _lb_earn[(_row["player_name"], _row["tournament_id"])] = _e
            except Exception:
                pass

        # Build per-player summary from weekly_lineups
        _player_totals: dict[str, int] = {}
        _player_weeks:  dict[str, list] = {}
        _wk_lineups = data.get("weekly_lineups", {})
        for _wk_key in sorted(_wk_lineups.keys()):
            _wkd = _wk_lineups[_wk_key]
            _tid  = _wkd.get("tournament_id", "")
            _wnum = _wkd.get("week", _wk_key.replace("week_", ""))
            _tname = _wkd.get("tournament", "")
            _pe   = _wkd.get("player_earnings", {})  # stored per-player breakdown
            for _pname in _wkd.get("lineup", []):
                # Priority: stored player_earnings → leaderboard lookup → 0
                _earn = _pe.get(_pname)
                if _earn is None:
                    _earn = _lb_earn.get((_pname, _tid), 0)
                _player_totals[_pname] = _player_totals.get(_pname, 0) + (_earn or 0)
                _player_weeks.setdefault(_pname, []).append({
                    "week": _wnum,
                    "tournament": _tname,
                    "earnings": _earn or 0,
                })

        # Enrich picks with computed earnings + tournaments_used for dashboard rendering
        picks = data.get("picks", {})
        for _pname, _pdata in picks.items():
            # Support old structure (tournaments_used) and new (uses/weeks)
            if "tournaments_used" not in _pdata:
                _pdata["tournaments_used"] = _player_weeks.get(_pname, [])
            _pdata["times_used"] = _pdata.get("uses", _pdata.get("times_used", 0))
            # Always prefer _player_totals (built from player_earnings ground truth)
            # over stale picks total which may contain old FedEx Cup points
            total_earnings = _player_totals.get(_pname, 0) or _coerce_money(_pdata.get("total_earnings", _pdata.get("total_points"))) or 0
            _pdata["total_earnings"] = total_earnings
            _pdata["total_points"]   = total_earnings

        # Synthesize picks entries for players only in weekly_lineups (not yet in picks dict)
        for _pname, _weeks in _player_weeks.items():
            if _pname not in picks:
                picks[_pname] = {
                    "times_used": len(_weeks),
                    "uses": len(_weeks),
                    "remaining_uses": max(0, 3 - len(_weeks)),
                    "total_earnings": _player_totals.get(_pname, 0),
                    "total_points": _player_totals.get(_pname, 0),
                    "tournaments_used": _weeks,
                }
        data["picks"] = picks

        # ── Summary total from tracker JSON (already correct) ─────────────────
        summary = data.setdefault("summary", {})
        total_earnings = _coerce_money(summary.get("total_earnings", summary.get("total_points")))
        if not total_earnings:
            total_earnings = sum(
                (_wk.get("earnings_earned") or 0) for _wk in _wk_lineups.values()
            )
        summary["total_earnings"] = total_earnings
        summary["total_points"]   = total_earnings
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

    if panel_title:
        st.markdown(f"#### {panel_title}")
    _label_parts = [p for p in [_event_name, _course_name] if p]
    if _label_parts:
        st.caption(" · ".join(_label_parts))

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
    _hist_table["_finish_num"] = pd.to_numeric(
        _hist_table["Finish"].str.lstrip("Tt"), errors="coerce"
    )

    def _row_style(row):
        fn = row["_finish_num"]
        finish_str = str(row["Finish"]).upper()
        if finish_str in ("MC", "CUT", "WD", "DQ"):
            base = "background-color:#1a0d0d;color:#9a6060"
        elif pd.notna(fn):
            if fn == 1:
                base = "background-color:#1f1800;color:#FFD700;font-weight:700"
            elif fn <= 3:
                base = "background-color:#0d2010;color:#00c44f;font-weight:600"
            elif fn <= 10:
                base = "background-color:#0d1e10;color:#6ddb9a"
            elif fn <= 20:
                base = "background-color:#0d1820;color:#4cb8ff"
            else:
                base = ""
        else:
            base = ""
        return [base] * len(row)

    _display_cols = ["Year", "Tournament", "Finish", "To Par", "SG: Total"]
    _styled_hist = (
        _hist_table[_display_cols + ["_finish_num"]]
        .style.apply(_row_style, axis=1)
        .format({
            "Year": lambda x: str(int(x)) if pd.notna(x) else "—",
            "SG: Total": lambda x: f"{x:+.2f}" if pd.notna(x) else "—",
        })
        .hide(axis="columns", subset=["_finish_num"])
    )
    st.dataframe(_styled_hist, hide_index=True, use_container_width=True)




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

    pass  # pool_df available for internal use above



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


PLACED_BETS_PATH = DATA_DIR / "odds" / "placed_bets.csv"
_PLACED_BETS_COLS = [
    "recommendation_id", "tournament_id", "player_name", "market",
    "odds_american", "stake_usd", "placed_at",
    "outcome_status", "outcome_win", "pnl_usd",
]


def load_placed_bets() -> pd.DataFrame:
    """Load the user's personally placed bets ledger.

    This is the source of truth for P&L tracking — only bets the user
    explicitly marked as placed appear here. Not cached because we write
    to it during the session and need fresh reads immediately after.
    """
    if not PLACED_BETS_PATH.exists():
        return pd.DataFrame(columns=_PLACED_BETS_COLS)
    try:
        df = pd.read_csv(PLACED_BETS_PATH)
        # Ensure all expected columns exist (file may predate new columns)
        for col in _PLACED_BETS_COLS:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception:
        return pd.DataFrame(columns=_PLACED_BETS_COLS)


def save_placed_bet(
    recommendation_id: str,
    tournament_id: str,
    player_name: str,
    market: str,
    odds_american,
    stake_usd: float,
) -> None:
    """Append one bet to the placed_bets ledger.

    We use recommendation_id as a unique key — if the user clicks the button
    twice by accident we don't double-record the same bet.
    """
    existing = load_placed_bets()
    if recommendation_id in existing["recommendation_id"].astype(str).values:
        return  # already recorded — idempotent

    new_row = pd.DataFrame([{
        "recommendation_id": recommendation_id,
        "tournament_id":     tournament_id,
        "player_name":       player_name,
        "market":            market,
        "odds_american":     odds_american,
        "stake_usd":         round(float(stake_usd), 2),
        "placed_at":         datetime.now().isoformat(),
        "outcome_status":    "pending",
        "outcome_win":       None,
        "pnl_usd":           None,
    }])
    combined = pd.concat([existing, new_row], ignore_index=True)
    combined.to_csv(PLACED_BETS_PATH, index=False)


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

        # ── Season expert accuracy tracker ───────────────────────────────────
        _exp_hist_path = DATA_DIR / "expert_picks"
        _pred_hist_path = OUTPUTS_DIR / "prediction_history.csv"
        if _pred_hist_path.exists() and _exp_hist_path.exists():
            try:
                _ph = pd.read_csv(_pred_hist_path)
                _ph_won = _ph[(_ph.get("result_recorded", False) == True) & (_ph["actual_won"].astype(str).isin(["True","1","true"]))][["tournament_id","player_name"]].copy()

                if not _ph_won.empty:
                    _ep_files = sorted(_exp_hist_path.glob("expert_picks_R*.csv"))
                    _ep_all = []
                    for _epf in _ep_files:
                        try:
                            _edf = pd.read_csv(_epf)
                            _tid = _epf.stem.replace("expert_picks_", "")
                            _edf["_tid"] = _tid
                            _ep_all.append(_edf)
                        except Exception:
                            continue

                    if _ep_all:
                        _ep_merged = pd.concat(_ep_all, ignore_index=True)
                        if "winner_name" in _ep_merged.columns and "expert_name" in _ep_merged.columns:
                            # Join expert winner picks against actual results
                            _ep_merged["winner_key"] = _ep_merged["winner_name"].fillna("").str.strip().str.lower()
                            _ph_won["winner_key"] = _ph_won["player_name"].fillna("").str.strip().str.lower()
                            _ep_graded = _ep_merged.merge(
                                _ph_won.rename(columns={"tournament_id": "_tid"}),
                                on=["_tid", "winner_key"], how="left"
                            )
                            _ep_graded["hit"] = _ep_graded["player_name"].notna()
                            _ep_graded = _ep_graded[_ep_graded["winner_key"] != ""]

                            if not _ep_graded.empty:
                                st.markdown("---")
                                st.markdown("**Expert winner pick accuracy — this season**")
                                _by_expert = (
                                    _ep_graded.groupby("expert_name")
                                    .agg(picks=("hit","count"), hits=("hit","sum"))
                                    .assign(hit_rate=lambda d: (d["hits"] / d["picks"] * 100).round(1))
                                    .sort_values("hits", ascending=False)
                                    .reset_index()
                                    .rename(columns={"expert_name":"Expert","picks":"Picks","hits":"Correct","hit_rate":"Hit %"})
                                )
                                st.dataframe(_by_expert, hide_index=True, use_container_width=True,
                                             column_config={"Hit %": st.column_config.NumberColumn(format="%.1f%%")})
                                _total_picks = int(_ep_graded["hit"].count())
                                _total_hits  = int(_ep_graded["hit"].sum())
                                st.caption(f"Season total: {_total_hits}/{_total_picks} correct winner picks ({_total_hits/_total_picks*100:.1f}%)" if _total_picks else "")
            except Exception:
                pass

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

    # ── Styled bet cards with reasoning ───────────────────────────────────────
    import html as _rb_hesc

    _mkt_colors = {
        "make_cut":    "#00c44f",
        "top10":       "#4cb8ff",
        "top20":       "#7ba3ff",
        "h2h":         "#f59e0b",
        "h2h_r1":      "#f59e0b",
        "h2h_r2":      "#f59e0b",
        "group_winner":"#f97316",
        "outright":    "#e040fb",
        "top5":        "#4cb8ff",
    }
    _mkt_labels = {
        "make_cut":    "Make Cut",
        "top10":       "Top 10",
        "top20":       "Top 20",
        "top5":        "Top 5",
        "h2h":         "Matchup",
        "h2h_r1":      "Matchup R1",
        "h2h_r2":      "Matchup R2",
        "group_winner":"3-Ball",
        "outright":    "Outright Win",
        "content_card":"Card",
    }

    def _fmt_odds(v) -> str:
        try:
            o = int(float(v))
            return f"+{o}" if o > 0 else str(o)
        except Exception:
            return "—"

    def _corr_badge(score: int) -> str:
        return ""

    # Group by market for tabbed display
    _all_mkts = rec_df["market"].unique().tolist() if "market" in rec_df.columns else []
    _mkt_order = ["make_cut", "top10", "top20", "h2h", "h2h_r1", "h2h_r2", "group_winner", "outright", "top5"]
    _display_mkts = [m for m in _mkt_order if m in _all_mkts] + [m for m in _all_mkts if m not in _mkt_order]

    _tab_labels = [_mkt_labels.get(m, m.replace("_", " ").title()) + f" ({int((rec_df['market']==m).sum())})" for m in _display_mkts]
    _tab_labels = ["All ({})".format(len(rec_df))] + _tab_labels
    _bet_tabs = st.tabs(_tab_labels)

    def _bet_card_html(row) -> str:
        """Return HTML for a single bet recommendation card."""
        _raw_bname = str(row.get("player_name", "?") or "?")
        _bname    = " ".join(reversed(_raw_bname.split(", "))) if ", " in _raw_bname else _raw_bname
        _mkt      = str(row.get("market", ""))
        _color    = _mkt_colors.get(_mkt, "#7a9bbf")
        _mkt_lbl  = _mkt_labels.get(_mkt, _mkt.replace("_", " ").title())
        _odds     = _fmt_odds(row.get("odds_american"))
        _edge     = float(pd.to_numeric(row.get("edge_pts"),    errors="coerce") or 0)
        _ev       = float(pd.to_numeric(row.get("ev_per_1"),    errors="coerce") or 0) * 100
        _mp       = float(pd.to_numeric(row.get("model_prob"),  errors="coerce") or 0) * 100
        _bp       = float(pd.to_numeric(row.get("book_prob"),   errors="coerce") or 0) * 100
        _kelly    = float(pd.to_numeric(row.get("kelly_fraction"), errors="coerce") or 0)
        _rank     = int(pd.to_numeric(row.get("recommendation_rank"), errors="coerce") or 0)
        _book     = str(row.get("book", "") or "")
        _label    = str(row.get("selection_label", _bname) or _bname)
        _gm       = str(row.get("group_members", "") or "")
        _reasoning_raw   = str(row.get("reasoning", "") or "")
        _reasoning_parts = [p.strip() for p in _reasoning_raw.split("|") if p.strip()]

        # Edge pill color: green ≥8pp, amber 4-8pp, muted <4pp
        _edge_col = "#00c44f" if _edge >= 8 else ("#f39c12" if _edge >= 4 else "#7a9bbf")
        _edge_bg  = "#00c44f22" if _edge >= 8 else ("#f39c1222" if _edge >= 4 else "#1a2537")

        # Model vs book comparison bar — scale to max(mp, bp) so bars are relative
        _bar_max  = max(_mp, _bp, 1.0)
        _mp_w     = min(int(_mp / _bar_max * 100), 100)
        _bp_w     = min(int(_bp / _bar_max * 100), 100)

        _book_str = f" · {_rb_hesc.escape(_book)}" if _book else ""
        _kelly_str = f"Kelly {_kelly*100:.1f}%" if _kelly > 0 else ""
        _ev_str    = f"EV {_ev:+.1f}%" if _ev != 0 else ""
        _meta_parts = [s for s in [_kelly_str, _ev_str] if s]
        _meta_html  = (
            f'<div style="font-size:0.62em;color:#7a9bbf;margin-top:4px">'
            + "  ·  ".join(_meta_parts) + "</div>"
        ) if _meta_parts else ""

        # Reasoning bullets
        _reason_html = "".join(
            f'<div style="font-size:0.76em;color:#b0c8e8;padding:5px 0;'
            f'border-top:1px solid #1c2f4a">&#8226; {_rb_hesc.escape(p)}</div>'
            for p in _reasoning_parts[:4]
        )

        # Group members (H2H / 3-ball)
        _gm_html = ""
        if _gm and "|" in _gm:
            _gm_html = (
                f'<div style="font-size:0.65em;color:#7a9bbf;margin-top:6px;'
                f'padding-top:4px;border-top:1px solid #1c2f4a">'
                f'{_rb_hesc.escape(_gm[:120])}</div>'
            )

        # Selection label — only show if it differs meaningfully from player name
        _label_html = ""
        if _label and _label.lower().strip() != _bname.lower().strip():
            _label_html = (
                f'<div style="font-size:0.68em;color:#7a9bbf;margin-top:2px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f'{_rb_hesc.escape(_label[:60])}</div>'
            )

        return (
            f'<div style="border:1px solid {_color}33;border-radius:10px;'
            f'padding:14px 16px 12px;background:linear-gradient(150deg,{_color}08 0%,#0a1520 100%);'
            f'margin-bottom:10px;height:100%">'

            # ── Header: market pill + book ──────────────────────────────────
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
            f'<span style="background:{_color}22;color:{_color};font-size:0.62em;font-weight:800;'
            f'padding:2px 8px;border-radius:4px;letter-spacing:0.08em;">{_mkt_lbl.upper()}</span>'
            f'<span style="font-size:0.62em;color:#7a9bbf">#{_rank}{_book_str}</span>'
            f'</div>'

            # ── Player name ─────────────────────────────────────────────────
            f'<div style="font-size:1.05em;font-weight:700;color:#e8f0f8;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px">'
            f'{_rb_hesc.escape(_bname)}</div>'
            f'{_label_html}'

            # ── Odds + edge pill ────────────────────────────────────────────
            f'<div style="display:flex;align-items:baseline;gap:10px;margin:8px 0">'
            f'<span style="font-size:1.8em;font-weight:800;color:{_color};line-height:1">{_odds}</span>'
            f'<span style="background:{_edge_bg};color:{_edge_col};font-size:0.75em;font-weight:700;'
            f'padding:2px 8px;border-radius:4px;white-space:nowrap">+{_edge:.1f}pp edge</span>'
            f'</div>'

            # ── Model vs Book comparison bar ────────────────────────────────
            f'<div style="margin-bottom:6px">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.65em;color:#7a9bbf;margin-bottom:3px">'
            f'<span style="color:{_color}">Model {_mp:.1f}%</span>'
            f'<span>Book {_bp:.1f}%</span>'
            f'</div>'
            f'<div style="position:relative;background:#0d1b2a;border-radius:3px;height:6px;overflow:hidden">'
            f'<div style="position:absolute;left:0;top:0;height:100%;width:{_bp_w}%;background:#3a5070;border-radius:3px"></div>'
            f'<div style="position:absolute;left:0;top:0;height:100%;width:{_mp_w}%;background:{_color};border-radius:3px;opacity:0.9"></div>'
            f'</div>'
            f'</div>'

            # ── Kelly / EV meta ─────────────────────────────────────────────
            f'{_meta_html}'

            # ── Reasoning bullets ───────────────────────────────────────────
            f'{_reason_html}'
            f'{_gm_html}'
            f'</div>'
        )

    def _render_bet_cards(df: pd.DataFrame, limit: int = 20):
        if df.empty:
            st.caption("No recommendations in this market.")
            return
        _sb  = "kelly_fraction" if "kelly_fraction" in df.columns else "recommendation_rank"
        _asc = False if _sb == "kelly_fraction" else True
        df   = df.sort_values(_sb, ascending=_asc).head(limit)
        rows = list(df.iterrows())
        for _i in range(0, len(rows), 2):
            _pair = rows[_i:_i+2]
            _cols = st.columns(2)
            for _ci, (_, _row) in enumerate(_pair):
                _cols[_ci].markdown(_bet_card_html(_row), unsafe_allow_html=True)

    with _bet_tabs[0]:
        _render_bet_cards(rec_df, limit=30)

    for _ti, _tm in enumerate(_display_mkts):
        with _bet_tabs[_ti + 1]:
            _mkt_df = rec_df[rec_df["market"] == _tm].copy() if "market" in rec_df.columns else pd.DataFrame()
            _render_bet_cards(_mkt_df, limit=20)

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
    _profile_pred_data = {}
    if preds_df is not None and not preds_df.empty and "player_name" in preds_df.columns:
        _pr = preds_df[preds_df["player_name"].apply(_name_key) == _name_key(selected_profile_player)]
        if not _pr.empty:
            _profile_pred_data = _pr.iloc[0].to_dict()
    if profile:
        render_player_profile_card(profile, show_full=True, pred_data=_profile_pred_data if _profile_pred_data else None)
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




def render_player_profile_card(profile: dict, show_full: bool = True, pred_data: dict | None = None):
    """Render player betting profile card. pred_data = row from latest_predictions.csv as dict."""
    import re as _re

    bullets = format_bullets_as_list(profile.get('bullets', ''))
    sg_stats = parse_strokes_gained_from_bullets(bullets)
    p = pred_data or {}

    # Prefer predictions CSV values; fall back to bullet-parsed values
    def _pval(col, fallback=None):
        v = p.get(col)
        return float(v) if v is not None and pd.notna(v) else fallback

    sg_ott  = _pval("season_sg_ott",  sg_stats.get("sg_ott"))
    sg_app  = _pval("season_sg_app",  sg_stats.get("sg_app"))
    sg_arg  = _pval("season_sg_arg",  sg_stats.get("sg_atg"))
    sg_putt = _pval("season_sg_putt", sg_stats.get("sg_putt"))
    sg_tot  = _pval("season_sg_total",sg_stats.get("sg_total"))
    win_p   = _pval("win_prob")
    t10_p   = _pval("top10_prob")
    ev      = _pval("expected_value")
    wr      = _pval("world_rank")
    ft      = _pval("form_trend", 0.0)
    hot     = _pval("hot_hand_score", 0.0)
    consec  = int(_pval("consecutive_cuts", 0) or 0)
    drv     = _pval("driving_dist_val", sg_stats.get("driving_dist"))
    dg_fit  = _pval("dg_fit_total")

    # === HEADER ===
    _sg_color = "#00c44f" if (sg_tot or 0) >= 0 else "#e74c3c"
    _form_tag = ("🔥 Hot" if ft > 0.3 else ("❄️ Cold" if ft < -0.3 else ""))
    _wr_str   = f"WR #{int(wr)}" if wr is not None else ""

    st.markdown(
        f"""<div style="border:1px solid #1e3a5a;border-radius:10px;padding:14px 16px;background:linear-gradient(150deg,#0d2a1e0d 0%,#0a1520 100%);margin-bottom:12px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
    <div>
      <div style="font-size:1.15em;font-weight:700;color:#e8f0f8">{profile.get('player_name','Player')}</div>
      <div style="font-size:0.75em;color:#7a9bbf;margin-top:2px">{_wr_str}{(" · " if _wr_str and _form_tag else "") + _form_tag}</div>
    </div>
    <div style="display:flex;gap:20px;flex-wrap:wrap">
      <div style="text-align:center"><div style="font-size:0.65em;color:#7a9bbf">WIN%</div><div style="font-size:1.1em;font-weight:700;color:#e8f0f8">{f"{win_p*100:.1f}%" if win_p is not None else "—"}</div></div>
      <div style="text-align:center"><div style="font-size:0.65em;color:#7a9bbf">TOP-10</div><div style="font-size:1.1em;font-weight:700;color:#e8f0f8">{f"{t10_p*100:.0f}%" if t10_p is not None else "—"}</div></div>
      <div style="text-align:center"><div style="font-size:0.65em;color:#7a9bbf">SG:TOTAL</div><div style="font-size:1.1em;font-weight:700;color:{_sg_color}">{f"{sg_tot:+.2f}" if sg_tot is not None else "—"}</div></div>
      <div style="text-align:center"><div style="font-size:0.65em;color:#7a9bbf">EXP VALUE</div><div style="font-size:1.1em;font-weight:700;color:#4cb8ff">{f"${ev:,.0f}" if ev is not None else "—"}</div></div>
      {f'<div style="text-align:center"><div style="font-size:0.65em;color:#7a9bbf">DRV DIST</div><div style="font-size:1.1em;font-weight:700;color:#e8f0f8">{drv:.0f} yds</div></div>' if drv else ""}
    </div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # === SG VISUAL BARS (gradient-based, no absolute positioning) ===
    def _sg_bar_row(label, val, bar_color, max_val):
        pct = min(abs(val) / (max_val * 1.2) * 50, 50)
        val_str = f"{val:+.3f}"
        center_line = "linear-gradient(to right, transparent calc(50% - 0.5px), #2a3f55 calc(50% - 0.5px), #2a3f55 calc(50% + 0.5px), transparent calc(50% + 0.5px))"
        if val >= 0:
            fill = f"linear-gradient(to right, #0d1b2a 50%, {bar_color} 50%, {bar_color} calc(50% + {pct:.1f}%), #0d1b2a calc(50% + {pct:.1f}%))"
        else:
            fill = f"linear-gradient(to right, #0d1b2a calc(50% - {pct:.1f}%), {bar_color} calc(50% - {pct:.1f}%), {bar_color} 50%, #0d1b2a 50%)"
        return (
            f'<div style="display:flex;align-items:center;margin-bottom:8px;gap:10px">'
            f'<div style="width:110px;font-size:0.8em;color:#8aabcc;text-align:right;flex-shrink:0;line-height:1.4">{label}</div>'
            f'<div style="flex:1;height:12px;border-radius:6px;background:{fill},{center_line}"></div>'
            f'<div style="width:56px;font-size:0.8em;font-weight:600;color:{bar_color};flex-shrink:0;line-height:1.4">{val_str}</div>'
            f'</div>'
        )

    sg_cats = [
        ("Off-the-Tee", sg_ott),
        ("Approach",    sg_app),
        ("Around Green",sg_arg),
        ("Putting",     sg_putt),
    ]
    sg_vals = [v for _, v in sg_cats if v is not None]
    if sg_vals:
        _max_sg = max(abs(v) for v in sg_vals) or 1.0
        bar_html = '<div style="margin:10px 0 16px 0">'
        for label, val in sg_cats:
            if val is None:
                continue
            _bar_color = "#00c44f" if val >= 0 else "#e74c3c"
            bar_html += _sg_bar_row(label, val, _bar_color, _max_sg)
        if dg_fit is not None:
            _fit_color = "#4cb8ff" if dg_fit >= 0 else "#e74c3c"
            bar_html += _sg_bar_row("Course Fit", dg_fit, _fit_color, max(_max_sg, abs(dg_fit), 0.3))
        bar_html += "</div>"
        st.markdown(bar_html, unsafe_allow_html=True)

    if not show_full:
        return

    # === CATEGORIZED INSIGHTS ===
    def _highlight_numbers(text: str) -> str:
        text = _re.sub(r'(\b\d+(?:\.\d+)?-under\b)', r'**\1**', text)
        text = _re.sub(r'(\b\d+(?:\.\d+)?-over\b)', r'**\1**', text)
        text = _re.sub(r'([+-]\d+\.\d+)', r'**\1**', text)
        text = _re.sub(r'(\b\d+(?:st|nd|rd|th)\b)', r'**\1**', text)
        text = _re.sub(r'(\b\d+(?:\.\d+)?%)', r'**\1**', text)
        return text

    course_bullets, form_bullets, stat_bullets = [], [], []
    for b in bullets:
        bl = b.lower()
        if 'strokes gained' in bl and ('season' in bl or 'ranks' in bl or 'rank' in bl or 'past five' in bl):
            stat_bullets.append(b)
        elif any(w in bl for w in ['first time', 'won this', 'won the tournament', 'this course',
                                    'at this venue', 'best finish', 'previous visit', 'competing in the tournament']):
            course_bullets.append(b)
        elif any(w in bl for w in ['last ten', 'appearance', 'finish', 'top-', 'consecutive', 'recent']):
            form_bullets.append(b)
        else:
            stat_bullets.append(b)

    # Inject predictions-based form context if missing from bullets
    if not form_bullets and consec > 0:
        form_bullets.append(f"{consec} consecutive cuts made this season.")
    if not form_bullets and hot >= 7:
        form_bullets.append(f"Hot-hand score {hot:.0f}/10 — strong recent form.")

    _insight_sections = [
        ("⛳ Course History", course_bullets, "#00c44f"),
        ("📈 Recent Form",    form_bullets,   "#4cb8ff"),
        ("📊 Stats",          stat_bullets,   "#f59e0b"),
    ]
    _cols = [s for s in _insight_sections if s[1]]
    if _cols:
        _icols = st.columns(len(_cols))
        for _col_obj, (title, items, color) in zip(_icols, _cols):
            with _col_obj:
                st.markdown(
                    f'<div style="font-size:0.78em;font-weight:700;color:{color};letter-spacing:0.08em;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid {color}22">{title}</div>',
                    unsafe_allow_html=True,
                )
                for b in items[:3]:
                    st.markdown(f'<div style="font-size:0.88em;line-height:1.55;margin-bottom:6px;color:#ccd6e8">&#8226; {_highlight_numbers(b)}</div>', unsafe_allow_html=True)

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

    # Resolve "R2026556" style name to real tournament name via schedule
    import re as _re
    if _re.match(r'^R\d+$', str(tournament_name)):
        _sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
        if _sched_path.exists():
            try:
                _sdf = pd.read_csv(_sched_path)
                _sm  = _sdf[_sdf["tournament_id"] == tournament_name]
                if not _sm.empty:
                    tournament_name = _sm.iloc[0]["tournament_name"]
            except Exception:
                pass

    # ── Tournament header ────────────────────────────────────────────────────
    _rs_lower  = str(round_status).lower()
    _rs_active = "progress" in _rs_lower or (_rs_lower.startswith("r") and _rs_lower[1:].isdigit())
    _rs_final  = _rs_lower in ("official", "final", "complete", "completed")

    if _rs_active:
        _status_display = f"Round {current_round} In Progress"
    elif _rs_final or (not _rs_active and round_status):
        _status_display = f"Round {current_round} Official"
    else:
        _status_display = "Upcoming"

    _cut_score_raw = (cut_line or {}).get("cutScore", "")
    _cut_score     = _cut_score_raw if _cut_score_raw not in ("", None) else "—"

    # Header row: name left, round/status/cut/field right
    _htitle, _hstats = st.columns([3, 2])
    with _htitle:
        st.markdown(f"## {tournament_name}")
        _dot = "🟢" if _rs_active else "⚪"
        st.caption(f"{_dot} {_status_display}  ·  Round {current_round} of 4  ·  {len(df)} players")
    with _hstats:
        _hc1, _hc2 = st.columns(2)
        _hc1.metric("Cut", _cut_score if _cut_score != "—" else f"R{current_round}")
        _hc2.metric("Field", len(df))

    # ── Cut projection (rounds 1-2 only) ────────────────────────────────────
    if cut_projection and current_round <= 2:
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

    _my_picks_lower = [p.lower() for p in (my_picks or [])]

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

            # Current round score + previous rounds
            _cur_r   = player.get(f"R{current_round}")
            _cur_str = f"{int(float(_cur_r))}" if pd.notna(_cur_r) else "—"
            _prev_parts = []
            for _pr in range(1, current_round):
                _v = player.get(f"R{_pr}")
                if pd.notna(_v):
                    _prev_parts.append(f"R{_pr}: {int(float(_v))}")
            _prev_str = " · ".join(_prev_parts)

            # Score color
            _score_color = "#00c44f" if _tot_num < 0 else ("#e53935" if _tot_num > 0 else "#dde6f5")

            # Movement
            change = player.get("position_change", 0)
            if pd.notna(change) and change != 0:
                _mv_str   = f"{'▲' if change > 0 else '▼'} {abs(int(change))}"
                _mv_color = "#00c44f" if change > 0 else "#e53935"
            else:
                _mv_str   = "—"
                _mv_color = "#3a5270"

            # My Pick badge
            _is_my_pick = any(
                name.lower() in _pk or _pk in name.lower()
                for _pk in _my_picks_lower
            )
            _pick_badge = (
                "<span style='background:#00c44f22;color:#00c44f;font-size:10px;"
                "font-weight:700;letter-spacing:1px;padding:2px 8px;border-radius:10px;"
                "border:1px solid #00c44f;'>MY PICK</span>"
                if _is_my_pick else ""
            )

            # Odds display
            _odds_html = (
                f"<div style='color:#5a7a9a;font-size:11px;font-weight:600;"
                f"margin-top:8px;padding-top:8px;border-top:1px solid #1a3050;'>"
                f"Win odds: <span style='color:#dde6f5;'>{odds}</span></div>"
                if odds else ""
            )

            # Round score mini-grid
            def _rnd_val(p, r):
                v = p.get(f"R{r}")
                try:
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return "—"
                    return str(int(float(v)))
                except (ValueError, TypeError):
                    return "—"

            _rnd_cells = "".join(
                f'<div style="text-align:center">'
                f'<div style="font-size:13px;font-weight:700;color:#dde6f5;">{_rnd_val(player, r)}</div>'
                f'<div style="font-size:9px;color:#3a5270;letter-spacing:.5px;">R{r}</div></div>'
                for r in range(1, 5)
            )

            st.markdown(
                f'<div style="background:#0b1929;border-radius:10px;padding:16px;'
                f'border:1px solid #1a3050;border-top:3px solid {_pos_colors[i]};">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;margin-bottom:10px;">'
                f'<span style="color:{_pos_colors[i]};font-size:11px;font-weight:800;'
                f'letter-spacing:1.5px;">{_pos_labels[i].upper()}</span>'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                + _pick_badge +
                f'<span style="font-size:12px;font-weight:700;color:{_mv_color};">{_mv_str}</span>'
                f'</div>'
                f'</div>'
                f'<div style="font-size:15px;font-weight:700;color:#e8eef8;margin-bottom:2px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>'
                f'<div style="color:#3a5270;font-size:11px;margin-bottom:10px;">{country}</div>'
                f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:10px;">'
                f'<span style="font-size:38px;font-weight:900;color:{_score_color};line-height:1;">{total}</span>'
                f'<span style="font-size:12px;color:#5a7a9a;">Thru {thru}</span>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;'
                f'padding-top:10px;border-top:1px solid #1a3050;">'
                + _rnd_cells +
                f'</div>'
                + _odds_html +
                f'</div>',
                unsafe_allow_html=True,
            )

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
    """Render comparison of live results vs model predictions.

    Layout: simple pick cards + movers summary always visible;
    full comparison table and scatter behind expanders.
    """
    tournament_id = meta.get("tournament_id", "")
    comparison = compare_live_vs_predictions(live_df, tournament_id)

    if comparison.empty:
        st.warning("No predictions found for this tournament.")
        return

    with_pred = comparison[comparison["model_rank"].notna()].copy()
    if with_pred.empty:
        st.warning("No matching players found between predictions and leaderboard.")
        return

    # ── Helper ────────────────────────────────────────────────────────────────
    def _verdict(diff: int) -> tuple[str, str]:
        """Return (label, color) based on spots gained vs model rank."""
        if diff >= 10:  return "Beating model", "#00c44f"
        if diff >= 3:   return "Ahead of model", "#6ddb9a"
        if diff >= -2:  return "As expected", "#5a7a9a"
        if diff >= -9:  return "Below model", "#ffa726"
        return "Missing model", "#e53935"

    # ── Section 1: Your picks vs model ───────────────────────────────────────
    _picks_live = st.session_state.get("_live_picks_this_week", [])

    # Find pick rows in comparison
    _pick_rows = []
    for _pname in _picks_live:
        _last = _pname.strip().split()[-1].lower()
        _m = with_pred[with_pred["player_name"].str.lower().str.contains(_last, na=False)]
        if not _m.empty:
            _pick_rows.append(_m.iloc[0])

    if _pick_rows:
        st.markdown("#### Your Picks vs Model")
        _pcols = st.columns(len(_pick_rows))
        for _col, _row in zip(_pcols, _pick_rows):
            _pos   = str(_row.get("position", "—"))
            _score = str(_row.get("total", "E"))
            _mrank = int(_row.get("model_rank", 0))
            _diff  = int(_row.get("rank_diff", 0))
            _label, _color = _verdict(_diff)
            _diff_str = f"+{_diff}" if _diff > 0 else str(_diff)
            with _col:
                _pname_vs = _row.get('player_name', '')
                st.markdown(
                    f'<div style="background:#0b1929;border:1px solid #1a3050;border-top:3px solid {_color};'
                    f'border-radius:10px;padding:14px;text-align:center;">'
                    f'<div style="font-size:13px;font-weight:700;color:#dde6f5;margin-bottom:6px;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_pname_vs}</div>'
                    f'<div style="font-size:28px;font-weight:900;color:#eee;line-height:1;">{_pos}</div>'
                    f'<div style="font-size:13px;color:#5a7a9a;margin-bottom:8px;">{_score}</div>'
                    f'<div style="font-size:11px;font-weight:700;color:{_color};">{_label}</div>'
                    f'<div style="font-size:11px;color:#3a5270;">Model #{_mrank} · {_diff_str} spots</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.markdown("")

    # ── Section 2: Biggest movers (always visible, compact) ──────────────────
    st.markdown("#### Biggest Movers vs Model")
    _oc1, _oc2 = st.columns(2)

    with _oc1:
        st.caption("Exceeding expectations")
        for _, _r in with_pred.nlargest(5, "rank_diff").iterrows():
            _d = int(_r["rank_diff"])
            if _d <= 0: continue
            st.markdown(
                f"<div style='padding:5px 0;border-bottom:1px solid #0d1e30'>"
                f"<span style='color:#dde6f5;font-weight:600'>{_r['player_name']}</span>"
                f" <span style='color:#5a7a9a;font-size:12px'>{_r['position']}</span>"
                f" <span style='color:#00c44f;font-size:12px;font-weight:700'>"
                f"+{_d} (model #{int(_r['model_rank'])})</span></div>",
                unsafe_allow_html=True,
            )

    with _oc2:
        st.caption("Below expectations")
        for _, _r in with_pred.nsmallest(5, "rank_diff").iterrows():
            _d = int(_r["rank_diff"])
            if _d >= 0: continue
            st.markdown(
                f"<div style='padding:5px 0;border-bottom:1px solid #0d1e30'>"
                f"<span style='color:#dde6f5;font-weight:600'>{_r['player_name']}</span>"
                f" <span style='color:#5a7a9a;font-size:12px'>{_r['position']}</span>"
                f" <span style='color:#e53935;font-size:12px;font-weight:700'>"
                f"{_d} (model #{int(_r['model_rank'])})</span></div>",
                unsafe_allow_html=True,
            )

    # ── Section 3: Model's top-10 picks — how they're doing ──────────────────
    st.markdown("")
    st.markdown("#### Model's Top-10 — Live Status")
    _top10 = with_pred.nsmallest(10, "model_rank").copy()
    for _, _r in _top10.iterrows():
        _d    = int(_r.get("rank_diff", 0))
        _lbl, _clr = _verdict(_d)
        _ds   = f"+{_d}" if _d > 0 else str(_d)
        _wp   = float(_r.get("win_prob", 0) or 0) * 100
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:6px 10px;border-bottom:1px solid #0d1e30'>"
            f"<span style='color:#5a7a9a;font-size:11px;width:24px'>#{int(_r['model_rank'])}</span>"
            f"<span style='color:#dde6f5;flex:1;margin:0 8px'>{_r['player_name']}</span>"
            f"<span style='color:#5a7a9a;font-size:12px;width:36px'>{_r['position']}</span>"
            f"<span style='color:#5a7a9a;font-size:12px;width:30px'>{_r['total']}</span>"
            f"<span style='color:{_clr};font-size:11px;font-weight:700;width:70px;text-align:right'>"
            f"{_lbl} ({_ds})</span></div>",
            unsafe_allow_html=True,
        )
    st.caption(f"Pre-tournament win probability shown · {len(with_pred)} players matched")





def render_fantasy_lineup_tracker(live_df: pd.DataFrame, live_meta: dict | None = None):
    """Track WineTime fantasy lineup performance — current week + season record."""
    live_df = ensure_player_name_column(live_df)
    live_df["_nk"] = live_df["player_name"].apply(_name_key)

    usage_data = load_usage_data()
    lineups = usage_data.get("weekly_lineups", {})
    picks   = usage_data.get("picks", {})

    if not lineups:
        st.info("No fantasy lineup data. Sync from the fantasy site in My Picks.")
        return

    # ── Find current week lineup ──────────────────────────────────────────────
    # Match by tournament_id from live meta, or fall back to latest non-empty week
    _live_tid  = (live_meta or {}).get("tournament_id", "")
    _live_name = (live_meta or {}).get("tournament_name", "")

    current_lineup = None
    for _wk in sorted(lineups.keys(), key=lambda x: int(x.split("_")[1]), reverse=True):
        _wv = lineups[_wk]
        if _wv.get("lineup"):
            # Prefer match by tournament_id embedded in name (e.g. "R2026556")
            _wname = _wv.get("tournament", "")
            if _live_tid and _live_tid in _wname:
                current_lineup = _wv
                break
            if not current_lineup:
                current_lineup = _wv  # fallback: latest non-empty

    if not current_lineup:
        st.info("No lineup found for this tournament.")
        return

    _week_num  = current_lineup.get("week", "?")
    _tourney   = current_lineup.get("tournament", "Tournament")
    _wrp       = current_lineup.get("wrp")
    _earnings  = current_lineup.get("earnings_earned")
    _pending   = _earnings is None

    # ── Header ───────────────────────────────────────────────────────────────
    _hc1, _hc2, _hc3 = st.columns([4, 1, 1])
    with _hc1:
        st.markdown(f"#### Week {_week_num} — {_tourney}")
    with _hc2:
        st.metric("WRP", f"#{_wrp}" if _wrp else ("In Progress" if _pending else "—"))
    with _hc3:
        st.metric("Earnings", f"${_earnings:,.0f}" if _earnings else ("Pending" if _pending else "—"))

    # ── Live player cards ─────────────────────────────────────────────────────
    _lineup_players = current_lineup.get("lineup", [])
    if not _lineup_players:
        st.info("No players in this week's lineup.")
    else:
        _cols = st.columns(len(_lineup_players))
        for _col, _player in zip(_cols, _lineup_players):
            _pk  = _name_key(_player)
            _row = live_df[live_df["_nk"] == _pk]
            if _row.empty:
                # Try partial last-name match
                _parts = _player.split()
                _last  = _parts[-1].lower() if _parts else ""
                _row   = live_df[live_df["_nk"].str.contains(_last, case=False, na=False)]

            if not _row.empty:
                _r      = _row.iloc[0]
                _pos    = str(_r.get("position", "—"))
                _total  = str(_r.get("total", "E"))
                _thru   = str(_r.get("thru", "—"))
                _status = str(_r.get("status", "")).lower()
                _r1 = int(_r["R1"]) if pd.notna(_r.get("R1")) else "—"
                _r2 = int(_r["R2"]) if pd.notna(_r.get("R2")) else "—"
                _r3 = int(_r["R3"]) if pd.notna(_r.get("R3")) else "—"
                _r4 = int(_r["R4"]) if pd.notna(_r.get("R4")) else "—"

                def _sc(v):
                    s = str(v).strip()
                    if s.startswith("-"): return "#00c44f"
                    if s in ("E", "0"):   return "#dde6f5"
                    return "#e53935"

                def _rc(v):
                    if v == "—": return "#3a5270"
                    try:
                        n = int(v)
                        if n <= 69:   return "#00c44f"
                        elif n <= 71: return "#6ddb9a"
                        elif n == 72: return "#dde6f5"
                        elif n <= 74: return "#ffa726"
                        else:         return "#e53935"
                    except Exception:
                        return "#3a5270"

                _border = "#e53935" if _status == "cut" else _sc(_total)
                _rnd_cells = "".join(
                    f'<div><div style="font-size:15px;font-weight:800;color:{_rc(v)};">{v}</div>'
                    f'<div style="font-size:10px;color:#3a5270;font-weight:600;">R{i}</div></div>'
                    for i, v in enumerate([_r1, _r2, _r3, _r4], 1)
                )
                with _col:
                    _total_color = _sc(_total)
                    st.markdown(
                        f'<div style="background:#0b1929;border:1px solid #1a3050;border-top:3px solid {_border};'
                        f'border-radius:12px;padding:16px 14px 12px;box-sizing:border-box;">'
                        f'<div style="font-size:13px;font-weight:800;color:#dde6f5;white-space:nowrap;'
                        f'overflow:hidden;text-overflow:ellipsis;margin-bottom:8px;">{_player}</div>'
                        f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px;">'
                        f'<span style="background:#132840;color:#dde6f5;font-size:12px;font-weight:800;'
                        f'padding:2px 9px;border-radius:20px;">{_pos}</span>'
                        f'<span style="font-size:32px;font-weight:900;color:{_total_color};line-height:1;">{_total}</span>'
                        f'<span style="font-size:11px;color:#5a7a9a;">Thru {_thru}</span>'
                        f'</div>'
                        f'<div style="border-top:1px solid #1a3050;padding-top:8px;'
                        f'display:grid;grid-template-columns:repeat(4,1fr);gap:4px;text-align:center;">'
                        + _rnd_cells +
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                with _col:
                    st.markdown(
                        f'<div style="background:#0b1929;border:1px solid #1a3050;border-top:3px solid #3a5270;'
                        f'border-radius:12px;padding:16px 14px 12px;">'
                        f'<div style="font-size:13px;font-weight:700;color:#dde6f5;margin-bottom:8px;">{_player}</div>'
                        f'<div style="font-size:12px;color:#5a7a9a;">Not in leaderboard</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("---")

    # ── Season record ─────────────────────────────────────────────────────────
    st.markdown("#### Season Record")

    def _wrp_badge(wrp, pending):
        if pending:
            return "<span style='background:#1a2a3a;color:#ffa726;font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;'>Pending</span>"
        if not wrp:
            return "<span style='color:#3a5270;font-size:11px;'>—</span>"
        n = int(wrp)
        if n <= 3:   c = "#ffd700"
        elif n <= 10: c = "#00c44f"
        elif n <= 20: c = "#6ddb9a"
        else:         c = "#5a7a9a"
        return (f"<span style='background:{c}22;color:{c};font-size:11px;font-weight:800;"
                f"padding:2px 8px;border-radius:10px;border:1px solid {c}44;'>#{n}</span>")

    _season_rows = []
    for _wk in sorted(lineups.keys(), key=lambda x: int(x.split("_")[1])):
        _wv = lineups[_wk]
        if not _wv.get("lineup"):
            continue
        _season_rows.append(_wv)

    if _season_rows:
        _total_earned = 0
        _rows_html = ""
        for _i, _wv in enumerate(_season_rows):
            _earn    = _wv.get("earnings_earned")
            _wrp     = _wv.get("wrp")
            _pending = _earn is None
            _bg      = "#0a1520" if _i % 2 == 0 else "#0d1a28"
            _earn_str = f"${_earn:,.0f}" if _earn else ("Pending" if _pending else "—")
            _earn_col = "#ffa726" if _pending else ("#00c44f" if _earn else "#3a5270")
            if _earn:
                _total_earned += _earn
            _lineup_str = " · ".join(_wv.get("lineup", []))
            _rows_html += (
                f"<div style='display:flex;align-items:center;gap:8px;"
                f"background:{_bg};padding:7px 10px;border-bottom:1px solid #0d1e30;'>"
                f"<span style='color:#3a5270;font-size:11px;font-weight:700;width:24px;text-align:center'>"
                f"{_wv.get('week','')}</span>"
                f"<span style='color:#dde6f5;font-size:12px;flex:1;white-space:nowrap;"
                f"overflow:hidden;text-overflow:ellipsis;'>{_wv.get('tournament','')[:28]}</span>"
                f"<span style='color:#5a7a9a;font-size:11px;flex:2;white-space:nowrap;"
                f"overflow:hidden;text-overflow:ellipsis;'>{_lineup_str}</span>"
                f"<span style='width:60px;text-align:center'>{_wrp_badge(_wrp, _pending)}</span>"
                f"<span style='color:{_earn_col};font-size:12px;font-weight:700;"
                f"width:80px;text-align:right;'>{_earn_str}</span>"
                f"</div>"
            )

        st.markdown(
            f"<div style='border:1px solid #1a3050;border-radius:10px;overflow:hidden;"
            f"font-family:monospace;'>"
            f"<div style='display:flex;gap:8px;background:#060e18;padding:5px 10px;"
            f"border-bottom:1px solid #1a3050;'>"
            f"<span style='color:#3a5270;font-size:10px;font-weight:700;width:24px'>WK</span>"
            f"<span style='color:#3a5270;font-size:10px;font-weight:700;flex:1'>TOURNAMENT</span>"
            f"<span style='color:#3a5270;font-size:10px;font-weight:700;flex:2'>LINEUP</span>"
            f"<span style='color:#3a5270;font-size:10px;font-weight:700;width:60px;text-align:center'>WRP</span>"
            f"<span style='color:#3a5270;font-size:10px;font-weight:700;width:80px;text-align:right'>EARNINGS</span>"
            f"</div>"
            f"{_rows_html}</div>",
            unsafe_allow_html=True,
        )

        _completed = [r for r in _season_rows if r.get("earnings_earned")]
        if _completed:
            st.caption(f"{len(_completed)} of {len(_season_rows)} weeks completed · ${_total_earned:,.0f} total earnings")

    # ── Player usage pips ─────────────────────────────────────────────────────
    if picks:
        _used_picks = {n: d for n, d in picks.items() if d.get("times_used", 0) > 0}
        if _used_picks:
            st.markdown("#### Player Usage")

            # Sort by earnings desc, then alpha
            _sorted_picks = sorted(
                _used_picks.items(),
                key=lambda x: -(x[1].get("total_earnings", 0))
            )

            # Render in a 2-column grid
            _pip_cols = st.columns(2)
            for _pi, (_pname, _pd) in enumerate(_sorted_picks):
                _used = _pd.get("times_used", 0)
                _rem  = _pd.get("remaining_uses", 3 - _used)
                _earn = _pd.get("total_earnings", 0)

                # Pip color based on remaining uses
                if _rem == 0:   _pip_c = "#e53935"
                elif _rem == 1: _pip_c = "#ffa726"
                else:           _pip_c = "#00c44f"

                # Build 3 pip dots
                _pips = ""
                for _dot in range(3):
                    if _dot < _used:
                        _pips += f"<span style='color:{_pip_c};font-size:14px;'>●</span>"
                    else:
                        _pips += "<span style='color:#1a3050;font-size:14px;'>●</span>"

                _earn_str = f"${_earn:,.0f}" if _earn else "—"

                with _pip_cols[_pi % 2]:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;justify-content:space-between;"
                        f"background:#0b1929;border:1px solid #1a3050;border-radius:8px;"
                        f"padding:8px 12px;margin-bottom:6px;'>"
                        f"<span style='color:#dde6f5;font-size:13px;font-weight:600;"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px'>{_pname}</span>"
                        f"<span style='letter-spacing:3px;'>{_pips}</span>"
                        f"<span style='color:#5a7a9a;font-size:12px;'>{_earn_str}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )


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

        _rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
        _rank_labels = ["1st", "2nd", "3rd"]

        for i, (_, player) in enumerate(top3_fits.iterrows()):
            with fit_cols[i]:
                name = str(player.get("player_name", "Unknown"))[:18]
                enhanced_pct = pd.to_numeric(player.get("enhanced_fit_pct"), errors="coerce")
                model_pct    = pd.to_numeric(player.get("dg_fit_pct"),        errors="coerce")
                lift_pts     = pd.to_numeric(player.get("fit_lift_pts"),       errors="coerce")
                starts       = int(pd.to_numeric(player.get("actual_starts"),  errors="coerce") or 0)
                confidence   = pd.to_numeric(player.get("actual_confidence"),  errors="coerce")
                avg_sg       = pd.to_numeric(player.get("actual_sg_avg"),      errors="coerce")
                top10_rate   = pd.to_numeric(player.get("actual_top10_rate"),  errors="coerce")

                rc = _rank_colors[i]
                rl = _rank_labels[i]
                enhanced_str = f"{enhanced_pct:.1f}%" if pd.notna(enhanced_pct) else "—"
                model_str    = f"{model_pct:.1f}%"   if pd.notna(model_pct)    else "—"
                lift_str     = f"{lift_pts:+.1f}"    if pd.notna(lift_pts)     else "—"
                conf_str     = f"{confidence:.2f}"   if pd.notna(confidence)   else "0.00"
                sg_str       = f"{avg_sg:+.2f}"      if pd.notna(avg_sg)       else "—"
                t10_str      = f"{top10_rate*100:.0f}%" if pd.notna(top10_rate) else "—"

                st.markdown(
                    f'<div style="background:#0b1929;border-radius:10px;padding:16px;'
                    f'border:1px solid #1a3050;border-top:3px solid {rc};text-align:center;">'
                    f'<div style="color:{rc};font-size:11px;font-weight:800;'
                    f'letter-spacing:1.5px;margin-bottom:8px;">{rl.upper()}</div>'
                    f'<div style="font-size:15px;font-weight:700;color:#e8eef8;margin-bottom:6px;">{name}</div>'
                    f'<div style="font-size:28px;font-weight:900;color:#00c44f;line-height:1;">{enhanced_str}</div>'
                    f'<div style="color:#5a7a9a;font-size:11px;margin-bottom:10px;">Enhanced Fit</div>'
                    f'<div style="border-top:1px solid #1a3050;padding-top:8px;display:flex;'
                    f'justify-content:space-between;font-size:12px;color:#9fb0c7;">'
                    f'<span>Model: <b style="color:#dde6f5">{model_str}</b></span>'
                    f'<span>Lift: <b style="color:#dde6f5">{lift_str}</b></span>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;font-size:11px;'
                    f'color:#9fb0c7;margin-top:4px;">'
                    f'<span>Starts: <b style="color:#dde6f5">{starts}</b></span>'
                    f'<span>Conf: <b style="color:#dde6f5">{conf_str}</b></span>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;font-size:11px;'
                    f'color:#9fb0c7;margin-top:4px;">'
                    f'<span>Avg SG: <b style="color:#dde6f5">{sg_str}</b></span>'
                    f'<span>Top-10: <b style="color:#dde6f5">{t10_str}</b></span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
    elif "dg_fit_total" in df.columns:
        st.markdown("#### 🎯 Best Course Fits")
        st.caption("Players whose game best matches this course (model-only fallback).")

        _rank_colors2 = ["#FFD700", "#C0C0C0", "#CD7F32"]
        _rank_labels2 = ["1st", "2nd", "3rd"]

        top3_fits = df.nlargest(3, "dg_fit_total")
        fit_cols = st.columns(3)

        for i, (_, player) in enumerate(top3_fits.iterrows()):
            with fit_cols[i]:
                name      = player.get("player_name", "Unknown")[:18]
                fit_total = float(player.get("dg_fit_total", 0) or 0)
                fit_str   = f"{fit_total:+.2f}"
                ott_fit   = float(player.get("dg_fit_ott",  0) or 0)
                app_fit   = float(player.get("dg_fit_app",  0) or 0)
                arg_fit   = float(player.get("dg_fit_arg",  0) or 0)
                putt_fit  = float(player.get("dg_fit_putt", 0) or 0)

                rc  = _rank_colors2[i]
                rl  = _rank_labels2[i]
                ott_c  = "#00c44f" if ott_fit  >= 0 else "#e53935"
                app_c  = "#00c44f" if app_fit  >= 0 else "#e53935"
                arg_c  = "#00c44f" if arg_fit  >= 0 else "#e53935"
                putt_c = "#00c44f" if putt_fit >= 0 else "#e53935"

                st.markdown(
                    f'<div style="background:#0b1929;border-radius:10px;padding:16px;'
                    f'border:1px solid #1a3050;border-top:3px solid {rc};text-align:center;">'
                    f'<div style="color:{rc};font-size:11px;font-weight:800;'
                    f'letter-spacing:1.5px;margin-bottom:8px;">{rl.upper()}</div>'
                    f'<div style="font-size:15px;font-weight:700;color:#e8eef8;margin-bottom:6px;">{name}</div>'
                    f'<div style="font-size:28px;font-weight:900;color:#00c44f;line-height:1;">{fit_str}</div>'
                    f'<div style="color:#5a7a9a;font-size:11px;margin-bottom:10px;">Course Fit Score</div>'
                    f'<div style="border-top:1px solid #1a3050;padding-top:8px;'
                    f'display:grid;grid-template-columns:repeat(4,1fr);gap:4px;">'
                    f'<div><div style="font-size:13px;font-weight:700;color:{ott_c};">{ott_fit:+.1f}</div>'
                    f'<div style="font-size:9px;color:#3a5270;">OTT</div></div>'
                    f'<div><div style="font-size:13px;font-weight:700;color:{app_c};">{app_fit:+.1f}</div>'
                    f'<div style="font-size:9px;color:#3a5270;">APP</div></div>'
                    f'<div><div style="font-size:13px;font-weight:700;color:{arg_c};">{arg_fit:+.1f}</div>'
                    f'<div style="font-size:9px;color:#3a5270;">ARG</div></div>'
                    f'<div><div style="font-size:13px;font-weight:700;color:{putt_c};">{putt_fit:+.1f}</div>'
                    f'<div style="font-size:9px;color:#3a5270;">PUTT</div></div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

    # --- Course Fit Score ranked table ---
    _cf_cols = ["dg_fit_total", "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt"]
    _cf_available = [c for c in _cf_cols if c in df.columns]
    if "dg_fit_total" in df.columns:
        st.markdown("#### Course Fit Rankings")
        st.caption("How well each player's game matches this course. Positive = strength at this venue.")

        _cf_df = df[["player_name"] + _cf_available].copy()
        for c in _cf_available:
            _cf_df[c] = pd.to_numeric(_cf_df[c], errors="coerce")
        _cf_df = _cf_df.sort_values("dg_fit_total", ascending=False).reset_index(drop=True)
        _cf_df.insert(0, "#", range(1, len(_cf_df) + 1))

        _cf_rename = {
            "player_name": "Player",
            "dg_fit_total": "Total",
            "dg_fit_ott": "OTT",
            "dg_fit_app": "APP",
            "dg_fit_arg": "ARG",
            "dg_fit_putt": "PUTT",
        }
        _cf_df = _cf_df.rename(columns={k: v for k, v in _cf_rename.items() if k in _cf_df.columns})

        _fit_stat_cols = [c for c in ["Total", "OTT", "APP", "ARG", "PUTT"] if c in _cf_df.columns]
        _max_abs = max((_cf_df[_fit_stat_cols].abs().max().max() or 0.01), 0.01)

        def _fit_cell(val):
            if pd.isna(val):
                return "color:#3a4a5a"
            v = float(val)
            intensity = min(abs(v) / _max_abs, 1.0)
            if v > 0:
                g = int(60 + intensity * 140)
                return f"background-color:rgba(0,{g},40,0.25);color:#{'00c44f' if v > _max_abs * 0.5 else '6ddb9a'};font-weight:{'700' if v > _max_abs * 0.7 else '400'}"
            else:
                r = int(60 + intensity * 140)
                return f"background-color:rgba({r},20,20,0.25);color:#{'e53935' if abs(v) > _max_abs * 0.5 else 'c47070'}"

        _styled_cf = (
            _cf_df.style
            .applymap(_fit_cell, subset=_fit_stat_cols)
            .format({c: lambda x: f"{x:+.3f}" if pd.notna(x) else "—" for c in _fit_stat_cols})
        )
        st.dataframe(_styled_cf, hide_index=True, use_container_width=True, height=480)



# ============================================================================
# SIDEBAR
# ============================================================================

# Sidebar header
st.sidebar.markdown("## ⛳ Golf Fantasy")
st.sidebar.markdown("---")

# Navigation
# Group: Weekly workflow (top), then tools, then admin
page = st.sidebar.radio(
    "📍 Navigation",
    [
        "🏆 This Week",
        "📋 My Picks",
        "🎰 Betting",
        "🔴 Live",
        "👤 Players",
        "📊 Predictions",
        "💬 Assistant",
    ],
    label_visibility="collapsed"
)

# Quick stats in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### Season Stats")

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

st.sidebar.metric("Current Week", f"{_current_week} of 30")
st.sidebar.metric("Weeks Entered", _logged_weeks)
st.sidebar.metric("Season Earnings", f"${season_earnings:,.0f}")
st.sidebar.metric("Unique Players Used", len(picks))
st.sidebar.metric("Total Picks", f"{total_picks}/90")

st.sidebar.markdown("---")

# Scheduler status — last run time and success rate
try:
    import json as _sj
    _sh_path = Path("logs/scheduler_history.json")
    if _sh_path.exists():
        with open(_sh_path) as _f:
            _sh = _sj.load(_f)
        if _sh:
            _last = _sh[-1]
            _last_ts = _last.get("timestamp", "")[:16].replace("T", " ")
            _ok = _last.get("success_count", 0)
            _total = _last.get("total_count", 0)
            _all_ok = _ok == _total
            _status_icon = "🟢" if _all_ok else "🟡"
            st.sidebar.caption(f"{_status_icon} Scheduler: {_last_ts} · {_ok}/{_total} tasks OK")
except Exception:
    pass

st.sidebar.caption(f"Dashboard loaded: {datetime.now().strftime('%b %d %H:%M')}")


# ============================================================================
# PAGE: THIS WEEK (consolidated from Strategy Dashboard + This Week + Scoring Engine)
# ============================================================================

_tw_teams_tab  = None
_team_pred_path = None
_is_team_event  = False

if page == "🏆 This Week":

    engine = load_scoring_engine(_scoring_engine_cache_key())
    _tw_pr_tab = _tw_tt_tab = _tw_tools_tab = _tw_wd_tab = _tw_opt_tab = _tw_pool_tab = _tw_teams_tab = None  # filled when tournament loads
    _team_pred_path = None
    _is_team_event  = False

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
            
            
            
            
            # ── At-a-Glance data (deferred render — needs _field_id resolved first) ──
            _gl_tracker_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"

            # 3. Top recommended bet (highest edge_pts) — no _field_id dependency
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

            # 4. Season standing — no _field_id dependency
            _gl_rank_label = "—"
            _gl_earnings_label = ""
            _gl_back_label = ""
            _gl_standings_path = DATA_DIR / "fantasy" / "league_standings.csv"
            if _gl_standings_path.exists():
                try:
                    _gl_st = pd.read_csv(_gl_standings_path)
                    _gl_me = _gl_st[_gl_st["team_name"] == "WineTime"]
                    if not _gl_me.empty:
                        _gl_rank_label    = f"{_gl_me.iloc[0]['place']} of {len(_gl_st)}"
                        _gl_earnings_label = str(_gl_me.iloc[0].get("earnings", ""))
                        _back_num = _gl_me.iloc[0].get("earnings_back_num", 0)
                        try:
                            _back_num = float(_back_num)
                            _gl_back_label = f"${_back_num/1_000_000:.2f}M behind" if _back_num > 0 else "Leading"
                        except Exception:
                            _gl_back_label = str(_gl_me.iloc[0].get("earnings_back", ""))
                except Exception:
                    pass

            # ── Odds last-updated caption (no manual refresh button — scheduler handles it) ──
            _preds_check = OUTPUTS_DIR / "latest_predictions.csv"
            if _preds_check.exists():
                try:
                    _last_odds = pd.read_csv(_preds_check, usecols=["odds_updated_at"]).iloc[0, 0]
                    st.caption(f"Odds updated: {_last_odds}")
                except Exception:
                    import os as _os_cap
                    from datetime import datetime as _dt_cap
                    _mtime = _dt_cap.fromtimestamp(_os_cap.path.getmtime(_preds_check)).strftime("%b %d %H:%M")
                    st.caption(f"Predictions updated: {_mtime}")

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
            _gl_meta_path = None
            _gl_lb_path   = None
            if _field_id:
                _gl_meta_path = DATA_DIR / "live" / f"leaderboard_{_field_id.lower()}_meta.json"
                _gl_lb_path   = DATA_DIR / "live" / f"leaderboard_{_field_id.lower()}.csv"

            # 1. Round status — needs _gl_meta_path
            _gl_round_label  = "Pre-Tournament"
            _gl_status_label = "Not started"
            _gl_status_color = "#4a6080"
            if _gl_meta_path and Path(_gl_meta_path).exists():
                try:
                    _gl_meta = json.loads(Path(_gl_meta_path).read_text())
                    _gl_rnum = int(_gl_meta.get("current_round", 0))
                    _gl_rs   = _gl_meta.get("round_status", "")
                    _gl_rs_lower = _gl_rs.lower()
                    if _gl_rnum > 0:
                        _gl_round_label = f"Round {_gl_rnum} of 4"
                    # PGA Tour API uses "R1"/"R2" etc. for active rounds; also handle verbose strings
                    _is_active = (
                        "progress" in _gl_rs_lower
                        or (_gl_rs_lower.startswith("r") and _gl_rs_lower[1:].isdigit())
                    )
                    _is_done = any(x in _gl_rs_lower for x in ("official", "complete", "final"))
                    if _gl_rnum > 0 and _is_active:
                        _gl_status_label = f"Round {_gl_rnum} In Progress"
                    elif _gl_rnum > 0 and _is_done:
                        _gl_status_label = f"Round {_gl_rnum} Official"
                    else:
                        _gl_status_label = _gl_rs or "Scheduled"
                    _gl_status_color = (
                        "#00c44f" if _is_active
                        else "#ffa726" if _is_done
                        else "#4a6080"
                    )
                except Exception:
                    pass

            # 2. My picks + live positions — needs _gl_lb_path
            _gl_picks_html = "<span style='color:#4a6080;font-size:11px;'>No picks yet — enter on fantasy site then sync</span>"
            if _gl_tracker_path.exists():
                try:
                    _gl_td     = json.loads(_gl_tracker_path.read_text())
                    _gl_wks    = _gl_td.get("weekly_lineups", {})
                    _cur_week_key = f"week_{t.week}" if hasattr(t, "week") else None
                    _gl_cur   = _gl_wks.get(_cur_week_key, {}) if _cur_week_key else {}
                    _gl_lineup = _gl_cur.get("lineup", [])
                    # Fallback: match by tournament name in case week number differs
                    if not _gl_lineup and tournament:
                        for _wk_entry in _gl_wks.values():
                            _wk_t = _wk_entry.get("tournament", _wk_entry.get("tournament_name", ""))
                            if _wk_t.lower().strip() == tournament.lower().strip():
                                _gl_lineup = _wk_entry.get("lineup", [])
                                break
                    _gl_lb_df  = pd.read_csv(_gl_lb_path) if (_gl_lb_path and Path(_gl_lb_path).exists()) else pd.DataFrame()
                    _gl_parts  = []
                    for _gp in _gl_lineup:
                        _last = _gp.strip().split()[-1].lower()
                        if not _gl_lb_df.empty:
                            _m = _gl_lb_df[_gl_lb_df["player_name"].str.lower().str.contains(_last, na=False)]
                            if not _m.empty:
                                _mr = _m.iloc[0]
                                _pos  = str(_mr.get("position", "?"))
                                _tot  = _mr.get("total", "?")
                                _p_color = "#00c44f" if _pos.lstrip("T").isdigit() and int(_pos.lstrip("T")) <= 10 else "#dde6f5"
                                _gl_parts.append(
                                    f"<span style='color:#00c44f;font-weight:700'>{_last.title()}</span>"
                                    f" <span style='color:{_p_color}'>{_pos} ({_tot})</span>"
                                )
                                continue
                        _gl_parts.append(f"<span style='color:#dde6f5'>{_last.title()}</span>")
                    if _gl_parts:
                        _gl_picks_html = "<br>".join(_gl_parts)
                except Exception:
                    pass

            # ── Render at-a-glance strip ─────────────────────────────────
            st.markdown(
                f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:12px;"
                f"margin:12px 0 16px;padding:16px;background:#0b1929;border:1px solid #1a3050;border-radius:10px;'>"
                f"<div><div style='font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;'>ROUND STATUS</div>"
                f"<div style='font-size:16px;font-weight:800;color:#dde6f5;'>{_gl_round_label}</div>"
                f"<div style='font-size:12px;color:{_gl_status_color};font-weight:600;'>{_gl_status_label}</div></div>"
                f"<div><div style='font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;'>MY PICKS</div>"
                f"<div style='font-size:13px;line-height:1.6;'>{_gl_picks_html}</div></div>"
                f"<div><div style='font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;'>TOP BET</div>"
                f"<div style='font-size:13px;font-weight:600;color:#dde6f5;'>{_gl_bet_label}</div></div>"
                f"<div><div style='font-size:10px;color:#4a6080;font-weight:600;letter-spacing:.5px;margin-bottom:4px;'>SEASON RANK</div>"
                f"<div style='font-size:16px;font-weight:800;color:#ffa726;'>{_gl_rank_label}</div>"
                f"<div style='font-size:11px;color:#4a6080;'>{_gl_earnings_label}</div>"
                f"<div style='font-size:10px;color:#3a5070;'>{_gl_back_label}</div>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

            _field_file = None
            if _field_id:
                _canonical = DATA_DIR / "fields" / f"field_{_field_id}.csv"
                if _canonical.exists():
                    _field_file = _canonical

            # ── Load WD data (used for tab badge + WD tab rendering) ─────────
            _wd_dir = DATA_DIR / "news"
            _wd_file = _wd_dir / f"withdrawals_{_field_id}.json"
            if not _wd_file.exists():
                _wd_files = sorted(_wd_dir.glob("withdrawals_R*.json"),
                                   key=lambda p: p.stat().st_mtime, reverse=True) if _wd_dir.exists() else []
                _wd_file = _wd_files[0] if _wd_files else None

            _wd_list = []
            if _wd_file and Path(_wd_file).exists():
                try:
                    with open(_wd_file) as _wdf:
                        _wd_list = json.load(_wdf)
                except Exception:
                    pass

            # ── Weather + Lineup Recommendation → rendered inside Tee Times tab (below)

            @st.cache_data(ttl=3600, show_spinner=False)
            def _run_lineup_rec():
                try:
                    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
                    from scripts.predictions.lineup_optimizer import run_optimizer
                    # Relaxed constraints so rec always returns a result
                    df, elig, imp, tname = run_optimizer(
                        top_n=45, top_combos=1, lineup_size=3,
                        min_avg_cut_prob=0.65, max_last_use_players=3,
                        min_leverage_players=0, leverage_threshold=0.65,
                        ceiling_weight=0.10, leverage_weight=0.08,
                        risk_weight=0.20, usage_weight=1.00,
                        last_use_penalty=15000,
                        locked_players=[], excluded_players=[], verbose=False,
                    )
                    return df, tname
                except Exception as _e:
                    return None, str(_e)

            # ── Page tabs ────────────────────────────────────────────────
            _wd_conf_count = sum(1 for w in _wd_list if w.get("status") == "WITHDRAWN")
            _wd_tab_label  = f"Withdrawals ({_wd_conf_count})" if _wd_conf_count else "Withdrawals"
            _team_pred_path = OUTPUTS_DIR / f"team_predictions_{_field_id}.csv" if _field_id else None
            _is_team_event  = bool(_team_pred_path and _team_pred_path.exists())

            if _is_team_event:
                _tw_tt_tab, _tw_teetimes_tab, _tw_pool_tab, _tw_opt_tab, _tw_wd_tab, _tw_teams_tab = st.tabs(
                    ["🏌️ Overview", "⏰ Tee Times", "📋 Player Pool", "🧮 Lineup Optimizer", _wd_tab_label, "👥 Teams"]
                )
            else:
                _tw_tt_tab, _tw_teetimes_tab, _tw_pool_tab, _tw_opt_tab, _tw_wd_tab = st.tabs(
                    ["🏌️ Overview", "⏰ Tee Times", "📋 Player Pool", "🧮 Lineup Optimizer", _wd_tab_label]
                )
                _tw_teams_tab = None
            _tw_pr_tab = None

            # ── Tournament Facts Helper ───────────────────────────────────
            def _load_tournament_facts(tid: str, name: str) -> list:
                """Return list of fact dicts for the current tournament, or []."""
                import json as _json
                facts_path = DATA_DIR / "tournament_facts" / "facts.json"
                if not facts_path.exists():
                    return []
                try:
                    data = _json.loads(facts_path.read_text())
                except Exception:
                    return []
                tid_upper = (tid or "").strip().upper()
                name_lower = (name or "").strip().lower()
                for entry in data.get("tournaments", []):
                    # Match by explicit ID first
                    if entry.get("id") and entry["id"].upper() == tid_upper:
                        return entry.get("facts", [])
                    # Then match by name pattern
                    for pat in entry.get("name_patterns", []):
                        if pat.lower() in name_lower:
                            return entry.get("facts", [])
                return []

            def _generate_dynamic_facts(preds_df: pd.DataFrame, current_tid: str = "") -> list:
                """Generate field-specific facts from latest_predictions.csv.
                Only runs if the predictions are for the current tournament.
                """
                dyn = []
                if preds_df is None or preds_df.empty:
                    return dyn
                try:
                    df = preds_df.copy()

                    # Guard: only use if predictions match the current tournament
                    if "tournament_id" in df.columns and current_tid:
                        tid_in_df = str(df["tournament_id"].iloc[0]).strip().upper()
                        if tid_in_df != current_tid.strip().upper():
                            return dyn  # stale predictions — wrong tournament

                    # Guard: drop rows with placeholder/invalid odds (e.g. +100000)
                    if "odds_to_win" in df.columns:
                        odds_num = pd.to_numeric(df["odds_to_win"], errors="coerce")
                        df = df[odds_num.isna() | (odds_num.abs() < 50000)].copy()

                    # ── OWGR Top-25 bubble fact ──────────────────────────────
                    if "world_rank" in df.columns and "odds_to_win" in df.columns:
                        wr = pd.to_numeric(df["world_rank"], errors="coerce")
                        odds_raw = pd.to_numeric(df["odds_to_win"], errors="coerce")
                        top25 = df[wr <= 25]
                        top25_count = len(top25)
                        # Player closest to rank 25 (on the inside)
                        bubble = df[(wr >= 20) & (wr <= 30)].copy()
                        bubble["_wr"] = pd.to_numeric(bubble["world_rank"], errors="coerce")
                        bubble = bubble.sort_values("_wr")
                        if not bubble.empty and top25_count > 0:
                            b_row = bubble.iloc[-1]  # highest rank (worst) inside top-25
                            b_name = str(b_row.get("player_name", "")).replace(", ", " ").title()
                            b_wr = int(b_row["_wr"]) if pd.notna(b_row["_wr"]) else "?"
                            b_odds = b_row.get("odds_to_win")
                            b_odds_str = ""
                            if b_odds and pd.notna(b_odds):
                                try:
                                    bv = int(float(b_odds))
                                    b_odds_str = f" (+{bv})" if bv > 0 else f" ({bv})"
                                except Exception:
                                    pass
                            dyn.append({
                                "stat": f"{top25_count} players",
                                "detail": f"{top25_count} players in this week's field are ranked inside the OWGR Top 25. Historical data shows every Masters winner since 2013 came from this group. {b_name}{b_odds_str} is on the bubble at world rank #{b_wr}.",
                            })

                    # ── Longest shot / lowest world rank in field ────────────
                    if "world_rank" in df.columns and "odds_to_win" in df.columns:
                        wr2 = pd.to_numeric(df["world_rank"], errors="coerce")
                        # Only include players with real odds and rank <= 500 (exclude exemptions/sponsors)
                        odds_valid = pd.to_numeric(df["odds_to_win"], errors="coerce")
                        longest = df[pd.notna(wr2) & (wr2 <= 500) & pd.notna(odds_valid)].copy()
                        longest["_wr2"] = wr2[longest.index]
                        longest = longest.sort_values("_wr2", ascending=False)
                        if not longest.empty:
                            lo_row = longest.iloc[0]
                            lo_name = str(lo_row.get("player_name", "")).replace(", ", " ").title()
                            lo_wr = int(lo_row["_wr2"]) if pd.notna(lo_row.get("_wr2")) else "?"
                            lo_odds = lo_row.get("odds_to_win")
                            lo_odds_str = ""
                            if lo_odds and pd.notna(lo_odds):
                                try:
                                    lv = int(float(lo_odds))
                                    lo_odds_str = f"+{lv}" if lv > 0 else str(lv)
                                except Exception:
                                    pass
                            dyn.append({
                                "stat": lo_odds_str or f"WR #{lo_wr}",
                                "detail": f"{lo_name} (world rank #{lo_wr}) is the lowest-ranked qualifier in this week's field{(' at ' + lo_odds_str) if lo_odds_str else ''}. Historically, players outside the top 100 in the world rarely contend at major venues like Augusta National.",
                            })

                    # ── Par-5 scoring leader in the field ────────────────────
                    if "par5_scoring_val" in df.columns and "par5_scoring_field_rank" in df.columns:
                        p5 = df.copy()
                        p5["_p5r"] = pd.to_numeric(p5["par5_scoring_field_rank"], errors="coerce")
                        p5["_p5v"] = pd.to_numeric(p5["par5_scoring_val"], errors="coerce")
                        p5 = p5[p5["_p5r"] == 1].dropna(subset=["_p5v"])
                        if not p5.empty:
                            p5_row = p5.iloc[0]
                            p5_name = str(p5_row.get("player_name", "")).replace(", ", " ").title()
                            p5_val = float(p5_row["_p5v"])
                            p5_sign = "+" if p5_val >= 0 else ""
                            dyn.append({
                                "stat": f"{p5_sign}{p5_val:.2f} SG",
                                "detail": f"{p5_name} leads this week's field in Par-5 scoring at {p5_sign}{p5_val:.2f} strokes gained per round. Augusta's four reachable par 5s make this the strongest predictive stat for Masters performance — 14 of the last 16 winners ranked top-40 in par-5 scoring.",
                            })

                    # ── Model favourite win probability ───────────────────────
                    if "win_prob" in df.columns and "player_name" in df.columns:
                        mdl = df.copy()
                        mdl["_wp"] = pd.to_numeric(mdl["win_prob"], errors="coerce")
                        mdl_sorted = mdl.sort_values("_wp", ascending=False).dropna(subset=["_wp"])
                        if len(mdl_sorted) >= 2:
                            mf1 = mdl_sorted.iloc[0]
                            mf2 = mdl_sorted.iloc[1]
                            mf1_name = str(mf1.get("player_name", "")).replace(", ", " ").title()
                            mf2_name = str(mf2.get("player_name", "")).replace(", ", " ").title()
                            mf1_wp = float(mf1["_wp"]) * 100
                            mf2_wp = float(mf2["_wp"]) * 100
                            mf1_odds = mf1.get("odds_to_win")
                            mf1_odds_str = ""
                            if mf1_odds and pd.notna(mf1_odds):
                                try:
                                    ov = int(float(mf1_odds))
                                    mf1_odds_str = f" ({'+' if ov > 0 else ''}{ov})"
                                except Exception:
                                    pass
                            dyn.append({
                                "stat": f"{mf1_wp:.1f}% win",
                                "detail": f"Our model gives {mf1_name}{mf1_odds_str} the highest win probability this week at {mf1_wp:.1f}%, followed by {mf2_name} at {mf2_wp:.1f}%. These probabilities are calibrated against historical outcomes — see Betting tab for value plays.",
                            })
                    # ── Augusta/Masters-specific historical field facts ────────
                    # Only fires when current tournament ends in "014" (Masters)
                    if current_tid.upper().endswith("014"):
                        try:
                            _masters_dfs = []
                            for _yr in range(2012, 2026):
                                _lp = DATA_DIR / "historical" / f"leaderboards_{_yr}.csv"
                                if not _lp.exists():
                                    continue
                                _ld = pd.read_csv(_lp, dtype=str)
                                _masters_rows = _ld[_ld["tournament_id"].str.endswith("014")].copy()
                                if not _masters_rows.empty:
                                    _masters_rows["_yr"] = _yr
                                    _masters_dfs.append(_masters_rows)

                            if _masters_dfs:
                                _mhist = pd.concat(_masters_dfs, ignore_index=True)
                                _mhist["to_par_num"] = pd.to_numeric(_mhist["to_par"], errors="coerce")

                                # Per-player history at Augusta
                                _aug_exp = _mhist.groupby("player_name").agg(
                                    augusta_starts=("_yr", "count"),
                                    augusta_made_cut=("position", lambda x: sum(~x.str.contains("CUT", na=False))),
                                    augusta_top5=("position", lambda x: sum(x.isin(["1","2","3","4","5","T2","T3","T4","T5"]))),
                                    augusta_wins=("position", lambda x: sum(x == "1")),
                                    augusta_avg_par=("to_par_num", "mean"),
                                ).reset_index()

                                # Match against current field players
                                _field_names = df["player_name"].dropna().tolist() if "player_name" in df.columns else []

                                def _nkey(n):
                                    # normalize: "Last, First" → "first last", handle both directions
                                    n = str(n).strip().lower()
                                    if "," in n:
                                        parts = n.split(",", 1)
                                        n = parts[1].strip() + " " + parts[0].strip()
                                    return n

                                _aug_exp["_nkey"] = _aug_exp["player_name"].apply(_nkey)
                                _field_nkeys = {_nkey(n): n for n in _field_names}

                                _matched = _aug_exp[_aug_exp["_nkey"].isin(_field_nkeys)].copy()

                                if not _matched.empty:
                                    # Fact: how many field players have 3+ prior Masters starts
                                    _veterans = _matched[_matched["augusta_starts"] >= 3]
                                    _vet_count = len(_veterans)
                                    _total_field = len(_field_names)
                                    if _vet_count > 0:
                                        # Top veteran by avg to-par (best Augusta performer in field)
                                        _best_aug = _matched[_matched["augusta_starts"] >= 2].sort_values(
                                            "augusta_avg_par"
                                        )
                                        if not _best_aug.empty:
                                            _ba = _best_aug.iloc[0]
                                            _ba_name = str(_field_nkeys.get(_ba["_nkey"], _ba["player_name"])).title()
                                            _ba_starts = int(_ba["augusta_starts"])
                                            _ba_avg = float(_ba["augusta_avg_par"])
                                            _ba_sign = "+" if _ba_avg > 0 else ""
                                            dyn.append({
                                                "stat": f"{_ba_sign}{_ba_avg:.1f} avg",
                                                "detail": f"{_ba_name} has the best Augusta track record in this field — averaging {_ba_sign}{_ba_avg:.1f} to par over {_ba_starts} starts. Course history matters at Augusta more than almost anywhere else on Tour.",
                                            })

                                    # Fact: veterans (3+ starts) vs newcomers in field
                                    _newcomers = _total_field - len(_matched[_matched["augusta_starts"] >= 1])
                                    if _newcomers > 0 and _vet_count > 0:
                                        dyn.append({
                                            "stat": f"{_vet_count} vets",
                                            "detail": f"{_vet_count} players in this field have 3+ prior Masters starts — Augusta experience that 8 of the last 13 Masters champions had before they won. {_newcomers} players in the field have never played Augusta before.",
                                        })

                        except Exception:
                            pass

                except Exception:
                    pass
                return dyn

            def _render_stat_card(stat: str, detail: str):
                """Render a single dark fact card (reusable)."""
                import html as _html
                st.markdown(
                    f"""<div style="background:#0d1117;border:1px solid #1e3a2f;border-radius:10px;padding:18px 16px 14px;min-height:130px;display:flex;flex-direction:column;justify-content:space-between;margin-bottom:0px">
  <div style="font-size:1.9em;font-weight:800;color:#00c44f;line-height:1.1;margin-bottom:10px">{_html.escape(stat)}</div>
  <div style="font-size:0.82em;color:#b0c4d8;line-height:1.5">{_html.escape(detail)}</div>
</div>""",
                    unsafe_allow_html=True,
                )

            def _render_tournament_facts(tid: str, name: str, preds_df: pd.DataFrame = None):
                """Render dark stat cards: curated historical facts + dynamic field facts."""
                curated = _load_tournament_facts(tid, name)
                dynamic = _generate_dynamic_facts(preds_df, current_tid=tid) if preds_df is not None else []
                all_facts = curated + dynamic
                if not all_facts:
                    return
                st.markdown("#### Tournament Intel")
                if curated:
                    # Curated historical facts in rows of 3
                    for _fi in range(0, len(curated), 3):
                        _fcols = st.columns(min(3, len(curated) - _fi))
                        for _fj, _fcol in enumerate(_fcols):
                            _fact = curated[_fi + _fj]
                            with _fcol:
                                _render_stat_card(_fact.get("stat", ""), _fact.get("detail", ""))
                if dynamic:
                    if curated:
                        st.markdown("**This week's field**")
                    # Dynamic field facts in rows of 2
                    for _fi in range(0, len(dynamic), 2):
                        _dcols = st.columns(min(2, len(dynamic) - _fi))
                        for _fj, _dcol in enumerate(_dcols):
                            _fact = dynamic[_fi + _fj]
                            with _dcol:
                                _render_stat_card(_fact.get("stat", ""), _fact.get("detail", ""))

            # ── Weather + Lineup Recommendation (Tee Times tab only) ─────
            with _tw_tt_tab:
                render_weather_widget(t.course or tournament, tid=str(_field_id))
                st.markdown("---")
                _facts_preds = pd.read_csv(OUTPUTS_DIR / "latest_predictions.csv") if (OUTPUTS_DIR / "latest_predictions.csv").exists() else None
                _render_tournament_facts(str(_field_id), tournament, preds_df=_facts_preds)
                st.markdown("---")
                st.markdown("### This Week's Lineup Recommendation")
                st.caption("Model's top 3 picks for this week — balanced mode, usage-aware.")
                with st.spinner("Loading lineup recommendation..."):
                    _rec_df, _rec_tname = _run_lineup_rec()

                if _rec_df is not None and not _rec_df.empty:
                    _rec_row = _rec_df.iloc[0]
                    _rec_picks = [str(_rec_row.get(f"pick{i}", "")).strip() for i in range(1, 4) if str(_rec_row.get(f"pick{i}", "")).strip()]
                    _rec_preds = pd.read_csv(OUTPUTS_DIR / "latest_predictions.csv") if (OUTPUTS_DIR / "latest_predictions.csv").exists() else pd.DataFrame()

                    # Rank lookup
                    _rec_sorted = _rec_preds.sort_values("win_prob", ascending=False).reset_index(drop=True) if not _rec_preds.empty else pd.DataFrame()

                    _pick_labels = ["#1 PICK", "#2 PICK", "#3 PICK"]
                    _pick_colors = ["#00c44f", "#4cb8ff", "#f59e0b"]
                    _lc1, _lc2, _lc3 = st.columns(3)
                    for _ci, (_col, _pick) in enumerate(zip([_lc1, _lc2, _lc3], _rec_picks)):
                        _ev_val = float(pd.to_numeric(_rec_row.get(f"ev{_ci + 1}", 0), errors="coerce") or 0)
                        _uses_val = int(pd.to_numeric(_rec_row.get(f"uses{_ci + 1}", 3), errors="coerce") or 0)
                        _uses_pips = "●" * _uses_val + "○" * (3 - _uses_val)
                        _color = _pick_colors[_ci]

                        _wp = _t10 = _sg = _wr = _ft = _hot = None
                        _top_reason = ""
                        if not _rec_preds.empty:
                            _pm = _rec_preds[_rec_preds["player_name"].apply(_name_key) == _name_key(_pick)]
                            if not _pm.empty:
                                _pr = _pm.iloc[0]
                                _wp = float(_pr.get("win_prob", 0) or 0)
                                _t10 = float(_pr.get("top10_prob", 0) or 0)
                                _sg = float(_pr.get("season_sg_total", 0) or 0)
                                _wr = _pr.get("world_rank")
                                _ft = float(_pr.get("form_trend", 0) or 0)
                                _hot = float(_pr.get("hot_hand_score", 0) or 0)
                                if _ft > 0.3:
                                    _top_reason = f"🔥 Hot form ({_hot:.0f}/10)"
                                elif _sg > 1.0:
                                    _top_reason = f"Elite SG:Total +{_sg:.2f}"
                                elif _hot >= 7:
                                    _top_reason = f"Hot hand {_hot:.0f}/10"
                                else:
                                    _top_reason = f"SG:Total {_sg:+.2f}"

                        _mrank = None
                        if not _rec_sorted.empty:
                            _rm = _rec_sorted[_rec_sorted["player_name"].apply(_name_key) == _name_key(_pick)]
                            if not _rm.empty:
                                _mrank = int(_rm.index[0]) + 1

                        with _col:
                            st.markdown(
                                f"""<div style="border:1px solid {_color}33;border-radius:10px;padding:16px 14px 12px;background:linear-gradient(160deg,{_color}0d 0%,#0d1b2a 100%)">
  <div style="font-size:0.68em;font-weight:700;color:{_color};letter-spacing:0.12em;margin-bottom:4px">{_pick_labels[_ci]}</div>
  <div style="font-size:1.18em;font-weight:700;color:#e8f0f8;margin-bottom:10px">{_pick}</div>
  <div style="display:flex;gap:16px;margin-bottom:8px">
    <div><div style="font-size:0.68em;color:#7a9bbf;margin-bottom:1px">WIN%</div><div style="font-size:1.05em;font-weight:600;color:#e8f0f8">{f"{_wp*100:.1f}%" if _wp is not None else "—"}</div></div>
    <div><div style="font-size:0.68em;color:#7a9bbf;margin-bottom:1px">TOP-10</div><div style="font-size:1.05em;font-weight:600;color:#e8f0f8">{f"{_t10*100:.0f}%" if _t10 is not None else "—"}</div></div>
    <div><div style="font-size:0.68em;color:#7a9bbf;margin-bottom:1px">EV</div><div style="font-size:1.05em;font-weight:600;color:{_color}">${_ev_val:,.0f}</div></div>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-size:0.75em;color:#7a9bbf">{_top_reason}</div>
    <div style="font-size:0.75em;color:#7a9bbf" title="Uses remaining">{_uses_pips} {_uses_val}/3 uses</div>
  </div>
  {f'<div style="font-size:0.68em;color:#7a9bbf;margin-top:4px">Model rank #{_mrank}' + (f" · WR #{int(_wr)}" if _wr is not None and pd.notna(_wr) else "") + "</div>" if _mrank else ""}
</div>""",
                                unsafe_allow_html=True,
                            )

                    st.markdown("")
                    _meta_c, _btn_c = st.columns([3, 1])
                    with _meta_c:
                        st.caption(
                            f"Lineup score ${float(_rec_row.get('score', 0)):,.0f} · "
                            f"Avg cut {float(_rec_row.get('avg_cut_prob', 0)):.1f}% · "
                            f"Any top-5 {float(_rec_row.get('p_top5_any', 0)):.1f}%"
                        )
                    with _btn_c:
                        if st.button("➕ Use These Picks", key="rec_save_picks", type="primary", use_container_width=True):
                            st.session_state["_prefill_picks"] = _rec_picks
                            st.info(f"Pre-filled: {', '.join(_rec_picks)} — confirm in My Picks → Add Picks.")
                else:
                    st.caption("Run the full pipeline first to generate predictions.")

                st.markdown("---")

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
                with _tw_tt_tab:
                    st.markdown("#### Course Layout")
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
            # Load draw advantage + dedicated tee times CSVs
            _da_df = pd.DataFrame()
            _da_round = 1
            _tt_draw_df = pd.DataFrame()
            _tt_draw_round = None
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
                            _tt_draw_round = _r
                            break
                        except Exception:
                            pass

            # Build _tt_valid: priority order:
            #   1. DG field CSV (dg_field_latest.csv) — most accurate tee times
            #   2. Dedicated tee_times_{tid}_r{n}.csv
            #   3. Leaderboard CSV tee_time column (fallback)
            _tt_valid = pd.DataFrame()
            _tt_draw_round = None
            # Prefer tournament-specific file (avoids stale upcoming-week data in dg_field_latest.csv)
            _dg_field_path = DATA_DIR / "datagolf" / f"dg_field_{_field_id}.csv"
            if not _dg_field_path.exists():
                _dg_field_path = DATA_DIR / "datagolf" / "dg_field_latest.csv"
            if _dg_field_path.exists():
                try:
                    _dg_fld = pd.read_csv(_dg_field_path)
                    _dg_fld["player_name"] = _dg_fld["player_name"].apply(
                        lambda n: (lambda p: f"{p[1].strip()} {p[0].strip()}")(n.split(",", 1))
                        if "," in str(n) else str(n)
                    )
                    _cur_rnd = int(_dg_fld["current_round"].iloc[0]) if "current_round" in _dg_fld.columns and pd.notna(_dg_fld["current_round"].iloc[0]) else 1
                    _tt_col  = f"r{_cur_rnd}_teetime"
                    if _tt_col in _dg_fld.columns:
                        _dg_fld["tee_time"] = _dg_fld[_tt_col].astype(str).str.strip()
                        if "start_tee" not in _dg_fld.columns and f"r{_cur_rnd}_starthole" in _dg_fld.columns:
                            _dg_fld["start_tee"] = _dg_fld[f"r{_cur_rnd}_starthole"]
                        _tt_valid = _dg_fld[_dg_fld["tee_time"].notna() & _dg_fld["tee_time"].ne("") & _dg_fld["tee_time"].ne("nan")].copy()
                        _tt_draw_round = _cur_rnd
                except Exception:
                    pass

            if _tt_valid.empty and not _tt_draw_df.empty and "tee_time_str" in _tt_draw_df.columns:
                _tt_valid = _tt_draw_df.copy()
                _tt_valid["tee_time"] = _tt_valid["tee_time_str"]

            if _tt_valid.empty:
                try:
                    _tt_files = sorted(
                        (DATA_DIR / "live").glob("leaderboard_r*.csv"),
                        key=lambda p: p.stat().st_mtime, reverse=True
                    ) if (DATA_DIR / "live").exists() else []
                    if _tt_files:
                        _tt_df = pd.read_csv(_tt_files[0])
                        if "tee_time" in _tt_df.columns and _tt_df["tee_time"].notna().any():
                            _tt_valid = _tt_df[_tt_df["tee_time"].astype(str).str.strip().ne("")].copy()
                except Exception:
                    pass








        # ── DataGolf Model Comparison ─────────────────────────────────────
        # Prefer DB (dg_pre_tournament), fall back to old CSV if DB has no rows
        _dg_comp = None
        try:
            import duckdb as _duckdb
            with _duckdb.connect(str(DATA_DIR / "golf_data.db"), read_only=True) as _dbc:
                _dg_comp = _dbc.execute(
                    "SELECT player_name, win AS dg_win_prob, top_10 AS dg_top10_prob "
                    "FROM dg_pre_tournament WHERE model='baseline_history_fit'"
                ).df()
        except Exception:
            pass
        if (_dg_comp is None or _dg_comp.empty):
            # Try tournament-scoped CSV first, then latest
            _dg_pred_path = DATA_DIR / "datagolf" / f"dg_pre_tournament_{str(_field_id)}.csv"
            if not _dg_pred_path.exists():
                _dg_pred_path = DATA_DIR / "datagolf" / "dg_pre_tournament_latest.csv"
            if _dg_pred_path.exists():
                _dg_raw = pd.read_csv(_dg_pred_path)
                _dg_comp = (
                    _dg_raw[_dg_raw["model"] == "baseline_history_fit"]
                    [["player_name", "win", "top_10"]]
                    .rename(columns={"win": "dg_win_prob", "top_10": "dg_top10_prob"})
                    .reset_index(drop=True)
                )
        if _dg_comp is not None and not _dg_comp.empty and not _preds.empty:
            with _tw_tt_tab:
                with st.expander("📊 Model vs DataGolf", expanded=False):
                    try:
                        _dg_comp["_nkey"] = _dg_comp["player_name"].apply(_name_key)

                        _our = _preds[["player_name", "win_prob", "top10_prob", "top20_prob"]].copy()
                        _our["_nkey"] = _our["player_name"].apply(_name_key)
                        _our = _our.sort_values("win_prob", ascending=False).reset_index(drop=True)
                        _our["our_rank"] = _our.index + 1

                        _dg_sorted = _dg_comp.sort_values("dg_win_prob", ascending=False).reset_index(drop=True)
                        _dg_sorted["dg_rank"] = _dg_sorted.index + 1

                        _merged = _our.merge(_dg_sorted[["_nkey", "dg_rank", "dg_win_prob", "dg_top10_prob"]],on="_nkey", how="left")
                        _merged["rank_diff"] = _merged["our_rank"] - _merged["dg_rank"]  # negative = we ratehigher

                        # Show top 20 by our model
                        _disp = _merged.head(20).copy()
                        _disp["Our Win%"]  = (_disp["win_prob"] * 100).round(1)
                        _disp["DG Win%"]   = (_disp["dg_win_prob"] * 100).round(1)
                        _disp["Our T10%"]  = (_disp["top10_prob"] * 100).round(1)
                        _disp["DG T10%"]   = (_disp["dg_top10_prob"] * 100).round(1)

                        def _diff_label(d):
                            if pd.isna(d): return "—"
                            d = int(d)
                            if d < -5: return f"↑ +{abs(d)}"   # we rank much higher
                            if d > 5:  return f"↓ -{abs(d)}"   # DG ranks higher
                            return f"~{d:+d}"

                        st.caption("Our model vs DataGolf's baseline+history model. Big gaps = divergence worth investigating.")
                        _cmp_parts = ["""
<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr 1fr;
     gap:0;font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.05em;
     padding:4px 10px;border-bottom:1px solid #0e1e30;margin-bottom:4px;">
  <div>PLAYER</div><div style="text-align:center;">OUR#</div><div style="text-align:center;">DG#</div>
  <div style="text-align:center;">Δ</div><div style="text-align:center;">OUR WIN</div><div style="text-align:center;">DG WIN</div>
</div>"""]
                        for _, _cr in _disp.iterrows():
                            _pn_cmp = str(_cr["player_name"]).split(",")[0].strip()
                            _our_r  = int(_cr["our_rank"]) if pd.notna(_cr.get("our_rank")) else "—"
                            _dg_r   = int(_cr["dg_rank"]) if pd.notna(_cr.get("dg_rank")) else "—"
                            _rd     = _cr.get("rank_diff")
                            _our_w  = f"{_cr['Our Win%']:.1f}%" if pd.notna(_cr.get("Our Win%")) else "—"
                            _dg_w   = f"{_cr['DG Win%']:.1f}%" if pd.notna(_cr.get("DG Win%")) else "—"

                            if pd.isna(_rd):
                                _d_str, _d_col, _bg = "—", "#4a6080", "#0d1825"
                            elif int(_rd) < -5:
                                _d_str, _d_col, _bg = f"↑+{abs(int(_rd))}", "#00c44f", "#091a0e"
                            elif int(_rd) > 5:
                                _d_str, _d_col, _bg = f"↓{abs(int(_rd))}", "#e07070", "#1a0909"
                            else:
                                _d_str, _d_col, _bg = f"~{int(_rd):+d}", "#4a6080", "#0d1825"

                            _cmp_parts.append(
                                f"<div style='display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr 1fr;"
                                f"gap:0;background:{_bg};padding:5px 10px;border-radius:4px;margin-bottom:2px;align-items:center;'>"
                                f"<div style='font-size:12px;font-weight:600;color:#dde6f5;'>{_pn_cmp}</div>"
                                f"<div style='text-align:center;font-size:11px;color:#7aaccc;'>#{_our_r}</div>"
                                f"<div style='text-align:center;font-size:11px;color:#5a9a6a;'>#{_dg_r}</div>"
                                f"<div style='text-align:center;font-size:11px;font-weight:700;color:{_d_col};'>{_d_str}</div>"
                                f"<div style='text-align:center;font-size:11px;color:#dde6f5;'>{_our_w}</div>"
                                f"<div style='text-align:center;font-size:11px;color:#aaccdd;'>{_dg_w}</div>"
                                f"</div>"
                            )
                        st.markdown("\n".join(_cmp_parts), unsafe_allow_html=True)

                        # Divergence callout
                        _divs = _merged[_merged["rank_diff"].abs() > 10].dropna(subset=["dg_rank"]).copy()
                        if not _divs.empty:
                            st.markdown("**Biggest disagreements:**")
                            _cols = st.columns(min(3, len(_divs)))
                            for _i, (_, _drow) in enumerate(_divs.head(3).iterrows()):
                                with _cols[_i]:
                                    _dir = "We're higher" if _drow["rank_diff"] < 0 else "DG is higher"
                                    _clr = "#00c44f" if _drow["rank_diff"] < 0 else "#4cb8ff"
                                    st.markdown(
                                        f"<div style='background:#1a1a2e;border-left:3px solid {_clr};"
                                        f"padding:8px 10px;border-radius:4px;font-size:0.82rem;'>"
                                        f"<b>{_drow['player_name'].split(',')[0].strip()}</b><br>"
                                        f"<span style='color:{_clr};'>{_dir}</span><br>"
                                        f"Our #{int(_drow['our_rank'])} · DG #{int(_drow['dg_rank'])}"
                                        f"</div>", unsafe_allow_html=True
                                    )
                    except Exception as _dg_exc:
                        st.caption(f"DG comparison unavailable: {_dg_exc}")






            with _tw_teetimes_tab:
                st.markdown("#### ⏰ Tee Times")

                if _tt_valid.empty:
                    st.info("Tee times haven't been fetched yet for this week.")
                    if _field_id and st.button("Fetch Tee Times", key="fetch_tt_btn", type="primary"):
                        import subprocess as _subp
                        with st.spinner("Fetching from PGA Tour..."):
                            _fetched_round = None
                            for _rnd in [2, 1, 3, 4]:
                                _res = _subp.run(
                                    ["python3", "scripts/scrapers/fetch_tee_times.py",
                                     "--tid", str(_field_id), "--round", str(_rnd)],
                                    capture_output=True, text=True, cwd=str(PROJECT_ROOT)
                                )
                                if _res.returncode == 0 and "Saved" in _res.stdout:
                                    _fetched_round = _rnd
                                    break
                        if _fetched_round:
                            st.success(f"Fetched R{_fetched_round} tee times.")
                            st.rerun()
                        else:
                            st.error("Could not fetch tee times from PGA Tour.")
                else:
                    # Sort by UTC time if available so 7:30 AM sorts before 10:00 AM
                    _sort_col = next(
                        (c for c in ["tee_time_utc", "tee_time_local"] if c in _tt_valid.columns), None
                    )
                    if _sort_col:
                        _tt_valid = _tt_valid.sort_values(_sort_col).reset_index(drop=True)

                    # Normalized key for cross-format name matching
                    # Tee times: "First Last" · Predictions: "Last, First"
                    _tt_valid["_nkey"] = _tt_valid["player_name"].apply(_name_key)

                    # Merge model rank + form from predictions via normalized key
                    # Ranks (dg_rank/owgr_rank/tour_rank) come from DG field CSV already in _tt_valid;
                    # use predictions as fallback when the field CSV didn't load those columns.
                    if not _preds.empty and "player_name" in _preds.columns:
                        _pr = _preds.sort_values("win_prob", ascending=False).reset_index(drop=True).copy()
                        _pr["_nkey"]       = _pr["player_name"].apply(_name_key)
                        _pr["_model_rank"] = _pr.index + 1
                        _pr["_form"]       = pd.to_numeric(_pr.get("form_trend"), errors="coerce").fillna(0)
                        # Pull rank columns from predictions as fallback if not in _tt_valid
                        for _rc, _src in [("dg_rank","dg_rank"),("owgr_rank","owgr_rank"),("tour_rank","tour_rank")]:
                            if _rc not in _tt_valid.columns and _src in _pr.columns:
                                _pr[f"_fb_{_rc}"] = pd.to_numeric(_pr[_src], errors="coerce")
                        _pm_cols = [c for c in ["_nkey","_model_rank","_form",
                                                "_fb_dg_rank","_fb_owgr_rank","_fb_tour_rank"] if c in _pr.columns]
                        _tt_valid = _tt_valid.merge(_pr[_pm_cols], on="_nkey", how="left")

                    # Uses remaining from usage tracker (not in predictions)
                    _tt_uses: dict = {}
                    _usage_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
                    if _usage_path.exists():
                        try:
                            import json as _utjson
                            with open(_usage_path) as _utf:
                                _utdata = _utjson.load(_utf)
                            for _uname, _uinfo in _utdata.get("picks", {}).items():
                                _tt_uses[_name_key(_uname)] = int(_uinfo.get("remaining_uses", 3))
                        except Exception:
                            pass
                    _tt_valid["_uses"] = _tt_valid["_nkey"].apply(lambda k: _tt_uses.get(k, 3))

                    # This week's picks from usage tracker for highlighting
                    _tt_my_picks: set = set()
                    if _usage_path.exists():
                        try:
                            import json as _myjson
                            with open(_usage_path) as _myf:
                                _mydata = _myjson.load(_myf)
                            _wk_key = f"week_{t.week}" if hasattr(t, "week") else None
                            if _wk_key:
                                _wk_lineup = _mydata.get("weekly_lineups", {}).get(_wk_key, {}).get("lineup", [])
                                _tt_my_picks = {_name_key(n) for n in _wk_lineup}
                        except Exception:
                            pass

                    # Merge draw advantage
                    _has_da = not _da_df.empty and "player_name" in _da_df.columns and "draw_tier" in _da_df.columns
                    if _has_da:
                        _da_df["_nkey"] = _da_df["player_name"].apply(_name_key)
                        _da_cols = ["_nkey"] + [c for c in ["window_avg_wind", "draw_tier"] if c in _da_df.columns]
                        _tt_valid = _tt_valid.merge(_da_df[_da_cols], on="_nkey", how="left")

                    # AM/PM wind banner
                    if not _da_df.empty and "am_pm" in _da_df.columns and "window_avg_wind" in _da_df.columns:
                        _am_rows = _da_df[_da_df["am_pm"] == "AM"]["window_avg_wind"].dropna()
                        _pm_rows = _da_df[_da_df["am_pm"] == "PM"]["window_avg_wind"].dropna()
                        if not _am_rows.empty and not _pm_rows.empty:
                            _am_avg = _am_rows.mean()
                            _pm_avg = _pm_rows.mean()
                            _fav = "AM" if _am_avg < _pm_avg else "PM"
                            st.markdown(
                                f"<div style='font-size:0.82rem;margin-bottom:8px;padding:6px 10px;"
                                f"background:#1a1a2e;border-radius:6px;'>"
                                f"<span style='color:{'#00c44f' if _fav=='AM' else '#e74c3c'};font-weight:600;'>AM: {_am_avg:.0f} mph avg</span>"
                                f"<span style='color:#888;margin:0 10px;'>|</span>"
                                f"<span style='color:{'#00c44f' if _fav=='PM' else '#e74c3c'};font-weight:600;'>PM: {_pm_avg:.0f} mph avg</span>"
                                f"<span style='color:#888;margin:0 10px;'>→</span>"
                                f"<span style='color:#00c44f;font-weight:700;'>{_fav} draw favored</span> (R{_da_round})"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    # ── Grouped tee-time cards ──────────────────────────────
                    _round_label = f"R{_tt_draw_round}" if _tt_draw_round else ""
                    _pick_count  = sum(1 for n in _tt_valid["_nkey"] if n in _tt_my_picks)

                    _tier_map_tt = {
                        "Strong Adv": "++ Calm", "Adv": "+ Calm",
                        "Neutral": "~", "Disadv": "- Wind", "Strong Disadv": "-- Wind",
                    }

                    # Filter toggle
                    _tt_filter = st.radio(
                        "Show",
                        ["All players", "Eligible only (uses > 0)"],
                        horizontal=True,
                        key="tt_filter_toggle",
                        label_visibility="collapsed",
                    )
                    _tt_rows = _tt_valid.copy()
                    if _tt_filter == "Eligible only (uses > 0)":
                        _tt_rows = _tt_rows[_tt_rows["_uses"] > 0]

                    st.caption(
                        f"{len(_tt_rows)} players · {_tt_rows['tee_time'].nunique()} tee times"
                        + (f" · {_round_label} draw" if _round_label else "")
                        + (f" · ★ = your picks ({_pick_count}/3 in field)" if _tt_my_picks else "")
                    )

                    # Group by tee time (preserve sorted order)
                    _tt_groups = {}
                    for _, _row in _tt_rows.iterrows():
                        _key = str(_row["tee_time"]).strip()
                        _tt_groups.setdefault(_key, []).append(_row)

                    _cards_html_parts = []
                    for _tt_key, _tt_group_rows in _tt_groups.items():
                        # Time slot header
                        _hole_str = ""
                        if "start_tee" in _tt_rows.columns:
                            _h = _tt_group_rows[0].get("start_tee")
                            if pd.notna(_h):
                                _hole_str = f"<span style='color:#4a6080;margin-left:8px;font-size:11px;'>Hole #{int(_h)}</span>"
                        _cards_html_parts.append(
                            f"<div style='font-size:13px;font-weight:700;color:#7aaabf;letter-spacing:.06em;"
                            f"padding:8px 0 6px;margin-top:14px;border-bottom:1px solid #0e1e30;"
                            f"margin-bottom:10px;'>{_tt_key}{_hole_str}"
                            f"<span style='color:#2a4060;font-size:11px;margin-left:10px;'>"
                            f"{len(_tt_group_rows)} player{'s' if len(_tt_group_rows)!=1 else ''}</span></div>"
                        )
                        _cards_html_parts.append(
                            "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px;'>"
                        )

                        for _pr in _tt_group_rows:
                            _nk       = _pr["_nkey"]
                            _is_pick  = _nk in _tt_my_picks
                            _uses_v   = int(_pr.get("_uses", 3))
                            _pname    = str(_pr["player_name"])

                            # Determine card style
                            if _uses_v == 0:
                                _border_c = "#2a2a3a"
                                _bg_c     = "#0c0c14"
                                _name_c   = "#4a5060"
                            elif _is_pick:
                                _border_c = "#00c44f"
                                _bg_c     = "linear-gradient(135deg,#00c44f12 0%,#0d1b2a 100%)"
                                _name_c   = "#e8f8ef"
                            else:
                                _border_c = "#1a2e44"
                                _bg_c     = "#0d1825"
                                _name_c   = "#dde6f5"

                            # Model rank badge
                            _mrank  = _pr.get("_model_rank")
                            _rank_str = ""
                            if pd.notna(_mrank):
                                _rank_str = f"<span style='background:#1a2e44;color:#7aaccc;font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;'>#{int(_mrank)}</span>"

                            # Ranking columns from DG field CSV (dg_rank / owgr_rank / tour_rank)
                            def _rval(col):
                                v = _pr.get(col)
                                if v is None or (isinstance(v, float) and pd.isna(v)):
                                    v = _pr.get(f"_fb_{col}")
                                try:
                                    return int(float(v)) if v is not None and pd.notna(v) else None
                                except Exception:
                                    return None

                            _dg_r    = _rval("dg_rank")
                            _owgr_r  = _rval("owgr_rank")
                            _tour_r  = _rval("tour_rank")

                            _form_v = float(_pr.get("_form", 0) or 0)

                            # Uses pips
                            _pips = "●" * _uses_v + "○" * (3 - _uses_v)
                            _pip_color = "#00c44f" if _uses_v == 3 else ("#f59e0b" if _uses_v == 2 else ("#e07070" if _uses_v == 1 else "#3a3a4a"))

                            # Form + draw badges
                            _badge_parts = []
                            if _form_v > 0.3:
                                _badge_parts.append("<span style='background:#2a1a0a;color:#f59e0b;font-size:9px;padding:1px 4px;border-radius:3px;'>HOT</span>")
                            elif _form_v < -0.3:
                                _badge_parts.append("<span style='background:#1a0a0a;color:#e07070;font-size:9px;padding:1px 4px;border-radius:3px;'>COLD</span>")
                            if _has_da and "draw_tier" in _tt_rows.columns:
                                _dt = _pr.get("draw_tier")
                                if pd.notna(_dt) and str(_dt) in _tier_map_tt:
                                    _dv = _tier_map_tt[str(_dt)]
                                    _dc = "#00c44f" if "++" in _dv else ("#5a9a6a" if "+" in _dv else ("#e07070" if "--" in _dv else "#c07070"))
                                    _badge_parts.append(f"<span style='color:{_dc};font-size:9px;'>{_dv}</span>")
                            _badges_html = " ".join(_badge_parts)

                            def _rank_stat(val, label, color="#7ab8dd"):
                                v_str = f"#{val}" if val is not None else "—"
                                return (f'<div><div style="font-size:15px;font-weight:700;color:{color};">{v_str}</div>'
                                        f'<div style="font-size:10px;color:#4a6080;letter-spacing:.04em;">{label}</div></div>')

                            _stats_html = (
                                _rank_stat(_dg_r,   "DG",   "#5a9a6a") +
                                _rank_stat(_owgr_r, "WR",   "#7ab8dd") +
                                _rank_stat(_tour_r, "TOUR", "#9988cc")
                            )

                            _star = "★ " if _is_pick else ""
                            _top_border = "border-top:2px solid #00c44f;" if _is_pick else ""
                            _opacity = "0.45" if _uses_v == 0 else "1"
                            _fw = "700" if _is_pick else "600"
                            _card_style = f"min-width:200px;max-width:260px;flex:1;background:{_bg_c};border:1px solid {_border_c};{_top_border}border-radius:10px;padding:14px 16px;opacity:{_opacity};"
                            _name_style = f"font-size:15px;font-weight:{_fw};color:{_name_c};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:10px;"
                            _cards_html_parts.append(
                                f'<div style="{_card_style}">'
                                f'<div style="margin-bottom:6px;">{_rank_str}</div>'
                                f'<div style="{_name_style}">{_star}{_pname}</div>'
                                f'<div style="display:flex;gap:16px;margin-bottom:10px;">{_stats_html}</div>'
                                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                                f'<span style="font-size:12px;color:{_pip_color};">{_pips}</span>'
                                f'<span style="font-size:11px;">{_badges_html}</span>'
                                f'</div>'
                                f'</div>'
                            )

                        _cards_html_parts.append("</div>")  # close flex row

                    st.markdown("\n".join(_cards_html_parts), unsafe_allow_html=True)


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

    with (_tw_pool_tab if _tw_pool_tab is not None else st.container()):
                # ── SAVE banner ───────────────────────────────────────────
                if _elite_save:
                    _save_names = " · ".join(_elite_save[:5])
                    st.markdown(f"""
<div style="background:rgba(255,160,0,0.08); border:1px solid rgba(255,160,0,0.3);
     border-radius:10px; padding:12px 16px; margin:16px 0 8px 0;">
  <span style="color:#ffa000; font-weight:700; font-size:13px;">⚡ STANDARD EVENT — Save These Players for Majors & Signatures</span><br>
  <span style="color:#8a7040; font-size:12px; margin-top:4px; display:block;">{_save_names}</span>
</div>
""", unsafe_allow_html=True)

                # ── PLAYER POOL ───────────────────────────────────────────
                if not _preds.empty:
                    _pool_top_name = ""
                    try:
                        _pool_top_name = _preds.nlargest(1, "expected_value").iloc[0]["player_name"]
                    except Exception:
                        pass
                    st.markdown(f"### 🏌️ Full Player Pool — Model Rankings{f'  ·  Top: {_pool_top_name}' if _pool_top_name else ''}")
                    with st.container():
    
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
                        # Load player explanations (reload if file exists but cache is empty)
                        _expls_path = OUTPUTS_DIR / "player_explanations.csv"
                        if _expls_path.exists():
                            _expls_df = pd.read_csv(_expls_path)
                            _expls = dict(zip(_expls_df["player_name"], _expls_df["explanation"]))
                        else:
                            _expls = {}
    
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
    
                            _expl = _expls.get(_pn, "")
                            _expl_html = f'<div style="font-size:10px;color:#6a8caf;margin-top:2px;font-style:italic;">{_expl}</div>' if _expl else ""
    
                            _pool_html.append(f"""
        <div class="pool-card {_card_cls}">
          <div class="pc-rank">#{_rank_i}</div>
          <div style="flex:1;">
            <div class="pc-name">{_pn}</div>
            <div class="pc-wr">WR #{_wr_v} &nbsp;·&nbsp; {_dots} {_uses}/3</div>
            {_expl_html}
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
    
    # ── Lineup Optimizer Tab ──────────────────────────────────────────────────
    with (_tw_opt_tab if _tw_opt_tab is not None else st.container()):
                    # Season strategy is on My Picks page

                    st.divider()
                    st.caption(
                        "Prize-money-curve optimizer: scores lineups by expected prize dollars, "
                        "weighting win probability heavily to match the exponential PGA Tour payout structure."
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
                            "desc": "Higher floor: prioritizes cut safety and preserving player uses for later weeks.",
                            "top_n": 36,
                            "min_cut": 0.68,
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
                            "desc": "Best default: balances expected prize money, cut safety, and usage discipline.",
                            "top_n": 45,
                            "min_cut": 0.62,
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
                            "desc": "Ceiling focus: maximizes win upside, accepts more volatility and usage burn.",
                            "top_n": 55,
                            "min_cut": 0.55,
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
    
                    # Locked / excluded players
                    _opt_field_names = sorted(_preds["player_name"].apply(_name_key).tolist()) if not _preds.empty else []
                    _opt_display_names = sorted(_preds["player_name"].tolist()) if not _preds.empty else []
                    _lock_col, _excl_col = st.columns(2)
                    with _lock_col:
                        _opt_locked = st.multiselect(
                            "Lock players in (must include):", _opt_display_names,
                            key="opt_locked", placeholder="Pick up to 2…"
                        )
                    with _excl_col:
                        _opt_excluded = st.multiselect(
                            "Exclude players:", _opt_display_names,
                            key="opt_excluded", placeholder="Players to avoid…"
                        )
    
                    _opt_run = st.button(
                        "▶ Run Optimizer", type="primary",
                        use_container_width=True, key="opt_run_btn",
                    )
    
                    if _opt_run:
                        try:
                            sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))
                            from scripts.predictions.lineup_optimizer import run_optimizer
    
                            # Build player rank/stat lookup from predictions
                            _opt_preds_lookup = {}
                            if not _preds.empty:
                                _opt_sorted = _preds.sort_values("win_prob", ascending=False).reset_index(drop=True)
                                for _oi, _or in _opt_sorted.iterrows():
                                    _opt_preds_lookup[_name_key(str(_or["player_name"]))] = {
                                        "rank": _oi + 1,
                                        "win_prob": float(_or.get("win_prob", 0) or 0),
                                        "top10_prob": float(_or.get("top10_prob", 0) or 0),
                                        "form_trend": float(_or.get("form_trend", 0) or 0),
                                    }
    
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
                                    locked_players=_opt_locked,
                                    excluded_players=_opt_excluded,
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
                                    "No lineups matched your constraints. Try 'Upside' mode or lower the cut threshold."
                                )
                            else:
                                _opt_purse = _opt_meta.get("purse", 8_000_000)
                                _pick_colors = ["#00c44f", "#4cb8ff", "#f59e0b"]

                                for _rank, _row in _opt_df.iterrows():
                                    _score   = float(_row.get("score", 0))
                                    _cut_avg = float(_row.get("avg_cut_prob", 0))
                                    _top5    = float(_row.get("p_top5_any", 0))
                                    _pen     = float(pd.to_numeric(_row.get("usage_penalty"), errors="coerce") or 0) > 0

                                    # ── Lineup header ───────────────────────────────────────────────
                                    _pen_html = '<span style="color:#f59e0b;font-size:0.78em;margin-left:10px">⚠ uses penalty</span>' if _pen else ""
                                    st.markdown(
                                        f"""<div style="background:linear-gradient(135deg,#0a1628 0%,#0d2040 100%);
                                          border:1px solid #1e3a5f;border-radius:10px;padding:14px 18px;margin-bottom:4px;
                                          display:flex;justify-content:space-between;align-items:center;">
                                          <div>
                                            <div style="font-size:0.68em;color:#4cb8ff;letter-spacing:0.12em;font-weight:700;">LINEUP #{_rank}</div>
                                            <div style="font-size:1.22em;font-weight:700;color:#e8f0f8;margin-top:2px;">
                                              Expected Prize: ${_score:,.0f}{_pen_html}
                                            </div>
                                          </div>
                                          <div style="text-align:right;">
                                            <div style="font-size:0.82em;color:#7a9bbf;">Avg cut {_cut_avg:.1f}%</div>
                                            <div style="font-size:0.82em;color:#7a9bbf;">Any top-5: {_top5:.1f}%</div>
                                          </div>
                                        </div>""",
                                        unsafe_allow_html=True,
                                    )

                                    # ── Per-player cards ────────────────────────────────────────────
                                    _pcols = st.columns(3)
                                    for _idx in range(1, 4):
                                        _p = str(_row.get(f"pick{_idx}", "")).strip()
                                        if not _p:
                                            continue
                                        _prize_ev = float(pd.to_numeric(_row.get(f"prize_ev{_idx}", 0), errors="coerce") or 0)
                                        _cut_pct  = float(pd.to_numeric(_row.get(f"cut{_idx}", 0), errors="coerce") or 0)
                                        _win_pct  = float(pd.to_numeric(_row.get(f"win{_idx}", 0), errors="coerce") or 0)
                                        _t10_pct  = float(pd.to_numeric(_row.get(f"top10{_idx}", 0), errors="coerce") or 0)
                                        _uses     = int(pd.to_numeric(_row.get(f"uses{_idx}", 3), errors="coerce") or 0)
                                        _pstats   = _opt_preds_lookup.get(_name_key(_p), {})
                                        _mrank    = _pstats.get("rank", "—")
                                        _ft       = _pstats.get("form_trend", 0)
                                        _color    = _pick_colors[_idx - 1]

                                        # Cut risk color: green ≥70%, yellow 55-70%, red <55%
                                        _cut_color = "#00c44f" if _cut_pct >= 70 else ("#f59e0b" if _cut_pct >= 55 else "#ef4444")
                                        # Uses pips
                                        _uses_pips = "●" * _uses + "○" * (3 - _uses)
                                        # Form indicator
                                        _form_tag = ""
                                        if _ft > 0.3:
                                            _form_tag = '<span style="color:#f59e0b;font-size:0.72em;margin-left:4px">HOT</span>'
                                        elif _ft < -0.3:
                                            _form_tag = '<span style="color:#7a9bbf;font-size:0.72em;margin-left:4px">COLD</span>'

                                        with _pcols[_idx - 1]:
                                            st.markdown(
                                                f"""<div style="border:1px solid {_color}44;border-radius:9px;padding:14px 12px 12px;
                                                  background:linear-gradient(160deg,{_color}0d 0%,#0d1b2a 100%);height:100%;">
                                                  <div style="font-size:0.66em;font-weight:700;color:{_color};letter-spacing:0.1em;margin-bottom:3px">PICK {_idx}</div>
                                                  <div style="font-size:1.05em;font-weight:700;color:#e8f0f8;margin-bottom:10px;line-height:1.2">{_p}{_form_tag}</div>
                                                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;margin-bottom:10px">
                                                    <div>
                                                      <div style="font-size:0.63em;color:#7a9bbf">WIN%</div>
                                                      <div style="font-size:1.0em;font-weight:600;color:#e8f0f8">{_win_pct:.1f}%</div>
                                                    </div>
                                                    <div>
                                                      <div style="font-size:0.63em;color:#7a9bbf">TOP-10</div>
                                                      <div style="font-size:1.0em;font-weight:600;color:#e8f0f8">{_t10_pct:.0f}%</div>
                                                    </div>
                                                    <div>
                                                      <div style="font-size:0.63em;color:#7a9bbf">EXP PRIZE</div>
                                                      <div style="font-size:1.0em;font-weight:600;color:{_color}">${_prize_ev:,.0f}</div>
                                                    </div>
                                                    <div>
                                                      <div style="font-size:0.63em;color:#7a9bbf">CUT PROB</div>
                                                      <div style="font-size:1.0em;font-weight:600;color:{_cut_color}">{_cut_pct:.0f}%</div>
                                                    </div>
                                                  </div>
                                                  <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid {_color}22;padding-top:8px">
                                                    <div style="font-size:0.72em;color:#7a9bbf">Model #{_mrank}</div>
                                                    <div style="font-size:0.82em;color:{_color}" title="Uses remaining this season">{_uses_pips} {_uses}/3</div>
                                                  </div>
                                                </div>""",
                                                unsafe_allow_html=True,
                                            )

                                    st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

                                # ── Alternate pick recommendation ──────────────────────────────
                                if not _opt_df.empty and not _opt_elig.empty:
                                    _top_picks = set()
                                    _top_row = _opt_df.iloc[0]
                                    for _ai in range(1, 4):
                                        _ap = str(_top_row.get(f"pick{_ai}", "")).strip()
                                        if _ap:
                                            _top_picks.add(_name_key(_ap))

                                    _alt_pool = _opt_elig[
                                        ~_opt_elig["player_name"].apply(_name_key).isin(_top_picks)
                                    ].copy()
                                    if not _alt_pool.empty:
                                        from scripts.predictions.lineup_optimizer import expected_prize_money as _epm
                                        _alt_pool["_alt_prize"] = _alt_pool.apply(
                                            lambda r: _epm(r.to_dict(), _opt_purse), axis=1
                                        )
                                        _alt_pool = _alt_pool.sort_values(
                                            ["cut_prob", "_alt_prize"], ascending=[False, False]
                                        )
                                        _alt = _alt_pool.iloc[0]
                                        _alt_name  = str(_alt["player_name"])
                                        _alt_win   = float(_alt.get("win_prob", 0) or 0) * 100
                                        _alt_t10   = float(_alt.get("top10_prob", 0) or 0) * 100
                                        _alt_cut   = float(_alt.get("cut_prob", 0) or 0) * 100
                                        _alt_uses  = int(_alt.get("remaining_uses", 3))
                                        _alt_prize = float(_alt["_alt_prize"])
                                        _alt_pips  = "●" * _alt_uses + "○" * (3 - _alt_uses)
                                        st.markdown(
                                            f"""<div style="border:1px solid #ffffff22;border-radius:9px;padding:12px 16px;
                                              background:#0d1b2a;margin-top:4px;">
                                              <div style="font-size:0.66em;color:#7a9bbf;letter-spacing:0.1em;font-weight:700;margin-bottom:4px">ALTERNATE PICK</div>
                                              <div style="display:flex;justify-content:space-between;align-items:center;">
                                                <div style="font-size:1.0em;font-weight:700;color:#e8f0f8">{_alt_name}</div>
                                                <div style="font-size:0.78em;color:#7a9bbf">{_alt_pips} {_alt_uses}/3 uses left</div>
                                              </div>
                                              <div style="font-size:0.78em;color:#7a9bbf;margin-top:5px">
                                                Win {_alt_win:.1f}% · Top-10 {_alt_t10:.0f}% · Cut {_alt_cut:.0f}% · Exp prize ${_alt_prize:,.0f}
                                              </div>
                                            </div>""",
                                            unsafe_allow_html=True,
                                        )

                            if _opt_meta:
                                st.caption(
                                    f"Combos evaluated: {_opt_meta.get('scored_combos', 0):,} / {_opt_meta.get('total_combos', 0):,} · "
                                    f"Filtered → cut: {_opt_meta.get('skipped_by_cut', 0):,} | "
                                    f"usage: {_opt_meta.get('skipped_by_usage', 0):,}"
                                )
    
                        except Exception as _opt_err:
                            st.error(f"Optimizer error: {_opt_err}")
                            st.caption("Make sure predictions are loaded (run full pipeline first).")
    
    # ── Withdrawals Tab ───────────────────────────────────────────────────────

    with (_tw_wd_tab if _tw_wd_tab is not None else st.container()):
        _confirmed_wds = [w for w in _wd_list if w.get("status") == "WITHDRAWN"]
        _possible_wds  = [w for w in _wd_list if w.get("status") != "WITHDRAWN"]

        # Load pre-removal predictions to show stats on WD cards
        _wd_stats: dict = {}
        try:
            import glob as _glob
            _all_preds_wd = sorted(
                _glob.glob(str(OUTPUTS_DIR / f"{tournament.lower().replace(' ','_')}_*_predictions.csv")),
                key=lambda p: Path(p).stat().st_mtime
            )
            if _all_preds_wd:
                _hist_preds = pd.read_csv(_all_preds_wd[0])
                for _, _hr in _hist_preds.iterrows():
                    _wd_stats[str(_hr.get("player_id", ""))] = _hr
        except Exception:
            pass

        def _wd_source_badge(src: str) -> str:
            _labels = {
                "leaderboard":           ("LIVE LB",   "#3b82f6"),
                "pga_field_api":         ("PGA API",   "#ef4444"),
                "pga_field_api_missing": ("PGA FIELD", "#ef4444"),
                "manual":                ("MANUAL",    "#f59e0b"),
                "field_vs_predictions":  ("POSSIBLE",  "#f59e0b"),
            }
            _txt, _col = _labels.get(src, (src.upper(), "#6b7280"))
            return f'<span style="background:{_col}22;color:{_col};border:1px solid {_col}44;border-radius:4px;padding:1px 6px;font-size:9px;font-weight:700;letter-spacing:0.5px;">{_txt}</span>'

        def _render_wd_card(w: dict, is_pick: bool = False) -> str:
            _pid  = str(w.get("player_id", ""))
            _name = w.get("player_name", "Unknown")
            if "," in _name:
                _parts = _name.split(",", 1)
                _disp  = f"{_parts[1].strip()} {_parts[0].strip()}"
            else:
                _disp = _name
            _src_badge = _wd_source_badge(w.get("source", ""))
            _det_raw   = w.get("detected_at", "")
            _det_str   = _det_raw[:16].replace("T", " ") if _det_raw else ""

            _st      = _wd_stats.get(_pid)
            _wr_str  = f"#{int(_st['world_rank'])}" if _st is not None and pd.notna(_st.get("world_rank")) else "—"
            _wp_str  = f"{float(_st['win_prob'])*100:.1f}%" if _st is not None and pd.notna(_st.get("win_prob")) else "—"
            _t10_str = f"{float(_st['top10_prob'])*100:.0f}%" if _st is not None and pd.notna(_st.get("top10_prob")) else "—"

            _border      = "#f59e0b" if is_pick else "#ef4444"
            _bg          = "rgba(245,158,11,0.08)" if is_pick else "rgba(239,68,68,0.06)"
            _pick_banner = '<div style="color:#f59e0b;font-size:10px;font-weight:700;letter-spacing:0.5px;margin-bottom:6px;">YOUR PICK</div>' if is_pick else ""

            return f"""
<div style="background:{_bg};border:1px solid {_border}44;border-radius:10px;padding:14px 16px;margin-bottom:8px;">
  {_pick_banner}
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-size:15px;font-weight:700;color:#f1f5f9;">{_disp}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:2px;">World Rank {_wr_str}</div>
    </div>
    <div style="text-align:right;">
      {_src_badge}
      {f'<div style="font-size:10px;color:#4b5563;margin-top:4px;">{_det_str}</div>' if _det_str else ""}
    </div>
  </div>
  <div style="display:flex;gap:20px;margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.06);">
    <div><div style="font-size:13px;font-weight:700;color:#f1f5f9;">{_wp_str}</div><div style="font-size:10px;color:#6b7280;">WIN PROB</div></div>
    <div><div style="font-size:13px;font-weight:700;color:#4cb8ff;">{_t10_str}</div><div style="font-size:10px;color:#6b7280;">TOP 10</div></div>
    <div style="margin-left:auto;align-self:center;"><span style="color:{_border};font-size:11px;font-weight:600;">WITHDRAWN</span></div>
  </div>
</div>"""

        if not _wd_list:
            st.markdown(
                '<div style="text-align:center;color:#4b5563;padding:40px 0;font-size:14px;">'
                'No withdrawals detected for this tournament.'
                '</div>',
                unsafe_allow_html=True
            )
        else:
            # Header row: summary + re-check button
            _last_checked = ""
            _dates = [w.get("detected_at", "") for w in _wd_list if w.get("detected_at")]
            if _dates:
                _last_checked = max(_dates)[:16].replace("T", " ")

            _wh_col1, _wh_col2 = st.columns([4, 1])
            with _wh_col1:
                st.markdown(
                    f'<div style="font-size:14px;font-weight:700;color:#ef4444;margin-bottom:2px;">'
                    f'{len(_confirmed_wds)} Confirmed Withdrawal{"s" if len(_confirmed_wds) != 1 else ""}'
                    f'{"  ·  " + str(len(_possible_wds)) + " possible" if _possible_wds else ""}'
                    f'</div>'
                    f'{"<div style=\"font-size:11px;color:#4b5563;\">Last checked: " + _last_checked + "</div>" if _last_checked else ""}',
                    unsafe_allow_html=True
                )
            with _wh_col2:
                if st.button("Re-check", key="wd_tab_refresh_btn", use_container_width=True):
                    import subprocess as _sp_wd
                    _sp_wd.run(
                        ["python3",
                         str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_withdrawals.py"),
                         "--tournament-id", str(_field_id),
                         "--auto-update-field"],
                        capture_output=True, cwd=PROJECT_ROOT
                    )
                    st.rerun()

            st.markdown('<div style="margin-top:12px;"></div>', unsafe_allow_html=True)

            # Your picks first, then rest of confirmed WDs
            _pick_ids_wd = set()
            _this_week_picks_wd = _this_week_picks if "_this_week_picks" in dir() else []
            for _w in _confirmed_wds:
                _is_pick = any(
                    _w["player_name"].lower() in str(p).lower() or str(p).lower() in _w["player_name"].lower()
                    for p in _this_week_picks_wd
                )
                if _is_pick:
                    _pick_ids_wd.add(_w["player_id"])
                    st.markdown(_render_wd_card(_w, is_pick=True), unsafe_allow_html=True)

            for _w in _confirmed_wds:
                if _w["player_id"] not in _pick_ids_wd:
                    st.markdown(_render_wd_card(_w, is_pick=False), unsafe_allow_html=True)

            if _possible_wds:
                with st.expander(f"Possible withdrawals ({len(_possible_wds)})", expanded=False):
                    for _w in _possible_wds:
                        st.markdown(
                            f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
                            f'{_wd_source_badge(_w.get("source",""))} '
                            f'<span style="color:#d1d5db;margin-left:8px;">{_w["player_name"]}</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

    # ── Power Rankings ────────────────────────────────────────────────────────
    def _load_power_rankings(tid: str, t_name: str) -> pd.DataFrame:
        """Find and load the best-matching power rankings CSV for this week."""
        pr_dir = DATA_DIR / "power_rankings"
        if not pr_dir.exists():
            return pd.DataFrame()

        # 1) Try direct match by tournament_id in paths.csv
        paths_file = pr_dir / "paths.csv"
        slug = ""
        if paths_file.exists():
            try:
                paths_df = pd.read_csv(paths_file, dtype=str).fillna("")
                tid_upper = str(tid or "").strip().upper()
                if tid_upper and "pga_id" in paths_df.columns:
                    tid_rows = paths_df[paths_df["pga_id"].str.upper().str.strip() == tid_upper]
                    if not tid_rows.empty:
                        slug = str(tid_rows.iloc[0].get("slug", "")).strip()
            except Exception:
                pass

        # 2) Fall back to name-based slug matching
        if not slug:
            name_slug = re.sub(r"[^a-z0-9]+", "-", str(t_name or "").lower()).strip("-")
            under_slug = name_slug.replace("-", "_")
            candidates = [name_slug, under_slug, f"{under_slug}_2026"]
            available = {p.stem for p in pr_dir.glob("*.csv") if p.stem != "paths" and p.stem != "pr_table"}
            for c in candidates:
                if c in available:
                    slug = c
                    break

        if not slug:
            return pd.DataFrame()

        csv_path = pr_dir / f"{slug}.csv"
        if not csv_path.exists():
            return pd.DataFrame()

        try:
            return pd.read_csv(csv_path)
        except Exception:
            return pd.DataFrame()

    _pr_df = _load_power_rankings(str(_field_id), tournament)

    with _tw_tt_tab:
        st.markdown("---")
        st.markdown("#### PGA Tour Power Rankings")
        if not _pr_df.empty and "rank" in _pr_df.columns:
            _pr_title = str(_pr_df["tournament_name"].iloc[0]) if "tournament_name" in _pr_df.columns else tournament
            st.caption(f"PGA Tour editorial power rankings — {_pr_title}")
            _pr_df["rank"] = pd.to_numeric(_pr_df["rank"], errors="coerce")
            _pr_sorted = _pr_df.sort_values("rank").reset_index(drop=True)
            for _, _pr_row in _pr_sorted.iterrows():
                _pr_rank = int(_pr_row["rank"]) if pd.notna(_pr_row["rank"]) else "?"
                _pr_name = str(_pr_row.get("player_name", "")).strip()
                _pr_country = str(_pr_row.get("country_flag", _pr_row.get("country", ""))).strip()
                _pr_analysis = str(_pr_row.get("analysis", "")).strip()
                _rank_color = "#00c44f" if _pr_rank <= 3 else "#4cb8ff" if _pr_rank <= 8 else "#7a9bbf"
                st.markdown(
                    f"""<div style="display:flex;gap:14px;padding:10px 14px;border-bottom:1px solid #1a2a3a;align-items:flex-start">
  <div style="min-width:32px;font-size:1.25em;font-weight:800;color:{_rank_color};padding-top:2px">#{_pr_rank}</div>
  <div>
    <div style="font-size:0.95em;font-weight:700;color:#e8f0f8;margin-bottom:3px">{_pr_name} <span style="font-size:0.75em;color:#7a9bbf;font-weight:400">{_pr_country}</span></div>
    <div style="font-size:0.8em;color:#9ab0c8;line-height:1.5">{_pr_analysis}</div>
  </div>
</div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Power rankings not yet fetched for this week.")
            if _field_id and st.button("Fetch Power Rankings", key="fetch_pr_btn", type="primary"):
                import subprocess as _subp_pr
                # Build slug from tournament name (same logic as Pipeline page)
                _pr_fetch_slug = re.sub(r"[^a-z0-9]+", "-", str(tournament or "").lower()).strip("-")
                _pr_fetch_cmd = [
                    "python3", "scripts/scrapers/fetch_power_rankings.py",
                    "--slug", _pr_fetch_slug, "--allow-fail",
                ]
                with st.spinner("Fetching PGA Tour power rankings..."):
                    _pr_res = _subp_pr.run(
                        _pr_fetch_cmd,
                        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
                    )
                if _pr_res.returncode == 0 and "Saved" in (_pr_res.stdout or ""):
                    st.success("Power rankings fetched.")
                    st.rerun()
                else:
                    st.warning("Auto-fetch didn't find rankings. PGA Tour publishes them Monday of tournament week — try again then, or use Pipeline → Power Rankings to set a custom path.")
                    if _pr_res.stderr:
                        st.caption(_pr_res.stderr[-300:])

# ── Teams Tab (team events only e.g. Zurich Classic) ─────────────────────────
if _tw_teams_tab is not None:
    with _tw_teams_tab:
        try:
            _td = pd.read_csv(_team_pred_path)
            _td_blended = _td[_td["data_source"] == "blended"]
            _td_dg_only = _td[_td["data_source"] == "dg_only"]

            st.caption(
                f"{len(_td)} teams · {len(_td_blended)} blended (DG + our model) · "
                f"{len(_td_dg_only)} DG-only · sorted by DG win probability"
            )

            # ── Top 10 cards ────────────────────────────────────────────────
            _tc_html = []
            for _, _tr in _td.head(10).iterrows():
                _rk   = int(_tr["rank"])
                _tn   = str(_tr["team_name"])
                _dg_w = f"{_tr['dg_win']:.2f}%" if pd.notna(_tr.get("dg_win")) else "—"
                _dg_t = f"{_tr['dg_top10']:.1f}%" if pd.notna(_tr.get("dg_top10")) else "—"
                _cut  = f"{_tr['dg_make_cut']:.1f}%" if pd.notna(_tr.get("dg_make_cut")) else "—"
                _comp = f"{float(_tr['our_composite']):.3f}" if pd.notna(_tr.get("our_composite")) else "—"
                _asg  = f"{float(_tr['team_avg_sg']):.2f}" if pd.notna(_tr.get("team_avg_sg")) else "—"
                _msg  = f"{float(_tr['team_max_sg']):.2f}" if pd.notna(_tr.get("team_max_sg")) else "—"
                _src  = _tr.get("data_source", "")
                _border_col = "#00c44f" if _src == "blended" else "#4a6080"
                _src_badge = (
                    '<span style="font-size:9px;background:rgba(0,196,79,0.15);color:#00c44f;'
                    'padding:2px 6px;border-radius:4px;font-weight:700;">BLENDED</span>'
                    if _src == "blended" else
                    '<span style="font-size:9px;background:rgba(74,96,128,0.2);color:#4a6080;'
                    'padding:2px 6px;border-radius:4px;">DG ONLY</span>'
                )
                _tc_html.append(f"""
<div style="background:#0d1a30;border:1px solid #1c2f4a;border-left:3px solid {_border_col};
     border-radius:12px;padding:14px 12px;margin-bottom:8px;display:flex;align-items:center;gap:12px;">
  <div style="font-size:11px;color:#4a6080;width:28px;text-align:right;flex-shrink:0;">#{_rk}</div>
  <div style="flex:1;">
    <div style="font-size:14px;font-weight:600;color:#dde6f5;">{_tn}</div>
    <div style="font-size:11px;color:#4a6080;margin-top:2px;">Avg SG: {_asg} &nbsp;·&nbsp; Max SG: {_msg} &nbsp;·&nbsp; {_src_badge}</div>
  </div>
  <div style="text-align:right;min-width:48px;">
    <div class="pc-stat">{_dg_w}</div>
    <div class="pc-stat-label">WIN</div>
  </div>
  <div style="text-align:right;min-width:48px;">
    <div class="pc-stat" style="color:#4cb8ff;">{_dg_t}</div>
    <div class="pc-stat-label">TOP 10</div>
  </div>
  <div style="text-align:right;min-width:48px;">
    <div class="pc-stat" style="color:#f4c430;">{_cut}</div>
    <div class="pc-stat-label">CUT</div>
  </div>
  <div style="text-align:right;min-width:52px;">
    <div class="pc-stat" style="color:#9b9bff;">{_comp}</div>
    <div class="pc-stat-label">SCORE</div>
  </div>
</div>""")
            st.markdown("\n".join(_tc_html), unsafe_allow_html=True)

            # ── Full table (collapsed) ───────────────────────────────────────
            with st.expander(f"Full rankings — all {len(_td)} teams"):
                _td_show = _td[["rank", "team_name", "dg_win", "dg_top10", "dg_make_cut",
                                 "our_composite", "team_avg_sg", "team_max_sg"]].copy()
                _td_show.columns = ["Rk", "Team", "Win%", "Top10%", "Cut%", "Score", "Avg SG", "Max SG"]
                st.dataframe(
                    _td_show.style.format({
                        "Win%":   "{:.2f}",
                        "Top10%": "{:.1f}",
                        "Cut%":   "{:.1f}",
                        "Score":  "{:.3f}",
                        "Avg SG": "{:.3f}",
                        "Max SG": "{:.3f}",
                    }, na_rep="—"),
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as _te:
            st.error(f"Could not load team predictions: {_te}")

# ============================================================================
# PAGE: ASSISTANT (Groq-powered golf chat)
# ============================================================================

elif page == "💬 Assistant":
    import os as _os
    import time as _time
    from datetime import datetime as _dt

    # -------------------------------------------------------------------------
    # Supplement renderer — data cards shown below the AI text response.
    # Separates narrative (AI writes) from structured data (Streamlit renders).
    # -------------------------------------------------------------------------

    def _chat_intent_key(intent: dict) -> str:
        """Map classify_query dict → simple string for storage."""
        if intent.get("is_compare"):       return "compare"
        if intent.get("is_h2h"):           return "h2h"
        if intent.get("is_pick_reason"):   return "player"
        if intent.get("is_player"):        return "player"
        if intent.get("is_daily_bet"):     return "daily_bet"
        if intent.get("is_bet"):           return "bet"
        if intent.get("is_course_breakdown"): return "course"
        if intent.get("is_live"):          return "live"
        if intent.get("is_lineup"):        return "lineup"
        return "general"

    def _chat_player_cards(players: list[str], tid: str):
        """Compact profile card(s) for named players using existing render_player_profile_card."""
        try:
            _cp_preds = pd.read_csv(OUTPUTS_DIR / "latest_predictions.csv")
            _cp_profiles = load_betting_profiles(tid or None)
        except Exception:
            return

        _cp_cols = st.columns(min(len(players), 2))
        for _ci, _cpname in enumerate(players[:2]):
            with _cp_cols[_ci % len(_cp_cols)]:
                _cp_key = _name_key(_cpname)
                _cp_any = _cp_key.split()[0]
                _cp_row = _cp_preds[_cp_preds["player_name"].apply(_name_key) == _cp_key]
                if _cp_row.empty:
                    _cp_row = _cp_preds[_cp_preds["player_name"].apply(_name_key).str.contains(_cp_any, na=False)]
                if _cp_row.empty:
                    continue
                _cp_pred_data = _cp_row.iloc[0].to_dict()
                _cp_profile = get_player_profile(_cp_profiles, _cpname) if not _cp_profiles.empty else None
                if _cp_profile:
                    render_player_profile_card(_cp_profile, show_full=False, pred_data=_cp_pred_data)
                else:
                    # Fallback: compact metric row when no betting profile exists
                    _cp_name_disp = _name_key(_cp_pred_data.get("player_name", _cpname)).title()
                    _cp_win  = float(_cp_pred_data.get("win_prob",   0) or 0)
                    _cp_t10  = float(_cp_pred_data.get("top10_prob", 0) or 0)
                    _cp_sg   = _cp_pred_data.get("season_sg_total")
                    _cp_wr   = _cp_pred_data.get("world_rank")
                    _cp_odds_raw = _cp_pred_data.get("odds_to_win") or _cp_pred_data.get("dk_win_odds_american")
                    _cp_odds_str = ""
                    if _cp_odds_raw and pd.notna(_cp_odds_raw):
                        try:
                            _ov = int(float(_cp_odds_raw))
                            _cp_odds_str = f"+{_ov}" if _ov > 0 else str(_ov)
                        except Exception:
                            pass
                    st.markdown(
                        f"<div style='border:1px solid #1e3a5a;border-radius:8px;padding:10px 14px;"
                        f"background:#0a1520;margin-bottom:8px'>"
                        f"<div style='font-weight:700;font-size:1.05em;color:#e8f0f8'>{_cp_name_disp}"
                        + (f" <span style='color:#7a9bbf;font-size:0.8em'>WR #{int(_cp_wr)}</span>" if _cp_wr and pd.notna(_cp_wr) else "")
                        + f"</div>"
                        f"<div style='display:flex;gap:20px;margin-top:6px'>"
                        f"<div><div style='font-size:0.65em;color:#7a9bbf'>WIN%</div>"
                        f"<div style='font-weight:700;color:#e8f0f8'>{_cp_win*100:.1f}%</div></div>"
                        f"<div><div style='font-size:0.65em;color:#7a9bbf'>TOP-10</div>"
                        f"<div style='font-weight:700;color:#e8f0f8'>{_cp_t10*100:.0f}%</div></div>"
                        + (f"<div><div style='font-size:0.65em;color:#7a9bbf'>SG TOT</div>"
                           f"<div style='font-weight:700;color:{'#00c44f' if float(_cp_sg)>=0 else '#e74c3c'}'>{float(_cp_sg):+.2f}</div></div>"
                           if _cp_sg and pd.notna(_cp_sg) else "")
                        + (f"<div><div style='font-size:0.65em;color:#7a9bbf'>ODDS</div>"
                           f"<div style='font-weight:700;color:#4cb8ff'>{_cp_odds_str}</div></div>"
                           if _cp_odds_str else "")
                        + f"</div></div>",
                        unsafe_allow_html=True,
                    )

    def _chat_compare_table(players: list[str], tid: str):
        """Side-by-side comparison table as a styled dataframe."""
        try:
            _ct_preds = pd.read_csv(OUTPUTS_DIR / "latest_predictions.csv")
            _ct_preds = _ct_preds.sort_values("win_prob", ascending=False).reset_index(drop=True)
            _ct_preds["_rank"] = _ct_preds.index + 1

            # Live leaderboard for tee times
            _ct_live = None
            if tid:
                _ct_lpath = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
                if _ct_lpath.exists():
                    try:
                        _ct_live = pd.read_csv(_ct_lpath)
                        _ct_live["_norm"] = _ct_live["player_name"].apply(lambda n: _name_key(str(n)))
                    except Exception:
                        pass

            # Odds snapshots for movement
            _ct_move: dict[str, str] = {}
            _ct_snap_dir = DATA_DIR / "odds" / "snapshots"
            if _ct_snap_dir.exists():
                try:
                    _ct_snaps = sorted(_ct_snap_dir.glob("odds_snapshot_*.csv"))
                    from datetime import timedelta as _td
                    _ct_cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
                    _ct_recent = []
                    for _sf in _ct_snaps:
                        try:
                            _st = pd.to_datetime(_sf.stem.replace("odds_snapshot_", ""), format="%Y%m%d_%H%M")
                            if _st >= _ct_cutoff:
                                _ct_recent.append(_sf)
                        except Exception:
                            continue
                    if len(_ct_recent) >= 2:
                        _ct_f = pd.read_csv(_ct_recent[0])
                        _ct_l = pd.read_csv(_ct_recent[-1])
                        for _df in [_ct_f, _ct_l]:
                            _df["player_name"] = _df["player_name"].apply(lambda n: _name_key(str(n)))
                        _ct_mg = _ct_f.merge(_ct_l, on="player_name", suffixes=("_o", "_n"))
                        for _, _mr in _ct_mg.iterrows():
                            try:
                                def _imp(o):
                                    o = float(o)
                                    return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
                                _chg = _imp(_mr["odds_numeric_n"]) - _imp(_mr["odds_numeric_o"])
                                _arr = "▲" if _chg > 0.01 else ("▼" if _chg < -0.01 else "→")
                                _oo = int(float(_mr["odds_numeric_o"]))
                                _on = int(float(_mr["odds_numeric_n"]))
                                _oo_s = f"+{_oo}" if _oo > 0 else str(_oo)
                                _on_s = f"+{_on}" if _on > 0 else str(_on)
                                _ct_move[str(_mr["player_name"]).lower()] = f"{_oo_s}→{_on_s} {_arr}"
                            except Exception:
                                continue
                except Exception:
                    pass

            rows = []
            for _pn in players:
                # Use _name_key for accent-safe matching (strips å→a, é→e, etc.)
                _pl_key = _name_key(_pn)          # e.g. "aberg ludvig"
                _pl_any = _pl_key.split()[0]       # first token after sort ≈ last name
                _m = _ct_preds[_ct_preds["player_name"].apply(_name_key) == _pl_key]
                if _m.empty:  # fallback: partial match on first token
                    _m = _ct_preds[_ct_preds["player_name"].apply(_name_key).str.contains(_pl_any, na=False)]
                if _m.empty:
                    continue
                _r = _m.iloc[0]
                _sg_tot = _r.get("season_sg_total")
                _sg_app = _r.get("season_sg_app")
                _h_starts = int(_r.get("hist_times_played", 0) or _r.get("course_starts", 0) or 0)
                _h_wins   = int(_r.get("hist_wins", 0) or 0)
                _h_t10s   = int(_r.get("hist_top10s", 0) or 0)
                _course_str = (f"{_h_starts}s" + (f"·{_h_wins}W" if _h_wins else "") +
                               (f"·{_h_t10s}T10" if _h_t10s else "")) if _h_starts else "—"

                # Tee time from live leaderboard (also use accent-safe search)
                _tee = "—"
                if _ct_live is not None:
                    _lm = _ct_live[_ct_live["_norm"].str.contains(_pl_any, na=False)]
                    if not _lm.empty:
                        _tv = str(_lm.iloc[0].get("tee_time", ""))
                        _tee = _tv if _tv not in ("nan", "", "None") else "—"
                        _pos = str(_lm.iloc[0].get("position", ""))
                        if _pos and _pos not in ("nan", ""):
                            _tee = f"{_pos} / {_tee}" if _tee != "—" else _pos

                # Odds movement (accent-safe: match on normalized first token)
                _mv = next((_ct_move[k] for k in _ct_move if _pl_any in k), "—")

                rows.append({
                    "Player":   _pn,  # use the matched display name passed in
                    "#":        f"#{int(_r['_rank'])}",
                    "Win%":     f"{float(_r.get('win_prob',0) or 0)*100:.1f}%",
                    "T10%":     f"{float(_r.get('top10_prob',0) or 0)*100:.0f}%",
                    "SG Tot":   f"{float(_sg_tot):+.2f}" if pd.notna(_sg_tot) else "—",
                    "SG App":   f"{float(_sg_app):+.2f}" if pd.notna(_sg_app) else "—",
                    "Course":   _course_str,
                    "Odds/Move": _mv,
                    "Live/Tee": _tee,
                })

            if rows:
                st.caption("Player comparison")
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "#":        st.column_config.TextColumn(width="small"),
                        "Win%":     st.column_config.TextColumn(width="small"),
                        "T10%":     st.column_config.TextColumn(width="small"),
                        "SG Tot":   st.column_config.TextColumn(width="small"),
                        "SG App":   st.column_config.TextColumn(width="small"),
                        "Live/Tee": st.column_config.TextColumn(width="medium"),
                    },
                )
        except Exception:
            pass

    def _chat_bet_cards(tid: str):
        """Top 3 recommended bets as a compact table."""
        try:
            _cb_path = DATA_DIR / "odds" / "recommended_bets_latest.csv"
            if not _cb_path.exists():
                return
            _cb_df = pd.read_csv(_cb_path)
            _CLEAN = {"top5","top10","top20","top30","make_cut","group_winner","h2h","h2h_r1","outright"}
            _cb_df = _cb_df[_cb_df["market"].isin(_CLEAN)]
            _cb_df["edge_pts"] = pd.to_numeric(_cb_df.get("edge_pts", 0), errors="coerce").fillna(0)
            _cb_df = _cb_df.sort_values("edge_pts", ascending=False).head(5)

            _MLABELS = {
                "top5": "Top 5", "top10": "Top 10", "top20": "Top 20",
                "make_cut": "Make Cut", "group_winner": "3-Ball",
                "h2h": "Matchup", "h2h_r1": "R1 Matchup", "outright": "Win",
            }

            _cb_rows = []
            for _, _br in _cb_df.iterrows():
                _bn = str(_br.get("player_name", "?"))
                if ", " in _bn:
                    _bn = " ".join(reversed(_bn.split(", ")))
                _odds = _br.get("odds_american")
                try:
                    _oi = int(float(_odds))
                    _odds_s = f"+{_oi}" if _oi > 0 else str(_oi)
                except Exception:
                    _odds_s = "—"
                _mp = float(_br.get("model_prob", 0) or 0)
                _bp = float(_br.get("book_prob", 0) or 0)
                _cb_rows.append({
                    "Player": _bn,
                    "Market": _MLABELS.get(str(_br.get("market", "")), str(_br.get("market", ""))),
                    "Odds":   _odds_s,
                    "Model%": f"{_mp*100:.0f}%",
                    "Book%":  f"{_bp*100:.0f}%",
                    "Edge":   f"+{float(_br.get('edge_pts',0)):.1f}pp",
                })

            if _cb_rows:
                st.caption("Top model bets")
                st.dataframe(
                    pd.DataFrame(_cb_rows),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Odds":   st.column_config.TextColumn(width="small"),
                        "Model%": st.column_config.TextColumn(width="small"),
                        "Book%":  st.column_config.TextColumn(width="small"),
                        "Edge":   st.column_config.TextColumn(width="small"),
                    },
                )
        except Exception:
            pass

    def _render_chat_supplement(meta: dict):
        """Dispatch to the right supplement renderer based on stored intent."""
        _intent   = meta.get("intent", "general")
        _players  = meta.get("players", [])
        _tid      = meta.get("tid", "")
        try:
            if _intent in ("player", "h2h", "pick_reason") and _players:
                st.divider()
                _chat_player_cards(_players, _tid)
            elif _intent == "compare" and _players:
                st.divider()
                _chat_compare_table(_players, _tid)
            elif _intent in ("bet", "daily_bet"):
                st.divider()
                _chat_bet_cards(_tid)
        except Exception:
            pass  # supplements are best-effort — never break the chat

    # --- Persistent API key config ---
    _CFG_PATH = PROJECT_ROOT / "data" / "config" / "assistant.json"

    def _load_api_key() -> str:
        """Load persisted API key from config file. Prefers Anthropic, falls back to Groq."""
        # Check env vars first
        _ant = _os.environ.get("ANTHROPIC_API_KEY", "")
        if _ant:
            return _ant
        _groq = _os.environ.get("GROQ_API_KEY", "")
        if _groq:
            return _groq
        # Check config file
        try:
            if _CFG_PATH.exists():
                with open(_CFG_PATH) as _f:
                    _cfg = json.load(_f)
                return _cfg.get("anthropic_api_key") or _cfg.get("groq_api_key") or ""
        except Exception:
            pass
        return ""

    def _save_api_key(key: str) -> None:
        """Save API key to config file."""
        try:
            _CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _existing = {}
            if _CFG_PATH.exists():
                with open(_CFG_PATH) as _f:
                    _existing = json.load(_f)
            if key.startswith("sk-ant-"):
                _existing["anthropic_api_key"] = key
            else:
                _existing["groq_api_key"] = key
            with open(_CFG_PATH, "w") as _f:
                json.dump(_existing, _f)
        except Exception:
            pass

    # Load key: config file → session state → empty
    if "chat_api_key" not in st.session_state:
        st.session_state["chat_api_key"] = _load_api_key()
    _api_key = st.session_state["chat_api_key"]
    _is_claude = _api_key.startswith("sk-ant-")

    # Chat UI styles
    st.markdown("""<style>
/* Follow-up suggestion chips */
div.chat-followups div[data-testid="stButton"] > button {
    border-radius: 999px !important;
    font-size: 0.78rem !important;
    padding: 0.25rem 0.85rem !important;
    background: transparent !important;
    border: 1px solid rgba(250,250,250,0.18) !important;
    color: rgba(250,250,250,0.60) !important;
    transition: all 0.15s ease !important;
}
div.chat-followups div[data-testid="stButton"] > button:hover {
    border-color: rgba(99,179,237,0.6) !important;
    color: rgba(99,179,237,1.0) !important;
    background: rgba(99,179,237,0.06) !important;
}
/* Quick action cards on empty state */
div.chat-actions div[data-testid="stButton"] > button {
    border-radius: 10px !important;
    font-size: 0.82rem !important;
    padding: 0.6rem 0.75rem !important;
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: rgba(255,255,255,0.80) !important;
    text-align: left !important;
    transition: all 0.15s ease !important;
    min-height: 52px !important;
}
div.chat-actions div[data-testid="stButton"] > button:hover {
    background: rgba(99,179,237,0.10) !important;
    border-color: rgba(99,179,237,0.4) !important;
    color: rgba(255,255,255,0.95) !important;
}
/* Search attribution badges */
.search-badge {
    display: inline-block;
    font-size: 0.70rem;
    color: rgba(99,179,237,0.75);
    background: rgba(99,179,237,0.08);
    border: 1px solid rgba(99,179,237,0.18);
    border-radius: 999px;
    padding: 1px 8px;
    margin: 2px 3px 0 0;
}
/* Thinking status text */
.chat-status {
    font-size: 0.82rem;
    color: rgba(250,250,250,0.40);
    font-style: italic;
}
</style>""", unsafe_allow_html=True)

    # --- Detect tournament ID + phase (refresh every render so phase updates during rounds) ---
    try:
        from scripts.chat.golf_chatbot import (
            _detect_tournament_id,
            _tournament_state,
        )
        _cur_tid = _detect_tournament_id()
        _ts = _tournament_state(_cur_tid) if _cur_tid else {}
        _fresh_phase = _ts.get("phase", "pre_tournament")
        # Always write fresh phase; only write tid if not already set (preserves user context)
        st.session_state["chat_phase"] = _fresh_phase
        if "chat_tid" not in st.session_state:
            st.session_state["chat_tid"] = _cur_tid
    except Exception:
        if "chat_phase" not in st.session_state:
            st.session_state["chat_phase"] = "pre_tournament"
        if "chat_tid" not in st.session_state:
            st.session_state["chat_tid"] = None

    with st.sidebar:
        st.markdown("### Assistant Settings")
        _key_input = st.text_input(
            "API Key (Anthropic or Groq)",
            value=_api_key,
            type="password",
            key="chat_api_key_input",
            help="Anthropic key (sk-ant-...) uses Claude. Groq key uses Llama (free). Saved locally.",
        )
        if _key_input and _key_input != _api_key:
            st.session_state["chat_api_key"] = _key_input
            _api_key = _key_input
            _is_claude = _api_key.startswith("sk-ant-")
            _save_api_key(_key_input)
            st.success("Key saved — won't need to enter again.")
        if not _api_key:
            st.warning("Enter an Anthropic key (Claude) or Groq key (free) above.\nGroq: groq.com  |  Anthropic: console.anthropic.com")

        # Refresh button — clears cached phase/tid so it re-detects on next query
        if st.button("Refresh context", key="chat_refresh_ctx_sidebar"):
            for _k in list(st.session_state.keys()):
                if _k in ("chat_phase", "chat_tid") or _k.startswith("_chat_base_ctx_"):
                    st.session_state.pop(_k, None)
            st.rerun()

    _PHASE_ACTIONS = {
        "pre_tournament": [
            ("Build my lineup", "Build my optimal lineup for this week. Consider my uses remaining, player form, and course fit. Give me 3 players and explain why each one makes sense."),
            ("Usage strategy", "For each of my tracked players, when is the best time to use them this season? Should I save any of them for a Major or Signature event?"),
            ("Best bets", "What are the top 3 bets with the best value this week? Walk me through the odds and why each one makes sense."),
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
            "When is the best time to use my remaining players this season?",
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

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    _has_history = bool(st.session_state["chat_history"])

    if not _has_history:
        # ── EMPTY STATE ──────────────────────────────────────────────────────
        # Centered welcome with tournament context + 2×2 action grid
        _phase_labels = {
            "pre_tournament": "Pre-tournament",
            "round_1": "Round 1 in progress",
            "round_2": "Round 2 in progress",
            "round_3": "Round 3 in progress",
            "round_4": "Round 4 in progress",
            "complete": "Tournament complete",
        }
        _tid_display = st.session_state.get("chat_tid", "")
        _phase_display = _phase_labels.get(_chat_phase, "")
        _subtitle = " · ".join(filter(None, [_phase_display, _tid_display]))

        st.markdown("## Golf Assistant")
        if _subtitle:
            st.caption(_subtitle)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**What would you like to know?**")
        st.markdown(" ")

        st.markdown('<div class="chat-actions">', unsafe_allow_html=True)
        _qa_c1, _qa_c2 = st.columns(2, gap="small")
        for _qi, (_ql, _qp) in enumerate(_quick_actions):
            with (_qa_c1 if _qi % 2 == 0 else _qa_c2):
                if st.button(_ql, use_container_width=True, key=f"qa_{_qi}"):
                    st.session_state["chat_prefill"] = _qp
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        # ── ACTIVE CHAT STATE ─────────────────────────────────────────────────
        # Compact header row: tournament label left, Clear button right
        _hcol_l, _hcol_r = st.columns([6, 1])
        with _hcol_l:
            _tid_display = st.session_state.get("chat_tid", "")
            if _tid_display:
                st.caption(f"Golf Assistant · {_tid_display}")
        with _hcol_r:
            _clr_col, _ref_col = st.columns(2)
            with _clr_col:
                if st.button("Clear", key="chat_clear_top", help="Clear conversation"):
                    st.session_state["chat_history"] = []
                    # Also clear cached base context so next turn rebuilds it
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("_chat_base_ctx_"):
                            del st.session_state[_k]
                    st.rerun()
            with _ref_col:
                if st.button("↺", key="chat_refresh_ctx", help="Refresh context (re-reads data files)"):
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("_chat_base_ctx_"):
                            del st.session_state[_k]
                    st.rerun()

        # Render conversation — supplements shown only for the last assistant message
        _last_asst_idx = next(
            (i for i in range(len(st.session_state["chat_history"]) - 1, -1, -1)
             if st.session_state["chat_history"][i]["role"] == "assistant"),
            None,
        )
        for _mi, _msg in enumerate(st.session_state["chat_history"]):
            with st.chat_message(_msg["role"]):
                st.markdown(_msg["content"])
                if _msg["role"] == "assistant" and _mi == _last_asst_idx and _msg.get("meta"):
                    _render_chat_supplement(_msg["meta"])

        # Follow-up suggestion chips after last assistant message
        if st.session_state["chat_history"][-1]["role"] == "assistant":
            try:
                from scripts.chat.golf_chatbot import generate_followup_questions as _gen_followups
                _last_resp = st.session_state["chat_history"][-1]["content"]
                _last_players = st.session_state.get("chat_last_players", [])
                _followups = _gen_followups(_last_resp, _last_players, _chat_phase)
            except Exception:
                _followups = _PHASE_FOLLOWUPS.get(_chat_phase, _PHASE_FOLLOWUPS["pre_tournament"])
            st.markdown('<div class="chat-followups">', unsafe_allow_html=True)
            _fu_cols = st.columns(len(_followups), gap="small")
            for _fi, _fq in enumerate(_followups):
                with _fu_cols[_fi]:
                    if st.button(
                        _fq,
                        key=f"fu_{_fi}_{len(st.session_state['chat_history'])}",
                        use_container_width=True,
                    ):
                        st.session_state["chat_prefill"] = _fq
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    _prefill = st.session_state.pop("chat_prefill", None)

    if _prompt := (st.chat_input("Ask about lineups, bets, players, live scores...") or _prefill):
        if not _api_key:
            st.error("Please enter your API key in the sidebar to use the assistant.")
        else:
            with st.chat_message("user"):
                st.markdown(_prompt)
            st.session_state["chat_history"].append({"role": "user", "content": _prompt})

            # Everything happens inside the assistant bubble — context build, tool calls, streaming
            _extract_players_resp = None
            _cur_meta = {}
            _response_text = ""
            _searches_run = []

            with st.chat_message("assistant"):
                _status = st.empty()
                try:
                    from scripts.chat.golf_chatbot import (
                        build_context as _build_ctx,
                        build_base_context as _build_base_ctx,
                        stream_response as _stream_response,
                        execute_tool_loop as _execute_tool_loop,
                        extract_mentioned_players as _extract_players_resp,
                        classify_query as _classify_q,
                    )
                except Exception as _import_err:
                    _status.error(f"Import error: {_import_err}")
                    _stream_response = None

                if _stream_response:
                    _cur_tid = st.session_state.get("chat_tid")
                    _last_players = st.session_state.get("chat_last_players", [])

                    # ── Session base context cache ─────────────────────────────
                    # Build the stable weekly context once per session (or when the
                    # tournament changes). Reuse it every turn so we only rebuild
                    # the intent-specific dynamic layer each message.
                    # This gives Anthropic's prompt cache a stable block to hit.
                    _base_cache_key = f"_chat_base_ctx_{_cur_tid or 'none'}"
                    if _base_cache_key not in st.session_state:
                        _status.markdown('<p class="chat-status">Loading session context...</p>', unsafe_allow_html=True)
                        try:
                            st.session_state[_base_cache_key] = _build_base_ctx(tournament_id=_cur_tid)
                        except Exception:
                            st.session_state[_base_cache_key] = None
                    _cached_base = st.session_state.get(_base_cache_key)

                    # Step 1: Build dynamic context (intent-specific layer only)
                    _status.markdown('<p class="chat-status">Loading data...</p>', unsafe_allow_html=True)
                    try:
                        _context = _build_ctx(
                            query=_prompt,
                            tournament_id=_cur_tid,
                            last_players=_last_players,
                            cached_base=_cached_base,
                        )
                        _intent_dict = _classify_q(_prompt)
                        _cur_meta = {
                            "intent":  _chat_intent_key(_intent_dict),
                            "players": _intent_dict.get("players", []) or _last_players,
                            "tid":     _cur_tid or "",
                        }
                    except Exception as _ctx_err:
                        _context = "You are a golf analytics assistant."
                        _cur_meta = {}

                    # Build message list
                    _messages = [{"role": "system", "content": _context}]
                    _messages += [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state["chat_history"][-20:]
                    ]

                    # Step 2: Tool loop (web search if Claude + Anthropic key)
                    if _api_key.startswith("sk-ant-"):
                        _status.markdown('<p class="chat-status">Thinking...</p>', unsafe_allow_html=True)
                        try:
                            _no_search_intents = {'is_round_recap', 'is_scoring_prop', 'is_picks_checkin', 'is_daily_bet', 'is_season_performance', 'is_tournament_results'}
                            _allow_search = not any(_intent_dict.get(k) for k in _no_search_intents)
                            _messages, _searches_run = _execute_tool_loop(_messages, _api_key, _allow_web_search=_allow_search)
                        except Exception:
                            _searches_run = []
                        if _searches_run:
                            _search_labels = " · ".join(f'"{q}"' for q in _searches_run)
                            _status.markdown(f'<p class="chat-status">Searched: {_search_labels}</p>', unsafe_allow_html=True)

                    _status.empty()

                    # Step 3: Stream response
                    try:
                        _response_text = st.write_stream(_stream_response(_messages, _api_key))
                    except Exception as _err:
                        _response_text = f"Error: {_err}"
                        st.error(_response_text)

                    # Show search attribution under the response
                    if _searches_run:
                        _badges = " ".join(
                            f'<span class="search-badge">searched: {q}</span>'
                            for q in _searches_run
                        )
                        st.markdown(_badges, unsafe_allow_html=True)

                    # Render supplement inside the same bubble, right after the text
                    if _response_text and _cur_meta.get("intent", "general") != "general":
                        _render_chat_supplement(_cur_meta)

            if _response_text:
                st.session_state["chat_history"].append(
                    {"role": "assistant", "content": _response_text, "meta": _cur_meta}
                )
                # Extract players mentioned for follow-up context
                try:
                    if _extract_players_resp:
                        st.session_state["chat_last_players"] = _extract_players_resp(_response_text)
                except Exception:
                    pass
                # Persist this exchange to the DB for future session context
                try:
                    from scripts.chat.conversation_store import log_exchange as _log_exchange
                    _log_exchange(
                        tournament_id=_cur_tid,
                        phase=st.session_state.get("chat_phase", "pre_tournament"),
                        question=_prompt,
                        response=_response_text,
                    )
                except Exception:
                    pass


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


    _tab_strategy, _tab_stats = st.tabs([
        "🎯 Usage Strategy",
        "📊 Season Stats",
    ])

    with _tab_strategy:
        # ── Season Usage Strategy ──────────────────────────────────────────────────
        try:
            from scripts.predictions.season_strategy import get_season_strategy as _get_strategy
            _strat = _get_strategy()
            if "error" not in _strat:
                _ce      = _strat["current_event"]
                _bud     = _strat["budget"]
                _pstrat  = _strat["player_strategy"]
                _pevents = _strat["premium_events"]
                _lineup  = _strat.get("weekly_lineup", {})

                # ── Optimal Lineup Card ───────────────────────────────────────
                import html as _hesc_lu
                _lu_players = _lineup.get("players", [])
                _lu_total   = _lineup.get("total_ev", 0)
                _lu_alts    = _lineup.get("alt_lineups", {})
                _tier_colors = {"elite": "#f1c40f", "strong": "#00c44f", "mid": "#4cb8ff", "value": "#9b59b6"}

                if _lu_players:
                    _lu_cards = ""
                    for _lp in _lu_players:
                        _lc = _tier_colors.get(_lp.get("tier",""), "#7a9bbf")
                        _lu_name = _hesc_lu.escape(_lp["name"])
                        _lu_ev   = _lp["ev"]
                        _lu_uses = _lp.get("uses_left", 0)
                        _lu_dots = "●" * _lu_uses + "○" * (3 - _lu_uses)
                        _lu_win  = _lp.get("win_prob", 0)
                        _lu_t10  = _lp.get("top10_prob", 0)
                        # Alt cost if you save this player
                        _alt     = _lu_alts.get(_lp["name"], {})
                        _alt_cost = _alt.get("ev_cost", 0)
                        _alt_str  = (
                            f'<div style="font-size:0.6em;color:#ef4444;margin-top:3px;">'
                            f'Save cost: −{_alt_cost:,} EV</div>'
                        ) if _alt_cost > 0 else ""
                        _lu_cards += f"""
<div style="flex:1;min-width:130px;background:#060f1c;border:1px solid {_lc}44;
            border-top:3px solid {_lc};border-radius:0 0 8px 8px;padding:12px 14px;">
  <div style="font-size:0.6em;font-weight:800;color:{_lc};letter-spacing:.1em;
              text-transform:uppercase;margin-bottom:4px;">{_lp.get("tier","").upper()}</div>
  <div style="font-size:0.9em;font-weight:700;color:#e8f0f8;line-height:1.2;
              margin-bottom:6px;">{_lu_name}</div>
  <div style="font-size:1.1em;font-weight:800;color:{_lc};">{_lu_ev:,} <span style="font-size:0.55em;color:#4a6080;">EV</span></div>
  <div style="font-size:0.65em;color:#4a6080;margin-top:3px;">{_lu_win:.0f}% win · {_lu_t10:.0f}% top-10</div>
  <div style="font-size:0.65em;color:#3a5070;letter-spacing:2px;margin-top:3px;">{_lu_dots}</div>
  {_alt_str}
</div>"""

                    st.markdown(f"""
<div style="background:#07101e;border:1px solid #0e2040;border-radius:10px;
            padding:16px 18px;margin-bottom:16px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <div>
      <span style="font-size:0.62em;font-weight:800;color:#4cb8ff;letter-spacing:.12em;
                   text-transform:uppercase;">Optimal Lineup This Week</span>
      <span style="font-size:0.62em;color:#2a4060;margin-left:10px;">
        {_hesc_lu.escape(_ce.get("name",""))}</span>
    </div>
    <div style="text-align:right;">
      <div style="font-size:1.2em;font-weight:800;color:#00c44f;">{_lu_total:,}</div>
      <div style="font-size:0.58em;color:#2a4060;text-transform:uppercase;">Combined EV</div>
    </div>
  </div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;">{_lu_cards}</div>
</div>""", unsafe_allow_html=True)

                # Verdict banner
                _tier_color = {"premium": "#00c44f", "high": "#4cb8ff", "standard": "#f59e0b"}.get(
                    _ce.get("tier", "standard"), "#f59e0b"
                )
                _tier_icon = {"premium": "MAJOR / PREMIUM", "high": "HIGH VALUE", "standard": "STANDARD EVENT"}.get(
                    _ce.get("tier", "standard"), "STANDARD EVENT"
                )
                st.markdown(
                    f"""<div style="border-left:4px solid {_tier_color};border-radius:0 10px 10px 0;
                      padding:14px 20px;background:{_tier_color}12;margin-bottom:20px;
                      border-top:1px solid {_tier_color}22;border-right:1px solid {_tier_color}22;
                      border-bottom:1px solid {_tier_color}22;">
                      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                        <span style="font-size:0.62em;font-weight:800;color:{_tier_color};
                          letter-spacing:0.12em;background:{_tier_color}22;
                          padding:2px 8px;border-radius:4px;">{_tier_icon}</span>
                        <span style="font-size:0.62em;color:#7a9bbf;letter-spacing:0.06em;">
                          SEASON USAGE STRATEGY</span>
                      </div>
                      <div style="font-size:0.97em;color:#e8f0f8;font-weight:500;line-height:1.5;">
                        {_strat['this_week_verdict']}</div>
                      <div style="display:flex;gap:20px;margin-top:10px;flex-wrap:wrap;">
                        <span style="font-size:0.72em;color:#7a9bbf;">
                          <span style="color:#e8f0f8;font-weight:600;">{_bud['uses_remaining']}</span>
                          &nbsp;uses banked</span>
                        <span style="font-size:0.72em;color:#7a9bbf;">
                          <span style="color:#e8f0f8;font-weight:600;">{_bud['weeks_remaining']}</span>
                          &nbsp;weeks left</span>
                        <span style="font-size:0.72em;color:#7a9bbf;">
                          ~<span style="color:#f59e0b;font-weight:600;">{_bud['new_players_needed']}</span>
                          &nbsp;new players still needed</span>
                      </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Upcoming premium events timeline (collapsed by default)
                _upcoming = [e for e in _pevents if e["tier"] in ("premium", "high")][:6]
                if _upcoming:
                  with st.expander("Upcoming premium events", expanded=False):
                    _ev_html_parts = []
                    for _uev in _upcoming:
                        import html as _hesc_uev
                        _utc    = {"premium": "#00c44f", "high": "#4cb8ff"}.get(_uev["tier"], "#7a9bbf")
                        _ubadge = {"premium": "MAJOR", "high": "SIGNATURE"}.get(_uev["tier"], "EVENT")
                        _udate  = _uev.get("start_date", "")[:10]
                        _uname  = _hesc_uev.escape(_uev["name"])
                        _ev_html_parts.append(
                            f"""<div style="flex:1;min-width:120px;max-width:180px;
                              border:1px solid {_utc}33;border-top:3px solid {_utc};
                              border-radius:0 0 8px 8px;padding:10px 12px;background:{_utc}08;">
                              <div style="font-size:0.58em;font-weight:800;color:{_utc};
                                letter-spacing:0.1em;margin-bottom:4px;">{_ubadge}</div>
                              <div style="font-size:0.8em;font-weight:700;color:#e8f0f8;
                                line-height:1.25;margin-bottom:6px;">{_uname}</div>
                              <div style="font-size:0.65em;color:#7a9bbf;">{_udate}</div>
                              <div style="font-size:0.68em;color:{_utc};font-weight:600;
                                margin-top:3px;">${_uev['purse']/1e6:.0f}M purse</div>
                            </div>"""
                        )
                    st.markdown(
                        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;">'
                        + "".join(_ev_html_parts) + "</div>",
                        unsafe_allow_html=True,
                    )

                # Player cards
                def _sp_all_premium(p):
                    return len(p["best_events"]) > 0 and all(e["tier"] == "premium" for e in p["best_events"])
                def _sp_has_premium(p):
                    return any(e["tier"] == "premium" for e in p["best_events"])
                def _sp_has_non_premium(p):
                    return any(e["tier"] != "premium" for e in p["best_events"])

                _sp_use   = [(n, p) for n, p in _pstrat.items() if p["use_this_week"]]
                _sp_save  = [(n, p) for n, p in _pstrat.items()
                             if not p["use_this_week"] and (p["save_signal"] or _sp_all_premium(p))]
                _sp_split = [(n, p) for n, p in _pstrat.items()
                             if not p["use_this_week"] and not p["save_signal"]
                             and not _sp_all_premium(p) and _sp_has_premium(p) and _sp_has_non_premium(p)]
                _sp_ok    = [(n, p) for n, p in _pstrat.items()
                             if not p["use_this_week"] and not p["save_signal"]
                             and not _sp_all_premium(p) and not _sp_has_premium(p)]

                # ── Roster table — one row per player ─────────────────────────
                import html as _hesc
                _all_players = (
                    [(n, p, "USE NOW",  "#00c44f") for n, p in _pstrat.items() if p["use_this_week"]] +
                    [(n, p, "SAVE",     "#ef4444") for n, p in _pstrat.items()
                     if not p["use_this_week"] and (p["save_signal"] or _sp_all_premium(p))] +
                    [(n, p, "USE/SAVE", "#f97316") for n, p in _pstrat.items()
                     if not p["use_this_week"] and not p["save_signal"]
                     and not _sp_all_premium(p) and _sp_has_premium(p) and _sp_has_non_premium(p)] +
                    [(n, p, "OK",       "#4cb8ff") for n, p in _pstrat.items()
                     if not p["use_this_week"] and not p["save_signal"]
                     and not _sp_all_premium(p) and not _sp_has_premium(p)]
                )
                _all_players.sort(key=lambda x: (
                    {"USE NOW": 0, "SAVE": 1, "USE/SAVE": 2, "OK": 3}[x[2]], x[1]["world_rank"]
                ))

                _row_parts = []
                for _rn, _rp, _rec, _rc in _all_players:
                    _best   = _rp["best_events"]
                    _target = " ".join(_best[0]["name"].split()[:3]) if _best else "—"
                    _wa     = _best[0].get("weeks_away", 0) if _best else 0
                    _target += f" ({int(_wa)}w)" if _wa > 0.5 else " (this wk)"
                    _uses   = _rp["uses_left"]
                    _dots   = "●" * _uses + "○" * (3 - _uses)
                    _hot    = " ↑" if _rp.get("is_hot_streak") else ""
                    # Opportunity cost column
                    _opp_ev  = int(_rp.get("opportunity_cost_ev", 0) or 0)
                    _opp_pct = float(_rp.get("opportunity_cost_pct", 0) or 0)
                    _tw_ev   = int(_rp.get("this_week_ev", 0) or 0)
                    _bf_ev   = int(_rp.get("best_future_ev", 0) or 0)
                    if _rec == "SAVE" and _opp_ev > 0:
                        _opp_cell = (
                            f'<div style="font-size:0.72em;color:#e8f0f8;">'
                            f'{_tw_ev:,} → {_bf_ev:,}</div>'
                            f'<div style="font-size:0.65em;color:#ef4444;">'
                            f'+{_opp_ev:,} EV ({_opp_pct:.0f}%) later</div>'
                        )
                    elif _rec == "USE NOW" and _tw_ev > 0:
                        _opp_cell = (
                            f'<div style="font-size:0.72em;color:#00c44f;">{_tw_ev:,} EV</div>'
                        )
                    else:
                        _opp_cell = f'<div style="font-size:0.72em;color:#4a6080;">{_tw_ev:,}</div>'

                    _row_parts.append(
                        f'<tr>'
                        f'<td style="padding:7px 10px;font-weight:600;color:#e8f0f8;">'
                        f'{_hesc.escape(_rn)}{_hot}</td>'
                        f'<td style="padding:7px 6px;font-size:0.75em;color:#7a9bbf;">#{_rp["world_rank"]}</td>'
                        f'<td style="padding:7px 6px;letter-spacing:1px;color:#7a9bbf;">{_dots}</td>'
                        f'<td style="padding:7px 8px;">'
                        f'<span style="font-size:0.7em;font-weight:800;color:{_rc};'
                        f'background:{_rc}22;padding:2px 7px;border-radius:4px;">{_rec}</span></td>'
                        f'<td style="padding:7px 10px;font-size:0.8em;color:#a0b8d0;">'
                        f'{_hesc.escape(_target)}</td>'
                        f'<td style="padding:7px 10px;">{_opp_cell}</td>'
                        f'</tr>'
                    )

                st.markdown(
                    '<table style="width:100%;border-collapse:collapse;font-size:0.88em;">'
                    '<thead><tr style="border-bottom:1px solid #1c2f4a;">'
                    '<th style="padding:6px 10px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">PLAYER</th>'
                    '<th style="padding:6px 6px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">WR</th>'
                    '<th style="padding:6px 6px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">USES</th>'
                    '<th style="padding:6px 8px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">REC</th>'
                    '<th style="padding:6px 10px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">TARGET</th>'
                    '<th style="padding:6px 10px;text-align:left;font-size:0.65em;color:#4a6080;font-weight:700;letter-spacing:0.1em;">EV / OPP COST</th>'
                    '</tr></thead><tbody>'
                    + "".join(_row_parts) +
                    '</tbody></table>',
                    unsafe_allow_html=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)


                # ── Season Allocation Plan (collapsed) ────────────────────────────
                _sp_plan      = _strat.get("season_plan", {})
                _sp_conflicts = _strat.get("plan_conflicts", {})

                if _sp_plan:
                  with st.expander("Season allocation plan", expanded=False):
                    st.caption("Greedy optimizer: highest-EV assignment wins, 3 players/week cap.")

                    # Group plan events into columns of 2
                    _plan_items = [
                        (ev_name, ev_data) for ev_name, ev_data in _sp_plan.items()
                        if ev_data.get("assigned")
                    ]
                    for _pi in range(0, len(_plan_items), 2):
                        _pcols = st.columns(2)
                        for _pccol, (_pev_name, _pev_data) in zip(_pcols, _plan_items[_pi:_pi+2]):
                            import html as _hesc_pev
                            _pev_tier    = _pev_data.get("tier", "standard")
                            _pev_date    = _pev_data.get("date", "")[:10]
                            _pev_type    = _pev_data.get("type", "")
                            _pev_assigned = _pev_data.get("assigned", [])
                            _pev_tc      = {"premium": "#00c44f", "high": "#4cb8ff"}.get(_pev_tier, "#7a9bbf")
                            _pev_badge   = {"premium": "MAJOR", "high": "SIGNATURE"}.get(_pev_tier, _pev_type.upper()[:10])
                            _pev_name_esc = _hesc_pev.escape(_pev_name)
                            _pev_players  = " · ".join(_hesc_pev.escape(p) for p in _pev_assigned)
                            _pev_html = (
                                f'<div style="border:1px solid {_pev_tc}33;border-top:2px solid {_pev_tc};'
                                f'border-radius:0 0 8px 8px;padding:10px 12px;background:{_pev_tc}06;margin-bottom:8px;">'
                                f'<div style="font-size:0.58em;font-weight:800;color:{_pev_tc};letter-spacing:0.1em;">{_pev_badge}</div>'
                                f'<div style="font-size:0.82em;font-weight:700;color:#e8f0f8;margin:3px 0;">{_pev_name_esc}</div>'
                                f'<div style="font-size:0.65em;color:#7a9bbf;margin-bottom:6px;">{_pev_date}</div>'
                                f'<div style="font-size:0.72em;color:#e8f0f8;">{_pev_players}</div>'
                                f'</div>'
                            )
                            with _pccol:
                                st.markdown(_pev_html, unsafe_allow_html=True)

                # ── Conflict Warnings (collapsed) ─────────────────────────────────
                if _sp_conflicts:
                  with st.expander(f"Scheduling conflicts ({len(_sp_conflicts)})", expanded=False):
                    import html as _cf_hesc
                    st.caption(
                        f"{len(_sp_conflicts)} event(s) where more than 3 players peak simultaneously. "
                        "Top-3 by EV get the slot — others need alternate weeks."
                    )
                    _cf_sorted = sorted(_sp_conflicts.items(), key=lambda x: x[1].get("week", 0))
                    _cf_col_list = st.columns(min(2, len(_cf_sorted)))
                    for _cfi, (_cf_name, _cf_data) in enumerate(_cf_sorted):
                        _cf_assigned = _cf_data.get("assigned", [])
                        _cf_overflow = _cf_data.get("overflow", [])
                        _cf_date     = _cf_data.get("date", "")[:10]
                        _cf_total    = len(_cf_assigned) + len(_cf_overflow)
                        _cf_a_html   = " &nbsp;·&nbsp; ".join(
                            f'<span style="color:#00c44f;font-weight:600">{_cf_hesc.escape(p)}</span>'
                            for p in _cf_assigned
                        )
                        _cf_ov_list  = _cf_overflow[:5]
                        _cf_ov_html  = " &nbsp;·&nbsp; ".join(
                            f'<span style="color:#f97316">{_cf_hesc.escape(p)}</span>'
                            for p in _cf_ov_list
                        )
                        _cf_more_html = (
                            f'<span style="color:#7a9bbf"> +{len(_cf_overflow)-5} more</span>'
                            if len(_cf_overflow) > 5 else ""
                        )
                        with _cf_col_list[_cfi % 2]:
                            st.markdown(
                                f'<div style="border:1px solid #f9731633;border-left:3px solid #f97316;'
                                f'border-radius:0 8px 8px 0;padding:10px 14px;'
                                f'background:#f9731608;margin-bottom:8px">'
                                f'<div style="display:flex;justify-content:space-between;'
                                f'align-items:baseline;margin-bottom:8px">'
                                f'<span style="font-size:0.88em;font-weight:700;color:#e8f0f8">'
                                f'{_cf_hesc.escape(_cf_name)}</span>'
                                f'<span style="font-size:0.6em;color:#7a9bbf;margin-left:8px">'
                                f'{_cf_date} &nbsp;·&nbsp; {_cf_total} players want in</span></div>'
                                f'<div style="font-size:0.7em;margin-bottom:6px">'
                                f'<span style="font-size:0.85em;text-transform:uppercase;'
                                f'letter-spacing:0.07em;color:#00c44f">Gets slot</span><br>'
                                f'<span style="line-height:2">{_cf_a_html}</span></div>'
                                f'<div style="font-size:0.7em;padding-top:6px;'
                                f'border-top:1px solid #f9731622">'
                                f'<span style="font-size:0.85em;text-transform:uppercase;'
                                f'letter-spacing:0.07em;color:#f97316">Needs alternative</span><br>'
                                f'<span style="line-height:2">{_cf_ov_html}{_cf_more_html}</span></div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

        except Exception as _strat_err:
            st.caption(f"Season strategy unavailable: {_strat_err}")


    with _tab_stats:
        st.markdown("### Season Scorecard")
        st.caption(f"WineTime · 2026 · Synced from [protourfantasygolf.com](https://connection.protourfantasygolf.com/scorecard/individual/2026/0/133)")

        _sc_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
        if _sc_path.exists():
            try:
                import json as _json
                _sc = _json.loads(_sc_path.read_text())
                _wl = _sc.get("weekly_lineups", {})
                _sc_rows = []
                for _wk_key in sorted(_wl.keys(), key=lambda x: int(x.split("_")[1])):
                    _e = _wl[_wk_key]
                    _lineup = _e.get("lineup", [])
                    if not _lineup and not _e.get("earnings_earned"):
                        continue  # skip empty future weeks
                    _week   = _e.get("week", "")
                    _tourney = _e.get("tournament", "")
                    _earn   = _e.get("earnings_earned")
                    _wrp    = _e.get("wrp", "")
                    _picks  = _sc.get("picks", {})
                    _p_cols = []
                    for _pn in _lineup[:3]:
                        _trec = next(
                            (t for t in _picks.get(_pn, {}).get("tournaments_used", [])
                             if t.get("week") == _week),
                            {}
                        )
                        _res  = _trec.get("result") or ("?" if not _earn else "—")
                        _earn_p = _trec.get("earnings", 0) or 0
                        _p_cols.append(f"{_pn.split()[-1]} ({_res}) ${_earn_p:,}" if _earn else f"{_pn.split()[-1]}")
                    while len(_p_cols) < 3:
                        _p_cols.append("—")
                    _sc_rows.append({
                        "Wk":         _week,
                        "Tournament": _tourney,
                        "WRP":        _wrp if _wrp else "—",
                        "Pick 1":     _p_cols[0],
                        "Pick 2":     _p_cols[1],
                        "Pick 3":     _p_cols[2],
                        "Earnings":   f"${_earn:,}" if _earn else ("Pending" if _lineup else "—"),
                    })
                if _sc_rows:
                    _sc_df = pd.DataFrame(_sc_rows)
                    st.dataframe(_sc_df, hide_index=True, use_container_width=True)
                    _season_total = _sc.get("summary", {}).get("total_earnings", 0)
                    _completed    = sum(1 for r in _sc_rows if r["Earnings"] not in ("Pending", "—"))
                    st.caption(f"**{_completed} completed weeks · Season total: ${_season_total:,}**")
                else:
                    st.info("No picks recorded yet.")
            except Exception as _sc_e:
                st.warning(f"Could not load scorecard: {_sc_e}")
        else:
            st.info("Tracker not found. Run the scorecard sync first.")

        if st.button("Sync from Fantasy Site", key="sync_scorecard_btn"):
            with st.spinner("Fetching from protourfantasygolf.com..."):
                _sync_out = run_script("scrapers/fetch_fantasy_scorecard.py")
            st.code(_sync_out, language=None)
            st.cache_data.clear()
            st.rerun()


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

        player_search = st.selectbox("Select a player:", [""] + all_players, key="quick_player")

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



                
                


                                                                
                                
                
                
                
                
                
                
                
                
                
                
                                           

            # Betting profile if available
            _profiles_tid = _tournament_id_from_df(preds_df)
            if not _profiles_tid:
                _profiles_tid = _latest_tournament_id_from_prop_lines()
            profiles_df = load_betting_profiles(_profiles_tid if _profiles_tid else None)
            if not profiles_df.empty:
                profile = get_player_profile(profiles_df, player_search)
                if profile:
                    st.markdown("#### 🎰 Betting Profile")
                    render_player_profile_card(profile, show_full=True, pred_data=player_data if player_data else None)

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

            # ── DG Approach Skill ──────────────────────────────────────────────
            # Per-player SG/shot broken down by distance range × lie type.
            # Data source: DataGolf /preds/approach-skill?period=l24
            _as_path = DATA_DIR / "datagolf" / "dg_approach_skill_latest.csv"
            if _as_path.exists():
                try:
                    _as_full = pd.read_csv(_as_path)
                    # Match by last name (DG uses "Last, First")
                    _as_last = player_search.strip().split()[-1].lower()
                    _as_row = _as_full[_as_full["player_name"].str.lower().str.contains(_as_last, na=False)]
                    # Narrow to exact if multiple
                    if len(_as_row) > 1:
                        _as_exact = _as_row[_as_row["player_name"].apply(_name_key) == _name_key(player_search)]
                        if not _as_exact.empty:
                            _as_row = _as_exact
                    if not _as_row.empty:
                        _asr = _as_row.iloc[0]
                        _as_composite = _asr.get("approach_skill_sg")
                        _as_prox = _asr.get("approach_skill_proximity")
                        _as_shots = _asr.get("approach_skill_shot_total")

                        # Compute vs-field using full dataset
                        _as_field_mean = pd.to_numeric(_as_full["approach_skill_sg"], errors="coerce").mean()
                        _as_vsf = (float(_as_composite) - _as_field_mean) if pd.notna(_as_composite) else None

                        st.markdown("---")
                        st.markdown("#### DG Approach Skill")
                        _as_period = _asr.get("time_period", "last 24 months")
                        _as_updated = str(_asr.get("last_updated", "")).split(" ")[0]
                        _as_shots_str = f"{int(_as_shots):,}" if _as_shots and pd.notna(_as_shots) else "—"
                        st.caption(f"DataGolf shot-quality model · {_as_period} · {_as_shots_str} approach shots tracked · Updated {_as_updated}")

                        # Composite metric card
                        if pd.notna(_as_composite):
                            _as_c_val = float(_as_composite)
                            _as_v_val = float(_as_vsf) if _as_vsf is not None else 0.0
                            _as_c_col = "#00c44f" if _as_c_val > _as_field_mean else "#e53935"
                            _as_prox_str = f"{float(_as_prox):.1f} ft avg" if _as_prox and pd.notna(_as_prox) else ""
                            # Field rank for composite
                            _as_all_vals = pd.to_numeric(_as_full["approach_skill_sg"], errors="coerce").dropna().sort_values(ascending=False)
                            _as_fld_rank = int(((_as_all_vals > _as_c_val).sum()) + 1)
                            _as_fld_total = int(_as_all_vals.notna().sum())

                            st.markdown(
                                f"<div style='background:#0b1929;border:1px solid #1a3050;border-top:3px solid {_as_c_col};"
                                f"border-radius:8px;padding:12px 16px;display:flex;align-items:center;gap:20px;margin-bottom:10px;'>"
                                f"<div style='flex:0 0 auto;text-align:center;'>"
                                f"<div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>Composite SG/Shot</div>"
                                f"<div style='font-size:28px;font-weight:800;color:#dde6f5;'>{_as_c_val:+.4f}</div>"
                                f"<div style='font-size:12px;color:{_as_c_col};font-weight:700;'>#{_as_fld_rank} of {_as_fld_total} players</div>"
                                f"</div>"
                                f"<div style='flex:1;'>"
                                f"<div style='font-size:11px;color:#6a8caf;'>vs field avg ({_as_field_mean:+.4f}): <span style='color:{_as_c_col};font-weight:700;'>{_as_v_val:+.4f}</span></div>"
                                f"{'<div style=\"font-size:11px;color:#6a8caf;margin-top:3px;\">Avg proximity: <span style=\"color:#dde6f5;\">' + _as_prox_str + '</span></div>' if _as_prox_str else ''}"
                                f"<div style='font-size:10px;color:#4a6080;margin-top:6px;'>Shot-count-weighted average SG per approach shot across all distance×lie segments with sufficient data.</div>"
                                f"</div></div>",
                                unsafe_allow_html=True,
                            )

                        # Per-segment breakdown
                        _as_segs = [
                            ("50–100 yd FW",   "50_100_fw"),
                            ("100–150 yd FW",  "100_150_fw"),
                            ("150–200 yd FW",  "150_200_fw"),
                            ("200+ yd FW",     "over_200_fw"),
                            ("Under 150 Rough","under_150_rgh"),
                            ("Over 150 Rough", "over_150_rgh"),
                        ]
                        _as_seg_cols = st.columns(3)
                        _as_seg_i = 0
                        for _seg_label, _seg_key in _as_segs:
                            _sg_ps = _asr.get(f"{_seg_key}_sg_per_shot")
                            _prox_ps = _asr.get(f"{_seg_key}_proximity_per_shot")
                            _cnt = _asr.get(f"{_seg_key}_shot_count")
                            _low = _asr.get(f"{_seg_key}_low_data_indicator", 1)
                            _gir = _asr.get(f"{_seg_key}_gir_rate")

                            _sg_v = float(_sg_ps) if _sg_ps is not None and pd.notna(_sg_ps) else None
                            _pr_v = float(_prox_ps) if _prox_ps is not None and pd.notna(_prox_ps) else None
                            _cnt_v = int(_cnt) if _cnt is not None and pd.notna(_cnt) else 0
                            _gir_v = float(_gir) * 100 if _gir is not None and pd.notna(_gir) else None
                            _low_flag = bool(int(_low)) if _low is not None else True

                            _seg_color = "#4a6080" if _low_flag else ("#00c44f" if (_sg_v or 0) > 0 else "#e53935")
                            _seg_alpha = "0.4" if _low_flag else "1"
                            _sg_str = f"{_sg_v:+.3f}" if _sg_v is not None else "—"
                            _pr_str = f"{_pr_v:.0f} ft" if _pr_v is not None else "—"
                            _gir_str = f"{_gir_v:.0f}%" if _gir_v is not None else "—"
                            _low_badge = "<span style='color:#888;font-size:9px;margin-left:4px;'>(low data)</span>" if _low_flag else ""

                            with _as_seg_cols[_as_seg_i % 3]:
                                st.markdown(
                                    f"<div style='background:#0b1929;border:1px solid #1a3050;border-radius:7px;"
                                    f"padding:9px 12px;margin-bottom:8px;opacity:{_seg_alpha};'>"
                                    f"<div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.5px;text-transform:uppercase;'>{_seg_label}{_low_badge}</div>"
                                    f"<div style='display:flex;gap:14px;margin-top:6px;align-items:baseline;'>"
                                    f"<div><div style='font-size:18px;font-weight:800;color:{_seg_color};'>{_sg_str}</div><div style='font-size:9px;color:#4a6080;'>SG/SHOT</div></div>"
                                    f"<div><div style='font-size:13px;font-weight:600;color:#dde6f5;'>{_pr_str}</div><div style='font-size:9px;color:#4a6080;'>PROXIMITY</div></div>"
                                    f"<div><div style='font-size:13px;font-weight:600;color:#dde6f5;'>{_gir_str}</div><div style='font-size:9px;color:#4a6080;'>GIR</div></div>"
                                    f"<div style='margin-left:auto;text-align:right;'><div style='font-size:11px;color:#4a6080;'>{_cnt_v:,}</div><div style='font-size:9px;color:#4a6080;'>shots</div></div>"
                                    f"</div></div>",
                                    unsafe_allow_html=True,
                                )
                            _as_seg_i += 1
                except Exception:
                    pass

            # ── DG Skill Ratings ───────────────────────────────────────────────
            # DataGolf's own shot-level skill estimates per player.
            # More stable than recent SG — reflects true ability, not just recent form.
            
            try:
                import duckdb as _duckdb
                _db_path = str(DATA_DIR / "golf_data.db")
                with _duckdb.connect(_db_path, read_only=True) as _dbc:
                    _sr_full = _dbc.execute("SELECT * FROM dg_rankings").df()
                    
                _sr_last = player_search.strip().split()[-1].lower()
                _sr_row = _sr_full[_sr_full['player_name'].str.lower().str.contains(_sr_last, na=False)]
                if len(_sr_row) > 1:
                    _sr_exact = _sr_row[_sr_row['player_name'].apply(_name_key) == _name_key(player_search)]
                    if not _sr_exact.empty:
                        _sr_row = _sr_exact
                if not _sr_row.empty:
                    _srr = _sr_row.iloc[0]
                    _sr_updated = str(_srr.get("last_updated", "")).split(" ")[0]
                    
                    st.markdown("---")
                    st.markdown("#### DG Skill Ratings")
                    st.caption(f"DataGolf shot-level skill estimates · More stable than recent SG · Updated {_sr_updated}")
                    _SR_DEFS = [
                          ("sg_total", "Total"),
                          ("sg_ott",   "Off Tee"),
                          ("sg_app",   "Approach"),
                          ("sg_arg",   "Around Green"),
                          ("sg_putt",  "Putting"),
                      ]
                    
                    _sr_cols = st.columns(5)
                    for _sri, (_sr_col, _sr_label) in enumerate(_SR_DEFS):
                        _sr_val = _srr.get(_sr_col)
                        _sr_num = float(_sr_val) if _sr_val is not None and pd.notna(_sr_val) else None 
                        
                    
                        _sr_all = pd.to_numeric(_sr_full[_sr_col], errors="coerce")
                        _sr_fld_rank = int((_sr_all > (_sr_num or -999)).sum()) + 1 if _sr_num is not None else None
                        _sr_fld_total = int(_sr_all.notna().sum())
                        
                        _sr_color = (
                              "#00c44f" if _sr_fld_rank and _sr_fld_rank <= 5 else
                              "#6ddb9a" if _sr_fld_rank and _sr_fld_rank <= 15 else
                              "#dde6f5" if _sr_fld_rank and _sr_fld_rank <= 35 else
                              "#ffa726" if _sr_fld_rank and _sr_fld_rank <= 60 else
                              "#e53935"
                          )
                        _sr_val_str = f"{_sr_num:+.3f}" if _sr_num is not None else "—"
                        _sr_rank_str = f"#{_sr_fld_rank}" if _sr_fld_rank else "—"

                        with _sr_cols[_sri]:
                            st.markdown(
                                f"<div style='background:#0b1929;border:1px solid #1a3050;"
                                f"border-top:3px solid {_sr_color};border-radius:8px;"
                                f"padding:10px 12px;text-align:center;'>"
                                f"<div style='font-size:10px;color:#4a6080;margin-bottom:6px;"
                                f"font-weight:700;letter-spacing:.6px;text-transform:uppercase;'>{_sr_label}</div>"
                                f"<div style='font-size:22px;font-weight:800;color:#dde6f5;'>{_sr_val_str}</div>"
                                f"<div style='font-size:12px;color:{_sr_color};margin-top:2px;font-weight:700;'>"
                                f"{_sr_rank_str} of {_sr_fld_total}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
            except Exception:
                pass
            
            
            
            

            # ── DG Player Decompositions ───────────────────────────────────────
            # Event-specific: DG's full prediction broken into components.
            # final_pred = complete SG prediction for this week's course.
            # course_fit_delta = how much this course helps/hurts vs baseline.
            _dc_full = load_dg_decompositions()
            if not _dc_full.empty:
                try:
                    _dc_last = player_search.strip().split()[-1].lower()
                    _dc_row = _dc_full[_dc_full["player_name"].str.lower().str.contains(_dc_last, na=False)]
                    if len(_dc_row) > 1:
                        _dc_exact = _dc_row[_dc_row["player_name"].apply(_name_key) == _name_key(player_search)]
                        if not _dc_exact.empty:
                            _dc_row = _dc_exact
                    if not _dc_row.empty:
                        _dcr = _dc_row.iloc[0]
                        _dc_event   = str(_dcr.get("event_name", ""))
                        _dc_course  = str(_dcr.get("course_name", ""))
                        _dc_updated = str(_dcr.get("last_updated", "")).split(" ")[0]
                        _dc_base    = _dcr.get("baseline_pred")
                        _dc_final   = _dcr.get("final_pred")
                        _dc_delta   = _dcr.get("course_fit_delta")
                        _dc_std     = _dcr.get("std_deviation")

                        st.markdown("---")
                        st.markdown("#### DG Tournament Prediction")
                        st.caption(f"{_dc_event} @ {_dc_course} · DG prediction decomposition · Updated {_dc_updated}")

                        # Top row: baseline → final with delta
                        if pd.notna(_dc_final):
                            _dc_f = float(_dc_final)
                            _dc_b = float(_dc_base) if pd.notna(_dc_base) else 0.0
                            _dc_d = float(_dc_delta) if pd.notna(_dc_delta) else 0.0
                            _dc_d_col = "#00c44f" if _dc_d > 0.05 else ("#e53935" if _dc_d < -0.05 else "#aaaaaa")
                            _dc_f_col = "#00c44f" if _dc_f > 1.5 else ("#6ddb9a" if _dc_f > 0.5 else ("#ffa726" if _dc_f > -0.2 else "#e53935"))
                            _dc_std_str = f"±{float(_dc_std):.2f}" if _dc_std and pd.notna(_dc_std) else "—"

                            st.markdown(
                                f"<div style='background:#0b1929;border:1px solid #1a3050;border-top:3px solid {_dc_f_col};"
                                f"border-radius:8px;padding:12px 16px;display:flex;gap:24px;align-items:center;margin-bottom:10px;'>"
                                f"<div style='text-align:center;'><div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>DG Prediction</div>"
                                f"<div style='font-size:28px;font-weight:800;color:{_dc_f_col};'>{_dc_f:+.3f}</div>"
                                f"<div style='font-size:11px;color:#6a8caf;'>SG/round vs field</div></div>"
                                f"<div style='text-align:center;'><div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>Baseline</div>"
                                f"<div style='font-size:20px;font-weight:700;color:#dde6f5;'>{_dc_b:+.3f}</div>"
                                f"<div style='font-size:11px;color:#6a8caf;'>overall skill</div></div>"
                                f"<div style='text-align:center;'><div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>Course Fit</div>"
                                f"<div style='font-size:20px;font-weight:700;color:{_dc_d_col};'>{_dc_d:+.3f}</div>"
                                f"<div style='font-size:11px;color:#6a8caf;'>vs baseline</div></div>"
                                f"<div style='text-align:center;'><div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>Uncertainty</div>"
                                f"<div style='font-size:20px;font-weight:700;color:#9b9bff;'>{_dc_std_str}</div>"
                                f"<div style='font-size:11px;color:#6a8caf;'>std deviation</div></div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        # Adjustment breakdown — grouped by category
                        _dc_groups = [
                            ("Course", [
                                ("Course History",    "course_history_adjustment"),
                                ("Course Experience", "course_experience_adjustment"),
                            ]),
                            ("Style Fit", [
                                ("Driving Accuracy",  "driving_accuracy_adjustment"),
                                ("Driving Distance",  "driving_distance_adjustment"),
                                ("Approach Fit",      "cf_approach_comp"),
                                ("Short Game Fit",    "cf_short_comp"),
                                ("Other Fit",         "other_fit_adjustment"),
                            ]),
                            ("Form & Skill", [
                                ("Recent Form",       "timing_adjustment"),
                                ("SG Category",       "strokes_gained_category_adjustment"),
                            ]),
                            ("Other", [
                                ("Age",               "age_adjustment"),
                                ("Country",           "country_adjustment"),
                            ]),
                        ]

                        # Collect all values to normalise bar widths globally
                        _all_adj = []
                        for _, _items in _dc_groups:
                            for _lbl, _col in _items:
                                _v = _dcr.get(_col)
                                if _v is not None and pd.notna(_v):
                                    _all_adj.append((_lbl, _col, float(_v)))
                        _max_abs = max((abs(v) for _, _, v in _all_adj), default=0.01) or 0.01

                        def _adj_bar(lbl, v):
                            _pct = min(abs(v) / _max_abs * 100, 100)
                            _col = "#00c44f" if v > 0.003 else ("#e53935" if v < -0.003 else "#5a6a7a")
                            _left_pct  = max(0, -v / _max_abs * 50)   # negative → grows left from centre
                            _right_pct = max(0,  v / _max_abs * 50)   # positive → grows right from centre
                            return (
                                f"<div style='display:grid;grid-template-columns:120px 1fr 52px;"
                                f"align-items:center;gap:8px;padding:3px 0;'>"
                                f"<span style='font-size:10px;color:#6a8caf;text-align:right;'>{lbl}</span>"
                                f"<div style='display:grid;grid-template-columns:1fr 1fr;height:5px;'>"
                                f"<div style='display:flex;justify-content:flex-end;'>"
                                f"<div style='background:{'#e53935' if v<-0.003 else '#0d1e30'};width:{_left_pct:.1f}%;height:5px;border-radius:2px 0 0 2px;'></div>"
                                f"</div>"
                                f"<div style='display:flex;'>"
                                f"<div style='background:{'#00c44f' if v>0.003 else '#0d1e30'};width:{_right_pct:.1f}%;height:5px;border-radius:0 2px 2px 0;'></div>"
                                f"</div>"
                                f"</div>"
                                f"<span style='font-size:10px;font-weight:700;color:{_col};'>{v:+.3f}</span>"
                                f"</div>"
                            )

                        _group_htmls = []
                        for _g_title, _g_items in _dc_groups:
                            _g_rows = []
                            for _lbl, _col in _g_items:
                                _v = _dcr.get(_col)
                                if _v is not None and pd.notna(_v):
                                    _g_rows.append(_adj_bar(_lbl, float(_v)))
                            if _g_rows:
                                _group_htmls.append(
                                    f"<div style='margin-bottom:10px;'>"
                                    f"<div style='font-size:9px;font-weight:700;color:#2e4870;letter-spacing:.1em;"
                                    f"text-transform:uppercase;margin-bottom:4px;border-bottom:1px solid #0d1e30;padding-bottom:2px;'>{_g_title}</div>"
                                    + "".join(_g_rows) +
                                    f"</div>"
                                )

                        if _group_htmls:
                            # Total fit summary rows
                            _tot_hist = _dcr.get("total_course_history_adjustment")
                            _tot_fit  = _dcr.get("total_fit_adjustment")
                            _summary_rows = ""
                            for _slbl, _sv in [("Total Course", _tot_hist), ("Total Fit", _tot_fit)]:
                                if _sv is not None and pd.notna(_sv):
                                    _sc = "#00c44f" if float(_sv) > 0.01 else ("#e53935" if float(_sv) < -0.01 else "#888")
                                    _summary_rows += (
                                        f"<div style='display:flex;justify-content:space-between;padding:2px 0;"
                                        f"border-top:1px solid #0d1e30;'>"
                                        f"<span style='font-size:10px;color:#4a6080;'>{_slbl}</span>"
                                        f"<span style='font-size:10px;font-weight:700;color:{_sc};'>{float(_sv):+.3f}</span>"
                                        f"</div>"
                                    )

                            st.markdown(
                                f"<div style='background:#0b1929;border:1px solid #1a3050;border-radius:8px;padding:12px 16px;margin-top:8px;'>"
                                f"<div style='font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.6px;"
                                f"text-transform:uppercase;margin-bottom:10px;'>Adjustment Breakdown</div>"
                                f"<div style='font-size:9px;color:#2e4870;text-align:center;margin-bottom:8px;"
                                f"letter-spacing:.05em;'>← negative &nbsp;&nbsp;|&nbsp;&nbsp; positive →</div>"
                                + "".join(_group_htmls)
                                + (f"<div style='margin-top:6px;'>{_summary_rows}</div>" if _summary_rows else "")
                                + f"</div>",
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
                        with st.expander("📋 Detailed Stats (Driving, Approach, Putting, Scoring)", expanded=False):
                            st.caption("PGA Tour stats from this season · Rank = position among all players · Trend = rank change over last 3 events")
                            # 2419=Bogey Avg/Rnd, 2414=Bogey Avoid%; 2675/2567/2568/2569/2564 = SG stats
                            _FS_GROUPS = {
                                "Strokes Gained": [2675, 2567, 2568, 2569, 2564],
                                "Scoring":        [120, 156, 108, 160],
                                "Driving":        [101, 102, 2401],
                                "Approach":       [103, 331, 130, 299, 142, 143],
                                "Putting":        [104, 119, 413],
                                "Consistency":    [352, 2414, 2419, 111],
                            }
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
                                _sid_rows = _fs_player[_fs_player["stat_id"] == stat_id].sort_values("tournament_id")
                                if len(_sid_rows) < 2:
                                    return "—", "#4a6080"
                                ranks = pd.to_numeric(_sid_rows["rank"], errors="coerce").dropna().tolist()
                                if len(ranks) < 2:
                                    return "—", "#4a6080"
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
                                    _latest = _sid_data.sort_values("tournament_id", ascending=False).iloc[0]
                                    _trend, _tcolor = _trend_arrow(_sid)
                                    _grp_rows.append({
                                        "Stat":       _FS_NAME_OVERRIDE.get(_sid, _latest["stat_name"]),
                                        "Value":      _latest["stat_value"],
                                        "Rank":       int(_latest["rank"]) if pd.notna(_latest["rank"]) else "—",
                                        "_rank_num":  _latest["rank"],
                                        "Trend":      _trend,
                                        "_tcolor":    _tcolor,
                                    })
                                if not _grp_rows:
                                    continue
                                st.markdown(
                                    f"<div style='font-size:11px;font-weight:700;color:#4a6080;"
                                    f"letter-spacing:.8px;text-transform:uppercase;"
                                    f"margin:14px 0 6px;'>{_grp_name}</div>",
                                    unsafe_allow_html=True,
                                )
                                _cols_per_row = min(3, len(_grp_rows))
                                for _chunk_start in range(0, len(_grp_rows), _cols_per_row):
                                    _chunk = _grp_rows[_chunk_start:_chunk_start + _cols_per_row]
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
                                                f"<div style='display:flex;justify-content:space-between;align-items:baseline;'>"
                                                f"<span style='font-size:17px;font-weight:800;color:#dde6f5;'>{_item['Value']}</span>"
                                                f"<span style='font-size:13px;font-weight:700;color:{_rc};'>#{_item['Rank']}</span>"
                                                f"</div>"
                                                f"<div style='font-size:12px;color:{_item['_tcolor']};margin-top:2px;'>{_item['Trend']}</div>"
                                                f"</div>",
                                                unsafe_allow_html=True,
                                            )
                except Exception:
                    pass

            # ── Season Hit Rate Cards ──────────────────────────────────────────
            # Shows per-player success rate for top5/top10/top20/make_cut over
            # the last N tournaments in prediction_history, with dot-sequence
            # visual (green = hit, red = miss) similar to NBA/MLB prop trackers.
            _hr_path = OUTPUTS_DIR / "prediction_history.csv"
            if _hr_path.exists():
                try:
                    _hr_all = pd.read_csv(_hr_path)
                    # Normalize boolean columns — stored as 'True'/'False' strings or 0/1
                    def _to_bool(s):
                        if isinstance(s, bool): return s
                        if isinstance(s, (int, float)): return bool(s)
                        return str(s).strip().lower() in ("true", "1", "yes")

                    # Match player by name key
                    _hr_all["_nk"] = _hr_all["player_name"].apply(_name_key)
                    _hr_player = _hr_all[_hr_all["_nk"] == _name_key(player_search)].copy()
                    # Only rows with recorded results
                    if "result_recorded" in _hr_player.columns:
                        _hr_player = _hr_player[_hr_player["result_recorded"].apply(_to_bool)]

                    if len(_hr_player) >= 2:
                        _hr_player = _hr_player.sort_values("tournament_date", ascending=True)
                        _last20 = _hr_player.tail(20)

                        # Derive make_cut from actual_position (< 999 = made cut)
                        _pos = pd.to_numeric(_last20["actual_position"], errors="coerce")
                        _made_cut = (_pos < 999) & _pos.notna()

                        def _hit_series(col):
                            if col not in _last20.columns:
                                return pd.Series(dtype=bool)
                            return _last20[col].apply(_to_bool)

                        _metrics = [
                            ("Make Cut", _made_cut, "#00c44f"),
                            ("Top 20",   _hit_series("actual_top20"),   "#4cb8ff"),
                            ("Top 10",   _hit_series("actual_top10"),   "#f59e0b"),
                            ("Top 5",    _hit_series("actual_top5"),    "#f97316"),
                        ]

                        st.markdown("---")
                        st.markdown("#### 2026 Season Hit Rates")
                        st.caption(f"Last {len(_last20)} tournaments with recorded results")

                        _hr_cols = st.columns(4)
                        for _hci, (_hm_label, _hm_series, _hm_color) in enumerate(_metrics):
                            with _hr_cols[_hci]:
                                _hits = _hm_series.sum() if len(_hm_series) > 0 else 0
                                _total = len(_hm_series) if len(_hm_series) > 0 else len(_last20)
                                _rate = _hits / _total if _total > 0 else 0

                                # Dot sequence — last 10 results, newest right
                                _dot_series = _hm_series.tail(10) if len(_hm_series) > 0 else _made_cut.tail(10) * False
                                _dots_html = ""
                                for _dv in _dot_series:
                                    _dc = _hm_color if bool(_dv) else "#1c2f4a"
                                    _dots_html += (
                                        f'<span style="display:inline-block;width:10px;height:10px;'
                                        f'border-radius:50%;background:{_dc};margin:1px;'
                                        f'border:1px solid {_hm_color if bool(_dv) else "#2a3f5a"};"></span>'
                                    )

                                _rate_color = (
                                    _hm_color if _rate >= 0.5 else
                                    "#f39c12" if _rate >= 0.3 else
                                    "#7a9bbf"
                                )

                                st.markdown(
                                    f'<div style="background:#0d1a30;border:1px solid #1e3050;'
                                    f'border-top:3px solid {_hm_color};border-radius:8px;'
                                    f'padding:12px 14px;text-align:center;">'
                                    f'<div style="font-size:0.68em;font-weight:700;color:#7a9bbf;'
                                    f'letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">'
                                    f'{_hm_label}</div>'
                                    f'<div style="font-size:1.8em;font-weight:800;color:{_rate_color};'
                                    f'line-height:1;">{_rate*100:.0f}%</div>'
                                    f'<div style="font-size:0.72em;color:#4a6080;margin-bottom:8px;">'
                                    f'{int(_hits)}/{_total} starts</div>'
                                    f'<div style="line-height:1.4;">{_dots_html}</div>'
                                    f'</div>',
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

            # Sub-tabs for each analysis type
            deep_tab1, deep_tab2, deep_tab3, deep_tab4, deep_tab5 = st.tabs(
                ["⛳ Strokes Gained", "🔥 Form Analysis", "🏌️ Course Fit", "📈 Tour Stats", "🤖 DG Predictions"]
            )

            with deep_tab1:
                render_strokes_gained_analysis(stats_df)

            with deep_tab2:
                render_form_stats_section(stats_df)

            with deep_tab3:
                render_course_specific_stats(stats_df)
                st.markdown("---")
                st.markdown("### Player History")
                st.caption("Past starts and results at this exact course.")
                _deep_default_player = str(st.session_state.get("quick_player", "")).strip()
                _deep_player_options = [""] + all_players
                _deep_index = _deep_player_options.index(_deep_default_player) if _deep_default_player in _deep_player_options else 0
                _deep_player = st.selectbox(
                    "Select player",
                    options=_deep_player_options,
                    index=_deep_index,
                    key="deep_course_history_player",
                )
                render_player_event_history_panel(_deep_player, stats_df, panel_title="")

            with deep_tab4:
                st.caption("Most recent rank and value for each stat · Click any column header to sort")

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

                    _stat_categories = {
                        "Strokes Gained": [2675, 2567, 2568, 2569, 2564],
                        "Scoring":        [120, 156, 108, 160],
                        "Driving":        [101, 102, 2401],
                        "Approach":       [103, 331, 130, 299, 142, 143],
                        "Putting":        [104, 119, 413],
                        "Consistency":    [352, 2414, 2419, 111],
                    }
                    _ordered_stat_ids = [sid for ids in _stat_categories.values() for sid in ids]
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
                    # Stats where lower rank # = better but lower value is also better
                    _LOWER_VAL_BETTER = {104, 413, 142, 143, 299, 120, 2419, 2414}

                    # Build pivots
                    _rank_pivot = _fs4_latest.pivot(index="player_name", columns="stat_id", values="rank")
                    _rank_pivot.columns = [_stat_labels.get(int(c), str(c)) for c in _rank_pivot.columns]
                    _val_pivot = _fs4_latest.pivot(index="player_name", columns="stat_id", values="stat_value_numeric")
                    _val_pivot.columns = [_stat_labels.get(int(c), str(c)) for c in _val_pivot.columns]

                    # ── Controls row ─────────────────────────────────────────────
                    _ctrl1, _ctrl2, _ctrl3 = st.columns([2, 2, 3])
                    with _ctrl1:
                        _fs4_mode = st.radio("Display", ["Field Rank", "Stat Value"], horizontal=True, key="fs4_display_mode")
                    with _ctrl2:
                        _fs4_cat = st.radio(
                            "Category",
                            ["All"] + list(_stat_categories.keys()),
                            horizontal=False,
                            key="fs4_category",
                        )
                    with _ctrl3:
                        _fs4_search = st.text_input("Highlight player", placeholder="e.g. Scheffler", key="fs4_player_search").strip().lower()

                    _display_df = _rank_pivot.copy() if _fs4_mode == "Field Rank" else _val_pivot.copy()

                    # Filter columns to selected category
                    if _fs4_cat != "All":
                        _cat_ids = _stat_categories[_fs4_cat]
                        _cat_cols = [_stat_labels.get(sid) for sid in _cat_ids if _stat_labels.get(sid) in _display_df.columns]
                        _display_df = _display_df[[c for c in _cat_cols if c in _display_df.columns]]

                    # Reorder columns
                    _ordered_labels = [_stat_labels.get(sid, str(sid)) for sid in _ordered_stat_ids]
                    _final_cols = [c for c in _ordered_labels if c in _display_df.columns]
                    _extra_cols = [c for c in _display_df.columns if c not in _final_cols]
                    _display_df = _display_df[_final_cols + _extra_cols]

                    # ── Top 5 leaders for selected category ──────────────────────
                    if _fs4_cat != "All":
                        _lead_ids = _stat_categories[_fs4_cat]
                        _lead_rows = []
                        for _lid in _lead_ids:
                            _lname = _stat_labels.get(_lid)
                            if not _lname:
                                continue
                            _ldata = _fs4_latest[_fs4_latest["stat_id"] == _lid].sort_values("_tid_rank").groupby("player_name", as_index=False).first()
                            if _ldata.empty:
                                continue
                            _ldata = _ldata.sort_values("rank", ascending=True).head(5)
                            _lead_rows.append((_lname, _ldata))

                        if _lead_rows:
                            st.markdown(f"**Top 5 — {_fs4_cat}**")
                            _lcols = st.columns(min(len(_lead_rows), 3))
                            for _li, (_lname, _ldata) in enumerate(_lead_rows[:3]):
                                with _lcols[_li]:
                                    _leader_html = f'<div style="background:#0b1929;border:1px solid #1a3050;border-radius:8px;padding:10px 12px;margin-bottom:10px">'
                                    _leader_html += f'<div style="font-size:0.7em;font-weight:700;color:#4a6080;letter-spacing:.7px;text-transform:uppercase;margin-bottom:6px">{_lname}</div>'
                                    for _lrank, _lrow in enumerate(_ldata.itertuples(), 1):
                                        _lcolor = "#00c44f" if _lrank == 1 else ("#6ddb9a" if _lrank <= 3 else "#dde6f5")
                                        _lval = getattr(_lrow, "stat_value", None) or getattr(_lrow, "stat_value_numeric", "")
                                        _lval_str = f"{float(_lval):.1f}" if _lval and pd.notna(_lval) else ""
                                        _leader_html += (
                                            f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                            f'padding:3px 0;border-bottom:1px solid #0d1b2a">'
                                            f'<span style="font-size:0.8em;color:{_lcolor};font-weight:{"700" if _lrank==1 else "400"}">'
                                            f'#{_lrank} {_lrow.player_name}</span>'
                                            f'<span style="font-size:0.75em;color:#7a9bbf">{_lval_str}</span>'
                                            f'</div>'
                                        )
                                    _leader_html += "</div>"
                                    st.markdown(_leader_html, unsafe_allow_html=True)
                        st.markdown("---")

                    # ── Build display dataframe ───────────────────────────────────
                    _display_df.index.name = "Player"
                    _display_df = _display_df.reset_index()
                    _sort_col = _display_df.columns[1] if len(_display_df.columns) > 1 else "Player"
                    _asc = (_fs4_mode == "Field Rank")
                    _display_df = _display_df.sort_values(_sort_col, ascending=_asc, na_position="last").reset_index(drop=True)

                    # ── Highlight searched player ─────────────────────────────────
                    def _bg_rank_cell(val):
                        if pd.isna(val):
                            return "background-color: transparent; color: #3a4a5a"
                        v = float(val)
                        if v <= 10:   return "background-color: #0d2e18; color: #00c44f; font-weight:700"
                        elif v <= 30: return "background-color: #0d2218; color: #6ddb9a"
                        elif v <= 60: return "background-color: transparent; color: #dde6f5"
                        elif v <= 100: return "background-color: #2a1a0d; color: #ffa726"
                        else:         return "background-color: #2a0d0d; color: #e53935"

                    def _highlight_player_row(row):
                        if _fs4_search and _fs4_search in str(row["Player"]).lower():
                            return ["background-color: #0d1f35; outline: 1px solid #4cb8ff"] * len(row)
                        return [""] * len(row)

                    _stat_cols = [c for c in _display_df.columns if c != "Player"]
                    st.caption(
                        f"{len(_display_df)} players · {len(_stat_cols)} stats · "
                        f"Most recent: {_tid_order[0] if _tid_order else 'N/A'}"
                        + (f" · Highlighting: **{_fs4_search}**" if _fs4_search else "")
                    )

                    if _fs4_mode == "Field Rank":
                        _styled = (
                            _display_df.style
                            .apply(_highlight_player_row, axis=1)
                            .applymap(_bg_rank_cell, subset=_stat_cols)
                            .format({c: lambda x: f"{int(x)}" if pd.notna(x) else "—" for c in _stat_cols})
                        )
                    else:
                        _styled = (
                            _display_df.style
                            .apply(_highlight_player_row, axis=1)
                            .format({c: lambda x: f"{x:.2f}" if pd.notna(x) else "—" for c in _stat_cols})
                        )

                    st.dataframe(_styled, use_container_width=True, height=560, hide_index=True)

            with deep_tab5:
                _dc5 = load_dg_decompositions()
                if _dc5.empty:
                    st.info("No decompositions data available. The API may be between tournaments.")
                else:
                    try:
                        _dc5_event   = _dc5["event_name"].iloc[0]  if "event_name"   in _dc5.columns else ""
                        _dc5_course  = _dc5["course_name"].iloc[0] if "course_name"  in _dc5.columns else ""
                        _dc5_updated = str(_dc5["last_updated"].iloc[0]) if "last_updated" in _dc5.columns else ""

                        # Header
                        st.markdown(f"#### {_dc5_event}")
                        st.caption(f"{_dc5_course} · Last updated: {_dc5_updated} · {len(_dc5)} players · Data via DataGolf API")

                        # Field summary metrics
                        _m1, _m2, _m3, _m4 = st.columns(4)
                        for _mc, _lbl, _col, _fmt in [
                            (_m1, "Field Avg Pred",  "final_pred",    "+.3f"),
                            (_m2, "Avg Baseline",    "baseline_pred", "+.3f"),
                            (_m3, "Avg Timing",      "timing_adjustment", "+.3f"),
                            (_m4, "Avg Course Fit",  "total_fit_adjustment", "+.3f"),
                        ]:
                            _v = pd.to_numeric(_dc5[_col], errors="coerce").mean() if _col in _dc5.columns else None
                            _mc.metric(_lbl, f"{_v:{_fmt}}" if _v is not None and pd.notna(_v) else "—")

                        st.markdown("---")

                        # View selector
                        _dc5_view = st.radio(
                            "Show columns",
                            ["Summary", "Course", "Fit", "Form & Skill", "All"],
                            horizontal=True,
                            key="dc5_view",
                        )

                        # Normalise player names (Last, First → First Last)
                        def _dc5_fmt_name(n):
                            p = str(n).split(",", 1)
                            return f"{p[1].strip()} {p[0].strip()}" if len(p) == 2 else str(n).strip()

                        _dc5["Player"] = _dc5["player_name"].apply(_dc5_fmt_name)

                        # Column groups
                        _dc5_col_groups = {
                            "Summary": {
                                "DG Pred":    "final_pred",
                                "Baseline":   "baseline_pred",
                                "Fit Δ":      "course_fit_delta",
                                "Form":       "timing_adjustment",
                                "σ":          "std_deviation",
                            },
                            "Course": {
                                "DG Pred":       "final_pred",
                                "Course Hist":   "course_history_adjustment",
                                "Exp":           "course_experience_adjustment",
                                "Total Course":  "total_course_history_adjustment",
                            },
                            "Fit": {
                                "DG Pred":    "final_pred",
                                "Acc Fit":    "driving_accuracy_adjustment",
                                "Dist Fit":   "driving_distance_adjustment",
                                "Appr Fit":   "cf_approach_comp",
                                "Short Fit":  "cf_short_comp",
                                "Other Fit":  "other_fit_adjustment",
                                "Total Fit":  "total_fit_adjustment",
                            },
                            "Form & Skill": {
                                "DG Pred":    "final_pred",
                                "Baseline":   "baseline_pred",
                                "Form":       "timing_adjustment",
                                "SG Cat":     "strokes_gained_category_adjustment",
                                "True SG":    "true_sg_adjustments",
                                "Age":        "age_adjustment",
                                "Country":    "country_adjustment",
                            },
                            "All": {
                                "DG Pred":      "final_pred",
                                "Baseline":     "baseline_pred",
                                "Fit Δ":        "course_fit_delta",
                                "Total Course": "total_course_history_adjustment",
                                "Total Fit":    "total_fit_adjustment",
                                "Form":         "timing_adjustment",
                                "SG Cat":       "strokes_gained_category_adjustment",
                                "Age":          "age_adjustment",
                                "σ":            "std_deviation",
                            },
                        }

                        _sel_cols = _dc5_col_groups[_dc5_view]
                        _dc5_disp = pd.DataFrame()
                        _dc5_disp["#"]      = range(1, len(_dc5) + 1)
                        _dc5_disp["Player"] = _dc5["Player"].values
                        for _display_name, _src_col in _sel_cols.items():
                            if _src_col in _dc5.columns:
                                _dc5_disp[_display_name] = pd.to_numeric(_dc5[_src_col], errors="coerce").values

                        # Sort by DG Pred descending
                        if "DG Pred" in _dc5_disp.columns:
                            _dc5_disp = _dc5_disp.sort_values("DG Pred", ascending=False).reset_index(drop=True)
                            _dc5_disp["#"] = range(1, len(_dc5_disp) + 1)

                        # Styling
                        _sigma_col = "σ"
                        _sg_style_cols = [c for c in _dc5_disp.columns if c not in ("Player", "#", _sigma_col)]

                        def _dc5_sg_color(val):
                            if pd.isna(val): return "color:#3a4a5a"
                            v = float(val)
                            if   v >  0.15: return "color:#00c44f;font-weight:700"
                            elif v >  0.05: return "color:#6ddb9a"
                            elif v > -0.05: return "color:#dde6f5"
                            elif v > -0.15: return "color:#ffa726"
                            else:           return "color:#e53935"

                        def _dc5_unc_color(val):
                            if pd.isna(val): return "color:#3a4a5a"
                            v = float(val)
                            if v > 3.0:   return "color:#e53935"
                            elif v > 2.5: return "color:#ffa726"
                            else:         return "color:#6ddb9a"

                        _fmt_dict = {c: (lambda x: f"{float(x):+.3f}" if pd.notna(x) else "—") for c in _sg_style_cols}
                        if _sigma_col in _dc5_disp.columns:
                            _fmt_dict[_sigma_col] = lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
                        _fmt_dict["#"] = lambda x: str(int(x)) if pd.notna(x) else ""

                        _styled5 = _dc5_disp.style.applymap(_dc5_sg_color, subset=_sg_style_cols)
                        if _sigma_col in _dc5_disp.columns:
                            _styled5 = _styled5.applymap(_dc5_unc_color, subset=[_sigma_col])
                        _styled5 = _styled5.format(_fmt_dict)

                        _col_cfg = {
                            "#":      st.column_config.NumberColumn("#", width="small"),
                            "Player": st.column_config.TextColumn("Player", width="medium"),
                        }
                        for _c in _sg_style_cols:
                            _col_cfg[_c] = st.column_config.NumberColumn(_c, width="small")
                        if _sigma_col in _dc5_disp.columns:
                            _col_cfg[_sigma_col] = st.column_config.NumberColumn("σ (spread)", width="small",
                                help="Std deviation — higher means more boom-or-bust")

                        _legend = {
                            "Summary": "DG Pred = full prediction · Baseline = course-neutral skill · Fit Δ = how course style suits player · Form = recent form adjustment · σ = uncertainty",
                            "Course":  "Course Hist = historical results at this course · Exp = experience adjustment · Total Course = combined",
                            "Fit":     "Acc/Dist = driving fit · Appr/Short = SG category fit · Other = remaining fit · Total Fit = sum of all style fits",
                            "Form & Skill": "Form = recent form (timing) · SG Cat = SG category alignment with course · True SG = overall SG adjustment · Age/Country = minor adjustments",
                            "All":     "All key adjustments. Values are SG/round vs average field.",
                        }
                        st.caption(_legend[_dc5_view])
                        st.dataframe(_styled5, use_container_width=True, height=580, hide_index=True,
                                     column_config=_col_cfg)

                    except Exception as _dc5_e:
                        st.error(f"Error loading decompositions: {_dc5_e}")


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
                    _rows += _h2h_row("Consistency (σ)", _hg(_r1,"finish_consistency"), _hg(_r2,"finish_consistency"), higher_better=False, fmt=".1f")

                    _rows += _h2h_sec("Round Scoring (Recent)")
                    _rows += _h2h_row("R1 Avg", _hg(_r1,"recent_r1_avg"), _hg(_r2,"recent_r1_avg"), higher_better=False, fmt="+.2f")
                    _rows += _h2h_row("R2 Avg", _hg(_r1,"recent_r2_avg"), _hg(_r2,"recent_r2_avg"), higher_better=False, fmt="+.2f")
                    _rows += _h2h_row("R3 Avg", _hg(_r1,"recent_r3_avg"), _hg(_r2,"recent_r3_avg"), higher_better=False, fmt="+.2f")
                    _rows += _h2h_row("R4 Avg", _hg(_r1,"recent_r4_avg"), _hg(_r2,"recent_r4_avg"), higher_better=False, fmt="+.2f")
                    _rows += _h2h_row("Closing Ability", _hg(_r1,"closing_delta"), _hg(_r2,"closing_delta"), higher_better=False, fmt="+.2f")

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

                    _rows += _h2h_sec("Par Scoring (Field Rank, lower = better)")
                    _rows += _h2h_row("Par 3 Rank", _hg(_r1,"par3_scoring_field_rank"), _hg(_r2,"par3_scoring_field_rank"), higher_better=False, fmt=".0f")
                    _rows += _h2h_row("Par 4 Avg", _hg(_r1,"par4_scoring_val"), _hg(_r2,"par4_scoring_val"), higher_better=False, fmt=".2f")
                    _rows += _h2h_row("Par 4 Rank", _hg(_r1,"par4_scoring_field_rank"), _hg(_r2,"par4_scoring_field_rank"), higher_better=False, fmt=".0f")
                    _rows += _h2h_row("Par 5 Avg", _hg(_r1,"par5_scoring_val"), _hg(_r2,"par5_scoring_val"), higher_better=False, fmt=".2f")
                    _rows += _h2h_row("Par 5 Rank", _hg(_r1,"par5_scoring_field_rank"), _hg(_r2,"par5_scoring_field_rank"), higher_better=False, fmt=".0f")

                    # Load DG decompositions for H2H
                    _dc_h2h_r1 = _dc_h2h_r2 = None
                    try:
                        _dc_h2h = load_dg_decompositions()
                        if not _dc_h2h.empty:
                            def _dc_h2h_find(name):
                                _last = name.strip().split()[-1].lower()
                                _rows_f = _dc_h2h[_dc_h2h["player_name"].str.lower().str.contains(_last, na=False)]
                                if len(_rows_f) > 1:
                                    _exact = _rows_f[_rows_f["player_name"].apply(_name_key) == _name_key(name)]
                                    if not _exact.empty:
                                        return _exact.iloc[0]
                                return _rows_f.iloc[0] if not _rows_f.empty else None
                            _dc_h2h_r1 = _dc_h2h_find(h2h_player1)
                            _dc_h2h_r2 = _dc_h2h_find(h2h_player2)
                    except Exception:
                        pass

                    def _dch(r, k):
                        if r is None:
                            return None
                        try:
                            v = r.get(k) if hasattr(r, "get") else getattr(r, k, None)
                            return float(v) if v is not None and pd.notna(v) else None
                        except Exception:
                            return None

                    if _dc_h2h_r1 is not None or _dc_h2h_r2 is not None:
                        _rows += _h2h_sec("DG Prediction (this week)")
                        _rows += _h2h_row("DG Final Pred",    _dch(_dc_h2h_r1,"final_pred"),                          _dch(_dc_h2h_r2,"final_pred"),                          fmt="+.3f")
                        _rows += _h2h_row("DG Baseline",      _dch(_dc_h2h_r1,"baseline_pred"),                       _dch(_dc_h2h_r2,"baseline_pred"),                       fmt="+.3f")
                        _rows += _h2h_row("Course Fit Δ",     _dch(_dc_h2h_r1,"course_fit_delta"),                    _dch(_dc_h2h_r2,"course_fit_delta"),                    fmt="+.3f")
                        _rows += _h2h_row("Recent Form",      _dch(_dc_h2h_r1,"timing_adjustment"),                   _dch(_dc_h2h_r2,"timing_adjustment"),                   fmt="+.3f")
                        _rows += _h2h_row("SG Category",      _dch(_dc_h2h_r1,"strokes_gained_category_adjustment"),   _dch(_dc_h2h_r2,"strokes_gained_category_adjustment"),   fmt="+.3f")
                        _rows += _h2h_row("Course History",   _dch(_dc_h2h_r1,"total_course_history_adjustment"),      _dch(_dc_h2h_r2,"total_course_history_adjustment"),      fmt="+.3f")
                        _rows += _h2h_row("Total Style Fit",  _dch(_dc_h2h_r1,"total_fit_adjustment"),                _dch(_dc_h2h_r2,"total_fit_adjustment"),                fmt="+.3f")
                        _rows += _h2h_row("Acc Fit",          _dch(_dc_h2h_r1,"driving_accuracy_adjustment"),          _dch(_dc_h2h_r2,"driving_accuracy_adjustment"),          fmt="+.3f")
                        _rows += _h2h_row("Dist Fit",         _dch(_dc_h2h_r1,"driving_distance_adjustment"),          _dch(_dc_h2h_r2,"driving_distance_adjustment"),          fmt="+.3f")
                        _rows += _h2h_row("Approach Fit",     _dch(_dc_h2h_r1,"cf_approach_comp"),                    _dch(_dc_h2h_r2,"cf_approach_comp"),                    fmt="+.3f")
                        _rows += _h2h_row("Short Game Fit",   _dch(_dc_h2h_r1,"cf_short_comp"),                       _dch(_dc_h2h_r2,"cf_short_comp"),                       fmt="+.3f")
                        _rows += _h2h_row("Uncertainty (σ)",  _dch(_dc_h2h_r1,"std_deviation"),                       _dch(_dc_h2h_r2,"std_deviation"),                       higher_better=False, fmt=".2f")

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

                                

        elif h2h_player1 and h2h_player2 and h2h_player1 == h2h_player2:
            st.warning("Select two different players.")

    # Player Similarity — moved from its own tab into an expander inside Player Lookup
    # (accessible via the expander below after player selection, or always visible here)
    with player_tab1:
        st.markdown("---")



# ============================================================================
# PAGE: BETTING (consolidated from Props Lab + Odds & Experts)
# ============================================================================

elif page == "🎰 Betting":
    st.markdown("## 🎰 Betting")
    st.caption("Sportsbook-style props powered by model predictions")

    # ── Derive current tournament ID from schedule ────────────────────────────
    _bet_sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
    _rp_tid = ""
    if _bet_sched_path.exists():
        try:
            _bet_sched_df = pd.read_csv(_bet_sched_path, dtype=str)
            _bet_today = datetime.now().strftime("%Y-%m-%d")
            _bet_active = _bet_sched_df[
                (_bet_sched_df.get("start_date", pd.Series(dtype=str)) <= _bet_today) &
                (_bet_sched_df.get("end_date", pd.Series(dtype=str)) >= _bet_today)
            ]
            if not _bet_active.empty and "tournament_id" in _bet_active.columns:
                _rp_tid = str(_bet_active.iloc[0]["tournament_id"]).strip()
            if not _rp_tid:
                _bet_upcoming = _bet_sched_df[
                    _bet_sched_df.get("start_date", pd.Series(dtype=str)) > _bet_today
                ].sort_values("start_date")
                if not _bet_upcoming.empty and "tournament_id" in _bet_upcoming.columns:
                    _rp_tid = str(_bet_upcoming.iloc[0]["tournament_id"]).strip()
        except Exception:
            pass

    # ── Quick edge summary — full detail in Value Bets tab ───────────────────
    _vb_path = OUTPUTS_DIR / "latest_predictions.csv"
    if _vb_path.exists():
        try:
            _vb_raw = pd.read_csv(_vb_path)
            if "model_vs_vegas_edge" in _vb_raw.columns:
                _vb_raw["model_vs_vegas_edge"] = pd.to_numeric(_vb_raw["model_vs_vegas_edge"], errors="coerce")
                
                st.caption("Full bet cards, Kelly sizing, and filters are in the **Value Bets** tab below.")
        except Exception:
            pass

    # ── Daily Bet Recommendation ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Today's Best Bet")

    _today_tid = _rp_tid or ""
    _daily_rec_df, _ = load_recommended_bets_df(_today_tid) if _today_tid else load_recommended_bets_df("")
    _daily_preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    _daily_preds = pd.read_csv(_daily_preds_path) if _daily_preds_path.exists() else pd.DataFrame()

    def _build_bet_reasoning(pr: pd.Series, market: str, model_prob: float, book_prob: float, field_size: int = 135) -> list[str]:
        """Generate 3-4 plain-English reasoning bullets for a recommended bet."""
        reasons = []

        # 1. Model rank + probability edge
        win_prob = float(pr.get("win_prob", 0) or 0)
        top10_prob = float(pr.get("top10_prob", 0) or 0)
        top20_prob = float(pr.get("top20_prob", 0) or 0)
        # Rank by win_prob not available here directly, use world_rank as proxy
        mkt_lower = market.lower().replace(" ", "").replace("_", "")
        if "top10" in mkt_lower:
            relevant_prob = top10_prob
            mkt_label = "top-10"
        elif "top20" in mkt_lower:
            relevant_prob = top20_prob
            mkt_label = "top-20"
        elif "top5" in mkt_lower:
            relevant_prob = float(pr.get("top5_prob", 0) or 0)
            mkt_label = "top-5"
        elif "makecut" in mkt_lower or "make_cut" in mkt_lower or "makethecut" in mkt_lower:
            relevant_prob = float(pr.get("cut_prob", 0) or 0)
            mkt_label = "make cut"
        elif "h2h" in mkt_lower or "matchup" in mkt_lower:
            relevant_prob = model_prob
            mkt_label = "matchup"
        elif "group" in mkt_lower:
            relevant_prob = model_prob
            mkt_label = "group win"
        else:
            relevant_prob = win_prob
            mkt_label = "win"
        if model_prob > 0 and book_prob > 0:
            reasons.append(f"Model gives {model_prob*100:.1f}% {mkt_label} chance vs book's {book_prob*100:.1f}% — {(model_prob-book_prob)*100:.1f}pp edge")

        # 2. Strongest SG category
        sg_map = {
            "season_sg_app": ("approach play", "season_sg_app_field_rank"),
            "season_sg_putt": ("putting", "season_sg_putt_field_rank"),
            "season_sg_ott": ("off-the-tee", "season_sg_ott_field_rank"),
            "season_sg_arg": ("short game", "season_sg_arg_field_rank"),
        }
        best_sg_label, best_sg_val, best_sg_rank = None, 0.0, None
        for col, (label, rank_col) in sg_map.items():
            v = float(pr.get(col, 0) or 0)
            r = pr.get(rank_col)
            if v > best_sg_val:
                best_sg_val, best_sg_label = v, label
                best_sg_rank = int(r) if pd.notna(r) else None
        if best_sg_label and best_sg_val > 0.2:
            rank_str = f" (#{best_sg_rank}/{field_size} in field)" if best_sg_rank else ""
            reasons.append(f"Elite {best_sg_label}: +{best_sg_val:.2f} SG/round{rank_str}")

        # 3. Form
        consec = int(pr.get("consecutive_cuts", 0) or 0)
        ft = float(pr.get("form_trend", 0) or 0)
        hot = float(pr.get("hot_hand_score", 0) or 0)
        if consec >= 5:
            reasons.append(f"Consistent: {consec} consecutive cuts made, form trending {'up' if ft > 0.1 else 'steady'}")
        elif ft > 0.3:
            reasons.append(f"Form trending up sharply (+{ft:.2f} trend), hot-hand score {hot:.0f}/10")
        elif hot >= 7:
            reasons.append(f"Hot form — hot-hand score {hot:.0f}/10")

        # 4. Course history
        hist_starts = int(pr.get("hist_times_played", 0) or 0)
        hist_wins = int(pr.get("hist_wins", 0) or 0)
        hist_t10 = int(pr.get("hist_top10s", 0) or 0)
        avg_to_par = pr.get("course_avg_to_par")
        if hist_wins > 0:
            reasons.append(f"Won here before ({hist_wins}x in {hist_starts} starts)")
        elif hist_t10 > 0 and hist_starts >= 2:
            reasons.append(f"{hist_t10} top-10{'s' if hist_t10 > 1 else ''} in {hist_starts} starts at this course")
        elif hist_starts == 0:
            reasons.append("First start at this venue — no course history drag")

        # 5. Odds direction
        _dir = str(pr.get("dk_odds_direction", "")).upper()
        if _dir == "UP":
            reasons.append("Odds shortening — market moving our way")
        elif _dir == "DOWN":
            reasons.append("Odds drifting — value improving, get on now")

        return reasons[:4]

    def _daily_bet_card(rec_df: pd.DataFrame, preds: pd.DataFrame):
        if rec_df.empty:
            st.caption("No recommended bets yet — fetch odds and score bets first.")
            return

        rec_df = rec_df.copy()
        # Exclude parlays — they need their own section, not the top-line headline
        rec_df = rec_df[rec_df.get("bet_type", pd.Series(["single"]*len(rec_df))).astype(str) != "content_card"]
        if rec_df.empty:
            st.caption("No single bets scored yet — fetch odds and score bets first.")
            return
        rec_df["edge_pts"] = pd.to_numeric(rec_df.get("edge_pts", rec_df.get("model_vs_vegas_edge", 0)), errors="coerce").fillna(0)
        if rec_df["edge_pts"].max() <= 1:
            rec_df["edge_pts"] = rec_df["edge_pts"] * 100
        # Composite headline score: confidence × edge × market prestige
        # Prestige weights: outright/top5/top10 are headline bets; make_cut is a value/supporting bet
        _prestige = {
            "outright": 1.5, "top5": 1.4, "top10": 1.3, "top20": 1.1,
            "h2h": 1.2, "h2h_r1": 1.2, "h2h_r2": 1.1,
            "group_winner": 1.05, "wire_to_wire": 1.1,
            "make_cut": 0.85, "miss_cut": 0.80,
            "nationality_group": 0.90,
        }
        _conf = pd.to_numeric(rec_df.get("confidence", 0.60), errors="coerce").fillna(0.60)
        _pres = rec_df.get("market", pd.Series([""] * len(rec_df))).apply(
            lambda m: _prestige.get(str(m).lower().replace(" ", "").replace("-", ""), 1.0)
        )
        rec_df["_headline_score"] = _conf * rec_df["edge_pts"] * _pres
        rec_df = rec_df.sort_values("_headline_score", ascending=False)

        _field_size = len(preds) if not preds.empty else 135
        _bet_labels = ["BET OF THE DAY", "SUPPORTING PLAY", "THIRD LOOK"]
        _bet_colors = ["#00c44f", "#4cb8ff", "#f59e0b"]
        top = rec_df.head(3)

        for _i, (_, _br) in enumerate(top.iterrows()):
            _raw_bname = str(_br.get("player_name", "") or "")
            # "nan" guard — fall back to selection_label for unnamed rows
            if not _raw_bname or _raw_bname.lower() in ("nan", "none", ""):
                _raw_bname = str(_br.get("selection_label", "") or "—")
            _bname = " ".join(reversed(_raw_bname.split(", "))) if ", " in _raw_bname else _raw_bname
            _mkt = str(_br.get("market", "outright")).replace("_", " ").title()
            _odds = _br.get("odds_american", None)
            _edge = float(_br.get("edge_pts", 0))
            _model_prob = float(pd.to_numeric(_br.get("model_prob", 0), errors="coerce") or 0)
            _book_prob = float(pd.to_numeric(_br.get("book_prob", 0), errors="coerce") or 0)
            _conf = float(pd.to_numeric(_br.get("confidence", 0), errors="coerce") or 0)
            _corr = int(pd.to_numeric(_br.get("corroboration_score", 0), errors="coerce") or 0)
            _color = _bet_colors[_i] if _i < len(_bet_colors) else "#7a9bbf"
            _label = _bet_labels[_i] if _i < len(_bet_labels) else f"BET #{_i+1}"

            # Format odds
            _odds_str = "—"
            if _odds is not None and pd.notna(_odds):
                try:
                    _oi = int(float(_odds))
                    _odds_str = f"+{_oi}" if _oi > 0 else str(_oi)
                except (ValueError, TypeError):
                    _odds_str = str(_odds)

            # Reasoning: use stored column first, dynamic build as fallback
            _stored_reasoning = str(_br.get("reasoning", "") or "")
            _reasons = []
            _dir_html = ""
            if _stored_reasoning:
                # Split pipe-separated stored reasoning into list
                _reasons = [p.strip() for p in _stored_reasoning.split("|") if p.strip()]
            if not preds.empty:
                _pm = preds[preds["player_name"].apply(_name_key) == _name_key(_bname)]
                if not _pm.empty:
                    _dir = str(_pm.iloc[0].get("dk_odds_direction", "")).upper()
                    _dir_html = {"UP": '<span style="color:#00c44f">▲</span>', "DOWN": '<span style="color:#e74c3c">▼</span>', "CONSTANT": '<span style="color:#7a9bbf">→</span>'}.get(_dir, "")
                    # Only build dynamically if nothing was stored
                    if not _reasons:
                        _reasons = _build_bet_reasoning(_pm.iloc[0], _mkt, _model_prob, _book_prob, _field_size)

            # Probability bar widths
            _model_w = min(int(_model_prob * 100 * 4), 100)
            _book_w = min(int(_book_prob * 100 * 4), 100)

            st.markdown(
                f"""<div style="border:1px solid {_color}44;border-radius:12px;padding:18px 18px 14px;background:linear-gradient(150deg,{_color}0d 0%,#0a1520 100%);margin-bottom:12px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
    <div>
      <div style="font-size:0.65em;font-weight:700;color:{_color};letter-spacing:0.14em;margin-bottom:4px">{_label}</div>
      <div style="font-size:1.3em;font-weight:700;color:#e8f0f8">{_bname} {_dir_html}</div>
      <div style="font-size:0.78em;color:#7a9bbf;margin-top:2px">{_mkt}{f" · {_conf:.0%} confidence" if _conf else ""}{f" · {_corr} signals" if _corr >= 2 else ""}</div>
    </div>
    <div style="text-align:right;min-width:80px">
      <div style="font-size:1.8em;font-weight:800;color:{_color};line-height:1">{_odds_str}</div>
      <div style="font-size:0.72em;color:#00c44f;font-weight:600">+{_edge:.1f}pp edge</div>
    </div>
  </div>
  <div style="margin-bottom:12px">
    <div style="display:flex;justify-content:space-between;font-size:0.68em;color:#7a9bbf;margin-bottom:3px"><span>Model {_model_prob*100:.1f}%</span><span>Book {_book_prob*100:.1f}%</span></div>
    <div style="background:#0d1b2a;border-radius:3px;height:6px;margin-bottom:3px;overflow:hidden"><div style="background:{_color};height:100%;width:{_model_w}%;border-radius:3px"></div></div>
    <div style="background:#0d1b2a;border-radius:3px;height:6px;overflow:hidden"><div style="background:#4a6080;height:100%;width:{_book_w}%;border-radius:3px"></div></div>
  </div>
  {"".join(f'<div style="font-size:0.75em;color:#b0c8e8;padding:3px 0;border-top:1px solid #1c2f4a;word-break:break-word;overflow-wrap:anywhere;">• {r}</div>' for r in _reasons[:4])}
</div>""",
                unsafe_allow_html=True,
            )

            # Group members expander (native Streamlit, can't go inside HTML)
            _grp = str(_br.get("group_members", "") or "")
            if _grp and _grp != "nan" and "|" in _grp:
                with st.expander("Group members", expanded=False):
                    for _gm in _grp.split("|"):
                        st.caption(_gm.strip())

    _daily_bet_card(_daily_rec_df, _daily_preds)
    st.caption("Updates automatically when odds are refreshed. Full breakdown in Value Bets tab.")
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


            # Load draw advantage for betting page
            _da_bet_df = pd.DataFrame()
            for _r in [1, 2, 3, 4]:
                _da_p = DATA_DIR / "live" / f"draw_advantage_{prop_tournament_id}_r{_r}.csv"
                if _da_p.exists():
                    _da_bet_df = pd.read_csv(_da_p)[["player_name", "tee_time_str", "window_avg_wind", "draw_advantage",
            "draw_tier"]]
                    break
            if not _da_bet_df.empty and not preds_df.empty:
                preds_df = preds_df.merge(_da_bet_df, on="player_name", how="left")
                        
                        
                        
            
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
            props_tab1, props_tab2, props_tab3 = st.tabs([
                "⚡ Value Bets",
                "⚔️ Matchups",
                "📋 Odds Explorer"
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
                        _fd_mkt_check = DATA_DIR / "odds" / f"pga_market_odds_{prop_tournament_id}.csv"
                        if not _fd_mkt_check.exists():
                            st.info(
                                f"No FanDuel odds fetched yet for {prop_tournament_id}. "
                                "Run **Fetch Odds** in the Data Management panel above."
                            )
                        else:
                            st.info(
                                "No value bets meet the current edge threshold. "
                                "Make cut and round matchup markets open Wednesday when pairings drop — "
                                "re-run **Score Bets** then for full recommendations."
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
                            _vb_rec_df["_pname_norm"] = _vb_rec_df["player_name"].astype(str).str.strip().str.lower()
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
                            "outright":          "Win",
                            "top5":              "Top 5",
                            "top10":             "Top 10",
                            "top20":             "Top 20",
                            "make_cut":          "Make Cut",
                            "h2h":               "Matchup",
                            "h2h_r1":            "Matchup R1",
                            "h2h_r2":            "Matchup R2",
                            "h2h_r3":            "Matchup R3",
                            "h2h_r4":            "Matchup R4",
                            "group_winner":      "Group Winner",
                            "r2_leader":         "Lead After R2",
                            "nationality_group": "Nationality",
                            "wire_to_wire":      "Wire-to-Wire",
                            "content_card":      "Parlay Card",
                        }
                        _mkt_opts = ["All"] + [_mkt_labels.get(m, m.title()) for m in _mkts_avail]
                        _mkt_raw   = ["All"] + list(_mkts_avail)

                        _vb_filter_col, _vb_book_col, _vb_thresh_col, _vb_bankroll_col = st.columns([2, 1.5, 2, 2])
                        with _vb_filter_col:
                            _sel_mkt_label = st.selectbox(
                                "Market", _mkt_opts, key="vb_market_filter"
                            )
                        with _vb_book_col:
                            _books_avail = sorted(_vb_rec_df["book"].dropna().str.upper().unique()) \
                                if "book" in _vb_rec_df.columns else []
                            _book_opts = ["All"] + _books_avail
                            _sel_book = st.selectbox(
                                "Book", _book_opts, key="vb_book_filter"
                            )
                        with _vb_thresh_col:
                            _vb_min_edge = st.slider(
                                "Min Edge (%)", 0.0, 8.0, 1.5, 0.5, key="vb_edge_thresh"
                            )
                        with _vb_bankroll_col:
                            _vb_bankroll = st.number_input(
                                "Bankroll ($)", min_value=100, max_value=100000,
                                value=1000, step=100, key="vb_bankroll",
                                help="Used to compute Kelly dollar amounts on each bet card"
                            )

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
                        if _sel_book != "All" and "book" in _filtered.columns:
                            _filtered = _filtered[
                                _filtered["book"].fillna("").str.upper() == _sel_book
                            ]
                        _filtered = _filtered[
                            _filtered["edge_pts"].fillna(0) >= _vb_min_edge
                        ].sort_values("edge_pts", ascending=False)

                        


                        # Shared helper — safe string conversion (NaN → default)
                        def _safe_str(v, default="—"):
                            if v is None: return default
                            s = str(v).strip()
                            return default if s.lower() in ("nan", "none", "") else s

                        # ── Best Plays banner (top 2-3 high-conviction singles) ──
                        _best_plays = _filtered[
                            (_filtered["bet_type"].astype(str) == "single") &
                            (_filtered["confidence"].fillna(0) >= 0.80) &
                            (_filtered["edge_pts"].fillna(0) >= 4.0)
                        ].sort_values("edge_pts", ascending=False).head(3)

                        if not _best_plays.empty:
                            st.markdown(
                                '<div style="font-size:0.72em;font-weight:700;color:#f39c12;'
                                'text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;">'
                                '★ Best Plays</div>',
                                unsafe_allow_html=True,
                            )
                            _bp_cols = st.columns(len(_best_plays))
                            for _bpi, (_, _bp) in enumerate(_best_plays.iterrows()):
                                with _bp_cols[_bpi]:
                                    _bp_mkt = str(_bp.get("market","")).lower()
                                    _bp_color = _CARD_MKT_COLOR.get(_bp_mkt, "#444") if False else {
                                        "outright":"#f1c40f","top5":"#3498db","top10":"#00c44f",
                                        "top20":"#9b59b6","make_cut":"#1abc9c","h2h":"#e67e22",
                                        "h2h_r1":"#e67e22","group_winner":"#e74c3c",
                                        "wire_to_wire":"#d35400",
                                    }.get(_bp_mkt, "#4a90d9")
                                    _bp_player = _safe_str(_bp.get("player_name"), "—")
                                    _bp_mkt_lbl = {
                                        "outright":"Win","top5":"Top 5","top10":"Top 10",
                                        "top20":"Top 20","make_cut":"Make Cut","h2h":"Matchup",
                                        "h2h_r1":"Matchup R1","group_winner":"Group Winner",
                                        "wire_to_wire":"Wire-to-Wire",
                                    }.get(_bp_mkt, _bp_mkt.title())
                                    _bp_book = _safe_str(_bp.get("book"),"").upper()
                                    _bp_book_s = "DK" if "DRAFT" in _bp_book else ("FD" if "FANDUEL" in _bp_book else _bp_book[:2])
                                    _bp_odds = int(float(_bp.get("odds_american",0) or 0))
                                    _bp_odds_s = f"+{_bp_odds}" if _bp_odds >= 0 else str(_bp_odds)
                                    _bp_edge = float(_bp.get("edge_pts",0) or 0)
                                    _bp_model = float(_bp.get("model_prob",0) or 0) * 100
                                    st.markdown(f"""
<div style="background:linear-gradient(135deg,#0d1a30,#0a1520);
            border:1px solid {_bp_color};border-radius:8px;padding:12px 14px;
            border-top:3px solid {_bp_color};">
  <div style="font-size:0.62em;color:{_bp_color};font-weight:700;
              text-transform:uppercase;letter-spacing:.06em;">{_bp_book_s} · {_bp_mkt_lbl}</div>
  <div style="font-size:1.05em;font-weight:700;color:#dde6f5;
              margin:4px 0 2px;white-space:nowrap;overflow:hidden;
              text-overflow:ellipsis;">{_bp_player}</div>
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:6px;">
    <span style="font-size:1.4em;font-weight:800;color:{_bp_color};">{_bp_odds_s}</span>
    <span style="font-size:0.82em;font-weight:700;color:#00c44f;">+{_bp_edge:.1f}pp edge</span>
  </div>
  <div style="font-size:0.68em;color:#7f8c8d;margin-top:3px;">Model {_bp_model:.1f}%</div>
</div>""", unsafe_allow_html=True)
                            st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

                        # ── Bet cards ───────────────────────────────────────
                        _CARD_MKT_COLOR = {
                            "outright":          "#f1c40f",
                            "top5":              "#3498db",
                            "top10":             "#00c44f",
                            "top20":             "#9b59b6",
                            "make_cut":          "#1abc9c",
                            "h2h":               "#e67e22",
                            "h2h_r1":            "#e67e22",
                            "h2h_r2":            "#e67e22",
                            "h2h_r3":            "#e67e22",
                            "h2h_r4":            "#e67e22",
                            "group_winner":      "#e74c3c",
                            "r2_leader":         "#16a085",
                            "nationality_group": "#8e44ad",
                            "wire_to_wire":      "#d35400",
                            "content_card":      "#2c3e50",
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

                        _singles_filtered   = _filtered[_filtered["bet_type"].astype(str) == "single"].head(12)
                        _parlays_filtered   = _filtered[_filtered["bet_type"].astype(str) == "content_card"].head(6)
                        _all_empty = _singles_filtered.empty and _parlays_filtered.empty

                        if _all_empty:
                            st.info("No bets meet the current filters. Try lowering the edge threshold.")

                        def _render_card_grid(card_df):
                            _n_cols = 2
                            for _ci in range(0, len(card_df), _n_cols):
                                _card_cols = st.columns(_n_cols)
                                for _cj, (_, _row) in enumerate(
                                    card_df.iloc[_ci:_ci + _n_cols].iterrows()
                                ):
                                    with _card_cols[_cj]:
                                        _mkt      = _safe_str(_row.get("market"), "").lower()
                                        _border   = _CARD_MKT_COLOR.get(_mkt, "#444")
                                        _mkt_lbl  = _mkt_labels.get(_mkt, _mkt.title())
                                        _player   = _safe_str(_row.get("player_name")) \
                                            if _safe_str(_row.get("player_name"), "") else \
                                            _safe_str(_row.get("title"), _safe_str(_row.get("selection_label")))
                                        _subtitle = _safe_str(_row.get("subtitle"), "") if _mkt == "content_card" else ""
                                        _odds_str = _fmt_odds(_row.get("odds_american", ""))
                                        _edge     = float(_row.get("edge_pts", 0) or 0)
                                        _model_p  = float(_row.get("model_prob") or 0) * 100
                                        _book_p   = float(_row.get("book_prob") or 0) * 100
                                        _ev       = float(_row.get("ev_per_1") or 0)
                                        _conf_lbl, _conf_color = _conf_badge(_row.get("confidence"))
                                        _rank     = pd.to_numeric(_row.get("world_rank"), errors="coerce")
                                        _rank_str = f"Rank #{int(_rank)}" if pd.notna(_rank) else ""
                                        _form     = pd.to_numeric(_row.get("form_trend"), errors="coerce")
                                        _form_str = ""
                                        if pd.notna(_form):
                                            _fv = float(_form)
                                            _form_str = f"Form {_fv:+.2f}"

                                        # Cut probability indicator
                                        _cut_p = _row.get("cut_prob")
                                        _cut_warn = ""
                                        if _mkt == "make_cut" and pd.notna(_cut_p):
                                            # For make_cut bets: show model's cut probability as confirmation
                                            _cp = float(_cut_p)
                                            _cp_color = "#00c44f" if _cp >= 0.75 else "#f39c12" if _cp >= 0.60 else "#e74c3c"
                                            _cut_warn = (
                                                f'<div style="margin-top:7px;padding:4px 8px;'
                                                f'background:rgba(26,188,156,0.08);border:1px solid rgba(26,188,156,0.25);'
                                                f'border-radius:5px;font-size:0.70em;color:{_cp_color};">'
                                                f'Model cut prob: {_cp*100:.0f}% · market-blended</div>'
                                            )
                                        elif _mkt in ("top5", "top10") and pd.notna(_cut_p):
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
                                        _dfs_own = pd.to_numeric(_row.get("dfs_ownership_proj"), errors="coerce")
                                        _dfs_str = f"{float(_dfs_own):.1f}%" if pd.notna(_dfs_own) else "—"

                                        # DK movement direction arrow
                                        _dk_dir = _safe_str(_row.get("dk_odds_direction"), "")
                                        if _dk_dir.upper() == "UP":
                                            _dir_arrow = "▲"; _dir_color = "#00c44f"
                                        elif _dk_dir.upper() == "DOWN":
                                            _dir_arrow = "▼"; _dir_color = "#e74c3c"
                                        else:
                                            _dir_arrow = "→"; _dir_color = "#7f8c8d"

                                        # Book badge
                                        _book_str = _safe_str(_row.get("book"), "").upper()
                                        _BOOK_BADGE = {
                                            "DRAFTKINGS": ("#00c44f", "#0d2e18", "DK"),
                                            "FANDUEL":    ("#1a78d4", "#0a1f3a", "FD"),
                                        }
                                        _bb_color, _bb_bg, _bb_label = _BOOK_BADGE.get(
                                            _book_str, ("#7f8c8d", "#1c2333", _book_str[:3] or "?")
                                        )
                                        _book_badge_html = (
                                            f'<span style="font-size:0.62em;font-weight:700;color:{_bb_color};'
                                            f'background:{_bb_bg};padding:2px 6px;border-radius:3px;'
                                            f'margin-right:5px;border:1px solid {_bb_color}33;">{_bb_label}</span>'
                                        )

                                        # Mkt type label badge
                                        _mkt_badge_html = (
                                            f'<span style="font-size:0.62em;font-weight:600;color:{_border};'
                                            f'text-transform:uppercase;letter-spacing:.05em;">{_mkt_lbl}</span>'
                                        )

                                        # Content card: parse legs + per-leg probs
                                        _legs_html = ""
                                        if _mkt == "content_card":
                                            import json as _json
                                            _leg_labels = []
                                            try:
                                                _slj = _row.get("selection_labels_json", "") or ""
                                                if _slj and _safe_str(_slj, "") not in ("", "nan"):
                                                    _leg_labels = _json.loads(_slj)
                                            except Exception:
                                                _sl = _safe_str(_row.get("selection_labels"), "")
                                                if _sl:
                                                    _leg_labels = [l.strip() for l in _sl.split("|") if l.strip()]

                                            # Per-leg probs from leg_prob_summary "Leg:XX% | Leg:XX%"
                                            _leg_prob_map: dict = {}
                                            _lps = _safe_str(_row.get("leg_prob_summary"), "")
                                            if _lps:
                                                for _part in _lps.split(" | "):
                                                    if ":" in _part:
                                                        _lname, _lp = _part.rsplit(":", 1)
                                                        try:
                                                            _leg_prob_map[_lname.strip()] = float(_lp.replace("%",""))
                                                        except Exception:
                                                            pass

                                            _weakest = _safe_str(_row.get("weakest_leg"), "")
                                            if _leg_labels:
                                                _leg_rows_html = []
                                                for _ll in _leg_labels:
                                                    _ll_stripped = _ll.strip()
                                                    # Match leg label to prob map (label may include market suffix)
                                                    _lp_val = _leg_prob_map.get(_ll_stripped)
                                                    if _lp_val is None:
                                                        # Try partial match
                                                        for k, v in _leg_prob_map.items():
                                                            if k in _ll_stripped or _ll_stripped in k:
                                                                _lp_val = v
                                                                break
                                                    _is_weakest = _weakest and _weakest in _ll_stripped
                                                    _lp_color = "#e74c3c" if _is_weakest else ("#f39c12" if (_lp_val or 100) < 35 else "#b0c4de")
                                                    _lp_str = f"{_lp_val:.0f}%" if _lp_val is not None else "—"
                                                    _weak_tag = " ⚠" if _is_weakest else ""
                                                    _leg_rows_html.append(
                                                        f'<div style="display:flex;justify-content:space-between;'
                                                        f'padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                                                        f'<span style="color:{_lp_color};font-size:0.72em;">{_ll_stripped}{_weak_tag}</span>'
                                                        f'<span style="color:{_lp_color};font-size:0.72em;font-weight:600;">{_lp_str}</span>'
                                                        f'</div>'
                                                    )
                                                _legs_html = (
                                                    f'<div style="margin-top:8px;padding:6px 8px;'
                                                    f'background:rgba(255,255,255,0.03);border-radius:4px;'
                                                    f'border:1px solid rgba(255,255,255,0.07);">'
                                                    f'<div style="font-size:0.65em;color:#7f8c8d;margin-bottom:4px;'
                                                    f'text-transform:uppercase;letter-spacing:.05em;">Parlay Legs (model prob)</div>'
                                                    + "".join(_leg_rows_html) +
                                                    f'</div>'
                                                )

                                        # Raw model prob (pre-blend) if different
                                        _raw_mp = pd.to_numeric(_row.get("raw_model_prob"), errors="coerce")
                                        _raw_mp_html = ""
                                        if pd.notna(_raw_mp) and abs(float(_raw_mp) - _model_p/100) > 0.005:
                                            _raw_pct = float(_raw_mp) * 100
                                            _raw_mp_html = (
                                                f'<span style="font-size:0.68em;color:#7f8c8d;margin-left:4px;">'
                                                f'(raw {_raw_pct:.1f}%)</span>'
                                            )

                                        # Group members (H2H / 3-ball / group bets)
                                        _group_members = _safe_str(_row.get("group_members"), "")
                                        _group_members_html = ""
                                        if _group_members and _mkt in ("h2h","h2h_r1","h2h_r2","h2h_r3","h2h_r4","group_winner","nationality_group","wire_to_wire"):
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
                                        # Draw advantage badge
                                        _draw_tier = str(_row.get("draw_tier", "") or "")
                                        _draw_wind = pd.to_numeric(_row.get("window_avg_wind"), errors="coerce")
                                        _draw_badge = ""
                                        if _draw_tier and _draw_tier not in ("nan", ""):
                                            _dt_cfg = {
                                                "Strong Adv": ("++ Calm", "#00c44f"),
                                                "Adv":        ("+ Calm",  "#4caf72"),
                                                "Neutral":    ("~",       "#7f8c8d"),
                                                "Disadv":     ("- Wind",  "#e67e22"),
                                                "Strong Disadv": ("-- Wind", "#e74c3c"),
                                            }.get(_draw_tier, ("", "#7f8c8d"))
                                            _dt_label, _dt_color = _dt_cfg
                                            _wind_detail = f" {_draw_wind:.0f}mph" if pd.notna(_draw_wind) else ""
                                            _draw_badge = (
                                                f'<span style="font-size:0.65em;font-weight:700;color:{_dt_color};'
                                                f'background:rgba(255,255,255,0.07);padding:2px 6px;border-radius:4px;'
                                                f'margin-left:6px;">Draw {_dt_label}{_wind_detail}</span>'
                                            )

                                        _card_html = re.sub(r'\n[ \t]*\n', '\n', f"""
<div style="background:#0d1a30;border-left:4px solid {_border};border-radius:8px;
            padding:14px 16px;margin-bottom:4px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="margin-bottom:3px;">{_book_badge_html}{_mkt_badge_html}{_corr_badge}{_draw_badge}</div>
      <div style="font-size:1.1em;font-weight:700;color:#dde6f5;margin-top:2px;">{_player}</div>
      <div style="font-size:0.75em;color:#7f8c8d;margin-top:1px;">{_subtitle if _subtitle else (_rank_str + ("  ·  " if _rank_str and _form_str else "") + _form_str)}</div>
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
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_model_p:.1f}%{_raw_mp_html}</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">MARKET (no-vig)</div>
      <div style="font-size:0.92em;font-weight:600;color:#dde6f5;">{_book_p:.1f}%</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">EDGE</div>
      <div style="font-size:1.1em;font-weight:800;color:{_border};">+{_edge:.1f}pp</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">EV / $1</div>
      <div style="font-size:0.92em;font-weight:700;color:#00c44f;">${_ev:.2f}</div>
    </div>
    <div>
      <div style="font-size:0.68em;color:#7f8c8d;">KELLY (½K)</div>
      <div style="font-size:0.92em;font-weight:600;color:#f39c12;">{_kelly_str}</div>
    </div>
  </div>
  {_legs_html}
  <div style="margin-top:8px;background:#1a2a40;border-radius:4px;height:4px;">
    <div style="width:{_bar_pct}%;height:4px;background:{_border};border-radius:4px;"></div>
  </div>
  {_cut_warn}
</div>
""")
                                        st.markdown(_card_html, unsafe_allow_html=True)

                                        # ── Mark as Placed ──────────────────
                                        # Load placed bets once per card render.
                                        # session_state caches the set of placed IDs
                                        # so we don't hit the CSV on every rerun.
                                        if "placed_bet_ids" not in st.session_state:
                                            _pb = load_placed_bets()
                                            st.session_state["placed_bet_ids"] = set(
                                                _pb["recommendation_id"].astype(str).tolist()
                                            )
                                        _rec_id = str(_row.get("recommendation_id", ""))
                                        _already_placed = _rec_id in st.session_state["placed_bet_ids"]

                                        if _already_placed:
                                            st.markdown(
                                                "<div style='font-size:0.78em;color:#00c44f;"
                                                "padding:2px 0 6px;'>✓ Placed</div>",
                                                unsafe_allow_html=True,
                                            )
                                        else:
                                            _stake_key  = f"stake_{_rec_id}"
                                            _button_key = f"place_{_rec_id}"
                                            # Default stake = half-Kelly dollar amount
                                            _default_stake = round(float(_kelly_f * _vb_bankroll), 0) if pd.notna(_kelly_f) and float(_kelly_f) > 0 else 10.0
                                            _pc1, _pc2 = st.columns([2, 3])
                                            with _pc1:
                                                _stake_input = st.number_input(
                                                    "Stake ($)", min_value=1.0,
                                                    value=max(_default_stake, 1.0),
                                                    step=5.0, key=_stake_key,
                                                    label_visibility="collapsed",
                                                )
                                            with _pc2:
                                                if st.button(
                                                    "Mark as Placed",
                                                    key=_button_key,
                                                    use_container_width=True,
                                                ):
                                                    save_placed_bet(
                                                        recommendation_id=_rec_id,
                                                        tournament_id=str(prop_tournament_id or ""),
                                                        player_name=_player,
                                                        market=_mkt,
                                                        odds_american=_row.get("odds_american"),
                                                        stake_usd=_stake_input,
                                                    )
                                                    st.session_state["placed_bet_ids"].add(_rec_id)
                                                    st.rerun()

                        if not _all_empty:
                            if not _singles_filtered.empty:
                                st.markdown(
                                    '<div style="font-size:0.70em;font-weight:700;color:#7f8c8d;'
                                    'text-transform:uppercase;letter-spacing:.08em;'
                                    'margin:10px 0 8px;">Singles</div>',
                                    unsafe_allow_html=True,
                                )
                                _render_card_grid(_singles_filtered)
                            if not _parlays_filtered.empty:
                                st.markdown(
                                    '<div style="font-size:0.70em;font-weight:700;color:#7f8c8d;'
                                    'text-transform:uppercase;letter-spacing:.08em;'
                                    'border-top:1px solid #1a2a40;padding-top:12px;'
                                    'margin:14px 0 8px;">DK Parlay Cards</div>',
                                    unsafe_allow_html=True,
                                )
                                _render_card_grid(_parlays_filtered)

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

            
            # Expert Picks (merged into Value Bets)
            with props_tab1:
                st.markdown("---")
                render_expert_picks_section(preds_df, prop_tournament_id)

            # =================================================================
            # TAB 2: HEAD-TO-HEAD MATCHUPS
            # =================================================================
            with props_tab2:

                _fd_mkt_path = DATA_DIR / "odds" / f"pga_market_odds_{prop_tournament_id}.csv"
                _dk_pl_path  = DATA_DIR / "odds" / f"prop_lines_{prop_tournament_id}.csv"

                
                try:
                    # ── Load FanDuel ──────────────────────────────────────
                    _fd_all = pd.read_csv(_fd_mkt_path) if _fd_mkt_path.exists() else pd.DataFrame()
                    def _fd_market(mtype, sub_contains=None):
                        if _fd_all.empty: return pd.DataFrame()
                        _s = _fd_all[_fd_all["market_type"] == mtype].copy()
                        if sub_contains:
                            _s = _s[_s["submarket_name"].str.contains(sub_contains, case=False, na=False)]
                        return _s

                    _fd_win   = _fd_market("ODDS_TO_WIN")
                    _fd_t10   = _fd_market("FINISH", "Incl. Ties")
                    if _fd_t10.empty: _fd_t10 = _fd_market("FINISH", "Top 10")
                    _fd_cut   = _fd_market("PLAYER_PROPS", "Make The Cut")

                    def _fd_odds_map(df):
                        if df.empty or "player_name" not in df.columns: return {}
                        df = df.copy()
                        df["odds_numeric"] = pd.to_numeric(df["odds_numeric"], errors="coerce")
                        return dict(zip(df["player_name"].str.lower().str.strip(),
                                        df["odds_numeric"]))

                    _fd_win_map = _fd_odds_map(_fd_win)
                    _fd_t10_map = _fd_odds_map(_fd_t10)
                    _fd_cut_map = _fd_odds_map(_fd_cut)

                    # ── Load DK ───────────────────────────────────────────
                    _dk_pl = pd.read_csv(_dk_pl_path) if _dk_pl_path.exists() else pd.DataFrame()
                    def _dk_market_map(market_str):
                        if _dk_pl.empty: return {}
                        _s = _dk_pl[_dk_pl["market"].astype(str).str.lower() == market_str].copy()
                        _s["odds"] = pd.to_numeric(_s["odds"], errors="coerce")
                        return dict(zip(_s["player_name"].str.lower().str.strip(), _s["odds"]))

                    _dk_win_map = _dk_market_map("outright")
                    _dk_t10_map = _dk_market_map("top10")
                    _dk_cut_map = _dk_market_map("make_cut")

                    # ── Build comparison table ────────────────────────────
                    # Use FD win market as the player universe (sorted by implied prob)
                    _shop_players = list(_fd_win_map.keys()) if _fd_win_map else list(_dk_win_map.keys())
                    _shop_players = sorted(
                        _shop_players,
                        key=lambda p: -(_fd_win_map.get(p, 99999) if _fd_win_map.get(p, 99999) > 0
                                        else abs(_fd_win_map.get(p, 99999)))
                    )[:35]

                    def _fmt_o(v):
                        if v is None or pd.isna(v): return "—"
                        n = int(v)
                        return f"+{n}" if n > 0 else str(n)

                    def _better(dk, fd):
                        """Return 'DK', 'FD', or '' depending on which is better value (higher implied payout)."""
                        if dk is None or pd.isna(dk) or fd is None or pd.isna(fd): return ""
                        # Higher American odds = better payout = better for bettor
                        return "DK" if int(dk) > int(fd) else ("FD" if int(fd) > int(dk) else "=")

                    _shop_rows = []
                    for _pn in _shop_players:
                        _dk_w = _dk_win_map.get(_pn)
                        _fd_w = _fd_win_map.get(_pn)
                        _dk_t = _dk_t10_map.get(_pn)
                        _fd_t = _fd_t10_map.get(_pn)
                        _dk_c = _dk_cut_map.get(_pn)
                        _fd_c = _fd_cut_map.get(_pn)
                        _shop_rows.append({
                            "Player":         _pn.title(),
                            "DK Win":         _fmt_o(_dk_w),
                            "FD Win":         _fmt_o(_fd_w),
                            "Win ▲":          _better(_dk_w, _fd_w),
                            "DK Top 10":      _fmt_o(_dk_t),
                            "FD Top 10":      _fmt_o(_fd_t),
                            "Top10 ▲":        _better(_dk_t, _fd_t),
                            "DK Make Cut":    _fmt_o(_dk_c),
                            "FD Make Cut":    _fmt_o(_fd_c),
                            "Cut ▲":          _better(_dk_c, _fd_c),
                            "_dk_w": _dk_w, "_fd_w": _fd_w,
                            "_dk_t": _dk_t, "_fd_t": _fd_t,
                        })

                    if _shop_rows:
                        _shop_df = pd.DataFrame(_shop_rows)

                        # Summary: how many FD vs DK wins
                        _win_counts = _shop_df["Win ▲"].value_counts()
                        _t10_counts = _shop_df["Top10 ▲"].value_counts()
                        _sc1, _sc2, _sc3, _sc4 = st.columns(4)
                        _sc1.metric("Win: FD better", int(_win_counts.get("FD", 0)))
                        _sc2.metric("Win: DK better", int(_win_counts.get("DK", 0)))
                        _sc3.metric("Top10: FD better", int(_t10_counts.get("FD", 0)))
                        _sc4.metric("Top10: DK better", int(_t10_counts.get("DK", 0)))

                        # Highlight rows with large spread
                        def _spread(dk, fd):
                            if dk is None or pd.isna(dk) or fd is None or pd.isna(fd): return 0
                            from scripts.models.recommend_bets import american_to_prob as _ap
                            return abs(_ap(int(dk)) - _ap(int(fd))) * 100

                        _shop_df["_spread_win"] = _shop_df.apply(
                            lambda r: _spread(r["_dk_w"], r["_fd_w"]), axis=1)
                        _shop_df["_spread_t10"] = _shop_df.apply(
                            lambda r: _spread(r["_dk_t"], r["_fd_t"]), axis=1)
                        _shop_df["Max Spread"] = _shop_df[["_spread_win","_spread_t10"]].max(axis=1).round(1)

                        _disp_cols = ["Player","DK Win","FD Win","Win ▲",
                                        "DK Top 10","FD Top 10","Top10 ▲",
                                        "DK Make Cut","FD Make Cut","Cut ▲","Max Spread"]
                        _shop_disp = _shop_df[_disp_cols].copy()

                        # Style: green for FD, blue-green for DK in ▲ columns
                        def _style_shop(df):
                            styles = pd.DataFrame("", index=df.index, columns=df.columns)
                            for col in ["Win ▲","Top10 ▲","Cut ▲"]:
                                if col in df.columns:
                                    styles.loc[df[col]=="FD", col] = "color:#1a78d4;font-weight:700"
                                    styles.loc[df[col]=="DK", col] = "color:#00c44f;font-weight:700"
                            # Highlight large spread rows
                            if "Max Spread" in df.columns:
                                _big = pd.to_numeric(df["Max Spread"], errors="coerce") >= 3.0
                                styles.loc[_big, "Max Spread"] = "color:#f39c12;font-weight:700"
                            return styles

                        st.dataframe(
                            _shop_disp.style.apply(_style_shop, axis=None),
                            hide_index=True, use_container_width=True, height=420,
                        )
                        st.caption("▲ = better value (higher payout). Max Spread = largest implied prob gap between books (pp). Rows with spread ≥ 3pp are worth line-shopping.")
                except Exception as _shop_e:
                    st.warning(f"Book shopping unavailable: {_shop_e}")

                st.markdown("---")


                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. Matchups are no longer active.")

                # ── DG Tournament Matchups ─────────────────────────────────────
                _tm_path = DATA_DIR / "datagolf" / f"dg_tourn_matchups_{prop_tournament_id}.csv"
                st.markdown("### ⚔️ Tournament Matchups")
                st.caption("Head-to-head odds from DataGolf for the full tournament. EV = DG probability × decimal odds − 1. Green = positive EV.")

                if not _tm_path.exists():
                    st.info(f"No tournament matchup data for {prop_tournament_id}. Run `fetch_dg_odds.py --market tournament_matchups` to fetch.")
                else:
                    try:
                        _tm_raw = pd.read_csv(_tm_path)
                        _tm_raw["book"] = _tm_raw["book"].astype(str).str.title()

                        # Extract DG model probs and book rows separately
                        _tm_dg    = _tm_raw[_tm_raw["is_dg_model"].astype(str).str.lower() == "true"].copy()
                        _tm_books = _tm_raw[_tm_raw["is_dg_model"].astype(str).str.lower() == "false"].copy()

                        _tm_book_pref = ["Draftkings","Fanduel","Bet365","Pinnacle","Betmgm","Caesars","Bovada","Betonline","Unibet"]
                        _tm_avail_books = [b for b in _tm_book_pref if b in _tm_books["book"].unique()] + \
                                          [b for b in _tm_books["book"].unique() if b not in _tm_book_pref]

                        # Filter controls
                        _tm_c1, _tm_c2, _tm_c3 = st.columns([2.5, 1, 1.5])
                        with _tm_c1:
                            _tm_sel_books = st.multiselect("Books", _tm_avail_books, default=_tm_avail_books[:4] if len(_tm_avail_books) >= 4 else _tm_avail_books, key="tm_books")
                        with _tm_c2:
                            _tm_pos_ev = st.checkbox("Positive EV only", value=False, key="tm_pos_ev")
                        with _tm_c3:
                            _tm_search = st.text_input("Search player", placeholder="e.g. McIlroy", key="tm_search")

                        _tm_sel_books = _tm_sel_books or _tm_avail_books

                        def _tm_to_decimal(o):
                            try:
                                v = float(str(o).replace("+",""))
                                if v >= 0:
                                    return 1 + v / 100
                                return 1 + 100 / abs(v)
                            except Exception:
                                return None

                        def _tm_fmt_odds(o):
                            try:
                                n = int(float(str(o).replace("+","")))
                                return f"+{n}" if n >= 0 else str(n)
                            except Exception:
                                return "—"

                        def _tm_fmt_name(n):
                            s = str(n).strip()
                            if "," in s:
                                parts = s.split(",", 1)
                                return parts[1].strip() + " " + parts[0].strip()
                            return s

                        # Build matchup list from DG model rows (one per pair)
                        _tm_pairs = _tm_dg[["p1_name","p2_name","p1_novig","p2_novig"]].drop_duplicates(subset=["p1_name","p2_name"])

                        if _tm_search:
                            _q = _tm_search.strip().lower()
                            _tm_pairs = _tm_pairs[
                                _tm_pairs["p1_name"].str.lower().str.contains(_q, na=False) |
                                _tm_pairs["p2_name"].str.lower().str.contains(_q, na=False)
                            ]

                        if _tm_pairs.empty:
                            st.info("No matchups match current filters.")
                        else:
                            # Build HTML table
                            _books_to_show = _tm_sel_books
                            _hdr_books = "".join(
                                f'<th style="text-align:center;padding:6px 8px;color:#5a7090;font-size:10px;'
                                f'text-transform:uppercase;letter-spacing:.05em;">{b[:2].upper()}</th>'
                                for b in _books_to_show
                            )
                            _tm_html = f"""
<style>
.tm-tbl {{width:100%;border-collapse:collapse;font-size:12px;}}
.tm-tbl th,.tm-tbl td {{padding:5px 8px;border-bottom:1px solid #0e1e30;}}
.tm-tbl tr:hover td {{background:#0d1929;}}
.tm-pos {{background:rgba(0,196,79,0.18);color:#00c44f;font-weight:700;border-radius:3px;padding:1px 4px;}}
.tm-neg {{color:#3a5060;}}
.tm-dg  {{color:#4cb8ff;font-weight:700;}}
.tm-vs  {{color:#1a3050;font-weight:900;text-align:center;padding:0 6px;}}
</style>
<table class="tm-tbl">
<thead><tr>
  <th style="text-align:left;color:#5a7090;font-size:10px;text-transform:uppercase;letter-spacing:.05em;">Player 1</th>
  <th style="text-align:center;color:#4cb8ff;font-size:10px;text-transform:uppercase;letter-spacing:.05em;">DG%</th>
  {_hdr_books}
  <th class="tm-vs"></th>
  <th style="text-align:left;color:#5a7090;font-size:10px;text-transform:uppercase;letter-spacing:.05em;">Player 2</th>
  <th style="text-align:center;color:#4cb8ff;font-size:10px;text-transform:uppercase;letter-spacing:.05em;">DG%</th>
  {_hdr_books}
</tr></thead><tbody>
"""
                            _tm_rows_shown = 0
                            for _, _pair in _tm_pairs.iterrows():
                                _p1 = _pair["p1_name"]
                                _p2 = _pair["p2_name"]
                                _dg1 = float(_pair.get("p1_novig", 0.5) or 0.5)
                                _dg2 = float(_pair.get("p2_novig", 0.5) or 0.5)

                                # Book odds for this pair
                                _pair_books = _tm_books[
                                    (_tm_books["p1_name"] == _p1) & (_tm_books["p2_name"] == _p2)
                                ].set_index("book")

                                # Check positive EV filter — at least one book has EV>0
                                if _tm_pos_ev:
                                    _any_pos = False
                                    for _bk in _books_to_show:
                                        if _bk in _pair_books.index:
                                            _r = _pair_books.loc[_bk]
                                            _d1 = _tm_to_decimal(_r.get("p1_odds"))
                                            _d2 = _tm_to_decimal(_r.get("p2_odds"))
                                            if _d1 and _dg1 * _d1 - 1 > 0:
                                                _any_pos = True; break
                                            if _d2 and _dg2 * _d2 - 1 > 0:
                                                _any_pos = True; break
                                    if not _any_pos:
                                        continue

                                def _book_cells(dg_prob, odds_col):
                                    cells = ""
                                    for _bk in _books_to_show:
                                        if _bk not in _pair_books.index:
                                            cells += '<td style="text-align:center;color:#1a2e40;">—</td>'
                                            continue
                                        _brow = _pair_books.loc[_bk]
                                        _odds_raw = _brow.get(odds_col)
                                        _dec = _tm_to_decimal(_odds_raw)
                                        if _dec is None:
                                            cells += '<td style="text-align:center;color:#1a2e40;">—</td>'
                                            continue
                                        _ev = dg_prob * _dec - 1
                                        _odds_str = _tm_fmt_odds(_odds_raw)
                                        _cls = "tm-pos" if _ev > 0 else "tm-neg"
                                        _ev_badge = f'<span style="font-size:9px;color:#00c44f;margin-left:3px;">+{_ev*100:.1f}%</span>' if _ev > 0 else ""
                                        cells += f'<td style="text-align:center;"><span class="{_cls}">{_odds_str}</span>{_ev_badge}</td>'
                                    return cells

                                _cells_p1 = _book_cells(_dg1, "p1_odds")
                                _cells_p2 = _book_cells(_dg2, "p2_odds")
                                _tm_rows_shown += 1

                                _tm_html += (
                                    f'<tr>'
                                    f'<td style="font-weight:600;color:#dde6f5;white-space:nowrap;">{_tm_fmt_name(_p1)}</td>'
                                    f'<td style="text-align:center;" class="tm-dg">{_dg1*100:.1f}%</td>'
                                    f'{_cells_p1}'
                                    f'<td class="tm-vs">vs</td>'
                                    f'<td style="font-weight:600;color:#dde6f5;white-space:nowrap;">{_tm_fmt_name(_p2)}</td>'
                                    f'<td style="text-align:center;" class="tm-dg">{_dg2*100:.1f}%</td>'
                                    f'{_cells_p2}'
                                    f'</tr>'
                                )

                            _tm_html += "</tbody></table>"

                            if _tm_rows_shown == 0:
                                st.info("No positive-EV matchups found. Uncheck 'Positive EV only' to see all.")
                            else:
                                _tm_updated = str(_tm_raw["last_updated"].iloc[0]) if "last_updated" in _tm_raw.columns else ""
                                if _tm_updated:
                                    st.caption(f"Updated: {_tm_updated}")
                                st.markdown(_tm_html, unsafe_allow_html=True)
                                st.caption(f"{_tm_rows_shown} matchups · EV = DG prob × decimal odds − 1 · Green = positive edge")
                    except Exception as _tm_e:
                        st.warning(f"Tournament matchups unavailable: {_tm_e}")

                # =============================================================
                # DG 3-BALL PAIRINGS
                # =============================================================
                st.markdown("---")
                st.markdown("### ⛳ DG 3-Ball Pairings")
                st.caption("Tee times and tournament matchup odds from DataGolf. Refresh with `fetch_dg_matchups.py`.")
                try:
                    import duckdb as _duckdb
                    with _duckdb.connect(str(DATA_DIR / "golf_data.db"), read_only=True) as _dbc:
                        _dg_mu = _dbc.execute(
                            "SELECT teetime, p1_name, p1_odds, p2_name, p2_odds, p3_name, p3_odds, last_update "
                            "FROM dg_matchups ORDER BY teetime"
                        ).df()
                except Exception:
                    _mu_csv = DATA_DIR / "datagolf" / "dg_matchups_latest.csv"
                    _dg_mu = pd.read_csv(_mu_csv) if _mu_csv.exists() else pd.DataFrame()

                if _dg_mu.empty:
                    st.info("No DG matchup data. Run `fetch_dg_matchups.py` to fetch.")
                else:
                    def _fmt_odds(v):
                        try:
                            n = int(float(v))
                            return f"+{n}" if n > 0 else str(n)
                        except Exception:
                            return "—"

                    def _fmt_name(n):
                        s = str(n)
                        if "," in s:
                            parts = s.split(",", 1)
                            return parts[1].strip() + " " + parts[0].strip()
                        return s

                    _mu_updated = str(_dg_mu["last_update"].iloc[0]) if "last_update" in _dg_mu.columns else ""
                    if _mu_updated:
                        st.caption(f"Updated: {_mu_updated}")

                    _mu_parts = ["""
<div style="display:grid;grid-template-columns:100px 1fr 70px 1fr 70px 1fr 70px;
     gap:0;font-size:10px;color:#4a6080;font-weight:700;letter-spacing:.05em;
     padding:4px 10px;border-bottom:1px solid #0e1e30;margin-bottom:4px;">
  <div>TEE TIME</div><div>PLAYER 1</div><div style="text-align:center;">ODDS</div>
  <div>PLAYER 2</div><div style="text-align:center;">ODDS</div>
  <div>PLAYER 3</div><div style="text-align:center;">ODDS</div>
</div>"""]

                    for _, _mr in _dg_mu.iterrows():
                        _tt   = str(_mr.get("teetime", "")).split("T")[-1][:5] if "T" in str(_mr.get("teetime","")) else str(_mr.get("teetime",""))[:5]
                        _p1   = _fmt_name(_mr.get("p1_name", ""))
                        _p2   = _fmt_name(_mr.get("p2_name", ""))
                        _p3   = _fmt_name(_mr.get("p3_name", ""))
                        _o1   = _fmt_odds(_mr.get("p1_odds"))
                        _o2   = _fmt_odds(_mr.get("p2_odds"))
                        _o3   = _fmt_odds(_mr.get("p3_odds"))
                        _is_tie = _p3.strip() in ("-1", "Tie", "", "nan")
                        _p3_disp = "—" if _is_tie else _p3
                        _o3_disp = "—" if _is_tie else _o3
                        _mu_parts.append(
                            f"<div style='display:grid;grid-template-columns:100px 1fr 70px 1fr 70px 1fr 70px;"
                            f"gap:0;background:#0b1929;padding:5px 10px;border-radius:4px;margin-bottom:2px;align-items:center;'>"
                            f"<div style='font-size:11px;color:#4a6080;'>{_tt}</div>"
                            f"<div style='font-size:12px;font-weight:600;color:#dde6f5;'>{_p1}</div>"
                            f"<div style='text-align:center;font-size:12px;color:#ffa726;font-weight:700;'>{_o1}</div>"
                            f"<div style='font-size:12px;font-weight:600;color:#dde6f5;'>{_p2}</div>"
                            f"<div style='text-align:center;font-size:12px;color:#ffa726;font-weight:700;'>{_o2}</div>"
                            f"<div style='font-size:12px;color:#8a9ab0;'>{_p3_disp}</div>"
                            f"<div style='text-align:center;font-size:12px;color:#ffa726;'>{_o3_disp}</div>"
                            f"</div>"
                        )
                    st.markdown("\n".join(_mu_parts), unsafe_allow_html=True)
                    st.caption(f"{len(_dg_mu)} pairings · Tournament matchup odds")

            # =================================================================
            # TAB 3: ODDS EXPLORER
            # =================================================================
            with props_tab3:

                # ── load DG outrights ──────────────────────────────────────────
                _oe_path = DATA_DIR / "datagolf" / f"dg_outrights_{prop_tournament_id}.csv"
                _oe_matchup_path = DATA_DIR / "datagolf" / f"dg_matchups_{prop_tournament_id}.csv"

                if not _oe_path.exists():
                    st.info(f"No DG odds data found for {prop_tournament_id}. Fetch will run automatically before tournament.")
                else:
                    _oe_raw = pd.read_csv(_oe_path)
                    # Normalize book names to title-case for consistent display/filtering
                    _oe_raw["book"] = _oe_raw["book"].astype(str).str.title()
                    _oe_model = _oe_raw[_oe_raw["is_dg_model"].astype(str).str.lower() == "true"][["player_name","market","implied_prob"]].copy()
                    _oe_books = _oe_raw[_oe_raw["is_dg_model"].astype(str).str.lower() == "false"].copy()

                    # Preferred display order for books
                    _oe_book_pref = ["Draftkings","Fanduel","Pointsbet","Bet365","Betonline","Caesars","Unibet","Bovada","Betmgm","Pinnacle","Betcris"]

                    # ── Market / book / EV filter controls ──────────────────
                    _oe_c1, _oe_c2, _oe_c3, _oe_c4 = st.columns([1, 2.5, 1.2, 1])
                    with _oe_c1:
                        _oe_mkt_opts = [m for m in ["top_10","top_20","top_5","win","make_cut"] if m in _oe_books["market"].unique()]
                        _oe_mkt_labels = {"top_10":"Top 10","top_20":"Top 20","top_5":"Top 5","win":"Win","make_cut":"Make Cut"}
                        _oe_sel_mkt = st.selectbox("Market", _oe_mkt_opts, format_func=lambda x: _oe_mkt_labels.get(x, x), key="oe_mkt")
                    with _oe_c2:
                        _oe_avail = sorted(_oe_books[_oe_books["market"]==_oe_sel_mkt]["book"].unique().tolist())
                        _oe_all_books = [b for b in _oe_book_pref if b in _oe_avail] + [b for b in _oe_avail if b not in _oe_book_pref]
                        _oe_sel_books = st.multiselect("Books", _oe_all_books, default=_oe_all_books, key="oe_books")
                    with _oe_c3:
                        _oe_pos_ev = st.checkbox("Positive EV only", value=False, key="oe_pos_ev")
                    with _oe_c4:
                        _oe_search = st.text_input("Search player", placeholder="e.g. McIlroy", key="oe_search")

                    # ── Build per-player DG prob lookup ──────────────────────
                    _oe_dg = _oe_model[_oe_model["market"]==_oe_sel_mkt].set_index("player_name")["implied_prob"].to_dict()

                    # ── Filter book rows ─────────────────────────────────────
                    _oe_sub = _oe_books[
                        (_oe_books["market"] == _oe_sel_mkt) &
                        (_oe_books["book"].isin(_oe_sel_books if _oe_sel_books else _oe_all_books))
                    ].copy()

                    def _oe_to_decimal(o):
                        try:
                            v = float(str(o).replace("+",""))
                            return (1 + v/100) if v > 0 else (1 + 100/abs(v))
                        except Exception:
                            return None

                    _oe_sub["_dec"] = _oe_sub["odds_american"].apply(_oe_to_decimal)
                    _oe_sub["_dg_prob"] = _oe_sub["player_name"].map(_oe_dg)
                    _oe_sub["_ev"] = (_oe_sub["_dg_prob"] * _oe_sub["_dec"] - 1) * 100

                    # Filter positive EV
                    if _oe_pos_ev:
                        _oe_sub = _oe_sub[_oe_sub["_ev"] > 0]

                    # Search filter
                    if _oe_search.strip():
                        _srch = _oe_search.strip().lower()
                        _oe_sub = _oe_sub[_oe_sub["player_name"].str.lower().str.contains(_srch, na=False)]

                    # ── Pivot table: player × book ───────────────────────────
                    # Sort players by DG model prob (descending)
                    _oe_player_order = (
                        _oe_model[_oe_model["market"]==_oe_sel_mkt]
                        .sort_values("implied_prob", ascending=False)["player_name"]
                        .tolist()
                    )
                    _oe_players_in_sub = [p for p in _oe_player_order if p in _oe_sub["player_name"].values]
                    # add any players missing from order
                    for p in _oe_sub["player_name"].unique():
                        if p not in _oe_players_in_sub:
                            _oe_players_in_sub.append(p)

                    if _oe_sub.empty or not _oe_players_in_sub:
                        st.info("No odds found for the selected filters.")
                    else:
                        # Build HTML table
                        _oe_books_ordered = _oe_sel_books if _oe_sel_books else _oe_all_books

                        # Styles
                        _oe_css = """
<style>
.oe-wrap { overflow-x:auto; }
.oe-tbl { border-collapse:collapse; width:100%; font-size:13px; }
.oe-tbl th {
    background:#1a1a2e; color:#a0a0b8; font-weight:600;
    padding:8px 10px; text-align:center; border-bottom:2px solid #2d2d4e;
    white-space:nowrap; position:sticky; top:0; z-index:2;
}
.oe-tbl th.player-col { text-align:left; min-width:140px; }
.oe-tbl th.dg-col { background:#0d2035; color:#4cb8ff; min-width:80px; }
.oe-tbl td { padding:6px 10px; text-align:center; border-bottom:1px solid #1e1e2e; white-space:nowrap; }
.oe-tbl td.player-cell { text-align:left; font-weight:500; color:#e0e0f0; padding-left:10px; }
.oe-tbl td.dg-cell { background:#0a1825; color:#4cb8ff; font-weight:600; }
.oe-tbl tr:hover td { background:#16162a !important; }
.oe-tbl tr:hover td.dg-cell { background:#0d2035 !important; }
.pos-ev { background:#0a2a14; color:#00e676; font-weight:700; border-radius:3px; }
.neg-ev { color:#6a6a7a; }
.ev-badge { font-size:10px; display:block; margin-top:1px; }
.ev-pos-badge { color:#00e676; }
.ev-neg-badge { color:#555570; }
</style>"""

                        _oe_rows_html = []
                        for _oe_pn in _oe_players_in_sub:
                            _oe_dg_p = _oe_dg.get(_oe_pn)
                            _oe_dg_pct = f"{_oe_dg_p*100:.1f}%" if _oe_dg_p is not None else "—"
                            # Format player name: "Last, First" → "First Last"
                            _oe_disp_name = _oe_pn
                            if "," in _oe_pn:
                                _pts = _oe_pn.split(",", 1)
                                _oe_disp_name = f"{_pts[1].strip()} {_pts[0].strip()}"

                            _cells = [
                                f'<td class="player-cell">{_oe_disp_name}</td>',
                                f'<td class="dg-cell">{_oe_dg_pct}</td>',
                            ]
                            for _bk in _oe_books_ordered:
                                _bk_row = _oe_sub[(_oe_sub["player_name"]==_oe_pn) & (_oe_sub["book"]==_bk)]
                                if _bk_row.empty:
                                    _cells.append('<td class="neg-ev">—</td>')
                                else:
                                    _r = _bk_row.iloc[0]
                                    try:
                                        _ods = int(float(_r["odds_american"]))
                                        _ods_str = f"+{_ods}" if _ods > 0 else str(_ods)
                                    except Exception:
                                        _ods_str = str(_r["odds_american"])
                                    _ev = _r["_ev"]
                                    if pd.notna(_ev) and _ev > 0:
                                        _cells.append(
                                            f'<td class="pos-ev">{_ods_str}'
                                            f'<span class="ev-badge ev-pos-badge">+{_ev:.1f}% EV</span></td>'
                                        )
                                    else:
                                        _ev_str = f"{_ev:.1f}%" if pd.notna(_ev) else ""
                                        _cells.append(
                                            f'<td class="neg-ev">{_ods_str}'
                                            f'<span class="ev-badge ev-neg-badge">{_ev_str}</span></td>'
                                        )

                            _oe_rows_html.append(f"<tr>{''.join(_cells)}</tr>")

                        _oe_header_cells = (
                            '<th class="player-col">Player</th>'
                            '<th class="dg-col">DG Model</th>'
                            + "".join(f"<th>{b}</th>" for b in _oe_books_ordered)
                        )

                        _oe_n_pos = int((_oe_sub["_ev"] > 0).sum()) if not _oe_sub.empty else 0
                        _oe_last_upd = _oe_raw.get("last_updated", pd.Series()).dropna().iloc[0] if "last_updated" in _oe_raw.columns and not _oe_raw["last_updated"].dropna().empty else ""

                        _oe_meta_c1, _oe_meta_c2, _oe_meta_c3 = st.columns(3)
                        with _oe_meta_c1:
                            st.caption(f"{len(_oe_players_in_sub)} players · {_oe_mkt_labels.get(_oe_sel_mkt, _oe_sel_mkt)} · {len(_oe_books_ordered)} books")
                        with _oe_meta_c2:
                            st.caption(f"{_oe_n_pos} positive-EV cells (DG model × actual odds)")
                        with _oe_meta_c3:
                            if _oe_last_upd:
                                st.caption(f"DG updated: {str(_oe_last_upd)[:16]}")

                        st.markdown(
                            _oe_css
                            + '<div class="oe-wrap"><table class="oe-tbl"><thead><tr>'
                            + _oe_header_cells
                            + "</tr></thead><tbody>"
                            + "".join(_oe_rows_html)
                            + "</tbody></table></div>",
                            unsafe_allow_html=True,
                        )

                    # ── Round Matchups section ───────────────────────────────
                    if _oe_matchup_path.exists():
                        st.markdown("---")
                        st.markdown("#### Round Matchups")
                        _oe_mu = pd.read_csv(_oe_matchup_path)
                        _oe_mu["book"] = _oe_mu["book"].astype(str).str.title()
                        _oe_mu_model = _oe_mu[_oe_mu["is_dg_model"].astype(str).str.lower()=="true"].copy()
                        _oe_mu_books = _oe_mu[_oe_mu["is_dg_model"].astype(str).str.lower()=="false"].copy()

                        if not _oe_mu_books.empty:
                            _oe_mu_c1, _oe_mu_c2, _oe_mu_c3 = st.columns([2, 1, 1])
                            with _oe_mu_c1:
                                _oe_mu_book_opts = sorted(_oe_mu_books["book"].unique().tolist())
                                _oe_mu_sel_book = st.selectbox("Matchup Book", _oe_mu_book_opts, key="oe_mu_book")
                            with _oe_mu_c2:
                                _oe_mu_pos_ev = st.checkbox("Positive EV only", value=False, key="oe_mu_pos_ev")
                            with _oe_mu_c3:
                                _oe_mu_search = st.text_input("Search player", placeholder="e.g. Scott", key="oe_mu_search")

                            _oe_mu_filt = _oe_mu_books[_oe_mu_books["book"]==_oe_mu_sel_book].copy()

                            # Merge DG model probs
                            _oe_mu_dg = _oe_mu_model.rename(columns={"p1_name":"p1","p2_name":"p2","p1_novig":"dg_p1","p2_novig":"dg_p2"})[["p1","p2","dg_p1","dg_p2"]]
                            _oe_mu_filt = _oe_mu_filt.merge(_oe_mu_dg, left_on=["p1_name","p2_name"], right_on=["p1","p2"], how="left")

                            def _oe_mu_dec(o):
                                try:
                                    v = float(str(o).replace("+",""))
                                    return (1 + v/100) if v > 0 else (1 + 100/abs(v))
                                except Exception:
                                    return None

                            _oe_mu_filt["dec_p1"] = _oe_mu_filt["p1_odds"].apply(_oe_mu_dec)
                            _oe_mu_filt["dec_p2"] = _oe_mu_filt["p2_odds"].apply(_oe_mu_dec)
                            _oe_mu_filt["ev_p1"] = (_oe_mu_filt["dg_p1"] * _oe_mu_filt["dec_p1"] - 1) * 100
                            _oe_mu_filt["ev_p2"] = (_oe_mu_filt["dg_p2"] * _oe_mu_filt["dec_p2"] - 1) * 100

                            if _oe_mu_pos_ev:
                                _oe_mu_filt = _oe_mu_filt[(_oe_mu_filt["ev_p1"] > 0) | (_oe_mu_filt["ev_p2"] > 0)]

                            if _oe_mu_search.strip():
                                _s = _oe_mu_search.strip().lower()
                                _oe_mu_filt = _oe_mu_filt[
                                    _oe_mu_filt["p1_name"].str.lower().str.contains(_s, na=False) |
                                    _oe_mu_filt["p2_name"].str.lower().str.contains(_s, na=False)
                                ]

                            if _oe_mu_filt.empty:
                                st.caption("No matchups for current filters.")
                            else:
                                def _fmt_p(n):
                                    if "," in str(n):
                                        pts = str(n).split(",", 1)
                                        return f"{pts[1].strip()} {pts[0].strip()}"
                                    return str(n)
                                def _fmt_o(o):
                                    try:
                                        v = int(float(o))
                                        return f"+{v}" if v > 0 else str(v)
                                    except Exception:
                                        return str(o)
                                def _fmt_ev(ev):
                                    if pd.isna(ev): return ""
                                    return f"+{ev:.1f}%" if ev > 0 else f"{ev:.1f}%"

                                _mu_rows = []
                                for _, _mr in _oe_mu_filt.iterrows():
                                    _p1 = _fmt_p(_mr.get("p1_name",""))
                                    _p2 = _fmt_p(_mr.get("p2_name",""))
                                    _o1 = _fmt_o(_mr.get("p1_odds",""))
                                    _o2 = _fmt_o(_mr.get("p2_odds",""))
                                    _dg1 = f"{_mr['dg_p1']*100:.1f}%" if pd.notna(_mr.get("dg_p1")) else "—"
                                    _dg2 = f"{_mr['dg_p2']*100:.1f}%" if pd.notna(_mr.get("dg_p2")) else "—"
                                    _ev1 = _fmt_ev(_mr.get("ev_p1"))
                                    _ev2 = _fmt_ev(_mr.get("ev_p2"))
                                    _mu_rows.append({
                                        "Player 1": _p1,
                                        "P1 Odds": _o1,
                                        "DG P1": _dg1,
                                        "P1 EV": _ev1,
                                        "Player 2": _p2,
                                        "P2 Odds": _o2,
                                        "DG P2": _dg2,
                                        "P2 EV": _ev2,
                                    })

                                _mu_display = pd.DataFrame(_mu_rows)

                                def _style_mu(v):
                                    if isinstance(v, str) and v.startswith("+") and "%" in v:
                                        return "color:#00e676;font-weight:700"
                                    if isinstance(v, str) and "%" in v:
                                        return "color:#666680"
                                    return ""

                                st.dataframe(
                                    _mu_display.style.applymap(_style_mu, subset=["P1 EV","P2 EV"]),
                                    hide_index=True, use_container_width=True,
                                    height=min(600, 38 + len(_mu_display) * 35),
                                )

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
                st.caption("Script output:")
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

        # ── Augusta composite scoring (Masters only) ─────────────────────────
        _aug_qual_df: pd.DataFrame = pd.DataFrame()
        _aug_composite_map: dict = {}
        _aug_qscore_map: dict = {}
        _has_augusta_data = False
        if selected_tournament_id:
            _aug_qual_path = DATA_DIR / "qualitative" / f"masters_qualifiers_{selected_tournament_id}.csv"
            if _aug_qual_path.exists():
                try:
                    _aug_raw = pd.read_csv(_aug_qual_path)
                    def _aug_nk(n: str) -> str:
                        s = str(n).strip().lower()
                        if ", " in s:
                            p = s.split(", ", 1)
                            return f"{p[1]} {p[0]}"
                        return s
                    def _aug_minmax(s: pd.Series) -> pd.Series:
                        mn, mx = s.min(), s.max()
                        return pd.Series([0.5]*len(s), index=s.index) if mx == mn else (s - mn) / (mx - mn)

                    for _ac in ["augusta_avg_to_par","sg_t2g_last4_total","augusta_starts",
                                "augusta_cuts_made","driving_dist_field_rank"]:
                        _aug_raw[_ac] = pd.to_numeric(_aug_raw[_ac], errors="coerce")
                    _aug_raw["augusta_starts"]     = _aug_raw["augusta_starts"].fillna(1).clip(lower=1)
                    _aug_raw["augusta_cuts_made"]  = _aug_raw["augusta_cuts_made"].fillna(0)
                    _aug_raw["driving_dist_field_rank"] = _aug_raw["driving_dist_field_rank"].fillna(88)

                    _aug_raw["_s_aug"]     = _aug_minmax(-_aug_raw["augusta_avg_to_par"].fillna(0))
                    _aug_raw["_s_form"]    = _aug_minmax(_aug_raw["sg_t2g_last4_total"].fillna(0))
                    _aug_raw["_s_consist"] = _aug_minmax(_aug_raw["augusta_cuts_made"] / _aug_raw["augusta_starts"])
                    _aug_raw["_s_dist"]    = _aug_minmax(-_aug_raw["driving_dist_field_rank"])

                    # Blend in model top10_prob if available
                    _prob_col = "top10_prob_calibrated" if "top10_prob_calibrated" in df.columns else "top10_prob"
                    if _prob_col in df.columns:
                        _df_prob = df[["player_name", _prob_col]].copy()
                        _df_prob["_key"] = _df_prob["player_name"].apply(_aug_nk)
                        _aug_raw["_key"]  = _aug_raw["player_name"].apply(_aug_nk)
                        _prob_map = dict(zip(_df_prob["_key"], pd.to_numeric(_df_prob[_prob_col], errors="coerce")))
                        _aug_raw["_model_prob"] = _aug_raw["_key"].map(_prob_map).fillna(0)
                        _aug_raw["_s_prob"] = _aug_minmax(_aug_raw["_model_prob"])
                    else:
                        _aug_raw["_s_prob"] = 0.5

                    _aug_raw["aug_composite"] = (
                        0.30 * _aug_raw["_s_aug"] +
                        0.25 * _aug_raw["_s_form"] +
                        0.20 * _aug_raw["_s_consist"] +
                        0.15 * _aug_raw["_s_dist"] +
                        0.10 * _aug_raw["_s_prob"]
                    ).round(3)

                    _aug_raw["aug_rank"] = _aug_raw["aug_composite"].rank(ascending=False, method="min").astype(int)
                    _aug_qual_df = _aug_raw.sort_values("aug_composite", ascending=False).reset_index(drop=True)

                    # Build lookup maps keyed by normalized name
                    for _, _ar in _aug_raw.iterrows():
                        _k = _aug_nk(str(_ar["player_name"]))
                        _aug_composite_map[_k] = round(float(_ar["aug_composite"]), 3)
                        _aug_qscore_map[_k]    = int(_ar.get("qualifier_score", 0))
                    _has_augusta_data = True
                except Exception:
                    pass

        # Tabs — add Augusta Fit tab when qualifier data is available
        _tab_labels = ["🏆 Top Picks", "🎖️ Tier List", "💡 Value Picks", "📊 Model Accuracy"]
        if _has_augusta_data:
            _tab_labels.append("⛳ Augusta Fit")
        _tabs = st.tabs(_tab_labels)
        tab1, tab2, tab3, tab4 = _tabs[0], _tabs[1], _tabs[2], _tabs[3]
        tab5 = _tabs[4] if _has_augusta_data else None

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
            # Augusta composite column (Masters only)
            if _has_augusta_data:
                def _aug_fit_fmt(name):
                    k = _aug_nk(str(name))
                    qs = _aug_qscore_map.get(k, 0)
                    comp = _aug_composite_map.get(k, None)
                    if comp is None:
                        return "—"
                    return f"{comp:.3f} ({qs}/8)"
                display_df['aug_fit'] = top_20['player_name'].apply(_aug_fit_fmt)
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
                'aug_fit': 'Augusta Fit',
            }
            _extra_display = ['2025 Earnings', 'KFT History', 'LIV History']
            if _has_augusta_data:
                _extra_display.append('Augusta Fit')
            display_df.columns = (
                [_col_rename.get(c, c) for c in display_cols] + _extra_display
            )

            # ── Player card grid ────────────────────────────────────────────
            def _picks_card_html(rank, row, max_win, max_t10):
                """Return HTML for a single Top Picks player card."""
                name_raw = str(row.get('player_name', ''))
                if ', ' in name_raw:
                    _p = name_raw.split(', ', 1)
                    name_display = f"{_p[1]} {_p[0]}"
                else:
                    name_display = name_raw

                win_pct  = float(row.get('win_prob', 0) or 0) * 100
                t10_pct  = float(row.get('top10_prob', 0) or 0) * 100
                wr_raw   = row.get('world_rank')
                sg_raw   = row.get('sg_total')
                vsf_raw  = row.get('projected_score_vs_field')
                odds_raw = row.get('odds_to_win')

                win_bar = min(100, (win_pct / (max_win * 100) * 100)) if max_win > 0 else 0
                t10_bar = min(100, (t10_pct / (max_t10 * 100) * 100)) if max_t10 > 0 else 0

                wr_str  = f"WR #{int(wr_raw)}" if pd.notna(wr_raw) and float(wr_raw) < 400 else ""
                sg_str  = f"{float(sg_raw):+.2f}" if pd.notna(sg_raw) else "—"
                sg_col  = "#00c44f" if pd.notna(sg_raw) and float(sg_raw) > 0 else ("#e74c3c" if pd.notna(sg_raw) and float(sg_raw) < 0 else "#8ba0b8")

                if pd.notna(vsf_raw):
                    _v = float(vsf_raw)
                    vsf_str = "E" if _v == 0 else (f"+{_v:.1f}" if _v > 0 else f"{_v:.1f}")
                    vsf_col = "#e74c3c" if _v > 0 else ("#8ba0b8" if _v == 0 else "#00c44f")
                else:
                    vsf_str, vsf_col = "—", "#8ba0b8"

                odds_str = f"{int(odds_raw):+d}" if pd.notna(odds_raw) and odds_raw != 0 else ""

                if rank == 1:   rbg, rcol = "#ffd70022", "#ffd700"
                elif rank == 2: rbg, rcol = "#c0c0c022", "#c0c0c0"
                elif rank == 3: rbg, rcol = "#cd7f3222", "#cd7f32"
                else:           rbg, rcol = "#00c44f18", "#00c44f"

                odds_html = f'<span style="font-size:0.78em;color:#8ba0b8;">Odds <span style="color:#dde6f5;font-weight:600;">{odds_str}</span></span>' if odds_str else ''
                wr_html   = f'<span style="color:#8ba0b8;font-size:0.8em;white-space:nowrap;">{wr_str}</span>' if wr_str else '<span></span>'

                return f"""
<div style="background:#0d1a30;border:1px solid #1e3a5f;border-radius:10px;padding:14px 16px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
    <div style="display:flex;align-items:center;gap:8px;overflow:hidden;">
      <span style="background:{rbg};color:{rcol};font-weight:700;font-size:0.9em;padding:2px 8px;border-radius:4px;min-width:28px;text-align:center;flex-shrink:0;">#{rank}</span>
      <span style="font-size:1.0em;font-weight:600;color:#dde6f5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name_display}</span>
    </div>
    {wr_html}
  </div>
  <div style="margin-bottom:8px;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
      <span style="color:#8ba0b8;font-size:0.75em;width:44px;flex-shrink:0;">Win</span>
      <div style="flex:1;background:#1a2537;border-radius:3px;height:5px;">
        <div style="width:{win_bar:.0f}%;background:#00c44f;border-radius:3px;height:5px;"></div>
      </div>
      <span style="color:#00c44f;font-size:0.85em;font-weight:700;width:40px;text-align:right;flex-shrink:0;">{win_pct:.1f}%</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="color:#8ba0b8;font-size:0.75em;width:44px;flex-shrink:0;">Top-10</span>
      <div style="flex:1;background:#1a2537;border-radius:3px;height:5px;">
        <div style="width:{t10_bar:.0f}%;background:#4cb8ff;border-radius:3px;height:5px;"></div>
      </div>
      <span style="color:#4cb8ff;font-size:0.85em;font-weight:700;width:40px;text-align:right;flex-shrink:0;">{t10_pct:.1f}%</span>
    </div>
  </div>
  <div style="display:flex;gap:14px;padding-top:8px;border-top:1px solid #1a2537;flex-wrap:wrap;">
    <span style="font-size:0.78em;color:#8ba0b8;">SG Total <span style="color:{sg_col};font-weight:600;">{sg_str}</span></span>
    <span style="font-size:0.78em;color:#8ba0b8;">vs Field <span style="color:{vsf_col};font-weight:600;">{vsf_str}</span></span>
    {odds_html}
  </div>
</div>"""

            _max_win = float(top_20['win_prob'].max() or 0.01)
            _max_t10 = float(top_20['top10_prob'].max() or 0.01)
            _card_rows_data = list(top_20.head(10).iterrows())

            for _ci in range(0, len(_card_rows_data), 2):
                _pair = _card_rows_data[_ci:_ci+2]
                _gcols = st.columns(2)
                for _gi, (_, _grow) in enumerate(_pair):
                    _gcols[_gi].markdown(
                        _picks_card_html(_ci + _gi + 1, _grow, _max_win, _max_t10),
                        unsafe_allow_html=True
                    )

            # Ranks 11-20 in a compact collapsible table
            if len(top_20) > 10:
                with st.expander("Show picks 11–20", expanded=False):
                    _rest = display_df.iloc[10:].reset_index(drop=True)
                    _rest.index = _rest.index + 11
                    st.dataframe(_rest, use_container_width=True)
                    st.caption("**vs Avg** — strokes vs field avg (negative = better). **Ceiling/Floor** — Q10/Q90 projection range.")

            st.markdown("""
<div style="background:#0d1a30; border:1px solid #1e3a5f; border-left:4px solid #00c44f;
            padding:16px 20px; border-radius:8px; margin:12px 0 4px 0;">
  <div style="font-size:1.0em; font-weight:600; color:#dde6f5; margin-bottom:6px;">
    🤖 Ask the Golf Assistant
  </div>
  <div style="color:#8ba0b8; font-size:0.9em; line-height:1.6;">
    For a full breakdown of any pick — form, course fit, model vs market, expert consensus, and a verdict —
    ask the assistant on the right:
    <br><br>
    <span style="color:#00c44f; font-family:monospace;">"Why should I pick [player name]?"</span><br>
    <span style="color:#00c44f; font-family:monospace;">"Make the case for [player name]"</span><br>
    <span style="color:#00c44f; font-family:monospace;">"Tell me about [player name] this week"</span>
  </div>
</div>
""", unsafe_allow_html=True)

        with tab2:
            render_tier_list(df)

        with tab3:
            _val_df = df.copy()
            _has_edge = (
                "model_vs_vegas_edge" in _val_df.columns
                and pd.to_numeric(_val_df["model_vs_vegas_edge"], errors="coerce").abs().max() > 0.1
            )

            def _value_card_html(rank, row, max_win, max_t10, edge=None):
                """Return HTML for a single Value Picks player card."""
                name_raw = str(row.get('player_name', ''))
                if ', ' in name_raw:
                    _p = name_raw.split(', ', 1)
                    name_display = f"{_p[1]} {_p[0]}"
                else:
                    name_display = name_raw

                win_pct = float(row.get('win_prob', 0) or 0) * 100
                t10_pct = float(row.get('top10_prob', 0) or 0) * 100
                t20_pct = float(row.get('top20_prob', 0) or 0) * 100
                wr_raw  = row.get('world_rank')
                sg_raw  = row.get('sg_total')
                vsf_raw = row.get('projected_score_vs_field')
                odds_raw = row.get('odds_to_win')

                win_bar = min(100, (win_pct / (max_win * 100) * 100)) if max_win > 0 else 0
                t10_bar = min(100, (t10_pct / (max_t10 * 100) * 100)) if max_t10 > 0 else 0

                wr_str  = f"WR #{int(wr_raw)}" if pd.notna(wr_raw) and float(wr_raw) < 400 else ""
                sg_str  = f"{float(sg_raw):+.2f}" if pd.notna(sg_raw) else "—"
                sg_col  = "#00c44f" if pd.notna(sg_raw) and float(sg_raw) > 0 else ("#e74c3c" if pd.notna(sg_raw) and float(sg_raw) < 0 else "#8ba0b8")

                if pd.notna(vsf_raw):
                    _v = float(vsf_raw)
                    vsf_str = "E" if _v == 0 else (f"+{_v:.1f}" if _v > 0 else f"{_v:.1f}")
                    vsf_col = "#e74c3c" if _v > 0 else ("#8ba0b8" if _v == 0 else "#00c44f")
                else:
                    vsf_str, vsf_col = "—", "#8ba0b8"

                odds_str = f"{int(odds_raw):+d}" if pd.notna(odds_raw) and odds_raw != 0 else ""

                edge_badge = ""
                if edge is not None and pd.notna(edge):
                    _e = float(edge)
                    edge_col = "#00c44f" if _e >= 5 else ("#f39c12" if _e >= 2 else "#8ba0b8")
                    edge_badge = f'<span style="background:{edge_col}22;color:{edge_col};font-size:0.8em;font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap;">+{_e:.1f}pp edge</span>'

                wr_html   = f'<span style="color:#8ba0b8;font-size:0.8em;white-space:nowrap;">{wr_str}</span>' if wr_str else '<span></span>'
                odds_html = f'<span style="font-size:0.78em;color:#8ba0b8;">Odds <span style="color:#dde6f5;font-weight:600;">{odds_str}</span></span>' if odds_str else ''
                t20_html  = f'<span style="font-size:0.78em;color:#8ba0b8;">Top-20 <span style="color:#f39c12;font-weight:600;">{t20_pct:.0f}%</span></span>' if not edge_badge else ''

                return f"""
<div style="background:#0d1a30;border:1px solid #1e3a5f;border-radius:10px;padding:14px 16px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
    <span style="font-size:1.0em;font-weight:600;color:#dde6f5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;margin-right:8px;">{name_display}</span>
    {edge_badge or wr_html}
  </div>
  <div style="margin-bottom:8px;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
      <span style="color:#8ba0b8;font-size:0.75em;width:44px;flex-shrink:0;">Win</span>
      <div style="flex:1;background:#1a2537;border-radius:3px;height:5px;">
        <div style="width:{win_bar:.0f}%;background:#00c44f;border-radius:3px;height:5px;"></div>
      </div>
      <span style="color:#00c44f;font-size:0.85em;font-weight:700;width:40px;text-align:right;flex-shrink:0;">{win_pct:.1f}%</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="color:#8ba0b8;font-size:0.75em;width:44px;flex-shrink:0;">Top-10</span>
      <div style="flex:1;background:#1a2537;border-radius:3px;height:5px;">
        <div style="width:{t10_bar:.0f}%;background:#4cb8ff;border-radius:3px;height:5px;"></div>
      </div>
      <span style="color:#4cb8ff;font-size:0.85em;font-weight:700;width:40px;text-align:right;flex-shrink:0;">{t10_pct:.1f}%</span>
    </div>
  </div>
  <div style="display:flex;gap:14px;padding-top:8px;border-top:1px solid #1a2537;flex-wrap:wrap;">
    <span style="font-size:0.78em;color:#8ba0b8;">SG <span style="color:{sg_col};font-weight:600;">{sg_str}</span></span>
    <span style="font-size:0.78em;color:#8ba0b8;">vs Field <span style="color:{vsf_col};font-weight:600;">{vsf_str}</span></span>
    {odds_html}
    {t20_html}
  </div>
</div>"""

            if _has_edge:
                st.caption("Players where the model probability is meaningfully higher than the market's implied probability — sorted by edge.")
                _val_df["model_vs_vegas_edge"] = pd.to_numeric(_val_df["model_vs_vegas_edge"], errors="coerce")
                _val_df = _val_df[_val_df["model_vs_vegas_edge"].notna()]
                _val_df = _val_df.sort_values("model_vs_vegas_edge", ascending=False)

                _min_edge = st.slider("Minimum edge (%)", min_value=0, max_value=20, value=3, step=1, key="val_min_edge")
                _val_filtered = _val_df[_val_df["model_vs_vegas_edge"] >= _min_edge].head(12)

                if _val_filtered.empty:
                    st.info(f"No players with edge ≥ {_min_edge}%. Try lowering the threshold.")
                else:
                    _ve_max_win = float(_val_filtered['win_prob'].max() or 0.01)
                    _ve_max_t10 = float(_val_filtered['top10_prob'].max() or 0.01)
                    _ve_rows = list(_val_filtered.iterrows())
                    for _vi in range(0, len(_ve_rows), 2):
                        _vpair = _ve_rows[_vi:_vi+2]
                        _vcols = st.columns(2)
                        for _vgi, (_, _vrow) in enumerate(_vpair):
                            _vcols[_vgi].markdown(
                                _value_card_html(
                                    _vi + _vgi + 1, _vrow, _ve_max_win, _ve_max_t10,
                                    edge=_vrow.get('model_vs_vegas_edge')
                                ),
                                unsafe_allow_html=True
                            )
            else:
                # Fallback when odds aren't available: top picks by win probability
                st.caption("Odds data not yet available for this week — showing model's top picks by win probability.")
                _prob_col = "win_prob_calibrated" if "win_prob_calibrated" in _val_df.columns else "win_prob"
                _val_df[_prob_col] = pd.to_numeric(_val_df[_prob_col], errors="coerce")
                _fb_sorted = _val_df[_val_df[_prob_col].notna()].sort_values(_prob_col, ascending=False).head(12)

                _fb_max_win = float(_fb_sorted[_prob_col].max() or 0.01)
                _fb_max_t10 = float(_fb_sorted['top10_prob'].max() or 0.01) if 'top10_prob' in _fb_sorted.columns else 0.01
                _fb_rows = list(_fb_sorted.iterrows())
                for _fbi in range(0, len(_fb_rows), 2):
                    _fbpair = _fb_rows[_fbi:_fbi+2]
                    _fbcols = st.columns(2)
                    for _fbgi, (_, _fbrow) in enumerate(_fbpair):
                        _fbcols[_fbgi].markdown(
                            _value_card_html(_fbi + _fbgi + 1, _fbrow, _fb_max_win, _fb_max_t10),
                            unsafe_allow_html=True
                        )
                st.caption("Run odds refresh after the field is announced to see model vs market edge values.")


        # ── Augusta Fit tab (Masters only) ───────────────────────────────────
        if _has_augusta_data and tab5 is not None:
            with tab5:
                st.markdown("### Augusta National Composite Ranking")
                st.caption(
                    "Scores each player against the historical Masters elimination framework, "
                    "then ranks the qualified pool (5+/8) by a composite of Augusta history, "
                    "current ball-striking form, course experience, and driving distance."
                )

                st.markdown("""
<div style="background:#0d1a30;border:1px solid #1e3a5f;border-left:4px solid #c4a000;
            padding:14px 18px;border-radius:8px;margin:8px 0 16px 0;">
  <b style="color:#f0d060;">Composite Score = </b>
  <span style="color:#dde6f5;">Augusta avg to-par (30%) &nbsp;+&nbsp; SG T2G last 4 starts (25%) &nbsp;+&nbsp;
  Cut rate at Augusta (20%) &nbsp;+&nbsp; Driving distance rank (15%) &nbsp;+&nbsp; Model top-10 prob (10%)</span>
</div>""", unsafe_allow_html=True)

                _aug_min_q = st.slider(
                    "Minimum qualifier score (out of 8)",
                    min_value=0, max_value=8, value=5, step=1, key="aug_min_q"
                )

                _aug_disp = _aug_qual_df[_aug_qual_df["qualifier_score"] >= _aug_min_q].copy()

                if _aug_disp.empty:
                    st.info(f"No players with qualifier score >= {_aug_min_q}.")
                else:
                    def _aug_fmt_name(n):
                        s = str(n).strip()
                        if ", " in s:
                            p = s.split(", ", 1)
                            return f"{p[1]} {p[0]}"
                        return s

                    _aug_show = _aug_disp[[
                        "player_name", "qualifier_score",
                        "aug_composite", "aug_rank",
                        "augusta_avg_to_par", "sg_t2g_last4_total",
                        "augusta_cuts_made", "augusta_starts",
                        "driving_dist_field_rank",
                        "qualifiers_failed",
                    ]].copy()

                    _aug_show["player_name"] = _aug_show["player_name"].apply(_aug_fmt_name)
                    _aug_show["aug_rank"] = _aug_show["aug_rank"].astype(int)
                    _aug_show["qualifier_score"] = _aug_show["qualifier_score"].astype(int)
                    _aug_show["cut_rate"] = _aug_show.apply(
                        lambda r: f"{int(r['augusta_cuts_made'])}/{int(r['augusta_starts'])}"
                        if pd.notna(r["augusta_starts"]) and r["augusta_starts"] > 0 else "0/0", axis=1
                    )
                    _aug_show["driving_dist_field_rank"] = _aug_show["driving_dist_field_rank"].apply(
                        lambda x: f"T{int(x)}" if pd.notna(x) else "—"
                    )
                    _aug_show["augusta_avg_to_par"] = _aug_show["augusta_avg_to_par"].apply(
                        lambda x: f"{float(x):+.2f}" if pd.notna(x) else "N/A"
                    )
                    _aug_show["sg_t2g_last4_total"] = _aug_show["sg_t2g_last4_total"].apply(
                        lambda x: f"{float(x):+.2f}" if pd.notna(x) else "N/A"
                    )
                    # Clean up missing criteria display
                    _aug_show["qualifiers_failed"] = _aug_show["qualifiers_failed"].apply(
                        lambda x: "—" if str(x).strip().lower() in ("", "nan", "none") else str(x)
                    )

                    _aug_show = _aug_show[[
                        "aug_rank", "player_name", "qualifier_score", "aug_composite",
                        "augusta_avg_to_par", "sg_t2g_last4_total", "cut_rate",
                        "driving_dist_field_rank", "qualifiers_failed",
                    ]]
                    _aug_show.columns = [
                        "#", "Player", "Qual (8)", "Composite Score",
                        "Augusta Avg", "SG T2G (L4)", "Cut Rate",
                        "Dist Rank", "Missing Criteria",
                    ]

                    st.dataframe(
                        _aug_show,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Composite Score": st.column_config.NumberColumn(format="%.3f"),
                        },
                    )
                    st.caption(
                        f"Showing {len(_aug_show)} players with qualifier score >= {_aug_min_q}. "
                        "**Augusta Avg** — career strokes-per-round vs par at Augusta (negative = under par). "
                        "**SG T2G (L4)** — strokes gained tee-to-green summed over last 4 starts. "
                        "**Cut Rate** — cuts made / starts at Augusta. **Dist Rank** — driving distance rank in current field."
                    )

                    # Best pick callout
                    _best_aug = _aug_disp[_aug_disp["qualifier_score"] >= 5]
                    if not _best_aug.empty:
                        _top_aug = _best_aug.iloc[0]
                        _top_aug_name  = _aug_fmt_name(str(_top_aug["player_name"]))
                        _top_aug_qs    = int(_top_aug["qualifier_score"])
                        _top_aug_avg   = float(_top_aug["augusta_avg_to_par"])
                        _top_aug_t2g   = float(_top_aug["sg_t2g_last4_total"])
                        _top_aug_cuts  = int(_top_aug["augusta_cuts_made"])
                        _top_aug_strt  = int(_top_aug["augusta_starts"])
                        _top_aug_comp  = float(_top_aug["aug_composite"])
                        st.markdown(f"""
<div style="background:#0d2e18;border:1px solid #00c44f;border-left:4px solid #00c44f;
            padding:14px 18px;border-radius:8px;margin:12px 0 4px 0;">
  <b style="color:#00c44f;">Best Positioned: {_top_aug_name}</b>
  <span style="color:#8ba0b8;font-size:0.9em;">&nbsp;({_top_aug_qs}/8 qualifiers &middot; composite {_top_aug_comp:.3f})</span><br>
  <span style="color:#dde6f5;font-size:0.9em;">
    Augusta avg: <b>{_top_aug_avg:+.2f}</b> &nbsp;&middot;&nbsp;
    SG T2G last 4: <b>{_top_aug_t2g:+.2f}</b> &nbsp;&middot;&nbsp;
    Cuts made: <b>{_top_aug_cuts}/{_top_aug_strt}</b>
  </span>
</div>""", unsafe_allow_html=True)


# ============================================================================
# PAGE: LIVE
# ============================================================================

elif page == "🔴 Live":

    # ── AUTO-REFRESH while a round is in progress ──────────────────────────
    _LIVE_AUTO_SECS = 120  # re-read files every 2 minutes
    if "live_auto_refresh_at" not in st.session_state:
        st.session_state.live_auto_refresh_at = time.time() + _LIVE_AUTO_SECS
    if "live_paused" not in st.session_state:
        st.session_state.live_paused = False

    _ar_col, _pause_col = st.columns([9, 1])
    with _pause_col:
        _pause_label = "▶ Resume" if st.session_state.live_paused else "⏸ Pause"
        if st.button(_pause_label, key="live_pause_btn", use_container_width=True):
            st.session_state.live_paused = not st.session_state.live_paused
            st.session_state.live_auto_refresh_at = time.time() + _LIVE_AUTO_SECS

    if not st.session_state.live_paused:
        _secs_left = int(st.session_state.live_auto_refresh_at - time.time())
        if _secs_left <= 0:
            st.session_state.live_auto_refresh_at = time.time() + _LIVE_AUTO_SECS
            st.cache_data.clear()
            st.rerun()
        _min_left, _sec_left = divmod(max(_secs_left, 0), 60)
        with _ar_col:
            st.caption(f"Auto-refresh in {_min_left}m {_sec_left:02d}s · background scraper updates data every 15 min during active rounds")
    else:
        with _ar_col:
            st.caption("Auto-refresh paused · background scraper still running every 15 min")

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
                for _pc in ["player_1", "player_2", "player_3"]:
                    if _pc in _r and pd.notna(_r[_pc]) and str(_r[_pc]).strip():
                        _picks_this_week.append(str(_r[_pc]).strip())
        except Exception:
            pass

    # Store picks in session state so render_live_vs_predictions can access them
    st.session_state["_live_picks_this_week"] = _picks_this_week

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
    _live_meta_for_picks: dict = {}
    if _live_dir.exists():
        _meta_candidates = sorted(
            _live_dir.glob("leaderboard_*_meta.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if _meta_candidates:
            try:
                with open(_meta_candidates[0]) as _mf:
                    _live_meta_for_picks = json.load(_mf)
                _cut_proj_score    = _live_meta_for_picks.get("cut_projection", {}).get("projected_cut_score")
                _current_round_live = int(_live_meta_for_picks.get("current_round", 1))
            except Exception:
                pass

    # Tournament context line above pick cards
    if _live_meta_for_picks:
        import re as _re_ctx
        _ctx_tname = _live_meta_for_picks.get("tournament_name", "")
        if _re_ctx.match(r'^R\d+$', str(_ctx_tname)):
            _sched_path_ctx = DATA_DIR / "raw" / "schedule_2026.csv"
            if _sched_path_ctx.exists():
                try:
                    _sdf_ctx = pd.read_csv(_sched_path_ctx)
                    _sm_ctx  = _sdf_ctx[_sdf_ctx["tournament_id"] == _ctx_tname]
                    if not _sm_ctx.empty:
                        _ctx_tname = _sm_ctx.iloc[0]["tournament_name"]
                except Exception:
                    pass
        _ctx_round  = _live_meta_for_picks.get("current_round", "?")
        _ctx_status = str(_live_meta_for_picks.get("round_status", "")).lower()
        _ctx_live   = "progress" in _ctx_status or (_ctx_status.startswith("r") and _ctx_status[1:].isdigit())
        _ctx_dot    = "🟢" if _ctx_live else "⚪"
        if _ctx_tname:
            st.caption(f"{_ctx_dot} {_ctx_tname}  ·  Round {_ctx_round} of 4")

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
                        f'<div style="background:#0b1929;border:1px solid #1a3050;'
                        f'border-top:3px solid {_border_color};border-radius:12px;'
                        f'padding:18px 16px 14px;box-sizing:border-box;">'
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:center;margin-bottom:10px;">'
                        f'<span style="background:#132840;color:#dde6f5;font-size:13px;'
                        f'font-weight:800;padding:3px 11px;border-radius:20px;">{_pos}</span>'
                        f'<span style="font-size:12px;font-weight:700;color:{_move_color};">{_move_str}</span>'
                        f'</div>'
                        f'<div style="font-size:15px;font-weight:700;color:#e8eef8;margin-bottom:10px;'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_pname}</div>'
                        f'<div style="margin-bottom:8px;">'
                        f'<span style="font-size:40px;font-weight:900;color:{_score_color};line-height:1;">{_total}</span>'
                        f'<span style="font-size:12px;color:#5a7a9a;margin-left:8px;">Thru {_thru}</span>'
                        f'</div>'
                        + _cut_badge_html +
                        f'<div style="border-top:1px solid #1a3050;margin-top:12px;padding-top:10px;'
                        f'display:grid;grid-template-columns:repeat(4,1fr);gap:4px;text-align:center;">'
                        + _rnd_cells +
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Picks not found in leaderboard yet — try refreshing live data first.")
    elif not _picks_this_week:
        st.info("No picks for this week yet. Enter them on the fantasy site, then sync in My Picks.")
    elif _lb_df.empty:
        st.info("No live leaderboard data found. Run the leaderboard scraper from ⚙️  Pipeline.")

    st.markdown("---")

    # Load leaderboard data first
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(LIVE_DIR.glob("leaderboard_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)

    # Schedule lookup helper (for resolving R-prefixed IDs)
    import re as _re_live
    _sched_map_live: dict = {}
    _sched_path_live = DATA_DIR / "raw" / "schedule_2026.csv"
    if _sched_path_live.exists():
        try:
            _sdf_live = pd.read_csv(_sched_path_live)
            for _, _sr in _sdf_live.iterrows():
                _sched_map_live[str(_sr.get("tournament_id", ""))] = str(_sr.get("tournament_name", ""))
        except Exception:
            pass

    def _resolve_tourney_name(raw_name: str) -> str:
        if _re_live.match(r'^R\d+$', str(raw_name)):
            return _sched_map_live.get(raw_name, raw_name)
        return raw_name

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
                    name = _resolve_tourney_name(meta.get("tournament_name", name))
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
        "🏆 My Lineup",
        "📈 Live Stats",
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

    if False:  # vs Market Odds removed — see Betting → Odds Movement for full live odds drift
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

        else:
            st.info("Load leaderboard data first")

    with tab3:
        if live_df is not None:
            render_fantasy_lineup_tracker(live_df, live_meta)
        else:
            st.info("Load leaderboard data first")

    with tab4:
        _live_stats_tid = live_meta.get("tournament_id") if live_meta else None
        _course_stats_path = LIVE_DIR / f"course_stats_{_live_stats_tid}.json" if _live_stats_tid else None

        _subtab_probs, _subtab_dg = st.tabs(["🎯 Live Probs", "🏌️ DG Live SG"])


        if False:  # PGA Tour SG stats removed — replaced by DG Live SG tab
            if False:
    
                _ls_fetched   = _ls.get("fetched_at", "")[:16].replace("T", " ")
                _ls_round     = _ls.get("current_round", "?")
                _ls_rounds    = _ls.get("rounds_fetched", [])
                _ls_pmap      = _ls.get("player_map", {})
                _ls_cats      = _ls.get("categories", {})
                _ls_pids      = _ls.get("player_ids", [])
                _rnd_label    = f"through R{max(_ls_rounds, key=int)}" if _ls_rounds else f"R{_ls_round}"
    
                st.markdown(f"### Live Tournament Stats — {_rnd_label}")
                st.caption(
                    f"Cumulative strokes gained vs field — matches PGA Tour website. "
                    f"Data as of {_ls_fetched} UTC. "
                    f"Rounds: {', '.join('R'+r for r in sorted(_ls_rounds, key=int)) if _ls_rounds else '—'}"
                )
    
                # ── Category selector ────────────────────────────────────────────
                _cat_options = {
                    "Strokes Gained":  "STROKES_GAINED",
                    "Scoring":         "SCORING",
                    "Driving":         "OFF_TEE",
                    "Approach":        "APPROACH_GREEN",
                    "Short Game":      "AROUND_GREEN",
                    "Putting":         "PUTTING",
                }
                _selected_cat_label = st.selectbox(
                    "Category", list(_cat_options.keys()), key="live_stats_cat"
                )
                _selected_cat = _cat_options[_selected_cat_label]
    
                _cat_data = _ls_cats.get(_selected_cat, {})
                _cumul    = _cat_data.get("cumulative", {})
                _per_rnd  = _cat_data.get("per_round",  {})
    
                # ── SCORING category: integer counts with leaders summary ────
                if _selected_cat == "SCORING" and _cumul:
                    def _sc_int(pid, key):
                        try:
                            return int(float(_cumul[pid].get(key, {}).get("value", 0)))
                        except (TypeError, ValueError):
                            return 0
                    def _sc_rank(pid, key):
                        try:
                            return int(_cumul[pid].get(key, {}).get("rank", 0))
                        except (TypeError, ValueError):
                            return 0

                    _sc_rows = []
                    for _pid in _ls_pids:
                        if _pid not in _cumul:
                            continue
                        _lb_row = live_df[live_df["player_id"].astype(str) == _pid] if live_df is not None else None
                        _pos    = _lb_row["position"].iloc[0] if _lb_row is not None and not _lb_row.empty else "—"
                        _total  = _lb_row["total"].iloc[0]    if _lb_row is not None and not _lb_row.empty else "—"
                        _name   = _ls_pmap.get(_pid, _pid)
                        _b  = _sc_int(_pid, "Birdies")
                        _e  = _sc_int(_pid, "Eagles")
                        _bo = _sc_int(_pid, "Bogeys")
                        _d  = _sc_int(_pid, "Double Bogeys")
                        _p  = _sc_int(_pid, "Pars")
                        _br = _sc_rank(_pid, "Birdies")
                        _bor = _sc_rank(_pid, "Bogeys")
                        # Net = each eagle saves 2 vs par, each birdie 1, each bogey -1, dbl -2
                        _net = _e * 2 + _b - _bo - _d * 2
                        _sc_rows.append({
                            "Pos": _pos, "Player": _name, "Score": _total,
                            "Birdies": _b, "B#": _br,
                            "Eagles": _e,
                            "Bogeys": _bo, "Bo#": _bor,
                            "Dbl+": _d,
                            "Net": _net,
                        })

                    if _sc_rows:
                        _sc_df = pd.DataFrame(_sc_rows)

                        # ── Leader summary cards ─────────────────────────────────
                        _col_b, _col_e, _col_bf = st.columns(3)
                        with _col_b:
                            st.markdown("**Birdie Leaders**")
                            for _, _r in _sc_df.nlargest(5, "Birdies")[["Player", "Birdies", "B#"]].iterrows():
                                _rk = f" (#{int(_r['B#'])})" if _r["B#"] else ""
                                st.markdown(f"- {_r['Player']}: **{_r['Birdies']}**{_rk}")
                        with _col_e:
                            st.markdown("**Eagle Leaders**")
                            _eagles_df = _sc_df[_sc_df["Eagles"] > 0].nlargest(5, "Eagles")[["Player", "Eagles"]]
                            if _eagles_df.empty:
                                st.markdown("*No eagles yet*")
                            else:
                                for _, _r in _eagles_df.iterrows():
                                    st.markdown(f"- {_r['Player']}: **{_r['Eagles']}**")
                        with _col_bf:
                            st.markdown("**Bogey-Free**")
                            _bf_df = _sc_df[_sc_df["Bogeys"] == 0].nlargest(5, "Birdies")[["Player", "Birdies"]]
                            if _bf_df.empty:
                                st.markdown("*None yet*")
                            else:
                                for _, _r in _bf_df.iterrows():
                                    st.markdown(f"- {_r['Player']}: {_r['Birdies']}B")

                        st.markdown("---")

                        # ── Full scoring table ───────────────────────────────────
                        _display_sc = _sc_df.drop(columns=["B#", "Bo#"])

                        def _color_scoring(val, col):
                            try:
                                v = int(val)
                                if col == "Birdies":
                                    if v >= 6: return "color:#00c44f; font-weight:600"
                                    if v >= 3: return "color:#81c784"
                                elif col == "Eagles":
                                    if v >= 1: return "color:#ffd700; font-weight:600"
                                elif col == "Bogeys":
                                    if v == 0: return "color:#00c44f"
                                    if v >= 4: return "color:#e53935; font-weight:600"
                                    if v >= 2: return "color:#ef9a9a"
                                elif col == "Dbl+":
                                    if v >= 2: return "color:#e53935; font-weight:600"
                                    if v == 1: return "color:#ef9a9a"
                                elif col == "Net":
                                    if v >= 4:  return "color:#00c44f; font-weight:600"
                                    if v >= 1:  return "color:#81c784"
                                    if v < 0:   return "color:#ef9a9a"
                                    if v <= -2: return "color:#e53935; font-weight:600"
                            except (TypeError, ValueError):
                                pass
                            return ""

                        _styled_sc = _display_sc.style
                        for _sc_col in ["Birdies", "Eagles", "Bogeys", "Dbl+", "Net"]:
                            if _sc_col in _display_sc.columns:
                                _styled_sc = _styled_sc.map(
                                    lambda v, c=_sc_col: _color_scoring(v, c), subset=[_sc_col]
                                )
                        st.dataframe(_styled_sc, hide_index=True, use_container_width=True)

                        # ── Per-round scoring breakdown ──────────────────────────
                        if _per_rnd and len(_ls_rounds) > 1:
                            st.markdown("---")
                            st.markdown("**Round-by-round scoring breakdown**")
                            _player_opts_sc = [_ls_pmap.get(p, p) for p in _ls_pids if p in _cumul]
                            _sel_player_sc  = st.selectbox("Select player", _player_opts_sc, key="live_scoring_player")
                            _sel_pid_sc = next((p for p in _ls_pids if _ls_pmap.get(p, p) == _sel_player_sc), None)
                            if _sel_pid_sc:
                                _sc_rnd_rows = []
                                for _rn in sorted(_ls_rounds, key=int):
                                    _rnd_d = _per_rnd.get(_rn, {}).get(_sel_pid_sc, {})
                                    if not _rnd_d:
                                        continue
                                    def _gvr(key, _d=_rnd_d):
                                        try:
                                            return int(float(_d.get(key, {}).get("value", 0)))
                                        except (TypeError, ValueError):
                                            return 0
                                    _rb = _gvr("Birdies"); _re = _gvr("Eagles")
                                    _rbo = _gvr("Bogeys"); _rd = _gvr("Double Bogeys")
                                    _sc_rnd_rows.append({
                                        "Round": f"R{_rn}",
                                        "Birdies": _rb, "Eagles": _re,
                                        "Bogeys": _rbo, "Dbl+": _rd,
                                        "Net": _re*2 + _rb - _rbo - _rd*2,
                                    })
                                if _sc_rnd_rows:
                                    _sc_rnd_df = pd.DataFrame(_sc_rnd_rows)
                                    _sc_rnd_styled = _sc_rnd_df.style
                                    for _sc_col in ["Birdies", "Eagles", "Bogeys", "Dbl+", "Net"]:
                                        if _sc_col in _sc_rnd_df.columns:
                                            _sc_rnd_styled = _sc_rnd_styled.map(
                                                lambda v, c=_sc_col: _color_scoring(v, c), subset=[_sc_col]
                                            )
                                    st.dataframe(_sc_rnd_styled, hide_index=True, use_container_width=True)
                    else:
                        st.info("No scoring data available yet.")

                # ── All other categories (SG, driving, etc.): +.3f format ────
                elif _cumul:
                    _sample_pid  = next((p for p in _ls_pids if p in _cumul), None)
                    _stat_names  = list(_cumul[_sample_pid].keys()) if _sample_pid else []

                    _rows = []
                    for _pid in _ls_pids:
                        if _pid not in _cumul:
                            continue
                        _lb_row = live_df[live_df["player_id"].astype(str) == _pid] if live_df is not None else None
                        _pos    = _lb_row["position"].iloc[0] if _lb_row is not None and not _lb_row.empty else "—"
                        _total  = _lb_row["total"].iloc[0]    if _lb_row is not None and not _lb_row.empty else "—"
                        _name   = _ls_pmap.get(_pid, _pid)
                        _row    = {"Pos": _pos, "Player": _name, "Score": _total}

                        for _sn in _stat_names:
                            _entry = _cumul[_pid].get(_sn, {})
                            try:
                                _v = float(_entry.get("value", 0))
                                _r = _entry.get("rank", "")
                                _row[_sn] = f"{_v:+.3f} (#{_r})" if _r else f"{_v:+.3f}"
                            except (TypeError, ValueError):
                                _row[_sn] = "—"
                        _rows.append(_row)

                    if _rows:
                        _stats_display = pd.DataFrame(_rows)

                        def _color_sg(val):
                            if not isinstance(val, str) or val == "—":
                                return ""
                            try:
                                v = float(val.split(" ")[0])
                                if v >= 2.0:   return "color:#00c44f; font-weight:600"
                                if v >= 0.5:   return "color:#81c784"
                                if v <= -0.5:  return "color:#ef9a9a"
                                if v <= -2.0:  return "color:#e53935; font-weight:600"
                            except Exception:
                                pass
                            return ""

                        _sg_cols = [c for c in _stats_display.columns if c not in ("Pos", "Player", "Score")]
                        _styled  = _stats_display.style.map(_color_sg, subset=_sg_cols)
                        st.dataframe(_styled, hide_index=True, use_container_width=True)

                        if _per_rnd and len(_ls_rounds) > 1:
                            st.markdown("---")
                            st.markdown("**Round-by-round breakdown**")
                            _player_options = [_ls_pmap.get(p, p) for p in _ls_pids if p in _cumul]
                            _sel_player_name = st.selectbox(
                                "Select player", _player_options, key="live_stats_player"
                            )
                            _sel_pid = next(
                                (p for p in _ls_pids if _ls_pmap.get(p, p) == _sel_player_name), None
                            )
                            if _sel_pid:
                                _rnd_rows = []
                                for _rn in sorted(_ls_rounds, key=int):
                                    _rnd_data = _per_rnd.get(_rn, {}).get(_sel_pid, {})
                                    if not _rnd_data:
                                        continue
                                    _rrow = {"Round": f"R{_rn}"}
                                    for _sn in _stat_names:
                                        _e = _rnd_data.get(_sn, {})
                                        try:
                                            _v = float(_e.get("value", 0))
                                            _r = _e.get("rank", "")
                                            _rrow[_sn] = f"{_v:+.3f} (#{_r})" if _r else f"{_v:+.3f}"
                                        except (TypeError, ValueError):
                                            _rrow[_sn] = "—"
                                    _rnd_rows.append(_rrow)
                                if _rnd_rows:
                                    _rnd_df = pd.DataFrame(_rnd_rows)
                                    st.dataframe(
                                        _rnd_df.style.map(_color_sg, subset=[c for c in _rnd_df.columns if c != "Round"]),
                                        hide_index=True,
                                        use_container_width=True,
                                    )
                    pass

        # ── DG Live Probs subtab ──────────────────────────────────────────────
        with _subtab_probs:
            @st.cache_data(ttl=180, show_spinner=False)
            def _fetch_dg_inplay() -> dict:
                import sys as _sys
                _sys.path.insert(0, str(PROJECT_ROOT))
                from scripts.scrapers.dg_client import dg_get as _dg_get
                return _dg_get("/preds/in-play", {"tour": "pga", "dead_heat": "yes", "odds_format": "percent"})

            _prob_c1, _prob_c2 = st.columns([5, 1])
            with _prob_c2:
                st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
                if st.button("Refresh", key="dg_probs_refresh"):
                    _fetch_dg_inplay.clear()
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            try:
                _ip_raw   = _fetch_dg_inplay()
                _ip_info  = _ip_raw.get("info", {})
                _ip_rows  = _ip_raw.get("data", [])
                _ip_event = _ip_info.get("event_name", "RBC Heritage") if _ip_info else ""
                _ip_round = _ip_info.get("current_round", "") if _ip_info else ""
                _ip_updated = _ip_info.get("last_updated", "") if _ip_info else ""

                with _prob_c1:
                    st.caption(f"DataGolf in-play model · {_ip_event} · R{_ip_round} · Updated: {_ip_updated} UTC · auto-refreshes every 3 min")

                if _ip_rows:
                    def _ip_fl(name):
                        if "," in str(name):
                            _pt = str(name).split(",", 1)
                            return f"{_pt[1].strip()} {_pt[0].strip()}"
                        return str(name)

                    _ip_pick_keys = {n.lower().strip() for n in (_picks_this_week or [])}

                    _ip_data = []
                    for _p in _ip_rows:
                        _pname = _ip_fl(_p.get("player_name", ""))
                        _is_pick = _pname.lower().strip() in _ip_pick_keys
                        _win  = _p.get("win")
                        _t5   = _p.get("top_5")
                        _t10  = _p.get("top_10")
                        _t20  = _p.get("top_20")
                        _cut  = _p.get("make_cut")
                        _ip_data.append({
                            "Player":   ("★ " if _is_pick else "") + _pname,
                            "Pos":      _p.get("current_pos", "—"),
                            "Score":    _p.get("current_score"),
                            "Today":    _p.get("today"),
                            "Thru":     _p.get("thru"),
                            "R1":       _p.get("R1"),
                            "R2":       _p.get("R2"),
                            "Win%":     round(_win * 100, 1) if _win is not None else None,
                            "Top5%":    round(_t5  * 100, 1) if _t5  is not None else None,
                            "Top10%":   round(_t10 * 100, 1) if _t10 is not None else None,
                            "Top20%":   round(_t20 * 100, 1) if _t20 is not None else None,
                            "Cut%":     round(_cut  * 100, 1) if _cut  is not None else None,
                            "_is_pick": _is_pick,
                            "_win_raw": _win or 0,
                        })

                    _ip_df = (
                        pd.DataFrame(_ip_data)
                        .sort_values("_win_raw", ascending=False, na_position="last")
                        .reset_index(drop=True)
                    )

                    # ── Pick summary cards ──
                    _ip_picks = _ip_df[_ip_df["_is_pick"]]
                    if not _ip_picks.empty:
                        st.markdown("**My picks — live win probabilities**")
                        _ipc = st.columns(max(len(_ip_picks), 1))
                        for _ci, (_, _pr) in enumerate(_ip_picks.iterrows()):
                            _win_pct = _pr.get("Win%")
                            _t10_pct = _pr.get("Top10%")
                            _win_str = f"{_win_pct:.1f}%" if _win_pct is not None else "—"
                            _t10_str = f"{_t10_pct:.1f}%" if _t10_pct is not None else "—"
                            _win_col = "#00c44f" if (_win_pct or 0) >= 10 else ("#ffa726" if (_win_pct or 0) >= 5 else "#dde6f5")
                            _score_raw = _pr.get("Score")
                            _score_str = (f"{int(_score_raw):+d}" if _score_raw and _score_raw != 0 else "E") if _score_raw is not None else "—"
                            _name = str(_pr.get("Player","")).replace("★ ","")
                            _ipc[_ci].markdown(
                                f"<div style='background:#0d1a2e;border:1px solid #1e3a5f;"
                                f"border-top:3px solid #4cb8ff;border-radius:8px;padding:12px 14px;text-align:center'>"
                                f"<div style='color:#4cb8ff;font-size:11px;font-weight:700;letter-spacing:.5px'>★ {_name.upper()}</div>"
                                f"<div style='font-size:26px;font-weight:900;color:#eee;line-height:1.1;margin:6px 0'>{_score_str}</div>"
                                f"<div style='font-size:12px;color:#888;margin-bottom:8px'>{_pr.get('Pos','—')} · thru {_pr.get('Thru','—')}</div>"
                                f"<div style='display:flex;justify-content:space-around'>"
                                f"<div><div style='font-size:18px;font-weight:800;color:{_win_col}'>{_win_str}</div>"
                                f"<div style='font-size:10px;color:#666'>WIN</div></div>"
                                f"<div><div style='font-size:18px;font-weight:800;color:#81c784'>{_t10_str}</div>"
                                f"<div style='font-size:10px;color:#666'>TOP 10</div></div>"
                                f"</div></div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown("")

                    # ── Full table with column config ──
                    _ip_display = _ip_df.drop(columns=["_is_pick", "_win_raw"])
                    _ip_prob_cols = [c for c in ["Win%", "Top5%", "Top10%", "Top20%", "Cut%"] if c in _ip_display.columns]

                    def _style_prob_row(row):
                        if str(row.get("Player","")).startswith("★"):
                            return ["background-color:#0d2e40"] * len(row)
                        return [""] * len(row)

                    def _style_win(val):
                        try:
                            v = float(val)
                            if v >= 15:  return "color:#00c44f; font-weight:800"
                            if v >= 8:   return "color:#81c784; font-weight:700"
                            if v >= 3:   return "color:#ccc"
                            return "color:#555"
                        except Exception:
                            return ""

                    def _style_t10(val):
                        try:
                            v = float(val)
                            if v >= 50:  return "color:#00c44f; font-weight:700"
                            if v >= 25:  return "color:#81c784"
                            if v >= 10:  return "color:#ccc"
                            return "color:#555"
                        except Exception:
                            return ""

                    _ip_styled = (
                        _ip_display.style
                        .apply(_style_prob_row, axis=1)
                        .map(_style_win, subset=["Win%"])
                        .map(_style_t10, subset=["Top10%"])
                    )
                    st.dataframe(
                        _ip_styled,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Player":  st.column_config.TextColumn("Player",  width="medium"),
                            "Pos":     st.column_config.TextColumn("Pos",     width="small"),
                            "Score":   st.column_config.NumberColumn("Score", format="%d", width="small"),
                            "Today":   st.column_config.NumberColumn("Today", format="%+d", width="small"),
                            "Thru":    st.column_config.NumberColumn("Thru",  format="%d",  width="small"),
                            "R1":      st.column_config.NumberColumn("R1",    format="%d",  width="small"),
                            "R2":      st.column_config.NumberColumn("R2",    format="%d",  width="small"),
                            "Win%":    st.column_config.NumberColumn("Win%",  format="%.1f%%", width="small"),
                            "Top5%":   st.column_config.NumberColumn("Top5%", format="%.1f%%", width="small"),
                            "Top10%":  st.column_config.NumberColumn("Top10%",format="%.1f%%", width="small"),
                            "Top20%":  st.column_config.NumberColumn("Top20%",format="%.1f%%", width="small"),
                            "Cut%":    st.column_config.NumberColumn("Cut%",  format="%.1f%%", width="small"),
                        },
                    )
                else:
                    st.info("No in-play data — tournament may not have started yet.")

            except Exception as _ip_err:
                st.warning(f"DG in-play API error: {_ip_err}")

        # ── DG Live SG subtab — direct API call ───────────────────────────────
        with _subtab_dg:
            _DG_ALL_STATS = "sg_putt,sg_arg,sg_app,sg_ott,sg_t2g,sg_total,driving_dist,driving_acc,gir,scrambling,prox_fw,prox_rgh"
            _DG_OPTIONAL = {
                "SG Total": "sg_total", "OTT": "sg_ott", "APP": "sg_app",
                "ARG": "sg_arg", "PUTT": "sg_putt", "T2G": "sg_t2g",
                "GIR%": "gir", "Scrambling%": "scrambling",
                "Prox FW": "prox_fw", "Prox RGH": "prox_rgh",
            }

            @st.cache_data(ttl=300, show_spinner=False)
            def _fetch_dg_live_api(round_param: str) -> dict:
                import sys as _sys
                _sys.path.insert(0, str(PROJECT_ROOT))
                from scripts.scrapers.dg_client import dg_get as _dg_get
                return _dg_get("/preds/live-tournament-stats", {
                    "tour": "pga", "stats": _DG_ALL_STATS,
                    "round": round_param, "display": "value",
                })

            # ── Controls bar ──
            _dg_c1, _dg_c2, _dg_c3 = st.columns([1, 3, 1])
            with _dg_c1:
                _dg_round_choice = st.selectbox(
                    "Round", ["event_avg", "1", "2", "3", "4"],
                    key="dg_live_round_sel", help="event_avg = full-tournament cumulative",
                )
            with _dg_c2:
                _dg_col_choices = st.multiselect(
                    "Columns", options=list(_DG_OPTIONAL.keys()),
                    default=["SG Total", "OTT", "APP", "ARG", "PUTT"],
                    key="dg_live_cols",
                )
            with _dg_c3:
                st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
                if st.button("Refresh", key="dg_live_refresh"):
                    _fetch_dg_live_api.clear()
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            try:
                _dg_data    = _fetch_dg_live_api(_dg_round_choice)
                _dg_event   = _dg_data.get("event_name", "")
                _dg_updated = _dg_data.get("last_updated", "")
                _dg_players = _dg_data.get("live_stats", [])

                st.caption(f"DataGolf · {_dg_event} · Round: {_dg_round_choice} · Updated: {_dg_updated} UTC · auto-refreshes every 5 min")

                if _dg_players:
                    def _dg_fl(name):
                        if "," in str(name):
                            _pt = str(name).split(",", 1)
                            return f"{_pt[1].strip()} {_pt[0].strip()}"
                        return str(name)

                    def _fv(val, pct=False, feet=False):
                        if val is None: return None
                        try:
                            v = float(val)
                            if pct:  return round(v * 100, 1)
                            if feet: return round(v, 1)
                            return round(v, 2)
                        except (TypeError, ValueError):
                            return None

                    _dg_pick_keys = {n.lower().strip() for n in (_picks_this_week or [])}

                    _dg_rows = []
                    for _p in _dg_players:
                        _pname = _dg_fl(_p.get("player_name", ""))
                        _is_pick = _pname.lower().strip() in _dg_pick_keys
                        _sg_tot = _fv(_p.get("sg_total"))
                        _dg_rows.append({
                            "Player":      ("★ " if _is_pick else "") + _pname,
                            "Pos":         _p.get("position"),
                            "Score":       _p.get("total"),
                            "Thru":        _p.get("thru"),
                            "_is_pick":    _is_pick,
                            "_name_raw":   _pname,
                            "SG Total":    _sg_tot,
                            "OTT":         _fv(_p.get("sg_ott")),
                            "APP":         _fv(_p.get("sg_app")),
                            "ARG":         _fv(_p.get("sg_arg")),
                            "PUTT":        _fv(_p.get("sg_putt")),
                            "T2G":         _fv(_p.get("sg_t2g")),
                            "GIR%":        _fv(_p.get("gir"), pct=True),
                            "Scrambling%": _fv(_p.get("scrambling"), pct=True),
                            "Prox FW":     _fv(_p.get("prox_fw"), feet=True),
                            "Prox RGH":    _fv(_p.get("prox_rgh"), feet=True),
                        })

                    _dg_all = pd.DataFrame(_dg_rows)
                    _dg_sorted = _dg_all.sort_values("SG Total", ascending=False, na_position="last").reset_index(drop=True)

                    # ── My picks cards ────────────────────────────────────────
                    _my_pick_rows = _dg_sorted[_dg_sorted["_is_pick"]]
                    if not _my_pick_rows.empty:
                        st.markdown("**My picks**")
                        _pick_cols = st.columns(max(len(_my_pick_rows), 1))
                        for _ci, (_, _pr) in enumerate(_my_pick_rows.iterrows()):
                            _sg   = _pr.get("SG Total")
                            _sg_str   = f"{float(_sg):+.2f}" if _sg is not None else "—"
                            _sg_color = "#00c44f" if (_sg or 0) >= 0 else "#ef5350"
                            _score = str(_pr.get("Score", "—"))
                            _pos   = str(_pr.get("Pos", "—"))
                            _thru  = str(_pr.get("Thru", "—"))
                            _name  = str(_pr.get("_name_raw", "")).strip()
                            _pick_cols[_ci].markdown(
                                f"<div style='background:#0d1a2e;border:1px solid #1e3a5f;"
                                f"border-top:3px solid #4cb8ff;border-radius:8px;padding:12px 14px;text-align:center'>"
                                f"<div style='color:#4cb8ff;font-size:11px;font-weight:700;letter-spacing:.5px'>★ {_name.upper()}</div>"
                                f"<div style='font-size:28px;font-weight:900;color:#eee;line-height:1.1;margin:6px 0'>{_score}</div>"
                                f"<div style='font-size:12px;color:#888;margin-bottom:6px'>{_pos} · thru {_thru}</div>"
                                f"<div style='font-size:15px;font-weight:700;color:{_sg_color}'>SG {_sg_str}</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown("")

                    # ── Gainers / Losers strip ────────────────────────────────
                    _valid_sg = _dg_sorted.dropna(subset=["SG Total"])
                    if len(_valid_sg) >= 6:
                        _gainers = _valid_sg.head(3)
                        _losers  = _valid_sg.tail(3).iloc[::-1]

                        _gl_left, _gl_right = st.columns(2)

                        def _gl_card(col, rows, label, color, icon):
                            cards_html = ""
                            for _, _r in rows.iterrows():
                                _sg = _r["SG Total"]
                                _n  = str(_r["_name_raw"])
                                _p  = str(_r["Pos"])
                                cards_html += (
                                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                                    f"padding:6px 10px;border-bottom:1px solid #111'>"
                                    f"<span style='color:#dde6f5;font-size:13px'>{_n}</span>"
                                    f"<span style='color:#888;font-size:11px'>{_p}</span>"
                                    f"<span style='color:{color};font-weight:700;font-size:13px'>{_sg:+.2f}</span>"
                                    f"</div>"
                                )
                            col.markdown(
                                f"<div style='background:#0b1929;border:1px solid #1a3050;border-radius:8px;overflow:hidden'>"
                                f"<div style='background:#0d2035;padding:7px 10px;font-size:11px;font-weight:700;"
                                f"color:{color};letter-spacing:.5px'>{icon} {label}</div>"
                                f"{cards_html}</div>",
                                unsafe_allow_html=True,
                            )

                        with _gl_left:
                            _gl_card(st, _gainers, "TOP GAINERS", "#00c44f", "▲")
                        with _gl_right:
                            _gl_card(st, _losers,  "BOTTOM LOSERS", "#ef5350", "▼")
                        st.markdown("")

                    # ── My picks SG breakdown chart ───────────────────────────
                    if not _my_pick_rows.empty and len(_dg_col_choices) > 0:
                        import plotly.graph_objects as _pgo
                        _sg_bar_cats = [c for c in ["OTT", "APP", "ARG", "PUTT"] if c in _dg_all.columns]
                        if _sg_bar_cats:
                            _bar_colors = ["#4cb8ff", "#00c44f", "#ffa726"]
                            _fig_picks = _pgo.Figure()
                            for _bi, (_, _pr) in enumerate(_my_pick_rows.iterrows()):
                                _bar_vals = [_pr.get(c) for c in _sg_bar_cats]
                                _fig_picks.add_trace(_pgo.Bar(
                                    name=str(_pr.get("_name_raw", f"Pick {_bi+1}")).split()[-1],
                                    x=_sg_bar_cats,
                                    y=_bar_vals,
                                    marker_color=_bar_colors[_bi % len(_bar_colors)],
                                    text=[f"{v:+.2f}" if v is not None else "" for v in _bar_vals],
                                    textposition="outside",
                                ))
                            _fig_picks.update_layout(
                                barmode="group",
                                title="My Picks — SG Breakdown",
                                height=300,
                                margin=dict(t=40, b=30, l=30, r=20),
                                plot_bgcolor="rgba(0,0,0,0)",
                                paper_bgcolor="rgba(0,0,0,0)",
                                yaxis=dict(zeroline=True, zerolinecolor="#444", gridcolor="#222", title="SG vs Field"),
                                font=dict(color="#ddd", size=12),
                                legend=dict(orientation="h", y=-0.15),
                            )
                            st.plotly_chart(_fig_picks, use_container_width=True)

                    # ── Full sortable table ───────────────────────────────────
                    _sort_col = "SG Total" if "SG Total" in _dg_col_choices else (_dg_col_choices[0] if _dg_col_choices else "SG Total")
                    _dg_show  = (
                        _dg_all[["Player", "Pos", "Score", "Thru", "_is_pick"] + [c for c in _dg_col_choices if c in _dg_all.columns]]
                        .sort_values(_sort_col, ascending=False, na_position="last")
                        .reset_index(drop=True)
                    )
                    _dg_display = _dg_show.drop(columns=["_is_pick"])
                    _sg_style_cols = [c for c in _dg_col_choices if c in ("SG Total","OTT","APP","ARG","PUTT","T2G")]

                    def _style_sg(val):
                        try:
                            v = float(val)
                            if v >= 1.5:  return "color:#00c44f; font-weight:700"
                            if v >= 0.5:  return "color:#81c784"
                            if v >= 0.0:  return "color:#ccc"
                            if v >= -0.5: return "color:#ef9a9a"
                            return "color:#ef5350; font-weight:700"
                        except Exception:
                            return ""

                    def _style_pick_row(row):
                        if str(row.get("Player", "")).startswith("★"):
                            return ["background-color:#0d2e40"] * len(row)
                        return [""] * len(row)

                    _dg_styled = _dg_display.style.apply(_style_pick_row, axis=1)
                    if _sg_style_cols:
                        _dg_styled = _dg_styled.map(_style_sg, subset=_sg_style_cols)
                    st.dataframe(
                        _dg_styled,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Player":      st.column_config.TextColumn("Player",      width="medium"),
                            "Pos":         st.column_config.TextColumn("Pos",         width="small"),
                            "Score":       st.column_config.TextColumn("Score",       width="small"),
                            "Thru":        st.column_config.NumberColumn("Thru",      format="%d",   width="small"),
                            "SG Total":    st.column_config.NumberColumn("SG Tot",    format="%+.2f", width="small"),
                            "OTT":         st.column_config.NumberColumn("OTT",       format="%+.2f", width="small"),
                            "APP":         st.column_config.NumberColumn("APP",       format="%+.2f", width="small"),
                            "ARG":         st.column_config.NumberColumn("ARG",       format="%+.2f", width="small"),
                            "PUTT":        st.column_config.NumberColumn("PUTT",      format="%+.2f", width="small"),
                            "T2G":         st.column_config.NumberColumn("T2G",       format="%+.2f", width="small"),
                            "GIR%":        st.column_config.NumberColumn("GIR%",      format="%.1f%%", width="small"),
                            "Scrambling%": st.column_config.NumberColumn("Scram%",    format="%.1f%%", width="small"),
                            "Prox FW":     st.column_config.NumberColumn("Prox FW",   format="%.1f'", width="small"),
                            "Prox RGH":    st.column_config.NumberColumn("Prox RGH",  format="%.1f'", width="small"),
                        },
                    )

                else:
                    st.info("No player data returned from DG API — tournament may not have started yet.")

            except Exception as _dg_err:
                st.warning(f"DG API error: {_dg_err}")


# =============================================================================
# PAGE: PIPELINE CONTROL
# =============================================================================
elif page == "⚙️ Pipeline":
    _OWNER_PIN = "winetime"
    if "pipeline_unlocked" not in st.session_state:
        st.session_state["pipeline_unlocked"] = False

    if not st.session_state["pipeline_unlocked"]:
        st.markdown("## ⚙️ Pipeline Control")
        with st.form("pipeline_pin_form", clear_on_submit=True):
            _pin_input = st.text_input("Enter PIN to access pipeline:", type="password", key="pipeline_pin_input")
            _pin_submit = st.form_submit_button("Unlock")
        if _pin_submit:
            if _pin_input == _OWNER_PIN:
                st.session_state["pipeline_unlocked"] = True
                st.rerun()
            else:
                st.error("Incorrect PIN.")
        st.stop()

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
                        ("Past Results", ["python3", "scripts/scrapers/fetch_past_results.py",
                                          "--tournament-id", tournament_id, "--years-back", "10"]),
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
                    # ── Most recent run health banner ─────────────────────
                    last = history[-1]
                    last_ts      = last.get("timestamp", "")[:16].replace("T", " ")
                    last_sched   = last.get("schedule", "")
                    last_ok      = last.get("success_count", 0)
                    last_total   = last.get("total_count", 0)
                    last_failed  = last.get("failed_tasks", [
                        r["task"] for r in last.get("results", []) if not r.get("success")
                    ])
                    if last_ok == last_total:
                        st.success(f"Last run: **{last_sched}** at {last_ts} — all {last_total} tasks passed")
                    else:
                        st.error(
                            f"Last run: **{last_sched}** at {last_ts} — "
                            f"{last_ok}/{last_total} passed  |  "
                            f"**Failed:** {', '.join(last_failed) if last_failed else 'see details below'}"
                        )

                    # ── Last 10 runs table ────────────────────────────────
                    st.markdown("**Recent Runs:**")
                    recent = history[-10:]
                    for entry in reversed(recent):
                        ts      = entry.get("timestamp", "")[:16].replace("T", " ")
                        sched   = entry.get("schedule", "")
                        ok      = entry.get("success_count", 0)
                        total   = entry.get("total_count", 0)
                        failed  = entry.get("failed_tasks", [
                            r["task"] for r in entry.get("results", []) if not r.get("success")
                        ])
                        if ok == total:
                            st.caption(f"✓ {ts} — {sched}: {ok}/{total}")
                        else:
                            fail_str = ", ".join(failed[:3]) + (f" +{len(failed)-3}" if len(failed) > 3 else "")
                            st.caption(f"✗ {ts} — {sched}: {ok}/{total}  |  failed: {fail_str}")
                else:
                    st.info("No scheduler history yet")
            except Exception:
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
