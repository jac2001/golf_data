#!/usr/bin/env python3
"""
Best Bet Notification Generator

Selects the top bet from recommended_bets, generates a Claude reasoning blurb,
and saves to outputs/best_bet.json for display on the /betting page.

Usage:
    python3 scripts/notifications/send_best_bet.py
    python3 scripts/notifications/send_best_bet.py --tournament-id R2026021
    python3 scripts/notifications/send_best_bet.py --dry-run   # skip Claude, use placeholder
"""

from __future__ import annotations

import argparse
import json
import re
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
ODDS_DIR     = DATA_DIR / "odds"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"

TID_PATTERN = re.compile(r"R\d{7}", re.IGNORECASE)


# ── Tournament ID resolution ───────────────────────────────────────────────────

def resolve_tournament_id(explicit: str = "") -> str:
    if explicit and TID_PATTERN.search(explicit.upper()):
        return TID_PATTERN.search(explicit.upper()).group(0).upper()

    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        try:
            df = pd.read_csv(pred_path, nrows=1)
            if "tournament_id" in df.columns:
                m = TID_PATTERN.search(str(df.iloc[0]["tournament_id"]))
                if m:
                    return m.group(0).upper()
        except Exception:
            pass

    files = sorted(ODDS_DIR.glob("recommended_bets_R*.csv"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        m = TID_PATTERN.search(f.stem)
        if m:
            return m.group(0).upper()

    return ""


# ── Load best bet ──────────────────────────────────────────────────────────────

MAX_ODDS = 2500  # cap long-shots — +5000 picks are noisy model outliers

def load_best_bet(tid: str) -> dict | None:
    path = ODDS_DIR / f"recommended_bets_{tid}.csv"
    if not path.exists():
        print(f"  No recommended bets file: {path.name}")
        return None

    df = pd.read_csv(path)
    if df.empty:
        print(f"  Recommended bets file is empty for {tid}")
        return None

    # Filter out extreme longshots
    df = df[df["odds_american"].abs() <= MAX_ODDS].copy()
    if df.empty:
        print(f"  All bets exceed odds cap ({MAX_ODDS}) — loosening to full set")
        df = pd.read_csv(path)

    # Sort: confidence * ev_per_1 rewards high-confidence, reasonable-EV bets
    df["_score"] = df["confidence"] * df["ev_per_1"]
    df = df.sort_values("_score", ascending=False)
    row = df.iloc[0].to_dict()
    return row


# ── Load context for Claude prompt ────────────────────────────────────────────

def load_player_context(player_name: str, tid: str) -> dict:
    ctx: dict = {}

    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        try:
            preds = pd.read_csv(pred_path)
            # Match player — predictions use "Last, First" format
            name_lower = player_name.strip().lower()

            def _norm(n: str) -> str:
                n = str(n).strip().lower()
                if "," in n:
                    parts = n.split(",", 1)
                    return f"{parts[1].strip()} {parts[0].strip()}"
                return n

            preds["_nkey"] = preds["player_name"].apply(_norm)
            target_key = _norm(player_name)

            match = preds[preds["_nkey"] == target_key]
            if not match.empty:
                r = match.iloc[0]
                ctx["sg_total"]       = round(float(r.get("sg_total", 0) or 0), 2)
                ctx["sg_app"]         = round(float(r.get("sg_app", 0) or 0), 2)
                ctx["sg_ott"]         = round(float(r.get("sg_ott", 0) or 0), 2)
                ctx["sg_putt"]        = round(float(r.get("sg_putt", 0) or 0), 2)
                ctx["world_rank"]     = int(r.get("world_rank", 0) or 0)
                ctx["dg_fit_total"]   = round(float(r.get("dg_fit_total", 0) or 0), 2)
                ctx["recent_form"]    = str(r.get("recent_form", "") or "")
                ctx["course_history"] = str(r.get("course_history_summary", "") or "")
                ctx["win_prob"]       = round(float(r.get("win_prob", 0) or 0) * 100, 1)
                ctx["top10_prob"]     = round(float(r.get("top10_prob", 0) or 0) * 100, 1)
        except Exception as e:
            print(f"  Warning: could not load player context — {e}")

    return ctx


def load_tournament_name(tid: str) -> str:
    sched_path = DATA_DIR / "raw" / "schedule_2026.csv"
    if sched_path.exists():
        try:
            df = pd.read_csv(sched_path)
            row = df[df["tournament_id"] == tid]
            if not row.empty:
                return str(row.iloc[0]["tournament_name"])
        except Exception:
            pass
    return tid


# ── Claude reasoning generation ───────────────────────────────────────────────

SYSTEM_PROMPT = """You write concise, confident betting analysis for a golf data dashboard.
Your output is 3-4 sentences only. Focus on WHY the model sees value — game fit, recent form,
course history, market mispricing. Be specific with numbers. No hedging, no preamble."""

def build_prompt(bet: dict, ctx: dict, tournament: str) -> str:
    market_label = {
        "top10": "Top 10",
        "top5":  "Top 5",
        "top20": "Top 20",
        "outright": "Outright Win",
        "make_cut": "Make Cut",
        "h2h": "H2H",
        "h2h_r1": "R1 H2H",
        "h2h_r2": "R2 H2H",
        "h2h_r3": "R3 H2H",
        "h2h_r4": "R4 H2H",
        "group_winner": "3-Ball",
    }.get(str(bet.get("market", "")), str(bet.get("market", "")))

    odds = int(bet.get("odds_american", 0))
    odds_str = f"+{odds}" if odds >= 0 else str(odds)
    edge = round(float(bet.get("edge_pts", 0)), 1)
    ev   = round(float(bet.get("ev_per_1", 0)) * 100, 1)

    ctx_lines = []
    if ctx.get("world_rank"):
        ctx_lines.append(f"World rank: #{ctx['world_rank']}")
    if ctx.get("sg_total") is not None:
        ctx_lines.append(f"SG total: {ctx['sg_total']:+.2f}")
    if ctx.get("sg_app") is not None:
        ctx_lines.append(f"SG app: {ctx['sg_app']:+.2f}, SG ott: {ctx['sg_ott']:+.2f}, SG putt: {ctx['sg_putt']:+.2f}")
    if ctx.get("dg_fit_total"):
        ctx_lines.append(f"DG course fit: {ctx['dg_fit_total']:+.2f}")
    if ctx.get("recent_form"):
        ctx_lines.append(f"Recent form: {ctx['recent_form']}")
    if ctx.get("course_history"):
        ctx_lines.append(f"Course history: {ctx['course_history']}")
    if ctx.get("top10_prob"):
        ctx_lines.append(f"Model top10 prob: {ctx['top10_prob']}%")

    ctx_block = "\n".join(ctx_lines) if ctx_lines else "No additional context available."

    return f"""Tournament: {tournament}
Best bet: {bet.get('player_name')} — {market_label} {odds_str} ({bet.get('book', 'DK')})
Model edge: +{edge}pp | EV: +{ev}% per $1 wagered
Selection: {bet.get('selection_label', '')}

Player context:
{ctx_block}

Write 3-4 sentences explaining why this bet has value. Be specific."""


def _load_api_key() -> str:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    import os
    return os.environ.get("ANTHROPIC_API_KEY", "")


def generate_reasoning(prompt: str) -> str:
    try:
        import anthropic
        api_key = _load_api_key()
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            # Cache the static system prompt — repeated calls (re-runs, retries)
            # hit the cache and cost ~90% less for the prompt tokens.
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        cache_read = getattr(msg.usage, "cache_read_input_tokens", 0) or 0
        cache_created = getattr(msg.usage, "cache_creation_input_tokens", 0) or 0
        if cache_read:
            print(f"  Cache hit: {cache_read} tokens read from cache")
        elif cache_created:
            print(f"  Cache created: {cache_created} tokens cached for future calls")
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  Claude API error: {e}")
        return ""


# ── Save output ────────────────────────────────────────────────────────────────

def save_best_bet(bet: dict, reasoning: str, tournament: str, tid: str) -> Path:
    odds = int(bet.get("odds_american", 0))
    market_label = {
        "top10": "Top 10", "top5": "Top 5", "top20": "Top 20",
        "outright": "Win", "make_cut": "Make Cut",
        "h2h": "H2H", "h2h_r1": "R1 H2H", "h2h_r2": "R2 H2H",
        "h2h_r3": "R3 H2H", "h2h_r4": "R4 H2H",
        "group_winner": "3-Ball",
    }.get(str(bet.get("market", "")), str(bet.get("market", "")))

    output = {
        "tournament_id":    tid,
        "tournament_name":  tournament,
        "player_name":      bet.get("player_name", ""),
        "market":           bet.get("market", ""),
        "market_label":     market_label,
        "selection_label":  bet.get("selection_label", ""),
        "book":             bet.get("book", ""),
        "odds_american":    odds,
        "odds_str":         f"+{odds}" if odds >= 0 else str(odds),
        "edge_pts":         round(float(bet.get("edge_pts", 0)), 1),
        "ev_per_1":         round(float(bet.get("ev_per_1", 0)), 4),
        "ev_pct":           round(float(bet.get("ev_per_1", 0)) * 100, 1),
        "model_prob":       round(float(bet.get("model_prob", 0)) * 100, 1),
        "book_prob":        round(float(bet.get("book_prob", 0)) * 100, 1),
        "confidence":       round(float(bet.get("confidence", 0)), 2),
        "reasoning":        reasoning,
        "generated_at":     datetime.now(timezone.utc).isoformat(),
    }

    out_path = OUTPUTS_DIR / "best_bet.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Saved -> {out_path}")
    return out_path


# ── Email ─────────────────────────────────────────────────────────────────────

def _load_email_config() -> dict:
    """Read SMTP settings from .env file."""
    config: dict = {}
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            for key in ("NOTIFY_EMAIL_TO", "NOTIFY_EMAIL_FROM",
                        "SMTP_USER", "SMTP_PASSWORD",
                        "SMTP_HOST", "SMTP_PORT"):
                if line.startswith(f"{key}="):
                    config[key] = line.split("=", 1)[1].strip()
    return config


def send_email(bet_data: dict, cfg: dict) -> bool:
    """Send best bet notification email via Gmail SMTP."""
    to_addr   = cfg.get("NOTIFY_EMAIL_TO", "")
    from_addr = cfg.get("NOTIFY_EMAIL_FROM") or cfg.get("SMTP_USER", "")
    user      = cfg.get("SMTP_USER", "")
    password  = cfg.get("SMTP_PASSWORD", "")
    host      = cfg.get("SMTP_HOST", "smtp.gmail.com")
    port      = int(cfg.get("SMTP_PORT", 587))

    if not all([to_addr, from_addr, user, password]):
        print("  Email skipped — SMTP config incomplete in .env")
        print("  Required: NOTIFY_EMAIL_TO, SMTP_USER, SMTP_PASSWORD")
        return False

    tournament = bet_data["tournament_name"]
    player     = bet_data["player_name"]
    market     = bet_data["market_label"]
    odds_str   = bet_data["odds_str"]
    book       = bet_data["book"]
    edge       = bet_data["edge_pts"]
    reasoning  = bet_data.get("reasoning", "")

    subject = f"Best Bet — {tournament}: {player} {market} {odds_str}"

    # Plain text
    text_body = f"""{tournament}
{'─' * len(tournament)}

{player} · {market} · {odds_str} ({book})
Edge: +{edge:.1f}pp

{reasoning}

→ Full analysis at http://localhost:3000/betting
"""

    # HTML
    html_body = f"""
<html><body style="font-family: -apple-system, sans-serif; background: #f4f6f9; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #fff; border-radius: 10px;
              border-left: 4px solid #00c44f; padding: 24px;">
    <div style="font-size: 11px; font-weight: 700; color: #00c44f;
                text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">
      Best Bet
    </div>
    <div style="font-size: 13px; color: #666; margin-bottom: 16px;">{tournament}</div>

    <div style="font-size: 22px; font-weight: 800; color: #1a1a2e; margin-bottom: 4px;">
      {player}
    </div>
    <div style="font-size: 15px; color: #444; margin-bottom: 16px;">
      {market} &nbsp;·&nbsp; <strong>{odds_str}</strong> &nbsp;·&nbsp; {book}
    </div>

    <div style="display: inline-block; background: #e8fdf0; color: #00a040;
                font-weight: 700; font-size: 13px; padding: 4px 12px;
                border-radius: 20px; margin-bottom: 20px;">
      +{edge:.1f}pp edge
    </div>

    <p style="font-size: 14px; color: #333; line-height: 1.65; margin: 0 0 20px;">{reasoning}</p>

    <a href="http://localhost:3000/betting"
       style="display: inline-block; background: #00c44f; color: #fff;
              text-decoration: none; font-weight: 700; font-size: 13px;
              padding: 10px 20px; border-radius: 8px;">
      View Full Analysis →
    </a>
  </div>
</body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())

        print(f"  Email sent to {to_addr}")
        return True
    except Exception as e:
        print(f"  Email failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate best bet notification")
    parser.add_argument("--tournament-id", default="")
    parser.add_argument("--send-email", action="store_true",
                        help="Send email notification after generating")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Claude API call, use placeholder reasoning")
    args = parser.parse_args()

    tid = resolve_tournament_id(args.tournament_id)
    if not tid:
        print("Could not resolve tournament ID — run recommend_bets.py first")
        sys.exit(1)

    tournament = load_tournament_name(tid)
    print(f"Tournament: {tournament} ({tid})")

    bet = load_best_bet(tid)
    if not bet:
        print("No bets to notify — writing empty best_bet.json")
        out = {"tournament_id": tid, "tournament_name": tournament,
               "player_name": None, "reasoning": None,
               "generated_at": datetime.now(timezone.utc).isoformat()}
        with open(OUTPUTS_DIR / "best_bet.json", "w") as f:
            json.dump(out, f, indent=2)
        sys.exit(0)

    odds = int(bet.get("odds_american", 0))
    odds_str = f"+{odds}" if odds >= 0 else str(odds)
    print(f"Best bet: {bet['player_name']} — {bet['market']} {odds_str} "
          f"(edge {bet['edge_pts']:.1f}pp, EV {float(bet['ev_per_1'])*100:.1f}%)")

    ctx = load_player_context(str(bet.get("player_name", "")), tid)

    if args.dry_run:
        reasoning = f"[Dry run] {bet['player_name']} shows model edge of {bet['edge_pts']:.1f}pp on {bet['market']} market."
    else:
        print("  Generating Claude reasoning...")
        prompt = build_prompt(bet, ctx, tournament)
        reasoning = generate_reasoning(prompt)
        if not reasoning:
            reasoning = f"Model shows +{bet['edge_pts']:.1f}pp edge on {bet['market']} market."

    print(f"  Reasoning: {reasoning[:120]}...")
    out_path = save_best_bet(bet, reasoning, tournament, tid)

    if args.send_email:
        bet_data = json.loads(out_path.read_text())
        send_email(bet_data, _load_email_config())

    print("Done.")


if __name__ == "__main__":
    main()
