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
| PGA TOUR (pgatour.com + GraphQL) | stats, leaderboards, results, tee times, weather, rankings | Verbal "free while non-commercial" (Oct 6 call, Grant Bardelli) | Not in writing; scope never spelled out; we scrape far more than the call covered. |
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
`historical-odds/*`; our subscription has no historical access, so those
return nothing useful.

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
`fetch_betting_profiles`, `fetch_hole_scores`, `fetch_power_rankings`,
plus weather (GraphQL `Weather`) for PGA events. `fetch_player_colleges`
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
2. Historical results: may we backfill missing events from past-results
   pages? (See "Known data gap" below.)
3. Is there an official feed we should use instead of the web API?
4. What the revenue share would cover, if we ever monetize.

**Known data gap (found Oct 20):** `data/historical/leaderboards_*.csv`
is missing 78 events since 2019 that the stats files have, mostly
opposite-field and fall events (Bermuda, Puerto Rico, Barracuda,
Corales, ZOZO, WWT, Hero) plus The Open 2024 and 2025. 2026 misses only
Puerto Rico and Myrtle Beach. Effects: the why lines can't state an
event record for those events (they fail safe and say nothing), recent
form skips those starts, and course-history features are thin for those
events (Bermuda: 37.5% coverage). Backfilling waits on question 2 and
belongs with the January retrain (stats-reviewer).

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
