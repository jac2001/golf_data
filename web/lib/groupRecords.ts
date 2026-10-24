/** Learning scaffold. Not wired to Match Center or database yet. */
export type RecordScope = { groupId: string; seasonId: string; mode: "let-it-ride" };
export type RecordWeek = {
  scope: RecordScope;
  /** Canonical calendar week; adapter combines ALL scheduled tours first. */
  weekId: string;
  order: number;
  status: "pending" | "final";
  complete: boolean;
  official: boolean;
  /** Includes the model when it played. Amounts are integer USD cents. */
  entries: readonly { userId: string; earningsCents: number }[];
};
export type RecordValue = { value: number; holderIds: string[] };
export type GroupRecords = {
  wins: RecordValue | null;
  streak: RecordValue | null;
  earnings: RecordValue | null;
};
export const emptyRecords = (): GroupRecords => ({ wins: null, streak: null, earnings: null });

/**
 * TODO(Jack): computeGroupRecords — see docs/RECORDS_CHIRPS_WORKBOOK.md.
 * 1. Filter exact scope, sort a COPY by order ascending.
 * 2. Pending/incomplete/unofficial weeks award nothing and break streaks.
 * 3. A qualifying week has >=2 distinct entries (model counts).
 * 4. Only a unique highest earner wins; ties break all winning streaks.
 * 5. Track total wins, current streak per person, best streak, highest earnings.
 *    Absence/loss breaks a person's streak; do not skip those weeks.
 * 6. Return all tied record holders, sorted by ID; no positive wins => null.
 *    Earnings of zero is a valid record. No qualifying weeks => all null.
 * Inputs are validated by prepareRecordWeeks. No mutation, dates, or fetches.
 */
export function computeGroupRecords(weeks: readonly RecordWeek[], scope: RecordScope): GroupRecords {
  const ordered = weeks
    .filter(week =>
      week.scope.groupId === scope.groupId &&
      week.scope.seasonId === scope.seasonId &&
      week.scope.mode === scope.mode
    )
    .sort((a, b) => a.order - b.order);
  const wins = new Map<string, number>();
  const currentStreaks = new Map<string, number>();
  const bestStreaks = new Map<string, number>();
  const highestEarnings = new Map<string, number>();

  for (const week of ordered) {
    const qualifies =
      week.status === 'final' &&
      week.complete &&
      week.official &&
      week.entries.length >= 2;
    
    if (!qualifies) {
    currentStreaks.clear();
    continue;
  }

  for (const entry of week.entries) {
    const previous = highestEarnings.get(entry.userId) ?? 0;

    highestEarnings.set(
      entry.userId,
      Math.max(previous, entry.earningsCents)
    );
  }

  const topEarnings = Math.max(
    ...week.entries.map(entry => entry.earningsCents)
  );
    const leaders = week.entries.filter(
    entry => entry.earningsCents === topEarnings
  );

  if (leaders.length !== 1) {
    currentStreaks.clear();
    continue;
  }

  const winner = leaders[0].userId;

  wins.set(winner, (wins.get(winner) ?? 0) + 1);

  const streak = (currentStreaks.get(winner) ?? 0) + 1;

  currentStreaks.clear();
  currentStreaks.set(winner, streak);

  bestStreaks.set(
    winner,
    Math.max(bestStreaks.get(winner) ?? 0, streak)
  );
  }

  const extractRecord = (
    values: Map<string, number>,
    allowZero = false,
  ): RecordValue | null => {
    if (values.size === 0) return null;
    const value = Math.max(...values.values());
    if (!allowZero && value <= 0) return null;
    const holderIds = [...values.entries()]
    .filter(([, amount]) => amount === value)
    .map(([userId]) => userId)
    .sort();

  return { value, holderIds };
};

return {
  wins: extractRecord(wins),
  streak: extractRecord(bestStreaks),
  earnings: extractRecord(highestEarnings, true),
};

  }
  

  




/** Adapter guard: ambiguous duplicates must not manufacture wins. */
export function prepareRecordWeeks(weeks: readonly RecordWeek[]): readonly RecordWeek[] {
  const seen = new Set<string>();
  for (const week of weeks) {
    const key = JSON.stringify([week.scope.groupId, week.scope.seasonId, week.scope.mode, week.weekId]);
    if (!week.weekId.trim() || !Number.isSafeInteger(week.order) || seen.has(key)) {
      throw new Error("Invalid or duplicate record week");
    }
    seen.add(key);
    const users = new Set<string>();
    for (const entry of week.entries) {
      if (!entry.userId.trim() || users.has(entry.userId) ||
          !Number.isSafeInteger(entry.earningsCents) || entry.earningsCents < 0) {
        throw new Error("Invalid or duplicate record entry");
      }
      users.add(entry.userId);
    }
  }
  return weeks;
}
