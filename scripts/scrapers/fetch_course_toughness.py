#!/usr/bin/env python3
"""
Fetch PGA Tour toughest course stats and save as CSV.

Attempts:
1) Parse PGA Tour stats page HTML for embedded JSON (__NEXT_DATA__).
2) If stat_id is found, call statdata API endpoint for the year.

Output:
    data/reference/course_toughness_<YEAR>.csv
    data/reference/course_toughness_latest.csv (copy)
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import requests



DEFAULT_URL = "https://www.pgatour.com/stats/course/toughest-course"
DEFAULT_API = (
    "https://statdata-api-prod.pgatour.com/api/clientfile/"
    "YTDEventStats?T_CODE=r&STAT_ID={stat_id}&YEAR={year}&format=json"
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
REF_DIR = DATA_DIR / "reference"


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def extract_next_data(html: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def find_stat_id(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in {"statid", "stat_id", "stat-id"}:
                return str(v)
            found = find_stat_id(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_stat_id(item)
            if found:
                return found
    return None


def find_rows(obj: Any) -> Optional[List[Dict[str, Any]]]:
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            keys = set().union(*(x.keys() for x in obj))
            key_l = {str(k).lower() for k in keys}
            if {"course", "coursename"} & key_l and {"scoring", "average", "avg"} & key_l:
                return obj
        for item in obj:
            found = find_rows(item)
            if found:
                return found
    elif isinstance(obj, dict):
        # Common table keys
        for key in ["rows", "tableRows", "stats", "data", "items"]:
            if key in obj and isinstance(obj[key], list):
                found = find_rows(obj[key])
                if found:
                    return found
        for v in obj.values():
            found = find_rows(v)
            if found:
                return found
    return None


def normalize_rows(rows: List[Dict[str, Any]], year: int, source_url: str, stat_id: Optional[str]) -> pd.DataFrame:
    out = []
    for r in rows:
        course = r.get("courseName") or r.get("course") or r.get("course_name") or ""
        tournament = r.get("tournamentName") or r.get("tournament") or r.get("eventName") or ""
        scoring = (
            r.get("scoringAverage")
            or r.get("scoringAverageToPar")
            or r.get("avgScore")
            or r.get("avg")
        )
        rounds = r.get("rounds") or r.get("roundsPlayed") or r.get("rds") or ""
        try:
            scoring = float(scoring)
        except Exception:
            scoring = None
        out.append(
            {
                "year": year,
                "course_name": str(course).strip(),
                "tournament_name": str(tournament).strip(),
                "scoring_avg_to_par": scoring,
                "rounds": rounds,
                "stat_id": stat_id,
                "source_url": source_url,
                "scraped_at": datetime.utcnow().strftime("%Y-%m-%d"),
            }
        )
    df = pd.DataFrame(out)
    df = df[df["course_name"].astype(str).str.len() > 0]
    return df



def normalize_course_stats_details(details: Dict[str, Any], year: int, source_url: str) -> pd.DataFrame:
    headers = details.get("headers", [])
    rows = details.get("rows", [])
    out = []

    # Build header map: normalize header names to keys
    # Headers: ['PAR', 'YARDS', 'AVG', '+/-', 'EAGLE-', 'BIRDIE', 'PAR', 'BOGEY', 'DBL BOGEY', 'DBL BOGEY+']
    header_map = {
        "PAR": "par",
        "YARDS": "yards",
        "AVG": "scoring_avg",
        "+/-": "scoring_to_par",
        "EAGLE-": "eagle_or_better",
        "BIRDIE": "birdies",
        "BOGEY": "bogeys",
        "DBL BOGEY": "dbl_bogeys",
        "DBL BOGEY+": "dbl_bogey_plus",
    }

    def to_float(x):
        if x is None:
            return None
        try:
            return float(str(x).replace(",", ""))
        except Exception:
            return None

    for r in rows:
        values = r.get("values", [])

        # Map headers -> values (handle duplicate PAR: first is course par, second is pars made)
        vals = {}
        par_seen = False
        for i, h in enumerate(headers):
            if h == "PAR" and par_seen:
                key = "pars"  # Second PAR is total pars made
            elif h == "PAR":
                key = "par"
                par_seen = True
            else:
                key = header_map.get(h, h.lower().replace(" ", "_"))
            val = values[i].get("value") if i < len(values) and isinstance(values[i], dict) else None
            vals[key] = val

        out.append({
            "year": year,
            "rank": r.get("rank"),
            "course_name": r.get("displayName", ""),
            "tournament_name": r.get("tournamentName", ""),
            "tournament_id": r.get("tournamentId", ""),
            "par": to_float(vals.get("par")),
            "yards": to_float(vals.get("yards")),
            "scoring_avg": to_float(vals.get("scoring_avg")),
            "scoring_to_par": to_float(vals.get("scoring_to_par")),
            "eagle_or_better": to_float(vals.get("eagle_or_better")),
            "birdies": to_float(vals.get("birdies")),
            "pars": to_float(vals.get("pars")),
            "bogeys": to_float(vals.get("bogeys")),
            "dbl_bogeys": to_float(vals.get("dbl_bogeys")),
            "dbl_bogey_plus": to_float(vals.get("dbl_bogey_plus")),
            "source_url": source_url,
            "scraped_at": datetime.now().strftime("%Y-%m-%d"),
        })

    return pd.DataFrame(out)
def fetch_api_data(stat_id: str, year: int, api_template: str) -> Optional[Dict[str, Any]]:
    url = api_template.format(stat_id=stat_id, year=year)
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def extract_stat_id_from_html(html: str) -> Optional[str]:
    # Look for statId or STAT_ID in raw HTML
    patterns = [
        r"statId\\s*[:=]\\s*\"?(\\d{2,6})\"?",
        r"STAT_ID\\s*[:=]\\s*\"?(\\d{2,6})\"?",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Season year (default: current year)")
    parser.add_argument("--url", default=DEFAULT_URL, help="Stats page URL")
    parser.add_argument("--api-template", default=DEFAULT_API, help="API template URL")
    parser.add_argument("--stat-id", default="", help="Force a STAT_ID if known")
    parser.add_argument("--debug", action="store_true", help="Write debug JSON if parsing fails")
    parser.add_argument("--output", default="", help="Output CSV path (optional)")
    args = parser.parse_args()

    REF_DIR.mkdir(parents=True, exist_ok=True)

    html = fetch_html(args.url)
    data = extract_next_data(html) or {}
    stat_id = args.stat_id or find_stat_id(data) or extract_stat_id_from_html(html)

    # Try dehydratedState > queries (Next.js pattern)
    df = pd.DataFrame()
    queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])

    for q in queries:
        qkey = q.get("queryKey", [])
        if qkey and qkey[0] == "courseStatDetails":
            details = q.get("state", {}).get("data", {})
            if details and details.get("rows"):
                df = normalize_course_stats_details(details, args.year, args.url)
                break

    # Fallback: Try direct courseStatsDetails structure
    if df.empty:
        details = data.get("data", {}).get("courseStatsDetails")
        if details and isinstance(details, dict) and details.get("rows"):
            df = normalize_course_stats_details(details, args.year, args.url)

    # Fallback to generic row finder
    if df.empty:
        rows = find_rows(data)
        if rows:
            df = normalize_rows(rows, args.year, args.url, stat_id)

    # If no rows from HTML, try API using stat_id
    if df.empty and stat_id:
        api_data = fetch_api_data(stat_id, args.year, args.api_template)
        if api_data:
            rows = find_rows(api_data) or []
            if rows:
                df = normalize_rows(rows, args.year, args.url, stat_id)

    if df.empty:
        if args.debug:
            dbg = REF_DIR / "course_toughness_debug.json"
            try:
                dbg.write_text(json.dumps(data, indent=2)[:200000])
                print(f"Wrote debug JSON: {dbg}")
            except Exception:
                pass
        raise SystemExit("No rows found. Check URL, stat_id, or API template.")

    output = Path(args.output) if args.output else (REF_DIR / f"course_toughness_{args.year}.csv")
    df.to_csv(output, index=False)

    latest = REF_DIR / "course_toughness_latest.csv"
    df.to_csv(latest, index=False)

    print(f"Saved: {output}")
    print(f"Updated: {latest}")


if __name__ == "__main__":
    main()
