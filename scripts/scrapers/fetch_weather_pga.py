#!/usr/bin/env python3
"""
Tournament daily/hourly forecast from PGA TOUR GraphQL → data/weather/{tid}.json.

This is the file /api/weather serves (daily Thu-Sun). Open-Meteo
(fetch_weather_openmetro.py) is a different adapter with a different output:
{tid}_hourly.json for draw advantage. Keep the two apart (audit finding 7).

Usage:
    python3 scripts/scrapers/fetch_weather_pga.py --tid R2026527

Exits 1 with the reason on failure, leaving any existing file untouched so
its saved_at stays an honest stale timestamp.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEATHER_DIR = PROJECT_ROOT / "data" / "weather"

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

WEATHER_QUERY = """
query Weather($tournamentId: ID!) {
  weather(tournamentId: $tournamentId) {
    title
    hourly {
      title condition windDirection windSpeedKPH windSpeedMPH humidity precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
    daily {
      title condition windDirection windSpeedKPH windSpeedMPH humidity precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
  }
}
"""


def save_weather_snapshot(tid: str, log=print) -> bool:
    """Fetch the forecast for `tid` and write data/weather/{tid}.json. True on success."""
    out_path = WEATHER_DIR / f"{tid}.json"
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": WEATHER_QUERY, "variables": {"tournamentId": tid},
                  "operationName": "Weather"},
            headers=GRAPHQL_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise RuntimeError(body["errors"][0].get("message", "Weather query failed"))
        w = (body.get("data") or {}).get("weather")
        if not (w and w.get("daily")):
            log(f"  PGA Tour weather API returned no daily data for {tid}")
            return False
        result = {
            "success": True,
            "source": "pgatour",
            "title": w.get("title", ""),
            "daily": w["daily"],
            "hourly": w.get("hourly", []),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        WEATHER_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        log(f"  Weather saved: {len(w['daily'])} days for {tid}")
        return True
    except Exception as e:
        log(f"  Weather snapshot failed for {tid}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch PGA TOUR tournament weather")
    parser.add_argument("--tid", required=True, help="Tournament ID, e.g. R2026527")
    args = parser.parse_args()
    ok = save_weather_snapshot(args.tid.upper(), log=lambda m: print(m, file=sys.stderr))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
