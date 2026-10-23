/**
 * memberName.ts — what a friend group sees you called.
 * =====================================================
 * Boards showed "rick legnon", "jack123" and "jacklegnon+invite2": the
 * raw Clerk username, a lowercase first/last name, or an email prefix.
 * Friends know each other by name, so a real name wins, tidied up.
 *
 * Order: first + last name > username > email prefix > "Player".
 *   - Names typed all lowercase are capitalized ("rick legnon" -> "Rick Legnon");
 *     anything with a capital is left as typed ("McIlroy", "DeChambeau").
 *   - A username is the person's own choice: kept exactly.
 *   - An email prefix loses its "+tag" and turns . _ - into spaces
 *     ("jack.legnon+golf" -> "Jack Legnon").
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type NameSource = {
  firstName?: string | null;
  lastName?: string | null;
  username?: string | null;
  email?: string | null;
};

const squash = (s: string) => s.replace(/\s+/g, " ").trim();

/** Capitalize each word, but only when the whole thing was typed lowercase. */
function tidyCase(s: string): string {
  if (s !== s.toLowerCase()) return s;
  return s.replace(/(^|[\s'-])(\p{L})/gu, (_, sep: string, ch: string) => sep + ch.toUpperCase());
}

export function memberName(src: NameSource | null | undefined): string {
  if (!src) return "Player";
  const full = squash(`${src.firstName ?? ""} ${src.lastName ?? ""}`);
  if (full) return tidyCase(full);
  const user = squash(src.username ?? "");
  if (user) return user;
  const prefix = squash((src.email ?? "").split("@")[0].split("+")[0].replace(/[._-]+/g, " "));
  if (prefix) return tidyCase(prefix);
  return "Player";
}
