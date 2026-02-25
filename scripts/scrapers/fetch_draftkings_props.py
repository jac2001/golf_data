#!/usr/bin/env python3
"""
DraftKings Prop Lines Scraper (Golf)
====================================

Builds sportsbook prop lines for dashboard edge scoring and saves:
    data/odds/prop_lines_<tournament_id>.csv
    data/odds/dk_content_cards_<tournament_id>.csv

Supported markets:
- h2h
- round_score (Over/Under)
- birdies (Over/Under)
- bogeys (Over/Under)
- make_cut (Yes/No)
- preset content cards / prebuilt parlays

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from scripts.utils.tournament_context import resolve_tournament_context

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

# Auto-persisted cache — written after successful discovery so subsequent
# runs for the same tournament skip the slow DK page scrape entirely.
_EG_CACHE_PATH = PROJECT_ROOT / "data" / "odds" / ".dk_eventgroup_cache.json"


def _load_eg_cache() -> dict:
    try:
        if _EG_CACHE_PATH.exists():
            return json.load(_EG_CACHE_PATH.open())
    except Exception:
        pass
    return {}


def _save_eg_cache(tournament_id: str, eventgroup_id: str) -> None:
    try:
        cache = _load_eg_cache()
        cache[str(tournament_id).upper()] = str(eventgroup_id)
        _EG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _EG_CACHE_PATH.open("w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

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
    ctx = resolve_tournament_context(tournament_id=str(tournament_id or ""))
    return str(ctx.get("tournament_name", "")).strip()


def _resolve_tournament_start_date_from_schedule(tournament_id: str) -> str:
    ctx = resolve_tournament_context(tournament_id=str(tournament_id or ""))
    return str(ctx.get("start_date", "")).strip()


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
        r"^(.*?)\s+bogeys?",
        r"^(.*?)\s+to\s+make\s+the?\s*cut",
        r"^(.*?)\s+to\s+make\s+cut",
        r"^(.*?)\s+to\s+miss\s+the?\s*cut",
        r"^(.*?)\s+to\s+miss\s+cut",
        r"^(.*?)\s+total\s+birdies?",
        r"^(.*?)\s+total\s+bogeys?",
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


def _extract_player_from_cut_labels(outcomes: List[Dict[str, Any]], offer_name: str, event_name: str, market_name: str) -> str:
    """
    Extract player name for make_cut markets.
    Handles labels like:
      - "Scottie Scheffler to Make the Cut"
      - "Scottie Scheffler - Yes"
      - "Yes"/"No" with player in offer name
    """
    patterns = [
        r"^(.*?)\s+to\s+make\s+the?\s*cut",
        r"^(.*?)\s+to\s+miss\s+the?\s*cut",
        r"^(.*?)\s*-\s*(?:yes|no)$",
    ]
    for o in outcomes:
        label = str(o.get("label", "")).strip()
        if not label:
            continue
        for pat in patterns:
            m = re.search(pat, label, flags=re.I)
            if m:
                name = _clean_player_name(m.group(1))
                if name:
                    return name

    return _extract_player_from_offer(offer_name, event_name, market_name)


def _infer_cut_side(label: str, offer_name: str, market_name: str) -> str:
    """
    Infer one-way cut market side from label/context.
    Returns:
      - "make_cut" for make/yes
      - "miss_cut" for miss/no
    """
    label_txt = str(label or "").strip().lower()
    if "miss cut" in label_txt or "miss the cut" in label_txt:
        return "miss_cut"
    if "make cut" in label_txt or "make the cut" in label_txt:
        return "make_cut"
    if " no" in f" {label_txt}" or label_txt == "no":
        return "miss_cut"
    if " yes" in f" {label_txt}" or label_txt == "yes":
        return "make_cut"

    ctx = f"{offer_name} {market_name}".lower()
    if ("miss cut" in ctx or "miss the cut" in ctx) and ("make cut" not in ctx and "make the cut" not in ctx):
        return "miss_cut"
    return "make_cut"


def _parse_one_way_cut_rows(
    parsed_outcomes: List[Dict[str, Any]],
    offer_name: str,
    event_name: str,
    market_name: str,
    round_num: Optional[int],
    fetched_at: str,
) -> List[Dict[str, Any]]:
    """
    Parse one-sided cut selections, e.g. "Player to Make the Cut" with no paired No price.
    """
    rows: List[Dict[str, Any]] = []
    for o in parsed_outcomes:
        label = str(o.get("label", "")).strip()
        if not label:
            continue
        player_name = _extract_player_from_cut_labels([o], offer_name, event_name, market_name)
        if not player_name:
            continue

        market = _infer_cut_side(label, offer_name, market_name)
        rows.append(
            {
                "market": market,
                "player_name": player_name,
                "line": 1.0,
                "odds": o["odds"],
                "round_num": round_num,
                "book": "DRAFTKINGS",
                "line_source": "draftkings_api",
                "event_name": event_name,
                "market_name": market_name or offer_name,
                "selection_id": o.get("selection_id"),
                "fetched_at": fetched_at,
            }
        )

    return rows


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

    if any(k in text for k in ["group winner", "tournament groups", "group_winner"]):
        return "group_winner"
    if "round score" in text:
        return "round_score"
    if "birdie" in text:
        return "birdies"
    if "bogey" in text:
        return "bogeys"
    if any(k in text for k in ["make the cut", "to make cut", "to make the cut", "miss the cut", "cut market"]):
        return "make_cut"
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
    if len(outcomes) < 1:
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

    if len(parsed_outcomes) < 1:
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
        if len(parsed_outcomes) < 2:
            return rows
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

    if market_type == "make_cut":
        yes = None
        no = None
        for o in parsed_outcomes:
            ll = o["label"].lower()
            if (
                ll == "yes"
                or ll.endswith(" yes")
                or " to make cut" in ll
                or " to make the cut" in ll
            ):
                yes = o
            elif (
                ll == "no"
                or ll.endswith(" no")
                or " to miss cut" in ll
                or " to miss the cut" in ll
            ):
                no = o

        if yes and no:
            yes_label = str(yes.get("label", "")).strip().lower()
            no_label = str(no.get("label", "")).strip().lower()
            yes_player = _extract_player_from_cut_labels([yes], offer_name, event_name, market_name)
            no_player = _extract_player_from_cut_labels([no], offer_name, event_name, market_name)
            generic_pair = yes_label in {"yes"} and no_label in {"no"}
            same_player_pair = (
                bool(yes_player)
                and bool(no_player)
                and yes_player.lower() == no_player.lower()
            )
            if not (generic_pair or same_player_pair):
                yes = None
                no = None

        if yes and no:
            player_name = _extract_player_from_cut_labels(parsed_outcomes, offer_name, event_name, market_name)
            if not player_name:
                return rows

            rows.append(
                {
                    "market": "make_cut",
                    "player_name": player_name,
                    "line": 1.0,
                    "odds": yes["odds"],          # yes-odds for quick display/prob
                    "over_odds": yes["odds"],     # semantic: over/yes
                    "under_odds": no["odds"],     # semantic: under/no
                    "round_num": round_num,
                    "book": "DRAFTKINGS",
                    "line_source": "draftkings_api",
                    "event_name": event_name,
                    "market_name": market_name or offer_name,
                    "selection_id": yes.get("selection_id"),
                    "selection_id_over": yes.get("selection_id"),
                    "selection_id_under": no.get("selection_id"),
                    "fetched_at": fetched_at,
                }
            )
            return rows

        rows.extend(
            _parse_one_way_cut_rows(
                parsed_outcomes=parsed_outcomes,
                offer_name=offer_name,
                event_name=event_name,
                market_name=market_name,
                round_num=round_num,
                fetched_at=fetched_at,
            )
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
        if len(skeys) < 1:
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
                    "selection_id": s.get("id", s.get("selectionId", s.get("outcomeId"))),
                    "line": s.get("line", s.get("points")),
                }
            )

        if len(parsed_outcomes) < 1:
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
            if len(parsed_outcomes) < 2:
                continue
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

        if market_type == "make_cut":
            yes = None
            no = None
            for o in parsed_outcomes:
                ll = o["label"].lower()
                if (
                    ll == "yes"
                    or ll.endswith(" yes")
                    or " to make cut" in ll
                    or " to make the cut" in ll
                ):
                    yes = o
                elif (
                    ll == "no"
                    or ll.endswith(" no")
                    or " to miss cut" in ll
                    or " to miss the cut" in ll
                ):
                    no = o
            if yes and no:
                yes_label = str(yes.get("label", "")).strip().lower()
                no_label = str(no.get("label", "")).strip().lower()
                yes_player = _extract_player_from_cut_labels([yes], offer_name, event_name, market_name)
                no_player = _extract_player_from_cut_labels([no], offer_name, event_name, market_name)
                generic_pair = yes_label in {"yes"} and no_label in {"no"}
                same_player_pair = (
                    bool(yes_player)
                    and bool(no_player)
                    and yes_player.lower() == no_player.lower()
                )
                if not (generic_pair or same_player_pair):
                    yes = None
                    no = None

            if yes and no:
                player_name = _extract_player_from_cut_labels(parsed_outcomes, offer_name, event_name, market_name)
                if not player_name:
                    continue

                rows.append(
                    {
                        "market": "make_cut",
                        "player_name": player_name,
                        "line": 1.0,
                        "odds": yes["odds"],
                        "over_odds": yes["odds"],
                        "under_odds": no["odds"],
                        "round_num": round_num,
                        "book": "DRAFTKINGS",
                        "line_source": "draftkings_api",
                        "event_name": event_name,
                        "market_name": offer_name or market_name,
                        "selection_id": yes.get("selection_id"),
                        "selection_id_over": yes.get("selection_id"),
                        "selection_id_under": no.get("selection_id"),
                        "fetched_at": fetched_at,
                    }
                )
                continue

            rows.extend(
                _parse_one_way_cut_rows(
                    parsed_outcomes=parsed_outcomes,
                    offer_name=offer_name,
                    event_name=event_name,
                    market_name=market_name,
                    round_num=round_num,
                    fetched_at=fetched_at,
                )
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
        "selection_id_over",
        "selection_id_under",
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
        (df["market"].isin(["winner", "group_winner"]) & df["player_name"].notna() & df["odds"].notna())
        |
        (df["market"].eq("h2h") & df["player_a"].notna() & df["player_b"].notna() & df["odds_a"].notna() & df["odds_b"].notna())
        |
        (df["market"].isin(["round_score", "birdies", "bogeys"]) & df["player_name"].notna() & df["over_odds"].notna() & df["under_odds"].notna())
        |
        (
            df["market"].isin(["make_cut", "miss_cut"])
            & df["player_name"].notna()
            & (df["odds"].notna() | (df["over_odds"].notna() & df["under_odds"].notna()))
        )
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


def _fetch_many_json(
    urls: List[str],
    headers: Dict[str, str],
    timeout: int = 8,
    max_workers: int = 8,
) -> List[Any]:
    """Fetch multiple JSON URLs concurrently and return successful payloads."""
    if not urls:
        return []

    payloads: List[Any] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch_json, u, headers, timeout) for u in urls]
        for fut in as_completed(futures):
            try:
                js = fut.result()
            except Exception:
                js = None
            if js is not None:
                payloads.append(js)
    return payloads


def _fetch_text(url: str, headers: Dict[str, str], timeout: int = 20) -> Optional[str]:
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def _extract_balanced_json_fragment(text: str, start_idx: int, open_char: str, close_char: str) -> str:
    """
    Extract a balanced JSON fragment from text, handling quoted strings safely.
    """
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != open_char:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start_idx:i + 1]
    return ""


def _extract_content_cards_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract contentCards arrays from arbitrary HTML/JS text.
    """
    payloads: List[Dict[str, Any]] = []
    if not text:
        return payloads

    # 1) __NEXT_DATA__ payload.
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, flags=re.S | re.I)
    if m:
        try:
            js = json.loads(m.group(1))
            payloads.append(js)
        except Exception:
            pass

    # 2) Direct "contentCards": [...] fragments.
    needle = '"contentCards"'
    pos = 0
    while True:
        idx = text.find(needle, pos)
        if idx < 0:
            break
        colon_idx = text.find(":", idx + len(needle))
        if colon_idx < 0:
            break
        arr_start = text.find("[", colon_idx)
        if arr_start < 0:
            pos = colon_idx + 1
            continue
        arr_json = _extract_balanced_json_fragment(text, arr_start, "[", "]")
        if arr_json:
            try:
                arr = json.loads(arr_json)
                if isinstance(arr, list):
                    payloads.append({"contentCards": arr})
            except Exception:
                pass
            pos = arr_start + len(arr_json)
        else:
            pos = arr_start + 1

    return payloads


def _event_ids_from_payloads(payloads: List[Any]) -> List[str]:
    ids = []
    seen = set()
    for p in payloads:
        if isinstance(p, dict) and isinstance(p.get("events"), list):
            for e in p["events"]:
                if not isinstance(e, dict):
                    continue
                eid = str(e.get("id", "")).strip()
                if eid and eid not in seen:
                    seen.add(eid)
                    ids.append(eid)
    return ids


def _sportsbook_slug_candidates(name: str) -> List[str]:
    if not name:
        return []
    s = str(name).lower()
    s = re.sub(r"\b20\d{2}\b", " ", s)
    s = s.replace("&", " and ")
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return []
    cands = [s]
    if s.startswith("the-"):
        cands.append(s[len("the-"):])
    else:
        cands.append(f"the-{s}")
    # unique order-preserving
    out = []
    seen = set()
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _build_candidate_content_card_urls(
    expected_tournament_name: str,
    detected_names: List[str],
) -> List[str]:
    base = "https://sportsbook.draftkings.com/leagues/golf"
    urls: List[str] = []

    name_candidates = []
    if expected_tournament_name:
        name_candidates.append(expected_tournament_name)
    name_candidates.extend(detected_names or [])

    seen = set()
    for name in name_candidates:
        for slug in _sportsbook_slug_candidates(name):
            page = f"{base}/{slug}"
            for suffix in [
                "",
                "?category=outrights&subcategory=cut",
                "?category=golfer-props&subcategory=birdies",
                "?category=golfer-props&subcategory=bogeys",
            ]:
                u = f"{page}{suffix}"
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
    return urls


def _build_card_api_urls(
    eventgroup_id: Optional[str],
    event_ids: List[str],
    region: str = "dkusnj",
) -> List[str]:
    """
    Build a broad set of candidate API URLs for content cards.
    """
    urls: List[str] = []
    eg = str(eventgroup_id or "").strip()
    if eg:
        urls.extend(
            [
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eg}/contentcards?format=json",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eg}/content-cards?format=json",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eg}?format=json&includeContentCards=true",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/leagues/{eg}",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/leagues/{eg}/contentcards",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/leagues/{eg}/content-cards",
                f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/prelive/leagues/{eg}",
                f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/live/leagues/{eg}",
                f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/pregame/leagues/{eg}",
            ]
        )

    for eid in event_ids:
        if not str(eid).strip():
            continue
        urls.extend(
            [
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/events/{eid}/contentcards?format=json",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/events/{eid}/content-cards?format=json",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/events/{eid}?format=json&includeContentCards=true",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eg}/events/{eid}/contentcards?format=json" if eg else "",
                f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eg}/events/{eid}/content-cards?format=json" if eg else "",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/events/{eid}",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/events/{eid}/contentcards",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/events/{eid}/content-cards",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/live/events/{eid}",
                f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/live/events/{eid}/contentcards",
            ]
        )

    # de-dup
    out = []
    seen = set()
    for u in urls:
        if not u:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _fetch_content_card_payloads_from_urls(
    urls: List[str],
    headers: Dict[str, str],
    timeout: int = 10,
    max_workers: int = 6,
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    if not urls:
        return payloads

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_fetch_text, u, headers, timeout): u for u in urls}
        for fut in as_completed(futs):
            try:
                text = fut.result()
            except Exception:
                text = None
            if not text:
                continue
            payloads.extend(_extract_content_cards_from_text(text))
    return payloads


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
    tokens = " ".join(_payload_sport_names(payload) + _extract_payload_event_names(payload)).lower()
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


def _sort_numericish_ids(values: Iterable[str]) -> List[str]:
    def _key(v: str) -> Tuple[int, str]:
        s = str(v)
        if s.isdigit():
            return (0, f"{int(s):012d}")
        return (1, s)

    return sorted({str(v) for v in values if str(v).strip()}, key=_key)


def _extract_ids_from_subscription_query(query: str, token: str) -> List[str]:
    """
    Parse numeric ids from subscription query snippets.
    Example:
      clientMetadata/Subcategories/any(s: s/Id eq '4508')
    """
    if not query:
        return []
    if token == "subcategory":
        pats = [r"Subcategories?/any\(.*?Id eq '(\d+)'\)", r"subCategoryId eq '(\d+)'"]
    else:
        pats = [r"Categories?/any\(.*?Id eq '(\d+)'\)", r"categoryId eq '(\d+)'"]
    out: List[str] = []
    for pat in pats:
        out.extend([m.group(1) for m in re.finditer(pat, query)])
    return out


def _expand_eventgroup_payloads_with_subcategories(
    payloads: List[Any],
    eventgroup_id: str,
    headers: Dict[str, str],
    max_subcategories: int = 24,
    max_categories: int = 12,
    timeout: int = 8,
    max_workers: int = 8,
    target_only: bool = True,
) -> List[Any]:
    """Fetch subcategory/category payloads for a chosen eventgroup."""
    out_payloads = list(payloads)
    if not out_payloads:
        return out_payloads

    subcategory_ids = set()
    category_ids = set()
    subcat_name_by_id: Dict[str, str] = {}
    cat_name_by_id: Dict[str, str] = {}

    target_sub_tokens = [
        "winner",
        "top ",
        "top finish",
        "head to head",
        "matchup",
        "finish higher",
        "round score",
        "birdie",
        "bogey",
        "cut",
    ]
    target_cat_tokens = [
        "tournament lines",
        "top finish",
        "make/miss cut",
        "round props",
        "golfer props",
        "tournament props",
    ]

    def _is_target_subcategory(name: str) -> bool:
        s = str(name or "").lower()
        return any(t in s for t in target_sub_tokens)

    def _is_target_category(name: str) -> bool:
        s = str(name or "").lower()
        return any(t in s for t in target_cat_tokens)

    for p in out_payloads:
        # Top-level lists often carry the full id set.
        if isinstance(p, dict):
            if isinstance(p.get("subcategories"), list):
                for s in p["subcategories"]:
                    if not isinstance(s, dict):
                        continue
                    if s.get("id") is not None:
                        sid = str(s["id"])
                        subcategory_ids.add(sid)
                        if s.get("name"):
                            subcat_name_by_id[sid] = str(s.get("name"))
                    if s.get("categoryId") is not None:
                        category_ids.add(str(s["categoryId"]))
            if isinstance(p.get("categories"), list):
                for c in p["categories"]:
                    if isinstance(c, dict) and c.get("id") is not None:
                        cid = str(c["id"])
                        category_ids.add(cid)
                        if c.get("name"):
                            cat_name_by_id[cid] = str(c.get("name"))
            if isinstance(p.get("subscriptionPartials"), dict):
                for v in p["subscriptionPartials"].values():
                    if not isinstance(v, dict):
                        continue
                    q = str(v.get("query", ""))
                    for sid in _extract_ids_from_subscription_query(q, token="subcategory"):
                        subcategory_ids.add(sid)
                    for cid in _extract_ids_from_subscription_query(q, token="category"):
                        category_ids.add(cid)

        for node in _walk(p):
            sid = node.get("subcategoryId")
            cid = node.get("categoryId")
            if sid is not None:
                subcategory_ids.add(str(sid))
            if cid is not None:
                category_ids.add(str(cid))

            # In subcategories[] objects, id is the subcategory id.
            if ("categoryId" in node) and ("id" in node) and node.get("id") is not None:
                sid = str(node.get("id"))
                subcategory_ids.add(sid)
                if node.get("name"):
                    subcat_name_by_id[sid] = str(node.get("name"))

            # Sometimes descriptors carry explicit IDs.
            if isinstance(node.get("offerSubcategoryDescriptors"), list):
                for d in _flatten_dict_items(node.get("offerSubcategoryDescriptors")):
                    if "subcategoryId" in d:
                        subcategory_ids.add(str(d["subcategoryId"]))
                    if "id" in d and d.get("id") is not None:
                        subcategory_ids.add(str(d["id"]))
                    if "categoryId" in d and d.get("categoryId") is not None:
                        category_ids.add(str(d["categoryId"]))
            if isinstance(node.get("offerCategoryDescriptors"), list):
                for d in _flatten_dict_items(node.get("offerCategoryDescriptors")):
                    if "categoryId" in d and d.get("categoryId") is not None:
                        category_ids.add(str(d["categoryId"]))
                    if "id" in d and d.get("id") is not None:
                        cid = str(d["id"])
                        category_ids.add(cid)
                        if d.get("name"):
                            cat_name_by_id[cid] = str(d.get("name"))

            # Capture category names from nodes where possible.
            if ("id" in node) and ("name" in node) and ("subcategoryId" not in node) and ("categoryId" not in node):
                nid = str(node.get("id"))
                nm = str(node.get("name") or "").strip()
                if nm and nid.isdigit():
                    if _is_target_category(nm):
                        cat_name_by_id[nid] = nm

    all_sub_ids = _sort_numericish_ids(subcategory_ids)
    all_cat_ids = _sort_numericish_ids(category_ids)

    target_sub_ids = [sid for sid in all_sub_ids if _is_target_subcategory(subcat_name_by_id.get(sid, ""))]
    target_cat_ids = [cid for cid in all_cat_ids if _is_target_category(cat_name_by_id.get(cid, ""))]

    if target_only:
        selected_sub_ids = target_sub_ids[:max_subcategories]
        selected_cat_ids = target_cat_ids[:max_categories]
    else:
        selected_sub_ids = (target_sub_ids + [sid for sid in all_sub_ids if sid not in target_sub_ids])[:max_subcategories]
        selected_cat_ids = (target_cat_ids + [cid for cid in all_cat_ids if cid not in target_cat_ids])[:max_categories]

    sub_urls = [
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/subcategories/{sid}?format=json"
        for sid in selected_sub_ids
    ]
    cat_urls = [
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/categories/{cid}?format=json"
        for cid in selected_cat_ids
    ]
    out_payloads.extend(_fetch_many_json(sub_urls + cat_urls, headers=headers, timeout=timeout, max_workers=max_workers))

    # Targeted market slugs used on sportsbook URL pages.
    targeted = [
        ("outrights", "cut"),
        ("golfer-props", "birdies"),
        ("golfer-props", "bogeys"),
    ]
    for cat_slug, sub_slug in targeted:
        u = (
            f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}"
            f"?format=json&category={cat_slug}&subcategory={sub_slug}"
        )
        js = _fetch_json(u, headers=headers, timeout=timeout)
        if js is not None:
            out_payloads.append(js)

    # Try a few known content-card endpoints (DK frequently rotates these).
    cc_urls = [
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/contentcards?format=json",
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}/content-cards?format=json",
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}?format=json&includeContentCards=true",
        f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/prelive/leagues/{eventgroup_id}",
        f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/live/leagues/{eventgroup_id}",
        f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/pregame/leagues/{eventgroup_id}",
    ]
    out_payloads.extend(_fetch_many_json(cc_urls, headers=headers, timeout=timeout, max_workers=max_workers))

    return out_payloads


def _fetch_live_dk_payloads_for_eventgroup(
    region: str,
    eventgroup_id: str,
    headers: Dict[str, str],
    include_subcategories: bool = True,
    max_subcategories: int = 24,
    max_categories: int = 12,
    request_timeout: int = 8,
    max_workers: int = 8,
    target_only: bool = True,
) -> List[Any]:
    urls = [
        f"https://sportsbook-nash.draftkings.com/api/sportscontent/{region}/v1/leagues/{eventgroup_id}",
        f"https://sportsbook.draftkings.com/api/odds/v1/leagues/{eventgroup_id}/offers/gamelines",
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/{eventgroup_id}?format=json",
        f"https://sportsbook-nash.draftkings.com/sites/US-SB/api/sportscontent/prepacks/league/v1/contentcards/prelive/leagues/{eventgroup_id}",
    ]

    payloads: List[Any] = []
    for u in urls:
        js = _fetch_json(u, headers=headers, timeout=request_timeout)
        if js is not None:
            payloads.append(js)

    if include_subcategories:
        payloads = _expand_eventgroup_payloads_with_subcategories(
            payloads=payloads,
            eventgroup_id=eventgroup_id,
            headers=headers,
            max_subcategories=max_subcategories,
            max_categories=max_categories,
            timeout=request_timeout,
            max_workers=max_workers,
            target_only=target_only,
        )

    return payloads


def fetch_live_dk_payloads(
    region: str = "dkusnj",
    eventgroup_id: Optional[str] = None,
    expected_tournament_name: str = "",
    tournament_id: str = "",
    max_subcategories: int = 24,
    max_categories: int = 12,
    request_timeout: int = 8,
    max_workers: int = 8,
    target_only: bool = True,
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
            max_subcategories=max_subcategories,
            max_categories=max_categories,
            request_timeout=request_timeout,
            max_workers=max_workers,
            target_only=target_only,
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
                    max_subcategories=max_subcategories,
                    max_categories=max_categories,
                    timeout=request_timeout,
                    max_workers=max_workers,
                    target_only=target_only,
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
            max_subcategories=max_subcategories,
            max_categories=max_categories,
            timeout=request_timeout,
            max_workers=max_workers,
            target_only=target_only,
        )
        return full_payloads, best["eventgroup_id"], best["names"]

    if fallback_payloads and fallback_id:
        fallback_payloads = _expand_eventgroup_payloads_with_subcategories(
            payloads=fallback_payloads,
            eventgroup_id=fallback_id,
            headers=headers,
            max_subcategories=max_subcategories,
            max_categories=max_categories,
            timeout=request_timeout,
            max_workers=max_workers,
            target_only=target_only,
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
                raw = json.loads(p.read_text(errors="ignore"))
            except Exception:
                continue
            # HAR file: walk all response bodies as separate payloads
            if isinstance(raw, dict) and isinstance(raw.get("log"), dict):
                entries = raw["log"].get("entries") or []
                n_extracted = 0
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    resp = e.get("response", {})
                    content = resp.get("content", {}) if isinstance(resp, dict) else {}
                    ctext = content.get("text") if isinstance(content, dict) else None
                    if not ctext:
                        continue
                    try:
                        body = json.loads(ctext)
                        payloads.append(body)
                        n_extracted += 1
                    except Exception:
                        pass
                print(f"  HAR: extracted {n_extracted} response payloads from {p.name}")
            elif isinstance(raw, list):
                payloads.extend(raw)
            else:
                payloads.append(raw)
    return payloads


def load_content_card_input_payloads(patterns: List[str]) -> List[Any]:
    """
    Load additional content-card payload candidates from JSON/HAR/text files.
    Useful when browser-exported Network responses contain cards but live endpoints don't.
    """
    payloads: List[Any] = []
    for pat in patterns:
        if Path(pat).is_absolute():
            match_paths = sorted(Path(x) for x in glob.glob(pat))
        else:
            match_paths = sorted(Path(x) for x in glob.glob(str(PROJECT_ROOT / pat)))
        for p in match_paths:
            if not p.exists() or p.is_dir():
                continue
            txt = p.read_text(errors="ignore")
            if not txt.strip():
                continue

            # 1) Try JSON parse first.
            raw = None
            try:
                raw = json.loads(txt)
            except Exception:
                raw = None

            if raw is not None:
                # HAR file support.
                if isinstance(raw, dict) and isinstance(raw.get("log"), dict):
                    entries = raw["log"].get("entries")
                    if isinstance(entries, list):
                        for e in entries:
                            if not isinstance(e, dict):
                                continue
                            resp = e.get("response")
                            if not isinstance(resp, dict):
                                continue
                            content = resp.get("content")
                            if not isinstance(content, dict):
                                continue
                            ctext = content.get("text")
                            if not isinstance(ctext, str) or not ctext:
                                continue
                            # Try JSON response body.
                            try:
                                body = json.loads(ctext)
                                payloads.append(body)
                            except Exception:
                                pass
                            # Also try embedded contentCards in text body.
                            payloads.extend(_extract_content_cards_from_text(ctext))
                else:
                    payloads.append(raw)

            # 2) Always attempt raw text extraction for embedded contentCards.
            payloads.extend(_extract_content_cards_from_text(txt))

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
        "event_name", "market_name", "selection_id", "selection_id_over", "selection_id_under", "fetched_at"
    ]
    output_cols = [c for c in output_cols if c in df.columns]
    df = df[output_cols]

    # Sort for readability
    sort_cols = ["market", "player_name", "odds"]
    sort_cols = [c for c in sort_cols if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, na_position="last")

    return df.reset_index(drop=True)


def _text_matches_expected_tournament(text: str, expected_tournament_name: str) -> bool:
    """Token-overlap match for free-form card text vs expected tournament name."""
    if not expected_tournament_name:
        return True
    etoks = set(_tokenize_tournament_text(expected_tournament_name))
    if not etoks:
        return True
    ntoks = set(_tokenize_tournament_text(text))
    if not ntoks:
        return False
    overlap = len(etoks.intersection(ntoks))
    return overlap >= max(1, min(2, len(etoks)))


def parse_content_cards(
    payloads: List[Any],
    fetched_at: str,
    tournament_id: str = "",
    expected_tournament_name: str = "",
    expected_start_date: str = "",
) -> pd.DataFrame:
    """
    Extract DraftKings prebuilt bet cards (contentCards) into a flat table.
    Kept separate from prop lines so edge-scoring schema remains stable.
    """
    # Build eventId -> eventName map so cards can be matched to current tournament.
    event_name_by_id: Dict[str, str] = {}
    for p in payloads:
        try:
            event_name_by_id.update(_extract_event_map(p))
        except Exception:
            pass

    def _extract_card_row(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(c, dict):
            return None

        display_odds = c.get("displayOdds")
        american = None
        decimal = None
        if isinstance(display_odds, dict):
            american = display_odds.get("american")
            decimal = display_odds.get("decimal")

        selections = c.get("selections") if isinstance(c.get("selections"), list) else []
        leg_labels = []
        leg_ids = []
        market_ids = []
        event_ids = []
        event_names = []
        for s in selections:
            if not isinstance(s, dict):
                continue
            leg_label = str(s.get("selectionLabel") or s.get("label") or s.get("name") or "").strip()
            if leg_label:
                leg_labels.append(leg_label)
            sid = str(s.get("selectionId", "")).strip()
            if sid:
                leg_ids.append(sid)
            mid = str(s.get("marketId", "")).strip()
            if mid:
                market_ids.append(mid)
            eid = str(s.get("eventId", "")).strip()
            if eid:
                event_ids.append(eid)
                ev_name = str(event_name_by_id.get(eid, "")).strip()
                if ev_name:
                    event_names.append(ev_name)
            ev_name_inline = str(s.get("eventName", "")).strip()
            if ev_name_inline:
                event_names.append(ev_name_inline)

        # Strictness to avoid noisy pseudo-card rows.
        if len(leg_labels) == 0:
            return None

        # ordered unique
        event_ids = list(dict.fromkeys([e for e in event_ids if e]))
        event_names = list(dict.fromkeys([e for e in event_names if e]))

        return {
            "tournament_id": tournament_id,
            "card_id": c.get("id"),
            "title": c.get("title"),
            "subtitle": c.get("subtitle"),
            "card_label": c.get("cardLabel"),
            "content_card_type": c.get("contentCardType"),
            "sort_order": c.get("sortOrder"),
            "bet_count": c.get("betCount"),
            "odds_american": _odds_to_int(american),
            "odds_decimal": pd.to_numeric(decimal, errors="coerce"),
            "selection_count": len(leg_labels),
            "selection_labels": " | ".join(leg_labels),
            "selection_ids": " | ".join(leg_ids),
            "selection_labels_json": json.dumps(leg_labels),
            "selection_ids_json": json.dumps(leg_ids),
            "market_ids_json": json.dumps(market_ids),
            "selection_event_ids_json": json.dumps(event_ids),
            "selection_event_names_json": json.dumps(event_names),
            "selection_event_names": " | ".join(event_names),
            "background_image_url": c.get("backgroundImageUrl"),
            "end_date": c.get("endDate"),
            "fetched_at": fetched_at,
        }

    rows: List[Dict[str, Any]] = []
    for p in payloads:
        for node in _walk(p):
            # Path 1: explicit contentCards array.
            cards = node.get("contentCards")
            if isinstance(cards, list):
                for c in cards:
                    row = _extract_card_row(c)
                    if row:
                        rows.append(row)

            # Path 2: standalone card-like objects under unknown keys.
            if not isinstance(node, dict):
                continue
            if isinstance(node.get("selections"), list):
                cardish_signal = any(
                    k in node
                    for k in ["title", "subtitle", "cardLabel", "contentCardType", "displayOdds", "backgroundImageUrl"]
                )
                if cardish_signal:
                    row = _extract_card_row(node)
                    if row:
                        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "card_id" in df.columns:
        has_card_id = df["card_id"].fillna("").astype(str).str.strip() != ""
        if has_card_id.any():
            df = pd.concat(
                [
                    df[has_card_id].drop_duplicates(subset=["card_id"], keep="first"),
                    df[~has_card_id].drop_duplicates(subset=["title", "selection_labels"], keep="first"),
                ],
                ignore_index=True,
            )
        else:
            df = df.drop_duplicates(subset=["title", "selection_labels"], keep="first")
    if "sort_order" in df.columns:
        df["sort_order"] = pd.to_numeric(df["sort_order"], errors="coerce")

    # Hard tournament filter to avoid stale previous-week cards from fallback payloads/HAR files.
    if expected_tournament_name or expected_start_date:
        def _parse_json_list_cell(value: Any) -> List[str]:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return []
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
            s = str(value).strip()
            if not s:
                return []
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except Exception:
                pass
            return []

        expected_dt = None
        if expected_start_date:
            try:
                expected_dt = pd.to_datetime(str(expected_start_date), utc=True, errors="coerce")
            except Exception:
                expected_dt = None

        keep_mask = []
        for _, row in df.iterrows():
            event_names = _parse_json_list_cell(row.get("selection_event_names_json"))
            event_match = any(_event_name_matches_expected(nm, expected_tournament_name) for nm in event_names if nm) if expected_tournament_name else False

            text_blob = " ".join(
                [
                    str(row.get("title", "") or ""),
                    str(row.get("subtitle", "") or ""),
                    str(row.get("selection_labels", "") or ""),
                    str(row.get("selection_event_names", "") or ""),
                ]
            )
            text_match = _text_matches_expected_tournament(text_blob, expected_tournament_name) if expected_tournament_name else False

            # Date guard: keep cards whose end_date is near this tournament's start week.
            date_match = False
            if expected_dt is not None and not pd.isna(expected_dt):
                end_date_raw = row.get("end_date")
                end_dt = pd.to_datetime(end_date_raw, utc=True, errors="coerce")
                if not pd.isna(end_dt):
                    delta_days = (end_dt - expected_dt).days
                    # Keep cards ending around/after tournament start; reject prior-week cards.
                    date_match = (-1 <= delta_days <= 10)

            keep_mask.append(bool(event_match or text_match or date_match))

        if keep_mask:
            filtered = df[pd.Series(keep_mask, index=df.index)].copy()
            # Strict apply: if nothing matches expected tournament/date, return empty
            # so stale previous-week cards are not written.
            df = filtered

    return df.sort_values(["sort_order", "title"], na_position="last").reset_index(drop=True)


def debug_payload_summary(payloads: List[Any]) -> None:
    print("\nDebug summary:")
    print(f"  payload_count: {len(payloads)}")
    key_counter: Counter[str] = Counter()
    outcomes_nodes = 0
    market_selection_payloads = 0
    total_markets = 0
    total_selections = 0
    content_cards = 0
    sample_rows: List[Tuple[str, str, str, int]] = []

    for p in payloads:
        if isinstance(p, dict) and isinstance(p.get("markets"), list) and isinstance(p.get("selections"), list):
            market_selection_payloads += 1
            total_markets += len(p.get("markets", []))
            total_selections += len(p.get("selections", []))
        for node in _walk(p):
            key_counter.update(node.keys())
            if isinstance(node.get("contentCards"), list):
                content_cards += len(node.get("contentCards", []))
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
    print(f"  content_cards: {content_cards}")
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
    parser.add_argument(
        "--content-cards-url",
        nargs="*",
        default=[],
        help="Optional sportsbook page URL(s) to scrape embedded contentCards JSON from",
    )
    parser.add_argument(
        "--content-cards-input",
        nargs="*",
        default=[],
        help="Optional JSON/HAR/text file(s) containing contentCards payloads",
    )
    parser.add_argument(
        "--fetch-profile",
        choices=["targeted", "fast", "balanced", "full"],
        default="targeted",
        help="Network fetch intensity (default: targeted — win/top5/top10/h2h/round props only)",
    )
    parser.add_argument("--output", help="Custom output CSV path")
    parser.add_argument("--content-cards-output", help="Custom output CSV path for content cards")
    parser.add_argument("--no-snapshot", action="store_true", help="Disable saving raw payload snapshots")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=0.0,
        help="Skip refresh if output file is newer than this many hours (default: 0, disabled)",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh even if output file is fresh")
    parser.add_argument("--debug", action="store_true", help="Print payload structure summary")
    args = parser.parse_args()

    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else (ODDS_DIR / f"prop_lines_{args.tournament_id}.csv")
    cards_out_path = (
        Path(args.content_cards_output)
        if args.content_cards_output
        else (ODDS_DIR / f"dk_content_cards_{args.tournament_id}.csv")
    )

    if args.max_age_hours > 0 and (not args.force_refresh):
        def _is_fresh(path: Path, max_age_hours: float) -> bool:
            if not path.exists():
                return False
            age_hours = (datetime.now().timestamp() - path.stat().st_mtime) / 3600.0
            return age_hours <= max_age_hours

        def _csv_has_rows(path: Path) -> bool:
            if not path.exists():
                return False
            try:
                probe = pd.read_csv(path, nrows=1)
                return not probe.empty
            except Exception:
                return False

        props_fresh = _is_fresh(out_path, args.max_age_hours)
        cards_fresh = _is_fresh(cards_out_path, args.max_age_hours)
        cards_non_empty = _csv_has_rows(cards_out_path)
        if props_fresh and cards_fresh and cards_non_empty:
            print(
                "Skipping DraftKings fetch - fresh prop + content-card files exist "
                f"({out_path.name}, {cards_out_path.name}, <= {args.max_age_hours:.1f}h old)"
            )
            return

    payloads: List[Any] = []
    expected_tournament_name = _resolve_tournament_name_from_schedule(args.tournament_id)
    expected_start_date = _resolve_tournament_start_date_from_schedule(args.tournament_id)
    if expected_tournament_name:
        print(f"Expected tournament for {args.tournament_id}: {expected_tournament_name}")

    profile_cfg = {
        # targeted: only the subcategory IDs we actually use — fastest after first run
        "targeted": {"max_subcategories": 20, "max_categories": 10, "request_timeout": 8, "max_workers": 12, "target_only": True},
        "fast": {"max_subcategories": 24, "max_categories": 12, "request_timeout": 6, "max_workers": 10, "target_only": True},
        "balanced": {"max_subcategories": 50, "max_categories": 25, "request_timeout": 8, "max_workers": 10, "target_only": False},
        "full": {"max_subcategories": 120, "max_categories": 60, "request_timeout": 12, "max_workers": 12, "target_only": False},
    }[args.fetch_profile]

    chosen_eventgroup: Optional[str] = None
    detected_names: List[str] = []
    resolved_eg_id = str(args.eventgroup_id or "").strip()

    if args.input_json:
        payloads.extend(load_input_payloads(args.input_json))

    extra_card_payloads: List[Any] = []
    card_input_patterns = list(args.content_cards_input or [])
    if not card_input_patterns:
        default_har = PROJECT_ROOT / "sportsbook.draftkings.com.har"
        if default_har.exists():
            card_input_patterns.append(str(default_har))
            if args.debug:
                print(f"Using default HAR for content cards: {default_har}")

    if card_input_patterns:
        extra_card_payloads.extend(load_content_card_input_payloads(card_input_patterns))
        if args.debug:
            print(f"Loaded {len(extra_card_payloads)} content-card payload candidate(s) from --content-cards-input")

    if not payloads:
        # ── Resolve eventgroup ID: CLI override → manual dict → cache → discover ──
        if not resolved_eg_id:
            resolved_eg_id = _resolve_override_eventgroup_id(args.tournament_id)
        if not resolved_eg_id:
            _cache = _load_eg_cache()
            resolved_eg_id = _cache.get(str(args.tournament_id).upper(), "")
            if resolved_eg_id:
                print(f"Using cached eventgroup id for {args.tournament_id}: {resolved_eg_id}")

        print("Trying live DraftKings endpoints...")
        payloads, chosen_eventgroup, detected_names = fetch_live_dk_payloads(
            region=args.region,
            eventgroup_id=resolved_eg_id or None,
            expected_tournament_name=expected_tournament_name,
            tournament_id=args.tournament_id,
            **profile_cfg,
        )
        if chosen_eventgroup:
            print(f"Using eventgroup id: {chosen_eventgroup}")
            # Persist for next run — skips discovery entirely
            _save_eg_cache(args.tournament_id, chosen_eventgroup)
        if detected_names:
            print(f"Detected sport/league names: {', '.join(detected_names[:6])}")

    if not payloads:
        print("No DraftKings prop payloads loaded; attempting content-cards-only fallback.")

        fetched_at = _now_utc_iso()
        cards_sources: List[Any] = list(extra_card_payloads)
        cards_eventgroup = chosen_eventgroup or resolved_eg_id

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
        }
        if cards_eventgroup:
            card_api_urls = _build_card_api_urls(
                eventgroup_id=cards_eventgroup,
                event_ids=[],
                region=args.region,
            )
            api_payloads = _fetch_many_json(
                card_api_urls,
                headers=headers,
                timeout=max(6, int(profile_cfg.get("request_timeout", 8))),
                max_workers=min(10, int(profile_cfg.get("max_workers", 8))),
            )
            cards_sources.extend(api_payloads)
            if args.debug:
                print(
                    f"  content-card fallback via eventgroup {cards_eventgroup}: "
                    f"{len(api_payloads)} payload(s) from {len(card_api_urls)} URL(s)"
                )

        cards_df = parse_content_cards(
            cards_sources,
            fetched_at=fetched_at,
            tournament_id=args.tournament_id,
            expected_tournament_name=expected_tournament_name,
            expected_start_date=expected_start_date,
        )

        if cards_df.empty:
            cc_urls = []
            if args.content_cards_url:
                cc_urls.extend([u for u in args.content_cards_url if str(u).strip()])
            cc_urls.extend(_build_candidate_content_card_urls(expected_tournament_name, detected_names))
            if cc_urls:
                html_card_payloads = _fetch_content_card_payloads_from_urls(
                    urls=cc_urls,
                    headers=headers,
                    timeout=max(8, int(profile_cfg.get("request_timeout", 8))),
                    max_workers=min(8, int(profile_cfg.get("max_workers", 8))),
                )
                if args.debug:
                    print(
                        f"  content-card HTML fallback tried {len(cc_urls)} URL(s), "
                        f"got {len(html_card_payloads)} payload candidate(s)"
                    )
                if html_card_payloads:
                    cards_df = parse_content_cards(
                        cards_sources + html_card_payloads,
                        fetched_at=fetched_at,
                        tournament_id=args.tournament_id,
                        expected_tournament_name=expected_tournament_name,
                        expected_start_date=expected_start_date,
                    )

        card_cols = [
            "tournament_id",
            "card_id",
            "title",
            "subtitle",
            "card_label",
            "content_card_type",
            "sort_order",
            "bet_count",
            "odds_american",
            "odds_decimal",
            "selection_count",
            "selection_labels",
            "selection_ids",
            "selection_labels_json",
            "selection_ids_json",
            "market_ids_json",
            "selection_event_ids_json",
            "selection_event_names_json",
            "selection_event_names",
            "background_image_url",
            "end_date",
            "fetched_at",
        ]
        if cards_df.empty:
            cards_df = pd.DataFrame(columns=card_cols)
            print("No content cards found in available DK payloads/endpoints; writing empty content-cards file.")

        cards_df.to_csv(cards_out_path, index=False)
        cards_latest_path = ODDS_DIR / "dk_content_cards_latest.csv"
        cards_df.to_csv(cards_latest_path, index=False)
        print(f"Saved {len(cards_df)} content cards to: {cards_out_path}")
        print(f"Saved latest content cards to: {cards_latest_path}")
        print("Tip: prop lines were not updated because live DK market payloads were unavailable.")
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
    cards_df = parse_content_cards(
        payloads,
        fetched_at=fetched_at,
        tournament_id=args.tournament_id,
        expected_tournament_name=expected_tournament_name,
        expected_start_date=expected_start_date,
    )
    if cards_df.empty and extra_card_payloads:
        cards_df = parse_content_cards(
            payloads + extra_card_payloads,
            fetched_at=fetched_at,
            tournament_id=args.tournament_id,
            expected_tournament_name=expected_tournament_name,
            expected_start_date=expected_start_date,
        )

    if cards_df.empty:
        # Fallback A: dedicated card/event endpoints that may not be included in league payload.
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
        }
        card_api_urls = _build_card_api_urls(
            eventgroup_id=chosen_eventgroup,
            event_ids=_event_ids_from_payloads(payloads),
            region=args.region,
        )
        if card_api_urls:
            extra_card_payloads = _fetch_many_json(
                card_api_urls,
                headers=headers,
                timeout=max(6, int(profile_cfg.get("request_timeout", 8))),
                max_workers=min(10, int(profile_cfg.get("max_workers", 8))),
            )
            if extra_card_payloads:
                cards_df = parse_content_cards(
                    payloads + extra_card_payloads,
                    fetched_at=fetched_at,
                    tournament_id=args.tournament_id,
                    expected_tournament_name=expected_tournament_name,
                    expected_start_date=expected_start_date,
                )
            elif args.debug:
                print(f"  content-card API fallback tried {len(card_api_urls)} URLs, 0 payloads")

    if cards_df.empty:
        # Fallback B: scrape sportsbook page HTML for embedded contentCards JSON.
        cc_urls = []
        if args.content_cards_url:
            cc_urls.extend([u for u in args.content_cards_url if str(u).strip()])
        cc_urls.extend(_build_candidate_content_card_urls(expected_tournament_name, detected_names))
        if cc_urls:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/json",
            }
            html_card_payloads = _fetch_content_card_payloads_from_urls(
                urls=cc_urls,
                headers=headers,
                timeout=max(8, int(profile_cfg.get("request_timeout", 8))),
                max_workers=min(8, int(profile_cfg.get("max_workers", 8))),
            )
            if args.debug:
                print(f"  content-card HTML fallback tried {len(cc_urls)} URL(s), got {len(html_card_payloads)} payload candidate(s)")
            if html_card_payloads:
                cards_df = parse_content_cards(
                    payloads + html_card_payloads,
                    fetched_at=fetched_at,
                    tournament_id=args.tournament_id,
                    expected_tournament_name=expected_tournament_name,
                    expected_start_date=expected_start_date,
                )

    card_cols = [
        "tournament_id",
        "card_id",
        "title",
        "subtitle",
        "card_label",
        "content_card_type",
        "sort_order",
        "bet_count",
        "odds_american",
        "odds_decimal",
        "selection_count",
        "selection_labels",
        "selection_ids",
        "selection_labels_json",
        "selection_ids_json",
        "market_ids_json",
        "selection_event_ids_json",
        "selection_event_names_json",
        "selection_event_names",
        "background_image_url",
        "end_date",
        "fetched_at",
    ]
    if cards_df.empty:
        cards_df = pd.DataFrame(columns=card_cols)
        print("No content cards found in available DK payloads/endpoints; writing empty content-cards file.")

    cards_df.to_csv(cards_out_path, index=False)
    cards_latest_path = ODDS_DIR / "dk_content_cards_latest.csv"
    cards_df.to_csv(cards_latest_path, index=False)
    print(f"Saved {len(cards_df)} content cards to: {cards_out_path}")
    print(f"Saved latest content cards to: {cards_latest_path}")

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
        print("Loaded payloads but could not parse supported markets (winner / h2h / round_score / birdies / bogeys / make_cut).")
        print("Likely cause: payloads are quote-only or market metadata keys differ.")
        if not cards_df.empty:
            print("Note: preset content cards were parsed and saved.")
        if snapshot_path:
            print(f"Inspect this snapshot and share one object with full market+outcomes: {snapshot_path}")
        return

    # Clean and transform for dashboard integration
    df = clean_prop_lines_for_dashboard(df)

    df.to_csv(out_path, index=False)

    print(f"Saved {len(df)} prop lines to: {out_path}")

    by_market = df["market"].value_counts().to_dict()
    print("Parsed markets:")
    for m, n in by_market.items():
        print(f"  {m}: {n}")


if __name__ == "__main__":
    main()
