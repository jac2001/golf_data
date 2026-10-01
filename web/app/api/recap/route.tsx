/**
 * /api/recap?group_id=N[&tid=X] — the Sunday recap card.
 * =======================================================
 * One shareable PNG per group per settled event: who won the week, the
 * beat-the-model verdict, the decisive golfer, and next week's
 * challenge. Built to be dropped into the group chat Sunday night —
 * the product's whole retention bet in one image.
 *
 * Reads the group's Let It Ride season (the active one, else the most
 * recent): the week's winner is that slate's weekly winner.
 * tid omitted → the most recent SETTLED event the season has picks in.
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
  // ?check=1 answers "is there a recap?" as JSON without rendering it, so
  // the Groups tab can disable the button instead of opening an error.
  const check = url.searchParams.get("check") === "1";
  const fail = (msg: string, status: number) => check
    ? Response.json({ available: false, reason: msg })
    : new Response(msg, { status });
  const groupId = Number(url.searchParams.get("group_id") || 0);
  let tid = (url.searchParams.get("tid") ?? "").toUpperCase();
  if (!groupId) return fail("group_id required", 400);

  const sql = getSql();
  const grp = await sql`SELECT name FROM groups WHERE id = ${groupId}` as { name: string }[];
  if (!grp.length) return fail("no such group", 404);
  const members = await sql`
    SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
  const ids = members.map(m => m.user_id);
  if (!ids.includes(userId)) return fail("Not a member of this group.", 403);
  ids.push("model");

  const league = await sql`
    SELECT id FROM leagues WHERE group_id = ${groupId}
    ORDER BY (status = 'active') DESC, created_at DESC LIMIT 1` as { id: number }[];
  if (!league.length) return fail("this group has no Let It Ride season yet", 404);
  const leagueId = league[0].id;

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
        SELECT 1 FROM league_picks WHERE tournament_id = ${t} AND league_id = ${leagueId} LIMIT 1` as unknown[];
      if (has.length) { tid = t; break; }
    }
  }
  if (!tid) return fail("no settled event with picks for this group", 404);
  const evMeta = events.find(e => e.tournament_id === tid);
  if (evMeta && !evMeta.finished) return fail("event not settled yet", 403);

  const picks = await sql`
    SELECT user_id, user_name, player_name FROM league_picks
    WHERE tournament_id = ${tid} AND league_id = ${leagueId}` as
    { user_id: string; user_name: string; player_name: string }[];
  if (!picks.length) return fail("no picks for this group/event", 404);

  const earn = await modelApi(`/api/results/earnings?tournament_id=${tid}`);
  const table = (earn?.players ?? {}) as Record<string, { earnings: number; position: string }>;
  if (!earn?.settled) return fail("event not settled yet", 403);

  type Golf = { player: string; earnings: number; position: string };
  type Row = { user_id: string; user_name: string; total: number; golfers: Golf[] };
  const rows = new Map<string, Row>();
  for (const p of picks) {
    const hit = table[nameKey(p.player_name)];
    const r = rows.get(p.user_id) ?? { user_id: p.user_id,
      user_name: p.user_id === "model" ? "The Model" : p.user_name, total: 0, golfers: [] };
    const g = { player: p.player_name, earnings: hit?.earnings ?? 0, position: hit?.position ?? "—" };
    r.total += g.earnings;
    r.golfers.push(g);
    rows.set(p.user_id, r);
  }
  const board = [...rows.values()].sort((a, b) => b.total - a.total);
  const winner = board[0];
  const runnerUp = board[1];
  const model = board.find(r => r.user_id === "model");
  const humans = board.filter(r => r.user_id !== "model");
  const beaters = model ? humans.filter(h => h.total > model.total) : [];

  // The golfer who DECIDED the week: the winner's best earner that the
  // runner-up didn't also have — a shared golfer cancels out. Falls back
  // to the winner's top earner when everything was shared.
  const rivalKeys = new Set((runnerUp?.golfers ?? []).map(g => nameKey(g.player)));
  const byMoney = [...winner.golfers].sort((a, b) => b.earnings - a.earnings);
  const decisive = byMoney.find(g => !rivalKeys.has(nameKey(g.player))) ?? byMoney[0];

  const eventName = evMeta?.name ?? tid;
  const next = events.find(e => !e.finished && !e.locked) ?? events.find(e => !e.finished);

  const verdict = !model ? "" :
    winner.user_id === "model"
      ? "THE MODEL TOOK THE WEEK"
      : beaters.length === humans.length
        ? "EVERYONE BEAT THE MODEL"
        : beaters.length > 0
          ? `${beaters.length} OF ${humans.length} BEAT THE MODEL`
          : "NOBODY BEAT THE MODEL";
  const verdictGood = beaters.length > 0 && winner.user_id !== "model";

  if (check) return Response.json({ available: true, tournament_id: tid, event: eventName });

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: BG, color: TEXT, fontFamily: "sans-serif", padding: 44 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 28, fontWeight: 900, letterSpacing: 2 }}>SUNDAY RECAP</div>
          <div style={{ display: "flex", fontSize: 20, color: MUTED }}>{grp[0].name} · {eventName}</div>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 24 }}>
          <div style={{ display: "flex", fontSize: 50, fontWeight: 900, color: YELLOW }}>{winner.user_name}</div>
          <div style={{ display: "flex", fontSize: 30, fontWeight: 900 }}>{money(winner.total)}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 20, color: YELLOW }}>
            <svg width="22" height="22" viewBox="0 0 24 24">
              <path fill={YELLOW} d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z" />
            </svg>
            takes the week
          </div>
        </div>
        {runnerUp && (
          <div style={{ display: "flex", fontSize: 20, color: MUTED, marginTop: 4 }}>
            {money(winner.total - runnerUp.total)} clear of {runnerUp.user_name}
          </div>
        )}

        <div style={{ display: "flex", gap: 22, marginTop: 22 }}>
          {/* Final standings */}
          <div style={{ display: "flex", flexDirection: "column", flex: 1, background: CARD,
            borderRadius: 14, border: `1px solid ${LINE}`, padding: "14px 22px" }}>
            <div style={{ display: "flex", fontSize: 16, color: MUTED, letterSpacing: 1, marginBottom: 6 }}>FINAL STANDINGS</div>
            {board.slice(0, 6).map((r, i) => (
              <div key={r.user_id} style={{ display: "flex", alignItems: "baseline", gap: 12, fontSize: 22, padding: "3px 0" }}>
                <div style={{ display: "flex", width: 24, fontWeight: 900, color: YELLOW }}>{i + 1}</div>
                <div style={{ display: "flex", fontWeight: 800, color: r.user_id === "model" ? YELLOW : TEXT }}>
                  {r.user_name}
                </div>
                <div style={{ display: "flex", marginLeft: "auto", fontWeight: 800 }}>{money(r.total)}</div>
              </div>
            ))}
            {board.length > 6 && (
              <div style={{ display: "flex", fontSize: 16, color: MUTED, marginTop: 4 }}>+{board.length - 6} more</div>
            )}
          </div>

          {/* The golfer who decided it + the model verdict */}
          <div style={{ display: "flex", flexDirection: "column", flex: 1, gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", background: CARD, borderRadius: 14,
              border: `1px solid ${LINE}`, padding: "14px 22px" }}>
              <div style={{ display: "flex", fontSize: 16, color: MUTED, letterSpacing: 1 }}>THE GOLFER WHO DECIDED IT</div>
              <div style={{ display: "flex", fontSize: 28, fontWeight: 900, marginTop: 6 }}>{decisive.player}</div>
              <div style={{ display: "flex", fontSize: 19, color: MUTED, marginTop: 2 }}>
                <span style={{ color: GREEN, fontWeight: 700 }}>{money(Math.max(decisive.earnings, 0))}</span>
                <span>&nbsp;· finished {decisive.position} for {winner.user_name}</span>
              </div>
            </div>
            {verdict && (
              <div style={{ display: "flex", flexDirection: "column", background: CARD, borderRadius: 14,
                border: `1px solid ${LINE}`, padding: "14px 22px" }}>
                <div style={{ display: "flex", fontSize: 24, fontWeight: 900, letterSpacing: 1, color: verdictGood ? GREEN : RED }}>
                  {verdict}
                </div>
                {beaters.length > 0 && beaters.length < humans.length && (
                  <div style={{ display: "flex", fontSize: 19, color: MUTED, marginTop: 4 }}>
                    {beaters.slice(0, 4).map(b => b.user_name).join(", ")}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", marginTop: "auto", justifyContent: "space-between",
          borderTop: `3px solid ${YELLOW}`, paddingTop: 14, alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 21, fontWeight: 800 }}>
            {next ? `REMATCH: ${next.name} — picks open now` : "Rematch next week"}
          </div>
          <div style={{ display: "flex", fontSize: 18, color: MUTED }}>playgolfedge.com/friends</div>
        </div>
      </div>
    ),
    { width: 1000, height: 640 },
  );
}
