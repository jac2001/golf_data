/**
 * /api/leagues/[id]/advice?tid=X — spend / save verdicts for MY slate.
 *
 * Render values the field once per event (/api/advice/values, shared);
 * this route applies the signed-in member's uses left with Jack's
 * golferVerdict (lib/advice.ts). Private by construction: it only ever
 * reads the caller's own picks, and returns nothing once the slate
 * locks — advice is for deciding, not for second-guessing friends.
 *
 * Uses left exclude this slate's own picks, so a golfer you've already
 * picked this week is judged on the decision you made ("was spending
 * him right?"), not on the use it consumed.
 */
import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameKey } from "@/lib/names";
import { adviseSlate, GolferValue } from "@/lib/advice";

type League = { id: number; tours: string[]; uses_per_player: number; players_per_week: number; uses_scope: string };
type Values = { tournament_id: string; golfers: (Omit<GolferValue, "key"> & { world_rank: number | null })[] };

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const leagueId = Number((await params).id);
  const tid = (new URL(req.url).searchParams.get("tid") ?? "").toUpperCase();
  if (!tid) return Response.json({ error: "tid required" }, { status: 400 });

  const sql = getSql();
  const leagues = await sql`
    SELECT l.id, l.tours, l.uses_per_player, l.players_per_week, l.uses_scope
    FROM leagues l JOIN group_members m ON m.group_id = l.group_id
    WHERE l.id = ${leagueId} AND m.user_id = ${userId}` as League[];
  const league = leagues[0];
  if (!league) return Response.json({ error: "Not your league" }, { status: 403 });

  // Lock state from the server's open list; off the list or unknown → no advice.
  let locked = true;
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    const ev = res.ok ? ((await res.json()).events ?? []).find((e: { tournament_id: string }) => e.tournament_id === tid) : null;
    locked = !ev || !!ev.locked;
  } catch { /* stays locked */ }
  if (locked) return Response.json({ tid, locked: true, verdicts: {} });

  let values: Values | null = null;
  try {
    // Shared-use season: a use spent here can't be spent on the other tour,
    // so windows on BOTH tours compete for it.
    const toursParam = league.uses_scope !== "tour" && league.tours.length > 1 ? `&tours=${league.tours.join(",")}` : "";
    const res = await fetch(`${MODEL_API}/api/advice/values?tournament_id=${encodeURIComponent(tid)}&limit=80${toursParam}`,
      { next: { revalidate: 600 } });
    values = res.ok ? await res.json() as Values : null;
  } catch { /* no advice this time */ }
  if (!values || String(values.tournament_id).toUpperCase() !== tid) {
    return Response.json({ tid, locked: false, verdicts: {}, unavailable: true });
  }

  const allTours = league.uses_scope !== "tour";
  const spent = await sql`
    SELECT player_key, count(*)::int AS n FROM league_picks
    WHERE league_id = ${league.id} AND user_id = ${userId} AND tournament_id <> ${tid}
      AND (${allTours} OR left(tournament_id, 1) = ${tid.slice(0, 1)})
    GROUP BY player_key` as { player_key: string; n: number }[];
  const usesLeft: Record<string, number> = {};
  for (const s of spent) usesLeft[s.player_key] = Math.max(0, league.uses_per_player - s.n);

  const field: GolferValue[] = values.golfers.map(g => ({ ...g, key: nameKey(g.player_name) }));
  const { verdicts } = adviseSlate(field, usesLeft, league.uses_per_player, league.players_per_week);

  const byName: Record<string, { verdict: string; reason: string; save_for?: string }> = {};
  for (const g of field) {
    const v = verdicts[g.key];
    if (v) byName[g.player_name] = { verdict: v.verdict, reason: v.reason, ...(v.saveFor ? { save_for: v.saveFor.name } : {}) };
  }
  return Response.json({ tid, locked: false, verdicts: byName });
}
