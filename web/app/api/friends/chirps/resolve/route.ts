/**
 * POST /api/friends/chirps/resolve { id, action: "dismiss" | "remove" } → { resolved }
 * ====================================================================================
 * The review of reports on a chirp (review item 8). The group's owner
 * reviews reports on OTHER members' chirps; a report about the owner's own
 * chirp goes to a site admin (lib/admin.ts). "remove" also removes the
 * chirp; either way every open report on it is marked resolved.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { track } from "@/lib/track";
import { isAdmin } from "@/lib/admin";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  const action = body.action === "remove" ? "remove" : body.action === "dismiss" ? "dismiss" : null;
  if (!/^\d+$/.test(id) || !action) return Response.json({ error: "id and action (dismiss|remove) required" }, { status: 400 });

  const sql = getSql();
  const row = await sql`SELECT c.group_id, c.user_id AS author, g.owner_id FROM chirps c JOIN groups g ON g.id = c.group_id
    WHERE c.id = ${id}` as { group_id: number; author: string; owner_id: string }[];
  if (!row.length) return Response.json({ error: "No such chirp." }, { status: 404 });
  const { author, owner_id } = row[0];
  const allowed = isAdmin(userId) || (owner_id === userId && author !== owner_id);
  if (!allowed) return Response.json({ error: "Not yours to review." }, { status: 403 });
  const own = row;

  if (action === "remove") {
    await sql`UPDATE chirps SET removed_at = now(), removed_by = ${userId} WHERE id = ${id} AND removed_at IS NULL`;
  }
  const done = await sql`UPDATE chirp_reports SET resolved_at = now(), resolved_by = ${userId}, resolution = ${action}
    WHERE chirp_id = ${id} AND resolved_at IS NULL RETURNING id` as unknown[];
  await track(sql, userId, "chirp_report_resolved", { action }, own[0].group_id);
  return Response.json({ resolved: done.length, action });
}
