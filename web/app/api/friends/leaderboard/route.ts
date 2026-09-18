/**
 * /api/friends/leaderboard — season standings for the Friends Game.
 * ==================================================================
 * Grades every pick against real tournament earnings: for each event
 * that has picks, pull the settled earnings table from the model API
 * and credit each user their players' winnings. Ungraded (future or
 * in-progress) events show as pending.
 */

import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";

type PickRow = { user_id: string; user_name: string; tournament_id: string; player_name: string };
type EarningsResp = {
  settled: boolean;
  players: Record<string, { player_name: string; earnings: number; position: string }>;
};

const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const sql = getSql();

  // ?group_id=N scopes the board to one group's members (membership checked).
  const groupId = Number(new URL(req.url).searchParams.get("group_id") || 0);
  let picks: PickRow[];
  if (groupId) {
    const members = await sql`
      SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
    const ids = members.map(m => m.user_id);
    if (!ids.includes(userId)) {
      return Response.json({ error: "Not a member of this group." }, { status: 403 });
    }
    ids.push("model");  // The Model plays in every group
    picks = await sql`
      SELECT user_id, user_name, tournament_id, player_name FROM picks
      WHERE user_id = ANY(${ids})` as PickRow[];
  } else {
    picks = await sql`
      SELECT user_id, user_name, tournament_id, player_name FROM picks` as PickRow[];
  }

  // One earnings fetch per distinct event, not per pick.
  const tids = [...new Set(picks.map(p => p.tournament_id))];
  const earningsByTid = new Map<string, EarningsResp>();
  await Promise.all(tids.map(async tid => {
    try {
      const res = await fetch(`${MODEL_API}/api/results/earnings?tournament_id=${tid}`,
        { next: { revalidate: 300 } });
      if (res.ok) earningsByTid.set(tid, await res.json());
    } catch { /* event stays pending */ }
  }));

  type UserRow = {
    user_id: string; user_name: string; total: number;
    events: Record<string, { picks: { player: string; earnings: number | null; position: string | null }[]; event_total: number; settled: boolean }>;
  };
  const users = new Map<string, UserRow>();

  for (const p of picks) {
    const u = users.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, total: 0, events: {} };
    const ev = u.events[p.tournament_id] ?? { picks: [], event_total: 0, settled: false };
    const table = earningsByTid.get(p.tournament_id);
    const hit = table?.players?.[nameKey(p.player_name)];
    const earnings = table?.settled ? (hit?.earnings ?? 0) : null;
    ev.picks.push({ player: p.player_name, earnings, position: hit?.position ?? null });
    if (earnings != null) { ev.event_total += earnings; u.total += earnings; ev.settled = true; }
    u.events[p.tournament_id] = ev;
    users.set(p.user_id, u);
  }

  const standings = [...users.values()].sort((a, b) => b.total - a.total);
  return Response.json({ standings, me: userId });
}
