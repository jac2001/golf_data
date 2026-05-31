#!/usr/bin/env python3
"""
Generate LLM-powered reasoning for the weekly lineup recommendation.

Two outputs saved to outputs/strategy_reasoning.json:

  weekly_narrative — one 4-6 sentence block covering the optimal 3-player
                     lineup (from lineup_optimizer) + key save advice.
  players          — individual SAVE narratives for notable held-back players.
                     USE NOW players are already covered in the weekly narrative.

Usage:
    python3 scripts/predictions/generate_strategy_reasoning.py
    python3 scripts/predictions/generate_strategy_reasoning.py --top-saves 6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
OUTPUT_FILE  = OUTPUTS_DIR / "strategy_reasoning.json"
CONFIG_FILE  = PROJECT_ROOT / "data" / "config" / "assistant.json"
PREDICTIONS  = OUTPUTS_DIR / "latest_predictions.csv"

LEAGUE_CONTEXT = """
You are advising a player in a season-long fantasy golf league called "Let It Ride."
Rules: each golfer has exactly 3 uses for the entire ~30-week season; you pick 3 golfers
per week; once all 3 uses are spent the golfer is gone. The goal is to maximise total
prize money earned across the season. Saving a use means banking it for a better event.
Premium events (Majors, Signature events) have larger purses and more value per use.
""".strip()


# ── API helpers ────────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key.startswith("sk-ant-"):
        return key
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            key = cfg.get("anthropic_api_key", "")
            if key.startswith("sk-ant-"):
                return key
        except Exception:
            pass
    return ""


# ── Prompt builders ────────────────────────────────────────────────────────────

def _fmt_player_profile(p: dict) -> str:
    """Build a short golf-stats profile for one player from the predictions row."""
    lines = []

    def _fv(key, decimals=1):
        v = p.get(key)
        if v is None: return None
        try: return round(float(v), decimals)
        except (TypeError, ValueError): return None

    def _sv(key):
        v = p.get(key)
        if v is None: return None
        s = str(v).strip()
        return s if s not in ("", "nan", "None") else None

    wr = _fv("world_rank", 0)
    if wr: lines.append(f"World #{int(wr)}")

    # Season SG
    sg_t  = _fv("season_sg_total", 2)
    sg_app = _fv("season_sg_app", 2)
    sg_ott = _fv("season_sg_ott", 2)
    sg_p  = _fv("season_sg_putt", 2)
    if sg_t is not None:
        sg_parts = [f"SG {sg_t:+.2f} total"]
        if sg_app is not None: sg_parts.append(f"approach {sg_app:+.2f}")
        if sg_ott is not None: sg_parts.append(f"driving {sg_ott:+.2f}")
        if sg_p  is not None: sg_parts.append(f"putting {sg_p:+.2f}")
        lines.append(", ".join(sg_parts))

    # Recent form
    scoring = _fv("recent_scoring_avg", 1)
    top10s  = _fv("recent_top10s", 0)
    birdies = _fv("recent_birdie_avg", 1)
    cuts    = _fv("recent_cuts_made", 0)
    last_pos = _fv("last_start_position", 0)
    momentum = _sv("momentum_trend")
    missed   = _fv("missed_cut_last_start", 0)
    form_parts = []
    if scoring is not None: form_parts.append(f"scoring avg {scoring}")
    if top10s  is not None: form_parts.append(f"{int(top10s)} top-10s in recent starts")
    if birdies is not None: form_parts.append(f"{birdies} birdies/round")
    if cuts    is not None: form_parts.append(f"{int(cuts)}/5 cuts made")
    if form_parts: lines.append("Recent: " + "; ".join(form_parts))
    if missed == 1:
        lines.append("Last start: missed cut")
    elif last_pos is not None:
        lines.append(f"Last start: T{int(last_pos)}")
    if momentum and momentum.upper() in ("HOT", "COLD"):
        lines.append(f"Form momentum: {momentum.upper()}")

    # Course history (from lineup_rows — course_sg/course_sig already injected)
    c_sg    = p.get("course_sg")
    c_sig   = p.get("course_sig", False)
    c_starts = _fv("course_starts", 0)
    c_best   = _fv("course_best_finish", 0)
    c_avg    = _fv("course_avg_to_par", 1)
    c_t10r   = _fv("course_top_10_rate", 2)
    if c_starts and c_starts > 0:
        cp = [f"{int(c_starts)} starts here"]
        if c_best is not None: cp.append(f"best T{int(c_best)}")
        if c_avg  is not None: cp.append(f"avg {c_avg:+.1f}/tournament")
        if c_t10r is not None: cp.append(f"{int(c_t10r*100)}% top-10 rate")
        if c_sg and c_sig: cp.append(f"SG {float(c_sg):+.2f} vs field here")
        lines.append("Course history: " + "; ".join(cp))
    elif c_sg and c_sig:
        lines.append(f"Course SG estimate: {float(c_sg):+.2f} vs field")

    return "\n    ".join(lines) if lines else "No profile data"


def _lineup_prompt(
    lineup_rows: list[dict],
    save_players: list[dict],
    current_event: dict,
    budget: dict,
) -> str:
    """Build the prompt for the single weekly lineup narrative."""

    picks_str = ""
    for i, p in enumerate(lineup_rows, 1):
        name    = p["player_name"]
        uses    = int(p.get("remaining_uses", 3))
        profile = _fmt_player_profile(p)
        picks_str += f"  {i}. {name} ({uses} uses left)\n    {profile}\n\n"

    saves_str = ""
    for p in save_players[:3]:
        name     = p["name"]
        best_evt = p.get("best_event_name", "a future event")
        opp_pct  = p.get("opportunity_cost_pct", 0)
        uses     = p.get("uses_left", 0)
        c_sg     = p.get("current_course_sg", 0.0)
        c_sig    = p.get("current_course_sig", False)
        reason   = p.get("reason", "")
        venue_note = f" (poor course fit: {c_sg:+.2f} SG)" if c_sig and c_sg < -0.2 else ""
        reason_note = f" Reason: {reason}" if reason else ""
        saves_str += (
            f"  - {name}: {uses} uses left | better spot at {best_evt} "
            f"({int(opp_pct)}% more value){venue_note}.{reason_note}\n"
        )

    return f"""{LEAGUE_CONTEXT}

Current event: {current_event.get('name')} \
(week {current_event.get('week')}, \
${current_event.get('purse', 0)/1e6:.1f}M purse, \
tier={current_event.get('tier', 'standard')})
Budget: {budget.get('uses_remaining')} total uses remaining | \
{budget.get('weeks_remaining')} weeks left in season

Recommended lineup:
{picks_str.rstrip()}

Players to save this week:
{saves_str.rstrip()}

Write 4-6 sentences as a weekly lineup recommendation addressed directly to the manager. \
Lead with what makes each pick compelling from a golf standpoint — their current form, \
course fit, and recent results. Reference specific stats from the profiles above (scoring \
averages, SG categories, course history) so it sounds like real analysis. Mention the \
most important save and why briefly at the end. \
Plain prose only — no headers, no bullets, no markdown, no bold."""


def _save_prompt(name: str, data: dict, current_event: dict) -> str:
    """Build the prompt for a single SAVE player narrative."""
    uses     = data.get("uses_left", 0)
    wr       = data.get("world_rank", 0)
    tier     = data.get("tier", "").upper()
    best_evs = data.get("best_events", [])
    c_sg     = data.get("current_course_sg", 0.0)
    c_sig    = data.get("current_course_sig", False)
    c_rnds   = data.get("current_course_rounds", 0)
    is_hot   = data.get("is_hot_streak", False)
    reason   = data.get("reason", "")   # season_strategy natural-language reason

    in_field = data.get("in_field", False)
    opp_pct  = data.get("opportunity_cost_pct", 0)

    # Best future event
    best_evt_name = ""
    best_evt_detail = ""
    if best_evs:
        b = best_evs[0]
        best_evt_name = b.get("name", "")
        weeks_away = b.get("weeks_away", 0)
        purse = b.get("purse", 0)
        b_csg = b.get("course_sg")
        best_evt_detail = (
            f"{best_evt_name} in {weeks_away:.0f} weeks (${purse/1e6:.1f}M purse"
            + (f", course SG {b_csg:+.2f}" if b_csg else "")
            + ")"
        )

    # This week's course fit context
    course_note = ""
    if c_sig and c_sg < -0.2:
        course_note = f"This week's course is a poor fit ({c_sg:+.2f} SG over {c_rnds} rounds)."
    elif c_sig and c_sg > 0.2:
        course_note = f"This week the course suits them ({c_sg:+.2f} SG), but a bigger purse is coming."

    context_lines = [
        f"Player: {name} | World #{wr} | Tier: {tier} | {uses}/3 uses remaining",
    ]
    if is_hot:
        context_lines.append("Currently on a hot streak.")
    if reason:
        context_lines.append(f"Strategy note: {reason}")
    if course_note:
        context_lines.append(course_note)
    if in_field:
        context_lines.append(f"Is in the field this week but saving earns ~{int(opp_pct)}% more value.")
    else:
        context_lines.append("Not in the field this week.")
    if best_evt_detail:
        context_lines.append(f"Best future spot: {best_evt_detail}")

    context = "\n".join(context_lines)

    return f"""{LEAGUE_CONTEXT}

Current event: {current_event.get('name')} \
(week {current_event.get('week')}, \
${current_event.get('purse', 0)/1e6:.1f}M, \
tier={current_event.get('tier', 'standard')})

{context}

Write 2-3 sentences explaining why to save this player's use for a better spot. \
Lead with what makes them a strong asset overall (their game/form), then explain \
why this week isn't the right spot. Reference specific details. \
Plain prose — no headers, bullets, bold, or markdown."""


# ── Core generation ────────────────────────────────────────────────────────────

def _last_key(name: str) -> str:
    """Normalize to lowercase last name for cross-format matching.

    Handles:
      'Last, First'  (predictions CSV)  → 'last'
      'Last'         (tracker key)       → 'last'
      'F Last'       (abbreviated tracker key) → 'last'
    """
    if "," in name:
        return name.split(",")[0].strip().lower()
    return name.strip().split()[-1].lower()


def generate_reasoning(
    top_saves: int = 8,
    verbose: bool = True,
) -> dict:
    """
    Full generation pipeline:
      1. Run lineup_optimizer to get the best 3-player combo.
      2. Get season_strategy for SAVE context + course fit data.
      3. Generate weekly lineup narrative (1 call).
      4. Generate individual SAVE narratives for top held-back players.
      5. Save outputs/strategy_reasoning.json.
    """
    api_key = _load_api_key()
    if not api_key:
        print("[ERROR] No Anthropic API key found.")
        print("  Set ANTHROPIC_API_KEY in your environment, or enter it in the")
        print("  dashboard chatbot settings first.")
        sys.exit(1)

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    # ── Step 1: Run the combinatorial optimizer ───────────────────────────────
    if verbose:
        print("[INFO] Running lineup optimizer...")
    try:
        import pandas as pd
        from scripts.predictions.lineup_optimizer import run_optimizer

        preds_df = pd.read_csv(PREDICTIONS)
        results_df, candidate_pool, importance, tournament_name = run_optimizer(
            top_n=40,
            top_combos=5,
            verbose=False,
        )
    except Exception as e:
        print(f"[ERROR] Lineup optimizer failed: {e}")
        sys.exit(1)

    if results_df.empty:
        print("[ERROR] Optimizer returned no results.")
        sys.exit(1)

    # Best combo is row 1 (highest score)
    best = results_df.iloc[0]
    lineup_size = 3
    lineup_names = [best.get(f"pick{i}", "") for i in range(1, lineup_size + 1) if best.get(f"pick{i}", "")]

    # Build lineup rows with all stats for the prompt
    lineup_rows = []
    for i, name in enumerate(lineup_names, 1):
        row = candidate_pool[candidate_pool["player_name"] == name]
        if row.empty:
            continue
        r = row.iloc[0].to_dict()
        r["prize_ev"] = best.get(f"prize_ev{i}", r.get("expected_value", 0))
        lineup_rows.append(r)

    if verbose:
        ev_total = sum(int(r.get("prize_ev", 0)) for r in lineup_rows)
        print(f"  Optimal lineup: {' + '.join(lineup_names)}  ({ev_total:,} EV)")

    # ── Step 2: Season strategy for SAVE context ──────────────────────────────
    if verbose:
        print("[INFO] Loading season strategy...")
    from scripts.predictions.season_strategy import get_season_strategy
    strat = get_season_strategy()
    if "error" in strat:
        print(f"[ERROR] Strategy: {strat['error']}")
        sys.exit(1)

    current_event   = strat["current_event"]
    budget          = strat["budget"]
    player_strategy = strat["player_strategy"]

    # Normalize lineup names to last-name keys for strategy dict lookups
    lineup_keys = {_last_key(n) for n in lineup_names}

    # Attach course fit + form columns to lineup rows
    FORM_COLS = [
        "season_sg_total", "season_sg_app", "season_sg_ott", "season_sg_putt",
        "recent_scoring_avg", "recent_top10s", "recent_birdie_avg",
        "recent_cuts_made", "last_start_position", "missed_cut_last_start",
        "momentum_trend", "course_starts", "course_best_finish",
        "course_avg_to_par", "course_top_10_rate", "world_rank",
    ]
    for r in lineup_rows:
        pn_key = _last_key(r.get("player_name", ""))
        sp = next(
            (d for sn, d in player_strategy.items() if _last_key(sn) == pn_key),
            {}
        )
        r["course_sg"]      = sp.get("current_course_sg", 0.0)
        r["course_sig"]     = sp.get("current_course_sig", False)
        r["remaining_uses"] = sp.get("uses_left", r.get("remaining_uses", 3))
        # Back-fill any form columns missing from candidate_pool with preds_df
        prow = preds_df[preds_df["player_name"].str.lower().str.contains(
            _last_key(r.get("player_name", "")), na=False
        )]
        if not prow.empty:
            pdata = prow.iloc[0]
            for col in FORM_COLS:
                if col not in r or r.get(col) is None:
                    r[col] = pdata.get(col)

    # Top SAVE players: not in lineup, not USE NOW, sorted by best_future_ev
    save_players = sorted(
        [
            {"name": n, **d}
            for n, d in player_strategy.items()
            if _last_key(n) not in lineup_keys
            and not d.get("use_this_week")
            and d.get("uses_left", 0) > 0
        ],
        key=lambda x: x.get("best_future_ev", 0),
        reverse=True,
    )

    # ── Step 3: Weekly lineup narrative ──────────────────────────────────────
    if verbose:
        print("[INFO] Generating weekly lineup narrative...")
    prompt = _lineup_prompt(lineup_rows, save_players, current_event, budget)
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        weekly_narrative = resp.content[0].text.strip()
        if verbose:
            print("  done")
    except Exception as e:
        weekly_narrative = ""
        print(f"  [WARN] Weekly narrative failed: {e}")

    # ── Step 4: Individual SAVE narratives ────────────────────────────────────
    targets = save_players[:top_saves]
    if verbose:
        print(f"[INFO] Generating {len(targets)} SAVE narratives...")

    narratives: dict[str, dict] = {}

    # Mark USE NOW players (they appear in the lineup)
    for name in lineup_names:
        name_key = _last_key(name)
        sp = next(
            (d for n, d in player_strategy.items() if _last_key(n) == name_key),
            {}
        )
        narratives[name] = {
            "recommendation": "USE NOW",
            "tier":           sp.get("tier", ""),
            "uses_left":      sp.get("uses_left", 0),
            "this_week_ev":   int(sp.get("this_week_ev", 0)),
            "in_field":       True,
            "narrative":      "",   # covered by weekly_narrative
        }

    for i, player in enumerate(targets, 1):
        name = player["name"]
        if verbose:
            print(f"  [{i}/{len(targets)}] {name}...", end=" ", flush=True)
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": _save_prompt(name, player, current_event)}],
            )
            narrative = resp.content[0].text.strip()
            if verbose:
                print("done")
        except Exception as e:
            narrative = ""
            if verbose:
                print(f"ERROR: {e}")

        narratives[name] = {
            "recommendation": "SAVE",
            "tier":           player.get("tier", ""),
            "uses_left":      player.get("uses_left", 0),
            "this_week_ev":   int(player.get("this_week_ev", 0)),
            "in_field":       player.get("in_field", False),
            "narrative":      narrative,
        }

        if i < len(targets):
            time.sleep(0.3)

    # ── Save ──────────────────────────────────────────────────────────────────
    # Read tournament_id from latest_predictions.csv so the API can detect staleness
    _tid = ""
    try:
        import pandas as _pd
        _pred = _pd.read_csv(OUTPUTS_DIR / "latest_predictions.csv", nrows=1)
        _tid = str(_pred["tournament_id"].iloc[0]) if "tournament_id" in _pred.columns else ""
    except Exception:
        pass

    output = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "tournament":      current_event.get("name", ""),
        "tournament_id":   _tid,
        "tournament_week": current_event.get("week", 0),
        "lineup":          lineup_names,
        "weekly_narrative": weekly_narrative,
        "players":         narratives,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    if verbose:
        print(f"\n[OK] Saved → {OUTPUT_FILE}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Generate LLM weekly lineup reasoning")
    parser.add_argument("--top-saves", type=int, default=8,
                        help="Number of SAVE players to generate individual narratives for (default: 8)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    generate_reasoning(top_saves=args.top_saves, verbose=not args.quiet)


if __name__ == "__main__":
    main()
