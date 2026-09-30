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
import { getOpenEvents, getEventField, getPredictions, OpenEvent } from "@/lib/api";
import { nameKey } from "@/lib/names";

type Group = { id: number; name: string; is_owner: boolean };
type League = {
  id: number; name: string; season_start: string; season_end: string | null;
  tours: string[]; uses_per_player: number; players_per_week: number;
};
type SlatePick = { user_id: string; user_name: string; player_name: string };
type Standing = {
  user_id: string; user_name: string; total: number; pga_total: number; euro_total: number;
};

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 18, marginBottom: 16,
};
const btn = (primary: boolean): React.CSSProperties => ({
  cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "0.76em",
  textTransform: "uppercase", letterSpacing: "0.05em", borderRadius: 5,
  padding: "7px 12px",
  background: primary ? "var(--bc-yellow)" : "transparent",
  color: primary ? "#081f14" : "var(--bc-muted)",
  border: `1px solid ${primary ? "var(--bc-yellow)" : "var(--bc-line)"}`,
});

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
            <button key={g.id} onClick={() => setGroupId(g.id)} style={btn(g.id === group.id)}>{g.name}</button>
          ))}
        </div>
      )}
      {err && <div style={{ ...card, color: "var(--bc-red-text)" }}>{err}</div>}
      {league === undefined && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {league === null && <StartSeason group={group} onStarted={loadLeague} />}
      {league && <Season league={league} />}
    </>
  );
}

function StartSeason({ group, onStarted }: { group: Group; onStarted: () => void }) {
  const [name, setName] = useState("Fall Series");
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const [tours, setTours] = useState<string[]>(["pga", "euro"]);
  const [uses, setUses] = useState(3);
  const [perWeek, setPerWeek] = useState(3);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  if (!group.is_owner) {
    return (
      <div style={card}>
        <strong>No Let It Ride season in {group.name} yet.</strong>
        <p style={{ color: "var(--bc-muted)", fontSize: "0.88em", margin: "6px 0 0" }}>
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
        uses_per_player: uses, players_per_week: perWeek,
      }));
      onStarted();
    } catch (e) { setMsg((e as Error).message); }
    finally { setBusy(false); }
  }

  const input: React.CSSProperties = {
    background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
    color: "var(--bc-text)", padding: "7px 10px", fontSize: "0.88em", fontFamily: "inherit",
  };
  const toggle = (t: string) => setTours(ts => ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]);

  return (
    <div style={card}>
      <div style={{ fontWeight: 900, fontSize: "1.05em", marginBottom: 4 }}>Start a Let It Ride season</div>
      <p style={{ color: "var(--bc-muted)", fontSize: "0.84em", margin: "0 0 14px", lineHeight: 1.5 }}>
        Every week, pick golfers for each tour&apos;s event. Each golfer can only be used a few
        times all season — on either tour — so the question is always who to spend now and who
        to save. Most prize money wins. The model plays too, under the same budget.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        <label style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>Season name<br />
          <input style={{ ...input, width: "100%" }} value={name} maxLength={60} onChange={e => setName(e.target.value)} /></label>
        <label style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>Starts<br />
          <input style={{ ...input, width: "100%" }} type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
        <label style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>Uses per golfer<br />
          <input style={{ ...input, width: "100%" }} type="number" min={1} max={10} value={uses} onChange={e => setUses(Number(e.target.value))} /></label>
        <label style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>Golfers per event<br />
          <input style={{ ...input, width: "100%" }} type="number" min={1} max={10} value={perWeek} onChange={e => setPerWeek(Number(e.target.value))} /></label>
      </div>
      <div style={{ display: "flex", gap: 8, margin: "14px 0", alignItems: "center" }}>
        <span style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>Tours:</span>
        <button onClick={() => toggle("pga")} style={btn(tours.includes("pga"))}>PGA Tour</button>
        <button onClick={() => toggle("euro")} style={btn(tours.includes("euro"))}>DP World Tour</button>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "0.76em", margin: "0 0 12px" }}>
        The season runs open-ended — you close it when the group decides.
      </p>
      <button onClick={submit} disabled={busy || !name.trim() || !tours.length} style={btn(true)}>
        {busy ? "Starting…" : "Start season"}
      </button>
      {msg && <div style={{ color: "var(--bc-red-text)", fontSize: "0.84em", marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

function Season({ league }: { league: League }) {
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [tid, setTid] = useState("");
  const [standings, setStandings] = useState<Standing[]>([]);
  const [myUses, setMyUses] = useState<Record<string, number>>({});
  const [me, setMe] = useState("");

  const loadStandings = useCallback(() => {
    call(`/api/leagues/${league.id}/standings`).then(d => {
      setStandings((d.standings as Standing[]) ?? []);
      setMyUses((d.my_uses as Record<string, number>) ?? {});
      setMe(String(d.me ?? ""));
    }).catch(() => {});
  }, [league.id]);

  useEffect(() => {
    getOpenEvents().then(d => {
      const evs = (d.events ?? []).filter(e =>
        league.tours.includes(e.tour) && e.start_date >= league.season_start
        && (!league.season_end || e.start_date <= league.season_end));
      setEvents(evs);
      const first = evs.find(e => !e.locked) ?? evs[evs.length - 1];
      if (first) setTid(first.tournament_id);
    }).catch(() => {});
    loadStandings();
  }, [league, loadStandings]);

  const ev = events.find(e => e.tournament_id === tid);

  return (
    <>
      <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontWeight: 900, fontSize: "1.1em" }}>{league.name}</div>
          <div style={{ color: "var(--bc-muted)", fontSize: "0.78em", marginTop: 2 }}>
            {league.players_per_week} golfers per event · {league.uses_per_player} uses per golfer, all season,
            both tours · since {league.season_start}
          </div>
        </div>
      </div>

      {events.length === 0 ? (
        <div style={card}>No events open for picks right now — the next one appears here the week before it starts.</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 14, overflowX: "auto" }}>
            {events.map(e => (
              <button key={e.tournament_id} onClick={() => setTid(e.tournament_id)} style={{ ...btn(e.tournament_id === tid), whiteSpace: "nowrap" }}>
                {e.tour === "euro" ? "DPWT · " : "PGA · "}{e.name}{e.locked ? " (locked)" : ""}
              </button>
            ))}
          </div>
          {ev && <Slate key={ev.tournament_id} league={league} ev={ev} myUses={myUses} me={me} onChange={loadStandings} />}
        </>
      )}

      <SeasonStandings standings={standings} me={me} />
    </>
  );
}

function Slate({ league, ev, myUses, me, onChange }: {
  league: League; ev: OpenEvent; myUses: Record<string, number>; me: string; onChange: () => void;
}) {
  const [picks, setPicks] = useState<SlatePick[]>([]);
  const [locked, setLocked] = useState(ev.locked);
  const [field, setField] = useState<{ name: string; win: number | null }[]>([]);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

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
        <div style={{ color: locked ? "var(--bc-muted)" : "var(--bc-green)", fontSize: "0.78em", fontWeight: 700 }}>
          {locked ? "Locked — picks revealed" : `${mine.length} of ${league.players_per_week} picked`}
        </div>
      </div>

      {msg && (
        <div style={{ background: "color-mix(in srgb, var(--bc-red) 10%, transparent)", borderRadius: 6,
          padding: "8px 12px", marginBottom: 10, color: "var(--bc-red-text)", fontSize: "0.86em" }}>{msg}</div>
      )}

      {/* My slate */}
      <div style={{ display: "grid", gap: 6, marginBottom: 14 }}>
        {Array.from({ length: league.players_per_week }).map((_, i) => {
          const p = mine[i];
          return (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
              background: "var(--bc-panel)", border: "1px dashed var(--bc-line)", borderRadius: 6, padding: "8px 12px" }}>
              <span style={{ fontWeight: p ? 700 : 400, color: p ? "var(--bc-text)" : "var(--bc-muted)", fontSize: "0.88em" }}>
                {p ? p.player_name : `Slot ${i + 1} — open`}
              </span>
              {p && (
                <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span style={{ color: "var(--bc-muted)", fontSize: "0.74em" }}>
                    use {usedOf(p.player_name)} of {league.uses_per_player}
                  </span>
                  {!locked && (
                    <button onClick={() => act("DELETE", p.player_name)} disabled={busy === p.player_name} style={btn(false)}>
                      Drop
                    </button>
                  )}
                </span>
              )}
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
            color: "var(--bc-text)", padding: "7px 12px", fontSize: "0.86em", width: "100%",
            boxSizing: "border-box", marginBottom: 8, fontFamily: "inherit" }} />
          <div style={{ maxHeight: 360, overflowY: "auto", display: "grid", gap: 4 }}>
            {shown.map(f => {
              const used = usedOf(f.name);
              const spent = used >= league.uses_per_player;
              return (
                <div key={f.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "6px 10px", borderBottom: "1px solid var(--bc-line)", opacity: spent ? 0.45 : 1 }}>
                  <span style={{ fontSize: "0.86em" }}>
                    {f.name}
                    {f.win != null && <span style={{ color: "var(--bc-muted)", fontSize: "0.82em", marginLeft: 8 }}>{(f.win * 100).toFixed(1)}% to win</span>}
                  </span>
                  <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    {/* Budget meter: one pip per use, filled = spent. */}
                    <span title={`${used} of ${league.uses_per_player} uses spent`} style={{ display: "flex", gap: 3 }}>
                      {Array.from({ length: league.uses_per_player }).map((_, i) => (
                        <span key={i} style={{ width: 7, height: 7, borderRadius: "50%",
                          background: i < used ? "var(--bc-muted)" : "var(--bc-green)" }} />
                      ))}
                    </span>
                    <button onClick={() => act("POST", f.name)} disabled={full || spent || busy === f.name} style={btn(!full && !spent)}>
                      {spent ? "Spent" : "Pick"}
                    </button>
                  </span>
                </div>
              );
            })}
            {shown.length === 0 && <div style={{ color: "var(--bc-muted)", fontSize: "0.84em", padding: 8 }}>
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
      <div style={{ color: "var(--bc-muted)", fontSize: "0.74em", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Everyone&apos;s picks
      </div>
      {[...byUser.entries()].map(([id, u]) => (
        <div key={id} style={{ fontSize: "0.86em" }}>
          <strong style={{ color: id === me ? "var(--bc-yellow)" : "var(--bc-text)" }}>{u.name}</strong>
          <span style={{ color: "var(--bc-muted)" }}> — {u.players.join(", ")}</span>
        </div>
      ))}
    </div>
  );
}

function SeasonStandings({ standings, me }: { standings: Standing[]; me: string }) {
  const th: React.CSSProperties = {
    padding: "7px 12px", fontSize: "0.7em", color: "var(--bc-muted)", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "right", borderBottom: "1px solid var(--bc-line)",
  };
  const td: React.CSSProperties = {
    padding: "8px 12px", fontSize: "0.86em", textAlign: "right", borderBottom: "1px solid var(--bc-line)",
    fontVariantNumeric: "tabular-nums",
  };
  return (
    <div style={card}>
      <div style={{ fontWeight: 900, marginBottom: 8 }}>Season standings</div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>
          <th style={{ ...th, textAlign: "left" }}>Member</th>
          <th style={th}>PGA</th><th style={th}>DPWT</th><th style={th}>Total</th>
        </tr></thead>
        <tbody>
          {standings.map((s, i) => (
            <tr key={s.user_id}>
              <td style={{ ...td, textAlign: "left", fontWeight: 700, color: s.user_id === me ? "var(--bc-yellow)" : "var(--bc-text)" }}>
                {i + 1}. {s.user_name}
              </td>
              <td style={{ ...td, color: "var(--bc-muted)" }}>{money(s.pga_total)}</td>
              <td style={{ ...td, color: "var(--bc-muted)" }}>{money(s.euro_total)}</td>
              <td style={{ ...td, fontWeight: 800 }}>{money(s.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
