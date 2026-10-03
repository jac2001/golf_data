/**
 * DELETE /api/account — the signed-in user deletes their account.
 * Body: {confirm: "DELETE"} (typed by the user; guards against a stray click).
 *
 * What happens (matches /privacy):
 *   deleted     — notification devices + their reminder log, preferences,
 *                 personal bet log and tails, legacy Weekly 3 picks,
 *                 group memberships, picks in events that haven't locked
 *   anonymized  — picks in locked/finished events become "Former player"
 *                 under one opaque id, so friends' past standings, stars
 *                 and recaps still add up
 *   groups      — owned groups pass to the longest-standing other member;
 *                 a group with no one else is deleted with its seasons
 *   Clerk       — the sign-in account itself, last
 *
 * The database work is one transaction. If the Clerk call fails after it,
 * the user's data is already gone and a retry finishes the job.
 */
import { auth, clerkClient } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { openEventLocks } from "@/lib/eventLocks";
import { purgeUserData } from "@/lib/accountPurge";

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  if (body.confirm !== "DELETE") {
    return Response.json({ error: 'Type DELETE to confirm' }, { status: 400 });
  }

  // Unlocked events: picks there are just deleted (nobody has seen them).
  // If the list can't load, treat nothing as unlocked → everything is
  // anonymized, never wrongly deleted out of a finished week.
  const locks = await openEventLocks();
  const unlocked = locks ? [...locks].filter(([, locked]) => !locked).map(([tid]) => tid) : [];
  const anon = `deleted:${crypto.randomUUID()}`;

  await purgeUserData(getSql(), userId, unlocked, anon);

  try {
    await (await clerkClient()).users.deleteUser(userId);
  } catch {
    return Response.json({ error: "Your data was deleted, but the sign-in account wasn't. Try again in a minute." }, { status: 502 });
  }
  return Response.json({ ok: true });
}
