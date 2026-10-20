/**
 * POST /api/friends/chirps/report { id, reason? } → { reported } — flag a chirp.
 * Members of the chirp's group only. The group owner can then remove it
 * (DELETE /api/friends/chirps); reports are kept for review.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";
import { track } from "@/lib/track";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  const reason = String(body.reason ?? "").slice(0, 200);
  if (!/^\d+$/.test(id)) return Response.json({ error: "id required" }, { status: 400 });

  const sql = getSql();
  const c = await sql`SELECT group_id FROM chirps WHERE id = ${id}` as { group_id: number }[];
  if (!c.length) return Response.json({ error: "No such chirp." }, { status: 404 });
  if (!(await visibleUserIds(userId, c[0].group_id))) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  await sql`INSERT INTO chirp_reports (chirp_id, user_id, reason) VALUES (${id}, ${userId}, ${reason})`;
  await track(sql, userId, "chirp_reported", {}, c[0].group_id);
  return Response.json({ reported: true });
}
