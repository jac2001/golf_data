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

type ClerkUser = Awaited<ReturnType<typeof currentUser>>;

export function nameOf(user: ClerkUser): string {
  if (!user) return "Player";
  return user.username
    || (user.firstName ? `${user.firstName} ${user.lastName ?? ""}`.trim() : "")
    || user.emailAddresses?.[0]?.emailAddress?.split("@")[0]
    || "Player";
}

type Sql = (strings: TemplateStringsArray, ...values: unknown[]) => Promise<unknown>;

export async function syncStoredNames(sql: Sql, userId: string, name: string): Promise<void> {
  try {
    await sql`UPDATE group_members SET user_name = ${name} WHERE user_id = ${userId} AND user_name <> ${name}`;
    await sql`UPDATE picks SET user_name = ${name} WHERE user_id = ${userId} AND user_name <> ${name}`;
    await sql`UPDATE user_bets SET user_name = ${name} WHERE user_id = ${userId} AND user_name <> ${name}`;
    await sql`UPDATE tailed_bets SET user_name = ${name} WHERE user_id = ${userId} AND user_name <> ${name}`;
  } catch { /* cosmetic sync — never block the request over it */ }
}
