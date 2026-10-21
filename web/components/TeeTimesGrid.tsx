"use client";

import Link from "next/link";
import { TeeTimesResponse } from "@/lib/api";

type Props = { data: TeeTimesResponse; myPicks?: string[] };

// Rank badge color
function rankColor(rank: number | null): string {
  if (rank == null) return "var(--bc-muted)";
  if (rank <= 5)  return "var(--bc-yellow)";
  if (rank <= 15) return "var(--bc-green)";
  if (rank <= 30) return "var(--bc-yellow)";
  return "var(--bc-muted)";
}

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

export default function TeeTimesGrid({ data, myPicks = [] }: Props) {
  const myPicksNorm = new Set(myPicks.map(normName));
  if (!data.groups.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
        No tee times available for Round {data.round ?? "—"}.
      </div>
    );
  }

  const totalPlayers = data.groups.reduce((s, g) => s + g.players.length, 0);

  return (
    <div>
      {/* Summary strip */}
      <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)", marginBottom: 14, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <span>Round {data.round}</span>
        <span>·</span>
        <span>{data.groups.length} tee times</span>
        <span>·</span>
        <span>{totalPlayers} players</span>
      </div>

      {/* Grid of tee time cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 10 }}>
        {data.groups.map(group => {
          return (
            <div key={group.tee_time} style={{
              background: "var(--bc-panel)",
              border: "1px solid var(--bc-line)",
              borderRadius: 8, overflow: "hidden",
            }}>
              {/* Tee time header */}
              <div style={{
                background: "var(--bc-panel)",
                padding: "6px 12px",
                borderBottom: "1px solid var(--bc-line)",
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <span style={{ color: "var(--bc-yellow)", fontWeight: 700, fontSize: "max(var(--fs-min), 0.85em)" }}>
                  {group.tee_time}
                </span>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  {group.players[0]?.start_tee && (
                    <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min-xs), 0.68em)" }}>
                      Hole {group.players[0].start_tee}
                    </span>
                  )}
                </div>
              </div>

              {/* Column headers. Edge left the tee sheet (Jack, Oct 21): it's a
                  betting number, not what you look for in a tee time. */}
              <div style={{
                display: "grid", gridTemplateColumns: "1fr auto",
                padding: "3px 12px", borderBottom: "1px solid var(--bc-panel)",
              }}>
                <span style={{ fontSize: "max(var(--fs-min-xs), 0.58em)", color: "var(--bc-line)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Player</span>
                <span style={{ fontSize: "max(var(--fs-min-xs), 0.58em)", color: "var(--bc-line)", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "right" }}>
                  Win% · Top10%
                </span>
              </div>

              {/* Players */}
              {group.players.map((p, i) => {
                const isPick = myPicksNorm.has(normName(p.name));
                const rColor = rankColor(p.model_rank);

                return (
                  <div key={p.name} style={{
                    padding: "8px 12px",
                    borderBottom: i < group.players.length - 1 ? "1px solid var(--bc-card)" : "none",
                    borderLeft: isPick ? "2px solid var(--bc-green)" : "2px solid transparent",
                    background: isPick ? "#091a0f" : "transparent",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}>
                    {/* Left: rank badge + name */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                      <span style={{
                        fontSize: "max(var(--fs-min-xs), 0.62em)", fontWeight: 800, color: rColor,
                        background: "var(--bc-panel)", padding: "2px 5px", borderRadius: 3,
                        minWidth: 28, textAlign: "center", flexShrink: 0,
                        border: `1px solid ${rColor}33`,
                      }}>
                        #{p.model_rank ?? "—"}
                      </span>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <Link
                            href={`/players?player=${encodeURIComponent(p.name)}`}
                            style={{
                              color: isPick ? "var(--bc-green)" : "#c0cce0",
                              fontWeight: isPick ? 700 : 600,
                              fontSize: "max(var(--fs-min), 0.85em)",
                              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                              textDecoration: "none",
                            }}
                            onMouseEnter={e => (e.currentTarget.style.color = "var(--bc-yellow)")}
                            onMouseLeave={e => (e.currentTarget.style.color = isPick ? "var(--bc-green)" : "#c0cce0")}
                          >
                            {p.name}
                          </Link>
                          {isPick && (
                            <span style={{
                              fontSize: "max(var(--fs-min-xs), 0.58em)", fontWeight: 800, color: "var(--bc-green)",
                              background: "color-mix(in srgb, var(--bc-green) 15%, transparent)", border: "1px solid color-mix(in srgb, var(--bc-green) 27%, transparent)",
                              borderRadius: 3, padding: "1px 4px", whiteSpace: "nowrap", flexShrink: 0,
                            }}>MY PICK</span>
                          )}
                        </div>
                        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min-xs), 0.64em)", marginTop: 1 }}>
                          {/* Jack, Oct 21: tee cards carry model rank, OWGR, win and top-10 only. */}
                          OWGR #{p.world_rank ?? "—"}
                        </div>
                      </div>
                    </div>

                    {/* Right: Win% · Top10% */}
                    <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "baseline" }}>
                        <span style={{ color: "var(--bc-green)", fontWeight: 700, fontSize: "max(var(--fs-min), 0.82em)" }}>
                          {p.win_prob != null ? `${p.win_prob.toFixed(1)}%` : "—"}
                        </span>
                        {p.top10_prob != null && (
                          <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.72em)" }}>
                            {p.top10_prob.toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
