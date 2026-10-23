/**
 * displayName — one rule for what to call a user, everywhere.
 * ============================================================
 * Preference order: chosen username > first name > email prefix.
 * Rows store the name at write time (denormalized for cheap reads), so
 * syncStoredNames refreshes what's already in the tables whenever we
 * notice the current name differs — names catch up lazily on the next
 * visit instead of needing a migration per rename.
 */

import { currentUser } from "@clerk/nextjs/server";
import { memberName } from "./memberName";

type ClerkUser = Awaited<ReturnType<typeof currentUser>>;

export function nameOf(user: ClerkUser): string {
  return memberName(user && {
    firstName: user.firstName, lastName: user.lastName, username: user.username,
    email: user.emailAddresses?.[0]?.emailAddress,

  });
}

type Sql = (strings: TemplateStringsArray, ...values: unknown[]) => Promise<unknown>;
const NAME_TABLES = ["group_members", "league_picks", "round_picks", "fade_picks",
  "college_picks", "chirps", "invite_joins", "user_bets", "tailed_bets"] as const;
export async function syncStoredNames(sql: Sql, userId: string, name: string): Promise<void> {
  for (const t of NAME_TABLES) {
    try {   // one try per table: one missing table can't stop the rest
      await (sql as unknown as { query: (q: string, p: unknown[]) => Promise<unknown> })
        .query(`UPDATE ${t} SET user_name = $1 WHERE user_id = $2 AND user_name <> $1`, [name, userId]);
    } catch { /* cosmetic sync — never block the request */ }
  }
}