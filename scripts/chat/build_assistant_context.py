#!/usr/bin/env python3
"""
Build Assistant Context File
============================
Generates outputs/assistant_context.md — a season-level summary that gives
the golf chatbot (and any external LLM) memory about:

  - How the model has been performing this season
  - Which picks hit/missed in recent tournaments
  - Bet grading results and ROI per tournament
  - Closing line value (CLV) — are we getting good prices?
  - Top SHAP features driving predictions

Run after every post-tournament refresh:
    python3 scripts/chat/build_assistant_context.py

Output: outputs/assistant_context.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA         = PROJECT_ROOT / "data"
OUTPUTS      = PROJECT_ROOT / "outputs"
OUT_FILE     = OUTPUTS / "assistant_context.md"


def _fmt_name(name: str) -> str:
    """Normalize 'Last, First' → 'First Last'."""
    s = str(name).strip()
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first} {last}"
    return s


def _rank_label(pos) -> str:
    """Format a numeric position as #5, CUT, etc. Returns — for missing/placeholder values."""
    if pd.isna(pos):
        return "—"
    s = str(pos).strip()
    if s in ("CUT", "MC", "WD", "DQ"):
        return s
    try:
        n = int(float(s))
        if n > 200:
            return "—"  # placeholder sentinel
        return f"#{n}"
    except ValueError:
        return s


# ── Section builders ────────────────────────────────────────────────────────

def _season_summary(pred_hist: pd.DataFrame, leaderboard: pd.DataFrame) -> str:
    """High-level season accuracy stats."""
    graded = pred_hist[pred_hist["actual_position"].notna()].copy()
    if graded.empty:
        return "## Season Summary\nNo completed tournament data yet.\n"

    tournaments = graded["tournament_id"].nunique()
    total_players = len(graded)

    # For each tournament, check if our #1 ranked player (highest predicted_win_prob)
    # hit the top 10 (reasonable "model called it" test)
    model_picks_in_t10 = 0
    model_top_pick_wins = 0
    t10_rate_total = 0
    t10_count = 0

    for tid, gdf in graded.groupby("tournament_id"):
        gdf = gdf.sort_values("predicted_win_prob", ascending=False)
        top_pick = gdf.iloc[0]
        if top_pick.get("actual_top10") in (True, 1, "True", "1"):
            model_picks_in_t10 += 1
        if top_pick.get("actual_won") in (True, 1, "True", "1"):
            model_top_pick_wins += 1
        # Top-10 rate for top-5 predicted players
        top5_preds = gdf.head(5)
        hits = sum(
            1 for _, r in top5_preds.iterrows()
            if r.get("actual_top10") in (True, 1, "True", "1")
        )
        t10_rate_total += hits
        t10_count += 5

    top_pick_t10_pct = model_picks_in_t10 / tournaments * 100 if tournaments else 0
    t5_t10_rate = t10_rate_total / t10_count * 100 if t10_count else 0

    # Winner prediction accuracy: rank of actual winner in our presets
    winner_ranks = []
    for tid, gdf in graded.groupby("tournament_id"):
        gdf = gdf.sort_values("predicted_win_prob", ascending=False).reset_index(drop=True)
        winner_row = gdf[gdf["actual_won"].astype(str).isin(["True", "1"])]
        if not winner_row.empty:
            winner_ranks.append(winner_row.index[0] + 1)  # 1-based rank

    avg_winner_rank = sum(winner_ranks) / len(winner_ranks) if winner_ranks else None

    lines = ["## Season Summary (2026 PGA Tour)"]
    lines.append(f"- Tournaments tracked: **{tournaments}**")
    lines.append(f"- Tournaments with results: **{graded['tournament_id'].nunique()}**")
    lines.append(f"- Top pick finished top 10: **{model_picks_in_t10}/{tournaments}** ({top_pick_t10_pct:.0f}%)")
    lines.append(f"- Top-5 predictions → top-10 rate: **{t5_t10_rate:.0f}%** (expected: ~33%)")
    if avg_winner_rank:
        lines.append(f"- Average rank of actual winner in our presets: **#{avg_winner_rank:.1f}**")
    if model_top_pick_wins:
        lines.append(f"- Times our #1 pick won: **{model_top_pick_wins}**")
    lines.append("")
    return "\n".join(lines)


def _tournament_results(pred_hist: pd.DataFrame, leaderboard: pd.DataFrame, n: int = 4) -> str:
    """Last N completed tournaments: winner, our top pick, model picks in top 10."""
    graded = pred_hist[pred_hist["actual_position"].notna()].copy()
    if graded.empty:
        return ""

    # Get sorted list of completed tournament IDs (most recent first)
    # Use leaderboard to find winners and sort by tournament order
    sched_path = DATA / "raw" / "schedule_2026.csv"
    sched = pd.read_csv(sched_path) if sched_path.exists() else pd.DataFrame()
    tid_order = {}
    if not sched.empty and "tournament_id" in sched.columns:
        for i, row in sched.iterrows():
            tid_order[str(row["tournament_id"])] = i

    # Sort by tournament_date from prediction_history (most recent first)
    tid_dates = (
        graded.groupby("tournament_id")["tournament_date"]
        .first()
        .apply(lambda d: pd.to_datetime(d, errors="coerce"))
    )
    completed_tids = graded["tournament_id"].unique().tolist()
    completed_tids.sort(key=lambda t: tid_dates.get(t, pd.Timestamp.min), reverse=True)
    recent_tids = completed_tids[:n]

    winners = {}
    if not leaderboard.empty:
        for _, row in leaderboard[leaderboard["position"].astype(str) == "1"].iterrows():
            winners[str(row["tournament_id"])] = _fmt_name(str(row["player_name"]))

    lines = [f"## Recent Tournament Results (Last {min(n, len(recent_tids))})"]

    for tid in recent_tids:
        gdf = graded[graded["tournament_id"] == tid].copy()
        tname = gdf["tournament_name"].iloc[0] if "tournament_name" in gdf.columns else tid
        gdf_sorted = gdf.sort_values("predicted_win_prob", ascending=False)

        winner = winners.get(tid, "Unknown")
        top_pick = _fmt_name(str(gdf_sorted.iloc[0]["player_name"]))
        top_pick_pos = gdf_sorted.iloc[0].get("actual_position", "?")

        # How many of our top 10 predictions finished top 10?
        top10_preds = gdf_sorted.head(10)
        t10_hits = sum(
            1 for _, r in top10_preds.iterrows()
            if r.get("actual_top10") in (True, 1, "True", "1")
        )

        # Where did the winner appear in our rankings?
        winner_row = gdf_sorted[gdf_sorted["actual_won"].astype(str).isin(["True", "1"])]
        winner_model_rank = (
            int(gdf_sorted.index.get_loc(winner_row.index[0])) + 1
            if not winner_row.empty else None
        )

        lines.append(f"\n### {tname} ({tid})")
        lines.append(f"- **Winner**: {winner}")
        if winner_model_rank:
            lines.append(f"- Winner was our **#{winner_model_rank}** ranked player pre-tournament")
        lines.append(f"- Our **#1 pick**: {top_pick} — finished {_rank_label(top_pick_pos)}")
        lines.append(f"- Top-10 predictions hit: **{t10_hits}/10** finished inside top 10")

    lines.append("")
    return "\n".join(lines)


def _bet_performance(results_path: Path, n_tournaments: int = 5) -> str:
    """Bet grading summary per tournament (settled bets only)."""
    if not results_path.exists():
        return ""
    try:
        df = pd.read_csv(results_path)
    except Exception:
        return ""

    settled = df[df["outcome_status"].isin(["won", "lost"])].copy()
    if settled.empty:
        return ""

    # Only recommended/priced bets (not every possible combination)
    if "status" in settled.columns:
        settled = settled[settled["status"] == "priced"]

    # Sort tournaments by schedule order
    sched_path = DATA / "raw" / "schedule_2026.csv"
    sched = pd.read_csv(sched_path) if sched_path.exists() else pd.DataFrame()
    tid_order = {}
    if not sched.empty and "tournament_id" in sched.columns:
        for i, row in sched.iterrows():
            tid_order[str(row["tournament_id"])] = i

    by_t = (
        settled.groupby("tournament_id")
        .agg(
            bets=("outcome_win", "count"),
            wins=("outcome_win", "sum"),
            total_pnl=("pnl_per_1", "sum"),
        )
        .reset_index()
    )
    by_t["win_rate"] = (by_t["wins"] / by_t["bets"] * 100).round(1)
    by_t["roi"] = (by_t["total_pnl"] / by_t["bets"] * 100).round(1)
    by_t["order"] = by_t["tournament_id"].map(lambda t: tid_order.get(t, 999))
    by_t = by_t.sort_values("order", ascending=False).head(n_tournaments)

    # Totals
    total_bets = settled["outcome_win"].count()
    total_wins = settled["outcome_win"].sum()
    total_roi  = (settled["pnl_per_1"].sum() / total_bets * 100) if total_bets else 0

    lines = ["## Bet Performance (Recommended Bets — Priced Only)"]
    lines.append(f"Season totals: **{total_bets} bets**, **{total_wins} wins** ({total_wins/total_bets*100:.0f}%), ROI **{total_roi:+.1f}%**\n")

    rows = ["| Tournament | Bets | Wins | Win% | ROI |"]
    rows.append("|---|---|---|---|---|")
    for _, r in by_t.iterrows():
        # Get tournament name from settled data
        tname_rows = settled[settled["tournament_id"] == r["tournament_id"]]
        tname = r["tournament_id"]
        rows.append(f"| {tname} | {r['bets']} | {r['wins']} | {r['win_rate']}% | {r['roi']:+.1f}% |")
    lines.extend(rows)
    lines.append("")
    lines.append("Note: Most bets are outright/top-10/top-20 markets. High volume because the system prices many combinations; actual staked bets are a subset.")
    lines.append("")
    return "\n".join(lines)


def _clv_summary(clv_path: Path) -> str:
    """Closing Line Value summary — are we beating the market?"""
    if not clv_path.exists():
        return ""
    try:
        df = pd.read_csv(clv_path)
    except Exception:
        return ""
    if df.empty or "clv_pp" not in df.columns:
        return ""

    tournaments = df["tournament_id"].nunique()
    avg_clv = df["clv_pp"].mean()
    pct_positive = (df["clv_pp"] > 0).mean() * 100

    # Best and worst CLV picks
    best = df.nlargest(3, "clv_pp")[["player_name_model", "tournament_name", "clv_pp"]]
    worst = df.nsmallest(3, "clv_pp")[["player_name_model", "tournament_name", "clv_pp"]]

    lines = ["## Closing Line Value (CLV)"]
    lines.append("CLV measures whether our model priced players better than the closing market. Positive CLV = we got value; negative = we were wrong about the price.")
    lines.append(f"- Tournaments with CLV data: **{tournaments}**")
    lines.append(f"- Average CLV: **{avg_clv:+.2f}pp** (percentage points vs closing line)")
    lines.append(f"- % of picks with positive CLV: **{pct_positive:.0f}%**")
    lines.append("")
    lines.append("**Best CLV picks this season:**")
    for _, r in best.iterrows():
        lines.append(f"  - {_fmt_name(str(r['player_name_model']))} ({r['tournament_name']}): +{r['clv_pp']:.1f}pp")
    lines.append("")
    return "\n".join(lines)


def _shap_summary(shap_path: Path) -> str:
    """Top model features by global SHAP importance."""
    if not shap_path.exists():
        return ""
    try:
        df = pd.read_csv(shap_path).sort_values("mean_abs_shap", ascending=False)
    except Exception:
        return ""

    FEATURE_NAMES = {
        "season_sg_app":           "Approach play (SG:APP season avg)",
        "form_trend":              "Recent form trend",
        "predictive_sg_weighted":  "Predictive SG profile (DataGolf weights)",
        "season_sg_t2g":           "Tee-to-green strokes gained",
        "world_rank_log":          "World ranking (log-scaled)",
        "season_sg_putt":          "Putting (SG:PUTT season avg)",
        "season_sg_ott":           "Off-the-tee (SG:OTT season avg)",
        "season_sg_arg":           "Around-the-green (SG:ARG season avg)",
        "season_sg_total":         "Total strokes gained",
        "recent_sg_weighted":      "Recent SG (weighted last 5 events)",
        "course_sg_total_weighted":"Course-history SG",
        "dg_fit_total":            "Course fit score (DataGolf)",
        "course_perf_score":       "Historical course performance",
        "has_course_sg_history":   "Has SG history at this course",
    }

    top = df.head(10)
    total_shap = df["mean_abs_shap"].sum()

    lines = ["## Model Feature Importance (Win Probability)"]
    lines.append("What the model weighs most when ranking players this week:\n")
    lines.append("| # | Feature | Importance |")
    lines.append("|---|---|---|")
    for i, (_, row) in enumerate(top.iterrows(), 1):
        feat = row["feature"]
        label = FEATURE_NAMES.get(feat, feat)
        pct = row["mean_abs_shap"] / total_shap * 100
        lines.append(f"| {i} | {label} | {pct:.1f}% |")
    lines.append("")
    return "\n".join(lines)


def _model_notes() -> str:
    """Static notes about the model architecture for LLM context."""
    return """## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
"""


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Building assistant context file...")

    # Load data
    pred_hist_path   = DATA / "prediction_tracking" / "prediction_history.csv"
    leaderboard_path = DATA / "historical" / "leaderboards_2026.csv"
    bet_results_path = DATA / "odds" / "recommended_bets_results.csv"
    clv_path         = DATA / "prediction_tracking" / "clv_history.csv"
    shap_path        = OUTPUTS / "shap_global_win.csv"

    pred_hist  = pd.read_csv(pred_hist_path)  if pred_hist_path.exists()  else pd.DataFrame()
    leaderboard = pd.read_csv(leaderboard_path) if leaderboard_path.exists() else pd.DataFrame()

    sections = [
        f"# Golf Model — Season Context\n_Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n",
        _season_summary(pred_hist, leaderboard),
        _tournament_results(pred_hist, leaderboard, n=4),
        _bet_performance(bet_results_path),
        _clv_summary(clv_path),
        _shap_summary(shap_path),
        _model_notes(),
    ]

    content = "\n".join(s for s in sections if s)
    OUTPUTS.mkdir(exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"Saved → {OUT_FILE.name} ({len(content):,} chars)")
    print()
    print(content[:600] + "..." if len(content) > 600 else content)


if __name__ == "__main__":
    main()
