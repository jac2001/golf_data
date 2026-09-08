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

740 graded recommendations, Feb 23 – Apr 11:

| Market | Record | ROI |
|---|---|---|
| make_cut | 10/10 | **+52.9%** |
| h2h_r4 | 25/58 | +4.1% |
| content_card | 1/3 | +308% (tiny sample) |
| h2h (r1–r3, tournament) | 71/215 | −25% to −41% |
| group_winner | 34/194 | −18.4% |
| top 5/10/20 | 15/187 | −8% to −33% |
| outright | 0/11 | −100% |
| **TOTAL** | **160/740** | **−22.3%** |

Takeaways:
- A well-calibrated model is necessary but not sufficient — the vig plus market
  efficiency ate the theoretical edge everywhere except make_cut, where books
  price laziest.
- Round-4 H2H (+4.1%) vs rounds 1–3 (−25% to −35%) suggests our live/late-week
  data pipeline adds real information the books lag on.
- The recorded avg CLV of +12.2pts is inconsistent with −22% ROI and needs a
  methodology audit before being cited anywhere.
- **Gap:** bet logging stopped April 11 — recommendations from the last ~15
  weeks of the season were never logged/graded. Fix before 2027.

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
