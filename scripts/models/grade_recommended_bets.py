#!/usr/bin/env python3
"""
Grade tracked bet recommendations against final leaderboard results.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"
LIVE_DIR = DATA_DIR / "live"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_name_key(name: Any) -> str:
    if pd.isna(name):
        return ""
    s = str(name).strip().lower()
    if "," in s:
        parts = s.split(",", 1)
        if len(parts) == 2:
            s = f"{parts[1].strip()} {parts[0].strip()}"
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(suffix, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def canonical_market(raw: Any) -> str:
    m = str(raw or "").strip().lower()
    aliases = {
        "winner": "outright",
        "win": "outright",
        "outright_winner": "outright",
        "to_win": "outright",
        "top_5": "top5",
        "top_10": "top10",
        "top_20": "top20",
        "top_30": "top30",
        "makecut": "make_cut",
        "misscut": "miss_cut",
    }
    return aliases.get(m, m)


def american_to_prob(odds: Any) -> float:
    try:
        o = int(float(str(odds).replace(",", "").replace("+", "").strip()))
    except Exception:
        return np.nan
    if o == 0:
        return np.nan
    if o > 0:
        return 100.0 / (o + 100.0)
    return abs(o) / (abs(o) + 100.0)


def american_to_decimal(odds: Any) -> float:
    try:
        o = int(float(str(odds).replace(",", "").replace("+", "").strip()))
    except Exception:
        return np.nan
    if o == 0:
        return np.nan
    if o > 0:
        return 1.0 + (o / 100.0)
    return 1.0 + (100.0 / abs(o))


def parse_position_num(position: Any) -> int | None:
    if pd.isna(position):
        return None
    s = str(position).strip().upper()
    if not s:
        return None
    if s in {"CUT", "MC", "WD", "DQ", "DNS"}:
        return 999
    s = s.replace("T", "")
    try:
        return int(float(s))
    except Exception:
        return None


def load_leaderboard(tournament_id: str) -> pd.DataFrame:
    candidates = [
        LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv",
        LIVE_DIR / f"leaderboard_{tournament_id}.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                return pd.read_csv(p)
            except Exception:
                continue
    return pd.DataFrame()


def leaderboard_complete(lb: pd.DataFrame) -> bool:
    if lb.empty:
        return False

    if "status" in lb.columns:
        statuses = lb["status"].fillna("").astype(str).str.lower().str.strip()
        if len(statuses) > 0 and statuses.isin(["complete", "final", "finished"]).all():
            return True

    round_max = pd.to_numeric(lb.get("current_round"), errors="coerce").max() if "current_round" in lb.columns else np.nan
    thru = lb.get("thru")
    if thru is not None:
        thru_vals = thru.fillna("").astype(str).str.upper().str.strip()
        all_finished = thru_vals.isin(["F", "F*", "18", ""]).all()
        if all_finished and (pd.isna(round_max) or round_max >= 4):
            return True

    return False


def build_player_result_lookup(lb: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if lb.empty:
        return out

    for _, row in lb.iterrows():
        k = normalize_name_key(row.get("player_name", ""))
        if not k:
            continue

        pos_num = parse_position_num(row.get("position", ""))
        made_cut = row.get("made_cut", np.nan)
        if isinstance(made_cut, str):
            made_cut = made_cut.strip().lower() in {"true", "1", "yes", "y"}

        out[k] = {
            "position_num": pos_num,
            "made_cut": made_cut if isinstance(made_cut, (bool, np.bool_)) else np.nan,
        }

    return out


def _parse_card_leg_label(label: str) -> dict[str, str]:
    s = str(label or "").strip()
    low = s.lower()

    m_top = re.search(r"\bto\s+finish\s+top\s*(5|10|20|30)\b", low)
    if m_top:
        n = m_top.group(1)
        player = re.sub(r"\s+to\s+finish\s+top\s*\d+.*$", "", s, flags=re.I).strip()
        return {"market": f"top{n}", "player": player, "raw": s}

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


def evaluate_market_outcome(market: str, player_key: str, player_results: dict[str, dict[str, Any]]) -> bool | None:
    m = canonical_market(market)
    row = player_results.get(player_key)
    if row is None:
        return None

    pos_num = row.get("position_num", None)
    made_cut = row.get("made_cut", np.nan)

    if m in {"outright", "winner"}:
        return pos_num == 1
    if m == "top5":
        return (pos_num is not None) and (pos_num <= 5)
    if m == "top10":
        return (pos_num is not None) and (pos_num <= 10)
    if m == "top20":
        return (pos_num is not None) and (pos_num <= 20)
    if m == "top30":
        return (pos_num is not None) and (pos_num <= 30)
    if m == "make_cut":
        if isinstance(made_cut, (bool, np.bool_)):
            return bool(made_cut)
        if pos_num is not None:
            return pos_num < 999
        return None
    if m == "miss_cut":
        if isinstance(made_cut, (bool, np.bool_)):
            return not bool(made_cut)
        if pos_num is not None:
            return pos_num == 999
        return None

    return None


def resolve_closing_odds_maps(tournament_id: str) -> tuple[dict[tuple[str, str], int], dict[str, int]]:
    single_map: dict[tuple[str, str], int] = {}
    card_map: dict[str, int] = {}

    prop_path = ODDS_DIR / f"prop_lines_{tournament_id}.csv"
    if prop_path.exists():
        try:
            lines = pd.read_csv(prop_path)
            for _, row in lines.iterrows():
                market = canonical_market(row.get("market", ""))
                player = normalize_name_key(row.get("player_name", ""))
                if not market or not player:
                    continue
                try:
                    odds = int(float(row.get("odds")))
                except Exception:
                    continue
                single_map[(market, player)] = odds
        except Exception:
            pass

    cards_path = ODDS_DIR / f"dk_content_cards_{tournament_id}.csv"
    if cards_path.exists():
        try:
            cards = pd.read_csv(cards_path)
            for _, row in cards.iterrows():
                cid = str(row.get("card_id", "") or "").strip()
                if not cid:
                    continue
                try:
                    odds = int(float(row.get("odds_american")))
                except Exception:
                    continue
                card_map[cid] = odds
        except Exception:
            pass

    return single_map, card_map


def settle_row(
    row: pd.Series,
    player_results: dict[str, dict[str, Any]],
    close_single_map: dict[tuple[str, str], int],
    close_card_map: dict[str, int],
) -> tuple[str, bool | None, float | None, str, float | None, float | None, float | None]:
    """
    Returns:
        outcome_status, outcome_win, pnl_per_1, reason, close_odds, close_prob, clv_pts
    """
    bet_type = str(row.get("bet_type", "single") or "single").strip().lower()

    open_odds = pd.to_numeric(row.get("odds_american"), errors="coerce")
    open_prob = american_to_prob(open_odds) if pd.notna(open_odds) else np.nan

    if bet_type == "single":
        market = canonical_market(row.get("market", ""))
        player_key = normalize_name_key(row.get("player_name", ""))
        if not market or not player_key:
            return "pending", None, None, "missing market/player", None, None, None

        outcome = evaluate_market_outcome(market, player_key, player_results)
        if outcome is None:
            return "pending", None, None, "missing player result or unsupported market", None, None, None

        close_odds = close_single_map.get((market, player_key))
        close_prob = american_to_prob(close_odds) if close_odds is not None else np.nan
        clv_pts = (close_prob - open_prob) * 100.0 if pd.notna(close_prob) and pd.notna(open_prob) else np.nan

    elif bet_type == "content_card":
        labels: list[str] = []
        raw_json = row.get("selection_labels_json", "")
        if pd.notna(raw_json) and str(raw_json).strip() not in {"", "nan", "None"}:
            try:
                parsed = json.loads(raw_json)
                if isinstance(parsed, list):
                    labels = [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                labels = []

        if not labels:
            raw = str(row.get("selection_labels", "") or "").strip()
            if raw:
                labels = [s.strip() for s in re.split(r"\s*\|\s*", raw) if s.strip()]

        if not labels:
            return "pending", None, None, "no card legs", None, None, None

        leg_outcomes: list[bool] = []
        unresolved = 0
        for leg in labels:
            p = _parse_card_leg_label(leg)
            market = p.get("market", "unknown")
            player = p.get("player", "")
            if market == "unknown" or not player:
                unresolved += 1
                continue
            o = evaluate_market_outcome(market, normalize_name_key(player), player_results)
            if o is None:
                unresolved += 1
                continue
            leg_outcomes.append(bool(o))

        if unresolved > 0:
            return "pending", None, None, f"{unresolved} legs unresolved", None, None, None

        outcome = all(leg_outcomes)

        card_id = str(row.get("card_id", "") or "").strip()
        close_odds = close_card_map.get(card_id)
        close_prob = american_to_prob(close_odds) if close_odds is not None else np.nan
        clv_pts = (close_prob - open_prob) * 100.0 if pd.notna(close_prob) and pd.notna(open_prob) else np.nan

    else:
        return "pending", None, None, f"unsupported bet type: {bet_type}", None, None, None

    dec = american_to_decimal(open_odds) if pd.notna(open_odds) else np.nan
    if pd.isna(dec):
        return "pending", None, None, "invalid odds", None, None, None

    pnl_per_1 = float(dec - 1.0) if outcome else -1.0
    return ("won" if outcome else "lost"), bool(outcome), pnl_per_1, "settled", close_odds, close_prob, clv_pts


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "outcome_status": "pending",
        "outcome_win": np.nan,
        "pnl_per_1": np.nan,
        "roi_pct": np.nan,
        "closing_odds_american": np.nan,
        "closing_implied_prob": np.nan,
        "clv_pts": np.nan,
        "graded_at": "",
    }
    work = df.copy()
    for c, d in defaults.items():
        if c not in work.columns:
            work[c] = d
    return work


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade tracked bet recommendations")
    parser.add_argument("--tournament-id", default="", help="Only grade this tournament id")
    parser.add_argument("--recommendations-log", default=str(ODDS_DIR / "recommended_bets_log.csv"))
    parser.add_argument("--results-out", default=str(ODDS_DIR / "recommended_bets_results.csv"))
    parser.add_argument("--all", action="store_true", help="Grade all rows, not just pending")
    parser.add_argument("--allow-incomplete", action="store_true", help="Attempt grading even if tournament not complete")
    args = parser.parse_args()

    log_path = Path(args.recommendations_log)
    results_path = Path(args.results_out)

    if not log_path.exists():
        print(f"Recommendations log not found: {log_path}")
        return 0

    log_df = pd.read_csv(log_path)
    if log_df.empty:
        print("Recommendations log is empty.")
        return 0

    log_df = ensure_columns(log_df)

    if args.tournament_id:
        tid = str(args.tournament_id).strip().upper()
        log_df = log_df[log_df["tournament_id"].astype(str).str.upper() == tid].copy()

    if log_df.empty:
        print("No matching recommendations to grade.")
        return 0

    if not args.all:
        pending_mask = log_df["outcome_status"].fillna("pending").astype(str).str.lower().isin(["", "pending"])
        target_df = log_df[pending_mask].copy()
    else:
        target_df = log_df.copy()

    if target_df.empty:
        print("No pending recommendations to grade.")
        return 0

    graded_rows: list[pd.Series] = []
    updates = 0

    for tid, tdf in target_df.groupby("tournament_id"):
        tid = str(tid).strip().upper()
        if not tid:
            continue

        lb = load_leaderboard(tid)
        if lb.empty:
            continue

        if not args.allow_incomplete and not leaderboard_complete(lb):
            continue

        player_results = build_player_result_lookup(lb)
        close_single_map, close_card_map = resolve_closing_odds_maps(tid)

        for idx, row in tdf.iterrows():
            outcome_status, outcome_win, pnl_per_1, reason, close_odds, close_prob, clv_pts = settle_row(
                row,
                player_results,
                close_single_map,
                close_card_map,
            )

            if outcome_status == "pending":
                continue

            global_idx = row.name
            log_df.loc[global_idx, "outcome_status"] = outcome_status
            log_df.loc[global_idx, "outcome_win"] = outcome_win
            log_df.loc[global_idx, "pnl_per_1"] = pnl_per_1
            log_df.loc[global_idx, "roi_pct"] = pnl_per_1 * 100.0 if pd.notna(pnl_per_1) else np.nan
            log_df.loc[global_idx, "closing_odds_american"] = close_odds
            log_df.loc[global_idx, "closing_implied_prob"] = close_prob
            log_df.loc[global_idx, "clv_pts"] = clv_pts
            log_df.loc[global_idx, "graded_at"] = now_utc_iso()
            log_df.loc[global_idx, "grade_reason"] = reason

            graded_rows.append(log_df.loc[global_idx].copy())
            updates += 1

    if updates == 0:
        print("No recommendations could be settled yet.")
        return 0

    # Persist updated log.
    log_df.to_csv(log_path, index=False)

    # Persist results ledger.
    graded_df = pd.DataFrame(graded_rows)
    if results_path.exists():
        try:
            prev = pd.read_csv(results_path)
            combined = pd.concat([prev, graded_df], ignore_index=True)
        except Exception:
            combined = graded_df.copy()
    else:
        combined = graded_df.copy()

    if "recommendation_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["recommendation_id"], keep="last")
    combined.to_csv(results_path, index=False)

    settled = graded_df[graded_df["outcome_status"].isin(["won", "lost"])].copy()
    hit_rate = float((settled["outcome_status"] == "won").mean() * 100.0) if not settled.empty else 0.0
    roi_pct = float(pd.to_numeric(settled["pnl_per_1"], errors="coerce").mean() * 100.0) if not settled.empty else 0.0

    print(f"Settled {updates} recommendations")
    print(f"  Hit rate: {hit_rate:.1f}% | Avg ROI per bet: {roi_pct:+.1f}%")
    print(f"Updated log -> {log_path}")
    print(f"Updated results -> {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
