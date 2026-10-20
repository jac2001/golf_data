# Data permissions

One place for what Golf Edge uses from whom, what we're actually allowed
to do with it, and what's still open (ROADMAP Now #3). Inventory taken
from the code on 2026-10-20; terms read the same day. Update this file
in the same change that adds or drops a source.

Not legal advice. Where it says "unclear", the answer is to ask the
provider in writing, not to decide it ourselves.

## Summary

| Source | What we use | Status | Biggest gap |
|---|---|---|---|
| DataGolf API | predictions, odds, fields, live scores, skill ratings | Paid subscription (Scratch Plus) | Terms say personal, non-commercial use and no redistribution. We display DG numbers publicly. |
| PGA TOUR (pgatour.com + GraphQL) | stats, leaderboards, results, tee times, weather, rankings | Verbal "free while non-commercial" (Oct 6 call, Grant Bardelli) | Not in writing. Most of it can move to DataGolf (see "Moving off PGA TOUR"). |
| Open-Meteo | DP World Tour forecasts, historical weather | Free tier, non-commercial | CC BY 4.0 attribution: added Oct 20. Ends if the site carries ads or subscriptions. |
| protourfantasygolf.com | Jack's original league: picks, usage, scorecards | Jack's own account | Third-party site; used for the legacy league only. |
| Anthropic, Groq | assistant, tournament intel, recaps | Paid API keys | Standard API terms; nothing redistributed beyond generated text. |
| GitHub, Vercel, Render, Neon, Clerk, Pushover | infrastructure | Our accounts | None for data rights. |

## DataGolf

**What we pull** (all through `scripts/scrapers/dg_client.py dg_get`):
pre-tournament predictions and the pre-tournament archive, player
decompositions, skill ratings, approach skill, field updates, schedule,
outright and matchup odds (`betting-tools`), in-play predictions, live
tournament and hole stats. Code also calls `historical-raw-data/*` and
`historical-odds/*`. Our plan DOES include `historical-raw-data`
(per-round scores and strokes gained back to the 1980s for majors;
verified Sep 25 and again Oct 20); prediction archives are limited.

**How it reaches users:**
- *Raw, publicly displayed:* "DG Model" / "DG Win" columns on /players;
  the DG tab on This Week; live scores in the Match Center ("Live scores
  come from DataGolf"); sportsbook prices on the Betting Board (from DG's
  betting-tools feed).
- *Derived:* our model blends DG's pre-tournament probabilities
  (weight 0.50) and DG odds into its published predictions; the
  integrity gate checks DG coverage.
- *Game scoring:* live positions for "estimated payouts if the
  tournament ended now"; final money comes from official results.

**Terms (datagolf.com/terms-and-conditions, section 13):** use is
"exclusively for your own personal, non-commercial use", API included,
and you "will not redistribute or transfer" the content. Nothing on
derived works or attribution.

**Read:** displaying DG's numbers to the public is redistribution,
paid or not. A model that blends DG inputs is a gray area. Live scoring
from DG is the most important use for the game.

**Open questions for DataGolf (email, get a written answer):**
1. May a free, non-commercial site display DG predictions/odds with
   attribution? If not, what plan covers it?
2. May we publish our own predictions that use DG inputs?
3. May we use in-play data to score a free friends game?
4. What changes if Golf Edge later earns money?

**Until answered (Jack's call):** the lowest-risk interim step is to
stop showing raw DG columns (/players DG views, This Week's DG tab,
sportsbook prices on the Betting Board) while keeping DG as a model input and
for live scoring, which the game needs.

## PGA TOUR

**What we pull.** Far more than "scorecards, weather and power
rankings". The automated refresh (`scripts/scheduled_refresh.py`) runs:
`fetch_tournament_stats`, `fetch_form_stats`, `fetch_course_stats`,
`fetch_course_characteristics` (strokes-gained and course stats: the
model's core features), `fetch_live_leaderboard`, `fetch_past_results`
(historical results: training labels, recent form, the why lines),
`fetch_tee_times`, `fetch_withdrawals`, `fetch_world_rankings`,
`fetch_player_database`, `fetch_expert_picks_pga`,
`fetch_betting_profiles`, `fetch_hole_scores`, plus weather (GraphQL `Weather`) for PGA events. `fetch_player_colleges`
(College Game) uses GraphQL `Player`. Requests use the public web app's
API key and headers.

**How it reaches users:** the model's predictions (derived), the why
lines' recent finishes and event history, tee times, weather, college
assignments, official results for settlement.

**Permission:** Oct 6 call with Grant Bardelli: likely free while
non-commercial, a small revenue share if monetized. Nothing in writing.
What we described on that call may not have covered scraping stats and
results at this scale.

**Open questions (follow up with Grant in writing):**
1. Confirm non-commercial use in writing, listing what we pull (the
   list above) and how it's shown.
2. Is there an official feed we should use instead of the web API?
3. What the revenue share would cover, if we ever monetize.

**Known data gap (found Oct 20):** `data/historical/leaderboards_*.csv`
is missing 78 events since 2019 that the stats files have, mostly
opposite-field and fall events (Bermuda, Puerto Rico, Barracuda,
Corales, ZOZO, WWT, Hero) plus The Open 2024 and 2025. 2026 misses only
Puerto Rico and Myrtle Beach. Effects: the why lines can't state an
event record for those events (they fail safe and say nothing), recent
form skips those starts, and course-history features are thin for those
events (Bermuda: 37.5% coverage). DataGolf's historical rounds have
every one of these events (checked Oct 20), so the backfill is a
DataGolf job, not a PGA TOUR one. It changes model inputs, so it goes
with the January retrain (stats-reviewer).

**Why PGA TOUR still supplied results (found and fixed Oct 20):** the
DataGolf replacement (`fetch_dg_historical_results.py`) wrote only to
DuckDB, which exists on Jack's Mac and not on GitHub Actions, and it
mapped ids by calendar year (a year off for every fall event before
2024). It now writes `data/historical/leaderboards_dg_{season}.csv`,
maps ids by season, and checks each event's name, date and winner
against ours before writing. Backfilled 2016-2026 on Oct 20; the
Tuesday refresh catches up anything new. The why lines read it now;
the model reads it from the January retrain, once
`scripts/validation/compare_leaderboard_sources.py` shows the two
sources agree.

## Moving off PGA TOUR

Power rankings: dropped Oct 20 (nothing used them).

| PGA TOUR scraper | DataGolf replacement | Notes |
|---|---|---|
| `fetch_past_results`, history CSVs | `historical-raw-data/rounds` | Done Oct 20: `leaderboards_dg_*.csv`. Retire the PGA TOUR step after the agreement check and the retrain. |
| `fetch_tournament_stats`, `fetch_form_stats` | `historical-raw-data/rounds` (SG by round) | Some events have no SG (`sg_categories: no`, e.g. Baycurrent). Model features: January retrain. |
| `fetch_tee_times`, `fetch_withdrawals` | `field-updates` | Already pulled every refresh. Verify tee times are present for both rounds. |
| `fetch_world_rankings` | DG rankings (OWGR column) | Verify the field. |
| PGA weather | Open-Meteo | Already used for DP World Tour. |
| `fetch_live_leaderboard` (settlement) | DG live stats for positions | DataGolf has no prize money. Official earnings need the purse payout table applied to final positions, or a PGA TOUR source. Decide before switching. |
| `fetch_hole_scores` | none | Per-player hole scores exist only at PGA TOUR (Live scorecard grid). |
| `fetch_player_colleges` | none | College Game needs it. |
| `fetch_course_stats`, `fetch_course_characteristics` | partial (`live-hole-stats` during events) | Course-fit features; keep until the retrain decides. |
| `fetch_expert_picks_pga` | none | PGA TOUR editorial picks feed a 12% expert-consensus blend in published predictions. Dropping it changes the model: decide with the retrain. |
| `fetch_betting_profiles` | none | Read by the chatbot, planning tools and the API. Check what's user-facing before dropping. |

## Open-Meteo

DP World Tour forecasts (`fetch_euro_events.py`, `fetch_weather_openmetro.py`),
the API's live weather, and historical weather for training
(`fetch_historical_weather.py`). Free tier: non-commercial means "private
or non-profit websites or apps that do not have subscriptions or
advertising", under CC BY 4.0. The weather strip credits "Open-Meteo.com
(CC BY 4.0)" when it shows their data (added Oct 20). Ads or
subscriptions would require a paid plan.

## protourfantasygolf.com

`fetch_league_picks`, `fetch_fantasy_usage`, `fetch_fantasy_scorecard`
read Jack's original league on a third-party fantasy site, for the
legacy league and dashboard. Not part of the Golf Edge game. If it keeps
running, check that site's terms; otherwise retire the fetchers.

## When this changes

Re-check every row before any of: ads, subscriptions, paid features,
sponsorship, or a public launch beyond friend groups. Each of DataGolf,
PGA TOUR and Open-Meteo draws its line at commercial use.
