"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  getMyPicks, getTournament, setMyPicks, clearMyPicks,
  MyPicksResponse, WeeklyLineup, RosterPlayer, Tournament,
} from "@/lib/api";

type Tab = "log" | "roster";

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n}`;
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function UsePips({ used, max }: { used: number; max: number }) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          style={{
            width: 8, height: 8, borderRadius: "50%",
            background: i < used ? "#00c44f" : "#1e3a5f",
            boxShadow: i < used ? "0 0 4px #00c44f55" : "none",
          }}
        />
      ))}
    </div>
  );
}

function WeekCard({ week }: { week: WeeklyLineup }) {
  const hasEarnings = week.earnings > 0;
  return (
    <div style={{
      background: "#0d1a30",
      borderTop: `1px solid ${hasEarnings ? "#1a3a20" : "#1e3a5f"}`,
      borderRight: `1px solid ${hasEarnings ? "#1a3a20" : "#1e3a5f"}`,
      borderBottom: `1px solid ${hasEarnings ? "#1a3a20" : "#1e3a5f"}`,
      borderLeft: `3px solid ${hasEarnings ? "#00c44f" : "#1e3a5f"}`,
      borderRadius: 8, padding: "14px 18px",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontWeight: 700, color: "#dde6f5", fontSize: "0.95em" }}>
            {week.tournament}
          </div>
          <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 2 }}>
            {week.week != null ? `Week ${week.week}` : ""}
            {week.date ? ` · ${fmtDate(week.date)}` : ""}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          {hasEarnings ? (
            <div style={{ fontWeight: 800, color: "#00c44f", fontSize: "1.05em" }}>
              {fmtMoney(week.earnings)}
            </div>
          ) : (
            <div style={{ color: "#3a5060", fontSize: "0.8em" }}>—</div>
          )}
          {week.finish != null && (
            <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 2 }}>
              {week.finish === 1 ? "Winner" : `WRP: ${week.finish}`}
            </div>
          )}
        </div>
      </div>

      {/* Lineup */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {week.lineup.map(name => (
          <Link
            key={name}
            href={`/players?player=${encodeURIComponent(name)}`}
            style={{
              fontSize: "0.78em", fontWeight: 600, color: "#9ab0c8",
              background: "#080f1e", border: "1px solid #1e3a5f",
              borderRadius: 4, padding: "3px 10px", textDecoration: "none",
              display: "inline-block",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "#4cb8ff"; e.currentTarget.style.borderColor = "#2a5080"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "#9ab0c8"; e.currentTarget.style.borderColor = "#1e3a5f"; }}
          >
            {name}
          </Link>
        ))}
      </div>
    </div>
  );
}

function RosterRow({ player, maxUses }: { player: RosterPlayer; maxUses: number }) {
  const [expanded, setExpanded] = useState(false);
  const remaining = player.remaining_uses;
  const depleted = remaining === 0;

  return (
    <div style={{
      background: "#0d1a30",
      borderTop: `1px solid ${depleted ? "#2a1a0a" : "#1e3a5f"}`,
      borderRight: `1px solid ${depleted ? "#2a1a0a" : "#1e3a5f"}`,
      borderBottom: `1px solid ${depleted ? "#2a1a0a" : "#1e3a5f"}`,
      borderLeft: `3px solid ${depleted ? "#5f3a1e" : remaining === maxUses ? "#1e3a5f" : "#00c44f"}`,
      borderRadius: 8, marginBottom: 6,
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: "100%", background: "transparent", border: "none", cursor: "pointer",
          padding: "12px 16px", display: "flex", alignItems: "center",
          justifyContent: "space-between", gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
          <UsePips used={player.times_used} max={maxUses} />
          <Link
            href={`/players?player=${encodeURIComponent(player.player_name)}`}
            onClick={e => e.stopPropagation()}
            style={{
              fontWeight: 700, fontSize: "0.9em", color: depleted ? "#5f3a1e" : "#dde6f5",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              textDecoration: "none",
            }}
            onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
            onMouseLeave={e => (e.currentTarget.style.color = depleted ? "#5f3a1e" : "#dde6f5")}
          >
            {player.player_name}
          </Link>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20, flexShrink: 0 }}>
          <span style={{
            fontSize: "0.85em", fontWeight: 700,
            color: player.total_earnings > 0 ? "#00c44f" : "#4a6080",
          }}>
            {player.total_earnings > 0 ? fmtMoney(player.total_earnings) : "—"}
          </span>
          <span style={{ fontSize: "0.65em", color: "#4a6080" }}>
            {remaining} left
          </span>
          <span style={{ color: "#4a6080", fontSize: "0.8em" }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <div style={{ padding: "0 16px 12px", borderTop: "1px solid #1a2a3a" }}>
          {player.tournaments.length === 0 ? (
            <div style={{ color: "#4a6080", fontSize: "0.78em", paddingTop: 10 }}>No tournament history.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 10 }}>
              {player.tournaments.map((t, i) => (
                <div key={i} style={{
                  display: "flex", justifyContent: "space-between",
                  fontSize: "0.78em", color: "#7f9ab0",
                }}>
                  <span>{t.tournament}</span>
                  <div style={{ display: "flex", gap: 16 }}>
                    {t.result && <span style={{ color: "#4a6080" }}>{t.result}</span>}
                    <span style={{ color: t.earnings > 0 ? "#00c44f" : "#4a6080", fontWeight: 600 }}>
                      {t.earnings > 0 ? fmtMoney(t.earnings) : "—"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MyPicksPage() {
  const [activeTab, setActiveTab] = useState<Tab>("log");
  const [data, setData]           = useState<MyPicksResponse | null>(null);
  const [tournament, setTournament] = useState<Tournament | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  const reload = () => {
    getMyPicks().then(setData).catch(() => {});
  };

  useEffect(() => {
    Promise.all([
      getMyPicks(),
      getTournament(),
    ]).then(([picks, tourn]) => {
      setData(picks);
      setTournament(tourn);
    }).catch(() => setError("Could not load My Picks. Is FastAPI running?"))
      .finally(() => setLoading(false));
  }, []);

  if (error) {
    return (
      <div style={{ maxWidth: 600, margin: "40px auto", padding: 24, background: "#1a0d0d", border: "1px solid #5f1e1e", borderRadius: 10, color: "#e74c3c" }}>
        <strong>Error</strong>
        <p style={{ margin: "8px 0 0", color: "#c0392b", fontSize: "0.9em" }}>{error}</p>
      </div>
    );
  }

  if (loading || !data) {
    return <div style={{ color: "#7f8c8d", padding: "40px 0", textAlign: "center" }}>Loading…</div>;
  }

  const { weeks, roster, summary, max_uses } = data;

  // Current week = most recent week matching tournament name (or first empty one)
  const currentWeek = tournament
    ? weeks.find(w => w.tournament === tournament.name) ?? weeks[0]
    : weeks[0];
  const currentLineup = currentWeek?.lineup ?? [];

  const TABS: { key: Tab; label: string }[] = [
    { key: "log",    label: `Season Log (${weeks.length})` },
    { key: "roster", label: `Player Roster (${roster.length})` },
  ];

  return (
    <div className="page-wrap-md">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 800, color: "#dde6f5", margin: 0 }}>
          My Picks
        </h1>
        <p style={{ color: "#7f8c8d", fontSize: "0.88em", margin: "4px 0 0" }}>
          {data.season} Season · {max_uses} uses per player
        </p>
      </div>

      {/* ── Summary strip ────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
        <SummaryCard label="Season Earnings"   value={fmtMoney(summary.total_earnings)} />
        <SummaryCard label="Weeks Played"      value={String(summary.total_weeks)} />
        <SummaryCard label="Players Used"      value={String(summary.total_players)} />
        <SummaryCard label="Avg per Week"      value={fmtMoney(summary.avg_earnings)} />
        {summary.best_week && (
          <SummaryCard
            label="Best Week"
            value={fmtMoney(summary.best_week.earnings)}
            sub={summary.best_week.tournament}
          />
        )}
      </div>

      {/* ── Current week picks entry ─────────────────────────────────────── */}
      {tournament && (
        <SetPicksPanel
          tournament={tournament}
          currentLineup={currentLineup}
          onSaved={reload}
        />
      )}

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1e3a5f" }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none",
                borderBottom: `2px solid ${isActive ? "#00c44f" : "transparent"}`,
                color: isActive ? "#dde6f5" : "#7f8c8d",
                padding: "8px 16px", fontSize: "0.88em",
                fontWeight: isActive ? 700 : 500,
                cursor: "pointer", marginBottom: -1,
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Season Log ───────────────────────────────────────────────────── */}
      {activeTab === "log" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {weeks.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
              No weekly lineups recorded yet.
            </div>
          ) : (
            weeks.map((w, i) => <WeekCard key={i} week={w} />)
          )}
        </div>
      )}

      {/* ── Player Roster ────────────────────────────────────────────────── */}
      {activeTab === "roster" && (
        <div>
          <div style={{ fontSize: "0.65em", color: "#4a6080", marginBottom: 12 }}>
            Sorted by total earnings · Click a player to see tournament history · Dots = uses
          </div>
          {roster.map(p => (
            <RosterRow key={p.player_name} player={p} maxUses={max_uses} />
          ))}
        </div>
      )}

    </div>
  );
}

function SetPicksPanel({
  tournament, currentLineup, onSaved,
}: {
  tournament: Tournament;
  currentLineup: string[];
  onSaved: () => void;
}) {
  const maxPicks = 3;
  const haspicks = currentLineup.length > 0;
  const [inputs, setInputs] = useState<string[]>(["", "", ""]);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const handleSubmit = async () => {
    const picks = inputs.map(s => s.trim()).filter(Boolean);
    if (picks.length !== maxPicks) { setMsg(`Enter all ${maxPicks} picks`); return; }
    setSaving(true); setMsg(null);
    try {
      await setMyPicks(tournament.tournament_id, picks);
      setMsg("Picks saved!");
      onSaved();
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : "Error saving picks");
    } finally { setSaving(false); }
  };

  const handleClear = async () => {
    setClearing(true); setMsg(null);
    try {
      await clearMyPicks(tournament.tournament_id);
      setMsg("Picks cleared.");
      onSaved();
    } catch { setMsg("Error clearing picks"); }
    finally { setClearing(false); }
  };

  return (
    <div style={{
      background: "#080f1e",
      borderTop: "1px solid #1e4a2f", borderRight: "1px solid #1e4a2f", borderBottom: "1px solid #1e4a2f",
      borderLeft: "3px solid #00c44f", borderRadius: 8,
      padding: "16px 20px", marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 700, color: "#dde6f5", fontSize: "0.95em" }}>
            {tournament.name ?? "This Week"} — Set Picks
          </div>
          <div style={{ fontSize: "0.7em", color: "#4a6080", marginTop: 2 }}>
            Enter player names exactly as stored in the tracker (e.g. "N Taylor", "A Fitzpatrick", "W Clark")
          </div>
        </div>
        {haspicks && (
          <button
            onClick={handleClear}
            disabled={clearing}
            style={{
              background: "transparent", border: "1px solid #5f1e1e",
              color: "#e74c3c", borderRadius: 5, padding: "4px 12px",
              fontSize: "0.75em", cursor: clearing ? "default" : "pointer",
            }}
          >
            {clearing ? "Clearing…" : "Clear Picks"}
          </button>
        )}
      </div>

      {haspicks ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {currentLineup.map(name => (
            <span key={name} style={{
              background: "#0d1f15", border: "1px solid #1e4a2f",
              color: "#00c44f", borderRadius: 4, padding: "4px 12px",
              fontSize: "0.85em", fontWeight: 600,
            }}>{name}</span>
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          {inputs.map((v, i) => (
            <input
              key={i}
              value={v}
              onChange={e => { const a = [...inputs]; a[i] = e.target.value; setInputs(a); }}
              placeholder={`Player ${i + 1}`}
              style={{
                background: "#0d1a30", border: "1px solid #1e3a5f",
                borderRadius: 5, color: "#dde6f5", padding: "7px 12px",
                fontSize: "0.85em", width: 150, outline: "none",
              }}
            />
          ))}
          <button
            onClick={handleSubmit}
            disabled={saving}
            style={{
              background: saving ? "#0d1929" : "#0a1f3a",
              border: "1px solid #1e5a3f", borderRadius: 5,
              color: saving ? "#4a6080" : "#00c44f",
              padding: "7px 20px", fontSize: "0.85em", fontWeight: 700,
              cursor: saving ? "default" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Confirm Picks"}
          </button>
        </div>
      )}

      {msg && (
        <div style={{ marginTop: 10, fontSize: "0.8em", color: msg.includes("Error") || msg.includes("Enter") ? "#e74c3c" : "#00c44f" }}>
          {msg}
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 130px", minWidth: 120,
    }}>
      <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1em", fontWeight: 700, color: "#dde6f5", marginTop: 2 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</div>}
    </div>
  );
}
