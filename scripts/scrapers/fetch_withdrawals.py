"""
Fetch Withdrawal Alerts
=======================
Detects player withdrawals (WD) using three sources:

1. Live leaderboard CSV — players with status == "WD" or "WITHDRAWN"
2. Field vs predictions comparison — player_ids in field but absent from
   predictions (suggesting a late withdrawal after predictions were run)
3. PGA Tour GraphQL field API — real-time withdrawn/alternate flags from the
   official field endpoint (catches pre-tournament WDs before leaderboard exists)

Saves results to:  data/news/withdrawals_{tournament_id}.json

With --auto-update-field, also removes confirmed WDs from the stored field CSV
so the next prediction run excludes them automatically.

Usage:
    python3 scripts/scrapers/fetch_withdrawals.py
    python3 scripts/scrapers/fetch_withdrawals.py --tournament-id R2026007
    python3 scripts/scrapers/fetch_withdrawals.py --tournament-id R2026041 --auto-update-field
"""

import sys
import json
import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT   = Path(__file__).parent.parent.parent
DATA_DIR       = PROJECT_ROOT / "data"
LIVE_DIR       = DATA_DIR / "live"
FIELDS_DIR     = DATA_DIR / "fields"
NEWS_DIR       = DATA_DIR / "news"
OUTPUTS_DIR    = PROJECT_ROOT / "outputs"

_GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
_GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}
_FIELD_QUERY = """
query TournamentField($id: ID!) {
  field(id: $id) {
    players {
      id
      firstName
      lastName
      withdrawn
      alternate
    }
  }
}
"""


def _latest_leaderboard(tournament_id: str | None = None) -> Path | None:
    """Return the most recent leaderboard CSV, optionally filtered by tournament."""
    candidates = sorted(
        LIVE_DIR.glob("leaderboard_r*.csv"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if tournament_id:
        tid_lc = tournament_id.lower()
        filtered = [p for p in candidates if tid_lc in p.name.lower()]
        if filtered:
            return filtered[0]
    return candidates[0] if candidates else None


def _detect_from_leaderboard(lb_path: Path) -> list[dict]:
    """Find WD/Withdrawn entries in the live leaderboard."""
    wds = []
    try:
        df = pd.read_csv(lb_path)
        if "status" in df.columns and "player_name" in df.columns:
            wd_mask = df["status"].astype(str).str.upper().isin(["WD", "WITHDRAWN", "DQ"])
            for _, row in df[wd_mask].iterrows():
                wds.append({
                    "player_name": str(row["player_name"]).strip(),
                    "player_id":   str(row.get("player_id", "")).strip(),
                    "status":      str(row["status"]).strip().upper(),
                    "source":      "leaderboard",
                })
    except Exception as e:
        print(f"  Warning: could not read leaderboard {lb_path.name}: {e}")
    return wds


def _detect_from_field_vs_predictions(tournament_id: str | None) -> list[dict]:
    """
    Compare field CSV to latest_predictions.csv.
    Players present in the field but missing from predictions =
    likely withdrew after predictions were generated.
    """
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not preds_path.exists():
        return []

    preds = pd.read_csv(preds_path)
    if "player_id" not in preds.columns:
        return []
    pred_ids = set(preds["player_id"].astype(str).str.strip())

    # Find best field file
    field_file = None
    if tournament_id:
        candidates = list(FIELDS_DIR.glob(f"*{tournament_id.lower()}*"))
        if candidates:
            field_file = max(candidates, key=lambda p: p.stat().st_mtime)

    if field_file is None:
        all_fields = sorted(FIELDS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if all_fields:
            field_file = all_fields[0]

    if field_file is None:
        return []

    wds = []
    try:
        field_df = pd.read_csv(field_file)
        if "player_id" in field_df.columns and "player_name" in field_df.columns:
            field_df["player_id"] = field_df["player_id"].astype(str).str.strip()
            missing = field_df[~field_df["player_id"].isin(pred_ids)]
            for _, row in missing.iterrows():
                wds.append({
                    "player_name": str(row["player_name"]).strip(),
                    "player_id":   str(row["player_id"]).strip(),
                    "status":      "POSSIBLE_WD",
                    "source":      "field_vs_predictions",
                })
    except Exception as e:
        print(f"  Warning: could not compare field file {field_file.name}: {e}")

    return wds


def _detect_from_live_pga_field(tournament_id: str) -> list[dict]:
    """
    Query the PGA Tour GraphQL field endpoint and find players flagged as
    withdrawn or alternate, then cross-reference against our stored field CSV.

    Two signals:
      withdrawn == true  → confirmed WD per PGA Tour
      player in stored field but absent from live API response → likely WD

    This runs before the tournament starts so the leaderboard doesn't exist yet.
    Returns list of dicts with player_name, player_id, status, source.
    """
    # ── Load our stored field ─────────────────────────────────────────────────
    field_path = FIELDS_DIR / f"field_{tournament_id}.csv"
    if not field_path.exists():
        print(f"  No stored field found at {field_path.name} — skipping live check")
        return []

    try:
        stored = pd.read_csv(field_path)
        stored["player_id"] = stored["player_id"].astype(str).str.strip()
    except Exception as e:
        print(f"  Warning: could not read stored field: {e}")
        return []

    stored_map = {r["player_id"]: r["player_name"] for _, r in stored.iterrows()}

    # ── Fetch live field from PGA Tour GraphQL ────────────────────────────────
    try:
        resp = requests.post(
            _GRAPHQL_URL,
            headers=_GRAPHQL_HEADERS,
            json={"query": _FIELD_QUERY, "variables": {"id": tournament_id}},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Warning: PGA Tour field API error: {e}")
        return []

    players = (data.get("data") or {}).get("field", {}).get("players") or []
    if not players:
        print("  PGA Tour field API returned no players")
        return []

    live_ids = set()
    wds: list[dict] = []

    for p in players:
        pid = str(p.get("id", "")).strip()
        if not pid:
            continue

        live_ids.add(pid)
        name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()

        if p.get("withdrawn"):
            # Confirmed WD flag from PGA Tour
            # Try to match stored name (Last, First format) for consistency
            stored_name = stored_map.get(pid, name)
            wds.append({
                "player_name": stored_name,
                "player_id":   pid,
                "status":      "WITHDRAWN",
                "source":      "pga_field_api",
            })

    # Players in our field but completely absent from the live API response
    # are likely WDs that haven't been flagged yet (PGA Tour sometimes removes
    # them before setting the withdrawn flag)
    for pid, pname in stored_map.items():
        if pid not in live_ids:
            wds.append({
                "player_name": pname,
                "player_id":   pid,
                "status":      "WITHDRAWN",
                "source":      "pga_field_api_missing",
            })

    n_flagged = sum(1 for w in wds if w["source"] == "pga_field_api")
    n_missing = sum(1 for w in wds if w["source"] == "pga_field_api_missing")
    print(f"  PGA field API: {len(players)} players live, "
          f"{n_flagged} withdrawn flag(s), {n_missing} missing from live field")
    return wds


def _auto_update_field(tournament_id: str, wd_ids: set[str]) -> int:
    """
    Remove confirmed WD player_ids from the stored field CSV.
    Returns number of players removed.
    """
    field_path = FIELDS_DIR / f"field_{tournament_id}.csv"
    if not field_path.exists() or not wd_ids:
        return 0
    try:
        df = pd.read_csv(field_path)
        df["player_id"] = df["player_id"].astype(str).str.strip()
        before = len(df)
        df = df[~df["player_id"].isin(wd_ids)]
        removed = before - len(df)
        if removed:
            df.to_csv(field_path, index=False)
            print(f"  ✂  Removed {removed} WD player(s) from {field_path.name}")
        return removed
    except Exception as e:
        print(f"  Warning: could not update field file: {e}")
        return 0


def fetch_withdrawals(
    tournament_id: str | None = None,
    auto_update_field: bool = False,
) -> list[dict]:
    """
    Detect withdrawals from three sources and merge results.

    auto_update_field: if True, removes confirmed WDs from the stored field CSV.
    The caller (scheduled_refresh, run_pipeline) can then decide whether to
    rerun predictions.
    """
    lb_path = _latest_leaderboard(tournament_id)

    all_wds: list[dict] = []

    # Source 1: live leaderboard (in-tournament WDs)
    if lb_path:
        lb_wds = _detect_from_leaderboard(lb_path)
        all_wds.extend(lb_wds)
        print(f"  Leaderboard check: {len(lb_wds)} WD(s) found in {lb_path.name}")
    else:
        print("  No leaderboard file found — skipping leaderboard check")

    # Source 2: field vs predictions (late WDs after predictions were run)
    field_wds = _detect_from_field_vs_predictions(tournament_id)
    existing_ids = {w["player_id"] for w in all_wds if w["player_id"]}
    for w in field_wds:
        if w["player_id"] not in existing_ids:
            all_wds.append(w)
    if field_wds:
        print(f"  Field comparison: {len(field_wds)} possible WD(s) detected")

    # Source 3: PGA Tour GraphQL field API (pre-tournament WDs)
    if tournament_id:
        live_wds = _detect_from_live_pga_field(tournament_id)
        existing_ids = {w["player_id"] for w in all_wds if w["player_id"]}
        new_live = [w for w in live_wds if w["player_id"] not in existing_ids]
        all_wds.extend(new_live)

    # Stamp detection time on any entry that doesn't have one
    for w in all_wds:
        w.setdefault("detected_at", datetime.now().isoformat())

    # Auto-remove confirmed WDs from stored field CSV if requested
    if auto_update_field and tournament_id:
        confirmed_ids = {
            w["player_id"] for w in all_wds
            if w["status"] == "WITHDRAWN" and w["player_id"]
        }
        if confirmed_ids:
            _auto_update_field(tournament_id, confirmed_ids)

    # Save — merge with any previously saved entries so manual additions persist
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    tid = tournament_id or "latest"
    out_path = NEWS_DIR / f"withdrawals_{tid}.json"

    existing_records: list[dict] = []
    if out_path.exists():
        try:
            existing_records = json.loads(out_path.read_text())
        except Exception:
            pass

    # Merge: keep existing records, add new ones not already present (by player_id)
    existing_pid_set = {r["player_id"] for r in existing_records if r.get("player_id")}
    for w in all_wds:
        if w["player_id"] not in existing_pid_set:
            existing_records.append(w)
            existing_pid_set.add(w["player_id"])

    with open(out_path, "w") as f:
        json.dump(existing_records, f, indent=2)

    print(f"  ✅ Saved {len(existing_records)} withdrawal record(s) → {out_path.name}")
    return existing_records


def main():
    parser = argparse.ArgumentParser(description="Detect player withdrawals")
    parser.add_argument("--tournament-id", "-t", default=None)
    parser.add_argument(
        "--auto-update-field", action="store_true",
        help="Remove confirmed WDs from the stored field CSV automatically"
    )
    args = parser.parse_args()

    print(f"\n🔍 Checking withdrawals (tournament: {args.tournament_id or 'auto'})")
    wds = fetch_withdrawals(args.tournament_id, auto_update_field=args.auto_update_field)
    if wds:
        print("\n  Withdrawals / Possible WDs:")
        for w in wds:
            print(f"    • {w['player_name']} ({w['status']}) via {w['source']}")
    else:
        print("  No withdrawals detected.")
    print()


if __name__ == "__main__":
    main()
