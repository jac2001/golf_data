/**
 * resultLookup.ts: the one lookup every scoring view uses.
 * =========================================================
 * Wraps Jack's resolveResult (lib/resultKey.ts: id first, then a unique
 * name, never a guess) and returns the row or undefined, so a view keeps
 * its "?? 0" fallback. An ambiguous pick (a shared name with no player_id)
 * is logged so it can't fail silently; it scores nothing rather than the
 * wrong golfer's money.
 */
import { resolveResult, type Pick, type ResultRow } from "./resultKey";

export function lookupResult<T extends ResultRow>(
  rows: Record<string, T> | null | undefined, pick: Pick, where: string,
): T | undefined {
  const r = resolveResult(rows, pick);
  if (!("reason" in r)) return r.row;
  if (r.reason === "ambiguous") {
    console.warn(`[results] ${where}: "${pick.player_name}" matches 2+ golfers and the pick has no player_id; left unscored`);
  }
  return undefined;
}
