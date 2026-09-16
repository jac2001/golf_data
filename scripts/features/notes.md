Lesson 1: How a prediction gets made. I'll teach it in layers using your real numbers, and at the end there's a small exercise where you explain a piece back to me.

---
The problem, stated plainly

Open master_training_data_2016_2026.csv and you have 48,591 rows. Each row is one player at one tournament — Scheffler at the 2024 Masters is a row, Scheffler at the 2024 PLAYERS is a different row. Each row has ~62 numbers describing the player before that tournament started (their strokes-gained form, world rank, course history), plus label columns recording what actually happened: won, top5, top10, top20 — each just 0 or 1.

So the question the model answers is: "given these 62 numbers, what's the probability this row ends in a 1?" That's it. Everything else is refinement.

One number to burn into memory: the won column is 1 in only 0.77% of rows. Winning is rare — 156 players enter, one wins. top10 is 8.9%. This imbalance shapes every design choice downstream, and it's why several things in your code exist (the probability cap, the class_weight setting, calibration itself).

How a decision tree thinks

A decision tree plays 20-questions with the features:

Is predictive_sg_weighted > 0.31?
├── No  → is world_rank_log > 4.6?   (rank ~100+)
│         ├── Yes → predict 0.1% win chance
│         └── No  → predict 0.9%
└── Yes → does he have course history here?
          ├── Yes → predict 4.2%
          └── No  → predict 2.5%

The tree learns which questions to ask by trying every feature and every cutoff, and picking the split that best separates winners from non-winners in the training data. The leaf percentages are just "of training rows that landed in this leaf, what fraction won?"

Here's the problem: let a tree grow unlimited and it keeps splitting until leaves contain a handful of rows. With winners being 0.77% of data, a deep tree will find absurd rules like "rank between 40–43 AND played in March → 100% win rate" because one guy in the training data fits that and happened to win. That's overfitting: memorizing coincidences instead of learning patterns.

Why a forest, and why your specific settin

A Random Forest trains many trees, each deen averages them:

- Each tree sees a random resample of the some left out)
- At each split, each tree may only consider a random subset of features — so they can't all lean on the same
one or two dominant signals

Individually the trees are mediocre and eaveraging them cancels the memorized noisebut keeps the shared signal — the same reason averaging 50 noisy measurements beats one.

Now look at your actual model in train_final_models.py:

RandomForestClassifier(
    max_depth=5,              # at most 5
    min_samples_leaf=25,      # every leaf must hold ≥ 25 rows
    min_samples_split=50,     # don't even
    class_weight='balanced_subsample',
)

Every one of those is an anti-overfitting ans a tree can ask at most 5 questions — itphysically cannot memorize one player. min_samples_leaf=25 means no leaf percentage is ever based on fewer than
25 examples — the "one guy in March" rule weight='balanced_subsample' tells each treeto treat the rare winners as if they were as common as losers while learning — otherwise a lazy tree discovers
it can be 99.23% accurate by predicting "n learns anything.

Where the probability comes from

At prediction time, this week's field goesrix() in predict_tournament.py — same 62features, computed for each player right now. Each row drops through every tree; each tree's leaf reports its
winner-fraction; the forest averages thoses win_prob.

Real output from your current latest_predi

┌─────────────────┬───────────────────────
│     player      │ predictive_sg_weighted │ world_rank │ win_prob │
├─────────────────┼───────────────────────
│ Cameron Young   │ +0.39                  │ 3          │ 5.5%     │
├─────────────────┼───────────────────────
│ Sepp Straka     │ +0.32                  │ 23         │ 3.7%     │
├─────────────────┼───────────────────────
│ Alejandro Tosti │ −0.65                  │ 391        │ 0.1%     │
└─────────────────┴───────────────────────
                                                                                                                Sanity-check it against the base rate: an of the time. The model says Young is ~7×more likely than average, Tosti ~8× less. Those aren't magic numbers — they're "rows that looked like this in   2016–2025 won about this often."
                                                                                                                One caveat that sets up lesson 2: raw forelly right but numerically unreliable — aforest saying "12%" might historically win 9% of the time. That's why the pickle on disk is actually            CalibratedClassifierCV wrapping the forests the next lesson.
                                                                                                                ---
Your turn. Two questions — answer in your own words, roughly, no code needed:                                   
1. Suppose we removed min_samples_leaf=25 and let leaves shrink to a single row. Training accuracy would go up. Why is that bad, and what would you expect2025 test data?
2. Your model gives Cameron Young 5.5% to win. Explain in one or two sentences what that number actually means — where it comes from mechanically.

Take your time — wrong-ish answers are usewhat to re-explain.