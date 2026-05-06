"""
Season Usage Strategy
=====================
Recommends optimal timing for spending each player's remaining uses.

Core idea: each player's 3 (or remaining) uses are a depletable asset.
Spending Scheffler at a $7.3M Standard event costs you the option to use
him at a $21M Major.  This module scores future events × player strength
to produce: "use this week" or "save for these events" per player.

This week's EV uses actual model predictions (win_prob_calibrated, top10_prob_calibrated,
cut_prob etc.) from outputs/latest_predictions.csv — not a rank proxy.

Future event EV uses the rank proxy, multiplied by a course-fit factor derived
from data/processed/player_course_performance.csv (course_sg_total_weighted).

Usage:
    from scripts.predictions.season_strategy import get_season_strategy
    strategy = get_season_strategy()
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"



OUTPUTS_DIR = PROJECT_ROOT / "outputs"

USAGE_TRACKER          = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
SCHEDULE_FILE          = DATA_DIR / "raw" / "schedule_2026.csv"
PREDICTIONS_FILE       = OUTPUTS_DIR / "latest_predictions.csv"
OWGR_FILE              = DATA_DIR / "rankings" / "owgr_2026.csv"
COURSE_PERF_FILE       = DATA_DIR / "processed" / "player_course_performance.csv"
TOURNAMENT_COURSE_FILE = DATA_DIR / "processed" / "player_tournament_course_form.csv"
LEADERBOARDS_FILE      = DATA_DIR / "historical" / "leaderboards_2026.csv"
LEADERBOARDS_2025_FILE = DATA_DIR / "historical" / "leaderboards_2025.csv"
DG_SKILL_FILE = DATA_DIR / "datagolf" / "dg_skill_ratings_latest.csv"
DG_RANKINGS_FILE = DATA_DIR / "datagolf" / "dg_rankings_latest.csv"
DG_PRE_TOURNEY_FILE = DATA_DIR / "datagolf" / "dg_pre_tournament_latest.csv"


def _name_key(name: str) -> str:
    """Normalize 'Last, First' or 'First Last' → sorted lowercase ASCII tokens."""
    import unicodedata
    parts = str(name).split(",")
    if len(parts) == 2:
        name = f"{parts[1].strip()} {parts[0].strip()}"
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = "".join(c if (c.isalnum() or c.isspace()) else " " for c in name.lower())
    return " ".join(sorted(name.split()))

# ── Type weights ──────────────────────────────────────────────────────────────
TYPE_WEIGHT = {
    "major":     1.00,
    "playoff":   0.90,
    "signature": 0.80,
    "team":      0.40,
    "standard":  0.45,
    "opposite":  0.30,
}

# ── Hot streak detection thresholds ───────────────────────────────────────────
# A player is "hot" when their recent SG is surging above their career baseline
# AND the trend is directionally positive.  Form is perishable — a hot player
# at a good event today may be a regression risk in 4 weeks.
#
# sg_trend is in strokes-gained per round per week (positive = improving).
# recent_sg_advantage = how far recent_sg exceeds career SG baseline.
#
# Hot override: if hot AND this-week EV >= 65% of best future EV → use now.
# The normal threshold is 90% — we loosen it because form may not persist.
HOT_STREAK_SG_TREND   = 0.20   # sg_trend (SG/round/week) threshold
HOT_STREAK_RECENT_ADV = 0.20   # recent_sg must exceed career SG by this margin
HOT_STREAK_EV_RATIO   = 0.65   # EV threshold for hot-streak override (vs 0.90 normal)

# ── Season plan config ─────────────────────────────────────────────────────────
MAX_PLAYERS_PER_EVENT = 3       # fantasy league weekly pick cap

# Payout fractions by finish-position band (PGA Tour structure)
PAYOUT_WIN    = 0.180
PAYOUT_T2_5   = 0.068
PAYOUT_T6_10  = 0.030
PAYOUT_T11_20 = 0.017
PAYOUT_T21_CUT = 0.006

# Course-fit multiplier scaling.
# course_sg_total_weighted is strokes-gained vs tour average at that specific course.
# +2.0 SG at a course → ~20% EV boost.  -2.0 SG → ~20% reduction.
# Clamped to [0.70, 1.30] so no single player/course blows up the rankings.
COURSE_FIT_SCALE = 0.10
COURSE_FIT_MIN   = 0.70
COURSE_FIT_MAX   = 1.30


def _parse_purse(val: str | float) -> float:
    """Convert '$21,000,000.00' → 21000000.0"""
    try:
        return float(str(val).replace("$", "").replace(",", ""))
    except Exception:
        return 0.0


def _sg_to_implied_rank(sg: float) -> float:
    """
    Convert strokes-gained total vs tour average into an implied world rank.

    Empirical calibration:
        SG +2.5 → ~rank 3   (Scheffler/McIlroy tier)
        SG +1.5 → ~rank 13
        SG +1.0 → ~rank 22
        SG +0.5 → ~rank 36
        SG  0.0 → ~rank 60  (tour average player)
        SG -0.5 → ~rank 99
        SG -1.0 → ~rank 163

    Formula: implied_rank = 60 * exp(-sg)
    This lets us detect players whose current form diverges from their
    official world ranking — e.g. a WR #145 player posting +0.5 SG this
    season is effectively playing like a top-36 player.
    """
    return max(1.0, 60.0 * math.exp(-float(sg)))


def _effective_rank(world_rank: float, sg_season: float, sg_career: float,
                    sg_tournaments: int) -> float:
    """
    Blend world rank, season SG, and career SG into a single effective rank.

    World rank can lag reality — it updates slowly and is distorted by
    schedule gaps (injuries, LIV, limited events).  SG-implied rank captures
    current form but can be noisy with few observations.

    Blend weights:
        - If player has < 3 tournaments of season SG data: lean on world rank + career
        - If player has >= 6 tournaments: lean on season SG (most current)
        - Career SG is a stable prior

    The final effective rank is used only for FUTURE event scoring (not current
    week, where we have actual calibrated model probabilities).
    """
    # Implied ranks from each signal
    rank_wr     = world_rank
    rank_season = _sg_to_implied_rank(sg_season) if sg_season != 0.0 else world_rank
    rank_career = _sg_to_implied_rank(sg_career) if sg_career != 0.0 else world_rank

    # Confidence in season SG based on tournament count (0 → 0 weight, 6+ → 0.5 weight)
    season_conf = min(1.0, sg_tournaments / 6.0)

    # Blend: world_rank × (1-season_conf) × 0.6 + career × 0.4,
    #         then blend in season at its confidence level
    base_rank = 0.60 * rank_wr + 0.40 * rank_career
    blended   = (1.0 - season_conf) * base_rank + season_conf * rank_season
    return max(1.0, blended)


def _field_difficulty_mult(world_rank: float, type_weight: float) -> float:
    """
    Penalty applied to the rank-proxy EV for harder fields.

    The rank proxy assumes a generic mixed field. But at a Major (top ~90
    players) or Signature (top ~50 players), weaker players are competing
    against an elite field and their realistic win/top-10 probability is
    far lower than the proxy suggests.

    Reality check:
      - WR #145 at the Masters: win prob ≈ 0.05%, cut prob ≈ 30%
      - WR #145 at a standard event: win prob ≈ 1%, cut prob ≈ 60%
      - But the proxy gives them the same 5% win prob at both events.

    Without this adjustment the model always tells everyone to save for
    Majors because the purse is 3× larger — even though a fringe player
    has virtually no chance there. This multiplier corrects for that.

    Multipliers are calibrated so that for WR #100+:
      - A Major's adjusted EV roughly equals a standard event's EV
      - For WR #50-100 the Major is worth ~2× a standard event (vs 4× raw)
      - For WR #1-20 the Major is worth ~4× a standard event (no discount)
    """
    if type_weight >= 0.90:  # Major or FedEx playoff
        if world_rank <= 20:
            return 1.00   # Elite — full advantage, these are the Major winners
        elif world_rank <= 50:
            return 0.60   # Good players compete at Majors but rarely win
        elif world_rank <= 100:
            return 0.25   # Fringe contenders — often miss cut at Augusta
        else:
            return 0.08   # Essentially no chance; standard events are better
    elif type_weight >= 0.75:  # Signature events (~50 best players)
        if world_rank <= 50:
            return 1.00
        elif world_rank <= 100:
            return 0.55
        else:
            return 0.25
    else:
        return 1.00   # Standard / opposite — open fields, no adjustment


def _player_expected_prize(
    world_rank: float,
    purse: float,
    type_weight: float,
    probs: dict | None = None,
) -> float:
    """
    Estimate expected prize money for a player at an event.

    If *probs* is provided (calibrated model probabilities for the current
    week), those are used directly — no rank proxy, no field difficulty
    adjustment needed because the model already accounts for field strength.

    If *probs* is None (future events), the rank proxy is used, then
    multiplied by a field difficulty factor to correct for the fact that
    weaker players have much lower realistic odds at elite fields.

    Prize curve (PGA Tour structure):
        Win:    18% of purse
        T2–5:    6.8%
        T6–10:   3.0%
        T11–20:  1.7%
        T21–cut: 0.6%
    """
    if probs is not None:
        win_prob   = max(0.0, float(probs.get("win_prob",   0) or 0))
        top5_prob  = max(win_prob, float(probs.get("top5_prob",  0) or 0))
        top10_prob = max(top5_prob, float(probs.get("top10_prob", 0) or 0))
        top20_prob = max(top10_prob, float(probs.get("top20_prob", 0) or 0))
        cut_prob   = max(top20_prob, min(0.98, float(probs.get("cut_prob", 0) or 0)))
        field_mult = 1.0  # actual model handles field strength
    else:
        if world_rank <= 0:
            world_rank = 1.0
        win_prob   = min(0.18, 0.60 / math.sqrt(world_rank))
        top5_prob  = min(0.50, win_prob * 3.5)
        top10_prob = min(0.70, win_prob * 6.0)
        top20_prob = min(0.85, win_prob * 10.0)
        cut_prob   = min(0.95, win_prob * 14.0)
        field_mult = _field_difficulty_mult(world_rank, type_weight)

    p_win     = win_prob
    p_t2_5    = max(0.0, top5_prob  - win_prob)
    p_t6_10   = max(0.0, top10_prob - top5_prob)
    p_t11_20  = max(0.0, top20_prob - top10_prob)
    p_t21_cut = max(0.0, cut_prob   - top20_prob)

    base = purse * (
        p_win     * PAYOUT_WIN     +
        p_t2_5    * PAYOUT_T2_5   +
        p_t6_10   * PAYOUT_T6_10  +
        p_t11_20  * PAYOUT_T11_20 +
        p_t21_cut * PAYOUT_T21_CUT
    )
    return base * type_weight * field_mult


def _player_tier(world_rank: float) -> str:
    if world_rank <= 15:
        return "elite"
    if world_rank <= 50:
        return "good"
    return "standard"


def _event_tier(tournament_type: str, purse: float) -> str:
    t = str(tournament_type).lower()
    if "major" in t or "playoff" in t:
        return "premium"
    if "signature" in t or purse >= 18_000_000:
        return "high"
    return "standard"


def _normalize_tournament_name(name: str) -> str:
    """Lowercase, strip punctuation, normalize whitespace for fuzzy name matching."""
    import re
    name = str(name).lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Strip common year-variant suffixes so "Masters Tournament (2020)" matches "The Masters"
    name = re.sub(r"\(\d{4}\)$", "", name).strip()
    # Strip leading "the "
    name = re.sub(r"^the ", "", name).strip()
    return name


def _load_course_fit(
    schedule: pd.DataFrame,
) -> tuple[dict[str, str], dict[tuple[str, str], float], dict[tuple[str, str], tuple[int, int]]]:
    """
    Returns:
        tid_to_course  — {tournament_id: course_key}  for 2026 schedule entries
        course_fit_map — {(name_key, course_key): course_sg_total_weighted}

    Course key resolution strategy:
        Historical form file has (tournament_id, course_key) pairs for years
        2016-2025.  Those IDs are year-prefixed (R2021014) so we can't match
        directly to 2026 IDs.  Instead we build a normalized tournament_name
        → course_key index from history, then look up 2026 schedule events by
        tournament name.  Works for recurring events (Masters, US Open, RBC, …).
    """
    tid_to_course: dict[str, str] = {}
    course_fit_map: dict[tuple[str, str], float] = {}
    course_rounds_map: dict[tuple[str, str], tuple[int, int]] = {}

    # Build tournament_name_normalized → course_key from historical form file
    name_to_course: dict[str, str] = {}
    if TOURNAMENT_COURSE_FILE.exists():
        try:
            tcf = pd.read_csv(
                TOURNAMENT_COURSE_FILE,
                usecols=["tournament_id", "tournament_name", "course_key"],
            ).drop_duplicates("tournament_id")
            for _, row in tcf.iterrows():
                nk = _normalize_tournament_name(str(row["tournament_name"]))
                ck = str(row["course_key"])
                # Most recent record wins (later year = most current course)
                name_to_course[nk] = ck
        except Exception:
            pass

    # Map 2026 schedule tournament_ids → course_key via tournament name
    if "tournament_id" in schedule.columns and name_to_course:
        for _, row in schedule.iterrows():
            tid = str(row.get("tournament_id", ""))
            if not tid:
                continue
            nk = _normalize_tournament_name(str(row["tournament_name"]))
            if nk in name_to_course:
                tid_to_course[tid] = name_to_course[nk]
            else:
                # Partial match: any stored name that is a substring of the
                # schedule name or vice versa
                for stored_nk, ck in name_to_course.items():
                    if stored_nk in nk or nk in stored_nk:
                        tid_to_course[tid] = ck
                        break

    # Load per-player course performance
    if COURSE_PERF_FILE.exists():
        try:
            cp = pd.read_csv(
                COURSE_PERF_FILE,
                usecols=["player_name", "course_key", "course_sg_total_weighted",
                         "course_sg_total_rounds", "starts"],
            )
            # Multiple rows can exist per (player, course) — keep the one with
            # the most SG rounds so the recency-weighted value uses full history.
            cp["_rounds"] = cp["course_sg_total_rounds"].fillna(0).astype(int)
            cp = cp.sort_values("_rounds").drop_duplicates(
                subset=["player_name", "course_key"], keep="last"
            )
            for _, row in cp.iterrows():
                nk  = _name_key(str(row["player_name"]))
                ck  = str(row["course_key"])
                sg  = row["course_sg_total_weighted"]
                if sg is not None and not pd.isna(sg):
                    course_fit_map[(nk, ck)] = float(sg)
                rounds = int(row["course_sg_total_rounds"]) if not pd.isna(row.get("course_sg_total_rounds", float("nan"))) else 0
                starts = int(row["starts"]) if not pd.isna(row.get("starts", float("nan"))) else 0
                course_rounds_map[(nk, ck)] = (rounds, starts)
        except Exception:
            pass

    return tid_to_course, course_fit_map, course_rounds_map


def _load_historical_fields() -> dict[str, set[str]]:
    """
    Build a map of normalized tournament_name → set of name_key strings for
    every player who appeared in that tournament in 2025.

    This is used to determine whether a tracker player likely qualifies for
    a future event.  The Masters, US Open, PGA Championship etc. have strict
    qualification criteria — a player who wasn't in last year's field probably
    doesn't qualify.  Standard events are open fields so everyone is considered
    qualified by default.

    Returns: {normalized_tournament_name: {name_key, ...}}
    """
    fields: dict[str, set[str]] = {}
    if not LEADERBOARDS_2025_FILE.exists():
        return fields
    try:
        lb = pd.read_csv(
            LEADERBOARDS_2025_FILE,
            usecols=["tournament_name", "player_name"],
        )
        for _, row in lb.iterrows():
            tnorm = _normalize_tournament_name(str(row["tournament_name"]))
            nk    = _name_key(str(row["player_name"]))
            fields.setdefault(tnorm, set()).add(nk)
    except Exception:
        pass
    return fields


def get_optimal_season_plan(
    player_strategy: dict,
) -> tuple[dict, dict]:
    """
    Greedy week-by-week season allocation optimizer.

    Assigns each tracker player to their peak event weeks, respecting:
      - Max 3 players per event (the fantasy league weekly pick cap)
      - Each player assigned to at most uses_left events

    Uses each player's full ``candidate_events`` list (not just ``best_events``)
    so that if a player's top event fills up they can fall back to their next
    best option — rather than simply being left unassigned.

    Greedy ordering: highest adjusted-EV assignment is made first.  This means
    the two elite players both wanting The Masters get it over a mid-tier player
    who also ranks it #1 but has lower absolute EV there.

    Returns
    -------
    plan : {event_name: {"week", "date", "tier", "type", "assigned": [], "overflow": []}}
        Each event that appears in at least one player's candidate list, sorted
        chronologically.  ``overflow`` = players who wanted this event but couldn't
        get a slot (either already assigned their uses elsewhere or event was full).

    conflicts : {event_name: {"wants", "assigned", "overflow", "week", "date", "tier"}}
        Subset of plan where more than MAX_PLAYERS_PER_EVENT players wanted a slot.
        These are the events where you'll need to make hard choices.
    """
    from collections import defaultdict

    # Build flat candidate list: one entry per (player, event) pair
    candidates: list[dict] = []
    for player, info in player_strategy.items():
        for ev_info in info.get("candidate_events", info.get("best_events", [])):
            candidates.append({
                "player":     player,
                "event":      ev_info["name"],
                "ev":         ev_info.get("ev", 0),
                "week":       ev_info.get("week", 0),
                "start_date": ev_info.get("start_date", ""),
                "tier":       ev_info.get("tier", ""),
                "type":       ev_info.get("type", ""),
            })

    # Highest EV first — greedy "best assignment wins"
    candidates.sort(key=lambda x: x["ev"], reverse=True)

    event_slots:  dict[str, list[str]] = defaultdict(list)   # event → [assigned]
    player_slots: dict[str, int]       = defaultdict(int)    # player → # assigned
    wants:        dict[str, list[str]] = defaultdict(list)   # event → [all wanting]
    event_meta:   dict[str, dict]      = {}                  # event → {week,date,tier,type}

    for c in candidates:
        player    = c["player"]
        event     = c["event"]
        uses_left = player_strategy[player]["uses_left"]

        if event not in event_meta:
            event_meta[event] = {
                "week":  c["week"],
                "date":  c["start_date"],
                "tier":  c["tier"],
                "type":  c["type"],
            }

        # Only count as "wanting" if they still have a use available here
        # (prevents players from cluttering wants lists for events they can't play)
        if player_slots[player] < uses_left:
            wants[event].append(player)
            if len(event_slots[event]) < MAX_PLAYERS_PER_EVENT:
                event_slots[event].append(player)
                player_slots[player] += 1

    # Sort events chronologically by week
    sorted_events = sorted(event_slots.keys(),
                           key=lambda e: event_meta.get(e, {}).get("week", 0))

    plan: dict[str, dict] = {}
    for event_name in sorted_events:
        assigned  = event_slots[event_name]
        all_wants = wants[event_name]
        overflow  = [p for p in all_wants if p not in assigned]
        meta      = event_meta.get(event_name, {})
        plan[event_name] = {
            "week":     meta.get("week", 0),
            "date":     meta.get("date", ""),
            "tier":     meta.get("tier", ""),
            "type":     meta.get("type", ""),
            "assigned": assigned,
            "overflow": overflow,
        }

    # Conflicts: events with more than the weekly cap wanting a slot
    conflicts: dict[str, dict] = {}
    for event_name, all_wants in wants.items():
        if len(all_wants) > MAX_PLAYERS_PER_EVENT:
            assigned = event_slots[event_name]
            meta     = event_meta.get(event_name, {})
            conflicts[event_name] = {
                "week":     meta.get("week", 0),
                "date":     meta.get("date", ""),
                "tier":     meta.get("tier", ""),
                "wants":    all_wants,
                "assigned": assigned,
                "overflow": [p for p in all_wants if p not in assigned],
            }

    return plan, conflicts


def get_season_strategy(
    current_week: int | None = None,
) -> dict:
    """
    Build a full season strategy dict for the current user.

    Returns
    -------
    {
        "current_event": {...},
        "premium_events": [...],
        "player_strategy": {
            "Scottie Scheffler": {
                "uses_left": 2,
                "world_rank": 1,
                "tier": "elite",
                "best_events": [...],
                "this_week_ev": float,      # from actual predictions if available
                "this_week_probs": dict,    # win/top10/cut probs this week
                "use_this_week": bool,
                "save_signal": bool,
                "reason": str,
            }, ...
        },
        "budget": {...},
        "this_week_verdict": str,
    }
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # ── Load schedule ─────────────────────────────────────────────────────────
    if not SCHEDULE_FILE.exists():
        return {"error": "Schedule file not found"}
    sched = pd.read_csv(SCHEDULE_FILE)
    sched["purse_num"]   = sched["purse"].apply(_parse_purse)
    sched["type_lower"]  = sched["tournament_type"].str.lower().fillna("standard")
    sched["type_weight"] = sched["type_lower"].apply(
        lambda t: next((v for k, v in TYPE_WEIGHT.items() if k in t), 0.45)
    )
    sched["event_score"] = sched["purse_num"] * sched["type_weight"]
    sched["event_tier"]  = sched.apply(
        lambda r: _event_tier(r["tournament_type"], r["purse_num"]), axis=1
    )

    current_events = sched[
        (sched["start_date"] <= today) & (sched["end_date"] >= today)
    ]
    future_events = sched[sched["start_date"] > today].sort_values("start_date")

    # Between tournaments: fall back to next upcoming event so strategy
    # still computes with the correct purse/tier instead of going blank.
    current_event_row = (
        current_events.iloc[0] if not current_events.empty
        else future_events.iloc[0] if not future_events.empty
        else None
    )
    if current_week is None and current_event_row is not None:
        current_week = int(current_event_row["week"])

    weeks_remaining = len(sched[sched["start_date"] >= today])

    # ── Course fit lookup ─────────────────────────────────────────────────────
    tid_to_course, course_fit_map, course_rounds_map = _load_course_fit(sched)

    # ── Historical field lookup (2025) ────────────────────────────────────────
    # Used to flag whether a tracker player was in last year's field for each
    # future event.  Premium events (Majors, Signatures) have restricted fields
    # so this is a meaningful qualification signal.  Standard events are open
    # so qualification is assumed True when no 2025 data exists.
    hist_fields = _load_historical_fields()

    # Attach course_key to each future event
    premium_events = []
    for _, ev in future_events.head(15).iterrows():
        tid  = str(ev.get("tournament_id", ""))
        ck   = tid_to_course.get(tid, "")
        premium_events.append({
            "week":       int(ev["week"]),
            "name":       str(ev["tournament_name"]),
            "type":       str(ev["tournament_type"]),
            "purse":      float(ev["purse_num"]),
            "tier":       str(ev["event_tier"]),
            "score":      float(ev["event_score"]),
            "start_date": str(ev["start_date"]),
            "tid":        tid,
            "course_key": ck,
        })

    # ── Load usage tracker ────────────────────────────────────────────────────
    if not USAGE_TRACKER.exists():
        return {"error": "Usage tracker not found"}
    with open(USAGE_TRACKER) as f:
        usage_data = json.load(f)

    picks = usage_data.get("picks", {})
    uses_remaining_total = sum(
        int(info.get("remaining_uses", 0)) for info in picks.values()
    )
    picks_needed      = weeks_remaining * 3
    new_players_needed = max(0, picks_needed - uses_remaining_total)

    # ── World rank map (OWGR → all ~500 players) ──────────────────────────────
    rank_map: dict[str, float] = {}

    if OWGR_FILE.exists():
        try:
            owgr = pd.read_csv(OWGR_FILE)
            for _, row in owgr.iterrows():
                key  = _name_key(str(row["player_name"]))
                rank = float(row.get("world_rank") or 200)
                rank_map[key] = rank if not pd.isna(rank) else 200.0
        except Exception:
            pass

    # ── Career SG from course performance (covers all players, not just field) ─
    # overall_sg_total_avg is the player's strokes-gained vs tour average
    # aggregated across all tracked venues — a stable long-run strength signal.
    career_sg_map: dict[str, float] = {}  # name_key → overall_sg_total_avg
    if COURSE_PERF_FILE.exists():
        try:
            cp_sg = pd.read_csv(
                COURSE_PERF_FILE,
                usecols=["player_name", "overall_sg_total_avg"],
            ).drop_duplicates("player_name")
            for _, row in cp_sg.iterrows():
                nk = _name_key(str(row["player_name"]))
                v  = row["overall_sg_total_avg"]
                if not pd.isna(v):
                    career_sg_map[nk] = float(v)
        except Exception:
            pass



    # --- DG Skill Ratings -- current SG for all ~800 ---- 
    dg_sg_map: dict[str, float] = {}
    if DG_SKILL_FILE.exists():
        try:
            dg_sr = pd.read_csv(DG_SKILL_FILE, usecols=['player_name', 'dg_skill_total'])
            for _, row in dg_sr.iterrows():
                nk = _name_key(str(row['player_name']))
                v  = row['dg_skill_total']
                if not pd.isna(v):
                    dg_sg_map[nk] = float(v)
        except Exception:
            pass

    
    
    # ── DG Rankings — more current world rank for all players ─────────────────
    dg_rank_map: dict[str, float] = {}
    if DG_RANKINGS_FILE.exists():
        try:
            dg_rk = pd.read_csv(DG_RANKINGS_FILE, usecols=["player_name", "owgr_rank"])
            for _, row in dg_rk.iterrows():
                nk = _name_key(str(row["player_name"]))
                v  = row["owgr_rank"]
                if not pd.isna(v):
                    dg_rank_map[nk] = float(v)
        except Exception:
            pass
        
        
    # --- DG Pre-Tournament Probs -- for current week blend -- 
    dg_pred_map: dict[str, dict] = {}
    if DG_PRE_TOURNEY_FILE.exists():
        try:
            dg_pt = pd.read_csv(DG_PRE_TOURNEY_FILE)
            dg_pt = dg_pt[dg_pt["model"] == "baseline_history_fit"].copy()
            # Only useful for individual events (team names have "/" separator)
            dg_pt = dg_pt[~dg_pt["team_name"].str.contains("/", na=False)]
            
            
            for _, row in dg_pt.iterrows():
                nk = _name_key(str(row['team_name']))
                dg_pred_map[nk] = {
                    'win_prob':   float(row.get('win',      0) or 0),
                    'top10_prob': float(row.get('top_10',   0) or 0),
                    'cut_prob':   float(row.get('make_cut', 0) or 0),
                }
                
        except Exception:
            pass
            






    # ── 2026 season results — cut rate and recent form ────────────────────────
    # Compute per-player: tournaments played, cut rate, avg finishing position.
    # This captures in-season form for ALL players (not just current field).
    season_form_map: dict[str, dict] = {}  # name_key → {cuts_made, events, avg_pos, cut_rate}
    if LEADERBOARDS_FILE.exists():
        try:
            lb = pd.read_csv(LEADERBOARDS_FILE)
            for pname, grp in lb.groupby("player_name"):
                nk     = _name_key(str(pname))
                events = len(grp)
                cuts   = (grp["rounds_played"] >= 3).sum()  # made cut = played R3+
                positions = grp["position"].replace({"CUT": 999, "WD": 999, "DQ": 999}).infer_objects(copy=False)
                positions = pd.to_numeric(positions, errors="coerce").fillna(999)
                avg_pos   = float(positions[positions < 999].mean()) if (positions < 999).any() else 999.0
                season_form_map[nk] = {
                    "events":    int(events),
                    "cuts_made": int(cuts),
                    "cut_rate":  round(cuts / events, 2) if events > 0 else 0.0,
                    "avg_pos":   round(avg_pos, 1),
                }
        except Exception:
            pass

    # ── Current week predictions — calibrated probs + rich form signals ───────
    sg_map:   dict[str, float] = {}   # season_sg_total for in-field players
    form_map: dict[str, dict]  = {}   # recent form signals for in-field players
    pred_map: dict[str, dict]  = {}   # calibrated probs for in-field players

    if PREDICTIONS_FILE.exists():
        try:
            preds = pd.read_csv(PREDICTIONS_FILE)
            for _, row in preds.iterrows():
                key = _name_key(str(row["player_name"]))
                
                
                
                

                # Supplement rank_map for players not in OWGR file
                if key not in rank_map and "world_rank" in preds.columns:
                    rnk = float(row.get("world_rank") or 200)
                    rank_map[key] = rnk if not pd.isna(rnk) else 200.0

                def _f(col: str, default: float = 0.0) -> float:
                    v = row.get(col, default)
                    try:
                        return float(v) if v is not None and not pd.isna(v) else default
                    except Exception:
                        return default

                sg_map[key] = _f("season_sg_total")

                # Rich form signals — used in card display and EV adjustment
                form_map[key] = {
                    "recent_sg":       _f("recent_sg_weighted"),
                    "sg_trend":        _f("recent_sg_trend"),
                    "tournaments":     int(_f("sg_blend_tournaments")),
                    "predictive_sg":   _f("predictive_sg_weighted"),
                    "hist_cut_rate":   _f("hist_cut_rate"),
                    "hist_top10s":     int(_f("hist_top10s")),
                    "course_fit":      _f("course_fit"),
                }

                pred_map[key] = {
                    "win_prob":   _f("win_prob_calibrated"),
                    "top5_prob":  _f("top5_prob_calibrated"),
                    "top10_prob": _f("top10_prob_calibrated"),
                    "top20_prob": _f("top20_prob_calibrated"),
                    "cut_prob":   _f("cut_prob"),
                }
        except Exception:
            pass

    # ── Key resolver: tracker uses last-name-only, data maps use full names ──────
    # Build a single-token -> full-key lookup so "McIlroy" resolves to
    # "mcilroy rory" instead of silently missing every lookup.
    _all_known_keys: set = (
        set(pred_map) | set(season_form_map) | set(rank_map) |
        set(sg_map)   | set(career_sg_map)   | set(dg_sg_map)
    )
    _pred_keys: set = set(pred_map)   # closure for abbreviated-name resolution
    _last_to_full: dict = {}
    for _fk in _all_known_keys:
        for _tok in _fk.split():
            if _tok not in _last_to_full:
                _last_to_full[_tok] = _fk

    def _resolve_key(raw_key: str) -> str:
        if raw_key in _all_known_keys:
            return raw_key
        if " " not in raw_key:
            return _last_to_full.get(raw_key, raw_key)
        # Handle abbreviated first names: "fitzpatrick m" → "fitzpatrick matt"
        # Separate long tokens (real names) from single-letter initials
        tokens = raw_key.split()
        long_tokens = [t for t in tokens if len(t) > 1]
        initials    = [t for t in tokens if len(t) == 1]
        if long_tokens and initials:
            candidates = [
                fk for fk in _all_known_keys
                if all(lt in fk.split() for lt in long_tokens)
                and all(
                    any(ft.startswith(it) for ft in fk.split() if ft not in long_tokens)
                    for it in initials
                )
            ]
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                # Multiple candidates (e.g. "Matt" vs "Matthew" from different sources)
                # Prefer the pred_map entry (most authoritative / current week)
                pred_cands = [c for c in candidates if c in _pred_keys]
                if len(pred_cands) == 1:
                    return pred_cands[0]
        return raw_key

    # ── Per-player strategy ───────────────────────────────────────────────────
    player_strategy: dict = {}

    for player_name, info in picks.items():
        uses_left = int(info.get("remaining_uses", 0))
        if uses_left <= 0:
            continue

        key = _resolve_key(_name_key(player_name))


        _szn_check = season_form_map.get(key, {})
        _in_field_check = key in pred_map
        if _szn_check.get("events", 0) == 0 and not _in_field_check:
            continue
        wr = max(1.0, float(rank_map.get(key) or dg_rank_map.get(key) or 200.0))

        # Season SG: prefer in-field prediction data, fall back to DG skill rating
        sg_season = sg_map.get(key, 0.0)
        if sg_season == 0.0:
            sg_season = dg_sg_map.get(key, 0.0)
        sg_career = career_sg_map.get(key, dg_sg_map.get(key, 0.0))
        # Season form data from 2026 leaderboards
        szn = season_form_map.get(key, {})
        szn_events   = szn.get("events", 0)
        szn_cut_rate = szn.get("cut_rate", 0.0)
        szn_avg_pos  = szn.get("avg_pos", 999.0)

        # Form signals from this week's predictions (in-field only)
        fm = form_map.get(key, {})
        recent_sg     = fm.get("recent_sg",     sg_season)
        sg_trend      = fm.get("sg_trend",      0.0)
        # sg_blend_tournaments counts only events where we have actual SG data
        # from the prediction model. Do NOT fall back to szn_events (leaderboard
        # count) — that would give false confidence when sg_season=0 for non-field players.
        tournaments   = fm.get("tournaments",   0)
        predictive_sg = fm.get("predictive_sg", sg_career)
        hist_cut_rate = fm.get("hist_cut_rate", szn_cut_rate)

        # Effective rank: blends world rank, season SG, career SG
        eff_rank = _effective_rank(wr, sg_season, sg_career, tournaments)
        tier     = _player_tier(eff_rank)

        # ── This week's EV: actual model probs if in field ────────────────────
        # This week: blend our calibrated probs with DG's (60/40) when both available
        this_week_probs = pred_map.get(key)
        dg_probs = dg_pred_map.get(key)
        if this_week_probs and dg_probs:
            this_week_probs = {
                "win_prob":   0.60 * this_week_probs["win_prob"]   + 0.40 * dg_probs["win_prob"],
                "top5_prob":  this_week_probs.get("top5_prob", 0),
                "top10_prob": 0.60 * this_week_probs["top10_prob"] + 0.40 * dg_probs["top10_prob"],
                "top20_prob": this_week_probs.get("top20_prob", 0),
                "cut_prob":   0.60 * this_week_probs["cut_prob"]   + 0.40 * dg_probs["cut_prob"],
            }

        # ── This week's EV ────────────────────────────────────────────────────
        if current_event_row is not None:
            this_week_ev = _player_expected_prize(
                eff_rank,
                float(current_event_row["purse_num"]),
                float(current_event_row["type_weight"]),
                probs=this_week_probs,
            )
        else:
            this_week_ev = 0.0

        # ── Current venue fit ─────────────────────────────────────────────────
        _cur_tid = str(current_event_row.get("tournament_id", "")) if current_event_row is not None else ""
        _cur_ck  = tid_to_course.get(_cur_tid, "")
        current_course_sg     = course_fit_map.get((key, _cur_ck), 0.0) if _cur_ck else 0.0
        _cr_rounds, _cr_starts = course_rounds_map.get((key, _cur_ck), (0, 0)) if _cur_ck else (0, 0)
        # Flag as meaningful when there's real historical evidence.
        # 3+ rounds covers a full start or a WD-after-R3 scenario.
        # Pre-SG-era courses have rounds=0 but ≥2 starts is still evidence.
        current_course_sig = (
            abs(current_course_sg) >= 0.25
            and (_cr_rounds >= 3 or (_cr_rounds == 0 and _cr_starts >= 2))
        )

        # ── Future event scores ───────────────────────────────────────────────
        # Base EV uses effective rank (blended SG + world rank).
        # Course-fit multiplier from historical venue SG.
        # Recent form multiplier: hot/cold streaks affect near-term events.
        # Qualification: for premium/high events, check 2025 field membership.
        #   If the player wasn't in last year's field, apply a heavy discount
        #   (they likely don't qualify) so these events don't dominate their plan.
        event_scores = []
        today_dt = datetime.strptime(today, "%Y-%m-%d")

        for ev in premium_events:
            tw       = ev["score"] / ev["purse"] if ev["purse"] > 0 else 0.45
            base_ev  = _player_expected_prize(eff_rank, ev["purse"], tw)

            # Course-fit multiplier
            ck         = ev.get("course_key", "")
            course_sg  = course_fit_map.get((key, ck), 0.0) if ck else 0.0
            course_mult = max(COURSE_FIT_MIN,
                              min(COURSE_FIT_MAX, 1.0 + COURSE_FIT_SCALE * course_sg))

            # Recent form multiplier — decays to zero at 8+ weeks out
            try:
                ev_dt      = datetime.strptime(ev["start_date"], "%Y-%m-%d")
                weeks_away = max(0, (ev_dt - today_dt).days / 7)
            except Exception:
                weeks_away = 8.0
            trend_decay  = max(0.0, 1.0 - weeks_away / 8.0)
            trend_mult   = 1.0 + 0.04 * float(sg_trend) * trend_decay
            trend_mult   = max(0.80, min(1.20, trend_mult))

            # Qualification check against 2025 field
            # Standard events are open — always qualified.
            # Premium/high events use historical field as proxy for eligibility.
            ev_name_norm = _normalize_tournament_name(ev["name"])
            hist_field   = hist_fields.get(ev_name_norm, set())
            if hist_field:
                qualified = key in hist_field
            else:
                # No 2025 data for this tournament — assume qualified
                # (new event or name mismatch; don't penalise)
                qualified = True

            # Non-qualified players get a 85% EV discount for premium events.
            # Standard events: no discount (open fields, anyone can enter).
            if not qualified and ev["tier"] in ("premium", "high"):
                qual_mult = 0.15
            else:
                qual_mult = 1.0

            adj_ev = base_ev * course_mult * trend_mult * qual_mult

            event_scores.append({
                "name":        ev["name"],
                "week":        ev["week"],
                "type":        ev["type"],
                "tier":        ev["tier"],
                "ev":          round(adj_ev, 0),
                "purse":       ev["purse"],
                "start_date":  ev["start_date"],
                "course_sg":   round(course_sg, 2),
                "course_mult": round(course_mult, 3),
                "trend_mult":  round(trend_mult, 3),
                "qualified":   qualified,
                "weeks_away":  round(weeks_away, 1),
            })

        event_scores.sort(key=lambda x: x["ev"], reverse=True)
        best_events = event_scores[:uses_left]

        # Keep a deeper candidate list for the season-plan optimizer.
        # The planner may need to assign a player to their 2nd or 3rd choice
        # if their top event is already full (>3 players wanted it).
        candidate_events = event_scores[:max(uses_left * 3, 6)]

        # ── Use-this-week decision ────────────────────────────────────────────
        # Dynamic threshold: as uses_left/weeks_remaining shrinks (pressure rises),
        # lower the bar so we don't save forever and waste picks.
        # _urgency = 1.0 means "1 use per 1 week remaining" → threshold = 0.55 (minimum)
        # _urgency = 0.0 means "lots of uses left" → threshold stays near 0.90
        _urgency = uses_left / max(1, weeks_remaining)
        _use_threshold = max(0.55, 0.90 - 0.50 * min(1.0, _urgency))

        best_ev_threshold = best_events[-1]["ev"] if best_events else 0.0
        best_single_ev    = best_events[0]["ev"]  if best_events else 0.0
        use_this_week = (
            current_event_row is not None
            and this_week_ev >= best_ev_threshold * _use_threshold
            and this_week_probs is not None
        )

        # ── Opportunity cost ──────────────────────────────────────────────────
        # How much EV are you giving up by using this player THIS week
        # instead of their single best remaining event?
        opp_cost_ev  = max(0.0, best_single_ev - this_week_ev)
        opp_cost_pct = (opp_cost_ev / best_single_ev * 100) if best_single_ev > 0 else 0.0

        # ── Hot streak detection ──────────────────────────────────────────────
        # A player is "hot" when recent form is surging above their career
        # baseline AND the trend direction is positive.  We use both signals
        # together because:
        #   - sg_trend alone can be noisy (one good round spikes the trend)
        #   - recent_sg alone might just reflect a good career baseline
        #   - Together they confirm: this player was good historically AND is
        #     getting even better right now
        #
        # When hot, we loosen the EV threshold from 90% → 65%, meaning we'll
        # recommend using them now even if a moderately better event is coming,
        # because that form advantage may not persist 4–6 weeks.
        is_hot_streak    = False
        hot_streak_override = False

        if this_week_probs is not None and uses_left >= 1:
            _career_baseline = sg_career if sg_career != 0.0 else sg_season
            if (sg_trend >= HOT_STREAK_SG_TREND and
                    recent_sg >= _career_baseline + HOT_STREAK_RECENT_ADV):
                is_hot_streak = True
                if not use_this_week:
                    if this_week_ev >= best_ev_threshold * HOT_STREAK_EV_RATIO:
                        use_this_week       = True
                        hot_streak_override = True

        # ── Venue fit clause (injected into reason when meaningful) ──────────
        _venue_clause = ""
        if current_course_sig:
            _vdir = "boost" if current_course_sg > 0 else "miss"
            _vev  = f"{_cr_rounds} rounds" if _cr_rounds >= 4 else f"{_cr_starts} starts"
            _venue_clause = (
                f" Venue {_vdir}: {current_course_sg:+.2f} SG at this course ({_vev})."
            )
        # Best future event venue fit (only mention if it's better than current)
        _best_venue_clause = ""
        if best_events:
            _bv_sg = best_events[0].get("course_sg", 0.0)
            if abs(_bv_sg) >= 0.25 and _bv_sg > current_course_sg + 0.2:
                _best_venue_clause = f" {best_events[0]['name']}: {_bv_sg:+.2f} SG historically."

        # ── Reason string ─────────────────────────────────────────────────────
        if use_this_week and hot_streak_override:
            _cb = sg_career if sg_career != 0.0 else sg_season
            wp  = this_week_probs["win_prob"]  * 100
            t10 = this_week_probs["top10_prob"] * 100
            reason = (
                f"Hot streak: SG {recent_sg:+.2f} vs career {_cb:+.2f} "
                f"(+{recent_sg - _cb:.2f}/rnd), trend rising. "
                f"Form is perishable — use now while it lasts. "
                f"{wp:.1f}% win / {t10:.0f}% top-10.{_venue_clause}"
            )
        elif use_this_week:
            wp  = this_week_probs["win_prob"]  * 100
            t10 = this_week_probs["top10_prob"] * 100
            _opp_str = (
                f" Opportunity cost vs best event: {opp_cost_ev:,.0f} EV ({opp_cost_pct:.0f}%) — within range."
                if opp_cost_ev > 0 else ""
            )
            reason = (
                f"{wp:.1f}% win / {t10:.0f}% top-10 this week "
                f"({this_week_ev:,.0f} EV). Ranks in top-{uses_left} windows.{_opp_str}{_venue_clause}"
            )
        elif best_events:
            _best = best_events[0]
            _best_name = _best["name"]
            _best_ev   = _best["ev"]
            if this_week_probs:
                wp  = this_week_probs["win_prob"]  * 100
                t10 = this_week_probs["top10_prob"] * 100
                reason = (
                    f"This week: {this_week_ev:,.0f} EV ({wp:.1f}% win / {t10:.0f}% top-10).{_venue_clause} "
                    f"{_best_name}: {_best_ev:,.0f} EV.{_best_venue_clause} "
                    f"Save — opportunity cost of using now: {opp_cost_ev:,.0f} EV ({opp_cost_pct:.0f}% better later)."
                )
            else:
                reason = (
                    f"Not in this week's field.{_venue_clause} "
                    f"Best window: {_best_name} ({_best_ev:,.0f} EV).{_best_venue_clause}"
                )
        else:
            reason = f"Limited future opportunities — consider using now.{_venue_clause}"

        upcoming_premium = [e for e in best_events if e["tier"] == "premium"]
        save_signal = (
            tier == "elite"
            and not use_this_week
            and len(upcoming_premium) > 0
        )

        player_strategy[player_name] = {
            "uses_left":           uses_left,
            "world_rank":          round(wr),
            "eff_rank":            round(eff_rank),
            "sg_season":           round(sg_season, 2),
            "sg_career":           round(sg_career, 2),
            "sg_trend":            round(sg_trend, 3),
            "recent_sg":           round(recent_sg, 2),
            "predictive_sg":       round(predictive_sg, 2),
            "tournaments":         tournaments,
            "hist_cut_rate":       round(hist_cut_rate, 2),
            "szn_cut_rate":        round(szn_cut_rate, 2),
            "szn_events":          szn_events,
            "szn_avg_pos":         szn_avg_pos,
            "tier":                tier,
            "best_events":         best_events,
            "candidate_events":    candidate_events,
            "this_week_ev":        round(this_week_ev, 0),
            "best_future_ev":      round(best_single_ev, 0),
            "opportunity_cost_ev": round(opp_cost_ev, 0),
            "opportunity_cost_pct": round(opp_cost_pct, 1),
            "this_week_probs":     this_week_probs,
            "in_field":            this_week_probs is not None,
            "use_this_week":       use_this_week and (this_week_probs is not None),
            "save_signal":         save_signal,
            "is_hot_streak":       is_hot_streak,
            "hot_streak_override": hot_streak_override,
            "current_course_sg":   round(current_course_sg, 2),
            "current_course_rounds": _cr_rounds,
            "current_course_starts": _cr_starts,
            "current_course_sig":  current_course_sig,
            "reason":              reason,
        }

    # ── This-week verdict ─────────────────────────────────────────────────────
    this_week_verdict = ""
    if current_event_row is not None:
        c_tier  = str(current_event_row.get("event_tier", "standard"))
        c_name  = str(current_event_row["tournament_name"])
        c_purse = float(current_event_row["purse_num"])

        next_4 = future_events.head(4)
        premium_soon = next_4[next_4["event_tier"] == "premium"]

        if c_tier == "premium":
            this_week_verdict = f"{c_name} is a premium event — use your best available players."
        elif not premium_soon.empty:
            names = " + ".join(premium_soon["tournament_name"].tolist())
            this_week_verdict = (
                f"{c_name} is a {c_tier} event (${c_purse/1e6:.1f}M). "
                f"Premium event(s) coming soon: {names}. "
                f"Save elite players — use good-tier picks here."
            )
        else:
            this_week_verdict = (
                f"{c_name} (${c_purse/1e6:.1f}M). "
                f"No premium events in the next 4 weeks — fine to use top players."
            )

    # ── Optimal weekly lineup ─────────────────────────────────────────────────
    # Pick the best 3 in-field players by this_week_ev, respecting uses_left.
    # Also compute alt lineups — what does it cost to save each top pick?
    _in_field = sorted(
        [(n, p) for n, p in player_strategy.items()
         if p.get("in_field") and p.get("uses_left", 0) > 0],
        key=lambda x: x[1]["this_week_ev"], reverse=True,
    )
    _top3 = _in_field[:3]
    _top3_ev = sum(p["this_week_ev"] for _, p in _top3)

    _lineup_alts: dict[str, dict] = {}
    for _save_name, _ in _top3:
        _alt = [(n, p) for n, p in _in_field if n != _save_name][:3]
        _alt_ev = sum(p["this_week_ev"] for _, p in _alt)
        _lineup_alts[_save_name] = {
            "players":  [n for n, _ in _alt],
            "total_ev": round(_alt_ev),
            "ev_cost":  round(_top3_ev - _alt_ev),
        }

    weekly_lineup = {
        "players": [
            {
                "name":       n,
                "ev":         p["this_week_ev"],
                "tier":       p["tier"],
                "uses_left":  p["uses_left"],
                "win_prob":   round(p["this_week_probs"]["win_prob"] * 100, 1) if p.get("this_week_probs") else 0,
                "top10_prob": round(p["this_week_probs"]["top10_prob"] * 100, 1) if p.get("this_week_probs") else 0,
                "course_sg":  p.get("current_course_sg", 0.0),
                "course_sig": p.get("current_course_sig", False),
            }
            for n, p in _top3
        ],
        "total_ev":  round(_top3_ev),
        "alt_lineups": _lineup_alts,
    }

    # ── Season allocation plan ─────────────────────────────────────────────────
    season_plan, plan_conflicts = get_optimal_season_plan(player_strategy)
    # ── Conflict overflow redirect ─────────────────────────────────────────────
    # If a player's best event is over-subscribed (>3 want it), and this week
    # is a reasonable alternative (≥70% of their best EV), flip them to USE.
    for ev_name, cf_data in plan_conflicts.items():
        for overflow_player in cf_data.get("overflow", []):
            ps = player_strategy.get(overflow_player)
            # Never redirect to USE for players not in this week's field
            if ps is None or ps.get('use_this_week') or not ps.get('in_field', False):
                continue
            
            best_ev = ps["best_events"][-1]["ev"] if ps["best_events"] else 0
            if best_ev > 0 and ps["this_week_ev"] >= best_ev * 0.70:
                player_strategy[overflow_player]["use_this_week"] = True
                player_strategy[overflow_player]["reason"] = (
                    f"Conflict at {ev_name} (too many players targeting it) — "
                    f"redirected here. " + player_strategy[overflow_player].get("reason", "")
                )

    

    return {
        "current_event": {
            "name":  str(current_event_row["tournament_name"]) if current_event_row is not None else "",
            "week":  int(current_event_row["week"]) if current_event_row is not None else 0,
            "purse": float(current_event_row["purse_num"]) if current_event_row is not None else 0,
            "tier":  str(current_event_row.get("event_tier", "")) if current_event_row is not None else "",
            "type":  str(current_event_row["tournament_type"]) if current_event_row is not None else "",
        },
        "premium_events":  premium_events,
        "player_strategy": player_strategy,
        "season_plan":     season_plan,
        "plan_conflicts":  plan_conflicts,
        "weekly_lineup": weekly_lineup,
        "budget": {
            "uses_remaining":    uses_remaining_total,
            "weeks_remaining":   weeks_remaining,
            "picks_needed":      picks_needed,
            "new_players_needed": new_players_needed,
        },
        "this_week_verdict": this_week_verdict,
    }
