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


def score_single_markets(preds_df: pd.DataFrame, lines_df: pd.DataFrame) -> pd.DataFrame:
    if preds_df.empty or lines_df.empty:
        return pd.DataFrame()

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
        if mkt not in {"outright", "top5", "top10", "top20", "top30", "make_cut", "miss_cut"}:
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
        book_prob = float(implied) if pd.notna(implied) and 0 < float(implied) < 1 else american_to_prob(odds)
        if pd.isna(book_prob):
            continue

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

        for player, model_p, book_p, odds, dec in [
            (pa, model_a, book_a, odds_a, dec_a),
            (pb, model_b, book_b, odds_b, dec_b),
        ]:
            edge_pts = (model_p - book_p) * 100.0
            ev_per_1 = (model_p * dec) - 1.0
            label = f"{player} to beat {pb if player == pa else pa}"
            if pd.notna(round_num):
                label += f" (R{int(round_num)})"
            rows.append({
                "bet_type": "single",
                "market": mkt_label,
                "player_name": player,
                "selection_label": label,
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

    for grp_key, grp in grp_lines.groupby(group_cols) if group_cols else [("all", grp_lines)]:
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
            label = f"{player} Group Winner"
            rows.append({
                "bet_type": "single",
                "market": "group_winner",
                "player_name": player,
                "selection_label": label,
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
    min_edge_points: float = 1.00
    min_ev_per_1: float = 0.00
    max_abs_odds: int = 10000
    max_per_market: int = 5
    top_n: int = 20
    top_n_cards: int = 8
    include_cards: bool = True
    include_partial_cards: bool = False


def apply_recommendation_filters(df: pd.DataFrame, cfg: RecommendationConfig) -> pd.DataFrame:
    if df.empty:
        return df

    work = df.copy()
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
        # h2h and group_winner have many more legs — allow more per market
        _h2h_mkts = singles["market"].astype(str).str.startswith("h2h") | \
                    (singles["market"].astype(str) == "group_winner")
        _cap = singles["market"].map(lambda m: 12 if str(m).startswith("h2h") or m == "group_winner"
                                     else cfg.max_per_market)
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


def build_recommendations(
    tournament_id: str,
    preds_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    cards_df: pd.DataFrame,
    cfg: RecommendationConfig,
) -> pd.DataFrame:
    single_df    = score_single_markets(preds_df, lines_df)
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

    run_id = now_utc_iso()
    rec_ts = run_id

    filtered = filtered.reset_index(drop=True)
    filtered["recommendation_rank"] = np.arange(1, len(filtered) + 1)
    filtered["tournament_id"] = tournament_id
    filtered["run_id"] = run_id
    filtered["recommended_at"] = rec_ts
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
        "status",
        "stake_units",
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
