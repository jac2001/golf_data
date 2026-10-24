/**
 * columnHelp.ts — what each This Week field column means, in one or two
 * plain sentences. Shown by components/Term's "?" on every column header.
 * Jargon (SG, EV, pp) lives in Jack's lib/glossary.ts; this is "what does
 * THIS number mean here". Keep each one true to how the number is built
 * (the source is named in the comment beside it).
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */
export type ColumnHelp = Readonly<{ label: string; definition: string; example: string }>;

export const COLUMN_HELP = {
  // win_prob_sim: share of 10,000 simulated tournaments he wins; win_prob: the model's direct estimate
  win: {
    label: "Win chance",
    definition: "How often he wins across 10,000 simulated versions of this week's tournament, before it starts. The smaller \"base model\" number is the machine-learning model's own estimate before simulation.",
    example: "6.0% means he wins about 600 of the 10,000 simulated tournaments.",
  },
  top10: {
    label: "Top-10 chance",
    definition: "How often he finishes in the top 10 (ties included) across the same 10,000 simulated tournaments.",
    example: "33.8% means a top-10 finish in about a third of the simulations.",
  },
  cut: {
    label: "Makes cut",
    definition: "The chance he survives the cut after two rounds and plays the weekend, when the event has a cut. Missing it usually means little or no prize money.",
    example: "84% means he misses the cut about one week in six.",
  },
  owgr: {
    label: "World rank",
    definition: "His Official World Golf Ranking position. Lower is better. It rewards results over the last two years, so it moves slowly.",
    example: "#85 means 84 golfers in the world rank ahead of him.",
  },
  // season_sg_total: strokes gained total per round, this season
  sg: {
    label: "Strokes gained",
    definition: "Shots per round better (+) or worse (-) than an average tour field over his season, counting every shot: driving, approach, short game and putting.",
    example: "+0.34 means about a third of a shot per round better than an average field.",
  },
  // form_trend: slope of strokes gained total over his last 5 events (scripts/features/recent_form.py)
  form: {
    label: "Form",
    definition: "Which way his game is heading: the trend in his strokes gained over his last five events. Positive means improving, negative means slipping.",
    example: "+0.17 means he's been gaining about 0.17 more shots per round each event lately.",
  },
  // model_vs_vegas_edge: our published win chance - DataGolf's consensus chance (api/main.py _edge_from_market)
  edge: {
    label: "Our edge",
    definition: "Our win chance minus the betting market's (DataGolf's consensus, with the bookmakers' margin taken out), in percentage points. Positive means we rate him higher than the market does. It's a disagreement, not a guarantee.",
    example: "+1.5pp means we give him a 1.5-point better chance to win than the market does.",
  },
  odds: {
    label: "Odds",
    definition: "His odds to win: DataGolf's consensus across sportsbooks, in American format. +1200 means a $100 bet would return $1,200 profit.",
    example: "+1200 means about a 7.7% chance to win (1 in 13), the market's fair price with the bookmakers' margin taken out.",
  },
  move: {
    label: "Move",
    definition: "Which way his DataGolf consensus odds have moved since the event's opening line. Up (longer odds) means the market has cooled on him; down (shorter) means it's warming to him. Small wobbles, common for longshots, don't count.",
    example: "↓ means his odds shortened: the market rates him higher than when the line opened.",
  },
} as const satisfies Record<string, ColumnHelp>;

export type ColumnKey = keyof typeof COLUMN_HELP;
