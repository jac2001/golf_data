/**
 * /api/match?group_id=N — the group match center.
 *
 * Designed around one question: "what needs to happen for me to beat my
 * friends this weekend?" For each tour's current event in the group's
 * Let It Ride season it returns the group ranked by money (projected
 * from DataGolf's live board during play, final once settled), you, your
 * closest rival, the gap, which of your golfers moving up one spot would
 * close it, and how the group stands against the model. College Game:
 * your school, its two counting alumni, and the school race.
 *
 * Reveal-at-lock applies: before an event locks you see only your own
 * picks (lib/eventLocks.ts, fail-closed).
 */
import { auth } from "@clerk/nextjs/server";
import { getSql, MODEL_API } from "@/lib/db";
import { nameKey } from "@/lib/names";
import { summarizeSlate, ranked, lastName as last } from "@/lib/matchCore";
import { openEventLocks, pickVisible } from "@/lib/eventLocks";

type Ev = { tournament_id: string; name: string; tour: "pga" | "euro"; start_date: string;
  locked: boolean; finished: boolean };
type PlayerMoney = { player_name: string; earnings: number; position: string;
  up_one?: number; thru?: string; today?: number | null; to_par?: number | null; round?: number | null };
type Earnings = { settled: boolean; projected?: boolean; data_updated?: string; data_updated_utc?: string;
  players: Record<string, PlayerMoney> };

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

async function api<T>(path: string, revalidate = 120): Promise<T | null> {
  try {
    const res = await fetch(`${MODEL_API}${path}`, { next: { revalidate } });
    return res.ok ? await res.json() as T : null;
  } catch { return null; }
}


export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const groupId = Number(new URL(req.url).searchParams.get("group_id"));
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });

  const sql = getSql();
  const roster = await sql`
    SELECT user_id, user_name FROM group_members WHERE group_id = ${groupId}` as
    { user_id: string; user_name: string }[];
  if (!roster.some(m => m.user_id === userId)) {
    return Response.json({ error: "Not a member of this group" }, { status: 403 });
  }
  const grp = await sql`SELECT name FROM groups WHERE id = ${groupId}` as { name: string }[];
  const leagueRows = await sql`
    SELECT id, name, tours FROM leagues WHERE group_id = ${groupId} AND status = 'active'` as
    { id: number; name: string; tours: string[] }[];
  const league = leagueRows[0] ?? null;

  const [open, locks] = await Promise.all([
    api<{ events: Ev[] }>("/api/events/open"),
    openEventLocks(),
  ]);
  const events = open?.events ?? [];

  // Focus event per tour: live beats this week's open slate beats the
  // most recent final — the weekend you'd actually want to look at.
  const focusFor = (tour: string): Ev | null => {
    const mine = events.filter(e => e.tour === tour);
    return mine.find(e => e.locked && !e.finished)
      ?? mine.find(e => !e.locked)
      ?? [...mine].filter(e => e.finished).sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
      ?? null;
  };

  const nameOf = (uid: string) =>
    uid === "model" ? "The Model" : (roster.find(m => m.user_id === uid)?.user_name || "Player");

  const slates = [];
  for (const tour of league?.tours ?? []) {
    const ev = focusFor(tour);
    if (!ev || !league) continue;
    const tid = ev.tournament_id.toUpperCase();
    const [picksRaw, table] = await Promise.all([
      sql`SELECT user_id, player_name, reason FROM league_picks
          WHERE league_id = ${league.id} AND tournament_id = ${tid}`,
      api<Earnings>(`/api/results/earnings?tournament_id=${tid}&projected=1`),
    ]);
    const picks = picksRaw as { user_id: string; player_name: string; reason: string | null }[];
    const visible = picks.filter(p => pickVisible(locks, tid, p.user_id, userId));
    const graded = !!(table?.settled || table?.projected);
    const sum = summarizeSlate(visible, table?.players ?? null, graded, nameOf, userId);

    slates.push({
      tournament_id: tid, name: ev.name, tour,
      status: ev.finished ? (table?.settled ? "final" : "settling") : ev.locked ? "live" : "open",
      start_date: ev.start_date,
      projected: !table?.settled && !!table?.projected,
      data_updated: table?.data_updated ?? "",
      data_updated_utc: table?.data_updated_utc ?? "",
      me_id: userId, ...sum,
    });
  }

  // ── College Game: the school race at the PGA focus event ─────────────
  let college = null;
  const pgaEv = focusFor("pga");
  if (pgaEv) {
    const tid = pgaEv.tournament_id.toUpperCase();
    const ids = [...roster.map(m => m.user_id), "model"];
    const [cpicksRaw, field, table] = await Promise.all([
      sql`SELECT user_id, school FROM college_picks
          WHERE tournament_id = ${tid} AND user_id = ANY(${ids})`,
      api<{ schools: { school: string; players: string[] }[] }>(`/api/colleges/field?tournament_id=${tid}`, 600),
      api<Earnings>(`/api/results/earnings?tournament_id=${tid}&projected=1`),
    ]);
    const cpicks = cpicksRaw as { user_id: string; school: string }[];
    const visible = cpicks.filter(p => pickVisible(locks, tid, p.user_id, userId));
    const graded = !!(table?.settled || table?.projected);
    const score = (school: string) => {
      const alumni = (field?.schools ?? []).find(s => s.school === school)?.players ?? [];
      const counted = alumni.map(n => {
        const hit = table?.players?.[nameKey(n)];
        return { name: n, position: hit?.position ?? "—", earnings: graded ? (hit?.earnings ?? 0) : 0,
                 thru: hit?.thru ?? "", to_par: hit?.to_par ?? null, round: hit?.round ?? null };
      }).sort((a, b) => b.earnings - a.earnings);
      return { counting: counted.slice(0, 2), bench: counted.slice(2, 4),
               total: counted.slice(0, 2).reduce((s, c) => s + c.earnings, 0) };
    };
    const lines = ranked(visible.map(p => ({ user_id: p.user_id, user_name: nameOf(p.user_id),
      school: p.school, ...score(p.school) })));
    const me = lines.find(l => l.user_id === userId) ?? null;
    let story = "";
    if (me && graded) {
      const above = lines.filter(l => l.total > me.total).sort((a, b) => a.total - b.total)[0];
      if (above) story = `${above.school} (${above.user_name}) leads you by ${money(above.total - me.total)}.`;
      else if (lines.length > 1) story = `${me.school} leads the school race.`;
      // A bench alumnus about to pass one of your counting two changes your score.
      const second = me.counting[1];
      const push = me.bench.find(b => second && b.earnings > 0 && b.earnings >= second.earnings * 0.8);
      if (push) story += ` ${last(push.name)} is close to becoming one of your two counting golfers.`;
    }
    college = {
      tournament_id: tid, name: pgaEv.name,
      status: pgaEv.finished ? (table?.settled ? "final" : "settling") : pgaEv.locked ? "live" : "open",
      projected: !table?.settled && !!table?.projected,
      lines, me_id: userId, story: story.trim(),
    };
  }

  return Response.json({
    group: { id: groupId, name: grp[0]?.name ?? "", members: roster.length },
    league: league ? { id: league.id, name: league.name } : null,
    slates, college, checked_at: new Date().toISOString(),
  });
}
