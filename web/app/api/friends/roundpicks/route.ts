/**
 * /api/friends/roundpicks — the Round Game.
 * ==========================================
 * One player per round, each player once per event, score to par with a
 * +5 penalty for a missed round. Round N locks at midnight local on
 * (start_date + N - 1) — pick tonight for tomorrow's round.
 *
 * GET    ?tournament_id → { event, rounds: {1..4: player|null}, locks, used }
 * POST   { tournament_id, round, player_name } → set/replace (pre-lock)
 * DELETE { tournament_id, round } → clear (pre-lock)
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

type EventInfo = { tid: string; name: string; tour: string; startDate: string };

async function openEvent(tid: string | null): Promise<EventInfo | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    const match = tid
      ? (events ?? []).find((e: { tournament_id: string }) => e.tournament_id === tid.toUpperCase())
      : (events ?? [])[0];
    if (!match) return null;
    return { tid: match.tournament_id, name: match.name, tour: match.tour,
             startDate: String(match.start_date ?? "") };
  } catch { return null; }
}

/** Round N's day is start_date + (N-1); it locks when that day arrives. */
function roundLocks(startDate: string): Record<number, boolean> {
  const locks: Record<number, boolean> = {};
  const base = new Date(`${startDate.slice(0, 10)}T00:00:00`);
  for (let r = 1; r <= 4; r++) {
    const day = new Date(base);
    day.setDate(base.getDate() + (r - 1));
    locks[r] = !isNaN(day.getTime()) && new Date() >= day;
  }
  return locks;
}

async function myPicks(sql: ReturnType<typeof getSql>, userId: string, tid: string) {
  const rows = await sql`
    SELECT round, player_name FROM round_picks
    WHERE user_id = ${userId} AND tournament_id = ${tid}` as { round: number; player_name: string }[];
  const rounds: Record<number, string | null> = { 1: null, 2: null, 3: null, 4: null };
  for (const r of rows) rounds[r.round] = r.player_name;
  return { rounds, used: rows.map(r => r.player_name) };
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const ev = await openEvent(new URL(req.url).searchParams.get("tournament_id"));
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  const sql = getSql();
  const mine = await myPicks(sql, userId, ev.tid);
  return Response.json({ event: ev, ...mine, locks: roundLocks(ev.startDate) });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });

  const round = Number(body.round);
  if (!(round >= 1 && round <= 4)) return Response.json({ error: "round must be 1-4" }, { status: 400 });
  if (roundLocks(ev.startDate)[round]) {
    return Response.json({ error: `Round ${round} is locked.` }, { status: 409 });
  }
  const player = String(body.player_name ?? "").trim();
  if (!player) return Response.json({ error: "player_name required" }, { status: 400 });

  const sql = getSql();
  // Once per event: the same name in a different round is a rule breach —
  // unless it's this round (replacing a pick with itself is a no-op).
  const clash = await sql`
    SELECT round FROM round_picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}
      AND player_name = ${player} AND round <> ${round}` as { round: number }[];
  if (clash.length) {
    return Response.json({ error: `You already used ${player} in round ${clash[0].round}.` }, { status: 409 });
  }

  const name = nameOf(await currentUser());
  await sql`
    INSERT INTO round_picks (user_id, user_name, tournament_id, round, player_name)
    VALUES (${userId}, ${name}, ${ev.tid}, ${round}, ${player})
    ON CONFLICT (user_id, tournament_id, round)
    DO UPDATE SET player_name = EXCLUDED.player_name, user_name = EXCLUDED.user_name`;
  const mine = await myPicks(sql, userId, ev.tid);
  return Response.json({ event: ev, ...mine, locks: roundLocks(ev.startDate) });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  const round = Number(body.round);
  if (roundLocks(ev.startDate)[round]) {
    return Response.json({ error: `Round ${round} is locked.` }, { status: 409 });
  }
  const sql = getSql();
  await sql`
    DELETE FROM round_picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid} AND round = ${round}`;
  const mine = await myPicks(sql, userId, ev.tid);
  return Response.json({ event: ev, ...mine, locks: roundLocks(ev.startDate) });
}
