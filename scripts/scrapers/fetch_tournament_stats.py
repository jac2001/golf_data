#!/usr/bin/env python3
"""
Tournament SG stats compatibility scraper.

This wrapper keeps the historical `fetch_tournament_stats.py` command stable
while delegating to `multi_year_stats_scraper_fixed.py`.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from multi_year_stats_scraper_fixed import (
    DEFAULT_OUTPUT_DIR,
    KEY_STATS,
    fetch_stat_for_tournament,
    get_tournaments_for_year,
    scrape_stats_for_year,
)


def _load_stat_catalog(project_root: Path) -> Dict[str, str]:
    """Load full PGA Tour stat catalog for --all-stats mode."""
    candidates = [
        project_root / "scripts" / "scrapers" / "pgatour_stat_id_catalog.csv",
        project_root / "pgatour_stat_id_catalog.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        catalog = pd.read_csv(path)
        return {
            str(row["stat_id"]).zfill(5): f"Stat {row['stat_id']}"
            for _, row in catalog.iterrows()
        }
    return dict(KEY_STATS)


def _tournament_sort_key(tournament_id: str) -> int:
    digits = "".join(ch for ch in str(tournament_id) if ch.isdigit())
    return int(digits) if digits else 0


def _latest_tournaments(year: int, refresh_latest: int, first_stat_id: str) -> List[dict]:
    tournaments = get_tournaments_for_year(year, first_stat_id)
    if not tournaments:
        return []
    tournaments = sorted(
        tournaments,
        key=lambda t: _tournament_sort_key(str(t.get("tournament_id", ""))),
        reverse=True,
    )
    return tournaments[:refresh_latest]


def _refresh_latest_only(
    year: int,
    output_dir: Path,
    refresh_latest: int,
    stats_to_scrape: Dict[str, str],
    sleep_time: float,
) -> bool:
    """Refresh only the latest N events and merge with any existing yearly file."""
    first_stat_id = next(iter(stats_to_scrape.keys()))
    target_events = _latest_tournaments(year, refresh_latest, first_stat_id)
    if not target_events:
        print(f"⚠️ No tournaments found for {year}")
        return False

    output_path = output_dir / f"tournament_stats_{year}.csv"
    refreshed_rows = []

    print(f"Refreshing latest {len(target_events)} tournament(s) for {year}...")
    for stat_id, stat_name in stats_to_scrape.items():
        for tournament in target_events:
            tid = str(tournament.get("tournament_id", "")).strip()
            tname = str(tournament.get("tournament_name", "")).strip()
            if not tid:
                continue
            print(f"  {tid} | {stat_name}")
            try:
                df = fetch_stat_for_tournament(
                    stat_id=stat_id,
                    stat_name=stat_name,
                    tournament_id=tid,
                    tournament_name=tname,
                    year=year,
                )
                if not df.empty:
                    refreshed_rows.append(df)
            except Exception as exc:  # pragma: no cover - network-path safety
                print(f"    ⚠️ Failed {tid} {stat_name}: {exc}")
            time.sleep(max(sleep_time, 0.0))

    if not refreshed_rows:
        print("⚠️ No stat rows returned during refresh")
        return False

    refreshed_df = pd.concat(refreshed_rows, ignore_index=True)
    target_ids = {str(t["tournament_id"]).strip() for t in target_events}

    if output_path.exists():
        existing = pd.read_csv(output_path)
        if "tournament_id" in existing.columns:
            existing = existing[~existing["tournament_id"].astype(str).isin(target_ids)]
        merged = pd.concat([existing, refreshed_df], ignore_index=True)
    else:
        merged = refreshed_df

    merged.to_csv(output_path, index=False)
    print(f"✅ Saved refreshed tournament stats: {output_path} ({len(merged):,} rows)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PGA Tour tournament SG stats")
    parser.add_argument("--year", type=int, required=True, help="Year to fetch")
    parser.add_argument(
        "--refresh-latest",
        type=int,
        default=0,
        help="Refresh only latest N tournaments and merge into yearly file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory (default: data/historical)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.4,
        help="Sleep between stat requests (seconds)",
    )
    parser.add_argument(
        "--all-stats",
        action="store_true",
        help="Use full stat catalog instead of SG key stats",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[2]

    stats_to_scrape = (
        _load_stat_catalog(project_root) if args.all_stats else dict(KEY_STATS)
    )

    if args.refresh_latest and args.refresh_latest > 0:
        ok = _refresh_latest_only(
            year=args.year,
            output_dir=output_dir,
            refresh_latest=int(args.refresh_latest),
            stats_to_scrape=stats_to_scrape,
            sleep_time=float(args.sleep),
        )
        raise SystemExit(0 if ok else 1)

    print(
        f"Running full tournament stats scrape for {args.year} "
        f"at {datetime.now().isoformat(timespec='seconds')}"
    )
    scrape_stats_for_year(
        year=args.year,
        output_dir=output_dir,
        stats_to_scrape=stats_to_scrape,
        sleep_time=float(args.sleep),
    )


if __name__ == "__main__":
    main()
