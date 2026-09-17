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

type GameTab = "picks" | "standings" | "tails";
const TABS: { id: GameTab; label: string }[] = [
  { id: "picks",     label: "My Picks" },
  { id: "standings", label: "Standings" },
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
