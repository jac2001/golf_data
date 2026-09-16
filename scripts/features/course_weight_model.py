"""
Shared regression logic for deriving course-specific SG importance weights
from historical results. Used by both derive_course_weights.py (one course
at a time, for majors that rotate venues) and backfill_course_fit_weights.py
(batch — every fixed-venue course in one pass).

Keeping the math in one place means both call sites can never drift apart.

Method
------
For a set of historical tournament_ids at the SAME course:
1. Outcome = score relative to the field that week, per round (positive =
   better than the field) — comparable scale to season SG.
2. Univariate slope per SG category (not multivariate — with ~70-150 players
   per edition, correlated SG categories make multivariate regression
   unstable; isolating one predictor at a time is far more robust).
3. Negative slopes floored to a small epsilon — a course "punishing" real
   skill doesn't happen physically; a negative slope here is noise.
4. Normalized to the same overall scale as the rest of the weights data, so
   the fit formula (dg_fit_X = season_sg_X * course_X_weight * 10) behaves
   consistently across every course.
5. Shrunk toward DEFAULT_WEIGHTS based on sample size — thin data leans on
   the safe average; a larger pooled sample trusts the derived numbers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TOURNAMENT_COURSES_JSON = ROOT / "data" / "reference" / "tournament_courses.json"

FEATS = ["season_sg_ott", "season_sg_app", "season_sg_arg", "season_sg_putt"]
WEIGHT_COLS = ["ott_sg", "app_sg", "arg_sg", "putt_sg"]

# Same defaults used historically in course_fit_dg.py / predict_tournament.py —
# the fallback for courses with no specific data, and the shrinkage anchor here.
DEFAULT_WEIGHTS = {"ott_sg": 0.020, "app_sg": 0.020, "arg_sg": 0.025, "putt_sg": 0.005}

# Majors that rotate venues — pooling all historical rows under one
# tournament_name would mix different courses' data together. These need
# explicit per-course derivation (one course at a time), never the blind
# batch pooling used for fixed-venue events.
ROTATING_VENUE_EVENTS = {"u s open", "the open championship", "open championship", "pga championship"}

# Target row-sum to normalize against, so a newly-derived course's weights
# sit in the same overall scale as historically curated rows (median row-sum
# across the original ~60 courses in course_sg_weights.csv).
TARGET_ROW_SUM = 0.074

# Below this many players, lean heavily on DEFAULT_WEIGHTS. At or above,
# trust the derived weights close to fully.
FULL_CONFIDENCE_N = 100

MIN_PLAYERS = 10  # below this, there's not enough signal to derive anything


def normalize_event_name(name: str) -> str:
    """Lowercase + strip punctuation for matching against ROTATING_VENUE_EVENTS."""
    if not isinstance(name, str):
        return ""
    cleaned = re.sub(r"\(\s*\d{4}\s*\)", "", name)  # drop year suffixes
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_rotating_venue(tournament_name: str) -> bool:
    return normalize_event_name(tournament_name) in ROTATING_VENUE_EVENTS


def load_course_mapping() -> dict:
    """Load data/reference/tournament_courses.json — the single source of
    truth for "which course does this tournament name refer to."""
    if not TOURNAMENT_COURSES_JSON.exists():
        return {}
    try:
        return json.loads(TOURNAMENT_COURSES_JSON.read_text()).get("tournaments", {})
    except Exception:
        return {}


def resolve_course_name(tournament_name: str, mapping: dict | None = None) -> str | None:
    """
    Resolve a tournament name to its actual course name via tournament_courses.json
    (exact name or alias match). Returns None if not found — callers should fall
    back to using the tournament_name itself as a pseudo-course-name in that case
    (older/defunct sponsor-name events that never got a mapping entry).

    Shared by the API endpoint and the batch backfill so they can never resolve
    the same tournament to two different keys.
    """
    if mapping is None:
        mapping = load_course_mapping()
    tn_norm = normalize_event_name(tournament_name)
    for name, details in mapping.items():
        name_norm = normalize_event_name(name)
        aliases_norm = [normalize_event_name(a) for a in details.get("aliases", [])]
        if tn_norm == name_norm or tn_norm in aliases_norm:
            return details.get("course")
    return None


def derive_weights(sub: pd.DataFrame) -> dict:
    """
    Derive {ott_sg, app_sg, arg_sg, putt_sg, n_players, confidence} from a
    DataFrame of historical player-tournament rows for ONE course.

    Required columns: season_sg_ott/app/arg/putt, total_score, rounds_played.
    Raises ValueError if there isn't enough usable data.
    """
    sub = sub.copy()
    sub["total_score"] = pd.to_numeric(sub["total_score"], errors="coerce")
    sub["rounds_played"] = pd.to_numeric(sub["rounds_played"], errors="coerce")
    sub = sub.dropna(subset=FEATS + ["total_score", "rounds_played"])
    sub = sub[sub["rounds_played"] > 0]

    n = len(sub)
    if n < MIN_PLAYERS:
        raise ValueError(f"Only {n} usable player-rows — need at least {MIN_PLAYERS}.")

    # Outcome: strokes better than the field, per round (matches SG sign convention).
    # Must compare per-round scores, not raw totals — a missed-cut player's 2-round
    # total (e.g. 150) and a made-cut player's 4-round total (e.g. 290) are on
    # completely different scales, so a single field_mean of raw totals blends two
    # unrelated quantities and produces a meaningless, wildly-scaled outcome. This
    # bug was masked previously because incomplete season-SG coverage happened to
    # exclude most missed-cut players via dropna; better coverage exposed it.
    sub["score_per_round"] = sub["total_score"] / sub["rounds_played"]
    field_mean_per_round = sub["score_per_round"].mean()
    y = field_mean_per_round - sub["score_per_round"]

    raw_slopes = {}
    for feat, wcol in zip(FEATS, WEIGHT_COLS):
        x = sub[feat].values
        slope = np.polyfit(x, y, 1)[0]
        raw_slopes[wcol] = max(slope, 1e-4)  # floor negative/zero — treat as noise

    # Normalize relative proportions to the established overall scale
    raw_sum = sum(raw_slopes.values())
    scaled = {k: v / raw_sum * TARGET_ROW_SUM for k, v in raw_slopes.items()}

    # Shrink toward DEFAULT_WEIGHTS based on sample size
    confidence = min(1.0, n / FULL_CONFIDENCE_N)
    final = {
        k: confidence * scaled[k] + (1 - confidence) * DEFAULT_WEIGHTS[k]
        for k in WEIGHT_COLS
    }
    final["n_players"] = n
    final["confidence"] = round(confidence, 3)
    return final
