#!/usr/bin/env python3
"""
Deterministic Bet Recommendation Engine (v1)
===========================================

Generates tracked recommendations from model predictions + sportsbook odds.
Outputs per-tournament recommendations and appends an audit log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


TID_PATTERN = re.compile(r"(R\d{7})", re.IGNORECASE)


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


def extract_tournament_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    m = TID_PATTERN.search(str(value))
    return m.group(1).upper() if m else ""


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


def parse_american(odds: Any) -> int | None:
    try:
        o = int(float(str(odds).replace(",", "").replace("+", "").strip()))
        return o if o != 0 else None
    except Exception:
        return None


def kelly_fraction(model_prob: float, decimal_odds: float,
                   fraction: float = 0.5, cap: float = 0.05) -> float:
    """Return fractional Kelly stake as a fraction of bankroll (0–cap).

    Uses half-Kelly by default (fraction=0.5) to reduce variance.
    Caps at 5% of bankroll regardless of edge size.
    Returns 0.0 for negative-edge or invalid inputs.
    """
    b = decimal_odds - 1.0
    if b <= 0 or not (0.0 < model_prob < 1.0):
        return 0.0
    f = (model_prob * b - (1.0 - model_prob)) / b
    return round(min(max(f, 0.0), cap) * fraction, 4)


def build_consensus_book_probs(tournament_id: str,
                                preds_df: pd.DataFrame) -> dict[str, float]:
    """Build a no-vig consensus outright win probability per player.

    Reads dg_outrights_{tid}.csv (DataGolf win market rows, 10+ books including
    DK, FanDuel, Pinnacle, Bet365, BetMGM, Caesars, Bovada, BetOnline).
    For each book normalizes raw implied probs to sum to 1.0, then returns
    the median across books as name_key → prob.

    Falls back to empty dict if DG file absent — callers use DK raw implied_prob.
    """
    dg_path = DATA_DIR / "datagolf" / f"dg_outrights_{tournament_id}.csv"
    if not dg_path.exists():
        return {}

    try:
        dg = pd.read_csv(dg_path)
    except Exception:
        return {}

    if "market" not in dg.columns or "player_name" not in dg.columns:
        return {}

    win_rows = dg[dg["market"].astype(str).str.lower() == "win"].copy()
    if win_rows.empty:
        return {}

    # Use odds_american col; convert to prob
    if "odds_american" not in win_rows.columns:
        return {}
    win_rows["raw_prob"] = win_rows["odds_american"].apply(
        lambda x: american_to_prob(parse_american(x))
    )
    win_rows = win_rows[win_rows["raw_prob"].notna() & (win_rows["raw_prob"] > 0)]

    book_probs: dict[str, list[float]] = {}
    books_loaded = []
    for book, grp in win_rows.groupby("book"):
        total = grp["raw_prob"].sum()
        if total <= 0:
            continue
        nv = grp["raw_prob"] / total
        for name, prob in zip(grp["player_name"], nv):
            key = normalize_name_key(name)
            if key:
                book_probs.setdefault(key, []).append(float(prob))
        books_loaded.append(str(book))

    if not book_probs:
        return {}

    print(f"  Consensus: loaded DG outrights ({len(books_loaded)} books: {', '.join(books_loaded)})")
    return {k: float(np.median(v)) for k, v in book_probs.items()}


def build_prop_consensus_probs(
    lines_df: pd.DataFrame,
) -> dict[tuple[str, str, str], float]:
    """Build per-book, per-market no-vig probability for each player.

    Computes a proper per-book no-vig probability by normalising each
    book's raw implied probs so they sum to ``expected_spots``.  Keyed
    by (player_name_key, canonical_market, book).

    Why this matters: when lines_df contains both DK and FanDuel lines,
    the old ``_market_vig`` approach sums ALL books together, halving the
    effective vig factor and inflating computed edges.  This function
    fixes that by isolating each book before normalising.

    Example
    -------
    DK  top10 for Rory: raw 0.600 / DK_sum(15.3) * 10 → 0.392 no-vig
    FD  top10 for Rory: raw 0.550 / FD_sum(14.8) * 10 → 0.372 no-vig
    Edge vs DK  = model_prob - 0.392
    Edge vs FD  = model_prob - 0.372
    (previously both would have used the same badly-mixed value ~0.19)
    """
    # Pool markets: probabilities compete for a fixed number of spots → vig = sum/spots
    # Binary markets: each bet is independent (makes cut yes/no) → vig = ~5% flat
    POOL_MARKETS = {"top5", "top10", "top20", "top30", "r2_leader"}
    BINARY_MARKETS = {"make_cut", "miss_cut"}
    PROP_MARKETS = POOL_MARKETS | BINARY_MARKETS
    EXPECTED_SPOTS: dict[str, float] = {
        "top5": 5.0, "top10": 10.0, "top20": 20.0, "top30": 30.0, "r2_leader": 1.0,
    }
    BINARY_VIG_FACTOR = 1.05   # typical ~5% book margin on two-way props

    if lines_df.empty or "book" not in lines_df.columns:
        return {}

    work = lines_df.copy()
    work["_mkt"]  = work["market"].astype(str).str.lower().map(canonical_market)
    work["_key"]  = work["player_name"].apply(normalize_name_key)
    work["_book"] = work["book"].fillna("UNKNOWN").astype(str).str.upper()
    work["_raw"]  = work["odds"].apply(lambda o: american_to_prob(parse_american(o)) or 0.0)
    work = work[work["_mkt"].isin(PROP_MARKETS) & (work["_raw"] > 0)].copy()

    if work.empty:
        return {}

    result: dict[tuple[str, str, str], float] = {}
    log_parts: list[str] = []

    for (mkt, book), grp in work.groupby(["_mkt", "_book"]):
        total = grp["_raw"].sum()
        if total <= 0:
            continue
        if mkt in BINARY_MARKETS:
            # Binary market: each player bet is independent — apply flat vig removal
            for _, row in grp.iterrows():
                k = (str(row["_key"]), str(mkt), str(book))
                result[k] = float(row["_raw"]) / BINARY_VIG_FACTOR
        else:
            # Pool market: normalize so probs sum to expected_spots
            exp   = EXPECTED_SPOTS.get(mkt, 10.0)
            scale = exp / total
            for _, row in grp.iterrows():
                k = (str(row["_key"]), str(mkt), str(book))
                result[k] = float(row["_raw"]) * scale
        log_parts.append(f"{book}/{mkt}:{len(grp)}")

    if result:
        print(f"  Prop no-vig (per book): {', '.join(log_parts)}")
    return result


def load_pga_market_odds(tournament_id: str) -> pd.DataFrame:
    """Convert pga_market_odds_{tid}.csv into prop_lines-compatible format.

    Market mappings:
      FINISH  "Top 5 Finish"  → top5
      FINISH  "Top 10 Finish" → top10
      FINISH  "Top 20 Finish" → top20
      MATCHUP_PROPS           → h2h   (one row per pair with player_a/b/odds_a/b)
      THREE_BALL + GROUP      → group_winner (one row per player per group)

    Returns a DataFrame that can be pd.concat-ed with the DK prop_lines_df.
    """
    path = resolve_pga_market_path(tournament_id)
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"  PGA market odds load error: {e}")
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    # ── FINISH: Top 5 / 10 / 20 ──────────────────────────────────────────────
    # Two submarket variants exist: "Top 10" (no ties) and "Top 10 Finish (Incl. Ties)".
    # FanDuel's standard product is the Incl. Ties version — that's what appears on
    # pgatour.com and what bettors actually bet. The bare "Top 10" has tighter odds
    # (exact top-10 without ties). We only use the "Finish" variant.
    def _sub_to_market(sub: str) -> str | None:
        s = sub.strip().lower()
        if "finish" not in s:
            return None  # skip bare "Top 10" / "Top 5" — use only "Top N Finish (Incl. Ties)"
        if "top 5" in s: return "top5"
        if "top 10" in s: return "top10"
        if "top 20" in s: return "top20"
        return None

    finish_df = df[df["market_type"] == "FINISH"].copy()
    _seen_finish: set = set()  # deduplicate player+market combos (multiple submarket variants)
    for _, row in finish_df.iterrows():
        sub = str(row.get("submarket_name", "")).strip()
        mkt = _sub_to_market(sub)
        if not mkt:
            continue
        player = str(row.get("player_name", "")).strip()
        odds_num = row.get("odds_numeric")
        if not player or pd.isna(odds_num):
            continue
        _fkey = (player, mkt)
        if _fkey in _seen_finish:
            continue  # skip duplicate submarket variant (e.g. "Top 10" and "Top 10 Finish (Incl. Ties)")
        _seen_finish.add(_fkey)
        rows.append({
            "market":      mkt,
            "player_name": player,
            "odds":        int(odds_num),
            "implied_prob": row.get("implied_prob", np.nan),
            "book":        "FANDUEL",
        })

    # ── MATCHUP_PROPS: H2H (pivot pairs into one row per matchup) ────────────
    matchup_df = df[df["market_type"] == "MATCHUP_PROPS"].copy()
    if not matchup_df.empty and "bet_group_id" in matchup_df.columns:
        for _gid, grp in matchup_df.groupby("bet_group_id"):
            grp = grp.reset_index(drop=True)
            if len(grp) != 2:
                continue
            pa = str(grp.iloc[0]["player_name"]).strip()
            pb = str(grp.iloc[1]["player_name"]).strip()
            odds_a = grp.iloc[0]["odds_numeric"]
            odds_b = grp.iloc[1]["odds_numeric"]
            if not pa or not pb or pd.isna(odds_a) or pd.isna(odds_b):
                continue
            sub = str(grp.iloc[0].get("submarket_name", ""))
            round_m = re.search(r"Round\s+(\d)", sub, re.I)
            round_num = int(round_m.group(1)) if round_m else np.nan
            rows.append({
                "market":      "h2h",
                "player_name": pa,
                "player_a":    pa,
                "player_b":    pb,
                "odds":        int(odds_a),
                "odds_a":      int(odds_a),
                "odds_b":      int(odds_b),
                "implied_prob": grp.iloc[0].get("implied_prob", np.nan),
                "book":        "FANDUEL",
                "round_num":   round_num,
                "event_name":  str(grp.iloc[0].get("tournament_name", "")),
            })

    # ── Country lookup for NATIONALITY groups ────────────────────────────────
    _player_country: dict[str, str] = {}
    _players_path = DATA_DIR / "players" / "pga_players_2026.csv"
    if _players_path.exists():
        try:
            _pdb = pd.read_csv(_players_path, usecols=["player_id", "country"])
            _pdb["player_id"] = _pdb["player_id"].apply(
                lambda x: str(int(float(x))) if pd.notna(x) else ""
            )
            _player_country = dict(zip(_pdb["player_id"], _pdb["country"].fillna("")))
        except Exception:
            pass

    # ── THREE_BALL + GROUP + NATIONALITY: group winner (one row per player) ──
    group_df = df[df["market_type"].isin(["THREE_BALL", "GROUP", "NATIONALITY"])].copy()
    if not group_df.empty and "bet_group_id" in group_df.columns:
        for _gid, grp in group_df.groupby("bet_group_id"):
            grp = grp.reset_index(drop=True)
            if len(grp) < 2:
                continue
            sub = str(grp.iloc[0].get("submarket_name", ""))
            round_m = re.search(r"Round\s+(\d)", sub, re.I)
            round_num = int(round_m.group(1)) if round_m else np.nan
            mtype = str(grp.iloc[0].get("market_type", ""))
            for _, prow in grp.iterrows():
                player = str(prow["player_name"]).strip()
                odds_num = prow["odds_numeric"]
                if not player or pd.isna(odds_num):
                    continue
                pid = str(int(float(prow.get("player_id", 0) or 0)))
                country = _player_country.get(pid, "") if mtype == "NATIONALITY" else ""
                rows.append({
                    "market":      "group_winner",
                    "player_name": player,
                    "player_a":    player,
                    "odds":        int(odds_num),
                    "odds_a":      int(odds_num),
                    "implied_prob": prow.get("implied_prob", np.nan),
                    "book":        "FANDUEL",
                    "round_num":   round_num,
                    "market_name": str(_gid),   # used for groupby in score_group_winner_markets
                    "event_name":  str(grp.iloc[0].get("tournament_name", "")),
                    "group_title": sub,          # e.g. "Top African Player", "Best Score - Round 2"
                    "market_subtype": mtype,     # THREE_BALL / GROUP / NATIONALITY
                    "player_country": country,   # e.g. "South Africa" — only set for NATIONALITY
                })

    # ── TOURNAMENT_PROPS: Wire to Wire Winner ────────────────────────────────
    tp_df = df[df["market_type"] == "TOURNAMENT_PROPS"].copy()
    if not tp_df.empty:
        for _, row in tp_df.iterrows():
            sub = str(row.get("submarket_name", "")).strip().lower()
            player = str(row.get("player_name", "")).strip()
            odds_num = row.get("odds_numeric")
            if not player or pd.isna(odds_num):
                continue
            if "wire" in sub:
                rows.append({
                    "market":       "wire_to_wire",
                    "player_name":  player,
                    "odds":         int(odds_num),
                    "implied_prob": row.get("implied_prob", np.nan),
                    "book":         "FANDUEL",
                })

    # ── PLAYER_PROPS: Leader After Round N → r2_leader / To Make The Cut → make_cut ──
    pp_df = df[df["market_type"] == "PLAYER_PROPS"].copy()
    if not pp_df.empty:
        for _, row in pp_df.iterrows():
            sub = str(row.get("submarket_name", "")).strip().lower()
            player = str(row.get("player_name", "")).strip()
            odds_num = row.get("odds_numeric")
            if not player or pd.isna(odds_num):
                continue
            if "leader after round" in sub:
                rows.append({
                    "market":      "r2_leader",
                    "player_name": player,
                    "odds":        int(odds_num),
                    "implied_prob": row.get("implied_prob", np.nan),
                    "book":        "FANDUEL",
                })
            elif "make the cut" in sub or "to make the cut" in sub:
                rows.append({
                    "market":      "make_cut",
                    "player_name": player,
                    "odds":        int(odds_num),
                    "implied_prob": row.get("implied_prob", np.nan),
                    "book":        "FANDUEL",
                })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    mkt_counts = result["market"].value_counts().to_dict()
    print(f"  PGA market odds loaded: {mkt_counts}")
    return result


def resolve_tournament_id(explicit_tid: str = "") -> str:
    tid = extract_tournament_id(explicit_tid)
    if tid:
        return tid

    # Prefer FanDuel/PGA market odds files (primary source)
    fd_files = sorted(ODDS_DIR.glob("pga_market_odds_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if fd_files:
        return extract_tournament_id(fd_files[0].stem.replace("pga_market_odds_", ""))

    # Fall back to DK prop lines if available
    prop_files = sorted(ODDS_DIR.glob("prop_lines_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if prop_files:
        return extract_tournament_id(prop_files[0].stem)
    return ""


def resolve_predictions_path(tid: str, explicit: str = "") -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p

    candidates: list[Path] = []

    # Tournament-specific latest file heuristic.
    if tid:
        for p in OUTPUTS_DIR.glob("*_latest.csv"):
            try:
                d = pd.read_csv(p, nrows=1)
                if not d.empty and "tournament_id" in d.columns:
                    file_tid = extract_tournament_id(d.iloc[0].get("tournament_id", ""))
                    if file_tid == tid:
                        candidates.append(p)
            except Exception:
                continue

    candidates.extend([
        OUTPUTS_DIR / "latest_predictions.csv",
        OUTPUTS_DIR / "latest.csv",
    ])

    # Recent fallback.
    recent_csvs = sorted(OUTPUTS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates.extend(recent_csvs[:20])

    seen: set[Path] = set()
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            return c
    return None


def resolve_prop_lines_path(tid: str, explicit: str = "") -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    if tid:
        p = ODDS_DIR / f"prop_lines_{tid}.csv"
        if p.exists():
            return p
    files = sorted(ODDS_DIR.glob("prop_lines_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def resolve_pga_market_path(tid: str) -> Path | None:
    """Locate pga_market_odds_{tid}.csv."""
    if tid:
        p = ODDS_DIR / f"pga_market_odds_{tid}.csv"
        if p.exists():
            return p
    return None


def resolve_cards_path(tid: str, explicit: str = "") -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    if tid:
        p = ODDS_DIR / f"dk_content_cards_{tid}.csv"
        if p.exists():
            return p
    latest = ODDS_DIR / "dk_content_cards_latest.csv"
    if latest.exists():
        return latest
    files = sorted(ODDS_DIR.glob("dk_content_cards_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


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


def market_prob_from_prediction(row: dict, market: str) -> tuple[float, bool]:
    market = canonical_market(market)
    # Live columns (updated by live_update_predictions.py after each round) are
    # preferred when available — they blend actual scores into model probabilities.
    pref_cols: dict[str, list[str]] = {
        "outright": ["live_win_prob",   "win_prob_calibrated", "win_prob", "win_prob_raw"],
        "top5":     ["live_top5_prob",  "top5_prob_calibrated", "top5_prob", "top5_prob_raw"],
        "top10":    ["live_top10_prob", "top10_prob_calibrated", "top10_prob", "top10_prob_raw"],
        "top20":    ["live_top20_prob", "top20_prob", "top20_prob_raw"],
        "top30":    ["top30_prob", "top20_prob"],
        "make_cut": ["make_cut_prob", "cut_prob"],
        "miss_cut": ["miss_cut_prob"],
        "r2_leader": ["live_win_prob",  "win_prob_calibrated", "win_prob", "win_prob_raw"],
    }

    cols = pref_cols.get(market, [])
    if market == "miss_cut":
        for c in cols:
            v = pd.to_numeric(row.get(c), errors="coerce")
            if pd.notna(v):
                return float(np.clip(v, 0.0, 1.0)), False
        cp = pd.to_numeric(row.get("cut_prob"), errors="coerce")
        if pd.notna(cp):
            return float(np.clip(1.0 - cp, 0.0, 1.0)), False
        return np.nan, False

    for c in cols:
        v = pd.to_numeric(row.get(c), errors="coerce")
        if pd.notna(v):
            return float(np.clip(v, 0.0, 1.0)), c.endswith("_calibrated")

    if market == "top30":
        t20 = pd.to_numeric(row.get("top20_prob"), errors="coerce")
        if pd.notna(t20):
            return float(np.clip(min(0.985, float(t20) * 1.30 + 0.05), 0.0, 1.0)), False

    return np.nan, False


def confidence_for_single(pred_row: dict, market: str, calibrated: bool, odds: int | None,
                          model_prob: float | None = None, book_prob: float | None = None) -> float:
    """Compute confidence score for a single-market bet recommendation.

    Confidence captures how much we trust the edge estimate, not just the
    probability.  Key drivers:
    - Base by market type (make_cut is most reliable, outright least)
    - +0.08 if model probability is calibrated (from calibrated columns)
    - +0.05 if model and market agree directionally (both above/below 50%)
    - +0.04 if model-market gap is moderate (2–10pp) — large gaps are noisy
    - +0.03 for course history (reduces uncertainty)
    - Penalties for extreme longshots (model less reliable far down the board)
    """
    base = {
        "outright":    0.58,
        "top5":        0.66,
        "top10":       0.72,
        "top20":       0.78,
        "top30":       0.70,
        "make_cut":    0.76,
        "miss_cut":    0.70,
        "h2h":         0.72,
        "h2h_r1":      0.72,
        "h2h_r2":      0.70,
        "group_winner":0.65,
        "nationality_group": 0.60,
        "wire_to_wire":0.50,
        "r2_leader":   0.55,
    }.get(canonical_market(market), 0.55)

    conf = base

    if calibrated:
        conf += 0.08

    # Model-market alignment boost: when both point the same direction, edge is more reliable
    if model_prob is not None and book_prob is not None:
        mp = float(model_prob)
        bp = float(book_prob)
        gap = abs(mp - bp)
        if 0.02 <= gap <= 0.12:
            # Moderate gap: edge estimate is cleanest here
            conf += 0.04
        if gap > 0.15:
            # Very large gap: model and market disagree a lot — more uncertainty
            conf -= 0.03

    hist_times = pd.to_numeric(pred_row.get("hist_times_played"), errors="coerce")
    hist_n = float(hist_times) if pd.notna(hist_times) else 0.0
    if hist_n >= 2:
        conf += 0.03
    elif hist_n == 0 and canonical_market(market) in ("make_cut", "miss_cut", "top10", "top20"):
        # No history at this course: model is extrapolating — reduce confidence
        conf -= 0.03

    has_history = pred_row.get("has_course_history")
    if isinstance(has_history, (bool, np.bool_)) and bool(has_history):
        conf += 0.02

    # Form trend boost: strong recent form reduces model uncertainty
    form = pd.to_numeric(pred_row.get("form_trend"), errors="coerce")
    if pd.notna(form) and abs(float(form)) >= 0.3:
        conf += 0.02

    if odds is not None:
        if abs(odds) > 10000:
            conf -= 0.10
        elif abs(odds) > 5000:
            conf -= 0.06
        elif abs(odds) > 2000:
            conf -= 0.02

    return float(np.clip(conf, 0.20, 0.95))


def selection_label_for_market(market: str, player: str) -> str:
    m = canonical_market(market)
    if m == "outright":
        return f"{player} to Win"
    if m == "top5":
        return f"{player} Top 5"
    if m == "top10":
        return f"{player} Top 10"
    if m == "top20":
        return f"{player} Top 20"
    if m == "top30":
        return f"{player} Top 30"
    if m == "make_cut":
        return f"{player} to Make Cut"
    if m == "miss_cut":
        return f"{player} to Miss Cut"
    if m == "r2_leader":
        return f"{player} to Lead After R2"
    return f"{player} {m}"


def _extract_card_leg_labels(card_row: pd.Series) -> list[str]:
    labels: list[str] = []

    raw_json = card_row.get("selection_labels_json", "")
    if pd.notna(raw_json) and str(raw_json).strip() not in ["", "nan", "None"]:
        try:
            arr = json.loads(raw_json)
            if isinstance(arr, list):
                labels.extend([str(x).strip() for x in arr if str(x).strip()])
        except Exception:
            pass

    if not labels:
        raw = str(card_row.get("selection_labels", "") or "").strip()
        if raw:
            labels = [s.strip() for s in re.split(r"\s*\|\s*", raw) if s.strip()]

    return labels


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


def score_content_cards(cards_df: pd.DataFrame, preds_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if cards_df.empty or preds_df.empty or "player_name" not in preds_df.columns:
        return pd.DataFrame(), pd.DataFrame()

    work = preds_df.copy()
    work["player_name"] = work["player_name"].fillna("").astype(str).str.strip()
    work = work[work["player_name"] != ""].copy()
    if work.empty:
        return pd.DataFrame(), pd.DataFrame()

    work["name_key"] = work["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in work.iterrows() if r["name_key"]}

    last_name_map: dict[str, list[dict]] = {}
    for _, r in work.iterrows():
        pname = str(r["player_name"]).strip()
        toks = re.sub(r"[^a-z0-9, ]+", " ", pname.lower()).replace(",", " ").split()
        if toks:
            last_name_map.setdefault(toks[-1], []).append(r.to_dict())

    def resolve_player(name_text: str) -> dict | None:
        k = normalize_name_key(name_text)
        if k in by_key:
            return by_key[k]
        toks = [t for t in re.sub(r"[^a-z0-9 ]+", " ", str(name_text).lower()).split() if t]
        if len(toks) == 1:
            cands = last_name_map.get(toks[0], [])
            if len(cands) == 1:
                return cands[0]
        return None

    card_rows = []
    leg_rows = []

    for _, card in cards_df.iterrows():
        legs = _extract_card_leg_labels(card)
        if not legs:
            continue

        leg_probs: list[float] = []
        priced_legs = 0
        unpriced_legs = 0
        players_in_card: list[str] = []
        markets_in_card: list[str] = []

        for leg in legs:
            parsed = _parse_card_leg_label(leg)
            market = parsed.get("market", "unknown")
            player_txt = parsed.get("player", "")
            p_row = resolve_player(player_txt) if player_txt else None
            p_prob = np.nan

            if p_row is not None and market != "unknown":
                p_prob, _ = market_prob_from_prediction(p_row, market)

            if pd.notna(p_prob):
                leg_probs.append(float(p_prob))
                priced_legs += 1
                if player_txt:
                    players_in_card.append(normalize_name_key(player_txt))
                markets_in_card.append(str(market))
                status = "priced"
            else:
                unpriced_legs += 1
                status = "unpriced"

            leg_rows.append(
                {
                    "card_id": card.get("card_id", ""),
                    "title": card.get("title", ""),
                    "leg_label": leg,
                    "market": market,
                    "player": player_txt,
                    "model_prob": p_prob,
                    "status": status,
                }
            )

        total_legs = len(legs)
        book_odds = parse_american(card.get("odds_american"))
        book_prob = american_to_prob(book_odds) if book_odds is not None else np.nan
        book_dec = american_to_decimal(book_odds) if book_odds is not None else np.nan

        model_prob = np.nan
        edge_pts = np.nan
        ev_per_1 = np.nan
        status = "unpriced"

        if leg_probs and pd.notna(book_prob) and pd.notna(book_dec):
            base_prob = float(np.prod(leg_probs))
            dup_players = max(0, len(players_in_card) - len(set(players_in_card)))
            dup_markets = max(0, len(markets_in_card) - len(set(markets_in_card)))
            corr_penalty = (0.92 ** dup_players) * (0.97 ** dup_markets) * (0.98 ** max(0, total_legs - 1))
            model_prob = float(np.clip(base_prob * corr_penalty, 0.0, 0.999))
            edge_pts = (model_prob - book_prob) * 100.0
            ev_per_1 = (model_prob * book_dec) - 1.0
            status = "priced" if unpriced_legs == 0 else "partial"

        confidence = float(np.clip(priced_legs / max(1, total_legs), 0.0, 1.0))

        # Per-leg summary: "Player (market): XX%" joined by " | "
        # Find weakest leg (lowest model prob) for display
        leg_summary_parts = []
        weakest_leg = ""
        weakest_prob = 1.0
        for lr in leg_rows[-total_legs:]:  # last N rows belong to this card
            p = lr.get("model_prob")
            lbl = str(lr.get("leg_label", ""))
            if pd.notna(p):
                leg_summary_parts.append(f"{lbl}:{float(p)*100:.0f}%")
                if float(p) < weakest_prob:
                    weakest_prob = float(p)
                    weakest_leg = lbl
        leg_prob_summary = " | ".join(leg_summary_parts)

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
                "selection_labels_json": card.get("selection_labels_json", ""),
                "leg_prob_summary": leg_prob_summary,
                "weakest_leg": weakest_leg,
                "weakest_leg_prob": weakest_prob if leg_summary_parts else np.nan,
            }
        )

    cards_scored = pd.DataFrame(card_rows)
    legs_scored = pd.DataFrame(leg_rows)
    if cards_scored.empty:
        return cards_scored, legs_scored

    cards_scored = cards_scored.sort_values(["status", "edge_pts", "ev_per_1"], ascending=[True, False, False], na_position="last").reset_index(drop=True)
    return cards_scored, legs_scored


def score_single_markets(
    preds_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    consensus_map: dict[str, float] | None = None,
    prop_consensus_map: dict[tuple[str, str, str], float] | None = None,
    dg_model_probs: dict[tuple[str, str], float] | None = None,
) -> pd.DataFrame:
    """Score prop lines vs model predictions.

    consensus_map:      name_key → no-vig consensus outright prob (multi-book).
    prop_consensus_map: (name_key, market, book) → per-book no-vig prob.
                        Built by build_prop_consensus_probs().  When present,
                        replaces the old mixed-book _market_vig approach.
    dg_model_probs:     (normalized_name, market) → DG model implied_prob.
                        When provided, overrides our model's pool-market probability
                        for players where DG has a reading (better calibrated).
    """
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

    # Fallback vig factors — computed from DK-only lines to avoid contamination
    # when FanDuel lines are also present.  Only used when prop_consensus_map
    # doesn't cover a given player/market/book triple (edge case).
    _EXPECTED_SPOTS = {"outright": 1, "winner": 1, "top5": 5, "top10": 10, "top20": 20, "top30": 30}
    _market_vig: dict[str, float] = {}
    _dk_lines = lines_df[
        lines_df.get("book", pd.Series("DRAFTKINGS", index=lines_df.index))
        .fillna("DRAFTKINGS").astype(str).str.upper().str.startswith("DRAFT")
    ] if "book" in lines_df.columns else lines_df
    for _mkt, _exp in _EXPECTED_SPOTS.items():
        _sub = _dk_lines[_dk_lines["market"].astype(str).str.lower().map(canonical_market) == _mkt]
        if _sub.empty:
            continue
        _total = _sub["odds"].apply(
            lambda o: american_to_prob(parse_american(o)) or 0.0
        ).sum()
        if _total > _exp * 0.5:
            _market_vig[_mkt] = _total / _exp
    if _market_vig and not prop_consensus_map:
        print(f"  Prop vig fallback: { {k: round(v,3) for k,v in _market_vig.items()} }")

    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    # Last-name fallback map.
    last_map: dict[str, list[dict]] = {}
    for _, r in pred.iterrows():
        k = str(r.get("name_key", ""))
        if not k:
            continue
        toks = k.split()
        if toks:
            last_map.setdefault(toks[-1], []).append(r.to_dict())

    def resolve_player(name: Any) -> dict | None:
        k = normalize_name_key(name)
        if not k:
            return None
        if k in by_key:
            return by_key[k]
        toks = k.split()
        if len(toks) == 1:
            cands = last_map.get(toks[0], [])
            if len(cands) == 1:
                return cands[0]
        return None

    rows: list[dict[str, Any]] = []
    for _, line in lines_df.iterrows():
        mkt = canonical_market(line.get("market", ""))
        if mkt not in {"outright", "top5", "top10", "top20", "top30", "make_cut", "miss_cut", "r2_leader"}:
            continue

        player_name = str(line.get("player_name", "") or "").strip()
        if not player_name:
            continue

        pred_row = resolve_player(player_name)

        # Use DG model probability when available — better calibrated for pool markets.
        # Allow scoring even when pred_row is None (player not in our predictions file)
        # as long as DG covers them — DG model IS the probability estimate.
        _dg_key = (normalize_name_key(player_name), mkt)
        _using_dg_prob = False
        if dg_model_probs and _dg_key in dg_model_probs:
            model_prob = dg_model_probs[_dg_key]
            calibrated = True
            _using_dg_prob = True
            if pred_row is None:
                pred_row = {}   # DG model covers this player — no predictions row needed
        else:
            if pred_row is None:
                continue
            model_prob, calibrated = market_prob_from_prediction(pred_row, mkt)
        if pd.isna(model_prob):
            continue

        odds = parse_american(line.get("odds"))
        if odds is None:
            continue

        dec = american_to_decimal(odds)
        if pd.isna(dec) or dec <= 0:
            continue

        player_key = normalize_name_key(player_name)
        book_str   = str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS").upper()
        is_outright = mkt in {"outright", "winner"}

        # ── book_prob: break-even probability at actual decimal odds ─────────
        # When DG model probs are used, they are already dead-heat-adjusted and
        # vig-free (DG top20 probs sum to exactly 20, top10 to 10, etc.).
        # EV = DG_prob × decimal - 1 is the correct formula per DG's methodology.
        # book_prob = 1/decimal is the break-even probability — edge and EV are
        # then consistent: edge > 0 ↔ EV > 0.
        #
        # For our own model probs (less calibrated), continue using no-vig
        # normalisation (no_vig_book_prob < raw_implied) as before.
        if _using_dg_prob:
            book_prob = 1.0 / dec
        elif is_outright and consensus_map and player_key in consensus_map:
            book_prob = consensus_map[player_key]
        else:
            implied = pd.to_numeric(line.get("implied_prob"), errors="coerce")
            raw_book_prob = float(implied) if pd.notna(implied) and 0 < float(implied) < 1 else american_to_prob(odds)
            if pd.isna(raw_book_prob):
                continue
            if prop_consensus_map and (player_key, mkt, book_str) in prop_consensus_map:
                book_prob = prop_consensus_map[(player_key, mkt, book_str)]
            elif mkt in _market_vig:
                book_prob = raw_book_prob / _market_vig[mkt]
            else:
                book_prob = raw_book_prob

        # ── Bayesian blend (own model only) ──────────────────────────────────
        # Skip for DG probs: DG already incorporates market info, blending is circular.
        raw_model_prob = float(np.clip(model_prob, 0.0, 1.0))
        if not _using_dg_prob:
            _BLEND_ALPHA = 0.75
            if is_outright and consensus_map and player_key in consensus_map:
                model_prob = _BLEND_ALPHA * model_prob + (1 - _BLEND_ALPHA) * consensus_map[player_key]
            elif prop_consensus_map and (player_key, mkt, book_str) in prop_consensus_map:
                model_prob = _BLEND_ALPHA * model_prob + (1 - _BLEND_ALPHA) * prop_consensus_map[(player_key, mkt, book_str)]

        edge_pts = (model_prob - book_prob) * 100.0
        ev_per_1 = (model_prob * dec) - 1.0
        conf = confidence_for_single(pred_row, mkt, calibrated, odds,
                                    model_prob=model_prob, book_prob=book_prob)

        rows.append(
            {
                "bet_type": "single",
                "market": mkt,
                "player_name": player_name,
                "selection_label": selection_label_for_market(mkt, player_name),
                "book": str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS"),
                "odds_american": odds,
                "book_prob": float(book_prob),
                "model_prob": float(np.clip(model_prob, 0.0, 1.0)),
                "raw_model_prob": raw_model_prob,
                "edge_pts": float(edge_pts),
                "ev_per_1": float(ev_per_1),
                "confidence": float(conf),
                "selection_count": 1,
                "priced_legs": 1,
                "unpriced_legs": 0,
                "status": "priced",
                "selection_labels_json": json.dumps([selection_label_for_market(mkt, player_name)]),
                "card_id": "",
                "title": "",
            }
        )

    return pd.DataFrame(rows)


# Strokes-per-mph wind advantage factor.
# Literature: ~0.10-0.15 strokes per mph for tour players.
# We use 0.12 as a conservative prior; tune once we have calibrated live data.
# Draw advantage is field_avg_wind - player_window_avg_wind (positive = calmer = better).
_WIND_STROKE_FACTOR = 0.12
_MAX_WIND_STROKE_ADJ = 2.0   # cap so a single storm day can't dominate


def _load_draw_advantage(tid: str, round_num: int) -> dict[str, float]:
    """Load pre-computed draw advantage (wind) per player for a given round.

    Returns dict: normalized_name → draw_advantage (positive = calmer than field avg).
    Empty dict if file not found.
    """
    path = DATA_DIR / "live" / f"draw_advantage_{tid.upper()}_r{round_num}.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        out: dict[str, float] = {}
        for _, row in df.iterrows():
            key = normalize_name_key(row.get("player_name", ""))
            val = pd.to_numeric(row.get("draw_advantage"), errors="coerce")
            if key and pd.notna(val):
                out[key] = float(val)
        return out
    except Exception:
        return {}


def _load_round_matchup_model():
    """Load the dedicated per-round XGBoost h2h model.

    Returns (model, feature_cols) or (None, None) if not available.
    The model predicts P(player_A scores lower than player_B in round R).
    """
    import pickle
    model_path = DATA_DIR / "models" / "round_matchup_model.pkl"
    if not model_path.exists():
        return None, None
    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        feature_cols = [
            "round_num", "score_diff_before",
            "sg_total_diff", "sg_ott_diff", "sg_app_diff", "sg_putt_diff",
        ]
        return model, feature_cols
    except Exception:
        return None, None


def _load_dg_matchups(tid: str) -> dict:
    """Load DataGolf 72-hole matchup model probabilities.

    Returns dict keyed by frozenset of two normalized name keys:
        {frozenset({nkey_a, nkey_b}): (dg_prob_a, dg_prob_b)}

    DG model probs are stored as American odds in datagolf_p1/p2 columns.
    Returns empty dict if file not found.
    """
    path = DATA_DIR / "datagolf" / f"dg_matchups_72h_{tid}.csv"
    
    if not path.exists():
        return {}
    
    try:
        df = pd.read_csv(path)
        
        if 'ties' in df.columns:
            df = df[df['ties'] == 'void']  # Filter out matchups with ties if 'ties' column exists
        
        lookup: dict = {}
        
        for _, row in df.iterrows():
            na = str(row.get("name_p1", "") or "").strip()
            nb = str(row.get("name_p2", "") or "").strip()
            if not na or not nb:
                continue
            p1 = parse_american(row.get("datagolf_p1"))
            p2 = parse_american(row.get("datagolf_p2"))
            if p1 is None or p2 is None:
                continue
            prob1 = american_to_prob(p1)
            prob2 = american_to_prob(p2)
            if pd.isna(prob1) or pd.isna(prob2):
                continue
            # Normalize: DG odds include vig, so re-normalize to sum to 1
            total = prob1 + prob2
            if total <= 0:
                continue
            prob1, prob2 = prob1 / total, prob2 / total
            key_a = normalize_name_key(na)
            key_b = normalize_name_key(nb)
            lookup[frozenset({key_a, key_b})] = (key_a, prob1, key_b, prob2)
        return lookup
    except Exception:
        return {}
        
        



def _load_dg_matchup_model(tid: str) -> dict:
    """Load DataGolf round matchup model probabilities from dg_matchups_{tid}.csv.

    Returns dict keyed by frozenset of two normalized name keys:
        {frozenset({nkey_p1, nkey_p2}): (nkey_p1, novig_p1, nkey_p2, novig_p2)}

    Uses no-vig probabilities already computed by fetch_dg_odds.py.
    Returns empty dict if file not found or DG fetch hasn't been run.
    """
    path = DATA_DIR / "datagolf" / f"dg_matchups_{tid}.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        dg_rows = df[df["is_dg_model"].astype(str).str.lower() == "true"]
        lookup: dict = {}
        for _, row in dg_rows.iterrows():
            na = str(row.get("p1_name", "") or "").strip()
            nb = str(row.get("p2_name", "") or "").strip()
            if not na or not nb:
                continue
            nv1 = pd.to_numeric(row.get("p1_novig"), errors="coerce")
            nv2 = pd.to_numeric(row.get("p2_novig"), errors="coerce")
            if pd.isna(nv1) or pd.isna(nv2):
                continue
            ka = normalize_name_key(na)
            kb = normalize_name_key(nb)
            lookup[frozenset({ka, kb})] = (ka, float(nv1), kb, float(nv2))
        return lookup
    except Exception:
        return {}


def _dg_outright_model_lookup(tid: str) -> dict[tuple[str, str], float]:
    """Extract DG model probabilities from dg_outrights_{tid}.csv.

    Returns {(normalized_player_name, canonical_market): dg_model_prob} for use
    in score_single_markets to override our own model's pool-market probability
    estimates (which are less calibrated than DG's model).

    Returns empty dict if the file was updated after the tournament started —
    that means it contains live in-round probabilities (e.g. 98% top10 for a
    leader in R4), which are useless and misleading for pre-tournament bets.
    """
    _MKT_MAP = {"win": "outright", "top_5": "top5", "top_10": "top10",
                "top_20": "top20", "make_cut": "make_cut"}
    path = DATA_DIR / "datagolf" / f"dg_outrights_{tid}.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)

        # Stale-data guard: if the file has any last_updated AFTER the
        # tournament's start date, it was refreshed during live play.
        # Fall back to own model so live probabilities don't corrupt edges.
        if "last_updated" in df.columns:
            try:
                from datetime import timezone
                sched = pd.read_csv(DATA_DIR / "raw" / "schedule_2026.csv")
                row = sched[sched["tournament_id"].astype(str) == tid]
                if not row.empty:
                    start_date = pd.to_datetime(row.iloc[0]["start_date"]).tz_localize("UTC")
                    max_updated = pd.to_datetime(df["last_updated"], utc=True).max()
                    if pd.notna(max_updated) and max_updated >= start_date:
                        print(f"  DG outrights for {tid} are live data "
                              f"(updated {max_updated.date()} >= start {start_date.date()}) "
                              f"— skipping, using own model probs")
                        return {}
            except Exception:
                pass

        dg = df[df["is_dg_model"].astype(str).str.lower() == "true"].copy()
        lookup: dict[tuple[str, str], float] = {}
        for _, row in dg.iterrows():
            name = str(row.get("player_name", "") or "").strip()
            mkt_raw = str(row.get("market", "") or "")
            mkt = _MKT_MAP.get(mkt_raw, mkt_raw)
            prob = pd.to_numeric(row.get("implied_prob"), errors="coerce")
            if name and mkt and pd.notna(prob):
                lookup[(normalize_name_key(name), mkt)] = float(prob)
        return lookup
    except Exception:
        return {}


def _dg_matchups_to_prop_lines(tid: str, round_num: int = 1) -> pd.DataFrame:
    """Convert dg_matchups_{tid}.csv (non-DG-model rows) into h2h prop_lines format.

    Includes all available books (sharp: Pinnacle/Betcris/Bet365 + US books).
    round_num is passed in from get_tournament_phase() so matchups score as
    h2h_r1/r2/r3/r4 matching the actual current round.
    """
    _ALL_BOOKS = {
        "fanduel", "draftkings", "betmgm", "caesars", "pointsbet",
        "pinnacle", "betcris", "bet365", "unibet", "bovada", "betonline",
    }
    path = DATA_DIR / "datagolf" / f"dg_matchups_{tid}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        book_rows = df[
            (df["is_dg_model"].astype(str).str.lower() == "false") &
            (df["book"].str.lower().isin(_ALL_BOOKS))
        ]
        if book_rows.empty:
            return pd.DataFrame()
        rows = []
        for _, r in book_rows.iterrows():
            o1 = str(r.get("p1_odds", "") or "").strip()
            o2 = str(r.get("p2_odds", "") or "").strip()
            if not o1 or not o2 or o1 == "nan" or o2 == "nan":
                continue
            gid = f"dg_{normalize_name_key(str(r['p1_name']))}_{normalize_name_key(str(r['p2_name']))}"
            rows.append({
                "player_a":    str(r.get("p1_name", "")),
                "player_b":    str(r.get("p2_name", "")),
                "odds_a":      o1,
                "odds_b":      o2,
                "market":      "h2h",
                "book":        str(r.get("book", "")).upper(),
                "round_num":   round_num,
                "bet_group_id": gid,
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _dg_outrights_to_prop_lines(tid: str) -> pd.DataFrame:
    """Convert dg_outrights_{tid}.csv into prop_lines format for score_single_markets.

    Market mapping: win→outright, top_5→top5, top_10→top10, top_20→top20
    Excludes DG model rows (model_prob comes via _dg_outright_model_lookup instead).
    Includes ALL books — sharp books (Pinnacle, Betcris) are used for best-price
    discovery; bettable US books get separate filtering in scoring.
    """
    _ALL_BOOKS = {
        "fanduel", "draftkings", "betmgm", "caesars", "pointsbet",
        "pinnacle", "betcris", "bet365", "unibet", "bovada", "betonline",
    }
    _MKT_MAP = {"win": "outright", "top_5": "top5", "top_10": "top10",
                "top_20": "top20", "make_cut": "make_cut"}
    path = DATA_DIR / "datagolf" / f"dg_outrights_{tid}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        df = df[
            (df["is_dg_model"].astype(str).str.lower() == "false") &
            (df["book"].str.lower().isin(_ALL_BOOKS))
        ]
        if df.empty:
            return pd.DataFrame()
        df = df.copy()
        df["market"] = df["market"].map(_MKT_MAP).fillna(df["market"])
        df = df.rename(columns={"odds_american": "odds"})
        df["book"] = df["book"].str.upper()
        # Normalize "Last, First" → "First Last"
        def _to_first_last(name):
            s = str(name).strip()
            if "," in s:
                parts = s.split(",", 1)
                return f"{parts[1].strip()} {parts[0].strip()}"
            return s
        df["player_name"] = df["player_name"].apply(_to_first_last)
        df["_source_priority"] = 0  # DG outrights are primary — fresher than DK prop_lines scraper
        return df[["player_name", "market", "book", "odds", "implied_prob", "_source_priority"]].copy()
    except Exception:
        return pd.DataFrame()


def _build_live_score_lookup(tid: str) -> dict[str, dict]:
    """Load live leaderboard for a tournament and return per-player round scores.

    Returns dict keyed by normalised name → {r1, r2, r3, r4, cum_r1, cum_r2, cum_r3}
    Returns empty dict if leaderboard not found.
    """
    lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    if not lb_path.exists():
        return {}
    try:
        lb = pd.read_csv(lb_path, dtype={"player_id": str})
        lookup: dict[str, dict] = {}
        for _, row in lb.iterrows():
            key = normalize_name_key(row.get("player_name", ""))
            if not key:
                continue
            r1 = pd.to_numeric(row.get("R1"), errors="coerce")
            r2 = pd.to_numeric(row.get("R2"), errors="coerce")
            r3 = pd.to_numeric(row.get("R3"), errors="coerce")
            r4 = pd.to_numeric(row.get("R4"), errors="coerce")
            lookup[key] = {
                "r1": r1, "r2": r2, "r3": r3, "r4": r4,
                "cum_r1": r1 if pd.notna(r1) else np.nan,
                "cum_r2": (r1 + r2) if (pd.notna(r1) and pd.notna(r2)) else np.nan,
                "cum_r3": (r1 + r2 + r3) if (pd.notna(r1) and pd.notna(r2) and pd.notna(r3)) else np.nan,
            }
        return lookup
    except Exception:
        return {}


def _get_score_diff_before(name_a: str, name_b: str, round_num: int,
                           live_lookup: dict) -> float:
    """Return (cum_a - cum_b) entering round_num, or 0.0 if unavailable.

    Negative = player A is AHEAD (lower cumulative = better in golf).
    """
    if round_num == 1 or not live_lookup:
        return 0.0
    cum_key = f"cum_r{round_num - 1}"
    key_a = normalize_name_key(name_a)
    key_b = normalize_name_key(name_b)
    row_a = live_lookup.get(key_a, {})
    row_b = live_lookup.get(key_b, {})
    cum_a = row_a.get(cum_key)
    cum_b = row_b.get(cum_key)
    if pd.isna(cum_a) or pd.isna(cum_b):
        return 0.0
    # Model was trained with positive = A ahead (B has more strokes = worse score)
    return float(cum_b) - float(cum_a)


def score_h2h_markets(
    preds_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    tid: str = "",
) -> pd.DataFrame:
    """Score head-to-head matchup lines using model win probabilities.

    For round-specific markets (h2h_r1/r2/r3/r4), uses a dedicated XGBoost
    round matchup model trained on 10 years of per-round pairwise outcomes.
    Primary features: sg_total_diff (skill) + score_diff_before (position).

    For tournament-long h2h (market 'h2h'), falls back to win_prob ratio.
    """
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

    h2h_lines = lines_df[lines_df["market"].astype(str).str.lower() == "h2h"].copy()
    if h2h_lines.empty:
        return pd.DataFrame()

    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    # Load round matchup model (trained on 10yrs per-round pairwise outcomes)
    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    # Load round matchup model (trained on 10yrs per-round pairwise outcomes)
    _rm_model, _rm_features = _load_round_matchup_model()

    # Load DataGolf 72-hour matchup model probabilities (tournament-length h2h)
    _dg_matchups = _load_dg_matchups(tid) if tid else {}
    # Load DataGolf round matchup model probabilities (replaces XGBoost for R1/R2/R3/R4)
    _dg_model_round = _load_dg_matchup_model(tid) if tid else {}
    if _dg_model_round:
        print(f"  DG round matchup model loaded: {len(_dg_model_round)} matchups")

    # Load live leaderboard scores for score_diff_before computation
    _live_lookup = _build_live_score_lookup(tid) if tid else {}

    # Pre-load draw advantage maps per round (populated if tee_times + weather fetched)
    _draw_adv_cache: dict[int, dict[str, float]] = {}

    def get_player_row(name: Any) -> dict | None:
        k = normalize_name_key(name)
        row = by_key.get(k)
        if row is None:
            toks = k.split()
            if toks:
                cands = [v for kk, v in by_key.items() if kk.split() and kk.split()[-1] == toks[-1]]
                if len(cands) == 1:
                    row = cands[0]
        return row

    def get_win_prob(name: Any) -> float | None:
        row = get_player_row(name)
        if row is None:
            return None
        for col in ["win_prob_calibrated", "win_prob", "win_prob_raw"]:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and v > 0:
                return float(v)
        return None

    def get_sg_stat(row: dict | None, col: str) -> float:
        """Get SG stat value, preferring season_ prefix."""
        if row is None:
            return 0.0
        for try_col in [f"season_{col}", col]:
            v = pd.to_numeric(row.get(try_col), errors="coerce")
            if pd.notna(v):
                return float(v)
        return 0.0

    def score_round_matchup(
        name_a: str, name_b: str, round_num: int
    ) -> tuple[float, float, float, float]:
        """Return (model_prob_a, model_prob_b, draw_adv_a, draw_adv_b).

        Uses dedicated round matchup model + wind draw advantage adjustment.
        Falls back to win_prob shrinkage if model unavailable.

        Draw advantage adjustment:
            Each 1 mph of wind advantage ≈ 0.12 strokes (conservative prior).
            Added to score_diff_before so the model sees it as effective position.
            Capped at ±2 strokes to prevent extreme-weather domination.
        """
        if _rm_model is None:
            pa, pb = _win_prob_fallback(name_a, name_b)
            return pa, pb, 0.0, 0.0

        row_a = get_player_row(name_a)
        row_b = get_player_row(name_b)

        sg_total_diff = get_sg_stat(row_a, "sg_total") - get_sg_stat(row_b, "sg_total")
        sg_ott_diff   = get_sg_stat(row_a, "sg_ott")   - get_sg_stat(row_b, "sg_ott")
        sg_app_diff   = get_sg_stat(row_a, "sg_app")   - get_sg_stat(row_b, "sg_app")
        sg_putt_diff  = get_sg_stat(row_a, "sg_putt")  - get_sg_stat(row_b, "sg_putt")
        score_diff    = _get_score_diff_before(name_a, name_b, round_num, _live_lookup)

        # ── Tee time / wind draw advantage ───────────────────────────────────
        # Load draw advantage for this round (cached per round_num)
        if round_num not in _draw_adv_cache:
            _draw_adv_cache[round_num] = _load_draw_advantage(tid, round_num) if tid else {}
        da_map = _draw_adv_cache[round_num]

        key_a = normalize_name_key(name_a)
        key_b = normalize_name_key(name_b)
        da_a = da_map.get(key_a, 0.0)
        da_b = da_map.get(key_b, 0.0)

        # Wind advantage → effective stroke advantage for this round
        # Negative score_diff = A is AHEAD (lower = better in golf).
        # A having calmer conditions (da_a > da_b) means A is expected to score
        # fewer strokes, so we subtract from A's effective score (improving position).
        wind_stroke_adj = np.clip(
            (da_a - da_b) * _WIND_STROKE_FACTOR,
            -_MAX_WIND_STROKE_ADJ,
            _MAX_WIND_STROKE_ADJ,
        )
        adjusted_score_diff = score_diff - wind_stroke_adj  # subtract = A effectively more ahead

        X = pd.DataFrame([{
            "round_num": round_num,
            "score_diff_before": adjusted_score_diff,
            "sg_total_diff": sg_total_diff,
            "sg_ott_diff": sg_ott_diff,
            "sg_app_diff": sg_app_diff,
            "sg_putt_diff": sg_putt_diff,
        }])
        try:
            prob_a = float(_rm_model.predict_proba(X)[0, 1])
        except Exception:
            pa, pb = _win_prob_fallback(name_a, name_b)
            return pa, pb, da_a, da_b
        prob_b = 1.0 - prob_a
        return prob_a, prob_b, da_a, da_b

    def _win_prob_fallback(name_a: str, name_b: str) -> tuple[float, float]:
        """Shrinkage-based fallback using 72-hour win probability."""
        wp_a = get_win_prob(name_a)
        wp_b = get_win_prob(name_b)
        if wp_a is None or wp_b is None or (wp_a + wp_b) <= 0:
            return 0.5, 0.5
        _k = 0.70
        denom = wp_a + wp_b
        return _k * (wp_a / denom) + 0.15, _k * (wp_b / denom) + 0.15

    # ── Known-book filter ─────────────────────────────────────────────────────
    # Include DG-sourced matchup books (BET365, Bovada, BetOnline, Unibet,
    # BetCris) alongside standard US books — DG doesn't provide DK/FD matchup
    # odds directly. BetCris is a sharp Latin American book with low vig,
    # included here because it's the source of DG's H2H matchup feed.
    _KNOWN_BOOKS = {
        "DRAFTKINGS", "FANDUEL", "BETMGM", "CAESARS", "POINTSBET",
        "BET365", "BOVADA", "BETONLINE", "UNIBET", "PINNACLE", "BETCRIS",
    }
    if "book" in h2h_lines.columns:
        h2h_lines = h2h_lines[
            h2h_lines["book"].astype(str).str.upper().isin(_KNOWN_BOOKS)
        ]
    if h2h_lines.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, line in h2h_lines.iterrows():
        pa = str(line.get("player_a", "") or "").strip()
        pb = str(line.get("player_b", "") or "").strip()
        odds_a = parse_american(line.get("odds_a"))
        odds_b = parse_american(line.get("odds_b"))
        if not pa or not pb or odds_a is None or odds_b is None:
            continue

        round_num = line.get("round_num")
        is_round_specific = pd.notna(round_num)

        if is_round_specific:
            _dg_rkey = frozenset({normalize_name_key(pa), normalize_name_key(pb)})
            _dg_rhit = _dg_model_round.get(_dg_rkey)
            if _dg_rhit is not None:
                # DataGolf model preferred — better calibrated than our XGBoost
                _rka, _rpa, _rkb, _rpb = _dg_rhit
                if normalize_name_key(pa) == _rka:
                    model_a, model_b = _rpa, _rpb
                else:
                    model_a, model_b = _rpb, _rpa
                da_a, da_b = 0.0, 0.0
            else:
                # Fallback: our XGBoost round matchup model
                model_a, model_b, da_a, da_b = score_round_matchup(pa, pb, int(round_num))
        else:
            # Tournament-long h2h: use win_prob ratio with shrinkage
            da_a, da_b = 0.0, 0.0
            # Tournament-long h2h: prefer DataGolf model prob, fall back to win_prob ratio
            _dg_key = frozenset({normalize_name_key(pa), normalize_name_key(pb)})
            _dg_hit = _dg_matchups.get(_dg_key)
            if _dg_hit is not None:
                # DG model: already normalized to sum to 1 (no-vig)
                _ka, _pa_dg, _kb, _pb_dg = _dg_hit
                if normalize_name_key(pa) == _ka:
                    model_a, model_b = _pa_dg, _pb_dg
                else:
                    model_a, model_b = _pb_dg, _pa_dg
            else:
                # Fallback: win_prob ratio with shrinkage
                wp_a = get_win_prob(pa)
                wp_b = get_win_prob(pb)
                if wp_a is None or wp_b is None or (wp_a + wp_b) <= 0:
                    continue
                _k = 0.85
                denom = wp_a + wp_b
                model_a = _k * (wp_a / denom) + (1 - _k) * 0.5
                model_b = _k * (wp_b / denom) + (1 - _k) * 0.5
                
                
        
        
        
        
            

        dec_a = american_to_decimal(odds_a)
        dec_b = american_to_decimal(odds_b)
        if pd.isna(dec_a) or pd.isna(dec_b) or dec_a <= 0 or dec_b <= 0:
            continue
        # DG model probs are no-vig. Remove vig from book side so the comparison
        # is apples-to-apples. Raw 1/decimal inflates book_prob by ~2-2.5pp per
        # side on typical H2H markets, which systematically kills edge detection.
        _raw_a = 1.0 / dec_a
        _raw_b = 1.0 / dec_b
        _total_implied = _raw_a + _raw_b
        book_a = _raw_a / _total_implied
        book_b = _raw_b / _total_implied
        book_str = str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS")
        round_num = line.get("round_num")
        mkt_label = f"h2h_r{int(round_num)}" if pd.notna(round_num) else "h2h"

        group_members = f"{pa} ({odds_a:+d}) | {pb} ({odds_b:+d})"

        for player, model_p, book_p, odds, dec, this_da, opp_da in [
            (pa, model_a, book_a, odds_a, dec_a, da_a, da_b),
            (pb, model_b, book_b, odds_b, dec_b, da_b, da_a),
        ]:
            edge_pts = (model_p - book_p) * 100.0
            ev_per_1 = (model_p * dec) - 1.0
            opponent = pb if player == pa else pa
            label = f"{player} to beat {opponent}"
            if pd.notna(round_num):
                label += f" (R{int(round_num)})"

            # Build reasoning bullets
            reason_parts: list[str] = []
            row_self = get_player_row(player)
            row_opp  = get_player_row(opponent)
            sg_self  = get_sg_stat(row_self, "sg_total")
            sg_opp   = get_sg_stat(row_opp,  "sg_total")
            sg_diff  = sg_self - sg_opp
            if abs(sg_diff) > 0.05:
                direction = "better" if sg_diff > 0 else "worse"
                reason_parts.append(f"SG total {abs(sg_diff):.2f} {direction} than {opponent.split(',')[0].strip()}")
            if is_round_specific and this_da != 0.0:
                da_diff = this_da - opp_da
                if abs(da_diff) >= 1.0:
                    wind_dir = "calmer" if da_diff > 0 else "windier"
                    stroke_val = abs(da_diff) * _WIND_STROKE_FACTOR
                    reason_parts.append(
                        f"Draw: {abs(da_diff):.1f} mph {wind_dir} conditions (~{stroke_val:.1f} stroke adv)"
                    )
            if abs(edge_pts) > 5:
                reason_parts.append(f"Model edge: {edge_pts:+.1f}pp vs book")


            rows.append({
                "bet_type": "single",
                "market": mkt_label,
                "player_name": player,
                "selection_label": label,
                "group_members": group_members,
                "book": book_str,
                "odds_american": odds,
                "book_prob": float(book_p),
                "model_prob": float(np.clip(model_p, 0.0, 1.0)),
                "edge_pts": float(edge_pts),
                "ev_per_1": float(ev_per_1),
                "confidence": 0.70 if abs(edge_pts) > 3 else 0.60,
                "selection_count": 1,
                "priced_legs": 1,
                "unpriced_legs": 0,
                "status": "priced",
                "selection_labels_json": json.dumps([label]),
                "card_id": "",
                "title": "",
                "reasoning": " | ".join(reason_parts),
                "draw_advantage": round(this_da, 2),
            })

    return pd.DataFrame(rows)


def score_group_winner_markets(preds_df: pd.DataFrame, lines_df: pd.DataFrame) -> pd.DataFrame:
    """Score 3-way group winner markets using model win probabilities.

    Edge = model_prob_A_in_group - book_implied_prob_A
    where model_prob = win_prob_A / (win_prob_A + win_prob_B + win_prob_C)
    """
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

    grp_lines = lines_df[
        lines_df["market"].astype(str).str.lower().isin(["group_winner", "group", "3_way", "3way"])
    ].copy()
    if grp_lines.empty:
        return pd.DataFrame()

    # Known-book filter — same rationale as h2h
    _KNOWN_BOOKS = {"DRAFTKINGS", "FANDUEL", "BETMGM", "CAESARS", "POINTSBET"}
    if "book" in grp_lines.columns:
        grp_lines = grp_lines[
            grp_lines["book"].astype(str).str.upper().isin(_KNOWN_BOOKS)
        ]
    if grp_lines.empty:
        return pd.DataFrame()

    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    def get_win_prob(name: Any) -> float:
        k = normalize_name_key(name)
        row = by_key.get(k)
        if row is None:
            toks = k.split()
            if toks:
                cands = [v for kk, v in by_key.items() if kk.split() and kk.split()[-1] == toks[-1]]
                if len(cands) == 1:
                    row = cands[0]
        if row is None:
            return 0.01  # floor for unknown players
        for col in ["win_prob_calibrated", "win_prob", "win_prob_raw"]:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and v > 0:
                return float(v)
        return 0.01

    # Group lines by event_name + round_num to identify 3-player groups
    group_cols = [c for c in ["event_name", "round_num", "market_name"] if c in grp_lines.columns]
    rows: list[dict] = []

    for grp_key, grp in grp_lines.groupby(group_cols, dropna=False) if group_cols else [("all", grp_lines)]:
        players = []
        for _, line in grp.iterrows():
            pa = str(line.get("player_a", "") or line.get("player_name", "") or "").strip()
            if pa:
                players.append((pa, parse_american(line.get("odds_a") or line.get("odds")), line))

        if len(players) < 2:
            continue

        wps = {p: get_win_prob(p) for p, _, _ in players}
        total_wp = sum(wps.values())
        if total_wp <= 0:
            continue

        # Infer a readable group type from the first line's metadata
        sample_line = players[0][2]
        group_title   = str(sample_line.get("group_title", "")).strip()
        market_subtype = str(sample_line.get("market_subtype", "")).strip()
        if market_subtype == "NATIONALITY":
            group_type = group_title          # e.g. "Top African Player"
        elif market_subtype == "THREE_BALL":
            round_tag = f" R{int(sample_line['round_num'])}" if pd.notna(sample_line.get("round_num")) else ""
            group_type = f"3-Ball{round_tag}"
        else:
            group_type = "Group"

        # Build group_members string sorted by odds (favourite first)
        # For nationality groups, include each player's country in parentheses
        _country_by_player = {p: str(ln.get("player_country", "") or "") for p, _, ln in players}
        sorted_players = sorted(
            [(p, o) for p, o, _ in players if o is not None],
            key=lambda x: x[1]
        )
        if market_subtype == "NATIONALITY":
            group_members = " | ".join(
                f"{p} ({_country_by_player.get(p, '')}, {o:+d})" if _country_by_player.get(p) else f"{p} ({o:+d})"
                for p, o in sorted_players
            )
        else:
            group_members = " | ".join(
                f"{p} ({o:+d})" for p, o in sorted_players
            )

        # ── Variance shrinkage toward equal-share prior ───────────────────────
        # For a 3-ball, the naive prior is 1/n (each player equally likely).
        # Shrinking toward that prior accounts for round-by-round variance that
        # win_prob alone doesn't capture. k=0.80 for 3-balls (2 rounds max),
        # slightly less than full-tournament h2h since groups span fewer holes.
        n_players = len(players)
        prior = 1.0 / n_players if n_players > 0 else 1.0
        _k_grp = 0.80

        for player, odds, line in players:
            if odds is None:
                continue
            raw_p  = wps[player] / total_wp
            model_p = _k_grp * raw_p + (1 - _k_grp) * prior
            book_p = american_to_prob(odds)
            if pd.isna(book_p):
                continue
            dec = american_to_decimal(odds)
            edge_pts = (model_p - book_p) * 100.0
            ev_per_1 = (model_p * dec) - 1.0
            label = f"{player} — {group_type}"
            mkt_val = "nationality_group" if market_subtype == "NATIONALITY" else "group_winner"
            rows.append({
                "bet_type": "single",
                "market": mkt_val,
                "player_name": player,
                "selection_label": label,
                "group_members": group_members,
                "book": str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS"),
                "odds_american": odds,
                "book_prob": float(book_p),
                "model_prob": float(np.clip(model_p, 0.0, 1.0)),
                "edge_pts": float(edge_pts),
                "ev_per_1": float(ev_per_1),
                "confidence": 0.65,
                "selection_count": 1,
                "priced_legs": 1,
                "unpriced_legs": 0,
                "status": "priced",
                "selection_labels_json": json.dumps([label]),
                "card_id": "",
                "title": "",
            })

    return pd.DataFrame(rows)


def score_wire_to_wire_market(
    preds_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    tid: str = "",
) -> pd.DataFrame:
    """Score Wire-to-Wire Winner prop from TOURNAMENT_PROPS.

    Wire-to-wire probability modelled as:
        P(W2W) ≈ P(R1 lead) × P(hold lead through R4)
    We approximate using:
        P(R1 lead) from r2_leader model prob (proxy — first-round leader)
        P(hold)    = win_prob_calibrated (probability of winning outright)
    Combined: sqrt(r1_leader_prob × win_prob) as geometric mean proxy.
    This is conservative and shrunk further toward book implied.
    """
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

    w2w_lines = lines_df[
        lines_df["market"].astype(str).str.lower() == "wire_to_wire"
    ].copy()
    if w2w_lines.empty:
        return pd.DataFrame()

    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    def get_player_row(name: Any) -> dict | None:
        k = normalize_name_key(name)
        if k in by_key:
            return by_key[k]
        toks = k.split()
        if toks:
            cands = [v for kk, v in by_key.items() if kk.split() and kk.split()[-1] == toks[-1]]
            if len(cands) == 1:
                return cands[0]
        return None

    # No-vig market prob for wire-to-wire (binary-style among field)
    raw_probs = [american_to_prob(parse_american(r.get("odds"))) for _, r in w2w_lines.iterrows()]
    raw_probs = [p for p in raw_probs if pd.notna(p) and p > 0]
    total_raw = sum(raw_probs) if raw_probs else 1.0

    rows: list[dict] = []
    for _, line in w2w_lines.iterrows():
        player_name = str(line.get("player_name", "") or "").strip()
        if not player_name:
            continue
        odds = parse_american(line.get("odds"))
        if odds is None:
            continue
        pr = get_player_row(player_name)
        if pr is None:
            continue

        raw_book_prob = american_to_prob(odds)
        if pd.isna(raw_book_prob) or raw_book_prob <= 0:
            continue
        book_prob = float(raw_book_prob) / max(total_raw, 1.0)  # no-vig normalised

        # Model proxy: geometric mean of win_prob and r1_leader proxy
        win_p = pd.to_numeric(pr.get("win_prob_calibrated") or pr.get("win_prob"), errors="coerce")
        r1_p  = pd.to_numeric(pr.get("r1_leader_prob"), errors="coerce")
        if pd.isna(win_p) or win_p <= 0:
            continue
        if pd.isna(r1_p) or r1_p <= 0:
            # Fall back: r1_leader ~ win_prob scaled by 0.6 (correlation heuristic)
            r1_p = float(win_p) * 0.60

        # Geometric mean, then shrink 40% toward book (high uncertainty market)
        geo = float(np.sqrt(win_p * r1_p))
        model_prob = 0.60 * geo + 0.40 * book_prob   # strong market shrinkage

        dec = american_to_decimal(odds)
        if pd.isna(dec):
            continue
        edge_pts = (model_prob - book_prob) * 100.0
        ev_per_1 = (model_prob * dec) - 1.0
        player_key = normalize_name_key(player_name)
        book_str = str(line.get("book", "FANDUEL") or "FANDUEL").upper()

        rows.append({
            "bet_type":        "single",
            "market":          "wire_to_wire",
            "player_name":     player_name,
            "selection_label": f"{player_name} — Wire to Wire Winner",
            "book":            book_str,
            "odds_american":   odds,
            "book_prob":       float(book_prob),
            "model_prob":      float(np.clip(model_prob, 0.0, 1.0)),
            "raw_model_prob":  float(np.clip(geo, 0.0, 1.0)),
            "edge_pts":        float(edge_pts),
            "ev_per_1":        float(ev_per_1),
            "confidence":      0.55,   # lower confidence — derived market
            "selection_count": 1,
            "priced_legs":     1,
            "unpriced_legs":   0,
            "status":          "priced",
            "selection_labels_json": json.dumps([f"{player_name} — Wire to Wire Winner"]),
            "card_id":         "",
            "title":           "",
        })

    return pd.DataFrame(rows)


# ── Tournament phase constants ────────────────────────────────────────────────
# Which markets are still live (bettable) during each tournament phase.
# Once a round is official, round-specific markets for that round are stale.
_PHASE_VALID_MARKETS: dict[str, set[str]] = {
    "pre":         {"outright", "top5", "top10", "top20", "top30", "make_cut", "miss_cut",
                    "h2h", "h2h_r1", "h2h_r2", "h2h_r3", "h2h_r4",
                    "group_winner", "nationality_group", "r2_leader",
                    "wire_to_wire", "content_card"},
    "r1":          {"outright", "top5", "top10", "top20", "top30", "make_cut", "miss_cut",
                    "h2h", "h2h_r1", "h2h_r2", "h2h_r3", "h2h_r4",
                    "group_winner", "nationality_group", "r2_leader",
                    "wire_to_wire", "content_card"},
    "r2":          {"top5", "top10", "top20", "top30", "make_cut", "miss_cut",
                    "h2h", "h2h_r2", "h2h_r3", "h2h_r4",
                    "group_winner", "r2_leader", "content_card"},
    # After cut confirmed: make_cut/miss_cut are settled, h2h_r1/r2 are stale
    "r2_postcut":  {"top5", "top10", "top20", "top30",
                    "h2h", "h2h_r3", "h2h_r4", "group_winner"},
    "r3":          {"top5", "top10", "top20", "top30",
                    "h2h", "h2h_r4", "group_winner"},
    "r4":          {"top5", "top10", "top20", "top30"},
    "post":        set(),  # tournament is over — nothing valid
}

# ── Minimum realistic model probability per market ────────────────────────────
# A positive edge alone doesn't mean the bet is worth taking.  Very low
# model probabilities (e.g. 1.5% win for a WR-200 player) produce noisy
# edge estimates and represent bets with no realistic upside.
_REALISTIC_MIN_MODEL_PROB: dict[str, float] = {
    "outright":    0.025,  # 2.5% win — roughly top-40 player in a 156-man field
    "top5":        0.070,  # 7% top-5 probability
    "top10":       0.110,  # 11% top-10 probability (base rate at Augusta ~11%)
    "top20":       0.190,  # 19% top-20 probability
    "top30":       0.260,  # 26% top-30 probability
    "make_cut":    0.470,  # 47% cut probability — at least a coin-flip or better
    "miss_cut":    0.120,  # 12% miss-cut (don't fade obvious cut-makers)
    "h2h":         0.380,  # 38% win in matchup (after shrinkage toward 50%)
    "h2h_r1":      0.380,
    "h2h_r2":      0.380,
    "h2h_r3":      0.380,
    "h2h_r4":      0.380,
    "group_winner":     0.260,  # 26% in 3-ball; fair share is 1/3 = 33.3%
    "nationality_group":0.100,  # nationality groups vary in size (3–49 players)
    "wire_to_wire":     0.010,  # very low — derived proxy, high uncertainty
    "r2_leader":        0.020,
    "content_card":     0.000,  # content cards: no floor (multi-leg probs are lower)
}


def get_tournament_phase(tid: str) -> str:
    """Detect the current phase of tournament *tid* from live leaderboard metadata.

    Phase strings:
        "pre"         — before the tournament starts (Thursday)
        "r1"          — Round 1 in progress or just completed
        "r2"          — Round 2 in progress, cut not yet determined
        "r2_postcut"  — Round 2 complete / cut has been made
        "r3"          — Round 3 in progress or complete
        "r4"          — Round 4 in progress
        "post"        — Tournament finished

    Falls back to schedule-date heuristic when live metadata is unavailable.
    """
    from datetime import date as _date

    # ── Try live metadata first ───────────────────────────────────────────────
    _tid_lower = tid.lower()
    _meta_path = DATA_DIR / "live" / f"leaderboard_{_tid_lower}_meta.json"
    if _meta_path.exists():
        try:
            with open(_meta_path) as _mf:
                _meta = json.load(_mf)
            _rnd    = int(_meta.get("current_round", 0) or 0)
            _status = str(_meta.get("round_status", "") or "").lower()
            _s_out  = int((_meta.get("cut_projection") or {}).get("safely_out", 0) or 0)

            if _rnd == 0:
                return "pre"
            if _rnd == 1:
                # Check whether Round 1 is actually complete by looking at DG live stats.
                # When the median 'thru' across all players equals 18, the round is
                # done and R2 lines are already posted — step the phase forward.
                _dg_latest = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_latest.csv"
                if _dg_latest.exists():
                    try:
                        _dg = pd.read_csv(_dg_latest)
                        _is_r1 = (
                            pd.to_numeric(_dg.get("round_param", pd.Series()), errors="coerce")
                            .dropna()
                            .eq(1)
                            .all()
                        )
                        _median_thru = (
                            pd.to_numeric(_dg.get("thru", pd.Series()), errors="coerce")
                            .median()
                        )
                        if _is_r1 and _median_thru >= 17:
                            return "r2"
                    except Exception:
                        pass
                return "r1"
            if _rnd == 2:
                # r2_postcut only when R2 is truly complete — check DG live stats
                # median thru (same approach as R1→R2 transition).
                # Do NOT use safely_out from cut_projection — that fires mid-round.
                _dg_latest = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_latest.csv"
                if _dg_latest.exists():
                    try:
                        _dg2 = pd.read_csv(_dg_latest)
                        _is_r2 = (
                            pd.to_numeric(_dg2.get("round_param", pd.Series()), errors="coerce")
                            .dropna().eq(2).all()
                        )
                        _median_thru2 = (
                            pd.to_numeric(_dg2.get("thru", pd.Series()), errors="coerce")
                            .median()
                        )
                        if _is_r2 and _median_thru2 >= 17:
                            return "r2_postcut"
                    except Exception:
                        pass
                if "official" in _status:
                    return "r2_postcut"
                return "r2"
            if _rnd == 3:
                return "r3"
            if _rnd >= 4:
                # Use DG live stats median thru — post only when all 18 holes done
                _dg_latest4 = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_latest.csv"
                if _dg_latest4.exists():
                    try:
                        _dg4 = pd.read_csv(_dg_latest4)
                        _median_thru4 = (
                            pd.to_numeric(_dg4.get("thru", pd.Series()), errors="coerce")
                            .median()
                        )
                        if pd.notna(_median_thru4) and _median_thru4 >= 17:
                            return "post"
                        return "r4"
                    except Exception:
                        pass
                return "r4" if "in progress" in _status else "post"
        except Exception:
            pass  # fall through to schedule-based detection

    # ── Schedule-date fallback ────────────────────────────────────────────────
    _schedule = DATA_DIR / "raw" / "schedule_2026.csv"
    if _schedule.exists():
        try:
            _sched = pd.read_csv(_schedule)
            _row = None
            for _col in ["tournament_id", "tid"]:
                if _col in _sched.columns:
                    _m = _sched[_sched[_col].astype(str).str.upper() == tid.upper()]
                    if not _m.empty:
                        _row = _m.iloc[0]
                        break
            if _row is not None:
                for _dc in ["start_date", "date"]:
                    if _dc in _row.index and pd.notna(_row[_dc]):
                        _start = _date.fromisoformat(str(_row[_dc])[:10])
                        _days  = (_date.today() - _start).days
                        if _days < 0:
                            return "pre"
                        if _days == 0:
                            return "r1"
                        if _days == 1:
                            return "r2"
                        if _days == 2:
                            return "r3"
                        if _days == 3:
                            return "r4"
                        return "post"
        except Exception:
            pass

    return "pre"   # safe default — accept all markets


@dataclass
class RecommendationConfig:
    min_confidence: float = 0.60
    min_edge_points: float = 1.50   # edge = DG_prob - 1/decimal; consistent with EV
    min_ev_per_1: float = 0.01     # 1% minimum EV floor — filters near-breakeven bets
    min_kelly_fraction: float = 0.005  # 0.5% half-Kelly — filters marginal plays a real bettor wouldn't touch
    max_abs_odds: int = 5000        # longshots never win; don't chase them
    max_per_market: int = 5
    top_n: int = 20
    top_n_cards: int = 8
    include_cards: bool = True
    include_partial_cards: bool = False
    phase: str = "pre"              # tournament phase — controls which markets are live


def apply_recommendation_filters(df: pd.DataFrame, cfg: RecommendationConfig) -> pd.DataFrame:
    if df.empty:
        return df

    work = df.copy()

    # ── Phase-based market filter ─────────────────────────────────────────────
    # Remove markets that are no longer live given the tournament phase.
    # E.g. make_cut bets after the cut is confirmed, or h2h_r1 after Round 1.
    _valid_mkts = _PHASE_VALID_MARKETS.get(cfg.phase, _PHASE_VALID_MARKETS["pre"])
    if _valid_mkts:  # non-empty set means we have restrictions
        before = len(work)
        work = work[work["market"].isin(_valid_mkts)]
        removed = before - len(work)
        if removed:
            print(f"  Phase filter ({cfg.phase}): removed {removed} stale-market bets")
    elif cfg.phase == "post":
        print("  Phase filter: tournament is over — no valid bets")
        return pd.DataFrame()

    if work.empty:
        return work

    # ── Realistic probability floor ───────────────────────────────────────────
    # Filter out bets where the model probability is too low to be meaningful.
    # A WR-200 player showing +3pp edge on outright win (1.5% vs 1.0%) is noise,
    # not a real opportunity.  Each market has a minimum meaningful probability.
    def _above_floor(row: pd.Series) -> bool:
        mkt   = str(row.get("market", ""))
        mp    = pd.to_numeric(row.get("model_prob"), errors="coerce")
        floor = _REALISTIC_MIN_MODEL_PROB.get(mkt, 0.0)
        if pd.isna(mp):
            return False
        return float(mp) >= floor

    before = len(work)
    work = work[work.apply(_above_floor, axis=1)]
    removed = before - len(work)
    if removed:
        print(f"  Probability floor: removed {removed} low-probability bets")

    if work.empty:
        return work

    # ── Market exclusions ──────────────────────────────────────────────────────
    # nationality_group: 2.4% actual vs 37.5% model_prob → -271u. Excluded.
    # outright: 109 graded bets, 0 wins. Books too efficient.
    # group_winner: 16.2% actual vs ~33% expected. Poor signal.
    # h2h (tournament-long): 26.3% actual vs ~50% expected. Excluded.
    # top5: 1% win rate across 395 graded bets, -78.6% ROI. Model systematically
    #   overestimates top-5 finish probability. Excluded permanently.
    # make_cut: ACTIVE. 100% win rate, +48.4% ROI.
    # h2h_r1/r2/r3/r4: ACTIVE. Round-specific matchups retain differentiated signal.
    _EXCLUDED_MARKETS = {"nationality_group", "outright", "group_winner", "h2h", "top5"}
    work = work[~work["market"].isin(_EXCLUDED_MARKETS)]

    # ── Per-market minimum edge overrides ────────────────────────────────────
    # make_cut: 4pp — well-calibrated binary prop
    # Edge = DG_prob - 1/decimal (consistent with EV = DG_prob × decimal - 1).
    # Since DG probs are vig-free and dead-heat adjusted, edge > 0 ↔ EV > 0.
    # Thresholds set to filter tiny-margin bets where variance dominates:
    #   top10/top20: 1.5pp → EV ≥ 2-3% at typical pool odds
    #   h2h_r1: 3pp → DG model must have meaningful read over book price
    #   make_cut: 2pp → binary prop, high base-rate, want clear signal
    _mkt_min_edge = {
        "make_cut": 2.0,
        "top10":    1.5,
        "top20":    1.5,
        "h2h_r1":   3.0,
        "outright": 3.0,
    }

    # ── Max book odds cap for pool markets ────────────────────────────────────
    # The model overestimates pool market probs for long shots. When the book
    # prices a player at +700+ for top10 or +400+ for top20, the "edge" we see
    # is model error, not market inefficiency. Cap to avoid chasing long shots.
    _MAX_BOOK_ODDS: dict[str, int] = {
        "top10": 700,   # book prob ≥ 12.5% — no top10 on +700 or longer
        "top20": 400,   # book prob ≥ 20.0% — no top20 on +400 or longer
    }
    if _MAX_BOOK_ODDS:
        _odds_col_raw = pd.to_numeric(work["odds_american"], errors="coerce")
        _cap_mask = pd.Series(True, index=work.index)
        for _mkt, _max_odds in _MAX_BOOK_ODDS.items():
            _is_mkt = work["market"] == _mkt
            _too_long = _odds_col_raw > _max_odds
            _cap_mask = _cap_mask & ~(_is_mkt & _too_long)
        before = len(work)
        work = work[_cap_mask]
        removed = before - len(work)
        if removed:
            print(f"  Book odds cap: removed {removed} long-shot pool bets")
    
    work = work[
        work.apply(
            lambda r: pd.to_numeric(r["edge_pts"], errors="coerce") >=
                      _mkt_min_edge.get(str(r["market"]), cfg.min_edge_points),
            axis=1,
        )
    ]

    work = work[pd.to_numeric(work["confidence"], errors="coerce") >= cfg.min_confidence]
    work = work[pd.to_numeric(work["edge_pts"], errors="coerce") >= cfg.min_edge_points]
    work = work[pd.to_numeric(work["ev_per_1"], errors="coerce") >= cfg.min_ev_per_1]
    work = work[pd.to_numeric(work["odds_american"], errors="coerce").abs() <= cfg.max_abs_odds]

    # ── Kelly fraction floor ───────────────────────────────────────────────────
    # Filters bets where even a fractional-Kelly bettor would stake near zero.
    # A low Kelly fraction means the edge is real but the bet isn't worth the
    # capital risk — either the model probability is too low or the odds are too
    # long for the certainty required. 0.5% half-Kelly is the minimum threshold.
    if "kelly_fraction" in work.columns and cfg.min_kelly_fraction > 0:
        before = len(work)
        work = work[pd.to_numeric(work["kelly_fraction"], errors="coerce") >= cfg.min_kelly_fraction]
        removed = before - len(work)
        if removed:
            print(f"  Kelly floor ({cfg.min_kelly_fraction:.3f}): removed {removed} marginal bets")

    if work.empty:
        return work

    singles = work[work["bet_type"] == "single"].copy()
    cards = work[work["bet_type"] == "content_card"].copy()

    _sort_cols = (
        ["kelly_fraction", "edge_pts", "ev_per_1", "confidence"]
        if "kelly_fraction" in work.columns
        else ["edge_pts", "ev_per_1", "confidence"]
    )
    _sort_asc = [False] * len(_sort_cols)

    if not singles.empty:
        singles = singles.sort_values(_sort_cols, ascending=_sort_asc)
        # h2h and group_winner have many more legs than finish markets — allow more per market
        _cap = singles["market"].map(
            lambda m: 12 if str(m).startswith("h2h") or m == "group_winner"
            else cfg.max_per_market
        )
        singles["_market_rank"] = singles.groupby("market").cumcount() + 1
        singles = singles[singles["_market_rank"] <= _cap].drop(columns=["_market_rank"])

        # Cap to 1 bet per player+market: prefer FanDuel, else best price among legal US books.
        if "book" in singles.columns and "player_name" in singles.columns:
            _ranked = singles.copy()
            _ranked["_is_fd"] = (_ranked["book"].str.upper() == "FANDUEL").astype(int)
            # Build a numeric odds column for sorting (highest = best price)
            _odds_col = next((c for c in ("odds", "odds_american", "line") if c in _ranked.columns), None)
            _ranked["_tmp_odds"] = pd.to_numeric(_ranked[_odds_col], errors="coerce") if _odds_col else 0
            _ranked = _ranked.sort_values(
                ["player_name", "market", "_is_fd", "_tmp_odds"],
                ascending=[True, True, False, False],
            )
            singles = _ranked.drop_duplicates(subset=["player_name", "market"], keep="first").drop(
                columns=["_is_fd", "_tmp_odds"], errors="ignore"
            )

        singles = singles.head(cfg.top_n + 20)  # allow more total to fit h2h/group

    if not cards.empty:
        if not cfg.include_partial_cards:
            cards = cards[cards["status"] == "priced"]
        cards = cards.sort_values(_sort_cols, ascending=_sort_asc).head(cfg.top_n_cards)

    out = pd.concat([singles, cards], ignore_index=True)
    if out.empty:
        return out

    out = out.sort_values(_sort_cols, ascending=_sort_asc).reset_index(drop=True)
    return out


def add_corroboration_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add corroboration_score: # of distinct market families where a player has edge > 0.

    A bet with corroboration_score >= 2 means the model independently found
    positive edge on the same player in multiple markets (e.g. top10 + H2H +
    3-ball group). That convergence is a much stronger signal than a single
    market crossing the edge threshold.

    Side effects:
    - Adds ``corroboration_score`` (int) and ``corroborated`` (bool) columns.
    - Boosts ``confidence`` by 0.05 for corroborated single bets (capped at 0.95).
    - Re-sorts so corroborated bets surface first within the same edge tier.
    """
    if df.empty or "player_name" not in df.columns:
        return df

    work = df.copy()

    # Normalise market to family so h2h_r1/r2/r3 all count as one "h2h" signal
    def _mkt_family(m: str) -> str:
        m = str(m or "")
        if m.startswith("h2h"):
            return "h2h"
        return m

    work["_family"] = work["market"].apply(_mkt_family)

    # Count distinct families with positive edge per named player
    scored = work[
        (pd.to_numeric(work["edge_pts"], errors="coerce") > 0) &
        work["player_name"].notna() &
        (work["player_name"].astype(str).str.strip() != "")
    ].copy()

    corr = (
        scored.groupby("player_name")["_family"]
        .nunique()
        .rename("corroboration_score")
    )

    work = work.merge(corr, on="player_name", how="left")
    work["corroboration_score"] = work["corroboration_score"].fillna(0).astype(int)
    work["corroborated"] = work["corroboration_score"] >= 2

    # Small confidence lift for corroborated bets
    boost = work["corroborated"] & (work["bet_type"] == "single")
    work.loc[boost, "confidence"] = (
        pd.to_numeric(work.loc[boost, "confidence"], errors="coerce").add(0.05).clip(upper=0.95)
    )

    work = work.drop(columns=["_family"])

    n_corr = int(work["corroborated"].sum())
    if n_corr:
        print(f"  Corroboration: {n_corr} bets have 2+ market signals on the same player")

    # Corroborated bets first, then by edge within each tier
    work = work.sort_values(
        ["corroborated", "edge_pts", "ev_per_1", "confidence"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    return work


def build_bet_reasoning(
    pred_row: dict,
    market: str,
    model_prob: float,
    book_prob: float,
    corroboration_score: int = 0,
    group_members: str = "",
    field_size: int = 135,
) -> str:
    """Generate a pipe-separated reasoning string for a bet recommendation.

    Stored in the ``reasoning`` column of the output CSV so it persists
    across sessions and can be displayed anywhere in the dashboard.

    Format: "Model 31.2% vs book 24.1% (+7.1pp) | APP +1.34 SG #8/135 | 6 cuts straight | Won here 2x"
    """
    mkt = canonical_market(market)
    parts: list[str] = []

    # ── 1. Core edge statement ────────────────────────────────────────────────
    edge = (model_prob - book_prob) * 100.0
    mkt_labels = {
        "top10": "top-10", "top20": "top-20", "top5": "top-5",
        "make_cut": "make cut", "miss_cut": "miss cut",
        "outright": "win", "h2h": "matchup", "group_winner": "3-ball win",
    }
    mkt_lbl = mkt_labels.get(mkt, mkt.replace("_", " "))
    parts.append(
        f"Model {model_prob*100:.1f}% {mkt_lbl} vs book {book_prob*100:.1f}% → +{edge:.1f}pp"
    )

    # ── 2. Strongest SG category ─────────────────────────────────────────────
    sg_map = {
        "season_sg_app":  ("APP",  "season_sg_app_field_rank"),
        "season_sg_putt": ("PUTT", "season_sg_putt_field_rank"),
        "season_sg_ott":  ("OTT",  "season_sg_ott_field_rank"),
        "season_sg_arg":  ("ARG",  "season_sg_arg_field_rank"),
    }
    best_lbl, best_val, best_rank = None, 0.0, None
    for col, (lbl, rank_col) in sg_map.items():
        v = float(pred_row.get(col, 0) or 0)
        if v > best_val:
            best_val = v
            best_lbl = lbl
            r = pred_row.get(rank_col)
            try:
                best_rank = int(r) if r is not None and not (isinstance(r, float) and np.isnan(r)) else None
            except (TypeError, ValueError):
                best_rank = None
    if best_lbl and best_val > 0.15:
        rank_str = f" #{best_rank}/{field_size}" if best_rank else ""
        parts.append(f"{best_lbl} +{best_val:.2f} SG/rnd{rank_str}")

    # ── 3. Form signal ───────────────────────────────────────────────────────
    consec = int(pred_row.get("consecutive_cuts", 0) or 0)
    ft     = float(pred_row.get("form_trend", 0) or 0)
    hot    = float(pred_row.get("hot_hand_score", 0) or 0)
    if consec >= 6:
        parts.append(f"{consec} consecutive cuts made")
    elif consec >= 3 and ft > 0.2:
        parts.append(f"{consec} cuts, form rising +{ft:.2f}")
    elif hot >= 7.5:
        parts.append(f"Hot form ({hot:.0f}/10 hot-hand)")
    elif ft > 0.35:
        parts.append(f"Form trending sharply (+{ft:.2f})")

    # ── 4. Course history ────────────────────────────────────────────────────
    hist_starts = int(pred_row.get("hist_times_played", 0) or 0)
    hist_wins   = int(pred_row.get("hist_wins", 0) or 0)
    hist_t10    = int(pred_row.get("hist_top10s", 0) or 0)
    course_sg   = float(pred_row.get("course_sg_total_weighted", 0) or 0)
    if hist_wins > 0:
        parts.append(f"Won here {hist_wins}x ({hist_starts} starts)")
    elif hist_t10 >= 2 and hist_starts >= 2:
        parts.append(f"{hist_t10} top-10s in {hist_starts} course starts")
    elif hist_t10 == 1 and hist_starts >= 2:
        parts.append(f"Top-10 in {hist_starts} starts here")
    elif hist_starts == 0 and course_sg > 0.3:
        parts.append(f"Course fit: +{course_sg:.2f} SG (no prior starts)")
    elif hist_starts == 0:
        parts.append("No course history — model relies on SG profile")

    # ── 5. Corroboration / H2H context ──────────────────────────────────────
    if corroboration_score >= 2:
        parts.append(f"{corroboration_score} independent markets agree")
    if group_members and "|" in group_members and mkt in ("h2h", "h2h_r1", "h2h_r2", "group_winner"):
        # Shorten opponent list for readability
        opponents = [s.strip() for s in group_members.split("|")][:3]
        parts.append("vs " + " | ".join(opponents))

    # ── 6. Odds movement ────────────────────────────────────────────────────
    direction = str(pred_row.get("dk_odds_direction", "")).upper()
    if direction == "UP":
        parts.append("Odds shortening — market moving our way")
    elif direction == "DOWN":
        parts.append("Odds drifting — value may be fleeting")

    return " | ".join(parts[:5])


def add_reasoning_column(df: pd.DataFrame, preds_df: pd.DataFrame) -> pd.DataFrame:
    """Attach a ``reasoning`` string to every row of a recommendation DataFrame.

    Reads player stats from *preds_df* (matched by normalized name key).
    Safe to call even when preds_df is empty — produces an empty string.
    """
    if df.empty:
        df = df.copy()
        df["reasoning"] = ""
        return df

    field_size = len(preds_df) if not preds_df.empty else 135

    by_key: dict[str, dict] = {}
    if not preds_df.empty and "player_name" in preds_df.columns:
        tmp = preds_df.copy()
        tmp["_nk"] = tmp["player_name"].apply(normalize_name_key)
        by_key = {r["_nk"]: r.to_dict() for _, r in tmp.iterrows() if r["_nk"]}

    def _reason(row: pd.Series) -> str:
        player_key = normalize_name_key(str(row.get("player_name", "")))
        pred_row   = by_key.get(player_key, {})
        mp  = float(pd.to_numeric(row.get("model_prob"), errors="coerce") or 0)
        bp  = float(pd.to_numeric(row.get("book_prob"),  errors="coerce") or 0)
        cs  = int(pd.to_numeric(row.get("corroboration_score"), errors="coerce") or 0)
        gm  = str(row.get("group_members", "") or "")
        mkt = str(row.get("market", ""))
        # Merge odds direction from pred_row if available
        if not pred_row and mp > 0 and bp > 0:
            return (
                f"Model {mp*100:.1f}% vs book {bp*100:.1f}% → "
                f"+{(mp-bp)*100:.1f}pp edge"
            )
        return build_bet_reasoning(
            pred_row=pred_row,
            market=mkt,
            model_prob=mp,
            book_prob=bp,
            corroboration_score=cs,
            group_members=gm,
            field_size=field_size,
        )

    df = df.copy()
    df["reasoning"] = df.apply(_reason, axis=1)
    return df


def build_recommendations(
    tournament_id: str,
    preds_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    cards_df: pd.DataFrame,
    cfg: RecommendationConfig,
) -> pd.DataFrame:
    # Build multi-book no-vig consensus for outright market edge calculation
    consensus_map = build_consensus_book_probs(tournament_id, preds_df)
    if consensus_map:
        print(f"  Consensus map: {len(consensus_map)} players across multiple books")

    # Build per-book no-vig for prop markets (top5/top10/top20/etc.)
    # Fixes the mixed-book inflation bug: when DK + FanDuel lines coexist in
    # lines_df, using a combined vig factor halves book_prob and inflates edges.
    prop_consensus_map = build_prop_consensus_probs(lines_df)

    # Load DG model probabilities for pool markets — primary signal when available
    dg_model_probs = _dg_outright_model_lookup(tournament_id)
    if dg_model_probs:
        n_dg = len(set(k[0] for k in dg_model_probs))
        print(f"  DG model probs loaded: {n_dg} players × {len(set(k[1] for k in dg_model_probs))} markets")

    single_df    = score_single_markets(preds_df, lines_df, consensus_map=consensus_map,
                                        prop_consensus_map=prop_consensus_map,
                                        dg_model_probs=dg_model_probs or None)
    h2h_df       = score_h2h_markets(preds_df, lines_df, tid=tournament_id)
    group_df     = score_group_winner_markets(preds_df, lines_df)
    w2w_df       = score_wire_to_wire_market(preds_df, lines_df, tid=tournament_id)
    if not w2w_df.empty:
        print(f"  Wire-to-wire: {len(w2w_df)} candidates scored")

    content_rows = pd.DataFrame()
    if cfg.include_cards and not cards_df.empty:
        scored_cards_df, _ = score_content_cards(cards_df, preds_df)
        if not scored_cards_df.empty:
            content_rows = scored_cards_df.copy()
            content_rows["bet_type"] = "content_card"
            content_rows["market"] = "content_card"
            content_rows["player_name"] = ""
            content_rows["selection_label"] = content_rows["title"].fillna("")
            content_rows["book"] = "DRAFTKINGS"

    all_rows = pd.concat([single_df, h2h_df, group_df, w2w_df, content_rows], ignore_index=True)
    if all_rows.empty:
        return all_rows

    filtered = apply_recommendation_filters(all_rows, cfg)
    if filtered.empty:
        return filtered

    # Cross-market corroboration: boost and re-rank bets backed by 2+ markets
    filtered = add_corroboration_scores(filtered)

    # Reasoning: human-readable explanation stored in CSV for persistent display
    filtered = add_reasoning_column(filtered, preds_df)

    run_id = now_utc_iso()
    rec_ts = run_id

    filtered = filtered.reset_index(drop=True)
    filtered["recommendation_rank"] = np.arange(1, len(filtered) + 1)
    filtered["tournament_id"] = tournament_id
    filtered["tournament_phase"] = cfg.phase
    filtered["run_id"] = run_id
    filtered["recommended_at"] = rec_ts

    # Kelly criterion stake sizing (half-Kelly, capped at 5% of bankroll)
    def _kelly(row: pd.Series) -> float:
        mp = pd.to_numeric(row.get("model_prob"), errors="coerce")
        o  = pd.to_numeric(row.get("odds_american"), errors="coerce")
        if pd.isna(mp) or pd.isna(o):
            return 0.0
        dec = american_to_decimal(int(o))
        if pd.isna(dec):
            return 0.0
        return kelly_fraction(float(mp), float(dec))

    filtered["kelly_fraction"] = filtered.apply(_kelly, axis=1)
    # stake_units kept as 1.0 for backward-compat (log grading uses it)
    filtered["stake_units"] = 1.0
    filtered["outcome_status"] = "pending"
    filtered["outcome_win"] = np.nan
    filtered["pnl_per_1"] = np.nan
    filtered["roi_pct"] = np.nan
    filtered["closing_odds_american"] = np.nan
    filtered["closing_implied_prob"] = np.nan
    filtered["clv_pts"] = np.nan
    filtered["graded_at"] = ""

    def make_rec_id(row: pd.Series) -> str:
        raw = "|".join([
            str(row.get("run_id", "")),
            str(row.get("tournament_id", "")),
            str(row.get("bet_type", "")),
            str(row.get("market", "")),
            str(row.get("player_name", "")),
            str(row.get("selection_label", "")),
            str(row.get("card_id", "")),
            str(row.get("odds_american", "")),
            str(row.get("book", "")),  # include book so same odds at diff books get unique IDs
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    filtered["recommendation_id"] = filtered.apply(make_rec_id, axis=1)

    ordered_cols = [
        "recommendation_id",
        "run_id",
        "recommended_at",
        "tournament_id",
        "tournament_phase",
        "recommendation_rank",
        "bet_type",
        "market",
        "book",
        "player_name",
        "selection_label",
        "card_id",
        "title",
        "selection_count",
        "priced_legs",
        "unpriced_legs",
        "selection_labels",
        "selection_labels_json",
        "odds_american",
        "book_prob",
        "model_prob",
        "raw_model_prob",
        "edge_pts",
        "ev_per_1",
        "confidence",
        "corroboration_score",
        "corroborated",
        "group_members",
        "leg_prob_summary",
        "weakest_leg",
        "weakest_leg_prob",
        "reasoning",
        "status",
        "stake_units",
        "kelly_fraction",
        "outcome_status",
        "outcome_win",
        "pnl_per_1",
        "roi_pct",
        "closing_odds_american",
        "closing_implied_prob",
        "clv_pts",
        "graded_at",
    ]
    ordered_cols = [c for c in ordered_cols if c in filtered.columns]
    return filtered[ordered_cols].copy()


def append_log(log_path: Path, recs_df: pd.DataFrame) -> pd.DataFrame:
    if log_path.exists():
        try:
            prev = pd.read_csv(log_path)
            combined = pd.concat([prev, recs_df], ignore_index=True)
        except Exception:
            combined = recs_df.copy()
    else:
        combined = recs_df.copy()

    if "recommendation_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["recommendation_id"], keep="last")
    
    _dedup_cols = ['tournament_id', 'player_name', 'market']
    if all(c in combined.columns for c in _dedup_cols):
        # Sort oldest first so keep="first" preserves the original recommendation                                         
      if "recommended_at" in combined.columns:                                                                          
          combined = combined.sort_values("recommended_at", ascending=True)                                             
      combined = combined.drop_duplicates(subset=_dedup_cols, keep="first")
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tracked +EV bet recommendations")
    parser.add_argument("--tournament-id", default="", help="Tournament ID, e.g. R2026007")
    parser.add_argument("--predictions", default="", help="Path to predictions CSV")
    parser.add_argument("--prop-lines", default="", help="Path to prop lines CSV")
    parser.add_argument("--cards", default="", help="Path to DK content cards CSV")

    parser.add_argument("--min-confidence", type=float, default=0.45)
    parser.add_argument("--min-edge-points", type=float, default=0.75)
    parser.add_argument("--min-ev", type=float, default=0.01)
    parser.add_argument("--max-abs-odds", type=int, default=5000)   # fixed: was 10000
    parser.add_argument("--max-per-market", type=int, default=15)
    parser.add_argument("--top-n", type=int, default=40)
    parser.add_argument("--top-n-cards", type=int, default=8)
    parser.add_argument("--no-cards", action="store_true", help="Disable content-card recommendations")
    parser.add_argument("--include-partial-cards", action="store_true")
    parser.add_argument('--min-kelly', type=float,default=None, help="Minimum Kelly fraction (e.g. 0.005 for 0.5% half-Kelly) to filter marginal bets")
    parser.add_argument(
        "--phase",
        default="auto",
        choices=["auto", "pre", "r1", "r2", "r2_postcut", "r3", "r4", "post"],
        help="Tournament phase (default: auto-detect from live metadata + schedule)",
    )

    args = parser.parse_args()

    tid = resolve_tournament_id(args.tournament_id)
    if not tid:
        print("No tournament ID found. Provide --tournament-id.")
        return 1

    pred_path = resolve_predictions_path(tid, args.predictions)
    cards_path = resolve_cards_path(tid, args.cards)

    if pred_path is None or not pred_path.exists():
        print("Predictions file not found.")
        return 1

    preds_df = pd.read_csv(pred_path)
    cards_df = pd.read_csv(cards_path) if (cards_path and cards_path.exists()) else pd.DataFrame()

    # Always fetch fresh DG odds — DG returns the current live event, so cached files
    # go stale when a new tournament starts. Re-fetch if file is missing OR > 4h old.
    import time as _time_mod
    _dg_outrights_path = DATA_DIR / "datagolf" / f"dg_outrights_{tid}.csv"
    _dg_matchups_path  = DATA_DIR / "datagolf" / f"dg_matchups_{tid}.csv"
    _dg_age_hours = 999.0
    if _dg_outrights_path.exists():
        _dg_age_hours = (_time_mod.time() - _dg_outrights_path.stat().st_mtime) / 3600
    if _dg_age_hours > 4.0:
        print(f"[INFO] Fetching fresh DataGolf odds (cached data is {_dg_age_hours:.1f}h old)...")
        try:
            import subprocess
            subprocess.run(
                ["python3", str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_dg_odds.py"),
                 "--tournament-id", tid, "--market", "all"],
                timeout=120, capture_output=False,
            )
        except Exception as _dg_err:
            print(f"  [warn] DG fetch failed: {_dg_err}")

    # Detect phase early so we can pass the correct round to DG matchup lines.
    _phase_early = args.phase
    if _phase_early == "auto":
        _phase_early = get_tournament_phase(tid)
    _phase_round_map = {"r1": 1, "r2": 2, "r2_postcut": 2, "r3": 3, "r4": 4}
    _current_round = _phase_round_map.get(_phase_early, 1)

    # Build lines_df: DG outrights are the primary source for outright/top5/top10/top20.
    # prop_lines (DK scraper) is dropped for markets DG covers — DG is fresher and
    # includes 10+ books (Pinnacle, Betcris, Bet365, etc.) vs DK-only from the scraper.
    _DG_MARKETS = {"outright", "top5", "top10", "top20"}

    dg_outright_lines = _dg_outrights_to_prop_lines(tid)
    if not dg_outright_lines.empty:
        lines_df = dg_outright_lines
        print(f"  DG outrights: {len(lines_df)} rows, {lines_df['book'].nunique()} books")
    else:
        # Fallback to prop_lines if DG file is missing
        _specific_lines = ODDS_DIR / f"prop_lines_{tid}.csv"
        if _specific_lines.exists():
            lines_df = pd.read_csv(_specific_lines)
            print(f"  Fallback prop lines: {_specific_lines.name} ({len(lines_df)} rows)")
        else:
            print("No lines available (DG outrights empty and no prop_lines file).")
            return 1

    # DataGolf round matchup lines — primary H2H source (all books incl. Pinnacle/Betcris).
    # Pass current round so matchups score as h2h_r1/r2/r3/r4 correctly.
    dg_matchup_lines = _dg_matchups_to_prop_lines(tid, round_num=_current_round)
    if not dg_matchup_lines.empty:
        lines_df = pd.concat([lines_df, dg_matchup_lines], ignore_index=True)
        n_books = dg_matchup_lines["book"].nunique()
        print(f"  DG matchups (R{_current_round}): {len(dg_matchup_lines)//2} pairs, {n_books} books")

    if not lines_df.empty and "player_name" in lines_df.columns and "market" in lines_df.columns:
        # Dedup single-market rows only (player_name + market + book).
        # H2H rows use player_a/player_b and have no player_name — exclude from dedup.
        _h2h_mask = lines_df["market"].astype(str).str.lower() == "h2h"
        _single_df = lines_df[~_h2h_mask].copy()
        _h2h_df    = lines_df[_h2h_mask].copy()

        if not _single_df.empty:
            _single_df["_nkey_dedup"] = _single_df["player_name"].apply(normalize_name_key)
            _src_series = _single_df["_source_priority"] if "_source_priority" in _single_df.columns else pd.Series(0, index=_single_df.index)
            _single_df["_src_pri"] = pd.to_numeric(_src_series, errors="coerce").fillna(0)
            _odds_col = "odds" if "odds" in _single_df.columns else None
            if _odds_col:
                _single_df["_odds_sort"] = pd.to_numeric(_single_df[_odds_col], errors="coerce")
                _single_df = (
                    _single_df.sort_values(["_src_pri", "_odds_sort"], ascending=[True, False])
                    .drop_duplicates(subset=["_nkey_dedup", "market", "book"], keep="first")
                    .drop(columns=["_nkey_dedup", "_src_pri", "_odds_sort", "_source_priority"], errors="ignore")
                    .reset_index(drop=True)
                )

        lines_df = pd.concat([_single_df, _h2h_df], ignore_index=True)









    # ── Phase detection ───────────────────────────────────────────────────────
    _phase = _phase_early  # already detected above before lines_df was built
    print(f"  Tournament phase: {_phase}")

    cfg = RecommendationConfig(
        min_confidence=float(args.min_confidence),
        min_edge_points=float(args.min_edge_points),
        min_ev_per_1=float(args.min_ev),
        max_abs_odds=int(args.max_abs_odds),
        max_per_market=int(args.max_per_market),
        top_n=int(args.top_n),
        top_n_cards=int(args.top_n_cards),
        include_cards=(not args.no_cards),
        include_partial_cards=bool(args.include_partial_cards),
        phase=_phase,
        min_kelly_fraction=float(args.min_kelly) if args.min_kelly is not None else 0.005,
    )

    recs_df = build_recommendations(tid, preds_df, lines_df, cards_df, cfg)

    # ── Annotate with intel flags ─────────────────────────────────────────────
    intel_path = DATA_DIR / "intel" / f"tournament_intel_{tid}.json"
    if not recs_df.empty and intel_path.exists():
        try:
            import json as _json
            intel = _json.loads(intel_path.read_text())
            # Build lookup: normalised last name → intel row
            def _nk(n):
                s = str(n).strip().lower()
                return s.split(",")[0].strip() if "," in s else s.split()[-1]
            intel_by_lname = {}
            for p in intel.get("players", []):
                intel_by_lname[_nk(p.get("player_name", ""))] = p

            warnings_col = []
            for _, row in recs_df.iterrows():
                p = intel_by_lname.get(_nk(row.get("player_name", "")), {})
                if p.get("injury_flag"):
                    warnings_col.append("injury risk")
                elif p.get("trend") == "trending_down" and p.get("sentiment") == "negative":
                    warnings_col.append("poor form + negative news")
                elif p.get("trend") == "trending_down":
                    warnings_col.append("form declining")
                elif p.get("sentiment") == "negative":
                    warnings_col.append("negative news")
                else:
                    warnings_col.append("")
            recs_df = recs_df.copy()
            recs_df["intel_warning"] = warnings_col
            flagged = sum(1 for w in warnings_col if w)
            if flagged:
                print(f"  Intel flags: {flagged} bets have warnings")
        except Exception as _ie:
            print(f"  [warn] Intel annotation failed: {_ie}")

    # Persist outputs even if empty to keep pipeline deterministic.
    out_path = ODDS_DIR / f"recommended_bets_{tid}.csv"
    latest_path = ODDS_DIR / "recommended_bets_latest.csv"
    log_path = ODDS_DIR / "recommended_bets_log.csv"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if recs_df.empty:
        # keep schema stable
        pd.DataFrame(columns=[
            "recommendation_id", "run_id", "recommended_at", "tournament_id", "recommendation_rank",
            "bet_type", "market", "book", "player_name", "selection_label", "card_id", "title",
            "selection_count", "priced_legs", "unpriced_legs", "selection_labels", "selection_labels_json",
            "odds_american", "book_prob", "model_prob", "edge_pts", "ev_per_1", "confidence", "status",
            "stake_units", "outcome_status", "outcome_win", "pnl_per_1", "roi_pct",
            "closing_odds_american", "closing_implied_prob", "clv_pts", "graded_at",
        ]).to_csv(out_path, index=False)
        # Don't overwrite _latest with an empty file — keep the most recent active week's recs
        # so the dashboard always shows something useful.
        if _phase != "post":
            (ODDS_DIR / "recommended_bets_latest.csv").write_text(out_path.read_text())
        print(f"No qualifying recommendations for {tid} with current thresholds.")
        print(f"Wrote empty recommendation file -> {out_path}")
        return 0

    recs_df.to_csv(out_path, index=False)
    recs_df.to_csv(latest_path, index=False)
    append_log(log_path, recs_df)

    single_count = int((recs_df["bet_type"] == "single").sum()) if "bet_type" in recs_df.columns else 0
    card_count = int((recs_df["bet_type"] == "content_card").sum()) if "bet_type" in recs_df.columns else 0
    best_edge = pd.to_numeric(recs_df.get("edge_pts"), errors="coerce").max()
    avg_conf = pd.to_numeric(recs_df.get("confidence"), errors="coerce").mean()

    print(f"Generated {len(recs_df)} recommendations for {tid}")
    print(f"  Singles: {single_count} | Cards: {card_count}")
    print(f"  Best edge: {best_edge:+.2f} pts | Avg confidence: {avg_conf:.2f}")
    print(f"Saved -> {out_path}")
    print(f"Saved -> {latest_path}")
    print(f"Appended log -> {log_path}")

    # Auto-snapshot open line for CLV tracking
    try:
        import subprocess
        subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "predictions" / "log_closing_line.py"),
             "--tournament-id", tid, "--type", "open"],
            capture_output=True, timeout=30
        )
    except Exception:
        pass  # Non-blocking — CLV logging failure should never stop rec output

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
