/**
 * /api/leagues/[id]/standings — Let It Ride season standings.
 *
 * Every member's season total in real prize money, split by tour (PGA
 * and DPWT are separate slates, so each gets its own total alongside
 * the combined one). Grades through the same results/earnings endpoint
 * as every other game: settled money after Monday's settle, purse-split
 * projections from live positions during a tournament weekend.
 *
 * Reveal-at-lock: other members' picks for an unlocked event are left
 * out entirely (not just their earnings) — see lib/eventLocks.ts.
 * `my_uses` is the caller's per-golfer use count for the pick screen's
 * budget meter.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameKey } from "@/lib/names";
import { openEventLocks, pickVisible } from "@/lib/eventLocks";

type PickRow = { user_id: string; user_name: string; tournament_id: string; player_name: string; player_key: string };
type EarningsResp = {
  settled: boolean; projected?: boolean;
  players: Record<string, { player_name: string; earnings: number; position: string }>;
};
type EventLine = {
  tour: "pga" | "euro";
  picks: { player: string; earnings: number | null; position: string | null }[];
  event_total: number; settled: boolean; projected: boolean;
};
type MemberRow = {
  user_id: string; user_name: string;
  total: number; pga_total: number; euro_total: number;
  events: Record<string, EventLine>;
};

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const leagueId = Number((await params).id);

  const sql = getSql();
  const league = await sql`
    SELECT l.id, l.group_id, l.name, l.uses_per_player, l.players_per_week
    FROM leagues l JOIN group_members m ON m.group_id = l.group_id
    WHERE l.id = ${leagueId} AND m.user_id = ${userId}` as
    { id: number; group_id: number; name: string; uses_per_player: number; players_per_week: number }[];
  if (!league.length) return Response.json({ error: "Not your league" }, { status: 403 });

  const [allRaw, locks, rosterRaw] = await Promise.all([
    sql`SELECT user_id, user_name, tournament_id, player_name, player_key
        FROM league_picks WHERE league_id = ${leagueId}`,
    openEventLocks(),
    sql`SELECT user_id, user_name FROM group_members WHERE group_id = ${league[0].group_id}`,
  ]);
  const all = allRaw as PickRow[];
  const roster = rosterRaw as { user_id: string; user_name: string }[];

  // Uses count every pick you've made, locked or not — you're spending
  // budget the moment you pick. Keyed by player_key (nameKey), because
  // the two tours' field files spell the same golfer differently.
  const myUses: Record<string, number> = {};
  for (const p of all) if (p.user_id === userId) myUses[p.player_key] = (myUses[p.player_key] ?? 0) + 1;

  const picks = all.filter(p => pickVisible(locks, p.tournament_id, p.user_id, userId));

  // One earnings fetch per distinct event, not per pick.
  const tids = [...new Set(picks.map(p => p.tournament_id))];
  const earnings = new Map<string, EarningsResp>();
  await Promise.all(tids.map(async tid => {
    try {
      const res = await fetch(`${MODEL_API}/api/results/earnings?tournament_id=${tid}&projected=1`,
        { next: { revalidate: 120 } });
      if (res.ok) earnings.set(tid, await res.json());
    } catch { /* event stays pending */ }
  }));

  // Every member — and the model, which plays every league — appears
  // from week one, at $0 until their picks earn something.
  const members = new Map<string, MemberRow>();
  for (const r of [...roster, { user_id: "model", user_name: "The Model" }]) {
    members.set(r.user_id, { user_id: r.user_id, user_name: r.user_name || "Player",
      total: 0, pga_total: 0, euro_total: 0, events: {} });
  }
  for (const p of picks) {
    const m = members.get(p.user_id)
      ?? { user_id: p.user_id, user_name: p.user_name || (p.user_id === "model" ? "The Model" : "Player"),
           total: 0, pga_total: 0, euro_total: 0, events: {} };
    const tour: "pga" | "euro" = p.tournament_id.startsWith("E") ? "euro" : "pga";
    const ev = m.events[p.tournament_id] ?? { tour, picks: [], event_total: 0, settled: false, projected: false };
    const table = earnings.get(p.tournament_id);
    const hit = table?.players?.[nameKey(p.player_name)];
    const gradable = !!(table?.settled || table?.projected);
    const earned = gradable ? (hit?.earnings ?? 0) : null;
    ev.picks.push({ player: p.player_name, earnings: earned, position: hit?.position ?? null });
    if (earned != null) {
      ev.event_total += earned;
      m.total += earned;
      if (tour === "euro") m.euro_total += earned; else m.pga_total += earned;
      if (table?.settled) ev.settled = true;
      if (table?.projected) ev.projected = true;
    }
    m.events[p.tournament_id] = ev;
    members.set(p.user_id, m);
  }

  const standings = [...members.values()].sort((a, b) => b.total - a.total);
  return Response.json({
    league: league[0], standings, me: userId,
    my_uses: myUses, locks_unavailable: locks === null,
  });
}
