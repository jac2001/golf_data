#!/usr/bin/env python3
"""
Masters Qualifier Scorer
========================
Scores each player in the current Masters field against the 10 historical
elimination criteria from the PGA Tour "From 91 to One" framework.

Sources:
- DuckDB leaderboards table: Augusta history, major results, career wins
- DuckDB tournament_stats: SG T2G over last 4 starts
- outputs/latest_predictions.csv: driving distance field rank

Output: data/qualitative/masters_qualifiers_{tid}.csv
  One row per player. Columns: player_name, each criterion (0/1),
  qualifier_score (sum), qualifiers_passed (list), qualifiers_failed (list)

Usage:
    python masters_qualifiers.py --tournament-id R2026014
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA = PROJECT_ROOT / "data"
OUTPUTS = PROJECT_ROOT / "outputs"

MASTERS_TID_SUFFIX = "014"
MAJOR_SUFFIXES = ("014", "026", "047")  # Masters, US Open, PGA Champ (no Open in DB)


def _norm(name: str) -> str:
    """Normalize to lowercase 'first last' for matching regardless of source format."""
    s = str(name).strip().lower()
    if ", " in s:
        parts = s.split(", ", 1)
        return f"{parts[1]} {parts[0]}"
    return s


def get_db():
    import duckdb
    return duckdb.connect(str(DATA / "golf_data.db"), read_only=True)


# ---------------------------------------------------------------------------
# 1. Augusta / Major history from leaderboards
# ---------------------------------------------------------------------------

def load_augusta_history(con) -> pd.DataFrame:
    """Per-player Augusta stats: starts, top30s, avg to_par, cuts made per year."""
    return pd.read_sql("""
        SELECT
            player_name,
            COUNT(*)                                          AS augusta_starts,
            SUM(CASE WHEN CAST(REPLACE(to_par, '+','') AS DOUBLE) < 0 THEN 1 ELSE 0 END)
                                                             AS augusta_under_par_finishes,
            AVG(TRY_CAST(REPLACE(to_par, '+','') AS DOUBLE)) AS augusta_avg_to_par,
            SUM(CASE WHEN rounds_played >= 4 THEN 1 ELSE 0 END)
                                                             AS augusta_cuts_made,
            SUM(CASE WHEN TRY_CAST(TRIM(position) AS INTEGER) <= 30
                      AND rounds_played >= 4 THEN 1 ELSE 0 END)
                                                             AS augusta_top30s
        FROM leaderboards
        WHERE tournament_id LIKE '%014'
        GROUP BY player_name
    """, con)


def load_masters_2025_cut(con) -> pd.DataFrame:
    """Did the player make the 2025 Masters cut?"""
    return pd.read_sql("""
        SELECT player_name,
               MAX(CASE WHEN rounds_played >= 4 THEN 1 ELSE 0 END) AS made_cut_2025
        FROM leaderboards
        WHERE tournament_id = 'R2025014'
        GROUP BY player_name
    """, con)


def load_major_top6_last2years(con) -> pd.DataFrame:
    """Did the player record a top-6 at any major in 2024 or 2025?"""
    suffix_list = "','".join(MAJOR_SUFFIXES)
    return pd.read_sql(f"""
        SELECT player_name,
               MAX(CASE
                   WHEN TRY_CAST(TRIM(position) AS INTEGER) <= 6
                        AND rounds_played >= 4
                        AND year >= 2024 THEN 1 ELSE 0
               END) AS top6_major_last2y
        FROM leaderboards
        WHERE RIGHT(tournament_id, 3) IN ('{suffix_list}')
        GROUP BY player_name
    """, con)


def load_career_wins(con) -> pd.DataFrame:
    """Career wins from leaderboards (position = '1', all events in DB 2012-2025)."""
    return pd.read_sql("""
        SELECT player_name,
               COUNT(*) AS career_wins_db
        FROM leaderboards
        WHERE TRIM(position) = '1'
        GROUP BY player_name
    """, con)


def load_defending_champion(con) -> pd.DataFrame:
    """Who won the 2025 Masters?"""
    return pd.read_sql("""
        SELECT player_name, 1 AS is_defending_champion
        FROM leaderboards
        WHERE tournament_id = 'R2025014'
        AND TRIM(position) = '1'
        LIMIT 1
    """, con)


# ---------------------------------------------------------------------------
# 2. SG Tee-to-Green last 4 starts from tournament_stats
# ---------------------------------------------------------------------------

def load_sg_t2g_last4(con, field_names: list[str]) -> pd.DataFrame:
    """
    Sum SG:OTT + SG:Approach event totals for each player's last 4 events.

    In tournament_stats the event total rows are:
      OTT:      stat_name LIKE '%Off-the-Tee%', stat_component = 'Total SG:APP'
      Approach: stat_name LIKE '%Approach%',    stat_component = 'Total SG:ARG'
    """
    rows = []
    for pname in field_names:
        db_name = _norm(pname)  # convert "Last, First" → "first last" for DB lookup
        # Try exact DB name match (DB stores "First Last")
        res = con.execute("""
            SELECT tournament_id, stat_name, stat_component, stat_value
            FROM tournament_stats
            WHERE LOWER(player_name) = ?
              AND year >= 2025
              AND (
                  (stat_name LIKE '%Off-the-Tee%'  AND stat_component = 'Total SG:APP')
               OR (stat_name LIKE '%Approach%'      AND stat_component = 'Total SG:ARG')
              )
            ORDER BY tournament_id DESC
        """, [db_name]).fetchall()

        if not res:
            rows.append({"player_name": pname, "sg_t2g_last4_total": None, "sg_t2g_events": 0})
            continue

        df_sg = pd.DataFrame(res, columns=["tournament_id", "stat_name", "stat_component", "stat_value"])
        # Get last 4 unique tournament_ids
        last4_tids = df_sg["tournament_id"].unique()[:4]
        df_last4 = df_sg[df_sg["tournament_id"].isin(last4_tids)]
        total_t2g = df_last4["stat_value"].sum()
        rows.append({
            "player_name": pname,
            "sg_t2g_last4_total": round(float(total_t2g), 3),
            "sg_t2g_events": int(len(last4_tids)),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Predictions CSV: driving distance rank + betting favorite
# ---------------------------------------------------------------------------

def load_predictions_context() -> pd.DataFrame:
    preds_path = OUTPUTS / "latest_predictions.csv"
    if not preds_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(preds_path)
    keep = ["player_name", "driving_dist_field_rank", "win_prob", "odds_american"]
    keep = [c for c in keep if c in df.columns]
    return df[keep].copy()


# ---------------------------------------------------------------------------
# 4. Score each criterion
# ---------------------------------------------------------------------------

def score_qualifiers(
    field_df: pd.DataFrame,
    augusta: pd.DataFrame,
    cut2025: pd.DataFrame,
    top6major: pd.DataFrame,
    career_wins: pd.DataFrame,
    defending: pd.DataFrame,
    sg_t2g: pd.DataFrame,
    preds: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge all sources and score 0/1 per criterion.
    Returns one row per player with qualifier_score and details.
    """
    df = field_df[["player_name"]].copy()
    df["_key"] = df["player_name"].apply(_norm)

    def merge(right, how="left"):
        """Merge on normalized name key, then drop the key column from right."""
        right = right.copy()
        right["_key"] = right["player_name"].apply(_norm)
        right = right.drop(columns=["player_name"])
        merged = df.merge(right, on="_key", how=how)
        return merged

    df = merge(augusta)
    df = merge(cut2025)
    df = merge(top6major)
    df = merge(career_wins)
    df = merge(sg_t2g)
    df = merge(preds)

    # Fill missing
    for col in ["augusta_starts", "augusta_top30s", "augusta_cuts_made",
                "made_cut_2025", "top6_major_last2y", "career_wins_db"]:
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0).astype(int)

    df["sg_t2g_last4_total"] = pd.to_numeric(df.get("sg_t2g_last4_total"), errors="coerce")
    df["driving_dist_field_rank"] = pd.to_numeric(df.get("driving_dist_field_rank"), errors="coerce")
    df["augusta_avg_to_par"] = pd.to_numeric(df.get("augusta_avg_to_par"), errors="coerce")
    df["win_prob"] = pd.to_numeric(df.get("win_prob"), errors="coerce")

    # Defending champion set
    defending_names = set(defending["player_name"].apply(_norm).tolist()) if not defending.empty else set()

    # --- Criterion 1: Prior Masters start
    df["crit_prior_masters_start"] = (df["augusta_starts"] >= 1).astype(int)

    # --- Criterion 2: Prior top-30 at Masters (article: 26 of last 28 winners)
    df["crit_prior_top30_masters"] = (df["augusta_top30s"] >= 1).astype(int)

    # --- Criterion 3: Made Masters cut in 2025
    df["crit_made_cut_2025"] = df["made_cut_2025"].fillna(0).astype(int)

    # --- Criterion 4: Top-6 major finish in last 2 years (2024-25)
    df["crit_top6_major_last2y"] = df["top6_major_last2y"].fillna(0).astype(int)

    # --- Criterion 5: Under-par scoring average at Augusta
    df["crit_augusta_under_par_avg"] = (
        df["augusta_avg_to_par"].notna() & (df["augusta_avg_to_par"] < 0)
    ).astype(int)

    # --- Criterion 6: SG T2G >= 18 shots over last 4 starts
    #   Only score if we have at least 3 events of data
    df["crit_sg_t2g_18plus"] = (
        df["sg_t2g_events"].fillna(0).ge(3) &
        df["sg_t2g_last4_total"].notna() &
        df["sg_t2g_last4_total"].ge(18.0)
    ).astype(int)

    # --- Criterion 7: Driving distance top 50 in field
    df["crit_driving_top50"] = (
        df["driving_dist_field_rank"].notna() &
        df["driving_dist_field_rank"].le(50)
    ).astype(int)

    # --- Criterion 8: 3+ career wins in DB
    #   Note: our DB covers 2012-2025, so some older players may be undercounted
    df["crit_career_wins_3plus"] = (df["career_wins_db"] >= 3).astype(int)

    # --- Criterion 9: Not defending champion (informational — negative in funnel)
    df["is_defending_champion"] = df["_key"].isin(defending_names).astype(int)

    # --- Criterion 10: Not betting favorite (informational — negative in funnel)
    if "win_prob" in df.columns and df["win_prob"].notna().any():
        max_prob = df["win_prob"].max()
        df["is_betting_favorite"] = (df["win_prob"] == max_prob).astype(int)
    else:
        df["is_betting_favorite"] = 0

    # --- Qualifier score (criteria 1-8 only; 9+10 are informational)
    crit_cols = [c for c in df.columns if c.startswith("crit_")]
    df["qualifier_score"] = df[crit_cols].sum(axis=1)
    df["qualifier_max"] = len(crit_cols)

    # Human-readable pass/fail lists
    crit_labels = {
        "crit_prior_masters_start":   "Prior Masters start",
        "crit_prior_top30_masters":   "Top-30 at Masters",
        "crit_made_cut_2025":         "Made cut 2025",
        "crit_top6_major_last2y":     "Top-6 major 2024-25",
        "crit_augusta_under_par_avg": "Under-par Augusta avg",
        "crit_sg_t2g_18plus":         "SG T2G 18+ last 4 starts",
        "crit_driving_top50":         "Driving dist top 50",
        "crit_career_wins_3plus":     "3+ career wins",
    }

    def _label_lists(row):
        passed, failed = [], []
        for col, label in crit_labels.items():
            (passed if row[col] == 1 else failed).append(label)
        return pd.Series({
            "qualifiers_passed": " | ".join(passed),
            "qualifiers_failed": " | ".join(failed),
        })

    labels = df.apply(_label_lists, axis=1)
    df = pd.concat([df, labels], axis=1)

    return df.sort_values("qualifier_score", ascending=False)


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tournament-id", default="R2026014")
    args = parser.parse_args()
    tid = args.tournament_id.upper().strip()

    print(f"Computing Masters qualifiers for {tid} ...")

    con = get_db()

    # Load current field
    field_path = DATA / "field" / f"field_{tid}.csv"
    if not field_path.exists():
        # Fallback: use predictions
        preds = load_predictions_context()
        if preds.empty:
            print("No field or predictions file found.")
            return 1
        field_df = preds[["player_name"]].drop_duplicates()
    else:
        field_df = pd.read_csv(field_path)[["player_name"]].drop_duplicates()

    print(f"  Field: {len(field_df)} players")

    # Load all sources
    augusta      = load_augusta_history(con)
    cut2025      = load_masters_2025_cut(con)
    top6major    = load_major_top6_last2years(con)
    career_wins  = load_career_wins(con)
    defending    = load_defending_champion(con)
    preds        = load_predictions_context()
    sg_t2g       = load_sg_t2g_last4(con, field_df["player_name"].tolist())
    con.close()

    # Score
    results = score_qualifiers(
        field_df, augusta, cut2025, top6major,
        career_wins, defending, sg_t2g, preds
    )

    # Save
    out_dir = DATA / "qualitative"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"masters_qualifiers_{tid}.csv"
    results.to_csv(out_path, index=False)
    print(f"Saved -> {out_path}")

    # Print top 15
    print(f"\n{'Player':<35} {'Score':>5}  Passed")
    print("-" * 80)
    for _, r in results.head(15).iterrows():
        score = int(r["qualifier_score"])
        name = str(r["player_name"])
        passed = str(r["qualifiers_passed"])
        print(f"{name:<35} {score:>2}/{int(r['qualifier_max'])}  {passed}")

    print(f"\nFailed all criteria:")
    zero = results[results["qualifier_score"] == 0]["player_name"].tolist()
    print(", ".join(zero[:10]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
