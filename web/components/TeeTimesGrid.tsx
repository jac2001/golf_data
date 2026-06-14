"use client";

import Link from "next/link";
import { TeeTimesResponse } from "@/lib/api";

type Props = { data: TeeTimesResponse; myPicks?: string[] };

const DRIFT_ARROW: Record<string, { s: string; c: string }> = {
  UP:       { s: "▲", c: "#e74c3c" },
  DOWN:     { s: "▼", c: "#00c44f" },
  CONSTANT: { s: "→", c: "#3a5060" },
};

// Rank badge color
function rankColor(rank: number | null): string {
  if (rank == null) return "#3a5060";
  if (rank <= 5)  return "#f1c40f";
  if (rank <= 15) return "#00c44f";
  if (rank <= 30) return "#4cb8ff";
  return "#3a5060";
}

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

export default function TeeTimesGrid({ data, myPicks = [] }: Props) {
  const myPicksNorm = new Set(myPicks.map(normName));
  if (!data.groups.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No tee times available for Round {data.round ?? "—"}.
      </div>
    );
  }

  const totalPlayers = data.groups.reduce((s, g) => s + g.players.length, 0);

  // Count USE players for the summary
  const usePlayers = data.groups.flatMap(g => g.players).filter(p => p.edge != null && p.edge > 3);

  return (
    <div>
      {/* Summary strip */}
      <div style={{ color: "#4a6080", fontSize: "0.75em", marginBottom: 14, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <span>Round {data.round}</span>
        <span>·</span>
        <span>{data.groups.length} tee times</span>
        <span>·</span>
        <span>{totalPlayers} players</span>
        {usePlayers.length > 0 && (
          <>
            <span>·</span>
            <span style={{ color: "#00c44f", fontWeight: 700 }}>
              {usePlayers.length} high-edge player{usePlayers.length !== 1 ? "s" : ""}
            </span>
          </>
        )}
      </div>

      {/* Grid of tee time cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 10 }}>
        {data.groups.map(group => {
          const hasUse = group.players.some(p => p.edge != null && p.edge > 3);
          return (
            <div key={group.tee_time} style={{
              background: "#0d1a30",
              border: `1px solid ${hasUse ? "#00c44f44" : "#1e3a5f"}`,
              borderRadius: 8, overflow: "hidden",
            }}>
              {/* Tee time header */}
              <div style={{
                background: hasUse ? "#0a1e14" : "#0a1628",
                padding: "6px 12px",
                borderBottom: `1px solid ${hasUse ? "#00c44f33" : "#1e3a5f"}`,
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <span style={{ color: hasUse ? "#00c44f" : "#4cb8ff", fontWeight: 700, fontSize: "0.85em" }}>
                  {group.tee_time}
                </span>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  {group.players[0]?.start_tee && (
                    <span style={{ color: "#3a5060", fontSize: "0.68em" }}>
                      Hole {group.players[0].start_tee}
                    </span>
                  )}
                  {hasUse && (
                    <span style={{ fontSize: "0.6em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", padding: "2px 5px", borderRadius: 3, border: "1px solid #00c44f33" }}>
                      VALUE
                    </span>
                  )}
                </div>
              </div>

              {/* Column headers — only show if we have edge data */}
              {group.players.some(p => p.edge != null) && (
                <div style={{
                  display: "grid", gridTemplateColumns: "1fr auto",
                  padding: "3px 12px", borderBottom: "1px solid #0a1628",
                }}>
                  <span style={{ fontSize: "0.58em", color: "#2a3a50", textTransform: "uppercase", letterSpacing: "0.05em" }}>Player</span>
                  <span style={{ fontSize: "0.58em", color: "#2a3a50", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "right" }}>
                    Win% · Top10% · Edge
                  </span>
                </div>
              )}

              {/* Players */}
              {group.players.map((p, i) => {
                const drift = DRIFT_ARROW[p.drift] ?? null;
                const isEdge = p.edge != null && p.edge > 3;
                const isPick = myPicksNorm.has(normName(p.name));
                const formColor = (p.form_trend ?? 0) > 0.2 ? "#00c44f"
                  : (p.form_trend ?? 0) < -0.1 ? "#e74c3c" : "#4a6080";
                const rColor = rankColor(p.model_rank);
                const edgeColor = p.edge == null ? "#3a5060"
                  : p.edge > 5 ? "#00c44f" : p.edge > 2 ? "#f39c12" : "#3a5060";

                return (
                  <div key={p.name} style={{
                    padding: "8px 12px",
                    borderBottom: i < group.players.length - 1 ? "1px solid #0f2236" : "none",
                    borderLeft: isPick ? "2px solid #00c44f" : isEdge ? "2px solid #f1c40f" : "2px solid transparent",
                    background: isPick ? "#091a0f" : isEdge ? "#0a1a10" : "transparent",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}>
                    {/* Left: rank badge + name */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                      <span style={{
                        fontSize: "0.62em", fontWeight: 800, color: rColor,
                        background: "#0a1220", padding: "2px 5px", borderRadius: 3,
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
                              color: isPick ? "#00c44f" : isEdge ? "#dde6f5" : "#c0cce0",
                              fontWeight: isPick || isEdge ? 700 : 600,
                              fontSize: "0.85em",
                              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                              textDecoration: "none",
                            }}
                            onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                            onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : isEdge ? "#dde6f5" : "#c0cce0")}
                          >
                            {p.name}
                          </Link>
                          {isPick && (
                            <span style={{
                              fontSize: "0.58em", fontWeight: 800, color: "#00c44f",
                              background: "#0d2e18", border: "1px solid #00c44f44",
                              borderRadius: 3, padding: "1px 4px", whiteSpace: "nowrap", flexShrink: 0,
                            }}>MY PICK</span>
                          )}
                        </div>
                        <div style={{ color: "#3a5060", fontSize: "0.64em", marginTop: 1 }}>
                          OWGR #{p.world_rank ?? "—"}
                          {drift && (
                            <span style={{ color: drift.c, marginLeft: 5 }}>{drift.s}</span>
                          )}
                          {(p.form_trend ?? 0) !== 0 && (
                            <span style={{ color: formColor, marginLeft: 5 }}>
                              Form {p.form_trend! > 0 ? "+" : ""}{p.form_trend!.toFixed(2)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Right: Win% · Top10% · Edge */}
                    <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "baseline" }}>
                        <span style={{ color: "#00c44f", fontWeight: 700, fontSize: "0.82em" }}>
                          {p.win_prob != null ? `${p.win_prob.toFixed(1)}%` : "—"}
                        </span>
                        {p.top10_prob != null && (
                          <span style={{ color: "#4a6080", fontSize: "0.72em" }}>
                            {p.top10_prob.toFixed(0)}%
                          </span>
                        )}
                      </div>
                      {p.edge != null && (
                        <div style={{ color: edgeColor, fontSize: "0.68em", fontWeight: isEdge ? 700 : 400, marginTop: 2 }}>
                          {p.edge > 0 ? "+" : ""}{p.edge.toFixed(1)}pp edge
                        </div>
                      )}
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
