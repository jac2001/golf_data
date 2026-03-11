"""
Golf chat assistant — context builder + Groq streaming response.

Context is query-aware: the blocks included depend on what the user asked.
  - Player question  → player deep-dive + SG + odds movement
  - Bet question     → bets + odds movement + weather
  - Live question    → leaderboard + cut projection
  - Lineup question  → my picks + usage + predictions
  - Weather/course   → weather forecast + course profile
  - General          → full overview (default)
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timedelta
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


# ---------------------------------------------------------------------------
# Tournament ID detection
# ---------------------------------------------------------------------------

def _detect_tournament_id() -> str | None:
    """Auto-detect active tournament ID."""
    preds_path = OUTPUTS / "latest_predictions.csv"
    if preds_path.exists():
        try:
            df = pd.read_csv(preds_path, usecols=lambda c: c in ("tournament_id",), nrows=5)
            if "tournament_id" in df.columns and not df.empty:
                return str(df["tournament_id"].mode().iloc[0])
        except Exception:
            pass

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

    for mf in meta_files:
        try:
            with open(mf) as f:
                meta = json.load(f)
            if str(meta.get("round_status", "")).lower() != "official":
                return meta.get("tournament_id")
        except Exception:
            pass

    meta_files.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(meta_files[0]) as f:
            return json.load(f).get("tournament_id")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

def _extract_players(query: str) -> list[str]:
    """Find player names mentioned in the query. Returns list of formatted names."""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, usecols=["player_name"])
        q_lower = query.lower()
        matched = []
        for raw in df["player_name"]:
            name = _fmt_name(str(raw))
            parts = name.lower().split()
            # Match on last name (≥4 chars) appearing as a word in the query
            last = parts[-1] if parts else ""
            if len(last) >= 4 and last in q_lower:
                matched.append(name)
        return matched
    except Exception:
        return []


def _classify_query(query: str) -> dict:
    """Return intent flags from user query."""
    q = query.lower()
    players = _extract_players(q)
    return {
        "players":           players,
        "is_player":         bool(players),
        "is_bet":            any(w in q for w in ["bet", "wager", "odds", "value", "edge", "parlay", "prop", "book", "wager"]) or re.search(r'\bline\b', q) is not None,
        "is_live":           any(w in q for w in ["live", "leaderboard", "leading", "update", "score", "round", "cut", "leader", "current", "standing", "position"]),
        "is_lineup":         any(w in q for w in ["lineup", "pick", "use", "fantasy", "team", "build", "choose", "start", "who should", "draft"]),
        "is_weather":        any(w in q for w in ["weather", "wind", "rain", "forecast", "conditions", "temperature", "temp"]),
        "is_course":         any(w in q for w in ["course", "hole", "layout", "yardage", "field", "green", "fairway", "rough", "setup"]),
        "is_value":          any(w in q for w in ["value", "underdog", "long shot", "longshot", "undervalued", "sharp"]),
    }


# ---------------------------------------------------------------------------
# Context blocks
# ---------------------------------------------------------------------------

def _predictions_block(top_n: int = 15) -> str:
    """Top N players ranked by win probability."""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df.sort_values("win_prob", ascending=False).head(top_n).copy()
        df["player_name"] = df["player_name"].apply(_fmt_name)

        out = pd.DataFrame()
        out["Player"] = df["player_name"]

        def _odds_with_implied(odds):
            o = _fmt_odds(odds)
            imp = _american_to_implied(odds)
            if imp is not None:
                return f"{o} ({imp*100:.0f}% implied)"
            return o

        out["Win Odds (Implied%)"] = df["odds_to_win"].apply(_odds_with_implied)
        out["Est. Win%"]   = (df["win_prob"] * 100).round(1).astype(str) + "%"
        out["World Rank"]  = df["world_rank"].apply(lambda x: f"#{int(x)}" if pd.notna(x) else "—")
        out["Top 10%"]     = (df["top10_prob"] * 100).round(0).astype(int).astype(str) + "%"
        out["Top 20%"]     = (df["top20_prob"] * 100).round(0).astype(int).astype(str) + "%"
        out["Course Hist"] = df.apply(_fmt_course_history, axis=1)

        # Note: raw SG numbers removed — use FORM & STATS section for player strengths.
        # This table is for odds/probability reference only.

        if "live_top10_prob" in df.columns:
            out["Live T10%"] = (df["live_top10_prob"] * 100).round(0).fillna(0).astype(int).astype(str) + "%"

        note = (
            "Est. Win% is our estimate — compare to Implied% for value. "
            "Top 10%/Top 20% are finish probabilities — do NOT compare to win odds. "
            "Player stats, form, and course history are in the FORM & STATS section below."
        )
        return f"## FIELD OVERVIEW — Top {top_n} contenders\n{note}\n" + out.to_markdown(index=False)
    except Exception as e:
        return f"## FIELD OVERVIEW\n(unavailable: {e})"


def _player_deep_dive_block(player_names: list[str], tid: str | None = None) -> str:
    """Detailed stat card for each named player — SG breakdown, odds, finish probs, course history."""
    if not player_names:
        return ""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)

        field_size = len(df)
        lines = [f"## PLAYER SPOTLIGHT: {', '.join(player_names)}"]

        for pname in player_names:
            # Match by exact last name first, then fall back to substring
            # Prevents "Scott" from matching "Scottie Scheffler"
            parts = pname.lower().split()
            last  = parts[-1]
            first = parts[0] if len(parts) > 1 else ""

            # 1. Exact last name match (case-insensitive)
            def _last_name(n):
                n = n.lower()
                return n.split()[-1] if n else ""
            mask_exact = df["player_name"].apply(_last_name) == last
            rows = df[mask_exact]

            # 2. If multiple hits (e.g. "Rose" matches "Justin Rose" and "Rose Zhang"),
            #    narrow by first name if we have it
            if len(rows) > 1 and first:
                first_mask = rows["player_name"].str.lower().str.startswith(first)
                if first_mask.any():
                    rows = rows[first_mask]

            # 3. Fall back to substring if exact match found nothing
            if rows.empty:
                mask_sub = df["player_name"].str.lower().str.contains(last, na=False)
                rows = df[mask_sub]

            if rows.empty:
                lines.append(f"\n### {pname}: Not found in this week's field")
                continue

            r = rows.iloc[0]
            actual = r["player_name"]
            wr = r.get("world_rank")
            wr_str = f"World #{int(wr)}" if pd.notna(wr) else ""
            lines.append(f"\n### {actual}" + (f" ({wr_str})" if wr_str else ""))

            # --- Odds & value ---
            odds      = _fmt_odds(r.get("odds_to_win"))
            win_prob  = float(r.get("win_prob", 0) or 0)
            implied   = _american_to_implied(r.get("odds_to_win"))
            t5        = float(r.get("top5_prob",  0) or 0)
            t10       = float(r.get("top10_prob", 0) or 0)
            t20       = float(r.get("top20_prob", 0) or 0)

            if implied:
                value_flag = ""
                if win_prob > implied * 1.3:
                    value_flag = " ← we like him MORE than the market"
                elif win_prob < implied * 0.7:
                    value_flag = " ← market favors him more than we do"
                lines.append(
                    f"**Win odds**: {odds} (book implies {implied*100:.0f}% chance){value_flag}"
                )
            else:
                lines.append(f"**Win odds**: {odds}")
            lines.append(
                f"**Finish chances**: Top 5: {t5*100:.0f}% | Top 10: {t10*100:.0f}% | Top 20: {t20*100:.0f}%"
            )

            # --- Form (plain English, no raw numbers) ---
            mc_last   = int(r.get("missed_cut_last_start", 0) or 0)
            t5_last   = int(r.get("post_top5_last_start",  0) or 0)
            last_pos  = r.get("last_start_position")
            consec_c  = int(r.get("consecutive_cuts",   0) or 0)
            consec_t  = int(r.get("consecutive_top10s", 0) or 0)
            r_t10     = float(r.get("recent_top10s",    0) or 0)
            r_cuts    = float(r.get("recent_cuts_pct",  0) or 0)
            hot       = bool(r.get("hot_hand_flag", False))
            hot_score = float(r.get("hot_hand_score", 0) or 0)
            ft        = float(r.get("form_trend",    0) or 0)

            try:
                last_pos_int = int(float(last_pos)) if last_pos and float(last_pos) < 999 else None
            except (TypeError, ValueError):
                last_pos_int = None

            form_parts = []
            if mc_last:
                form_parts.append("missed the cut last start")
            elif last_pos_int:
                label = "top-5 finish" if t5_last else ("top-10" if last_pos_int <= 10 else "")
                form_parts.append(f"T{last_pos_int} last start" + (f" ({label})" if label else ""))

            if consec_t >= 2:
                form_parts.append(f"{consec_t} top-10s in a row")
            elif r_t10 >= 2:
                form_parts.append(f"{int(round(r_t10))} top-10s in last 5 starts")
            if consec_c >= 5:
                form_parts.append(f"made {consec_c} cuts straight")
            elif r_cuts >= 0.8:
                form_parts.append("consistently making cuts")
            elif r_cuts < 0.5:
                form_parts.append("missing cuts regularly")
            if hot and hot_score >= 8:
                form_parts.append("in red-hot form right now")
            elif ft > 0.5:
                form_parts.append("trending up")
            elif ft < -0.5:
                form_parts.append("trending down lately")

            if form_parts:
                lines.append(f"**Recent form**: {' · '.join(form_parts)}")

            # --- Stats in field-rank language ---
            sg_cats = [
                ("season_sg_ott_field_rank", "off the tee"),
                ("season_sg_app_field_rank", "approach play"),
                ("season_sg_arg_field_rank", "around the greens"),
                ("season_sg_putt_field_rank", "putting"),
            ]
            stat_parts = []
            for col, label in sg_cats:
                rank = r.get(col)
                if pd.isna(rank):
                    continue
                rank = int(rank)
                if rank <= 5:
                    stat_parts.append(f"elite {label} (#{rank} in field)")
                elif rank <= 15:
                    stat_parts.append(f"strong {label} (top-15 in field)")
                elif rank > field_size * 0.75:
                    stat_parts.append(f"below-average {label} (#{rank} of {field_size})")
            if stat_parts:
                lines.append(f"**Stats in this field**: {' · '.join(stat_parts)}")

            # --- Course history (narrative) ---
            n_starts  = max(int(r.get("course_starts", 0) or 0), int(r.get("hist_times_played", 0) or 0))
            wins      = int(r.get("hist_wins",   0) or 0)
            t10s      = int(r.get("hist_top10s", 0) or 0)
            best      = r.get("course_best_finish")
            cut_rt    = float(r.get("course_made_cut_rate", 1) or 1)
            avg_fin   = r.get("course_avg_finish")

            if n_starts == 0:
                lines.append("**Course history**: No history here — first start at this venue")
            else:
                ch_parts = [f"{n_starts} start{'s' if n_starts != 1 else ''} at this course"]
                if wins:
                    ch_parts.append(f"WON {wins}x" if wins > 1 else "won here before")
                elif t10s >= 2:
                    ch_parts.append(f"{t10s} top-10 finishes")
                elif t10s == 1:
                    ch_parts.append("1 top-10 finish")
                if pd.notna(best) and float(best) <= 10:
                    ch_parts.append(f"best finish T{int(float(best))}")
                if pd.notna(avg_fin) and float(avg_fin) <= 25:
                    ch_parts.append(f"avg finish T{int(float(avg_fin))}")
                if cut_rt < 0.5 and n_starts >= 3:
                    ch_parts.append("struggles to make the weekend here")
                elif cut_rt >= 0.9 and n_starts >= 3:
                    ch_parts.append("makes the cut here every time")
                lines.append(f"**Course history**: {' · '.join(ch_parts)}")

            # --- Live position if tournament in progress ---
            if "live_position" in r and pd.notna(r.get("live_position")):
                total  = r.get("total", "?")
                thru   = r.get("thru",  "?")
                live_w = r.get("live_win_prob")
                live_str = f" | Updated win chance: {float(live_w)*100:.1f}%" if pd.notna(live_w) else ""
                lines.append(f"**Live position**: {r['live_position']} | {total} total | thru {thru}{live_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"## PLAYER SPOTLIGHT\n(unavailable: {e})"


def _player_form_context_block(top_n: int = 20) -> str:
    """
    Plain-English form, stats, and course history for the top contenders.
    Designed for Claude to use as a golf analyst would — results, streaks, strengths.
    Avoids raw SG numbers; uses field ranks and descriptive language instead.
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)
        full_field_size = len(df)  # actual field size before filtering
        df = df.sort_values("win_prob", ascending=False).head(top_n).copy()

        def _last_result(row) -> str:
            pos = row.get("last_start_position")
            mc  = row.get("missed_cut_last_start", 0)
            t5  = row.get("post_top5_last_start", 0)
            try:
                pos = int(float(pos))
            except (TypeError, ValueError):
                pos = None
            if mc:
                return "MC last start"
            if pos is None or pos >= 999:
                return "no recent result"
            if t5:
                return f"T{pos} last start (top-5 finish)"
            if pos <= 10:
                return f"T{pos} last start (top-10)"
            return f"T{pos} last start"

        def _form_streak(row) -> str:
            cuts = int(row.get("consecutive_cuts", 0) or 0)
            t10s = int(row.get("consecutive_top10s", 0) or 0)
            r_t10 = float(row.get("recent_top10s", 0) or 0)
            r_cut = float(row.get("recent_cuts_pct", 0) or 0)
            parts = []
            if t10s >= 2:
                parts.append(f"{t10s} top-10s in a row")
            elif r_t10 >= 2:
                parts.append(f"{int(round(r_t10))} top-10s in last 5 starts")
            if cuts >= 5:
                parts.append(f"made {cuts} cuts in a row")
            elif r_cut >= 0.8:
                parts.append(f"making cuts consistently ({int(r_cut*100)}%)")
            elif r_cut < 0.5:
                parts.append("struggling to make cuts recently")
            if row.get("hot_hand_flag"):
                hot = float(row.get("hot_hand_score", 5) or 5)
                if hot >= 8:
                    parts.append("in red-hot form")
                elif hot >= 5:
                    parts.append("playing well")
            ft = float(row.get("form_trend", 0) or 0)
            if ft > 0.5:
                parts.append("trending up")
            elif ft < -0.5:
                parts.append("trending down")
            return ", ".join(parts) if parts else "steady form"

        def _sg_strengths(row) -> str:
            """Describe SG profile in field-rank terms, not raw numbers."""
            cats = {
                "off the tee":  row.get("season_sg_ott_field_rank"),
                "approach":     row.get("season_sg_app_field_rank"),
                "around green": row.get("season_sg_arg_field_rank"),
                "putting":      row.get("season_sg_putt_field_rank"),
            }
            weak_cutoff  = full_field_size * 0.75  # bottom 25%
            parts = []
            for label, rank in cats.items():
                if pd.isna(rank):
                    continue
                rank = int(rank)
                if rank <= 5:
                    parts.append(f"elite {label} (#{rank} in field)")
                elif rank <= 15:
                    parts.append(f"strong {label} (top-15)")
                elif rank > weak_cutoff:
                    parts.append(f"below-average {label} (#{rank})")
            return "; ".join(parts) if parts else ""

        def _course_narrative(row) -> str:
            starts  = int(row.get("course_starts", 0) or 0)
            hist_s  = int(row.get("hist_times_played", 0) or 0)
            best    = row.get("course_best_finish")
            avg     = row.get("course_avg_finish")
            wins    = int(row.get("hist_wins", 0) or 0)
            t10s    = int(row.get("hist_top10s", 0) or 0)
            cut_rt  = float(row.get("course_made_cut_rate", 1) or 1)
            # Use the larger of course_starts or hist_times_played
            n = max(starts, hist_s)
            if n == 0:
                return "no course history"
            parts = [f"{n} start{'s' if n != 1 else ''} here"]
            if wins:
                parts.append(f"WON {wins}x" if wins > 1 else "WON here before")
            elif t10s >= 2:
                parts.append(f"{t10s} top-10s")
            elif t10s == 1:
                parts.append("1 top-10")
            if pd.notna(best) and float(best) <= 15:
                parts.append(f"best finish T{int(float(best))}")
            if cut_rt < 0.5 and n >= 3:
                parts.append("struggles to make weekend")
            return " · ".join(parts)

        lines = [
            "## FORM, STATS & COURSE HISTORY",
            "Plain-English context for each contender. Use this to speak like a golf analyst — results, streaks, strengths — not model numbers.",
            "",
        ]

        for _, row in df.iterrows():
            name  = row["player_name"]
            wr    = row.get("world_rank")
            wr_str = f"World #{int(wr)}" if pd.notna(wr) else ""
            last  = _last_result(row)
            streak = _form_streak(row)
            sg_str = _sg_strengths(row)
            course = _course_narrative(row)

            line = f"**{name}**"
            if wr_str:
                line += f" ({wr_str})"
            line += f" — {last}. {streak.capitalize()}."
            if sg_str:
                line += f" Stats: {sg_str}."
            line += f" Course: {course}."
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        return f"## FORM & STATS\n(unavailable: {e})"


def _odds_movement_block(player_names: list[str] | None = None) -> str:
    """Price drift from odds snapshots — biggest movers, or movement for specific players."""
    snap_dir = DATA / "odds" / "snapshots"
    if not snap_dir.exists():
        return ""
    try:
        snap_files = sorted(snap_dir.glob("odds_snapshot_*.csv"))
        # Only use snapshots from the last 7 days (keeps within current tournament week)
        cutoff = datetime.now() - timedelta(days=7)
        recent = []
        for f in snap_files:
            try:
                ts_str = f.stem.replace("odds_snapshot_", "")
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M")
                if ts >= cutoff:
                    recent.append(f)
            except Exception:
                continue

        if len(recent) < 2:
            return ""

        first = pd.read_csv(recent[0])
        last  = pd.read_csv(recent[-1])

        for df in [first, last]:
            df["player_name"] = df["player_name"].apply(_fmt_name)

        merged = first.merge(last, on="player_name", suffixes=("_open", "_now"))
        merged = merged.dropna(subset=["odds_numeric_open", "odds_numeric_now"])

        def imp(o):
            try:
                o = float(o)
                return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
            except Exception:
                return None

        merged["prob_open"] = merged["odds_numeric_open"].apply(imp)
        merged["prob_now"]  = merged["odds_numeric_now"].apply(imp)
        merged = merged.dropna(subset=["prob_open", "prob_now"])
        merged["prob_chg"] = merged["prob_now"] - merged["prob_open"]
        merged = merged.sort_values("prob_chg", ascending=False)

        if player_names:
            p_lower = [p.lower() for p in player_names]
            mask = merged["player_name"].str.lower().apply(
                lambda n: any(pl in n or n in pl for pl in p_lower)
            )
            subset = merged[mask]
        else:
            # Top 5 shortened + top 5 lengthened
            top5 = merged.head(5)
            bot5 = merged.tail(5).sort_values("prob_chg")
            subset = pd.concat([top5, bot5]).drop_duplicates()

        if subset.empty:
            return ""

        t0 = recent[0].stem.replace("odds_snapshot_", "")
        t1 = recent[-1].stem.replace("odds_snapshot_", "")
        lines = [f"## ODDS MOVEMENT ({t0} → {t1})", "Positive = odds shortened (became more favored)."]

        for _, row in subset.iterrows():
            o_open = _fmt_odds(row["odds_numeric_open"])
            o_now  = _fmt_odds(row["odds_numeric_now"])
            chg    = row["prob_chg"]
            arrow  = "▲" if chg > 0.005 else ("▼" if chg < -0.005 else "→")
            pct    = f"{chg*100:+.1f}pp"
            lines.append(f"- {row['player_name']}: {o_open} → {o_now} {arrow} ({pct})")

        return "\n".join(lines)
    except Exception as e:
        return f"## ODDS MOVEMENT\n(unavailable: {e})"


def _weather_block(tid: str) -> str:
    """4-round weather forecast from cached weather JSON."""
    if not tid:
        return ""
    path = DATA / "weather" / f"{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)
        daily = data.get("daily", [])
        if not daily:
            return ""
        round_labels = ["Thursday (R1)", "Friday (R2)", "Saturday (R3)", "Sunday (R4)"]
        lines = ["## WEATHER FORECAST"]
        for i, day in enumerate(daily[:4]):
            label  = round_labels[i] if i < 4 else f"Day {i+1}"
            hi     = str(day.get("temperature", {}).get("maxTempF", "?")).replace("°F","")
            lo     = str(day.get("temperature", {}).get("minTempF", "?")).replace("°F","")
            wind   = day.get("windSpeedMPH", "?")
            precip = day.get("precipitation", "?")
            desc   = day.get("condition", "").replace("_", " ").title()
            wdir   = day.get("windDirection", "").replace("_", " ").title()
            lines.append(
                f"- {label}: {desc} | {lo}–{hi}°F | Wind: {wind} mph {wdir} | Precip: {precip}"
            )
        saved = data.get("saved_at", "")
        if saved:
            lines.append(f"_(forecast as of {saved[:10]})_")
        return "\n".join(lines)
    except Exception as e:
        return f"## WEATHER\n(unavailable: {e})"


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
                    bubble    = cp.get("bubble_count", "?")
                    cut_info  = (
                        f"\n\n## CUT PROJECTION: {cut_score:+d} | {bubble} players on bubble"
                        if isinstance(cut_score, int)
                        else f"\n\n## CUT PROJECTION: {cut_score} | {bubble} players on bubble"
                    )
            except Exception:
                pass

        if rounds_complete == 0:
            return cut_info

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
    """Top recommended bets."""
    path = DATA / "odds" / "recommended_bets_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df[df["status"] == "priced"].copy() if "status" in df.columns else df
        df = df.sort_values("edge_pts", ascending=False).head(top_n)

        out = pd.DataFrame()
        out["Market"]  = df["market"] if "market" in df.columns else "—"
        out["Player"]  = df["player_name"].apply(_fmt_name)
        out["Book"]    = df["book"] if "book" in df.columns else "—"
        out["Odds"]    = df["odds_american"].apply(lambda x: _fmt_odds(x) if pd.notna(x) else "—")
        if "book_prob" in df.columns:
            out["Book Says"] = (df["book_prob"] * 100).round(1).astype(str) + "%"
        if "model_prob" in df.columns:
            out["We Think"]  = (df["model_prob"] * 100).round(1).astype(str) + "%"
        if "ev_per_1" in df.columns:
            out["EV/$1"] = df["ev_per_1"].round(2).apply(lambda x: f"+${x:.2f}" if x > 0 else f"-${abs(x):.2f}")
        if "confidence" in df.columns:
            out["Conf"] = df["confidence"].apply(lambda x: "High" if x >= 0.9 else ("Med" if x >= 0.7 else "Low"))

        note = (
            "Each row is a specific market. 'Book Says' and 'We Think' are for THAT market only. "
            "EV/$1 = expected profit per $1 wagered."
        )
        return "## TOP BETS THIS WEEK\n" + note + "\n" + out.to_markdown(index=False)
    except Exception as e:
        return f"## TOP BETS THIS WEEK\n(unavailable: {e})"


def _course_profile_block(tid: str) -> str:
    """Course summary + hardest/easiest holes."""
    if not tid:
        return ""
    tid_lower = tid.lower()
    year = datetime.now().year
    hole_path    = DATA / "course_characteristics" / f"{tid_lower}_{year}.csv"
    profile_path = DATA / "course_characteristics" / f"{tid_lower}_{year}_profiles.csv"
    lines = []

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
            lines.append(f"Par {par} | {yardage} yards | {p3} par-3s, {p4} par-4s, {p5} par-5s")
            lines.append(f"Field scoring avg: {scoring:.3f} | Birdie rate: {birdie:.1f}% | Bogey rate: {bogey:.1f}%")
        except Exception as e:
            lines.append(f"## COURSE PROFILE\n(unavailable: {e})")

    if hole_path.exists():
        try:
            h = pd.read_csv(hole_path).sort_values("difficulty_rank")
            hardest = h.head(3)
            easiest = h.tail(3).sort_values("difficulty_rank", ascending=False)

            def _hole_str(row) -> str:
                return (
                    f"  Hole {int(row['hole_num'])} "
                    f"(Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): "
                    f"avg {row['scoring_avg']:.3f} ({row['scoring_diff']:+.3f} vs par)"
                )

            lines.append("\nHardest holes:")
            for _, r in hardest.iterrows():
                lines.append(_hole_str(r))
            lines.append("\nEasiest holes (birdie chances):")
            for _, r in easiest.iterrows():
                lines.append(_hole_str(r))
        except Exception:
            pass

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
            short = comment[:120] + "…" if len(comment) > 120 else comment
            lines.append(f"- **{expert}** → {winner}: {short}")
        return "\n".join(lines)
    except Exception as e:
        return f"## EXPERT CONSENSUS\n(unavailable: {e})"


def _my_picks_block() -> str:
    """Current week picks + remaining uses."""
    path = DATA / "fantasy" / "usage_tracker_2026.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)
        weekly   = data.get("weekly_lineups", {})
        cur_week = weekly[max(weekly.keys())] if weekly else None
        picks    = data.get("picks", {})
        max_uses = int(data.get("max_uses_per_player", 3))

        lines = ["## MY PICKS THIS WEEK"]
        if cur_week:
            lineup     = cur_week.get("lineup", [])
            tournament = cur_week.get("tournament", "")
            lines.append(
                f"**Week {cur_week.get('week','?')} lineup — {tournament}**: "
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
    """League standings, weekly picks, ownership, and rival intel."""
    standings_path = DATA / "fantasy" / "league_standings.csv"
    weekly_path    = DATA / "fantasy" / "league_weekly_picks.csv"
    usage_path     = DATA / "fantasy" / "league_player_usage.csv"

    if not standings_path.exists():
        return ""

    MY_TEAM = "WineTime"
    lines = ["## LEAGUE CONTEXT (Louisiana/Delaware Connection — 28 teams, max 3 uses/player)"]

    try:
        standings = pd.read_csv(standings_path)
        my_row    = standings[standings["team_name"] == MY_TEAM]
        my_place  = my_row["place"].iloc[0] if not my_row.empty else "?"
        my_earn   = my_row["earnings"].iloc[0] if not my_row.empty else "?"
        my_back   = my_row["earnings_back"].iloc[0] if not my_row.empty else "?"
        lines.append(f"\n**Season Standings — {MY_TEAM} is {my_place} | {my_earn} | {my_back} back**")
        top5 = standings.head(5)[["place", "team_name", "owner", "earnings", "earnings_back"]]
        lines.append(top5.to_markdown(index=False))
        if not my_row.empty and int(my_row.index[0]) >= 5:
            lines.append(f"...  {my_place} | {MY_TEAM} | {my_earn} | {my_back} back")
    except Exception as e:
        lines.append(f"(standings unavailable: {e})")

    if weekly_path.exists():
        try:
            weekly = pd.read_csv(weekly_path)
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

            top12 = weekly.head(12)
            if MY_TEAM not in top12["team_name"].values:
                top12 = pd.concat([top12, weekly[weekly["team_name"] == MY_TEAM]]).drop_duplicates()
            lines.append(f"\n**Current week standings (top 12 + {MY_TEAM}):**")
            display = top12[["weekly_rank","team_name","player_1","player_2","player_3","total_earnings"]].copy()
            display["total_earnings"] = display["total_earnings"].apply(lambda x: f"${x:,}")
            lines.append(display.to_markdown(index=False))

            all_picks = pd.concat([
                weekly[["player_1"]].rename(columns={"player_1": "player"}),
                weekly[["player_2"]].rename(columns={"player_2": "player"}),
                weekly[["player_3"]].rename(columns={"player_3": "player"}),
            ]).query("player != 'VACANT'")["player"].value_counts()
            lines.append("\n**Player ownership this week (# of teams):**")
            lines.append(" | ".join(f"{p}: {c}" for p, c in all_picks.items()))
        except Exception as e:
            lines.append(f"(weekly picks unavailable: {e})")

    if usage_path.exists():
        try:
            usage = pd.read_csv(usage_path)
            locked = usage[usage["uses_left"] == 0].copy()
            if not locked.empty:
                locked_summary = (
                    locked[locked["team_name"] != MY_TEAM]
                    .groupby("player")["team_name"]
                    .apply(lambda teams: ", ".join(sorted(teams)))
                    .reset_index()
                    .rename(columns={"team_name": "locked_out_teams"})
                    .sort_values("player")
                )
                lines.append("\n**Rival teams locked out of players (used all 3x):**")
                lines.append(locked_summary.to_markdown(index=False))

            my_usage = usage[usage["team_name"] == MY_TEAM][["player","times_used","uses_left","total_earned"]]
            if not my_usage.empty:
                lines.append(f"\n**{MY_TEAM} player use history:**")
                my_usage = my_usage.sort_values("times_used", ascending=False).copy()
                my_usage["total_earned"] = my_usage["total_earned"].apply(lambda x: f"${int(x):,}")
                lines.append(my_usage.to_markdown(index=False))
        except Exception as e:
            lines.append(f"(usage data unavailable: {e})")

    return "\n".join(lines)


def _tournament_state(tid: str) -> dict:
    """Return tournament phase dict."""
    state = {"name": tid, "round": 0, "round_status": "", "phase": "pre_tournament"}
    if not tid:
        return state
    meta_path = DATA / "live" / f"leaderboard_{tid.lower()}_meta.json"
    if not meta_path.exists():
        return state
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        state["name"]         = meta.get("tournament_name", tid)
        state["round"]        = int(meta.get("current_round", 0))
        state["round_status"] = meta.get("round_status", "")
        state["fetched_at"]   = meta.get("fetched_at", "")
        r  = state["round"]
        rs = state["round_status"].lower()
        # "groupings official" / "no round" = tee times set but no golf played yet
        _pre_play_statuses = {"groupings official", "no round", "not started", ""}
        if rs == "official" and r == 4:
            state["phase"] = "complete"
        elif r == 0 or rs in _pre_play_statuses:
            state["phase"] = "pre_tournament"
        else:
            state["phase"] = f"round_{r}"
    except Exception:
        pass
    return state


def _tournament_state_block(tid: str) -> str:
    """Inject tournament state header so the LLM knows how to frame responses."""
    ts    = _tournament_state(tid)
    phase = ts["phase"]
    name  = ts["name"]
    r     = ts["round"]

    if phase == "pre_tournament":
        status_line = "PRE-TOURNAMENT — no rounds have been played yet."
        instruction = (
            "Focus on pre-tournament analysis: predictions, betting value, lineup decisions, course fit. "
            "Do not reference live scores or leaderboard positions."
        )
    elif phase == "complete":
        status_line = "TOURNAMENT COMPLETE — all 4 rounds are official."
        instruction = (
            "This tournament is FINISHED. When asked about it, reference final results. "
            "Shift any lineup/betting questions toward the NEXT TOURNAMENT on the schedule."
        )
    else:
        rounds_remaining = 4 - r
        status_line = f"ROUND {r} OF 4 COMPLETE — {rounds_remaining} round(s) remaining."
        instruction = (
            f"We are mid-tournament after Round {r}. "
            "Focus on the live leaderboard: who's leading, who's surged or faded, who still has a realistic chance. "
            f"A player needs to be within ~{max(4, rounds_remaining * 4)} strokes to have a serious chance. "
            "Betting questions: focus on in-play value based on current position. "
            "Lineup questions: picks are already locked for this week."
        )

    fetched = ts.get("fetched_at", "")
    freshness = f" (data last refreshed: {fetched[:16].replace('T',' ')} UTC)" if fetched else ""

    return (
        f"## TOURNAMENT STATUS: {name}\n"
        f"{status_line}{freshness}\n"
        f"RESPOND ACCORDINGLY: {instruction}"
    )


def _schedule_block(current_tid: str | None = None) -> str:
    """Season schedule: completed, current, and next 3 upcoming."""
    path = DATA / "raw" / "schedule_2026.csv"
    if not path.exists():
        return ""
    try:
        sched = pd.read_csv(path)
        today = datetime.now().date()

        complete_tids = set()
        for mf in glob.glob(str(DATA / "live" / "leaderboard_r*_meta.json")):
            try:
                with open(mf) as f:
                    m = json.load(f)
                if m.get("round_status", "").lower() == "official":
                    complete_tids.add(str(m.get("tournament_id", "")))
            except Exception:
                pass

        lines = ["## 2026 SEASON SCHEDULE"]
        lines.append("(Predictions are only available for the CURRENT week.)")

        upcoming_shown = 0
        skipped = 0

        for _, row in sched.iterrows():
            tid   = str(row.get("tournament_id", ""))
            name  = row.get("tournament_name", "")
            ttype = row.get("tournament_type", "")
            purse = row.get("purse", "")
            week  = int(row.get("week", 0))
            start = str(row.get("start_date", ""))
            end   = str(row.get("end_date", ""))

            try:
                start_date = datetime.strptime(start, "%Y-%m-%d").date()
            except Exception:
                start_date = None

            is_done     = tid in complete_tids and tid != current_tid
            is_current  = tid == current_tid
            is_upcoming = start_date and start_date > today and not is_done and not is_current

            if is_done:
                marker = "✓ DONE "
            elif is_current:
                marker = "▶ NOW  "
            elif is_upcoming:
                if upcoming_shown < 3:
                    marker = "→ NEXT " if upcoming_shown == 0 else "  "
                    upcoming_shown += 1
                else:
                    skipped += 1
                    continue
            else:
                continue

            lines.append(f"{marker}Wk{week:02d} | {name} | {ttype} | {purse} | {start} – {end}")

        if skipped:
            lines.append(f"  ... + {skipped} more upcoming tournaments")

        return "\n".join(lines)
    except Exception as e:
        return f"## SCHEDULE\n(unavailable: {e})"


# ---------------------------------------------------------------------------
# Main context builder — query-aware routing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert golf analyst helping a user with fantasy lineup decisions, betting, and tournament analysis.
Communicate like a knowledgeable golf fan talking to another fan — plain English, not technical jargon.

FORMATTING RULES (follow these exactly):
- Lead with the direct answer in the first sentence. Then give reasoning.
- Bold player names using **Name** on first mention in each section.
- Bold key numbers: odds and finish results.
- Use bullet lists (- item) for comparisons, player lists, and multi-part reasoning.
- Use short paragraphs (2-4 sentences max). No walls of text.
- For 3+ players, use a comparison table if markdown renders (Name | Odds | Key stat | Course).
- Recommended bet format: **Player, Market** — Odds → brief reason.

GOLF-LANGUAGE RULES — CRITICAL:
- You are talking to a golfer, NOT a data scientist. Never quote raw SG numbers like '+0.87'.
- Instead, say: "ranks 3rd in this field in approach play" or "elite ball-striker, average putter".
- Describe form with results: "coming off a T5 at Arnold Palmer", "missed the cut last week", "3 top-10s in a row".
- Describe course history as a golfer would: "loves TPC Sawgrass — won here before, makes the cut every time" or "no history here, first start".
- For driving: say "one of the longer hitters in the field" or "short but straight" — not rank numbers unless they're striking (e.g., "#1 off the tee").
- SG numbers in the tables are for reference — translate them into narrative when speaking.
- 'Est. Win%' in the field table is our confidence level — say "we like him more than the market does" not "his win probability is X%".

COMMUNICATION RULES:
- Use American odds (+1300, +600) and plain finish results.
- Never say 'model output', 'implied probability', 'edge pp', or 'win probability was X%'.
- For pre-tournament expectations, say 'listed at +1300' or 'ranked #1 in the world'.
- EV/$1 = expected profit per dollar wagered. Positive = good bet long-term.
- When discussing course fit, reference which parts of the game matter (driving accuracy, approach, putting on fast greens, etc.).
- For lineup advice, reference the user's uses remaining and league standing.
- Don't dump the whole context table — synthesize it. Use specific numbers only when they make the point clearly.
- NEVER invent or interpolate statistics. Only cite specific results, streaks, or rankings that appear explicitly in the FORM & STATS or PLAYER SPOTLIGHT sections. If a stat isn't in the provided data, say "no data" or leave it out — do not guess.

VALUE PLAYS — CRITICAL RULE:
- The field table has 'Est. Win%' and 'Win Odds (Implied%)'. To find value, compare Est. Win% to Implied%.
- Example: Est. Win% = 17%, Implied% = 6% → market undervalues this player for a win bet.
- Top 10% and Top 5% are finish probabilities — NEVER compare them to win odds.
- For top 10 / top 20 bets, use the BETS TABLE which shows 'Book Says' vs 'We Think' per market.

TOURNAMENT UPDATES:
- 5+ strokes back with 1 round left is a very difficult deficit. Be realistic.
- When noting over/underperformance, say 'Scheffler was the +1300 favorite but sits T15' — not probabilities.
- Focus on actual tournament position, strokes to leader, and remaining holes."""


def build_context(
    query: str = "",
    tournament_id: str | None = None,
    last_players: list[str] | None = None,
) -> str:
    """Assemble context relevant to the user's query.

    Routes context blocks based on query intent:
    - Player question  → player deep-dive card + compact field + odds movement + weather
    - Bet question     → bets + odds movement + weather + compact field
    - Live question    → leaderboard + predictions + my picks + league
    - Lineup question  → predictions + expert picks + my picks + league
    - Weather/course   → weather + course profile + compact field
    - General          → full default (everything)

    last_players: players mentioned in the previous assistant response — injected
    as context so follow-up questions like 'what about his odds?' resolve correctly.
    """
    if tournament_id is None:
        tournament_id = _detect_tournament_id()

    intent = _classify_query(query) if query.strip() else {
        "players": [], "is_player": False, "is_bet": False,
        "is_live": False, "is_lineup": False, "is_weather": False,
        "is_course": False, "is_value": False,
    }

    # If the query mentions no players but the previous response did, carry them forward
    if not intent["players"] and last_players:
        intent["players"] = last_players
        intent["is_player"] = True

    sections = [_SYSTEM_PROMPT, ""]

    # Inject prior conversation entities so follow-ups resolve correctly
    if last_players:
        sections.append(f"## CONVERSATION CONTEXT\nPlayers discussed in the previous response: {', '.join(last_players)}\n")
        sections.append("")

    # Always: tournament status
    if tournament_id:
        sections.append(f"## TOURNAMENT: {_tournament_state(tournament_id)['name']} | {tournament_id}")
        sections.append("")
        sections.append(_tournament_state_block(tournament_id))
        sections.append("")

    # ── Route by intent ────────────────────────────────────────────────────
    if intent["is_player"]:
        # Deep dive on the named player(s) + form context + compact field
        sections.append(_player_deep_dive_block(intent["players"], tournament_id))
        sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        sections.append(_predictions_block(top_n=10))
        sections.append("")
        sections.append(_odds_movement_block(player_names=intent["players"]))
        sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
        sections.append(_recommended_bets_block(top_n=8))
        sections.append("")

    elif intent["is_lineup"]:
        # Fantasy-focused — check before bet so "build my lineup" doesn't misroute
        sections.append(_predictions_block(top_n=15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        sections.append(_league_context_block())
        sections.append("")
        sections.append(_recommended_bets_block(top_n=5))
        sections.append("")

    elif intent["is_bet"] or intent["is_value"]:
        # Bets + odds movement front-and-center, compact field, weather for context
        sections.append(_predictions_block(top_n=12))
        sections.append("")
        sections.append(_player_form_context_block(top_n=12))
        sections.append("")
        sections.append(_recommended_bets_block(top_n=15))
        sections.append("")
        sections.append(_odds_movement_block())
        sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")

    elif intent["is_live"]:
        # Leaderboard first, then field context
        if tournament_id:
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
        sections.append(_predictions_block(top_n=15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10))
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        sections.append(_league_context_block())
        sections.append("")

    elif intent["is_weather"] or intent["is_course"]:
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
            sections.append(_course_profile_block(tournament_id))
            sections.append("")
        sections.append(_predictions_block(top_n=10))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10))
        sections.append("")

    else:
        # General: full overview
        sections.append(_predictions_block(top_n=15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        if tournament_id:
            sections.append(_course_profile_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
        sections.append(_recommended_bets_block())
        sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        sections.append(_league_context_block())
        sections.append("")

    # Always append schedule
    sections.append(_schedule_block(current_tid=tournament_id))

    return "\n".join(s for s in sections if s is not None)


# ---------------------------------------------------------------------------
# Groq streaming
# ---------------------------------------------------------------------------

_CLAUDE_MODEL  = "claude-haiku-4-5-20251001"
_GROQ_PRIMARY  = "llama-3.3-70b-versatile"
_GROQ_FALLBACK = "llama-3.1-8b-instant"


def stream_response(messages: list[dict], api_key: str, provider: str = "auto") -> Iterator[str]:
    """Stream a response — Claude primary (if Anthropic key), Groq fallback (free).

    provider:
      "auto"      → use Claude if api_key looks like an Anthropic key, else Groq
      "anthropic" → always Claude
      "groq"      → always Groq
    """
    is_anthropic = api_key.startswith("sk-ant-") or provider == "anthropic"
    if not is_anthropic and provider != "groq":
        # detect by prefix
        is_anthropic = api_key.startswith("sk-ant-")

    if is_anthropic:
        yield from _stream_claude(messages, api_key)
    else:
        yield from _stream_groq(messages, api_key)


def _stream_claude(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream from Claude (Anthropic). Extracts system prompt automatically."""
    try:
        from anthropic import Anthropic
    except ImportError:
        yield "*(anthropic package not installed — run: pip install anthropic)*"
        return

    system = ""
    conv = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            conv.append(m)

    client = Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=_CLAUDE_MODEL,
            max_tokens=2500,
            system=system,
            messages=conv,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"*(Claude error: {e})*"


def _stream_groq(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream from Groq with rate-limit fallback to smaller model."""
    from groq import Groq, RateLimitError

    client = Groq(api_key=api_key)

    def _stream(model: str):
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=2500,
        )

    try:
        for chunk in _stream(_GROQ_PRIMARY):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
    except RateLimitError:
        yield f"*(Daily limit reached for {_GROQ_PRIMARY} — switching to {_GROQ_FALLBACK})*\n\n"
        for chunk in _stream(_GROQ_FALLBACK):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta


def extract_mentioned_players(text: str) -> list[str]:
    """Return player names (First Last) that appear in the given text."""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, usecols=["player_name"])
        text_lower = text.lower()
        found = []
        for raw in df["player_name"]:
            name = _fmt_name(str(raw))
            last = name.split()[-1].lower()
            if len(last) >= 4 and last in text_lower:
                found.append(name)
        return found[:5]  # cap at 5
    except Exception:
        return []


def generate_followup_questions(
    response_text: str,
    last_players: list[str],
    phase: str,
) -> list[str]:
    """Generate 3 contextual follow-up questions based on who was just discussed."""
    _PHASE_FALLBACK = {
        "pre_tournament":  ["Who are the biggest risks this week?", "Any players to avoid at any price?", "Which players have the best course history here?"],
        "round_1":         ["Who's still a realistic winner?", "Any surprise leaders to know about?", "Who to watch closely in Round 2?"],
        "round_2":         ["Who has the best closing record from this position?", "Who's the biggest threat to the leader?", "Who do you like to make a big move this weekend?"],
        "round_3":         ["Who has the best closing record in the field?", "What does the winning score look like from here?", "Any sleepers who could make a late charge?"],
        "round_4":         ["Who tends to buckle under pressure?", "What does the winner need to shoot?", "Who's the best putter among the current leaders?"],
        "complete":        ["What should I prioritize next week?", "Who outperformed their pre-tournament ranking?", "How did the recommended bets finish?"],
    }
    if not last_players:
        return _PHASE_FALLBACK.get(phase, _PHASE_FALLBACK["pre_tournament"])

    p = last_players[0]
    questions = [f"What are {p}'s odds and value this week?"]
    if len(last_players) >= 2:
        p2 = last_players[1]
        questions.append(f"How does {p} compare to {p2}?")
    else:
        questions.append(f"How has {p} played this course historically?")
    questions.append(_PHASE_FALLBACK.get(phase, _PHASE_FALLBACK["pre_tournament"])[0])
    return questions[:3]
