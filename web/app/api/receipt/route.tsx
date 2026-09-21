/**
 * /api/receipt?tid=R2026557&u=<user_id>&game=weekly|rounds|fades — receipt cards.
 * =========================================================================
 * A shareable PNG of one player's week: picks, money (or round scores),
 * rank, and the verdict vs The Model. Rendered server-side with next/og
 * (JSX → SVG → PNG at request time — no headless browser, no canvas).
 *
 * Public by design: a receipt exists to leave the app and live in a group
 * chat. The privacy rule still holds because a receipt only renders for
 * LOCKED events — pre-lock picks stay invisible here too.
 */

import { ImageResponse } from "next/og";
import { getSql, MODEL_API } from "@/lib/db";

export const runtime = "nodejs";

const BG = "#0c2a1c", PANEL = "#081f14", CARD = "#0f3322", LINE = "#1e4a33";
const TEXT = "#f2f7f0", MUTED = "#9dbfa9", YELLOW = "#ffd24a", GREEN = "#6fd49a", RED = "#ff6b6b";

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
const toPar = (v: number) => (v > 0 ? `+${v}` : v === 0 ? "E" : String(v));
const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

async function modelApi(path: string): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${MODEL_API}${path}`, { next: { revalidate: 300 } });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const tid = (url.searchParams.get("tid") ?? "").toUpperCase();
  const uid = url.searchParams.get("u") ?? "";
  const raw = url.searchParams.get("game");
  const game = raw === "rounds" ? "rounds" : raw === "fades" ? "fades" : "weekly";
  if (!tid || !uid) return new Response("tid and u required", { status: 400 });

  // Locked events only — receipts never leak live picks.
  const open = await modelApi("/api/events/open");
  const ev = ((open?.events as { tournament_id: string; locked: boolean; name: string }[]) ?? [])
    .find(e => e.tournament_id === tid);
  if (ev && !ev.locked) return new Response("event not locked", { status: 403 });

  // Event display name (open list, else earnings payload, else the id)
  let eventName = ev?.name ?? "";

  const sql = getSql();
  type Line = { label: string; player: string; value: string; color: string };
  let lines: Line[] = [];
  let totalLabel = "", totalValue = "", verdict = "", rankText = "";
  let userName = "";

  if (game === "weekly" || game === "fades") {
    // The fade game is the weekly game through a mirror: same earnings
    // table, but LOW is the win and cashing big is the disaster.
    const fade = game === "fades";
    const picks = (fade
      ? await sql`
        SELECT user_id, user_name, player_name FROM fade_picks
        WHERE tournament_id = ${tid}`
      : await sql`
        SELECT user_id, user_name, player_name FROM picks
        WHERE tournament_id = ${tid}`) as { user_id: string; user_name: string; player_name: string }[];
    const mine = picks.filter(p => p.user_id === uid);
    if (!mine.length) return new Response("no picks for this user/event", { status: 404 });
    userName = mine[0].user_name;

    const earn = await modelApi(`/api/results/earnings?tournament_id=${tid}`);
    const table = (earn?.players ?? {}) as Record<string, { earnings: number; position: string; player_name: string }>;
    const estimated = !!earn?.earnings_estimated;

    const scoreOf = (ps: { player_name: string }[]) =>
      ps.reduce((s, p) => s + (table[nameKey(p.player_name)]?.earnings ?? 0), 0);

    lines = mine.map(p => {
      const hit = table[nameKey(p.player_name)];
      return {
        label: hit?.position ? `#${hit.position}` : "—",
        player: p.player_name,
        value: hit ? money(hit.earnings) : "$0",
        // In the fade game a player who cashed is the mistake.
        color: hit && hit.earnings > 0 ? (fade ? RED : GREEN) : (fade ? GREEN : MUTED),
      };
    });
    const myTotal = scoreOf(mine);
    totalLabel = fade
      ? "Fade total — lowest wins"
      : estimated ? "Total (est. purse split)" : "Total earnings";
    totalValue = money(myTotal);

    // Rank across everyone with picks this event
    const totals = new Map<string, number>();
    for (const p of picks) totals.set(p.user_id, (totals.get(p.user_id) ?? 0));
    for (const [u] of totals) totals.set(u, scoreOf(picks.filter(p => p.user_id === u)));
    const sorted = [...totals.entries()].sort((a, b) => fade ? a[1] - b[1] : b[1] - a[1]);
    const rank = sorted.findIndex(([u]) => u === uid) + 1;
    rankText = `#${rank} of ${sorted.length}`;
    const modelTotal = totals.get("model");
    if (modelTotal != null && uid !== "model") {
      const d = fade ? modelTotal - myTotal : myTotal - modelTotal;
      verdict = d >= 0 ? `BEAT THE MODEL BY ${money(d)}` : `MODEL WINS BY ${money(-d)}`;
    }
  } else {
    const picks = await sql`
      SELECT user_id, user_name, round, player_name FROM round_picks
      WHERE tournament_id = ${tid}` as { user_id: string; user_name: string; round: number; player_name: string }[];
    const mine = picks.filter(p => p.user_id === uid).sort((a, b) => a.round - b.round);
    if (!mine.length) return new Response("no round picks for this user/event", { status: 404 });
    userName = mine[0].user_name;

    const rounds = await modelApi(`/api/events/rounds?tournament_id=${tid}`);
    const table = (rounds?.players ?? {}) as Record<string, { rounds: Record<string, number> }>;
    const avail = Number(rounds?.rounds_available ?? 0);

    const scoreRow = (p: { round: number; player_name: string }): number | null => {
      const s = table[nameKey(p.player_name)]?.rounds?.[String(p.round)];
      if (s !== undefined) return s;
      return p.round <= avail ? 5 : null;  // missed round penalty
    };
    const scoreOf = (ps: { round: number; player_name: string }[]) =>
      ps.reduce((s, p) => s + (scoreRow(p) ?? 0), 0);

    lines = mine.map(p => {
      const s = scoreRow(p);
      return {
        label: `R${p.round}`,
        player: p.player_name,
        value: s == null ? "…" : toPar(s),
        color: s == null ? MUTED : s < 0 ? GREEN : s > 0 ? RED : TEXT,
      };
    });
    const myTotal = scoreOf(mine);
    totalLabel = "Total to par";
    totalValue = toPar(myTotal);

    const byUser = new Map<string, { round: number; player_name: string }[]>();
    for (const p of picks) byUser.set(p.user_id, [...(byUser.get(p.user_id) ?? []), p]);
    const sorted = [...byUser.entries()].map(([u, ps]) => [u, scoreOf(ps)] as const)
      .sort((a, b) => a[1] - b[1]);
    const rank = sorted.findIndex(([u]) => u === uid) + 1;
    rankText = `#${rank} of ${sorted.length}`;
    const model = sorted.find(([u]) => u === "model");
    if (model && uid !== "model") {
      const d = model[1] - myTotal;  // lower is better
      verdict = d >= 0 ? `BEAT THE MODEL BY ${d}` : `MODEL WINS BY ${-d}`;
    }
  }

  if (!eventName) {
    // Finished events drop off the open list — the history endpoint knows
    // every settled event's display name.
    const hist = await modelApi("/api/history/tournaments");
    const row = ((hist?.tournaments as { tournament_id: string; name: string }[]) ?? [])
      .find(t => t.tournament_id?.toUpperCase() === tid);
    eventName = row?.name ?? tid;
  }
  const isModel = uid === "model";

  return new ImageResponse(
    (
      <div style={{
        width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: BG, color: TEXT, fontFamily: "sans-serif", padding: 48,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", fontSize: 34, fontWeight: 900, letterSpacing: 2 }}>
            GOLF EDGE
          </div>
          <div style={{ display: "flex", fontSize: 22, color: MUTED }}>{eventName}</div>
        </div>

        <div style={{ display: "flex", alignItems: "center", marginTop: 28, gap: 16 }}>
          <div style={{ display: "flex", fontSize: 44, fontWeight: 900 }}>{userName}</div>
          {isModel && (
            <div style={{ display: "flex", background: YELLOW, color: PANEL, fontSize: 20,
              fontWeight: 900, padding: "4px 14px", borderRadius: 6, letterSpacing: 2 }}>
              MODEL
            </div>
          )}
          <div style={{ display: "flex", marginLeft: "auto", fontSize: 30, fontWeight: 900, color: YELLOW }}>
            {rankText}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", marginTop: 24,
          background: CARD, borderRadius: 14, border: `1px solid ${LINE}`, padding: "8px 28px" }}>
          {lines.map((l, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", padding: "14px 0",
              borderBottom: i < lines.length - 1 ? `1px solid ${LINE}` : "none" }}>
              <div style={{ display: "flex", width: 76, fontSize: 24, color: MUTED, fontWeight: 700 }}>{l.label}</div>
              <div style={{ display: "flex", fontSize: 28, fontWeight: 700 }}>{l.player}</div>
              <div style={{ display: "flex", marginLeft: "auto", fontSize: 28, fontWeight: 900, color: l.color }}>
                {l.value}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", marginTop: 22 }}>
          <div style={{ display: "flex", fontSize: 24, color: MUTED }}>{totalLabel}</div>
          <div style={{ display: "flex", marginLeft: 16, fontSize: 40, fontWeight: 900 }}>{totalValue}</div>
          {verdict && (
            <div style={{ display: "flex", marginLeft: "auto", fontSize: 26, fontWeight: 900,
              color: verdict.startsWith("BEAT") ? GREEN : RED, letterSpacing: 1 }}>
              {verdict}
            </div>
          )}
        </div>

        <div style={{ display: "flex", marginTop: "auto", justifyContent: "space-between",
          borderTop: `3px solid ${YELLOW}`, paddingTop: 16 }}>
          <div style={{ display: "flex", fontSize: 20, color: MUTED }}>
            playgolfedge.com — think you can beat the model?
          </div>
        </div>
      </div>
    ),
    { width: 1000, height: 560 },
  );
}
