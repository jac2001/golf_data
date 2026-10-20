/**
 * chirpCard.ts — the matchup snapshot a chirp carries (server only).
 * ==================================================================
 * docs/CHIRPS_DESIGN.md. A chirp is about something on the board, so the
 * server freezes the sender's standing at that moment: rank, players,
 * lineup earnings, who leads and by how much. Built with the Match
 * Center's own logic (lib/matchCore summarizeSlate) from what the SENDER
 * could see (lib/eventLocks pickVisible), and it carries NO golfer names,
 * so it can never reveal a hidden pick. Before lock it's just the status.
 */
import { getSql, MODEL_API } from "@/lib/db";
import { summarizeSlate } from "@/lib/matchCore";
import { openEventLocks, pickVisible } from "@/lib/eventLocks";

export type ChirpCard = {
  event: string;
  status: "open" | "live" | "settling" | "final";
  /** The sender's rank among everyone on the slate (model included), or null. */
  rank: number | null;
  players: number;
  total: number | null;
  /** Who leads (if not the sender) and by how much. */
  leader: string | null;
  gap: number | null;
  /** Live money is an estimate; "final" only once settled. */
  estimated: boolean;
};

type Earnings = { settled: boolean; projected?: boolean;
  players: Record<string, { player_name: string; earnings: number; position: string }> };

async function model<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${MODEL_API}${path}`, { next: { revalidate: 120 } });
    return res.ok ? await res.json() as T : null;
  } catch { return null; }
}

export async function buildChirpCard(groupId: number, tid: string, senderId: string): Promise<ChirpCard> {
  const sql = getSql();
  const [open, locks] = await Promise.all([
    model<{ events: { tournament_id: string; name: string; locked: boolean; finished: boolean }[] }>("/api/events/open"),
    openEventLocks(),
  ]);
  const ev = (open?.events ?? []).find(e => e.tournament_id.toUpperCase() === tid);
  const base: ChirpCard = { event: ev?.name ?? tid, status: "open", rank: null, players: 0,
    total: null, leader: null, gap: null, estimated: false };
  // Unknown lock state reveals nothing (domain rule 4).
  if (!locks || !(locks.get(tid) ?? true)) return base;

  const lg = await sql`SELECT id FROM leagues WHERE group_id = ${groupId} AND status = 'active' ORDER BY id DESC LIMIT 1` as { id: number }[];
  const roster = await sql`SELECT user_id, user_name FROM group_members WHERE group_id = ${groupId}` as { user_id: string; user_name: string }[];
  if (!lg.length) return { ...base, status: ev?.finished ? "final" : "live" };

  const [picksRaw, table] = await Promise.all([
    sql`SELECT user_id, player_name FROM league_picks WHERE league_id = ${lg[0].id} AND tournament_id = ${tid}`,
    model<Earnings>(`/api/results/earnings?tournament_id=${tid}&projected=1`),
  ]);
  const picks = (picksRaw as { user_id: string; player_name: string }[])
    .filter(p => pickVisible(locks, tid, p.user_id, senderId));
  const graded = !!(table?.settled || table?.projected);
  const nameOf = (uid: string) => uid === "model" ? "The Model" : (roster.find(r => r.user_id === uid)?.user_name || "Player");
  const sum = summarizeSlate(picks, table?.players ?? null, graded, nameOf, senderId);
  const me = sum.lines.find(l => l.user_id === senderId) ?? null;
  const leader = sum.lines.find(l => l.rank === 1 && l.user_id !== senderId) ?? null;
  const status: ChirpCard["status"] = ev?.finished ? (table?.settled ? "final" : "settling") : "live";
  return {
    event: base.event, status,
    rank: me?.rank ?? null, players: sum.lines.length,
    total: graded && me ? me.total : null,
    leader: me && me.rank > 1 && leader ? leader.user_name : null,
    gap: graded && me && me.rank > 1 && leader ? leader.total - me.total : null,
    estimated: !table?.settled,
  };
}
