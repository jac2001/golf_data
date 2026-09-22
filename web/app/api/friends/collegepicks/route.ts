/**
 * /api/friends/collegepicks — the College Game.
 * ==============================================
 * One SCHOOL per event, picked before lock. Your score is the combined
 * prize money of your school's TOP TWO finishers that week (best-ball
 * style — so a two-star Auburn can beat a ten-deep Texas roster).
 * Highest total wins the week; the season counts event wins.
 *
 * The server validates the school against /api/colleges/field — only
 * schools with alumni actually in the field exist that week.
 *
 * GET    ?tournament_id=X → { event, schools, pick }
 * POST   { tournament_id, school } → set your school (pre-lock, replaces)
 * DELETE { tournament_id } → clear it (pre-lock)
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

type EventInfo = { tid: string; name: string; tour: string; locked: boolean; startDate: string; finished: boolean };
type School = { school: string; players: string[] };

async function openEvent(tid: string | null): Promise<EventInfo | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    const match = tid
      ? (events ?? []).find((e: { tournament_id: string }) => e.tournament_id === tid.toUpperCase())
      : (events ?? []).find((e: { locked: boolean }) => !e.locked);
    if (!match) return null;
    return { tid: match.tournament_id, name: match.name, tour: match.tour,
      locked: !!match.locked, startDate: String(match.start_date ?? ""), finished: !!match.finished };
  } catch { return null; }
}

async function schoolsFor(tid: string): Promise<School[]> {
  try {
    const res = await fetch(`${MODEL_API}/api/colleges/field?tournament_id=${tid}`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    return (await res.json()).schools ?? [];
  } catch { return []; }
}

async function myPick(userId: string, tid: string): Promise<string | null> {
  const sql = getSql();
  const rows = await sql`
    SELECT school FROM college_picks
    WHERE user_id = ${userId} AND tournament_id = ${tid}` as { school: string }[];
  return rows[0]?.school ?? null;
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const tid = new URL(req.url).searchParams.get("tournament_id");
  const ev = await openEvent(tid);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  return Response.json({
    event: ev,
    schools: await schoolsFor(ev.tid),
    pick: await myPick(userId, ev.tid),
  });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "School picks are locked — the tournament has started." }, { status: 409 });

  const school = String(body.school ?? "").trim();
  if (!school) return Response.json({ error: "school required" }, { status: 400 });

  const schools = await schoolsFor(ev.tid);
  if (!schools.some(s => s.school === school)) {
    return Response.json({ error: `${school} has no alumni in this field.` }, { status: 400 });
  }

  const displayName = nameOf(await currentUser());
  const sql = getSql();
  await sql`
    INSERT INTO college_picks (user_id, user_name, tournament_id, school)
    VALUES (${userId}, ${displayName}, ${ev.tid}, ${school})
    ON CONFLICT (user_id, tournament_id) DO UPDATE
    SET school = ${school}, user_name = ${displayName}`;
  return Response.json({ event: ev, pick: school });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "School picks are locked — the tournament has started." }, { status: 409 });
  const sql = getSql();
  await sql`DELETE FROM college_picks WHERE user_id = ${userId} AND tournament_id = ${ev.tid}`;
  return Response.json({ event: ev, pick: null });
}
