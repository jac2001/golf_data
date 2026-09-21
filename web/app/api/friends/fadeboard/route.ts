/**
 * /api/friends/fadeboard — Fade Game leaderboards.
 * =================================================
 * ?tournament_id=X: everyone's fades for that event, graded by real
 * earnings, sorted ASCENDING — lowest combined earnings wins. Fades
 * stay hidden until the event locks (same anti-copy rule as every
 * other game).
 *
 * No param: SEASON standings, counted in EVENT WINS — not a sum. A
 * season sum is broken for this game: lower is better, so the fewer
 * events you enter the better you look, and "never play" becomes the
 * optimal season. Wins per settled event (ties all credited) keep the
 * incentive pointing at playing and winning.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";

type PickRow = { user_id: string; user_name: string; player_name: string };
type EarningsResp = {
  settled: boolean;
  earnings_estimated?: boolean;
  players: Record<string, { player_name: string; earnings: number; position: string }>;
};

const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

async function earningsFor(tid: string): Promise<EarningsResp | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/results/earnings?tournament_id=${tid}`,
      { next: { revalidate: 300 } });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

/** Season standings in EVENT WINS: per settled event, whoever's fades
 *  earned the least takes a win (ties all credited). Entered counts
 *  every event with fades, settled or not. */
async function seasonStandings(ids: string[], me: string) {
  const sql = getSql();
  const picks = await sql`
    SELECT user_id, user_name, tournament_id, player_name FROM fade_picks
    WHERE user_id = ANY(${ids})` as (PickRow & { tournament_id: string })[];

  const tids = [...new Set(picks.map(p => p.tournament_id))];
  const earningsByTid = new Map<string, EarningsResp | null>();
  await Promise.all(tids.map(async t => earningsByTid.set(t, await earningsFor(t))));

  type Row = { user_id: string; user_name: string; wins: number; entered: number; settled: number };
  const users = new Map<string, Row>();
  const row = (p: { user_id: string; user_name: string }) => {
    const u = users.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, wins: 0, entered: 0, settled: 0 };
    users.set(p.user_id, u);
    return u;
  };

  for (const t of tids) {
    const table = earningsByTid.get(t);
    const entrants = new Map<string, { u: { user_id: string; user_name: string }; total: number }>();
    for (const p of picks.filter(p => p.tournament_id === t)) {
      const e = entrants.get(p.user_id) ?? { u: p, total: 0 };
      e.total += table?.players?.[nameKey(p.player_name)]?.earnings ?? 0;
      entrants.set(p.user_id, e);
    }
    for (const e of entrants.values()) row(e.u).entered += 1;
    if (!table?.settled) continue;
    for (const e of entrants.values()) row(e.u).settled += 1;
    const best = Math.min(...[...entrants.values()].map(e => e.total));
    for (const e of entrants.values()) if (e.total === best) row(e.u).wins += 1;
  }

  const standings = [...users.values()].sort((a, b) =>
    b.wins - a.wins || b.settled - a.settled || a.user_name.localeCompare(b.user_name));
  return Response.json({ season: true, standings, me });
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const tid = url.searchParams.get("tournament_id")?.toUpperCase();
  const groupId = Number(url.searchParams.get("group_id") || 0);
  const ids = await visibleUserIds(userId, groupId || undefined);
  if (!ids) {
    return Response.json({ error: "Not a member of this group." }, { status: 403 });
  }
  if (!tid) return seasonStandings(ids, userId);

  // Locked yet? Events off the open list are past, therefore visible.
  let locked = true;
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (res.ok) {
      const { events } = await res.json();
      const ev = (events ?? []).find((e: { tournament_id: string }) => e.tournament_id === tid);
      if (ev) locked = !!ev.locked;
    }
  } catch { /* treat as locked/past */ }

  const sql = getSql();
  const picks = await sql`
    SELECT user_id, user_name, player_name FROM fade_picks
    WHERE tournament_id = ${tid} AND user_id = ANY(${ids})
    ORDER BY user_name, created_at` as PickRow[];

  let table: EarningsResp | null = null;
  if (locked) {
    try {
      const res = await fetch(`${MODEL_API}/api/results/earnings?tournament_id=${tid}`,
        { next: { revalidate: 300 } });
      if (res.ok) table = await res.json();
    } catch { /* board shows pending */ }
  }

  type Row = { user_id: string; user_name: string; total: number | null;
    fades: { player: string; earnings: number | null; position: string | null }[] };
  const users = new Map<string, Row>();

  for (const p of picks) {
    const u = users.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, total: null, fades: [] };
    if (!locked) {
      u.fades.push({ player: "hidden", earnings: null, position: null });
    } else {
      const hit = table?.players?.[nameKey(p.player_name)];
      const earnings = table?.settled ? (hit?.earnings ?? 0) : null;
      u.fades.push({ player: p.player_name, earnings, position: hit?.position ?? null });
      if (earnings != null) u.total = (u.total ?? 0) + earnings;
    }
    users.set(p.user_id, u);
  }

  // Ascending: the person whose fades earned the LEAST is on top.
  const standings = [...users.values()].sort((a, b) =>
    (a.total ?? Infinity) - (b.total ?? Infinity) || a.user_name.localeCompare(b.user_name));

  return Response.json({
    tournament_id: tid, locked,
    settled: !!table?.settled,
    earnings_estimated: !!table?.earnings_estimated,
    standings, me: userId,
  });
}
