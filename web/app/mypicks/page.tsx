"use client";

import { useState, useEffect } from "react";
import {
  getMyPicks,
  MyPicksResponse, WeeklyLineup, RosterPlayer,
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
      border: `1px solid ${hasEarnings ? "#1a3a20" : "#1e3a5f"}`,
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
          <span
            key={name}
            style={{
              fontSize: "0.78em", fontWeight: 600, color: "#9ab0c8",
              background: "#080f1e", border: "1px solid #1e3a5f",
              borderRadius: 4, padding: "3px 10px",
            }}
          >
            {name}
          </span>
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
      border: `1px solid ${depleted ? "#2a1a0a" : "#1e3a5f"}`,
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
          <span style={{
            fontWeight: 700, fontSize: "0.9em", color: depleted ? "#5f3a1e" : "#dde6f5",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {player.player_name}
          </span>
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
  const [data, setData]   = useState<MyPicksResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    getMyPicks()
      .then(setData)
      .catch(() => setError("Could not load My Picks. Is FastAPI running?"))
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

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1e3a5f" }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                background: "transparent", border: "none",
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
