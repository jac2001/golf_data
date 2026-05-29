"use client";

import React, { useState } from "react";
import { InPlayPlayer, HoleData } from "@/lib/api";

type Props = {
  players: InPlayPlayer[];
  currentRound: number | null;
  lastUpdate: string;
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

function holeRelColor(rel: number | null): { bg: string; fg: string } {
  if (rel == null) return { bg: "#0a1525", fg: "#3a5060"  };
  if (rel <= -2)   return { bg: "#3a2800", fg: "#f1c40f"  };
  if (rel === -1)  return { bg: "#2a0a0a", fg: "#e74c3c"  };
  if (rel === 0)   return { bg: "#0d1a30", fg: "#5a7090"  };
  if (rel === 1)   return { bg: "#0d1e38", fg: "#4cb8ff"  };
  return             { bg: "#0a0d1a", fg: "#7f5090"  };
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

export default function InPlayLeaderboard({ players, currentRound, lastUpdate, holeScores }: Props) {
  const [expandedPlayer, setExpandedPlayer] = useState<string | null>(null);

  if (!players.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No leaderboard data available. Tournament may not have started yet.
      </div>
    );
  }

  const rounds = currentRound ?? 1;
  const showR = (r: number) => r <= rounds;
  const totalCols = 5 + rounds + 3; // pos + player + total + thru + rounds + today + win% + top10%

  // Detect cut line — first player where made_cut is false
  let cutLineAfter = -1;
  for (let i = 0; i < players.length - 1; i++) {
    if (players[i].made_cut !== false && players[i + 1].made_cut === false) {
      cutLineAfter = i;
      break;
    }
  }

  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    textAlign: "center", whiteSpace: "nowrap",
  };

  return (
    <div>
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
              <th style={{ ...th }}>Today</th>
              <th style={{ ...th, color: "#00c44f" }}>Win%</th>
              <th style={{ ...th, color: "#4cb8ff" }}>Top 10%</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
              const isCut = p.made_cut === false;
              const isExpanded = expandedPlayer === p.player_name;
              const playerHoles = holeScores ? holeScores[p.player_name] ?? null : null;

              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid #0f2236",
                background: bg, textAlign: "center", fontSize: "0.85em",
              };

              const totalColor = scoreColor(p.total_numeric);
              const todayColor = scoreColor(p.today);
              const todayStr = p.today == null ? "—"
                : p.today === 0 ? "E"
                : p.today > 0 ? `+${p.today}` : String(p.today);

              return (
                <React.Fragment key={`group-${i}`}>
                  <tr
                    style={{ opacity: isCut ? 0.55 : 1, cursor: holeScores ? "pointer" : "default" }}
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
                      {p.movement && p.movement !== "CONSTANT" && (
                        <span style={{ fontSize: "0.75em", color: p.movement === "UP" ? "#e74c3c" : "#00c44f", marginRight: 4 }}>
                          {p.movement === "UP" ? "▲" : "▼"}
                        </span>
                      )}
                      {p.player_name}
                      {isCut && (
                        <span style={{ fontSize: "0.7em", color: "#5a2020", marginLeft: 6, background: "#2a0f0f", padding: "1px 4px", borderRadius: 3 }}>CUT</span>
                      )}
                    </td>
                    <td style={{ ...td, color: totalColor, fontWeight: 700 }}>{p.total ?? "E"}</td>
                    <td style={{ ...td, color: "#7f8c8d" }}>{p.thru ?? "—"}</td>
                    {showR(1) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R1)}</td>}
                    {showR(2) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R2)}</td>}
                    {showR(3) && <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R3)}</td>}
                    {showR(4) && (() => {
                      if (p.R4 != null) return <td style={{ ...td, color: "#8ba0b8" }}>{fmtRound(p.R4)}</td>;
                      if (p.today != null && p.thru != null) return (
                        <td style={{ ...td, color: "#6a8aaa", fontStyle: "italic" }}>
                          {p.today === 0 ? "E*" : p.today > 0 ? `+${p.today}*` : `${p.today}*`}
                        </td>
                      );
                      return <td style={{ ...td, color: "#3a5060" }}>—</td>;
                    })()}
                    <td style={{ ...td, color: todayColor, fontWeight: 600 }}>{todayStr}</td>
                    <td style={{ ...td, color: "#00c44f", fontWeight: 700 }}>
                      {p.win_prob != null ? `${p.win_prob.toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ ...td, color: "#4cb8ff", fontWeight: 600 }}>
                      {p.top10_prob != null ? `${p.top10_prob.toFixed(0)}%` : "—"}
                    </td>
                  </tr>

                  {/* Expanded scorecard */}
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
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>
        {lastUpdate && `DataGolf last updated: ${lastUpdate}`}
        {holeScores && " · click any row to expand scorecard"}
      </p>
    </div>
  );
}
