#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get


def fetch_matchups():
    return dg_get("/betting-tools/matchups-all-pairings", {
        "market": "tournament_matchups",
        "odds_format": "american"
    })


def parse_response(data) -> pd.DataFrame:
    rows       = data.get("pairings", [])
    last_update = data.get("last_update", "")
    event_name = data.get("event_name", "")
    round_num  = data.get("round", "")
    records = []

    for pairing in rows:
        p1 = pairing.get("p1", {})
        p2 = pairing.get("p2", {})
        p3 = pairing.get("p3", {})
        records.append({
            "event_name":  event_name,
            "round":       round_num,
            "last_update": last_update,
            "group":       pairing.get("group"),
            "teetime":     pairing.get("teetime"),
            "start_hole":  pairing.get("start_hole"),
            "p1_dg_id":    p1.get("dg_id"),
            "p1_name":     p1.get("name", ""),
            "p1_odds":     p1.get("odds"),
            "p2_dg_id":    p2.get("dg_id"),
            "p2_name":     p2.get("name", ""),
            "p2_odds":     p2.get("odds"),
            "p3_dg_id":    p3.get("dg_id"),
            "p3_name":     p3.get("name", ""),
            "p3_odds":     p3.get("odds"),
        })
    return pd.DataFrame(records)


DATA_DIR = PROJECT_ROOT / "data"
DG_DIR   = DATA_DIR / "datagolf"


def main():
    DG_DIR.mkdir(parents=True, exist_ok=True)
    print("[INFO] Fetching DG Matchups...")
    data = fetch_matchups()
    df = parse_response(data)
    print(f"[INFO] {len(df)} pairings")
    out_path = DG_DIR / "dg_matchups_latest.csv"
    df.to_csv(out_path, index=False)
    print(f"[OK] Saved → {out_path}")
    print(df[["teetime", "p1_name", "p1_odds", "p2_name", "p2_odds", "p3_name", "p3_odds"]].head(10).to_string(index=False))

    try:
        from scripts.database.upsert_dg import upsert_table
        upsert_table("dg_matchups")
        print("[OK] DB updated → dg_matchups")
    except Exception as _e:
        print(f"[WARN] DB upsert skipped: {_e}")


if __name__ == "__main__":
    main()
