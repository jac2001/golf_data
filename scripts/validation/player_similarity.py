#!/usr/bin/env python3
"""
Player Similarity — find statistically similar players by SG profile.

Uses cosine similarity on normalized strokes-gained features.
Cosine similarity measures the *shape* of a player's profile (their pattern
of strengths/weaknesses) rather than raw magnitude. Two players score as
similar if they excel in the same categories and struggle in the same ones.

Outputs:
    outputs/player_similarity.csv  — for every player, their 10 nearest neighbors
                                    with a similarity score (1.0 = identical profile)
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
PREDS_FILE   = OUTPUTS_DIR / "latest_predictions.csv"

# Features that define a player's style/profile
# We use season SG (stable, larger sample) not week-to-week recent SG
SIMILARITY_FEATURES = [
    "season_sg_ott",    # off the tee
    "season_sg_app",    # approach
    "season_sg_arg",    # around the green
    "season_sg_putt",   # putting
    "season_sg_t2g",    # tee to green composite
    "course_fit",       # how well their game fits this course type
]


N_NEIGHBORS = 10

def compute_similarity() -> pd.DataFrame:
    preds = pd.read_csv(PREDS_FILE)

    # Keep only rows with enough data
    available = [f for f in SIMILARITY_FEATURES if f in preds.columns]
    df = preds[["player_name", "world_rank", "win_prob"] + available].copy()
    df = df.dropna(subset=available)

    print(f"  {len(df)} players with full feature data")

    # StandardScaler: subtract mean, divide by std so every feature is on the
    # same scale (otherwise sg_t2g would dominate because its range is larger)
    X = df[available].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Cosine similarity matrix: shape (n_players, n_players)
    # sim[i, j] = how similar player i is to player j (1.0 = identical direction)
    sim_matrix = cosine_similarity(X_scaled)

    # Build neighbor table
    rows = []
    names = df["player_name"].tolist()
    for i, name in enumerate(names):
        # Get similarity scores for all other players, sorted descending
        sims = sim_matrix[i]
        order = np.argsort(-sims)  # descending
        rank = 1
        for j in order:
            if j == i:
                continue  # skip self
            if rank > N_NEIGHBORS:
                break
            rows.append({
                "player_name":      name,
                "similar_player":   names[j],
                "similarity_score": round(float(sims[j]), 4),
                "similar_rank":     rank,
                "similar_win_prob": round(float(df.iloc[j]["win_prob"]), 5),
                "similar_world_rank": int(df.iloc[j]["world_rank"]) if pd.notna(df.iloc[j]["world_rank"]) else None,
            })
            rank += 1

    result = pd.DataFrame(rows)
    out = OUTPUTS_DIR / "player_similarity.csv"
    result.to_csv(out, index=False)
    print(f"  Saved → {out.name}  ({len(df)} players × {N_NEIGHBORS} neighbors)")
    return result


if __name__ == "__main__":
    print("Computing player similarity...")
    df = compute_similarity()
    # Print a few examples
    for player in ["Fitzpatrick, Matt", "Thomas, Justin", "Bridgeman, Jacob"]:
        sub = df[df["player_name"] == player].head(5)
        if sub.empty:
            continue
        print(f"\nMost similar to {player}:")
        for _, r in sub.iterrows():
            print(f"  {r['similar_player']:<30}  similarity={r['similarity_score']:.3f}rank={int(r['similar_world_rank']) if r['similar_world_rank'] else '?'}")

