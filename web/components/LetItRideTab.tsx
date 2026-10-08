"use client";

/**
 * Let It Ride — the Friends Game's season mode (docs/PHASE2_DESIGN.md).
 *
 * One group, one active season. Each week has up to two slates (the PGA
 * event and the DPWT event), a few golfers per slate, and a season
 * budget of uses per golfer shared across both tours. Every rule is
 * enforced server-side; this screen only shows the budget and relays
 * the server's own messages (Jack's validateLeaguePick) verbatim.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getEventField, getPredictions, OpenEvent } from "@/lib/api";
import { nameKey } from "@/lib/names";
import LockCountdown from "@/components/LockCountdown";
import { choice } from "@/components/broadcast";
import { useStoredChoice } from "@/lib/useStoredChoice";
import EventNav, { NavEvent, landingEvent, Star } from "@/components/EventNav";

type Group = { id: number; name: string; is_owner: boolean };
type League = {
  id: number; name: string; season_start: string; season_end: string | null;
  tours: string[]; uses_per_player: number; players_per_week: number;
  uses_scope: "golfer" | "tour";
};
type SlatePick = { user_id: string; user_name: string; player_name: string };
type Standing = {
  user_id: string; user_name: string; total: number; pga_total: number; euro_total: number;
  stars: number;
  banked: number;   // settled money (from the standings route)
  live: number;     // projected money from events still in progress
};

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 18, marginBottom: 16,
};
// btn(true) is the screen's ONE yellow action (start / save a season).
// Toggles use choice(); per-row actions (Pick, Remove) use rowBtn so a
// 60-golfer list isn't 60 yellow buttons.
const btn = (primary: boolean): React.CSSProperties => ({
  cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "max(var(--fs-min), 0.76em)",
  textTransform: "uppercase", letterSpacing: "0.05em", borderRadius: 5,
  padding: "7px 12px",
  background: primary ? "var(--bc-yellow)" : "transparent",
  color: primary ? "#081f14" : "var(--bc-muted)",
  border: `1px solid ${primary ? "var(--bc-yellow)" : "var(--bc-line)"}`,
});

const rowBtn = (enabled: boolean): React.CSSProperties => ({
  ...btn(false),
  color: enabled ? "var(--bc-text)" : "var(--bc-muted)",
  border: `1px solid ${enabled ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
});

type Advice = { verdict: "spend" | "save" | "spent"; reason: string; save_for?: string };

/** Spend / Save tag on a golfer — a short fixed-width word so rows never
 *  wrap; tapping shows the why in the shared reason bar above the list.
 *  Quiet colors: it's a hint, not a call to action (no yellow). */
function AdviceTag({ a, open, onToggle }: { a?: Advice; open: boolean; onToggle: () => void }) {
  if (!a || a.verdict === "spent") return null;
  const save = a.verdict === "save";
  const c = save ? "var(--bc-orange)" : "var(--bc-green)";
  return (
    <button onClick={onToggle} aria-pressed={open} aria-label={`${save ? "Save" : "Spend"}: ${a.reason}`} style={{
      cursor: "pointer", fontFamily: "inherit", padding: "1px 5px", borderRadius: 3, flexShrink: 0,
      fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, letterSpacing: "0.03em", textTransform: "uppercase",
      color: open ? "#081f14" : c, background: open ? c : "transparent",
      border: `1px solid color-mix(in srgb, ${c} 45%, transparent)`,
    }}>
      {save ? "Save" : "Spend"}
    </button>
  );
}

/** The one place a reason shows: a single line above the list, so tapping a
 *  tag never changes row heights. With nothing selected it explains the tags. */
function AdviceBar({ name, a, onClose }: { name: string; a?: Advice; onClose: () => void }) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start", minHeight: 22, marginBottom: 6,
      color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", lineHeight: 1.4 }}>
      {a ? (
        <>
          <span><strong style={{ color: "var(--bc-text)" }}>{name}:</strong> {a.reason}</span>
          <button onClick={onClose} aria-label="Close" style={{ marginLeft: "auto", background: "none", border: "none",
            color: "var(--bc-muted)", cursor: "pointer", fontSize: "1em", padding: 0, fontFamily: "inherit" }}>✕</button>
        </>
      ) : (
        <span>Advice for your uses: <span style={{ color: "var(--bc-green)", fontWeight: 700 }}>Spend</span> = this week is
          one of his best windows · <span style={{ color: "var(--bc-orange)", fontWeight: 700 }}>Save</span> = he&apos;s
          worth more later. Tap a tag for why.</span>
      )}
    </div>
  );
}

/** Server messages arrive as "422: You've used…" — show the sentence. */
async function call(url: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const res = await fetch(url, init);
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String((d as { error?: string }).error ?? `Request failed (${res.status})`));
  return d as Record<string, unknown>;
}
const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export default function LetItRideTab() {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [league, setLeague] = useState<League | null | undefined>(undefined);
  const [err, setErr] = useState("");

  useEffect(() => {
    call("/api/friends/groups")
      .then(d => {
        const gs = (d.groups as Group[]) ?? [];
        setGroups(gs);
        if (gs.length) setGroupId(gs[0].id);
      })
      .catch(e => { setErr(e.message); setGroups([]); });
  }, []);

  const loadLeague = useCallback(() => {
    if (!groupId) return;
    setLeague(undefined);
    call(`/api/leagues?group_id=${groupId}`)
      .then(d => setLeague((d.league as League) ?? null))
      .catch(e => { setErr(e.message); setLeague(null); });
  }, [groupId]);
  useEffect(loadLeague, [loadLeague]);

  if (groups === null) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (groups.length === 0) {
    return <div style={card}>Let It Ride is played inside a group. Create or join one on the Groups tab first.</div>;
  }
  const group = groups.find(g => g.id === groupId) ?? groups[0];

  return (
    <>
      {groups.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {groups.map(g => (
            <button key={g.id} onClick={() => setGroupId(g.id)} style={choice(g.id === group.id)}>{g.name}</button>
          ))}
        </div>
      )}
      {err && <div style={{ ...card, color: "var(--bc-red-text)" }}>{err}</div>}
      {league === undefined && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {league === null && <StartSeason group={group} onStarted={loadLeague} />}
      {league && <Season league={league} isOwner={group.is_owner} onChanged={loadLeague} />}
    </>
  );
}

function StartSeason({ group, onStarted }: { group: Group; onStarted: () => void }) {
  const [name, setName] = useState("Fall Series");
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const [tours, setTours] = useState<string[]>(["pga", "euro"]);
  const [uses, setUses] = useState(3);
  const [perWeek, setPerWeek] = useState(3);
  const [scope, setScope] = useState<"golfer" | "tour">("tour");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  if (!group.is_owner) {
    return (
      <div style={card}>
        <strong>No Let It Ride season in {group.name} yet.</strong>
        <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)", margin: "6px 0 0" }}>
          The group owner starts one — nudge them.
        </p>
      </div>
    );
  }

  async function submit() {
    setBusy(true); setMsg("");
    try {
      await call("/api/leagues", json("POST", {
        group_id: group.id, name, season_start: start, tours,
        uses_per_player: uses, players_per_week: perWeek, uses_scope: scope,
      }));
      onStarted();
    } catch (e) { setMsg((e as Error).message); }
    finally { setBusy(false); }
  }

  const input: React.CSSProperties = {
    background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
    color: "var(--bc-text)", padding: "7px 10px", fontSize: "max(var(--fs-min), 0.88em)", fontFamily: "inherit",
  };
  const toggle = (t: string) => setTours(ts => ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]);

  return (
    <div style={card}>
      <div style={{ fontWeight: 900, fontSize: "1.05em", marginBottom: 4 }}>Start a Let It Ride season</div>
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)", margin: "0 0 14px", lineHeight: 1.5 }}>
        Every week, pick golfers for each tour&apos;s event. Each golfer can only be used a few
        times all season — on either tour — so the question is always who to spend now and who
        to save. Most prize money wins. The model plays too, under the same budget.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        <label style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Season name<br />
          <input style={{ ...input, width: "100%" }} value={name} maxLength={60} onChange={e => setName(e.target.value)} /></label>
        <label style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Starts<br />
          <input style={{ ...input, width: "100%" }} type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
        <label style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Uses per golfer<br />
          <input style={{ ...input, width: "100%" }} type="number" min={1} max={10} value={uses} onChange={e => setUses(Number(e.target.value))} /></label>
        <label style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Golfers per event<br />
          <input style={{ ...input, width: "100%" }} type="number" min={1} max={10} value={perWeek} onChange={e => setPerWeek(Number(e.target.value))} /></label>
      </div>
      <div style={{ display: "flex", gap: 8, margin: "14px 0", alignItems: "center" }}>
        <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Tours:</span>
        <button onClick={() => toggle("pga")} style={choice(tours.includes("pga"))}>PGA Tour</button>
        <button onClick={() => toggle("euro")} style={choice(tours.includes("euro"))}>DP World Tour</button>
      </div>
      <ScopeChoice scope={scope} setScope={setScope} />
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.76em)", margin: "0 0 12px" }}>
        The season runs open-ended — you close it when the group decides.
      </p>
      <button onClick={submit} disabled={busy || !name.trim() || !tours.length} style={btn(true)}>
        {busy ? "Starting…" : "Start season"}
      </button>
      {msg && <div style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

type Week = NavEvent;
const shortDate = (d: string) =>
  new Date(`${d.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

function Season({ league, isOwner, onChanged }: { league: League; isOwner: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [weeks, setWeeks] = useState<Week[] | null>(null);
  const [tid, setTid] = useState("");
  const [standings, setStandings] = useState<Standing[]>([]);
  const [myUses, setMyUses] = useState<Record<string, number>>({});
  const [myUsesByTour, setMyUsesByTour] = useState<Record<string, Record<string, number>>>({});
  const [winners, setWinners] = useState<Record<string, string[]>>({});
  const [me, setMe] = useState("");

  const loadStandings = useCallback(() => {
    call(`/api/leagues/${league.id}/standings`).then(d => {
      setStandings((d.standings as Standing[]) ?? []);
      setMyUses((d.my_uses as Record<string, number>) ?? {});
      setMyUsesByTour((d.my_uses_by_tour as Record<string, Record<string, number>>) ?? {});
      setWinners((d.weekly_winners as Record<string, string[]>) ?? {});
      setMe(String(d.me ?? ""));
    }).catch(() => {});
  }, [league.id]);

  // Land on the week that needs you: an open slate first, else a live
  // one, else the most recent final — on the tour that has it.
  useEffect(() => {
    call(`/api/leagues/${league.id}/weeks`).then(d => {
      const ws = (d.weeks as Week[]) ?? [];
      setWeeks(ws);
      const land = landingEvent(ws);
      if (land) setTid(land.tournament_id);
    }).catch(() => setWeeks([]));
    loadStandings();
  }, [league.id, loadStandings]);

  const week = (weeks ?? []).find(w => w.tournament_id === tid);

  const tourNames = league.tours.map(t => t === "euro" ? "DP World Tour" : "PGA Tour").join(" + ");

  return (
    <>
      <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontWeight: 900, fontSize: "1.1em" }}>{league.name}</div>
          <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)", marginTop: 2 }}>
            {league.players_per_week} golfers per event · {league.uses_per_player} uses per golfer
            {league.uses_scope === "tour" && league.tours.length > 1 ? " on each tour" : " all season"} · {tourNames} · since {league.season_start}
          </div>
        </div>
        {isOwner && (
          <button onClick={() => setEditing(e => !e)} style={choice(editing)}>{editing ? "Close" : "Season settings"}</button>
        )}
      </div>
      {editing && <SeasonSettings league={league} onSaved={() => { setEditing(false); onChanged(); }} />}

      {weeks === null ? <p style={{ color: "var(--bc-muted)" }}>Loading…</p>
        : weeks.length === 0 ? (
          <div style={card}>No events in this season yet.</div>
        ) : (
          <>
            <EventNav events={weeks} selected={tid} onPick={setTid} starred={winners} />
            {week && (week.status === "upcoming" || week.status === "awaiting" ? (
              <div style={card}>
                <strong>{week.name}</strong>
                <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.86em)", margin: "6px 0 0" }}>
                  {week.status === "awaiting"
                    ? `Starts ${shortDate(week.start_date)}. The field hasn't posted yet — picks open as soon as it does, usually by Tuesday.`
                    : `Starts ${shortDate(week.start_date)}. Picks open the week before, once the field is set.`}
                </p>
              </div>
            ) : (
              <Slate key={week.tournament_id} league={league} me={me} onChange={loadStandings}
                myUses={league.uses_scope === "tour" ? (myUsesByTour[week.tour] ?? {}) : myUses}
                ev={{ tournament_id: week.tournament_id, name: week.name, tour: week.tour,
                      start_date: week.start_date, end_date: "", locked: week.status !== "open",
                      finished: week.status === "completed", purse: null, has_model: true, field_available: true }}
                winners={(winners[week.tournament_id] ?? []).map(id => standings.find(s => s.user_id === id)?.user_name ?? "")} />
            ))}
          </>
        )}

      <SeasonStandings standings={standings} me={me} />
    </>
  );
}

function Slate({ league, ev, myUses, me, onChange, winners }: {
  league: League; ev: OpenEvent; myUses: Record<string, number>; me: string; onChange: () => void;
  winners: string[];
}) {
  const [picks, setPicks] = useState<SlatePick[]>([]);
  const [locked, setLocked] = useState(ev.locked);
  const [field, setField] = useState<{ name: string; win: number | null }[]>([]);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  // Spend/save advice for MY uses (private, pre-lock only), keyed by nameKey.
  const [advice, setAdvice] = useState<Record<string, Advice>>({});
  const [why, setWhy] = useState("");
  // Per-device preference; some players want a plain list.
  const [adviceMode, setAdviceMode] = useStoredChoice<"on" | "off">("lir-advice", ["on", "off"], "on");
  const showAdvice = adviceMode === "on";
  const setShowAdvice = (on: boolean) => setAdviceMode(on ? "on" : "off");

  useEffect(() => {
    if (ev.locked) return;
    call(`/api/leagues/${league.id}/advice?tid=${ev.tournament_id}`)
      .then(d => {
        const out: Record<string, Advice> = {};
        for (const [name, a] of Object.entries((d.verdicts ?? {}) as Record<string, Advice>)) out[nameKey(name)] = a;
        setAdvice(out);
      })
      .catch(() => setAdvice({}));  // advice is a bonus; the slate works without it
  }, [league.id, ev.tournament_id, ev.locked]);

  const load = useCallback(() => {
    call(`/api/leagues/${league.id}/picks?tid=${ev.tournament_id}`)
      .then(d => { setPicks((d.picks as SlatePick[]) ?? []); setLocked(!!d.locked); })
      .catch(e => setMsg(e.message));
  }, [league.id, ev.tournament_id]);

  useEffect(() => {
    load();
    // Field names from the event's field file; win chances (when the
    // model has this event) order the list so the contenders lead.
    Promise.all([
      getEventField(ev.tournament_id).catch(() => ({ players: [] as string[] })),
      getPredictions(200, ev.tournament_id).catch(() => null),
    ]).then(([f, p]) => {
      const win = new Map<string, number | null>(
        (p?.players ?? []).map(x => [nameKey(x.player_name), x.win_prob ?? null]));
      const names = f.players.length ? f.players : (p?.players ?? []).map(x => x.player_name);
      setField(names.map(n => ({ name: n, win: win.get(nameKey(n)) ?? null }))
        .sort((a, b) => (b.win ?? -1) - (a.win ?? -1)));
    });
  }, [ev.tournament_id, load]);

  const mine = picks.filter(p => p.user_id === me);
  const full = mine.length >= league.players_per_week;
  const usedOf = (n: string) => myUses[nameKey(n)] ?? 0;

  async function act(method: "POST" | "DELETE", player: string) {
    setBusy(player); setMsg("");
    try {
      await call(`/api/leagues/${league.id}/picks`, json(method, { tid: ev.tournament_id, player_name: player }));
      load(); onChange();
    } catch (e) { setMsg((e as Error).message); }
    finally { setBusy(""); }
  }

  const shown = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const mineSet = new Set(mine.map(p => p.player_name));
    return field.filter(f => !mineSet.has(f.name) && (!ql || f.name.toLowerCase().includes(ql))).slice(0, 60);
  }, [field, q, mine]);

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10, flexWrap: "wrap", gap: 6 }}>
        <div style={{ fontWeight: 800 }}>{ev.name}</div>
        <div style={{ color: locked ? "var(--bc-muted)" : "var(--bc-green)", fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700 }}>
          {locked ? "Locked — picks revealed" : `${mine.length} of ${league.players_per_week} picked`}
        </div>
      </div>
      {!locked && ev.start_date && (
        <div style={{ fontSize: "max(var(--fs-min), 0.78em)", marginBottom: 10 }}>
          <LockCountdown startDate={ev.start_date} tour={ev.tour} />
        </div>
      )}
      {winners.length > 0 && (
        <div style={{ color: "var(--bc-yellow)", fontWeight: 800, fontSize: "max(var(--fs-min), 0.86em)", marginBottom: 10 }}>
          <Star /> Week winner: {winners.join(" & ")}
        </div>
      )}
      {locked && mine.length > 0 && (
        <button onClick={() => shareReceipt(league.id, ev.tournament_id, me)} style={{ ...btn(false), marginBottom: 12 }}>
          Share my picks
        </button>
      )}

      {msg && (
        <div style={{ background: "color-mix(in srgb, var(--bc-red) 10%, transparent)", borderRadius: 6,
          padding: "8px 12px", marginBottom: 10, color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.86em)" }}>{msg}</div>
      )}

      {/* My slate */}
      <div style={{ display: "grid", gap: 6, marginBottom: 14 }}>
        {Array.from({ length: league.players_per_week }).map((_, i) => {
          const p = mine[i];
          return (
            <div key={i}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
              background: "var(--bc-panel)", border: "1px dashed var(--bc-line)", borderRadius: 6, padding: "8px 12px" }}>
              <span style={{ fontWeight: p ? 700 : 400, color: p ? "var(--bc-text)" : "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)" }}>
                {p ? p.player_name : `Slot ${i + 1} — open`}
              </span>
              {p && (
                <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  {!locked && showAdvice && <AdviceTag a={advice[nameKey(p.player_name)]} open={why === p.player_name}
                    onToggle={() => setWhy(w => w === p.player_name ? "" : p.player_name)} />}
                  <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.74em)" }}>
                    use {usedOf(p.player_name)} of {league.uses_per_player}
                  </span>
                  {!locked && (
                    <button onClick={() => act("DELETE", p.player_name)} disabled={busy === p.player_name} style={rowBtn(true)}>
                      Drop
                    </button>
                  )}
                </span>
              )}
            </div>
            </div>
          );
        })}
      </div>

      {locked ? (
        <LockedSlate picks={picks} me={me} />
      ) : (
        <>
          <input placeholder="Search the field…" value={q} onChange={e => setQ(e.target.value)} style={{
            background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
            color: "var(--bc-text)", padding: "7px 12px", fontSize: "max(var(--fs-min), 0.86em)", width: "100%",
            boxSizing: "border-box", marginBottom: 8, fontFamily: "inherit" }} />
          {Object.keys(advice).length > 0 && (
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                {showAdvice && <AdviceBar name={why} a={why ? advice[nameKey(why)] : undefined} onClose={() => setWhy("")} />}
              </div>
              <button onClick={() => { setShowAdvice(!showAdvice); setWhy(""); }} style={{ background: "none", border: "none",
                cursor: "pointer", color: "var(--bc-muted)", fontFamily: "inherit", fontSize: "max(var(--fs-min), 0.78em)",
                textDecoration: "underline", padding: 0, whiteSpace: "nowrap" }}>
                {showAdvice ? "Hide advice" : "Show advice"}
              </button>
            </div>
          )}
          <div style={{ maxHeight: 360, overflowY: "auto", display: "grid", gap: 4 }}>
            {shown.map(f => {
              const used = usedOf(f.name);
              const spent = used >= league.uses_per_player;
              return (
                <div key={f.name} style={{ padding: "6px 10px", borderBottom: "1px solid var(--bc-line)", opacity: spent ? 0.45 : 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: "max(var(--fs-min), 0.86em)", minWidth: 0 }}>
                    {f.name}
                    {f.win != null && <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", marginLeft: 8, whiteSpace: "nowrap" }}>{(f.win * 100).toFixed(1)}%</span>}
                  </span>
                  <span style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                    {showAdvice && !spent && <AdviceTag a={advice[nameKey(f.name)]} open={why === f.name}
                      onToggle={() => setWhy(w => w === f.name ? "" : f.name)} />}
                    {/* Budget meter: one pip per use, filled = spent. */}
                    <span title={`${used} of ${league.uses_per_player} uses spent`} style={{ display: "flex", gap: 3 }}>
                      {Array.from({ length: league.uses_per_player }).map((_, i) => (
                        <span key={i} style={{ width: 7, height: 7, borderRadius: "50%",
                          background: i < used ? "var(--bc-muted)" : "var(--bc-green)" }} />
                      ))}
                    </span>
                    <button onClick={() => act("POST", f.name)} disabled={full || spent || busy === f.name} style={rowBtn(!full && !spent)}>
                      {spent ? "Spent" : "Pick"}
                    </button>
                  </span>
                </div>
                </div>
              );
            })}
            {shown.length === 0 && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)", padding: 8 }}>
              {field.length ? "No golfers match." : "The field hasn't posted yet."}</div>}
          </div>
        </>
      )}
    </div>
  );
}

function LockedSlate({ picks, me }: { picks: SlatePick[]; me: string }) {
  const byUser = new Map<string, { name: string; players: string[] }>();
  for (const p of picks) {
    const u = byUser.get(p.user_id) ?? { name: p.user_id === "model" ? "The Model" : p.user_name, players: [] };
    u.players.push(p.player_name);
    byUser.set(p.user_id, u);
  }
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.74em)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Everyone&apos;s picks
      </div>
      {[...byUser.entries()].map(([id, u]) => (
        <div key={id} style={{ fontSize: "max(var(--fs-min), 0.86em)" }}>
          <strong style={{ color: id === me ? "var(--bc-green)" : "var(--bc-text)" }}>{u.name}</strong>
          <span style={{ color: "var(--bc-muted)" }}> — {u.players.join(", ")}</span>
        </div>
      ))}
    </div>
  );
}

// TODO(Jack): label banked vs projected in this table.
//   Right now the Total column shows s.total, which mixes final money with
//   money still moving. Show s.banked as the season total and, when
//   s.live > 0, a small "+$X live" next to it (and a caption explaining it).
//   Think about: what should sorting use — banked, or banked + live?
function SeasonStandings({ standings, me }: { standings: Standing[]; me: string }) {
  const th: React.CSSProperties = {
    padding: "7px 8px", fontSize: "max(var(--fs-min), 0.7em)", color: "var(--bc-muted)", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "right", borderBottom: "1px solid var(--bc-line)",
  };
  const td: React.CSSProperties = {
    padding: "8px 8px", fontSize: "max(var(--fs-min), 0.86em)", textAlign: "right", borderBottom: "1px solid var(--bc-line)",
    fontVariantNumeric: "tabular-nums",
  };
  return (
    <div style={card}>
      <div style={{ fontWeight: 900, marginBottom: 8 }}>Season standings</div>
      {/* Phones: the per-tour columns drop out (Total is the answer at a
          glance) and the table scrolls inside its card if it still can't fit. */}
      <div className="table-scroll">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>Member</th>
          <th style={th}>Wins</th><th className="mobile-hidden" style={th}>PGA</th><th className="mobile-hidden" style={th}>DPWT</th><th style={th}>Total</th>
        </tr></thead>
        <tbody>
          {standings.map((s, i) => (
            <tr key={s.user_id}>
              <td style={{ ...td, textAlign: "left", fontWeight: 700, color: s.user_id === me ? "var(--bc-green)" : "var(--bc-text)" }}>
                {i + 1}. {s.user_name}
              </td>
              <td style={{ ...td, color: "var(--bc-yellow)", whiteSpace: "nowrap" }}>
                {s.stars > 0 ? Array.from({ length: Math.min(s.stars, 5) }).map((_, i) => <Star key={i} />) : "—"}
                {s.stars > 5 && <span style={{ fontSize: "max(var(--fs-min-xs), 0.82em)", marginLeft: 3 }}>×{s.stars}</span>}
              </td>
              <td className="mobile-hidden" style={{ ...td, color: "var(--bc-muted)" }}>{money(s.pga_total)}</td>
              <td className="mobile-hidden" style={{ ...td, color: "var(--bc-muted)" }}>{money(s.euro_total)}</td>
              <td style={{ ...td, fontWeight: 700, color: "var(--bc-text)", whiteSpace: "nowrap" }}>
                {money(s.banked)}
                {s.live > 0 && (
                  <div style={{ color: "var(--bc-green)", fontSize: "max(var(--fs-min-xs), 0.82em)", fontWeight: 600 }}>
                    +{money(s.live)} live
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.74em)", margin: "8px 0 0" }}>
        Totals are banked prize money; + live is projected from events still in play.
      </p>
    </div>
  );
}


/** Receipt PNG: shares the image file on phones with Web Share, else opens it. */
async function shareReceipt(leagueId: number, tid: string, uid: string) {
  const url = `/api/receipt?game=ride&l=${leagueId}&tid=${encodeURIComponent(tid)}&u=${encodeURIComponent(uid)}`;
  if (typeof navigator.share === "function" && typeof navigator.canShare === "function") {
    try {
      const blob = await fetch(url).then(r => r.blob());
      const file = new File([blob], `golf-edge-${tid}.png`, { type: "image/png" });
      if (navigator.canShare({ files: [file] })) { await navigator.share({ files: [file] }); return; }
    } catch { /* fall through to opening it */ }
  }
  window.open(url, "_blank");
}

/** Season standings on their own (Friends Game → Standings, group feed):
 *  resolves the group's active season and reuses SeasonStandings. With
 *  no groupId, uses the first group that has a season. */
export function LetItRideStandings({ groupId, compact = false }: { groupId?: number; compact?: boolean }) {
  const [rows, setRows] = useState<Standing[] | null>(null);
  const [me, setMe] = useState("");
  const [label, setLabel] = useState("");

  useEffect(() => {
    (async () => {
      try {
        let leagueId: number | null = null;
        if (groupId) {
          const d = await call(`/api/leagues?group_id=${groupId}`);
          const l = d.league as League | null;
          if (l) { leagueId = l.id; setLabel(l.name); }
        } else {
          const d = await call("/api/leagues");
          const first = ((d.active as { id: number; name: string; group_name: string }[]) ?? [])[0];
          if (first) { leagueId = first.id; setLabel(`${first.name} · ${first.group_name}`); }
        }
        if (!leagueId) { setRows([]); return; }
        const s = await call(`/api/leagues/${leagueId}/standings`);
        setRows((s.standings as Standing[]) ?? []);
        setMe(String(s.me ?? ""));
      } catch { setRows([]); }
    })();
  }, [groupId]);

  if (rows === null) return compact ? null : <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (rows.length === 0) {
    return compact ? null : (
      <div style={card}>No Let It Ride season yet — the group owner starts one from Games → Let It Ride.</div>
    );
  }
  return (
    <>
      {label && !compact && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)", marginBottom: 8 }}>{label}</div>}
      <SeasonStandings standings={rows} me={me} />
    </>
  );
}

/** Uses budget: one per golfer across tours, or a separate one per tour. */
function ScopeChoice({ scope, setScope }: { scope: "golfer" | "tour"; setScope: (s: "golfer" | "tour") => void }) {
  return (
    <div style={{ margin: "0 0 12px" }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>Uses:</span>
        <button onClick={() => setScope("tour")} style={choice(scope === "tour")}>Separate per tour</button>
        <button onClick={() => setScope("golfer")} style={choice(scope === "golfer")}>Shared across tours</button>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.74em)", margin: "6px 0 0", lineHeight: 1.5 }}>
        {scope === "tour"
          ? "A golfer who plays both tours can be picked his full number of times on each — a DP World Tour pick never costs a PGA use."
          : "One budget per golfer, whichever tour you spend it on — spending a star on a small event costs you at the big ones."}
      </p>
    </div>
  );
}

/** Owner-only season editor. Changes apply going forward; existing
 *  picks always stand. Ending the season is final. */
function SeasonSettings({ league, onSaved }: { league: League; onSaved: () => void }) {
  const [name, setName] = useState(league.name);
  const [tours, setTours] = useState<string[]>(league.tours);
  const [uses, setUses] = useState(league.uses_per_player);
  const [perWeek, setPerWeek] = useState(league.players_per_week);
  const [scope, setScope] = useState<"golfer" | "tour">(league.uses_scope);
  const [end, setEnd] = useState(league.season_end ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [confirmEnd, setConfirmEnd] = useState(false);

  async function save(extra: Record<string, unknown> = {}) {
    setBusy(true); setMsg("");
    try {
      await call(`/api/leagues/${league.id}`, json("PATCH", {
        name, tours, uses_per_player: uses, players_per_week: perWeek,
        uses_scope: scope, season_end: end || null, ...extra,
      }));
      onSaved();
    } catch (e) { setMsg((e as Error).message); }
    finally { setBusy(false); }
  }

  const input: React.CSSProperties = {
    background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
    color: "var(--bc-text)", padding: "7px 10px", fontSize: "max(var(--fs-min), 0.88em)", fontFamily: "inherit", width: "100%",
    boxSizing: "border-box",
  };
  const label: React.CSSProperties = { fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" };
  const toggle = (t: string) => setTours(ts => ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]);

  return (
    <div style={{ ...card, borderColor: "var(--bc-line-hi)" }}>
      <div style={{ fontWeight: 900, marginBottom: 12 }}>Season settings</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 12 }}>
        <label style={label}>Season name<br /><input style={input} value={name} maxLength={60} onChange={e => setName(e.target.value)} /></label>
        <label style={label}>Uses per golfer<br /><input style={input} type="number" min={1} max={10} value={uses} onChange={e => setUses(Number(e.target.value))} /></label>
        <label style={label}>Golfers per event<br /><input style={input} type="number" min={1} max={10} value={perWeek} onChange={e => setPerWeek(Number(e.target.value))} /></label>
        <label style={label}>Ends (optional)<br /><input style={input} type="date" value={end} min={league.season_start} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <span style={label}>Tours:</span>
        <button onClick={() => toggle("pga")} style={choice(tours.includes("pga"))}>PGA Tour</button>
        <button onClick={() => toggle("euro")} style={choice(tours.includes("euro"))}>DP World Tour</button>
      </div>
      <ScopeChoice scope={scope} setScope={setScope} />
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.74em)", margin: "0 0 12px" }}>
        Changes apply from now on. Picks already made always stand.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => save()} disabled={busy || !name.trim() || !tours.length} style={btn(true)}>
          {busy ? "Saving…" : "Save changes"}
        </button>
        {!confirmEnd ? (
          <button onClick={() => setConfirmEnd(true)} style={btn(false)}>End season</button>
        ) : (
          <>
            <span style={{ fontSize: "max(var(--fs-min), 0.8em)", color: "var(--bc-red-text)" }}>End it for everyone? This is final.</span>
            <button onClick={() => save({ status: "complete" })} disabled={busy} style={{ ...btn(false), color: "var(--bc-red-text)", borderColor: "var(--bc-red-text)" }}>
              Yes, end season
            </button>
            <button onClick={() => setConfirmEnd(false)} style={btn(false)}>Cancel</button>
          </>
        )}
      </div>
      {msg && <div style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 10 }}>{msg}</div>}
    </div>
  );
}
