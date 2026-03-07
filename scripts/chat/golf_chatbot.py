"""
Golf chat assistant — context builder + Groq streaming response.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"
OUTPUTS = PROJECT_ROOT / "outputs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_name(name: str) -> str:
    """Normalize 'Last, First' → 'First Last'. Pass-through otherwise."""
    s = str(name).strip()
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first} {last}"
    return s


def _american_to_implied(odds) -> float | None:
    """Convert American odds to implied probability (0–1)."""
    try:
        o = float(odds)
        if o > 0:
            return 100 / (o + 100)
        else:
            return abs(o) / (abs(o) + 100)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Tournament ID detection
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


# ---------------------------------------------------------------------------
# Context blocks
# ---------------------------------------------------------------------------

def _predictions_block(top_n: int = 20) -> str:
    """Top N players by win probability.

    Fix 1: names normalized to First Last.
    Fix 2: implied_prob% column derived from DK American odds.
    Fix 3: edge_pp column = model win% − implied win% (positive = model favors player).
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df.sort_values("win_prob", ascending=False).head(top_n).copy()

        # Fix 1: normalize player names
        df["player_name"] = df["player_name"].apply(_fmt_name)

        # Fix 2: implied probability from market odds
        df["implied_prob"] = df["odds_to_win"].apply(_american_to_implied)

        # Fix 3: model vs market edge (in percentage points)
        df["edge_pp"] = ((df["win_prob"] - df["implied_prob"]) * 100).round(1)

        # Select and format columns
        cols = ["player_name", "win_prob", "implied_prob", "edge_pp",
                "top10_prob", "odds_to_win", "projected_score_vs_field",
                "form_trend", "course_perf_score"]
        live_cols = ["live_win_prob", "live_win_prob_change"]
        for c in live_cols:
            if c in df.columns:
                cols.append(c)

        df = df[[c for c in cols if c in df.columns]].copy()

        df["win_prob"]    = (df["win_prob"] * 100).round(1).astype(str) + "%"
        df["implied_prob"] = df["implied_prob"].apply(
            lambda x: f"{x*100:.1f}%" if x is not None else "—"
        )
        df["top10_prob"]  = (df["top10_prob"] * 100).round(1).astype(str) + "%"
        df["edge_pp"]     = df["edge_pp"].apply(
            lambda x: f"+{x:.1f}pp" if x > 0 else f"{x:.1f}pp" if pd.notna(x) else "—"
        )
        if "live_win_prob" in df.columns:
            df["live_win_prob"] = (df["live_win_prob"] * 100).round(1).astype(str) + "%"
        if "live_win_prob_change" in df.columns:
            df["live_win_prob_change"] = (df["live_win_prob_change"] * 100).round(1).astype(str) + "pp"
        if "projected_score_vs_field" in df.columns:
            df["projected_score_vs_field"] = df["projected_score_vs_field"].round(2)
        if "course_perf_score" in df.columns:
            df["course_perf_score"] = df["course_perf_score"].round(2)

        df.columns = [c.replace("_", " ").title() for c in df.columns]
        note = "(Edge Pp = model win% minus market implied%; positive means model likes player more than market)"
        return "## MODEL TOP 20 (by win probability)\n" + note + "\n" + df.to_markdown(index=False)
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

        meta_path = DATA / "live" / f"leaderboard_{tid_lower}_meta.json"
        rounds_complete = 0
        round_status = ""
        cut_info = ""
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                rounds_complete = int(meta.get("current_round", 0))
                round_status = meta.get("round_status", "")
                cp = meta.get("cut_projection", {})
                if cp:
                    cut_score = cp.get("projected_cut_score", "?")
                    bubble = cp.get("bubble_count", "?")
                    cut_info = (
                        f"\n\n## CUT PROJECTION: {cut_score:+d} | {bubble} players on bubble"
                        if isinstance(cut_score, int)
                        else f"\n\n## CUT PROJECTION: {cut_score} | {bubble} players on bubble"
                    )
            except Exception:
                pass

        if rounds_complete == 0:
            return cut_info

        # Normalize names in leaderboard for merge
        df["player_name"] = df["player_name"].apply(_fmt_name)

        cols = ["position", "player_name", "total", "thru", "current_round"]
        preds_path = OUTPUTS / "latest_predictions.csv"
        if preds_path.exists():
            try:
                preds = pd.read_csv(preds_path, usecols=["player_name", "live_win_prob", "win_prob"])
                preds["player_name"] = preds["player_name"].apply(_fmt_name)
                df = df.merge(preds, on="player_name", how="left")
                df["live_win%"] = (df["live_win_prob"] * 100).round(1).astype(str) + "%"
                df["pre_win%"]  = (df["win_prob"] * 100).round(1).astype(str) + "%"
                cols += ["live_win%", "pre_win%"]
            except Exception:
                pass

        df = df.head(20)[[c for c in cols if c in df.columns]].copy()
        df.columns = [c.replace("_", " ").title() for c in df.columns]

        status_label = f" — {round_status}" if round_status else ""
        header = f"## LIVE LEADERBOARD — Round {rounds_complete} of 4{status_label}"
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
        df["player_name"] = df["player_name"].apply(_fmt_name)
        if "edge_pts" in df.columns:
            df["edge_pts"] = df["edge_pts"].round(1).astype(str) + "pp"
        if "model_prob" in df.columns:
            df["model_prob"] = (df["model_prob"] * 100).round(1).astype(str) + "%"
        if "ev_per_1" in df.columns:
            df["ev_per_1"] = df["ev_per_1"].round(3)

        df.columns = [c.replace("_", " ").title() for c in df.columns]
        return "## TOP RECOMMENDED BETS\n" + df.to_markdown(index=False)
    except Exception as e:
        return f"## TOP RECOMMENDED BETS\n(unavailable: {e})"


def _course_profile_block(tid: str) -> str:
    """Course context from hole-level and summary profile CSVs.

    Reads data/course_characteristics/r{tid}_{year}.csv (per-hole) and
    r{tid}_{year}_profiles.csv (summary). Emits course facts and the 3
    hardest / 3 easiest holes so the model can reason about course fit.
    """
    if not tid:
        return ""
    tid_lower = tid.lower()
    year = datetime.now().year

    hole_path    = DATA / "course_characteristics" / f"{tid_lower}_{year}.csv"
    profile_path = DATA / "course_characteristics" / f"{tid_lower}_{year}_profiles.csv"

    lines = []

    # Summary stats
    if profile_path.exists():
        try:
            p = pd.read_csv(profile_path).iloc[0]
            course  = p.get("course_name", "")
            par     = int(p.get("course_par", 72))
            yardage = p.get("course_yardage", "")
            scoring = float(p.get("total_scoring_avg", 0))
            birdie  = float(p.get("birdie_pct", 0))
            bogey   = float(p.get("bogey_pct", 0))
            p3      = int(p.get("par3_count", 0))
            p4      = int(p.get("par4_count", 0))
            p5      = int(p.get("par5_count", 0))

            lines.append(f"## COURSE PROFILE: {course}")
            lines.append(
                f"Par {par} | {yardage} yards | Layout: {p3} par-3s, {p4} par-4s, {p5} par-5s"
            )
            lines.append(
                f"Field scoring avg: {scoring:.3f} (par+{scoring-par:.3f}) | "
                f"Birdie rate: {birdie:.1f}% | Bogey rate: {bogey:.1f}%"
            )
        except Exception as e:
            lines.append(f"## COURSE PROFILE\n(summary unavailable: {e})")

    # Per-hole difficulty
    if hole_path.exists():
        try:
            h = pd.read_csv(hole_path).sort_values("difficulty_rank")
            hardest = h.head(3)
            easiest = h.tail(3).sort_values("difficulty_rank", ascending=False)

            def _hole_str(row) -> str:
                return (
                    f"  Hole {int(row['hole_num'])} "
                    f"(Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): "
                    f"avg {row['scoring_avg']:.3f} "
                    f"({row['scoring_diff']:+.3f} vs par)"
                )

            lines.append("\nHardest holes (by scoring average vs par):")
            for _, r in hardest.iterrows():
                lines.append(_hole_str(r))

            lines.append("\nEasiest holes (birdie opportunities):")
            for _, r in easiest.iterrows():
                lines.append(_hole_str(r))
        except Exception as e:
            lines.append(f"(hole-level data unavailable: {e})")

    return "\n".join(lines) if lines else ""


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
            winner = _fmt_name(str(row.get("winner_name", "?")))
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

        weekly = data.get("weekly_lineups", {})
        current_week = weekly[max(weekly.keys())] if weekly else None
        picks = data.get("picks", {})
        max_uses = int(data.get("max_uses_per_player", 3))

        lines = ["## MY PICKS THIS WEEK"]
        if current_week:
            lineup = current_week.get("lineup", [])
            tournament = current_week.get("tournament", "")
            lines.append(
                f"**Week {current_week.get('week', '?')} lineup — {tournament}**: "
                + ", ".join(lineup)
            )

        lines.append("\n**Season uses remaining:**")
        for player, info in picks.items():
            remaining = info.get("remaining_uses", max_uses - info.get("times_used", 0))
            if remaining < max_uses:
                lines.append(f"- {player}: {remaining} use(s) remaining")

        return "\n".join(lines)
    except Exception as e:
        return f"## MY PICKS THIS WEEK\n(unavailable: {e})"


def _league_context_block() -> str:
    """League standings, current week picks, and player ownership across all 28 teams.

    Reads:
      data/fantasy/league_standings.csv     — season standings
      data/fantasy/league_weekly_picks.csv  — this week's picks + earnings per team
      data/fantasy/league_player_usage.csv  — all-time usage per player per team
    """
    standings_path = DATA / "fantasy" / "league_standings.csv"
    weekly_path    = DATA / "fantasy" / "league_weekly_picks.csv"
    usage_path     = DATA / "fantasy" / "league_player_usage.csv"

    if not standings_path.exists():
        return ""

    lines = ["## LEAGUE CONTEXT (Louisiana/Delaware Connection — 28 teams, max 3 uses/player)"]

    MY_TEAM = "WineTime"

    # --- Season standings (top 5 + WineTime) ---
    try:
        standings = pd.read_csv(standings_path)
        my_row = standings[standings["team_name"] == MY_TEAM]
        my_place = my_row["place"].iloc[0] if not my_row.empty else "?"
        my_earnings = my_row["earnings"].iloc[0] if not my_row.empty else "?"
        my_back = my_row["earnings_back"].iloc[0] if not my_row.empty else "?"

        lines.append(f"\n**Season Standings — {MY_TEAM} is {my_place} | {my_earnings} | {my_back} back**")
        top5 = standings.head(5)[["place", "team_name", "owner", "earnings", "earnings_back"]]
        lines.append(top5.to_markdown(index=False))
        if not my_row.empty and int(my_row.index[0]) >= 5:
            lines.append(f"...  {my_place} | {MY_TEAM} | {my_earnings} | {my_back} back")
    except Exception as e:
        lines.append(f"(standings unavailable: {e})")

    # --- Current week picks and results ---
    if weekly_path.exists():
        try:
            weekly = pd.read_csv(weekly_path)
            # Sort by total earnings desc
            weekly = weekly.sort_values("total_earnings", ascending=False).reset_index(drop=True)
            my_week = weekly[weekly["team_name"] == MY_TEAM]

            if not my_week.empty:
                r = my_week.iloc[0]
                lines.append(
                    f"\n**{MY_TEAM} this week (rank #{r['weekly_rank']}): "
                    f"{r['player_1']} ${r['earnings_1']:,} | "
                    f"{r['player_2']} ${r['earnings_2']:,} | "
                    f"{r['player_3']} ${r['earnings_3']:,} | "
                    f"Total ${r['total_earnings']:,}**"
                )

            lines.append("\n**Current week standings (all teams):**")
            display = weekly[["weekly_rank", "team_name", "player_1", "player_2", "player_3", "total_earnings"]].copy()
            display["total_earnings"] = display["total_earnings"].apply(lambda x: f"${x:,}")
            lines.append(display.to_markdown(index=False))

            # Player ownership this week
            all_picks = pd.concat([
                weekly[["player_1"]].rename(columns={"player_1": "player"}),
                weekly[["player_2"]].rename(columns={"player_2": "player"}),
                weekly[["player_3"]].rename(columns={"player_3": "player"}),
            ]).query("player != 'VACANT'")["player"].value_counts()

            lines.append("\n**Player ownership this week (# of teams):**")
            ownership_str = " | ".join(f"{p}: {c}" for p, c in all_picks.items())
            lines.append(ownership_str)

        except Exception as e:
            lines.append(f"(weekly picks unavailable: {e})")

    # --- Season-long usage: players with 2+ uses (running low) ---
    if usage_path.exists():
        try:
            usage = pd.read_csv(usage_path)
            # Players used 2 or 3 times by each team — shows who's getting depleted
            scarce = (
                usage[usage["times_used"] >= 2]
                .groupby("player")
                .agg(teams_used_twice=("team_name", "count"), avg_earned=("total_earned", "mean"))
                .sort_values("teams_used_twice", ascending=False)
                .head(12)
                .reset_index()
            )
            lines.append("\n**Players used 2+ times (scarcity alert — limited future availability):**")
            scarce["avg_earned"] = scarce["avg_earned"].apply(lambda x: f"${int(x):,}")
            lines.append(scarce.to_markdown(index=False))

            # My team's remaining uses
            my_usage = usage[usage["team_name"] == MY_TEAM][["player", "times_used", "uses_left", "total_earned"]]
            if not my_usage.empty:
                lines.append(f"\n**{MY_TEAM} player use history (season):**")
                my_usage = my_usage.sort_values("times_used", ascending=False)
                lines.append(my_usage.to_markdown(index=False))
        except Exception as e:
            lines.append(f"(usage data unavailable: {e})")

    return "\n".join(lines)


def _tournament_header(tid: str) -> str:
    """Tournament name from meta JSON."""
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


# ---------------------------------------------------------------------------
# Main context builder
# ---------------------------------------------------------------------------

def build_context(tournament_id: str | None = None) -> str:
    """Assemble full system prompt context from all data sources."""
    if tournament_id is None:
        tournament_id = _detect_tournament_id()

    sections = [
        "You are an expert golf analytics assistant with access to current tournament data.",
        "Your role: help the user make lineup decisions, evaluate betting edges, analyze player form, and explain live tournament developments.",
        "Always ground your responses in the provided data. Cite specific numbers (win probabilities, odds, strokes gained).",
        "When Edge Pp is positive and large (>10pp), the model strongly favors that player vs the market — highlight it.",
        "",
    ]

    if tournament_id:
        sections.append(_tournament_header(tournament_id))
        sections.append("")

    sections.append(_predictions_block())
    sections.append("")

    if tournament_id:
        course = _course_profile_block(tournament_id)
        if course:
            sections.append(course)
            sections.append("")

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

    league = _league_context_block()
    if league:
        sections.append(league)
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
