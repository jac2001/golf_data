"use client";

/**
 * /friends — the Friends Game.
 * =============================
 * Signed-in friends pick 3 players for the current tournament (same
 * format as Jack's league), see the season leaderboard graded by real
 * earnings, and track the model bets they've tailed. proxy.ts ensures
 * everyone here is signed in.
 */

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { PageHead, SubTabs } from "@/components/broadcast";
import { getPredictions, getOpenEvents, getEventField, OpenEvent } from "@/lib/api";

/** Link a player name to their profile page. The profile page already
 *  reads ?player= (a "deep link" — state carried in the URL, so it
 *  survives refresh and can be shared). */
function PlayerLink({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <Link href={`/players?player=${encodeURIComponent(name)}`}
      style={{ color: "inherit", textDecoration: "none", borderBottom: "1px dotted var(--bc-muted)", ...style }}>
      {name}
    </Link>
  );
}


function useApi() {
  const { getToken } = useAuth();
  return useCallback(async (url: string, init: RequestInit = {}) => {
    const token = await getToken();
    return fetchJson(url, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  }, [getToken]);
}

/** fetch that FAILS LOUDLY: any non-OK response or non-JSON body becomes
 *  an Error whose message says what actually came back — so the UI can
 *  show "401 Unauthorized" or "404 <!DOCTYPE html…" instead of a shrug. */
async function fetchJson(url: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const res = await fetch(url, init);
  const text = await res.text();
  try {
    const d = JSON.parse(text);
    if (!res.ok && d?.error) throw new Error(`${res.status}: ${d.error}`);
    return d;
  } catch (e) {
    if (e instanceof SyntaxError) {
      throw new Error(`${res.status}: non-JSON response (${text.slice(0, 60).replace(/\s+/g, " ")}…)`);
    }
    throw e;
  }
}

/** Push subscribe wants the VAPID public key as raw bytes, but it ships
 *  as URL-safe base64 — the standard little decoder. */
function vapidKeyBytes(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

/** One-line toggle for pick reminders. Renders nothing where push can't
 *  work (iOS Safari needs the app added to the Home Screen first). */
function ReminderBell() {
  const api = useApi();
  const [state, setState] = useState<"unsupported" | "off" | "on" | "busy">("unsupported");

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    navigator.serviceWorker.register("/sw.js")
      .then(reg => reg.pushManager.getSubscription())
      .then(sub => setState(sub ? "on" : "off"))
      .catch(() => setState("off"));
  }, []);

  async function toggle() {
    const prev = state;
    setState("busy");
    try {
      const reg = await navigator.serviceWorker.ready;
      if (prev === "on") {
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          await api("/api/friends/reminders", {
            method: "DELETE", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint: sub.endpoint }),
          });
          await sub.unsubscribe();
        }
        setState("off");
      } else {
        if ((await Notification.requestPermission()) !== "granted") { setState("off"); return; }
        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: vapidKeyBytes(process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "") as BufferSource,
        });
        await api("/api/friends/reminders", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subscription: sub.toJSON() }),
        });
        setState("on");
      }
    } catch { setState(prev === "busy" ? "off" : prev); }
  }

  if (state === "unsupported") return null;
  const on = state === "on";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
      color: "var(--bc-muted)", fontSize: "0.8em" }}>
      <span>Pick reminders — a nudge the day before an event locks if your picks aren&apos;t in.</span>
      <button onClick={toggle} disabled={state === "busy"} style={{
        ...btnQuiet, padding: "4px 12px", fontSize: "0.9em",
        color: on ? "#081f14" : "var(--bc-muted)",
        background: on ? "var(--bc-yellow)" : "transparent",
        borderColor: on ? "var(--bc-yellow)" : "var(--bc-line)",
      }}>
        {state === "busy" ? "…" : on ? "On" : "Off"}
      </button>
    </div>
  );
}

type GameTab = "games" | "standings" | "groups" | "bets" | "tails";
const TABS: { id: GameTab; label: string }[] = [
  { id: "games",     label: "Games" },
  { id: "standings", label: "Standings" },
  { id: "groups",    label: "Groups" },
  { id: "bets",      label: "My Bets" },
  { id: "tails",     label: "My Tails" },
];

type EventInfo = { tid: string; name: string; tour: string; locked: boolean; startDate: string };
type Standing = {
  user_id: string; user_name: string; total: number;
  events: Record<string, { picks: { player: string; earnings: number | null; position: string | null }[]; event_total: number; settled: boolean }>;
};
type Tail = { recommendation_id: string; label: string; tournament_id: string;
  odds_american: number | null; stake_units: number; outcome: string; pnl: number | null };

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

/** Compact board cells show the surname, whichever format the name
 *  arrived in: "Scheffler, Scottie" and "Scottie Scheffler" → "Scheffler". */
const lastName = (n: string) =>
  n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);

const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 20, marginBottom: 16,
};
const cell: React.CSSProperties = {
  padding: "8px 12px", borderBottom: "1px solid var(--bc-line)",
  fontSize: "0.86em", color: "var(--bc-text)", textAlign: "left",
};
const hdr: React.CSSProperties = {
  ...cell, color: "var(--bc-muted)", fontWeight: 600, fontSize: "0.74em",
  textTransform: "uppercase", letterSpacing: "0.04em",
};

const ModelBadge = () => (
  <span style={{ marginLeft: 6, fontSize: "0.62em", fontWeight: 900, letterSpacing: "0.08em",
    color: "#081f14", background: "var(--bc-yellow)", borderRadius: 3, padding: "2px 6px",
    textTransform: "uppercase", verticalAlign: "middle" }}>
    Model
  </span>
);

export default function FriendsPage() {
  const [tab, setTab] = useState<GameTab>("games");
  const [invited, setInvited] = useState(false);

  // Invite links land here (/friends?invite=1) but deliberately DON'T
  // auto-join: a link gets forwarded, screenshotted, and re-shared — the
  // invite CODE, texted separately, stays the actual key. The link's only
  // job is to get a friend signed in and standing in front of the join
  // form. (Read in an effect, not useSearchParams — one-shot action, and
  // the hook would force a Suspense boundary.)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("invite") || q.get("join")) {   // ?join= is the old link format
      window.history.replaceState(null, "", "/friends");
      setInvited(true);
      setTab("groups");
    }
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <PageHead
        kicker="Pick 3 · graded by real earnings · bragging rights only"
        title="Friends Game"
      />
      <SubTabs tabs={TABS} active={tab} onChange={setTab} />
      {invited && (
        <div style={{ background: "color-mix(in srgb, var(--bc-yellow) 10%, transparent)",
          border: "1px solid color-mix(in srgb, var(--bc-yellow) 35%, transparent)",
          borderRadius: 8, padding: "10px 14px", marginBottom: 14,
          color: "var(--bc-yellow)", fontSize: "0.88em", fontWeight: 600 }}>
          You&apos;ve been invited to a group — type the invite code from your
          friend&apos;s message below and hit Join.
        </div>
      )}
      {tab === "games" && <><ReminderBell /><GamesTab /></>}
      {tab === "standings" && <StandingsTab />}
      {tab === "groups" && <GroupsTab focusJoin={invited} />}
      {tab === "bets" && <MyBetsTab />}
      {tab === "tails" && <TailsTab />}
    </div>
  );
}

// ── Games: one tab, three modes ──────────────────────────────────────────────

type GameMode = "picks" | "rounds" | "fades";
const GAME_MODES: { id: GameMode; name: string; tag: string }[] = [
  { id: "picks",  name: "Weekly 3",   tag: "Pick 3 · most money wins" },
  { id: "rounds", name: "Round Game", tag: "1 per round · to par" },
  { id: "fades",  name: "Fade Game",  tag: "Fade 3 stars · least money wins" },
];

function GamesTab() {
  // Remembered per device — a convenience, so the page still renders
  // fine when storage is unavailable (private mode, prerender).
  const [mode, setMode] = useState<GameMode>(() => {
    try {
      const m = localStorage.getItem("friends-game-mode");
      if (m === "picks" || m === "rounds" || m === "fades") return m;
    } catch { /* default below */ }
    return "picks";
  });

  function pick(m: GameMode) {
    setMode(m);
    try { localStorage.setItem("friends-game-mode", m); } catch { /* fine */ }
  }

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
        gap: 8, marginBottom: 16 }}>
        {GAME_MODES.map(g => {
          const on = mode === g.id;
          return (
            <button key={g.id} onClick={() => pick(g.id)} style={{
              cursor: "pointer", textAlign: "left", fontFamily: "inherit",
              background: on ? "color-mix(in srgb, var(--bc-yellow) 10%, var(--bc-card))" : "var(--bc-card)",
              border: on ? "1px solid var(--bc-yellow)" : "1px solid var(--bc-line)",
              borderRadius: 8, padding: "10px 12px", minWidth: 0,
            }}>
              <div style={{ fontWeight: 900, fontSize: "0.86em", letterSpacing: "0.02em",
                color: on ? "var(--bc-yellow)" : "var(--bc-text)" }}>
                {g.name}
              </div>
              <div style={{ color: "var(--bc-muted)", fontSize: "0.7em", marginTop: 3, lineHeight: 1.35 }}>
                {g.tag}
              </div>
            </button>
          );
        })}
      </div>
      {mode === "picks" && <PicksTab />}
      {mode === "rounds" && <RoundGameTab />}
      {mode === "fades" && <FadeTab />}
    </>
  );
}

// ── My Picks ─────────────────────────────────────────────────────────────────

type FieldRow = { player_name: string; world_rank: number | null;
  win_prob: number | null; top10_prob: number | null; cut_prob: number | null };

/** Chips order: this week's action first, then history newest-first. */
function chipOrder(evs: OpenEvent[]): OpenEvent[] {
  const open = evs.filter(e => !e.finished);
  const done = evs.filter(e => e.finished)
    .sort((a, b) => b.start_date.localeCompare(a.start_date));
  return [...open, ...done];
}

const chipRow: React.CSSProperties = {
  display: "flex", gap: 8, marginBottom: 14,
  overflowX: "auto", flexWrap: "nowrap",
  paddingBottom: 4,          // keep the scrollbar off the chips
  WebkitOverflowScrolling: "touch" as never,
};

function PicksTab() {
  const api = useApi();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [event, setEvent]   = useState<EventInfo | null>(null);
  const [picks, setPicks]   = useState<string[]>([]);
  const [field, setField]   = useState<FieldRow[]>([]);
  const [query, setQuery]   = useState("");
  const [err, setErr]       = useState("");
  const [loading, setLoading] = useState(true);

  // Which events are pickable this week (PGA + DP World Tour can run
  // concurrently, so this is a list, not "the" tournament).
  useEffect(() => {
    getOpenEvents().then(d => {
      const evs = d.events ?? [];
      setEvents(evs);
      const firstOpen = evs.find(e => !e.locked) ?? evs.find(e => !e.finished) ?? evs[evs.length - 1];
      if (firstOpen) setSelected(firstOpen.tournament_id);
      else setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const load = useCallback(() => {
    if (!selected) return;
    setLoading(true); setErr("");
    api(`/api/friends/picks?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => { setEvent(d.event as EventInfo); setPicks(d.picks as string[]); })
      .catch(e => setErr(`Could not load your picks — ${e.message}`))
      .finally(() => setLoading(false));
  }, [api, selected]);

  useEffect(() => {
    if (!selected) return;
    load();
    const meta = events.find(e => e.tournament_id === selected);
    setField([]); setQuery("");
    if (meta?.has_model) {
      // PGA event: the field with THIS event's model numbers — the API
      // serves archived Tuesday predictions per tournament_id. Trust the
      // payload's own label, not the request: numbers for the wrong
      // event are worse than none (the euro-settle lesson).
      getPredictions(200, selected)
        .then(d => {
          if (String(d.tournament_id ?? "").toUpperCase() !== selected.toUpperCase()) {
            throw new Error("predictions are for a different event");
          }
          setField(
            (d.players ?? [])
              .filter((r: FieldRow) => r.player_name)
              .sort((a: FieldRow, b: FieldRow) => (b.win_prob ?? 0) - (a.win_prob ?? 0))
          );
        })
        .catch(() =>
          // No predictions saved for this event (pre-Tuesday, or a week
          // without an archive) — plain field, no numbers.
          getEventField(selected)
            .then(d => setField((d.players ?? []).map(p => ({
              player_name: p, world_rank: null, win_prob: null, top10_prob: null, cut_prob: null,
            }))))
            .catch(() => {})
        );
    } else {
      // Euro events have no model (yet) — plain alphabetized field.
      getEventField(selected)
        .then(d => setField((d.players ?? []).map(p => ({
          player_name: p, world_rank: null, win_prob: null, top10_prob: null, cut_prob: null,
        }))))
        .catch(() => {});
    }
  }, [load, selected, events]);

  async function add(player: string) {
    setErr("");
    try {
      const d = await api("/api/friends/picks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: player, tournament_id: selected }),
      });
      setPicks(d.picks as string[]); setQuery("");
    } catch (e) { setErr((e as Error).message); }
  }

  async function remove(player: string) {
    setErr("");
    try {
      const d = await api("/api/friends/picks", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: player, tournament_id: selected }),
      });
      setPicks(d.picks as string[]);
    } catch (e) { setErr((e as Error).message); }
  }

  if (loading) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (!event) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        {err || "No tournament to pick for right now — check back Tuesday of tournament week."}
      </p>
    </div>
  );

  // Derived state: computed from query + field on every render, never
  // stored — one source of truth, nothing to keep in sync.
  const visible = query.length >= 2
    ? field.filter(r => r.player_name.toLowerCase().includes(query.toLowerCase()))
    : field;

  return (
    <>
      {events.length > 1 && (
        <div style={chipRow}>
          {chipOrder(events).map(ev => (
            <button key={ev.tournament_id} onClick={() => setSelected(ev.tournament_id)} style={{
              ...btnQuiet, padding: "7px 14px", whiteSpace: "nowrap", flexShrink: 0,
              color: selected === ev.tournament_id ? "#081f14" : "var(--bc-muted)",
              background: selected === ev.tournament_id ? "var(--bc-yellow)" : "transparent",
              borderColor: selected === ev.tournament_id ? "var(--bc-yellow)" : "var(--bc-line)",
            }}>
              {ev.name}
              <span style={{ marginLeft: 6, fontSize: "0.85em", opacity: 0.75 }}>
                {ev.tour === "euro" ? "DPWT" : "PGA"}
                {ev.finished ? " · final" : ev.locked ? " · live" : ""}
              </span>
            </button>
          ))}
        </div>
      )}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: "1.05em" }}>{event.name || event.tid}</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginTop: 2 }}>
              {event.locked
                ? "Picks are locked — tournament underway."
                : `Picks lock ${event.startDate?.slice(0, 10) || "at tee-off"} · ${3 - picks.length} of 3 remaining`}
            </div>
          </div>
        </div>

        {/* Current picks */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          {picks.map(p => (
            <span key={p} style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
              borderRadius: 6, padding: "8px 12px", fontSize: "0.9em", fontWeight: 700,
            }}>
              <PlayerLink name={p} />
              {!event.locked && (
                <button onClick={() => remove(p)} aria-label={`Remove ${p}`} style={{
                  background: "none", border: "none", color: "var(--bc-muted)",
                  cursor: "pointer", fontSize: "1em", padding: 0, lineHeight: 1,
                }}>✕</button>
              )}
            </span>
          ))}
          {picks.length === 0 && (
            <span style={{ color: "var(--bc-muted)", fontSize: "0.85em" }}>No picks yet.</span>
          )}
        </div>

        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "0.84em", marginTop: 10 }}>{err}</p>}
      </div>

      {field.length === 0 && !event.locked && (
        <div style={{ ...card, background: "var(--bc-panel)" }}>
          <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.88em" }}>
            The field for {event.name} isn&apos;t announced yet — DP World Tour
            fields publish once the current event finishes (usually Friday).
            Check back this weekend; picks stay open until Thursday.
          </p>
        </div>
      )}

      {/* The field board: browse this week's field with the model's numbers
          and pick straight from the row. Names link to full profiles. */}
      {field.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 0" }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Filter the field…"
              style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
            />
          </div>
          <div style={{ maxHeight: 420, overflowY: "auto", marginTop: 10 }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr>
                <th style={hdr}>Player</th>
                <th style={{ ...hdr, textAlign: "right" }}>World rank</th>
                <th style={{ ...hdr, textAlign: "right" }}>Win chance</th>
                <th style={{ ...hdr, textAlign: "right" }}>Top-10</th>
                <th style={{ ...hdr, textAlign: "right" }}>Makes cut</th>
                <th style={hdr} />
              </tr></thead>
              <tbody>
                {visible.map(r => {
                  const picked = picks.includes(r.player_name);
                  return (
                    <tr key={r.player_name}
                        style={{ background: picked ? "var(--bc-card-hi)" : "transparent" }}>
                      <td style={{ ...cell, fontWeight: 600 }}>
                        <PlayerLink name={r.player_name} />
                      </td>
                      <td style={{ ...cell, textAlign: "right", color: "var(--bc-muted)", fontVariantNumeric: "tabular-nums" }}>
                        {r.world_rank != null ? `#${Math.round(r.world_rank)}` : "—"}
                      </td>
                      <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {r.win_prob != null ? `${(r.win_prob * 100).toFixed(1)}%` : "—"}
                      </td>
                      <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--bc-muted)" }}>
                        {r.top10_prob != null ? `${(r.top10_prob * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--bc-muted)" }}>
                        {r.cut_prob != null ? `${(r.cut_prob * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td style={{ ...cell, textAlign: "right" }}>
                        {picked ? (
                          !event.locked
                            ? <button onClick={() => remove(r.player_name)}
                                style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em", color: "var(--bc-green)" }}>
                                Picked ✓</button>
                            : <span style={{ color: "var(--bc-green)", fontSize: "0.78em", fontWeight: 700 }}>Picked ✓</span>
                        ) : (
                          <button onClick={() => add(r.player_name)}
                            disabled={event.locked || picks.length >= 3}
                            style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em",
                              opacity: event.locked || picks.length >= 3 ? 0.4 : 1,
                              cursor: event.locked || picks.length >= 3 ? "default" : "pointer" }}>
                            Pick</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ ...card, background: "var(--bc-panel)" }}>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.82em", lineHeight: 1.6 }}>
          How it works: pick 3 players per event before it starts. Your score is
          their combined prize money — real for PGA weeks, estimated from the
          purse and standard payout table for DP World Tour weeks (DataGolf
          doesn&apos;t publish euro prize money). Season standings live on the
          next tab — the model plays too, once its Tuesday lineup goes live.
        </p>
      </div>
    </>
  );
}

// ── Standings ────────────────────────────────────────────────────────────────

/** Opens the PNG in a new tab; on phones with Web Share, offers the sheet
 *  with the image attached so it drops straight into a chat. */
async function shareReceipt(tid: string, uid: string, game: "weekly" | "rounds" | "fades") {
  const url = `/api/receipt?tid=${encodeURIComponent(tid)}&u=${encodeURIComponent(uid)}&game=${game}`;
  if (typeof navigator.share === "function" && typeof navigator.canShare === "function") {
    try {
      const blob = await fetch(url).then(r => r.blob());
      const file = new File([blob], `golf-edge-${tid}.png`, { type: "image/png" });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file] });
        return;
      }
    } catch { /* fall through to opening it */ }
  }
  window.open(url, "_blank");
}

function StandingsTab() {
  // Season standings exist for the weekly and fade games only — the
  // Round Game is per-tournament by design (its whole-event board
  // lives on the Games tab), so no "rounds" pill here and a
  // remembered "rounds" mode falls back to picks.
  const [mode, setMode] = useState<"picks" | "fades">(() => {
    try {
      const m = localStorage.getItem("friends-game-mode");
      if (m === "picks" || m === "fades") return m;
    } catch { /* default below */ }
    return "picks";
  });

  return (
    <>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {GAME_MODES.filter(g => g.id !== "rounds").map(g => {
          const on = mode === g.id;
          return (
            <button key={g.id} onClick={() => setMode(g.id as "picks" | "fades")} style={{
              ...btnQuiet, padding: "7px 14px",
              color: on ? "#081f14" : "var(--bc-muted)",
              background: on ? "var(--bc-yellow)" : "transparent",
              borderColor: on ? "var(--bc-yellow)" : "var(--bc-line)",
            }}>
              {g.name}
            </button>
          );
        })}
      </div>
      {mode === "picks" && <WeeklyStandings />}
      {mode === "fades" && <FadeStandings />}
    </>
  );
}

function WeeklyStandings() {
  const api = useApi();
  const [standings, setStandings] = useState<Standing[] | null>(null);
  const [me, setMe] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api("/api/friends/leaderboard")
      .then(d => { setStandings((d.standings as Standing[]) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setStandings([]));
  }, [api]);

  if (!standings) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (standings.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        Nobody has made a pick yet. Be the first — the leaderboard starts with you.
      </p>
    </div>
  );

  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={hdr}>#</th><th style={hdr}>Player</th>
          <th style={{ ...hdr, textAlign: "right" }}>Season earnings</th>
          <th style={{ ...hdr, textAlign: "right" }}>Weeks</th>
        </tr></thead>
        <tbody>
          {standings.map((s, i) => (
            <React.Fragment key={s.user_id}>
              <tr onClick={() => setOpen(open === s.user_id ? null : s.user_id)}
                  style={{ cursor: "pointer", background: s.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
                <td style={{ ...cell, fontWeight: 800, color: "var(--bc-yellow)" }}>{i + 1}</td>
                <td style={{ ...cell, fontWeight: 700 }}>
                  {s.user_name}
                  {s.user_id === "model" && <ModelBadge />}
                  {s.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                </td>
                <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>
                  {money(s.total)}
                </td>
                <td style={{ ...cell, textAlign: "right", color: "var(--bc-muted)" }}>
                  {Object.keys(s.events).length}
                </td>
              </tr>
              {open === s.user_id && Object.entries(s.events).map(([tid, ev]) => (
                <tr key={tid}>
                  <td style={cell} />
                  <td colSpan={3} style={{ ...cell, background: "var(--bc-panel)", fontSize: "0.8em" }}>
                    <button onClick={() => shareReceipt(tid, s.user_id, "weekly")}
                      title="Share this week's receipt" style={{
                        background: "transparent", border: "1px solid var(--bc-line)",
                        borderRadius: 4, color: "var(--bc-yellow)", cursor: "pointer",
                        fontSize: "0.9em", padding: "1px 8px", marginRight: 8 }}>
                      Receipt
                    </button>
                    <span style={{ color: "var(--bc-muted)" }}>{tid} · </span>
                    {ev.picks.map((p, pi) => (
                      <React.Fragment key={p.player}>
                        {pi > 0 && " · "}
                        <PlayerLink name={p.player} />
                        {p.earnings != null ? ` (${money(p.earnings)})` : " (pending)"}
                      </React.Fragment>
                    ))}
                    <span style={{ float: "right", fontWeight: 700 }}>
                      {ev.settled ? money(ev.event_total) : "pending"}
                    </span>
                  </td>
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Fade Game season: EVENT WINS, not a money sum — summing a
 *  lowest-wins score would reward never playing. */
type FadeSeasonRow = { user_id: string; user_name: string; wins: number; entered: number; settled: number };

function FadeStandings() {
  const api = useApi();
  const [rows, setRows] = useState<FadeSeasonRow[] | null>(null);
  const [me, setMe] = useState("");

  useEffect(() => {
    api("/api/friends/fadeboard")
      .then(d => { setRows((d.standings as FadeSeasonRow[]) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setRows([]));
  }, [api]);

  if (!rows) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (rows.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        No fades yet — the season tally starts once the first Fade Game
        week settles. Place yours on the Games tab.
      </p>
    </div>
  );

  return (
    <>
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>#</th><th style={hdr}>Player</th>
            <th style={{ ...hdr, textAlign: "right" }}>Event wins</th>
            <th style={{ ...hdr, textAlign: "right" }}>Entered</th>
          </tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.user_id} style={{ background: r.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
                <td style={{ ...cell, fontWeight: 800, color: "var(--bc-yellow)" }}>{i + 1}</td>
                <td style={{ ...cell, fontWeight: 700 }}>
                  {r.user_name}
                  {r.user_id === "model" && <ModelBadge />}
                  {r.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                </td>
                <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                  {r.wins}
                </td>
                <td style={{ ...cell, textAlign: "right", color: "var(--bc-muted)" }}>{r.entered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "0.78em", marginTop: 10 }}>
        Scored in event wins — lowest combined earnings takes the week.
        Weekly boards live inside the Fade Game on the Games tab.
      </p>
    </>
  );
}

// ── My Tails ─────────────────────────────────────────────────────────────────

function TailsTab() {
  const api = useApi();
  const [tails, setTails] = useState<Tail[] | null>(null);
  const [summary, setSummary] = useState<{ pnl: number; settled: number; won: number } | null>(null);

  useEffect(() => {
    api("/api/friends/tail")
      .then(d => { setTails((d.tails as Tail[]) ?? []); setSummary((d.summary as { pnl: number; settled: number; won: number }) ?? null); })
      .catch(() => setTails([]));
  }, [api]);

  if (!tails) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (tails.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        You haven&apos;t tailed any bets yet. Hit &quot;Tail&quot; on a card on the
        Betting Board and your record shows up here — graded by the same honest
        ledger the public site uses.
      </p>
    </div>
  );

  return (
    <>
      {summary && summary.settled > 0 && (
        <div style={{ ...card, display: "flex", gap: 28 }}>
          <div>
            <div style={{ fontWeight: 900, fontSize: "1.3em",
              color: summary.pnl >= 0 ? "var(--bc-green)" : "var(--bc-red-text)" }}>
              {summary.pnl >= 0 ? "+" : ""}{summary.pnl.toFixed(2)}u
            </div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.72em" }}>NET P&L</div>
          </div>
          <div>
            <div style={{ fontWeight: 900, fontSize: "1.3em" }}>{summary.won}/{summary.settled}</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.72em" }}>SETTLED WINS</div>
          </div>
        </div>
      )}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>Bet</th><th style={hdr}>Event</th>
            <th style={{ ...hdr, textAlign: "right" }}>Odds</th>
            <th style={{ ...hdr, textAlign: "right" }}>Stake</th>
            <th style={{ ...hdr, textAlign: "right" }}>Result</th>
          </tr></thead>
          <tbody>
            {tails.map(t => (
              <tr key={t.recommendation_id}>
                <td style={cell}>{t.label}</td>
                <td style={{ ...cell, color: "var(--bc-muted)" }}>{t.tournament_id}</td>
                <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {t.odds_american != null ? (t.odds_american > 0 ? `+${t.odds_american}` : t.odds_american) : "—"}
                </td>
                <td style={{ ...cell, textAlign: "right" }}>{t.stake_units}u</td>
                <td style={{ ...cell, textAlign: "right", fontWeight: 700,
                  color: t.outcome === "won" ? "var(--bc-green)"
                       : t.outcome === "lost" ? "var(--bc-red-text)" : "var(--bc-muted)" }}>
                  {t.outcome === "pending" ? "pending"
                    : `${t.outcome}${t.pnl != null ? ` (${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}u)` : ""}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Groups ───────────────────────────────────────────────────────────────────

type Group = { id: number; name: string; invite_code: string; is_owner: boolean;
  members: { user_id: string; user_name: string }[] };
type FeedBet = { user_name: string; description: string; odds_american: number | null;
  stake_units: number; outcome: string; tournament_id: string };
type FeedPick = { event: string; user_name: string; player_name: string };

const btn: React.CSSProperties = {
  background: "var(--bc-yellow)", color: "#081f14", border: "none",
  borderRadius: 6, padding: "9px 16px", fontWeight: 800, fontSize: "0.8em",
  textTransform: "uppercase", letterSpacing: "0.05em", cursor: "pointer",
};
const btnQuiet: React.CSSProperties = {
  ...btn, background: "transparent", color: "var(--bc-muted)",
  border: "1px solid var(--bc-line)", fontWeight: 700,
};
const inputStyle: React.CSSProperties = {
  padding: "9px 12px", borderRadius: 6, fontSize: "0.88em",
  background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
  color: "var(--bc-text)", outline: "none",
};

function GroupsTab({ focusJoin = false }: { focusJoin?: boolean }) {
  const api = useApi();
  const joinRef = React.useRef<HTMLInputElement>(null);
  useEffect(() => { if (focusJoin) joinRef.current?.focus(); }, [focusJoin]);
  const [groups, setGroups]   = useState<Group[] | null>(null);
  const [open, setOpen]       = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [code, setCode]       = useState("");
  const [err, setErr]         = useState("");
  const [copied, setCopied]   = useState<number | null>(null);

  const load = useCallback(() => {
    api("/api/friends/groups")
      .then(d => setGroups((d.groups as Group[]) ?? []))
      .catch(e => { setErr(String(e.message)); setGroups([]); });
  }, [api]);
  useEffect(load, [load]);

  async function create() {
    if (!newName.trim()) return;
    setErr("");
    try {
      await api("/api/friends/groups", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      setNewName(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function join() {
    if (!code.trim()) return;
    setErr("");
    try {
      await api("/api/friends/groups", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite_code: code.trim() }),
      });
      setCode(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function leave(g: Group) {
    if (!confirm(g.is_owner
      ? `Delete "${g.name}" for everyone? This can't be undone.`
      : `Leave "${g.name}"?`)) return;
    try {
      await api("/api/friends/groups", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: g.id }),
      });
    } catch { /* list reload below shows truth either way */ }
    setOpen(null); load();
  }

  function copyCode(g: Group) {
    try { navigator.clipboard.writeText(g.invite_code); setCopied(g.id);
      setTimeout(() => setCopied(null), 1500); } catch { /* clipboard blocked */ }
  }

  function inviteMessage(g: Group) {
    return `Join my group "${g.name}" on Golf Edge: ${window.location.origin}/friends?invite=1 — invite code: ${g.invite_code}`;
  }

  // Copies a ready-to-text message: the link gets them signed in and onto
  // the join form; the code in the same message is what they type there.
  function copyLink(g: Group) {
    try {
      navigator.clipboard.writeText(inviteMessage(g));
      setCopied(g.id); setTimeout(() => setCopied(null), 1500);
    } catch { /* clipboard blocked */ }
  }

  // Native share sheet where the platform has one (iMessage/WhatsApp on
  // phones), clipboard fallback everywhere else. navigator.share exists
  // only in secure contexts and mostly on mobile — feature-detect, never
  // assume. A dismissed share sheet rejects with AbortError; that's the
  // user changing their mind, not an error to surface.
  async function share(g: Group) {
    const text = inviteMessage(g);
    if (typeof navigator.share === "function") {
      try { await navigator.share({ text }); return; }
      catch { return; /* dismissed or unsupported payload — no fallback spam */ }
    }
    copyLink(g);
  }

  if (!groups) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;

  return (
    <>
      <div style={{ ...card, display: "flex", gap: 20, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="New group name…" style={inputStyle}
            onKeyDown={e => e.key === "Enter" && create()} />
          <button onClick={create} style={btn}>Create</button>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input ref={joinRef} value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="Invite code…" style={{ ...inputStyle, width: 130,
              textTransform: "uppercase", letterSpacing: "0.1em" }}
            onKeyDown={e => e.key === "Enter" && join()} />
          <button onClick={join} style={btnQuiet}>Join</button>
        </div>
        {err && <span style={{ color: "var(--bc-red-text)", fontSize: "0.84em", alignSelf: "center" }}>{err}</span>}
      </div>

      {groups.length === 0 && (
        <div style={card}>
          <p style={{ color: "var(--bc-muted)", margin: 0, fontSize: "0.88em" }}>
            No groups yet. Create one and text the invite code to your friends —
            group standings, shared bets, and everyone&apos;s picks (revealed at
            tee-off) live here.
          </p>
        </div>
      )}

      {groups.map(g => (
        <div key={g.id} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, fontSize: "1.05em" }}>{g.name}</span>
            <button onClick={() => copyCode(g)} title="Copy invite code" style={{
              ...btnQuiet, padding: "4px 10px", letterSpacing: "0.1em",
              color: copied === g.id ? "var(--bc-green)" : "var(--bc-muted)",
            }}>
              {copied === g.id ? "Copied!" : g.invite_code}
            </button>
            <button onClick={() => share(g)} title="Share the invite (message + code)" style={{
              ...btn, padding: "5px 12px", fontSize: "0.72em",
            }}>
              Share
            </button>
            <button onClick={() => copyLink(g)} title="Copy the invite message" style={{
              ...btnQuiet, padding: "4px 10px",
              color: copied === g.id ? "var(--bc-green)" : "var(--bc-yellow)",
              borderColor: "color-mix(in srgb, var(--bc-yellow) 35%, transparent)",
            }}>
              {copied === g.id ? "Copied!" : "Copy invite"}
            </button>
            <span style={{ color: "var(--bc-muted)", fontSize: "0.8em" }}>
              {g.members.map(m => m.user_name).join(" · ")}
            </span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button onClick={() => setOpen(open === g.id ? null : g.id)} style={btnQuiet}>
                {open === g.id ? "Hide" : "Open"}
              </button>
              <button onClick={() => leave(g)} style={{ ...btnQuiet, color: "var(--bc-red-text)" }}>
                {g.is_owner ? "Delete" : "Leave"}
              </button>
            </span>
          </div>
          {open === g.id && <GroupFeed groupId={g.id} />}
        </div>
      ))}
    </>
  );
}

function GroupFeed({ groupId }: { groupId: number }) {
  const api = useApi();
  const [feed, setFeed] = useState<{ openNames?: string[];
    bets: FeedBet[]; picks: FeedPick[] } | null>(null);
  const [standings, setStandings] = useState<Standing[] | null>(null);

  useEffect(() => {
    api(`/api/friends/feed?group_id=${groupId}`)
      .then(d => setFeed(d as never))
      .catch(() => setFeed({ openNames: [], bets: [], picks: [] }));
    api(`/api/friends/leaderboard?group_id=${groupId}`)
      .then(d => setStandings((d.standings as Standing[]) ?? []))
      .catch(() => setStandings([]));
  }, [groupId, api]);

  if (!feed) return <p style={{ color: "var(--bc-muted)", marginTop: 12 }}>Loading…</p>;

  // Group picks by event, then by user, for the reveal.
  const byEvent = new Map<string, Map<string, string[]>>();
  for (const p of feed.picks) {
    const ev = byEvent.get(p.event) ?? new Map<string, string[]>();
    ev.set(p.user_name, [...(ev.get(p.user_name) ?? []), p.player_name]);
    byEvent.set(p.event, ev);
  }

  return (
    <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
      {/* Standings strip */}
      {standings && standings.length > 0 && (
        <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
          <div style={{ color: "var(--bc-muted)", fontSize: "0.7em", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Standings</div>
          {standings.map((st, i) => (
            <div key={st.user_id} style={{ display: "flex", fontSize: "0.86em", padding: "2px 0" }}>
              <span style={{ color: "var(--bc-yellow)", fontWeight: 800, width: 24 }}>{i + 1}</span>
              <span style={{ fontWeight: 600 }}>{st.user_name}</span>
              <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>{money(st.total)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Picks — revealed per event once it locks */}
      <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.7em", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Picks
        </div>
        {byEvent.size === 0 ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "0.84em" }}>
            {feed.openNames?.length
              ? `Hidden until tee-off — picks open for ${feed.openNames.join(", ")}.`
              : "No locked events with picks yet."}
          </span>
        ) : (
          [...byEvent.entries()].map(([evName, byUser]) => (
            <div key={evName} style={{ marginBottom: 8 }}>
              <div style={{ color: "var(--bc-yellow)", fontSize: "0.76em", fontWeight: 700 }}>{evName}</div>
              {[...byUser.entries()].map(([user, ps]) => (
                <div key={user} style={{ fontSize: "0.86em", padding: "2px 0" }}>
                  <span style={{ fontWeight: 600 }}>{user}</span>
                  <span style={{ color: "var(--bc-muted)" }}> — </span>
                  {ps.map((pl, pi) => (
                    <React.Fragment key={pl}>
                      {pi > 0 && <span style={{ color: "var(--bc-muted)" }}>, </span>}
                      <PlayerLink name={pl} style={{ color: "var(--bc-muted)" }} />
                    </React.Fragment>
                  ))}
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Shared bets */}
      <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.7em", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Shared bets</div>
        {feed.bets.length === 0 ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "0.84em" }}>
            Nothing shared yet — log a bet on the My Bets tab and flip it to shared.
          </span>
        ) : feed.bets.map((b, i) => (
          <div key={i} style={{ display: "flex", gap: 8, fontSize: "0.86em", padding: "3px 0", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600 }}>{b.user_name}</span>
            <span>{b.description}</span>
            {b.odds_american != null && (
              <span style={{ color: "var(--bc-muted)" }}>
                {b.odds_american > 0 ? `+${b.odds_american}` : b.odds_american}
              </span>
            )}
            <span style={{ marginLeft: "auto", fontWeight: 700,
              color: b.outcome === "won" ? "var(--bc-green)"
                   : b.outcome === "lost" ? "var(--bc-red-text)" : "var(--bc-muted)" }}>
              {b.outcome}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── My Bets ──────────────────────────────────────────────────────────────────

type UserBet = { id: number; tournament_id: string; description: string;
  odds_american: number | null; stake_units: number; shared: boolean; outcome: string };

function MyBetsTab() {
  const api = useApi();
  const [bets, setBets] = useState<UserBet[] | null>(null);
  const [desc, setDesc]   = useState("");
  const [odds, setOdds]   = useState("");
  const [stake, setStake] = useState("1");
  const [shared, setShared] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api("/api/friends/bets")
      .then(d => setBets((d.bets as UserBet[]) ?? []))
      .catch(e => { setErr((e as Error).message); setBets([]); });
  }, [api]);
  useEffect(load, [load]);

  async function add() {
    if (!desc.trim()) return;
    setErr("");
    try {
      await api("/api/friends/bets", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: desc.trim(),
          odds_american: odds.trim() ? parseInt(odds, 10) : null,
          stake_units: parseFloat(stake) || 1,
          shared,
        }),
      });
      setDesc(""); setOdds(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function patch(id: number, body: object) {
    try {
      await api("/api/friends/bets", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...body }),
      });
    } catch (e) { setErr((e as Error).message); }
    load();
  }

  async function del(id: number) {
    try {
      await api("/api/friends/bets", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
    } catch (e) { setErr((e as Error).message); }
    load();
  }

  if (!bets) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;

  return (
    <>
      <div style={card}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input value={desc} onChange={e => setDesc(e.target.value)}
            placeholder='What did you bet? e.g. "Scheffler top 10, DraftKings"'
            style={{ ...inputStyle, flex: "1 1 280px" }}
            onKeyDown={e => e.key === "Enter" && add()} />
          <input value={odds} onChange={e => setOdds(e.target.value)}
            placeholder="+450" style={{ ...inputStyle, width: 70 }} />
          <input value={stake} onChange={e => setStake(e.target.value)}
            placeholder="1" title="Stake (units)" style={{ ...inputStyle, width: 50 }} />
          <label style={{ display: "flex", alignItems: "center", gap: 6,
            color: "var(--bc-muted)", fontSize: "0.82em", cursor: "pointer" }}>
            <input type="checkbox" checked={shared} onChange={e => setShared(e.target.checked)} />
            share with my groups
          </label>
          <button onClick={add} style={btn}>Log bet</button>
        </div>
        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "0.84em", margin: "10px 0 0" }}>{err}</p>}
      </div>

      {bets.length === 0 ? (
        <div style={card}>
          <p style={{ color: "var(--bc-muted)", margin: 0, fontSize: "0.88em" }}>
            No bets logged. Anything you bet anywhere can live here — mark it
            shared and your groups see it in their feed.
          </p>
        </div>
      ) : bets.map(b => (
        <div key={b.id} style={{ ...card, padding: "12px 16px", display: "flex",
          gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: "0.9em" }}>{b.description}</span>
          {b.odds_american != null && (
            <span style={{ color: "var(--bc-muted)", fontSize: "0.84em" }}>
              {b.odds_american > 0 ? `+${b.odds_american}` : b.odds_american}
            </span>
          )}
          <span style={{ color: "var(--bc-muted)", fontSize: "0.8em" }}>{b.stake_units}u</span>
          <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
            {(["won", "lost", "pending"] as const).map(o => (
              <button key={o} onClick={() => patch(b.id, { outcome: o })} style={{
                ...btnQuiet, padding: "3px 9px", fontSize: "0.72em",
                color: b.outcome === o
                  ? (o === "won" ? "var(--bc-green)" : o === "lost" ? "var(--bc-red-text)" : "var(--bc-yellow)")
                  : "var(--bc-muted)",
                borderColor: b.outcome === o ? "currentColor" : "var(--bc-line)",
              }}>
                {o}
              </button>
            ))}
            <button onClick={() => patch(b.id, { shared: !b.shared })} title="Visible to your groups?" style={{
              ...btnQuiet, padding: "3px 9px", fontSize: "0.72em",
              color: b.shared ? "var(--bc-yellow)" : "var(--bc-muted)",
              borderColor: b.shared ? "currentColor" : "var(--bc-line)",
            }}>
              {b.shared ? "shared" : "private"}
            </button>
            <button onClick={() => del(b.id)} aria-label="Delete bet" style={{
              ...btnQuiet, padding: "3px 9px", fontSize: "0.72em" }}>✕</button>
          </span>
        </div>
      ))}
    </>
  );
}

// ── Round Game ───────────────────────────────────────────────────────────────

type RoundPicksState = { rounds: Record<string, string | null>; used: string[];
  locks: Record<string, boolean> };
type RoundRow = { user_id: string; user_name: string; total: number; scored: number;
  rounds: Record<string, { player: string; score: number | null; visible: boolean }> };

function RoundGameTab() {
  const api = useApi();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState("");
  const [state, setState] = useState<RoundPicksState | null>(null);
  const [eventName, setEventName] = useState("");
  const [field, setField] = useState<string[]>([]);
  const [board, setBoard] = useState<RoundRow[] | null>(null);
  const [me, setMe] = useState("");
  const [pickingRound, setPickingRound] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    getOpenEvents().then(d => {
      const evs = d.events ?? [];
      setEvents(evs);
      // Default to this week's action; history stays one chip away.
      const current = evs.find(e => !e.finished) ?? evs[evs.length - 1];
      if (current) setSelected(current.tournament_id);
    }).catch(() => {});
  }, []);

  const load = useCallback(() => {
    if (!selected) return;
    setErr("");
    api(`/api/friends/roundpicks?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => { setState(d as never); setEventName((d.event as EventInfo).name); })
      .catch(e => setErr(e.message));
    api(`/api/friends/roundboard?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => { setBoard((d.standings as RoundRow[]) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setBoard([]));
    getEventField(selected).then(d => setField(d.players ?? [])).catch(() => setField([]));
  }, [api, selected]);
  useEffect(load, [load]);

  async function pick(round: number, player: string) {
    setErr("");
    try {
      const d = await api("/api/friends/roundpicks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tournament_id: selected, round, player_name: player }),
      });
      setState(d as never); setPickingRound(null); setQuery("");
    } catch (e) { setErr((e as Error).message); }
  }

  async function clear(round: number) {
    setErr("");
    try {
      const d = await api("/api/friends/roundpicks", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tournament_id: selected, round }),
      });
      setState(d as never);
    } catch (e) { setErr((e as Error).message); }
  }

  const suggestions = query.length >= 2
    ? field.filter(pl => pl.toLowerCase().includes(query.toLowerCase())
        && !(state?.used ?? []).includes(pl)).slice(0, 8)
    : [];

  const fmt = (v: number) => (v > 0 ? `+${v}` : v === 0 ? "E" : String(v));

  return (
    <>
      {events.length > 1 && (
        <div style={chipRow}>
          {chipOrder(events).map(ev => (
            <button key={ev.tournament_id} onClick={() => { setSelected(ev.tournament_id); setPickingRound(null); }} style={{
              ...btnQuiet, padding: "7px 14px", whiteSpace: "nowrap", flexShrink: 0,
              color: selected === ev.tournament_id ? "#081f14" : "var(--bc-muted)",
              background: selected === ev.tournament_id ? "var(--bc-yellow)" : "transparent",
              borderColor: selected === ev.tournament_id ? "var(--bc-yellow)" : "var(--bc-line)",
            }}>
              {ev.name}
              {ev.finished && <span style={{ marginLeft: 6, fontSize: "0.85em", opacity: 0.75 }}>final</span>}
            </button>
          ))}
        </div>
      )}

      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: "1.05em", marginBottom: 4 }}>{eventName || selected}</div>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginBottom: 14 }}>
          One player per round, each player once per event. Score is their round
          to par; a missed round costs +{5}. Lowest total wins.
        </div>

        {[1, 2, 3, 4].map(r => {
          const locked = !!state?.locks?.[String(r)];
          const current = state?.rounds?.[String(r)] ?? null;
          return (
            <div key={r} style={{ display: "flex", alignItems: "center", gap: 10,
              padding: "8px 0", borderBottom: "1px solid var(--bc-line)", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 800, width: 32, color: locked ? "var(--bc-muted)" : "var(--bc-yellow)" }}>R{r}</span>
              {current
                ? <span style={{ fontWeight: 600 }}><PlayerLink name={current} /></span>
                : <span style={{ color: "var(--bc-muted)", fontSize: "0.85em" }}>
                    {locked ? "no pick — +5" : "no pick yet"}
                  </span>}
              {!locked && (
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button onClick={() => { setPickingRound(pickingRound === r ? null : r); setQuery(""); }}
                    style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em" }}>
                    {current ? "Change" : "Pick"}
                  </button>
                  {current && (
                    <button onClick={() => clear(r)} style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em" }}>✕</button>
                  )}
                </span>
              )}
              {locked && <span style={{ marginLeft: "auto", color: "var(--bc-muted)", fontSize: "0.72em" }}>locked</span>}
              {pickingRound === r && !locked && (
                <div style={{ flexBasis: "100%", position: "relative" }}>
                  <input autoFocus value={query} onChange={e => setQuery(e.target.value)}
                    placeholder={field.length ? "Search the field…" : "Field not announced yet"}
                    style={{ ...inputStyle, width: "100%", boxSizing: "border-box", marginTop: 6 }} />
                  {suggestions.length > 0 && (
                    <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
                      background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
                      borderRadius: 8, marginTop: 4, overflow: "hidden" }}>
                      {suggestions.map(pl => (
                        <button key={pl} onClick={() => pick(r, pl)} style={{
                          display: "block", width: "100%", textAlign: "left",
                          background: "none", border: "none", cursor: "pointer",
                          padding: "9px 14px", color: "var(--bc-text)", fontSize: "0.88em" }}>
                          {pl}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "0.84em", marginTop: 10 }}>{err}</p>}
      </div>

      {/* Event board */}
      {board && board.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>#</th><th style={hdr}>Player</th>
              {[1, 2, 3, 4].map(r => <th key={r} style={{ ...hdr, textAlign: "right" }}>R{r}</th>)}
              <th style={{ ...hdr, textAlign: "right" }}>Total</th>
            </tr></thead>
            <tbody>
              {board.map((row, i) => (
                <tr key={row.user_id} style={{ background: row.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, fontWeight: 800, color: "var(--bc-yellow)" }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 700 }}>
                    {row.user_name}
                    {row.user_id === "model" && <ModelBadge />}
                    {row.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                  </td>
                  {[1, 2, 3, 4].map(r => {
                    const c = row.rounds[String(r)];
                    return (
                      <td key={r} style={{ ...cell, textAlign: "right", fontSize: "0.8em" }}>
                        {!c ? <span style={{ color: "var(--bc-muted)" }}>—</span>
                          : !c.visible ? <span style={{ color: "var(--bc-muted)" }}>hidden</span>
                          : <>
                              <span style={{ color: "var(--bc-muted)" }}>{lastName(c.player)}</span>{" "}
                              <span style={{ fontWeight: 700, color: c.score == null ? "var(--bc-muted)"
                                : c.score < 0 ? "var(--bc-green)" : c.score > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                                {c.score == null ? "…" : fmt(c.score)}
                              </span>
                            </>}
                      </td>
                    );
                  })}
                  <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                    {row.scored ? fmt(row.total) : "—"}
                    {row.scored > 0 && (
                      <button onClick={() => shareReceipt(selected, row.user_id, "rounds")}
                        title="Share receipt" style={{
                          background: "transparent", border: "1px solid var(--bc-line)",
                          borderRadius: 4, color: "var(--bc-yellow)", cursor: "pointer",
                          fontSize: "0.72em", padding: "1px 7px", marginLeft: 8 }}>
                        ⇪
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ── Fade Game ────────────────────────────────────────────────────────────────

type FadePoolRow = { player_name: string; win_prob: number | null; expected_earnings: number | null };
type FadeEvent = EventInfo & { purse: number | null; hasModel: boolean };
type FadeBoardRow = { user_id: string; user_name: string; total: number | null;
  fades: { player: string; earnings: number | null; position: string | null }[] };

function FadeTab() {
  const api = useApi();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [event, setEvent] = useState<FadeEvent | null>(null);
  const [pool, setPool]   = useState<FadePoolRow[]>([]);
  const [partial, setPartial] = useState(false);
  const [fades, setFades] = useState<string[]>([]);
  const [board, setBoard] = useState<{ settled: boolean; earnings_estimated: boolean;
    standings: FadeBoardRow[]; me: string } | null>(null);
  const [err, setErr]     = useState("");
  const [loading, setLoading] = useState(true);

  // The fade pool is defined by model win chances, so only PGA
  // (has_model) events are playable.
  useEffect(() => {
    getOpenEvents().then(d => {
      const evs = (d.events ?? []).filter(e => e.has_model);
      setEvents(evs);
      const first = evs.find(e => !e.locked) ?? evs.find(e => !e.finished) ?? evs[evs.length - 1];
      if (first) setSelected(first.tournament_id);
      else setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const load = useCallback(() => {
    if (!selected) return;
    setLoading(true); setErr(""); setBoard(null);
    api(`/api/friends/fades?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => {
        const ev = d.event as FadeEvent;
        setEvent(ev);
        setPool((d.pool as FadePoolRow[]) ?? []);
        setPartial(!!d.partial);
        setFades((d.fades as string[]) ?? []);
        if (ev.locked) {
          api(`/api/friends/fadeboard?tournament_id=${encodeURIComponent(selected)}`)
            .then(b => setBoard(b as never)).catch(() => {});
        }
      })
      .catch(e => setErr(`Could not load the fade game — ${e.message}`))
      .finally(() => setLoading(false));
  }, [api, selected]);

  useEffect(() => { load(); }, [load]);

  async function toggle(player: string, faded: boolean) {
    setErr("");
    try {
      const d = await api("/api/friends/fades", {
        method: faded ? "DELETE" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: player, tournament_id: selected }),
      });
      setFades(d.fades as string[]);
    } catch (e) { setErr((e as Error).message); }
  }

  if (loading) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (!event) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0, lineHeight: 1.6 }}>
        The Fade Game is off this week. It needs a regular PGA stroke-play
        event with model numbers — team weeks (Ryder Cup, Presidents Cup)
        and off-weeks don&apos;t qualify because there&apos;s no individual
        prize money to fade. It opens back up on Tuesday of the next
        PGA tournament week.
      </p>
      {err && <p style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginTop: 10 }}>{err}</p>}
    </div>
  );

  return (
    <>
      {events.length > 1 && (
        <div style={chipRow}>
          {chipOrder(events).map(ev => (
            <button key={ev.tournament_id} onClick={() => setSelected(ev.tournament_id)} style={{
              ...btnQuiet, padding: "7px 14px", whiteSpace: "nowrap", flexShrink: 0,
              color: selected === ev.tournament_id ? "#081f14" : "var(--bc-muted)",
              background: selected === ev.tournament_id ? "var(--bc-yellow)" : "transparent",
              borderColor: selected === ev.tournament_id ? "var(--bc-yellow)" : "var(--bc-line)",
            }}>
              {ev.name}
              <span style={{ marginLeft: 6, fontSize: "0.85em", opacity: 0.75 }}>
                {ev.finished ? "final" : ev.locked ? "live" : ""}
              </span>
            </button>
          ))}
        </div>
      )}

      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: "1.05em" }}>{event.name || event.tid}</div>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginTop: 2 }}>
          {event.locked
            ? "Fades are locked — tournament underway."
            : `Pick 3 top-20 players you think will FLOP · lowest combined earnings wins · ${3 - fades.length} of 3 remaining`}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          {fades.map(p => (
            <span key={p} style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              background: "var(--bc-panel)", border: "1px solid var(--bc-red-text)",
              borderRadius: 6, padding: "8px 12px", fontSize: "0.9em", fontWeight: 700,
            }}>
              <PlayerLink name={p} />
              {!event.locked && (
                <button onClick={() => toggle(p, true)} aria-label={`Remove fade ${p}`} style={{
                  background: "none", border: "none", color: "var(--bc-muted)",
                  cursor: "pointer", fontSize: "1em", padding: 0, lineHeight: 1,
                }}>✕</button>
              )}
            </span>
          ))}
          {fades.length === 0 && (
            <span style={{ color: "var(--bc-muted)", fontSize: "0.85em" }}>No fades yet.</span>
          )}
        </div>

        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "0.84em", marginTop: 10 }}>{err}</p>}
      </div>

      {/* Post-lock: how everyone's fades are cashing (least money on top). */}
      {board && board.standings.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            Fadeboard
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.78em", marginLeft: 8 }}>
              lowest total wins{board.earnings_estimated ? " · est. purse split" : ""}
            </span>
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>#</th><th style={hdr}>Player</th>
              <th style={hdr}>Fades</th>
              <th style={{ ...hdr, textAlign: "right" }}>Total</th>
            </tr></thead>
            <tbody>
              {board.standings.map((row, i) => (
                <tr key={row.user_id} style={{ background: row.user_id === board.me ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, fontWeight: 800, color: "var(--bc-yellow)" }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 700 }}>
                    {row.user_name}
                    {row.user_id === "model" && <ModelBadge />}
                    {row.user_id === board.me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                  </td>
                  <td style={{ ...cell, fontSize: "0.8em", color: "var(--bc-muted)" }}>
                    {row.fades.map(f => (
                      <span key={f.player} style={{ marginRight: 10, whiteSpace: "nowrap" }}>
                        {lastName(f.player)}
                        {f.earnings != null && (
                          <span style={{ fontWeight: 700, marginLeft: 4,
                            color: f.earnings > 0 ? "var(--bc-red-text)" : "var(--bc-green)" }}>
                            {money(f.earnings)}
                          </span>
                        )}
                      </span>
                    ))}
                  </td>
                  <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                    {row.total != null ? money(row.total) : "…"}
                    {board.settled && row.total != null && (
                      <button onClick={() => shareReceipt(selected, row.user_id, "fades")}
                        title="Share receipt" style={{
                          background: "transparent", border: "1px solid var(--bc-line)",
                          borderRadius: 4, color: "var(--bc-yellow)", cursor: "pointer",
                          fontSize: "0.72em", padding: "1px 7px", marginLeft: 8 }}>
                        ⇪
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* The pool: only these 20 are fair game. */}
      {!event.locked && pool.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            The pool
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.78em", marginLeft: 8 }}>
              top 20 by model win chance — pick the ones you don&apos;t believe in
            </span>
          </div>
          {partial && (
            <div style={{ margin: "4px 16px 0", padding: "8px 12px", borderRadius: 6,
              background: "color-mix(in srgb, var(--bc-yellow) 10%, transparent)",
              border: "1px solid color-mix(in srgb, var(--bc-yellow) 35%, transparent)",
              color: "var(--bc-yellow)", fontSize: "0.78em", fontWeight: 600 }}>
              Early field — only the first commitments are in. Numbers and the
              pool firm up once the full field posts (usually Tuesday).
            </div>
          )}
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>Player</th>
              <th style={{ ...hdr, textAlign: "right" }}>Win chance</th>
              <th style={{ ...hdr, textAlign: "right" }}>Model expects</th>
              <th style={hdr} />
            </tr></thead>
            <tbody>
              {pool.map(r => {
                const faded = fades.includes(r.player_name);
                return (
                  <tr key={r.player_name}
                      style={{ background: faded ? "var(--bc-card-hi)" : "transparent" }}>
                    <td style={{ ...cell, fontWeight: 600 }}>
                      <PlayerLink name={r.player_name} />
                    </td>
                    <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {r.win_prob != null ? `${(r.win_prob * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--bc-muted)" }}>
                      {r.expected_earnings != null ? money(r.expected_earnings) : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right" }}>
                      {faded ? (
                        <button onClick={() => toggle(r.player_name, true)}
                          style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em", color: "var(--bc-red-text)" }}>
                          Faded ✕</button>
                      ) : (
                        <button onClick={() => toggle(r.player_name, false)}
                          disabled={fades.length >= 3}
                          style={{ ...btnQuiet, padding: "3px 10px", fontSize: "0.74em",
                            opacity: fades.length >= 3 ? 0.4 : 1,
                            cursor: fades.length >= 3 ? "default" : "pointer" }}>
                          Fade</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!event.locked && pool.length === 0 && (
        <div style={{ ...card, background: "var(--bc-panel)" }}>
          <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.88em", lineHeight: 1.6 }}>
            The pool for {event.name} isn&apos;t set yet. Fades open once the
            model&apos;s numbers post for this event — usually Tuesday, when
            the full field is announced and predictions run. Your 3 fades
            stay open until tee-off Thursday, so there&apos;s no rush.
          </p>
        </div>
      )}

      <div style={{ ...card, background: "var(--bc-panel)" }}>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.82em", lineHeight: 1.6 }}>
          How it works: before tee-off, fade 3 players from the top 20 —
          the favorites you think are overhyped. Your score is their combined
          prize money and the LOWEST total wins, so fading the eventual champion
          is a disaster. The model plays too: it fades the three players in its
          own top 20 it expects to earn the least.
        </p>
      </div>
    </>
  );
}
