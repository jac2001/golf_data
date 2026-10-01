/**
 * /api/leagues/[id]/weeks — every slate in the season, with its status.
 *
 * The pick screen used to build its chips from events/open, which only
 * covers three weeks back and ten days ahead — a season's October slates
 * would vanish by November. This lists the whole season from the
 * schedule (every event on the league's tours since season_start, a few
 * weeks ahead), with status from the open list where it knows:
 *   open       — pickable now
 *   live       — locked, in progress
 *   completed  — finished (or older than the open window)
 *   upcoming   — beyond the pick window; opens the week before
 */
import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";

type Week = {
  tournament_id: string; name: string; tour: "pga" | "euro"; start_date: string;
  status: "open" | "awaiting" | "live" | "completed" | "upcoming";
};

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const sql = getSql();
  const rows = await sql`
    SELECT l.season_start::text, l.season_end::text, l.tours
    FROM leagues l JOIN group_members m ON m.group_id = l.group_id
    WHERE l.id = ${Number((await params).id)} AND m.user_id = ${userId}` as
    { season_start: string; season_end: string | null; tours: string[] }[];
  if (!rows.length) return Response.json({ error: "Not your league" }, { status: 403 });
  const league = rows[0];

  // Status for events inside the open window.
  const open = new Map<string, { locked: boolean; finished: boolean; field: boolean }>();
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (res.ok) for (const e of (await res.json()).events ?? []) {
      open.set(String(e.tournament_id).toUpperCase(), { locked: !!e.locked, finished: !!e.finished,
        field: e.field_available !== false });
    }
  } catch { /* statuses fall back to the calendar below */ }

  // The schedule from the day before season_start, per tour.
  const dayBefore = new Date(`${league.season_start}T12:00:00Z`);
  dayBefore.setUTCDate(dayBefore.getUTCDate() - 1);
  const after = dayBefore.toISOString().slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);

  const weeks: Week[] = [];
  for (const tour of league.tours) {
    try {
      const res = await fetch(`${MODEL_API}/api/schedule/upcoming?tour=${tour}&after=${after}&limit=52`,
        { next: { revalidate: 600 } });
      if (!res.ok) continue;
      for (const e of (await res.json()).events ?? []) {
        if (league.season_end && e.start_date > league.season_end) continue;
        const tid = String(e.tournament_id).toUpperCase();
        const o = open.get(tid);
        const status: Week["status"] = o
          ? (o.finished ? "completed" : o.locked ? "live" : o.field ? "open" : "awaiting")
          : (e.start_date < today ? "completed" : "upcoming");
        weeks.push({ tournament_id: tid, name: e.name, tour: tour as "pga" | "euro",
                     start_date: e.start_date, status });
      }
    } catch { /* that tour's weeks just don't show */ }
  }

  // Past + this week + a few ahead: an open-ended season shouldn't list
  // the whole next year of chips.
  const ahead = weeks.filter(w => w.status === "upcoming")
    .sort((a, b) => a.start_date.localeCompare(b.start_date)).slice(0, 4 * league.tours.length);
  const shown = [...weeks.filter(w => w.status !== "upcoming"), ...ahead]
    .sort((a, b) => a.start_date.localeCompare(b.start_date) || a.tour.localeCompare(b.tour));
  return Response.json({ weeks: shown });
}
