#!/usr/bin/env python3
"""
Shared tournament context resolution and name-matching helpers.

Used by pipeline and scrapers to avoid duplicate schedule parsing logic and
to enforce consistent tournament matching across data sources.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

TOURNAMENT_STOPWORDS = {
    "the",
    "and",
    "at",
    "to",
    "of",
    "open",
    "championship",
    "classic",
    "invitational",
    "pro",
    "am",
    "tour",
    "tournament",
    "golf",
    "world",
    "presented",
    "by",
    "cup",
    "in",
    "on",
}


def _blank_context() -> Dict[str, str]:
    return {
        "tournament_id": "",
        "tournament_name": "",
        "power_slug": "",
        "start_date": "",
        "end_date": "",
        "year": "",
        "tournament_type": "",
        "purse": "",
        "schedule_file": "",
    }


def normalize_tournament_text(value: str) -> str:
    if not value:
        return ""
    s = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    return re.sub(r"\s+", " ", s)


def tournament_tokens(value: str) -> set[str]:
    text = normalize_tournament_text(value)
    if not text:
        return set()
    return {
        tok
        for tok in text.split()
        if tok and tok not in TOURNAMENT_STOPWORDS and len(tok) > 1
    }


def tournament_name_match(actual: str, expected: str) -> bool:
    """
    Token overlap check that is strict enough to block previous/next week
    mismatches while handling punctuation/branding differences.
    """
    at = tournament_tokens(actual)
    et = tournament_tokens(expected)
    if not at or not et:
        return False
    overlap = len(at.intersection(et))
    return overlap >= max(1, min(2, len(et)))


def _latest_schedule_path(explicit_path: Optional[Path] = None) -> Optional[Path]:
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        return None
    cands = sorted(RAW_DIR.glob("schedule_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _load_schedule_df(schedule_path: Optional[Path] = None) -> tuple[pd.DataFrame, Optional[Path]]:
    sp = _latest_schedule_path(schedule_path)
    if not sp:
        return pd.DataFrame(), None
    try:
        df = pd.read_csv(sp, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(), sp
    return df, sp


def _row_to_context(row: pd.Series, schedule_path: Optional[Path]) -> Dict[str, str]:
    ctx = _blank_context()
    ctx["tournament_id"] = str(row.get("tournament_id", "")).strip().upper()
    ctx["tournament_name"] = str(row.get("tournament_name", "")).strip()
    ctx["power_slug"] = str(row.get("power_slug", "")).strip()
    ctx["start_date"] = str(row.get("start_date", "")).strip()
    ctx["end_date"] = str(row.get("end_date", "")).strip()
    ctx["tournament_type"] = str(row.get("tournament_type", "")).strip()
    ctx["purse"] = str(row.get("purse", "")).strip()
    ctx["schedule_file"] = str(schedule_path) if schedule_path else ""

    if len(ctx["tournament_id"]) >= 5 and ctx["tournament_id"].startswith("R") and ctx["tournament_id"][1:5].isdigit():
        ctx["year"] = ctx["tournament_id"][1:5]
    elif ctx["start_date"]:
        ctx["year"] = ctx["start_date"][:4]
    return ctx


def resolve_tournament_context(
    tournament_id: str = "",
    tournament_name: str = "",
    on_date: str = "",
    schedule_path: Optional[Path] = None,
) -> Dict[str, str]:
    """
    Resolve a tournament context from schedule data.

    Priority:
    1) tournament_id exact match
    2) tournament_name exact/fuzzy match
    3) on_date -> in-progress else next upcoming
    """
    ctx = _blank_context()
    df, sp = _load_schedule_df(schedule_path)
    if df.empty:
        return ctx

    if "tournament_id" in df.columns:
        df["__tid"] = df["tournament_id"].astype(str).str.upper().str.strip()
    if "tournament_name" in df.columns:
        df["__tname_norm"] = df["tournament_name"].astype(str).apply(normalize_tournament_text)

    tid = str(tournament_id or "").strip().upper()
    if tid and "__tid" in df.columns:
        m = df[df["__tid"] == tid]
        if not m.empty:
            return _row_to_context(m.iloc[0], sp)

    tname = normalize_tournament_text(tournament_name or "")
    if tname and "__tname_norm" in df.columns:
        exact = df[df["__tname_norm"] == tname]
        if not exact.empty:
            return _row_to_context(exact.iloc[0], sp)

        scored = []
        for _, row in df.iterrows():
            cand = str(row.get("tournament_name", ""))
            if not cand:
                continue
            if tournament_name_match(cand, tournament_name):
                overlap = len(tournament_tokens(cand).intersection(tournament_tokens(tournament_name)))
                scored.append((overlap, row))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            return _row_to_context(scored[0][1], sp)

    dstr = str(on_date or "").strip()
    if dstr:
        try:
            d = pd.to_datetime(dstr).date()
            if "start_date" in df.columns and "end_date" in df.columns:
                work = df.copy()
                work["__start"] = pd.to_datetime(work["start_date"], errors="coerce").dt.date
                work["__end"] = pd.to_datetime(work["end_date"], errors="coerce").dt.date

                current = work[(work["__start"] <= d) & (work["__end"] >= d)]
                if not current.empty:
                    return _row_to_context(current.iloc[0], sp)

                upcoming = work[work["__start"] > d].sort_values("__start")
                if not upcoming.empty:
                    return _row_to_context(upcoming.iloc[0], sp)
        except Exception:
            pass

    return ctx


def context_matches_name(found_tournament_name: str, ctx: Dict[str, str]) -> bool:
    expected = str((ctx or {}).get("tournament_name", "")).strip()
    if not expected:
        return True
    return tournament_name_match(found_tournament_name, expected)


def context_summary(ctx: Dict[str, str]) -> str:
    tid = str((ctx or {}).get("tournament_id", "")).strip()
    name = str((ctx or {}).get("tournament_name", "")).strip()
    start = str((ctx or {}).get("start_date", "")).strip()
    if tid and name:
        return f"{name} ({tid})" + (f" start={start}" if start else "")
    if name:
        return name
    if tid:
        return tid
    return "unknown"

