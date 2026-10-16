/**
 * GET /api/friends/past-events?game=rounds|fades|college → { events: OpenEvent[] }
 * ==================================================================================
 * Finished events this person's people (lib/gameScope.ts) played in one
 * game. The per-event games build their event lists from events/open,
 * which reaches only 21 days back, so a group's results used to vanish
 * three weeks later. The game screens merge these in as finished events.
 * Names and dates come from the schedule; only events with picks count.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";

const TABLES = { rounds: "round_picks", fades: "fade_picks", college: "college_picks" } as const;
type Game = keyof typeof TABLES;

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const game = new URL(req.url).searchParams.get("game") as Game | null;
  if (!game || !(game in TABLES)) return Response.json({ error: "game must be rounds, fades or college" }, { status: 400 });

  const ids = await visibleUserIds(userId);
  if (!ids) return Response.json({ events: [] });
  const sql = getSql();
  // Table names can't be bound parameters; `game` is checked against TABLES above.
  const rows = (game === "rounds"
    ? await sql`SELECT tournament_id, min(created_at)::date::text AS first FROM round_picks WHERE user_id = ANY(${ids}) GROUP BY 1`
    : game === "fades"
    ? await sql`SELECT tournament_id, min(created_at)::date::text AS first FROM fade_picks WHERE user_id = ANY(${ids}) GROUP BY 1`
    : await sql`SELECT tournament_id, min(created_at)::date::text AS first FROM college_picks WHERE user_id = ANY(${ids}) GROUP BY 1`
  ) as { tournament_id: string; first: string }[];
  if (!rows.length) return Response.json({ events: [] });

  const tids = new Set(rows.map(r => r.tournament_id.toUpperCase()));
  // Schedule from a month before the earliest pick (picks are made the week before).
  const earliest = rows.map(r => r.first).sort()[0];
  const after = new Date(`${earliest}T12:00:00Z`);
  after.setUTCDate(after.getUTCDate() - 31);
  const today = new Date().toISOString().slice(0, 10);

  const events = [];
  for (const tour of ["pga", "euro"] as const) {
    try {
      const res = await fetch(`${MODEL_API}/api/schedule/upcoming?tour=${tour}&after=${after.toISOString().slice(0, 10)}&limit=60`,
        { next: { revalidate: 3600 } });
      if (!res.ok) continue;
      for (const e of (await res.json()).events ?? []) {
        const tid = String(e.tournament_id).toUpperCase();
        if (!tids.has(tid) || e.start_date >= today) continue;
        events.push({
          tournament_id: tid, name: e.name, tour, start_date: e.start_date, end_date: e.start_date,
          locked: true, finished: true, purse: e.purse ?? null, has_model: true, field_available: true,
        });
      }
    } catch { /* that tour's past events just don't merge in */ }
  }
  return Response.json({ events });
}
