/**
 * Site admins: who reviews what a group's owner can't fairly review (a
 * report about the owner's own chirp). User ids aren't secrets; keeping
 * the list in code means it's reviewed like any other change.
 */
export const ADMIN_USER_IDS: readonly string[] = [
  "user_3JSk7qFVfXHrIY9JVjh1xCEXVGd",   // Jack (jack123), decided 2026-10-20
];

export const isAdmin = (userId: string | null | undefined): boolean =>
  !!userId && ADMIN_USER_IDS.includes(userId);
