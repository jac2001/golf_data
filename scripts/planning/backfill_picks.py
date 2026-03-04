"""
Backfill picks table with model_rank (from prediction_history) and
opening_odds / opening_implied_prob (from pga_odds_{tid}.csv).

Usage:
    python3 scripts/planning/backfill_picks.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def normalize(name: str) -> str:
    import unicodedata
    if not name:
        return ""
    n = str(name).strip().lower()
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.encode("ascii", "ignore").decode("ascii")
    # "Last, First" → "First Last"
    if ", " in n:
        parts = n.split(", ", 1)
        n = f"{parts[1]} {parts[0]}"
    return n


def build_model_rank_lookup(pred_hist: pd.DataFrame) -> dict:
    """Rank players by win_prob within each tournament.

    Returns two lookups:
      - by_tid:  {(tid_upper, norm_name): rank}   e.g. ("R2026007", "rory mcilroy")
      - by_name: {(norm_tournament, norm_name): rank}  e.g. ("cognizant classic", "player")

    For duplicate prediction runs of the same tournament (multiple date-slug IDs),
    uses the latest run (max tournament_id string, which sorts by date prefix).
    """
    # Group by normalized tournament_name, pick latest run per tournament
    pred_hist = pred_hist.copy()
    pred_hist["_t_norm"] = pred_hist["tournament_name"].apply(lambda x: normalize(str(x)))
    # Within each tournament_name group, keep only the latest tournament_id
    latest_ids = (
        pred_hist.groupby("_t_norm")["tournament_id"]
        .apply(lambda s: sorted(s.unique())[-1])  # latest lexicographically = latest date slug
        .to_dict()
    )
    pred_hist = pred_hist[pred_hist.apply(
        lambda r: r["tournament_id"] == latest_ids.get(r["_t_norm"]), axis=1
    )]

    by_tid = {}
    by_name = {}
    for (tid, t_norm), grp in pred_hist.groupby(["tournament_id", "_t_norm"]):
        ranked = grp.sort_values("predicted_win_prob", ascending=False).reset_index(drop=True)
        for i, row in ranked.iterrows():
            p_norm = normalize(row["player_name"])
            rank = i + 1
            by_tid[(str(tid).upper(), p_norm)] = rank
            by_name[(t_norm, p_norm)] = rank
    return by_tid, by_name


def build_odds_lookup(schedule_df: pd.DataFrame) -> dict:
    """Load pga_odds_{tid}.csv for each tournament → {(tid, norm_name): (odds_str, implied_prob)}"""
    lookup = {}
    odds_dir = DATA_DIR / "odds"
    for _, row in schedule_df.iterrows():
        tid = str(row.get("tournament_id", "")).upper()
        if not tid:
            continue
        odds_file = odds_dir / f"pga_odds_{tid}.csv"
        if not odds_file.exists():
            continue
        try:
            odf = pd.read_csv(odds_file)
        except Exception:
            continue
        for _, orow in odf.iterrows():
            key = (tid, normalize(orow.get("player_name", "")))
            odds_val = orow.get("odds_to_win")
            impl = orow.get("implied_prob")
            if pd.notna(odds_val):
                # Format as American odds string (+XXXX or -XXX)
                odds_int = int(odds_val)
                odds_str = f"+{odds_int}" if odds_int >= 0 else str(odds_int)
                lookup[key] = (odds_str, float(impl) if pd.notna(impl) else None)
    return lookup


def backfill(dry_run: bool = False):
    from scripts.database.db import get_conn

    # Load picks from DB
    with get_conn(read_only=True) as conn:
        picks_df = conn.execute("SELECT * FROM picks").fetchdf()

    print(f"Picks loaded: {len(picks_df)} rows")

    # Load prediction_history
    pred_hist_path = OUTPUTS_DIR / "prediction_history.csv"
    if not pred_hist_path.exists():
        print("prediction_history.csv not found — skipping model_rank backfill")
        pred_hist = pd.DataFrame()
    else:
        pred_hist = pd.read_csv(pred_hist_path)

    # Load schedule for tournament_id mapping
    schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
    schedule_df = pd.read_csv(schedule_path) if schedule_path.exists() else pd.DataFrame()

    # Build tournament name → id map for picks that lack tournament_id
    name_to_tid = {}
    if not schedule_df.empty:
        for _, row in schedule_df.iterrows():
            name_to_tid[row["tournament_name"].strip().lower()] = str(row["tournament_id"]).upper()

    # Resolve tournament_id for each pick
    def resolve_tid(row):
        if row.get("tournament_id") and str(row["tournament_id"]) != "None":
            return str(row["tournament_id"]).upper()
        t_name = str(row.get("tournament", "")).strip().lower()
        return name_to_tid.get(t_name, "")

    picks_df["resolved_tid"] = picks_df.apply(resolve_tid, axis=1)

    # Build lookups
    if not pred_hist.empty:
        rank_by_tid, rank_by_name = build_model_rank_lookup(pred_hist)
    else:
        rank_by_tid, rank_by_name = {}, {}
    odds_lookup = build_odds_lookup(schedule_df) if not schedule_df.empty else {}

    print(f"model_rank lookup: {len(rank_by_tid)} entries (tid) + {len(rank_by_name)} (name)")
    print(f"odds lookup: {len(odds_lookup)} entries")

    updates = []
    for _, pick in picks_df.iterrows():
        tid = pick["resolved_tid"]
        norm = normalize(pick["player_name"])
        t_norm = normalize(str(pick.get("tournament", "")))

        model_rank = rank_by_tid.get((tid, norm)) or rank_by_name.get((t_norm, norm))
        odds_info = odds_lookup.get((tid, norm))
        opening_odds = odds_info[0] if odds_info else None
        opening_implied = odds_info[1] if odds_info else None

        current_rank = pick.get("model_rank")
        current_odds = pick.get("opening_odds")

        rank_changed = model_rank is not None and (
            pd.isna(current_rank) or current_rank != model_rank
        )
        odds_changed = opening_odds is not None and (
            pd.isna(current_odds) or current_odds != opening_odds
        )

        if rank_changed or odds_changed:
            updates.append({
                "season": pick["season"],
                "week": pick["week"],
                "player_name": pick["player_name"],
                "model_rank": model_rank if rank_changed else (
                    None if pd.isna(current_rank) else int(current_rank)
                ),
                "opening_odds": opening_odds if odds_changed else current_odds,
                "opening_implied_prob": opening_implied if odds_changed else (
                    pick.get("opening_implied_prob")
                ),
            })
            status = []
            if rank_changed:
                status.append(f"rank={model_rank}")
            if odds_changed:
                status.append(f"odds={opening_odds} ({opening_implied:.1%})" if opening_implied else f"odds={opening_odds}")
            print(f"  Wk{pick['week']} {pick['player_name']}: {', '.join(status)}")

    print(f"\n{len(updates)} picks to update")

    if dry_run:
        print("DRY RUN — no changes saved")
        return

    if not updates:
        print("Nothing to update")
        return

    with get_conn() as conn:
        for u in updates:
            conn.execute("""
                UPDATE picks
                SET model_rank = ?, opening_odds = ?, opening_implied_prob = ?,
                    updated_at = current_timestamp
                WHERE season = ? AND week = ? AND player_name = ?
            """, [
                u["model_rank"], u["opening_odds"], u["opening_implied_prob"],
                u["season"], u["week"], u["player_name"],
            ])
    print("Backfill complete")

    # Show final state
    with get_conn(read_only=True) as conn:
        result = conn.execute("""
            SELECT week, player_name, result, fedex_points, model_rank,
                   opening_odds, opening_implied_prob
            FROM picks ORDER BY week, player_name
        """).fetchdf()
    print("\nFinal picks table:")
    print(result.to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", "-n", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
