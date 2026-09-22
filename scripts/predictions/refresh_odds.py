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

# DataGolf is the only odds source — the DK/PGA-GraphQL fetchers
# (fetch_pga_odds) are no longer imported or called anywhere.


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

    print(f"  Refreshing odds for {tournament_id} from DataGolf ...")

    # Freshen the DG files (fetch_dg_odds also derives the per-player
    # win-consensus file data/odds/odds_{tid}.csv). A fetch failure is
    # fine — we fall through to whatever cached files exist.
    import subprocess as _sp
    try:
        _sp.run(["python3", str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_dg_odds.py"),
                 "--tournament-id", tournament_id, "--market", "all"],
                capture_output=True, timeout=180, cwd=PROJECT_ROOT)
    except Exception as _e:
        print(f"  DG odds fetch skipped ({_e}) — using cached files")

    # ── Match odds → predictions BY NAME: DG rows carry dg_id, not the
    #    PGA player_id predictions use, so the id merge is impossible.
    win_path = PROJECT_ROOT / "data" / "odds" / f"odds_{tournament_id}.csv"
    merged = preds.copy()
    if "odds_to_win" not in merged.columns:
        merged["odds_to_win"] = np.nan
    if "odds_numeric" not in merged.columns:
        merged["odds_numeric"] = np.nan

    if win_path.exists():
        try:
            dgw = pd.read_csv(win_path)

            def _key(n: str) -> str:
                n = str(n)
                if "," in n:
                    last, _, first = n.partition(",")
                    n = f"{first.strip()} {last.strip()}"
                n = _normalize_name(n)
                return _NICKNAME_MAP.get(n, n)

            dgw["_nk"] = dgw["player_name"].apply(_key)
            dgw["_numeric"] = pd.to_numeric(
                dgw["odds_american"].astype(str).str.replace("+", "", regex=False),
                errors="coerce")
            odds_map = dict(zip(dgw["_nk"], dgw["odds_american"].astype(str)))
            num_map  = dict(zip(dgw["_nk"], dgw["_numeric"]))

            nk = merged["player_name"].apply(_key)
            merged["odds_to_win"]  = nk.map(odds_map).combine_first(merged["odds_to_win"])
            merged["odds_numeric"] = nk.map(num_map).combine_first(merged["odds_numeric"])
            print(f"  DG win odds merged: {int(nk.map(num_map).notna().sum())}/{len(merged)} players")
        except Exception as _e:
            print(f"  DG win odds merge skipped: {_e}")
    else:
        print(f"  No {win_path.name} — odds columns keep their previous values")
    
    
    
    # ------------- Recompute derived odds columns ----------------
    
    # ── No-vig consensus probability via DataGolf outrights (10+ books) ────────
    # dg_outrights_{tid}.csv has win market rows per player per book.
    # We normalize each book independently then take the median across books.
    dg_outrights_path = PROJECT_ROOT / "data" / "datagolf" / f"dg_outrights_{tournament_id}.csv"
    book_probs = []
    book_names = []

    if dg_outrights_path.exists():
        try:
            dg = pd.read_csv(dg_outrights_path)
            dg_win = dg[dg["market"].astype(str).str.lower() == "win"].copy()
            if not dg_win.empty and "player_name" in dg_win.columns and "odds_american" in dg_win.columns:
                # Build name_key → player_id map from merged (predictions)
                merged["_nk"] = merged["player_name"].apply(
                    lambda n: " ".join(sorted(str(n).lower().split(","))) if "," in str(n)
                    else str(n).strip().lower()
                )
                dg_win["_nk"] = dg_win["player_name"].apply(
                    lambda n: f"{n.split(',')[1].strip()} {n.split(',')[0].strip()}".lower()
                    if "," in str(n) else str(n).strip().lower()
                )
                dg_win["raw_prob"] = dg_win["odds_american"].apply(
                    lambda x: (1 / (1 + float(x)/100) if float(x) > 0 else float(-x) / (float(-x) + 100))
                    if str(x).lstrip("+-").replace(".","").isdigit() else np.nan
                )
                dg_win = dg_win[dg_win["raw_prob"].notna() & (dg_win["raw_prob"] > 0)]

                for book, grp in dg_win.groupby("book"):
                    total = grp["raw_prob"].sum()
                    if total <= 0:
                        continue
                    grp = grp.copy()
                    grp["nv_prob"] = grp["raw_prob"] / total
                    # Align to merged by name key
                    nk_map = dict(zip(grp["_nk"], grp["nv_prob"]))
                    aligned = merged["_nk"].map(nk_map)
                    book_probs.append(aligned.values)
                    book_names.append(str(book))

                print(f"  Consensus: DG outrights — {len(book_names)} books: {', '.join(book_names)}")
        except Exception as _dge:
            print(f"  DG outrights consensus skipped: {_dge}")

    if not book_probs:
        # Fallback: DK no-vig from merged odds_numeric
        raw_dk_prob = merged["odds_numeric"].apply(_odds_to_prob)
        dk_total    = raw_dk_prob.sum()
        merged["vegas_prob"] = raw_dk_prob / dk_total if dk_total > 0 else raw_dk_prob
        print("  Using DK no-vig odds (DG outrights not available)")
    else:
        consensus = np.nanmedian(np.column_stack(book_probs), axis=1)
        merged["vegas_prob"] = consensus

    # Clean up temp key column
    merged = merged.drop(columns=["_nk"], errors="ignore")

    if "win_prob" in merged.columns:
        merged["model_vs_vegas_edge"] = merged["win_prob"] - merged["vegas_prob"]
        merged["is_value_bet"]        = merged["model_vs_vegas_edge"] > 0
        merged["odds_drift_level"]    = merged["model_vs_vegas_edge"].apply(_drift_label)

    # ── DK movement direction (optional — from dk_odds_{tid}.csv if present) ──
    dk_path = PROJECT_ROOT / "data" / "odds" / f"dk_odds_{tournament_id}.csv"
    if dk_path.exists():
        try:
            dk_dir = pd.read_csv(dk_path)[["player_id", "dk_odds_direction"]].copy()
            dk_dir["player_id"] = dk_dir["player_id"].astype(str)
            merged = merged.merge(dk_dir, on="player_id", how="left", suffixes=("", "_new"))
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