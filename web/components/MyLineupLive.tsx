"use client";

import React from "react";
import Link from "next/link";
import { MyPickPlayer, HoleData } from "@/lib/api";

type Props = {
  picks: MyPickPlayer[];
  tournament: string;
  holeScores?: Record<string, Record<string, HoleData[]>>;
};

// ── Scorecard helpers ────────────────────────────────────────────────────────

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
  return s.startsWith("-") ? "var(--bc-green)" : "var(--bc-red-text)";
}

function MiniScoreCard({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);
  const frontStrokes = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backStrokes  = back.reduce((s,  h) => s + (h.strokes ?? 0), 0);
  const frontPar     = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar      = back.reduce((s,  h) => s + (h.par ?? 0), 0);
  const frontPlayed  = front.some(h => h.strokes != null);
  const backPlayed   = back.some(h => h.strokes != null);
  const totalStrokes = frontStrokes + backStrokes;
  const totalPar     = frontPar + backPar;
  const vsPar        = (frontPlayed || backPlayed) ? totalStrokes - totalPar : null;
  const vsParStr     = vsPar == null ? "—" : vsPar === 0 ? "E" : vsPar > 0 ? `+${vsPar}` : String(vsPar);
  const vsParColor   = vsPar == null ? "var(--bc-muted)" : vsPar < 0 ? "var(--bc-green)" : vsPar > 0 ? "var(--bc-red-text)" : "var(--bc-muted)";

  function HCell({ h }: { h: HoleData }) {
    const played = h.strokes != null;
    const color  = played ? relColor(h.rel) : "#1e3050";
    let boxStyle: React.CSSProperties = {
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 24, height: 24, fontSize: "0.8em", fontWeight: played && h.rel !== 0 ? 700 : 400, color,
    };
    if (played && h.rel != null) {
      if (h.rel <= -2) boxStyle = { ...boxStyle, border: "2px solid var(--bc-yellow)", borderRadius: "50%", background: "rgba(255,210,74,0.08)" };
      else if (h.rel === -1) boxStyle = { ...boxStyle, border: "2px solid var(--bc-red-text)", borderRadius: "50%", background: "#180808" };
      else if (h.rel === 1)  boxStyle = { ...boxStyle, border: "1px solid #1a3a52", background: "#060d18" };
      else if (h.rel >= 2)   boxStyle = { ...boxStyle, border: "2px solid #6a3080", background: "#100818" };
    }
    return (
      <td style={{ padding: "2px 1px", textAlign: "center", minWidth: 28 }}>
        <div style={boxStyle}>{played ? h.strokes : "·"}</div>
        {played && h.running && (
          <div style={{ fontSize: "0.48em", color: runningColor(h.running), textAlign: "center", marginTop: 1 }}>
            {h.running}
          </div>
        )}
      </td>
    );
  }

  const thStyle: React.CSSProperties = { fontSize: "0.55em", color: "var(--bc-line)", textAlign: "center", padding: "2px 1px", minWidth: 28, fontWeight: 700 };
  const parStyle: React.CSSProperties = { fontSize: "0.6em", color: "var(--bc-muted)", textAlign: "center", padding: "1px 1px" };
  const subStyle: React.CSSProperties = { fontSize: "0.72em", color: "var(--bc-muted)", fontWeight: 700, textAlign: "center", padding: "2px 6px", minWidth: 36, borderLeft: "1px solid var(--bc-line)" };

  return (
    <div style={{ marginTop: 14, borderTop: "1px solid var(--bc-card)", paddingTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: "0.62em", color: "var(--bc-muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Round {round}
        </span>
        {(frontPlayed || backPlayed) && (
          <span style={{ fontSize: "0.72em", fontWeight: 800, color: vsParColor }}>
            {vsParStr} ({totalStrokes})
          </span>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
          <thead>
            <tr>
              {front.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.55em", color: "var(--bc-line)" }}>OUT</td>
              {back.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.55em", color: "var(--bc-line)" }}>IN</td>
              <td style={{ ...subStyle, fontSize: "0.55em", color: "var(--bc-line)" }}>TOT</td>
            </tr>
          </thead>
          <tbody>
            <tr>
              {front.map(h => <td key={h.hole} style={parStyle}>{h.par ?? "—"}</td>)}
              <td style={{ ...subStyle, color: "var(--bc-line)", fontSize: "0.6em" }}>{frontPar || "—"}</td>
              {back.map(h => <td key={h.hole} style={parStyle}>{h.par ?? "—"}</td>)}
              <td style={{ ...subStyle, color: "var(--bc-line)", fontSize: "0.6em" }}>{backPar || "—"}</td>
              <td style={{ ...subStyle, color: "var(--bc-line)", fontSize: "0.6em" }}>{totalPar || "—"}</td>
            </tr>
            <tr>
              {front.map(h => <HCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {frontPlayed ? frontStrokes : "—"}
                {frontPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = frontStrokes - frontPar; return v < 0 ? "var(--bc-green)" : v > 0 ? "var(--bc-red-text)" : "var(--bc-muted)"; })() }}>
                    {(() => { const v = frontStrokes - frontPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              {back.map(h => <HCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {backPlayed ? backStrokes : "—"}
                {backPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = backStrokes - backPar; return v < 0 ? "var(--bc-green)" : v > 0 ? "var(--bc-red-text)" : "var(--bc-muted)"; })() }}>
                    {(() => { const v = backStrokes - backPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              <td style={{ ...subStyle, color: vsParColor, fontWeight: 800 }}>
                {(frontPlayed || backPlayed) ? totalStrokes : "—"}
                {vsPar != null && <div style={{ fontSize: "0.62em" }}>{vsParStr}</div>}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function scoreColor(n: number | null): string {
  if (n == null) return "var(--bc-muted)";
  if (n < 0) return "var(--bc-green)";
  if (n > 0) return "var(--bc-red-text)";
  return "var(--bc-muted)";
}

function RoundPip({ score, label }: { score: number | null; label: string }) {
  const color = score == null ? "var(--bc-muted)" : scoreColor(score);
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "0.6em", color: "var(--bc-muted)", textTransform: "uppercase", marginBottom: 2 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: "0.85em", color }}>
        {score == null ? "—" : String(score)}
      </div>
    </div>
  );
}

function StatusBadge({ status, madeCut }: { status: string | null; madeCut: boolean | null }) {
  if (madeCut === false) {
    return <span style={{ fontSize: "0.7em", fontWeight: 700, color: "var(--bc-red-text)", background: "#2a0f0f", padding: "2px 7px", borderRadius: 3, border: "1px solid #5a1a1a" }}>MISSED CUT</span>;
  }
  if (status === "W") {
    return <span style={{ fontSize: "0.7em", fontWeight: 800, color: "var(--bc-yellow)", background: "#1f1800", padding: "2px 7px", borderRadius: 3, border: "1px solid #5a4a00" }}>WON</span>;
  }
  if (madeCut === true) {
    return <span style={{ fontSize: "0.7em", fontWeight: 700, color: "var(--bc-green)", background: "#0d2218", padding: "2px 7px", borderRadius: 3, border: "1px solid #004422" }}>MADE CUT</span>;
  }
  return null;
}

function MoveDelta({ delta }: { delta: number | null }) {
  if (delta == null || delta === 0) return null;
  const color = delta > 0 ? "var(--bc-green)" : "var(--bc-red-text)";
  const arrow = delta > 0 ? "↑" : "↓";
  return <span style={{ fontSize: "0.75em", color, marginLeft: 8 }}>{arrow}{Math.abs(delta)}</span>;
}

export default function MyLineupLive({ picks, tournament, holeScores }: Props) {
  if (!picks.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
        No lineup found. Run the season strategy pipeline to generate picks.
      </div>
    );
  }

  return (
    <div>
      {tournament && (
        <p style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginBottom: 14 }}>{tournament}</p>
      )}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        {picks.map((p, i) => {
          const totalNum = p.total_numeric;
          const totalStr = p.total ?? "—";
          const totalColor = scoreColor(totalNum);
          const borderColor = i === 0 ? "var(--bc-yellow)" : i === 1 ? "var(--bc-green)" : "var(--bc-yellow)";
          const playerHoles = holeScores ? holeScores[p.player] ?? null : null;
          const hasCards = playerHoles && Object.keys(playerHoles).length > 0;

          return (
            <div key={p.player} style={{
              flex: hasCards ? "1 1 100%" : "1 1 260px",
              minWidth: hasCards ? 0 : 220,
              background: "var(--bc-card)",
              borderLeft: `1px solid var(--bc-line)`, borderRight: `1px solid var(--bc-line)`, borderBottom: `1px solid var(--bc-line)`,
              borderTop: `3px solid ${borderColor}`,
              borderRadius: 10, padding: "16px 18px",
            }}>
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                <div>
                  <Link
                    href={`/players?player=${encodeURIComponent(p.player)}`}
                    style={{ color: "var(--bc-text)", fontWeight: 800, fontSize: "1.05em", textDecoration: "none", display: "block" }}
                    onMouseEnter={e => (e.currentTarget.style.color = "var(--bc-yellow)")}
                    onMouseLeave={e => (e.currentTarget.style.color = "var(--bc-text)")}
                  >
                    {p.player}
                  </Link>
                  <div style={{ marginTop: 4 }}>
                    <StatusBadge status={p.status} madeCut={p.made_cut} />
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: totalColor, fontWeight: 800, fontSize: "1.6em", lineHeight: 1 }}>{totalStr}</div>
                  <div style={{ color: "var(--bc-muted)", fontSize: "0.72em", marginTop: 3 }}>
                    {p.position ? `${p.position}` : "—"}
                    <MoveDelta delta={p.position_change} />
                  </div>
                  {p.thru && <div style={{ color: "var(--bc-muted)", fontSize: "0.68em" }}>Thru {p.thru}</div>}
                </div>
              </div>

              {/* Round score pips */}
              <div style={{ display: "flex", gap: 12, justifyContent: "flex-start" }}>
                <RoundPip score={p.R1} label="R1" />
                <RoundPip score={p.R2} label="R2" />
                <RoundPip score={p.R3} label="R3" />
                <RoundPip score={p.R4} label="R4" />
              </div>

              {/* Hole-by-hole scorecards */}
              {hasCards && Object.entries(playerHoles)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([rnd, holes]) => (
                  <MiniScoreCard key={rnd} holes={holes} round={rnd} />
                ))
              }
            </div>
          );
        })}
      </div>

      <p style={{ color: "var(--bc-muted)", fontSize: "0.70em", marginTop: 10 }}>
        Your 3 picks for this week. Round scores are raw strokes.
      </p>
    </div>
  );
}
