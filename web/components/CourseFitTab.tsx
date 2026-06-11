"use client";

import { useState, useMemo } from "react";
import { CourseFitResponse, CourseFitPlayer } from "@/lib/api";

type SortMode = "model" | "boost" | "history";

// ── Shared table styles ───────────────────────────────────────────────────────

const cell: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #1a2a3a",
  fontSize: "0.83em",
  color: "#c8d8e8",
  textAlign: "left",
};

const hdr: React.CSSProperties = {
  ...cell,
  color: "#7a9ab8",
  fontWeight: 600,
  fontSize: "0.76em",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  borderBottom: "1px solid #1e3a5f",
  whiteSpace: "nowrap",
};

const COL_SPAN = 12;

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(decimals)}%`;
}

function sgColor(v: number | null): string {
  if (v == null) return "#4a6080";
  if (v >= 0.3)  return "#00c44f";
  if (v >= 0.1)  return "#7ecf9e";
  if (v <= -0.3) return "#e05555";
  if (v <= -0.1) return "#c08888";
  return "#7a9ab8";
}

function adjColor(v: number | null): string {
  if (v == null) return "#4a6080";
  if (v >= 0.08)  return "#00c44f";
  if (v >= 0.02)  return "#7ecf9e";
  if (v <= -0.08) return "#e05555";
  if (v <= -0.02) return "#c08888";
  return "#7a9ab8";
}

function shiftColor(v: number | null): string {
  if (v == null) return "#7a9ab8";
  if (v > 0.004)  return "#00c44f";
  if (v < -0.004) return "#e05555";
  return "#7a9ab8";
}

function usesColor(n: number | null): string {
  if (n == null) return "#3a5060";
  if (n >= 2) return "#00c44f";
  if (n === 1) return "#f0c040";
  return "#e05555";
}

function fmtAdj(v: number | null): string {
  if (v == null) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}

// Mini SG bar (scale ±1.5)
function SgBar({ value }: { value: number | null }) {
  if (value == null) return <span style={{ color: "#3a5060" }}>—</span>;
  const capped = Math.max(-1.5, Math.min(1.5, value));
  const barW   = Math.abs(capped / 1.5) * 28;
  const color  = sgColor(value);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ color, fontSize: "0.82em", width: 36, textAlign: "right" }}>
        {(value >= 0 ? "+" : "") + value.toFixed(2)}
      </span>
      <span style={{ display: "inline-block", height: 6, width: Math.max(barW, 2), background: color, borderRadius: 3, opacity: 0.8 }} />
    </span>
  );
}

// Mini adjustment bar (scale configurable, default ±0.35)
function AdjBar({ value, scale = 0.35 }: { value: number | null; scale?: number }) {
  if (value == null) return <span style={{ color: "#3a5060" }}>—</span>;
  const capped = Math.max(-scale, Math.min(scale, value));
  const barW   = Math.abs(capped / scale) * 28;
  const color  = adjColor(value);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ color, fontSize: "0.82em", width: 38, textAlign: "right" }}>
        {fmtAdj(value)}
      </span>
      <span style={{ display: "inline-block", height: 6, width: Math.max(barW, 2), background: color, borderRadius: 3, opacity: 0.8 }} />
    </span>
  );
}

// ── Course profile bars ───────────────────────────────────────────────────────

function CourseProfile({ profile }: { profile: CourseFitResponse["course_profile"] }) {
  const ITEMS = [
    { key: "arg"  as const, label: "Around Green", desc: "Chipping, pitching, bunker play" },
    { key: "ott"  as const, label: "Off the Tee",  desc: "Driving distance & accuracy" },
    { key: "putt" as const, label: "Putting",       desc: "Strokes gained on the greens" },
    { key: "app"  as const, label: "Approach",      desc: "Iron play into greens" },
  ].sort((a, b) => profile[b.key] - profile[a.key]);

  return (
    <div style={{ background: "#080f1e", border: "1px solid #1e3a5f", borderRadius: 8, padding: "14px 18px", marginBottom: 20 }}>
      <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 12 }}>
        Course Demand Profile — what this course rewards most
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {ITEMS.map(({ key, label, desc }) => {
          const val = profile[key];
          const barColor = val > 0.3 ? "#00c44f" : val > 0.18 ? "#f0c040" : "#2a5a7a";
          return (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 110, fontSize: "0.82em", color: "#c8d8e8", flexShrink: 0 }}>{label}</div>
              <div style={{ flex: 1, height: 8, background: "#0d1929", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${val * 100}%`, height: "100%", background: barColor, borderRadius: 4, transition: "width 0.3s ease" }} />
              </div>
              <div style={{ width: 36, fontSize: "0.82em", color: "#7a9ab8", textAlign: "right", flexShrink: 0 }}>{Math.round(val * 100)}%</div>
              <div style={{ width: 200, fontSize: "0.72em", color: "#3a5060" }}>{desc}</div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 10, fontSize: "0.68em", color: "#2a4060" }}>
        Higher % = this skill is more differentiating at this course vs. an average PGA Tour event.
      </div>
    </div>
  );
}

// ── Decomposition detail panel (expand row) ───────────────────────────────────

function DecompPanel({ player: p }: { player: CourseFitPlayer }) {
  const base   = p.dg_baseline_pred;
  const final  = p.dg_final_pred;
  const timing = p.dg_timing_adj;
  const fit    = p.dg_fit_adj;
  const hist   = p.dg_hist_adj;

  if (base == null || final == null) {
    return (
      <tr>
        <td colSpan={COL_SPAN} style={{ ...cell, background: "#060d1a", color: "#3a5060", fontStyle: "italic", fontSize: "0.78em" }}>
          No DG decomposition available for this player.
        </td>
      </tr>
    );
  }

  const steps: { label: string; value: number | null; color?: string }[] = [
    { label: "Skill baseline", value: base,   color: "#7a9ab8" },
    { label: "+ Timing / form", value: timing, color: adjColor(timing) },
    { label: "+ Course fit",    value: fit,    color: adjColor(fit) },
    { label: "+ History",       value: hist,   color: adjColor(hist) },
  ];

  const remaining = final != null && base != null
    ? final - base - (timing ?? 0) - (fit ?? 0) - (hist ?? 0)
    : null;

  return (
    <tr>
      <td colSpan={COL_SPAN} style={{ background: "#060d1a", padding: "10px 20px 14px 48px", borderBottom: "1px solid #1e3a5f" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 0, flexWrap: "wrap", rowGap: 6 }}>
          {steps.map((s, idx) => (
            <span key={idx} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {idx > 0 && <span style={{ color: "#2a4060", margin: "0 6px" }}>→</span>}
              <span style={{ fontSize: "0.74em", color: "#4a6080" }}>{s.label}</span>
              <span style={{
                fontSize: "0.82em", fontWeight: 600,
                color: idx === 0 ? "#7a9ab8" : adjColor(s.value),
              }}>
                {idx === 0
                  ? (s.value != null ? (s.value >= 0 ? "+" : "") + s.value.toFixed(2) : "—")
                  : fmtAdj(s.value)
                }
              </span>
            </span>
          ))}
          {remaining != null && Math.abs(remaining) > 0.005 && (
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ color: "#2a4060", margin: "0 6px" }}>→</span>
              <span style={{ fontSize: "0.74em", color: "#4a6080" }}>+ other</span>
              <span style={{ fontSize: "0.82em", fontWeight: 600, color: adjColor(remaining) }}>
                {fmtAdj(remaining)}
              </span>
            </span>
          )}
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "#2a4060", margin: "0 6px" }}>→</span>
            <span style={{ fontSize: "0.74em", color: "#4a6080" }}>DG final</span>
            <span style={{
              fontSize: "0.88em", fontWeight: 700,
              color: final >= 1.5 ? "#00c44f" : final >= 0 ? "#7ecf9e" : "#7a9ab8",
            }}>
              {(final >= 0 ? "+" : "") + final.toFixed(2)} SG
            </span>
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 20 }}>
            <span style={{ fontSize: "0.74em", color: "#4a6080" }}>DG win%</span>
            <span style={{
              fontSize: "0.88em", fontWeight: 700,
              color: (p.dg_win ?? 0) > 0.08 ? "#00c44f" : (p.dg_win ?? 0) > 0.03 ? "#f0c040" : "#7a9ab8",
            }}>
              {p.dg_win != null ? fmtPct(p.dg_win) : "—"}
            </span>
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 8 }}>
            <span style={{ fontSize: "0.74em", color: "#4a6080" }}>Model win%</span>
            <span style={{ fontSize: "0.88em", fontWeight: 700, color: "#7a9ab8" }}>
              {p.win_prob != null ? fmtPct(p.win_prob) : "—"}
            </span>
          </span>
        </div>
        <div style={{ marginTop: 6, fontSize: "0.7em", color: "#2a4060" }}>
          Baseline = DG skill rating (pure SG, no course context). Positive timing = currently above expected form.
        </div>
      </td>
    </tr>
  );
}

// ── Player row ────────────────────────────────────────────────────────────────

function PlayerRow({ player: p, index: i, historyType, expanded, onToggle }: {
  player: CourseFitPlayer;
  index: number;
  historyType: "venue" | "tournament";
  expanded: boolean;
  onToggle: () => void;
}) {
  const shift = p.win_prob_shift ?? 0;
  const name  = p.player_name.includes(",")
    ? p.player_name.split(",").reverse().join(" ").trim()
    : p.player_name;

  const rowBg = expanded ? "#0a1525" : (i % 2 === 0 ? "transparent" : "#050c18");

  return (
    <>
      <tr
        onClick={onToggle}
        style={{ background: rowBg, cursor: "pointer" }}
        title="Click to see DG decomposition"
      >

        {/* Rank */}
        <td style={{ ...cell, color: "#4a6080", width: 32 }}>{p.overall_rank}</td>

        {/* Player name + uses badge */}
        <td style={{ ...cell, minWidth: 170 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "#dde6f5", fontWeight: 600, fontSize: "0.88em" }}>{name}</span>
            {p.uses_remaining != null && (
              <span style={{
                fontSize: "0.68em", fontWeight: 700,
                color: usesColor(p.uses_remaining),
                background: "#0a1520", border: `1px solid ${usesColor(p.uses_remaining)}40`,
                borderRadius: 4, padding: "1px 6px",
              }}>
                {p.uses_remaining}u
              </span>
            )}
            <span style={{ fontSize: "0.68em", color: expanded ? "#00c44f" : "#2a4060", marginLeft: 2 }}>
              {expanded ? "▲" : "▼"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 4, marginTop: 2, flexWrap: "wrap" }}>
            {p.world_rank != null && (
              <span style={{ fontSize: "0.7em", color: "#4a6080" }}>#{p.world_rank}</span>
            )}
            {!p.has_history && (
              <span style={{ fontSize: "0.68em", color: "#4a5060", background: "#0d1520", border: "1px solid #1e2a3a", borderRadius: 3, padding: "1px 5px" }}>
                no history
              </span>
            )}
          </div>
        </td>

        {/* Venue / tournament history record */}
        <td style={{ ...cell, textAlign: "center" }}>
          {p.venue_starts > 0 ? (
            <div style={{ fontSize: "0.82em" }}>
              <span style={{ color: "#7a9ab8" }}>{p.venue_starts} starts</span>
              {p.venue_top10s > 0 && (
                <span style={{ marginLeft: 6, color: "#f0c040", fontWeight: 600 }}>
                  T10×{p.venue_top10s}
                </span>
              )}
              {p.venue_wins > 0 && (
                <span style={{ marginLeft: 4, color: "#00c44f", fontWeight: 700 }}>W</span>
              )}
            </div>
          ) : (
            <span style={{ color: "#2a3a4a", fontSize: "0.78em" }}>—</span>
          )}
        </td>

        {/* Tourney record */}
        <td style={{ ...cell, textAlign: "center" }}>
          {p.has_history && p.course_starts != null ? (
            <div style={{ fontSize: "0.82em" }}>
              {p.avg_to_par != null && (
                <span style={{ fontWeight: 600, color: p.avg_to_par < 0 ? "#00c44f" : "#e05555" }}>
                  {p.avg_to_par > 0 ? "+" : ""}{p.avg_to_par}
                </span>
              )}
              {p.cut_rate != null && (
                <span style={{ marginLeft: 6, fontSize: "0.85em", color: "#4a6080" }}>
                  {Math.round(p.cut_rate * 100)}% cut
                </span>
              )}
            </div>
          ) : (
            <span style={{ color: "#2a3a4a", fontSize: "0.78em" }}>—</span>
          )}
        </td>

        {/* SG OTT / APP vs avg */}
        <td style={{ ...cell, textAlign: "center" }}><SgBar value={p.sg_ott_vs_avg} /></td>
        <td style={{ ...cell, textAlign: "center" }}><SgBar value={p.sg_app_vs_avg} /></td>

        {/* DG adjustments: Timing + Course Fit */}
        <td style={{ ...cell, textAlign: "center" }}><AdjBar value={p.dg_timing_adj} scale={0.4} /></td>
        <td style={{ ...cell, textAlign: "center" }}><AdjBar value={p.dg_fit_adj} scale={0.2} /></td>

        {/* Course boost (our model) */}
        <td style={{ ...cell, textAlign: "right" }}>
          <span style={{ color: shiftColor(p.win_prob_shift), fontWeight: Math.abs(shift) > 0.005 ? 700 : 400, fontSize: "0.88em" }}>
            {shift > 0.0005 ? "+" : ""}{shift !== 0 ? fmtPct(p.win_prob_shift, 2) : "—"}
          </span>
        </td>

        {/* DG Win% */}
        <td style={{ ...cell, textAlign: "right" }}>
          <span style={{
            fontSize: "0.88em", fontWeight: 600,
            color: (p.dg_win ?? 0) > 0.08 ? "#00c44f" : (p.dg_win ?? 0) > 0.03 ? "#f0c040" : "#7a9ab8",
          }}>
            {p.dg_win != null ? fmtPct(p.dg_win) : "—"}
          </span>
        </td>

        {/* Model Win% */}
        <td style={{ ...cell, textAlign: "right", fontWeight: 600, color: "#dde6f5" }}>
          {fmtPct(p.win_prob)}
        </td>

        {/* Top 10% */}
        <td style={{ ...cell, textAlign: "right" }}>
          {fmtPct(p.top10_prob)}
        </td>
      </tr>

      {/* Expand panel */}
      {expanded && <DecompPanel player={p} />}
    </>
  );
}

// ── Section divider ───────────────────────────────────────────────────────────

function SectionHeader({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <tr>
      <td colSpan={COL_SPAN} style={{
        padding: "8px 12px 4px",
        fontSize: "0.72em",
        color,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        borderBottom: `1px solid ${color}30`,
        background: `${color}08`,
      }}>
        {label} <span style={{ fontWeight: 400, opacity: 0.6 }}>({count})</span>
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function CourseFitTab({ data }: { data: CourseFitResponse }) {
  const venueLabel = data.venue_label || "Venue";
  const [sortMode, setSortMode]   = useState<SortMode>("boost");
  const [search, setSearch]       = useState("");
  const [minStarts, setMinStarts] = useState(1);
  const [expanded, setExpanded]   = useState<Set<string>>(new Set());

  function toggleExpand(name: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  const startCounts = [0, 1, 2, 3, 4].map(n => ({
    n,
    count: data.players.filter(p => (p.course_starts ?? 0) >= n).length,
  }));

  const filtered = useMemo(() => {
    let list = [...data.players].filter(p => (p.course_starts ?? 0) >= minStarts);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(p => p.player_name.toLowerCase().includes(q));
    }
    return list;
  }, [data.players, minStarts, search]);

  const { risers, fallers } = useMemo(() => {
    let list = [...filtered];

    if (sortMode === "model") {
      list.sort((a, b) => (b.win_prob ?? 0) - (a.win_prob ?? 0));
      return { risers: list, fallers: [] };
    }

    if (sortMode === "history") {
      list.sort((a, b) => {
        if (!a.has_history && b.has_history) return 1;
        if (a.has_history && !b.has_history) return -1;
        return (a.avg_to_par ?? 99) - (b.avg_to_par ?? 99);
      });
      return { risers: list, fallers: [] };
    }

    const r = list
      .filter(p => p.has_history && (p.win_prob_shift ?? 0) > 0.0001)
      .sort((a, b) => (b.win_prob_shift ?? 0) - (a.win_prob_shift ?? 0));
    const f = list
      .filter(p => !p.has_history || (p.win_prob_shift ?? 0) <= 0.0001)
      .sort((a, b) => {
        if (!a.has_history && b.has_history) return 1;
        if (a.has_history && !b.has_history) return -1;
        return (a.win_prob_shift ?? 0) - (b.win_prob_shift ?? 0);
      });
    return { risers: r, fallers: f };
  }, [filtered, sortMode]);

  const SORT_LABELS: Record<SortMode, string> = {
    boost:   "Risers & Fallers",
    model:   "By Model Rank",
    history: "By Course History",
  };

  const showSplit = sortMode === "boost";

  return (
    <div>
      <CourseProfile profile={data.course_profile} />

      {data.course_history_type === "tournament" && (
        <div style={{
          background: "#1a1000", border: "1px solid #5a4000",
          borderRadius: 8, padding: "10px 16px", marginBottom: 16,
          fontSize: "0.82em", color: "#c09040", lineHeight: 1.6,
        }}>
          <strong>Note:</strong> "Venue Record" shows {venueLabel} history across all years in our database. The SG vs avg values and course boost reflect that same multi-year history.
        </div>
      )}

      {/* Sort buttons + search */}
      <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
        {(["boost", "model", "history"] as SortMode[]).map(mode => (
          <button key={mode} onClick={() => setSortMode(mode)} style={{
            background: sortMode === mode ? "#1a3a5f" : "#0d1929",
            border: `1px solid ${sortMode === mode ? "#00c44f" : "#1e3a5f"}`,
            color: sortMode === mode ? "#dde6f5" : "#7a9ab8",
            borderRadius: 6, padding: "5px 12px", fontSize: "0.8em", cursor: "pointer",
          }}>
            {SORT_LABELS[mode]}
          </button>
        ))}
        <input
          placeholder="Search player…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            background: "#0d1929", border: "1px solid #1e3a5f", borderRadius: 6,
            color: "#c8d8e8", padding: "5px 10px", fontSize: "0.8em",
            outline: "none", marginLeft: "auto",
          }}
        />
      </div>

      {/* Min starts + uses legend */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.75em", color: "#4a6080", marginRight: 4 }}>Min starts:</span>
        {startCounts.map(({ n, count }) => (
          <button key={n} onClick={() => setMinStarts(n)} style={{
            background: minStarts === n ? "#1a2a40" : "#0d1929",
            border: `1px solid ${minStarts === n ? "#7a9ab8" : "#1e3a5f"}`,
            color: minStarts === n ? "#dde6f5" : "#4a6080",
            borderRadius: 5, padding: "3px 10px", fontSize: "0.77em", cursor: "pointer",
          }}>
            {n === 0 ? "All" : `${n}+`}
            <span style={{ marginLeft: 4, color: "#3a5070" }}>({count})</span>
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, fontSize: "0.72em", alignItems: "center" }}>
          <span style={{ color: "#4a6080" }}>Uses:</span>
          {[{ n: 2, label: "2 left" }, { n: 1, label: "1 left" }, { n: 0, label: "0 left" }].map(({ n, label }) => (
            <span key={n} style={{ color: usesColor(n) }}>
              <span style={{ fontWeight: 700 }}>{n}u</span> {label}
            </span>
          ))}
          <span style={{ color: "#3a5060" }}>— not on roster</span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 980 }}>
          <thead>
            <tr>
              <th style={hdr}>#</th>
              <th style={hdr}>Player</th>
              <th style={{ ...hdr, textAlign: "center" }}>{venueLabel}</th>
              <th style={{ ...hdr, textAlign: "center" }}>Avg Score</th>
              <th style={{ ...hdr, textAlign: "center" }}>OTT</th>
              <th style={{ ...hdr, textAlign: "center" }}>APP</th>
              <th style={{ ...hdr, textAlign: "center" }}>Timing</th>
              <th style={{ ...hdr, textAlign: "center" }}>Fit Adj</th>
              <th style={{ ...hdr, textAlign: "right" }}>Boost</th>
              <th style={{ ...hdr, textAlign: "right" }}>DG Win%</th>
              <th style={{ ...hdr, textAlign: "right" }}>Win%</th>
              <th style={{ ...hdr, textAlign: "right" }}>T10%</th>
            </tr>
          </thead>
          <tbody>
            {showSplit ? (
              <>
                <SectionHeader label="Course suits" count={risers.length} color="#00c44f" />
                {risers.map((p, i) => (
                  <PlayerRow
                    key={p.player_name} player={p} index={i}
                    historyType={data.course_history_type}
                    expanded={expanded.has(p.player_name)}
                    onToggle={() => toggleExpand(p.player_name)}
                  />
                ))}
                <SectionHeader label="Course hurts / no data" count={fallers.length} color="#e05555" />
                {fallers.map((p, i) => (
                  <PlayerRow
                    key={p.player_name} player={p} index={i}
                    historyType={data.course_history_type}
                    expanded={expanded.has(p.player_name)}
                    onToggle={() => toggleExpand(p.player_name)}
                  />
                ))}
              </>
            ) : (
              (sortMode === "model" ? risers : risers).map((p, i) => (
                <PlayerRow
                  key={p.player_name} player={p} index={i}
                  historyType={data.course_history_type}
                  expanded={expanded.has(p.player_name)}
                  onToggle={() => toggleExpand(p.player_name)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 10, fontSize: "0.72em", color: "#2a4060" }}>
        Click any row to expand DG decomposition. Timing = DG form adjustment. Fit Adj = course suitability adjustment. DG Win% = DataGolf model.
      </div>
    </div>
  );
}
