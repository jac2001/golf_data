/**
 * /api/friends/bets — your own bets, shared if you want.
 * =======================================================
 * These are bets you actually placed anywhere (any book, any market),
 * distinct from tailing a model rec. Self-graded — you mark won/lost —
 * because nobody but you knows what your ticket said.
 *
 * GET    → your bets
 * POST   → log one { description, odds_american?, stake_units?, shared? }
 * PATCH  → update { id, outcome? ('pending'|'won'|'lost'|'void'), shared? }
 * DELETE → remove { id }
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

const OUTCOMES = new Set(["pending", "won", "lost", "void"]);

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const sql = getSql();
  const bets = await sql`
    SELECT id, tournament_id, description, odds_american, stake_units, shared, outcome, created_at
    FROM user_bets WHERE user_id = ${userId} ORDER BY created_at DESC`;
  return Response.json({ bets });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const description = String(body.description ?? "").trim().slice(0, 200);
  if (!description) return Response.json({ error: "Describe the bet first." }, { status: 400 });

  // Stamp the current event so the bet sorts into the right week later.
  let tid = "";
  try {
    const res = await fetch(`${MODEL_API}/api/tournament`, { cache: "no-store" });
    if (res.ok) tid = String((await res.json()).tournament_id ?? "");
  } catch { /* fine — bet just goes unstamped */ }

  const name = nameOf(await currentUser());

  const sql = getSql();
  const rows = await sql`
    INSERT INTO user_bets (user_id, user_name, tournament_id, description, odds_american, stake_units, shared)
    VALUES (${userId}, ${name}, ${tid}, ${description},
            ${body.odds_american ?? null}, ${Number(body.stake_units ?? 1)}, ${!!body.shared})
    RETURNING id` as { id: number }[];
  return Response.json({ id: rows[0].id });
}

export async function PATCH(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const id = Number(body.id);
  if (!id) return Response.json({ error: "id required" }, { status: 400 });

  const sql = getSql();
  if (body.outcome !== undefined) {
    const outcome = String(body.outcome);
    if (!OUTCOMES.has(outcome)) return Response.json({ error: "Bad outcome" }, { status: 400 });
    await sql`UPDATE user_bets SET outcome = ${outcome} WHERE id = ${id} AND user_id = ${userId}`;
  }
  if (body.shared !== undefined) {
    await sql`UPDATE user_bets SET shared = ${!!body.shared} WHERE id = ${id} AND user_id = ${userId}`;
  }
  return Response.json({ ok: true });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const sql = getSql();
  await sql`DELETE FROM user_bets WHERE id = ${Number(body.id)} AND user_id = ${userId}`;
  return Response.json({ ok: true });
}
