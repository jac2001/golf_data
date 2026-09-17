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
  if (n == null) return "var(--bc-muted)";
  if (n < 0) return "var(--bc-green)";
  if (n > 0) return "var(--bc-red-text)";
  return "var(--bc-muted)";
}

function fmtRound(n: number | null): string {
  if (n == null) return "—";
  return String(n);
}

function fmtTotal(total: string | null, numeric: number | null): { str: string; color: string } {
  if (total != null && total !== "") {
    const color = numeric != null ? scoreColor(numeric) : "var(--bc-muted)";
    return { str: total, color };
  }
  return { str: "—", color: "var(--bc-muted)" };
}

function MovementArrow({ dir }: { dir: string | null }) {
  if (!dir) return <span style={{ color: "var(--bc-muted)" }}>—</span>;
  if (dir === "UP")   return <span style={{ color: "var(--bc-red-text)", fontWeight: 700 }}>▲</span>;
  if (dir === "DOWN") return <span style={{ color: "var(--bc-green)", fontWeight: 700 }}>▼</span>;
  return <span style={{ color: "var(--bc-muted)" }}>→</span>;
}

function PosDelta({ delta }: { delta: number | null }) {
  if (delta == null || delta === 0) return <span style={{ color: "var(--bc-muted)" }}>—</span>;
  const color = delta > 0 ? "var(--bc-green)" : "var(--bc-red-text)";
  return <span style={{ color, fontSize: "0.8em" }}>{delta > 0 ? "↑" : "↓"}{Math.abs(delta)}</span>;
}

function holeRelColor(rel: number | null): { bg: string; fg: string } {
  if (rel == null) return { bg: "var(--bc-panel)", fg: "var(--bc-muted)"  };  // not played
  if (rel <= -2)   return { bg: "#3a2800", fg: "var(--bc-yellow)"  };  // eagle — gold
  if (rel === -1)  return { bg: "#2a0a0a", fg: "var(--bc-red-text)"  };  // birdie — red
  if (rel === 0)   return { bg: "var(--bc-card)", fg: "var(--bc-muted)"  };  // par — muted
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
        <div style={{ fontSize: "0.55em", color: "var(--bc-muted)", marginBottom: 1 }}>{h.hole}</div>
        <div style={{ background: bg, color: fg, fontWeight: 700, fontSize: "0.8em", padding: "3px 4px", borderRadius: 3, minWidth: 24 }}>
          {h.strokes ?? "·"}
        </div>
        <div style={{ fontSize: "0.5em", color: "var(--bc-muted)", marginTop: 1 }}>{h.par ?? ""}</div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: "0.6em", color: "var(--bc-muted)", marginBottom: 4 }}>Round {round}</div>
      <div style={{ display: "flex", gap: 4, alignItems: "flex-end", flexWrap: "wrap" }}>
        {front.map(h => <HoleCell key={h.hole} h={h} />)}
        <div style={{ minWidth: 28, textAlign: "center", borderLeft: "1px solid var(--bc-line)", paddingLeft: 4 }}>
          <div style={{ fontSize: "0.55em", color: "var(--bc-muted)", marginBottom: 1 }}>OUT</div>
          <div style={{ fontSize: "0.8em", fontWeight: 700, color: "var(--bc-muted)" }}>{frontTotal || "—"}</div>
        </div>
        {back.map(h => <HoleCell key={h.hole} h={h} />)}
        <div style={{ minWidth: 28, textAlign: "center", borderLeft: "1px solid var(--bc-line)", paddingLeft: 4 }}>
          <div style={{ fontSize: "0.55em", color: "var(--bc-muted)", marginBottom: 1 }}>IN</div>
          <div style={{ fontSize: "0.8em", fontWeight: 700, color: "var(--bc-muted)" }}>{backTotal || "—"}</div>
        </div>
      </div>
    </div>
  );
}

export default function Leaderboard({ players, currentRound, cutProjection, fetchedAt, holeScores }: Props) {
  const [expandedPlayer, setExpandedPlayer] = useState<string | null>(null);

  if (!players.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
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
    background: "var(--bc-panel)", color: "var(--bc-muted)",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid var(--bc-line)",
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
        <p style={{ fontSize: "0.72em", color: "var(--bc-muted)", marginBottom: 10 }}>
          Click any row to see hole-by-hole scores
        </p>
      )}

      <div style={{ overflowX: "auto", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-card)" }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "left", width: 48 }}>Pos</th>
              <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
              <th style={{ ...th, color: "var(--bc-green)" }}>Total</th>
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
              const bg = i % 2 === 0 ? "var(--bc-card)" : "var(--bc-panel)";
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid var(--bc-card)",
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
                    <td style={{ ...td, textAlign: "left", color: "var(--bc-muted)", fontWeight: 700 }}>
                      {p.position ?? "—"}
                    </td>
                    <td style={{ ...td, textAlign: "left", color: isCut ? "var(--bc-muted)" : "var(--bc-text)", fontWeight: 600, whiteSpace: "nowrap" }}>
                      {holeScores && (
                        <span style={{ marginRight: 6, color: isExpanded ? "var(--bc-green)" : "var(--bc-muted)", fontSize: "0.8em" }}>
                          {isExpanded ? "▾" : "▸"}
                        </span>
                      )}
                      {p.player_name}
                      {isCut && (
                        <span style={{ fontSize: "0.7em", color: "#5a2020", marginLeft: 6, background: "#2a0f0f", padding: "1px 4px", borderRadius: 3 }}>CUT</span>
                      )}
                    </td>
                    <td style={{ ...td, color: totalColor, fontWeight: 700 }}>{totalStr}</td>
                    <td style={{ ...td, color: "var(--bc-muted)" }}>{p.thru ?? "—"}</td>
                    {showR(1) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R1)}</td>}
                    {showR(2) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R2)}</td>}
                    {showR(3) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R3)}</td>}
                    {showR(4) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R4)}</td>}
                    <td style={{ ...td }}><MovementArrow dir={p.movement} /></td>
                    <td style={{ ...td }}><PosDelta delta={p.position_change} /></td>
                  </tr>

                  {/* Expanded scorecard row */}
                  {isExpanded && (
                    <tr>
                      <td colSpan={totalCols} style={{ background: "var(--bc-panel)", borderBottom: "1px solid var(--bc-line)", padding: "12px 16px" }}>
                        {playerHoles ? (
                          Object.entries(playerHoles)
                            .sort(([a], [b]) => Number(a) - Number(b))
                            .map(([rnd, holes]) => (
                              <ScorecardRow key={rnd} holes={holes} round={rnd} />
                            ))
                        ) : (
                          <span style={{ color: "var(--bc-muted)", fontSize: "0.8em" }}>
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
                        padding: "4px 10px", background: "rgba(224,85,85,0.10)",
                        borderBottom: "1px solid rgba(224,85,85,0.35)", textAlign: "center",
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
        <p style={{ color: "var(--bc-muted)", fontSize: "0.70em", marginTop: 6 }}>Updated {fetchedAt}</p>
      )}
    </div>
  );
}

function CutChip({ label, value, highlight, dim }: { label: string; value: string; highlight?: boolean; dim?: boolean }) {
  const color = highlight ? "var(--warning)" : dim ? "var(--bc-muted)" : "var(--bc-muted)";
  const bg    = highlight ? "#2a1f0a" : dim ? "#0a1220" : "var(--bc-card)";
  return (
    <div style={{ background: bg, border: "1px solid var(--bc-line)", borderRadius: 8, padding: "8px 14px" }}>
      <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: "1em", fontWeight: 700, color, marginTop: 2 }}>{value}</div>
    </div>
  );
}
