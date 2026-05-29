"use client";

import { useState } from "react";
import { ExpertPick, ExpertConsensusPlayer } from "@/lib/api";

type Props = {
  experts: ExpertPick[];
  consensus: ExpertConsensusPlayer[];
  tournament: string;
};

type View = "consensus" | "byexpert";

function Bar({ pct, color, max = 100 }: { pct: number; color: string; max?: number }) {
  const fill = Math.min(pct / max * 100, 100);
  return (
    <div style={{
      flex: 1, height: 6, background: "#0a1525", borderRadius: 3, overflow: "hidden",
    }}>
      <div style={{ width: `${fill}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.3s" }} />
    </div>
  );
}

function ConsensusTable({ rows, nExperts }: { rows: ExpertConsensusPlayer[]; nExperts: number }) {
  const maxLineup = Math.max(...rows.map(r => r.lineup_mentions), 1);

  return (
    <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
        <thead>
          <tr>
            {["#", "Player", "Lineups", "", "Winner", ""].map((h, i) => (
              <th key={i} style={{
                padding: "7px 10px", background: "#0a1628",
                fontSize: "0.65em", fontWeight: 700, color: "#4a6080",
                textTransform: "uppercase", letterSpacing: "0.05em",
                borderBottom: "1px solid #1e3a5f",
                textAlign: i === 1 ? "left" : "center",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
            const isTopWinner = r.winner_picks > 0;
            return (
              <tr key={r.player_name} style={{ background: bg }}>
                <td style={{ padding: "7px 10px", textAlign: "center", color: "#4a6080", fontSize: "0.75em", width: 32 }}>
                  {i + 1}
                </td>
                <td style={{ padding: "7px 12px", fontWeight: 600, fontSize: "0.88em", color: isTopWinner ? "#dde6f5" : "#9ab0c8", whiteSpace: "nowrap" }}>
                  {r.player_name}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "center", fontSize: "0.82em", color: "#00c44f", fontWeight: 700, width: 60 }}>
                  {r.lineup_mentions}/{nExperts}
                </td>
                <td style={{ padding: "7px 10px", width: 120 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Bar pct={r.lineup_mentions} color="#00c44f" max={maxLineup} />
                    <span style={{ fontSize: "0.68em", color: "#4a6080", width: 30, textAlign: "right" }}>
                      {r.lineup_pct.toFixed(0)}%
                    </span>
                  </div>
                </td>
                <td style={{ padding: "7px 10px", textAlign: "center", fontSize: "0.82em", color: isTopWinner ? "#f1c40f" : "#3a5060", fontWeight: isTopWinner ? 800 : 400, width: 60 }}>
                  {r.winner_picks > 0 ? `${r.winner_picks}/${nExperts}` : "—"}
                </td>
                <td style={{ padding: "7px 10px", width: 100 }}>
                  {r.winner_picks > 0 && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Bar pct={r.winner_picks} color="#f1c40f" max={nExperts} />
                      <span style={{ fontSize: "0.68em", color: "#4a6080", width: 30, textAlign: "right" }}>
                        {r.winner_pct.toFixed(0)}%
                      </span>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ExpertCard({ expert }: { expert: ExpertPick }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f",
      borderLeft: expert.winner_pick ? "3px solid #f1c40f" : "3px solid #1e3a5f",
      borderRadius: 8, marginBottom: 8,
    }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: "100%", background: "transparent", border: "none", cursor: "pointer",
          padding: "12px 16px", display: "flex", alignItems: "flex-start",
          justifyContent: "space-between", gap: 16, textAlign: "left",
        }}
      >
        {/* Left: expert name + lineup chips */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
            <span style={{ fontWeight: 700, color: "#dde6f5", fontSize: "0.9em" }}>
              {expert.expert_name}
            </span>
            {expert.expert_title && (
              <span style={{ fontSize: "0.65em", color: "#4a6080" }}>{expert.expert_title}</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {expert.lineup.map(name => (
              <span key={name} style={{
                fontSize: "0.72em", fontWeight: 600, color: "#9ab0c8",
                background: "#080f1e", border: "1px solid #1e3a5f",
                borderRadius: 4, padding: "2px 8px",
              }}>
                {name.split(" ").pop()}
              </span>
            ))}
          </div>
        </div>

        {/* Right: winner pick + toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
          {expert.winner_pick && (
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em" }}>Winner</div>
              <div style={{ fontSize: "0.82em", fontWeight: 800, color: "#f1c40f" }}>
                {expert.winner_pick.split(" ").pop()}
              </div>
            </div>
          )}
          <span style={{ color: "#4a6080", fontSize: "0.8em" }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded && (
        <div style={{ padding: "0 16px 14px", borderTop: "1px solid #1a2a3a" }}>

          {/* Full lineup + bench */}
          <div style={{ display: "flex", gap: 24, marginTop: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>
                Lineup
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {expert.lineup.map(name => (
                  <span key={name} style={{
                    fontSize: "0.78em", color: "#dde6f5", background: "#091525",
                    border: "1px solid #00c44f33", borderRadius: 5, padding: "3px 10px",
                  }}>
                    {name}
                  </span>
                ))}
              </div>
            </div>
            {expert.bench.length > 0 && (
              <div>
                <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>
                  Bench
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {expert.bench.map(name => (
                    <span key={name} style={{
                      fontSize: "0.78em", color: "#7f9ab0", background: "#091525",
                      border: "1px solid #1e3a5f", borderRadius: 5, padding: "3px 10px",
                    }}>
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {expert.winner_pick && (
              <div>
                <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}>
                  Winner Pick
                </div>
                <span style={{
                  fontSize: "0.78em", fontWeight: 700, color: "#f1c40f", background: "#1a1200",
                  border: "1px solid #f1c40f33", borderRadius: 5, padding: "3px 10px",
                }}>
                  {expert.winner_pick}
                </span>
              </div>
            )}
          </div>

          {/* Comment */}
          {expert.comment && (
            <div style={{
              marginTop: 12, padding: "10px 14px",
              borderLeft: "3px solid #1e3a5f",
              background: "#080f1e", borderRadius: "0 6px 6px 0",
            }}>
              <p style={{ margin: 0, fontSize: "0.82em", color: "#7f9ab0", lineHeight: 1.6 }}>
                {expert.comment}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ExpertPicksTab({ experts, consensus, tournament }: Props) {
  const [view, setView] = useState<View>("consensus");

  if (!experts.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No expert picks available for this tournament.
      </div>
    );
  }

  const winnerCounts: Record<string, number> = {};
  experts.forEach(e => { if (e.winner_pick) winnerCounts[e.winner_pick] = (winnerCounts[e.winner_pick] || 0) + 1; });
  const topWinner = Object.entries(winnerCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
  const uniqueWinners = Object.keys(winnerCounts).length;

  return (
    <div>
      {/* Summary strip */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          ["Experts",        String(experts.length)],
          ["Top Consensus",  topWinner.split(" ").pop() ?? topWinner],
          ["Unique Winners", String(uniqueWinners)],
          ["Tournament",     tournament || "—"],
        ].map(([label, value]) => (
          <div key={label} style={{
            background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
            padding: "10px 16px", flex: "1 1 120px", minWidth: 110,
          }}>
            <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
            <div style={{ fontSize: "0.9em", fontWeight: 700, color: "#dde6f5", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
          </div>
        ))}
      </div>

      {/* View toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {(["consensus", "byexpert"] as View[]).map(v => (
          <button
            key={v}
            onClick={() => setView(v)}
            style={{
              background: view === v ? "#00c44f22" : "transparent",
              border: `1px solid ${view === v ? "#00c44f" : "#1e3a5f"}`,
              borderRadius: 6, color: view === v ? "#00c44f" : "#7f8c8d",
              padding: "5px 14px", fontSize: "0.82em", fontWeight: 600, cursor: "pointer",
            }}
          >
            {v === "consensus" ? "Consensus Board" : "By Expert"}
          </button>
        ))}
      </div>

      {view === "consensus" && (
        <ConsensusTable rows={consensus} nExperts={experts.length} />
      )}

      {view === "byexpert" && (
        <div>
          {experts.map(e => <ExpertCard key={e.expert_name} expert={e} />)}
        </div>
      )}
    </div>
  );
}
