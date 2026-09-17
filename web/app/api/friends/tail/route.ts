/**
 * /api/friends/tail — "I'm tailing that bet."
 * ============================================
 * POST toggles a tail on a model recommendation (on if absent, off if
 * present). GET returns your tails with graded P&L pulled from the
 * honest ledger, so your personal record uses the same numbers the
 * public Betting Board shows.
 */

import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameOf } from "@/lib/displayName";

type TailRow = {
  recommendation_id: string; tournament_id: string; bet_label: string;
  odds_american: number | null; stake_units: number; created_at: string;
};

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const recId = String(body.recommendation_id ?? "").trim();
  if (!recId) return Response.json({ error: "recommendation_id required" }, { status: 400 });

  const sql = getSql();
  const existing = await sql`
    SELECT id FROM tailed_bets WHERE user_id = ${userId} AND recommendation_id = ${recId}` as { id: number }[];

  if (existing.length) {
    await sql`DELETE FROM tailed_bets WHERE user_id = ${userId} AND recommendation_id = ${recId}`;
    return Response.json({ tailed: false });
  }

  const displayName = nameOf(await currentUser());

  await sql`
    INSERT INTO tailed_bets (user_id, user_name, recommendation_id, tournament_id, bet_label, odds_american, stake_units)
    VALUES (${userId}, ${displayName}, ${recId},
            ${String(body.tournament_id ?? "")}, ${String(body.bet_label ?? "")},
            ${body.odds_american ?? null}, ${Number(body.stake_units ?? 1)})
    ON CONFLICT (user_id, recommendation_id) DO NOTHING`;
  return Response.json({ tailed: true });
}

export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const sql = getSql();
  const tails = await sql`
    SELECT recommendation_id, tournament_id, bet_label, odds_american, stake_units, created_at
    FROM tailed_bets WHERE user_id = ${userId} ORDER BY created_at DESC` as TailRow[];

  let outcomes: Record<string, { outcome_status: string; pnl_per_1: number | null; label: string }> = {};
  if (tails.length) {
    try {
      const ids = tails.map(t => t.recommendation_id).join(",");
      const res = await fetch(`${MODEL_API}/api/bets/outcomes?ids=${encodeURIComponent(ids)}`,
        { next: { revalidate: 300 } });
      if (res.ok) outcomes = (await res.json()).outcomes ?? {};
    } catch { /* outcomes stay pending */ }
  }

  let pnl = 0, settled = 0, won = 0;
  const rows = tails.map(t => {
    const o = outcomes[t.recommendation_id];
    const stakePnl = o?.pnl_per_1 != null ? o.pnl_per_1 * t.stake_units : null;
    if (stakePnl != null && o!.outcome_status !== "pending") {
      pnl += stakePnl; settled += 1;
      if (o!.outcome_status === "won") won += 1;
    }
    return { ...t, label: t.bet_label || o?.label || t.recommendation_id,
             outcome: o?.outcome_status ?? "pending", pnl: stakePnl };
  });

  return Response.json({ tails: rows, summary: { pnl, settled, won } });
}
