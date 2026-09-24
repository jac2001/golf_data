# ML Lessons Cheat Sheet — Golf Project

Ten core lessons + the debugging/evaluation instincts, with the real numbers
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

## Lesson 7 — Probability Ladders → Dollars (expectedPayout)

**The setup.** The model outputs a CUMULATIVE ladder per player:
win ⊆ top5 ⊆ top10 ⊆ top20 ⊆ cut — each rung contains the ones above it.
Prize money is paid by DISJOINT bucket (winner, 2nd–5th, 6th–10th, …), so
expected earnings needs the conversion (`web/lib/modelBrain.ts` — I wrote it):

- **Disjoint from cumulative = adjacent differences.** P(2nd–5th) =
  P(top5) − P(win). Every rung is "at least this good", so subtracting the
  rung above leaves exactly the band between them.
- **Clamp each difference at ≥ 0.** Calibration adjusts each market
  independently, so a corrected top5 can dip *below* the corrected win —
  mathematically impossible for true probabilities, routine for calibrated
  ones. Without the clamp, a crossing pays negative money.
- **Null-fill from the rung below, in ladder order, on a COPY.** Code review
  found three seams in my first draft: `find(k => k > key)` filled rungs in
  *alphabetical* order (top10 borrowed from top20, top5 from win — behavior
  decided by spelling); the fill mutated the caller's object; and a
  half-applied patch computed `filled` but still read `probs` — dead code
  wearing a fix's name.
- **Payout table** (avg % of purse): win 18.0, 2–5 6.6, 6–10 3.0,
  11–20 1.6, made-cut-rest 0.45. EV = purse × Σ bucketProb × pct.

**First live outing:** the model's Round-3 pick, Jacob Bridgeman (5.5% win,
highest in field), shot −7 and won the tournament — model finished #1 of 3
in the Round Game. One week, zero evidential weight (see Lesson 5), maximum
bragging rights.

**Explain-back prompts (answer, then mark verified):**
- Why can a calibrated top5 drop below a calibrated win, and why can't a
  true top5?
- What breaks if you sort the ladder alphabetically? Which pair of rungs
  silently swaps its fill source?
- Why does `modelFadePicks` reusing `expectedPayout` mean a payout-table
  change can't desynchronize the two games?

---

## Lesson 8 — Label Provenance (key data by its OWN label)

**The failure, twice, months apart, different feeds:**

1. **Euro settle:** the DPWT field feed flips to the *next* event the moment
   one finishes. Settling BMW PGA off it wrote the results under the Open de
   France id at a $3M purse — the winner "earned" $499,800 instead of ~$1.5M
   of the real $9M purse. Corrupted rows, purged and resettled.
2. **DataGolf feeds:** `/field-updates` and `/betting-tools` serve THE
   CURRENT EVENT and take no tournament parameter. A Monday fetch during a
   team week saved the **Presidents Cup roster (24 = two 12-man teams) as
   Bank of Utah's field**, and Biltmore's week-old odds as its market. A full
   junk prediction run shipped before a name-merge matching only 4/24 players
   exposed it.

**The rule:** a feed that serves "the current X" is a landmine. The tid you
*request* is a hope; the `event_name` the *payload carries* is a fact. Key
data by the payload's own label or refuse to write.

**The mechanism** (`scripts/scrapers/event_guard.py`): distinctive-token
overlap between payload event name and the schedule's name for the requested
id — stopwords ("championship", "open", "cup") stripped so 'Bank of Utah
Championship' vs 'Presidents Cup' shares nothing while 'THE CJ CUP Byron
Nelson' still matches 'CJ Cup Byron Nelson'. **Fails closed**: unknown
schedule name = no write. A red pipeline saying "feed serves Presidents Cup"
beats a green one shipping fiction.

**Explain-back prompts:**
- Why is failing closed right here, when most fetchers in this repo
  deliberately degrade gracefully?
- The bogus field had *fuller-looking* data than the truth (24 stars vs no
  field at all). Which instinct from the list below does that rhyme with?

---

## Lesson 9 — Guards, Idempotency, and Rules the App Can't Break

**Constraints ARE the rules.** The friends games' rules live as database
constraints, not application checks: UNIQUE(user, event, player) = "can't
pick the same player twice"; UNIQUE(user, event, round) = "one pick per
round". `ON CONFLICT DO NOTHING` makes every write idempotent — a retry, a
double-tap, a replayed cron all land as no-ops. The app enforces politeness;
the schema enforces law.

**Re-running is a test.** The model-sync cron is supposed to be idempotent,
so I ran it twice as a check — and run #2 picked Round 4 a day early. The
bug (no "never pick more than one round ahead" guard) was invisible in any
single run. If a job claims idempotency, running it again is the cheapest
integration test you own.

**Don't bet a rumor.** Early-week DG fields are partial (24 commitments of
~130). Probabilities normalize over whoever showed up, so a 24-man "field"
inflates everyone — Scheffler at 13.8% was an artifact of the denominator.
The model refuses to place picks under 50 players ("field too small to bet")
and the UI banners the pool as provisional. Same shape as the win cap and
`min_samples_leaf`: a guard that says *this estimate's inputs don't support
acting on it yet.*

**At-most-once by claiming first.** Push reminders insert into a
UNIQUE(endpoint, event) table with `RETURNING` *before* sending — an empty
return means some earlier run already claimed the send. Claim-then-act turns
"probably won't double-send" into "can't".

**Explain-back prompts:**
- Why is the UNIQUE constraint stronger than the same check in the API
  route? Name a path that bypasses the route but not the constraint.
- What's the analogy between the 50-player floor and `min_samples_leaf=25`?

---

## Lesson 10 — Incentive Design (the score function IS the game)

**Ask "what's the laziest way to win?" before shipping any scoring rule.**

- **Naive Fade Game** (pick 3 flops, lowest combined earnings wins) is
  broken on arrival: pick three 500-to-1 club pros, they miss every cut,
  everyone ties at $0 forever. The fix isn't policing — it's making the
  degenerate strategy unavailable: you may only fade from the model's top 20
  by win chance. Now the question is genuinely hard (*which favorite
  flops?*) and fading the eventual champion costs you his whole check.
- **Season aggregation inverts too.** Summing a lowest-wins score across a
  season makes *not entering* the optimal strategy — skip every week, sum
  $0, win the season. Fixed by counting EVENT WINS per settled event (ties
  all credited): the incentive points back at playing and winning.
- Same family as the optimizer's *spend-now bias* (Instincts): whenever a
  score function and the behavior you want diverge, participants — human or
  algorithmic — drift toward the score, not the intent.

**Explain-back prompts:**
- The weekly game sums earnings across a season and is NOT broken. What
  property of "higher is better" makes summation safe there and fatal in
  the fade game?
- Design a season format for the Round Game that stays fair for someone
  who joins mid-season. What does it trade away?

---

## Lesson 11 — Field Arithmetic (per-player models vs the event's identities)

**The bug that taught it:** the euro model's first served field summed
its win probabilities to **1.253** — a 25% overbook. Every individual
number was properly calibrated; jointly they described a tournament
with 1.25 winners.

**Why calibration can't see it:** isotonic calibration teaches each
player-level classifier the POPULATION base rate ("of player-weeks
like this, X% won"). It knows nothing about which players share a
field. But a field has hard identities — exactly 1 winner, exactly 5
top-5s, exactly 10 top-10s — and independent binaries have no
mechanism to respect them. A strong field overbooks; a weak field
underbooks.

**The fix:** rank-preserving normalization at serve time — scale each
cumulative column to its identity (win → sums to 1, top-N → sums to
N). `made_cut` deliberately stays raw: ties move the cut line, so
there is no fixed count to normalize to — know which columns HAVE an
identity before enforcing one.

**The rhyme:** this is Lesson 7's clamp one level up. There:
pointwise-calibrated markets crossed the ladder (top5 < win). Here:
pointwise-calibrated players broke the field's arithmetic. Same law —
**individually optimal estimates don't automatically satisfy joint
constraints; enforce the constraint explicitly where it lives.**

**Explain-back prompts:**
- Why does a strong field overbook and a weak field underbook, given
  every player's number is individually calibrated?
- The PGA pipeline normalizes too, buried in post-processing. What's
  the argument for doing it at SERVE time instead of TRAIN time?

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
- **Anchor every clock to the moment of decision.** Three instances, one
  disease: a 365-day form window anchored to the player's own last round
  (couldn't see layoffs), CI freshness by file mtime (checkout resets it),
  and game locks at midnight UTC (PGA picks quietly closed at 7pm ET).
  Time anchored to the data's own extent, the machine's clock, or the
  wrong timezone always LOOKS right on the happy path.
- **Designs fossilize around cardinality assumptions.** model-sync fetched
  predictions ONCE because "only one event has numbers" was true the day
  it was written — the euro model's debut broke it precisely where the
  one became many. When a count assumption (one tournament, one tour, one
  user) quietly underpins a design, it fails on the day of success.
- **Integrity outranks participation.** The model missed France's weekly
  lock by 20 minutes of deploy latency; we did NOT backfill its picks,
  though the numbers were public pre-lock. Nobody picks after tee-off —
  not even the house's own model, not even sympathetically late — because
  one exception makes every board's reveal-at-lock promise negotiable.
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
