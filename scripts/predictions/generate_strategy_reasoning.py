#!/usr/bin/env python3
"""
Generate LLM-powered natural language reasoning for season strategy picks.

Calls get_season_strategy(), formats per-player context, and asks Claude to
write 2-3 sentence narratives grounded strictly in the provided data.

Output: outputs/strategy_reasoning.json

Usage:
    python3 scripts/predictions/generate_strategy_reasoning.py
    python3 scripts/predictions/generate_strategy_reasoning.py --top-n 10
    python3 scripts/predictions/generate_strategy_reasoning.py --player "McIlroy"
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

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUTS_DIR / "strategy_reasoning.json"

CONFIG_FILE = PROJECT_ROOT / "data" / "config" / "assistant.json"

# League context injected into every prompt so Claude understands the stakes
LEAGUE_CONTEXT = """
You are advising a player in a season-long fantasy golf league called "Let It Ride."
Rules:
- Each player has exactly 3 uses per golfer for the entire ~30-week season.
- You must pick 3 golfers per week. Once you use all 3 of a golfer's uses, they are gone.
- The goal is to maximize total prize money earned across the season.
- Saving a use means banking it for a better tournament later.
- Premium events (Majors, Signature events) have larger purses and more value per use.
""".strip()


def _load_api_key() -> str:
    """Load Anthropic API key from environment or saved config."""
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


def _format_player_context(name: str, data: dict, current_event: dict) -> str:
    """Build a structured data block for one player to feed into the prompt."""
    rec  = "USE THIS WEEK" if data.get("use_this_week") else "SAVE"
    tier = data.get("tier", "unknown").upper()
    uses = data.get("uses_left", 0)
    wr   = data.get("world_rank", 0)

    ev       = int(data.get("this_week_ev", 0))
    best_ev  = int(data.get("best_future_ev", 0))
    opp_cost = int(data.get("opportunity_cost_ev", 0))
    opp_pct  = data.get("opportunity_cost_pct", 0)

    probs = data.get("this_week_probs") or {}
    win   = round(probs.get("win_prob", 0) * 100, 1)
    top10 = round(probs.get("top10_prob", 0) * 100, 1)

    c_sg    = data.get("current_course_sg", 0.0)
    c_sig   = data.get("current_course_sig", False)
    c_rnds  = data.get("current_course_rounds", 0)

    best_events = data.get("best_events", [])
    best_str = ""
    if best_events:
        b = best_events[0]
        best_str = (
            f"  Best future event: {b['name']} (week {b['week']}, "
            f"{b['weeks_away']:.1f} weeks away, "
            f"${b['purse']/1e6:.1f}M purse, tier={b['tier']}, "
            f"EV={int(b['ev']):,}"
            + (f", course_sg={b['course_sg']:+.2f}" if b.get('course_sg') else "")
            + ")"
        )

    venue_str = ""
    if c_sig:
        direction = "strong historical fit" if c_sg > 0 else "historically poor fit"
        venue_str = f"  Venue fit at {current_event.get('name','this week')}: {c_sg:+.2f} SG ({c_rnds} rounds) — {direction}"

    is_in_field = data.get("in_field", False)
    hot = " [HOT STREAK]" if data.get("is_hot_streak") else ""

    lines = [
        f"Player: {name}{hot}",
        f"  World rank: #{wr}  |  Tier: {tier}  |  Uses remaining: {uses}/3",
        f"  Recommendation: {rec}",
        f"  This week ({current_event.get('name', '?')}): {ev:,} EV  |  {win}% win  |  {top10}% top-10"
        if is_in_field else
        f"  This week: NOT IN FIELD",
    ]
    if venue_str:
        lines.append(venue_str)
    if best_str:
        lines.append(best_str)
    if opp_cost > 0:
        lines.append(f"  Opportunity cost of using now vs best future event: {opp_cost:,} EV ({opp_pct:.0f}% more EV later)")
    if data.get("save_signal"):
        lines.append("  Save signal: premium events upcoming — strong reason to conserve this use")

    return "\n".join(lines)


def _build_prompt(name: str, player_context: str, current_event: dict) -> str:
    """Build the full prompt sent to Claude for one player."""
    return f"""{LEAGUE_CONTEXT}

Current tournament: {current_event.get('name', 'Unknown')} \
(week {current_event.get('week', '?')}, \
${current_event.get('purse', 0)/1e6:.1f}M purse, \
tier={current_event.get('tier', 'standard')})

Here is the data for {name}:

{player_context}

Write exactly 2-3 sentences. No headers, no bullet points, no bold text, no markdown. \
Plain prose only. Be specific — reference the actual numbers (EV, win probability, \
course history, opportunity cost). Explain the USE/SAVE decision plainly, as if \
advising a friend. Do not invent facts not in the data above."""


def generate_reasoning(
    top_n: int = 12,
    player_filter: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Run the full generation pipeline.

    Returns the complete reasoning dict that was saved to OUTPUT_FILE.
    """
    api_key = _load_api_key()
    if not api_key:
        print("[ERROR] No Anthropic API key found.")
        print("  Set ANTHROPIC_API_KEY in your environment or .env file,")
        print("  or enter it in the dashboard chatbot settings first.")
        sys.exit(1)

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    # ── Load strategy data ────────────────────────────────────────────────────
    if verbose:
        print("[INFO] Loading season strategy data...")
    from scripts.predictions.season_strategy import get_season_strategy
    strat = get_season_strategy()
    if "error" in strat:
        print(f"[ERROR] Strategy error: {strat['error']}")
        sys.exit(1)

    current_event  = strat["current_event"]
    player_strategy = strat["player_strategy"]

    if verbose:
        print(f"  Tournament: {current_event.get('name')} (week {current_event.get('week')})")
        print(f"  Players in strategy: {len(player_strategy)}")

    # ── Select players to generate for ───────────────────────────────────────
    # Priority: USE NOW first (highest this_week_ev), then SAVE by best_future_ev
    if player_filter:
        targets = {
            n: d for n, d in player_strategy.items()
            if player_filter.lower() in n.lower()
        }
    else:
        use_now = sorted(
            [(n, d) for n, d in player_strategy.items() if d.get("use_this_week")],
            key=lambda x: x[1].get("this_week_ev", 0), reverse=True,
        )
        saves = sorted(
            [(n, d) for n, d in player_strategy.items() if not d.get("use_this_week")],
            key=lambda x: x[1].get("best_future_ev", 0), reverse=True,
        )
        ordered = use_now + saves
        targets = dict(ordered[:top_n])

    if verbose:
        print(f"  Generating narratives for {len(targets)} players...")

    # ── Generate per-player ───────────────────────────────────────────────────
    narratives: dict[str, dict] = {}
    for i, (name, data) in enumerate(targets.items(), 1):
        if verbose:
            rec = "USE" if data.get("use_this_week") else "SAVE"
            print(f"  [{i}/{len(targets)}] {name} ({rec})...", end=" ", flush=True)

        ctx    = _format_player_context(name, data, current_event)
        prompt = _build_prompt(name, ctx, current_event)

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",   # fast + cheap for batch generation
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            narrative = resp.content[0].text.strip()
            if verbose:
                print("done")
        except Exception as e:
            narrative = ""
            if verbose:
                print(f"ERROR: {e}")

        # A player flagged use_this_week but not in the field is a data edge case
        # (conflict redirect). Treat as SAVE for display purposes.
        in_field = data.get("in_field", False)
        rec_label = "USE NOW" if (data.get("use_this_week") and in_field) else "SAVE"

        narratives[name] = {
            "recommendation": rec_label,
            "tier":           data.get("tier", ""),
            "uses_left":      data.get("uses_left", 0),
            "this_week_ev":   int(data.get("this_week_ev", 0)),
            "in_field":       in_field,
            "narrative":      narrative,
        }

        # Respect API rate limits — small pause between calls
        if i < len(targets):
            time.sleep(0.3)

    # ── Save output ───────────────────────────────────────────────────────────
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tournament":   current_event.get("name", ""),
        "tournament_week": current_event.get("week", 0),
        "players":      narratives,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    if verbose:
        print(f"\n[OK] Saved → {OUTPUT_FILE}  ({len(narratives)} players)")

    return output


def main():
    parser = argparse.ArgumentParser(description="Generate LLM strategy reasoning")
    parser.add_argument("--top-n",   type=int, default=12,
                        help="Number of players to generate for (default: 12)")
    parser.add_argument("--player",  type=str, default=None,
                        help="Filter to a single player by name substring")
    parser.add_argument("--quiet",   action="store_true",
                        help="Suppress progress output")
    args = parser.parse_args()

    generate_reasoning(
        top_n=args.top_n,
        player_filter=args.player,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
