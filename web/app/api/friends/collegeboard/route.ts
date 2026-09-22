/**
 * /api/friends/collegeboard — College Game leaderboards.
 * =======================================================
 * ?tournament_id=X: everyone's school for that event, scored by the
 * school's TOP TWO alumni earnings (settled or live-projected), sorted
 * descending. Schools hidden until lock, same anti-copy rule as every
 * game. No param: season standings in EVENT WINS (ties all credited).
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";

type PickRow = { user_id: string; user_name: string; tournament_id: string; school: string };
type EarningsResp = {
  settled: boolean; projected?: boolean; earnings_estimated?: boolean;
  players: Record<string, { player_name: string; earnings: number; position: string }>;
};
type School = { school: string; players: string[] };

const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { next: { revalidate: 120 } });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

/** A school's score: its best two alumni checks that week. */
function schoolScore(school: string, rosters: School[], table: EarningsResp | null):
  { total: number | null; counted: { player: string; earnings: number; position: string }[] } {
  if (!table || (!table.settled && !table.projected)) return { total: null, counted: [] };
  const roster = rosters.find(s => s.school === school)?.players ?? [];
  const earned = roster.map(p => {
    const hit = table.players?.[nameKey(p)];
    return { player: p, earnings: hit?.earnings ?? 0, position: hit?.position ?? "—" };
  }).sort((a, b) => b.earnings - a.earnings).slice(0, 2);
  return { total: earned.reduce((s, e) => s + e.earnings, 0), counted: earned };
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const tid = url.searchParams.get("tournament_id")?.toUpperCase();
  const groupId = Number(url.searchParams.get("group_id") || 0);
  const ids = await visibleUserIds(userId, groupId || undefined);
  if (!ids) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  const sql = getSql();

  if (!tid) {
    // Season: event wins per settled event.
    const picks = await sql`
      SELECT user_id, user_name, tournament_id, school FROM college_picks
      WHERE user_id = ANY(${ids})` as PickRow[];
    const tids = [...new Set(picks.map(p => p.tournament_id))];
    type Row = { user_id: string; user_name: string; wins: number; entered: number };
    const users = new Map<string, Row>();
    const row = (p: PickRow) => {
      const u = users.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, wins: 0, entered: 0 };
      users.set(p.user_id, u); return u;
    };
    for (const t of tids) {
      const [table, rosterResp] = await Promise.all([
        fetchJson<EarningsResp>(`${MODEL_API}/api/results/earnings?tournament_id=${t}`),
        fetchJson<{ schools: School[] }>(`${MODEL_API}/api/colleges/field?tournament_id=${t}`),
      ]);
      const rosters = rosterResp?.schools ?? [];
      const entrants = picks.filter(p => p.tournament_id === t);
      for (const p of entrants) row(p).entered += 1;
      if (!table?.settled) continue;
      const totals = entrants.map(p => ({ p, total: schoolScore(p.school, rosters, table).total ?? 0 }));
      const best = Math.max(...totals.map(t2 => t2.total));
      for (const t2 of totals) if (t2.total === best) row(t2.p).wins += 1;
    }
    const standings = [...users.values()].sort((a, b) => b.wins - a.wins || a.user_name.localeCompare(b.user_name));
    return Response.json({ season: true, standings, me: userId });
  }

  // Per-event board.
  let locked = true;
  const open = await fetchJson<{ events: { tournament_id: string; locked: boolean }[] }>(`${MODEL_API}/api/events/open`);
  const ev = (open?.events ?? []).find(e => e.tournament_id === tid);
  if (ev) locked = !!ev.locked;

  const picks = await sql`
    SELECT user_id, user_name, school FROM college_picks
    WHERE tournament_id = ${tid} AND user_id = ANY(${ids})
    ORDER BY user_name` as { user_id: string; user_name: string; school: string }[];

  let table: EarningsResp | null = null;
  let rosters: School[] = [];
  if (locked) {
    [table, rosters] = await Promise.all([
      fetchJson<EarningsResp>(`${MODEL_API}/api/results/earnings?tournament_id=${tid}&projected=1`),
      fetchJson<{ schools: School[] }>(`${MODEL_API}/api/colleges/field?tournament_id=${tid}`).then(r => r?.schools ?? []),
    ]);
  }

  const standings = picks.map(p => {
    if (!locked) return { user_id: p.user_id, user_name: p.user_name, school: "hidden", total: null, counted: [] };
    const { total, counted } = schoolScore(p.school, rosters, table);
    return { user_id: p.user_id, user_name: p.user_name, school: p.school, total, counted };
  }).sort((a, b) => (b.total ?? -1) - (a.total ?? -1));

  return Response.json({
    tournament_id: tid, locked,
    settled: !!table?.settled, projected: !!table?.projected,
    standings, me: userId,
  });
}
