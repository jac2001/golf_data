/**
 * matchupDiff.ts: which golfers actually decide your matchup.
 * ============================================================
 * Let It Ride is the sum of your golfers' money, so a golfer you and your
 * rival both picked adds the same to both totals and cancels out. Only the
 * golfers you DON'T share move the gap. Facts only: no "what needs to
 * happen" scenarios here.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */
import { nameKey } from "./names.ts";
import { lastName } from "./matchCore.ts";

export type DiffGolfer = { name: string; position: string; earnings: number; thru: string; to_par?: number | null };
export type DiffLine = { user_id: string; user_name: string; golfers: DiffGolfer[] };
export type MatchupDiff = {
  rival: { user_id: string; user_name: string };
  shared: DiffGolfer[];   // in both lineups (yours, in your order)
  mine: DiffGolfer[];     // only you have
  theirs: DiffGolfer[];   // only they have
  sentence: string;
};

/** "Lee", "Lee and Kim", "Lee, Kim and Day". */
export const listNames = (gs: DiffGolfer[]) => {
  const ln = gs.map(g => lastName(g.name));
  return ln.length <= 2 ? ln.join(" and ") : `${ln.slice(0, -1).join(", ")} and ${ln[ln.length - 1]}`;
};

export function matchupDiff(lines: readonly DiffLine[], meId: string, rivalId: string | null | undefined): MatchupDiff | null {
  const me = lines.find(l => l.user_id === meId);
  const them = rivalId && rivalId !== meId ? lines.find(l => l.user_id === rivalId) : undefined;
  if (!me || !them || !me.golfers.length || !them.golfers.length) return null;

  const mineKeys = new Set(me.golfers.map(g => nameKey(g.name)));
  const theirKeys = new Set(them.golfers.map(g => nameKey(g.name)));
  const shared = me.golfers.filter(g => theirKeys.has(nameKey(g.name)));
  const mine = me.golfers.filter(g => !theirKeys.has(nameKey(g.name)));
  const theirs = them.golfers.filter(g => !mineKeys.has(nameKey(g.name)));
  const who = them.user_name;

  let sentence: string;
  if (!mine.length && !theirs.length) {
    sentence = `You and ${who} picked the same golfers, so this one can only end level.`;
  } else if (!mine.length) {
    sentence = `All your golfers are in ${who}'s lineup too. It comes down to ${listNames(theirs)}.`;
  } else if (!theirs.length) {
    sentence = `All of ${who}'s golfers are in your lineup too. It comes down to ${listNames(mine)}.`;
  } else if (!shared.length) {
    sentence = `You and ${who} share no golfers: it's ${listNames(mine)} against ${listNames(theirs)}.`;
  } else {
    const sharedText = shared.length === 1 ? listNames(shared) : `${shared.length} golfers (${listNames(shared)})`;
    sentence = `You and ${who} share ${sharedText}. It comes down to ${listNames(mine)} versus ${listNames(theirs)}.`;
  }
  return { rival: { user_id: them.user_id, user_name: who }, shared, mine, theirs, sentence };
}