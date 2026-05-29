"use client";

import React, { useState } from "react";
import { LeaderboardPlayer, CutProjection, HoleData } from "@/lib/api";

type Props = {
  players: LeaderboardPlayer[];
  currentRound: number | null;
  cutProjection: CutProjection | null;
  fetchedAt: string | null;
  holeScores?: Record<string, Record<string, HoleData[]>>;
};

function scoreColor(n: number | null): string {
  if (n == null) return "#7f8c8d";
  if (n < 0) return "#00c44f";
  if (n > 0) return "#e74c3c";
  return "#8ba0b8";
}

function fmtRound(n: number | null): string {
  if (n == null) return "—";
  return String(n);
}

function fmtTotal(total: string | null, numeric: number | null): { str: string; color: string } {
  if (total != null && total !== "") {
    const color = numeric != null ? scoreColor(numeric) : "#8ba0b8";
    return { str: total, color };
  }
  return { str: "—", color: "#7f8c8d" };
}

function MovementArrow({ dir }: { dir: string | null }) {
  if (!dir) return <span style={{ color: "#3a5060" }}>—</span>;
  if (dir === "UP")   return <span style={{ color: "#e74c3c", fontWeight: 700 }}>▲</span>;
  if (dir === "DOWN") return <span style={{ color: "#00c44f", fontWeight: 700 }}>▼</span>;
  return <span style={{ color: "#3a5060" }}>→</span>;
}

function PosDelta({ delta }: { delta: number | null }) {
  if (delta == null || delta === 0) return <span style={{ color: "#3a5060" }}>—</span>;
  const color = delta > 0 ? "#00c44f" : "#e74c3c";
  return <span style={{ color, fontSize: "0.8em" }}>{delta > 0 ? "↑" : "↓"}{Math.abs(delta)}</span>;
}

function holeRelColor(rel: number | null): { bg: string; fg: string } {
  if (rel == null) return { bg: "#0a1525", fg: "#3a5060"  };  // not played
  if (rel <= -2)   return { bg: "#3a2800", fg: "#f1c40f"  };  // eagle — gold
  if (rel === -1)  return { bg: "#2a0a0a", fg: "#e74c3c"  };  // birdie — red
  if (rel === 0)   return { bg: "#0d1a30", fg: "#5a7090"  };  // par — muted
  if (rel === 1)   return { bg: "#0d1e38", fg: "#4cb8ff"  };  // bogey — blue
  return             { bg: "#0a0d1a", fg: "#7f5090"  };        // double+ — purple
}

function ScorecardRow({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);
  const frontTotal = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backTotal  = back.reduce((s, h) => s + (h.strokes ?? 0), 0);

  function HoleCell({ h }: { h: HoleData }) {
    const { bg, fg } = holeRelColor(h.rel);
    return (
      <div style={{ textAlign: "center", minWidth: 28 }}>
        <div style={{ fontSize: "0.55em", color: "#3a5060", marginBottom: 1 }}>{h.hole}</div>
        <div style={{ background: bg, color: fg, fontWeight: 700, fontSize: "0.8em", padding: "3px 4px", borderRadius: 3, minWidth: 24 }}>
          {h.strokes ?? "·"}
        </div>
        <div style={{ fontSize: "0.5em", color: "#2a3a4a", marginTop: 1 }}>{h.par ?? ""}</div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: "0.6em", color: "#3a5060", marginBottom: 4 }}>Round {round}</div>
      <div style={{ display: "flex", gap: 4, alignItems: "flex-end", flexWrap: "wrap" }}>
        {front.map(h => <HoleCell key={h.hole} h={h} />)}
        <div style={{ minWidth: 28, textAlign: "center", borderLeft: "1px solid #1e3a5f", paddingLeft: 4 }}>
          <div style={{ fontSize: "0.55em", color: "#3a5060", marginBottom: 1 }}>OUT</div>
          <div style={{ fontSize: "0.8em", fontWeight: 700, color: "#8ba0b8" }}>{frontTotal || "—"}</div>
        </div>
        {back.map(h => <HoleCell key={h.hole} h={h} />)}
        <div style={{ minWidth: 28, textAlign: "center", borderLeft: "1px solid #1e3a5f", paddingLeft: 4 }}>
          <div style={{ fontSize: "0.55em", color: "#3a5060", marginBottom: 1 }}>IN</div>
          <div style={{ fontSize: "0.8em", fontWeight: 700, color: "#8ba0b8" }}>{backTotal || "—"}</div>
        </div>
      </div>
    </div>
  );
}

export default function Leaderboard({ players, currentRound, cutProjection, fetchedAt, holeScores }: Props) {
  const [expandedPlayer, setExpandedPlayer] = useState<string | null>(null);

  if (!players.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No leaderboard data available. Tournament may not have started yet.
      </div>
    );
  }

  let cutLineAfter = -1;
  for (let i = 0; i < players.length - 1; i++) {
    if (players[i].made_cut !== false && players[i + 1].made_cut === false) {
      cutLineAfter = i;
      break;
    }
  }

  const rounds = currentRound ?? 1;
  const showR = (r: number) => r <= rounds;
  const totalCols = 6 + rounds + 2;

  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    textAlign: "center", whiteSpace: "nowrap",
  };

  return (
    <div>
      {cutProjection && (
        <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
          {cutProjection.projected_cut_score != null && (
            <CutChip label="Projected Cut" value={
              cutProjection.projected_cut_score === 0 ? "E" :
              cutProjection.projected_cut_score > 0 ? `+${cutProjection.projected_cut_score}` :
              String(cutProjection.projected_cut_score)
            } />
          )}
          {cutProjection.safely_in    != null && <CutChip label="Safe In"   value={String(cutProjection.safely_in)}   />}
          {cutProjection.bubble_count != null && <CutChip label="On Bubble" value={String(cutProjection.bubble_count)} highlight />}
          {cutProjection.safely_out   != null && <CutChip label="Safe Out"  value={String(cutProjection.safely_out)}  dim />}
        </div>
      )}

      {holeScores && (
        <p style={{ fontSize: "0.72em", color: "#3a5060", marginBottom: 10 }}>
          Click any row to see hole-by-hole scores
        </p>
      )}

      <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "left", width: 48 }}>Pos</th>
              <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
              <th style={{ ...th, color: "#00c44f" }}>Total</th>
              <th style={{ ...th }}>Thru</th>
              {showR(1) && <th style={{ ...th }}>R1</th>}
              {showR(2) && <th style={{ ...th }}>R2</th>}
              {showR(3) && <th style={{ ...th }}>R3</th>}
              {showR(4) && <th style={{ ...th }}>R4</th>}
              <th style={{ ...th }}>Move</th>
              <th style={{ ...th }}>Trend</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid #0f2236",
                background: bg, textAlign: "center", fontSize: "0.85em",
              };
              const { str: totalStr, color: totalColor } = fmtTotal(p.total, p.total_numeric);
              const isCut      = p.made_cut === false;
              const isExpanded = expandedPlayer === p.player_name;
              const playerHoles = holeScores ? holeScores[p.player_name] ?? null : null;

              return (
                <React.Fragment key={`group-${i}`}>

                  {/* Main player row */}
                  <tr
                    style={{ opacity: isCut ? 0.6 : 1, cursor: holeScores ? "pointer" : "default" }}
                    onClick={() => holeScores && setExpandedPlayer(isExpanded ? null : p.player_name)}
                  >
                    <td style={{ ...td, textAlign: "left", color: "#7f8c8d", fontWeight: 700 }}>
                      {p.position ?? "—"}
                    </td>
                    <td style={{ ...td, textAlign: "left", color: isCut ? "#3a5060" : "#dde6f5", fontWeight: 600, whiteSpace: "nowrap" }}>
                      {holeScores && (
                        <span style={{ marginRight: 6, color: isExpanded ? "#00c44f" : "#3a5060", fontSize: "0.8em" }}>
                          {isExpanded ? "▾" : "▸"}
                        </span>
                      )}
                      {p.player_name}
                      {isCut && (
                        <span style={{ fontSize: "0.7em", color: "#5a2020", marginLeft: 6, background: "#2a0f0f", padding: "1px 4px", borderRadius: 3 }}>CUT</span>
                      )}
                    </td>
                    <td style={{ ...td, color: totalColor, fontWeight: 700 }}>{totalStr}</td>
                    <td style={{ ...td, color: "#7f8c8d" }}>{p.thru ?? "—"}</td>
                    {showR(1) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R1)}</td>}
                    {showR(2) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R2)}</td>}
                    {showR(3) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R3)}</td>}
                    {showR(4) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R4)}</td>}
                    <td style={{ ...td }}><MovementArrow dir={p.movement} /></td>
                    <td style={{ ...td }}><PosDelta delta={p.position_change} /></td>
                  </tr>

                  {/* Expanded scorecard row */}
                  {isExpanded && (
                    <tr>
                      <td colSpan={totalCols} style={{ background: "#080f1e", borderBottom: "1px solid #1e3a5f", padding: "12px 16px" }}>
                        {playerHoles ? (
                          Object.entries(playerHoles)
                            .sort(([a], [b]) => Number(a) - Number(b))
                            .map(([rnd, holes]) => (
                              <ScorecardRow key={rnd} holes={holes} round={rnd} />
                            ))
                        ) : (
                          <span style={{ color: "#3a5060", fontSize: "0.8em" }}>
                            No hole-by-hole data for {p.player_name}
                          </span>
                        )}
                      </td>
                    </tr>
                  )}

                  {/* Cut line divider */}
                  {cutLineAfter === i && (
                    <tr>
                      <td colSpan={totalCols} style={{
                        padding: "4px 10px", background: "#1a0d0d",
                        borderBottom: "1px solid #5f1e1e", textAlign: "center",
                        fontSize: "0.65em", color: "#7f3030",
                        letterSpacing: "0.1em", fontWeight: 700, textTransform: "uppercase",
                      }}>
                        — Cut Line —
                        {cutProjection?.projected_cut_score != null && (
                          <span style={{ marginLeft: 8 }}>
                            ({cutProjection.projected_cut_score > 0 ? "+" : ""}{cutProjection.projected_cut_score})
                          </span>
                        )}
                      </td>
                    </tr>
                  )}

                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {fetchedAt && (
        <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>Updated {fetchedAt}</p>
      )}
    </div>
  );
}

function CutChip({ label, value, highlight, dim }: { label: string; value: string; highlight?: boolean; dim?: boolean }) {
  const color = highlight ? "#f39c12" : dim ? "#3a5060" : "#5a7090";
  const bg    = highlight ? "#2a1f0a" : dim ? "#0a1220" : "#0d1a30";
  return (
    <div style={{ background: bg, border: "1px solid #1e3a5f", borderRadius: 8, padding: "8px 14px" }}>
      <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: "1em", fontWeight: 700, color, marginTop: 2 }}>{value}</div>
    </div>
  );
}
