/**
 * /api/friends/picks — the weekly 3-pick game.
 * =============================================
 * GET    → your picks for the current tournament (plus lock state)
 * POST   → add a pick  { player_name }
 * DELETE → remove one  { player_name }
 *
 * Rules mirror Jack's league week: 3 players max, picks lock when the
 * tournament starts. The current event and its start date come from
 * the model API, so this route never invents its own schedule.
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

type EventInfo = { tid: string; name: string; locked: boolean; startDate: string };

async function currentEvent(): Promise<EventInfo | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/tournament`, { cache: "no-store" });
    if (!res.ok) return null;
    const t = await res.json();
    if (!t?.tournament_id) return null;
    const startDate = String(t.start_date ?? "");
    // Lock at midnight local on the start date — Thursday tee times vary,
    // Wednesday-night picks are the spirit of the game.
    const locked = !!startDate && new Date() >= new Date(`${startDate.slice(0, 10)}T00:00:00`);
    return { tid: String(t.tournament_id), name: String(t.name ?? ""), locked, startDate };
  } catch {
    return null;
  }
}

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const ev = await currentEvent();
  if (!ev) return Response.json({ error: "No active tournament" }, { status: 503 });

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

  const ev = await currentEvent();
  if (!ev) return Response.json({ error: "No active tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Picks are locked — the tournament has started." }, { status: 409 });

  const body = await req.json().catch(() => ({}));
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

  const ev = await currentEvent();
  if (!ev) return Response.json({ error: "No active tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Picks are locked — the tournament has started." }, { status: 409 });

  const body = await req.json().catch(() => ({}));
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
