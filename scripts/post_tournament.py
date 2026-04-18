#!/usr/bin/env python3
"""
Post-Tournament Pipeline
========================
Runs all four post-tournament steps in sequence for a completed event:

  1. Scrape final leaderboard → leaderboards_{year}.csv
  2. Re-fetch form/SG stats (finalized after tournament)
  3. Backfill prediction_history.csv with actual finishes
  4. Grade recommended_bets_log.csv (mark won/lost, compute P&L)

Usage:
    python scripts/post_tournament.py --tournament-id R2026014
    python scripts/post_tournament.py --tournament-id R2026014 --dry-run
    python scripts/post_tournament.py --tournament-id R2026014 --skip-scrape
    python scripts/post_tournament.py --tournament-id R2026014 --step grade
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
DATA_DIR     = PROJECT_ROOT / "data"
HIST_DIR     = DATA_DIR / "historical"
ODDS_DIR     = DATA_DIR / "odds"
BETS_LOG     = ODDS_DIR / "recommended_bets_log.csv"

PYTHON = sys.executable  # same interpreter that launched this script


# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm_name(name) -> str:
    """Lowercase, strip accents, normalise Last/First vs First Last."""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    for suf in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(suf, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def _parse_pos(raw) -> int | None:
    """Parse '1', 'T4', 'CUT', 'WD' etc. → int (999 = did not finish)."""
    if pd.isna(raw):
        return None
    s = str(raw).strip().upper()
    if s in {"CUT", "MC", "WD", "DQ", "MDF", "WDJ", "RTD"}:
        return 999
    s = re.sub(r"^T", "", s)
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_opponent(selection_label) -> str | None:
    """Extract opponent name from 'Player A to beat Player B' or 'Player A to beat Player B (R1)'."""
    if pd.isna(selection_label):
        return None
    s = str(selection_label)
    if " to beat " not in s:
        return None
    opponent = s.split(" to beat ", 1)[1]
    # Strip round suffix like " (R1)", " (R2)"
    opponent = re.sub(r"\s*\(R\d\)\s*$", "", opponent).strip()
    return opponent if opponent else None


def _parse_r_score(raw) -> int | None:
    """Parse r_to_par values: 'E'→0, '-3'→-3, '+2'→2, raw int strings."""
    if pd.isna(raw):
        return None
    s = str(raw).strip().upper()
    if s in ("", "N/A", "-", "WD", "DQ", "CUT", "MDF", "RTD"):
        return None
    if s == "E":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return None


def _american_to_decimal(odds_american) -> float | None:
    """Convert American odds (+150 → 2.50, -110 → 1.909)."""
    try:
        o = float(odds_american)
    except (TypeError, ValueError):
        return None
    if o > 0:
        return round(1 + o / 100, 4)
    else:
        return round(1 + 100 / abs(o), 4)


def _run(cmd: list[str], label: str) -> bool:
    """Run a subprocess command, stream output, return True on success."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"  [ERROR] {label} exited with code {result.returncode}")
        return False
    return True


# ── Step 1: Scrape final leaderboard ──────────────────────────────────────────

def step_scrape(tid: str, dry_run: bool = False) -> bool:
    """Fetch the final leaderboard from PGA Tour and append to leaderboards_{year}.csv."""
    year = re.search(r"R(\d{4})", tid.upper())
    year_str = year.group(1) if year else "current"
    label = f"STEP 1 — Scrape final leaderboard ({tid}, {year_str})"

    cmd = [
        PYTHON, str(SCRIPTS_DIR / "scrapers" / "fetch_past_results.py"),
        "--tournament-id", tid,
        "--year", year_str,
    ]

    if dry_run:
        print(f"\n[DRY RUN] Would run: {' '.join(cmd)}")
        return True

    return _run(cmd, label)


# ── Step 2: Re-fetch form/SG stats ────────────────────────────────────────────

def step_form_stats(tid: str, dry_run: bool = False) -> bool:
    """Re-fetch strokes-gained stats — these update after the tournament ends."""
    label = "STEP 2 — Re-fetch form/SG stats"
    year_match = re.search(r"R(\d{4})", tid.upper())
    year_str = year_match.group(1) if year_match else str(__import__("datetime").datetime.now().year)
    cmd = [PYTHON, str(SCRIPTS_DIR / "scrapers" / "fetch_form_stats.py"), "--year", year_str]

    if dry_run:
        print(f"\n[DRY RUN] Would run: {' '.join(cmd)}")
        return True

    return _run(cmd, label)


# ── Step 3: Backfill prediction history ───────────────────────────────────────

def step_backfill(dry_run: bool = False) -> bool:
    """Match prediction_history.csv rows to actual finishes."""
    label = "STEP 3 — Backfill prediction history"
    cmd = [PYTHON, str(SCRIPTS_DIR / "predictions" / "backfill_results.py")]
    if dry_run:
        cmd.append("--dry-run")

    return _run(cmd, label)


# ── Step 4: Grade bets ────────────────────────────────────────────────────────

_MANUAL_MARKETS = {"group_winner", "3ball"}  # h2h/h2h_r1/matchup are auto-graded by position comparison

def _grade_market(bet_type: str, market: str, pos: int) -> bool | None:
    """
    Return True (win), False (loss), or None (manual/unresolvable).

    market is the primary key; bet_type is a fallback.
    """
    m = (market or bet_type or "").lower().strip()

    if m in _MANUAL_MARKETS:
        return None  # requires pairing data — mark manual

    if m in ("make_cut", "cut"):
        return pos != 999

    for threshold, labels in [
        (5,  ("top5", "top_5")),
        (10, ("top10", "top_10")),
        (20, ("top20", "top_20")),
        (30, ("top30", "top_30")),
        (40, ("top40", "top_40")),
    ]:
        if m in labels:
            return pos <= threshold

    if m in ("win", "outright", "winner", "to_win"):
        return pos == 1

    return None


def step_grade_bets(tid: str, dry_run: bool = False) -> dict:
    """
    Grade all ungraded bets for the given tournament.

    Returns a summary dict with counts.
    """
    print(f"\n{'='*60}")
    print(f"  STEP 4 — Grade bets for {tid}")
    print(f"{'='*60}")

    if not BETS_LOG.exists():
        print(f"  Bets log not found: {BETS_LOG}")
        return {}

    # ── Load leaderboard for this tournament ─────────────────────────────────
    year_match = re.search(r"R(\d{4})", tid.upper())
    year = int(year_match.group(1)) if year_match else 2026
    lb_path = HIST_DIR / f"leaderboards_{year}.csv"

    if not lb_path.exists():
        print(f"  Leaderboard file not found: {lb_path.name}  (run step 1 first)")
        return {}

    lb = pd.read_csv(lb_path, dtype=str)
    # Filter to this tournament
    lb_tid = lb[lb["tournament_id"].str.upper() == tid.upper()].copy()
    if lb_tid.empty:
        print(f"  No leaderboard rows found for {tid} in {lb_path.name}")
        return {}

    lb_tid["_pos_int"]  = lb_tid["position"].apply(_parse_pos)
    lb_tid["_name_key"] = lb_tid["player_name"].apply(_norm_name)

    # Build (name_key → final position) lookup
    pos_lookup: dict[str, int] = {}
    for _, row in lb_tid.iterrows():
        key = row["_name_key"]
        p   = row["_pos_int"]
        if p is not None and key not in pos_lookup:
            pos_lookup[key] = p

    # Build per-round score lookups (name_key → round_to_par) for round-specific matchup grading
    rnd_lookups: dict[str, dict[str, int]] = {}  # {"r1": {name_key: score}, "r2": ..., ...}
    for _rnd in ("r1", "r2", "r3", "r4"):
        col = f"{_rnd}_to_par"
        if col in lb_tid.columns:
            lk: dict[str, int] = {}
            for _, row in lb_tid.iterrows():
                key = row["_name_key"]
                s   = _parse_r_score(row.get(col))
                if s is not None and key not in lk:
                    lk[key] = s
            rnd_lookups[_rnd] = lk
    r1_lookup = rnd_lookups.get("r1", {})

    print(f"  Leaderboard: {len(pos_lookup)} players found for {tid}")

    # ── Load bets log ─────────────────────────────────────────────────────────
    bets = pd.read_csv(BETS_LOG)

    # Normalise tournament_id column for comparison
    tid_mask = bets["tournament_id"].astype(str).str.upper() == tid.upper()
    _os = bets["outcome_status"].astype(str).str.strip().str.lower()
    ungraded_mask = bets["outcome_status"].isna() | _os.isin(["", "nan", "pending"])

    target = bets[tid_mask & ungraded_mask].copy()
    print(f"  Ungraded bets for {tid}: {len(target)}")

    if target.empty:
        print("  Nothing to grade.")
        return {"graded": 0, "manual": 0, "unmatched": 0}

    graded_count = manual_count = unmatched_count = 0
    results: list[dict] = []

    for idx, row in target.iterrows():
        name_key  = _norm_name(row.get("player_name", ""))
        market    = str(row.get("market", "") or "").lower().strip()
        bet_type  = str(row.get("bet_type", "") or "").lower().strip()
        m         = market or bet_type

        # ── H2H / matchup grading (position comparison) ──────────────────────
        _h2h_rnd_match = re.match(r"h2h_r(\d)", m)
        if m in ("h2h", "matchup") or _h2h_rnd_match:
            rnd_key   = f"r{_h2h_rnd_match.group(1)}" if _h2h_rnd_match else None
            lookup    = rnd_lookups.get(rnd_key, {}) if rnd_key else pos_lookup
            score_lbl = rnd_key if rnd_key else "pos"

            # Resolve player score
            p_score = lookup.get(name_key)
            if p_score is None:
                tokens = name_key.split()
                p_score = next(
                    (v for k, v in lookup.items()
                     if len(tokens) >= 2 and k.startswith(tokens[0]) and k.split()[-1] == tokens[-1]),
                    None
                )

            # Parse and resolve opponent score
            opponent_raw = _parse_opponent(row.get("selection_label", ""))
            opp_key      = _norm_name(opponent_raw) if opponent_raw else None
            o_score      = lookup.get(opp_key) if opp_key else None
            if o_score is None and opp_key:
                tokens = opp_key.split()
                o_score = next(
                    (v for k, v in lookup.items()
                     if len(tokens) >= 2 and k.startswith(tokens[0]) and k.split()[-1] == tokens[-1]),
                    None
                )

            if p_score is None or o_score is None:
                missing = []
                if p_score is None: missing.append(row.get("player_name", "?"))
                if o_score is None: missing.append(opponent_raw or "opponent")
                unmatched_count += 1
                results.append((idx, {
                    "outcome_status": "unmatched",
                    "outcome_win": None,
                    "pnl_per_1": None,
                    "roi_pct": None,
                    "graded_at": pd.Timestamp.now().isoformat(timespec="seconds") + "Z",
                    "grade_reason": f"h2h unmatched: {', '.join(missing)}",
                }))
                continue

            stake     = float(row.get("stake_units", 1) or 1)
            dec_odds  = _american_to_decimal(row.get("odds_american"))

            if p_score < o_score:
                won    = True
                pnl    = round(stake * (dec_odds - 1), 4) if dec_odds else None
                roi    = round(pnl / stake * 100, 2) if (pnl is not None and stake) else None
                status = "won"
            elif p_score > o_score:
                won    = False
                pnl    = round(-stake, 4)
                roi    = -100.0
                status = "lost"
            else:
                # Tie / push — stake returned
                won    = None
                pnl    = 0.0
                roi    = 0.0
                status = "push"

            graded_count += 1
            opp_name = opponent_raw or opp_key or "?"
            pnl_str  = f"P&L {pnl:+.2f}" if pnl is not None else "P&L n/a"
            print(f"  {status.upper():6s}  {row.get('player_name','?'):<25} "
                  f"{m:<10} {score_lbl}={p_score} vs {opp_name} ({score_lbl}={o_score})  {pnl_str}")
            results.append((idx, {
                "outcome_status": status,
                "outcome_win": won,
                "pnl_per_1": pnl,
                "roi_pct": roi,
                "graded_at": pd.Timestamp.now().isoformat(timespec="seconds") + "Z",
                "grade_reason": f"h2h settled: {score_lbl}={p_score} vs {opp_name} ({score_lbl}={o_score})",
            }))
            continue

        # ── All other markets: positional grading ────────────────────────────
        pos = pos_lookup.get(name_key)
        if pos is None:
            tokens = name_key.split()
            pos = next(
                (p for k, p in pos_lookup.items()
                 if len(tokens) >= 2 and k.startswith(tokens[0]) and k.split()[-1] == tokens[-1]),
                None
            )

        if pos is None:
            unmatched_count += 1
            results.append((idx, {
                "outcome_status": "unmatched",
                "outcome_win": None,
                "pnl_per_1": None,
                "roi_pct": None,
                "graded_at": pd.Timestamp.now().isoformat(timespec="seconds") + "Z",
                "grade_reason": "player not found in leaderboard",
            }))
            continue

        won = _grade_market(bet_type, market, pos)

        if won is None:
            manual_count += 1
            results.append((idx, {
                "outcome_status": "manual",
                "outcome_win": None,
                "pnl_per_1": None,
                "roi_pct": None,
                "graded_at": pd.Timestamp.now().isoformat(timespec="seconds") + "Z",
                "grade_reason": f"market requires manual grade (pos={pos})",
            }))
            continue

        stake    = float(row.get("stake_units", 1) or 1)
        dec_odds = _american_to_decimal(row.get("odds_american"))

        if dec_odds is not None:
            pnl = round(stake * (dec_odds - 1), 4) if won else round(-stake, 4)
            roi = round(pnl / stake * 100, 2) if stake else None
        else:
            pnl = roi = None

        outcome_status = "won" if won else "lost"
        graded_count += 1
        results.append((idx, {
            "outcome_status": outcome_status,
            "outcome_win": won,
            "pnl_per_1": pnl,
            "roi_pct": roi,
            "graded_at": pd.Timestamp.now().isoformat(timespec="seconds") + "Z",
            "grade_reason": f"settled (pos={pos})",
        }))

        pnl_str = f"P&L {pnl:+.2f}" if pnl is not None else "P&L n/a"
        print(f"  {outcome_status.upper():6s}  {row.get('player_name','?'):<25} "
              f"{str(row.get('market','?')):<12} pos={pos:<4} {pnl_str}")

    # ── Apply updates ─────────────────────────────────────────────────────────
    if dry_run:
        print(f"\n[DRY RUN] Would update {graded_count + manual_count + unmatched_count} rows.")
    else:
        for idx, updates in results:
            for col, val in updates.items():
                if col not in bets.columns:
                    bets[col] = None
                bets.at[idx, col] = val

        # Back up then save
        backup = BETS_LOG.with_suffix(".bak.csv")
        import shutil
        shutil.copy(BETS_LOG, backup)
        bets.to_csv(BETS_LOG, index=False)
        print(f"\n  Saved → {BETS_LOG.name}  (backup → {backup.name})")

    summary = {"graded": graded_count, "manual": manual_count, "unmatched": unmatched_count}
    print(f"\n  Summary: {graded_count} graded, {manual_count} manual, {unmatched_count} unmatched")
    return summary


# ── Aggregate P&L report ──────────────────────────────────────────────────────

def pnl_report(tid: str) -> None:
    """Print a P&L summary for all graded bets in this tournament."""
    if not BETS_LOG.exists():
        return

    bets = pd.read_csv(BETS_LOG)
    sub = bets[bets["tournament_id"].astype(str).str.upper() == tid.upper()].copy()
    graded = sub[sub["outcome_status"].isin(["won", "lost", "push"])].copy()

    if graded.empty:
        print("\n  No graded bets to report.")
        return

    graded["pnl_per_1"] = pd.to_numeric(graded["pnl_per_1"], errors="coerce")
    total_pnl = graded["pnl_per_1"].sum()
    wins   = (graded["outcome_status"] == "won").sum()
    pushes = (graded["outcome_status"] == "push").sum()
    total  = len(graded)
    roi    = total_pnl / total * 100 if total else 0.0

    print(f"\n{'='*60}")
    print(f"  P&L REPORT — {tid}")
    print(f"{'='*60}")
    push_str = f"  |  Pushes: {pushes}" if pushes else ""
    print(f"  Bets: {total}  |  Wins: {wins}{push_str}  |  Win rate: {wins/total*100:.1f}%")
    print(f"  Total P&L (per 1 unit): {total_pnl:+.2f}  |  ROI: {roi:+.1f}%")

    # Break down by market
    if "market" in graded.columns:
        print(f"\n  By market:")
        for mkt, g in graded.groupby("market"):
            m_pnl = g["pnl_per_1"].sum()
            m_wins = (g["outcome_status"] == "won").sum()
            print(f"    {str(mkt):<14} {len(g):2d} bets  {m_wins} wins  P&L {m_pnl:+.2f}")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post-tournament pipeline: scrape → stats → backfill → grade bets"
    )
    parser.add_argument("--tournament-id", required=True,
                        help="R-prefixed tournament ID, e.g. R2026014")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing any files")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip step 1 (leaderboard scrape) — use if already done")
    parser.add_argument("--skip-stats", action="store_true",
                        help="Skip step 2 (form stats re-fetch)")
    parser.add_argument("--skip-backfill", action="store_true",
                        help="Skip step 3 (prediction history backfill)")
    parser.add_argument("--step", choices=["scrape", "stats", "backfill", "grade"],
                        help="Run only one specific step")
    args = parser.parse_args()

    tid = args.tournament_id.strip().upper()
    dry = args.dry_run

    print(f"\n{'='*60}")
    print(f"  POST-TOURNAMENT PIPELINE — {tid}")
    if dry:
        print(f"  DRY RUN — no files will be written")
    print(f"{'='*60}")

    if args.step == "scrape":
        step_scrape(tid, dry_run=dry)
        return
    if args.step == "stats":
        step_form_stats(tid, dry_run=dry)
        return
    if args.step == "backfill":
        step_backfill(dry_run=dry)
        return
    if args.step == "grade":
        step_grade_bets(tid, dry_run=dry)
        pnl_report(tid)
        return

    # Full pipeline
    ok = True
    if not args.skip_scrape:
        ok = step_scrape(tid, dry_run=dry)
    if ok and not args.skip_stats:
        ok = step_form_stats(tid, dry_run=dry)
    if ok and not args.skip_backfill:
        ok = step_backfill(dry_run=dry)
    if ok:
        step_grade_bets(tid, dry_run=dry)
        pnl_report(tid)

    print(f"\n{'='*60}")
    print(f"  Pipeline {'complete' if ok else 'FAILED'}.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
