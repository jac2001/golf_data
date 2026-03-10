#!/usr/bin/env python3
"""
Draw Advantage Calculator
=========================

Computes tee-time draw advantage based on hourly weather forecasts.
Players with calmer conditions during their round get a positive draw_advantage score.

Usage:
    python3 scripts/predictions/draw_advantage.py --tid R2026011 --round 1
    python3 scripts/predictions/draw_advantage.py --tid R2026011 --round 1 --date 2026-03-13
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
WEATHER_DIR = DATA_DIR / "weather"

# Roughly 4.5 hours to play 18 holes
ROUND_DURATION_HOURS = 4.5

# Timezone offset map (for parsing tee time strings)
_TZ_OFFSETS = {
    "EDT": -4, "EST": -5,
    "CDT": -5, "CST": -6,
    "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8,
    "BST": +1, "GMT": 0, "UTC": 0,
}


def _parse_tee_time_to_local_hour(tee_str: str) -> float | None:
    """Return local decimal hour (e.g., 7.783 for 7:47 AM) from tee time string."""
    if not tee_str or not tee_str.strip():
        return None
    try:
        parts = tee_str.strip().split()
        time_part = parts[0]
        ampm = parts[1].upper() if len(parts) > 1 else "AM"
        h_str, m_str = time_part.split(":")
        hour = int(h_str)
        minute = int(m_str)
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        return hour + minute / 60.0
    except Exception:
        return None


def load_hourly_weather(tid: str) -> pd.DataFrame:
    """Load hourly forecast JSON for given tournament ID."""
    path = WEATHER_DIR / f"{tid}_hourly.json"
    if not path.exists():
        return pd.DataFrame()
    with open(path) as f:
        records = json.load(f)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    # Parse time column to datetime
    df["dt"] = pd.to_datetime(df["time"], errors="coerce")
    df["hour"] = df["dt"].dt.hour + df["dt"].dt.minute / 60.0
    df["date_str"] = df["dt"].dt.strftime("%Y-%m-%d")
    return df


def get_weather_window(hourly_df: pd.DataFrame, local_hour: float, date_str: str) -> pd.DataFrame:
    """Get hourly rows within [local_hour, local_hour + 4.5) on date_str."""
    if hourly_df.empty:
        return pd.DataFrame()
    day_df = hourly_df[hourly_df["date_str"] == date_str].copy()
    if day_df.empty:
        # Fall back to first available date
        day_df = hourly_df.copy()
    end_hour = local_hour + ROUND_DURATION_HOURS
    window = day_df[(day_df["hour"] >= local_hour) & (day_df["hour"] < end_hour)]
    return window


def compute_draw_advantage(tid: str, round_num: int, date_str: str | None = None) -> pd.DataFrame:
    """
    Compute draw advantage for all players in the tee_times CSV.

    Args:
        tid: Tournament ID (e.g. 'R2026011')
        round_num: Round number (1-4)
        date_str: Date of the round as 'YYYY-MM-DD' (defaults to first date in hourly file)

    Returns:
        DataFrame with draw advantage columns, saved to data/live/draw_advantage_{tid}_r{round}.csv
    """
    tt_path = LIVE_DIR / f"tee_times_{tid}_r{round_num}.csv"
    if not tt_path.exists():
        raise FileNotFoundError(f"Tee times file not found: {tt_path}")

    tee_df = pd.read_csv(tt_path)
    if tee_df.empty:
        raise ValueError("Tee times CSV is empty")

    hourly_df = load_hourly_weather(tid)
    if hourly_df.empty:
        raise FileNotFoundError(f"Hourly weather not found: {WEATHER_DIR}/{tid}_hourly.json")

    # Determine date to use
    if not date_str:
        # Use first available date in the hourly file
        date_str = hourly_df["date_str"].dropna().iloc[0]
        print(f"No date specified, using first available: {date_str}")

    results = []
    for _, row in tee_df.iterrows():
        tee_str = str(row.get("tee_time_str", "") or "")
        local_hour = _parse_tee_time_to_local_hour(tee_str)
        if local_hour is None:
            continue

        am_pm = "AM" if local_hour < 12 else "PM"
        window = get_weather_window(hourly_df, local_hour, date_str)

        if window.empty:
            avg_wind = None
            max_gust = None
            avg_precip = None
        else:
            avg_wind = float(pd.to_numeric(window["wind_mph"], errors="coerce").mean())
            max_gust = float(pd.to_numeric(window["gusts_mph"], errors="coerce").max())
            avg_precip = float(pd.to_numeric(window["precip_pct"], errors="coerce").mean())

        results.append({
            "player_id": row.get("player_id", ""),
            "player_name": row.get("player_name", ""),
            "round": round_num,
            "tee_time_str": tee_str,
            "tee_hour": round(local_hour, 2),
            "am_pm": am_pm,
            "window_avg_wind": avg_wind,
            "window_max_gust": max_gust,
            "window_precip_pct": avg_precip,
        })

    df = pd.DataFrame(results)
    if df.empty:
        print("No valid tee times to compute advantage for.")
        return df

    # Compute draw advantage: positive = calmer than field avg (favorable)
    valid_wind = df["window_avg_wind"].dropna()
    field_avg = float(valid_wind.mean()) if not valid_wind.empty else 0.0
    df["field_avg_wind"] = round(field_avg, 1)
    df["draw_advantage"] = (field_avg - df["window_avg_wind"]).round(1)

    # Tier labels
    df["draw_tier"] = pd.cut(
        df["draw_advantage"],
        bins=[-99, -3, -1, 1, 3, 99],
        labels=["Strong Disadv", "Disadv", "Neutral", "Adv", "Strong Adv"],
    ).astype(str)

    out_path = LIVE_DIR / f"draw_advantage_{tid}_r{round_num}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved draw advantage → {out_path}")

    # Print AM vs PM summary
    am_avg = df[df["am_pm"] == "AM"]["window_avg_wind"].mean()
    pm_avg = df[df["am_pm"] == "PM"]["window_avg_wind"].mean()
    if pd.notna(am_avg) and pd.notna(pm_avg):
        fav = "AM" if am_avg < pm_avg else "PM"
        print(f"AM avg wind: {am_avg:.1f} mph | PM avg wind: {pm_avg:.1f} mph → {fav} draw favored")

    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute tee time draw advantage")
    parser.add_argument("--tid", required=True, help="Tournament ID, e.g. R2026011")
    parser.add_argument("--round", type=int, default=1, dest="round_num")
    parser.add_argument("--date", type=str, default="", help="Round date YYYY-MM-DD")
    args = parser.parse_args()

    date_str = args.date if args.date else None
    df = compute_draw_advantage(args.tid, args.round_num, date_str)
    if not df.empty:
        print(df[["player_name", "tee_time_str", "am_pm", "window_avg_wind", "draw_advantage", "draw_tier"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
