/**
 * /api/friends/groups — play together.
 * =====================================
 * GET    → groups you belong to, with members
 * POST   → create a group { name }  (returns an invite code to share)
 * PUT    → join by code { invite_code }
 * DELETE → leave { group_id }  (owner leaving deletes the group)
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

async function displayName(): Promise<string> {
  const user = await currentUser();
  return user?.firstName ? `${user.firstName} ${user.lastName ?? ""}`.trim()
    : user?.emailAddresses?.[0]?.emailAddress?.split("@")[0] ?? "Player";
}

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const sql = getSql();
  const groups = await sql`
    SELECT g.id, g.name, g.invite_code, g.owner_id
    FROM groups g JOIN group_members m ON m.group_id = g.id
    WHERE m.user_id = ${userId} ORDER BY g.created_at` as
    { id: number; name: string; invite_code: string; owner_id: string }[];

  const ids = groups.map(g => g.id);
  const members = ids.length ? await sql`
    SELECT group_id, user_id, user_name FROM group_members
    WHERE group_id = ANY(${ids}) ORDER BY joined_at` as
    { group_id: number; user_id: string; user_name: string }[] : [];

  return Response.json({
    groups: groups.map(g => ({
      ...g,
      is_owner: g.owner_id === userId,
      members: members.filter(m => m.group_id === g.id)
        .map(m => ({ user_id: m.user_id, user_name: m.user_name })),
    })),
  });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const name = String(body.name ?? "").trim().slice(0, 60);
  if (!name) return Response.json({ error: "Group name required" }, { status: 400 });

  // Unambiguous alphabet — no 0/O or 1/I to squint at in a group chat.
  const code = Array.from({ length: 6 },
    () => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 32)]).join("");

  const sql = getSql();
  const me = await displayName();
  const rows = await sql`
    INSERT INTO groups (name, invite_code, owner_id)
    VALUES (${name}, ${code}, ${userId}) RETURNING id` as { id: number }[];
  await sql`
    INSERT INTO group_members (group_id, user_id, user_name)
    VALUES (${rows[0].id}, ${userId}, ${me})`;
  return Response.json({ id: rows[0].id, name, invite_code: code });
}

export async function PUT(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const code = String(body.invite_code ?? "").trim().toUpperCase();

  const sql = getSql();
  const g = await sql`SELECT id, name FROM groups WHERE invite_code = ${code}` as
    { id: number; name: string }[];
  if (!g.length) return Response.json({ error: "No group with that code." }, { status: 404 });

  const me = await displayName();
  await sql`
    INSERT INTO group_members (group_id, user_id, user_name)
    VALUES (${g[0].id}, ${userId}, ${me})
    ON CONFLICT (group_id, user_id) DO NOTHING`;
  return Response.json({ joined: g[0] });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const groupId = Number(body.group_id);
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });

  const sql = getSql();
  const g = await sql`SELECT owner_id FROM groups WHERE id = ${groupId}` as { owner_id: string }[];
  if (!g.length) return Response.json({ error: "Group not found" }, { status: 404 });

  if (g[0].owner_id === userId) {
    await sql`DELETE FROM groups WHERE id = ${groupId}`;  // cascades to members
    return Response.json({ deleted: true });
  }
  await sql`DELETE FROM group_members WHERE group_id = ${groupId} AND user_id = ${userId}`;
  return Response.json({ left: true });
}
