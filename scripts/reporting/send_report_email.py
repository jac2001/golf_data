#!/usr/bin/env python3
"""
Send post-tournament report and weekly preview by email.

Usage:
    python3 scripts/reporting/send_report_email.py                  # most recent results + this week's picks
    python3 scripts/reporting/send_report_email.py --tid R2026012   # specific tournament
    python3 scripts/reporting/send_report_email.py --preview        # print HTML, don't send

Setup (one-time):
    1. Enable 2-Step Verification on your Google account
    2. myaccount.google.com → Security → App Passwords → create "Golf Reports"
    3. Paste the 16-char password into GMAIL_APP_PASSWORD below
"""

from __future__ import annotations

import argparse
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
GMAIL_ADDRESS     = "jacklegnon@gmail.com"
GMAIL_APP_PASSWORD = "kjdq qeqd vyob xpnw"
TO_ADDRESS        = "jacklegnon@gmail.com"
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT  = Path(__file__).resolve().parents[2]
OUTPUTS       = PROJECT_ROOT / "outputs"
PICKS_REPORTS = OUTPUTS / "picks_reports"
PRED_HISTORY  = PROJECT_ROOT / "data" / "prediction_tracking" / "prediction_history.csv"
LATEST_PREDS  = OUTPUTS / "latest_predictions.csv"
SEASON_LOG    = OUTPUTS / "season_log.csv"
SCHEDULE_CSV  = PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_name(name: str) -> str:
    s = str(name).strip()
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first} {last}"
    return s


def _pos_label(pos) -> str:
    try:
        n = int(float(str(pos)))
        if n >= 999: return "MC"
        if n == 1:   return "WIN"
        return f"T{n}"
    except (ValueError, TypeError):
        return str(pos)


def _finish_color(label: str) -> str:
    if label == "WIN":                                    return "#00c44f"
    if label.startswith("T"):
        try:
            if int(label[1:]) <= 5:  return "#00c44f"
            if int(label[1:]) <= 10: return "#4cb8ff"
            if int(label[1:]) <= 20: return "#94a3b8"
        except ValueError:
            pass
    if label == "MC": return "#e53935"
    return "#64748b"


def load_latest_report_json() -> tuple[str | None, dict]:
    jsons = sorted(PICKS_REPORTS.glob("*_report.json")) if PICKS_REPORTS.exists() else []
    if not jsons:
        return None, {}
    latest = jsons[-1]
    with open(latest) as f:
        return latest.stem.replace("_report", ""), json.load(f)


def load_report_for_tid(tid: str) -> dict:
    if PRED_HISTORY.exists():
        df = pd.read_csv(PRED_HISTORY)
        row = df[df["tournament_id"] == tid]
        if not row.empty:
            t_name = row["tournament_name"].iloc[0].lower().replace(" ", "_").replace("'", "")
            path = PICKS_REPORTS / f"{t_name}_report.json"
            if path.exists():
                with open(path) as f:
                    return json.load(f)
    for p in (PICKS_REPORTS.glob("*_report.json") if PICKS_REPORTS.exists() else []):
        with open(p) as f:
            d = json.load(f)
        if d.get("tournament_id") == tid or tid in str(p):
            return d
    return {}


def get_fantasy_picks_for_tournament(tournament_name: str) -> dict | None:
    """Return season_log row matching the tournament name (fuzzy)."""
    if not SEASON_LOG.exists():
        return None
    df = pd.read_csv(SEASON_LOG)
    t_lower = tournament_name.lower()
    match = df[df["tournament"].str.lower().str.contains(t_lower[:15], na=False)]
    if match.empty:
        return None
    row = match.iloc[-1]
    return {
        "week":       row.get("week", ""),
        "tournament": row.get("tournament", ""),
        "wrp":        row.get("wrp", ""),
        "total":      row.get("total_earnings", ""),
        "players": [
            {"name": row.get("player_1", ""), "result": row.get("result_1", ""), "earnings": row.get("earnings_1", 0)},
            {"name": row.get("player_2", ""), "result": row.get("result_2", ""), "earnings": row.get("earnings_2", 0)},
            {"name": row.get("player_3", ""), "result": row.get("result_3", ""), "earnings": row.get("earnings_3", 0)},
        ],
    }


def get_top_model_picks(n: int = 5) -> list[dict]:
    if not LATEST_PREDS.exists():
        return []
    df = pd.read_csv(LATEST_PREDS)
    df = df.sort_values("win_prob", ascending=False).head(n)
    results = []
    for _, row in df.iterrows():
        results.append({
            "name":       _fmt_name(row.get("player_name", "?")),
            "win_prob":   round(float(row.get("win_prob", 0)) * 100, 1),
            "top10_prob": round(float(row.get("top10_prob", 0)) * 100, 1),
            "ev":         round(float(row.get("expected_value", 0)), 2),
            "odds":       row.get("dk_odds", row.get("odds", "N/A")),
        })
    return results


def get_this_week_tournament_name() -> str:
    if LATEST_PREDS.exists():
        df = pd.read_csv(LATEST_PREDS)
        if "tournament_name" in df.columns and not df.empty:
            return str(df["tournament_name"].iloc[0])
    return "This Week"


def get_season_summary() -> dict:
    if not SEASON_LOG.exists():
        return {}
    df = pd.read_csv(SEASON_LOG)
    df = df[df["total_earnings"].notna() & (df["total_earnings"] != "")]
    try:
        total = int(df["total_earnings"].astype(float).sum())
    except Exception:
        total = 0
    weeks = len(df)
    best_wrp = None
    if "wrp" in df.columns:
        wrp_vals = pd.to_numeric(df["wrp"], errors="coerce").dropna()
        if not wrp_vals.empty:
            best_wrp = int(wrp_vals.min())
    return {"total_earnings": total, "weeks_played": weeks, "best_wrp": best_wrp}


# ── HTML builder ──────────────────────────────────────────────────────────────

# Use table-based layout — flexbox/grid often strips in email clients
_CSS = """
<style>
  body    { margin:0; padding:0; background:#0f172a; font-family:Arial,Helvetica,sans-serif; color:#e2e8f0; }
  a       { color:#4cb8ff; text-decoration:none; }
  .wrap   { max-width:600px; margin:0 auto; padding:24px 16px; }
  .hdr    { background:#0b1929; border-radius:10px; padding:20px 24px; margin-bottom:20px;
            border-bottom:3px solid #00c44f; }
  .hdr h1 { margin:0 0 4px; font-size:22px; color:#00c44f; }
  .hdr p  { margin:0; color:#64748b; font-size:13px; }
  .card   { background:#1e293b; border-radius:8px; padding:16px 20px; margin-bottom:16px; }
  .card h3 { margin:0 0 12px; font-size:14px; color:#94a3b8; text-transform:uppercase;
             letter-spacing:.8px; border-bottom:1px solid #0f172a; padding-bottom:8px; }
  .row    { width:100%; border-collapse:collapse; }
  .row td { padding:7px 4px; border-bottom:1px solid #0f172a; font-size:13px; vertical-align:middle; }
  .badge  { display:inline-block; padding:2px 9px; border-radius:10px; font-size:12px;
            font-weight:700; color:#000; }
  .section-title { font-size:18px; font-weight:700; color:#e2e8f0; margin:24px 0 8px; }
  .footer { color:#475569; font-size:11px; text-align:center; margin-top:28px; }
</style>
"""


def _wrp_badge_html(wrp) -> str:
    try:
        n = int(float(str(wrp)))
        if n <= 3:   c = "#ffd700"
        elif n <= 10: c = "#00c44f"
        elif n <= 20: c = "#6ddb9a"
        else:         c = "#64748b"
        return f'<span class="badge" style="background:{c};">#{n}</span>'
    except Exception:
        return f'<span style="color:#64748b;font-size:12px;">{wrp or "—"}</span>'


def _money(val) -> str:
    try:
        return f"${int(float(str(val))):,}"
    except Exception:
        return "—"


def _section_results(report: dict, tid: str) -> str:
    if not report:
        return ""

    t_name = report.get("tournament", "Last Tournament")

    # Winner from top_picks_analysis
    tpa = report.get("top_picks_analysis", {})
    t5  = tpa.get("top_5_picks", {})
    players   = t5.get("players", [])
    positions = t5.get("positions", [])
    winner_name = "—"
    for p, pos in zip(players, positions):
        if pos == 1:
            winner_name = _fmt_name(p)
            break

    # Model's top-5 pre-tournament picks and how they did
    top5_rows = ""
    for p, pos in zip(players[:5], positions[:5]):
        label = _pos_label(pos)
        color = _finish_color(label)
        top5_rows += (
            f'<tr><td style="color:#e2e8f0;font-weight:600;">{p}</td>'
            f'<td style="text-align:right;">'
            f'<span class="badge" style="background:{color};">{label}</span>'
            f'</td></tr>'
        )

    # Calibration metrics
    metrics   = report.get("metrics", {})
    t10_rate  = metrics.get("top10_picks_hit_rate")
    pred_t10  = metrics.get("predicted_rate_top10")
    act_t10   = metrics.get("actual_rate_top10")
    t10_str   = f"{t10_rate:.0%}" if t10_rate is not None else "—"
    cal_str   = (f"Predicted {pred_t10:.1%} · Actual {act_t10:.1%}"
                 if pred_t10 is not None and act_t10 is not None else "")

    # Fantasy picks for this tournament
    fantasy = get_fantasy_picks_for_tournament(t_name)
    fantasy_html = ""
    if fantasy:
        pick_rows = ""
        for p in fantasy["players"]:
            if not p["name"]:
                continue
            result  = str(p["result"]) if p["result"] else "—"
            r_color = _finish_color(_pos_label(result))
            pick_rows += (
                f'<tr><td style="color:#e2e8f0;font-weight:600;">{p["name"]}</td>'
                f'<td style="text-align:center;">'
                f'<span class="badge" style="background:{r_color};">{result}</span>'
                f'</td>'
                f'<td style="text-align:right;color:#94a3b8;">{_money(p["earnings"])}</td>'
                f'</tr>'
            )
        wrp_html = _wrp_badge_html(fantasy["wrp"]) if fantasy["wrp"] else ""
        total_html = _money(fantasy["total"])
        fantasy_html = f"""
        <div class="card">
          <h3>WineTime Fantasy · Week {fantasy["week"]}</h3>
          <table class="row" style="margin-bottom:10px;">{pick_rows}</table>
          <table class="row">
            <tr>
              <td style="color:#64748b;font-size:12px;">Weekly Rank</td>
              <td style="text-align:right;">{wrp_html}</td>
            </tr>
            <tr>
              <td style="color:#64748b;font-size:12px;">Earnings</td>
              <td style="text-align:right;font-weight:700;color:#00c44f;">{total_html}</td>
            </tr>
          </table>
        </div>"""

    return f"""
    <div class="hdr">
      <h1>{t_name}</h1>
      <p>Post-Tournament Report</p>
    </div>

    <div class="card">
      <h3>Winner</h3>
      <table class="row">
        <tr>
          <td style="color:#e2e8f0;font-size:16px;font-weight:700;">{winner_name}</td>
          <td style="text-align:right;">
            <span class="badge" style="background:#00c44f;">WIN</span>
          </td>
        </tr>
      </table>
    </div>

    <div class="card">
      <h3>Model's Top-5 Picks — Results</h3>
      <table class="row">{top5_rows}</table>
      <p style="margin:10px 0 0;font-size:12px;color:#64748b;">
        Top-10 hit rate: <strong style="color:#e2e8f0;">{t10_str}</strong>
        {f"&nbsp;·&nbsp;{cal_str}" if cal_str else ""}
      </p>
    </div>

    {fantasy_html}
    """


def _section_this_week(picks: list[dict], tournament_name: str) -> str:
    if not picks:
        return ""

    rows = ""
    for p in picks:
        ev_color = "#00c44f" if p["ev"] > 0 else "#e53935"
        ev_str   = f"+{p['ev']:.2f}" if p["ev"] > 0 else f"{p['ev']:.2f}"
        rows += (
            f'<tr>'
            f'<td style="color:#e2e8f0;font-weight:600;">{p["name"]}</td>'
            f'<td style="text-align:center;color:#94a3b8;font-size:12px;">'
            f'Win {p["win_prob"]}% · T10 {p["top10_prob"]}%</td>'
            f'<td style="text-align:right;">'
            f'<span class="badge" style="background:{ev_color};">EV {ev_str}</span>'
            f'</td>'
            f'</tr>'
        )

    return f"""
    <p class="section-title">{tournament_name}</p>

    <div class="card">
      <h3>Model's Top 5 by Win Probability</h3>
      <table class="row">{rows}</table>
    </div>
    """


def _section_season(summary: dict) -> str:
    if not summary:
        return ""
    best = f"#{summary['best_wrp']}" if summary.get("best_wrp") else "—"
    return f"""
    <div class="card">
      <h3>2026 Season Summary</h3>
      <table class="row">
        <tr>
          <td style="color:#64748b;font-size:12px;">Total Earnings</td>
          <td style="text-align:right;font-weight:700;color:#00c44f;">{_money(summary["total_earnings"])}</td>
        </tr>
        <tr>
          <td style="color:#64748b;font-size:12px;">Weeks Played</td>
          <td style="text-align:right;color:#e2e8f0;">{summary["weeks_played"]}</td>
        </tr>
        <tr>
          <td style="color:#64748b;font-size:12px;">Best WRP Rank</td>
          <td style="text-align:right;color:#ffd700;font-weight:700;">{best}</td>
        </tr>
      </table>
    </div>
    """


def build_html_email(report: dict, tid: str, model_picks: list[dict]) -> str:
    date_str       = datetime.now().strftime("%B %d, %Y")
    this_week_name = get_this_week_tournament_name()
    season         = get_season_summary()

    body = (
        _section_results(report, tid)
        + _section_this_week(model_picks, this_week_name)
        + _section_season(season)
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">{_CSS}</head>
<body>
<div class="wrap">
  {body}
  <div class="footer">
    Golf Analytics Report &nbsp;·&nbsp; {date_str}<br>
    <a href="http://localhost:8501">Open Dashboard</a>
  </div>
</div>
</body>
</html>"""


# ── Sender ────────────────────────────────────────────────────────────────────

def send_email(subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html"))

    print(f"Connecting to Gmail SMTP...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())
    print(f"Sent to {TO_ADDRESS}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send golf report email")
    parser.add_argument("--tid",     help="Tournament ID (e.g. R2026012)")
    parser.add_argument("--preview", action="store_true", help="Print HTML, don't send")
    args = parser.parse_args()

    if args.tid:
        tid    = args.tid
        report = load_report_for_tid(tid)
    else:
        _, report = load_latest_report_json()
        tid = report.get("tournament_id", "recent")

    t_name      = report.get("tournament", "Golf Report")
    model_picks = get_top_model_picks(n=5)
    html        = build_html_email(report, tid, model_picks)
    subject     = f"Golf Report: {t_name} Results + This Week's Picks"

    if args.preview:
        print(html)
        return

    send_email(subject, html)


if __name__ == "__main__":
    main()
