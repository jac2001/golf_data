# Players page audit (Oct 21, 2026)

`web/app/players/page.tsx` (2,304 lines, signed-in only): four tabs (Profiles,
Head-to-Head, Stats, Course Fit). Checked against the code and production's
API on Oct 21 (Bermuda week, field of 120). The rendered page wasn't viewed:
it needs a sign-in. Every finding below names its evidence.

Severity: **P1** wrong or private information shown to members · **P2**
misleading or broken · **P3** clarity, design, code health.

## P1: wrong or private

1. **[fixed Oct 22] Jack's tracker and the dead strategy file are public.**
   `/api/players/profile` (no auth) returns `uses_remaining`, `badge`,
   `recommendation`, `this_week_ev` for any golfer. The page shows REC and EV:
   Scheffler's profile reads "REC USE NOW · EV $0" while his `badge` is MAXED
   (Jack's uses spent). Same class as audit #9's highlights (now owner-only).
   Fix: drop these from the public profile (owner-only endpoint if wanted);
   remove REC/EV from the page (EV was already dropped on This Week).
2. **[fixed Oct 22] Two different chances for the same golfer.** Profile, Stats and H2H show
   the base model (`win_prob`, `top10_prob`); This Week shows the 10,000-run
   simulation (`*_sim`). Ben James: top-10 **17.5%** on Players, **33.8%** on
   This Week. Fix: one published number everywhere (sim when present, as This
   Week does), labeled the same.
3. **[fixed Oct 22] "Edge" is 100x too small.** `model_vs_vegas_edge` is a fraction (0.0048)
   printed as points: profile chip and H2H "Edge vs Vegas" show "+0.0pp" for
   everyone (same bug fixed on This Week, c6297ef).
4. **[fixed Oct 22] H2H "Season Wins" shows top-10s.** `va={p1.betting_profile?.top_10s}`
   under the label "Season Wins".
5. **[fixed Oct 22] Missing shown as zero.** `/api/players/stats`: `course_made_cut_rate`,
   `course_win_rate`, `course_sg_ott/app/putt_avg` are 0 for all 120 golfers;
   the Stats tab prints course **Cut% "0%"** for the 76 golfers with starts here.
   8 golfers (Jay Leng, Nick Jones, ...) have season SG exactly 0 in every
   category AND world rank exactly 500: both placeholders for "no data", shown
   as "+0.00" and "World #500". Fix at the API (null, not 0 / 500) and in the
   view ("—", "Unranked").
6. **[fixed Oct 22] AI synopsis shows Anthropic's billing error.** `/api/players/synopsis`
   returns HTTP 502 `"LLM error: ... Your credit balance is too low ... Plans &
   Billing ... request_id"`; the card renders `{error}` verbatim. Fix: a plain
   "Analysis unavailable right now" (log the detail server-side), and hide the
   Generate button while the key can't serve.

## P2: misleading or broken

7. **[fixed Oct 22] "DK Odds" chip.** DraftKings is retired (rule 5), and the profile endpoint
   never gets DataGolf's odds (`odds_to_win` null), so the chip never shows.
   Fix: reuse `_dg_odds_for` (This Week's source), label "Odds (DataGolf)".
8. **[fixed Oct 22] Drift arrow colors inverted.** Profile: "UP" (odds lengthening = market
   cooling) is green ▲. This Week's Move treats UP as bad. Also null today
   (profile lacks the DG move). Fix with #7: one Move, same meaning.
9. **[fixed Oct 22] "DG Win%" headline is pre-course.** The chip shows DataGolf's baseline
   (7.9% Ben James); the line below says "6.1% adjusted" (baseline + history +
   fit, DG's real prediction). Fix: headline the adjusted number.
10. **[fixed Oct 22] Players Course Fit tab is permanently generic in production.** Its weights
    come only from the local DuckDB (`course_fit_weights`), absent on Render, so
    every course gets the hardcoded default (`is_default: true`, confidence 0,
    0 players): Bermuda "Around the green 35.7%" vs This Week's DataGolf profile
    "Approach 34.7%". Two pages, opposite answers. Fix: retire this tab in favor
    of This Week's redesigned Course Fit (link there), or feed it DG's profile.
11. **[fixed Oct 22, Jack's helpers] The PGA TOUR betting profile is mostly empty.** (Correction: the
    card already skipped empty fields one by one; the real bug was a blank summary "  " drawing an
    empty box. presentFields now drives the summary and the stat row.) Ranks, driving accuracy,
    GIR, FedEx, summary, bullets null/empty for Ben James. The card shows a wall
    of "—". Fix: show only fields with values, or drop the card (it's also a
    "Moving off PGA TOUR" candidate, DATA_PERMISSIONS).
12. **[fixed Oct 22, Jack's helpers] No "not in this week's field" state.** Scheffler (not playing): an "Our
    Model" card of dashes, WIN RANK "—". Fix: say "Not in the Bermuda field",
    show his season/skill sections, hide this-week sections.
13. **[fixed Oct 22] Two "course fit delta" values with different signs.** Ben James:
    `dg_prediction.course_fit_delta` -0.018 vs `decompositions.course_fit_delta`
    +0.039, and DG's actual `total_fit_adjustment` -0.14. H2H "Course Fit Adj."
    uses the +0.039 one. Fix: one fit number (DG total fit, as Course Fit uses).
14. **[fixed Oct 22] Three different "SG Total" rows in H2H** (our season SG, DG skill rating,
    PGA TOUR betting profile) with no explanation; values differ (0.34 / 1.28 /
    1.50 for Ben James). Fix: one, named by source and period.
15. **[fixed Oct 22, Jack's helpers] Career earnings are blank for 2026** (`earnings` null, e.g. 2nd at
    Biltmore): a column of "—"; when present they print unformatted. Fix: hide
    the column when empty; format as money when present. (Settlement estimates
    exist in /api/results/earnings; don't mix them in unlabeled.)
16. **[fixed Oct 22] Season counts disagree**: career `by_year` 2026 = 6 starts; betting
    profile `events_played` = 7. Fix: one source per number, named.
17. **[fixed Oct 22] "Top10 Score" label** on `recent_top10s` (a count, not a score).
18. **Raw DataGolf on a page** (decompositions, skill ratings, approach skill,
    DG predictions; ~46 DG references) and a public API that serves them:
    DATA_PERMISSIONS open question 1. Note for Jack's decision; not a bug.

## P3: clarity, design, code health

19. **Jargon without help.** SG, OTT, APP, ARG, "Timing adj.", "True SG adj.",
    "Prox FW", "DG Fit Δ%" appear with no explanation. Fix: `Term` + the
    glossary/column help (This Week pattern); plain labels ("Recent form" not
    "Timing adj.").
20. **[fixed Oct 22, b1a42b5] Wide tables on phones.** (Pinned name column, tighter cells, Sort by picker on Stats.) Stats (up to ~14 columns), career, round
    breakdown, approach buckets. Fix: cards or a sort selector on phones (Field
    tab pattern); fewer default columns with "More columns".
21. **Three sub-views named "Course Fit"** (page tab, profile sub-tab, stats
    mode), each a different number.
22. **Colors:** palette mostly tokens (3 hex), but `BLUE` is defined as yellow
    ("H2H player B"), `GOLD` is also yellow, `LABEL` = `MUTED`. Rename to intent.
23. **Duplicate helpers:** `posColor`/`posColor2`, `sgColor`/`sgColor2`,
    `toParColor2`. One each, in `lib/`.
24. **2,304-line file** with 20+ components; split by tab
    (`app/players/_components/…`) so each can be tested and reviewed.
25. **[fixed Oct 22, 51e2082] Loading/empty/error states** (one Notice; added the missing catches and Try again) are inconsistent: some "Failed to load.",
    some red raw errors, some nothing.

## Fixed Oct 22 (P1)

#1-#6, plus `/api/mypicks` (Jack's whole season usage tracker, public; no site
caller) now owner-only. Published chances are the simulation everywhere on
Players (`api _published_chances`), and the profile headline is the win chance
with the field rank under it. Placeholders: all-zero columns and rank-500/all-0
rows become null (`api _null_placeholders`). LLM failures (synopsis, live
pulse) log the provider's message and return a plain 503.

## Suggested order

1. P1 #1, #3, #4, #6 (small, high-trust fixes) and #2 (one published chance).
2. #5 at the API (null not 0) + view; #7/#8 (DG odds + Move, shared with This Week).
3. #10: retire the Players Course Fit tab in favor of This Week's.
4. #12, #11, #15, #9, #13, #14: profile clarity pass ("not in the field",
   only real fields, one fit number, one SG).
5. #19, #20, #21: plain language + phone layout.
6. #22-#25: code health (split the file first; it makes 1-5 easier to review).

Teaching candidates: the "which number do we publish" rule (#2/#9, a pure
function with tests); the "show only fields with values" helper (#11/#15);
the not-in-field decision (#12).
