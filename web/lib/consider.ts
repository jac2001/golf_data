/**
 * consider.ts — "Consider for my picks": research -> the pick screen.
 * ====================================================================
 * This Week links a golfer to /friends?game=ride&tid=R2026528&consider=<name>.
 * The pick screen opens on that event with the golfer in the search box and
 * his spend/save advice open. Nothing is ever submitted: the member still
 * taps Pick.
 *
 * The name comes from a URL, so anyone can type anything into it. This
 * file decides which golfer in THIS event's field, if any, it means.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */
import { resultKey } from "./resultKey.ts";

// ── resolveConsider ───────────────────────────────────────────────
//
// raw:   the ?consider= value, already URL-decoded by URLSearchParams
//        (null when the link has none).
// field: the event's field as the pick screen shows it ("Ludvig Åberg").
//
// Return the FIELD's spelling of the golfer the link names, or null.
//
// Facts the tests pin:
//   - Any spelling resultKey treats as the same golfer finds him
//     ("Aberg, Ludvig" -> "Ludvig Åberg"). Reuse your resultKey.
//   - Not in this field -> null (a link from last week, a typo).
//   - Never a guess: if 2+ field names share the key, null.
//   - null, empty or whitespace-only -> null.
//   - Junk guard: longer than 80 characters -> null (it's a URL; real
//     golfer names are far shorter).
//   - Return the field's own string, not the raw one: the pick screen
//     searches and picks by the field's spelling.
//
// Why null and not an error: a bad link should still open the pick
// screen, just without a golfer pre-filled.

export function resolveConsider(raw: string | null | undefined, field: readonly string[]): string | null {
  if (raw == null || raw.trim() === "" || raw.length > 80) {
    return null;
  }
  const key = resultKey(raw);

  if (!key) return null;
  const matches = field.filter(name => resultKey(name) === key);
  return matches.length === 1 ? matches[0] : null;
}

/** The link This Week puts on a golfer. Plumbing (Claude's). */
export function considerHref(name: string, tournamentId?: string | null): string {
  const q = new URLSearchParams({ game: "ride" });
  if (tournamentId) q.set("tid", tournamentId.toUpperCase());
  q.set("consider", name);
  return `/friends?${q.toString()}`;
}
