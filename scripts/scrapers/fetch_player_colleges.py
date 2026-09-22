"""
Player → college mapping from PGA Tour player bios.
====================================================
Feeds the College Game: data/players/player_colleges.csv
(player_id, player_name, school). Players with no school in their bio
(most internationals) get an empty school and simply don't count for
any college — the game only sees schools with alumni in the field.

Rerunnable; refetches everyone. ~1 request per player, gently paced.
"""

import sys
import time
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAYERS_CSV = PROJECT_ROOT / "data" / "players" / "pga_players_2026.csv"
OUT = PROJECT_ROOT / "data" / "players" / "player_colleges.csv"

URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {"x-pgat-platform": "web", "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
           "Content-Type": "application/json"}
QUERY = """query Player($id: ID!) { player(id: $id) { id displayName playerBio { school } } }"""


def fetch_school(pid: str) -> tuple[str, str]:
    r = requests.post(URL, headers=HEADERS, timeout=15,
                      json={"operationName": "Player", "query": QUERY, "variables": {"id": pid}})
    r.raise_for_status()
    p = (r.json().get("data") or {}).get("player") or {}
    return str(p.get("displayName") or ""), str((p.get("playerBio") or {}).get("school") or "")


def main() -> None:
    df = pd.read_csv(PLAYERS_CSV)
    df = df[pd.to_numeric(df["player_id"], errors="coerce").notna()].reset_index(drop=True)
    rows, failed = [], 0
    for i, r in df.iterrows():
        pid = str(int(r["player_id"]))
        try:
            name, school = fetch_school(pid)
            rows.append({"player_id": pid,
                         "player_name": name or str(r.get("player_name", "")),
                         "school": school})
        except Exception:
            failed += 1
            rows.append({"player_id": pid, "player_name": str(r.get("player_name", "")), "school": ""})
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(df)} players")
        time.sleep(0.25)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    n = (out["school"].str.len() > 0).sum()
    print(f"{len(out)} players, {n} with a school ({failed} fetch failures) -> {OUT.relative_to(PROJECT_ROOT)}")
    print(out[out["school"].str.len() > 0]["school"].value_counts().head(10))


if __name__ == "__main__":
    main()
