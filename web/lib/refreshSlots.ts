/**
 * refreshSlots.ts — which data-refresh slots GitHub dropped.
 * ==========================================================
 * The data-refresh workflow's Mon–Wed cron slots fetch what the week's
 * predictions need (DataGolf pre-tournament, odds, field). GitHub skips
 * scheduled runs now and then; on Oct 20 it dropped Tuesday's 06:00 CT
 * slot entirely and the pipeline found last week's DataGolf file. The
 * watchdog (/api/watchdog, daily 15:00 UTC) asks this function which
 * slots passed with no data-refresh run at all, and re-dispatches them.
 *
 * Pure function, no imports from "@/": `npm test` runs it.
 */

/** The slots that matter, in UTC (mirror .github/workflows/data-refresh.yml). */
export const SLOTS: { dow: number; hour: number; schedule: string }[] = [
  { dow: 1, hour: 11, schedule: "monday" },             // Mon 06:00 CT
  { dow: 2, hour: 11, schedule: "tuesday-morning" },    // Tue 06:00 CT
  { dow: 2, hour: 23, schedule: "tuesday-evening" },    // Tue 18:00 CT
  { dow: 3, hour: 11, schedule: "wednesday-morning" },  // Wed 06:00 CT
  { dow: 3, hour: 23, schedule: "wednesday-evening" },  // Wed 18:00 CT
];

/** How late a run can start and still count as that slot's run. */
export const GRACE_MS = 3 * 3_600_000;
/** Only slots this recent are worth re-running (older work is stale). */
export const LOOKBACK_MS = 30 * 3_600_000;
/** A run this long before the slot (an early dispatch) still covers it. */
const EARLY_MS = 15 * 60_000;

/**
 * Slots whose time is between LOOKBACK_MS ago and GRACE_MS ago with NO
 * data-refresh run created since (slot time - 15 min). A run of any kind
 * in that window counts: a later slot's run fetches the same inputs.
 * Returns the most recent missed slot only: one dispatch catches up.
 */
export function missedSlot(now: Date, runCreatedAt: string[]): string | null {
  const t = now.getTime();
  const runs = runCreatedAt.map(s => Date.parse(s)).filter(n => !Number.isNaN(n));
  const candidates: { at: number; schedule: string }[] = [];
  for (let back = 0; back <= 2; back++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - back));
    for (const s of SLOTS) {
      if (d.getUTCDay() !== s.dow) continue;
      const at = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), s.hour);
      if (t - at >= GRACE_MS && t - at <= LOOKBACK_MS) candidates.push({ at, schedule: s.schedule });
    }
  }
  candidates.sort((a, b) => b.at - a.at);
  const latest = candidates[0];
  if (!latest) return null;
  const covered = runs.some(r => r >= latest.at - EARLY_MS);
  return covered ? null : latest.schedule;
}
