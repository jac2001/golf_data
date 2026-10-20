/**
 * POST /api/friends/chirps/resolve { id, action: "dismiss" | "remove" } → { resolved }
 * ====================================================================================
 * The group owner's review of reports on a chirp (review item 8). Owner
 * only. "remove" also removes the chirp; either way every open report on
 * it is marked resolved, with who and how.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { track } from "@/lib/track";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const id = String(body.id ?? "");
  const action = body.action === "remove" ? "remove" : body.action === "dismiss" ? "dismiss" : null;
  if (!/^\d+$/.test(id) || !action) return Response.json({ error: "id and action (dismiss|remove) required" }, { status: 400 });

  const sql = getSql();
  const own = await sql`SELECT c.group_id FROM chirps c JOIN groups g ON g.id = c.group_id
    WHERE c.id = ${id} AND g.owner_id = ${userId}` as { group_id: number }[];
  if (!own.length) return Response.json({ error: "Only the group's owner reviews reports." }, { status: 403 });

  if (action === "remove") {
    await sql`UPDATE chirps SET removed_at = now(), removed_by = ${userId} WHERE id = ${id} AND removed_at IS NULL`;
  }
  const done = await sql`UPDATE chirp_reports SET resolved_at = now(), resolved_by = ${userId}, resolution = ${action}
    WHERE chirp_id = ${id} AND resolved_at IS NULL RETURNING id` as unknown[];
  await track(sql, userId, "chirp_report_resolved", { action }, own[0].group_id);
  return Response.json({ resolved: done.length, action });
}
