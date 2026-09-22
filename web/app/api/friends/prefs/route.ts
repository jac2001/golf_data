/**
 * /api/friends/prefs — per-account preferences.
 * ==============================================
 * GET → { remind_weekly, remind_fades } (defaults true when unset)
 * PUT { remind_weekly?, remind_fades? } → upsert
 *
 * Per ACCOUNT, unlike push subscriptions (per browser): turning off
 * fade reminders silences them on every device at once, which is what
 * a person means when they flip that switch. reminders-cron reads
 * these before nudging.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

const DEFAULTS = { remind_weekly: true, remind_fades: true };

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const sql = getSql();
  const rows = await sql`
    SELECT remind_weekly, remind_fades FROM user_prefs WHERE user_id = ${userId}` as
    { remind_weekly: boolean; remind_fades: boolean }[];
  return Response.json(rows[0] ?? DEFAULTS);
}

export async function PUT(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const sql = getSql();
  const cur = (await sql`
    SELECT remind_weekly, remind_fades FROM user_prefs WHERE user_id = ${userId}` as
    { remind_weekly: boolean; remind_fades: boolean }[])[0] ?? DEFAULTS;

  const weekly = typeof body.remind_weekly === "boolean" ? body.remind_weekly : cur.remind_weekly;
  const fades = typeof body.remind_fades === "boolean" ? body.remind_fades : cur.remind_fades;

  await sql`
    INSERT INTO user_prefs (user_id, remind_weekly, remind_fades, updated_at)
    VALUES (${userId}, ${weekly}, ${fades}, now())
    ON CONFLICT (user_id) DO UPDATE
    SET remind_weekly = ${weekly}, remind_fades = ${fades}, updated_at = now()`;
  return Response.json({ remind_weekly: weekly, remind_fades: fades });
}
