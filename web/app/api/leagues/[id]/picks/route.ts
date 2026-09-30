/**
 * /api/leagues/[id]/picks — Let It Ride picks for one slate.
 *
 * GET    ?tid=X           → my picks for that slate, plus everyone's
 *                           once it locks (reveal-at-lock).
 * POST   {tid, player_name} → add a pick. Rules: validateLeaguePick()
 *                           (lib/leagueRules.ts) decides and explains;
 *                           the INSERT re-checks both budget counts in
 *                           one statement so concurrent requests can't
 *                           overspend.
 * DELETE {tid, player_name} → drop a pick before lock (refunds the use).
 */
import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { validateLeaguePick } from "@/lib/leagueRules";
import { nameKey } from "@/lib/names";
import { openEventLocks } from "@/lib/eventLocks";

type League = {
  id: number; group_id: number; season_start: string; season_end: string | null;
  tours: string[]; uses_per_player: number; players_per_week: number; status: string;
  uses_scope: "golfer" | "tour";
};
type Slate = { tid: string; tour: string; locked: boolean; startDate: string };

async function memberLeague(leagueId: number, userId: string): Promise<League | null> {
  const sql = getSql();
  const rows = await sql`
    SELECT l.id, l.group_id, l.season_start::text, l.season_end::text, l.tours,
           l.uses_per_player, l.players_per_week, l.status, l.uses_scope
    FROM leagues l JOIN group_members m ON m.group_id = l.group_id
    WHERE l.id = ${leagueId} AND m.user_id = ${userId}` as League[];
  return rows[0] ?? null;
}

/** The server decides what's pickable and when it locks — never the client. */
async function slate(tid: string): Promise<Slate | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    const e = (events ?? []).find((x: { tournament_id: string }) => x.tournament_id === tid.toUpperCase());
    return e ? { tid: e.tournament_id, tour: e.tour, locked: !!e.locked, startDate: String(e.start_date) } : null;
  } catch {
    return null;
  }
}

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const league = await memberLeague(Number((await params).id), userId);
  if (!league) return Response.json({ error: "Not your league" }, { status: 403 });

  const tid = (new URL(req.url).searchParams.get("tid") ?? "").toUpperCase();
  if (!tid) return Response.json({ error: "tid required" }, { status: 400 });
  // Reading is allowed for past slates too (a season outlives the open
  // window). Lock status comes from the fail-closed rule: an event off an
  // AVAILABLE open list is past, so locked; an unavailable list shows
  // only my own picks.
  const locks = await openEventLocks();
  const s = await slate(tid) ?? { tid, tour: tid.startsWith("E") ? "euro" : "pga",
    locked: locks ? (locks.get(tid) ?? true) : false, startDate: "" };

  const sql = getSql();
  const rows = s.locked
    ? await sql`
        SELECT user_id, user_name, player_name FROM league_picks
        WHERE league_id = ${league.id} AND tournament_id = ${s.tid} ORDER BY user_name, created_at`
    : await sql`
        SELECT user_id, user_name, player_name FROM league_picks
        WHERE league_id = ${league.id} AND tournament_id = ${s.tid} AND user_id = ${userId}
        ORDER BY created_at`;
  return Response.json({ tid: s.tid, tour: s.tour, locked: s.locked, picks: rows });
}

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const league = await memberLeague(Number((await params).id), userId);
  if (!league || league.status !== "active") {
    return Response.json({ error: "No active league" }, { status: 403 });
  }

  const body = await req.json().catch(() => ({}));
  const tid = String(body.tid ?? "").toUpperCase();
  const golfer = String(body.player_name ?? "").trim();
  if (!tid || !golfer) return Response.json({ error: "tid and player_name required" }, { status: 400 });
  const s = await slate(tid);
  if (!s) return Response.json({ error: "Unknown or closed event" }, { status: 404 });

  const key = nameKey(golfer);
  // Which picks spend the same budget: every tour ('golfer' scope) or
  // only this slate's tour ('tour' scope). Tour is the tid's prefix.
  const allTours = league.uses_scope !== "tour";
  const prefix = s.tid.slice(0, 1);
  const sql = getSql();
  const [{ uses, slate_n, dup }] = await sql`
    SELECT
      count(*) FILTER (WHERE player_key = ${key}
        AND (${allTours} OR left(tournament_id, 1) = ${prefix}))::int                AS uses,
      count(*) FILTER (WHERE tournament_id = ${s.tid})::int                          AS slate_n,
      count(*) FILTER (WHERE tournament_id = ${s.tid} AND player_key = ${key})::int  AS dup
    FROM league_picks WHERE league_id = ${league.id} AND user_id = ${userId}` as
    { uses: number; slate_n: number; dup: number }[];

  const verdict = validateLeaguePick({
    locked: s.locked,
    inSeason: s.startDate >= league.season_start
      && (league.season_end == null || s.startDate <= league.season_end),
    tourInLeague: league.tours.includes(s.tour),
    alreadyPicked: dup > 0,
    usesOfThisGolfer: uses,
    picksThisSlate: slate_n,
    usesPerPlayer: league.uses_per_player,
    playersPerWeek: league.players_per_week,
    golferName: golfer,
  });
  if (!verdict.ok) return Response.json({ error: verdict.error }, { status: verdict.status });

  const user = await currentUser();
  const userName = user?.firstName || user?.username || "Player";
  // Backstop: inserts only if BOTH budgets still hold at write time. The
  // advisory lock serializes one member's pick writes — without it,
  // concurrent inserts each count the same stale total and all succeed
  // (race test: 5 stored against a limit of 3). Per-(league, member), so
  // other members' picks never wait. Released at commit.
  const [, inserted] = await sql.transaction([
    sql`SELECT pg_advisory_xact_lock(hashtextextended(${`${league.id}:${userId}`}, 0))`,
    sql`
      INSERT INTO league_picks (league_id, user_id, user_name, tournament_id, player_name, player_key)
      SELECT ${league.id}, ${userId}, ${userName}, ${s.tid}, ${golfer}, ${key}
      WHERE (SELECT count(*) FROM league_picks
             WHERE league_id = ${league.id} AND user_id = ${userId} AND player_key = ${key}
               AND (${allTours} OR left(tournament_id, 1) = ${prefix}))
            < ${league.uses_per_player}
        AND (SELECT count(*) FROM league_picks
             WHERE league_id = ${league.id} AND user_id = ${userId} AND tournament_id = ${s.tid})
            < ${league.players_per_week}
      ON CONFLICT DO NOTHING
      RETURNING id`,
  ]) as [unknown, { id: number }[]];
  if (!inserted.length) {
    return Response.json({ error: "That pick no longer fits your budget — refresh and try again" }, { status: 409 });
  }
  return Response.json({ ok: true }, { status: 201 });
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const league = await memberLeague(Number((await params).id), userId);
  if (!league) return Response.json({ error: "Not your league" }, { status: 403 });

  const body = await req.json().catch(() => ({}));
  const tid = String(body.tid ?? "").toUpperCase();
  const s = tid ? await slate(tid) : null;
  if (!s) return Response.json({ error: "Unknown or closed event" }, { status: 404 });
  if (s.locked) return Response.json({ error: "Picks are locked — the event has started" }, { status: 409 });

  const sql = getSql();
  await sql`
    DELETE FROM league_picks
    WHERE league_id = ${league.id} AND user_id = ${userId}
      AND tournament_id = ${s.tid} AND player_key = ${nameKey(String(body.player_name ?? ""))}`;
  return Response.json({ ok: true });
}
