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

def _lineup_prompt(
    lineup_rows: list[dict],
    save_players: list[dict],
    current_event: dict,
    budget: dict,
) -> str:
    """Build the prompt for the single weekly lineup narrative."""
    ev_total = sum(int(p.get("prize_ev", 0)) for p in lineup_rows)

    picks_str = ""
    for i, p in enumerate(lineup_rows, 1):
        name   = p["player_name"]
        ev     = int(p.get("prize_ev", 0))
        win    = round(float(p.get("win_prob", 0)) * 100, 1)
        t10    = round(float(p.get("top10_prob", 0)) * 100, 1)
        cut    = round(float(p.get("cut_prob", 0)) * 100, 1)
        uses   = int(p.get("remaining_uses", 3))
        c_sg   = p.get("course_sg", 0.0)
        c_sig  = p.get("course_sig", False)
        venue  = f", {c_sg:+.2f} SG at this course" if c_sig and abs(c_sg) >= 0.25 else ""
        picks_str += (
            f"  {i}. {name} — {ev:,} EV | {win}% win | {t10}% top-10 | "
            f"{cut}% cut | {uses} uses left{venue}\n"
        )

    saves_str = ""
    for p in save_players[:4]:
        name     = p["name"]
        best_ev  = int(p.get("best_future_ev", 0))
        best_evt = p.get("best_event_name", "")
        opp_pct  = p.get("opportunity_cost_pct", 0)
        uses     = p.get("uses_left", 0)
        c_sg     = p.get("current_course_sg", 0.0)
        c_sig    = p.get("current_course_sig", False)
        venue    = f" (venue miss: {c_sg:+.2f} SG)" if c_sig and c_sg < -0.2 else ""
        saves_str += (
            f"  - {name}: {uses} uses left | best event: {best_evt} "
            f"({best_ev:,} EV, {opp_pct:.0f}% more than this week){venue}\n"
        )

    return f"""{LEAGUE_CONTEXT}

Current event: {current_event.get('name')} \
(week {current_event.get('week')}, \
${current_event.get('purse', 0)/1e6:.1f}M purse, \
tier={current_event.get('tier', 'standard')})
Budget: {budget.get('uses_remaining')} total uses remaining | \
{budget.get('weeks_remaining')} weeks left in season

Optimal lineup (chosen by combinatorial optimizer, combined EV {ev_total:,}):
{picks_str.rstrip()}

Notable players to save this week:
{saves_str.rstrip()}

Write 4-6 sentences as a weekly lineup recommendation. Cover: why each of the 3 \
picks makes sense this week (reference their specific numbers), and briefly note \
the most important save and why. Plain prose only — no headers, no bullets, \
no markdown, no bold text. Speak directly to the manager."""


def _save_prompt(name: str, data: dict, current_event: dict) -> str:
    """Build the prompt for a single SAVE player narrative."""
    uses     = data.get("uses_left", 0)
    wr       = data.get("world_rank", 0)
    tier     = data.get("tier", "").upper()
    best_evs = data.get("best_events", [])
    best_ev  = int(data.get("best_future_ev", 0))
    opp_cost = int(data.get("opportunity_cost_ev", 0))
    opp_pct  = data.get("opportunity_cost_pct", 0)
    c_sg     = data.get("current_course_sg", 0.0)
    c_sig    = data.get("current_course_sig", False)
    c_rnds   = data.get("current_course_rounds", 0)

    in_field = data.get("in_field", False)
    probs    = data.get("this_week_probs") or {}
    win      = round(probs.get("win_prob", 0) * 100, 1)
    t10      = round(probs.get("top10_prob", 0) * 100, 1)
    tw_ev    = int(data.get("this_week_ev", 0))

    venue_line = ""
    if c_sig:
        direction = "strong fit" if c_sg > 0 else "poor fit"
        venue_line = f"\n  Venue: {c_sg:+.2f} SG at this course ({c_rnds} rounds) — {direction}"

    best_line = ""
    if best_evs:
        b = best_evs[0]
        best_line = (
            f"\n  Best future event: {b['name']} "
            f"(week {b['week']}, {b['weeks_away']:.1f}w away, "
            f"${b['purse']/1e6:.1f}M, {best_ev:,} EV"
            + (f", course_sg={b['course_sg']:+.2f}" if b.get("course_sg") else "")
            + ")"
        )

    this_week_line = (
        f"\n  This week: {tw_ev:,} EV | {win}% win | {t10}% top-10"
        if in_field else "\n  This week: NOT IN FIELD"
    )

    context = (
        f"Player: {name}\n"
        f"  World rank: #{wr} | Tier: {tier} | Uses left: {uses}/3"
        f"{this_week_line}"
        f"{venue_line}"
        f"{best_line}"
        + (f"\n  Opportunity cost of using now: {opp_cost:,} EV ({opp_pct:.0f}% more value later)"
           if opp_cost > 0 else "")
    )

    return f"""{LEAGUE_CONTEXT}

Current event: {current_event.get('name')} \
(week {current_event.get('week')}, \
${current_event.get('purse', 0)/1e6:.1f}M, \
tier={current_event.get('tier', 'standard')})

{context}

Write 2-3 sentences explaining why to save this player this week. Reference the \
specific numbers. Plain prose — no headers, bullets, bold, or markdown."""


# ── Core generation ────────────────────────────────────────────────────────────

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

    # Attach course fit from strategy to lineup rows
    lineup_name_set = {n.lower() for n in lineup_names}
    for r in lineup_rows:
        pn = r.get("player_name", "")
        sp = next(
            (d for name, d in player_strategy.items() if name.lower() == pn.lower()),
            {}
        )
        r["course_sg"]  = sp.get("current_course_sg", 0.0)
        r["course_sig"] = sp.get("current_course_sig", False)
        r["remaining_uses"] = sp.get("uses_left", r.get("remaining_uses", 3))

    # Top SAVE players: not in lineup, not USE NOW, sorted by best_future_ev
    save_players = sorted(
        [
            {"name": n, **d}
            for n, d in player_strategy.items()
            if n not in lineup_names
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
        sp = next(
            (d for n, d in player_strategy.items() if n.lower() == name.lower()),
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
    output = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "tournament":      current_event.get("name", ""),
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
