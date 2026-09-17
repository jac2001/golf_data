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
  if (n == null) return "var(--bc-muted)";
  if (n < 0) return "var(--bc-green)";
  if (n > 0) return "var(--bc-red-text)";
  return "var(--bc-muted)";
}

function fmtRound(n: number | null): string {
  if (n == null) return "—";
  return String(n);
}


function relColor(rel: number | null): string {
  if (rel == null) return "var(--bc-muted)";
  if (rel <= -2) return "var(--bc-yellow)";
  if (rel === -1) return "var(--bc-red-text)";
  if (rel === 0)  return "var(--bc-muted)";
  if (rel === 1)  return "#4cb8ff";
  return "#9b59b6";
}

function runningColor(s: string | null | undefined): string {
  if (!s || s === "E") return "var(--bc-muted)";
  if (s.startsWith("-")) return "var(--bc-green)";
  return "var(--bc-red-text)";
}

function ScoreCell({ h }: { h: HoleData }) {
  const played = h.strokes != null;
  const rel = h.rel;
  const color = played ? relColor(rel) : "var(--bc-line)";

  let boxStyle: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    width: 28, height: 28, fontWeight: played && rel !== 0 ? 700 : 500,
    fontSize: "0.88em", color,
  };

  if (played && rel != null) {
    if (rel <= -2) {
      boxStyle = { ...boxStyle, border: "2px solid var(--bc-yellow)", borderRadius: "50%", background: "rgba(255,210,74,0.08)" };
    } else if (rel === -1) {
      boxStyle = { ...boxStyle, border: "2px solid var(--bc-red-text)", borderRadius: "50%", background: "#180808" };
    } else if (rel === 1) {
      boxStyle = { ...boxStyle, border: "1px solid #1a3a52", background: "var(--bc-panel)" };
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
    textAlign: "center", fontSize: "0.62em", color: "var(--bc-muted)",
    fontWeight: 700, padding: "3px 2px", minWidth: 34,
    textTransform: "uppercase", letterSpacing: "0.03em",
  };
  const parCell: React.CSSProperties = {
    textAlign: "center", fontSize: "0.7em", color: "var(--bc-muted)",
    padding: "2px 2px",
  };
  const subtotalCell: React.CSSProperties = {
    textAlign: "center", fontSize: "0.78em", fontWeight: 700,
    color: "var(--bc-muted)", padding: "3px 6px", minWidth: 40,
    borderLeft: "1px solid var(--bc-line)",
  };

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: "0.65em", color: "var(--bc-muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Round {round}
        </span>
        {(frontPlayed || backPlayed) && (
          <span style={{
            fontSize: "0.72em", fontWeight: 800,
            color: totalVsPar != null && totalVsPar < 0 ? "var(--bc-green)" : totalVsPar != null && totalVsPar > 0 ? "var(--bc-red-text)" : "var(--bc-muted)",
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
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "var(--bc-muted)", fontWeight: 700 }}>OUT</td>
              {back.map(h => <td key={h.hole} style={thCell}>{h.hole}</td>)}
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "var(--bc-muted)", fontWeight: 700 }}>IN</td>
              <td style={{ ...subtotalCell, fontSize: "0.62em", color: "var(--bc-muted)", fontWeight: 700 }}>TOT</td>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ ...parCell, textAlign: "left", color: "var(--bc-line)", fontSize: "0.62em", paddingRight: 6 }}>PAR</td>
              {front.map(h => <td key={h.hole} style={parCell}>{h.par ?? "—"}</td>)}
              <td style={{ ...subtotalCell, color: "var(--bc-muted)", fontSize: "0.7em" }}>{frontPar || "—"}</td>
              {back.map(h => <td key={h.hole} style={parCell}>{h.par ?? "—"}</td>)}
              <td style={{ ...subtotalCell, color: "var(--bc-muted)", fontSize: "0.7em" }}>{backPar || "—"}</td>
              <td style={{ ...subtotalCell, color: "var(--bc-muted)", fontSize: "0.7em" }}>{totalPar || "—"}</td>
            </tr>
            <tr>
              <td style={{ ...parCell, textAlign: "left", color: "var(--bc-line)", fontSize: "0.62em", paddingRight: 6 }}>SCORE</td>
              {front.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subtotalCell }}>
                {frontPlayed ? frontStrokes : "—"}
                {frontPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = frontStrokes - frontPar; return v < 0 ? "var(--bc-green)" : v > 0 ? "var(--bc-red-text)" : "var(--bc-muted)"; })() }}>
                    {(() => { const v = frontStrokes - frontPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              {back.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subtotalCell }}>
                {backPlayed ? backStrokes : "—"}
                {backPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = backStrokes - backPar; return v < 0 ? "var(--bc-green)" : v > 0 ? "var(--bc-red-text)" : "var(--bc-muted)"; })() }}>
                    {(() => { const v = backStrokes - backPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              <td style={{ ...subtotalCell, color: totalVsPar != null && totalVsPar < 0 ? "var(--bc-green)" : totalVsPar != null && totalVsPar > 0 ? "var(--bc-red-text)" : "var(--bc-muted)", fontWeight: 800 }}>
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
      <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
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
    background: "var(--bc-panel)", color: "var(--bc-muted)",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid var(--bc-line)",
    textAlign: "center", whiteSpace: "nowrap",
  };

  return (
    <div>
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
              <th style={{ ...th }}>Today</th>
              <th style={{ ...th, color: "var(--bc-green)" }}>Win%</th>
              <th style={{ ...th, color: "var(--bc-yellow)" }}>Top 10%</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const isPick = myPicksNorm.has(normName(p.player_name));
              const bg = isPick ? "#091a0f" : i % 2 === 0 ? "var(--bc-card)" : "var(--bc-panel)";
              const isCut = p.made_cut === false;
              const isExpanded = expandedPlayer === p.player_name;
              const playerHoles = holeScores ? holeScores[p.player_name] ?? null : null;

              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid var(--bc-card)",
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
                      borderLeft: isPick ? "2px solid var(--bc-green)" : "2px solid transparent",
                    }}
                    onClick={() => holeScores && setExpandedPlayer(isExpanded ? null : p.player_name)}
                  >
                    <td style={{ ...td, textAlign: "left", color: "var(--bc-muted)", fontWeight: 700 }}>
                      {p.position ?? "—"}
                    </td>
                    <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
                      {holeScores && (
                        <span style={{ marginRight: 6, color: isExpanded ? "var(--bc-green)" : "var(--bc-muted)", fontSize: "0.8em" }}>
                          {isExpanded ? "▾" : "▸"}
                        </span>
                      )}
                      {p.movement && p.movement !== "CONSTANT" && (
                        <span style={{ fontSize: "0.75em", color: p.movement === "UP" ? "var(--bc-red-text)" : "var(--bc-green)", marginRight: 4 }}>
                          {p.movement === "UP" ? "▲" : "▼"}
                        </span>
                      )}
                      <Link
                        href={`/players?player=${encodeURIComponent(p.player_name)}`}
                        onClick={e => e.stopPropagation()}
                        style={{
                          color: isPick ? "var(--bc-green)" : isCut ? "var(--bc-muted)" : "var(--bc-text)",
                          textDecoration: "none",
                          fontWeight: isPick ? 700 : 600,
                        }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--bc-yellow)")}
                        onMouseLeave={e => (e.currentTarget.style.color = isPick ? "var(--bc-green)" : isCut ? "var(--bc-muted)" : "var(--bc-text)")}
                      >
                        {p.player_name}
                      </Link>
                      {isPick && (
                        <span style={{ fontSize: "0.58em", fontWeight: 800, color: "var(--bc-green)", background: "color-mix(in srgb, var(--bc-green) 15%, transparent)", border: "1px solid rgba(0,196,79,0.27)", borderRadius: 3, padding: "1px 4px", marginLeft: 6, whiteSpace: "nowrap" }}>
                          MY PICK
                        </span>
                      )}
                      {isCut && (
                        <span style={{ fontSize: "0.7em", color: "#5a2020", marginLeft: 6, background: "#2a0f0f", padding: "1px 4px", borderRadius: 3 }}>CUT</span>
                      )}
                    </td>
                    <td style={{ ...td, color: totalColor, fontWeight: 700 }}>{p.total ?? "E"}</td>
                    <td style={{ ...td, color: "var(--bc-muted)" }}>{p.thru ?? "—"}</td>
                    {showR(1) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R1)}</td>}
                    {showR(2) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R2)}</td>}
                    {showR(3) && <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R3)}</td>}
                    {showR(4) && (() => {
                      if (p.R4 != null) return <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtRound(p.R4)}</td>;
                      if (p.today != null && p.thru != null) return (
                        <td style={{ ...td, color: "var(--bc-muted)", fontStyle: "italic" }}>
                          {p.today === 0 ? "E*" : p.today > 0 ? `+${p.today}*` : `${p.today}*`}
                        </td>
                      );
                      return <td style={{ ...td, color: "var(--bc-muted)" }}>—</td>;
                    })()}
                    <td style={{ ...td, color: todayColor, fontWeight: 600 }}>{todayStr}</td>
                    <td style={{ ...td, color: "var(--bc-green)", fontWeight: 700 }}>
                      {p.win_prob != null ? `${p.win_prob.toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ ...td, color: "var(--bc-yellow)", fontWeight: 600 }}>
                      {p.top10_prob != null ? `${p.top10_prob.toFixed(0)}%` : "—"}
                    </td>
                  </tr>

                  {/* Expanded scorecard */}
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
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ color: "var(--bc-muted)", fontSize: "0.70em", marginTop: 6 }}>
        {lastUpdate && `DataGolf last updated: ${lastUpdate}`}
        {holeScores && " · click any row to expand scorecard"}
      </p>
    </div>
  );
}
