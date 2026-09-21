/**
 * /api/reminders-cron — the Thursday nudge.
 * ==========================================
 * Daily Vercel Cron. For every open, unlocked event starting within
 * the next 40 hours, look at each subscribed browser's user and push
 * one notification per event listing what they're missing (weekly
 * picks, fades). reminders_sent's UNIQUE(endpoint, tournament_id)
 * makes the cron idempotent — nobody gets nagged twice for the same
 * event, however many times this runs.
 *
 * Lives OUTSIDE /api/friends so Clerk doesn't gate the cron (same as
 * model-sync); a push endpoint the service reports dead (404/410) is
 * deleted on the spot.
 */

import webpush from "web-push";
import { getSql, MODEL_API } from "@/lib/db";

export const runtime = "nodejs";

const WINDOW_H = 40;

type OpenEvent = {
  tournament_id: string; name: string; start_date: string;
  locked: boolean; has_model: boolean;
};
type SubRow = { user_id: string; endpoint: string; p256dh: string; auth: string };

export async function GET(req: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret && req.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  const pub = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const priv = process.env.VAPID_PRIVATE_KEY;
  if (!pub || !priv) return Response.json({ error: "VAPID keys not configured" }, { status: 500 });
  webpush.setVapidDetails(process.env.VAPID_SUBJECT ?? "mailto:admin@playgolfedge.com", pub, priv);

  const sqlEarly = getSql();

  // ?test=1 — pushes a hello to every subscription so a fresh device
  // can be verified without waiting for a real lock window. No dedupe
  // on purpose: a test should always arrive.
  if (new URL(req.url).searchParams.get("test")) {
    const subs = await sqlEarly`
      SELECT user_id, endpoint, p256dh, auth FROM push_subscriptions` as SubRow[];
    const log: string[] = [];
    for (const sub of subs) {
      try {
        await webpush.sendNotification(
          { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
          JSON.stringify({ title: "Golf Edge", body: "Reminders are working on this device.", url: "/friends" }),
        );
        log.push(`test pushed to ${sub.user_id}`);
      } catch (e) {
        log.push(`test failed for ${sub.user_id} (${(e as { statusCode?: number }).statusCode ?? "unknown"})`);
      }
    }
    return Response.json({ ok: true, log: log.length ? log : ["no subscribers yet"] });
  }

  let events: OpenEvent[] = [];
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { cache: "no-store" });
    if (res.ok) events = (await res.json()).events ?? [];
  } catch { /* nothing to remind about */ }

  const soon = events.filter(e => {
    if (e.locked) return false;
    const start = new Date(`${String(e.start_date).slice(0, 10)}T00:00:00`).getTime();
    const hours = (start - Date.now()) / 3_600_000;
    return hours > 0 && hours <= WINDOW_H;
  });
  if (soon.length === 0) return Response.json({ ok: true, log: ["no events locking soon"] });

  const sql = getSql();
  const subs = await sql`
    SELECT user_id, endpoint, p256dh, auth FROM push_subscriptions` as SubRow[];
  if (subs.length === 0) return Response.json({ ok: true, log: ["no subscribers"] });

  const log: string[] = [];
  for (const ev of soon) {
    const tid = ev.tournament_id.toUpperCase();
    const picks = await sql`
      SELECT user_id, count(*)::int AS n FROM picks
      WHERE tournament_id = ${tid} GROUP BY user_id` as { user_id: string; n: number }[];
    const fades = await sql`
      SELECT user_id, count(*)::int AS n FROM fade_picks
      WHERE tournament_id = ${tid} GROUP BY user_id` as { user_id: string; n: number }[];
    const nPicks = new Map(picks.map(r => [r.user_id, r.n]));
    const nFades = new Map(fades.map(r => [r.user_id, r.n]));

    for (const sub of subs) {
      const missing: string[] = [];
      const p = nPicks.get(sub.user_id) ?? 0;
      if (p < 3) missing.push(`${3 - p} pick${3 - p === 1 ? "" : "s"}`);
      if (ev.has_model) {
        const f = nFades.get(sub.user_id) ?? 0;
        if (f < 3) missing.push(`${3 - f} fade${3 - f === 1 ? "" : "s"}`);
      }
      if (missing.length === 0) continue;

      // Claim the send before doing it — an empty RETURNING means some
      // earlier run already got here for this endpoint + event.
      const claim = await sql`
        INSERT INTO reminders_sent (endpoint, tournament_id)
        VALUES (${sub.endpoint}, ${tid})
        ON CONFLICT DO NOTHING RETURNING 1` as unknown[];
      if (claim.length === 0) continue;

      try {
        await webpush.sendNotification(
          { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
          JSON.stringify({
            title: `${ev.name} locks soon`,
            body: `You still need ${missing.join(" and ")} — tee-off is coming.`,
            url: "/friends",
          }),
        );
        log.push(`${tid}: pushed to ${sub.user_id} (${missing.join(", ")})`);
      } catch (e) {
        const code = (e as { statusCode?: number }).statusCode;
        if (code === 404 || code === 410) {
          await sql`DELETE FROM push_subscriptions WHERE endpoint = ${sub.endpoint}`;
          log.push(`${tid}: dead endpoint removed for ${sub.user_id}`);
        } else {
          log.push(`${tid}: push failed for ${sub.user_id} (${code ?? "unknown"})`);
        }
      }
    }
  }

  return Response.json({ ok: true, log });
}
