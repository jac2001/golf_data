/**
 * pickReason.ts — why The Model picked a golfer, in words a member reads.
 * ========================================================================
 * The saved reasons were spend/save advice, money only, and could argue
 * against the pick: Ben Kohles (Bermuda, Oct 20) was picked with the
 * reason "$110K now vs $117K at The American Express — save." This says
 * the GOLFER case first, then where this week ranks among his best events.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

import type { FutureWindow } from "./advice.ts";

export type PickReasonInput = {
  /** This week's published win chance, 0..1. null = unknown. */
  winProb: number | null;
  /** 1 = the model's highest win chance in the field this week. */
  winRank: number | null;
  /** Jack's whyLine for him ("Made the cut at this event 3 of 3 times"), or null. */
  why: string | null;
  /** Expected lineup earnings this week, in dollars. */
  nowEv: number;
  /** The model's uses left on him BEFORE this pick (1 or more). */
  usesLeft: number;
  /** His upcoming events where he'd realistically get picked, any order. */
  future: readonly FutureWindow[];
};

export const k = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v / 1000)}K`;

// ── TODO(Jack): modelPickReason ──────────────────────────────────────────────
//
// modelPickReason(input) -> "<golfer case> <timing>" (or just the timing).
//
// 1. The golfer case (first; skip it when there's nothing to say):
//      winRank 1 and a win chance  -> "Model's top pick: about a 1 in N chance to win."
//      otherwise a why line        -> the why line, plus "."
//      otherwise a win chance      -> "About a 1 in N chance to win."
//    N = Math.round(1 / winProb). A win chance of null or <= 0 counts as none.
//
// 2. The timing: where THIS week ranks among his events. Put nowEv and every
//    future ev in one list, highest first; rank = this week's place (1 = best;
//    a tie with a future event counts as this week being ahead).
//      rank 1, no future events   -> "His best event left: about $114K expected."
//      rank 1                      -> "His best event left: about $127K expected, ahead of WM Phoenix Open ($122K)."
//                                     (the next-best future event)
//      rank <= usesLeft            -> "One of his 3 best events left: about $125K expected (best: $131K at Cognizant Classic)."
//                                     (3 = usesLeft; best = his top future event)
//      rank > usesLeft             -> "Worth more at The American Express ($117K), but still one of this week's best uses."
//                                     (the future event at position usesLeft: the use this pick gives up)
//    Money with k(): 127_000 -> "$127K".
//
// Joined with one space. Hint: build the two parts separately, then join.

export function modelPickReason(input: PickReasonInput): string {
  void input;
  throw new Error("TODO(Jack): modelPickReason");
}
