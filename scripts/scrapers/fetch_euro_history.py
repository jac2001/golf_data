"""
Euro (DPWT) history pull → DuckDB.
===================================
One-time archive fetch feeding the January euro model:
  - round-by-round scoring for every euro event DG has (2017–2026)
  - closing/opening win odds (bet365) where archived

Lands in data/golf_data.db as `euro_rounds` (one row per player-round)
and `euro_odds` (one row per player-event). Local-only by design — the
DB never ships to the cloud; this is training data, not runtime data.

Rerunnable: tables are rebuilt wholesale (CREATE OR REPLACE), and a
single event failing is logged and skipped, never fatal.

Usage:
    python3 scripts/scrapers/fetch_euro_history.py
"""

import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "golf_data.db"
BOOK = "bet365"  # deepest euro coverage in the odds archive


def main() -> None:
    events = [e for e in dg_get("/historical-raw-data/event-list", {"file_format": "json"})
              if str(e.get("tour", "")).lower() == "euro"]
    print(f"{len(events)} euro events in DG's archive")

    odds_list = {(e["event_id"], e["calendar_year"])
                 for e in dg_get("/historical-odds/event-list", {"tour": "euro", "file_format": "json"})
                 if e.get("outrights") == "yes"}
    print(f"{len(odds_list)} of them have archived outright odds")

    round_rows: list[dict] = []
    odds_rows: list[dict] = []
    failed_rounds: list[str] = []
    failed_odds: list[str] = []

    for i, ev in enumerate(events, 1):
        eid, year, name = ev["event_id"], ev["calendar_year"], ev["event_name"]
        try:
            raw = dg_get("/historical-raw-data/rounds",
                         {"tour": "euro", "event_id": eid, "year": year, "file_format": "json"})
            for p in raw.get("scores", []):
                base = {
                    "event_id": eid, "calendar_year": year, "event_name": name,
                    "date": ev.get("date"),
                    "dg_id": p.get("dg_id"), "player_name": p.get("player_name"),
                    "fin_text": p.get("fin_text"),
                }
                for rnd in (1, 2, 3, 4):
                    r = p.get(f"round_{rnd}")
                    if not isinstance(r, dict):
                        continue
                    row = dict(base)
                    row["round_num"] = rnd
                    # keep every stat DG provides for the round, as-is
                    row.update(r)
                    round_rows.append(row)
        except Exception as e:
            failed_rounds.append(f"{year} {name}: {str(e)[:80]}")

        if (eid, year) in odds_list:
            try:
                raw = dg_get("/historical-odds/outrights",
                             {"tour": "euro", "event_id": eid, "year": year,
                              "market": "win", "book": BOOK,
                              "odds_format": "decimal", "file_format": "json"})
                for o in raw.get("odds", []):
                    row = {"event_id": eid, "calendar_year": year, "event_name": name,
                           "book": BOOK, "market": "win"}
                    row.update(o)
                    odds_rows.append(row)
            except Exception as e:
                failed_odds.append(f"{year} {name}: {str(e)[:80]}")

        if i % 25 == 0:
            print(f"  {i}/{len(events)} events — {len(round_rows)} round rows, {len(odds_rows)} odds rows")
        time.sleep(0.3)  # stay well under DG's rate limit on ~574 calls

    rounds_df = pd.DataFrame(round_rows)
    odds_df = pd.DataFrame(odds_rows)
    print(f"\nfetched: {len(rounds_df)} player-rounds across "
          f"{rounds_df['event_id'].nunique() if not rounds_df.empty else 0} events; "
          f"{len(odds_df)} odds rows across "
          f"{odds_df['event_id'].nunique() if not odds_df.empty else 0} events")

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE OR REPLACE TABLE euro_rounds AS SELECT * FROM rounds_df")
    con.execute("CREATE OR REPLACE TABLE euro_odds AS SELECT * FROM odds_df")
    n_r = con.execute("SELECT count(*) FROM euro_rounds").fetchone()[0]
    n_o = con.execute("SELECT count(*) FROM euro_odds").fetchone()[0]
    con.close()
    print(f"DuckDB: euro_rounds={n_r} rows, euro_odds={n_o} rows -> {DB_PATH.name}")

    if failed_rounds:
        print(f"\n{len(failed_rounds)} round fetches failed:")
        for f in failed_rounds[:10]:
            print("  ", f)
    if failed_odds:
        print(f"{len(failed_odds)} odds fetches failed:")
        for f in failed_odds[:10]:
            print("  ", f)


if __name__ == "__main__":
    main()
