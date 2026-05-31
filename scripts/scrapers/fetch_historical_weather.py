#!/usr/bin/env python3
"""
Fetch historical weather for all tournaments in the training dataset.

HOW IT WORKS
------------
1. Pull the current-year PGA Tour schedule from DataGolf — it includes
   lat/lon coordinates for each venue and a `event_id` field.

2. PGA Tour tournament IDs follow the pattern R{year}{event_id:03d}.
   So DG event_id=14 in 2026 → R2026014 (The Masters).
   This same event_id maps across years: event_id=14 in 2024 → R2024014.

3. For historical years, we estimate tournament start dates by offsetting
   the known 2026 date backward: R2022014 ≈ (2026-04-09) − 4×365 days.
   Most PGA Tour events happen the same week each year, so we're typically
   within 2–3 days of the actual date — precise enough for weekly averages.

4. For each tournament we call Open-Meteo's free Archive API (no key needed)
   to get actual hourly wind/precip/temp for the 4 tournament days.

5. We average over daytime playing hours (8am–6pm local) to get conditions
   players actually experienced, not overnight readings.

OUTPUT
------
data/weather/tournament_weather.csv
  tournament_id   — e.g. R2022014
  wind_mph_avg    — mean daytime wind during tournament (most important)
  wind_mph_max    — peak hourly wind (captures "brutal day" signal)
  precip_mm       — total precipitation over 4 rounds
  temp_f_avg      — mean daytime temperature

Usage:
  python3 scripts/scrapers/fetch_historical_weather.py
  python3 scripts/scrapers/fetch_historical_weather.py --years 2024 2025
  python3 scripts/scrapers/fetch_historical_weather.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# Allow `from scripts.scrapers.dg_client import dg_get` regardless of cwd
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
WEATHER_DIR  = DATA_DIR / "weather"
PROCESSED_DIR = DATA_DIR / "processed"

OUTPUT_PATH = WEATHER_DIR / "tournament_weather.csv"
TRAINING_CSV = PROCESSED_DIR / "master_training_data_2016_2026.csv"

# ── Constants ─────────────────────────────────────────────────────────────────
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
# Archive data has a ~5-day lag vs real time; recent events fall back to NaN
ARCHIVE_LAG_DAYS = 7

# Playing hours: 8am–6pm local (indices 8–18 in the hourly array)
PLAY_HOUR_START = 8
PLAY_HOUR_END   = 18


# ── Open-Meteo archive fetch ──────────────────────────────────────────────────

def fetch_archive(lat: float, lon: float, start: date, end: date) -> dict | None:
    """Fetch hourly weather from Open-Meteo archive for a date range.

    Returns the parsed JSON dict, or None on failure.
    """
    params = {
        "latitude":          lat,
        "longitude":         lon,
        "start_date":        start.isoformat(),
        "end_date":          end.isoformat(),
        "hourly":            "windspeed_10m,precipitation,temperature_2m",
        "wind_speed_unit":   "mph",
        "temperature_unit":  "fahrenheit",
        "timezone":          "auto",
    }
    try:
        r = requests.get(OPEN_METEO_ARCHIVE, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [open-meteo] failed ({start}): {e}")
        return None


def summarise_weather(raw: dict) -> dict | None:
    """Collapse raw hourly Open-Meteo response into 4 summary stats.

    We only use daytime hours (8am–6pm local) so overnight calm periods
    don't dilute the tournament-conditions estimate.
    """
    if not raw or "hourly" not in raw:
        return None

    hourly = raw["hourly"]
    times  = hourly.get("time", [])
    wind   = hourly.get("windspeed_10m", [])
    precip = hourly.get("precipitation", [])
    temp   = hourly.get("temperature_2m", [])

    daytime_wind  = []
    daytime_temp  = []
    total_precip  = 0.0

    for i, t in enumerate(times):
        try:
            hour = int(t[11:13])  # "2022-04-07T14:00" → 14
        except Exception:
            continue

        # Include all hours for precip (rain can fall overnight)
        if i < len(precip) and precip[i] is not None:
            total_precip += float(precip[i])

        # Restrict wind and temp to playing hours
        if PLAY_HOUR_START <= hour < PLAY_HOUR_END:
            if i < len(wind) and wind[i] is not None:
                daytime_wind.append(float(wind[i]))
            if i < len(temp) and temp[i] is not None:
                daytime_temp.append(float(temp[i]))

    if not daytime_wind:
        return None

    return {
        "wind_mph_avg": round(sum(daytime_wind) / len(daytime_wind), 2),
        "wind_mph_max": round(max(daytime_wind), 2),
        "precip_mm":    round(total_precip, 2),
        "temp_f_avg":   round(sum(daytime_temp) / len(daytime_temp), 1) if daytime_temp else None,
    }


# ── DataGolf schedule lookup ──────────────────────────────────────────────────

def build_event_lookup() -> dict[int, tuple[float, float, date]]:
    """Return {event_id: (lat, lon, start_date_2026)} from DG schedule.

    The 2026 start dates let us estimate historical dates for any year:
        historical_date = 2026_date + (target_year - 2026) * 365 days
    """
    try:
        from scripts.scrapers.dg_client import dg_get
        data = dg_get("/get-schedule", {"tour": "pga"})
    except Exception as e:
        print(f"  [warn] Could not fetch DG schedule: {e}")
        return {}

    lookup: dict[int, tuple[float, float, date]] = {}
    for evt in data.get("schedule", []):
        try:
            eid  = int(evt["event_id"])
            lat  = float(evt["latitude"])
            lon  = float(evt["longitude"])
            d    = date.fromisoformat(evt["start_date"])
            lookup[eid] = (lat, lon, d)
        except Exception:
            continue

    print(f"  DG schedule loaded: {len(lookup)} events with coordinates")
    return lookup


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch historical tournament weather")
    parser.add_argument("--years",   nargs="+", type=int, help="Limit to specific years")
    parser.add_argument("--dry-run", action="store_true",  help="Show what would be fetched, don't call API")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip tournaments already in output CSV (default: True)")
    parser.add_argument("--no-skip", action="store_true", help="Refetch everything, overwrite existing")
    args = parser.parse_args()

    if args.no_skip:
        args.skip_existing = False

    WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load training data to get tournament list ──────────────────────────────
    if not TRAINING_CSV.exists():
        print(f"ERROR: Training data not found at {TRAINING_CSV}")
        return 1

    print("Loading training data...")
    df = pd.read_csv(TRAINING_CSV, usecols=["tournament_id", "year"], low_memory=False)
    tournaments = (
        df[["tournament_id", "year"]]
        .drop_duplicates()
        .sort_values(["year", "tournament_id"])
    )
    if args.years:
        tournaments = tournaments[tournaments["year"].isin(args.years)]

    print(f"  {len(tournaments)} unique tournaments across years: "
          f"{sorted(tournaments['year'].unique())[:5]}...{sorted(tournaments['year'].unique())[-1:]}")

    # ── Load existing results (for skip logic) ────────────────────────────────
    existing: set[str] = set()
    if args.skip_existing and OUTPUT_PATH.exists():
        existing_df = pd.read_csv(OUTPUT_PATH)
        existing = set(existing_df["tournament_id"].astype(str))
        print(f"  {len(existing)} tournaments already in {OUTPUT_PATH.name} — will skip")

    # ── Build DG event→coords lookup ─────────────────────────────────────────
    print("\nFetching DataGolf schedule for coordinates...")
    event_lookup = build_event_lookup()  # {event_id: (lat, lon, date_2026)}

    # ── Fetch weather per tournament ──────────────────────────────────────────
    today        = date.today()
    archive_cutoff = today - timedelta(days=ARCHIVE_LAG_DAYS)
    results: list[dict] = []
    skipped_no_coords = 0
    skipped_existing  = 0
    skipped_too_recent = 0

    print(f"\nFetching weather for {len(tournaments)} tournaments...")
    print("-" * 60)

    for i, (_, row) in enumerate(tournaments.iterrows(), 1):
        tid  = str(row["tournament_id"])
        year = int(row["year"])

        # Parse event_id from tournament_id: R2022014 → 14
        try:
            event_id = int(tid[5:])
        except Exception:
            skipped_no_coords += 1
            continue

        if args.skip_existing and tid in existing:
            skipped_existing += 1
            continue

        if event_id not in event_lookup:
            if i <= 10 or i % 50 == 0:
                print(f"  [{i:3d}] {tid}  — no DG coords, skip")
            skipped_no_coords += 1
            continue

        lat, lon, date_2026 = event_lookup[event_id]

        # Estimate historical start date by offsetting from 2026
        # 365 days per year is close enough (leap year error ≤ 1 day per 4 years)
        year_offset = year - 2026
        start = date_2026 + timedelta(days=year_offset * 365)
        end   = start + timedelta(days=3)  # 4-round tournament

        if start > archive_cutoff:
            skipped_too_recent += 1
            continue

        if args.dry_run:
            print(f"  [{i:3d}] {tid}  lat={lat:.2f} lon={lon:.2f}  {start} → {end}")
            continue

        raw     = fetch_archive(lat, lon, start, end)
        summary = summarise_weather(raw)

        if summary:
            results.append({"tournament_id": tid, **summary})
            if i % 25 == 0 or i <= 5:
                print(f"  [{i:3d}/{len(tournaments)}] {tid}  wind={summary['wind_mph_avg']:.1f}mph  "
                      f"precip={summary['precip_mm']:.1f}mm  temp={summary['temp_f_avg']}°F")
        else:
            print(f"  [{i:3d}] {tid}  — no data returned")

        # Be polite to Open-Meteo's free tier
        time.sleep(0.3)

    # ── Save / merge results ─────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n[dry-run] Would fetch ~{len(tournaments) - skipped_no_coords - skipped_existing - skipped_too_recent} tournaments")
        return 0

    if not results:
        print("\nNo new results to save.")
    else:
        new_df = pd.DataFrame(results)

        if args.skip_existing and OUTPUT_PATH.exists():
            old_df = pd.read_csv(OUTPUT_PATH)
            combined = pd.concat([old_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["tournament_id"], keep="last")
        else:
            combined = new_df

        combined = combined.sort_values("tournament_id").reset_index(drop=True)
        combined.to_csv(OUTPUT_PATH, index=False)
        print(f"\n✓ Saved {len(combined)} tournaments → {OUTPUT_PATH}")

    print(f"\nSummary:")
    print(f"  Fetched:          {len(results)}")
    print(f"  Skipped (existing): {skipped_existing}")
    print(f"  Skipped (no coords): {skipped_no_coords}")
    print(f"  Skipped (too recent): {skipped_too_recent}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
