"""
prediction_integrity.py — refuse to publish predictions built on the wrong data.
================================================================================
Three times this season one event's DataGolf data was used under another
event's name (Biltmore ran with DG decompositions for 1% of the field;
Baycurrent read Bank of Utah's file and its whole top 10 had none — the
simulation then rated Clark, DG's #3, 23rd). Each fix closed one path.

This gate checks the OUTPUT instead, so it catches the next path too.
run_pipeline's post-run sanity checks call it; any failure makes the run
red, nothing is committed, and the site keeps the last good predictions.

Thresholds were set on real files (2026-10-07):
                         broken Baycurrent   good Baycurrent   good weeks
  final_pred coverage           51%               100%           99-100%
  top-10 with final_pred         0%               100%             100%
  sim vs model (Spearman)       0.20              0.84               —
"""

from __future__ import annotations

import pandas as pd

MIN_COVERAGE = 0.90      # share of the field with this event's DG prediction
TOP_N = 10               # the model's top N must ALL have it
MIN_SIM_AGREEMENT = 0.50 # Spearman rank correlation, simulation vs model


def check(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return (failures, notes) for one event's predictions table."""
    failures: list[str] = []
    notes: list[str] = []
    if df.empty or "win_prob" not in df.columns:
        return ["predictions table is empty or has no win_prob"], notes
    n = len(df)
    top = df.sort_values("win_prob", ascending=False).head(TOP_N)

    for col, label in (("final_pred", "DG decompositions (final_pred)"),
                       ("dg_win", "DG pre-tournament (dg_win)")):
        if col not in df.columns:
            failures.append(f"{label} missing entirely — the merge was skipped (wrong event or no file)")
            continue
        cov = df[col].notna().mean()
        if cov < MIN_COVERAGE:
            failures.append(f"{label} covers only {cov:.0%} of the field (need ≥{MIN_COVERAGE:.0%}) — "
                            "likely another event's file")
        else:
            notes.append(f"✓ {label}: {cov:.0%} of {n} players")
        missing = top[top[col].isna()]["player_name"].tolist()
        if missing:
            failures.append(f"{label} missing for the model's top {TOP_N}: {', '.join(missing[:5])}"
                            + (" …" if len(missing) > 5 else ""))

    if "win_prob_sim" in df.columns and df["win_prob_sim"].notna().sum() >= 10:
        rho = df["win_prob"].rank().corr(df["win_prob_sim"].rank())   # Spearman = Pearson on ranks
        if rho < MIN_SIM_AGREEMENT:
            failures.append(f"simulation disagrees with the model (rank correlation {rho:.2f}, "
                            f"need ≥{MIN_SIM_AGREEMENT:.2f}) — its inputs are probably mismatched")
        else:
            notes.append(f"✓ simulation agrees with model (rank correlation {rho:.2f})")
    return failures, notes
