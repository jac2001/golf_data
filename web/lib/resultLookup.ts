/**
 * resultLookup.ts: the one lookup every scoring view uses.
 * =========================================================
 * Wraps Jack's resolveResult (lib/resultKey.ts: id first, then a unique
 * name, never a guess). An AMBIGUOUS pick (a shared name with no
 * player_id; every DP World Tour pick, which has no ids) is neither a
 * golfer who earned $0 nor a missing one: resolvePick says so, the view
 * shows that golfer as UNRESOLVED_POS and flags the total incomplete, and
 * the server logs it. Until Oct 21 this collapsed to undefined and every
 * view's "?? 0" scored it as $0 (audit).
 */
import { resolveResult, type Pick, type ResultRow } from "./resultKey.ts";

/** The position label a view shows for an unresolved golfer (fits the 40px column). */
export const UNRESOLVED_POS = "?";

export type Lookup<T> = { hit: T | undefined; unresolved: boolean };

export function resolvePick<T extends ResultRow>(
  rows: Record<string, T> | null | undefined, pick: Pick, where: string,
): Lookup<T> {
  const r = resolveResult(rows, pick);
  if (!("reason" in r)) return { hit: r.row, unresolved: false };
  if (r.reason === "ambiguous") {
    console.warn(`[results] ${where}: "${pick.player_name}" matches 2+ golfers and the pick has no player_id; shown as unresolved`);
    return { hit: undefined, unresolved: true };
  }
  return { hit: undefined, unresolved: false };
}

/** The row or undefined, for views that score nothing (how-to-play's demo). */
export function lookupResult<T extends ResultRow>(
  rows: Record<string, T> | null | undefined, pick: Pick, where: string,
): T | undefined {
  return resolvePick(rows, pick, where).hit;
}
