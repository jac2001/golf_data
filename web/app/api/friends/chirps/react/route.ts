/**
 * POST /api/friends/chirps/react { id, emoji } → { on } — toggle one reaction.
 * Members of the chirp's group only; a fixed small set of reactions.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";
import { track } from "@/lib/track";

const REACTIONS = new Set(["👏", "😂", "🔥", "😬"]);

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? ""), emoji = String(body.emoji ?? "");
  if (!/^\d+$/.test(id) || !REACTIONS.has(emoji)) return Response.json({ error: "id and a known reaction required" }, { status: 400 });

  const sql = getSql();
  const c = await sql`SELECT group_id FROM chirps WHERE id = ${id} AND removed_at IS NULL` as { group_id: number }[];
  if (!c.length) return Response.json({ error: "No such chirp." }, { status: 404 });
  if (!(await visibleUserIds(userId, c[0].group_id))) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  const gone = await sql`DELETE FROM chirp_reactions WHERE chirp_id = ${id} AND user_id = ${userId} AND emoji = ${emoji} RETURNING 1` as unknown[];
  if (gone.length) return Response.json({ on: false });
  await sql`INSERT INTO chirp_reactions (chirp_id, user_id, emoji) VALUES (${id}, ${userId}, ${emoji}) ON CONFLICT DO NOTHING`;
  await track(sql, userId, "chirp_reacted", { emoji }, c[0].group_id);
  return Response.json({ on: true });
}
