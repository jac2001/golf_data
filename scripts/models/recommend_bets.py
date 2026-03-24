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

    Loads FanDuel and PGA Tour odds files (when available) alongside DK
    implied probs already in preds_df.  For each book, normalizes the raw
    implied probs so they sum to 1.0 (removes the vig).  Returns a
    name_key → consensus_prob dict (median across available books).

    Falls back to an empty dict if no additional books are found — callers
    should treat a missing key as "use DK raw implied_prob".
    """
    book_probs: dict[str, list[float]] = {}  # name_key → [prob_book1, ...]

    def _load_book(path: Path, name_col: str, odds_col: str) -> None:
        try:
            df = pd.read_csv(path)
            if name_col not in df.columns or odds_col not in df.columns:
                return
            df = df[[name_col, odds_col]].copy()
            df["raw_prob"] = df[odds_col].apply(american_to_prob)
            df = df[df["raw_prob"].notna() & (df["raw_prob"] > 0)]
            total = df["raw_prob"].sum()
            if total <= 0:
                return
            df["nv_prob"] = df["raw_prob"] / total
            for _, row in df.iterrows():
                key = normalize_name_key(row[name_col])
                if key:
                    book_probs.setdefault(key, []).append(float(row["nv_prob"]))
        except Exception:
            pass

    # FanDuel outright — column is "winner" market; filter if market col exists
    fd_path = ODDS_DIR / f"fanduel_odds_{tournament_id}.csv"
    if fd_path.exists():
        try:
            fd = pd.read_csv(fd_path)
            if "market" in fd.columns:
                fd = fd[fd["market"].astype(str).str.lower() == "winner"]
            if not fd.empty and "player_name" in fd.columns and "odds_numeric" in fd.columns:
                fd = fd[["player_name", "odds_numeric"]].copy()
                fd["raw_prob"] = fd["odds_numeric"].apply(american_to_prob)
                fd = fd[fd["raw_prob"].notna() & (fd["raw_prob"] > 0)]
                total = fd["raw_prob"].sum()
                if total > 0:
                    fd["nv_prob"] = fd["raw_prob"] / total
                    for _, row in fd.iterrows():
                        key = normalize_name_key(row["player_name"])
                        if key:
                            book_probs.setdefault(key, []).append(float(row["nv_prob"]))
                    print(f"  Consensus: loaded FanDuel odds ({len(fd)} players)")
        except Exception as e:
            print(f"  Consensus: FanDuel load failed — {e}")

    # PGA Tour odds
    pga_path = ODDS_DIR / f"pga_odds_{tournament_id}.csv"
    if pga_path.exists():
        _load_book(pga_path, "player_name", "odds_numeric")
        if pga_path.exists():
            print(f"  Consensus: loaded PGA Tour odds")

    if not book_probs:
        return {}

    # Median across books for each player
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
    PROP_MARKETS = {"top5", "top10", "top20", "top30", "make_cut", "miss_cut", "r2_leader"}
    EXPECTED_SPOTS: dict[str, float] = {
        "top5": 5.0, "top10": 10.0, "top20": 20.0, "top30": 30.0,
        "make_cut": 60.0, "miss_cut": 60.0, "r2_leader": 1.0,
    }

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
        exp   = EXPECTED_SPOTS.get(mkt, 10.0)
        scale = exp / total          # same formula as _market_vig but isolated to this book
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
    SUBMARKET_MARKET = {
        "top 5 finish":  "top5",
        "top 10 finish": "top10",
        "top 20 finish": "top20",
    }
    finish_df = df[df["market_type"] == "FINISH"].copy()
    for _, row in finish_df.iterrows():
        sub = str(row.get("submarket_name", "")).strip().lower()
        mkt = SUBMARKET_MARKET.get(sub)
        if not mkt:
            continue
        player = str(row.get("player_name", "")).strip()
        odds_num = row.get("odds_numeric")
        if not player or pd.isna(odds_num):
            continue
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

    # ── PLAYER_PROPS: Leader After Round N → r2_leader ────────────────────────
    pp_df = df[df["market_type"] == "PLAYER_PROPS"].copy()
    if not pp_df.empty:
        for _, row in pp_df.iterrows():
            sub = str(row.get("submarket_name", "")).strip().lower()
            if "leader after round" not in sub:
                continue
            player = str(row.get("player_name", "")).strip()
            odds_num = row.get("odds_numeric")
            if not player or pd.isna(odds_num):
                continue
            rows.append({
                "market":      "r2_leader",
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
    pref_cols: dict[str, list[str]] = {
        "outright": ["win_prob_calibrated", "win_prob", "win_prob_raw"],
        "top5": ["top5_prob_calibrated", "top5_prob", "top5_prob_raw"],
        "top10": ["top10_prob_calibrated", "top10_prob", "top10_prob_raw"],
        "top20": ["top20_prob_calibrated", "top20_prob", "top20_prob_raw"],
        "top30": ["top30_prob", "top20_prob"],
        "make_cut": ["make_cut_prob", "cut_prob"],
        "miss_cut": ["miss_cut_prob"],
        # Round-leader prop — no dedicated prediction column; win_prob is the
        # best available proxy (better players more likely to lead after any round).
        "r2_leader": ["win_prob_calibrated", "win_prob", "win_prob_raw"],
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


def confidence_for_single(pred_row: dict, market: str, calibrated: bool, odds: int | None) -> float:
    base = {
        "outright": 0.58,
        "top5": 0.66,
        "top10": 0.72,
        "top20": 0.78,
        "top30": 0.70,
        "make_cut": 0.75,
        "miss_cut": 0.70,
        # Win_prob is an imperfect proxy for round leadership — lower base
        "r2_leader": 0.55,
    }.get(canonical_market(market), 0.55)

    conf = base
    if calibrated:
        conf += 0.08

    hist_times = pd.to_numeric(pred_row.get("hist_times_played"), errors="coerce")
    if pd.notna(hist_times) and float(hist_times) >= 2:
        conf += 0.03

    has_history = pred_row.get("has_course_history")
    if isinstance(has_history, (bool, np.bool_)) and bool(has_history):
        conf += 0.03

    if odds is not None:
        if abs(odds) > 10000:
            conf -= 0.08
        elif abs(odds) > 5000:
            conf -= 0.05

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
) -> pd.DataFrame:
    """Score prop lines vs model predictions.

    consensus_map:      name_key → no-vig consensus outright prob (multi-book).
    prop_consensus_map: (name_key, market, book) → per-book no-vig prob.
                        Built by build_prop_consensus_probs().  When present,
                        replaces the old mixed-book _market_vig approach.
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
        if pred_row is None:
            continue

        model_prob, calibrated = market_prob_from_prediction(pred_row, mkt)
        if pd.isna(model_prob):
            continue

        odds = parse_american(line.get("odds"))
        if odds is None:
            continue

        implied = pd.to_numeric(line.get("implied_prob"), errors="coerce")
        raw_book_prob = float(implied) if pd.notna(implied) and 0 < float(implied) < 1 else american_to_prob(odds)
        if pd.isna(raw_book_prob):
            continue

        # Use no-vig probability as book_prob (priority order):
        # 1. Outright:  multi-book consensus (build_consensus_book_probs)
        # 2. Props:     per-book no-vig from build_prop_consensus_probs
        # 3. Fallback:  DK-only _market_vig (single-book normalisation)
        # 4. Last:      raw implied_prob (includes vig — least accurate)
        player_key = normalize_name_key(player_name)
        book_str   = str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS").upper()
        is_outright = mkt in {"outright", "winner"}
        if is_outright and consensus_map and player_key in consensus_map:
            book_prob = consensus_map[player_key]
        elif prop_consensus_map and (player_key, mkt, book_str) in prop_consensus_map:
            book_prob = prop_consensus_map[(player_key, mkt, book_str)]
        elif mkt in _market_vig:
            book_prob = raw_book_prob / _market_vig[mkt]
        else:
            book_prob = raw_book_prob

        dec = american_to_decimal(odds)
        if pd.isna(dec):
            continue

        edge_pts = (model_prob - book_prob) * 100.0
        ev_per_1 = (model_prob * dec) - 1.0
        conf = confidence_for_single(pred_row, mkt, calibrated, odds)

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


def score_h2h_markets(preds_df: pd.DataFrame, lines_df: pd.DataFrame) -> pd.DataFrame:
    """Score head-to-head matchup lines using model win probabilities.

    Edge for side A = model_prob_A_vs_B - book_implied_prob_A
    where model_prob_A_vs_B = win_prob_A / (win_prob_A + win_prob_B)
    """
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

    h2h_lines = lines_df[lines_df["market"].astype(str).str.lower() == "h2h"].copy()
    if h2h_lines.empty:
        return pd.DataFrame()

    pred = preds_df.copy()
    pred["name_key"] = pred["player_name"].apply(normalize_name_key)
    by_key = {r["name_key"]: r.to_dict() for _, r in pred.iterrows() if r["name_key"]}

    def get_win_prob(name: Any) -> float | None:
        k = normalize_name_key(name)
        row = by_key.get(k)
        if row is None:
            # last-name fallback
            toks = k.split()
            if toks:
                cands = [v for kk, v in by_key.items() if kk.split() and kk.split()[-1] == toks[-1]]
                if len(cands) == 1:
                    row = cands[0]
        if row is None:
            return None
        for col in ["win_prob_calibrated", "win_prob", "win_prob_raw"]:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and v > 0:
                return float(v)
        return None

    rows: list[dict] = []
    for _, line in h2h_lines.iterrows():
        pa = str(line.get("player_a", "") or "").strip()
        pb = str(line.get("player_b", "") or "").strip()
        odds_a = parse_american(line.get("odds_a"))
        odds_b = parse_american(line.get("odds_b"))
        if not pa or not pb or odds_a is None or odds_b is None:
            continue

        wp_a = get_win_prob(pa)
        wp_b = get_win_prob(pb)
        if wp_a is None or wp_b is None or (wp_a + wp_b) <= 0:
            continue

        # Normalised model probs for this matchup
        denom = wp_a + wp_b
        model_a = wp_a / denom
        model_b = wp_b / denom

        book_a = american_to_prob(odds_a)
        book_b = american_to_prob(odds_b)
        if pd.isna(book_a) or pd.isna(book_b):
            continue

        dec_a = american_to_decimal(odds_a)
        dec_b = american_to_decimal(odds_b)
        book_str = str(line.get("book", "DRAFTKINGS") or "DRAFTKINGS")
        round_num = line.get("round_num")
        mkt_label = f"h2h_r{int(round_num)}" if pd.notna(round_num) else "h2h"

        group_members = f"{pa} ({odds_a:+d}) | {pb} ({odds_b:+d})"

        for player, model_p, book_p, odds, dec in [
            (pa, model_a, book_a, odds_a, dec_a),
            (pb, model_b, book_b, odds_b, dec_b),
        ]:
            edge_pts = (model_p - book_p) * 100.0
            ev_per_1 = (model_p * dec) - 1.0
            opponent = pb if player == pa else pa
            label = f"{player} to beat {opponent}"
            if pd.notna(round_num):
                label += f" (R{int(round_num)})"
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

        for player, odds, line in players:
            if odds is None:
                continue
            model_p = wps[player] / total_wp
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


@dataclass
class RecommendationConfig:
    min_confidence: float = 0.60
    min_edge_points: float = 3.00   # raised from 1.0 — low-edge bets showed near-zero win rate
    min_ev_per_1: float = 0.00
    max_abs_odds: int = 5000        # lowered from 10000 — extreme longshots never win
    max_per_market: int = 5
    top_n: int = 20
    top_n_cards: int = 8
    include_cards: bool = True
    include_partial_cards: bool = False


def apply_recommendation_filters(df: pd.DataFrame, cfg: RecommendationConfig) -> pd.DataFrame:
    if df.empty:
        return df

    work = df.copy()

    # ── Market exclusions ──────────────────────────────────────────────────────
    # nationality_group: model applies win_prob share within nationality cohorts,
    #   but has no concept of the market's actual vig structure. Results across
    #   288 graded bets: 2.4% win rate vs 37.5% model_prob → -271 units.
    #   Excluded permanently.
    #
    # top5 / top10 / top20 (PAUSED): across 3 tournaments (869 graded finish-market
    #   bets after removing nationality_group), actual wins = 0 after removing a
    #   grading duplicate. The market is efficient for finish positions — our model
    #   overestimates probabilities for selected players because edge-selection
    #   introduces severe sample bias. Re-enable when properly recalibrated.
    #   To re-enable: remove "top5", "top10", "top20" from _EXCLUDED_MARKETS below.
    #
    # outright (PAUSED): 109 graded bets, 0 wins across all odds levels.
    #   Model finds apparent edge but books' outright markets are too efficient.
    #   Re-enable only if backed by corroborating multi-book consensus.
    _EXCLUDED_MARKETS = {"nationality_group", "top5", "top10", "top20", "outright"}
    work = work[~work["market"].isin(_EXCLUDED_MARKETS)]

    work = work[pd.to_numeric(work["confidence"], errors="coerce") >= cfg.min_confidence]
    work = work[pd.to_numeric(work["edge_pts"], errors="coerce") >= cfg.min_edge_points]
    work = work[pd.to_numeric(work["ev_per_1"], errors="coerce") >= cfg.min_ev_per_1]
    work = work[pd.to_numeric(work["odds_american"], errors="coerce").abs() <= cfg.max_abs_odds]

    if work.empty:
        return work

    singles = work[work["bet_type"] == "single"].copy()
    cards = work[work["bet_type"] == "content_card"].copy()

    if not singles.empty:
        singles = singles.sort_values(["edge_pts", "ev_per_1", "confidence"], ascending=[False, False, False])
        # h2h and group_winner have many more legs than finish markets — allow more per market
        _cap = singles["market"].map(
            lambda m: 12 if str(m).startswith("h2h") or m == "group_winner"
            else cfg.max_per_market
        )
        singles["_market_rank"] = singles.groupby("market").cumcount() + 1
        singles = singles[singles["_market_rank"] <= _cap].drop(columns=["_market_rank"])
        singles = singles.head(cfg.top_n + 20)  # allow more total to fit h2h/group

    if not cards.empty:
        if not cfg.include_partial_cards:
            cards = cards[cards["status"] == "priced"]
        cards = cards.sort_values(["edge_pts", "ev_per_1", "confidence"], ascending=[False, False, False]).head(cfg.top_n_cards)

    out = pd.concat([singles, cards], ignore_index=True)
    if out.empty:
        return out

    out = out.sort_values(["edge_pts", "ev_per_1", "confidence"], ascending=[False, False, False]).reset_index(drop=True)
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

    single_df    = score_single_markets(preds_df, lines_df, consensus_map=consensus_map,
                                        prop_consensus_map=prop_consensus_map)
    h2h_df       = score_h2h_markets(preds_df, lines_df)
    group_df     = score_group_winner_markets(preds_df, lines_df)

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

    all_rows = pd.concat([single_df, h2h_df, group_df, content_rows], ignore_index=True)
    if all_rows.empty:
        return all_rows

    filtered = apply_recommendation_filters(all_rows, cfg)
    if filtered.empty:
        return filtered

    # Cross-market corroboration: boost and re-rank bets backed by 2+ markets
    filtered = add_corroboration_scores(filtered)

    run_id = now_utc_iso()
    rec_ts = run_id

    filtered = filtered.reset_index(drop=True)
    filtered["recommendation_rank"] = np.arange(1, len(filtered) + 1)
    filtered["tournament_id"] = tournament_id
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
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    filtered["recommendation_id"] = filtered.apply(make_rec_id, axis=1)

    ordered_cols = [
        "recommendation_id",
        "run_id",
        "recommended_at",
        "tournament_id",
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
        "edge_pts",
        "ev_per_1",
        "confidence",
        "corroboration_score",
        "corroborated",
        "group_members",
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
    combined.to_csv(log_path, index=False)
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate tracked +EV bet recommendations")
    parser.add_argument("--tournament-id", default="", help="Tournament ID, e.g. R2026007")
    parser.add_argument("--predictions", default="", help="Path to predictions CSV")
    parser.add_argument("--prop-lines", default="", help="Path to prop lines CSV")
    parser.add_argument("--cards", default="", help="Path to DK content cards CSV")

    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--min-edge-points", type=float, default=1.00)
    parser.add_argument("--min-ev", type=float, default=0.00)
    parser.add_argument("--max-abs-odds", type=int, default=10000)
    parser.add_argument("--max-per-market", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--top-n-cards", type=int, default=8)
    parser.add_argument("--no-cards", action="store_true", help="Disable content-card recommendations")
    parser.add_argument("--include-partial-cards", action="store_true")

    args = parser.parse_args()

    tid = resolve_tournament_id(args.tournament_id)
    if not tid:
        print("No tournament ID found. Provide --tournament-id.")
        return 1

    pred_path = resolve_predictions_path(tid, args.predictions)
    lines_path = resolve_prop_lines_path(tid, args.prop_lines)
    cards_path = resolve_cards_path(tid, args.cards)

    if pred_path is None or not pred_path.exists():
        print("Predictions file not found.")
        return 1
    if lines_path is None or not lines_path.exists():
        print("Prop lines file not found.")
        return 1

    preds_df = pd.read_csv(pred_path)
    lines_df = pd.read_csv(lines_path)
    cards_df = pd.read_csv(cards_path) if (cards_path and cards_path.exists()) else pd.DataFrame()

    # Augment prop lines with FanDuel markets from pga_market_odds_{tid}.csv
    # (adds top20, H2H matchups, 3-ball, and group props — not in DK prop_lines)
    pga_market_lines = load_pga_market_odds(tid)
    if not pga_market_lines.empty:
        lines_df = pd.concat([lines_df, pga_market_lines], ignore_index=True)
        print(f"  Merged {len(pga_market_lines)} PGA market lines into prop_lines")

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
    )

    recs_df = build_recommendations(tid, preds_df, lines_df, cards_df, cfg)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
