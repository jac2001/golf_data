/**
 * The match center's core: given one slate's visible picks and the
 * event's money table, rank the group and answer "what needs to happen?"
 * Pure, so it's testable without a session (the route wraps it).
 */
import { nameKey } from "./names";

export type PlayerMoney = { player_name: string; earnings: number; position: string;
  up_one?: number; thru?: string; to_par?: number | null; round?: number | null };
export type Golfer = { name: string; position: string; earnings: number; up_one: number; thru: string;
  to_par: number | null; round: number | null };
export type MemberLine = { user_id: string; user_name: string; total: number; golfers: Golfer[]; rank: number };

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
export const lastName = (n: string) =>
  n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);

/** Rank by total, highest first; ties share a rank. */
export function ranked<T extends { total: number }>(rows: T[]): (T & { rank: number })[] {
  const sorted = [...rows].sort((a, b) => b.total - a.total);
  return sorted.map(r => ({ ...r, rank: 1 + sorted.filter(o => o.total > r.total).length }));
}

export function summarizeSlate(
  picks: { user_id: string; player_name: string }[],
  table: Record<string, PlayerMoney> | null,
  graded: boolean,
  nameOf: (uid: string) => string,
  me: string,
) {
  const byUser = new Map<string, Golfer[]>();
  for (const p of picks) {
    const hit = table?.[nameKey(p.player_name)];
    byUser.set(p.user_id, [...(byUser.get(p.user_id) ?? []), {
      name: p.player_name, position: hit?.position ?? "—",
      earnings: graded ? (hit?.earnings ?? 0) : 0,
      up_one: hit?.up_one ?? 0, thru: hit?.thru ?? "",
      to_par: hit?.to_par ?? null, round: hit?.round ?? null,
    }]);
  }
  const lines: MemberLine[] = ranked([...byUser.entries()].map(([uid, golfers]) => ({
    user_id: uid, user_name: nameOf(uid),
    total: golfers.reduce((s, g) => s + g.earnings, 0),
    golfers: golfers.sort((a, b) => b.earnings - a.earnings),
  })));

  const mine = lines.find(l => l.user_id === me) ?? null;
  const humans = lines.filter(l => l.user_id !== "model");
  const model = lines.find(l => l.user_id === "model") ?? null;

  // Closest rival: the person directly above you; if you lead, the one
  // chasing you. The model counts — it's in the race.
  let rival: MemberLine | null = null;
  let story = "";
  if (mine && graded && lines.length > 1) {
    const above = lines.filter(l => l.total > mine.total).sort((a, b) => a.total - b.total)[0];
    const below = lines.filter(l => l.user_id !== mine.user_id && l.total <= mine.total)
      .sort((a, b) => b.total - a.total)[0];
    rival = above ?? below ?? null;
    if (above) {
      const gap = above.total - mine.total;
      const flip = [...mine.golfers].sort((a, b) => b.up_one - a.up_one).find(g => g.up_one > gap);
      story = flip
        ? `${lastName(flip.name)} moving up one spot would put you ahead of ${above.user_name}.`
        : `You need ${money(gap)} more to catch ${above.user_name}.`;
    } else if (below) {
      story = mine.total === below.total
        ? `You're tied with ${below.user_name}.`
        : `You lead ${below.user_name} by ${money(mine.total - below.total)}.`;
    }
  }
  return {
    lines,
    rival: rival ? { user_id: rival.user_id, user_name: rival.user_name, total: rival.total } : null,
    gap: rival && mine ? rival.total - mine.total : 0,
    story,
    beating_model: model ? humans.filter(h => h.total > model.total).length : null,
    humans: humans.length,
  };
}
