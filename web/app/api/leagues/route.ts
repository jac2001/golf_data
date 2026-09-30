/**
 * /api/leagues — Let It Ride seasons (docs/PHASE2_DESIGN.md).
 *
 * GET  ?group_id=N  → the group's active league (or null) + config.
 *                     Members only.
 * POST {group_id, name, season_start, season_end?, tours?,
 *       uses_per_player?, players_per_week?}
 *                   → starts a season. Group owner only; the
 *                     one_active_league index refuses a second active
 *                     season, so a double-click can't create two.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

type League = {
  id: number; group_id: number; name: string;
  season_start: string; season_end: string | null; tours: string[];
  uses_per_player: number; players_per_week: number; status: string;
};

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const groupId = Number(new URL(req.url).searchParams.get("group_id"));
  const sql = getSql();

  // No group_id: which of MY groups are running a season, plus how many
  // groups I'm in — the standings view uses this to find a season.
  if (!groupId) {
    const rows = await sql`
      SELECT l.id, l.name, g.id AS group_id, g.name AS group_name
      FROM group_members m
      JOIN groups g ON g.id = m.group_id
      JOIN leagues l ON l.group_id = g.id AND l.status = 'active'
      WHERE m.user_id = ${userId}` as { id: number; name: string; group_id: number; group_name: string }[];
    const [{ n }] = await sql`
      SELECT count(*)::int AS n FROM group_members WHERE user_id = ${userId}` as { n: number }[];
    return Response.json({ active: rows, group_count: n });
  }

  const member = await sql`
    SELECT 1 FROM group_members WHERE group_id = ${groupId} AND user_id = ${userId}` as unknown[];
  if (!member.length) return Response.json({ error: "Not a member of this group" }, { status: 403 });

  const rows = await sql`
    SELECT id, group_id, name, season_start::text, season_end::text, tours,
           uses_per_player, players_per_week, status
    FROM leagues WHERE group_id = ${groupId} AND status = 'active'` as League[];
  return Response.json({ league: rows[0] ?? null });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const body = await req.json().catch(() => ({}));

  const groupId = Number(body.group_id);
  const name = String(body.name ?? "").trim().slice(0, 60);
  const start = String(body.season_start ?? "");
  const end = body.season_end ? String(body.season_end) : null;
  const tours = Array.isArray(body.tours) && body.tours.length
    ? body.tours.filter((t: unknown) => t === "pga" || t === "euro") : ["pga", "euro"];
  const uses = Number(body.uses_per_player ?? 3);
  const perWeek = Number(body.players_per_week ?? 3);

  if (!groupId || !name || !/^\d{4}-\d{2}-\d{2}$/.test(start)) {
    return Response.json({ error: "group_id, name and season_start (YYYY-MM-DD) are required" }, { status: 400 });
  }
  if (end && end < start) return Response.json({ error: "season_end is before season_start" }, { status: 400 });
  if (!tours.length) return Response.json({ error: "Pick at least one tour" }, { status: 400 });
  if (!(uses >= 1 && uses <= 10 && perWeek >= 1 && perWeek <= 10)) {
    return Response.json({ error: "Uses and golfers-per-week must be between 1 and 10" }, { status: 400 });
  }

  const sql = getSql();
  const owner = await sql`
    SELECT 1 FROM groups WHERE id = ${groupId} AND owner_id = ${userId}` as unknown[];
  if (!owner.length) return Response.json({ error: "Only the group owner can start a season" }, { status: 403 });

  try {
    const rows = await sql`
      INSERT INTO leagues (group_id, name, season_start, season_end, tours,
                           uses_per_player, players_per_week, created_by)
      VALUES (${groupId}, ${name}, ${start}, ${end}, ${tours}, ${uses}, ${perWeek}, ${userId})
      RETURNING id` as { id: number }[];
    return Response.json({ id: rows[0].id }, { status: 201 });
  } catch (e) {
    if (String(e).includes("one_active_league")) {
      return Response.json({ error: "This group already has an active season" }, { status: 409 });
    }
    throw e;
  }
}
