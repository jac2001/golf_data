"use client";

/** Profiles tab: player lookup, AI synopsis, and the profile (sections chosen by lib/profileSections).
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { PlayerApproachSkill, PlayerCareer, PlayerDecompositions, PlayerProfile, PlayerSkillRatings, PlayerSynopsis, RoundStat, getOpenEvents, getPlayerCareer, getPlayerProfile, getPlayerSynopsis, getTournamentLeaderboard } from "@/lib/api";
import { hasAny, presentFields, type FieldSpec } from "@/lib/presentFields";
import { profileSections, type Section } from "@/lib/profileSections";
import { AdjBar, BG, GOLD, BORDER, Chip, GREEN, MUTED, RED, TEXT, card, fmt, fmtMoney, fmtOdds, fmtPct, fmtSg, isMajor, normName, parseCourseHistory, parseRecentResults, posColor, sectionLabel, sgColor, toParColor, tint, Notice } from "./shared";
import { FieldBrowser, PlayerSelect } from "./PlayerPicker";
import styles from "./players.module.css";


// ── Synopsis card ─────────────────────────────────────────────────────────────

const SECTION_META: { key: keyof PlayerSynopsis["sections"]; label: string; color: string }[] = [
  { key: "form",          label: "Form",          color: GREEN },
  { key: "course_fit",    label: "Course fit",    color: GOLD  },
  { key: "betting_angle", label: "Betting Angle", color: GOLD  },
  { key: "fantasy",       label: "Fantasy",       color: "var(--bc-orange)" },
];


function SynopsisCard({
  synopsis,
  loading,
  error,
  onGenerate,
  onRegenerate,
  hasProfile,
}: {
  synopsis: PlayerSynopsis | null;
  loading: boolean;
  error: string | null;
  onGenerate: () => void;
  onRegenerate: () => void;
  hasProfile: boolean;
}) {
  if (!hasProfile) return null;

  if (!synopsis && !loading && !error) {
    return (
      <div style={{
        ...card,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--bc-panel)", border: `1px dashed ${BORDER}`,
      }}>
        <div>
          <div style={{ fontSize: "max(var(--fs-min), 0.88em)", color: TEXT, fontWeight: 600, marginBottom: 2 }}>
            AI Player Analysis
          </div>
          <div style={{ fontSize: "max(var(--fs-min), 0.75em)", color: MUTED }}>
            Generate a synopsis using form, course fit, and betting context.
          </div>
        </div>
        <button
          onClick={onGenerate}
          style={{
            background: tint(GREEN, 13), border: `1px solid ${tint(GREEN, 27)}`,
            color: GREEN, borderRadius: 8, padding: "8px 18px",
            fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 700, cursor: "pointer", flexShrink: 0,
          }}
        >
          Generate Analysis
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ ...card, background: "var(--bc-panel)", border: `1px dashed ${BORDER}`, textAlign: "center", padding: "28px 20px" }}>
        <div style={{ fontSize: "max(var(--fs-min), 0.85em)", color: MUTED }}>Generating analysis…</div>
        <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: MUTED, marginTop: 4 }}>
          Gathering stats and asking Claude for a take
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ ...card, background: "#1a0808", border: `1px solid ${tint(RED, 27)}` }}>
        <div style={{ fontSize: "max(var(--fs-min), 0.82em)", color: RED }}>{error}</div>
        <button onClick={onGenerate} style={{ marginTop: 8, fontSize: "max(var(--fs-min), 0.78em)", color: MUTED, background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
          Try again
        </button>
      </div>
    );
  }

  if (!synopsis) return null;

  const ts = synopsis.generated_ts ? new Date(synopsis.generated_ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div style={{ ...card, background: "var(--bc-panel)", border: `1px solid var(--bc-line)`, marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <span style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>
            AI Analysis
          </span>
          <span style={{ fontSize: "max(var(--fs-min-xs), 0.65em)", color: MUTED, marginLeft: 8 }}>
            {synopsis.tournament_name} · {synopsis.course_name}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {synopsis.cached && (
            <span style={{ fontSize: "max(var(--fs-min-xs), 0.65em)", color: MUTED }}>cached {ts}</span>
          )}
          <button
            onClick={onRegenerate}
            style={{
              background: "none", border: `1px solid ${BORDER}`,
              color: MUTED, borderRadius: 6, padding: "3px 10px",
              fontSize: "max(var(--fs-min), 0.72em)", cursor: "pointer",
            }}
          >
            Regenerate
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {SECTION_META.map(({ key, label, color }) => {
          const text = synopsis.sections[key];
          if (!text) return null;
          return (
            <div key={key} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <span style={{
                fontSize: "max(var(--fs-min-xs), 0.65em)", fontWeight: 800, color,
                textTransform: "uppercase", letterSpacing: "0.1em",
                background: tint(color, 9), border: `1px solid ${tint(color, 20)}`,
                borderRadius: 4, padding: "2px 7px", flexShrink: 0, marginTop: 2,
                minWidth: 80, textAlign: "center",
              }}>
                {label}
              </span>
              <p style={{ margin: 0, fontSize: "max(var(--fs-min), 0.85em)", color: TEXT, lineHeight: 1.65 }}>
                {text}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Lookup tab ────────────────────────────────────────────────────────────────

export function LookupTab({ players, defaultPlayer }: { players: string[]; defaultPlayer?: string }) {
  const [selected, setSelected]         = useState(defaultPlayer ?? "");
  const [profile, setProfile]           = useState<PlayerProfile | null>(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState<string | null>(null);

  const [synopsis, setSynopsis]         = useState<PlayerSynopsis | null>(null);
  const [synopsisLoading, setSynopsisLoading] = useState(false);
  const [synopsisError, setSynopsisError]     = useState<string | null>(null);

  const fetchProfile = useCallback((name: string) => {
    if (!name) return;
    setLoading(true);
    setError(null);
    setProfile(null);
    setSynopsis(null);
    setSynopsisError(null);
    getPlayerProfile(name)
      .then(setProfile)
      .catch(() => setError(name))   // the name, so Try again can reload it
      .finally(() => setLoading(false));
  }, []);

  // Auto-load when arriving from a deep link (e.g. ?player=Name)
  useEffect(() => {
    if (defaultPlayer) fetchProfile(defaultPlayer);
  }, [defaultPlayer, fetchProfile]);

  function handleSelect(name: string) {
    setSelected(name);
    fetchProfile(name);
  }

  function fetchSynopsis(force = false) {
    if (!selected) return;
    setSynopsisLoading(true);
    setSynopsisError(null);
    getPlayerSynopsis(selected, force)
      .then(setSynopsis)
      .catch(e => setSynopsisError(e.message ?? "Failed to generate analysis."))
      .finally(() => setSynopsisLoading(false));
  }

  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <PlayerSelect players={players} value={selected} onChange={handleSelect} id="lookup" placeholder="Search player…" />
      </div>

      {error && <Notice kind="error" onRetry={() => fetchProfile(error)}>Couldn&apos;t load {error}&apos;s profile.</Notice>}
      {loading && <Notice kind="loading">Loading profile…</Notice>}

      {!profile && !loading && <FieldBrowser onPick={handleSelect} />}

      {profile && !loading && (
        <>
          <SynopsisCard
            synopsis={synopsis}
            loading={synopsisLoading}
            error={synopsisError}
            onGenerate={() => fetchSynopsis(false)}
            onRegenerate={() => fetchSynopsis(true)}
            hasProfile={true}
          />
          <ProfileView profile={profile} />
        </>
      )}
    </>
  );
}


// ── Per-round SG breakdown (shown in expanded Recent Starts row) ──────────────

function RoundBreakdownPanel({ rounds }: { rounds: RoundStat[] }) {
  const BG    = "var(--bc-panel)";
  const CELL  = "var(--bc-panel)";
  const BORD  = "var(--bc-line)";
  const MUT   = "var(--bc-muted)";
  const GRN   = "var(--bc-green)";
  const RED   = "var(--negative)";
  const GOLD  = "var(--bc-yellow)";

  function sgColor(v: number | null) {
    if (v == null) return MUT;
    return v >= 0 ? GRN : RED;
  }

  function fmtSg(v: number | null) {
    if (v == null) return "—";
    return v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
  }

  function fmtScore(score: number | null, par: number | null) {
    if (score == null) return "—";
    if (par == null) return String(score);
    const diff = score - par;
    const sign = diff > 0 ? "+" : diff < 0 ? "" : "E";
    const label = diff === 0 ? "E" : `${sign}${diff}`;
    return `${score} (${label})`;
  }

  const th: React.CSSProperties = {
    padding: "5px 10px", fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700,
    color: MUT, textTransform: "uppercase", letterSpacing: "0.05em",
    background: BG, textAlign: "center", whiteSpace: "nowrap",
    borderBottom: `1px solid ${BORD}`,
  };
  const label: React.CSSProperties = {
    padding: "5px 10px", fontSize: "max(var(--fs-min), 0.75em)", color: MUT,
    background: BG, borderRight: `1px solid ${BORD}`,
    borderBottom: `1px solid ${BORD}`, whiteSpace: "nowrap",
  };
  function cell(i: number): React.CSSProperties {
    return {
      padding: "5px 10px", fontSize: "max(var(--fs-min), 0.8em)", textAlign: "center",
      background: i % 2 === 0 ? CELL : "var(--bc-panel)",
      borderBottom: `1px solid ${BORD}`,
    };
  }

  const rows: { key: string; label: string; fmt: (r: RoundStat) => React.ReactNode }[] = [
    { key: "score",    label: "Score",    fmt: r => <span style={{ color: "var(--bc-text)", fontWeight: 700 }}>{fmtScore(r.score, r.course_par)}</span> },
    { key: "sg_total", label: "SG Total", fmt: r => <span style={{ color: sgColor(r.sg_total), fontWeight: 700 }}>{fmtSg(r.sg_total)}</span> },
    { key: "sg_ott",   label: "SG OTT",   fmt: r => <span style={{ color: sgColor(r.sg_ott) }}>{fmtSg(r.sg_ott)}</span> },
    { key: "sg_app",   label: "SG APP",   fmt: r => <span style={{ color: sgColor(r.sg_app) }}>{fmtSg(r.sg_app)}</span> },
    { key: "sg_arg",   label: "SG ARG",   fmt: r => <span style={{ color: sgColor(r.sg_arg) }}>{fmtSg(r.sg_arg)}</span> },
    { key: "sg_putt",  label: "SG Putt",  fmt: r => <span style={{ color: sgColor(r.sg_putt) }}>{fmtSg(r.sg_putt)}</span> },
    { key: "birdies",  label: "Birdies",  fmt: r => <span style={{ color: r.birdies ? GRN : MUT }}>{r.birdies || "—"}</span> },
    { key: "bogies",   label: "Bogies",   fmt: r => <span style={{ color: r.bogies ? RED : MUT }}>{r.bogies || "—"}</span> },
    { key: "eagles",   label: "Eagles",   fmt: r => <span style={{ color: r.eagles_or_better ? GOLD : MUT }}>{r.eagles_or_better || "—"}</span> },
    { key: "dist",     label: "Drive",    fmt: r => <span style={{ color: MUT }}>{r.driving_dist != null ? `${r.driving_dist.toFixed(0)} yds` : "—"}</span> },
    { key: "prox_fw",  label: "Proximity (fairway)",  fmt: r => <span style={{ color: MUT }}>{r.prox_fw != null ? `${r.prox_fw.toFixed(1)} ft` : "—"}</span> },
  ];

  return (
    <div style={{ marginBottom: 14 }}>
      <p style={{ fontSize: "max(var(--fs-min), 0.7em)", color: MUT, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
        Round-by-Round Breakdown
      </p>
      <div style={{ overflowX: "auto", border: `1px solid ${BORD}`, borderRadius: 8 }}>
        <table className={styles.wide} style={{ borderCollapse: "collapse", background: BG }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "left", minWidth: 80 }}></th>
              {rounds.map(r => (
                <th key={r.round_num} style={{ ...th, minWidth: 120 }}>Round {r.round_num}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.key}>
                <td style={{ ...label, background: i % 2 === 0 ? CELL : "var(--bc-panel)" }}>{row.label}</td>
                {rounds.map(r => (
                  <td key={r.round_num} style={cell(i)}>{row.fmt(r)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// Inline leaderboard for an expanded tournament row in Recent Starts
function TournamentResultsPanel({ tid, highlightPlayer }: { tid: string; highlightPlayer: string }) {
  const [rows, setRows]   = useState<import("@/lib/api").TournamentLeaderboardRow[] | null>(null);
  const [error, setError] = useState(false);
  const highlightKey      = normName(highlightPlayer);

  useEffect(() => {
    getTournamentLeaderboard(tid)
      .then(setRows)
      .catch(() => setError(true));
  }, [tid]);

  if (error) return <Notice kind="error">Couldn&apos;t load this event&apos;s leaderboard.</Notice>;
  if (!rows)  return <Notice kind="loading">Loading leaderboard…</Notice>;

  const hasEarnings = rows.some(r => r.earnings != null);
  const hasSg = rows.some(r => r.sg_total != null);
  const sgColor3 = (v: number | null) => v == null ? MUTED : v >= 0 ? GREEN : RED;
  const fmtSg3 = (v: number | null) => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
  const fmtPct3 = (v: number | null) => v == null ? "—" : `${v.toFixed(0)}%`;

  const thS: React.CSSProperties = {
    padding: "5px 8px", background: "var(--bc-panel)", fontSize: "max(var(--fs-min-xs), 0.67em)", fontWeight: 700,
    color: MUTED, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${BORDER}`,
  };
  const tdS = (isPick: boolean, i: number): React.CSSProperties => ({
    padding: "4px 8px", fontSize: "max(var(--fs-min), 0.8em)",
    borderBottom: "1px solid var(--bc-card)",
    background: isPick ? "var(--bc-panel)" : i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-card)",
  });

  return (
    <div style={{ overflowX: "auto", borderRadius: 6, border: `1px solid ${BORDER}`, marginTop: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...thS, textAlign: "left", width: 40 }}>Pos</th>
            <th style={{ ...thS, textAlign: "left" }}>Player</th>
            <th style={{ ...thS, textAlign: "center" }}>R1</th>
            <th style={{ ...thS, textAlign: "center" }}>R2</th>
            <th style={{ ...thS, textAlign: "center" }}>R3</th>
            <th style={{ ...thS, textAlign: "center" }}>R4</th>
            <th style={{ ...thS, textAlign: "center" }}>Total</th>
            {hasSg && (
              <>
                <th style={{ ...thS, textAlign: "center" }}>SG Tot</th>
                <th style={{ ...thS, textAlign: "center" }}>OTT</th>
                <th style={{ ...thS, textAlign: "center" }}>APP</th>
                <th style={{ ...thS, textAlign: "center" }}>ARG</th>
                <th style={{ ...thS, textAlign: "center" }}>Putt</th>
                <th style={{ ...thS, textAlign: "center" }}>Dist</th>
                <th style={{ ...thS, textAlign: "center" }}>Acc%</th>
                <th style={{ ...thS, textAlign: "center" }}>GIR%</th>
                <th style={{ ...thS, textAlign: "center" }}>Scrmb%</th>
              </>
            )}
            {hasEarnings && <th style={{ ...thS, textAlign: "right" }}>Earnings</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isPick = normName(r.player_name) === highlightKey;
            return (
              <tr key={i}>
                <td style={{ ...tdS(isPick, i), fontWeight: 700, color: posColor(r.position, TEXT), borderLeft: isPick ? "2px solid var(--bc-green)" : undefined }}>
                  {r.position}
                </td>
                <td style={{ ...tdS(isPick, i), whiteSpace: "nowrap" }}>
                  <Link href={`/players?player=${encodeURIComponent(r.player_name)}`}
                    onClick={e => e.stopPropagation()}
                    style={{ color: isPick ? GREEN : TEXT, textDecoration: "none", fontWeight: isPick ? 700 : 400 }}>
                    {r.player_name}
                  </Link>
                </td>
                <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{r.r1 ?? "—"}</td>
                <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{r.r2 ?? "—"}</td>
                <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{r.r3 ?? "—"}</td>
                <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{r.r4 ?? "—"}</td>
                <td style={{ ...tdS(isPick, i), textAlign: "center", fontWeight: 600, color: toParColor(r.to_par) }}>
                  {r.to_par || "—"}
                </td>
                {hasSg && (
                  <>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", fontWeight: 700, color: sgColor3(r.sg_total) }}>{fmtSg3(r.sg_total)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: sgColor3(r.sg_ott) }}>{fmtSg3(r.sg_ott)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: sgColor3(r.sg_app) }}>{fmtSg3(r.sg_app)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: sgColor3(r.sg_arg) }}>{fmtSg3(r.sg_arg)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: sgColor3(r.sg_putt) }}>{fmtSg3(r.sg_putt)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{r.driving_dist != null ? r.driving_dist.toFixed(0) : "—"}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{fmtPct3(r.driving_acc)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{fmtPct3(r.gir_pct)}</td>
                    <td style={{ ...tdS(isPick, i), textAlign: "center", color: MUTED }}>{fmtPct3(r.scrambling)}</td>
                  </>
                )}
                {hasEarnings && (
                  <td style={{ ...tdS(isPick, i), textAlign: "right", color: MUTED, fontSize: "max(var(--fs-min), 0.75em)" }}>
                    {r.earnings ?? "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


function CareerCard({ playerName }: { playerName: string }) {
  const [career, setCareer]       = useState<PlayerCareer | null>(null);
  const [loading, setLoading]     = useState(false);
  const [loaded, setLoaded]       = useState(false);
  const [view, setView]           = useState<"recent" | "yearly">("yearly");
  const [majorsOnly, setMajorsOnly] = useState(false);
  const [careerFailed, setCareerFailed] = useState(false);
  // tracks which tournament row is expanded in Recent Starts, and which tab is active
  const [expandedTid, setExpandedTid] = useState<string | null>(null);
  const [expandedTab, setExpandedTab] = useState<"rounds" | "leaderboard">("rounds");

  function load() {
    setLoading(true);
    setCareerFailed(false);
    getPlayerCareer(playerName)
      .then(d => { setCareer(d); setLoaded(true); })
      .catch(() => setCareerFailed(true))   // was: marked loaded with no data, so the card showed nothing
      .finally(() => setLoading(false));
  }

  const thStyle: React.CSSProperties = {
    padding: "6px 10px", background: "var(--bc-panel)", fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700,
    color: MUTED, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${BORDER}`, whiteSpace: "nowrap",
  };
  const tdBase = (i: number): React.CSSProperties => ({
    padding: "5px 10px", borderBottom: `1px solid var(--bc-card)`, fontSize: "max(var(--fs-min), 0.83em)",
    background: i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)",
  });

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <p style={{ ...sectionLabel, margin: 0 }}>Career stats (events in our results)</p>
        {!loaded && !loading && (
          <button onClick={load} style={{
            background: tint(GOLD, 13), border: `1px solid ${tint(GOLD, 27)}`,
            color: GOLD, borderRadius: 7, padding: "5px 14px",
            fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700, cursor: "pointer",
          }}>
            Load Career Stats
          </button>
        )}
        {loaded && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(["yearly", "recent"] as const).map(v => (
              <button key={v} onClick={() => { setView(v); if (v !== "recent") setMajorsOnly(false); }} style={{
                background: view === v ? tint(GREEN, 13) : "transparent",
                border: `1px solid ${view === v ? GREEN : BORDER}`,
                borderRadius: 6, color: view === v ? GREEN : MUTED,
                padding: "4px 12px", fontSize: "max(var(--fs-min), 0.75em)", fontWeight: 600, cursor: "pointer",
              }}>
                {v === "yearly" ? "By Year" : "Recent Starts"}
              </button>
            ))}
            {view === "recent" && (
              <button onClick={() => setMajorsOnly(m => !m)} style={{
                background: majorsOnly ? tint(GOLD, 13) : "transparent",
                border: `1px solid ${majorsOnly ? GOLD : BORDER}`,
                borderRadius: 6, color: majorsOnly ? GOLD : MUTED,
                padding: "4px 12px", fontSize: "max(var(--fs-min), 0.75em)", fontWeight: 600, cursor: "pointer",
              }}>
                Majors Only
              </button>
            )}
          </div>
        )}
      </div>
      {careerFailed && <Notice kind="error" onRetry={load}>Couldn&apos;t load career stats.</Notice>}

      {loading && <Notice kind="loading">Loading career stats…</Notice>}

      {/* ── By Year view ─────────────────────────────────────────────────── */}
      {loaded && career && view === "yearly" && (
        <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${BORDER}` }}>
          <table className={styles.wide} style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
            <thead>
              <tr>
                {[
                  ["Year", "left"], ["Events", "center"], ["Wins", "center"],
                  ["Top 10", "center"], ["Top 25", "center"], ["Cuts", "center"],
                  ["Avg Score", "center"], ["SG Tot", "center"],
                  ["SG OTT", "center"], ["SG APP", "center"], ["SG ARG", "center"], ["SG Putt", "center"],
                  ["Dist", "center"], ["Acc%", "center"], ["GIR%", "center"], ["Scrmb%", "center"],
                ].map(([h, align]) => (
                  <th key={h} style={{ ...thStyle, textAlign: align as "left" | "center" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {career.by_year.map((y, i) => (
                <tr key={y.year} style={{ background: i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)" }}>
                  <td style={{ ...tdBase(i), fontWeight: 700, color: TEXT }}>{y.year}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{y.starts}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", fontWeight: y.wins > 0 ? 800 : 400, color: y.wins > 0 ? GOLD : MUTED }}>
                    {y.wins || "—"}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: y.top10s > 0 ? GREEN : MUTED }}>{y.top10s || "—"}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{y.top25s || "—"}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{y.cuts_made}/{y.starts}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                    {y.avg_scoring != null ? y.avg_scoring.toFixed(1) : "—"}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: sgColor(y.avg_sg_total) }}>
                    {fmtSg(y.avg_sg_total)}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(y.avg_sg_ott) }}>{fmtSg(y.avg_sg_ott)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(y.avg_sg_app) }}>{fmtSg(y.avg_sg_app)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(y.avg_sg_arg) }}>{fmtSg(y.avg_sg_arg)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(y.avg_sg_putt) }}>{fmtSg(y.avg_sg_putt)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                    {y.avg_driving_dist != null ? y.avg_driving_dist.toFixed(0) : "—"}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                    {y.avg_driving_acc != null ? `${y.avg_driving_acc.toFixed(0)}%` : "—"}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                    {y.avg_gir_pct != null ? `${y.avg_gir_pct.toFixed(0)}%` : "—"}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                    {y.avg_scrambling != null ? `${y.avg_scrambling.toFixed(0)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Recent Starts view ───────────────────────────────────────────── */}
      {loaded && career && view === "recent" && (
        <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${BORDER}` }}>
          <table className={styles.wide} style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
            <thead>
              <tr>
                {[
                  ["Tournament", "left"], ["Year", "left"], ["Pos", "center"],
                  ["Score", "center"], ["R1", "center"], ["R2", "center"], ["R3", "center"], ["R4", "center"],
                  ["SG Tot", "center"], ["OTT", "center"],
                  ["APP", "center"], ["ARG", "center"], ["Putt", "center"],
                  ["Dist", "center"], ["Acc%", "center"], ["GIR%", "center"], ["Scrmb%", "center"],
                  // Earnings only when some start has them (2026 has none yet: audit #15).
                  ...(hasAny(career.recent, "earnings") ? [["Earnings", "right"]] : []),
                ].map(([h, align]) => (
                  <th key={h} style={{ ...thStyle, textAlign: align as "left" | "center" | "right" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {career.recent.filter(r => !majorsOnly || isMajor(r.tournament_name)).map((r, i) => {
                const isExpanded = expandedTid === r.tournament_id;
                // Only show tournament leaderboard if we have a settled tournament ID
                // (IDs starting with R and year <= current — not future events)
                const canExpand = !!r.tournament_id;
                return (
                  <React.Fragment key={`${r.tournament_id}-${i}`}>
                    <tr
                      onClick={() => {
                        if (!canExpand) return;
                        if (isExpanded) {
                          setExpandedTid(null);
                        } else {
                          setExpandedTid(r.tournament_id);
                          setExpandedTab(r.rounds.length > 0 ? "rounds" : "leaderboard");
                        }
                      }}
                      style={{ cursor: canExpand ? "pointer" : "default", background: i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)" }}
                    >
                      <td style={{ ...tdBase(i), maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: TEXT }}>{r.tournament_name}</span>
                          {canExpand && (
                            <span style={{ fontSize: "max(var(--fs-min), 0.7em)", color: isExpanded ? GOLD : "var(--bc-line)" }}>
                              {isExpanded ? "▲" : "▼"}
                            </span>
                          )}
                        </span>
                      </td>
                      <td style={{ ...tdBase(i), color: MUTED }}>{r.year}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 700, color: posColor(r.position, TEXT) }}>
                        {r.position}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: toParColor(r.to_par) }}>
                        {r.to_par ?? "—"}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{r.r1 ?? "—"}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{r.r2 ?? "—"}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{r.r3 ?? "—"}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>{r.r4 ?? "—"}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: sgColor(r.sg_total) }}>
                        {fmtSg(r.sg_total)}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(r.sg_ott) }}>{fmtSg(r.sg_ott)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(r.sg_app) }}>{fmtSg(r.sg_app)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(r.sg_arg) }}>{fmtSg(r.sg_arg)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor(r.sg_putt) }}>{fmtSg(r.sg_putt)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                        {r.driving_dist != null ? r.driving_dist.toFixed(0) : "—"}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                        {r.driving_acc != null ? `${r.driving_acc.toFixed(0)}%` : "—"}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                        {r.gir_pct != null ? `${r.gir_pct.toFixed(0)}%` : "—"}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: MUTED }}>
                        {r.scrambling != null ? `${r.scrambling.toFixed(0)}%` : "—"}
                      </td>
                      {hasAny(career.recent, "earnings") && (
                        <td style={{ ...tdBase(i), textAlign: "right", color: MUTED, fontSize: "max(var(--fs-min), 0.78em)" }}>
                          {fmtMoney(r.earnings)}
                        </td>
                      )}
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={18} style={{ background: "var(--bc-panel)", padding: "12px 16px", borderBottom: "1px solid var(--bc-card)" }}>
                          {/* Tab bar */}
                          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                            {r.rounds.length > 0 && (
                              <button
                                onClick={e => { e.stopPropagation(); setExpandedTab("rounds"); }}
                                style={{
                                  background: expandedTab === "rounds" ? "var(--bc-card)" : "transparent",
                                  border: `1px solid ${expandedTab === "rounds" ? GREEN : "var(--bc-line)"}`,
                                  color: expandedTab === "rounds" ? GREEN : "var(--bc-muted)",
                                  borderRadius: 6, padding: "4px 14px",
                                  fontSize: "max(var(--fs-min), 0.75em)", fontWeight: 600, cursor: "pointer",
                                }}>
                                My Rounds
                              </button>
                            )}
                            <button
                              onClick={e => { e.stopPropagation(); setExpandedTab("leaderboard"); }}
                              style={{
                                background: expandedTab === "leaderboard" ? "var(--bc-card)" : "transparent",
                                border: `1px solid ${expandedTab === "leaderboard" ? GOLD : "var(--bc-line)"}`,
                                color: expandedTab === "leaderboard" ? GOLD : "var(--bc-muted)",
                                borderRadius: 6, padding: "4px 14px",
                                fontSize: "max(var(--fs-min), 0.75em)", fontWeight: 600, cursor: "pointer",
                              }}>
                              Leaderboard
                            </button>
                          </div>
                          {/* Tab content */}
                          {expandedTab === "rounds" && r.rounds.length > 0 && (
                            <RoundBreakdownPanel rounds={r.rounds} />
                          )}
                          {expandedTab === "leaderboard" && (
                            <TournamentResultsPanel tid={r.tournament_id} highlightPlayer={playerName} />
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
      )}

      {loaded && !loading && (!career || (!career.recent.length && !career.by_year.length)) && (
        <p style={{ color: MUTED, fontSize: "max(var(--fs-min), 0.83em)" }}>No career data found.</p>
      )}
    </div>
  );
}


// ── Profile view ──────────────────────────────────────────────────────────────

function ProfileView({ profile }: { profile: PlayerProfile }) {
  const m = profile.our_model;

  // Which cards show, and in what order: Jack's profileSections (#12). A
  // golfer not in this week's field gets a note, not cards of dashes.
  const [eventName, setEventName] = useState<string | null>(null);
  useEffect(() => {
    getOpenEvents().then(d => setEventName(d.events?.find(e =>
      e.tournament_id.toUpperCase() === String(profile.tournament_id ?? "").toUpperCase())?.name ?? null)).catch(() => {});
  }, [profile.tournament_id]);
  const plan = profileSections(profile, eventName);

  const cards: Record<Section, React.ReactNode> = {
    thisWeek: <>
      {/* Section 2: Our Model */}
      <div style={card}>
        <p style={sectionLabel}>Our Model</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <Chip label="Win%" value={fmtPct(m.win_prob)} />
          <Chip label="Top 10%" value={fmtPct(m.top10_prob)} />
          <Chip label="Cut%" value={fmtPct(m.cut_prob)} />
          <Chip label="Season SG" value={fmt(m.season_sg_total, 2)} color={sgColor(m.season_sg_total)} />
          {m.odds_to_win != null && (
            <Chip label="Odds (DataGolf)" value={fmtOdds(m.odds_to_win)} />
          )}
          {m.model_vs_vegas_edge != null && (
            // The API sends a fraction (0.037); shown in percentage points (+3.7pp).
            <Chip label="Our edge" value={`${m.model_vs_vegas_edge > 0 ? "+" : ""}${fmt(m.model_vs_vegas_edge * 100)}pp`} color={m.model_vs_vegas_edge > 0 ? GREEN : RED} />
          )}
        </div>
        {m.explanation && (
          <p style={{ fontSize: "max(var(--fs-min), 0.85em)", color: TEXT, margin: "0 0 8px 0", lineHeight: 1.5 }}>
            {m.explanation}
          </p>
        )}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
          {m.form_trend != null && (
            <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: sgColor(m.form_trend) }}>
              <span style={{ color: MUTED }}>Form </span>
              {m.form_trend > 0 ? "+" : ""}{fmt(m.form_trend, 2)}
            </span>
          )}
          {/* Move: DataGolf odds since the opening line, same meaning as This
              Week (UP = odds longer = the market cooled; DOWN = warmed to him).
              It was colored the other way round (Players audit #8). */}
          {(m.dk_odds_direction === "UP" || m.dk_odds_direction === "DOWN") && (
            <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: m.dk_odds_direction === "DOWN" ? GREEN : RED }}>
              <span style={{ color: MUTED }}>Move </span>
              {m.dk_odds_direction === "DOWN" ? "↓ odds shorter since the line opened" : "↑ odds longer since the line opened"}
            </span>
          )}
        </div>
      </div>
    </>,
    career: <>
      {/* Section 3: Career Stats */}
      <CareerCard playerName={profile.player_name} />
    </>,
    dgPrediction: <>
      {/* Section 4: DG Tournament Prediction */}
      {profile.dg_prediction && (
        <div style={card}>
          <p style={sectionLabel}>DG Tournament Prediction</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            {/* DataGolf's real prediction is the course-adjusted one (bhf);
                "win" is its baseline before course fit and history (#9). */}
            <Chip label="DG Win%"    value={fmtPct(profile.dg_prediction.bhf_win ?? profile.dg_prediction.win)} />
            <Chip label="Top 5%"     value={fmtPct(profile.dg_prediction.top_5)} />
            <Chip label="Top 10%"    value={fmtPct(profile.dg_prediction.top_10)} />
            <Chip label="Top 20%"    value={fmtPct(profile.dg_prediction.top_20)} />
            <Chip label="Make Cut%"  value={fmtPct(profile.dg_prediction.make_cut)} />
          </div>
          {/* Course fit context: baseline → adjusted */}
          {profile.dg_prediction.baseline_win != null && profile.dg_prediction.bhf_win != null && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
              background: "var(--bc-panel)", border: `1px solid ${BORDER}`, borderRadius: 8,
              padding: "10px 14px",
            }}>
              <span style={{ fontSize: "max(var(--fs-min), 0.8em)", color: MUTED }}>Before course fit and history</span>
              <span style={{ fontSize: "max(var(--fs-min), 0.88em)", color: MUTED, fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(profile.dg_prediction.baseline_win)}
              </span>
              <span style={{ fontSize: "max(var(--fs-min), 0.8em)", color: MUTED }}>→</span>
              <span style={{ fontSize: "max(var(--fs-min), 0.88em)", fontWeight: 700, color: GOLD, fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(profile.dg_prediction.bhf_win)} at this course
              </span>
              {profile.dg_prediction.course_fit_delta_pct != null && (
                <span style={{
                  fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700,
                  color: profile.dg_prediction.course_fit_delta_pct >= 0 ? GREEN : RED,
                }}>
                  ({profile.dg_prediction.course_fit_delta_pct >= 0 ? "+" : ""}
                  {(profile.dg_prediction.course_fit_delta_pct * 100).toFixed(1)}%)
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </>,
    courseFit: <>
      {/* Section 4: Course Decompositions */}
      {profile.decompositions && <DecompositionsCard dec={profile.decompositions} />}
    </>,
    skills: <>
      {/* Section 5: DG Skill Ratings */}
      {profile.skill_ratings && <SkillRatingsCard sr={profile.skill_ratings} />}
    </>,
    approach: <>
      {/* Section 6: Approach Skill */}
      {profile.approach_skill && <ApproachCard ap={profile.approach_skill} />}
    </>,
    season: <>
      {/* Section 7: Betting Profile */}
      {profile.betting_profile && <BettingProfileCard bp={profile.betting_profile} />}
    </>,
  };

  return (
    <>
      {/* Section 1: Header */}
      <div style={{ ...card, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <h1 style={{ margin: 0, fontSize: "1.6em", fontWeight: 800, letterSpacing: "-0.02em" }}>
                {profile.player_name}
              </h1>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 6 }}>
              <span style={{ fontSize: "max(var(--fs-min), 0.82em)", color: MUTED }}>
                {m.world_rank != null ? `World #${Math.round(m.world_rank)}` : "Unranked"}
              </span>
              {plan.note && <span style={{ fontSize: "max(var(--fs-min), 0.82em)", color: TEXT }}>{plan.note}</span>}
            </div>
          </div>
          {/* The chances are the headline (Jack, Oct 22), the field rank under
              each. Same simulation numbers This Week shows (api _published_chances). */}
          {plan.inField && <div style={{ display: "flex", gap: 20 }}>
            {([["Win chance", m.win_prob, m.win_rank], ["Top-10 chance", m.top10_prob, m.top10_rank]] as const).map(([lbl, v, rank]) => (
              <div key={lbl} style={{ textAlign: "center" }}>
                <div style={{ fontSize: "1.6em", fontWeight: 800, color: GREEN }}>{v != null ? fmtPct(v) : "—"}</div>
                <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED, textTransform: "uppercase" }}>{lbl}</div>
                {rank != null && <div style={{ fontSize: 12, color: MUTED }}>#{rank} in the field</div>}
              </div>
            ))}
          </div>}
        </div>
      </div>

      {plan.show.map(sec => <React.Fragment key={sec}>{cards[sec]}</React.Fragment>)}
    </>
  );
}


// ── Decompositions card ───────────────────────────────────────────────────────

const DEC_ROWS: { key: keyof PlayerDecompositions; label: string }[] = [
  // course_fit_delta = DG final_pred - baseline_pred: every adjustment, not just fit (#21)
  { key: "course_fit_delta",                   label: "All adjustments vs his baseline" },
  { key: "total_course_history_adjustment",    label: "Course History" },
  { key: "driving_distance_adjustment",        label: "Driving Distance" },
  { key: "driving_accuracy_adjustment",        label: "Driving Accuracy" },
  { key: "strokes_gained_category_adjustment", label: "SG Category" },
  { key: "timing_adjustment",                  label: "Recent form" },
  { key: "age_adjustment",                     label: "Age" },
  { key: "true_sg_adjustments",                label: "True SG Adj." },
];


const DEC_TOTAL: keyof PlayerDecompositions = "total_fit_adjustment";


function DecompositionsCard({ dec }: { dec: PlayerDecompositions }) {
  const rowValues = DEC_ROWS.map(d => dec[d.key] as number | null).filter(v => v != null) as number[];
  const totalVal  = dec[DEC_TOTAL] as number | null;
  const allVals   = totalVal != null ? [...rowValues, Math.abs(totalVal)] : rowValues;
  const maxAbs    = allVals.length ? Math.max(...allVals.map(Math.abs), 0.01) : 0.5;

  return (
    <div style={card}>
      <p style={sectionLabel}>Adjustment Breakdown</p>

      {/* Axis label */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: "max(var(--fs-min-xs), 0.65em)", color: MUTED, marginBottom: 10,
        paddingLeft: 170, paddingRight: 48,
      }}>
        <span>← negative</span>
        <span>positive →</span>
      </div>

      {DEC_ROWS.map(({ key, label }) => (
        <AdjBar key={key} label={label} value={dec[key] as number | null} maxAbs={maxAbs} />
      ))}

      {/* Total row */}
      {totalVal != null && (
        <>
          <div style={{ borderTop: `1px solid ${BORDER}`, margin: "8px 0" }} />
          <AdjBar label="Total Fit Adj." value={totalVal} maxAbs={maxAbs} />
        </>
      )}
    </div>
  );
}


// ── Skill ratings card ────────────────────────────────────────────────────────

const SR_ROWS: { key: keyof PlayerSkillRatings; label: string }[] = [
  { key: "ott",  label: "Off the Tee" },
  { key: "app",  label: "Approach" },
  { key: "arg",  label: "Around Green" },
  { key: "putt", label: "Putting" },
  { key: "acc",  label: "Accuracy SG" },
];


function SkillRatingsCard({ sr }: { sr: import("@/lib/api").PlayerSkillRatings }) {
  const rowVals = SR_ROWS.map(r => sr[r.key]).filter(v => v != null) as number[];
  const distAbs = sr.dist != null ? Math.abs(sr.dist) : 0;
  // scale the dist bar by 1/10 so it sits alongside SG values visually
  const maxAbs  = Math.max(...rowVals.map(Math.abs), distAbs / 10, 0.01);

  return (
    <div style={card}>
      <p style={sectionLabel}>DG Skill Ratings</p>

      {/* Total highlight */}
      {sr.total != null && (
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: "2em", fontWeight: 800, color: sr.total >= 0 ? GREEN : RED }}>
            {sr.total >= 0 ? "+" : ""}{sr.total.toFixed(2)}
          </span>
          <span style={{ fontSize: "max(var(--fs-min), 0.75em)", color: MUTED }}>SG / round vs field avg</span>
        </div>
      )}

      {/* Axis label */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: "max(var(--fs-min-xs), 0.65em)", color: MUTED, marginBottom: 10,
        paddingLeft: 170, paddingRight: 48,
      }}>
        <span>← negative</span>
        <span>positive →</span>
      </div>

      {SR_ROWS.map(({ key, label }) => (
        <AdjBar key={key} label={label} value={sr[key]} maxAbs={maxAbs} />
      ))}

      {/* Driving distance — different unit (yards) */}
      {sr.dist != null && (
        <>
          <div style={{ borderTop: `1px solid ${BORDER}`, margin: "8px 0" }} />
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ width: 160, fontSize: "max(var(--fs-min), 0.78em)", color: MUTED, flexShrink: 0 }}>Drive Distance</span>
            <span style={{ fontSize: "max(var(--fs-min), 0.88em)", fontWeight: 700, color: sr.dist >= 0 ? GREEN : RED }}>
              {sr.dist >= 0 ? "+" : ""}{sr.dist.toFixed(1)} yds vs avg
            </span>
          </div>
        </>
      )}
    </div>
  );
}


// ── Approach skill card ───────────────────────────────────────────────────────

const APPROACH_BANDS: { key: keyof Omit<PlayerApproachSkill, "overall_prox">; label: string }[] = [
  { key: "50_100",       label: "50–100 yd (FW)" },
  { key: "100_150",      label: "100–150 yd (FW)" },
  { key: "150_200",      label: "150–200 yd (FW)" },
  { key: "over_200",     label: "200+ yd (FW)" },
  { key: "rgh_under_150", label: "<150 yd (Rough)" },
  { key: "rgh_over_150",  label: "150+ yd (Rough)" },
];


function ApproachCard({ ap }: { ap: PlayerApproachSkill }) {
  return (
    <div style={card}>
      <p style={sectionLabel}>Approach Skill</p>
      {ap.overall_prox != null && (
        <p style={{ fontSize: "max(var(--fs-min), 0.8em)", color: MUTED, marginBottom: 12 }}>
          Overall proximity: <span style={{ color: GOLD }}>{fmt(ap.overall_prox, 1)} ft</span>
        </p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
        {APPROACH_BANDS.map(({ key, label }) => {
          const band = ap[key];
          return (
            <div key={key} style={{
              background: "var(--bc-panel)", borderRadius: 7, padding: "8px 12px",
              border: `1px solid ${BORDER}`,
            }}>
              <div style={{ fontSize: "max(var(--fs-min), 0.7em)", color: MUTED, marginBottom: 3 }}>{label}</div>
              <div style={{ display: "flex", gap: 16 }}>
                <span style={{ fontSize: "max(var(--fs-min), 0.82em)" }}>
                  <span style={{ color: MUTED }}>SG </span>
                  <span style={{ color: sgColor(band.sg), fontWeight: 600 }}>
                    {band.sg != null ? `${band.sg >= 0 ? "+" : ""}${fmt(band.sg, 3)}` : "—"}
                  </span>
                </span>
                <span style={{ fontSize: "max(var(--fs-min), 0.82em)" }}>
                  <span style={{ color: MUTED }}>Prox </span>
                  <span style={{ color: TEXT }}>{band.prox != null ? `${fmt(band.prox, 1)} ft` : "—"}</span>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


const BP_STATS: FieldSpec<import("@/lib/api").PlayerBettingProfile>[] = [
  { key: "driving_distance", label: "Drive", format: (v: number) => `${v.toFixed(1)} yd` },
  { key: "driving_accuracy", label: "Acc", format: (v: number) => `${v.toFixed(1)}%` },
  { key: "gir_pct", label: "GIR" },
  { key: "scrambling_pct", label: "Scramble" },
  { key: "fedex_rank", label: "FedEx", format: (v: number) => `#${Math.round(v)}` },
];


function BettingProfileCard({ bp }: { bp: import("@/lib/api").PlayerBettingProfile }) {
  const courseHistory  = parseCourseHistory(bp.course_history_raw);
  const recentResults  = parseRecentResults(bp.recent_results_raw);
  const keyBullets     = (bp.bullets ?? []).filter(b =>
    !b.startsWith("Responsible") && !b.match(/^[A-Z][a-z]+ (won|finished) this tournament/)
  ).slice(0, 6);

  // A profile row with nothing in it renders as an empty shell with just a
  // header — hide the card entirely unless something is worth showing.
  const summary = presentFields(bp, [{ key: "summary", label: "Summary" }])[0]?.text ?? null;   // "  " is not a summary
  const statRow = presentFields(bp, BP_STATS);
  const hasContent = !!summary || keyBullets.length > 0 || courseHistory.length > 0
    || recentResults.length > 0 || bp.events_played != null || bp.wins != null;
  if (!hasContent) return null;

  return (
    <div style={card}>
      {/* Named by source (Players audit #16): PGA TOUR's season counts can
          differ from Career Stats, which counts the events in our results. */}
      <p style={sectionLabel}>PGA TOUR season profile (from pgatour.com)</p>

      {/* Summary narrative */}
      {summary && (
        <div style={{
          borderLeft: "3px solid var(--bc-line)", paddingLeft: 12,
          marginBottom: 16, color: MUTED, fontSize: "max(var(--fs-min), 0.85em)", lineHeight: 1.65,
        }}>
          {summary}
        </div>
      )}

      {/* Season record */}
      {(bp.events_played != null || bp.wins != null || bp.top_10s != null || bp.cuts_made != null) && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {([
            ["Events",   bp.events_played],
            ["Wins",     bp.wins,     bp.wins != null && bp.wins > 0 ? GOLD : undefined],
            ["Top 10s",  bp.top_10s,  bp.top_10s != null && bp.top_10s > 0 ? GREEN : undefined],
            ["Cuts Made",bp.cuts_made],
          ] as [string, number | null, string?][]).map(([label, val, col]) => val != null ? (
            <div key={label} style={{
              background: "var(--bc-panel)", border: `1px solid ${BORDER}`, borderRadius: 7,
              padding: "8px 14px", textAlign: "center", minWidth: 70,
            }}>
              <div style={{ fontSize: "1.1em", fontWeight: 800, color: col ?? TEXT }}>{val}</div>
              <div style={{ fontSize: "max(var(--fs-min-xs), 0.65em)", color: MUTED, marginTop: 1 }}>{label}</div>
            </div>
          ) : null)}
        </div>
      )}

      {/* SG breakdown with ranks */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 8, marginBottom: 14 }}>
        {([
          ["SG Total",  bp.sg_total,  bp.sg_total_rank],
          ["SG OTT",    bp.sg_ott,    bp.sg_ott_rank],
          ["SG APP",    bp.sg_app,    bp.sg_app_rank],
          ["SG ARG",    bp.sg_arg,    bp.sg_arg_rank],
          ["SG Putt",   bp.sg_putt,   bp.sg_putt_rank],
        ] as [string, number | null, number | null][]).map(([label, val, rank]) => val != null ? (
          <div key={label} style={{
            background: "var(--bc-panel)", border: `1px solid ${BORDER}`,
            borderRadius: 7, padding: "8px 12px",
          }}>
            <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED }}>{label}</div>
            <div style={{ fontSize: "1em", fontWeight: 700, color: sgColor(val) }}>
              {`${val >= 0 ? "+" : ""}${fmt(val, 2)}`}
            </div>
            {rank != null && (
              <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED }}>Rank #{Math.round(rank)}</div>
            )}
          </div>
        ) : null)}
      </div>

      {/* Driving + scoring stats row: only the stats with a value (Jack's presentFields). */}
      {statRow.length > 0 && (
        <div style={{ display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
          {statRow.map(f => (
            <span key={f.label} style={{ fontSize: "max(var(--fs-min), 0.82em)", color: TEXT }}>
              <span style={{ color: MUTED }}>{f.label} </span>{f.text}
            </span>
          ))}
        </div>
      )}

      {/* Key insights bullets */}
      {keyBullets.length > 0 && (
        <>
          <p style={{ ...sectionLabel, marginTop: 4 }}>Key Insights</p>
          <ul style={{ margin: "0 0 16px 0", paddingLeft: 18 }}>
            {keyBullets.map((b, i) => (
              <li key={i} style={{ fontSize: "max(var(--fs-min), 0.82em)", color: MUTED, lineHeight: 1.6, marginBottom: 4 }}>
                {b}
              </li>
            ))}
          </ul>
        </>
      )}

      {/* Recent results table */}
      {recentResults.length > 0 && (
        <>
          <p style={{ ...sectionLabel, marginTop: 4 }}>Recent Results</p>
          <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${BORDER}`, marginBottom: 16 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)", fontSize: "max(var(--fs-min), 0.82em)" }}>
              <thead>
                <tr>
                  {["Finish", "Tournament", "Score", "Year"].map(h => (
                    <th key={h} style={{
                      padding: "6px 10px", textAlign: h === "Finish" ? "center" : "left",
                      fontSize: "max(var(--fs-min), 0.7em)", fontWeight: 700, color: MUTED,
                      textTransform: "uppercase", letterSpacing: "0.05em",
                      borderBottom: `1px solid ${BORDER}`, background: "var(--bc-panel)",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentResults.slice(0, 8).map((r, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)" }}>
                    <td style={{ padding: "5px 10px", textAlign: "center", fontWeight: 700, color: posColor(r.finish) }}>
                      {r.finish}
                    </td>
                    <td style={{ padding: "5px 10px", color: TEXT, whiteSpace: "nowrap", overflow: "hidden", maxWidth: 220, textOverflow: "ellipsis" }}>
                      {r.tournament}
                    </td>
                    <td style={{ padding: "5px 10px", color: r.to_par.startsWith("-") ? GREEN : r.to_par === "E" ? MUTED : RED, fontWeight: 600 }}>
                      {r.to_par}
                    </td>
                    <td style={{ padding: "5px 10px", color: MUTED }}>{r.year}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Course history */}
      {courseHistory.length > 0 && (
        <>
          <p style={{ ...sectionLabel, marginTop: 4 }}>Course History</p>
          {courseHistory.map(course => (
            <div key={course.course_name} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: "max(var(--fs-min), 0.75em)", color: GOLD, marginBottom: 4 }}>{course.course_name}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {course.tournaments.slice(0, 8).map((t, i) => (
                  <div key={i} style={{
                    fontSize: "max(var(--fs-min), 0.72em)", background: "var(--bc-panel)", border: `1px solid ${BORDER}`,
                    borderRadius: 5, padding: "3px 8px", display: "flex", gap: 6, alignItems: "center",
                  }}>
                    <span style={{ color: MUTED }}>{t.year}</span>
                    <span style={{ color: posColor(t.position), fontWeight: 700 }}>{t.position}</span>
                    {t.to_par && t.to_par !== "-" && (
                      <span style={{ color: MUTED }}>{t.to_par}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
