"use client";

/** Stats tab: the field's season, course, form and DataGolf numbers in one sortable table.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { FieldStatsPlayer, getFieldStats } from "@/lib/api";
import { BLUE, BORDER, CARD_BG, GOLD, GREEN, LABEL, MUTED, RED, TEXT, card, normName, rankColor } from "./shared";


// ── Stats tab ─────────────────────────────────────────────────────────────────

type StatsView = "sg" | "course" | "form" | "dg";


const VIEWS: { key: StatsView; label: string }[] = [
  { key: "sg",     label: "SG Breakdown" },
  { key: "course", label: "Course Fit" },
  { key: "form",   label: "Form" },
  { key: "dg",     label: "DG Model" },
];


export function StatsTab({ myPicks = [] }: { myPicks?: string[] }) {
  const myPicksNorm = useMemo(() => new Set(myPicks.map(normName)), [myPicks]);

  const [view, setView]     = useState<StatsView>("sg");
  const [players, setPlayers] = useState<FieldStatsPlayer[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortCol, setSortCol] = useState<keyof FieldStatsPlayer>("season_sg_total");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");

  useEffect(() => {
    getFieldStats().then(d => setPlayers(d.players)).finally(() => setLoading(false));
  }, []);

  // Reset default sort when view changes
  useEffect(() => {
    const defaults: Record<StatsView, keyof FieldStatsPlayer> = {
      sg:     "season_sg_total",
      course: "course_sg_total_avg",
      form:   "form_trend",
      dg:     "dg_win",
    };
    setSortCol(defaults[view]);
    setSortDir("desc");
  }, [view]);

  function handleSort(col: keyof FieldStatsPlayer) {
    if (col === sortCol) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortCol(col); setSortDir("desc"); }
  }

  const sorted = useMemo(() => {
    if (!players) return [];
    const q = search.trim().toLowerCase();
    return [...players]
      .filter(p => !q || p.player_name.toLowerCase().includes(q))
      .sort((a, b) => {
        const av = (a[sortCol] as number | null) ?? (sortDir === "desc" ? -Infinity : Infinity);
        const bv = (b[sortCol] as number | null) ?? (sortDir === "desc" ? -Infinity : Infinity);
        return sortDir === "desc" ? bv - av : av - bv;
      });
  }, [players, sortCol, sortDir, search]);

  // ── shared table header / cell styles ───────────────────────────────────────

  const th = (col: keyof FieldStatsPlayer, label: string, align: "left" | "center" = "center") => (
    <th
      key={col as string}
      onClick={() => handleSort(col)}
      style={{
        padding: "7px 10px", background: "var(--bc-panel)", cursor: "pointer", userSelect: "none",
        textAlign: align, fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700, letterSpacing: "0.05em",
        textTransform: "uppercase", whiteSpace: "nowrap",
        color: sortCol === col ? GREEN : LABEL,
        borderBottom: `1px solid ${BORDER}`,
      }}
    >
      {label}{sortCol === col && (sortDir === "desc" ? " ↓" : " ↑")}
    </th>
  );

  const tdStyle = (i: number): React.CSSProperties => ({
    padding: "6px 10px",
    background: i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)",
    borderBottom: `1px solid var(--bc-card)`,
  });

  function sgCell(val: number | null, rank: number | null, i: number) {
    return (
      <td style={{ ...tdStyle(i), textAlign: "center" }}>
        <span style={{ color: val != null && val >= 0 ? GREEN : RED, fontWeight: 600, fontSize: "max(var(--fs-min), 0.85em)" }}>
          {val != null ? `${val >= 0 ? "+" : ""}${val.toFixed(2)}` : "—"}
        </span>
        {rank != null && (
          <span style={{ display: "block", fontSize: "max(var(--fs-min-xs), 0.65em)", color: rankColor(rank) }}>
            #{Math.round(rank)}
          </span>
        )}
      </td>
    );
  }

  if (loading) return <p style={{ color: MUTED }}>Loading…</p>;
  if (!players) return <p style={{ color: RED }}>Failed to load stats.</p>;

  return (
    <>
      <input 
        placeholder='Filter player...'
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{
          background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 6,
          color: TEXT, padding: "7px 12px", marginBottom: 12, width: 200, fontSize: "max(var(--fs-min), 0.85em)",
          outline: "none",
        }}
      />
      {/* View switcher */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {VIEWS.map(v => (
          <button
            key={v.key}
            onClick={() => setView(v.key)}
            style={{
              background: view === v.key ? GREEN + "22" : "transparent",
              border: `1px solid ${view === v.key ? GREEN : BORDER}`,
              borderRadius: 6, color: view === v.key ? GREEN : MUTED,
              padding: "5px 14px", fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 600, cursor: "pointer",
            }}
          >
            {v.label}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: "max(var(--fs-min), 0.75em)", color: LABEL, alignSelf: "center" }}>
          {sorted.length} players · click column to sort
        </span>
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
          <thead>
            <tr>
              <th style={{ padding: "7px 10px", background: "var(--bc-panel)", textAlign: "center", fontSize: "max(var(--fs-min-xs), 0.68em)", color: LABEL, borderBottom: `1px solid ${BORDER}`, width: 36 }}>#</th>
              {th("player_name", "Player", "left")}

              {view === "sg" && <>
                {th("season_sg_total",         "Total")}
                {th("season_sg_ott",           "OTT")}
                {th("season_sg_app",           "APP")}
                {th("season_sg_arg",           "ARG")}
                {th("season_sg_putt",          "Putt")}
              </>}

              {view === "course" && <>
                {th("course_sg_total_avg",  "SG Avg")}
                {th("course_sg_starts",     "Starts")}
                {th("course_made_cut_rate", "Cut%")}
                {th("course_win_rate",      "Win%")}
                {th("dg_course_fit_delta_pct", "DG Fit Δ%")}
              </>}

              {view === "form" && <>
                {th("form_trend",       "Form")}
                {th("consecutive_cuts", "Consec. Cuts")}
                {th("recent_top10s",    "Recent top 10s")}
                {th("recent_wins",      "Recent Wins")}
                {th("consecutive_top10s", "Consec. Top10s")}
              </>}

              {view === "dg" && <>
                {th("dg_win",              "DG Win%")}
                {th("win_prob",            "Our Win%")}
                {th("dg_top10",            "DG Top10%")}
                {th("top10_prob",          "Our Top10%")}
                {th("dg_course_fit_delta_pct", "Course Fit Δ%")}
              </>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => {
              const isPick = myPicksNorm.has(normName(p.player_name));
              return (
              <tr key={p.player_name} style={isPick ? { background: "var(--bc-panel)" } : undefined}>
                <td style={{ ...tdStyle(i), textAlign: "center", color: LABEL, fontSize: "max(var(--fs-min), 0.75em)", ...(isPick ? { background: "var(--bc-panel)" } : {}) }}>{i + 1}</td>
                <td style={{ ...tdStyle(i), fontSize: "max(var(--fs-min), 0.85em)", fontWeight: 600, whiteSpace: "nowrap", borderLeft: isPick ? "2px solid var(--bc-green)" : undefined, ...(isPick ? { background: "var(--bc-panel)" } : {}) }}>
                  <Link
                    href={`/players?player=${encodeURIComponent(p.player_name)}`}
                    style={{ color: isPick ? GREEN : TEXT, textDecoration: "none" }}
                  >
                    {p.player_name}
                  </Link>
                  {isPick && (
                    <span style={{
                      marginLeft: 8, fontSize: "max(var(--fs-min-xs), 0.65em)", fontWeight: 800,
                      color: GREEN, background: "color-mix(in srgb, var(--bc-green) 9%, transparent)", border: "1px solid color-mix(in srgb, var(--bc-green) 20%, transparent)",
                      borderRadius: 4, padding: "1px 6px", letterSpacing: "0.07em",
                    }}>MY PICK</span>
                  )}
                </td>

                {view === "sg" && <>
                  {sgCell(p.season_sg_total, null, i)}
                  {sgCell(p.season_sg_ott,  p.season_sg_ott_field_rank,  i)}
                  {sgCell(p.season_sg_app,  p.season_sg_app_field_rank,  i)}
                  {sgCell(p.season_sg_arg,  p.season_sg_arg_field_rank,  i)}
                  {sgCell(p.season_sg_putt, p.season_sg_putt_field_rank, i)}
                </>}

                {view === "course" && <>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontSize: "max(var(--fs-min), 0.85em)", color: (p.course_sg_total_avg ?? 0) >= 0 ? GREEN : RED, fontWeight: 600 }}>
                    {p.course_sg_starts ? (p.course_sg_total_avg != null ? `${p.course_sg_total_avg >= 0 ? "+" : ""}${p.course_sg_total_avg.toFixed(2)}` : "—") : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: MUTED, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.course_sg_starts ? Math.round(p.course_sg_starts) : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontSize: "max(var(--fs-min), 0.85em)", color: p.course_made_cut_rate != null ? (p.course_made_cut_rate >= 0.8 ? GREEN : MUTED) : MUTED }}>
                    {p.course_sg_starts ? (p.course_made_cut_rate != null ? `${(p.course_made_cut_rate * 100).toFixed(0)}%` : "—") : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GOLD, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.course_sg_starts && p.course_win_rate ? `${(p.course_win_rate * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 600, fontSize: "max(var(--fs-min), 0.85em)",
                      color: p.dg_course_fit_delta_pct != null ? (p.dg_course_fit_delta_pct >= 0 ? GREEN : RED) : MUTED }}>
                    {p.dg_course_fit_delta_pct != null
                      ? `${p.dg_course_fit_delta_pct >= 0 ? "+" : ""}${(p.dg_course_fit_delta_pct * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                </>}

                {view === "form" && <>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)",
                      color: (p.form_trend ?? 0) > 0.2 ? GREEN : (p.form_trend ?? 0) < -0.1 ? RED : MUTED }}>
                    {p.form_trend != null ? `${p.form_trend >= 0 ? "+" : ""}${p.form_trend.toFixed(2)}` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: (p.consecutive_cuts ?? 0) >= 5 ? GREEN : TEXT, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.consecutive_cuts ?? "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.recent_top10s != null ? p.recent_top10s.toFixed(1) : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: p.recent_wins ? GOLD : MUTED, fontWeight: p.recent_wins ? 700 : 400, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.recent_wins ?? 0}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: (p.consecutive_top10s ?? 0) >= 2 ? GREEN : MUTED, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.consecutive_top10s ?? 0}
                  </td>
                </>}

                {view === "dg" && <>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {p.dg_win != null ? `${(p.dg_win * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GREEN, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.dg_top10 != null ? `${(p.dg_top10 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GREEN, fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.top10_prob != null ? `${(p.top10_prob * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 600, fontSize: "max(var(--fs-min), 0.85em)",
                      color: p.dg_course_fit_delta_pct != null ? (p.dg_course_fit_delta_pct >= 0 ? GREEN : RED) : MUTED }}>
                    {p.dg_course_fit_delta_pct != null
                      ? `${p.dg_course_fit_delta_pct >= 0 ? "+" : ""}${(p.dg_course_fit_delta_pct * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                </>}
              </tr>
            );})}
          </tbody>
        </table>
      </div>
    </>
  );
}
