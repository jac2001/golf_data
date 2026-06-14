"use client";

import Link from "next/link";
import { VsPredPlayer } from "@/lib/api";

type Props = { players: VsPredPlayer[]; myPicks?: string[] };

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

export default function VsPredictions({ players, myPicks = [] }: Props) {
  const myPicksNorm = new Set(myPicks.map(normName));
  if (!players.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No data available.
      </div>
    );
  }

  // Top overperformers and underperformers (rank_diff: positive = beating model, negative = below)
  const withDiff = players.filter(p => p.rank_diff != null && p.model_rank != null);
  const overPerf  = [...withDiff].sort((a, b) => (b.rank_diff ?? 0) - (a.rank_diff ?? 0)).slice(0, 3);
  const underPerf = [...withDiff].sort((a, b) => (a.rank_diff ?? 0) - (b.rank_diff ?? 0)).slice(0, 3);

  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    textAlign: "center", whiteSpace: "nowrap",
  };

  return (
    <div>
      {/* Callout strips */}
      {(overPerf.length > 0 || underPerf.length > 0) && (
        <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
          {overPerf.length > 0 && (
            <div style={{ flex: "1 1 240px" }}>
              <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                Outperforming Model
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {overPerf.map(p => (
                  <div key={p.player} style={{ background: "#0d2218", border: "1px solid #00c44f33", borderRadius: 8, padding: "8px 12px", flex: "1 1 120px" }}>
                    <div style={{ color: "#dde6f5", fontWeight: 700, fontSize: "0.85em" }}>
                      <Link href={`/players?player=${encodeURIComponent(p.player)}`} style={{ color: "#dde6f5", textDecoration: "none" }} onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")} onMouseLeave={e => (e.currentTarget.style.color = "#dde6f5")}>{p.player}</Link>
                    </div>
                    <div style={{ fontSize: "0.72em", marginTop: 3 }}>
                      <span style={{ color: "#00c44f" }}>Live #{p.position ?? "?"}</span>
                      <span style={{ color: "#3a5060", margin: "0 5px" }}>vs</span>
                      <span style={{ color: "#4a6080" }}>Model #{p.model_rank}</span>
                      <span style={{ color: "#00c44f", marginLeft: 8 }}>+{p.rank_diff}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {underPerf.length > 0 && (
            <div style={{ flex: "1 1 240px" }}>
              <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                Underperforming Model
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {underPerf.map(p => (
                  <div key={p.player} style={{ background: "#1a0d0d", border: "1px solid #e74c3c33", borderRadius: 8, padding: "8px 12px", flex: "1 1 120px" }}>
                    <div style={{ color: "#dde6f5", fontWeight: 700, fontSize: "0.85em" }}>
                      <Link href={`/players?player=${encodeURIComponent(p.player)}`} style={{ color: "#dde6f5", textDecoration: "none" }} onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")} onMouseLeave={e => (e.currentTarget.style.color = "#dde6f5")}>{p.player}</Link>
                    </div>
                    <div style={{ fontSize: "0.72em", marginTop: 3 }}>
                      <span style={{ color: "#e74c3c" }}>Live #{p.position ?? "?"}</span>
                      <span style={{ color: "#3a5060", margin: "0 5px" }}>vs</span>
                      <span style={{ color: "#4a6080" }}>Model #{p.model_rank}</span>
                      <span style={{ color: "#e74c3c", marginLeft: 8 }}>{p.rank_diff}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
              <th style={{ ...th }}>Live Pos</th>
              <th style={{ ...th, color: "#00c44f" }}>Total</th>
              <th style={{ ...th }}>Thru</th>
              <th style={{ ...th }}>Model #</th>
              <th style={{ ...th }}>Δ Rank</th>
              <th style={{ ...th, color: "#00c44f" }}>Model Win%</th>
              <th style={{ ...th, color: "#4cb8ff" }}>Model Top10%</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const isPick = myPicksNorm.has(normName(p.player));
              const bg = isPick ? "#091a0f" : i % 2 === 0 ? "#0d1a30" : "#0a1525";
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid #0f2236",
                background: bg, textAlign: "center", fontSize: "0.85em",
              };

              const isCut = p.made_cut === false;
              const diff  = p.rank_diff ?? 0;
              const diffColor = diff > 5 ? "#00c44f" : diff < -5 ? "#e74c3c" : diff !== 0 ? "#f39c12" : "#3a5060";
              const diffStr   = diff === 0 ? "=" : diff > 0 ? `+${diff}` : String(diff);

              const totalColor = p.total_numeric == null ? "#7f8c8d"
                : p.total_numeric < 0 ? "#00c44f"
                : p.total_numeric > 0 ? "#e74c3c"
                : "#8ba0b8";

              return (
                <tr key={`vsp-${i}`} style={{ opacity: isCut ? 0.55 : 1, borderLeft: isPick ? "2px solid #00c44f" : "2px solid transparent" }}>
                  <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
                    <Link
                      href={`/players?player=${encodeURIComponent(p.player)}`}
                      style={{ color: isPick ? "#00c44f" : isCut ? "#3a5060" : "#dde6f5", textDecoration: "none", fontWeight: isPick ? 700 : 600 }}
                      onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                      onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : isCut ? "#3a5060" : "#dde6f5")}
                    >
                      {p.player}
                    </Link>
                    {isPick && (
                      <span style={{ fontSize: "0.58em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", border: "1px solid #00c44f44", borderRadius: 3, padding: "1px 4px", marginLeft: 6 }}>
                        MY PICK
                      </span>
                    )}
                    {isCut && <span style={{ fontSize: "0.7em", color: "#5a2020", marginLeft: 6, background: "#2a0f0f", padding: "1px 4px", borderRadius: 3 }}>CUT</span>}
                  </td>
                  <td style={{ ...td, color: "#8ba0b8", fontWeight: 700 }}>{p.position ?? "—"}</td>
                  <td style={{ ...td, color: totalColor, fontWeight: 700 }}>{p.total ?? "—"}</td>
                  <td style={{ ...td, color: "#7f8c8d" }}>{p.thru ?? "—"}</td>
                  <td style={{ ...td, color: "#4cb8ff", fontWeight: 700 }}>{p.model_rank != null ? `#${p.model_rank}` : "—"}</td>
                  <td style={{ ...td, color: diffColor, fontWeight: Math.abs(diff) > 5 ? 700 : 400 }}
                    title={diff > 0 ? "beating model prediction" : diff < 0 ? "below model prediction" : "on model"}>
                    {diffStr}
                  </td>
                  <td style={{ ...td, color: "#00c44f" }}>{p.win_prob != null ? `${p.win_prob.toFixed(1)}%` : "—"}</td>
                  <td style={{ ...td, color: "#4cb8ff" }}>{p.top10_prob != null ? `${p.top10_prob.toFixed(1)}%` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>
        Δ Rank = Live position minus model rank · green = beating prediction · red = below prediction
      </p>
    </div>
  );
}
