/**
 * /api/friends/reminders — push-reminder subscriptions.
 * ======================================================
 * POST   { subscription } → save this browser's push endpoint
 * DELETE { endpoint }     → forget it
 *
 * A subscription is PER BROWSER, not per account: the endpoint is the
 * push service's address for one installed app on one device, so a
 * user with a phone and a laptop has two rows. The endpoint's UNIQUE
 * constraint makes re-subscribing idempotent (upsert refreshes keys).
 * Delivery happens in /api/reminders-cron.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

type Sub = { endpoint: string; keys: { p256dh: string; auth: string } };

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const sub = body.subscription as Sub | undefined;
  if (!sub?.endpoint || !sub.keys?.p256dh || !sub.keys?.auth) {
    return Response.json({ error: "subscription with endpoint and keys required" }, { status: 400 });
  }

  const sql = getSql();
  await sql`
    INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
    VALUES (${userId}, ${sub.endpoint}, ${sub.keys.p256dh}, ${sub.keys.auth})
    ON CONFLICT (endpoint) DO UPDATE
    SET user_id = ${userId}, p256dh = ${sub.keys.p256dh}, auth = ${sub.keys.auth}`;
  return Response.json({ ok: true });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const endpoint = String(body.endpoint ?? "");
  if (!endpoint) return Response.json({ error: "endpoint required" }, { status: 400 });

  const sql = getSql();
  await sql`DELETE FROM push_subscriptions WHERE endpoint = ${endpoint} AND user_id = ${userId}`;
  return Response.json({ ok: true });
}
