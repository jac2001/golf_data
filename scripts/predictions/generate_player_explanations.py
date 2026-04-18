#!/usr/bin/env python3
"""
Generate Plain-English Player Card Explanations
================================================
For every player in this week's field, produces a one-liner like:

  "Elite approach play · trending up · good value vs. market"
  "Strong ball striking · 4 top-10s here in 6 starts · priced in"
  "Cold lately · weak putter · tough course fit"

How it works:
  1. Load SHAP values (win model) — these tell us WHY each player ranks where they do
  2. Map feature names → readable labels
  3. Pick the 2-3 strongest signals (positive AND negative) per player
  4. Layer in course history and form context from predictions
  5. Save to outputs/player_explanations.csv

Output columns: player_name, explanation, explanation_short
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
PREDS_FILE   = OUTPUTS_DIR / "latest_predictions.csv"
SHAP_FILE    = OUTPUTS_DIR / "shap_values_win.csv"
OUT_FILE     = OUTPUTS_DIR / "player_explanations.csv"

# ── Feature → human label mapping ──────────────────────────────────────────
# Positive SHAP = this feature is pushing the player's win prob UP
# We describe positive contributions positively, negative contributions negatively

FEATURE_LABELS = {
    # SG categories — positive = elite in that area
    "season_sg_app":              ("elite approach",       "weak approach"),
    "season_sg_ott":              ("elite driving",        "struggles off tee"),
    "season_sg_putt":             ("elite putter",         "weak putter"),
    "season_sg_arg":              ("elite short game",     "weak around greens"),
    "season_sg_t2g":              ("elite ball striking",  "weak ball striking"),
    "season_sg_total":            ("elite overall SG",     "below-avg SG"),
    "predictive_sg_weighted":     ("strong SG profile",    "weak SG profile"),
    # Form
    "form_trend":                 ("trending up",          "trending down"),
    "recent_sg_weighted":         ("hot recent form",      "cold recent form"),
    "recent_sg_trend":            ("improving form",       "fading form"),
    # Course
    "has_course_sg_history":      ("course experience",    "first time here"),
    "course_sg_total_weighted":   ("strong course SG",     "poor course SG"),
    "has_made_cut_here":          ("cuts made here",       "cut struggles here"),
    "hist_cut_rate":              ("cuts made here",       "cut risk"),   # same concept as has_made_cut_here
    "course_perf_score":          ("strong course record", "poor course record"),
    # Fit
    "dg_fit_total":               ("good course fit",      "poor course fit"),
    "course_fit":                 ("good course fit",      "poor course fit"),
    "season_sg_app_field_pct":    ("approach advantage",   "approach disadvantage"),
    "season_sg_ott_vs_field":     ("driving advantage",    "driving disadvantage"),
    "season_sg_putt_vs_field":    ("putting advantage",    "putting disadvantage"),
    # World rank — skip; handled separately via pred_row["world_rank"] in fallback
    "world_rank_log":             (None, None),
    # Field strength
    "field_avg_season_sg_app":    (None, None),   # field-level feature, skip
    "field_avg_season_sg_ott":    (None, None),
    "field_avg_season_sg_putt":   (None, None),
    "field_avg_season_sg_total":  (None, None),
}

# Minimum absolute SHAP value to include a feature in the explanation
SHAP_THRESHOLD = 0.004

# Default percentile gates
FIELD_PCT_THRESHOLD = 0.78      # must be >= 78th pct to show a positive label
FIELD_PCT_NEG_THRESHOLD = 0.28  # must be <= 28th pct to show a negative label

# Per-feature overrides — "elite" ball-striking labels need a higher bar because
# the top players ALL have good ball striking at ball-striking courses, making
# those labels uninformative if the threshold is too low.
FEATURE_PCT_OVERRIDES: dict[str, tuple[float, float]] = {
    # Ball striking / tee-to-green: require top 10% of field
    "season_sg_t2g":           (0.90, 0.22),
    "season_sg_app":           (0.88, 0.22),
    "season_sg_ott":           (0.85, 0.22),
    "season_sg_app_field_pct": (0.85, 0.22),
    "season_sg_ott_vs_field":  (0.85, 0.22),
    # Putting: moderate bar — it's the differentiator on most courses
    "season_sg_putt":          (0.80, 0.25),
    "season_sg_putt_vs_field": (0.80, 0.25),
    # Short game: raise bar — same problem as ball striking on scrambling courses
    "season_sg_arg":           (0.88, 0.22),
    # Overall SG summary — only show when truly dominant
    "season_sg_total":         (0.88, 0.20),
    "predictive_sg_weighted":  (0.88, 0.20),
}


def _shap_label(feature: str, shap_val: float, player_field_pcts: dict | None = None) -> str | None:
    """Convert a feature + SHAP value into a plain-English phrase, or None to skip."""
    mapping = FEATURE_LABELS.get(feature)
    if mapping is None:
        return None
    pos_label, neg_label = mapping
    if pos_label is None:
        return None

    # Field percentile gate — prevents generic labels on average players
    if player_field_pcts is not None and feature in player_field_pcts:
        pct = player_field_pcts[feature]
        pos_thr, neg_thr = FEATURE_PCT_OVERRIDES.get(feature, (FIELD_PCT_THRESHOLD, FIELD_PCT_NEG_THRESHOLD))
        if shap_val > 0 and pct < pos_thr:
            return None   # not elite enough in this field for this feature
        if shap_val < 0 and pct > neg_thr:
            return None   # not weak enough to call out

    if shap_val > 0:
        return pos_label
    else:
        return neg_label


def _course_context(row: pd.Series) -> str | None:
    """Generate a short course-history phrase from predictions columns."""
    starts = int(row.get("course_starts", 0) or 0)
    if starts == 0:
        return None
    t10_rate = float(row.get("course_top_10_rate", 0) or 0)
    best     = row.get("course_best_finish")
    if starts >= 3 and t10_rate >= 0.35:
        return f"{int(t10_rate * starts)}/{starts} top-10s here"
    if starts >= 2 and pd.notna(best) and int(best) <= 5:
        return f"top-5 finish here before"
    if starts >= 4:
        return f"{starts} starts here"
    return None


def _value_phrase(row: pd.Series) -> str | None:
    """Return a value/odds phrase if there's a meaningful edge."""
    win_prob  = float(row.get("win_prob", 0) or 0)
    # Look for DK outright odds to estimate book probability
    dk_odds   = row.get("dk_win_odds_american") or row.get("win_odds_american")
    if pd.isna(dk_odds) or not dk_odds:
        return None
    try:
        odds = float(dk_odds)
        if odds > 0:
            book_prob = 100 / (odds + 100)
        else:
            book_prob = abs(odds) / (abs(odds) + 100)
        edge = (win_prob - book_prob) * 100  # percentage points
        if edge >= 1.5:
            return "value vs. market"
        if edge <= -1.5:
            return "priced in"
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return None


def generate_explanation(player_name: str, shap_row: pd.Series,
                          pred_row: pd.Series, features: list[str],
                          field_medians: dict, field_pcts: dict | None = None) -> str:
    """Build a one-liner explanation for one player.

    field_pcts: {feature_name: player's percentile rank in the field (0-1)}
    """
    # Skip course-generic features — use field_medians to filter out non-differentiating signals
    SKIP_IF_common = {"cuts made here", "course experience"}

    # Semantic groups: once a label from a group is chosen, skip others in the same group.
    # Maps label → group name (both positive and negative versions)
    LABEL_GROUPS = {
        # Ball striking subsumes approach and driving sub-labels
        "elite ball striking":    "striking",
        "weak ball striking":     "striking",
        "elite approach":         "striking",
        "weak approach":          "striking",
        "approach advantage":     "striking",
        "approach disadvantage":  "striking",
        "elite driving":          "striking",
        "struggles off tee":      "striking",
        "driving advantage":      "striking",
        "driving disadvantage":   "striking",
        # Putting
        "elite putter":           "putting",
        "weak putter":            "putting",
        "putting advantage":      "putting",
        "putting disadvantage":   "putting",
        # Form
        "trending up":            "form",
        "trending down":          "form",
        "hot recent form":        "form",
        "cold recent form":       "form",
        "improving form":         "form",
        "fading form":            "form",
        # Course fit
        "good course fit":        "fit",
        "poor course fit":        "fit",
        "strong course record":   "course_rec",
        "poor course record":     "course_rec",
        "strong course sg":       "course_sg",
        "poor course sg":         "course_sg",
    }

    # Collect all features with meaningful SHAP contributions
    contributions = []
    for feat in features:
        if feat not in shap_row.index:
            continue
        val = float(shap_row[feat])
        if abs(val) < SHAP_THRESHOLD:
            continue
        label = _shap_label(feat, val, player_field_pcts=field_pcts)
        if label:
            contributions.append((abs(val), val, label))

    # Sort by magnitude, deduplicate labels AND semantic groups
    contributions.sort(key=lambda x: -x[0])
    seen_labels, seen_groups, phrases = set(), set(), []
    for _, shap_val, label in contributions:
        if label.lower() in SKIP_IF_common:
            continue   # handled by course_ctx below with specificity
        group = LABEL_GROUPS.get(label.lower())
        if label in seen_labels:
            continue
        if group and group in seen_groups:
            continue
        seen_labels.add(label)
        if group:
            seen_groups.add(group)
        phrases.append((shap_val, label))
        if len(phrases) >= 4:
            break

    pos_phrases = [lbl for val, lbl in phrases if val > 0]
    neg_phrases = [lbl for val, lbl in phrases if val < 0]

    parts = []
    parts.extend(pos_phrases[:2])

    # Course context — only show when genuinely above average
    starts = int(pred_row.get("course_starts", 0) or 0)
    avg_starts = field_medians.get("course_starts", 2)
    course_ctx = _course_context(pred_row)
    if course_ctx and starts >= max(3, avg_starts):
        if course_ctx not in parts:
            parts.append(course_ctx)

    # Value phrase
    val_phrase = _value_phrase(pred_row)
    if val_phrase:
        parts.append(val_phrase)

    # Leading negative if no strong positives
    if not pos_phrases and neg_phrases:
        parts = neg_phrases[:2]
    elif neg_phrases and len(parts) < 2:
        parts.append(neg_phrases[0])

    # Fallback to world rank or form
    if not parts:
        rank = pred_row.get("world_rank")
        form = float(pred_row.get("form_trend", 0) or 0)
        if pd.notna(rank) and int(rank) <= 15:
            parts = [f"top-{int(rank)} in the world"]
        elif form > 0.4:
            parts = ["trending up lately"]
        elif form < -0.4:
            parts = ["cold recent form"]
        else:
            parts = ["balanced profile"]

    return " · ".join(p.capitalize() for p in parts[:3])


def main():
    if not SHAP_FILE.exists():
        print(f"SHAP file not found: {SHAP_FILE}")
        print("Run: python3 scripts/validation/compute_shap.py first")
        return

    if not PREDS_FILE.exists():
        print(f"Predictions not found: {PREDS_FILE}")
        return

    shap_df = pd.read_csv(SHAP_FILE)
    preds   = pd.read_csv(PREDS_FILE)
    print(f"Generating explanations for {len(preds)} players...")

    # Feature columns (everything except player_name, tournament_id)
    meta_cols = {"player_name", "tournament_id"}
    features  = [c for c in shap_df.columns if c not in meta_cols]

    # Merge SHAP + predictions on player_name
    merged = preds.merge(shap_df, on="player_name", how="left", suffixes=("", "_shap"))

    # Compute field medians for filtering non-differentiating signals
    field_medians = {
        col: float(preds[col].median())
        for col in ["course_starts", "course_top_10_rate", "form_trend"]
        if col in preds.columns
    }

    # Compute field percentile rank for every SHAP feature that exists in preds
    # field_percentiles[player_name][feature] = 0-1 percentile within this week's field
    pct_feats = [f for f in features if f in preds.columns]
    pct_df = preds[["player_name"] + pct_feats].copy()
    for feat in pct_feats:
        pct_df[feat] = pct_df[feat].rank(pct=True, na_option="keep")
    field_percentiles: dict[str, dict] = {
        row["player_name"]: {f: row[f] for f in pct_feats}
        for _, row in pct_df.iterrows()
    }

    rows = []
    for _, row in merged.iterrows():
        pname = row["player_name"]
        shap_row = row[features] if all(f in row.index for f in features) else pd.Series(dtype=float)
        player_pcts = field_percentiles.get(pname)
        explanation = generate_explanation(pname, shap_row, row, features, field_medians, field_pcts=player_pcts)
        rows.append({"player_name": pname, "explanation": explanation})

    out = pd.DataFrame(rows)
    out.to_csv(OUT_FILE, index=False)
    print(f"Saved → {OUT_FILE.name}")

    # Print sample
    preds_ranked = preds.sort_values("win_prob", ascending=False).head(10)
    sample = out[out["player_name"].isin(preds_ranked["player_name"])]
    sample = preds_ranked[["player_name","win_prob"]].merge(sample, on="player_name")
    for _, r in sample.iterrows():
        print(f"  {r['player_name']:<30} {r['win_prob']*100:.1f}%  →  {r['explanation']}")


if __name__ == "__main__":
    main()
