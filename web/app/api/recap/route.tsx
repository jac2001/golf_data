/**
 * /api/recap?group_id=N[&tid=X] — the Sunday recap card.
 * =======================================================
 * One shareable PNG per group per settled WEEK: every tour the season
 * played that week (one panel and star each), combined lineup earnings,
 * the beat-the-model verdict, and next week's rematch. Built to be
 * dropped into the group chat Sunday night — the product's whole
 * retention bet in one image.
 *
 * Reads the group's Let It Ride season (the active one, else the most
 * recent). The week = the most recent settled event the season has picks
 * in, plus any other settled event that started within 3 days of it.
 * ?tid= pins that anchor event. Settled events only (the receipt rule:
 * nothing leaks early) — and all of the week, or nothing.
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
const ordinal = (n: number) =>
  `${n}${["th", "st", "nd", "rd"][((n % 100) - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th"}`;
const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");
const shortName = (n: string) => n.replace(/ presented by.*$/i, "");

async function modelApi(path: string): Promise<Record<string, unknown> | null> {
  try {
    // No caching: whether an event is settled is exactly what this route
    // gates on, and a cached "not settled" kept the recap button disabled
    // for minutes after the first real settlement (2026-10-05). Both API
    // calls are cheap.
    const res = await fetch(`${MODEL_API}${path}`, { cache: "no-store" });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

type Ev = { tournament_id: string; name: string; finished: boolean; start_date: string; locked: boolean };
type Golf = { player: string; earnings: number; position: string };
type Row = { user_id: string; user_name: string; total: number; golfers: Golf[] };
type Slate = { ev: Ev; board: Row[]; star: Row; credit: { golfer: Golf; decided: boolean } | null };

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
  const tid = (url.searchParams.get("tid") ?? "").toUpperCase();
  if (!groupId) return fail("group_id required", 400);

  const sql = getSql();
  const grp = await sql`SELECT name FROM groups WHERE id = ${groupId}` as { name: string }[];
  if (!grp.length) return fail("no such group", 404);
  const members = await sql`
    SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
  if (!members.some(m => m.user_id === userId)) return fail("Not a member of this group.", 403);

  const league = await sql`
    SELECT id FROM leagues WHERE group_id = ${groupId}
    ORDER BY (status = 'active') DESC, created_at DESC LIMIT 1` as { id: number }[];
  if (!league.length) return fail("this group has no Let It Ride season yet", 404);
  const leagueId = league[0].id;

  // ── Which week? ─────────────────────────────────────────────────────────
  const open = await modelApi("/api/events/open");
  const events = ((open?.events as Ev[]) ?? []);
  const withPicks: Ev[] = [];
  for (const e of events.filter(e => e.finished).sort((a, b) => b.start_date.localeCompare(a.start_date))) {
    const has = await sql`
      SELECT 1 FROM league_picks WHERE tournament_id = ${e.tournament_id} AND league_id = ${leagueId} LIMIT 1` as unknown[];
    if (has.length) withPicks.push(e);
  }
  const anchor = tid ? withPicks.find(e => e.tournament_id === tid) : withPicks[0];
  if (!anchor) return fail(tid ? "event not settled yet" : "no settled event with picks for this group", tid ? 403 : 404);
  const days = (a: string, b: string) => Math.abs(Date.parse(a) - Date.parse(b)) / 86_400_000;
  const weekEvents = withPicks.filter(e => days(e.start_date, anchor.start_date) <= 3)
    .sort((a, b) => (a.tournament_id.startsWith("R") ? 0 : 1) - (b.tournament_id.startsWith("R") ? 0 : 1));

  // ── One board per event ─────────────────────────────────────────────────
  const slates: Slate[] = [];
  for (const ev of weekEvents) {
    const earn = await modelApi(`/api/results/earnings?tournament_id=${ev.tournament_id}`);
    if (!earn?.settled) return fail("event not settled yet", 403);
    const table = (earn.players ?? {}) as Record<string, { earnings: number; position: string }>;
    const picks = await sql`
      SELECT user_id, user_name, player_name FROM league_picks
      WHERE tournament_id = ${ev.tournament_id} AND league_id = ${leagueId}` as
      { user_id: string; user_name: string; player_name: string }[];
    const rows = new Map<string, Row>();
    for (const p of picks) {
      const hit = table[nameKey(p.player_name)];
      const r = rows.get(p.user_id) ?? { user_id: p.user_id,
        user_name: p.user_id === "model" ? "The Model" : p.user_name, total: 0, golfers: [] };
      const g = { player: p.player_name, earnings: hit?.earnings ?? 0, position: hit?.position ?? "—" };
      r.total += g.earnings; r.golfers.push(g); rows.set(p.user_id, r);
    }
    const board = [...rows.values()].sort((a, b) => b.total - a.total);
    if (!board.length) continue;
    const [star, second] = board;
    // "Decided it" only when it's literally true: an unshared golfer whose
    // money exceeds the winning margin (take him away and the result flips).
    // Otherwise he's the winner's biggest contributor.
    const margin = second ? star.total - second.total : Infinity;
    const shared = new Set((second?.golfers ?? []).map(g => nameKey(g.player)));
    const byMoney = [...star.golfers].sort((a, b) => b.earnings - a.earnings);
    const decider = byMoney.find(g => !shared.has(nameKey(g.player)) && g.earnings > margin);
    const credit = decider ? { golfer: decider, decided: true }
      : byMoney[0] && byMoney[0].earnings > 0 ? { golfer: byMoney[0], decided: false } : null;
    slates.push({ ev, board, star, credit });
  }
  if (!slates.length) return fail("no picks for this group/event", 404);

  // ── The week across tours ───────────────────────────────────────────────
  const week = new Map<string, Row>();
  for (const sl of slates) for (const r of sl.board) {
    const w = week.get(r.user_id) ?? { ...r, total: 0, golfers: [] };
    w.total += r.total; week.set(r.user_id, w);
  }
  const weekBoard = [...week.values()].sort((a, b) => b.total - a.total);
  const top = weekBoard[0], runnerUp = weekBoard[1];
  const model = weekBoard.find(r => r.user_id === "model");
  const humans = weekBoard.filter(r => r.user_id !== "model");
  const beaters = model ? humans.filter(h => h.total > model.total) : [];
  const twoTours = slates.length > 1;
  const verdict = !model || !humans.length ? "" : humans.length === 1
    ? (beaters.length ? `${humans[0].user_name.toUpperCase()} BEAT THE MODEL` : `THE MODEL BEAT ${humans[0].user_name.toUpperCase()}`)
      + (twoTours ? " THIS WEEK" : "")
    : `${beaters.length} OF ${humans.length} PLAYERS BEAT THE MODEL`;
  const verdictGood = beaters.length > 0;

  const upcoming = events.filter(e => !e.finished && !e.locked).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const nextWeek = upcoming.filter(e => days(e.start_date, upcoming[0].start_date) <= 3).map(e => shortName(e.name));
  const s0 = new Date(anchor.start_date.slice(0, 10) + "T12:00:00Z");
  const e0 = new Date(s0.getTime() + 3 * 86_400_000);
  const dates = `${s0.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })} ${s0.getUTCDate()}–${e0.getUTCDate()}`;
  const pos = (p: string) => /^\d+$/.test(p) ? ordinal(Number(p)) : p;

  if (check) return Response.json({ available: true, tournament_id: anchor.tournament_id,
    event: slates.map(sl => shortName(sl.ev.name)).join(" + ") });

  const STAR = (
    <svg width="20" height="20" viewBox="0 0 24 24">
      <path fill={YELLOW} d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z" />
    </svg>
  );

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: BG, color: TEXT, fontFamily: "sans-serif", padding: "32px 44px 28px" }}>
        {/* Brand first: a forwarded image should say what it is at a glance. */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", fontSize: 26, fontWeight: 900, letterSpacing: 1, color: YELLOW }}>GOLF EDGE</div>
            <div style={{ display: "flex", fontSize: 22, fontWeight: 800, letterSpacing: 2 }}>SUNDAY RECAP</div>
          </div>
          <div style={{ display: "flex", fontSize: 19, color: MUTED }}>{grp[0].name} · {dates}</div>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 18 }}>
          <div style={{ display: "flex", fontSize: 48, fontWeight: 900 }}>{top.user_name}</div>
          <div style={{ display: "flex", fontSize: 32, fontWeight: 900 }}>{money(top.total)}</div>
          <div style={{ display: "flex", fontSize: 19, color: MUTED }}>
            lineup earnings{twoTours ? " · both tours" : ""}
          </div>
        </div>
        {runnerUp && (
          <div style={{ display: "flex", fontSize: 20, color: MUTED, marginTop: 2 }}>
            {money(top.total - runnerUp.total)} clear of {runnerUp.user_name}{twoTours ? " for the week" : ""}
          </div>
        )}

        <div style={{ display: "flex", gap: 18, marginTop: 16 }}>
          {slates.map(sl => (
            <div key={sl.ev.tournament_id} style={{ display: "flex", flexDirection: "column", flex: 1, background: CARD,
              borderRadius: 14, border: `1px solid ${LINE}`, padding: "14px 20px" }}>
              <div style={{ display: "flex", fontSize: 15, color: MUTED, letterSpacing: 1 }}>
                {sl.ev.tournament_id.startsWith("E") ? "DP WORLD TOUR" : "PGA TOUR"} · {shortName(sl.ev.name).toUpperCase()}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 22, fontWeight: 900, marginTop: 6 }}>
                {STAR}{sl.star.user_name} takes it
              </div>
              {sl.board.slice(0, twoTours ? 3 : 5).map((r, i) => (
                <div key={r.user_id} style={{ display: "flex", alignItems: "baseline", gap: 10, fontSize: 20,
                  padding: "2px 0", color: i === 0 ? TEXT : MUTED }}>
                  <div style={{ display: "flex", width: 20 }}>{i + 1}</div>
                  <div style={{ display: "flex", fontWeight: i === 0 ? 800 : 600 }}>{r.user_name}</div>
                  <div style={{ display: "flex", marginLeft: "auto", fontWeight: 800 }}>{money(r.total)}</div>
                </div>
              ))}
              {sl.credit && (
                <div style={{ display: "flex", flexDirection: "column", marginTop: 8, paddingTop: 8, borderTop: `1px solid ${LINE}` }}>
                  <div style={{ display: "flex", fontSize: 14, color: MUTED, letterSpacing: 1 }}>
                    {sl.credit.decided ? "DECIDED IT" : "BIGGEST CONTRIBUTOR"}
                  </div>
                  <div style={{ display: "flex", fontSize: 22, fontWeight: 900, marginTop: 2 }}>{sl.credit.golfer.player}</div>
                  <div style={{ display: "flex", fontSize: 17, color: MUTED }}>
                    Finished {pos(sl.credit.golfer.position)} · added&nbsp;
                    <span style={{ color: GREEN, fontWeight: 700 }}>{money(sl.credit.golfer.earnings)}</span>
                    &nbsp;to {sl.star.user_name}&apos;s total
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {verdict && (
          <div style={{ display: "flex", marginTop: 14, fontSize: 22, fontWeight: 900, letterSpacing: 1,
            color: verdictGood ? GREEN : RED }}>
            {verdict}
          </div>
        )}

        <div style={{ display: "flex", marginTop: "auto", justifyContent: "space-between",
          borderTop: `3px solid ${YELLOW}`, paddingTop: 12, alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 20, fontWeight: 800 }}>
            {nextWeek.length ? `REMATCH: ${nextWeek.join(" + ")} — picks open now` : "Rematch next week"}
          </div>
          <div style={{ display: "flex", fontSize: 17, color: MUTED }}>playgolfedge.com</div>
        </div>
      </div>
    ),
    { width: 1000, height: twoTours ? 600 : 520 },
  );
}
