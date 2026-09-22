/**
 * POST /api/friends/reminders/test — push a hello to THIS account's
 * devices only. The public ?test=1 on reminders-cron blasts every
 * subscriber (fine with two devices, obnoxious at twenty); this is
 * the settings page's scoped version.
 */

import webpush from "web-push";
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

export const runtime = "nodejs";

export async function POST() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const pub = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const priv = process.env.VAPID_PRIVATE_KEY;
  if (!pub || !priv) return Response.json({ error: "VAPID keys not configured" }, { status: 500 });
  webpush.setVapidDetails(process.env.VAPID_SUBJECT ?? "mailto:admin@playgolfedge.com", pub, priv);

  const sql = getSql();
  const subs = await sql`
    SELECT endpoint, p256dh, auth FROM push_subscriptions
    WHERE user_id = ${userId}` as { endpoint: string; p256dh: string; auth: string }[];
  if (subs.length === 0) return Response.json({ sent: 0, removed: 0 });

  let sent = 0, removed = 0;
  for (const sub of subs) {
    try {
      await webpush.sendNotification(
        { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
        JSON.stringify({ title: "Golf Edge", body: "Reminders are working on this device.", url: "/friends" }),
      );
      sent += 1;
    } catch (e) {
      const code = (e as { statusCode?: number }).statusCode;
      if (code === 404 || code === 410) {
        await sql`DELETE FROM push_subscriptions WHERE endpoint = ${sub.endpoint}`;
        removed += 1;
      }
    }
  }
  return Response.json({ sent, removed });
}
