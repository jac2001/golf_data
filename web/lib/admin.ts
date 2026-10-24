/**
 * Site admins: who reviews what a group's owner can't fairly review (a
 * report about the owner's own chirp). User ids aren't secrets; keeping
 * the list in code means it's reviewed like any other change.
 */
export const ADMIN_USER_IDS: readonly string[] = [
  "user_3JSk7qFVfXHrIY9JVjh1xCEXVGd",   // Jack (jack123), decided 2026-10-20
];

/** Jack's own test logins: real accounts, not players. Left out of the pilot
 *  scorecard (with admins) so its counts are real people only. */
export const TEST_USER_IDS: readonly string[] = [
  "user_3KkCgOQKv7yWVkrnAkyrEM0DLNb",   // jacklegnon+invite1, decided 2026-10-23
  "user_3KkPlnlARnhrrPNZ3fpPouzUzRf",   // jacklegnon+invite2, decided 2026-10-23
];

export const isAdmin = (userId: string | null | undefined): boolean =>
  !!userId && ADMIN_USER_IDS.includes(userId);
