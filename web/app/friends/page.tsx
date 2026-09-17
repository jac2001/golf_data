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
import { PageHead, SubTabs } from "@/components/broadcast";
import { getPlayerList } from "@/lib/api";

type GameTab = "picks" | "standings" | "groups" | "bets" | "tails";
const TABS: { id: GameTab; label: string }[] = [
  { id: "picks",     label: "My Picks" },
  { id: "standings", label: "Standings" },
  { id: "groups",    label: "Groups" },
  { id: "bets",      label: "My Bets" },
  { id: "tails",     label: "My Tails" },
];

type EventInfo = { tid: string; name: string; locked: boolean; startDate: string };
type Standing = {
  user_id: string; user_name: string; total: number;
  events: Record<string, { picks: { player: string; earnings: number | null; position: string | null }[]; event_total: number; settled: boolean }>;
};
type Tail = { recommendation_id: string; label: string; tournament_id: string;
  odds_american: number | null; stake_units: number; outcome: string; pnl: number | null };

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

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

export default function FriendsPage() {
  const [tab, setTab] = useState<GameTab>("picks");

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <PageHead
        kicker="Pick 3 · graded by real earnings · bragging rights only"
        title="Friends Game"
      />
      <SubTabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "picks" && <PicksTab />}
      {tab === "standings" && <StandingsTab />}
      {tab === "groups" && <GroupsTab />}
      {tab === "bets" && <MyBetsTab />}
      {tab === "tails" && <TailsTab />}
    </div>
  );
}

// ── My Picks ─────────────────────────────────────────────────────────────────

function PicksTab() {
  const [event, setEvent]   = useState<EventInfo | null>(null);
  const [picks, setPicks]   = useState<string[]>([]);
  const [field, setField]   = useState<string[]>([]);
  const [query, setQuery]   = useState("");
  const [err, setErr]       = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    fetch("/api/friends/picks")
      .then(r => r.json())
      .then(d => {
        if (d.error) { setErr(d.error); return; }
        setEvent(d.event); setPicks(d.picks);
      })
      .catch(() => setErr("Could not load your picks."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    getPlayerList().then(d => setField(d.players ?? [])).catch(() => {});
  }, [load]);

  async function add(player: string) {
    setErr("");
    const res = await fetch("/api/friends/picks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: player }),
    });
    const d = await res.json();
    if (d.error) setErr(d.error); else { setPicks(d.picks); setQuery(""); }
  }

  async function remove(player: string) {
    setErr("");
    const res = await fetch("/api/friends/picks", {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: player }),
    });
    const d = await res.json();
    if (d.error) setErr(d.error); else setPicks(d.picks);
  }

  if (loading) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (!event) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        {err || "No tournament to pick for right now — check back Tuesday of tournament week."}
      </p>
    </div>
  );

  const suggestions = query.length >= 2
    ? field.filter(p => p.toLowerCase().includes(query.toLowerCase()) && !picks.includes(p)).slice(0, 8)
    : [];

  return (
    <>
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
              {p}
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

        {/* Add pick */}
        {!event.locked && picks.length < 3 && (
          <div style={{ position: "relative", marginTop: 14 }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search this week's field…"
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: "0.9em",
                background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
                color: "var(--bc-text)", outline: "none", boxSizing: "border-box",
              }}
            />
            {suggestions.length > 0 && (
              <div style={{
                position: "absolute", top: "100%", left: 0, right: 0, zIndex: 50,
                background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
                borderRadius: 8, marginTop: 4, overflow: "hidden",
              }}>
                {suggestions.map(p => (
                  <button key={p} onClick={() => add(p)} style={{
                    display: "block", width: "100%", textAlign: "left",
                    background: "none", border: "none", cursor: "pointer",
                    padding: "9px 14px", color: "var(--bc-text)", fontSize: "0.88em",
                  }}>
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "0.84em", marginTop: 10 }}>{err}</p>}
      </div>

      <div style={{ ...card, background: "var(--bc-panel)" }}>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.82em", lineHeight: 1.6 }}>
          How it works: pick 3 players before the tournament starts. Your week&apos;s
          score is their combined real prize money. Season standings live on the
          next tab — the model plays too, once its Tuesday lineup goes live.
        </p>
      </div>
    </>
  );
}

// ── Standings ────────────────────────────────────────────────────────────────

function StandingsTab() {
  const [standings, setStandings] = useState<Standing[] | null>(null);
  const [me, setMe] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/friends/leaderboard")
      .then(r => r.json())
      .then(d => { setStandings(d.standings ?? []); setMe(d.me ?? ""); })
      .catch(() => setStandings([]));
  }, []);

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
                  {s.user_name}{s.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
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
                    <span style={{ color: "var(--bc-muted)" }}>{tid} · </span>
                    {ev.picks.map(p =>
                      `${p.player}${p.earnings != null ? ` (${money(p.earnings)})` : " (pending)"}`
                    ).join(" · ")}
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

// ── My Tails ─────────────────────────────────────────────────────────────────

function TailsTab() {
  const [tails, setTails] = useState<Tail[] | null>(null);
  const [summary, setSummary] = useState<{ pnl: number; settled: number; won: number } | null>(null);

  useEffect(() => {
    fetch("/api/friends/tail")
      .then(r => r.json())
      .then(d => { setTails(d.tails ?? []); setSummary(d.summary ?? null); })
      .catch(() => setTails([]));
  }, []);

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
type FeedPick = { user_name: string; player_name: string };

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

function GroupsTab() {
  const [groups, setGroups]   = useState<Group[] | null>(null);
  const [open, setOpen]       = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [code, setCode]       = useState("");
  const [err, setErr]         = useState("");
  const [copied, setCopied]   = useState<number | null>(null);

  const load = useCallback(() => {
    fetch("/api/friends/groups").then(r => r.json())
      .then(d => setGroups(d.groups ?? [])).catch(() => setGroups([]));
  }, []);
  useEffect(load, [load]);

  async function create() {
    if (!newName.trim()) return;
    setErr("");
    const res = await fetch("/api/friends/groups", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim() }),
    });
    const d = await res.json();
    if (d.error) setErr(d.error); else { setNewName(""); load(); }
  }

  async function join() {
    if (!code.trim()) return;
    setErr("");
    const res = await fetch("/api/friends/groups", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_code: code.trim() }),
    });
    const d = await res.json();
    if (d.error) setErr(d.error); else { setCode(""); load(); }
  }

  async function leave(g: Group) {
    if (!confirm(g.is_owner
      ? `Delete "${g.name}" for everyone? This can't be undone.`
      : `Leave "${g.name}"?`)) return;
    await fetch("/api/friends/groups", {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id: g.id }),
    });
    setOpen(null); load();
  }

  function copyCode(g: Group) {
    try { navigator.clipboard.writeText(g.invite_code); setCopied(g.id);
      setTimeout(() => setCopied(null), 1500); } catch { /* clipboard blocked */ }
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
          <input value={code} onChange={e => setCode(e.target.value.toUpperCase())}
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
  const [feed, setFeed] = useState<{ event: { name: string; locked: boolean } | null;
    bets: FeedBet[]; picks: FeedPick[] } | null>(null);
  const [standings, setStandings] = useState<Standing[] | null>(null);

  useEffect(() => {
    fetch(`/api/friends/feed?group_id=${groupId}`).then(r => r.json())
      .then(setFeed).catch(() => setFeed({ event: null, bets: [], picks: [] }));
    fetch(`/api/friends/leaderboard?group_id=${groupId}`).then(r => r.json())
      .then(d => setStandings(d.standings ?? [])).catch(() => setStandings([]));
  }, [groupId]);

  if (!feed) return <p style={{ color: "var(--bc-muted)", marginTop: 12 }}>Loading…</p>;

  const byUser = new Map<string, string[]>();
  for (const p of feed.picks) {
    byUser.set(p.user_name, [...(byUser.get(p.user_name) ?? []), p.player_name]);
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

      {/* This week's picks — revealed at lock */}
      <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.7em", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          {feed.event ? `Picks · ${feed.event.name}` : "Picks"}
        </div>
        {feed.event && !feed.event.locked ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "0.84em" }}>
            Hidden until tee-off — no copying.
          </span>
        ) : byUser.size === 0 ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "0.84em" }}>No picks this week.</span>
        ) : (
          [...byUser.entries()].map(([user, ps]) => (
            <div key={user} style={{ fontSize: "0.86em", padding: "2px 0" }}>
              <span style={{ fontWeight: 600 }}>{user}</span>
              <span style={{ color: "var(--bc-muted)" }}> — {ps.join(", ")}</span>
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
  const [bets, setBets] = useState<UserBet[] | null>(null);
  const [desc, setDesc]   = useState("");
  const [odds, setOdds]   = useState("");
  const [stake, setStake] = useState("1");
  const [shared, setShared] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    fetch("/api/friends/bets").then(r => r.json())
      .then(d => setBets(d.bets ?? [])).catch(() => setBets([]));
  }, []);
  useEffect(load, [load]);

  async function add() {
    if (!desc.trim()) return;
    setErr("");
    const res = await fetch("/api/friends/bets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description: desc.trim(),
        odds_american: odds.trim() ? parseInt(odds, 10) : null,
        stake_units: parseFloat(stake) || 1,
        shared,
      }),
    });
    const d = await res.json();
    if (d.error) setErr(d.error); else { setDesc(""); setOdds(""); load(); }
  }

  async function patch(id: number, body: object) {
    await fetch("/api/friends/bets", {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, ...body }),
    });
    load();
  }

  async function del(id: number) {
    await fetch("/api/friends/bets", {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
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
