"""
Euro (DPWT) model — train + walk-forward + market benchmark.
=============================================================
Trains XGBoost classifiers (win / top5 / top10 / top20 / made_cut) on
the euro training table, PURE — market_prob is deliberately NOT a
feature. It is the benchmark, and the blend with it happens after,
as an explicit deployment step (mirrors the PGA odds-ensemble design):

  learning   = what do fundamentals say?         (this file, features only)
  benchmark  = do fundamentals beat the market?  (log-loss on shared rows)
  deployment = combine both                       (log-odds blend, evaluated here)

Walk-forward: for each test season 2021–2026, train on strictly
earlier seasons. Comparisons only ever on rows where the market has
an opinion — beating the market on rows it never priced is a fake win.

Usage:
    python3 scripts/validation/train_euro_model.py
Saves final all-data models to data/models/euro/euro_{target}_model.pkl
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLE = PROJECT_ROOT / "data" / "processed" / "euro_training_2017_2026.csv"
MODEL_DIR = PROJECT_ROOT / "data" / "models" / "euro"

FEATURES = [
    "sg_last5", "sg_last20", "sg_trend", "score_vs_par_last10",
    "birdie_rate_last10", "bogey_rate_last10",
    "rounds_played_365d", "prior_rounds_count",
]
TARGETS = ["won", "top5", "top10", "top20", "made_cut"]

# Same restraint philosophy as the PGA forests: shallow trees, real
# leaves — a rare-event model must not memorize lucky individuals.
PARAMS = dict(
    n_estimators=300, max_depth=4, learning_rate=0.05,
    min_child_weight=25, subsample=0.8, colsample_bytree=0.8,
    eval_metric="logloss", n_jobs=4, random_state=26,
)


def blend(model_p: np.ndarray, market_p: np.ndarray, w: float = 0.5) -> np.ndarray:
    """Log-odds blend — average in the space where probabilities add."""
    eps = 1e-6
    lo = lambda p: np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps)))
    z = w * lo(model_p) + (1 - w) * lo(market_p)
    return 1 / (1 + np.exp(-z))


def main() -> None:
    df = pd.read_csv(TABLE)
    print(f"{len(df)} rows, features: {FEATURES}\n")

    # ── Walk-forward: the only honest evaluation for a time series ──
    print(f"{'year':>5} {'target':>9} {'model AUC':>10} {'model LL':>9} {'mkt LL':>8} {'blend LL':>9} {'n':>6}")
    summary = {t: {"model": [], "market": [], "blend": []} for t in ("won", "top10")}
    for year in range(2021, 2027):
        train = df[df["calendar_year"] < year]
        test = df[df["calendar_year"] == year]
        if train.empty or test.empty:
            continue
        for target in ("won", "top10"):
            m = XGBClassifier(**PARAMS)
            m.fit(train[FEATURES], train[target])
            p = m.predict_proba(test[FEATURES])[:, 1]

            # Market comparison ONLY on rows the market priced.
            has_mkt = test["market_prob"].notna().values
            if has_mkt.sum() < 100:
                continue
            y = test[target].values[has_mkt]
            pm = p[has_mkt]
            mk = test["market_prob"].values[has_mkt]
            # market_prob is a WIN probability; for top10 rescale it as
            # a naive prior (rank-preserving monotone stretch).
            mk_t = mk if target == "won" else np.clip(mk * (test[target].mean() / max(mk.mean(), 1e-9)), 1e-6, 0.99)
            bl = blend(pm, mk_t)

            ll_m, ll_k, ll_b = log_loss(y, pm), log_loss(y, mk_t), log_loss(y, bl)
            auc = roc_auc_score(y, pm) if y.sum() else float("nan")
            summary[target]["model"].append(ll_m)
            summary[target]["market"].append(ll_k)
            summary[target]["blend"].append(ll_b)
            print(f"{year:>5} {target:>9} {auc:>10.3f} {ll_m:>9.4f} {ll_k:>8.4f} {ll_b:>9.4f} {has_mkt.sum():>6}")

    print("\nmean log-loss across seasons (lower is better):")
    for t, s in summary.items():
        if s["model"]:
            print(f"  {t:>6}: model {np.mean(s['model']):.4f} | market {np.mean(s['market']):.4f} | blend {np.mean(s['blend']):.4f}")

    # ── Final models on ALL data, for live euro weeks ──
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for target in TARGETS:
        m = XGBClassifier(**PARAMS)
        m.fit(df[FEATURES], df[target])
        out = MODEL_DIR / f"euro_{target}_model.pkl"
        joblib.dump({"model": m, "features": FEATURES}, out)
    print(f"\nfinal models (all data) -> {MODEL_DIR.relative_to(PROJECT_ROOT)}/")

    # Feature importances from the win model — do the features look like golf?
    m = joblib.load(MODEL_DIR / "euro_won_model.pkl")["model"]
    imp = sorted(zip(FEATURES, m.feature_importances_), key=lambda x: -x[1])
    print("win-model importances:", ", ".join(f"{f}={v:.2f}" for f, v in imp))


if __name__ == "__main__":
    main()
