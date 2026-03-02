"""                                                                                
  Refresh Odds — Lightweight odds-only update
  ============================================
  Updates odds columns in latest_predictions.csv without re-running
  the full ML pipeline. Takes ~30 seconds vs several minutes for a full run.

  What changes:   odds_to_win, vegas_prob, model_vs_vegas_edge,
                  is_value_bet, odds_drift_level
  What stays:     win_prob, top5_prob, top10_prob, expected_value
                  (those require a full model rerun)

  Usage:
      python3 scripts/predictions/refresh_odds.py
      python3 scripts/predictions/refresh_odds.py --tournament-id R2026007
"""

import sys
import argparse
import unicodedata
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent.parent

# Add scrapers dir to path — same pattern used across all scripts in this project.
# This lets us import fetch_pga_odds by filename rather than as a package path,
# which avoids the "No module named 'scripts'" error when scripts/ has no __init__.py
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "scrapers"))
from fetch_pga_odds import fetch_and_merge_odds, fetch_all_market_odds


def get_current_tournament_id() -> str | None:
    """Read this week's tournament ID from the schedule CSV."""
    sched_path = PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv"
    if not sched_path.exists():
        return None

    sched = pd.read_csv(sched_path)
    today = datetime.now().strftime("%Y-%m-%d")

    # Active = tournament has started but not finished
    active = sched[(sched["start_date"] <= today) & (sched["end_date"] >= today)]
    if not active.empty:
        return str(active.iloc[0]["tournament_id"])

    # Not in a tournament week — grab the next upcoming one
    upcoming = sched[sched["start_date"] > today].sort_values("start_date")
    if not upcoming.empty:
        return str(upcoming.iloc[0]["tournament_id"])

    return None


def _norm(name: str) -> str:
    """Normalize 'Last, First' or 'First Last' → 'first last' for matching."""
    parts = str(name).split(",")
    if len(parts) == 2:
        return f"{parts[1].strip()} {parts[0].strip()}".lower()
    return str(name).strip().lower()


def _odds_to_prob(odds_numeric) -> float:
    """Convert American odds integer to implied probability (0–1)."""
    try:
        o = float(odds_numeric)
        return 100 / (o + 100) if o >= 0 else abs(o) / (abs(o) + 100)
    except Exception:
        return 0.0


def _drift_label(edge: float) -> str:
    """Classify model-vs-market edge into a readable label."""
    if edge > 0.05:   return "MODEL>>VEGAS"
    if edge > 0.02:   return "SIGNIFICANT"
    if edge > 0.01:   return "MODERATE"
    if edge < -0.05:  return "VEGAS>>MODEL"
    return "OK"




def _normalize_name(s: str) -> str:
    """Lowercase, strip accents, normalize spacing."""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# Common nickname/short-name → full name overrides
_NICKNAME_MAP = {
    "dan brown":       "daniel brown",
    "cam davis":       "cameron davis",
    "cam young":       "cameron young",
    "matt fitzpatrick":"matthew fitzpatrick",
    "si woo kim":      "si woo kim",
    "tom kim":         "tom kim",
}


def _fallback_odds_from_prop_lines(tournament_id: str, preds: pd.DataFrame) -> pd.DataFrame:
    """
    When the DK API is unavailable, load odds from the locally-cached
    prop_lines_{tid}.csv (outright market) and match players by name.
    Returns a DataFrame with columns [player_id, odds_to_win, odds_numeric],
    same shape as fetch_and_merge_odds output — or empty DataFrame on failure.
    """
    prop_path = PROJECT_ROOT / "data" / "odds" / f"prop_lines_{tournament_id}.csv"
    if not prop_path.exists():
        print(f"  Fallback: prop_lines file not found at {prop_path}")
        return pd.DataFrame()

    try:
        prop = pd.read_csv(prop_path)
        prop = prop[prop["market"] == "outright"].copy()
        if prop.empty:
            print("  Fallback: no outright rows in prop_lines file.")
            return pd.DataFrame()

        # Build name → player_id lookup from predictions
        name_to_id = {
            _normalize_name(str(row["player_name"])): str(row["player_id"])
            for _, row in preds.iterrows()
            if pd.notna(row.get("player_name"))
        }

        rows = []
        unmatched = []
        for _, row in prop.iterrows():
            norm = _normalize_name(str(row.get("player_name", "")))
            norm = _NICKNAME_MAP.get(norm, norm)
            pid = name_to_id.get(norm)
            if pid:
                rows.append({
                    "player_id":   pid,
                    "odds_to_win": str(row.get("odds", "")),
                    "odds_numeric": float(row.get("odds", 0)),
                })
            else:
                unmatched.append(row.get("player_name", "?"))

        if unmatched:
            print(f"  Fallback: {len(unmatched)} unmatched players: {unmatched[:8]}")
        print(f"  Fallback: matched {len(rows)}/{len(prop)} players from prop_lines.")
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    except Exception as e:
        print(f"  Fallback error: {e}")
        return pd.DataFrame()


def refresh_odds(tournament_id: str) -> bool:
    preds_path = PROJECT_ROOT / 'outputs' / 'latest_predictions.csv'

    if not preds_path.exists():
        print(f"Error: {preds_path} not found. Run the full pipeline first.")
        return False

    # Load predictions first — needed for fallback name matching
    preds = pd.read_csv(preds_path)

    print(f"  Fetching fresh odds for {tournament_id} ...")

    # Fetch all markets first so we can save pga_market_odds and pass to merge
    try:
        all_markets_df = fetch_all_market_odds(tournament_id)
        if not all_markets_df.empty:
            _mkt_path = PROJECT_ROOT / "data" / "odds" / f"pga_market_odds_{tournament_id}.csv"
            all_markets_df.to_csv(_mkt_path, index=False)
            print(f"  Saved all PGA markets to {_mkt_path.name}")
    except Exception as _e:
        print(f"  PGA market fetch skipped: {_e}")
        all_markets_df = None

    odds_df = fetch_and_merge_odds(tournament_id,
                                   all_markets_df=all_markets_df if all_markets_df is not None and not all_markets_df.empty else None)

    if odds_df.empty:
        print("  DK API returned empty — trying prop_lines fallback...")
        odds_df = _fallback_odds_from_prop_lines(tournament_id, preds)
        if odds_df.empty:
            print("ERROR: No odds data from API or prop_lines fallback.")
            return False

    print(f"  Got odds for {len(odds_df)} players.")

    # ── Match odds → predictions by player_id (most reliable) ──────────
    preds["player_id"]   = preds["player_id"].astype(str)
    odds_df["player_id"] = odds_df["player_id"].astype(str)

    # Keep only the columns we need from odds_df
    odds_slim = odds_df[["player_id", "odds_to_win", "odds_numeric"]].copy()
    odds_slim.columns = ["player_id", "new_odds_to_win", "new_odds_numeric"]

    merged = preds.merge(odds_slim, on="player_id", how="left")

    # Fill in new odds where available, keep old value where not
    # Guard: columns may not exist on a fresh predictions file
    if "odds_to_win" not in merged.columns:
        merged["odds_to_win"] = np.nan
    if "odds_numeric" not in merged.columns:
        merged["odds_numeric"] = np.nan
    merged["odds_to_win"]  = merged["new_odds_to_win"].combine_first(merged["odds_to_win"])
    merged["odds_numeric"] = merged["new_odds_numeric"].combine_first(merged["odds_numeric"])
    merged = merged.drop(columns=["new_odds_to_win", "new_odds_numeric"])
    
    
    
    # ------------- Recompute derived odds columns ----------------
    
    # ── No-vig consensus probability ────────────────────────────────────────
    # Raw DK odds → implied prob includes vig (~10-15% overround). We remove it
    # by normalizing per book (each player's prob ÷ sum of all probs = 100%).
    # Averaging across multiple books gives a cleaner "true market probability".
    raw_dk_prob = merged["odds_numeric"].apply(_odds_to_prob)
    dk_total    = raw_dk_prob.sum()
    dk_nv       = raw_dk_prob / dk_total if dk_total > 0 else raw_dk_prob  # no-vig DK

    # Try to load additional books for consensus
    book_probs = [dk_nv]
    book_names = ["DK"]

    for book_tag, fname_pat, odds_col in [
        ("FD",  f"fanduel_odds_{tournament_id}.csv", "odds_numeric"),
        ("PGA", f"pga_odds_{tournament_id}.csv",     "odds_numeric"),
        ("DKP", f"dk_odds_{tournament_id}.csv",      "dk_odds_numeric"),
    ]:
        book_path = PROJECT_ROOT / "data" / "odds" / fname_pat
        if not book_path.exists():
            continue
        try:
            bdf = pd.read_csv(book_path)
            bdf["player_id"] = bdf["player_id"].astype(str)
            bdf = bdf[["player_id", odds_col]].dropna()
            # Compute raw implied prob per player
            bdf["raw_prob"] = bdf[odds_col].apply(_odds_to_prob)
            total = bdf["raw_prob"].sum()
            if total > 0:
                bdf["nv_prob"] = bdf["raw_prob"] / total
            else:
                continue
            # Align to merged (left join on player_id)
            aligned = merged[["player_id"]].merge(bdf[["player_id", "nv_prob"]], on="player_id", how="left")
            book_probs.append(aligned["nv_prob"].values)
            book_names.append(book_tag)
        except Exception as _be:
            print(f"  Skipped {book_tag} odds: {_be}")

    if len(book_probs) > 1:
        import numpy as _np
        consensus = _np.nanmedian(_np.column_stack(book_probs), axis=1)
        merged["vegas_prob"] = consensus
        print(f"  Consensus odds from {len(book_probs)} books: {book_names}")
    else:
        merged["vegas_prob"] = dk_nv.values
        print("  Using DK no-vig odds (no other books available)")

    if "win_prob" in merged.columns:
        merged["model_vs_vegas_edge"] = merged["win_prob"] - merged["vegas_prob"]
        merged["is_value_bet"]        = merged["model_vs_vegas_edge"] > 0
        merged["odds_drift_level"]    = merged["model_vs_vegas_edge"].apply(_drift_label)

    # ── DK movement direction from PGA Tour compressed endpoint ─────────────
    dk_path = PROJECT_ROOT / "data" / "odds" / f"dk_odds_{tournament_id}.csv"
    if dk_path.exists():
        try:
            dk_dir = pd.read_csv(dk_path)[["player_id", "dk_odds_direction"]].copy()
            dk_dir["player_id"] = dk_dir["player_id"].astype(str)
            merged = merged.merge(dk_dir, on="player_id", how="left", suffixes=("", "_new"))
            # Keep existing column if already present, else use new one
            if "dk_odds_direction" in merged.columns:
                pass  # already merged cleanly
            print(f"  DK direction merged: {int(dk_dir['dk_odds_direction'].notna().sum())} players")
        except Exception as _e:
            print(f"  Skipped DK direction: {_e}")

    # ── Timestamp ────────────────────────────────────────────────────────────
    merged["odds_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    merged.to_csv(preds_path, index=False)

    n_value  = int(merged["is_value_bet"].sum()) if "is_value_bet" in merged.columns else "—"
    n_edge   = int((merged["model_vs_vegas_edge"].abs() > 0.03).sum()) if "model_vs_vegas_edge" in merged.columns else "—"
    print(f"  ✅ Saved. Value bets: {n_value}  |  Players with edge >3pts: {n_edge}")

    # Auto-save a drift snapshot so the dashboard can track odds movement
    try:
        _snap_script = PROJECT_ROOT / "scripts" / "predictions" / "save_odds_snapshot.py"
        import subprocess as _sp
        _sp.run(["python3", str(_snap_script)], capture_output=True, cwd=PROJECT_ROOT)
    except Exception:
        pass  # Non-fatal; dashboard will just show no movement data

    return True
    

def main():
    parser = argparse.ArgumentParser(description="Refresh odds without full model rerun")
    parser.add_argument("--tournament-id", "-t", default=None,
                        help="Tournament ID (e.g. R2026007). Auto-detects if omitted.")
    args = parser.parse_args()

    t_id = args.tournament_id or get_current_tournament_id()
    if not t_id:
        print("ERROR: Could not determine current tournament ID.")
        sys.exit(1)

    print(f"\n🔄 Refreshing odds for tournament: {t_id}")
    ok = refresh_odds(t_id)
    print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()