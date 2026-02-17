#!/usr/bin/env python3
"""
DraftKings Prop Lines Scraper (Golf)
====================================

Builds sportsbook prop lines for dashboard edge scoring and saves:
    data/odds/prop_lines_<tournament_id>.csv

Supported markets:
- h2h
- round_score (Over/Under)
- birdies (Over/Under)

Usage:
    # Try live endpoints first
    python3 scripts/scrapers/fetch_draftkings_props.py --tournament-id R2026005

    # Parse local raw JSON files exported from DevTools/Network
    python3 scripts/scrapers/fetch_draftkings_props.py \
      --tournament-id R2026005 \
      --input-json data/odds/snapshots/dk_payload_*.json
"""

from __future__ import annotations
import argparse
import glob
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ODDS_DIR = PROJECT_ROOT / "data" / "odds"
SNAPSHOT_DIR = ODDS_DIR / "snapshots"

DEFAULT_EVENTGROUP_CANDIDATES = [
    "88807",
    "88808",
]

# Manual per-tournament overrides when DK rotates league/eventgroup ids.
# Extend this map as new IDs are verified.
TOURNAMENT_EVENTGROUP_OVERRIDES = {
    "R2026007": "89343",  # The Genesis Invitational
}

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
    "proam",
    "tour",
    "tournament",
    "golf",
    "world",
    "presented",
    "by",
    "cup",
    "memorial",
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _walk(obj: Any) -> Iterable[Dict[str, Any]]:
    """Yield every dict node recursively."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk(x)


def _flatten_dict_items(items: Any) -> List[Dict[str, Any]]:
    """Flatten possibly nested list structures into a list of dicts."""
    out: List[Dict[str, Any]] = []
    if isinstance(items, dict):
        out.append(items)
    elif isinstance(items, list):
        for it in items:
            out.extend(_flatten_dict_items(it))
    return out


def _decimal_to_american(decimal_odds: float) -> Optional[int]:
    if decimal_odds is None or decimal_odds <= 1:
        return None
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def _odds_to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if int(v) == 0:
            return None
        return int(v)

    s = str(v).strip()
    if not s:
        return None

    s = (
        s.replace("−", "-")
        .replace("–", "-")
        .replace("+", "")
        .replace(",", "")
        .strip()
    )

    m = re.search(r"-?\d+", s)
    if not m:
        return None

    try:
        out = int(m.group(0))
        return out if out != 0 else None
    except Exception:
        return None


def _extract_round_num(*texts: str) -> Optional[int]:
    blob = " ".join([t for t in texts if t]).lower()

    m = re.search(r"\br(?:ound)?\s*([1-4])\b", blob)
    if m:
        return int(m.group(1))

    m = re.search(r"\bround\s*([1-4])\b", blob)
    if m:
        return int(m.group(1))

    return None


def _extract_line(*texts: str, fallback: Any = None) -> Optional[float]:
    if fallback is not None:
        try:
            return float(fallback)
        except Exception:
            pass

    blob = " ".join([str(t) for t in texts if t])

    # Over 69.5 / Under 4.5 / O69.5 / U69.5
    m = re.search(r"(?:over|under|\b[oOuU]\b)\s*([0-9]+(?:\.[0-9]+)?)", blob, flags=re.I)
    if m:
        return float(m.group(1))

    # Generic decimal in market text if no explicit O/U token
    m = re.search(r"\b([0-9]{1,2}\.[05])\b", blob)
    if m:
        return float(m.group(1))

    return None


def _clean_player_name(name: str) -> str:
    if not name:
        return ""
    s = re.sub(r"\s+", " ", str(name)).strip()
    s = re.sub(r"\s*-\s*R[1-4]$", "", s, flags=re.I)
    return s.strip()


def _tokenize_tournament_text(text: str) -> List[str]:
    if not text:
        return []
    clean = re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()
    toks = [t for t in clean.split() if t]
    return [t for t in toks if t not in TOURNAMENT_STOPWORDS and len(t) > 1]


def _resolve_tournament_name_from_schedule(tournament_id: str) -> str:
    if not tournament_id:
        return ""

    schedule_files = sorted(RAW_DIR.glob("schedule_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    for sf in schedule_files:
        try:
            sdf = pd.read_csv(sf, dtype=str)
        except Exception:
            continue
        if "tournament_id" not in sdf.columns:
            continue
        match = sdf[sdf["tournament_id"].astype(str).str.upper() == str(tournament_id).upper()]
        if match.empty:
            continue
        if "tournament_name" in match.columns:
            name = str(match.iloc[0].get("tournament_name", "")).strip()
            if name:
                return name
    return ""


def _resolve_override_eventgroup_id(tournament_id: str) -> str:
    return TOURNAMENT_EVENTGROUP_OVERRIDES.get(str(tournament_id).upper(), "")


def _extract_payload_event_names(payload: Any) -> List[str]:
    names: List[str] = []
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            for e in events:
                if isinstance(e, dict) and e.get("name"):
                    names.append(str(e.get("name")))
    return names


def _payload_text_names(payloads: List[Any]) -> List[str]:
    names: List[str] = []
    for p in payloads:
        names.extend(_payload_sport_names(p))
        names.extend(_extract_payload_event_names(p))
    # ordered unique
    seen = set()
    out: List[str] = []
    for n in names:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


def _eventgroup_match_score(names: List[str], expected_tournament_name: str) -> float:
    if not names or not expected_tournament_name:
        return 0.0
    expected_tokens = set(_tokenize_tournament_text(expected_tournament_name))
    if not expected_tokens:
        return 0.0

    best = 0.0
    for n in names:
        ntoks = set(_tokenize_tournament_text(n))
        if not ntoks:
            continue
        overlap = len(expected_tokens.intersection(ntoks))
        if overlap <= 0:
            continue
        score = overlap / max(1, len(expected_tokens))
        # Small bonus for tighter match lengths.
        score += 0.05 * (overlap / max(1, len(ntoks)))
        best = max(best, score)
    return best


def _event_name_matches_expected(event_name: str, expected_tournament_name: str) -> bool:
    if not expected_tournament_name:
        return True
    etoks = set(_tokenize_tournament_text(expected_tournament_name))
    if not etoks:
        return True
    ntoks = set(_tokenize_tournament_text(event_name))
    if not ntoks:
        return False

    overlap = len(etoks.intersection(ntoks))
    return overlap >= max(1, min(2, len(etoks)))


def _extract_player_from_offer(offer_name: str, event_name: str, market_name: str) -> str:
    candidates = [offer_name or "", event_name or "", market_name or ""]

    patterns = [
        r"^(.*?)\s+round\s+score",
        r"^(.*?)\s+birdies?",
        r"^(.*?)\s+total\s+birdies?",
    ]

    for raw in candidates:
        txt = raw.strip()
        if not txt:
            continue
        for pat in patterns:
            m = re.search(pat, txt, flags=re.I)
            if m:
                return _clean_player_name(m.group(1))

    # Last resort: if event is "A v B ..." this is not a single-player prop
    return ""


def _classify_market(market_name: str, offer_name: str, event_name: str, outcomes: List[Dict[str, Any]]) -> Optional[str]:
    text = f"{market_name} {offer_name} {event_name}".lower()
    labels = " ".join([str(o.get("label", "")).lower() for o in outcomes])

    is_hole_market = "hole winner" in text or "winner of hole" in text
    if not is_hole_market:
        if (
            market_name.strip().lower() in {"winner", "outright"}
            or "tournament winner" in text
            or "event winner" in text
            or "to win" in text
        ):
            return "winner"

    if "round score" in text:
        return "round_score"
    if "birdie" in text:
        return "birdies"
    if any(k in text for k in ["head to head", "h2h", "matchup", "match-up", "to finish higher"]):
        return "h2h"

    # Fallback: two-player market with no O/U labels
    if len(outcomes) == 2 and " over " not in labels and " under " not in labels:
        if " v " in text or " vs " in text:
            return "h2h"

    return None


def _extract_event_map(payload: Any) -> Dict[str, str]:
    """Build eventId -> eventName map across mixed payload shapes."""
    events: Dict[str, str] = {}

    for node in _walk(payload):
        # Common shapes: {eventId, name} or {id, name}
        if "eventId" in node and ("name" in node or "eventName" in node):
            eid = str(node.get("eventId"))
            ename = str(node.get("name") or node.get("eventName") or "").strip()
            if eid and ename:
                events[eid] = ename

        if "id" in node and ("name" in node or "eventName" in node):
            # Keep only plausible numeric event IDs
            sid = str(node.get("id"))
            if sid.isdigit() and len(sid) >= 6:
                ename = str(node.get("name") or node.get("eventName") or "").strip()
                if ename:
                    events[sid] = ename

    return events


def _parse_offer_node(node: Dict[str, Any], event_map: Dict[str, str], fetched_at: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    outcomes = _flatten_dict_items(node.get("outcomes"))
    if len(outcomes) < 2:
        return rows

    parsed_outcomes: List[Dict[str, Any]] = []
    for o in outcomes:
        odds = _odds_to_int(
            o.get("oddsAmerican")
            if o.get("oddsAmerican") is not None
            else o.get("displayOdds", o.get("americanOdds", o.get("odds", o.get("price"))))
        )
        if odds is None:
            dec = o.get("trueOdds", o.get("decimalOdds"))
            try:
                odds = _decimal_to_american(float(dec)) if dec is not None else None
            except Exception:
                odds = None
        if odds is None:
            continue

        label = str(
            o.get("label")
            or o.get("name")
            or o.get("outcomeName")
            or o.get("participant")
            or o.get("selectionName")
            or ""
        ).strip()
        if not label:
            continue

        parsed_outcomes.append(
            {
                "label": label,
                "odds": odds,
                "selection_id": o.get("id", o.get("selectionId", o.get("outcomeId"))),
                "line": o.get("line", o.get("points", o.get("total", o.get("handicap")))),
            }
        )

    if len(parsed_outcomes) < 2:
        return rows

    market_name = str(node.get("marketName") or node.get("criterionName") or node.get("name") or "").strip()
    offer_name = str(node.get("label") or node.get("name") or "").strip()

    event_id = node.get("eventId")
    event_name = ""
    if event_id is not None:
        event_name = event_map.get(str(event_id), "")
    if not event_name:
        event_name = str(node.get("eventName") or "").strip()

    market_type = _classify_market(market_name, offer_name, event_name, parsed_outcomes)
    if not market_type:
        # Heuristic fallback based on O/U labels + extracted line.
        labels_blob = " ".join([x["label"] for x in parsed_outcomes]).lower()
        has_ou = "over" in labels_blob and "under" in labels_blob
        line_guess = _extract_line(offer_name, market_name, event_name)
        if has_ou and line_guess is not None:
            market_type = "birdies" if line_guess <= 12 else "round_score"
    if not market_type:
        return rows

    round_num = _extract_round_num(market_name, offer_name, event_name)

    if market_type == "winner":
        for o in parsed_outcomes:
            player_name = _clean_player_name(o["label"])
            if not player_name:
                continue
            rows.append(
                {
                    "market": "winner",
                    "player_name": player_name,
                    "odds": o["odds"],
                    "book": "DRAFTKINGS",
                    "line_source": "draftkings_api",
                    "event_name": event_name,
                    "market_name": market_name or offer_name,
                    "selection_id": o.get("selection_id"),
                    "fetched_at": fetched_at,
                }
            )
        return rows

    if market_type == "h2h":
        a, b = parsed_outcomes[0], parsed_outcomes[1]
        rows.append(
            {
                "market": "h2h",
                "player_a": _clean_player_name(a["label"]),
                "player_b": _clean_player_name(b["label"]),
                "odds_a": a["odds"],
                "odds_b": b["odds"],
                "book": "DRAFTKINGS",
                "line_source": "draftkings_api",
                "event_name": event_name,
                "market_name": market_name or offer_name,
                "round_num": round_num,
                "fetched_at": fetched_at,
            }
        )
        return rows

    over = None
    under = None
    for o in parsed_outcomes:
        ll = o["label"].lower()
        if ll.startswith("over") or re.search(r"\bover\b", ll):
            over = o
        elif ll.startswith("under") or re.search(r"\bunder\b", ll):
            under = o

    if not over or not under:
        return rows

    line_val = _extract_line(
        over.get("label"),
        under.get("label"),
        offer_name,
        market_name,
        event_name,
        fallback=over.get("line") if over.get("line") is not None else under.get("line"),
    )

    player_name = _extract_player_from_offer(offer_name, event_name, market_name)
    if not player_name:
        # If we cannot derive a player name, skip this market for edge-scoring compatibility.
        return rows

    rows.append(
        {
            "market": market_type,
            "player_name": player_name,
            "line": line_val,
            "over_odds": over["odds"],
            "under_odds": under["odds"],
            "round_num": round_num,
            "book": "DRAFTKINGS",
            "line_source": "draftkings_api",
            "event_name": event_name,
            "market_name": market_name or offer_name,
            "selection_id_over": over.get("selection_id"),
            "selection_id_under": under.get("selection_id"),
            "fetched_at": fetched_at,
        }
    )
    return rows


def _parse_markets_selections_payload(payload: Any, fetched_at: str) -> List[Dict[str, Any]]:
    """
    Parse DraftKings v5-ish payload shape:
      {events:[], markets:[], selections:[], categories:[], subcategories:[]}
    """
    if not isinstance(payload, dict):
        return []

    markets = payload.get("markets")
    selections = payload.get("selections")
    events = payload.get("events")
    subcategories = payload.get("subcategories")
    categories = payload.get("categories")

    if not isinstance(markets, list) or not isinstance(selections, list):
        return []

    event_name_by_id: Dict[str, str] = {}
    if isinstance(events, list):
        for e in events:
            if isinstance(e, dict) and e.get("id") and e.get("name"):
                event_name_by_id[str(e["id"])] = str(e["name"])

    subcat_name_by_id: Dict[str, str] = {}
    subcat_category_by_id: Dict[str, str] = {}
    if isinstance(subcategories, list):
        for s in subcategories:
            if isinstance(s, dict) and s.get("id") is not None:
                sid = str(s["id"])
                if s.get("name"):
                    subcat_name_by_id[sid] = str(s["name"])
                if s.get("categoryId") is not None:
                    subcat_category_by_id[sid] = str(s["categoryId"])

    cat_name_by_id: Dict[str, str] = {}
    if isinstance(categories, list):
        for c in categories:
            if isinstance(c, dict) and c.get("id") is not None and c.get("name"):
                cat_name_by_id[str(c["id"])] = str(c["name"])

    # group selections by marketId
    selections_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for s in selections:
        if not isinstance(s, dict):
            continue
        mid = s.get("marketId")
        if mid is None:
            continue
        selections_by_market.setdefault(str(mid), []).append(s)

    rows: List[Dict[str, Any]] = []

    for m in markets:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if mid is None:
            continue
        skeys = selections_by_market.get(str(mid), [])
        if len(skeys) < 2:
            continue

        parsed_outcomes: List[Dict[str, Any]] = []
        for s in skeys:
            display_odds = s.get("displayOdds")
            display_american = None
            if isinstance(display_odds, dict):
                display_american = display_odds.get("american")
            elif isinstance(display_odds, str):
                display_american = display_odds

            odds = _odds_to_int(
                s.get("oddsAmerican")
                if s.get("oddsAmerican") is not None
                else s.get("americanOdds", display_american)
            )
            if odds is None:
                try:
                    odds = _decimal_to_american(float(s.get("trueOdds"))) if s.get("trueOdds") is not None else None
                except Exception:
                    odds = None
            if odds is None:
                continue

            label = str(
                s.get("label")
                or s.get("name")
                or s.get("outcomeName")
                or s.get("selectionName")
                or ""
            ).strip()
            if not label and isinstance(s.get("participants"), list) and s["participants"]:
                p0 = s["participants"][0]
                if isinstance(p0, dict) and p0.get("name"):
                    label = str(p0["name"]).strip()
            if not label:
                continue

            parsed_outcomes.append(
                {
                    "label": label,
                    "odds": odds,
                    "selection_id": s.get("id"),
                    "line": s.get("line", s.get("points")),
                }
            )

        if len(parsed_outcomes) < 2:
            continue

        market_name = str(m.get("name") or "").strip()
        market_type_name = ""
        if isinstance(m.get("marketType"), dict):
            market_type_name = str(m["marketType"].get("name") or "").strip()

        subcat_id = m.get("subcategoryId")
        subcat_name = subcat_name_by_id.get(str(subcat_id), "") if subcat_id is not None else ""
        cat_name = ""
        if subcat_id is not None:
            cat_name = cat_name_by_id.get(subcat_category_by_id.get(str(subcat_id), ""), "")

        event_name = event_name_by_id.get(str(m.get("eventId")), "")
        offer_name = " | ".join([x for x in [cat_name, subcat_name, market_name, market_type_name] if x]).strip()

        market_type = _classify_market(market_name, offer_name, event_name, parsed_outcomes)
        if not market_type:
            labels_blob = " ".join([x["label"] for x in parsed_outcomes]).lower()
            has_ou = "over" in labels_blob and "under" in labels_blob
            line_guess = _extract_line(offer_name, market_name, event_name)
            if has_ou and line_guess is not None:
                market_type = "birdies" if line_guess <= 12 else "round_score"
        if not market_type:
            continue

        round_num = _extract_round_num(market_name, offer_name, event_name)

        if market_type == "winner":
            for o in parsed_outcomes:
                player_name = _clean_player_name(o["label"])
                if not player_name:
                    continue
                rows.append(
                    {
                        "market": "winner",
                        "player_name": player_name,
                        "odds": o["odds"],
                        "book": "DRAFTKINGS",
                        "line_source": "draftkings_api",
                        "event_name": event_name,
                        "market_name": offer_name or market_name,
                        "selection_id": o.get("selection_id"),
                        "fetched_at": fetched_at,
                    }
                )
            continue

        if market_type == "h2h":
            a, b = parsed_outcomes[0], parsed_outcomes[1]
            rows.append(
                {
                    "market": "h2h",
                    "player_a": _clean_player_name(a["label"]),
                    "player_b": _clean_player_name(b["label"]),
                    "odds_a": a["odds"],
                    "odds_b": b["odds"],
                    "book": "DRAFTKINGS",
                    "line_source": "draftkings_api",
                    "event_name": event_name,
                    "market_name": offer_name or market_name,
                    "round_num": round_num,
                    "fetched_at": fetched_at,
                }
            )
            continue

        over = None
        under = None
        for o in parsed_outcomes:
            ll = o["label"].lower()
            if ll.startswith("over") or re.search(r"\bover\b", ll):
                over = o
            elif ll.startswith("under") or re.search(r"\bunder\b", ll):
                under = o
        if not over or not under:
            continue

        line_val = _extract_line(
            over.get("label"),
            under.get("label"),
            offer_name,
            market_name,
            event_name,
            fallback=over.get("line") if over.get("line") is not None else under.get("line"),
        )
        player_name = _extract_player_from_offer(offer_name, event_name, market_name)
        if not player_name:
            continue

        rows.append(
            {
                "market": market_type,
                "player_name": player_name,
                "line": line_val,
                "over_odds": over["odds"],
                "under_odds": under["odds"],
                "round_num": round_num,
                "book": "DRAFTKINGS",
                "line_source": "draftkings_api",
                "event_name": event_name,
                "market_name": offer_name or market_name,
                "selection_id_over": over.get("selection_id"),
                "selection_id_under": under.get("selection_id"),
                "fetched_at": fetched_at,
            }
        )

    return rows


def parse_draftkings_payloads(payloads: List[Any], fetched_at: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for payload in payloads:
        event_map = _extract_event_map(payload)
        for node in _walk(payload):
            # only nodes with outcome lists are potentially useful offers
            if isinstance(node.get("outcomes"), list):
                rows.extend(_parse_offer_node(node, event_map=event_map, fetched_at=fetched_at))
        # Parse alternate DK shape where markets+selections are top-level.
        rows.extend(_parse_markets_selections_payload(payload, fetched_at=fetched_at))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Normalize required schema columns so downstream scoring can safely consume.
    required_cols = [
        "market",
        "player_a",
        "player_b",
        "odds_a",
        "odds_b",
        "odds",
        "player_name",
        "line",
        "over_odds",
        "under_odds",
        "round_num",
        "book",
        "line_source",
        "event_name",
        "market_name",
        "selection_id",
        "fetched_at",
    ]
    for c in required_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # Clean numeric columns.
    for c in ["odds_a", "odds_b", "odds", "over_odds", "under_odds", "round_num"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["line"] = pd.to_numeric(df["line"], errors="coerce")

    # Drop clearly invalid rows.
    keep = (
        (df["market"].eq("winner") & df["player_name"].notna() & df["odds"].notna())
        |
        (df["market"].eq("h2h") & df["player_a"].notna() & df["player_b"].notna() & df["odds_a"].notna() & df["odds_b"].notna())
        |
        (df["market"].isin(["round_score", "birdies"]) & df["player_name"].notna() & df["over_odds"].notna() & df["under_odds"].notna())
    )
    df = df[keep].copy()

    if df.empty:
        return df

    # Deduplicate across multiple endpoint payloads.
    dedupe_cols = ["market", "player_a", "player_b", "player_name", "line", "over_odds", "under_odds", "odds", "odds_a", "odds_b", "round_num"]
    dedupe_cols = [c for c in dedupe_cols if c in df.columns]
    df = df.drop_duplicates(subset=dedupe_cols, keep="first")

    # Stable ordering for CSV readability.
    sort_cols = [c for c in ["market", "round_num", "player_name", "player_a"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, na_position="last")

    return df.reset_index(drop=True)


def _fetch_json(url: str, headers: Dict[str, str], timeout: int = 20) -> Optional[Any]:
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _fetch_text(url: str, headers: Dict[str, str], timeout: int = 20) -> Optional[str]:
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def _extract_eventgroup_ids_from_text(text: str) -> List[str]:
    ids = []
    patterns = [
        r"eventgroups?/(\d{4,})",
        r"eventGroupId\"?\s*:\s*\"?(\d{4,})",
        r"leagueId\"?\s*:\s*\"?(\d{4,})",
        r"L(\d{4,})Q",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            ids.append(m.group(1))
    # Keep order, remove duplicates.
    out = []
    seen = set()
    for x in ids:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _payload_sport_names(payload: Any) -> List[str]:
    names: List[str] = []

    if isinstance(payload, dict):
        sports = payload.get("sports")
        leagues = payload.get("leagues")
        if isinstance(sports, list):
            for s in sports:
                if isinstance(s, dict) and s.get("name"):
                    names.append(str(s.get("name")))
        if isinstance(leagues, list):
            for l in leagues:
                if isinstance(l, dict) and l.get("name"):
                    names.append(str(l.get("name")))

    return names


def _payload_looks_golf(payload: Any) -> bool:
    tokens = " ".join(_payload_sport_names(payload)).lower()
    if not tokens:
        # If sport metadata is absent, treat as unknown (not explicitly non-golf).
        return False
    if "golf" in tokens or "pga" in tokens or "dp world" in tokens or "lpga" in tokens:
        return True
    return False


def _discover_candidate_eventgroup_ids(headers: Dict[str, str]) -> List[str]:
    candidates: List[str] = []

    # Try pulling IDs from public golf pages first.
    discovery_urls = [
        "https://sportsbook.draftkings.com/leagues/golf",
        "https://sportsbook.draftkings.com/sports/golf",
    ]

    for url in discovery_urls:
        html = _fetch_text(url, headers=headers, timeout=20)
        if html:
            candidates.extend(_extract_eventgroup_ids_from_text(html))

    candidates.extend(DEFAULT_EVENTGROUP_CANDIDATES)

    # Keep ordered unique.
    out = []
    seen = set()
    for c in candidates:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _expand_eventgroup_payloads_with_subcategories(
    payloads: List[Any],
    eventgroup_id: str,
    headers: Dict[str, str],
    max_subcategories: int = 40,
    max_categories: int = 20,
) -> List[Any]:
    """Fetch subcategory/category payloads for a chosen eventgroup."""
    out_payloads = list(payloads)
    if not out_payloads:
        return out_payloads

    subcategory_ids = set()
    category_ids = set()
    for p in out_payloads:
        for node in _walk(p):
            sid = node.get("subcategoryId")
            cid = node.get("categoryId")
            if sid is not None:
                subcategory_ids.add(str(sid))
            if cid is not None:
                category_ids.add(str(cid))

            # Sometimes descriptors carry explicit IDs.
            if isinstance(node.get("offerSubcategoryDescriptors"), list):
                for d in _flatten_dict_items(node.get("offerSubcategoryDescriptors")):
                    if "subcategoryId" in d:
                        subcategory_ids.add(str(d["subcategoryId"]))

    for sid in sorted(subcategory_ids)[:max_subcategories]:
        u = f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/subcategories/{sid}?format=json"
        js = _fetch_json(u, headers=headers)
        if js is not None:
            out_payloads.append(js)

    for cid in sorted(category_ids)[:max_categories]:
        u = f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/categories/{cid}?format=json"
        js = _fetch_json(u, headers=headers)
        if js is not None:
            out_payloads.append(js)

    return out_payloads


def _fetch_live_dk_payloads_for_eventgroup(
    region: str,
    eventgroup_id: str,
    headers: Dict[str, str],
    include_subcategories: bool = True,
) -> List[Any]:
    urls = [
        f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/leagues/{eventgroup_id}",
        f"https://sportsbook.draftkings.com/api/odds/v1/leagues/{eventgroup_id}/offers/gamelines",
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}?format=json",
    ]

    payloads: List[Any] = []
    for u in urls:
        js = _fetch_json(u, headers=headers)
        if js is not None:
            payloads.append(js)

    if include_subcategories:
        payloads = _expand_eventgroup_payloads_with_subcategories(
            payloads=payloads,
            eventgroup_id=eventgroup_id,
            headers=headers,
            max_subcategories=40,
            max_categories=20,
        )

    return payloads


def fetch_live_dk_payloads(
    region: str = "dkusnj",
    eventgroup_id: Optional[str] = None,
    expected_tournament_name: str = "",
    tournament_id: str = "",
) -> Tuple[List[Any], Optional[str], List[str]]:
    """
    Try multiple DraftKings golf endpoints.
    Some endpoints can be region-dependent and may change over time.
    """
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    if eventgroup_id:
        candidates = [eventgroup_id]
    else:
        candidates = _discover_candidate_eventgroup_ids(headers)
        override_id = _resolve_override_eventgroup_id(tournament_id)
        if override_id:
            candidates = [override_id] + candidates

    if not candidates:
        candidates = DEFAULT_EVENTGROUP_CANDIDATES[:]

    # Try each eventgroup and pick the best golf match.
    fallback_payloads: List[Any] = []
    fallback_id: Optional[str] = None
    fallback_names: List[str] = []
    golf_candidates: List[Dict[str, Any]] = []

    for egid in candidates:
        base_payloads = _fetch_live_dk_payloads_for_eventgroup(
            region=region,
            eventgroup_id=str(egid),
            headers=headers,
            include_subcategories=False,
        )
        if not base_payloads:
            continue

        names = _payload_text_names(base_payloads)
        names_blob = " ".join(names).lower()
        looks_golf = any(_payload_looks_golf(p) for p in base_payloads) or ("golf" in names_blob)
        score = _eventgroup_match_score(names, expected_tournament_name)
        is_lpga = "lpga" in names_blob
        is_pga = ("pga" in names_blob) and not is_lpga

        if looks_golf:
            golf_candidates.append(
                {
                    "payloads": base_payloads,
                    "eventgroup_id": str(egid),
                    "names": names,
                    "score": score,
                    "is_lpga": is_lpga,
                    "is_pga": is_pga,
                }
            )

        if not fallback_payloads:
            fallback_payloads = base_payloads
            fallback_id = str(egid)
            fallback_names = names

    if golf_candidates:
        # Prefer explicit expected tournament name matches.
        if expected_tournament_name:
            matched = [c for c in golf_candidates if c["score"] > 0]
            if matched:
                matched.sort(key=lambda c: (c["score"], int(not c["is_lpga"]), int(c["is_pga"])), reverse=True)
                best = matched[0]
                full_payloads = _expand_eventgroup_payloads_with_subcategories(
                    payloads=best["payloads"],
                    eventgroup_id=best["eventgroup_id"],
                    headers=headers,
                )
                return full_payloads, best["eventgroup_id"], best["names"]
            # No name match at all: do not silently choose a wrong tournament.
            return [], None, []

        # Fallback: prefer non-LPGA when no direct name match found.
        non_lpga = [c for c in golf_candidates if not c["is_lpga"]]
        pool = non_lpga if non_lpga else golf_candidates
        best = pool[0]
        full_payloads = _expand_eventgroup_payloads_with_subcategories(
            payloads=best["payloads"],
            eventgroup_id=best["eventgroup_id"],
            headers=headers,
        )
        return full_payloads, best["eventgroup_id"], best["names"]

    if fallback_payloads and fallback_id:
        fallback_payloads = _expand_eventgroup_payloads_with_subcategories(
            payloads=fallback_payloads,
            eventgroup_id=fallback_id,
            headers=headers,
        )

    return fallback_payloads, fallback_id, fallback_names


def load_input_payloads(patterns: List[str]) -> List[Any]:
    payloads: List[Any] = []
    for pat in patterns:
        if Path(pat).is_absolute():
            match_paths = sorted(Path(x) for x in glob.glob(pat))
        else:
            match_paths = sorted(Path(x) for x in glob.glob(str(PROJECT_ROOT / pat)))
        for p in match_paths:
            if not p.exists() or p.is_dir():
                continue
            try:
                raw = json.loads(p.read_text())
                if isinstance(raw, list):
                    payloads.extend(raw)
                else:
                    payloads.append(raw)
            except Exception:
                continue
    return payloads


def save_snapshot(payloads: List[Any], tournament_id: str) -> Optional[Path]:
    if not payloads:
        return None
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = SNAPSHOT_DIR / f"draftkings_props_{tournament_id}_{ts}.json"
    out.write_text(json.dumps(payloads, indent=2))
    return out


def clean_prop_lines_for_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and transform prop lines for dashboard integration.

    - Separates 'winner' market into: outright, top5, top10, top20
    - Cleans market_name to be concise
    - Adds implied_prob from odds
    - Removes unnecessary columns
    """
    if df.empty:
        return df

    df = df.copy()

    # Classify winner sub-markets based on market_name
    def classify_winner_market(row):
        if row.get("market") != "winner":
            return row.get("market")

        mname = str(row.get("market_name", "")).lower()

        if "top 20" in mname:
            return "top20"
        elif "top 10" in mname:
            return "top10"
        elif "top 5" in mname:
            return "top5"
        elif "winner" in mname or "outright" in mname:
            return "outright"
        else:
            return "outright"  # default

    df["market"] = df.apply(classify_winner_market, axis=1)

    # Clean market_name to be concise
    def clean_market_name(mname: str) -> str:
        if pd.isna(mname):
            return ""
        s = str(mname)
        # Remove common prefixes
        s = re.sub(r"^Tournament Lines\s*\|\s*", "", s)
        s = re.sub(r"^Tournament Winner\s*\|\s*", "", s)
        # Collapse multiple pipes
        s = re.sub(r"\s*\|\s*", " | ", s)
        # Remove duplicate segments
        parts = [p.strip() for p in s.split("|")]
        seen = set()
        unique_parts = []
        for p in parts:
            if p.lower() not in seen:
                unique_parts.append(p)
                seen.add(p.lower())
        return " | ".join(unique_parts).strip()

    df["market_name"] = df["market_name"].apply(clean_market_name)

    # Add implied probability from American odds
    def odds_to_implied_prob(odds):
        if pd.isna(odds) or odds == 0:
            return None
        odds = float(odds)
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    df["implied_prob"] = df["odds"].apply(odds_to_implied_prob)

    # Clean up player names - remove any trailing whitespace
    if "player_name" in df.columns:
        df["player_name"] = df["player_name"].str.strip()

    # Select and reorder columns for cleaner output
    output_cols = [
        "market", "player_name", "odds", "implied_prob", "book",
        "player_a", "player_b", "odds_a", "odds_b",
        "line", "over_odds", "under_odds", "round_num",
        "event_name", "market_name", "fetched_at"
    ]
    output_cols = [c for c in output_cols if c in df.columns]
    df = df[output_cols]

    # Sort for readability
    sort_cols = ["market", "player_name", "odds"]
    sort_cols = [c for c in sort_cols if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, na_position="last")

    return df.reset_index(drop=True)


def debug_payload_summary(payloads: List[Any]) -> None:
    print("\nDebug summary:")
    print(f"  payload_count: {len(payloads)}")
    key_counter: Counter[str] = Counter()
    outcomes_nodes = 0
    market_selection_payloads = 0
    total_markets = 0
    total_selections = 0
    sample_rows: List[Tuple[str, str, str, int]] = []

    for p in payloads:
        if isinstance(p, dict) and isinstance(p.get("markets"), list) and isinstance(p.get("selections"), list):
            market_selection_payloads += 1
            total_markets += len(p.get("markets", []))
            total_selections += len(p.get("selections", []))
        for node in _walk(p):
            key_counter.update(node.keys())
            if "outcomes" in node:
                outcomes = _flatten_dict_items(node.get("outcomes"))
                if outcomes:
                    outcomes_nodes += 1
                    market_name = str(node.get("marketName") or node.get("criterionName") or node.get("name") or "")
                    offer_name = str(node.get("label") or node.get("name") or "")
                    event_name = str(node.get("eventName") or node.get("event", ""))
                    sample_rows.append((market_name, offer_name, event_name, len(outcomes)))

    print("  top_keys:", ", ".join([f"{k}:{v}" for k, v in key_counter.most_common(15)]))
    print(f"  outcomes_nodes: {outcomes_nodes}")
    print(f"  market_selection_payloads: {market_selection_payloads}")
    if market_selection_payloads:
        print(f"  total_markets: {total_markets} | total_selections: {total_selections}")
    for i, (mkt, off, evt, nout) in enumerate(sample_rows[:8], start=1):
        print(f"  sample_{i}: outcomes={nout} | market='{mkt[:60]}' | offer='{off[:60]}' | event='{evt[:60]}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch DraftKings prop lines for golf")
    parser.add_argument("--tournament-id", required=True, help="Tournament ID, e.g. R2026005")
    parser.add_argument(
        "--input-json",
        nargs="*",
        default=[],
        help=(
            "Optional JSON files/globs to parse (workspace-relative globs supported). "
            "If omitted, scraper tries live DraftKings endpoints first."
        ),
    )
    parser.add_argument("--region", default="dkusnj", help="DraftKings region key used in sportsbook-nash URL")
    parser.add_argument("--eventgroup-id", help="Optional DraftKings event group id override for golf")
    parser.add_argument("--output", help="Custom output CSV path")
    parser.add_argument("--no-snapshot", action="store_true", help="Disable saving raw payload snapshots")
    parser.add_argument("--debug", action="store_true", help="Print payload structure summary")
    args = parser.parse_args()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    payloads: List[Any] = []
    expected_tournament_name = _resolve_tournament_name_from_schedule(args.tournament_id)
    if expected_tournament_name:
        print(f"Expected tournament for {args.tournament_id}: {expected_tournament_name}")

    if args.input_json:
        payloads.extend(load_input_payloads(args.input_json))

    if not payloads:
        print("Trying live DraftKings endpoints...")
        payloads, chosen_eventgroup, detected_names = fetch_live_dk_payloads(
            region=args.region,
            eventgroup_id=args.eventgroup_id,
            expected_tournament_name=expected_tournament_name,
            tournament_id=args.tournament_id,
        )
        if chosen_eventgroup:
            print(f"Using eventgroup id: {chosen_eventgroup}")
        if detected_names:
            print(f"Detected sport/league names: {', '.join(detected_names[:6])}")

    if not payloads:
        print("No DraftKings payloads loaded.")
        print("Tip: export JSON responses from browser DevTools and rerun with --input-json.")
        return

    # Guardrail: hard fail if payload clearly isn't golf.
    looks_golf = any(_payload_looks_golf(p) for p in payloads)
    if not args.input_json and not looks_golf:
        print("Loaded DraftKings payloads, but detected non-golf sport data.")
        print("Try setting --eventgroup-id explicitly (example from your token patterns is often 88807).")
        print("Example:")
        print("  python3 scripts/scrapers/fetch_draftkings_props.py --tournament-id R2026005 --eventgroup-id 88807 --debug")
        return

    snapshot_path = None
    if not args.no_snapshot:
        snapshot_path = save_snapshot(payloads, tournament_id=args.tournament_id)
        print(f"Saved raw payload snapshot to: {snapshot_path}")

    if args.debug:
        debug_payload_summary(payloads)

    fetched_at = _now_utc_iso()
    df = parse_draftkings_payloads(payloads, fetched_at=fetched_at)

    if not df.empty and expected_tournament_name and "event_name" in df.columns:
        event_names = df["event_name"].fillna("").astype(str).str.strip()
        non_empty = event_names[event_names != ""]
        if not non_empty.empty:
            explicit_match_mask = event_names.apply(lambda x: _event_name_matches_expected(x, expected_tournament_name) if x else False)
            keep_mask = event_names.eq("") | explicit_match_mask
            matched_df = df[keep_mask].copy()
            if not explicit_match_mask.any():
                observed = sorted(set(non_empty.unique().tolist()))
                print("Loaded DraftKings payloads, but events do not match expected tournament.")
                print(f"Expected: {expected_tournament_name}")
                print(f"Observed events: {', '.join(observed[:6])}")
                print("Tip: rerun with --eventgroup-id for the PGA tournament eventgroup.")
                return
            df = matched_df

    if df.empty:
        print("Loaded payloads but could not parse supported markets (winner / h2h / round_score / birdies).")
        print("Likely cause: payloads are quote-only or market metadata keys differ.")
        if snapshot_path:
            print(f"Inspect this snapshot and share one object with full market+outcomes: {snapshot_path}")
        return

    # Clean and transform for dashboard integration
    df = clean_prop_lines_for_dashboard(df)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = ODDS_DIR / f"prop_lines_{args.tournament_id}.csv"

    df.to_csv(out_path, index=False)

    print(f"Saved {len(df)} prop lines to: {out_path}")

    by_market = df["market"].value_counts().to_dict()
    print("Parsed markets:")
    for m, n in by_market.items():
        print(f"  {m}: {n}")


if __name__ == "__main__":
    main()
