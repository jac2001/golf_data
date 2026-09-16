# Redesign Content Map — nothing gets lost

Rule for the Broadcast implementation: every feature below must have a home
in the new design before its old page is touched. Mockups are the showcase;
this table is the contract.

## Current surface → new home

| Current | Contents | New home | Status |
|---|---|---|---|
| **Predictions** page (6 tabs) | Field table, Lineup cards, Tee times, Course (holes+history), DG compare, Course fit; weather strip, WD alerts | **Field Forecast** screen, with a sub-tab row (Field / Lineup / Tee Times / Course / Model vs DG / Course Fit) in the yellow active-tab style | Mock shows Field view; sub-tabs are a modification, no loss |
| **Betting** page (4 tabs) | Value bets, Matchups (3-ball + H2H), Odds Explorer (multi-book), Expert Picks | **Betting Board** screen + same sub-tab row (Board / Matchups / Odds Explorer / Expert Picks) | Mock shows Board; sub-tabs added |
| **History → bets + slip** | Graded bet ledger, P&L by market, bet slip | **Betting Board** — honest ledger is already in the mock; slip becomes a Board drawer | Merged, nothing lost |
| **History → results + model** | Past tournaments, leaderboards, model accuracy per event (ModelComparison) | **How It Works** gains a "Results" section (public track record, per-event) | Move, restyle |
| **Live** page (5 tabs) | Leaderboard, Vs Predictions, My Lineup Live, SG stats, Hole stats; LivePulse, scorecards | **Live** screen — same 5 tabs in Broadcast style (scoreboard tables suit it best of all pages) | No mock yet — design at build time from the system |
| **Players** page (4 tabs) | Lookup, Head-to-Head, Stats, Course Fit | **Player** screen (mock = profile) + Lookup landing + H2H view keeping the dual-color bars | Mock shows profile; other tabs styled in-system |
| **My Picks** (log, roster) | Weekly pick log w/ earnings, roster usage | **My League** zone: roster → Star Budget (mocked); log → Miss Ledger page (merged with machine comparison) | Merged into League zone |
| **Fantasy** tab (new) | Ladder, miss ledger, 2027 season map, trio panel | **My League** zone: Tuesday Call (mocked), Season Plan, Star Budget, Miss Ledger | Direct mapping — the zone's 4 sub-pages |
| **Assistant** | Chatbot w/ intel | Keeps its nav slot in both zones; restyled chat surface | No loss; placement kept simple |
| **Methodology** | Full modeling story | **How It Works** (renamed in nav) + Results section | Rename + addition |

## New-only additions (no old counterpart)
- **Home** — the focused landing (hero, storylines, trust strip). Pure addition;
  today's site has no real landing page.

## Label translations (site-wide layer)
| Old | New (jargon on hover/tooltip) |
|---|---|
| SG: OTT / APP / ARG / PUTT | Off the tee / Approach / Short game / Putting |
| EV | Projected payout |
| edge (pp) | Our edge (points) — cards say "our chance vs book price" |
| p(win), win_prob | Win chance |
| course_fit score | Course fit: Excellent / Good / Average / Poor |
| form/trend values | Hot / Warming / Steady / Cooling |
| WD | Withdrawn |

## Implementation order (screen by screen, old page stays until parity)
1. Design tokens + shared components (nav, sub-tabs, scoreboard table, cards)
2. Home (new)
3. Field Forecast (absorbs Predictions)
4. Betting Board (absorbs Betting + History bets/slip)
5. My League zone (absorbs My Picks + Fantasy)
6. Player / Players
7. Live
8. How It Works + Results (absorbs History results/model)
9. Assistant restyle; retire old routes
