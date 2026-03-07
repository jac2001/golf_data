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

def _fmt_odds(odds) -> str:
    """Format American odds as +1300 or -110."""
    try:
        o = int(float(odds))
        return f"+{o}" if o > 0 else str(o)
    except (TypeError, ValueError):
        return "—"


def _fmt_course_history(row) -> str:
    """Compact course history: '5 starts · 3 T10s · 2 wins' or 'No history'."""
    starts = int(row.get("hist_times_played", 0) or 0)
    if starts == 0:
        return "No history"
    top10s = int(row.get("hist_top10s", 0) or 0)
    wins   = int(row.get("hist_wins", 0) or 0)
    parts  = [f"{starts} starts", f"{top10s} T10s"]
    if wins:
        parts.append(f"{wins} win{'s' if wins > 1 else ''}")
    return " · ".join(parts)


def _predictions_block(top_n: int = 20) -> str:
    """Top N players ranked by win probability, in user-friendly terms.

    Columns: Player, Win Odds, World Rank, Top 10%, Top 5%,
             Course History, SG Total, SG OTT, SG APP, SG Putt,
             Live Position (if tournament is live).
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df.sort_values("win_prob", ascending=False).head(top_n).copy()
        df["player_name"] = df["player_name"].apply(_fmt_name)

        # Build output frame with plain-English columns
        out = pd.DataFrame()
        out["Player"]       = df["player_name"]

        # Win Odds + implied % together so value comparisons are explicit
        def _odds_with_implied(odds):
            o = _fmt_odds(odds)
            imp = _american_to_implied(odds)
            if imp is not None:
                return f"{o} ({imp*100:.0f}% implied)"
            return o
        out["Win Odds (Implied%)"] = df["odds_to_win"].apply(_odds_with_implied)

        # Est. Win% — clearly labelled as our estimate, for value play comparisons
        out["Est. Win%"]    = (df["win_prob"] * 100).round(1).astype(str) + "%"
        out["World Rank"]   = df["world_rank"].apply(
            lambda x: f"#{int(x)}" if pd.notna(x) else "—"
        )
        out["Top 10%"]      = (df["top10_prob"] * 100).round(0).astype(int).astype(str) + "%"
        out["Top 5%"]       = (df["top5_prob"] * 100).round(0).astype(int).astype(str) + "%"
        out["Course History"] = df.apply(_fmt_course_history, axis=1)

        # Strokes Gained (season, signed vs field average)
        for sg_col, label in [
            ("sg_total", "SG Total"),
            ("sg_ott",   "SG OTT"),
            ("sg_app",   "SG APP"),
            ("sg_putt",  "SG Putt"),
        ]:
            if sg_col in df.columns:
                out[label] = df[sg_col].apply(
                    lambda x: f"{x:+.2f}" if pd.notna(x) else "—"
                )

        # Live position if available
        if "live_top10_prob" in df.columns:
            live_t10 = (df["live_top10_prob"] * 100).round(0).fillna(0).astype(int)
            out["Live T10%"] = live_t10.astype(str) + "%"

        note = (
            "IMPORTANT: Est. Win% is our win probability estimate — compare this to Implied% for value plays. "
            "Top 10% and Top 5% are finish probabilities — do NOT compare these to win odds. "
            "SG = Strokes Gained vs field average. OTT = off the tee, APP = approach, Putt = putting."
        )
        return "## FIELD OVERVIEW — Top 20 contenders\n" + note + "\n" + out.to_markdown(index=False)
    except Exception as e:
        return f"## FIELD OVERVIEW\n(unavailable: {e})"


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
    """Top recommended bets in plain-English terms."""
    path = DATA / "odds" / "recommended_bets_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df[df["status"] == "priced"].copy() if "status" in df.columns else df
        df = df.sort_values("edge_pts", ascending=False).head(top_n)

        out = pd.DataFrame()
        out["Market"]       = df["market"] if "market" in df.columns else "—"
        out["Player"]       = df["player_name"].apply(_fmt_name)
        out["Book"]         = df["book"] if "book" in df.columns else "—"
        out["Odds"]         = df["odds_american"].apply(
            lambda x: _fmt_odds(x) if pd.notna(x) else "—"
        )
        # Book implied % and model estimate — clearly scoped to the specific market
        if "book_prob" in df.columns:
            out["Book Says (this market)"] = (df["book_prob"] * 100).round(1).astype(str) + "%"
        if "model_prob" in df.columns:
            out["We Think (this market)"]  = (df["model_prob"] * 100).round(1).astype(str) + "%"
        if "ev_per_1" in df.columns:
            out["EV / $1"]   = df["ev_per_1"].round(2).apply(
                lambda x: f"+${x:.2f}" if x > 0 else f"-${abs(x):.2f}"
            )
        if "confidence" in df.columns:
            out["Confidence"] = df["confidence"].apply(
                lambda x: "High" if x >= 0.9 else ("Med" if x >= 0.7 else "Low")
            )

        note = (
            "Each row is a specific market (top20, top10, h2h, outright win). "
            "'Book Says' and 'We Think' apply to THAT market only — not to win probability. "
            "EV / $1 = expected profit per $1 wagered. Positive = good bet long-term."
        )
        return "## TOP BETS THIS WEEK\n" + note + "\n" + out.to_markdown(index=False)
    except Exception as e:
        return f"## TOP BETS THIS WEEK\n(unavailable: {e})"


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

    # --- Rival intel: which competitor teams are locked out of elite players ---
    if usage_path.exists():
        try:
            usage = pd.read_csv(usage_path)

            # Teams that have used a player all 3 times (locked out forever)
            locked = usage[usage["uses_left"] == 0].copy()
            if not locked.empty:
                # Group by player: list which rival teams can NEVER use them again
                locked_summary = (
                    locked[locked["team_name"] != MY_TEAM]
                    .groupby("player")["team_name"]
                    .apply(lambda teams: ", ".join(sorted(teams)))
                    .reset_index()
                    .rename(columns={"team_name": "locked_out_teams"})
                    .sort_values("player")
                )
                lines.append("\n**Rival teams locked out (used all 3x — can never use again):**")
                lines.append("This is competitive intel: if a rival can't use Scheffler/McIlroy at a major, that's a significant disadvantage for them.")
                lines.append(locked_summary.to_markdown(index=False))

            # My team's own usage history (YOUR uses — this is what matters for YOUR decisions)
            my_usage = usage[usage["team_name"] == MY_TEAM][["player", "times_used", "uses_left", "total_earned"]]
            if not my_usage.empty:
                lines.append(f"\n**{MY_TEAM} (your team) player use history — uses_left is what constrains YOUR picks:**")
                my_usage = my_usage.sort_values("times_used", ascending=False).copy()
                my_usage["total_earned"] = my_usage["total_earned"].apply(lambda x: f"${int(x):,}")
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
        "You are an expert golf analyst helping a user with fantasy lineup decisions, betting, and tournament analysis.",
        "Communicate like a knowledgeable golf fan talking to another fan — use plain English, not technical jargon.",
        "",
        "COMMUNICATION RULES:",
        "- Use American odds (+1300, +600) and plain finish percentages. Reference course history and strokes gained stats.",
        "- SG = Strokes Gained. Positive = better than field average, negative = worse. OTT = off the tee, APP = approach, Putt = putting.",
        "- Never say 'model output', 'implied probability', 'edge pp', 'projected score vs field', or 'win probability was X%'.",
        "- For pre-tournament expectations, say 'listed at +1300' or 'ranked #1 in the world' — not 'had a 21% win probability'.",
        "- EV / $1 = expected profit per dollar wagered. Positive = good bet long-term.",
        "- When discussing course fit, reference specific holes, yardage, and which SG categories matter.",
        "- For lineup advice, reference the user's uses remaining and league standing.",
        "",
        "VALUE PLAYS — CRITICAL RULE:",
        "- The field table has 'Est. Win%' and 'Win Odds (Implied%)'. To find value, compare Est. Win% to the Implied% in the odds.",
        "- Example: Est. Win% = 17%, Implied% = 6% → the odds undervalue this player for a WIN bet.",
        "- Top 10% and Top 5% measure finish placement — NEVER compare them to win odds. They are different markets.",
        "- For top 10 / top 20 value, use the BETS TABLE which shows 'Book Says' vs 'We Think' for that specific market.",
        "",
        "TOURNAMENT UPDATES — RULES:",
        "- 5+ strokes back with 1 round left is a very difficult deficit. Be realistic — don't call large gaps 'only X strokes'.",
        "- When noting who has outperformed or underperformed, say 'Scheffler was the favorite at +1300 but sits T15' — not probabilities.",
        "- Focus on actual tournament position, strokes to leader, and remaining holes.",
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
