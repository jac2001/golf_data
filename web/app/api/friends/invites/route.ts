/**
 * /api/friends/invites — one-tap invite links for a group.
 * =========================================================
 * POST   { group_id }        → create a link (any member). Returns the URL.
 * GET    ?group_id=          → the group's links, with who joined through
 *                              each (members see all links; decision A).
 * DELETE { link_id }         → revoke (the group's owner, or the link's creator)
 *
 * Rules (expiry, max uses, revoke) live in lib/inviteRules.ts (Jack).
 * The join itself is /api/join/[token].
 */

import { randomBytes } from "node:crypto";
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { INVITE_MAX_USES, inviteExpiry } from "@/lib/inviteRules";

type Sql = ReturnType<typeof getSql>;

async function isMember(sql: Sql, groupId: number, userId: string): Promise<boolean> {
  const r = await sql`SELECT 1 FROM group_members WHERE group_id = ${groupId} AND user_id = ${userId}` as unknown[];
  return r.length > 0;
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const groupId = Number(body.group_id);
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });

  const sql = getSql();
  if (!(await isMember(sql, groupId, userId)))
    return Response.json({ error: "Not a member of that group" }, { status: 403 });

  // 128 random bits, URL-safe: unguessable, so the link itself is the key.
  const token = randomBytes(16).toString("base64url");
  const expires = inviteExpiry(new Date());
  await sql`
    INSERT INTO invite_links (token, group_id, created_by, expires_at, max_uses)
    VALUES (${token}, ${groupId}, ${userId}, ${expires.toISOString()}, ${INVITE_MAX_USES})`;
  const origin = new URL(req.url).origin;
  return Response.json({ url: `${origin}/join/${token}`, expires_at: expires.toISOString(), max_uses: INVITE_MAX_USES });
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const groupId = Number(new URL(req.url).searchParams.get("group_id"));
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });

  const sql = getSql();
  if (!(await isMember(sql, groupId, userId)))
    return Response.json({ error: "Not a member of that group" }, { status: 403 });

  const links = await sql`
    SELECT l.id, l.token, l.created_by, l.created_at, l.expires_at, l.max_uses, l.uses, l.revoked_at,
           COALESCE(m.user_name, 'Someone') AS created_by_name
    FROM invite_links l
    LEFT JOIN group_members m ON m.group_id = l.group_id AND m.user_id = l.created_by
    WHERE l.group_id = ${groupId} ORDER BY l.created_at DESC` as {
      id: number; token: string; created_by: string; created_at: string; expires_at: string;
      max_uses: number; uses: number; revoked_at: string | null; created_by_name: string }[];
  const ids = links.map(l => l.id);
  const joins = ids.length ? await sql`
    SELECT link_id, user_name, joined_at FROM invite_joins
    WHERE link_id = ANY(${ids}) ORDER BY joined_at` as { link_id: number; user_name: string; joined_at: string }[] : [];

  const origin = new URL(req.url).origin;
  return Response.json({
    links: links.map(l => ({
      id: l.id, url: `${origin}/join/${l.token}`, created_by_name: l.created_by_name,
      created_at: l.created_at, expires_at: l.expires_at, max_uses: l.max_uses, uses: l.uses,
      revoked: l.revoked_at !== null, mine: l.created_by === userId,
      joined: joins.filter(j => j.link_id === l.id).map(j => ({ name: j.user_name, at: j.joined_at })),
    })),
  });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const linkId = Number(body.link_id);
  if (!linkId) return Response.json({ error: "link_id required" }, { status: 400 });

  const sql = getSql();
  // Owner of the group, or whoever created the link — in one statement, so
  // a non-owner can't revoke someone else's link.
  const r = await sql`
    UPDATE invite_links l SET revoked_at = now()
    FROM groups g
    WHERE l.id = ${linkId} AND g.id = l.group_id AND l.revoked_at IS NULL
      AND (g.owner_id = ${userId} OR l.created_by = ${userId})
    RETURNING l.id` as { id: number }[];
  if (!r.length) return Response.json({ error: "Not found, already revoked, or not yours to revoke" }, { status: 404 });
  return Response.json({ revoked: linkId });
}
