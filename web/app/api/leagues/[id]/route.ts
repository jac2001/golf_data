/**
 * /api/leagues/[id] — edit a season's settings (group owner only).
 *
 * PATCH any of: name, tours, uses_per_player, players_per_week,
 * uses_scope ('golfer' | 'tour'), season_end (YYYY-MM-DD or null),
 * status: 'complete' (ends the season — final; the group can then start
 * a new one).
 *
 * Changes apply going forward. Existing picks always stand: lowering
 * uses to 2 blocks a fourth-but-not-third pick of a golfer someone has
 * already used three times; it never deletes a pick.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const leagueId = Number((await params).id);

  const sql = getSql();
  const rows = await sql`
    SELECT l.id, l.name, l.season_start::text, l.season_end::text, l.tours,
           l.uses_per_player, l.players_per_week, l.uses_scope, l.status
    FROM leagues l JOIN groups g ON g.id = l.group_id
    WHERE l.id = ${leagueId} AND g.owner_id = ${userId}` as {
      id: number; name: string; season_start: string; season_end: string | null; tours: string[];
      uses_per_player: number; players_per_week: number; uses_scope: string; status: string;
    }[];
  if (!rows.length) return Response.json({ error: "Only the group owner can change the season" }, { status: 403 });
  const cur = rows[0];
  if (cur.status !== "active") return Response.json({ error: "This season has ended" }, { status: 409 });

  const b = await req.json().catch(() => ({}));
  const name = b.name !== undefined ? String(b.name).trim().slice(0, 60) : cur.name;
  const tours: string[] = Array.isArray(b.tours)
    ? b.tours.filter((t: unknown) => t === "pga" || t === "euro") : cur.tours;
  const uses = b.uses_per_player !== undefined ? Number(b.uses_per_player) : cur.uses_per_player;
  const perWeek = b.players_per_week !== undefined ? Number(b.players_per_week) : cur.players_per_week;
  const scope = b.uses_scope !== undefined ? String(b.uses_scope) : cur.uses_scope;
  const end = b.season_end === undefined ? cur.season_end : (b.season_end ? String(b.season_end) : null);
  const status = b.status === "complete" ? "complete" : "active";

  if (!name) return Response.json({ error: "The season needs a name" }, { status: 400 });
  if (!tours.length) return Response.json({ error: "Pick at least one tour" }, { status: 400 });
  if (!(uses >= 1 && uses <= 10 && perWeek >= 1 && perWeek <= 10)) {
    return Response.json({ error: "Uses and golfers-per-event must be between 1 and 10" }, { status: 400 });
  }
  if (scope !== "golfer" && scope !== "tour") return Response.json({ error: "Unknown use scope" }, { status: 400 });
  if (end && !/^\d{4}-\d{2}-\d{2}$/.test(end)) return Response.json({ error: "End date must be YYYY-MM-DD" }, { status: 400 });
  if (end && end < cur.season_start) return Response.json({ error: "The season can't end before it started" }, { status: 400 });

  await sql`
    UPDATE leagues SET name = ${name}, tours = ${tours}, uses_per_player = ${uses},
      players_per_week = ${perWeek}, uses_scope = ${scope}, season_end = ${end}, status = ${status}
    WHERE id = ${leagueId}`;
  return Response.json({ ok: true });
}
