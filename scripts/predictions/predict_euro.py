"""
Euro (DPWT) weekly predictions — OUR model, served.
====================================================
Loads the calibrated euro models and prices the current euro event's
field. Cloud-safe: no DuckDB — recent rounds history is fetched from
DG's archive at serve time (~50 internal calls), because runners are
ephemeral and the training DB is local.

Feature parity is structural, not aspirational: this imports
rolling_form_features FROM the table builder — training and serving
literally share the function, so they cannot drift.

Deployment note: PURE model only (no market blend yet — blending win
alone would break the probability ladder; per-market blending is the
next enhancement). market benchmark lives in the trainer.

Usage:
    python3 scripts/predictions/predict_euro.py
Output:
    data/predictions_euro/euro_model_{tid}.csv
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "scrapers"))

from dg_client import dg_get  # noqa: E402
from scripts.features.build_euro_training_table import rolling_form_features  # noqa: E402

MODEL_DIR = PROJECT_ROOT / "data" / "models" / "euro"
OUT_DIR = PROJECT_ROOT / "data" / "predictions_euro"
HISTORY_DAYS = 420  # covers every window the features use, with slack

TARGETS = {"won": "win_prob", "top5": "top5_prob", "top10": "top10_prob",
           "top20": "top20_prob", "made_cut": "cut_prob"}


def current_euro_event() -> tuple[str, str, str]:
    """(tid, name, start_date) — resolved by the FIELD payload's own
    event name against the euro schedule. The feed serves 'the current
    event'; its label decides, never our assumption."""
    raw = dg_get("/field-updates", {"tour": "euro", "file_format": "json"})
    name = str(raw.get("event_name", ""))
    sched = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "schedule_euro_2026.csv")
    row = sched[sched["tournament_name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"euro field feed serves '{name}' — not in the schedule; refusing to guess")
    return str(row.iloc[0]["tournament_id"]), name, str(row.iloc[0]["start_date"])


def fetch_recent_rounds(before: pd.Timestamp) -> pd.DataFrame:
    """All euro archive rounds from the last HISTORY_DAYS before `before`."""
    events = dg_get("/historical-raw-data/event-list", {"file_format": "json"})
    cutoff = before - timedelta(days=HISTORY_DAYS)
    recent = [e for e in events
              if str(e.get("tour", "")).lower() == "euro"
              and pd.to_datetime(e.get("date")) >= cutoff
              and pd.to_datetime(e.get("date")) < before]
    print(f"history: {len(recent)} euro events in the last {HISTORY_DAYS} days")

    rows = []
    for ev in recent:
        try:
            raw = dg_get("/historical-raw-data/rounds",
                         {"tour": "euro", "event_id": ev["event_id"],
                          "year": ev["calendar_year"], "file_format": "json"})
            for p in raw.get("scores", []):
                for rnd in (1, 2, 3, 4):
                    r = p.get(f"round_{rnd}")
                    if isinstance(r, dict):
                        rows.append({"dg_id": p.get("dg_id"), "date": ev.get("date"),
                                     "round_num": rnd, **r})
        except Exception as e:
            print(f"  [warn] {ev.get('event_name')}: {str(e)[:60]}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> None:
    tid, name, start_date = current_euro_event()
    event_start = pd.to_datetime(start_date)
    print(f"predicting {name} ({tid}), starts {start_date}")

    field_path = PROJECT_ROOT / "data" / "fields" / f"field_{tid}.csv"
    if not field_path.exists():
        raise SystemExit(f"no field file {field_path.name} — run fetch_euro_events --field first")
    field = pd.read_csv(field_path)

    history = fetch_recent_rounds(before=pd.Timestamp.now())
    by_player = dict(tuple(history.groupby("dg_id"))) if len(history) else {}

    feats = []
    for _, p in field.iterrows():
        prior_all = by_player.get(p["dg_id"], history.iloc[0:0])
        prior = prior_all[prior_all["date"] < event_start]
        row = {"player_name": p["player_name"], "dg_id": p["dg_id"]}
        row.update(rolling_form_features(prior, event_start))
        feats.append(row)
    fdf = pd.DataFrame(feats)

    for target, out_col in TARGETS.items():
        bundle = joblib.load(MODEL_DIR / f"euro_{target}_model.pkl")
        fdf[out_col] = bundle["model"].predict_proba(fdf[bundle["features"]])[:, 1]

    out = fdf[["player_name", "dg_id"] + list(TARGETS.values())].copy()

    # Field-level identities: exactly 1 winner, 5 top-5s, etc. Per-player
    # calibration knows the POPULATION rate, not this field's arithmetic —
    # scale each cumulative column to its identity (rank-preserving).
    # cut_prob has no fixed count (ties move the line) and stays as-is.
    for col, k in [("win_prob", 1), ("top5_prob", 5), ("top10_prob", 10), ("top20_prob", 20)]:
        s = out[col].sum()
        if s > 0:
            out[col] = (out[col] * (k / s)).clip(upper=0.99)

    out.insert(0, "tournament_id", tid)
    out = out.sort_values("win_prob", ascending=False)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"euro_model_{tid}.csv"
    out.to_csv(path, index=False)
    print(f"{len(out)} players -> {path.relative_to(PROJECT_ROOT)}")
    print(out.head(5)[["player_name", "win_prob", "top10_prob"]].to_string(index=False))
    print(f"win probs sum: {out['win_prob'].sum():.3f} (a sane field sums near 1)")


if __name__ == "__main__":
    main()
