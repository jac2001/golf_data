/**
 * POST /api/events { event, props? } — a browser-side product event.
 * ===================================================================
 * Only events the browser alone can see (the install card, permission
 * answers). Server-side events (joined_group, pick_made) are recorded
 * by their own routes and are NOT accepted here, so a client can't
 * inflate them. Signed-in only; props are capped and flattened.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { track } from "@/lib/track";

const ALLOWED = new Set([
  "install_card_shown",      // { step, platform }
  "install_card_accepted",   // { step, platform }
  "install_card_dismissed",  // { step, platform, count }
  "reminders_enabled",       // { platform, installed }
  // The weekly scorecard (launch plan, measures 4 and 5):
  "match_viewed",            // { status: live|final|..., group_id } once per visit
  "invite_shared",           // { group_id, via: share|copy }
  "nudge_shared",            // { game, group_id, via: share|copy }
]);

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const event = String(body.event ?? "");
  if (!ALLOWED.has(event)) return Response.json({ error: "unknown event" }, { status: 400 });

  const props: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries((body.props ?? {}) as Record<string, unknown>).slice(0, 8)) {
    if (typeof v === "number" || typeof v === "boolean") props[k.slice(0, 32)] = v;
    else if (typeof v === "string") props[k.slice(0, 32)] = v.slice(0, 64);
  }

  // group_id also goes in its own column (per-group scorecard counts), but
  // only for a group this person is actually in: a client can't attribute
  // activity to someone else's group.
  let groupId: number | null = null;
  const g = Number(props.group_id);
  if (Number.isInteger(g) && g > 0) {
    const m = await getSql()`SELECT 1 FROM group_members WHERE group_id = ${g} AND user_id = ${userId}` as unknown[];
    if (m.length) groupId = g;
  }
  await track(getSql(), userId, event, props, groupId);
  return Response.json({ ok: true });
}
