#!/usr/bin/env python3
"""
Post-Tournament Recap Generator

Builds a data bundle from settled results + pre-tournament predictions + graded bets,
then calls Claude to write a 3-4 sentence narrative recap.
Saves to outputs/tournament_recap_{tid}.json.

Run automatically after post_tournament.py, or manually:
    python3 scripts/notifications/generate_recap.py --tournament-id R2026014
    python3 scripts/notifications/generate_recap.py --tournament-id R2026014 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"

OUTPUTS_DIR.mkdir(exist_ok=True)


# ── Data loading ──────────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    import re
    return re.sub(r"[^a-z ]", "", str(name).lower()).strip()


def load_final_leaderboard(tid: str) -> list[dict]:
    """Return top-10 finishers from the historical leaderboard CSV."""
    path = DATA_DIR / "historical" / "leaderboards_2026.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df = df[df["tournament_id"].astype(str).str.upper() == tid.upper()].copy()
    if df.empty:
        return []
    df["_pos_num"] = pd.to_numeric(df["position"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    df = df.sort_values("_pos_num", na_position="last").head(10)
    return [
        {"position": r["position"], "player": r["player_name"], "to_par": r["to_par"]}
        for _, r in df.iterrows()
    ]


def load_pre_tournament_predictions(tid: str) -> list[dict]:
    """Return pre-tournament model top-10 picks from prediction history."""
    path = DATA_DIR / "prediction_tracking" / "prediction_history.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df = df[df["tournament_id"].astype(str).str.upper() == tid.upper()].copy()
    if df.empty:
        return []
    df["_model_rank"] = pd.to_numeric(df.get("model_rank", pd.Series(dtype=float)), errors="coerce")
    if "_model_rank" not in df.columns or df["_model_rank"].isna().all():
        for col in ["win_prob_calibrated", "win_prob"]:
            if col in df.columns:
                df["_model_rank"] = df[col].rank(ascending=False)
                break
    df = df.sort_values("_model_rank").head(10)

    results = []
    for _, r in df.iterrows():
        actual_pos = r.get("actual_position")
        results.append({
            "player":      r["player_name"],
            "model_rank":  int(r["_model_rank"]) if pd.notna(r["_model_rank"]) else None,
            "actual_pos":  str(actual_pos).strip() if pd.notna(actual_pos) else "MC/WD",
            "win_prob":    round(float(r["win_prob_calibrated"]) * 100, 1)
                           if "win_prob_calibrated" in r and pd.notna(r.get("win_prob_calibrated"))
                           else None,
        })
    return results


def load_bet_summary(tid: str) -> dict | None:
    """Return graded bet stats for the tournament if available."""
    path = DATA_DIR / "odds" / "recommended_bets_log.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df = df[df["tournament_id"].astype(str).str.upper() == tid.upper()]
    graded = df[df["outcome_status"].isin(["won", "lost", "push"])].copy()
    if graded.empty:
        return None
    graded["pnl_per_1"] = pd.to_numeric(graded["pnl_per_1"], errors="coerce")
    total   = len(graded)
    wins    = (graded["outcome_status"] == "won").sum()
    total_pnl = graded["pnl_per_1"].sum()
    roi     = total_pnl / total * 100 if total else 0.0
    return {
        "bets":    total,
        "wins":    int(wins),
        "roi_pct": round(roi, 1),
        "pnl":     round(float(total_pnl), 2),
    }


def load_tournament_name(tid: str) -> str:
    sched = DATA_DIR / "raw" / "schedule_2026.csv"
    if not sched.exists():
        return tid
    df = pd.read_csv(sched)
    row = df[df["tournament_id"].astype(str).str.upper() == tid.upper()]
    if row.empty:
        return tid
    return str(row.iloc[0].get("tournament_name", tid))


# ── Claude prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a sharp golf analyst writing post-tournament recaps for a betting and fantasy
golf dashboard. Your recaps are punchy, informative, and data-driven — like a brief
entry in a betting journal. Write 3-4 sentences covering:
  1. Who won and how dominant/surprising the result was
  2. How the pre-tournament model performed (key hits, notable misses)
  3. Anything noteworthy about the betting/fantasy angle

Keep it under 100 words. Use specific names and numbers. No filler phrases.
Do NOT start with "The" or the tournament name as the first word.
"""

def build_prompt(
    tournament_name: str,
    leaderboard: list[dict],
    predictions: list[dict],
    bets: dict | None,
) -> str:
    lb_lines = "\n".join(
        f"  {p['position']}. {p['player']}  {p['to_par']}"
        for p in leaderboard[:5]
    )
    pred_lines = "\n".join(
        f"  Model #{p['model_rank']}: {p['player']} "
        f"({p['win_prob']}% win prob) → finished {p['actual_pos']}"
        for p in predictions[:8]
        if p["model_rank"] is not None
    )
    bet_line = ""
    if bets:
        bet_line = (
            f"\nBet results: {bets['wins']}/{bets['bets']} wins, "
            f"ROI {bets['roi_pct']:+.1f}% ({bets['pnl']:+.2f}u P&L)"
        )

    return f"""\
Tournament: {tournament_name}

Final leaderboard (top 5):
{lb_lines}

Pre-tournament model picks vs actual finishes:
{pred_lines}
{bet_line}

Write the recap now."""


# ── Claude call ───────────────────────────────────────────────────────────────

def generate_narrative(prompt: str, dry_run: bool = False) -> str:
    if dry_run:
        return "[DRY RUN] Recap would be generated here by Claude."
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  Claude call failed: {e}", file=sys.stderr)
        return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_recap(tid: str, dry_run: bool = False) -> dict:
    tid = tid.upper()
    print(f"Generating recap for {tid}...")

    name        = load_tournament_name(tid)
    leaderboard = load_final_leaderboard(tid)
    predictions = load_pre_tournament_predictions(tid)
    bets        = load_bet_summary(tid)

    if not leaderboard:
        print(f"  No final leaderboard found for {tid} — run post_tournament.py first")
        return {}

    winner = leaderboard[0]["player"] if leaderboard else "Unknown"
    print(f"  Winner: {winner}")
    print(f"  Leaderboard rows: {len(leaderboard)}")
    print(f"  Prediction rows: {len(predictions)}")
    if bets:
        print(f"  Bets: {bets['wins']}/{bets['bets']} wins, ROI {bets['roi_pct']:+.1f}%")

    prompt    = build_prompt(name, leaderboard, predictions, bets)
    narrative = generate_narrative(prompt, dry_run=dry_run)
    print(f"  Narrative: {narrative[:80]}..." if len(narrative) > 80 else f"  Narrative: {narrative}")

    recap = {
        "tournament_id":   tid,
        "tournament_name": name,
        "winner":          winner,
        "winner_score":    leaderboard[0]["to_par"] if leaderboard else None,
        "top5":            leaderboard[:5],
        "model_top5":      predictions[:5],
        "bet_summary":     bets,
        "narrative":       narrative,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
    }

    out_path = OUTPUTS_DIR / f"tournament_recap_{tid}.json"
    if not dry_run:
        with open(out_path, "w") as f:
            json.dump(recap, f, indent=2)
        print(f"  Saved → {out_path}")
    else:
        print(f"  [DRY RUN] Would save → {out_path}")

    return recap


def main():
    parser = argparse.ArgumentParser(description="Generate post-tournament recap narrative")
    parser.add_argument("--tournament-id", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude call and file write")
    args = parser.parse_args()

    result = generate_recap(args.tournament_id, dry_run=args.dry_run)
    if result:
        print("\nRecap preview:")
        print(f"  {result.get('narrative', '')}")


if __name__ == "__main__":
    main()
