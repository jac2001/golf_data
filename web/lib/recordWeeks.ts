/**
 * recordWeeks.ts: Let It Ride history -> the RecordWeek rows Jack's
 * computeGroupRecords reads (docs/RECORDS_CHIRPS_WORKBOOK.md).
 * =====================================================================
 * Week membership is explicit: a week is the Monday-to-Sunday calendar
 * week an event STARTS in, built from the season's schedule (every tour
 * the season plays, between its start and end dates), never from
 * settlement time or adjacent tournament ids. Every scheduled week that
 * has begun gets exactly one row, including weeks nobody played and
 * weeks still pending, so a missed or unresolved week breaks streaks.
 *
 * Money is graded the way every scoring view grades it (resolvePick:
 * id first, then a unique name, never a guess). A week is:
 *   - pending   while any event someone picked isn't settled (or its
 *               results didn't load). Its entries are left empty: nothing
 *               about an unfinished week leaks through records.
 *   - complete  only if every pick resolved to a result row.
 *   - official  only if no event was paid from the purse table.
 * The model plays every season and is an entry like anyone else.
 *
 * Nothing is cached or incremented: the caller rebuilds from current
 * results every time, so a corrected settlement rewrites history.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */
import type { RecordScope, RecordWeek } from "./groupRecords.ts";
import { resolvePick } from "./resultLookup.ts";

export type ScheduledEvent = { tournamentId: string; name: string; startDate: string };   // YYYY-MM-DD
export type RecordPick = { user_id: string; tournament_id: string; player_name: string; player_id: string | null };
export type EventResults = {
  settled: boolean;
  estimated: boolean;
  players: Record<string, { player_name?: string | null; player_id?: string | null; earnings: number }>;
};

export type RecordHistory =
  | { ok: true; weeks: RecordWeek[]; events: Record<string, { tournamentId: string; name: string }[]> }
  | { ok: false; reason: "unplaced-pick"; tournamentId: string };

const DAY = 86_400_000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** The Monday (UTC calendar date) of the week a YYYY-MM-DD date falls in. */
export function weekOf(date: string): { weekId: string; order: number } {
  const ms = Date.parse(`${date}T00:00:00Z`);
  const mondayMs = ms - ((new Date(ms).getUTCDay() + 6) % 7) * DAY;
  // 1970-01-05 was a Monday: whole weeks since then, an integer that sorts.
  return { weekId: new Date(mondayMs).toISOString().slice(0, 10), order: Math.round((mondayMs - Date.parse("1970-01-05T00:00:00Z")) / (7 * DAY)) };
}

/**
 * @param events  the season's scheduled events (already limited to its tours
 *                and dates). Events that haven't started by `today` are left out.
 * @param results per tournament id; null = the results didn't load.
 * @param today   YYYY-MM-DD in the tour's day (an event starting today has begun).
 */
export function buildRecordWeeks(
  scope: RecordScope,
  events: readonly ScheduledEvent[],
  picks: readonly RecordPick[],
  results: ReadonlyMap<string, EventResults | null>,
  today: string,
): RecordHistory {
  const started = events.filter(e => ISO_DATE.test(e.startDate) && e.startDate <= today);
  const byTid = new Map(started.map(e => [e.tournamentId.toUpperCase(), e]));

  // A pick on an event outside the schedule can't be placed in a week.
  // Dropping it could hand someone else a win, so the history refuses.
  for (const p of picks) {
    const tid = p.tournament_id.toUpperCase();
    if (!byTid.has(tid) && !events.some(e => e.tournamentId.toUpperCase() === tid)) {
      return { ok: false, reason: "unplaced-pick", tournamentId: tid };
    }
  }

  const weekEvents = new Map<string, { order: number; events: ScheduledEvent[] }>();
  for (const e of byTid.values()) {
    const { weekId, order } = weekOf(e.startDate);
    const w = weekEvents.get(weekId) ?? { order, events: [] };
    w.events.push(e);
    weekEvents.set(weekId, w);
  }

  const weeks: RecordWeek[] = [];
  const labels: Record<string, { tournamentId: string; name: string }[]> = {};
  for (const [weekId, w] of [...weekEvents].sort((a, b) => a[1].order - b[1].order)) {
    const tids = new Set(w.events.map(e => e.tournamentId.toUpperCase()));
    const weekPicks = picks.filter(p => tids.has(p.tournament_id.toUpperCase()));
    const picked = [...new Set(weekPicks.map(p => p.tournament_id.toUpperCase()))];
    labels[weekId] = w.events
      .slice().sort((a, b) => (a.tournamentId.startsWith("R") ? 0 : 1) - (b.tournamentId.startsWith("R") ? 0 : 1))   // PGA first
      .map(e => ({ tournamentId: e.tournamentId.toUpperCase(), name: e.name }));

    const pending = picked.some(tid => !results.get(tid)?.settled);
    if (pending) {
      weeks.push({ scope, weekId, order: w.order, status: "pending", complete: false, official: false, entries: [] });
      continue;
    }
    let complete = true;
    const cents = new Map<string, number>();
    for (const p of weekPicks) {
      const table = results.get(p.tournament_id.toUpperCase())!;
      const { hit, unresolved } = resolvePick(table.players, p, "records");
      if (unresolved) complete = false;
      // Integer cents per golfer, then summed: no fractional-dollar ties.
      cents.set(p.user_id, (cents.get(p.user_id) ?? 0) + Math.round((hit?.earnings ?? 0) * 100));
    }
    const official = picked.every(tid => !results.get(tid)!.estimated);
    weeks.push({
      scope, weekId, order: w.order, status: "final", complete, official,
      entries: [...cents].map(([userId, earningsCents]) => ({ userId, earningsCents })),
    });
  }
  return { ok: true, weeks, events: labels };
}

/**
 * The latest week that has begun, and whether it may prompt a record chirp:
 * it must be final, complete, official and contested (2+ entries), and an
 * older qualifying week must exist (a first-ever baseline breaks nothing).
 * An unresolved latest week never falls back to an older one.
 */
export function latestWeekEligibility(weeks: readonly RecordWeek[]): { weekId: string | null; eligible: boolean } {
  if (!weeks.length) return { weekId: null, eligible: false };
  const ordered = [...weeks].sort((a, b) => a.order - b.order);
  const qualifies = (w: RecordWeek) => w.status === "final" && w.complete && w.official && w.entries.length >= 2;
  const latest = ordered[ordered.length - 1];
  return { weekId: latest.weekId, eligible: qualifies(latest) && ordered.slice(0, -1).some(qualifies) };
}
