/**
 * /api/friends/picks — the weekly 3-pick game, now multi-event.
 * ==============================================================
 * PGA and DP World Tour events run the same weeks, so "the" tournament
 * became "which tournament": every call carries a tournament_id that
 * must be one of the model API's open events (the server re-checks —
 * client-supplied ids are never trusted for lock state).
 *
 * GET    ?tournament_id=X → your picks for that event (plus lock state)
 * POST   { tournament_id, player_name } → add a pick (3 max, pre-lock)
 * DELETE { tournament_id, player_name } → remove one (pre-lock)
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

type EventInfo = { tid: string; name: string; tour: string; locked: boolean; startDate: string };

/** Resolve a client-requested event against the model API's open list —
 *  the server decides what's pickable and when it locks, never the client. */
async function openEvent(tid: string | null): Promise<EventInfo | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    if (!Array.isArray(events) || events.length === 0) return null;
    const match = tid
      ? events.find((e: { tournament_id: string }) => e.tournament_id === tid.toUpperCase())
      : events.find((e: { locked: boolean }) => !e.locked) ?? events[0];
    if (!match) return null;
    return {
      tid: match.tournament_id, name: match.name, tour: match.tour,
      locked: !!match.locked, startDate: String(match.start_date ?? ""),
    };
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const tid = new URL(req.url).searchParams.get("tournament_id");
  const ev = await openEvent(tid);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });

  const sql = getSql();
  const rows = await sql`
    SELECT player_name, created_at FROM picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}
    ORDER BY created_at` as { player_name: string; created_at: string }[];

  return Response.json({ event: ev, picks: rows.map(r => r.player_name) });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Picks are locked — the tournament has started." }, { status: 409 });

  const player = String(body.player_name ?? "").trim();
  if (!player) return Response.json({ error: "player_name required" }, { status: 400 });

  const displayName = nameOf(await currentUser());

  const sql = getSql();
  const existing = await sql`
    SELECT count(*)::int AS n FROM picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}` as { n: number }[];
  if (existing[0].n >= 3) {
    return Response.json({ error: "You already have 3 picks this week." }, { status: 409 });
  }

  await sql`
    INSERT INTO picks (user_id, user_name, tournament_id, player_name)
    VALUES (${userId}, ${displayName}, ${ev.tid}, ${player})
    ON CONFLICT (user_id, tournament_id, player_name) DO NOTHING`;

  const rows = await sql`
    SELECT player_name FROM picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}
    ORDER BY created_at` as { player_name: string }[];
  return Response.json({ event: ev, picks: rows.map(r => r.player_name) });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Picks are locked — the tournament has started." }, { status: 409 });

  const player = String(body.player_name ?? "").trim();

  const sql = getSql();
  await sql`
    DELETE FROM picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid} AND player_name = ${player}`;

  const rows = await sql`
    SELECT player_name FROM picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}
    ORDER BY created_at` as { player_name: string }[];
  return Response.json({ event: ev, picks: rows.map(r => r.player_name) });
}
