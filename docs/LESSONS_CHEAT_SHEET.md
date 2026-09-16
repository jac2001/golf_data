# ML Lessons Cheat Sheet — Golf Project

Six core lessons + the debugging/evaluation instincts, with the real numbers
from this project. Every claim here traces to a file in the repo.

---

## Lesson 1 — How a Prediction Gets Made

**The setup.** Training table: ~49K rows, one per player-tournament (2016–2026).
Each row = the player's stats *before* the event + what happened (`won`, `top5`,
`top10`, `top20` as 0/1). The model answers one question: given these ~60
numbers, what's the probability this row ends in a 1?

**Key number: winning is rare — 0.77% of rows.** This imbalance drives every
design choice (class weights, calibration, the old win cap).

**Decision trees** play 20-questions with features, learning splits that separate
winners from losers. Unlimited trees **memorize**: with 1-row leaves, a tree
learns "rank 240–260 AND 12 events played → 100% win" from one lucky qualifier.
Training accuracy rises; test accuracy falls. *Training accuracy measures
memorization; test accuracy measures learning.*

**Random Forest** = many deliberately-handicapped trees (random row samples,
random feature subsets per split), averaged. They overfit *differently*, so
averaging cancels the noise and keeps the signal.

**Our constraints** (`train_final_models.py`): `max_depth=5` (can't memorize
individuals), `min_samples_leaf=25` (every probability comes from ≥25 real
examples), `class_weight='balanced_subsample'` (stops the "nobody ever wins"
lazy solution).

**What "5.5% to win" means mechanically:** the row drops through every tree;
each leaf reports its historical winner-fraction; the forest averages them.
English: *of past player-weeks that resembled this profile, about 1 in 18 won.*
The model never knows the player — only profiles.

**My explain-back answers (verified):**
- Remove `min_samples_leaf` → training accuracy up (memorizing flukes), test
  accuracy down. The gap between them is the overfitting meter
  (`overfit_gap = train_auc - test_auc` in the trainer).
- 5.5% = features computed this week → every tree → leaf winner-fractions →
  averaged.

---

## Lesson 2 — Calibration (Does 10% Mean 10%?)

**The idea.** A model can *rank* well and still exaggerate numbers (say 30%
when reality is 18%). For betting that's fatal — EV multiplies the probability
itself, not the ranking.

**The fix:** wrap the forest in `CalibratedClassifierCV(method='isotonic')` —
learns a monotonic correction from predicted to observed frequencies on
held-out folds.

**The proof — full 2026 season, 3,171 graded predictions:**

| Market | Predicted avg | Actual | Ratio |
|---|---|---|---|
| Win | 0.97% | 0.95% | 0.98 |
| Top 5 | 4.89% | 5.39% | 1.10 |
| Top 10 | 9.78% | 10.47% | 1.07 |
| Top 20 | 18.32% | 21.04% | 1.15 |

Ratio 1.00 = perfect. When our model says 10%, it happens ~10% of the time.

**Honest caveat (always state it):** published probabilities blend market odds
(≤25%) + expert consensus (12%), so part of the calibration comes from the
market, not pure model skill.

**Metric pair to know:** **AUC** = ranking skill (0.81 win AUC: given a random
winner and non-winner, model rates the winner higher 81% of the time; order
only). **Log-loss / Brier** = are the *numbers* right; punishes confident
wrongness. You need both: window=4 training improved AUC but degraded log-loss
0.310→0.349 — better ranks, corrupted confidence. One without the other misleads.

---

## Lesson 3 — Temporal Validation & Leakage

**Cardinal rule: time only moves forward.** Train on years < Y, test on Y.
Never shuffle time-series data.

**Selection bias:** every decision made while looking at a dataset makes that
dataset's score a little bit of a lie. We tuned on 2025 → 2025's 0.837 win AUC
is flattered; 2026 (untouched) = the honest 0.809. *"You graded yourself on the
practice exam you studied from."* Applies at every level: hyperparameters,
feature A/Bs, even experiment configs (pre-register windows/half-lives; don't
shop for a better one after looking).

**Walk-forward CV (I implemented it — `walk_forward_cv.py`):** train on all
years before Y, test on Y, for Y = 2020…2026. Seven report cards instead of
one. **The headline is the std, not the mean**: win 0.783 ± 0.076 (33–42
winners/year → small-sample wobble), top10 0.737 ± 0.032. A model that's
0.75 ± 0.01 and one that's 0.75 ± 0.06 are different products.

**Mom version:** time-machine test — pretend it's 2020, show the model only
history, grade it on 2020; repeat for every year. Never let it peek at the
future; seven grades tell you if it's good or lucky.

**Small leaks count:** impute test-set features with *training-set* medians —
test medians would leak the future's statistical profile.

**Recency findings (pre-registered):** hard windows (last-4-years) gain AUC but
wreck calibration; **half-life sample weighting** (`0.5^(age/2)` — a 2-year-old
row counts half) keeps all rows as a calibration anchor while recent rows
dominate patterns: best of both. Anchor year is irrelevant (only ratios between
years matter). Adopted for the 2027 retrain.

---

## Lesson 4 — De-Vigging & Expected Value

**Odds are prices, not probabilities.** +700 → implied 100/(700+100) = 12.5%.
Sum all 156 players' implied probs at The Open: **147.1%**. The extra 47 points
is the **vig** — the book's margin, spread across every price.

**De-vig (multiplicative/proportional):** divide by the total. Scheffler
12.5% → 8.5% "fair." Pool markets normalize to the number of paid spots
(top-10 sums to 10). **Per book, never pooled** — mixing books halves apparent
vig and manufactures phantom edges (real bug, found and fixed).

**Two numbers, two jobs:** raw implied (1/decimal) is the **profit hurdle**
(EV > 0 ⇔ your prob > raw implied); the de-vigged fair prob is the
**disagreement meter**. Model 12% vs raw 10% is +EV *if right* — but it means
disagreeing with a market that truly believes 7.1%, and when a solo model
disagrees with a sharp market by 2x, the model is usually the one that's wrong.
To profit you must beat the book's real opinion by the entire vig cushion.

**The season's hard lesson: well-calibrated ≠ profitable. 776 bets, −20.9% ROI.**
Honest probabilities are table stakes; profit requires *private information* the
market hasn't priced. An honest-but-losing model isn't unlucky — it's
*redundant*, knowing what the market knows, priced at a 47% markup.
**Edge lives where the market is lazy:** make_cut 10/10 (+52.9%), round-4 H2H
+4.1% (our live data beats their update speed). Broad markets: bled.

**Kelly:** stake fraction = edge/net-odds; we use half-Kelly — conceding our
probabilities aren't exactly right, trading growth for variance.

**My explain-backs:** (1) the +900 friend forgot the price already contains the
book's cushion — his real claim is 12% vs a market believing 7.1%; (2) honest
models lose when they can't disagree with the de-vigged market in the right
direction by more than noise.

---

## Lesson 5 — Monte Carlo Simulation

**Why:** single probabilities can't answer *joint* questions ("all three picks
cash?"). No formula exists for combinations of 156 correlated outcomes — so
**play the tournament 10,000 times and count**. When math is intractable,
replace it with simulated experience.

**Our simulator** (`simulate_tournament.py`): each player gets Normal(μ, σ) —
μ from projected strokes gained, **σ from his own round-to-round variance**
(min 20 rounds). Draw R1; R2 adds `AUTOCORR=0.06` carry-over; cut top 65 after
R2; R3–R4 for survivors; rank totals; tally 10,000 leaderboards.

**Volatility insight (my explain-back):** two players, same μ=70. σ=3 wins more
tournaments; σ=1 makes more cuts. Winning needs an extreme right-tail week and
volatility widens *both* tails — same dial, opposite effects on the two
questions. This is why the sim needs per-player σ, not just averages.

**Hot hand (my explain-back, sharpened):** carryover is *measured* at 6% —
94% of yesterday's excess evaporates overnight. Momentum exists; pundits are
wrong about its size by an order of magnitude. Putting is the noisiest SG
category, so post-win "heat" is mostly variance. *The difference between an
opinion about momentum and a number.*

**Gumbel-max trick** (`validation/monte_carlo.py`): to sample a finishing order
from probabilities without slow sequential draws — score each player
`log(p) + Gumbel noise` and **sort**; a theorem guarantees the right
distribution. Turns 10,000 sequential simulations into one vectorized numpy op
(verified: sim rates match inputs, MAE < 0.003). Lesson: clever reformulation
can turn sequential simulation into parallel arithmetic.

**Mom version:** shuffle-and-deal the tournament ten thousand times with
weighted dice; answer any question by counting.

---

## Lesson 6 — The Evaluation Story (vs DataGolf)

**Setup:** point-in-time snapshots of DG's pre-tournament predictions (no
hindsight), joined to our graded predictions. 14 events, 1,492 matched.

**Results:** DG wins log-loss by 4–5% in every market (win 0.0443 vs 0.0463);
DG better at rank ordering (Spearman 0.378 vs 0.310); **we're better calibrated
in all four markets** (win ratio 1.017 vs 1.040) — with the market-blend caveat
stated. Within 5% of a decade-old commercial model, solo-built.

**Pooled vs within-event AUC:** pooled compares players across different
tournaments — a 30-man no-cut field has ~33% top-10 base rate vs 6% in a full
field, so pooling punishes correct cross-event rankings. Within-event (per
tournament, then averaged) asks the question that matters. Always check both.

**The trend investigation (a full case study):** top10 within-event slid
0.765→0.742→0.717→0.684 (2023–26). Killed three theories with controlled
experiments: NaN-heavy rows (clean vs broken events scored the same), pooling
artifact (within-event identical), training staleness (no recency recipe moved
2026). Then `dg_trend_check.py` (mine): **DG slid in lockstep 2023–25** →
rising parity, the game itself got harder. The 2026 extra gap was our own data
rot (string-ID join bug) — fixed, 0.684→0.735, dead even with DG's 0.725.

---

## The Instincts (cross-cutting — these impress most)

- **Audit numbers that are too good.** Every flattering anomaly we checked was
  a bug in our favor: +12.2pt "CLV" (in-play odds as closing lines), 3/3
  parlays (wire-to-wire misgrade), phantom ledger weeks. Errors that flatter
  you don't get investigated naturally — so investigate them deliberately.
- **Contradicting metrics are bug detectors.** +12pt CLV cannot coexist with
  −21% ROI; one of them is lying.
- **Pre-register, then look.** State the hypothesis, configs, and decision rule
  *before* seeing results (half-life 2 vs 4; lift ≥ +0.05 to adopt). Both of my
  registered predictions that failed (shrinkage-beats-memory; optimizer within
  ±15%) taught more than the successes.
- **Controlled experiments kill beautiful theories.** The NaN-spike story
  matched the timeline perfectly and was wrong — clean vs broken events scored
  identically. Run the experiment before acting on the story.
- **Ceiling analysis before feature work.** Year-over-year self-correlation:
  dollars +0.04 (unlearnable — no forecast can beat the target's own noise),
  finish pct +0.09 (weak but real). Saved weeks of doomed feature engineering.
  *Estimate the stable quantity, derive the noisy one* (finish → purse curve →
  dollars).
- **Sophistication must beat the dumb baseline on the same data.** Multi-year
  shrinkage tied one-year memory (+0.091 vs +0.090) — adopted only for
  coverage. Purse-only baseline for projections; last-year-finish for fit.
  Same-pairs comparisons only.
- **Shrinkage is one idea in many costumes:** `min_samples_leaf`, Laplace
  smoothing `(k+1)/(n+2)`, empirical-Bayes `(n·x̄ + K·prior)/(n+K)` — small
  samples get pulled toward a prior, proportionally to their smallness.
- **Silent failures wear green checkmarks.** Pipelines that exit 0 after
  failing, `append_log` that never wrote, a WD blocking settlement forever.
  Assert on status; grep for the call you meant to change; verify the artifact.
- **The optimizer ladder** (2026): static plan $19.2M < rolling replay $27.0M
  < me $37.9M < hindsight-perfect $111M. Live information is worth +34%;
  humans still beat the machine (flat future EV can't price option value —
  the *spend-now bias*: sharp short-term signal + flat long-term signal biases
  any rolling optimizer toward spending now). Even a champion captures ~34% of
  perfect — the week level is mostly luck.

---

## Resume-Defensible Numbers (one glance before walking in)

- 48K training rows, ~60 features, 2016–2026; win base rate 0.77%
- Walk-forward: top10 0.737 ± 0.032 across 7 seasons (I built the harness)
- Season calibration 0.98–1.15x on 3,171 graded predictions
- vs DataGolf: within 5% log-loss, better calibrated ×4, 1,492 predictions
- Betting: 776 graded, −20.9% ROI, make_cut 10/10 +52.9% — and I can explain why
- ILP optimizer (pulp/CBC): ~8K binary vars, uses/slots constraints, evaluated
  against my own championship seasons with a hindsight-optimal bound
