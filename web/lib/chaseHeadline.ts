/**
 * chaseHeadline.ts — the Match Center headline when you're NOT leading.
 * ======================================================================
 * The old line named your RIVAL as if they led: "You're 4th.
 * jacklegnon+invite2 leads you by $514,211." while Rick was 1st at $1.24M
 * (Oct 23). A new player reads that as "the rival is winning." This says
 * where you stand out of how many, and who actually leads, by how much.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

import { money, ordinal } from "./matchTypes.ts";

/** One row of the group board (Match Center's Line, minus the golfers). */
export type Standing = { user_id: string; user_name: string; total: number; rank: number };

// ── TODO(Jack): chaseHeadline ────────────────────────────────────────────────
//
// chaseHeadline(lines, meId, final) -> the headline, or null.
//
// Return null when it isn't your case: you're not on the board, or you're
// ranked 1st (leading or tied for the lead has its own wording already).
//
// Otherwise two sentences: WHERE YOU ARE, then WHO LEADS.
//
//   Where you are  (N = everyone on the board, The Model included)
//     live:   "You're 4th of 4."          tied: "You're tied for 2nd of 4."
//     final:  "You finished 4th of 4."    tied: "You finished tied for 2nd of 4."
//     (you're tied when someone else has your rank)
//
//   Who leads  (the gap is the leader's total minus yours, via money())
//     one leader      live: "Rick leads by $1.22M."
//                     final: "Rick won by $1.22M."
//     two tied        live: "Rick and Sam lead by $X."
//                     final: "Rick and Sam shared the win, $X ahead."
//     three or more   live: "3 players share the lead, $X ahead."
//                     final: "3 players shared the win, $X ahead."
//   Leaders' names in board order (the order of `lines`).
//
// Use the imported ordinal() for "4th" and money() for the gap.
// Hint: find me, then the leaders (rank 1), then build the two halves.

export function chaseHeadline(lines: readonly Standing[], meId: string, final: boolean): string | null {
  void lines; void meId; void final;
  throw new Error("TODO(Jack): chaseHeadline");
}
