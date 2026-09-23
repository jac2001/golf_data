/**
 * /api/recap?group_id=N[&tid=X] — the Sunday recap card.
 * =======================================================
 * One shareable PNG per group per settled event: who won the week, the
 * beat-the-model verdict, the decisive golfer, and next week's
 * challenge. Built to be dropped into the group chat Sunday night —
 * the product's whole retention bet in one image.
 *
 * tid omitted → the most recent SETTLED event this group has picks in.
 * Settled events only (the receipt rule: nothing leaks early).
 *
 * MEMBERS ONLY, unlike receipts: a receipt URL carries an unguessable
 * user id, but group ids are sequential ints — a public recap would be
 * enumerable by anyone. Sharing still works because shareRecap fetches
 * the PNG with the member's session and shares the FILE into the chat;
 * recipients get the image, never the URL.
 */

import { auth } from "@clerk/nextjs/server";
import { ImageResponse } from "next/og";
import { getSql, MODEL_API } from "@/lib/db";

export const runtime = "nodejs";

const BG = "#0c2a1c", CARD = "#0f3322", LINE = "#1e4a33";
const TEXT = "#f2f7f0", MUTED = "#9dbfa9", YELLOW = "#ffd24a", GREEN = "#6fd49a", RED = "#ff6b6b";

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

async function modelApi(path: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${MODEL_API}${path}`, { next: { revalidate: 300 } });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return new Response("Unauthorized", { status: 401 });

  const url = new URL(req.url);
  const groupId = Number(url.searchParams.get("group_id") || 0);
  let tid = (url.searchParams.get("tid") ?? "").toUpperCase();
  if (!groupId) return new Response("group_id required", { status: 400 });

  const sql = getSql();
  const grp = await sql`SELECT name FROM groups WHERE id = ${groupId}` as { name: string }[];
  if (!grp.length) return new Response("no such group", { status: 404 });
  const members = await sql`
    SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
  const ids = members.map(m => m.user_id);
  if (!ids.includes(userId)) return new Response("Not a member of this group.", { status: 403 });
  ids.push("model");

  // Which settled events does this group have picks in?
  type Ev = { tournament_id: string; name: string; finished: boolean; start_date: string; locked: boolean };
  const open = await modelApi("/api/events/open");
  const events = ((open?.events as Ev[]) ?? []);
  const settledTids: string[] = [];
  for (const e of events.filter(e => e.finished)
      .sort((a, b) => b.start_date.localeCompare(a.start_date))) {
    settledTids.push(e.tournament_id);
  }
  if (!tid) {
    for (const t of settledTids) {
      const has = await sql`
        SELECT 1 FROM picks WHERE tournament_id = ${t} AND user_id = ANY(${ids}) LIMIT 1` as unknown[];
      if (has.length) { tid = t; break; }
    }
  }
  if (!tid) return new Response("no settled event with picks for this group", { status: 404 });
  const evMeta = events.find(e => e.tournament_id === tid);
  if (evMeta && !evMeta.finished) return new Response("event not settled yet", { status: 403 });

  const picks = await sql`
    SELECT user_id, user_name, player_name FROM picks
    WHERE tournament_id = ${tid} AND user_id = ANY(${ids})` as
    { user_id: string; user_name: string; player_name: string }[];
  if (!picks.length) return new Response("no picks for this group/event", { status: 404 });

  const earn = await modelApi(`/api/results/earnings?tournament_id=${tid}`);
  const table = (earn?.players ?? {}) as Record<string, { earnings: number; position: string }>;
  if (!earn?.settled) return new Response("event not settled yet", { status: 403 });

  type Row = { user_id: string; user_name: string; total: number;
    best: { player: string; earnings: number; position: string } };
  const rows = new Map<string, Row>();
  for (const p of picks) {
    const hit = table[nameKey(p.player_name)];
    const e = hit?.earnings ?? 0;
    const r = rows.get(p.user_id) ?? { user_id: p.user_id, user_name: p.user_name, total: 0,
      best: { player: p.player_name, earnings: -1, position: "—" } };
    r.total += e;
    if (e > r.best.earnings) r.best = { player: p.player_name, earnings: e, position: hit?.position ?? "—" };
    rows.set(p.user_id, r);
  }
  const board = [...rows.values()].sort((a, b) => b.total - a.total);
  const winner = board[0];
  const runnerUp = board[1];
  const model = board.find(r => r.user_id === "model");
  const humans = board.filter(r => r.user_id !== "model");
  const beatModel = model ? humans.filter(h => h.total > model.total).length : 0;

  const eventName = evMeta?.name ?? tid;
  const next = events.find(e => !e.finished && !e.locked) ?? events.find(e => !e.finished);

  const verdict = !model ? "" :
    winner.user_id === "model"
      ? `THE MODEL TOOK THE WEEK — best human ${money((humans[0]?.total ?? 0))}`
      : beatModel > 0
        ? `${beatModel} OF ${humans.length} BEAT THE MODEL`
        : "NOBODY BEAT THE MODEL";

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: BG, color: TEXT, fontFamily: "sans-serif", padding: 48 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 30, fontWeight: 900, letterSpacing: 2 }}>SUNDAY RECAP</div>
          <div style={{ display: "flex", fontSize: 20, color: MUTED }}>{grp[0].name} · {eventName}</div>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 30 }}>
          <div style={{ display: "flex", fontSize: 52, fontWeight: 900, color: YELLOW }}>
            {winner.user_name}
          </div>
          <div style={{ display: "flex", fontSize: 30, fontWeight: 900 }}>{money(winner.total)}</div>
          <div style={{ display: "flex", fontSize: 20, color: MUTED }}>takes the week</div>
        </div>
        {runnerUp && (
          <div style={{ display: "flex", fontSize: 20, color: MUTED, marginTop: 6 }}>
            {money(winner.total - runnerUp.total)} clear of {runnerUp.user_name}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", marginTop: 26, background: CARD,
          borderRadius: 14, border: `1px solid ${LINE}`, padding: "16px 26px" }}>
          <div style={{ display: "flex", fontSize: 18, color: MUTED, letterSpacing: 1 }}>THE DECISIVE GOLFER</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 6 }}>
            <div style={{ display: "flex", fontSize: 30, fontWeight: 900 }}>{winner.best.player}</div>
            <div style={{ display: "flex", fontSize: 24, fontWeight: 700, color: GREEN }}>
              {money(Math.max(winner.best.earnings, 0))}
            </div>
            <div style={{ display: "flex", fontSize: 20, color: MUTED }}>
              finished {winner.best.position} for {winner.user_name}
            </div>
          </div>
        </div>

        {verdict && (
          <div style={{ display: "flex", marginTop: 20, fontSize: 26, fontWeight: 900, letterSpacing: 1,
            color: verdict.startsWith("NOBODY") || verdict.startsWith("THE MODEL") ? RED : GREEN }}>
            {verdict}
          </div>
        )}

        <div style={{ display: "flex", marginTop: "auto", justifyContent: "space-between",
          borderTop: `3px solid ${YELLOW}`, paddingTop: 16, alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 20, color: MUTED }}>
            {next ? `Next week: ${next.name} — picks open now` : "playgolfedge.com"}
          </div>
          <div style={{ display: "flex", fontSize: 18, color: MUTED }}>playgolfedge.com</div>
        </div>
      </div>
    ),
    { width: 1000, height: 560 },
  );
}
