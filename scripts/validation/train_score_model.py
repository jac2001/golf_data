#!/usr/bin/env python3
"""Train score regression model: predicts 4-round to-par total."""
import glob, joblib, numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR     = PROJECT_ROOT / "data" / "models"

# Same feature set used by classification models (no leakage)
SCORE_FEATURES = [
    "season_sg_total", "season_sg_ott", "season_sg_app", "season_sg_arg",
    "season_sg_t2g", "season_sg_putt", "season_sg_arg_vs_field",
    "season_sg_total_vs_field", "season_sg_ott_vs_field",
    "season_sg_app_vs_field", "season_sg_putt_vs_field",
    "season_sg_ott_field_pct", "season_sg_app_field_pct", "season_sg_putt_field_pct",
    "recent_sg_weighted", "recent_sg_trend",
    "recent_sg_ott_weighted", "recent_sg_app_weighted", "recent_sg_putt_weighted",
    "hist_times_played", "hist_avg_finish", "hist_best_finish",
    "hist_wins", "hist_top5s", "hist_top10s", "hist_cut_rate", "hist_missed_cuts",
    "has_won_here", "has_course_history", "has_made_cut_here",
    "venue_avg_finish", "venue_finish_std",
    "form_trend", "finish_consistency", "recent_top10s", "recent_top5s",
    "recent_cuts_pct", "recent_birdie_avg", "recent_scoring_avg",
    "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt",
    "dg_fit_total", "predictive_sg_weighted",
    "world_rank",
]


def to_par_numeric(series):
    """Convert to_par to float: 'E'->0, '+3'->3, '-12'->-12, numeric pass-through."""
    def _parse(v):
        if pd.isna(v): return np.nan
        s = str(v).strip()
        if s in ("E", "e", "0", "0.0"): return 0.0
        try: return float(s)
        except: return np.nan
    return series.map(_parse)


def main():
    # Load most recent master training data
    files = sorted(glob.glob(str(PROCESSED_DIR / "master_training_data_*.csv")))
    if not files:
        print(f"ERROR: No master_training_data_*.csv found in {PROCESSED_DIR}")
        return
    data_file = files[-1]
    print(f"Loading: {data_file}")
    df = pd.read_csv(data_file)
    print(f"  Raw rows: {len(df)}")

    # Filter to completed 4-round tournaments only
    df = df[df["rounds_played"] == 4].copy()
    print(f"  After rounds_played==4 filter: {len(df)}")

    # Parse to_par target
    df["to_par_num"] = to_par_numeric(df["to_par"])
    df = df.dropna(subset=["to_par_num"])
    print(f"  After dropping NaN to_par: {len(df)}")

    # Train/test split (2025 holdout, same as classification models)
    field_avg = +(
        df.groupby(["tournament_id", "year"])['to_par_num']
        .transform('mean')
    )
    df['score_vs_field'] = df['to_par_num'] - field_avg
    train = df[df['year'].astype(int) < 2024].copy()
    test  = df[df['year'].astype(int) == 2025].copy()
    
    print(f"  Train rows: {len(train)} | Test rows: {len(test)}")

    # Use only features present in data
    feats = [f for f in SCORE_FEATURES if f in df.columns]
    missing = [f for f in SCORE_FEATURES if f not in df.columns]
    if missing:
        print(f"  Missing features (will skip): {missing}")
    print(f"  Using {len(feats)} features")

    X_train, y_train = train[feats].fillna(0), train['score_vs_field']
    X_test, y_test = test[feats].fillna(0), test['score_vs_field']

    # Train
    print("\nTraining RandomForestRegressor...")
    model = RandomForestRegressor(
        n_estimators=200, max_depth=8,
        min_samples_split=30, n_jobs=-1, random_state=42
    )
    model.fit(X_train, y_train)

    # Evaluate
    preds_train = model.predict(X_train)
    preds_test  = model.predict(X_test)
    print(f"\nTrain MAE: {mean_absolute_error(y_train, preds_train):.2f} | "
          f"RMSE: {root_mean_squared_error(y_train, preds_train):.2f}")
    print(f"Test  MAE: {mean_absolute_error(y_test,  preds_test):.2f}  | "
          f"RMSE: {root_mean_squared_error(y_test,  preds_test):.2f}")

    # Sanity check: distribution of test predictions
    pred_series = pd.Series(preds_test)
    print(f"\nTest prediction distribution (relative to field avg):")
    print(f"  min={pred_series.min():.1f}  mean={pred_series.mean():.1f}  "
            f"max={pred_series.max():.1f}  std={pred_series.std():.1f}")
    print(f"  (Expected: mean near 0, good players around -3 to -5, tail around +3)")


    # Feature importance (top 15)
    fi = (pd.Series(model.feature_importances_, index=feats)
          .sort_values(ascending=False)
          .head(15))
    print("\nTop 15 feature importances:")
    print(fi.to_string())

    # Save model and feature list
    MODEL_DIR.mkdir(exist_ok=True)
    model_path = MODEL_DIR / "score_model_final.pkl"
    feats_path = MODEL_DIR / "score_model_features.txt"
    joblib.dump(model, model_path)
    feats_path.write_text("\n".join(feats))
    print(f"\nSaved model -> {model_path}")
    print(f"Saved features -> {feats_path}")


if __name__ == "__main__":
    main()
