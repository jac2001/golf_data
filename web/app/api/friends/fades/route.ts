/**
 * /api/friends/fades — the Fade Game.
 * ====================================
 * Pick 3 players you think will FLOP; your score is their combined
 * earnings and LOWEST total wins. The catch that makes it a game: you
 * may only fade from the model's top 20 by win chance (the "pool") —
 * otherwise the winning strategy is three club pros and everyone ties
 * at $0. PGA events only, since the pool is defined by model numbers.
 *
 * The pool is computed HERE, server-side, with the same fadePool()
 * the browser uses to render the board — one function, one truth.
 * A POST for a player outside the pool is rejected no matter what the
 * client claimed to be showing.
 *
 * GET    ?tournament_id=X → { event, pool, fades }
 * POST   { tournament_id, player_name } → add a fade (3 max, pre-lock)
 * DELETE { tournament_id, player_name } → remove one (pre-lock)
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";
import { fadePool, expectedPayout, Probs } from "@/lib/modelBrain";

type EventInfo = {
  tid: string; name: string; tour: string; locked: boolean;
  startDate: string; purse: number | null; hasModel: boolean;
};
type PredRow = Probs & { player_name: string };

async function openEvent(tid: string | null): Promise<EventInfo | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    if (!Array.isArray(events) || events.length === 0) return null;
    const match = tid
      ? events.find((e: { tournament_id: string }) => e.tournament_id === tid.toUpperCase())
      : events.find((e: { locked: boolean; has_model: boolean }) => !e.locked && e.has_model);
    if (!match) return null;
    return {
      tid: match.tournament_id, name: match.name, tour: match.tour,
      locked: !!match.locked, startDate: String(match.start_date ?? ""),
      purse: match.purse ?? null, hasModel: !!match.has_model,
    };
  } catch {
    return null;
  }
}

/** The fade pool for an event: Jack's fadePool() over that event's own
 *  predictions (the API serves archived Tuesday numbers per tournament).
 *  Empty when the payload's label doesn't match — never someone else's pool. */
async function poolFor(tid: string): Promise<PredRow[]> {
  try {
    const res = await fetch(
      `${MODEL_API}/api/predictions?limit=200&tournament_id=${encodeURIComponent(tid)}`,
      { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const d = await res.json();
    if (String(d.tournament_id ?? "").toUpperCase() !== tid.toUpperCase()) return [];
    return fadePool((d.players ?? []).filter((p: PredRow) => p.player_name));
  } catch {
    return [];
  }
}

async function myFades(userId: string, tid: string): Promise<string[]> {
  const sql = getSql();
  const rows = await sql`
    SELECT player_name FROM fade_picks
    WHERE user_id = ${userId} AND tournament_id = ${tid}
    ORDER BY created_at` as { player_name: string }[];
  return rows.map(r => r.player_name);
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const tid = new URL(req.url).searchParams.get("tournament_id");
  const ev = await openEvent(tid);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (!ev.hasModel) {
    return Response.json({ error: "The Fade Game needs model numbers — PGA events only." }, { status: 400 });
  }

  const pool = await poolFor(ev.tid);
  return Response.json({
    event: ev,
    pool: pool.map(p => ({
      player_name: p.player_name,
      win_prob: p.win_prob,
      // What the model expects them to bank — the number you're betting against.
      expected_earnings: ev.purse ? Math.round(expectedPayout(ev.purse, p)) : null,
    })),
    fades: await myFades(userId, ev.tid),
  });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Fades are locked — the tournament has started." }, { status: 409 });
  if (!ev.hasModel) {
    return Response.json({ error: "The Fade Game needs model numbers — PGA events only." }, { status: 400 });
  }

  const player = String(body.player_name ?? "").trim();
  if (!player) return Response.json({ error: "player_name required" }, { status: 400 });

  // The rule of the game, enforced where it can't be bypassed.
  const pool = await poolFor(ev.tid);
  if (pool.length === 0) {
    return Response.json({ error: "No fresh model numbers for this event yet." }, { status: 503 });
  }
  if (!pool.some(p => p.player_name === player)) {
    return Response.json({ error: `${player} isn't in the top 20 — you can only fade the favorites.` }, { status: 400 });
  }

  const sql = getSql();
  const existing = await sql`
    SELECT count(*)::int AS n FROM fade_picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid}` as { n: number }[];
  if (existing[0].n >= 3) {
    return Response.json({ error: "You already have 3 fades this week." }, { status: 409 });
  }

  const displayName = nameOf(await currentUser());
  await sql`
    INSERT INTO fade_picks (user_id, user_name, tournament_id, player_name)
    VALUES (${userId}, ${displayName}, ${ev.tid}, ${player})
    ON CONFLICT (user_id, tournament_id, player_name) DO NOTHING`;

  return Response.json({ event: ev, fades: await myFades(userId, ev.tid) });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const ev = await openEvent(String(body.tournament_id ?? "") || null);
  if (!ev) return Response.json({ error: "No open tournament" }, { status: 503 });
  if (ev.locked) return Response.json({ error: "Fades are locked — the tournament has started." }, { status: 409 });

  const player = String(body.player_name ?? "").trim();
  const sql = getSql();
  await sql`
    DELETE FROM fade_picks
    WHERE user_id = ${userId} AND tournament_id = ${ev.tid} AND player_name = ${player}`;

  return Response.json({ event: ev, fades: await myFades(userId, ev.tid) });
}
