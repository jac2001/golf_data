/**
 * resultKey.ts — one way to match a pick to a results row.
 * =========================================================
 * A pick's golfer name comes from our field files (DataGolf spellings:
 * "Ludvig Aberg"); results come from PGA TOUR leaderboards ("Ludvig
 * Åberg"). Matching those with a key that keeps accents, or folding only
 * one side (the recap did), scores a real pick at $0 (audit finding 5).
 * Every scoring view (Match Center, standings, recap, receipt, Round,
 * Fade, College) looks golfers up through resultIndex(), so the same
 * event, member and score mean the same thing everywhere.
 *
 * This is for MATCHING ONLY. Stored player_key values (picks, use
 * budgets) stay on names.ts nameKey; changing those needs a migration.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

// ── TODO(Jack): resultKey ─────────────────────────────────────────────────────
//
// Turn any spelling of a golfer's name into one comparable key.
//
// Facts the tests pin:
//   - Order-free: "Scheffler, Scottie" and "Scottie Scheffler" match.
//   - Case-free.
//   - Accent-free: "Ludvig Åberg" = "Ludvig Aberg", "Nicolás Echavarría" =
//     "Nicolas Echavarria". Some letters don't decompose into a base letter
//     plus an accent and need mapping by hand: ø→o, æ→ae, ß→ss, đ→d, ł→l
//     ("Rasmus Højgaard" = "Rasmus Hojgaard").
//   - Punctuation-free: periods and apostrophes vanish ("J.T. Poston" =
//     "JT Poston", "Sean O'Hair" = "Sean OHair"); a hyphen splits words
//     ("Byeong-Hun An" = "Byeong Hun An").
//   - Suffixes don't count: "Davis Love III" = "Davis Love", "Ted Potter, Jr."
//     = "Potter, Ted" (jr, sr, ii, iii, iv).
//   - Different golfers stay different: Nicolai vs Rasmus Højgaard,
//     Matt vs Alex Fitzpatrick (first names are part of the key).
//   - Empty or whitespace-only names give "".
//
// Hints: str.normalize("NFD") splits "Å" into "A" + a combining mark;
// /[̀-ͯ]/g matches those marks. Do the hand mappings first.

export function resultKey(name: string): string {
  const FOLD: Record<string, string> = { "ø": "o", "æ": "ae", "ß": "ss", "đ": "d", "ł": "l" };
  const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv"]);
  let s = name.toLowerCase();
  s = s.replace(/[øæßđł]/g, ch => FOLD[ch]);
  s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  s = s.replace(/[.']/g, "").replace(/[,-]/g, " ");
  return s
    .split(/\s+/)
    .filter(w => w !== "" && !SUFFIXES.has(w))
    .sort()
    .join(" ");
}

// ── TODO(Jack): resolveResult ─────────────────────────────────────────────────
//
// Find ONE pick's row in a results table. Ids first, names as a fallback,
// and never a guess when a name is shared.
//
// rows: the table as the API sends it (`players` in /api/results/earnings),
//       an object whose values each carry player_name and, when the source
//       has one, player_id:
//       { "johnson zach":       { player_name: "Zach Johnson", player_id: "24024", earnings: 0 },
//         "johnson zach#29747": { player_name: "Zach Johnson", player_id: "29747", earnings: 0 }, ... }
//       Ignore the object's keys (the API builds them its own way).
// pick: { player_name, player_id? }. Picks made since Oct 20, 2026 store the
//       PGA TOUR player_id; older picks and DP World Tour picks have none.
//
// Return one of:
//   { row, via: "id" }        a row whose player_id equals the pick's
//   { row, via: "name" }      no id match, and exactly ONE row has the pick's
//                             resultKey
//   { row: null, reason: "ambiguous" }  no id match, and 2+ rows share the key
//   { row: null, reason: "missing" }    nothing matches (or there's no table)
//
// Facts the tests pin:
//   - An id match wins even when the names are spelled differently.
//   - A pick id the table doesn't have (DataGolf's live board carries no PGA
//     ids) falls back to the name.
//   - Ids compare as text, ignoring leading zeros ("06567" = "6567").
//   - Rows without a player_name never match by name.
//   - null/undefined rows: { row: null, reason: "missing" }.
//
// Why "ambiguous" is its own answer: the view shows that golfer as
// unresolved and the server logs it (lib/resultLookup), instead of scoring a member on
// the wrong man's money. With ids on every new pick it should never fire.

export type ResultRow = { player_name?: string | null; player_id?: string | null };
export type Pick = { player_name: string; player_id?: string | null };
export type Resolved<T> =
  | { row: T; via: "id" | "name" }
  | { row: null; reason: "ambiguous" | "missing" };

export function resolveResult<T extends ResultRow>(
  rows: Record<string, T> | null | undefined, pick: Pick,
): Resolved<T> {
  const all = Object.values(rows ?? {});
  const cleanId = (v?: string | null) => (v ?? "").trim().replace(/^0+/, "");
  const id = cleanId(pick.player_id);
  if (id) {
    const byId = all.find(r => cleanId(r.player_id) === id);
    if (byId) return { row: byId, via: "id" };
  }

  const key = resultKey(pick.player_name)
  const named = key ? all.filter(r => r.player_name && resultKey(r.player_name) === key) : [];
  if (named.length === 1) return { row: named[0], via: "name" };
  if (named.length > 1) return { row: null, reason: "ambiguous" };
  return { row: null, reason: "missing" };
}
