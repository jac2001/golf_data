/**
 * /api/friends/roundboard — Round Game leaderboards.
 * ===================================================
 * ?tournament_id → that event's board: everyone's picks per LOCKED round
 * (unlocked rounds stay hidden — same anti-copy rule as the 3-pick game)
 * with to-par scores from the model API's rounds table. A locked round
 * with a score missing (cut, WD, snapshot not settled) shows the +5
 * penalty only once the round is complete for the field.
 * No param → season totals across all events.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";

const PENALTY = 5;
const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

type PickRow = { user_id: string; user_name: string; tournament_id: string; round: number; player_name: string };
type RoundsResp = { rounds_available: number;
  players: Record<string, { rounds: Record<string, number> }> };

async function roundsFor(tid: string): Promise<RoundsResp | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/rounds?tournament_id=${tid}`,
      { next: { revalidate: 300 } });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const tid = url.searchParams.get("tournament_id")?.toUpperCase() ?? null;
  const sql = getSql();

  // Which rounds are locked (visible) per event comes from the open list;
  // finished events are entirely visible.
  let lockedRounds = new Map<string, number>();  // tid -> highest locked round (4 = all)
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (res.ok) {
      const { events } = await res.json();
      for (const e of events ?? []) {
        const start = new Date(`${String(e.start_date).slice(0, 10)}T00:00:00`);
        const days = Math.floor((Date.now() - start.getTime()) / 86400000) + 1;
        lockedRounds.set(e.tournament_id, Math.max(0, Math.min(4, days)));
      }
    }
  } catch { /* events not in the open list are past -> fully visible */ }

  const picks = (tid
    ? await sql`SELECT user_id, user_name, tournament_id, round, player_name
                FROM round_picks WHERE tournament_id = ${tid}`
    : await sql`SELECT user_id, user_name, tournament_id, round, player_name
                FROM round_picks`) as PickRow[];

  const tids = [...new Set(picks.map(p => p.tournament_id))];
  const roundsByTid = new Map<string, RoundsResp | null>();
  await Promise.all(tids.map(async t => roundsByTid.set(t, await roundsFor(t))));

  type Row = { user_id: string; user_name: string; total: number; scored: number;
    rounds: Record<string, { player: string; score: number | null; visible: boolean }> };
  const users = new Map<string, Row>();

  for (const p of picks) {
    const maxLocked = lockedRounds.get(p.tournament_id) ?? 4;
    const visible = p.round <= maxLocked;
    const table = roundsByTid.get(p.tournament_id);
    const avail = table?.rounds_available ?? 0;
    const hit = table?.players?.[nameKey(p.player_name)];
    let score: number | null = null;
    if (visible) {
      const s = hit?.rounds?.[String(p.round)];
      if (s !== undefined) score = s;
      // Penalty only once the field has finished that round — before that
      // a missing score just means "on course".
      else if (p.round < avail || (p.round <= avail && maxLocked > p.round)) score = PENALTY;
    }
    const u = users.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, total: 0, scored: 0, rounds: {} };
    const key = tid ? String(p.round) : `${p.tournament_id}·R${p.round}`;
    u.rounds[key] = { player: visible ? p.player_name : "hidden", score, visible };
    if (score != null) { u.total += score; u.scored += 1; }
    users.set(p.user_id, u);
  }

  const standings = [...users.values()].sort((a, b) =>
    (b.scored === 0 ? -1 : 0) - (a.scored === 0 ? -1 : 0) || a.total - b.total);
  return Response.json({ tournament_id: tid, standings, me: userId });
}
