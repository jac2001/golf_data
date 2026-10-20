/**
 * GET /api/admin/chirp-reports → { reports } — the site admin's queue.
 * ====================================================================
 * Open reports a group owner can't fairly review: reports about the
 * owner's OWN chirps (lib/admin.ts; decided by Jack 2026-10-20). Owners
 * review everything else in their thread. Admins only (403 otherwise).
 * Reporters stay unnamed here too. Resolve via POST /api/friends/chirps/resolve.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { isAdmin } from "@/lib/admin";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  if (!isAdmin(userId)) return Response.json({ error: "Admins only." }, { status: 403 });

  const sql = getSql();
  const reports = await sql`
    SELECT c.id::text AS chirp_id, c.text, c.user_name AS author, c.tournament_id, c.created_at::text,
           g.name AS group_name, count(r.id)::int AS reports,
           array_remove(array_agg(NULLIF(r.reason, '')), NULL) AS reasons
    FROM chirp_reports r
    JOIN chirps c ON c.id = r.chirp_id
    JOIN groups g ON g.id = c.group_id
    WHERE r.resolved_at IS NULL AND c.user_id = g.owner_id
    GROUP BY c.id, g.name
    ORDER BY max(r.created_at) DESC` as unknown[];
  return Response.json({ reports });
}
