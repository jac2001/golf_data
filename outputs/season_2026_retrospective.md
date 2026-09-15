# 2026 Season Retrospective

*Generated 2026-09-07 · 29 settled tournaments · 3,171 graded predictions*

## Model performance

| Market | Predicted avg | Actual rate | Calibration | n |
|---|---|---|---|---|
| Win | 0.97% | 0.95% | 0.977 | 3,171 |
| Top 5 | 4.89% | 5.39% | 1.104 | 3,171 |
| Top 10 | 9.78% | 10.47% | 1.070 | 3,171 |
| Top 20 | 18.32% | 21.04% | 1.149 | 2,804 |

Season-long calibration held between 0.98x–1.15x across all markets — the model's
probabilities meant what they said. Slight under-prediction in place markets
(top 20 worst at 1.15x) is the main correction target for 2027 retraining.

**Winner identification:** the eventual winner was our #1 pick in 6 of 29
tournaments, and in our top-5 picks 13 of 29 times. (Season sweep: Scheffler
won the TOUR Championship as our top pick at 8.7%.)

**vs DataGolf** (14-event point-in-time benchmark, 1,492 predictions):
within 4–5% of DG on log loss in every market, better calibrated in all four,
weaker at rank ordering (Spearman 0.310 vs 0.378). Full detail:
`outputs/benchmark_vs_dg_summary.json`.

## Betting results (the honest section)

776 graded recommendations, full season (Feb 23 – Aug 30). The log originally
stopped at April 11 — an `append_log` refactor dropped the file write — and was
recovered in September from the surviving per-tournament files, then graded.

| Market | Record | ROI |
|---|---|---|
| make_cut | 10/10 | **+52.9%** |
| h2h_r4 | 25/58 | +4.1% |
| content_card | 3/6 | +336% (tiny sample; every card leg manually verified) |
| h2h (r1–r3, tournament) | 80/239 | −24% to −41% |
| group_winner | 34/194 | −18.4% |
| top 5/10/20 | 18/196 | −8% to −34% |
| outright | 0/11 | −100% |
| **TOTAL** | **174/776** | **−20.9%** |

Takeaways:
- A well-calibrated model is necessary but not sufficient — the vig plus market
  efficiency ate the theoretical edge everywhere except make_cut, where books
  price laziest.
- Round-4 H2H (+4.1%) vs rounds 1–3 (−24% to −35%) suggests our live/late-week
  data pipeline adds real information the books lag on.
- The season's recorded "+12.2pt average CLV" was audited and confirmed to be
  an artifact: grading read in-play odds as "closing" lines on a 6% winner-
  biased sample. True 2026 CLV is unknowable (closing snapshots were never
  captured); the 2027 pipeline now snapshots real closing lines pre-R1.
- One +1900 card ("to Win Wire to Wire") was initially misgraded as won by a
  leg parser that ignored the qualifier — caught in audit, corrected, parser
  fixed. Numbers above reflect the correction.

## Fantasy league (WineTime)

**3rd of 10** — $37,933,002, finishing $1.11M behind first over a 30-week season
(margin of one good week). Playoff surge: weeks 28–30 banked $9.03M, the
strongest three-week run of the season (Åberg/Burns/Clark BMW week $4.07M;
Hovland/McIlroy/Young TOUR Championship week $3.35M).

## Infrastructure scorecard

Fixed during the season: dual cron/launchd conflict, silent pipeline exit-0
failures, DG-earnings tracker clobbering, week-matcher substring bug, Playoff
tournament-type crash, and (Sept) the two settlement bugs — WD-blocks-official
and Sunday off-by-one-week — that caused most weekly delays all year.

## 2027 offseason priorities

1. Walk-forward CV retraining (replace single 2025 split)
2. Top-20 recalibration; remove the 0.20 win-prob cap heuristic
3. Small-field/no-cut model handling (playoffs, signatures)
4. Betting: concentrate on make_cut + late-week H2H; fix bet logging gap; audit CLV calc
5. Cloud-native refresh so the public site self-updates
