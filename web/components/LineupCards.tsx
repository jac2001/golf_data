"use client";

import { LineupPick } from "@/lib/api";

type Props = {
  picks: LineupPick[];
  narrative: string;
  generatedAt: string;
};

const TIER_COLOR: Record<string, string> = {
  elite:    "#f1c40f",
  great:    "#00c44f",
  good:     "#4cb8ff",
  value:    "#9b59b6",
  longshot: "#e67e22",
};

const DRIFT_ARROW: Record<string, { symbol: string; color: string }> = {
  UP:       { symbol: "▲", color: "#e74c3c" },
  DOWN:     { symbol: "▼", color: "#00c44f" },
  CONSTANT: { symbol: "→", color: "#4a6080" },
};

function UsePips({ count }: { count: number | null }) {
  const total = 3;
  const filled = Math.min(count ?? 0, total);
  return (
    <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} style={{
          width: 9, height: 9, borderRadius: "50%",
          background: i < filled ? "#00c44f" : "#1a3050",
          border: `1px solid ${i < filled ? "#00c44f88" : "#1e3a5f"}`,
          boxShadow: i < filled ? "0 0 4px #00c44f44" : "none",
        }} />
      ))}
      <span style={{ fontSize: "0.65em", color: "#4a6080", marginLeft: 4 }}>
        {count ?? 0} use{count !== 1 ? "s" : ""} left
      </span>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: "#080f1e",
      border: "1px solid #1a2537",
      borderRadius: 6,
      padding: "8px 10px",
      textAlign: "center",
    }}>
      <div style={{ fontSize: "0.58em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: "1.05em", fontWeight: 800, color }}>{value}</div>
    </div>
  );
}

function PickCard({ pick, rank }: { pick: LineupPick; rank: number }) {
  const color = TIER_COLOR[pick.tier] ?? "#4cb8ff";
  const drift = DRIFT_ARROW[pick.drift] ?? null;

  const evStr = pick.this_week_ev != null
    ? (pick.this_week_ev >= 1000 ? `$${(pick.this_week_ev / 1000).toFixed(0)}k` : `$${pick.this_week_ev}`)
    : null;

  const sgStr = pick.season_sg != null
    ? (pick.season_sg > 0 ? `+${pick.season_sg.toFixed(2)}` : pick.season_sg.toFixed(2))
    : null;

  return (
    <div style={{
      background: "#0d1a30",
      border: `1px solid #1e3a5f`,
      borderTop: `3px solid ${color}`,
      borderRadius: 10,
      padding: "16px 18px",
      position: "relative",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      gap: 0,
    }}>
      {/* Background glow */}
      <div style={{
        position: "absolute", top: 0, right: 0,
        width: 140, height: 140,
        background: `radial-gradient(circle at top right, ${color}0d 0%, transparent 65%)`,
        pointerEvents: "none",
      }} />

      {/* Header: rank+tier on left, recommendation on right */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 6 }}>
        <span style={{
          fontSize: "0.6em", fontWeight: 800, color,
          background: `${color}15`, padding: "2px 8px",
          borderRadius: 4, border: `1px solid ${color}30`,
          textTransform: "uppercase", letterSpacing: "0.06em",
          whiteSpace: "nowrap",
        }}>
          Pick {rank} · {pick.tier}
        </span>
        <span style={{
          fontSize: "0.6em", fontWeight: 700, color: "#00c44f",
          background: "#0d2e18", padding: "2px 7px",
          borderRadius: 4, border: "1px solid #00c44f30",
          whiteSpace: "nowrap",
        }}>
          {pick.recommendation || "USE NOW"}
        </span>
      </div>

      {/* Player name */}
      <div style={{ fontSize: "1.3em", fontWeight: 800, color: "#dde6f5", lineHeight: 1.15, marginBottom: 6 }}>
        {pick.player_name}
      </div>

      {/* Sub-info: rank · odds · drift */}
      <div style={{ fontSize: "0.72em", color: "#5a7090", display: "flex", gap: 8, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
        {pick.world_rank != null && <span>World #{pick.world_rank}</span>}
        {pick.odds_to_win && pick.odds_to_win !== "—" && (
          <span style={{ color: "#3a5070" }}>{pick.odds_to_win} to win</span>
        )}
        {drift && (
          <span style={{ color: drift.color, fontWeight: 700, fontSize: "1.1em" }}>
            {drift.symbol}
          </span>
        )}
      </div>

      {/* 2×2 stats grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 6,
        marginBottom: 14,
      }}>
        <StatBox label="Win %" value={pick.win_prob != null ? `${pick.win_prob.toFixed(1)}%` : "—"} color="#00c44f" />
        <StatBox label="Top 10 %" value={pick.top10_prob != null ? `${pick.top10_prob.toFixed(0)}%` : "—"} color="#4cb8ff" />
        {sgStr  && <StatBox label="SG Total" value={sgStr}  color="#8ba0b8" />}
        {evStr  && <StatBox label="EV" value={evStr} color="#f1c40f" />}
      </div>

      {/* Uses remaining */}
      <UsePips count={pick.uses_left} />

      {/* Narrative */}
      {pick.narrative && (
        <p style={{
          fontSize: "0.74em", color: "#6a8090",
          lineHeight: 1.55, borderTop: "1px solid #1a2537", paddingTop: 10,
          margin: "12px 0 0",
        }}>
          {pick.narrative}
        </p>
      )}
    </div>
  );
}

export default function LineupCards({ picks, narrative, generatedAt }: Props) {
  if (!picks.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No lineup data. Run the season strategy pipeline to generate picks.
      </div>
    );
  }

  return (
    <div>
      {/* 3-column grid — always equal width, no wrapping surprises */}
      <div style={{
        display: "grid",
        gridTemplateColumns: `repeat(${picks.length}, 1fr)`,
        gap: 14,
        marginBottom: 20,
      }}>
        {picks.map((pick, i) => (
          <PickCard key={pick.player_name} pick={pick} rank={i + 1} />
        ))}
      </div>

      {/* Weekly narrative */}
      {narrative && (
        <div style={{
          background: "#080f1e", border: "1px solid #1e3a5f",
          borderLeft: "3px solid #00c44f",
          borderRadius: 10, padding: "14px 18px",
        }}>
          <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8 }}>
            Weekly Analysis
          </div>
          <p style={{ color: "#8ba0b8", fontSize: "0.85em", lineHeight: 1.6, margin: 0 }}>
            {narrative}
          </p>
          {generatedAt && (
            <p style={{ color: "#2a3a50", fontSize: "0.68em", marginTop: 8, marginBottom: 0 }}>
              Generated: {generatedAt.slice(0, 16)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
