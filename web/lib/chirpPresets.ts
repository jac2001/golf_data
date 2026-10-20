/**
 * chirpPresets.ts — which quick chirps to offer right now.
 * ========================================================
 * docs/CHIRPS_DESIGN.md. Chirps sit on the matchup card, and the preset
 * lines are tied to what just happened. A preset is only offered when it's
 * TRUE: "Don't look now" when one of your golfers leads the tournament,
 * "So much for the expert" when you're ahead of the model, and so on. A
 * taunt that isn't backed by the board just reads as noise.
 *
 * Pure function, no imports from "@/": `npm test` runs it. The sheet shows
 * whatever you return as tappable chips, plus a box for a custom message.
 */

/** What the matchup says about you right now (built from the Match Center). */
export type ChirpContext = {
  status: "open" | "live" | "settling" | "final";
  /** Your rank in the group (1 = leading), or null if you didn't play. */
  myRank: number | null;
  /** People on the slate (the model counts as one). */
  players: number;
  /** You're tied for your rank with someone (e.g. tied for 1st). */
  tied: boolean;
  /** Your golfer currently at position 1 / T1 in the tournament, or null. */
  myGolferLeading: string | null;
  /** How many of your golfers missed the cut (or withdrew), out of myGolfers. */
  myGolfersOut: number;
  myGolfers: number;
  /** You vs the model: true ahead, false behind, null if the model isn't on the slate. */
  aheadOfModel: boolean | null;
};

export type Preset = {
  /** Stable id stored with the chirp (for counting which ones people use). */
  id: string;
  /** The line as sent. Short, no money amounts. */
  text: string;
};

/** Most chips the sheet shows at once. */
export const MAX_PRESETS = 4;

/** The four lines from the roadmap, plus a neutral one that's always true. */
export const LINES = {
  leading: "Don't look now",
  passed: "Check the leaderboard",
  beatModel: "So much for the expert",
  collapse: "There's always next week",
  goodLuck: "Good luck, everyone",
} as const;

// ── TODO(Jack): chirpPresets ──────────────────────────────────────────────────
//
// Return the presets to offer for this context, most fitting first, at most
// MAX_PRESETS. Use the LINES keys as ids (e.g. { id: "leading", text: LINES.leading }).
//
// Facts the tests pin:
//   - Before lock (status "open") nothing has happened yet: only neutral
//     lines (goodLuck), no taunts.
//   - "Don't look now" only when myGolferLeading is set.
//   - "Check the leaderboard" only when you're leading the group (myRank 1)
//     with someone else on the slate (players > 1).
//   - "So much for the expert" only when aheadOfModel is true.
//   - "There's always next week" only when your lineup has collapsed (you
//     decide what "collapsed" means, decision b).
//   - Didn't play (myRank null): nothing to brag about; neutral only.
//   - Never more than MAX_PRESETS; no duplicates; same input, same output.
//
// Decisions that are yours (reason in a comment):
//   a. Order when several are true (leading AND ahead of the model AND your
//      golfer leads): which goes first?
//   b. "Collapsed": all your golfers out? Half? Or last place?
//   c. Tied for first: is "Check the leaderboard" still fair, or does a tie
//      call for something else (or nothing)?
//
// Done when: npm test (from web/) passes lib/chirpPresets.test.ts, plus one
// test of your own for decision (a).

export function chirpPresets(c: ChirpContext): Preset[] {
  
  if (c.status === "open" || c.myRank === null) {
  return [{ id: "goodLuck", text: LINES.goodLuck }];
  }
  const out: Preset[] = []
  // Collapsed means every selected golfer is out
  // Requiring at least one golfer avoids treating 0 out of 0 as collapsed

  const collapsed = c.myGolfers > 0 && c.myGolfersOut === c.myGolfers;
  if (collapsed) {
    out.push({ id: "collapse", text: LINES.collapse });
  }

  // Prioritize the group rivalry over beating the model
  // or having one golfer lead the tournament.
  // Tied leaders can also say "Check the leaderboard":
  // they really are sharing first place.
  if (c.myRank === 1 && c.players > 1) {
    out.push({ id: "passed", text: LINES.passed});
  }

  if (c.aheadOfModel === true) {
    out.push({ id: "beatModel", text: LINES.beatModel });
  }

  if (c.myGolferLeading !== null) {
    out.push({
      id: "leading",
      text: LINES.leading,
    });
  }

  // If no specific chirp fits, still give the player an option.
  if (out.length === 0) {
    out.push({ id: "goodLuck", text: LINES.goodLuck });
  }

  return out.slice(0, MAX_PRESETS);
}
