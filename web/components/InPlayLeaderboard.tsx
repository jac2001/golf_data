"use client";

import React, { useState } from "react";
import Link from "next/link";
import { InPlayPlayer, HoleData } from "@/lib/api";

type Props = {
  players: InPlayPlayer[];
  currentRound: number | null;
  lastUpdate: string;
  holeScores?: Record<string, Record<string, HoleData[]>>;
  myPicks?: string[];
};

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

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


function relColor(rel: number | null): string {
  if (rel == null) return "#5a7090";
  if (rel <= -2) return "#f1c40f";
  if (rel === -1) return "#e74c3c";
  if (rel === 0)  return "#7f8c8d";
  if (rel === 1)  return "#4cb8ff";
  return "#9b59b6";
}

function runningColor(s: string | null | undefined): string {
  if (!s || s === "E") return "#4a6080";
  if (s.startsWith("-")) return "#00c44f";
  return "#e74c3c";
}

function ScoreCell({ h }: { h: HoleData }) {
  const played = h.strokes != null;
  const rel = h.rel;
  const color = played ? relColor(rel) : "#2a3a50";

  let boxStyle: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    width: 28, height: 28, fontWeight: played && rel !== 0 ? 700 : 500,
    fontSize: "0.88em", color,
  };

  if (played && rel != null) {
    if (rel <= -2) {
      boxStyle = { ...boxStyle, border: "2px solid #f1c40f", borderRadius: "50%", background: "#1a1200" };
    } else if (rel === -1) {
      boxStyle = { ...boxStyle, border: "2px solid #e74c3c", borderRadius: "50%", background: "#180808" };
    } else if (rel === 1) {
      boxStyle = { ...boxStyle, border: "1px solid #1a3a52", background: "#080f1e" };
    } else if (rel >= 2) {
      boxStyle = { ...boxStyle, border: "2px solid #6a3080", background: "#100818" };
    }
  }

  return (
    <td style={{ padding: "3px 2px", textAlign: "center", minWidth: 34 }}>
      <div style={boxStyle}>{played ? h.strokes : "·"}</div>
      {played && h.running && (
        <div style={{ fontSize: "0.55em", color: runningColor(h.running), marginTop: 1, textAlign: "center" }}>
          {h.running}
        </div>
      )}
    </td>
  );
}

function ScorecardRow({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);

  const frontStrokes = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backStrokes  = back.reduce((s, h)  => s + (h.strokes ?? 0), 0);
  const frontPar     = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar      = back.reduce((s, h)  => s + (h.par ?? 0), 0);
  const frontPlayed  = front.some(h => h.strokes != null);
  const backPlayed   = back.some(h => h.strokes != null);
  const totalStrokes = frontStrokes + backStrokes;
  const totalPar     = frontPar + backPar;
  const totalVsPar   = frontPlayed || backPlayed ? totalStrokes - totalPar : null;
  const totalStr     = totalVsPar == null ? "—" : totalVsPar === 0 ? "E" : totalVsPar > 0 ? `+${totalVsPar}` : String(totalVsPar);

  const thCell: React.CSSProperties = {
    textAlign: "center", fontSize: "0.62em", color: "#3a5060",
    fontWeight: 700, padding: "3px 2px", minWidth: 34,
    textTransform: "uppercase", letterSpacing: "0.03em",
  };
  const parCell: React.CSSProperties = {
    textAlign: "center", fontSize: "0.7em", color: "#4a6080",
    padding: "2px 2px",
  };
  const subtotalCell: React.CSSProperties = {
    textAlign: "center", fontSize: "0.78em", fontWeight: 700,
    color: "#8ba0b8", padding: "3px 6px", minWidth: 40,
    borderLeft: "1px solid #1e3a5f",
  };

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: "0.65em", color: "#4a6080", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Round {round}
        </span>
        {(frontPlayed || backPlayed) && (
          <span style={{
            fontSize: "0.72em", fontWeight: 800,
            color: totalVsPar != null && totalVsPar < 0 ? "#00c44f" : totalVsPar != null && totalVsPar > 0 ? "#e74c3c" : "#8ba0b8",
          }}>
            {totalStr} ({totalStrokes})
          </span>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
          <thead>
            <tr>
              <td style={{ ...thCell, textAlign: "left", minWidth: 40 }}></td>
              {front.map(h => <td key={h.hole} style={thCell}>{h.hole}</td>)}
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "#3a5060", fontWeight: 700 }}>OUT</td>
              {back.map(h => <td key={h.hole} style={thCell}>{h.hole}</td>)}
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "#3a5060", fontWeight: 700 }}>IN</td>
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "#3a5060", fontWeight: 700 }}>TOT</td>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ ...parCell, textAlign: "left", color: "#2a3a50", fontSize: "0.62em", paddingRight: 6 }}>PAR</td>
              {front.map(h => <td key={h.hole} style={parCell}>{h.par ?? "—"}</td>)}
              <td style={{ ...subtotalCell, color: "#3a5060", fontSize: "0.7em" }}>{frontPar || "—"}</td>
              {back.map(h => <td key={h.hole} style={parCell}>{h.par ?? "—"}</td>)}
              <td style={{ ...subtotalCell, color: "#3a5060", fontSize: "0.7em" }}>{backPar || "—"}</td>
              <td style={{ ...subtotalCell, color: "#3a5060", fontSize: "0.7em" }}>{totalPar || "—"}</td>
            </tr>
            <tr>
              <td style={{ ...parCell, textAlign: "left", color: "#2a3a50", fontSize: "0.62em", paddingRight: 6 }}>SCORE</td>
              {front.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subtotalCell }}>
                {frontPlayed ? frontStrokes : "—"}
                {frontPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = frontStrokes - frontPar; return v < 0 ? "#00c44f" : v > 0 ? "#e74c3c" : "#4a6080"; })() }}>
                    {(() => { const v = frontStrokes - frontPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              {back.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subtotalCell }}>
                {backPlayed ? backStrokes : "—"}
                {backPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = backStrokes - backPar; return v < 0 ? "#00c44f" : v > 0 ? "#e74c3c" : "#4a6080"; })() }}>
                    {(() => { const v = backStrokes - backPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              <td style={{ ...subtotalCell, color: totalVsPar != null && totalVsPar < 0 ? "#00c44f" : totalVsPar != null && totalVsPar > 0 ? "#e74c3c" : "#8ba0b8", fontWeight: 800 }}>
                {frontPlayed || backPlayed ? totalStrokes : "—"}
                {totalVsPar != null && (
                  <div style={{ fontSize: "0.62em" }}>{totalStr}</div>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function InPlayLeaderboard({ players, currentRound, lastUpdate, holeScores, myPicks = [] }: Props) {
  const [expandedPlayer, setExpandedPlayer] = useState<string | null>(null);
  const myPicksNorm = new Set(myPicks.map(normName));

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
              const isPick = myPicksNorm.has(normName(p.player_name));
              const bg = isPick ? "#091a0f" : i % 2 === 0 ? "#0d1a30" : "#0a1525";
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
                    style={{
                      opacity: isCut ? 0.55 : 1,
                      cursor: holeScores ? "pointer" : "default",
                      borderLeft: isPick ? "2px solid #00c44f" : "2px solid transparent",
                    }}
                    onClick={() => holeScores && setExpandedPlayer(isExpanded ? null : p.player_name)}
                  >
                    <td style={{ ...td, textAlign: "left", color: "#7f8c8d", fontWeight: 700 }}>
                      {p.position ?? "—"}
                    </td>
                    <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
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
                      <Link
                        href={`/players?player=${encodeURIComponent(p.player_name)}`}
                        onClick={e => e.stopPropagation()}
                        style={{
                          color: isPick ? "#00c44f" : isCut ? "#3a5060" : "#dde6f5",
                          textDecoration: "none",
                          fontWeight: isPick ? 700 : 600,
                        }}
                        onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                        onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : isCut ? "#3a5060" : "#dde6f5")}
                      >
                        {p.player_name}
                      </Link>
                      {isPick && (
                        <span style={{ fontSize: "0.58em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", border: "1px solid #00c44f44", borderRadius: 3, padding: "1px 4px", marginLeft: 6, whiteSpace: "nowrap" }}>
                          MY PICK
                        </span>
                      )}
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
