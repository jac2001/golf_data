/**
 * /api/join/[token] — open and accept a one-tap invite.
 * ======================================================
 * GET  (public, no sign-in): what the invite page shows BEFORE sign-in.
 *      Decision B: the group's name and the inviter's first name only.
 *      No members, no picks.
 * POST (signed in): join. The rules decide the message (lib/inviteRules.ts,
 *      Jack); the guarded UPDATE below is what actually enforces expiry,
 *      revoke and max uses, atomically, so two friends tapping at once
 *      can't push a link past its limit.
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { nameOf } from "@/lib/displayName";
import { inviteMessage, inviteStatus } from "@/lib/inviteRules";
import { track } from "@/lib/track";

type Sql = ReturnType<typeof getSql>;
type LinkRow = {
  id: number; group_id: number; group_name: string; created_by: string; inviter_name: string | null;
  expires_at: string; max_uses: number; uses: number; revoked_at: string | null;
};

async function loadLink(sql: Sql, token: string): Promise<LinkRow | null> {
  const r = await sql`
    SELECT l.id, l.group_id, g.name AS group_name, l.created_by, m.user_name AS inviter_name,
           l.expires_at, l.max_uses, l.uses, l.revoked_at
    FROM invite_links l
    JOIN groups g ON g.id = l.group_id
    LEFT JOIN group_members m ON m.group_id = l.group_id AND m.user_id = l.created_by
    WHERE l.token = ${token}` as LinkRow[];
  return r[0] ?? null;
}

function asRule(l: LinkRow) {
  return { expires_at: new Date(l.expires_at), max_uses: l.max_uses, uses: l.uses,
           revoked_at: l.revoked_at ? new Date(l.revoked_at) : null };
}

const firstName = (n: string | null) => (n ?? "A friend").trim().split(/\s+/)[0] || "A friend";

async function memberOf(sql: Sql, groupId: number, userId: string | null): Promise<boolean> {
  if (!userId) return false;
  const r = await sql`SELECT 1 FROM group_members WHERE group_id = ${groupId} AND user_id = ${userId}` as unknown[];
  return r.length > 0;
}

export async function GET(_req: Request, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const sql = getSql();
  const link = await loadLink(sql, token);
  if (!link) return Response.json({ error: "This invite link doesn't exist." }, { status: 404 });

  const { userId } = await auth();
  const status = inviteStatus(asRule(link), new Date(), await memberOf(sql, link.group_id, userId));
  await track(sql, userId, "invite_opened", { link_id: link.id, status }, link.group_id);
  return Response.json({
    group_name: link.group_name,
    inviter: firstName(link.inviter_name),
    status,
    message: inviteMessage(status, link.group_name),
    group_id: status === "already_member" ? link.group_id : undefined,
  }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(_req: Request, { params }: { params: Promise<{ token: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in to join." }, { status: 401 });
  const { token } = await params;
  const sql = getSql();
  const link = await loadLink(sql, token);
  if (!link) return Response.json({ error: "This invite link doesn't exist." }, { status: 404 });

  if (await memberOf(sql, link.group_id, userId))
    return Response.json({ joined: link.group_id, status: "already_member",
                           message: inviteMessage("already_member", link.group_name) });

  // The enforcement: count this use only if the link is still valid AT
  // THIS INSTANT. One statement, so concurrent taps can't both take the
  // 20th seat.
  const claimed = await sql`
    UPDATE invite_links SET uses = uses + 1
    WHERE id = ${link.id} AND revoked_at IS NULL AND expires_at > now() AND uses < max_uses
    RETURNING id` as { id: number }[];
  if (!claimed.length) {
    const fresh = (await loadLink(sql, token)) ?? link;
    const status = inviteStatus(asRule(fresh), new Date(), false);
    return Response.json({ status, message: inviteMessage(status, link.group_name) }, { status: 409 });
  }

  const me = nameOf(await currentUser());
  await sql`
    INSERT INTO group_members (group_id, user_id, user_name)
    VALUES (${link.group_id}, ${userId}, ${me})
    ON CONFLICT (group_id, user_id) DO NOTHING`;
  await sql`
    INSERT INTO invite_joins (link_id, user_id, user_name) VALUES (${link.id}, ${userId}, ${me})
    ON CONFLICT (link_id, user_id) DO NOTHING`;
  await track(sql, userId, "joined_group", { source: "link", link_id: link.id }, link.group_id);
  return Response.json({ joined: link.group_id, status: "ok" });
}
