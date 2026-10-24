/**
 * recordHistory.ts: load one Let It Ride season's record history (server only).
 * ==============================================================================
 * Fetches what lib/recordWeeks.ts needs: the season's schedule on every tour
 * it plays (between season_start and season_end), every pick, and the settled
 * results of each event someone picked. Fails closed: if a schedule can't be
 * loaded, weeks could go missing and streaks bridge across them, so there is
 * no history rather than a wrong one. Rebuilt on every call (nothing stored),
 * so a corrected settlement rewrites the records.
 *
 * Callers check group membership first.
 */
import { getSql, MODEL_API } from "@/lib/db";
import type { RecordScope } from "@/lib/groupRecords";
import { buildRecordWeeks, type EventResults, type RecordHistory, type RecordPick, type ScheduledEvent } from "@/lib/recordWeeks";

export type SeasonRow = { id: number; group_id: number; season_start: string; season_end: string | null; tours: string[] };

const dayBefore = (d: string) => new Date(Date.parse(`${d}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);

/** Today in the PGA TOUR's day (ET), YYYY-MM-DD. */
function tourToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

async function seasonSchedule(season: SeasonRow): Promise<ScheduledEvent[] | null> {
  const tours = season.tours.filter(t => t === "pga" || t === "euro");
  const lists = await Promise.all(tours.map(async tour => {
    try {
      const res = await fetch(`${MODEL_API}/api/schedule/upcoming?tour=${tour}&after=${dayBefore(season.season_start)}&limit=52`,
        { next: { revalidate: 3600 } });
      if (!res.ok) return null;
      const d = await res.json() as { events?: { tournament_id: string; name: string; start_date: string }[] };
      return d.events ?? null;
    } catch { return null; }
  }));
  if (lists.some(l => l === null)) return null;
  return lists.flat().map(e => ({ tournamentId: String(e!.tournament_id).toUpperCase(), name: e!.name, startDate: String(e!.start_date).slice(0, 10) }))
    // Provisional DPWT ids (E2027T01211) never take picks; drop them.
    .filter(e => e.tournamentId[5] !== "T" && (!season.season_end || e.startDate <= season.season_end));
}

export async function loadRecordHistory(season: SeasonRow): Promise<RecordHistory | null> {
  const sql = getSql();
  const [events, picksRaw] = await Promise.all([
    seasonSchedule(season),
    sql`SELECT user_id, tournament_id, player_name, player_id FROM league_picks WHERE league_id = ${season.id}`,
  ]);
  if (!events) return null;
  const picks = picksRaw as RecordPick[];
  const today = tourToday();
  const started = new Set(events.filter(e => e.startDate <= today).map(e => e.tournamentId));
  const tids = [...new Set(picks.map(p => p.tournament_id.toUpperCase()))].filter(t => started.has(t));

  const results = new Map<string, EventResults | null>();
  await Promise.all(tids.map(async tid => {
    try {
      // Settled results only (no ?projected): a weekend's estimates never grade a record.
      const res = await fetch(`${MODEL_API}/api/results/earnings?tournament_id=${tid}`, { next: { revalidate: 300 } });
      if (!res.ok) { results.set(tid, null); return; }
      const d = await res.json() as { settled?: boolean; earnings_estimated?: boolean; players?: EventResults["players"] };
      results.set(tid, { settled: !!d.settled, estimated: !!d.earnings_estimated, players: d.players ?? {} });
    } catch { results.set(tid, null); }
  }));

  const scope: RecordScope = { groupId: String(season.group_id), seasonId: String(season.id), mode: "let-it-ride" };
  return buildRecordWeeks(scope, events, picks, results, today);
}
