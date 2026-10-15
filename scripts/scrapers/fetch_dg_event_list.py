#!/usr/bin/env python3
"""
Refresh data/raw/dg_pga_event_list.csv: every PGA TOUR event DataGolf's
historical archive lists, with its date (DG's `date` is the final-round
date). event_dates.py turns these into the real date of each tournament_id,
which training and serving use to order a player's past events.

Run weekly (data-refresh Monday step). Without it the file freezes: the
first version ended at Baycurrent (2026-10-11), so every later event would
have had no date and been dropped from players' form (stats review,
2026-10-15).

Usage:
    python3 scripts/scrapers/fetch_dg_event_list.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dg_client import dg_get  # noqa: E402

OUT = ROOT / "data" / "raw" / "dg_pga_event_list.csv"


def main() -> None:
    raw = dg_get("/historical-raw-data/event-list", {"file_format": "json"})
    ev = pd.DataFrame(raw)
    ev = ev[ev["tour"].astype(str).str.lower() == "pga"]
    ev = ev[pd.to_numeric(ev["calendar_year"], errors="coerce") >= 2014]
    if ev.empty:
        raise SystemExit("DG event list returned no PGA events — keeping the existing file")
    out = (ev[["calendar_year", "event_id", "date", "event_name"]]
           .assign(date=lambda d: pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d"))
           .sort_values(["date", "event_id"]))
    old = len(pd.read_csv(OUT)) if OUT.exists() else 0
    if len(out) < old:
        raise SystemExit(f"DG returned {len(out)} events, fewer than the {old} on file — refusing to shrink it")
    out.to_csv(OUT, index=False)
    print(f"{len(out)} PGA events (was {old}); latest {out['date'].max()}: "
          f"{out.iloc[-1]['event_name']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
