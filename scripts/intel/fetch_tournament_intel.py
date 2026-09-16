#!/usr/bin/env python3
"""
Pre-tournament intel agent. Searches the web for player news, injuries,
and course conditions for the current week's tournament.

Runs as part of the Tuesday pipeline (after predict_tournament.py).
Output: data/intel/tournament_intel_R{tid}.json

Usage:
    python3 scripts/intel/fetch_tournament_intel.py
    python3 scripts/intel/fetch_tournament_intel.py --top-n 20 --tid R2026021
"""

import argparse
import json
import re
import time
import anthropic
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTEL_DIR = PROJECT_ROOT / "data" / "intel"
INTEL_DIR.mkdir(exist_ok=True)


client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

# Haiku is the primary model — cheap enough to run weekly without burning
# through credits (this script makes ~20 web-search calls per run). One retry
# with backoff covers transient overload/rate-limit errors; a hard budget
# error (out of credits) gives up immediately so the pipeline step degrades
# gracefully instead of crashing.
_MODEL = "claude-haiku-4-5-20251001"


def _is_budget_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(x in s for x in ["credit", "billing", "quota", "balance"])


def _is_transient_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(x in s for x in ["429", "overloaded", "rate_limit", "timeout"])


def _call_with_fallback(prompt: str) -> str | None:
    """Run a web-search prompt against Haiku, retrying once on transient
    overload/rate-limit errors. Returns the response text, or None if the
    call failed (budget exhausted, or retry also failed)."""
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return text_blocks[-1] if text_blocks else None
        except Exception as e:
            if attempt == 0 and _is_transient_error(e):
                print(" [transient error — retrying in 5s]", end="")
                time.sleep(5)
                continue
            if _is_budget_error(e):
                print(" [credit balance too low — skipping]", end="")
            else:
                print(f" [error: {e}]", end="")
            return None
    return None


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object found in text, ignoring preamble/fences."""
    # Try to extract from code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))
    # Fall back: find first { ... } spanning the whole object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    raise json.JSONDecodeError("no JSON object found", text, 0)

# ── Step 1: Load top-N players from this week's predictions ────────────────

def load_top_players(n=20) -> list[dict]:
    preds = pd.read_csv(PROJECT_ROOT / "outputs" / "latest_predictions.csv")
    sort_col = "win_prob_sim" if "win_prob_sim" in preds.columns and preds["win_prob_sim"].notna().any() else "win_prob"
    keep = [c for c in ["player_name", "win_prob_sim", "win_prob", "world_rank"] if c in preds.columns]
    top = preds.nlargest(n, sort_col)[keep]
    return top.to_dict("records")


# ── Step 2: Search for player news ─────────────────────────────────────────
  # Uses Claude's built-in web_search tool (no external API key needed)

PLAYER_SEARCH_PROMPT = """
Search for recent news (last 14 days) about {player_name} in the context of
PGA Tour golf and this week's {tournament_name} tournament. Look for:
- Injury or health concerns
- Last 3 tournament results with finish positions (e.g. "T4 at Memorial", "MC at Charles Schwab")
- Whether their form is improving, declining, or flat across those results
- Any quotes about their game or this course
- Withdrawal risk

Return ONLY this JSON object with no explanation, no markdown, no backticks:
{{"player_name": "{player_name}", "injury_flag": false, "injury_detail": null, "recent_form_summary": "1-2 sentences", "last_3_results": ["result1", "result2", "result3"], "trend": "trending_up", "key_quote": null, "sentiment": "neutral", "sources": ["url1"]}}

trend must be exactly one of: "trending_up", "trending_down", "stable"
Only return the JSON, nothing else.
"""





COURSE_SEARCH_PROMPT = """
Search for current course conditions at {tournament_name} this week on the PGA Tour.
Look for: rough length, green speed (stimp), pin sheet difficulty, weather impact on
scoring, any course setup notes from players or officials.

Return ONLY this raw JSON object with no explanation, no markdown, no backticks:
{{"course_name": "string", "rough_length": "string or null", "green_speed": "string or null", "setup_notes": "2-3 sentences", "scoring_outlook": "low or moderate or high", "sources": ["url1"]}}
"""

def search_player(player_name: str, tournament_name: str) -> dict:
    prompt = PLAYER_SEARCH_PROMPT.format(
        player_name=player_name,
        tournament_name=tournament_name,
    )
    text = _call_with_fallback(prompt)
    if text is None:
        return {"player_name": player_name, "error": "API call failed"}
    try:
        return _parse_json(text)
    except json.JSONDecodeError:
        return {"player_name": player_name, "error": text}

def search_course_conditions(tournament_name: str, course_name: str) -> dict:
    prompt = COURSE_SEARCH_PROMPT.format(
        tournament_name=tournament_name,
        course_name=course_name,
    )
    text = _call_with_fallback(prompt)
    if text is None:
        return {"error": "API call failed"}
    try:
        return _parse_json(text)
    except json.JSONDecodeError:
        return {"error": text}


# ── Step 4: Assemble and save ───────────────────────────────────────────────

def run(tid: str, tournament_name: str, course_name: str, top_n=20):
    players = load_top_players(n=top_n)
    print(f"Fetching intel for {len(players)} players at {tournament_name}...")

    player_intel = []
    for p in players:
        print(f"  {p['player_name']}...", end="", flush=True)
        try:
            intel = search_player(p["player_name"], tournament_name)
        except Exception as e:
            intel = {"player_name": p["player_name"], "error": str(e)}
        intel["win_prob"] = p["win_prob"]
        intel["world_rank"] = p["world_rank"]
        player_intel.append(intel)
        print(" done")

    print("Fetching course conditions...")
    try:
        course_intel = search_course_conditions(tournament_name, course_name)
    except Exception as e:
        course_intel = {"error": str(e)}

    output = {
        "tid": tid,
        "tournament_name": tournament_name,
        "generated_at": pd.Timestamp.now().isoformat(),
        "course_conditions": course_intel,
        "players": player_intel,
    }

    # Always save whatever was gathered — partial intel beats none, and this
    # keeps the pipeline step from being marked "failed" over one bad player.
    out_path = INTEL_DIR / f"tournament_intel_{tid}.json"
    out_path.write_text(json.dumps(output, indent=2))
    n_ok = sum(1 for p in player_intel if "error" not in p)
    print(f"Saved → {out_path}  ({n_ok}/{len(player_intel)} players succeeded)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tid", default="R2026021")
    parser.add_argument("--tournament", default="Charles Schwab Challenge")
    parser.add_argument("--course", default="Colonial Country Club")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    run(
        tid=args.tid,
        tournament_name=args.tournament,
        course_name=args.course,
        top_n=args.top_n,
    )