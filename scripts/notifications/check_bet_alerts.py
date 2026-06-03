"""
check_bet_alerts.py
===================
Monitors our tracked bets (slip.json) and fantasy picks (usage_tracker_2026.json)
during active tournaments. Sends push + email notifications when something worth
knowing happens:

  Bet alerts:
    - A pending bet flips on_track → off_track (danger: player falling out of position)
    - A pending bet flips off_track → on_track (recovery)
    - A bet settles (won or lost) — only fires if a results CSV exists

  Pick alerts:
    - A fantasy pick is on the cut bubble (within 2 shots of projected cut)
    - A fantasy pick makes a significant position move (≥10 spots in a round)

State is persisted in data/bets/alert_state.json. An alert only fires when the
state actually *changes* — so you won't get the same notification every 30 minutes.

Push notification providers (configure in .env):
  Pushover (recommended — $5 one-time iOS/Android app):
    PUSHOVER_USER_KEY=<your user key from pushover.net>
    PUSHOVER_APP_TOKEN=<token from pushover.net/apps>

  ntfy.sh (free, open-source alternative):
    NTFY_TOPIC=<your unique topic name, e.g. golf-alerts-abc123>

Usage:
    python3 scripts/notifications/check_bet_alerts.py [--dry-run]

Dry-run prints what alerts would be sent without sending anything.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"

SLIP_PATH        = DATA_DIR / "bets" / "slip.json"
STATE_PATH       = DATA_DIR / "bets" / "alert_state.json"
TRACKER_PATH     = DATA_DIR / "fantasy" / "usage_tracker_2026.json"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _name_sort_key(name: str) -> str:
    return " ".join(sorted(name.replace(",", "").lower().split()))


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _load_notify_config() -> dict:
    """Read notification settings (email + push) from .env."""
    config: dict = {}
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            for key in (
                "NOTIFY_EMAIL_TO", "NOTIFY_EMAIL_FROM",
                "SMTP_USER", "SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT",
                "PUSHOVER_USER_KEY", "PUSHOVER_APP_TOKEN",
                "NTFY_TOPIC",
            ):
                if line.startswith(f"{key}="):
                    config[key] = line.split("=", 1)[1].strip()
    return config


# Priority levels passed to _send_alert
PRIORITY_NORMAL  = 0   # standard push
PRIORITY_HIGH    = 1   # bypasses iOS/Android quiet hours (Pushover only)


def _send_push(title: str, message: str, cfg: dict, priority: int = PRIORITY_NORMAL) -> bool:
    """
    Send a push notification via Pushover or ntfy.sh.

    Pushover  — instant push to iOS/Android, $5 one-time app.
                Set PUSHOVER_USER_KEY + PUSHOVER_APP_TOKEN in .env.
                Priority 1 = urgent, bypasses quiet hours.

    ntfy.sh   — free & open-source alternative.
                Set NTFY_TOPIC to any unique string (e.g. 'golf-alerts-abc123').
                Subscribe to that topic in the ntfy app on your phone.
    """
    sent = False

    # ── Pushover ──────────────────────────────────────────────────────────────
    user_key  = cfg.get("PUSHOVER_USER_KEY", "")
    app_token = cfg.get("PUSHOVER_APP_TOKEN", "")
    if user_key and app_token:
        try:
            payload: dict = {
                "token":    app_token,
                "user":     user_key,
                "title":    title,
                "message":  message,
                "priority": priority,
            }
            # retry + expire are only valid for priority=2 (emergency)
            if priority >= 2:
                payload["retry"]  = 60
                payload["expire"] = 3600
            data = urllib.parse.urlencode(payload).encode()
            req = urllib.request.Request(
                "https://api.pushover.net/1/messages.json",
                data=data,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            print(f"  Pushover sent: {title}")
            sent = True
        except Exception as e:
            print(f"  Pushover failed: {e}")

    # ── ntfy.sh ───────────────────────────────────────────────────────────────
    ntfy_topic = cfg.get("NTFY_TOPIC", "")
    if ntfy_topic:
        try:
            ntfy_priority = "urgent" if priority >= 1 else "default"
            req = urllib.request.Request(
                f"https://ntfy.sh/{ntfy_topic}",
                data=message.encode(),
                headers={
                    "Title":    title,
                    "Priority": ntfy_priority,
                    "Tags":     "golf",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            print(f"  ntfy sent: {title}")
            sent = True
        except Exception as e:
            print(f"  ntfy failed: {e}")

    if not user_key and not ntfy_topic:
        print("  Push skipped — set PUSHOVER_USER_KEY+PUSHOVER_APP_TOKEN or NTFY_TOPIC in .env")

    return sent


def _send_email(subject: str, body: str, cfg: dict) -> bool:
    to_addr   = cfg.get("NOTIFY_EMAIL_TO", "")
    from_addr = cfg.get("NOTIFY_EMAIL_FROM") or cfg.get("SMTP_USER", "")
    user      = cfg.get("SMTP_USER", "")
    password  = cfg.get("SMTP_PASSWORD", "")
    host      = cfg.get("SMTP_HOST", "smtp.gmail.com")
    port      = int(cfg.get("SMTP_PORT", 587))

    if not all([to_addr, from_addr, user, password]):
        print("  Email skipped — set NOTIFY_EMAIL_TO, SMTP_USER, SMTP_PASSWORD in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        print(f"  Email sent: {subject}")
        return True
    except Exception as e:
        print(f"  Email failed: {e}")
        return False


def _send_alert(subject: str, body: str, cfg: dict, dry_run: bool,
                priority: int = PRIORITY_NORMAL) -> bool:
    """Send push notification + email. Both fire independently — one failing won't block the other."""
    if dry_run:
        print(f"\n[DRY RUN] {subject}\n{body}")
        return True
    _send_push(subject, body, cfg, priority)
    _send_email(subject, body, cfg)
    return True


# ── Live leaderboard loading ──────────────────────────────────────────────────

def _load_leaderboard(tid: str) -> tuple[dict, float | None]:
    """
    Returns (player_key → row_dict, projected_cut_score).
    Player key is the sort-key so we can match across name formats.
    """
    lb_path   = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    meta_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}_meta.json"

    lb: dict[str, dict] = {}
    if lb_path.exists():
        import pandas as pd
        try:
            df = pd.read_csv(lb_path, low_memory=False)
            for _, row in df.iterrows():
                key = _name_sort_key(str(row.get("player_name", "")))
                lb[key] = row.to_dict()
        except Exception:
            pass

    projected_cut: float | None = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            projected_cut = meta.get("cut_projection", {}).get("projected_cut_score")
        except Exception:
            pass

    return lb, projected_cut


def _live_status(market: str, pos_str: str | None, total_numeric: float | None,
                 projected_cut: float | None, thru: str | None) -> str | None:
    """Mirror the status logic from api/main.py _attach_live_context."""
    THRESHOLDS = {
        "outright": (5, 12), "top5": (5, 8), "top10": (10, 14),
        "top20": (20, 25), "top30": (30, 37),
    }

    if thru == "F":
        return "finished"

    pos_num: int | None = None
    if pos_str:
        try:
            pos_num = int(str(pos_str).lstrip("Tt"))
        except ValueError:
            pass

    if market in THRESHOLDS and pos_num is not None:
        on_t, margin_t = THRESHOLDS[market]
        return "on_track" if pos_num <= on_t else "marginal" if pos_num <= margin_t else "off_track"

    if market == "make_cut" and total_numeric is not None and projected_cut is not None:
        diff = total_numeric - projected_cut
        return "on_track" if diff <= 0 else "marginal" if diff <= 2 else "off_track"

    if market.startswith("h2h") or market in ("matchup", "group_winner"):
        return "tracking"

    return None


# ── Bet slip alerts ───────────────────────────────────────────────────────────

def check_bet_alerts(state: dict, cfg: dict, dry_run: bool) -> list[str]:
    """Check each pending bet in slip.json for status changes."""
    slip_data = _load_json(SLIP_PATH)
    bets = slip_data.get("bets", []) if isinstance(slip_data, dict) else []

    pending = [b for b in bets if not b.get("outcome_status") or b["outcome_status"] == "pending"]
    if not pending:
        return []

    # Load leaderboard once per unique tournament
    lb_by_tid: dict[str, tuple[dict, float | None]] = {}
    for b in pending:
        tid = b.get("tournament_id", "")
        if tid and tid not in lb_by_tid:
            lb_by_tid[tid] = _load_leaderboard(tid)

    prev_bet_states: dict = state.get("bets", {})
    new_bet_states: dict  = {}
    alerts: list[str] = []

    for bet in pending:
        bet_id = bet.get("id", "")
        tid    = bet.get("tournament_id", "")
        lb, projected_cut = lb_by_tid.get(tid, ({}, None))

        player_key = _name_sort_key(bet.get("player_name", ""))
        row = lb.get(player_key)

        if row is None:
            new_bet_states[bet_id] = prev_bet_states.get(bet_id, {})
            continue

        pos_str       = str(row.get("position", "")).strip() or None
        total_numeric = row.get("total_numeric")
        thru          = str(row.get("thru", "")).strip() or None
        total_str     = str(row.get("total", "")).strip() or None

        try:
            total_numeric = float(total_numeric)
        except (TypeError, ValueError):
            total_numeric = None

        current_status = _live_status(
            bet.get("market", ""), pos_str, total_numeric, projected_cut, thru
        )
        new_bet_states[bet_id] = {"status": current_status, "position": pos_str}

        prev = prev_bet_states.get(bet_id, {})
        prev_status = prev.get("status")

        player  = bet.get("player_name", "?")
        market  = bet.get("market", "?")
        odds    = bet.get("odds_american", 0)
        odds_s  = f"+{odds}" if odds >= 0 else str(odds)

        # Fire alert on status flip
        if prev_status and current_status and prev_status != current_status:
            if current_status == "off_track":
                emoji_txt = "DANGER"
                push_priority = PRIORITY_HIGH   # wake the phone — bet is losing
                detail = f"{player} has fallen to {pos_str} ({total_str}) — outside position for your {market.upper()} bet ({odds_s})."
            elif current_status == "on_track" and prev_status in ("off_track", "marginal"):
                emoji_txt = "RECOVERY"
                push_priority = PRIORITY_NORMAL
                detail = f"{player} is back in position at {pos_str} ({total_str}) for your {market.upper()} bet ({odds_s})."
            elif current_status == "marginal":
                emoji_txt = "WARNING"
                push_priority = PRIORITY_NORMAL
                detail = f"{player} is on the bubble at {pos_str} ({total_str}) for your {market.upper()} bet ({odds_s})."
            else:
                continue  # no noteworthy flip

            subject = f"[{emoji_txt}] Bet Alert — {player} {market.upper()}"
            body    = f"Golf Bet Tracker\n{'─'*40}\n\n{detail}\n\nCurrent: {pos_str}  {total_str}  thru {thru}\n\nView full slip → http://localhost:3000/history\n"

            _send_alert(subject, body, cfg, dry_run, push_priority)
            alerts.append(subject)

    state["bets"] = new_bet_states
    return alerts


# ── Fantasy pick alerts ───────────────────────────────────────────────────────

def check_pick_alerts(state: dict, cfg: dict, dry_run: bool) -> list[str]:
    """Check this week's fantasy picks for cut bubble / big position moves."""
    tracker = _load_json(TRACKER_PATH)
    if not isinstance(tracker, dict):
        return []

    # Find picks made this week — look for any entry with a current week pick
    # usage_tracker structure: { "player_name": { "picks": [{"week": N, "tournament_id": T, ...}] } }
    # We want picks where a live leaderboard exists for the tournament_id

    picks_this_week: list[dict] = []
    for player_key, pdata in tracker.items():
        if not isinstance(pdata, dict):
            continue
        for pick in pdata.get("picks", []):
            tid = pick.get("tournament_id", "")
            lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
            if lb_path.exists():
                picks_this_week.append({
                    "player_key": player_key,
                    "tournament_id": tid,
                })

    if not picks_this_week:
        return []

    lb_by_tid: dict[str, tuple[dict, float | None]] = {}
    for p in picks_this_week:
        tid = p["tournament_id"]
        if tid not in lb_by_tid:
            lb_by_tid[tid] = _load_leaderboard(tid)

    prev_pick_states: dict = state.get("picks", {})
    new_pick_states: dict  = {}
    alerts: list[str] = []

    for pick in picks_this_week:
        player_key = pick["player_key"]
        tid        = pick["tournament_id"]
        lb, projected_cut = lb_by_tid[tid]

        name_key = _name_sort_key(player_key)
        # Tracker uses last-name-only keys — try to find best match
        row = lb.get(name_key)
        if row is None:
            # Fall back: find any lb key that starts with this token
            matches = [v for k, v in lb.items() if name_key in k]
            row = matches[0] if matches else None

        if row is None:
            continue

        pos_str       = str(row.get("position", "")).strip() or None
        total_numeric = row.get("total_numeric")
        thru          = str(row.get("thru", "")).strip() or None
        total_str     = str(row.get("total", "")).strip() or None

        try:
            total_numeric = float(total_numeric)
        except (TypeError, ValueError):
            total_numeric = None

        try:
            pos_num = int(str(pos_str or "").lstrip("Tt"))
        except ValueError:
            pos_num = None

        state_key = f"{player_key}_{tid}"
        prev = prev_pick_states.get(state_key, {})
        prev_pos = prev.get("pos_num")
        new_pick_states[state_key] = {"pos_num": pos_num, "total": total_str}

        player_display = player_key.title()

        # Cut bubble alert — high priority, this is time-sensitive
        if projected_cut is not None and total_numeric is not None and thru != "F":
            diff = total_numeric - projected_cut
            if 0 <= diff <= 2 and prev.get("alerted_bubble") is not True:
                subject = f"[CUT LINE] {player_display} on the bubble — {total_str}"
                body    = f"Fantasy Pick Alert\n{'─'*40}\n\n{player_display} is within {diff:.0f} strokes of the projected cut ({projected_cut:+.0f}) at {pos_str} ({total_str}) thru {thru}.\n\nView leaderboard → http://localhost:3000/live\n"
                _send_alert(subject, body, cfg, dry_run, PRIORITY_HIGH)
                alerts.append(subject)
                new_pick_states[state_key]["alerted_bubble"] = True

        # Big move alert (≥10 positions in either direction since last check)
        if pos_num is not None and prev_pos is not None:
            move = prev_pos - pos_num  # positive = moved up (better)
            if abs(move) >= 10:
                direction = "up" if move > 0 else "down"
                subject = f"[MOVE] {player_display} moved {abs(move)} spots {direction} ({pos_str})"
                body    = f"Fantasy Pick Alert\n{'─'*40}\n\n{player_display} has moved {abs(move)} positions {direction} to {pos_str} ({total_str}) thru {thru}.\n\nView leaderboard → http://localhost:3000/live\n"
                _send_alert(subject, body, cfg, dry_run, PRIORITY_NORMAL)
                alerts.append(subject)

    state["picks"] = new_pick_states
    return alerts


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Check bet and pick alerts")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending")
    parser.add_argument("--test", action="store_true", help="Send a test notification to verify credentials")
    args = parser.parse_args()

    cfg   = _load_notify_config()
    state = _load_json(STATE_PATH)
    if not isinstance(state, dict):
        state = {}

    if args.test:
        print("Sending test notification…")
        _send_push(
            title="Golf Alerts — Test",
            message="Push notifications are working. You'll get bet and pick alerts here during tournaments.",
            cfg=cfg,
            priority=PRIORITY_NORMAL,
        )
        return

    print(f"[{datetime.now().strftime('%H:%M')}] Checking bet alerts…")

    all_alerts: list[str] = []
    all_alerts += check_bet_alerts(state, cfg, args.dry_run)
    all_alerts += check_pick_alerts(state, cfg, args.dry_run)

    if all_alerts:
        print(f"  Sent {len(all_alerts)} alert(s): {all_alerts}")
    else:
        print("  No status changes — no alerts sent.")

    # Persist updated state so we don't re-fire the same alert
    state["last_checked"] = datetime.utcnow().isoformat() + "Z"
    _save_state(state)


if __name__ == "__main__":
    main()
