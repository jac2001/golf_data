/**
 * /api/friends/fadeboard?tournament_id=X — Fade Game leaderboard.
 * ================================================================
 * Everyone's fades for one event, graded by real earnings, sorted
 * ASCENDING — lowest combined earnings wins. Fades stay hidden until
 * the event locks (same anti-copy rule as every other game).
 *
 * Per-event only, on purpose: a season SUM is broken for this game —
 * lower is better, so the fewer events you enter the better you look,
 * and "never play" becomes the optimal season. (Same incentive-design
 * trap as unrestricted fading; a fair season format — average per
 * entered event, or event wins — can come later.)
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

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const tid = url.searchParams.get("tournament_id")?.toUpperCase();
  if (!tid) return Response.json({ error: "tournament_id required" }, { status: 400 });
  const groupId = Number(url.searchParams.get("group_id") || 0);
  const ids = await visibleUserIds(userId, groupId || undefined);
  if (!ids) {
    return Response.json({ error: "Not a member of this group." }, { status: 403 });
  }

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
