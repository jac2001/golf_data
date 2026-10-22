"use client";

/** Stats tab: the field's season, course, form and DataGolf numbers in one sortable table.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { FieldStatsPlayer, getFieldStats } from "@/lib/api";
import { GOLD, BORDER, CARD_BG, GREEN, MUTED, RED, TEXT, card, normName, rankColor, tint, Notice } from "./shared";
import Term from "@/components/Term";
import { COLUMN_HELP } from "@/lib/columnHelp";
import styles from "./players.module.css";


// ── Stats tab ─────────────────────────────────────────────────────────────────

type StatsView = "sg" | "course" | "form" | "dg";


const VIEWS: { key: StatsView; label: string }[] = [
  { key: "sg",     label: "SG Breakdown" },
  { key: "course", label: "At this course" },   // course history, not fit (audit #21)
  { key: "form",   label: "Form" },
  { key: "dg",     label: "DG Model" },
];

// Plain labels for the phone sort picker (column headers are too small to tap).
const SORT_COLS: Record<StatsView, [keyof FieldStatsPlayer, string][]> = {
  sg:     [["season_sg_total", "SG total"], ["season_sg_ott", "Off the tee"], ["season_sg_app", "Approach"],
           ["season_sg_arg", "Around the green"], ["season_sg_putt", "Putting"]],
  course: [["course_sg_total_avg", "SG avg here"], ["course_sg_starts", "Starts"], ["course_made_cut_rate", "Cut %"],
           ["course_win_rate", "Win %"], ["dg_course_fit_delta_pct", "Fit effect"]],
  form:   [["form_trend", "Form"], ["consecutive_cuts", "Consecutive cuts"], ["recent_top10s", "Recent top 10s"],
           ["recent_wins", "Recent wins"], ["consecutive_top10s", "Consecutive top 10s"]],
  dg:     [["dg_win", "DG win %"], ["win_prob", "Our win %"], ["dg_top10", "DG top 10 %"],
           ["top10_prob", "Our top 10 %"], ["dg_course_fit_delta_pct", "Fit effect"]],
};


export function StatsTab({ myPicks = [] }: { myPicks?: string[] }) {
  const myPicksNorm = useMemo(() => new Set(myPicks.map(normName)), [myPicks]);

  const [view, setView]     = useState<StatsView>("sg");
  const [players, setPlayers] = useState<FieldStatsPlayer[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortCol, setSortCol] = useState<keyof FieldStatsPlayer>("season_sg_total");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");

  const [failed, setFailed] = useState(false);
  const load = () => {
    setLoading(true); setFailed(false);
    getFieldStats().then(d => setPlayers(d.players)).catch(() => setFailed(true)).finally(() => setLoading(false));
  };
  useEffect(load, []);

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

  const th = (col: keyof FieldStatsPlayer, label: React.ReactNode, align: "left" | "center" = "center") => (
    <th
      key={col as string}
      className={col === "player_name" ? styles.pin : undefined}
      onClick={() => handleSort(col)}
      style={{
        padding: "7px 10px", background: "var(--bc-panel)", cursor: "pointer", userSelect: "none",
        textAlign: align, fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700, letterSpacing: "0.05em",
        textTransform: "uppercase", whiteSpace: "nowrap",
        color: sortCol === col ? GREEN : MUTED,
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

  if (loading) return <Notice kind="loading">Loading the field&apos;s stats…</Notice>;
  if (failed || !players) return <Notice kind="error" onRetry={load}>Couldn&apos;t load the field&apos;s stats.</Notice>;

  return (
    <>
      <input
        className={styles.search}
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
              background: view === v.key ? tint(GREEN, 13) : "transparent",
              border: `1px solid ${view === v.key ? GREEN : BORDER}`,
              borderRadius: 6, color: view === v.key ? GREEN : MUTED,
              padding: "5px 14px", fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 600, cursor: "pointer",
            }}
          >
            {v.label}
          </button>
        ))}
        <span className={styles.clickHint} style={{ marginLeft: "auto", fontSize: "max(var(--fs-min), 0.75em)", color: MUTED, alignSelf: "center" }}>
          {sorted.length} players · click column to sort
        </span>
      </div>

      <div className={styles.sortPicker}>
        <label htmlFor="stats-sort" style={{ fontSize: "max(var(--fs-min), 0.8em)", color: MUTED }}>Sort by</label>
        <select
          id="stats-sort"
          value={sortCol as string}
          onChange={e => { setSortCol(e.target.value as keyof FieldStatsPlayer); setSortDir("desc"); }}
          style={{ background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 6, color: TEXT, padding: "6px 8px", flex: 1 }}
        >
          {SORT_COLS[view].map(([col, label]) => <option key={col as string} value={col as string}>{label}</option>)}
        </select>
        <button
          onClick={() => setSortDir(d => d === "desc" ? "asc" : "desc")}
          aria-label={sortDir === "desc" ? "Highest first; tap for lowest first" : "Lowest first; tap for highest first"}
          style={{ background: "transparent", border: `1px solid ${BORDER}`, borderRadius: 6, color: TEXT, padding: "6px 10px" }}
        >
          {sortDir === "desc" ? "↓" : "↑"}
        </button>
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        <table className={styles.wide} style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
          <thead>
            <tr>
              <th className={styles.phoneHide} style={{ padding: "7px 10px", background: "var(--bc-panel)", textAlign: "center", fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED, borderBottom: `1px solid ${BORDER}`, width: 36 }}>#</th>
              {th("player_name", "Player", "left")}

              {view === "sg" && <>
                {th("season_sg_total",         <Term term="SG">Total</Term>)}
                {th("season_sg_ott",           <Term term="OTT">OTT</Term>)}
                {th("season_sg_app",           <Term term="APP">APP</Term>)}
                {th("season_sg_arg",           <Term term="ARG">ARG</Term>)}
                {th("season_sg_putt",          <Term term="PUTT">Putt</Term>)}
              </>}

              {view === "course" && <>
                {th("course_sg_total_avg",  "SG Avg")}
                {th("course_sg_starts",     "Starts")}
                {th("course_made_cut_rate", "Cut%")}
                {th("course_win_rate",      "Win%")}
                {th("dg_course_fit_delta_pct", "Fit effect on win %")}
              </>}

              {view === "form" && <>
                {th("form_trend",       <Term help={COLUMN_HELP.form}>Form</Term>)}
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
                {th("dg_course_fit_delta_pct", "Fit effect on win %")}
              </>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => {
              const isPick = myPicksNorm.has(normName(p.player_name));
              return (
              <tr key={p.player_name} style={isPick ? { background: "var(--bc-panel)" } : undefined}>
                <td className={styles.phoneHide} style={{ ...tdStyle(i), textAlign: "center", color: MUTED, fontSize: "max(var(--fs-min), 0.75em)", ...(isPick ? { background: "var(--bc-panel)" } : {}) }}>{i + 1}</td>
                <td className={styles.pin} style={{ ...tdStyle(i), fontSize: "max(var(--fs-min), 0.85em)", fontWeight: 600, whiteSpace: "nowrap", borderLeft: isPick ? "2px solid var(--bc-green)" : undefined, ...(isPick ? { background: "var(--bc-panel)" } : {}) }}>
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
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GOLD, fontSize: "max(var(--fs-min), 0.85em)" }}>
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
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GOLD, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {p.dg_win != null ? `${(p.dg_win * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GREEN, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GOLD, fontSize: "max(var(--fs-min), 0.85em)" }}>
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
