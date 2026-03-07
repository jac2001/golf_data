"""
Golf chat assistant — context builder + Groq streaming response.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Iterator

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"
OUTPUTS = PROJECT_ROOT / "outputs"


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _detect_tournament_id() -> str | None:
    """Auto-detect active tournament ID.

    Priority:
    1. tournament_id column in latest_predictions.csv
    2. tournament_id in recommended_bets_latest.csv (tied to current week's odds run)
    3. Meta JSON with a non-Official round status (still in progress)
    4. Most recently modified meta JSON file (mtime, not filename sort)
    """
    # 1. Predictions CSV
    preds_path = OUTPUTS / "latest_predictions.csv"
    if preds_path.exists():
        try:
            df = pd.read_csv(preds_path, usecols=lambda c: c in ("tournament_id",), nrows=5)
            if "tournament_id" in df.columns and not df.empty:
                return str(df["tournament_id"].mode().iloc[0])
        except Exception:
            pass

    # 2. Recommended bets — most reliable current-week indicator
    bets_path = DATA / "odds" / "recommended_bets_latest.csv"
    if bets_path.exists():
        try:
            df = pd.read_csv(bets_path, usecols=["tournament_id"], nrows=5)
            if not df.empty:
                return str(df["tournament_id"].mode().iloc[0])
        except Exception:
            pass

    meta_files = glob.glob(str(DATA / "live" / "leaderboard_r*_meta.json"))
    if not meta_files:
        return None

    # 3. Prefer a meta file whose round_status is not "Official" (active tournament)
    for mf in meta_files:
        try:
            with open(mf) as f:
                meta = json.load(f)
            if str(meta.get("round_status", "")).lower() != "official":
                return meta.get("tournament_id")
        except Exception:
            pass

    # 4. Most recently modified meta file
    meta_files.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(meta_files[0]) as f:
            return json.load(f).get("tournament_id")
    except Exception:
        pass
    return None


def _predictions_block(top_n: int = 20) -> str:
    """Top N players by win probability from latest_predictions.csv."""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df.sort_values("win_prob", ascending=False).head(top_n)

        cols = ["player_name", "win_prob", "top10_prob", "odds_to_win",
                "projected_score_vs_field", "form_trend", "course_perf_score"]
        live_cols = ["live_win_prob", "live_win_prob_change"]
        for c in live_cols:
            if c in df.columns:
                cols.append(c)

        df = df[[c for c in cols if c in df.columns]].copy()
        df["win_prob"] = (df["win_prob"] * 100).round(1).astype(str) + "%"
        df["top10_prob"] = (df["top10_prob"] * 100).round(1).astype(str) + "%"
        if "live_win_prob" in df.columns:
            df["live_win_prob"] = (df["live_win_prob"] * 100).round(1).astype(str) + "%"
        if "live_win_prob_change" in df.columns:
            df["live_win_prob_change"] = (df["live_win_prob_change"] * 100).round(1).astype(str) + "pp"
        if "projected_score_vs_field" in df.columns:
            df["projected_score_vs_field"] = df["projected_score_vs_field"].round(2)
        if "course_perf_score" in df.columns:
            df["course_perf_score"] = df["course_perf_score"].round(2)

        df.columns = [c.replace("_", " ").title() for c in df.columns]
        return "## MODEL TOP 20 (by win probability)\n" + df.to_markdown(index=False)
    except Exception as e:
        return f"## MODEL TOP 20\n(unavailable: {e})"


def _live_leaderboard_block(tid: str) -> str:
    """Live leaderboard top 20. Only shown if at least 1 round is complete."""
    if not tid:
        return ""
    tid_lower = tid.lower()
    path = DATA / "live" / f"leaderboard_{tid_lower}.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        if df.empty:
            return ""

        # Detect rounds completed
        meta_path = DATA / "live" / f"leaderboard_{tid_lower}_meta.json"
        rounds_complete = 0
        cut_info = ""
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                rounds_complete = int(meta.get("current_round", 0))
                cp = meta.get("cut_projection", {})
                if cp:
                    cut_score = cp.get("projected_cut_score", "?")
                    bubble = cp.get("bubble_count", "?")
                    cut_info = f"\n\n## CUT PROJECTION: {cut_score:+d} | {bubble} players on bubble" if isinstance(cut_score, int) else f"\n\n## CUT PROJECTION: {cut_score} | {bubble} players on bubble"
            except Exception:
                pass

        if rounds_complete == 0:
            return cut_info

        cols = ["position", "player_name", "total", "thru", "current_round"]
        preds_path = OUTPUTS / "latest_predictions.csv"
        if preds_path.exists():
            try:
                preds = pd.read_csv(preds_path, usecols=["player_name", "live_win_prob", "win_prob"])
                df = df.merge(preds, on="player_name", how="left")
                df["live_win%"] = (df["live_win_prob"] * 100).round(1).astype(str) + "%"
                df["pre_win%"] = (df["win_prob"] * 100).round(1).astype(str) + "%"
                cols += ["live_win%", "pre_win%"]
            except Exception:
                pass

        df = df.head(20)[[c for c in cols if c in df.columns]].copy()
        df.columns = [c.replace("_", " ").title() for c in df.columns]

        header = f"## LIVE LEADERBOARD — Round {rounds_complete} of 4 complete"
        return header + "\n" + df.to_markdown(index=False) + cut_info
    except Exception as e:
        return f"## LIVE LEADERBOARD\n(unavailable: {e})"


def _recommended_bets_block(top_n: int = 10) -> str:
    """Top recommended bets by edge."""
    path = DATA / "odds" / "recommended_bets_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df[df["status"] == "priced"].copy() if "status" in df.columns else df
        df = df.sort_values("edge_pts", ascending=False).head(top_n)

        cols = ["market", "player_name", "book", "odds_american",
                "edge_pts", "model_prob", "ev_per_1", "confidence"]
        df = df[[c for c in cols if c in df.columns]].copy()
        if "edge_pts" in df.columns:
            df["edge_pts"] = df["edge_pts"].round(1)
        if "model_prob" in df.columns:
            df["model_prob"] = (df["model_prob"] * 100).round(1).astype(str) + "%"
        if "ev_per_1" in df.columns:
            df["ev_per_1"] = df["ev_per_1"].round(3)

        df.columns = [c.replace("_", " ").title() for c in df.columns]
        return "## TOP RECOMMENDED BETS\n" + df.to_markdown(index=False)
    except Exception as e:
        return f"## TOP RECOMMENDED BETS\n(unavailable: {e})"


def _expert_picks_block() -> str:
    """Expert consensus winner picks."""
    path = DATA / "expert_picks" / "expert_picks_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        if df.empty:
            return ""
        lines = ["## EXPERT CONSENSUS"]
        for _, row in df.iterrows():
            expert = row.get("expert_name", "?")
            winner = row.get("winner_name", "?")
            comment = str(row.get("comment", "")).strip()
            short_comment = comment[:120] + "…" if len(comment) > 120 else comment
            lines.append(f"- **{expert}** → {winner}: {short_comment}")
        return "\n".join(lines)
    except Exception as e:
        return f"## EXPERT CONSENSUS\n(unavailable: {e})"


def _my_picks_block() -> str:
    """Current week picks + remaining uses from usage tracker."""
    path = DATA / "fantasy" / "usage_tracker_2026.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)

        # Current week lineup
        weekly = data.get("weekly_lineups", {})
        current_week = None
        if weekly:
            current_week = weekly[max(weekly.keys())]

        # Uses remaining per player
        picks = data.get("picks", {})
        max_uses = int(data.get("max_uses_per_player", 3))

        lines = ["## MY PICKS THIS WEEK"]
        if current_week:
            lineup = current_week.get("lineup", [])
            tournament = current_week.get("tournament", "")
            lines.append(f"**Week {current_week.get('week', '?')} lineup — {tournament}**: {', '.join(lineup)}")

        lines.append("\n**Uses remaining per player (season):**")
        for player, info in picks.items():
            remaining = info.get("remaining_uses", max_uses - info.get("times_used", 0))
            if remaining < max_uses:  # Only show players already used
                lines.append(f"- {player}: {remaining} use(s) remaining")

        return "\n".join(lines)
    except Exception as e:
        return f"## MY PICKS THIS WEEK\n(unavailable: {e})"


def _tournament_header(tid: str) -> str:
    """Tournament name, course, and metadata from meta JSON."""
    if not tid:
        return ""
    tid_lower = tid.lower()
    meta_path = DATA / "live" / f"leaderboard_{tid_lower}_meta.json"
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            name = meta.get("tournament_name", tid)
            return f"## TOURNAMENT: {name} | {tid}"
        except Exception:
            pass
    return f"## TOURNAMENT: {tid}"


def build_context(tournament_id: str | None = None) -> str:
    """Build full system prompt context string from all data sources."""
    if tournament_id is None:
        tournament_id = _detect_tournament_id()

    sections = [
        "You are an expert golf analytics assistant with access to current tournament data.",
        "Your role: help the user make lineup decisions, evaluate betting edges, analyze player form, and explain live tournament developments.",
        "Always ground your responses in the provided data. Cite specific numbers (win probabilities, odds, strokes gained).",
        "When model and market odds disagree significantly (edge > 15 percentage points), highlight it.",
        "",
    ]

    if tournament_id:
        sections.append(_tournament_header(tournament_id))
        sections.append("")

    sections.append(_predictions_block())
    sections.append("")

    if tournament_id:
        live = _live_leaderboard_block(tournament_id)
        if live:
            sections.append(live)
            sections.append("")

    bets = _recommended_bets_block()
    if bets:
        sections.append(bets)
        sections.append("")

    experts = _expert_picks_block()
    if experts:
        sections.append(experts)
        sections.append("")

    my_picks = _my_picks_block()
    if my_picks:
        sections.append(my_picks)
        sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Groq streaming
# ---------------------------------------------------------------------------

def stream_response(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream a response from Groq llama-3.3-70b-versatile."""
    from groq import Groq

    client = Groq(api_key=api_key)
    stream = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        stream=True,
        temperature=0.3,
        max_tokens=1500,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta
