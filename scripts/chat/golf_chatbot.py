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

def _strip_accents(s: str) -> str:
    """Normalize accented characters to ASCII equivalents (e.g. Å → A, é → e)."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _extract_players(query: str) -> list[str]:
    """Find player names mentioned in the query. Returns list of formatted names.
    Matches on last name (≥4 chars) OR first name (≥4 chars, unique enough to avoid false positives).
    Accent-insensitive: 'Aberg' matches 'Åberg'.
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, usecols=["player_name"])
        # Normalize query: lowercase + strip accents so 'aberg' matches 'åberg'
        q_lower = _strip_accents(query.lower())
        matched = []
        # Build a set of first names that appear more than once — too ambiguous to match on
        all_names = [_strip_accents(_fmt_name(str(r)).lower()).split() for r in df["player_name"]]
        first_name_counts: dict[str, int] = {}
        for parts in all_names:
            if parts:
                first_name_counts[parts[0]] = first_name_counts.get(parts[0], 0) + 1

        for raw in df["player_name"]:
            name = _fmt_name(str(raw))
            # Use accent-stripped version for matching only; keep original for display
            parts = _strip_accents(name.lower()).split()
            last  = parts[-1] if parts else ""
            first = parts[0]  if parts else ""

            # Match on last name (≥4 chars)
            if len(last) >= 4 and re.search(rf'\b{re.escape(last)}\b', q_lower):
                matched.append(name)
            # Match on first name (≥4 chars, only if unique in the field)
            elif len(first) >= 4 and first_name_counts.get(first, 0) == 1:
                if re.search(rf'\b{re.escape(first)}\b', q_lower):
                    matched.append(name)

        return matched
    except Exception:
        return []


def _classify_query(query: str) -> dict:
    """Return intent flags from user query."""
    q = query.lower()
    players = _extract_players(q)
    is_h2h = (
        len(players) >= 2 and
        any(w in q for w in [" vs ", " versus ", " or ", "compare", "between", "better", "over"])
    )
    return {
        "players":           players,
        "is_player":         bool(players) and not is_h2h,
        "is_h2h":            is_h2h,
        "is_bet":            any(w in q for w in ["bet", "wager", "odds", "value", "edge", "parlay", "prop", "book", "wager"]) or re.search(r'\bline\b', q) is not None,
        "is_live":           any(w in q for w in ["live", "leaderboard", "leading", "update", "score", "round", "cut", "leader", "current", "standing", "position"]),
        "is_lineup":         any(w in q for w in ["lineup", "fantasy", "team", "build", "choose", "draft", "who should i pick", "my picks"]) or (any(w in q for w in ["pick", "use", "start"]) and not bool(players)),
        "is_weather":        any(w in q for w in ["weather", "wind", "rain", "forecast", "conditions", "temperature", "temp"]),
        "is_course":         any(w in q for w in ["course", "hole", "layout", "yardage", "field", "green", "fairway", "rough", "setup"]),
        "is_value":          any(w in q for w in ["value", "underdog", "long shot", "longshot", "undervalued", "sharp"]),
        "is_course_breakdown": any(w in q for w in [
            "wins at", "wins here", "game plan", "what game", "type of player", "fits this course",
            "course breakdown", "what skills", "what does this course", "who fits", "favors",
            "advantage", "suits", "bomber", "accuracy", "iron play", "ball striker",
            "what kind of player", "who should win", "course fit",
        ]) or (any(w in q for w in ["what wins", "who wins"]) and not bool(players)),
        "is_daily_bet": any(w in q for w in [
            "recommend a bet", "best bet today", "bet of the day", "what should i bet",
            "daily bet", "give me a bet", "top bet", "best bet for today",
            "what to bet", "betting recommendation", "bet recommendation",
            "recommended bet", "what bet", "bet today", "should i bet",
        ]),
        "is_pick_reason": bool(players) and any(w in q for w in [
            "why pick", "why should i pick", "make the case", "case for",
            "should i pick", "worth picking", "good pick", "strong pick",
            "explain the pick", "why is", "why him", "why them",
            "tell me about", "break down", "breakdown", "analysis of",
            "what do you think about", "thoughts on", "take on",
            "worth using", "worth starting", "start or sit",
        ]),
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


def _player_deep_dive_block(player_names: list[str], tid: str | None = None, include_odds: bool = False) -> str:
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

        # Resolve course par from characteristics file (default 72)
        course_par = 72
        if tid:
            year = datetime.now().year
            prof_path = DATA / "course_characteristics" / f"{tid.lower()}_{year}_profiles.csv"
            if prof_path.exists():
                try:
                    course_par = int(pd.read_csv(prof_path).iloc[0].get("course_par", 72))
                except Exception:
                    pass

        lines = [
            f"## PLAYER SPOTLIGHT: {', '.join(player_names)}",
            "INSTRUCTION: Every number in this block MUST appear verbatim in your response. Do not paraphrase or replace with adjectives.",
        ]

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

            # --- Odds & value (only shown for betting questions) ---
            win_prob  = float(r.get("win_prob", 0) or 0)
            t5        = float(r.get("top5_prob",  0) or 0)
            t10       = float(r.get("top10_prob", 0) or 0)
            t20       = float(r.get("top20_prob", 0) or 0)

            if include_odds:
                odds    = _fmt_odds(r.get("odds_to_win"))
                implied = _american_to_implied(r.get("odds_to_win"))
                if implied:
                    value_flag = ""
                    if win_prob > implied * 1.3:
                        value_flag = " ← we like him MORE than the market"
                    elif win_prob < implied * 0.7:
                        value_flag = " ← market favors him more than we do"
                    lines.append(f"**Win odds**: {odds} (book implies {implied*100:.0f}% chance){value_flag}")
                else:
                    lines.append(f"**Win odds**: {odds}")
                lines.append(f"**Finish chances**: Top 5: {t5*100:.0f}% | Top 10: {t10*100:.0f}% | Top 20: {t20*100:.0f}%")

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

            # --- Season summary ---
            n_events    = int(r.get("sg_event_count", 0) or 0)
            r_wins      = int(r.get("recent_wins",  0) or 0)
            r_t5s       = int(r.get("recent_top5s", 0) or 0)
            r_t10s_raw  = float(r.get("recent_top10s", 0) or 0)
            r_scoring   = r.get("recent_scoring_avg")
            if n_events >= 1:
                season_parts = [f"{n_events} starts this season"]
                if r_wins:
                    season_parts.append(f"{r_wins} win{'s' if r_wins > 1 else ''}")
                if r_t5s:
                    season_parts.append(f"{r_t5s} top-5{'s' if r_t5s > 1 else ''}")
                if r_t10s_raw >= 1:
                    season_parts.append(f"{int(round(r_t10s_raw))} top-10s in last 5 starts")
                if consec_c:
                    season_parts.append(f"{consec_c} consecutive cuts made")
                if pd.notna(r_scoring) and float(r_scoring) > 0:
                    season_parts.append(f"scoring avg {float(r_scoring):.2f}/round")
                lines.append(f"**This season**: {' · '.join(season_parts)}")

            form_parts = []
            if mc_last:
                form_parts.append("missed the cut last start")
            elif last_pos_int:
                label = " (top-5)" if t5_last else (" (top-10)" if last_pos_int <= 10 else "")
                form_parts.append(f"T{last_pos_int} last start{label}")

            if consec_t >= 2:
                form_parts.append(f"{consec_t} consecutive top-10s")
            if hot:
                form_parts.append(f"in peak form (hot-hand score {int(hot_score)}/10)")
            elif ft > 0.5:
                form_parts.append("trending up")
            elif ft < -0.5:
                form_parts.append("trending down")
            if r_cuts >= 0.8:
                form_parts.append(f"making {r_cuts*100:.0f}% of cuts recently")
            elif r_cuts < 0.5:
                form_parts.append(f"missing cuts at an alarming rate ({r_cuts*100:.0f}% made)")

            if form_parts:
                lines.append(f"**Recent form**: {' · '.join(form_parts)}")

            # --- SG strokes gained (raw value + field rank for every category) ---
            sg_cats = [
                ("season_sg_total",  "season_sg_total_field_rank",  "total"),
                ("season_sg_t2g",    "season_sg_t2g_field_rank",    "tee-to-green"),
                ("season_sg_ott",    "season_sg_ott_field_rank",    "off the tee"),
                ("season_sg_app",    "season_sg_app_field_rank",    "approach"),
                ("season_sg_arg",    "season_sg_arg_field_rank",    "around green"),
                ("season_sg_putt",   "season_sg_putt_field_rank",   "putting"),
            ]
            stat_parts = []
            for val_col, rank_col, label in sg_cats:
                val  = r.get(val_col)
                rank = r.get(rank_col)
                if pd.isna(val) and pd.isna(rank):
                    continue
                val_str  = f"{float(val):+.3f} SG/round" if pd.notna(val) else ""
                rank_str = f"#{int(rank)} in field" if pd.notna(rank) else ""
                combined = ", ".join(filter(None, [val_str, rank_str]))
                stat_parts.append(f"{label}: {combined}")
            if stat_parts:
                lines.append(f"**Strokes Gained**: {' · '.join(stat_parts)}")

            # --- Traditional stats ---
            trad_parts = []
            drv_dist = r.get("driving_dist_val")
            drv_acc  = r.get("driving_acc_val")
            gir      = r.get("gir_pct_val")
            scramble = r.get("scrambling_val")
            sand     = r.get("sand_save_val")
            bogey_av = r.get("bogey_avoid_val")
            putts_r  = r.get("putts_per_round_val")
            one_putt = r.get("one_putt_pct_val")
            birdie_v = r.get("birdie_avg_val")
            birdie_r = r.get("birdie_avg_field_rank")
            consist  = r.get("finish_consistency")
            if pd.notna(drv_dist): trad_parts.append(f"drives it {float(drv_dist):.0f} yds")
            if pd.notna(drv_acc):  trad_parts.append(f"{float(drv_acc):.1f}% driving accuracy")
            if pd.notna(gir):      trad_parts.append(f"{float(gir):.1f}% GIR")
            if pd.notna(scramble): trad_parts.append(f"{float(scramble):.1f}% scrambling")
            if pd.notna(sand):     trad_parts.append(f"{float(sand):.1f}% sand saves")
            if pd.notna(bogey_av): trad_parts.append(f"{float(bogey_av):.1f}% bogey avoidance")
            if pd.notna(putts_r):  trad_parts.append(f"{float(putts_r):.2f} putts/round")
            if pd.notna(one_putt): trad_parts.append(f"{float(one_putt):.1f}% one-putt")
            if pd.notna(birdie_v):
                rank_str = f" (#{int(birdie_r)} in field)" if pd.notna(birdie_r) else ""
                trad_parts.append(f"{float(birdie_v):.2f} birdies/round{rank_str}")
            if trad_parts:
                # Split into ball-striking and scoring lines for readability
                ball_striking = [p for p in trad_parts if any(x in p for x in ["yds", "accuracy", "GIR", "scrambling", "sand"])]
                scoring_stats = [p for p in trad_parts if any(x in p for x in ["bogey", "putts", "one-putt", "birdies"])]
                other = [p for p in trad_parts if p not in ball_striking and p not in scoring_stats]
                sample_note = f" (based on {n_events} starts)" if n_events and n_events < 6 else ""
                if ball_striking:
                    lines.append(f"**Ball striking**{sample_note}: {' · '.join(ball_striking)}")
                if scoring_stats:
                    lines.append(f"**Scoring stats**: {' · '.join(scoring_stats)}")
                if other:
                    lines.append(f"**Other**: {' · '.join(other)}")

            # --- Course history + course-specific performance ---
            n_starts   = max(int(r.get("course_starts", 0) or 0), int(r.get("hist_times_played", 0) or 0))
            wins       = int(r.get("hist_wins",   0) or 0)
            t5s_here   = int(r.get("hist_top5s",  0) or 0)
            t10s       = int(r.get("hist_top10s", 0) or 0)
            best       = r.get("course_best_finish")
            hist_best  = r.get("hist_best_finish")
            hist_avg   = r.get("hist_avg_finish")
            hist_cut   = r.get("hist_cut_rate")
            cut_rt     = float(r.get("course_made_cut_rate", 1) or 1)
            avg_to_par = r.get("course_avg_to_par")
            c_scoring  = r.get("course_stat_120_scoring_average_weighted")
            c_drv_acc  = r.get("course_stat_102_driving_accuracy_weighted")
            c_sg_app   = r.get("course_sg_app_weighted")
            c_sg_ott   = r.get("course_sg_ott_weighted")
            c_sg_putt  = r.get("course_sg_putt_weighted")

            if n_starts == 0:
                lines.append("**Course history**: No history here — first start at this venue")
            else:
                ch_parts = [f"{n_starts} start{'s' if n_starts != 1 else ''} at this course"]
                if wins:
                    ch_parts.append(f"WON {wins}x" if wins > 1 else "won here before")
                if t5s_here:
                    ch_parts.append(f"{t5s_here} top-5{'s' if t5s_here > 1 else ''} here")
                elif t10s:
                    ch_parts.append(f"{t10s} top-10{'s' if t10s > 1 else ''} here")
                best_val = best or hist_best
                if pd.notna(best_val) and float(best_val) <= 20:
                    ch_parts.append(f"best finish T{int(float(best_val))}")
                if pd.notna(hist_avg):
                    ch_parts.append(f"avg finish T{int(float(hist_avg))}")
                if pd.notna(avg_to_par):
                    actual_total = course_par * 4 + float(avg_to_par)
                    ch_parts.append(f"avg {float(avg_to_par):+.1f} per tournament ({actual_total:.0f} total)")
                elif pd.notna(c_scoring):
                    ch_parts.append(f"scoring avg {float(c_scoring):.1f}/round here ({float(c_scoring) * 4:.0f} est. total)")
                cut_rate = float(hist_cut) if pd.notna(hist_cut) else cut_rt
                if cut_rate < 0.5 and n_starts >= 3:
                    ch_parts.append(f"makes cut only {cut_rate*100:.0f}% of the time here")
                elif cut_rate >= 0.9 and n_starts >= 3:
                    ch_parts.append(f"makes cut {cut_rate*100:.0f}% here")
                lines.append(f"**Course history**: {' · '.join(ch_parts)}")

                # Course-specific strengths/weaknesses vs season stats
                c_stat_parts = []
                if pd.notna(c_sg_ott):
                    c_val = float(c_sg_ott)
                    if c_val >= 0.4:
                        c_stat_parts.append(f"elite off-the-tee here (+{c_val:.2f} SG/round historically)")
                    elif c_val <= -0.3:
                        c_stat_parts.append(f"drives it poorly at this course ({c_val:+.2f} SG/round)")
                if pd.notna(c_drv_acc):
                    season_acc = float(r.get("driving_acc_val") or 0)
                    c_val = float(c_drv_acc)
                    if c_val >= 65:
                        c_stat_parts.append(f"hits fairways here ({c_val:.0f}% driving acc)")
                    elif season_acc and c_val > season_acc + 5:
                        c_stat_parts.append(f"drives straighter here than season avg ({c_val:.0f}% vs {season_acc:.0f}%)")
                if pd.notna(c_sg_app):
                    c_val = float(c_sg_app)
                    if c_val >= 0.3:
                        c_stat_parts.append(f"strong approach play at this course (+{c_val:.2f} SG/round)")
                    elif c_val <= -0.2:
                        c_stat_parts.append(f"struggles with irons here ({c_val:+.2f} SG/round)")
                if pd.notna(c_sg_putt):
                    c_val = float(c_sg_putt)
                    if c_val >= 0.3:
                        c_stat_parts.append(f"putts well on these greens (+{c_val:.2f} SG/round)")
                    elif c_val <= -0.3:
                        c_stat_parts.append(f"poor putter on these greens ({c_val:+.2f} SG/round)")
                if c_stat_parts:
                    lines.append(f"**At this course specifically**: {' · '.join(c_stat_parts)}")

            # --- Par scoring breakdown (rank + avg value) ---
            par3_rank = r.get("par3_scoring_field_rank")
            par4_rank = r.get("par4_scoring_field_rank")
            par5_rank = r.get("par5_scoring_field_rank")
            par4_val  = r.get("par4_scoring_val")
            par5_val  = r.get("par5_scoring_val")
            par_parts = []
            for label, rank_col, val_col in [
                ("par 3s", par3_rank, None),
                ("par 4s", par4_rank, par4_val),
                ("par 5s", par5_rank, par5_val),
            ]:
                if pd.isna(rank_col):
                    continue
                rank = int(rank_col)
                val_str = f" (avg {float(val_col):+.2f})" if pd.notna(val_col) else ""
                if rank <= 10:
                    par_parts.append(f"elite {label} (#{rank} in field{val_str})")
                elif rank <= 20:
                    par_parts.append(f"strong {label} (#{rank}{val_str})")
                elif rank > field_size * 0.75:
                    par_parts.append(f"weak {label} (#{rank} of {field_size}{val_str})")
                else:
                    par_parts.append(f"avg {label} (#{rank}{val_str})")
            if par_parts:
                lines.append(f"**Par scoring**: {' · '.join(par_parts)}")

            # --- Round-by-round tendencies (always show all available avgs) ---
            r1    = r.get("recent_r1_avg");  r1_pct = r.get("recent_r1_avg_field_pct")
            r2    = r.get("recent_r2_avg");  r2_pct = r.get("recent_r2_avg_field_pct")
            r3    = r.get("recent_r3_avg");  r3_pct = r.get("recent_r3_avg_field_pct")
            r4    = r.get("recent_r4_avg");  r4_pct = r.get("recent_r4_avg_field_pct")
            closing_delta = r.get("closing_delta")
            _rnd  = [(1, r1, r1_pct), (2, r2, r2_pct), (3, r3, r3_pct), (4, r4, r4_pct)]
            _have = [(n, float(v), float(p)) for n, v, p in _rnd if pd.notna(v) and pd.notna(p)]
            round_parts = []
            if len(_have) >= 2:
                # Show vs-par AND actual score (e.g. R1: -2.8 (69.2))
                rnd_strs = [f"R{n}: {v:+.1f} ({course_par + v:.1f})" for n, v, p in _have]
                round_parts.append(f"round avgs — {' | '.join(rnd_strs)}")
                # Flag notable patterns
                for n, v, p in _have:
                    if n == 1 and p >= 0.85:
                        round_parts.append("strong starter")
                    elif n == 1 and p <= 0.20:
                        round_parts.append("slow starter")
                    if n == 4 and p >= 0.85:
                        round_parts.append("elite Sunday closer")
                    elif n == 4 and p <= 0.20:
                        round_parts.append("fades on Sundays")
            elif _have:
                n, v, p = _have[0]
                round_parts.append(f"R{n} avg {v:+.1f}")
            if pd.notna(closing_delta):
                cd = float(closing_delta)
                if cd <= -0.5:
                    round_parts.append(f"gains strokes closing tournaments (delta {cd:+.2f})")
                elif cd >= 0.5:
                    round_parts.append(f"loses strokes on Sundays vs Thursday (delta {cd:+.2f})")
            if round_parts:
                lines.append(f"**Round tendencies**: {' · '.join(round_parts)}")

            # --- Projected score (median + range) ---
            proj_vs  = r.get("projected_score_vs_field")
            p_floor  = r.get("proj_floor")
            p_median = r.get("proj_median")
            p_ceil   = r.get("proj_ceiling")
            if pd.notna(p_median):
                proj_str = f"median {float(p_median):+.1f} vs field"
                if pd.notna(p_floor) and pd.notna(p_ceil):
                    proj_str += f" | range: {float(p_floor):+.1f} (floor) to {float(p_ceil):+.1f} (ceiling)"
                lines.append(f"**Projection**: {proj_str}")
            elif pd.notna(proj_vs):
                lines.append(f"**Projection**: {float(proj_vs):+.1f} vs field average")

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


def _pick_reason_context_block(player_names: list[str], tid: str | None = None) -> str:
    """
    Enriched context for "why should I pick X?" fantasy lineup questions.
    Layers the player deep-dive with:
      - Model rank + finish probabilities (no sportsbook language)
      - Usage remaining from usage_tracker_2026.json (max 3 uses per season)
      - League-wide usage totals from league_total_usages.csv (scraped from fantasy site)
      - Key model drivers: SG, course fit, form trend, course history
      - Expert consensus count
      - Honest concerns (recent cuts, form dip, bad course history)
    """
    base = _player_deep_dive_block(player_names, tid, include_odds=False)
    if not base:
        return ""

    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return base

    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)
        df["_name_key"] = df["player_name"].str.lower().str.strip()

        # Model rank by win probability
        df = df.sort_values("win_prob", ascending=False).reset_index(drop=True)
        df["_model_rank"] = range(1, len(df) + 1)

        # Expert picks
        expert_counts: dict[str, int] = {}
        if tid:
            ep_path = DATA / "expert_picks" / f"expert_picks_{tid}.csv"
            if not ep_path.exists():
                ep_path = DATA / "expert_picks" / "expert_picks_latest.csv"
            if ep_path.exists():
                try:
                    ep = pd.read_csv(ep_path)
                    name_col = next((c for c in ep.columns if "player" in c.lower() or "name" in c.lower()), None)
                    if name_col:
                        for nm in ep[name_col].dropna():
                            nk = _fmt_name(str(nm)).lower().strip()
                            expert_counts[nk] = expert_counts.get(nk, 0) + 1
                except Exception:
                    pass

        # Usage tracker — my team's uses remaining per player
        usage_data: dict[str, dict] = {}
        usage_path = DATA / "fantasy" / "usage_tracker_2026.json"
        if usage_path.exists():
            try:
                import json
                raw_usage = json.loads(usage_path.read_text())
                usage_data = raw_usage.get("picks", {})
            except Exception:
                pass

        extra_lines = ["\n## PICK CASE BUILDER"]
        extra_lines.append("Use this block to structure your fantasy reasoning. Lead with the 2-3 strongest reasons, then one honest concern, then a clear verdict.\n")

        for pname in player_names:
            parts = pname.lower().split()
            last = parts[-1]
            mask = df["player_name"].apply(lambda n: n.lower().split()[-1] == last)
            if not mask.any():
                mask = df["player_name"].str.lower().str.contains(last, na=False)
            if not mask.any():
                continue
            r = df[mask].iloc[0]
            actual = r["player_name"]

            model_rank  = int(r.get("_model_rank", 999))
            field_size  = len(df)
            win_prob    = float(r.get("win_prob", 0) or 0)
            t10_prob    = float(r.get("top10_prob", 0) or 0)
            t20_prob    = float(r.get("top20_prob", 0) or 0)
            dg_fit      = float(r.get("dg_fit_total", 0) or 0)
            pred_sg_w   = float(r.get("predictive_sg_weighted", 0) or 0)
            sg_total    = float(r.get("season_sg_total", 0) or 0)
            form_trend  = float(r.get("form_trend", 0) or 0)
            mc_last     = int(r.get("missed_cut_last_start", 0) or 0)
            consec_mc   = int(r.get("consecutive_missed_cuts", 0) or 0)
            course_hist = int(max(r.get("hist_times_played", 0) or 0, r.get("course_starts", 0) or 0))
            hist_t10s   = int(r.get("hist_top10s", 0) or 0)
            n_events    = int(r.get("sg_event_count", 0) or 0)

            extra_lines.append(f"### {actual} — Fantasy Pick Case")

            # Field standing — model rank only, no market language
            pct = round((1 - (model_rank - 1) / max(field_size, 1)) * 100)
            standing = f"Model ranks him #{model_rank} of {field_size} in the field (top {100-pct+1}%)"
            extra_lines.append(f"**Field standing**: {standing}")

            # Finish probabilities
            extra_lines.append(
                f"**Model probabilities**: Win {win_prob*100:.1f}% · Top-10 {t10_prob*100:.0f}% · Top-20 {t20_prob*100:.0f}%"
            )

            # Recent results — last 5 starts, most recent first
            # Try exact match, then last-name match
            recent = recent_results_map.get(nk, [])
            if not recent:
                for key, val in recent_results_map.items():
                    if key.split()[-1] == nk.split()[-1]:
                        recent = val
                        break
            if recent:
                result_parts = [f"{pos} ({tname})" for pos, tname in recent]
                extra_lines.append(f"**Recent results**: {' · '.join(result_parts)}")
            else:
                extra_lines.append("**Recent results**: no 2026 results found")

            # Usage remaining — critical for fantasy decision
            usage_entry = None
            for name_key, udata in usage_data.items():
                if _strip_accents(name_key.lower()) == _strip_accents(actual.lower()):
                    usage_entry = udata
                    break
            if usage_entry is not None:
                remaining = usage_entry.get("remaining_uses", 3)
                times_used = usage_entry.get("times_used", 0)
                past = usage_entry.get("tournaments_used", [])
                past_str = ", ".join(
                    f"{t.get('tournament','?')} ({t.get('result','?')})"
                    for t in past
                ) if past else "none yet"
                if remaining == 0:
                    extra_lines.append(f"**Usage**: INELIGIBLE — used all 3 times this season. Past: {past_str}")
                elif remaining == 1:
                    extra_lines.append(
                        f"**Usage**: {remaining} use remaining (used {times_used}x — last chance to play him). Past: {past_str}"
                    )
                else:
                    extra_lines.append(
                        f"**Usage**: {remaining} uses remaining ({times_used} used). Past: {past_str}"
                    )
            else:
                extra_lines.append("**Usage**: 3 uses remaining (not yet used this season)")

            # League-wide usage — from the fantasy site's total_golfer_usages page
            # Match by last name since site uses abbreviated formats like "Fitzpatrick, M"
            last_name = nk.split()[-1] if nk else ""
            lu_entry = None
            # Try exact normalized match first, then last-name fallback
            for key, val in league_usage.items():
                if _strip_accents(key) == _strip_accents(nk):
                    lu_entry = val
                    break
            if lu_entry is None:
                for key, val in league_usage.items():
                    if key.split()[-1] == last_name:
                        lu_entry = val
                        break

            LEAGUE_SIZE = 28
            TOTAL_POOL = LEAGUE_SIZE * 3  # 84 maximum uses across the league
            if lu_entry:
                times = lu_entry["times_used"]
                util  = lu_entry["util_pct"]
                # Thresholds based on 84 total possible uses (28 teams × 3):
                #   > 20 uses (~25%+) = high-demand chalk, many teams have already spent uses
                #   10-20 uses = moderate popularity
                #   < 10 uses = low demand, others are avoiding or overlooking him
                if times >= 20:
                    scarcity = (
                        f"HIGH DEMAND — {times}/{TOTAL_POOL} total uses ({util}%). "
                        f"Roughly {max(1, times // 3)}+ teams have used him multiple times. "
                        f"If your uses are still available, protect them carefully."
                    )
                elif times >= 10:
                    scarcity = (
                        f"MODERATE — {times}/{TOTAL_POOL} uses ({util}%). "
                        f"A fair number of teams have used him but he's not yet exhausted across the league."
                    )
                else:
                    scarcity = (
                        f"LOW DEMAND — {times}/{TOTAL_POOL} uses ({util}%). "
                        f"Most teams are not targeting him — either a contrarian value pick or the field is cold on him."
                    )
                extra_lines.append(
                    f"**League usage** (season total, 28 teams × max 3 = 84 pool): {times} uses ({util}%) — {scarcity}"
                )
            else:
                extra_lines.append(
                    "**League usage**: not found in league tracker — likely unused or first-time pick across the league"
                )

            # Key model drivers
            drivers = []
            if pred_sg_w > 0.3:
                drivers.append(f"elite predictive SG ({pred_sg_w:+.3f}/round on course-weighted skills)")
            elif pred_sg_w > 0.1:
                drivers.append(f"solid predictive SG ({pred_sg_w:+.3f}/round)")
            if dg_fit > 0.2:
                drivers.append(f"strong course-fit score ({dg_fit:+.3f}) — game matches what wins here")
            elif dg_fit > 0.05:
                drivers.append(f"positive course fit ({dg_fit:+.3f})")
            if sg_total > 0.5:
                drivers.append(f"strong season SG total ({sg_total:+.3f}/round)")
            if hist_t10s >= 2 and course_hist >= 3:
                drivers.append(f"{hist_t10s} top-10s in {course_hist} starts at this venue")
            elif hist_t10s >= 1 and course_hist >= 2:
                drivers.append(f"top-10 history here ({hist_t10s} in {course_hist} starts)")
            if form_trend > 0.5:
                drivers.append("form is trending up coming into this week")
            if n_events >= 3 and sg_total > 0.2:
                drivers.append(f"consistent form across {n_events} events this season")

            if drivers:
                extra_lines.append("**Why the model likes him**:")
                for d in drivers[:4]:
                    extra_lines.append(f"  - {d}")

            # Expert consensus
            exp_count = expert_counts.get(nk, 0)
            if exp_count > 0:
                extra_lines.append(
                    f"**Expert consensus**: appears in {exp_count} expert lineups "
                    f"({exp_count/max(1,sum(v > 0 for v in expert_counts.values()))*100:.0f}% of experts have him)"
                )
            else:
                extra_lines.append("**Expert consensus**: not widely held by experts — either contrarian or overlooked")

            # Honest concerns
            concerns = []
            if usage_entry and usage_entry.get("remaining_uses", 3) == 0:
                concerns.append("INELIGIBLE — no uses remaining this season")
            elif usage_entry and usage_entry.get("remaining_uses", 3) == 1:
                concerns.append("only 1 use left — consider saving for a stronger spot")
            if mc_last:
                concerns.append("missed the cut last start")
            if consec_mc >= 2:
                concerns.append(f"missed {consec_mc} cuts in a row — form is questionable")
            if form_trend < -0.5:
                concerns.append("form trend is declining recently")
            if course_hist < 2:
                concerns.append(f"limited course history ({course_hist} starts) — unknown quantity here")
            elif course_hist >= 3 and hist_t10s == 0:
                concerns.append(f"no top-10s in {course_hist} previous starts at this course")
            if dg_fit < -0.1:
                concerns.append(f"course fit is negative ({dg_fit:.3f}) — this track may not suit his game")
            if pred_sg_w < 0 and sg_total < 0:
                concerns.append("SG is below field average — model may be overstating his chances")
            if n_events < 4:
                concerns.append(f"only {n_events} events tracked this season — small sample size")

            if concerns:
                extra_lines.append("**Honest concerns**:")
                for c in concerns[:3]:
                    extra_lines.append(f"  - {c}")
            else:
                extra_lines.append("**Honest concerns**: no major red flags — clean case")

            extra_lines.append("")

        return base + "\n" + "\n".join(extra_lines)

    except Exception as e:
        return base + f"\n\n## PICK CASE BUILDER\n(unavailable: {e})"


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
            name   = row["player_name"]
            wr     = row.get("world_rank")
            wr_str = f"World #{int(wr)}" if pd.notna(wr) else ""
            last   = _last_result(row)
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

            # Append critical extras: course scoring avg, par-3 concern, R4 closing, projection
            extras = []
            avg_to_par = row.get("course_avg_to_par")
            c_scoring  = row.get("course_stat_120_scoring_average_weighted")
            if pd.notna(avg_to_par) and int(row.get("hist_times_played", 0) or 0) >= 2:
                extras.append(f"avg {float(avg_to_par):+.1f}/tournament here")
            elif pd.notna(c_scoring) and int(row.get("hist_times_played", 0) or 0) >= 2:
                extras.append(f"scoring avg {float(c_scoring):.1f}/round here")

            par3_rank = row.get("par3_scoring_field_rank")
            if pd.notna(par3_rank):
                r = int(par3_rank)
                if r <= 10:
                    extras.append("elite par-3 scorer")
                elif r > full_field_size * 0.75:
                    extras.append(f"poor par-3 scorer (#{r}) — concern at this course")

            r4_pct = row.get("recent_r4_avg_field_pct")
            r4_val = row.get("recent_r4_avg")
            if pd.notna(r4_pct) and pd.notna(r4_val):
                if float(r4_pct) >= 0.9:
                    extras.append(f"elite Sunday closer (avg {float(r4_val):+.1f})")
                elif float(r4_pct) <= 0.2:
                    extras.append(f"fades on Sundays (avg {float(r4_val):+.1f})")

            proj = row.get("projected_score")
            if pd.notna(proj):
                extras.append(f"projected {float(proj):+.1f} for the week")

            if extras:
                line += f" Key: {' · '.join(extras)}."
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


def _live_odds_context_block(tid: str) -> str:
    """In-play win odds + pre-tournament movement for live responses.

    Joins:
      - live leaderboard (current position + live odds_to_win)
      - pre-tournament DK odds (dk_odds_R{tid}.csv)
      - current prop lines (top5/top10 markets)
    Computes odds movement and derives market signals.
    """
    if not tid:
        return ""
    tid_lower = tid.lower()
    lb_path    = DATA / "live"  / f"leaderboard_{tid_lower}.csv"
    pre_path   = DATA / "odds"  / f"dk_odds_{tid}.csv"
    props_path = DATA / "odds"  / f"prop_lines_{tid}.csv"

    if not lb_path.exists():
        return ""
    try:
        lb = pd.read_csv(lb_path)
        if lb.empty or "odds_to_win" not in lb.columns:
            return ""

        lb["player_name"] = lb["player_name"].apply(_fmt_name)
        top15 = lb.head(15).copy()

        # Pre-tournament odds for movement comparison
        pre_map: dict[str, float] = {}
        if pre_path.exists():
            try:
                pre = pd.read_csv(pre_path)
                pre["player_name"] = pre["player_name"].apply(_fmt_name)
                for _, row in pre.iterrows():
                    pre_map[row["player_name"]] = float(row.get("dk_odds_numeric", row.get("dk_odds", 0)) or 0)
            except Exception:
                pass

        # Top-5 and Top-10 odds lookup
        top5_map:  dict[str, str] = {}
        top10_map: dict[str, str] = {}
        if props_path.exists():
            try:
                props = pd.read_csv(props_path)
                props["player_name"] = props["player_name"].apply(_fmt_name)
                for mkt, out_map in [("top5", top5_map), ("top10", top10_map)]:
                    sub = props[props["market"] == mkt]
                    for _, row in sub.iterrows():
                        o = float(row.get("odds", 0) or 0)
                        out_map[row["player_name"]] = _fmt_odds(o)
            except Exception:
                pass

        rows = []
        for _, r in top15.iterrows():
            name  = r["player_name"]
            pos   = str(r.get("position", "?"))
            total = str(r.get("total", "?"))
            cur_o = r.get("odds_to_win")
            if pd.isna(cur_o):
                continue

            cur_o = float(cur_o)
            cur_str = _fmt_odds(cur_o)
            imp_cur = _american_to_implied(cur_o)

            # Movement vs pre-tournament
            pre_o = pre_map.get(name)
            if pre_o and pre_o > 0:
                imp_pre = _american_to_implied(pre_o)
                if imp_pre and imp_cur:
                    move_pct = (imp_cur - imp_pre) / imp_pre * 100
                    arrow = "▼" if move_pct > 5 else ("▲" if move_pct < -5 else "→")
                    pre_str = _fmt_odds(pre_o)
                    move_str = f"{arrow} (was {pre_str}, {move_pct:+.0f}% probability shift)"
                else:
                    move_str = ""
            else:
                move_str = "(no pre-tournament line)"

            t5_str  = top5_map.get(name, "—")
            t10_str = top10_map.get(name, "—")

            rows.append(
                f"- **{name}** | {pos} ({total}) | Win: {cur_str} "
                f"({imp_cur*100:.0f}% implied) {move_str} | T5: {t5_str} | T10: {t10_str}"
            )

        if not rows:
            return ""

        # Market signal: who is the market most confident about?
        contenders = top15[top15["odds_to_win"].notna()].copy()
        contenders["_imp"] = contenders["odds_to_win"].apply(
            lambda x: _american_to_implied(float(x)) or 0
        )
        top_pick = contenders.nlargest(1, "_imp").iloc[0]["player_name"] if not contenders.empty else ""

        # Biggest odds move (largest probability shift)
        biggest_move = ""
        best_shift = 0.0
        for _, r in contenders.iterrows():
            name  = r["player_name"]
            pre_o = pre_map.get(name)
            cur_o = float(r["odds_to_win"])
            if pre_o and pre_o > 0:
                ip = _american_to_implied(cur_o) or 0
                pp = _american_to_implied(pre_o) or 0
                if pp > 0:
                    shift = (ip - pp) / pp
                    if shift > best_shift:
                        best_shift = shift
                        biggest_move = f"{name} ({_fmt_odds(pre_o)} → {_fmt_odds(cur_o)}, +{shift*100:.0f}% prob shift)"

        lines = ["## IN-PLAY WIN ODDS & MARKET MOVEMENT"]
        lines.append("Current DraftKings win odds + movement since pre-tournament open. Use this to reason about market confidence and value.")
        lines.append("")
        lines += rows
        lines.append("")
        if top_pick:
            lines.append(f"**Market leader**: {top_pick} is the market's top choice to win.")
        if biggest_move:
            lines.append(f"**Biggest mover**: {biggest_move} — market has heavily re-priced this player.")
        lines.append("")
        lines.append("NOTE: Win odds reflect current tournament position. T5/T10 odds reflect remaining rounds.")

        return "\n".join(lines)
    except Exception as e:
        return f"## IN-PLAY ODDS\n(unavailable: {e})"


def _live_tournament_stats_block(tid: str) -> str:
    """Live in-tournament SG and stats from scorecardStatsComparison.

    Reads data/live/live_tournament_stats_{tid}.json (written by fetch_live_tournament_stats.py).
    Shows SG total/OTT/APP/ATG/PUTT for leaderboard players, with field ranks.
    Far more relevant than season stats for mid-tournament analysis.
    """
    if not tid:
        return ""
    path = DATA / "live" / f"live_tournament_stats_{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)

        player_map: dict[str, str] = data.get("player_map", {})
        categories    = data.get("categories", {})
        fetched_at    = data.get("fetched_at", "")[:16].replace("T", " ")
        rounds_done   = data.get("rounds_fetched", [])
        current_round = data.get("current_round", "?")

        if not categories:
            return ""

        # Use cumulative (sum of per-round values) — matches PGA Tour website display
        sg_data = categories.get("STROKES_GAINED", {}).get("cumulative", {})
        scoring  = categories.get("SCORING",       {}).get("cumulative", {})
        driving  = categories.get("OFF_TEE",       {}).get("cumulative", {})

        # Order players by leaderboard position (same order as player_ids list)
        ordered_pids = data.get("player_ids", list(player_map.keys()))

        rnd_label = f"through Round {max(rounds_done, key=int)}" if rounds_done else f"Round {current_round}"
        lines = [
            f"## LIVE TOURNAMENT STATS — {tid} ({rnd_label}, as of {fetched_at} UTC)",
            "Cumulative strokes gained vs field — matches PGA Tour website. More relevant than season stats.",
            "Values = total SG accumulated over completed rounds (not per-round average). Rank = field position.",
            "",
        ]

        # SG table
        sg_cat_labels = [
            ("SG: Total",              "SG Tot"),
            ("SG: Off the Tee",        "OTT"),
            ("SG: Approach the Green", "APP"),
            ("SG: Around the Green",   "ATG"),
            ("SG: Putting",            "PUTT"),
        ]
        lines.append("**Strokes Gained — This Tournament:**")
        header_cols = ["Player"] + [lbl for _, lbl in sg_cat_labels]
        rows = []
        for pid in ordered_pids:
            if pid not in sg_data:
                continue
            name  = _fmt_name(player_map.get(pid, f"ID:{pid}"))
            p_row = [name]
            for stat_name, _ in sg_cat_labels:
                entry = sg_data[pid].get(stat_name, {})
                val   = entry.get("value", None)
                rank  = entry.get("rank",  "—")
                try:
                    val_str = f"{float(val):+.3f}"
                except (TypeError, ValueError):
                    val_str = "—"
                p_row.append(f"{val_str} (#{rank})")
            rows.append(p_row)

        if rows:
            # Format as simple markdown table
            col_widths = [max(len(str(r[i])) for r in [header_cols] + rows) for i in range(len(header_cols))]
            def _fmt_row(r):
                return "| " + " | ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(r))) + " |"
            lines.append(_fmt_row(header_cols))
            lines.append("|" + "|".join("-" * (w + 2) for w in col_widths) + "|")
            for r in rows:
                lines.append(_fmt_row(r))

        # Key insight lines from the data
        lines.append("")
        lines.append("**Tournament leaders by SG category:**")
        for stat_name, short in sg_cat_labels:
            best_pid  = None
            best_val  = -999.0
            for pid in ordered_pids:
                entry = sg_data.get(pid, {}).get(stat_name, {})
                try:
                    v = float(entry.get("value", -999))
                    if v > best_val:
                        best_val = v
                        best_pid = pid
                except (TypeError, ValueError):
                    pass
            if best_pid and best_val > -999:
                name = _fmt_name(player_map.get(best_pid, best_pid))
                rank = sg_data.get(best_pid, {}).get(stat_name, {}).get("rank", "?")
                lines.append(f"  - {short}: **{name}** ({best_val:+.3f} cumulative, #{rank} in field)")

        # Scoring stats if available
        if scoring:
            lines.append("")
            lines.append("**Scoring stats this tournament (birdies, bogeys, scoring avg):**")
            for pid in ordered_pids[:8]:
                if pid not in scoring:
                    continue
                name = _fmt_name(player_map.get(pid, pid))
                parts = []
                for stat_name, stat_data in scoring[pid].items():
                    val  = stat_data.get("value", "")
                    rank = stat_data.get("rank",  "")
                    if val and val != "—":
                        parts.append(f"{stat_name}: {val} (#{rank})")
                if parts:
                    lines.append(f"  - {name}: {' · '.join(parts[:3])}")

        return "\n".join(lines)
    except Exception as e:
        return f"## LIVE TOURNAMENT STATS\n(unavailable: {e})"


def _live_course_stats_block(tid: str) -> str:
    """Live hole-by-hole course stats for the current tournament."""
    if not tid:
        return ""
    path = DATA / "live" / f"course_stats_{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            d = json.load(f)

        holes = d.get("holes", [])
        if not holes:
            return ""

        def _pct(val: str) -> str:
            return str(val).replace("%", "").strip() + "%"

        fetched = d.get("fetched_at", "")[:16].replace("T", " ")
        lines = [
            f"## LIVE COURSE STATS — {d.get('course_name', tid)} (as of {fetched} UTC)",
            f"Par {d.get('par')} | {d.get('yardage')} yards — scoring averages vs par across all completed rounds this week.",
            "",
        ]

        # Sort by scoring average descending for hardest/easiest context
        sorted_holes = sorted(holes, key=lambda h: float(h["scoringAverage"]), reverse=True)
        hardest = sorted_holes[:4]
        easiest = sorted_holes[-3:]

        lines.append("**Hardest holes this week** (where scores are lost):")
        for h in hardest:
            avg = float(h["scoringAverage"])
            lines.append(
                f"  Hole {h['holeNum']:2d}: avg {avg:+.3f} vs par | "
                f"birdie {_pct(h['birdiesPercent'])} | bogey {_pct(h['bogeysPercent'])} | dbl+ {_pct(h['doubleBogeysPercent'])}"
            )

        lines.append("")
        lines.append("**Easiest holes this week** (birdie opportunities):")
        for h in reversed(easiest):
            avg = float(h["scoringAverage"])
            lines.append(
                f"  Hole {h['holeNum']:2d}: avg {avg:+.3f} vs par | "
                f"birdie {_pct(h['birdiesPercent'])} | bogey {_pct(h['bogeysPercent'])}"
            )

        lines.append("")
        lines.append("**All holes** (hole | avg vs par | birdie% | bogey%):")
        for h in sorted(holes, key=lambda h: h["holeNum"]):
            avg = float(h["scoringAverage"])
            lines.append(
                f"  H{h['holeNum']:2d}  {avg:+.3f}  birdie={_pct(h['birdiesPercent'])}  bogey={_pct(h['bogeysPercent'])}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"## LIVE COURSE STATS\n(unavailable: {e})"


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


def _course_fit_reasoning_block(tid: str | None) -> str:
    """
    Data-driven course demand reasoning: what skills historically win at this venue.
    Loads hole data (current year first, then historical fallback).
    Derives: hardest holes, birdie holes, par-3 difficulty, finish strength needed.
    """
    if not tid:
        return ""

    year = datetime.now().year
    course_df = None

    # 1. Try current year file
    cur_path = DATA / "course_characteristics" / f"all_courses_{year}.csv"
    if cur_path.exists():
        try:
            df = pd.read_csv(cur_path)
            subset = df[df["tournament_id"] == tid]
            if not subset.empty:
                course_df = subset.copy()
        except Exception:
            pass

    # 2. Fallback to historical file (same course, different year)
    if course_df is None or course_df.empty:
        hist_path = DATA / "course_characteristics" / "all_courses_historical_2023_2025.csv"
        if hist_path.exists():
            try:
                df = pd.read_csv(hist_path)
                # Match by tournament_id pattern (e.g. R2026011 → R2023011)
                base_id = tid[-3:]  # last 3 chars = event number e.g. "011"
                mask = df["tournament_id"].astype(str).str.endswith(base_id)
                subset = df[mask]
                if not subset.empty:
                    # Average across years for more stable estimates
                    course_df = subset.groupby("hole_num", as_index=False).agg(
                        hole_par=("hole_par", "first"),
                        hole_yards=("hole_yards", "mean"),
                        scoring_avg=("scoring_avg", "mean"),
                        scoring_diff=("scoring_diff", "mean"),
                    )
                    # Get course name from most recent year
                    course_name = df[mask]["course_name"].iloc[-1] if "course_name" in df.columns else ""
                    tournament_name = df[mask]["tournament_name"].iloc[-1] if "tournament_name" in df.columns else tid
            except Exception:
                pass

    if course_df is None or course_df.empty:
        return ""

    try:
        h = course_df.copy()
        if "course_name" not in locals():
            course_name = h.get("course_name", pd.Series([""])).iloc[0] if "course_name" in h.columns else ""
            tournament_name = h.get("tournament_name", pd.Series([tid])).iloc[0] if "tournament_name" in h.columns else tid

        par_counts = h.groupby("hole_par")["hole_num"].count()
        n_par3 = int(par_counts.get(3, 0))
        n_par4 = int(par_counts.get(4, 0))
        n_par5 = int(par_counts.get(5, 0))
        course_par = int(h["hole_par"].sum()) if len(h) == 18 else 72

        # Scoring stats by par type
        par3_avg_diff = h[h["hole_par"] == 3]["scoring_diff"].mean()
        par4_avg_diff = h[h["hole_par"] == 4]["scoring_diff"].mean()
        par5_avg_diff = h[h["hole_par"] == 5]["scoring_diff"].mean()

        # Hardest 3 holes (highest scoring_diff = most over par)
        hardest = h.nlargest(3, "scoring_diff")[["hole_num", "hole_par", "hole_yards", "scoring_diff"]]
        # Best birdie holes (lowest scoring_diff = most under par)
        birdie_holes = h.nsmallest(3, "scoring_diff")[["hole_num", "hole_par", "hole_yards", "scoring_diff"]]

        # Finish strength: how hard is the closing stretch (last 4 holes)?
        last4 = h[h["hole_num"] >= 15]["scoring_diff"].mean() if len(h[h["hole_num"] >= 15]) >= 3 else None

        lines = [f"## COURSE FIT REASONING: {tournament_name} ({course_name or tid})"]
        lines.append(f"Par {course_par} | {n_par3} par-3s, {n_par4} par-4s, {n_par5} par-5s | Data averaged from 2023–2025")
        lines.append("")

        # Par-type difficulty
        lines.append("**What this course demands (by the numbers):**")
        if pd.notna(par3_avg_diff):
            p3_desc = "hard — above-par scoring" if par3_avg_diff > 0.05 else ("easy — birdie opportunities" if par3_avg_diff < -0.05 else "neutral")
            lines.append(f"- Par 3s ({n_par3} holes): avg {par3_avg_diff:+.3f} vs par — {p3_desc}. Iron precision from the tee is {'critical' if par3_avg_diff > 0.05 else 'less of a factor'}.")
        if pd.notna(par4_avg_diff):
            p4_desc = "penal — mistakes are punished" if par4_avg_diff > 0.08 else ("scoring opportunities" if par4_avg_diff < 0 else "neutral")
            lines.append(f"- Par 4s ({n_par4} holes): avg {par4_avg_diff:+.3f} vs par — {p4_desc}. {'Accuracy and scrambling matter here.' if par4_avg_diff > 0.05 else ''}")
        if pd.notna(par5_avg_diff):
            p5_desc = "birdie opportunities — must convert" if par5_avg_diff < -0.15 else ("difficult par 5s" if par5_avg_diff > 0 else "modest birdie holes")
            lines.append(f"- Par 5s ({n_par5} holes): avg {par5_avg_diff:+.3f} vs par — {p5_desc}.")

        # Hardest holes
        lines.append("")
        lines.append("**Hardest holes (where tournaments are lost):**")
        for _, row in hardest.iterrows():
            lines.append(f"- Hole {int(row['hole_num'])} (Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): avg {row['scoring_diff']:+.3f} vs par")

        # Birdie holes
        lines.append("")
        lines.append("**Birdie opportunities (where tournaments are won):**")
        for _, row in birdie_holes.iterrows():
            lines.append(f"- Hole {int(row['hole_num'])} (Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): avg {row['scoring_diff']:+.3f} vs par")

        # Closing stretch
        if pd.notna(last4):
            close_desc = "brutal finish" if last4 > 0.15 else ("demanding" if last4 > 0.05 else "manageable")
            lines.append("")
            lines.append(f"**Closing stretch (holes 15–18)**: avg {last4:+.3f} vs par — {close_desc}. {'Closing ability and nerves are decisive.' if last4 > 0.05 else ''}")

        # Derived skill requirements
        lines.append("")
        lines.append("**KEY SKILL REQUIREMENTS derived from scoring data:**")
        if par3_avg_diff > 0.05:
            lines.append(f"- IRON PLAY FROM THE TEE: par 3s average +{par3_avg_diff:.3f} — players who miss par-3 greens bleed bogeys. Par-3 field rank is a direct predictor here.")
        if par4_avg_diff > 0.06:
            lines.append(f"- SCRAMBLING & SHORT GAME: par 4s average +{par4_avg_diff:.3f} — greens are missed regularly; recovery skill separates the field. Around-green SG and scrambling % are critical.")
        if par5_avg_diff < -0.15:
            lines.append(f"- PAR-5 CONVERSION: par 5s average {par5_avg_diff:.3f} — players who can't birdie the par 5s fall behind. Par-5 scoring rank matters.")
        if last4 and last4 > 0.10:
            lines.append(f"- CLOSING ABILITY: the final 4 holes average +{last4:.3f} — players who can't close the back nine fade. R4 scoring average is a key predictor.")

        return "\n".join(lines)
    except Exception as e:
        return f"## COURSE FIT REASONING\n(unavailable: {e})"


def _course_fit_players_block(tid: str | None, top_n: int = 12) -> str:
    """Map field players to course demands derived from hole scoring data.

    For each key skill requirement (iron play, scrambling, par-5 conversion, closing),
    show the top 5 players in the field ranked by that specific stat.
    Only emits sections for demands that are clearly present at this course.
    """
    if not tid:
        return ""

    # Need course demand data first
    year = datetime.now().year
    course_df = None

    cur_path = DATA / "course_characteristics" / f"all_courses_{year}.csv"
    if cur_path.exists():
        try:
            df = pd.read_csv(cur_path)
            subset = df[df["tournament_id"] == tid]
            if not subset.empty:
                course_df = subset.copy()
        except Exception:
            pass

    if course_df is None or course_df.empty:
        hist_path = DATA / "course_characteristics" / "all_courses_historical_2023_2025.csv"
        if hist_path.exists():
            try:
                df = pd.read_csv(hist_path)
                base_id = tid[-3:]
                mask = df["tournament_id"].astype(str).str.endswith(base_id)
                subset = df[mask]
                if not subset.empty:
                    course_df = subset.groupby("hole_num", as_index=False).agg(
                        hole_par=("hole_par", "first"),
                        scoring_diff=("scoring_diff", "mean"),
                    )
            except Exception:
                pass

    preds_path = OUTPUTS / "latest_predictions.csv"
    if not preds_path.exists():
        return ""

    try:
        preds = pd.read_csv(preds_path)
        preds["player_name"] = preds["player_name"].apply(_fmt_name)
        preds = preds.sort_values("win_prob", ascending=False).head(top_n).copy()

        sections = ["## COURSE FIT — TOP PLAYERS BY SKILL DEMAND"]

        # Determine demands from hole data if available
        demands = {}
        if course_df is not None and not course_df.empty:
            h = course_df
            par3_diff = h[h["hole_par"] == 3]["scoring_diff"].mean() if "hole_par" in h.columns else None
            par4_diff = h[h["hole_par"] == 4]["scoring_diff"].mean() if "hole_par" in h.columns else None
            par5_diff = h[h["hole_par"] == 5]["scoring_diff"].mean() if "hole_par" in h.columns else None
            last4_diff = h[h["hole_num"] >= 15]["scoring_diff"].mean() if "hole_num" in h.columns and len(h[h["hole_num"] >= 15]) >= 3 else None

            if par3_diff is not None and par3_diff > 0.05:
                demands["iron_play"] = ("SG Approach (Iron Play from Tee)", "season_sg_app_field_rank", "season_sg_app", par3_diff, "par-3")
            if par4_diff is not None and par4_diff > 0.06:
                demands["scrambling"] = ("Around-Green / Scrambling", "season_sg_arg_field_rank", "season_sg_arg", par4_diff, "par-4")
            if par5_diff is not None and par5_diff < -0.15:
                demands["par5"] = ("Par-5 Conversion (Distance + Power)", "season_sg_ott_field_rank", "season_sg_ott", par5_diff, "par-5")
            if last4_diff is not None and last4_diff > 0.10:
                demands["closing"] = ("Closing Ability (R4 Scoring)", "recent_r4_avg_field_pct", "recent_r4_avg", last4_diff, "finish")

        # Always include overall SG and approach as a baseline
        if "iron_play" not in demands:
            demands["approach"] = ("SG Approach (Iron Play)", "season_sg_app_field_rank", "season_sg_app", None, "overall")
        demands["sg_total"] = ("Overall Strokes Gained (Total)", "season_sg_total_field_rank", "season_sg_total", None, "overall")
        demands["putting"] = ("Putting (SG Putt)", "season_sg_putt_field_rank", "season_sg_putt", None, "putting")
        demands["course_history"] = ("Course History", "hist_times_played", "hist_avg_finish", None, "history")

        for key, (label, rank_col, val_col, diff, hole_type) in demands.items():
            diff_str = f" (course demands: {diff:+.3f} avg vs par on {hole_type}s)" if diff is not None else ""
            sections.append(f"\n**{label}**{diff_str}:")

            if key == "course_history":
                # Sort by most starts + best avg finish
                sub = preds.copy()
                sub["_starts"] = sub.get("hist_times_played", pd.Series(0, index=sub.index)).fillna(0)
                sub["_avg"]    = sub.get("hist_avg_finish",   pd.Series(999, index=sub.index)).fillna(999)
                sub = sub[sub["_starts"] >= 1].sort_values(["_starts", "_avg"], ascending=[False, True]).head(5)
                for _, row in sub.iterrows():
                    starts = int(row.get("hist_times_played", 0) or 0)
                    wins   = int(row.get("hist_wins", 0) or 0)
                    avg_f  = row.get("hist_avg_finish")
                    avg_s  = row.get("hist_avg_finish")
                    win_str = " · WON here" if wins else ""
                    avg_str = f" · avg finish T{int(float(avg_s))}" if pd.notna(avg_s) else ""
                    sections.append(f"  - {row['player_name']}: {starts} start{'s' if starts != 1 else ''}{win_str}{avg_str}")
            elif key == "closing":
                # Sort by R4 scoring (best R4 field pct = highest pct value)
                sub = preds.copy()
                if "recent_r4_avg_field_pct" in sub.columns:
                    sub = sub.dropna(subset=["recent_r4_avg_field_pct"]).sort_values("recent_r4_avg_field_pct", ascending=False).head(5)
                    for _, row in sub.iterrows():
                        r4_val = row.get("recent_r4_avg")
                        r4_pct = float(row["recent_r4_avg_field_pct"])
                        val_str = f" (avg R4: {float(r4_val):+.1f}/round)" if pd.notna(r4_val) else ""
                        pct_str = f" #{int(r4_pct * len(preds))} in field" if pd.notna(r4_pct) else ""
                        sections.append(f"  - {row['player_name']}{val_str}{pct_str}")
                else:
                    sections.append("  (R4 data not available)")
            else:
                # Sort by rank column (ascending = better rank = #1 is best)
                if rank_col in preds.columns:
                    sub = preds.dropna(subset=[rank_col]).sort_values(rank_col, ascending=True).head(5)
                    for _, row in sub.iterrows():
                        rank = row.get(rank_col)
                        val  = row.get(val_col)
                        rank_str = f"#{int(rank)} in field" if pd.notna(rank) else ""
                        val_str  = f"{float(val):+.3f} SG/round" if pd.notna(val) else ""
                        combined = " · ".join(filter(None, [val_str, rank_str]))
                        sections.append(f"  - {row['player_name']}: {combined}")
                else:
                    sections.append(f"  ({rank_col} not available in data)")

        return "\n".join(sections)
    except Exception as e:
        return f"## COURSE FIT — TOP PLAYERS BY SKILL\n(unavailable: {e})"


def _recommended_bets_block(top_n: int = 10) -> str:
    """Top recommended bets — prefers live (mid-tournament) file over pre-tournament file."""
    # Try live file first (generated by generate_live_bets.py during scheduled refresh)
    tid = _detect_tournament_id()
    live_path = (DATA / "odds" / f"recommended_bets_live_{tid}.csv") if tid else None
    static_path = DATA / "odds" / "recommended_bets_latest.csv"

    is_live = bool(live_path and live_path.exists())
    path = live_path if is_live else static_path

    if not path or not path.exists():
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
        if "live_score_rank" in df.columns:
            out["Live Rank"] = df["live_score_rank"].apply(lambda x: f"#{int(x)}" if pd.notna(x) and x < 900 else "—")
        if "rounds_complete" in df.columns:
            rc = df["rounds_complete"].iloc[0]
            rounds_note = f"Based on {int(rc)}-round live position + Monte Carlo simulation."
        else:
            rounds_note = ""

        source_label = "LIVE (mid-tournament)" if is_live else "PRE-TOURNAMENT MODEL"
        note = (
            f"Source: {source_label}. "
            + rounds_note + " "
            + "Each row is a specific market. 'Book Says' = book's implied probability (no-vig). "
            "'We Think' = our live probability estimate based on current leaderboard position."
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
        _round_done_statuses = {"official", "complete", "completed", "final"}
        if r == 4 and rs in _round_done_statuses:
            state["phase"] = "complete"
        elif r == 0 or rs in _pre_play_statuses:
            state["phase"] = "pre_tournament"
        elif rs in _round_done_statuses:
            # Round r is fully official — all scores are in
            state["phase"] = f"round_{r}"
        else:
            # Round r is actively in progress (some players still on course)
            state["phase"] = f"round_{r}_in_progress"
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
    elif phase.endswith("_in_progress"):
        # Round is actively being played — scores are live but not all players are done
        rounds_remaining = 4 - r
        status_line = f"ROUND {r} OF 4 IN PROGRESS — some players still on course."
        instruction = (
            f"Round {r} is CURRENTLY BEING PLAYED — do NOT say it is complete. "
            "The leaderboard shows live scoring and positions may still change today. "
            "Focus on who is leading, who is making moves, and who is fading. "
            f"Rounds remaining after today: {rounds_remaining - 1}. "
            f"A player needs to be within ~{max(4, rounds_remaining * 4)} strokes to have a realistic chance. "
            "Betting questions: focus on in-play value. "
            "Lineup questions: picks are locked for this week."
        )
    else:
        # Round is fully official
        rounds_remaining = 4 - r
        status_line = f"ROUND {r} OF 4 COMPLETE (OFFICIAL) — {rounds_remaining} round(s) remaining."
        instruction = (
            f"Round {r} scores are official. We are mid-tournament. "
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
Communicate like a knowledgeable golf fan talking to another fan — plain English, backed by specific data.

FORMATTING RULES:
- Lead with the direct answer in the first sentence. Then give reasoning.
- Bold player names using **Name** on first mention.
- Bold key numbers: finish positions, averages, streak numbers.
- Use bullet lists for comparisons and multi-part reasoning.
- Short paragraphs (2-4 sentences). No walls of text.

HEAD-TO-HEAD STRUCTURE — for comparison questions ("X vs Y", "X or Y", "compare X and Y"):
  0. One-sentence verdict (bold) — pick one player directly, no hedging
  1. Form edge — label it "FORM EDGE: [Name]". State: last start result, consecutive cuts, top-5s this season, scoring avg. Pick the winner clearly. No contradictions.
  2. Course history edge — label it "COURSE HISTORY EDGE: [Name]". State: starts, wins, avg to par, course-specific SG if available. Pick one winner.
  3. Strokes Gained — use a markdown table: Category | Player A (value, rank) | Player B (value, rank) | Edge. One row per category. After the table, 1-2 sentence summary of who wins the SG battle overall and why.
  4. Traditional stats — use a markdown table: Stat | Player A | Player B | Edge. Cover driving dist/acc, GIR, scrambling, putts/round, birdies/round.
  5. Course fit — use the COURSE FIT REASONING block. State the actual scoring data for what this course demands (e.g. "par 3s avg +0.09 over par — iron precision critical; par 4s avg +0.07 — scrambling separates the field"). Then map each player's specific stats to those demands. Be explicit: who wins each demand category and why.
  6. Round tendencies — table: Round | Player A | Player B. Then one sentence on who is the better closer.
  7. Counter-argument — 2 sentences making the strongest possible case FOR the losing player. Start with "The case for [Name]:". Then explain why it still isn't enough.
  8. Final pick — 2-3 sentences. Name the winner. Cite the 2-3 decisive stats. Be direct.
  RULES: State each category winner ONCE, clearly. No self-corrections mid-paragraph. No hedging. If a stat seems off due to small sample, note it once and move on. Pick one player.

RESPONSE STRUCTURE — for player questions ("is X good?", "why X?", "tell me about X"):
  0. One-sentence quick verdict (bold) — lead with your take before any data
  1. Season snapshot + recent form (This season: X starts, X wins, X top-5s. Last start: T# or MC. Consecutive cuts.)
  2. Course history at THIS venue (X starts, wins/top-5s, avg score to par, course-specific SG if available)
  3. Strokes Gained breakdown — cite all categories with raw value + field rank
  4. Ball striking stats (driving dist/acc, GIR, scrambling) + Scoring stats (putts/round, birdies/round, bogey%)
  5. Par scoring by hole type + Round tendencies (all 4 round avgs) + projection range (median, floor, ceiling)
  6. Why pick him THIS week — cite the COURSE FIT REASONING block. State 2-3 specific demands this course makes (with the actual scoring data, e.g. "par 3s avg +0.09 over par here — iron precision from the tee is critical") and map each demand directly to the player's specific stats. This is the "why it matters THIS week" paragraph.
  7. One-sentence YES / NO / WAIT recommendation — compare to 1-2 other top players if relevant
  Do NOT add a betting or odds section unless the user explicitly asked about betting.
  Every claim must reference a specific number — no editorializing or parenthetical explanations.

DATA RULES — READ CAREFULLY AND FOLLOW EXACTLY:
- The PLAYER SPOTLIGHT block contains exact numbers. YOU MUST QUOTE THEM VERBATIM. Do not paraphrase, round, or replace with adjectives.
- Do NOT say "strong recent form" → say "T3 last start, 4 top-10s in last 5, 8 consecutive cuts made"
- Do NOT say "he plays well here" → say "3 starts here, 1 win, averages -4.2 per tournament"
- Do NOT say "strong approach player" → say "approach: +0.53 SG/round, #20 in field"
- Do NOT say "strong off the tee (top-15)" → say "off the tee: +0.699 SG/round, #14 in field"

REQUIRED EXAMPLE — your SG section MUST look like this:
  Strokes Gained: total +0.85/round · off the tee +0.699/round (#14 in field) · approach +0.244/round (#31) · around green +0.610/round (#5) · putting +0.479/round (#28)

REQUIRED EXAMPLE — your traditional stats section MUST look like this:
  306 yds driving distance · 58.9% driving accuracy · 77.8% GIR · 87.5% scrambling · 1.86 putts/round · 4.50 birdies/round (#34)

REQUIRED EXAMPLE — your round tendencies MUST look like this:
  Round avgs: R1 -2.8 | R2 -2.4 | R3 -1.2 | R4 -4.1 (elite Sunday closer)

REQUIRED EXAMPLE — your course history MUST look like this:
  9 starts · WON 2x · 2 top-5s · best finish T1 · avg finish T16 · avg -8.0 per tournament

CITE THESE FROM THE PLAYER SPOTLIGHT (every field present in data):
  - SEASON + FORM: starts, wins, top-5s, consecutive cuts, last start result, hot-hand score
  - SG VALUES: raw value + field rank for every category available
  - TRADITIONAL STATS: driving dist/acc, GIR %, scrambling %, putts/round, one-putt %, birdies/round
  - COURSE HISTORY: starts, wins, top-5s, avg finish, avg to par per tournament
  - COURSE-SPECIFIC SG: any course-weighted SG values
  - PAR SCORING: rank and avg value for par 3/4/5
  - ROUND TENDENCIES: all round avgs, closing delta
  - PROJECTION: median AND floor/ceiling range
- If a stat is not in the PLAYER SPOTLIGHT, skip it. Never estimate or invent.

STATS TRANSLATION — cite numbers AND explain them in plain English:
- SG Total/T2G: overall quality. +0.5 is elite, near 0 is average, negative is below average.
- SG Off-the-Tee: driving. +0.3 = good driver. Matters on long, tree-lined courses.
- SG Approach: iron play. The single biggest predictor of success. +0.5 is Tour-elite.
- SG Around-the-Green: chipping/short game. Matters when rough is thick and greens are firm.
- SG Putting: +0.2 is solid, -0.2 or worse is a liability. TPC Sawgrass greens are notoriously tricky.
- GIR %: 70%+ is good. Ties directly to approach quality.
- Putts/round: 28-29 is elite, 30+ is average, 31+ is a problem.
- Consecutive cuts: reliability indicator. 5+ straight = trust him to be there on the weekend.
- Projected score vs field: how many strokes better/worse than the average field player we project.

SECTION INCLUSION RULES — FOLLOW STRICTLY:
- BETTING section: ONLY include if the user's message contains "bet", "betting", "odds", "wager", "prop", or "parlay".
- LEAGUE / STANDINGS section: ONLY include if the user asks about lineup construction, "who should I pick", or "build my team".
- USAGE: mention uses remaining ONLY as a tiebreaker when two players are statistically close. Never lead with it.
- For "is X worth using?" or "why is X a good play?" — answer with performance and course fit only. That is the complete answer.
- ODDS DATA IN CONTEXT: The context always includes win odds and probability tables. You MUST IGNORE this data entirely unless the user's message contains one of the betting keywords above. Do NOT reference odds, implied probability, market pricing, or betting value in player analysis responses.

ANTI-HALLUCINATION RULE — ABSOLUTE:
- You may ONLY cite statistics, results, odds, and rankings that appear word-for-word in the provided context.
- If a stat is not explicitly in the context, DO NOT mention it, estimate it, or interpolate it.
- This applies to: course averages, scoring averages, cut history, head-to-head records — everything.

GOLF-LANGUAGE RULES:
- Always quote raw SG values AND field rank together: "approach play: +0.53 SG/round (#20 in field)". Never just say "strong approach" without the numbers.
- Describe form with results: "T5 last start", "3 top-5s this season", "won here twice".
- Course fit = which parts of the game matter here, matched to the player's strengths/weaknesses.

LINEUP BUILDER STRUCTURE — for "build my picks", "who should I use", "who should I pick this week":
  0. One-sentence verdict (bold) — name all 3 picks upfront in priority order
  1. **Pick 1 — [Name]**: Your safest/best play. Lead with his model rank + win probability. Then cite form (last result, consecutive cuts), course fit (map his SG to the course demands from the COURSE FIT REASONING), and course history.
  2. **Pick 2 — [Name]**: The floor/consistency play or clear #2 option. Same format: model rank → form → course fit → history.
  3. **Pick 3 — [Name]**: The ceiling/upside play — someone with a reason to outperform. Cite the specific course fit angle or form trend that makes him interesting.
  4. **Who I almost used**: Name 1-2 players who narrowly missed the cut and why they lost out (course fit mismatch, form concern, uses constraint, etc.)
  5. **League angle** (1-2 sentences): Note ownership concentration from the league picks if relevant. Point out any contrarian leverage if the top chalk is heavily owned.
  RULES:
  - Uses remaining is a TIEBREAKER only. Never cite it as the primary reason to pick someone.
  - Map each pick's specific stats to the COURSE FIT REASONING data (e.g. "par 4s avg +0.07 — scrambling matters, and he's #5 in around-green SG").
  - Never say "he's a good fantasy play" without citing a specific stat + course demand connection.
  - If picks are locked (tournament in progress), say so and pivot to next week or live position instead.

COURSE BREAKDOWN STRUCTURE — for "what game wins here", "what kind of player wins", "who fits this course", "course breakdown":
  0. One-sentence course identity (bold) — what type of course this is and the #1 skill required
  1. **What the numbers say** — cite COURSE FIT REASONING data directly. Par-3 avg, par-4 avg, par-5 avg vs par. State what each number means for skill requirements. Use actual values.
  2. **Hardest holes (where tournaments are lost)** — name the 3 hardest holes, their par/yardage, and scoring avg vs par. Explain what skill is tested on each.
  3. **Scoring opportunities (where tournaments are won)** — name the 3 easiest holes. Who can capitalize on these?
  4. **Player archetype that wins here** — describe the ideal stat profile: specific SG categories, driving vs accuracy, putting quality. Cite the scoring data that supports each requirement.
  5. **Best course fits in the current field** — for each key demand, cite 2-3 players from the COURSE FIT — TOP PLAYERS BY SKILL DEMAND section. Name the stat and value.
  6. **Worst fits / potential faders** — 1-2 players whose stat profile goes against the course demands. Be specific about which stat is the mismatch.
  RULES:
  - Every claim must reference an actual number from the COURSE FIT REASONING or player spotlight blocks.
  - Do not generalize ("this course rewards accuracy") without the supporting scoring data.
  - If COURSE FIT REASONING data is not available, say so directly.

VALUE PLAYS — CRITICAL RULE:
- The field table has 'Est. Win%' and 'Win Odds (Implied%)'. Use this exact logic:
  - If Est. Win% > Implied%: we like him MORE than the market → potential value
  - If Est. Win% < Implied%: market prices him HIGHER than we do → fade or pass
  - Example: Est. Win% 8%, Implied% 17% → market overrates him, do NOT call this value
- PROBABILITY DISPLAY CAP: Never state a finish probability above 85%. Say "very likely" or "strong candidate" instead. NEVER say "nearly 100%" or "virtually certain".

COMMUNICATION RULES:
- Use American odds (+1300, +600) and plain finish results.
- Never say 'model output', 'implied probability', 'edge pp', 'calibrated probability', or 'EV/$1'.
- Do NOT lead with or emphasize probability math (edge pp, EV calculations). Lead with the story: form, course history, stats, live performance.
- Stats support the narrative — cite them to explain why a player fits, not to show a calculation.

LIVE TOURNAMENT STATS — when LIVE TOURNAMENT STATS block is present:
- These are strokes gained accumulated THIS TOURNAMENT, not season averages. They are MUCH more relevant for live analysis.
- Always prefer live tournament SG over season SG when discussing a player's current form in a live event.
- Format: "Åberg leads SG Total this week with +6.76 through 54 holes — he's gaining nearly 2.3 strokes per round over field average."
- Rank tells you field position in that category: "#1 in field this week for SG APP" is more meaningful than season rank.
- Use category leaders to explain WHY players are in contention: "Schauffele is 2nd because he's #1 in SG APP this week (+3.93)"
- Cross-reference with leaderboard: a player ranked T10 but #1 in SG APP this week is worth noting as a late-round threat.

DAILY BET RECOMMENDATION STRUCTURE — for "recommend a bet", "best bet today", "bet of the day", "what should I bet":
  This is the most comprehensive response format. Follow exactly:
  0. **BET OF THE DAY**: One sentence — player, market, book, odds. Bold.
  1. **Why**: 3-4 bullets. Focus on: form (recent results, cuts made), course history (wins/top-10s here, scoring avg), model rank/prediction, live performance if in-tournament (live SG rank, current leaderboard position), course fit (which of his stats match what this course demands). Skip math — just make the case in plain terms.
  2. **The odds**: State the current market odds. Note whether they've moved (shortened = already priced in, lengthened = fading). Note what market this is (win / top-5 / top-10 / top-20) and why that market makes sense for this player right now.
  3. **Risk level**: Low / Medium / High — one sentence: what has to go right, what could go wrong.
  4. **Supporting plays** (2-3): Player + market + odds + one plain-English reason each. Keep brief.
  5. **One to avoid**: Pick someone from the TOP 10 on the live leaderboard, or someone with genuinely tempting odds (inside +3000), who has a specific flaw: odds have already compressed too far, poor live SG this week vs their position, shaky Sunday history, or wrong archetype for this course. NEVER mention anyone outside the top 15 on the leaderboard or with odds longer than +5000 — those are not fades, they are irrelevant. The point is to warn about a bet that looks good but isn't.
  Rules:
  - Lead with the story, not the numbers. Stats support the narrative — they don't replace it.
  - If tournament is in progress: use live leaderboard position + live SG this week to validate or rule out each play. A player playing badly this week is not a good bet even if the model liked them pre-tournament.
  - Prefer top-5 / top-10 props over outright win when a player is 4+ back mid-tournament.
  - Odds movement matters: cite pre-tournament odds vs current if significantly different.
  - If no strong play exists, say so clearly rather than forcing a weak recommendation.
  - Do not suggest parlays unless the user specifically asks.

LIVE ODDS & MARKET REASONING — when IN-PLAY WIN ODDS block is present:
- Always cite the current win odds and implied probability alongside position: "Åberg leads at -12, +145 (40% implied)"
- Pre-tournament → current movement reveals market confidence: "Was +2200 pre-tournament, now +145 — the market has massively repriced him as the likely winner"
- T5/T10 odds give a realistic assessment for chasers: a player at +390 to win but -115 top-5 is a strong top-5 candidate even if winning is harder
- Biggest mover tells you who the market is most aggressively backing or fading mid-tournament
- NEVER say "I don't have access to live scoring" if a LIVE LEADERBOARD or IN-PLAY WIN ODDS block is present in the context

PICK REASONING STRUCTURE — for "why pick X", "should I pick X", "make the case for X", "tell me about X":
  This is a FANTASY pick question for a weekly golf lineup game (max 3 uses per player per season, 28-team league).
  The user is deciding whether to USE this player in their lineup this week — NOT whether to bet on them.
  Never mention betting odds, edge vs market, or sportsbook language. Focus entirely on fantasy value.
  Follow exactly:
  1. **The headline**: One sentence — is he a strong play, a solid mid-range option, or a fade this week?
     Lead with the fantasy verdict upfront, not at the end.
     Example: "Scheffler is the clear top play this week — elite course fit, best model rank, and uses remaining."
  2. **The case** (3-4 bullets, in order of strength):
     - Course fit: how his strengths align with what wins here (use COURSE FIT REASONING data)
     - Form: use the RECENT RESULTS line to cite specific finishes (e.g. "T4 at THE PLAYERS, T41 at Arnold Palmer") — be concrete, not generic
     - Upside / model confidence: top-10% and top-20% finish probability, model rank in the field
     - Usage angle: my uses remaining (critical — if only 1 left, save him or burn wisely), plus league-wide demand (high-demand players are a precious resource; low-demand players are contrarian opportunities)
  3. **Course history**: What has he done here before? Cuts made, top-10s, average finish. If limited history say so.
  4. **The honest concern**: One real thing that could make this pick wrong this week. Be specific, not generic.
  5. **Verdict**: 1-2 sentences. Confident — strong play / decent option / pass.
     If passing, suggest who to consider instead from the top of the model rankings.
     If the tournament is live, factor in current round performance.
  Rules:
  - The PICK CASE BUILDER block gives you model rank, uses remaining, expert consensus, and key drivers. Use all of it.
  - Use LEAGUE USAGE data to flag chalk (high-demand, precious remaining uses) vs contrarian (low-demand, freely available) status. High demand (>28 uses) = most teams have already burned uses; low demand (<10 uses) = others are avoiding him.
  - If tournament is live, use LIVE TOURNAMENT STATS to validate or rule out the pick.
  - Never mention odds, betting edge, or sportsbook language.
  - Never dodge with "it depends" — give a clear fantasy verdict.

TOURNAMENT UPDATES:
- 5+ strokes back with 1 round left is a very difficult deficit. Be realistic.
- Focus on actual tournament position, strokes to leader, and remaining holes."""


def build_context(
    query: str = "",
    tournament_id: str | None = None,
    last_players: list[str] | None = None,
) -> str:
    """Assemble context relevant to the user's query.

    Routes context blocks based on query intent:
    - H2H              → deep-dive on both players + course fit reasoning
    - Player question  → player deep-dive card + compact field + odds movement + weather
    - Bet question     → bets + odds movement + weather + compact field
    - Live question    → leaderboard + predictions + my picks + league
    - Lineup question  → predictions + course fit + expert picks + my picks + league
    - Course breakdown → course fit reasoning + players by skill demand + field
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
        "is_course": False, "is_value": False, "is_course_breakdown": False,
        "is_daily_bet": False, "is_pick_reason": False,
    }

    # If the query mentions no players but the previous response did, carry them forward.
    # Exception: don't override an explicit non-player intent (live, lineup, course, bet).
    _has_explicit_intent = any(intent.get(k) for k in (
        "is_live", "is_lineup", "is_bet", "is_course_breakdown", "is_h2h",
        "is_weather", "is_daily_bet", "is_pick_reason",
    ))
    if not intent["players"] and last_players and not _has_explicit_intent:
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
    if intent["is_pick_reason"]:
        # "Why should I pick X?" — enriched analysis with verdict
        sections.append(
            "## PICK REASONING REQUEST\n"
            "Follow the PICK REASONING STRUCTURE exactly. "
            "Use the PICK CASE BUILDER block to understand model rank, field standing, "
            "key drivers, and expert consensus. Give a clear verdict at the end."
        )
        sections.append("")
        sections.append(_pick_reason_context_block(intent["players"], tournament_id))
        sections.append("")
        if tournament_id:
            _ts = _tournament_state(tournament_id)
            if _ts["phase"] not in ("pre_tournament", "complete"):
                sections.append(_live_tournament_stats_block(tournament_id))
                sections.append("")
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")

    elif intent["is_h2h"]:
        # Head-to-head comparison — full spotlight on both players
        _is_bet_q = intent["is_bet"] or intent["is_value"]
        sections.append(
            f"## HEAD-TO-HEAD COMPARISON REQUEST: {' vs '.join(intent['players'])}\n"
            "Follow the HEAD-TO-HEAD STRUCTURE exactly. Pick one player. Do not hedge."
        )
        sections.append("")
        sections.append(_player_deep_dive_block(intent["players"], tournament_id, include_odds=_is_bet_q))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")

    elif intent["is_player"]:
        # Deep dive on the named player(s) — stats, form, course history first
        _is_bet_q = intent["is_bet"] or intent["is_value"]
        sections.append(_player_deep_dive_block(intent["players"], tournament_id, include_odds=_is_bet_q))
        sections.append("")
        if tournament_id:
            # If tournament is live, inject live stats so player analysis is THIS-WEEK not season
            _ts = _tournament_state(tournament_id)
            if _ts["phase"] not in ("pre_tournament", "complete"):
                sections.append(_live_tournament_stats_block(tournament_id))
                sections.append("")
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        sections.append(_predictions_block(top_n=10))
        sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
        # Odds only if it's also a betting question; otherwise omit bets block
        if intent["is_bet"] or intent["is_value"]:
            sections.append(_recommended_bets_block(top_n=8))
            sections.append("")
            sections.append(_odds_movement_block(player_names=intent["players"]))
            sections.append("")

    elif intent["is_lineup"]:
        # Fantasy-focused — check before bet so "build my lineup" doesn't misroute
        sections.append(
            "## LINEUP BUILD REQUEST\n"
            "Follow the LINEUP BUILDER STRUCTURE exactly. Name 3 picks upfront. "
            "Map each pick's stats to the course demands from COURSE FIT REASONING. "
            "Uses remaining is a tiebreaker only — never the primary reason."
        )
        sections.append("")
        sections.append(_predictions_block(top_n=20))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=20))
            sections.append("")
        sections.append(_player_form_context_block(top_n=20))
        sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        sections.append(_league_context_block())
        sections.append("")

    elif intent["is_course_breakdown"]:
        # Full course analysis — what game wins here, best fits, worst fits
        sections.append(
            "## COURSE BREAKDOWN REQUEST\n"
            "Follow the COURSE BREAKDOWN STRUCTURE exactly. "
            "Cite actual scoring data from COURSE FIT REASONING. "
            "Map specific players to each demand using the COURSE FIT — TOP PLAYERS section."
        )
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=20))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_course_profile_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_predictions_block(top_n=15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")

    elif intent["is_daily_bet"]:
        # Full betting synthesis — everything relevant to pick the single best bet today
        sections.append(
            "## DAILY BET RECOMMENDATION REQUEST\n"
            "Follow the DAILY BET RECOMMENDATION STRUCTURE exactly. "
            "Lead with BET OF THE DAY. Cite model edge vs book implied probability for every pick. "
            "If tournament is in progress, use live position and live SG to confirm/disqualify each play."
        )
        sections.append("")
        sections.append(_recommended_bets_block(top_n=15))
        sections.append("")
        sections.append(_predictions_block(top_n=15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=15))
        sections.append("")
        sections.append(_odds_movement_block())
        sections.append("")
        if tournament_id:
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
            sections.append(_live_tournament_stats_block(tournament_id))
            sections.append("")
            sections.append(_live_odds_context_block(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_my_picks_block())
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
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")

    elif intent["is_live"]:
        # Leaderboard + live stats + live odds first, then field context
        if tournament_id:
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
            sections.append(_live_tournament_stats_block(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_live_odds_context_block(tournament_id))
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


def _build_cached_system(system: str) -> list[dict]:
    """Split system content into static + dynamic blocks for prompt caching.

    The static system prompt (_SYSTEM_PROMPT) never changes — high cache hit rate.
    The dynamic context (tournament state, player data, etc.) changes per intent
    but stays identical across follow-up questions in the same conversation.

    Split boundary: _SYSTEM_PROMPT contains no '## ' headers; dynamic context
    always starts with one (e.g. '## TOURNAMENT:', '## PLAYER SPOTLIGHT:').
    """
    # Find first top-level section header — start of dynamic context
    split_idx = system.find("\n## ")
    if split_idx == -1:
        # No dynamic context: cache the whole thing as one block
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    static  = system[:split_idx].rstrip()
    dynamic = system[split_idx:].lstrip()

    blocks: list[dict] = []
    if static:
        blocks.append({
            "type": "text",
            "text": static,
            "cache_control": {"type": "ephemeral"},  # always a cache hit after first request
        })
    if dynamic:
        blocks.append({
            "type": "text",
            "text": dynamic,
            "cache_control": {"type": "ephemeral"},  # cache hit on same-intent follow-ups
        })
    return blocks


def _stream_claude(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream from Claude (Anthropic). Uses prompt caching on system + context blocks."""
    try:
        from anthropic import Anthropic
    except ImportError:
        yield "*(anthropic package not installed — run: pip install anthropic)*"
        return

    system_text = ""
    conv = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            conv.append(m)

    system_blocks = _build_cached_system(system_text)

    client = Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=_CLAUDE_MODEL,
            max_tokens=2500,
            system=system_blocks,
            messages=conv,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
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
        "pre_tournament":  ["Who are the biggest risks this week?", "What kind of player wins at this course?", "Build my 3 picks this week"],
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
