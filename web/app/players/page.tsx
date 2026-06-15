"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  getPlayerList,
  getPlayerProfile,
  getFieldStats,
  getPlayerSynopsis,
  getPlayerCareer,
  getTournamentLeaderboard,
  getLineup,
  PlayerProfile,
  PlayerDecompositions,
  PlayerSkillRatings,
  PlayerApproachSkill,
  PlayerOurModel,
  FieldStatsPlayer,
  PlayerSynopsis,
  PlayerCareer,
  CareerResult,
  CareerYearSummary,
} from "@/lib/api";

const BG       = "#0d1a30";
const CARD_BG  = "#0f2035";
const BORDER   = "#1e3a5f";
const TEXT      = "#dde6f5";
const MUTED     = "#8ba0b8";
const LABEL     = "#4a6080";
const GREEN     = "#00c44f";
const BLUE      = "#4cb8ff";
const GOLD      = "#f1c40f";
const RED       = "#e74c3c";

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}

function fmtPct(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

function fmtOdds(n: number | null | undefined): string {
  if (n == null) return "—";
  return n >= 0 ? `+${Math.round(n)}` : String(Math.round(n));
}

function fmtEv(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString()}`;
}

function sgColor(v: number | null): string {
  if (v == null) return MUTED;
  return v >= 0 ? GREEN : RED;
}

const sectionLabel: React.CSSProperties = {
  fontSize: "0.68em",
  fontWeight: 700,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: LABEL,
  marginBottom: 10,
};

const card: React.CSSProperties = {
  background: CARD_BG,
  border: `1px solid ${BORDER}`,
  borderRadius: 10,
  padding: "16px 20px",
  marginBottom: 16,
};

// ── Stat chip ────────────────────────────────────────────────────────────────

function Chip({ label, value, color = TEXT }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      background: "#091525", border: `1px solid ${BORDER}`, borderRadius: 8,
      padding: "10px 16px", minWidth: 80,
    }}>
      <span style={{ fontSize: "1.15em", fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: "0.68em", color: MUTED, marginTop: 2 }}>{label}</span>
    </div>
  );
}

// ── Adjustment bar ────────────────────────────────────────────────────────────

function AdjBar({ label, value, maxAbs }: { label: string; value: number | null; maxAbs: number }) {
  const pct = value == null || maxAbs === 0 ? 0 : Math.abs(value) / maxAbs * 100;
  const positive = (value ?? 0) >= 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
      <span style={{ width: 160, fontSize: "0.78em", color: MUTED, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
        {/* left half */}
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
          {!positive && value != null && (
            <div style={{
              width: `${pct}%`, height: 8, borderRadius: 2,
              background: RED, maxWidth: "100%",
            }} />
          )}
        </div>
        {/* center line */}
        <div style={{ width: 1, height: 14, background: BORDER, flexShrink: 0 }} />
        {/* right half */}
        <div style={{ flex: 1 }}>
          {positive && value != null && (
            <div style={{
              width: `${pct}%`, height: 8, borderRadius: 2,
              background: GREEN, maxWidth: "100%",
            }} />
          )}
        </div>
      </div>
      <span style={{
        width: 44, fontSize: "0.78em", textAlign: "right", flexShrink: 0,
        color: value == null ? MUTED : (positive ? GREEN : RED),
        fontVariantNumeric: "tabular-nums",
      }}>
        {value == null ? "—" : `${positive ? "+" : ""}${value.toFixed(2)}`}
      </span>
    </div>
  );
}


// ── Pip dots for uses remaining ───────────────────────────────────────────────

function UsePips({ uses }: { uses: number }) {
  return (
    <div style={{ display: "flex", gap: 5 }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 9, height: 9, borderRadius: "50%",
          background: i < uses ? GREEN : "#1e3a5f",
        }} />
      ))}
    </div>
  );
}

// ── Badge ─────────────────────────────────────────────────────────────────────

function Badge({ badge }: { badge: string }) {
  const color = badge === "USE" ? GREEN : badge === "SAVE" ? GOLD : badge === "MAXED" ? RED : "transparent";
  if (!badge) return null;
  return (
    <span style={{
      padding: "3px 10px", borderRadius: 5, fontSize: "0.72em", fontWeight: 800,
      letterSpacing: "0.08em", background: color + "22", color, border: `1px solid ${color}44`,
    }}>
      {badge}
    </span>
  );
}

// ── Course history parser ─────────────────────────────────────────────────────

type CourseResult = { tournament: string; year: number; position: string; to_par: string };
type CourseHistory = { course_name: string; tournaments: CourseResult[] };

function parseCourseHistory(raw: string | null): CourseHistory[] {
  if (!raw || raw === "nan" || raw === "None") return [];
  try {
    return JSON.parse(raw) as CourseHistory[];
  } catch {
    return [];
  }
}

function posColor(pos: string): string {
  const n = parseInt(pos, 10);
  if (isNaN(n)) return MUTED;
  if (n === 1) return GOLD;
  if (n <= 5) return GREEN;
  if (n <= 10) return BLUE;
  return MUTED;
}

function normName(n: string): string {
  return n.toLowerCase().split(/[\s,]+/).filter(Boolean).sort().join(" ");
}

// ── Player select helper (reused by both tabs) ────────────────────────────────

function PlayerSelect({
  players, value, onChange, id, placeholder,
}: {
  players: string[]; value: string; onChange: (v: string) => void;
  id: string; placeholder?: string;
}) {
  const [inputVal, setInputVal] = useState(value);

  useEffect(() => { setInputVal(value); }, [value]);

  return (
    <div style={{ position: "relative" }}>
      <input
        list={id + "-list"}
        value={inputVal}
        onChange={e => setInputVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter") {
            const match = players.find(p => p.toLowerCase() === inputVal.toLowerCase());
            if (match) onChange(match);
          }
        }}
        onBlur={() => {
          const match = players.find(p => p.toLowerCase() === inputVal.toLowerCase());
          if (match) onChange(match);
          else setInputVal(value);
        }}
        placeholder={placeholder ?? "Search player…"}
        style={{
          width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: "0.9em",
          background: CARD_BG, border: `1px solid ${BORDER}`, color: TEXT,
          outline: "none", boxSizing: "border-box",
        }}
      />
      <datalist id={id + "-list"}>
        {players.map(p => <option key={p} value={p} />)}
      </datalist>
    </div>
  );
}

// ── Synopsis card ─────────────────────────────────────────────────────────────

const SECTION_META: { key: keyof PlayerSynopsis["sections"]; label: string; color: string }[] = [
  { key: "form",          label: "Form",          color: GREEN },
  { key: "course_fit",    label: "Course Fit",    color: BLUE  },
  { key: "betting_angle", label: "Betting Angle", color: GOLD  },
  { key: "fantasy",       label: "Fantasy",       color: "#c070f0" },
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
        background: "#080f1e", border: `1px dashed ${BORDER}`,
      }}>
        <div>
          <div style={{ fontSize: "0.88em", color: TEXT, fontWeight: 600, marginBottom: 2 }}>
            AI Player Analysis
          </div>
          <div style={{ fontSize: "0.75em", color: MUTED }}>
            Generate a synopsis using form, course fit, and betting context.
          </div>
        </div>
        <button
          onClick={onGenerate}
          style={{
            background: GREEN + "22", border: `1px solid ${GREEN}44`,
            color: GREEN, borderRadius: 8, padding: "8px 18px",
            fontSize: "0.82em", fontWeight: 700, cursor: "pointer", flexShrink: 0,
          }}
        >
          Generate Analysis
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ ...card, background: "#080f1e", border: `1px dashed ${BORDER}`, textAlign: "center", padding: "28px 20px" }}>
        <div style={{ fontSize: "0.85em", color: MUTED }}>Generating analysis…</div>
        <div style={{ fontSize: "0.72em", color: LABEL, marginTop: 4 }}>
          Gathering stats and asking Claude for a take
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ ...card, background: "#1a0808", border: `1px solid ${RED}44` }}>
        <div style={{ fontSize: "0.82em", color: RED }}>{error}</div>
        <button onClick={onGenerate} style={{ marginTop: 8, fontSize: "0.78em", color: MUTED, background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
          Try again
        </button>
      </div>
    );
  }

  if (!synopsis) return null;

  const ts = synopsis.generated_ts ? new Date(synopsis.generated_ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div style={{ ...card, background: "#080f1e", border: `1px solid #1a3a5f`, marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <span style={{ fontSize: "0.68em", color: LABEL, textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 700 }}>
            AI Analysis
          </span>
          <span style={{ fontSize: "0.65em", color: LABEL, marginLeft: 8 }}>
            {synopsis.tournament_name} · {synopsis.course_name}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {synopsis.cached && (
            <span style={{ fontSize: "0.65em", color: LABEL }}>cached {ts}</span>
          )}
          <button
            onClick={onRegenerate}
            style={{
              background: "none", border: `1px solid ${BORDER}`,
              color: MUTED, borderRadius: 6, padding: "3px 10px",
              fontSize: "0.72em", cursor: "pointer",
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
                fontSize: "0.65em", fontWeight: 800, color,
                textTransform: "uppercase", letterSpacing: "0.1em",
                background: color + "18", border: `1px solid ${color}33`,
                borderRadius: 4, padding: "2px 7px", flexShrink: 0, marginTop: 2,
                minWidth: 80, textAlign: "center",
              }}>
                {label}
              </span>
              <p style={{ margin: 0, fontSize: "0.85em", color: TEXT, lineHeight: 1.65 }}>
                {text}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type PageTab = "lookup" | "h2h" | "stats";

function PlayersPageInner() {
  const searchParams = useSearchParams();
  const deepLinkPlayer = searchParams.get("player") ?? undefined;

  const [pageTab, setPageTab]       = useState<PageTab>(deepLinkPlayer ? "lookup" : "lookup");
  const [players, setPlayers]       = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [myPicks, setMyPicks]       = useState<string[]>([]);

  useEffect(() => {
    getPlayerList()
      .then(d => setPlayers(d.players))
      .finally(() => setListLoading(false));
    getLineup()
      .then(l => { if (l.confirmed) setMyPicks(l.picks.map(p => p.player_name)); })
      .catch(() => {});
  }, []);

  const tabBtn = (key: PageTab, label: string) => (
    <button
      key={key}
      onClick={() => setPageTab(key)}
      style={{
        background: "transparent", border: "none", cursor: "pointer",
        padding: "8px 16px", fontSize: "0.88em", fontWeight: pageTab === key ? 700 : 500,
        color: pageTab === key ? TEXT : MUTED,
        borderBottom: `2px solid ${pageTab === key ? GREEN : "transparent"}`,
        marginBottom: -1, transition: "color 0.15s",
      }}
    >
      {label}
    </button>
  );

  return (
    <main style={{ background: BG, minHeight: "100vh", color: TEXT, padding: "24px 20px" }}>
      <div className="page-wrap-md">

        {/* Page header */}
        <h1 style={{ margin: "0 0 4px", fontSize: "1.4em", fontWeight: 800, color: TEXT }}>Players</h1>

        {/* Tab bar */}
        <div style={{ display: "flex", gap: 4, borderBottom: `1px solid ${BORDER}`, marginBottom: 24 }}>
          {tabBtn("lookup", "Lookup")}
          {tabBtn("h2h",    "Head-to-Head")}
          {tabBtn("stats",  "Stats")}
        </div>

        {listLoading ? (
          <p style={{ color: MUTED }}>Loading players…</p>
        ) : pageTab === "lookup" ? (
          <LookupTab players={players} defaultPlayer={deepLinkPlayer} />
        ) : pageTab === "h2h" ? (
          <H2HTab players={players} />
        ) : (
          <StatsTab myPicks={myPicks} />
        )}
      </div>
    </main>
  );
}

export default function PlayersPage() {
  return (
    <Suspense>
      <PlayersPageInner />
    </Suspense>
  );
}

// ── Lookup tab ────────────────────────────────────────────────────────────────

function LookupTab({ players, defaultPlayer }: { players: string[]; defaultPlayer?: string }) {
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
      .catch(() => setError("Failed to load player profile."))
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

      {error && <p style={{ color: RED }}>{error}</p>}
      {loading && <p style={{ color: MUTED }}>Loading profile…</p>}

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

// ── Stats tab ─────────────────────────────────────────────────────────────────

type StatsView = "sg" | "course" | "form" | "dg";

const VIEWS: { key: StatsView; label: string }[] = [
  { key: "sg",     label: "SG Breakdown" },
  { key: "course", label: "Course Fit" },
  { key: "form",   label: "Form" },
  { key: "dg",     label: "DG Model" },
];

function rankColor(rank: number | null): string {
  if (rank == null) return MUTED;
  if (rank <= 5)  return GREEN;
  if (rank <= 15) return BLUE;
  if (rank <= 30) return TEXT;
  return MUTED;
}

function StatsTab({ myPicks = [] }: { myPicks?: string[] }) {
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
        padding: "7px 10px", background: "#0a1628", cursor: "pointer", userSelect: "none",
        textAlign: align, fontSize: "0.68em", fontWeight: 700, letterSpacing: "0.05em",
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
    background: i % 2 === 0 ? "#0d1a30" : "#0a1525",
    borderBottom: `1px solid #0f2236`,
  });

  function sgCell(val: number | null, rank: number | null, i: number) {
    return (
      <td style={{ ...tdStyle(i), textAlign: "center" }}>
        <span style={{ color: val != null && val >= 0 ? GREEN : RED, fontWeight: 600, fontSize: "0.85em" }}>
          {val != null ? `${val >= 0 ? "+" : ""}${val.toFixed(2)}` : "—"}
        </span>
        {rank != null && (
          <span style={{ display: "block", fontSize: "0.65em", color: rankColor(rank) }}>
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
          color: TEXT, padding: "7px 12px", marginBottom: 12, width: 200, fontSize: "0.85em",
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
              padding: "5px 14px", fontSize: "0.82em", fontWeight: 600, cursor: "pointer",
            }}
          >
            {v.label}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: "0.75em", color: LABEL, alignSelf: "center" }}>
          {sorted.length} players · click column to sort
        </span>
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
          <thead>
            <tr>
              <th style={{ padding: "7px 10px", background: "#0a1628", textAlign: "center", fontSize: "0.68em", color: LABEL, borderBottom: `1px solid ${BORDER}`, width: 36 }}>#</th>
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
                {th("recent_top10s",    "Top10 Score")}
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
              <tr key={p.player_name} style={isPick ? { background: "#060e09" } : undefined}>
                <td style={{ ...tdStyle(i), textAlign: "center", color: LABEL, fontSize: "0.75em", ...(isPick ? { background: "#060e09" } : {}) }}>{i + 1}</td>
                <td style={{ ...tdStyle(i), fontSize: "0.85em", fontWeight: 600, whiteSpace: "nowrap", borderLeft: isPick ? "2px solid #00c44f" : undefined, ...(isPick ? { background: "#060e09" } : {}) }}>
                  <Link
                    href={`/players?player=${encodeURIComponent(p.player_name)}`}
                    style={{ color: isPick ? GREEN : TEXT, textDecoration: "none" }}
                  >
                    {p.player_name}
                  </Link>
                  {isPick && (
                    <span style={{
                      marginLeft: 8, fontSize: "0.65em", fontWeight: 800,
                      color: GREEN, background: "#00c44f18", border: "1px solid #00c44f33",
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
                  <td style={{ ...tdStyle(i), textAlign: "center", fontSize: "0.85em", color: (p.course_sg_total_avg ?? 0) >= 0 ? GREEN : RED, fontWeight: 600 }}>
                    {p.course_sg_starts ? (p.course_sg_total_avg != null ? `${p.course_sg_total_avg >= 0 ? "+" : ""}${p.course_sg_total_avg.toFixed(2)}` : "—") : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: MUTED, fontSize: "0.85em" }}>
                    {p.course_sg_starts ? Math.round(p.course_sg_starts) : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontSize: "0.85em", color: p.course_made_cut_rate != null ? (p.course_made_cut_rate >= 0.8 ? GREEN : MUTED) : MUTED }}>
                    {p.course_sg_starts ? (p.course_made_cut_rate != null ? `${(p.course_made_cut_rate * 100).toFixed(0)}%` : "—") : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GOLD, fontSize: "0.85em" }}>
                    {p.course_sg_starts && p.course_win_rate ? `${(p.course_win_rate * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 600, fontSize: "0.85em",
                      color: p.dg_course_fit_delta_pct != null ? (p.dg_course_fit_delta_pct >= 0 ? GREEN : RED) : MUTED }}>
                    {p.dg_course_fit_delta_pct != null
                      ? `${p.dg_course_fit_delta_pct >= 0 ? "+" : ""}${(p.dg_course_fit_delta_pct * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                </>}

                {view === "form" && <>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 700, fontSize: "0.88em",
                      color: (p.form_trend ?? 0) > 0.2 ? GREEN : (p.form_trend ?? 0) < -0.1 ? RED : MUTED }}>
                    {p.form_trend != null ? `${p.form_trend >= 0 ? "+" : ""}${p.form_trend.toFixed(2)}` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: (p.consecutive_cuts ?? 0) >= 5 ? GREEN : TEXT, fontSize: "0.85em" }}>
                    {p.consecutive_cuts ?? "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontSize: "0.85em" }}>
                    {p.recent_top10s != null ? p.recent_top10s.toFixed(1) : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: p.recent_wins ? GOLD : MUTED, fontWeight: p.recent_wins ? 700 : 400, fontSize: "0.85em" }}>
                    {p.recent_wins ?? 0}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: (p.consecutive_top10s ?? 0) >= 2 ? GREEN : MUTED, fontSize: "0.85em" }}>
                    {p.consecutive_top10s ?? 0}
                  </td>
                </>}

                {view === "dg" && <>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontWeight: 700, fontSize: "0.88em" }}>
                    {p.dg_win != null ? `${(p.dg_win * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GREEN, fontWeight: 700, fontSize: "0.88em" }}>
                    {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: BLUE, fontSize: "0.85em" }}>
                    {p.dg_top10 != null ? `${(p.dg_top10 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", color: GREEN, fontSize: "0.85em" }}>
                    {p.top10_prob != null ? `${(p.top10_prob * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ ...tdStyle(i), textAlign: "center", fontWeight: 600, fontSize: "0.85em",
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

// ── H2H tab ───────────────────────────────────────────────────────────────────

function H2HTab({ players }: { players: string[] }) {
  const [p1Name, setP1Name]     = useState("");
  const [p2Name, setP2Name]     = useState("");
  const [p1, setP1]             = useState<PlayerProfile | null>(null);
  const [p2, setP2]             = useState<PlayerProfile | null>(null);
  const [loadingP1, setLoadingP1] = useState(false);
  const [loadingP2, setLoadingP2] = useState(false);

  function load(name: string, which: 1 | 2) {
    const setLoading = which === 1 ? setLoadingP1 : setLoadingP2;
    const setData    = which === 1 ? setP1 : setP2;
    setLoading(true);
    setData(null);
    getPlayerProfile(name).then(setData).finally(() => setLoading(false));
  }

  function handleP1(name: string) { setP1Name(name); if (name) load(name, 1); }
  function handleP2(name: string) { setP2Name(name); if (name) load(name, 2); }

  const ready = p1 && p2 && !loadingP1 && !loadingP2;

  return (
    <>
      {/* Two selectors */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 12, alignItems: "center", marginBottom: 24 }}>
        <div>
          <div style={{ ...sectionLabel, marginBottom: 6 }}>Player 1</div>
          <PlayerSelect players={players} value={p1Name} onChange={handleP1} id="h2h-p1" placeholder="Select player 1…" />
        </div>
        <div style={{ fontSize: "1.1em", fontWeight: 900, color: "#2a3f58", paddingTop: 22 }}>VS</div>
        <div>
          <div style={{ ...sectionLabel, marginBottom: 6 }}>Player 2</div>
          <PlayerSelect players={players} value={p2Name} onChange={handleP2} id="h2h-p2" placeholder="Select player 2…" />
        </div>
      </div>

      {(loadingP1 || loadingP2) && <p style={{ color: MUTED }}>Loading…</p>}

      {ready && <H2HView p1={p1!} p2={p2!} />}

      {!p1Name && !p2Name && (
        <div style={{ textAlign: "center", padding: "48px 0", color: LABEL, fontSize: "0.88em" }}>
          Select two players above to compare them head-to-head.
        </div>
      )}
    </>
  );
}

// ── H2H view ──────────────────────────────────────────────────────────────────

function H2HView({ p1, p2 }: { p1: PlayerProfile; p2: PlayerProfile }) {
  const m1 = p1.our_model;
  const m2 = p2.our_model;

  return (
    <>
      {/* Header cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 48px 1fr", gap: 0, marginBottom: 20, alignItems: "stretch" }}>
        <H2HHeaderCard profile={p1} accent={GREEN} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: "0.78em", fontWeight: 900, color: "#2a3f58" }}>VS</span>
        </div>
        <H2HHeaderCard profile={p2} accent={BLUE} />
      </div>

      {/* Comparison grid */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>

        <H2HSection label="Model Predictions" />
        <H2HRow label="Win %" va={m1.win_prob != null ? m1.win_prob * 100 : null} vb={m2.win_prob != null ? m2.win_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Top 10 %" va={m1.top10_prob != null ? m1.top10_prob * 100 : null} vb={m2.top10_prob != null ? m2.top10_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Cut %" va={m1.cut_prob != null ? m1.cut_prob * 100 : null} vb={m2.cut_prob != null ? m2.cut_prob * 100 : null} fmt=".0f" suffix="%" higherBetter />
        <H2HRow label="Edge vs Vegas" va={m1.model_vs_vegas_edge} vb={m2.model_vs_vegas_edge} fmt=".1f" suffix="pp" higherBetter />

        <H2HSection label="DG Model" />
        <H2HRow label="DG Win %" va={p1.dg_prediction?.win != null ? p1.dg_prediction.win * 100 : null} vb={p2.dg_prediction?.win != null ? p2.dg_prediction.win * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="DG Top 10 %" va={p1.dg_prediction?.top_10 != null ? p1.dg_prediction.top_10 * 100 : null} vb={p2.dg_prediction?.top_10 != null ? p2.dg_prediction.top_10 * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="DG Course-Adj Win%" va={p1.dg_prediction?.bhf_win != null ? p1.dg_prediction.bhf_win * 100 : null} vb={p2.dg_prediction?.bhf_win != null ? p2.dg_prediction.bhf_win * 100 : null} fmt=".1f" suffix="%" higherBetter />

        <H2HSection label="Season Form" />
        <H2HRow label="Season SG Total" va={m1.season_sg_total} vb={m2.season_sg_total} fmt="+.2f" higherBetter />
        <H2HRow label="Form Trend" va={m1.form_trend} vb={m2.form_trend} fmt="+.2f" higherBetter />
        <H2HRow label="World Rank" va={m1.world_rank} vb={m2.world_rank} fmt=".0f" higherBetter={false} prefix="#" />

        <H2HSection label="Skill Ratings (DG)" />
        <H2HRow label="SG Total" va={p1.skill_ratings?.total} vb={p2.skill_ratings?.total} fmt="+.2f" higherBetter />
        <H2HRow label="Off the Tee" va={p1.skill_ratings?.ott} vb={p2.skill_ratings?.ott} fmt="+.2f" higherBetter />
        <H2HRow label="Approach" va={p1.skill_ratings?.app} vb={p2.skill_ratings?.app} fmt="+.2f" higherBetter />
        <H2HRow label="Around Green" va={p1.skill_ratings?.arg} vb={p2.skill_ratings?.arg} fmt="+.2f" higherBetter />
        <H2HRow label="Putting" va={p1.skill_ratings?.putt} vb={p2.skill_ratings?.putt} fmt="+.2f" higherBetter />

        <H2HSection label="Course Fit" />
        <H2HRow label="Course Fit Adj." va={p1.decompositions?.course_fit_delta} vb={p2.decompositions?.course_fit_delta} fmt="+.3f" higherBetter />
        <H2HRow label="Distance Adj." va={p1.decompositions?.driving_distance_adjustment} vb={p2.decompositions?.driving_distance_adjustment} fmt="+.3f" higherBetter />
        <H2HRow label="Timing Adj." va={p1.decompositions?.timing_adjustment} vb={p2.decompositions?.timing_adjustment} fmt="+.3f" higherBetter />

        <H2HSection label="PGA Tour Stats" />
        <H2HRow label="SG Total" va={p1.betting_profile?.sg_total} vb={p2.betting_profile?.sg_total} fmt="+.2f" higherBetter />
        <H2HRow label="SG OTT" va={p1.betting_profile?.sg_ott} vb={p2.betting_profile?.sg_ott} fmt="+.2f" higherBetter />
        <H2HRow label="SG Approach" va={p1.betting_profile?.sg_app} vb={p2.betting_profile?.sg_app} fmt="+.2f" higherBetter />
        <H2HRow label="SG Putt" va={p1.betting_profile?.sg_putt} vb={p2.betting_profile?.sg_putt} fmt="+.2f" higherBetter />
        <H2HRow label="Drive Distance" va={p1.betting_profile?.driving_distance} vb={p2.betting_profile?.driving_distance} fmt=".1f" suffix=" yd" higherBetter />
        <H2HRow label="Season Wins" va={p1.betting_profile?.top_10s} vb={p2.betting_profile?.top_10s} fmt=".0f" higherBetter />
      </div>
    </>
  );
}

function H2HHeaderCard({ profile, accent }: { profile: PlayerProfile; accent: string }) {
  const m = profile.our_model;
  const isGreen = accent === GREEN;
  return (
    <div style={{
      background: CARD_BG, border: `1px solid ${accent}44`,
      borderRadius: 12, padding: "18px 16px", textAlign: "center",
    }}>
      <Link
        href={`/players?player=${encodeURIComponent(profile.player_name)}`}
        style={{ textDecoration: "none" }}
      >
        <div style={{ fontSize: "1.25em", fontWeight: 800, color: TEXT, marginBottom: 2 }}>
          {profile.player_name.split(" ").slice(-1)[0]}
        </div>
        <div style={{ fontSize: "0.72em", color: LABEL, marginBottom: 12 }}>
          {profile.player_name}
          {m.world_rank != null && ` · #${Math.round(m.world_rank)} World`}
        </div>
      </Link>
      <div style={{ display: "flex", justifyContent: "space-around", marginBottom: 10 }}>
        {[
          ["WIN", m.win_prob != null ? `${(m.win_prob * 100).toFixed(1)}%` : "—"],
          ["TOP 10", m.top10_prob != null ? `${(m.top10_prob * 100).toFixed(1)}%` : "—"],
          ["EV", m.this_week_ev != null ? `$${(m.this_week_ev / 1000).toFixed(0)}k` : "—"],
        ].map(([lbl, val]) => (
          <div key={lbl}>
            <div style={{ fontSize: "1.35em", fontWeight: 800, color: accent }}>{val}</div>
            <div style={{ fontSize: "0.62em", color: LABEL, textTransform: "uppercase", letterSpacing: "0.08em" }}>{lbl}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {m.odds_to_win != null && (
          <span style={{ fontSize: "0.78em", color: MUTED }}>
            {m.odds_to_win >= 0 ? "+" : ""}{Math.round(m.odds_to_win)}
          </span>
        )}
        <UsePips uses={m.uses_remaining} />
        {m.badge && <Badge badge={m.badge} />}
      </div>
    </div>
  );
}

// ── H2H row helpers ───────────────────────────────────────────────────────────

function H2HSection({ label }: { label: string }) {
  return (
    <div style={{
      background: "#080f1e", padding: "6px 16px",
      fontSize: "0.65em", fontWeight: 700, color: LABEL,
      textTransform: "uppercase", letterSpacing: "0.1em",
      borderTop: `1px solid ${BORDER}`,
    }}>
      {label}
    </div>
  );
}

function fmtH2H(v: number, fmt: string, prefix: string, suffix: string): string {
  if (fmt.startsWith("+")) {
    const dec = parseInt(fmt.slice(1).replace("f", "").replace(".", "")) || 2;
    const decimals = fmt.includes(".") ? parseInt(fmt.split(".")[1]) : 0;
    return `${prefix}${v >= 0 ? "+" : ""}${v.toFixed(decimals)}${suffix}`;
  }
  const decimals = fmt.includes(".") ? parseInt(fmt.split(".f")[0].split(".")[1]) : 0;
  return `${prefix}${v.toFixed(decimals)}${suffix}`;
}

function H2HRow({
  label, va, vb, fmt = ".1f", suffix = "", prefix = "", higherBetter,
}: {
  label: string; va: number | null | undefined; vb: number | null | undefined;
  fmt?: string; suffix?: string; prefix?: string; higherBetter: boolean;
}) {
  const a = va ?? null;
  const b = vb ?? null;

  const aWins = a != null && b != null && (higherBetter ? a > b : a < b);
  const bWins = a != null && b != null && (higherBetter ? b > a : b < a);

  // Bar proportions: shift both values positive then normalize
  let fillA = 50, fillB = 50;
  if (a != null && b != null) {
    const shift = Math.min(a, b, 0);
    const fa = a - shift, fb = b - shift;
    const total = fa + fb;
    if (total > 0) {
      fillA = Math.max(2, fa / total * 100);
      fillB = Math.max(2, fb / total * 100);
    }
  }

  const aStr = a != null ? fmtH2H(a, fmt, prefix, suffix) : "—";
  const bStr = b != null ? fmtH2H(b, fmt, prefix, suffix) : "—";

  const aColor = aWins ? GREEN : bWins ? "#4a6080" : TEXT;
  const bColor = bWins ? BLUE  : aWins ? "#4a6080" : TEXT;
  const barA   = aWins ? GREEN : "#0d2e18";
  const barB   = bWins ? BLUE  : "#0d1e30";

  return (
    <div>
      {/* Label row */}
      <div style={{
        textAlign: "center", fontSize: "0.65em", color: "#2e4870",
        textTransform: "uppercase", letterSpacing: "0.09em", paddingTop: 9,
      }}>
        {label}
      </div>
      {/* Value | bar | value */}
      <div style={{
        display: "grid", gridTemplateColumns: "auto 1fr auto",
        alignItems: "center", gap: 12, padding: "5px 20px 10px",
        borderBottom: `1px solid #0a1624`,
      }}>
        <div style={{ fontSize: "1em", fontWeight: aWins ? 700 : 400, color: aColor, minWidth: 58, textAlign: "right" }}>
          {aStr}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: `${fillA.toFixed(1)}fr ${fillB.toFixed(1)}fr`, height: 8, borderRadius: 5, overflow: "hidden" }}>
          <div style={{ background: barA }} />
          <div style={{ background: barB }} />
        </div>
        <div style={{ fontSize: "1em", fontWeight: bWins ? 700 : 400, color: bColor, minWidth: 58, textAlign: "left" }}>
          {bStr}
        </div>
      </div>
    </div>
  );
}

// ── Career card ───────────────────────────────────────────────────────────────

function posColor2(pos: string): string {
  const n = parseInt(pos, 10);
  if (isNaN(n)) return MUTED;
  if (n === 1) return GOLD;
  if (n <= 5)  return GREEN;
  if (n <= 10) return BLUE;
  return TEXT;
}

function sgColor2(v: number | null): string {
  if (v == null) return MUTED;
  return v >= 0 ? GREEN : RED;
}

function fmtSg(v: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

function toParColor2(v: string | null): string {
  if (!v) return MUTED;
  if (v.startsWith("-")) return GREEN;
  if (v === "0" || v === "E") return MUTED;
  return RED;
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

  if (error) return <p style={{ color: RED, fontSize: "0.8em", margin: "8px 0 0" }}>Failed to load.</p>;
  if (!rows)  return <p style={{ color: MUTED, fontSize: "0.8em", margin: "8px 0 0" }}>Loading leaderboard…</p>;

  const hasEarnings = rows.some(r => r.earnings != null);

  const thS: React.CSSProperties = {
    padding: "5px 8px", background: "#060f1c", fontSize: "0.67em", fontWeight: 700,
    color: LABEL, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${BORDER}`,
  };
  const tdS = (isPick: boolean, i: number): React.CSSProperties => ({
    padding: "4px 8px", fontSize: "0.8em",
    borderBottom: "1px solid #0a1828",
    background: isPick ? "#060e09" : i % 2 === 0 ? "#081220" : "#091828",
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
            {hasEarnings && <th style={{ ...thS, textAlign: "right" }}>Earnings</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isPick = normName(r.player_name) === highlightKey;
            return (
              <tr key={i}>
                <td style={{ ...tdS(isPick, i), fontWeight: 700, color: posColor2(r.position), borderLeft: isPick ? "2px solid #00c44f" : undefined }}>
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
                <td style={{ ...tdS(isPick, i), textAlign: "center", fontWeight: 600, color: toParColor2(r.to_par) }}>
                  {r.to_par || "—"}
                </td>
                {hasEarnings && (
                  <td style={{ ...tdS(isPick, i), textAlign: "right", color: MUTED, fontSize: "0.75em" }}>
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
  // tracks which tournament row is expanded in Recent Starts
  const [expandedTid, setExpandedTid] = useState<string | null>(null);

  function load() {
    setLoading(true);
    getPlayerCareer(playerName)
      .then(d => { setCareer(d); setLoaded(true); })
      .catch(() => setLoaded(true))
      .finally(() => setLoading(false));
  }

  const thStyle: React.CSSProperties = {
    padding: "6px 10px", background: "#081220", fontSize: "0.68em", fontWeight: 700,
    color: LABEL, textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: `1px solid ${BORDER}`, whiteSpace: "nowrap",
  };
  const tdBase = (i: number): React.CSSProperties => ({
    padding: "5px 10px", borderBottom: `1px solid #0d1e2e`, fontSize: "0.83em",
    background: i % 2 === 0 ? "#091525" : "#0a1628",
  });

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <p style={{ ...sectionLabel, margin: 0 }}>Career Stats</p>
        {!loaded && !loading && (
          <button onClick={load} style={{
            background: BLUE + "22", border: `1px solid ${BLUE}44`,
            color: BLUE, borderRadius: 7, padding: "5px 14px",
            fontSize: "0.78em", fontWeight: 700, cursor: "pointer",
          }}>
            Load Career Stats
          </button>
        )}
        {loaded && (
          <div style={{ display: "flex", gap: 6 }}>
            {(["yearly", "recent"] as const).map(v => (
              <button key={v} onClick={() => setView(v)} style={{
                background: view === v ? GREEN + "22" : "transparent",
                border: `1px solid ${view === v ? GREEN : BORDER}`,
                borderRadius: 6, color: view === v ? GREEN : MUTED,
                padding: "4px 12px", fontSize: "0.75em", fontWeight: 600, cursor: "pointer",
              }}>
                {v === "yearly" ? "By Year" : "Recent Starts"}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && <p style={{ color: MUTED, fontSize: "0.85em" }}>Loading…</p>}

      {/* ── By Year view ─────────────────────────────────────────────────── */}
      {loaded && career && view === "yearly" && (
        <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${BORDER}` }}>
          <table style={{ width: "100%", borderCollapse: "collapse", background: "#091525" }}>
            <thead>
              <tr>
                {[
                  ["Year", "left"], ["Events", "center"], ["Wins", "center"],
                  ["Top 10", "center"], ["Top 25", "center"], ["Cuts", "center"],
                  ["Avg Score", "center"], ["SG Tot", "center"],
                  ["SG OTT", "center"], ["SG APP", "center"], ["SG Putt", "center"],
                ].map(([h, align]) => (
                  <th key={h} style={{ ...thStyle, textAlign: align as "left" | "center" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {career.by_year.map((y, i) => (
                <tr key={y.year} style={{ background: i % 2 === 0 ? "#091525" : "#0a1628" }}>
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
                  <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: sgColor2(y.avg_sg_total) }}>
                    {fmtSg(y.avg_sg_total)}
                  </td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(y.avg_sg_ott) }}>{fmtSg(y.avg_sg_ott)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(y.avg_sg_app) }}>{fmtSg(y.avg_sg_app)}</td>
                  <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(y.avg_sg_putt) }}>{fmtSg(y.avg_sg_putt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Recent Starts view ───────────────────────────────────────────── */}
      {loaded && career && view === "recent" && (
        <div style={{ overflowX: "auto", borderRadius: 8, border: `1px solid ${BORDER}` }}>
          <table style={{ width: "100%", borderCollapse: "collapse", background: "#091525" }}>
            <thead>
              <tr>
                {[
                  ["Tournament", "left"], ["Year", "left"], ["Pos", "center"],
                  ["Score", "center"], ["SG Tot", "center"], ["OTT", "center"],
                  ["APP", "center"], ["Putt", "center"], ["Earnings", "right"],
                ].map(([h, align]) => (
                  <th key={h} style={{ ...thStyle, textAlign: align as "left" | "center" | "right" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {career.recent.map((r, i) => {
                const isExpanded = expandedTid === r.tournament_id;
                // Only show tournament leaderboard if we have a settled tournament ID
                // (IDs starting with R and year <= current — not future events)
                const canExpand = !!r.tournament_id;
                return (
                  <React.Fragment key={`${r.tournament_id}-${i}`}>
                    <tr
                      onClick={() => canExpand && setExpandedTid(isExpanded ? null : r.tournament_id)}
                      style={{ cursor: canExpand ? "pointer" : "default", background: i % 2 === 0 ? "#091525" : "#0a1628" }}
                    >
                      <td style={{ ...tdBase(i), maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ color: TEXT }}>{r.tournament_name}</span>
                          {canExpand && (
                            <span style={{ fontSize: "0.7em", color: isExpanded ? BLUE : "#2a4060" }}>
                              {isExpanded ? "▲" : "▼"}
                            </span>
                          )}
                        </span>
                      </td>
                      <td style={{ ...tdBase(i), color: MUTED }}>{r.year}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 700, color: posColor2(r.position) }}>
                        {r.position}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: toParColor2(r.to_par) }}>
                        {r.to_par ?? "—"}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", fontWeight: 600, color: sgColor2(r.sg_total) }}>
                        {fmtSg(r.sg_total)}
                      </td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(r.sg_ott) }}>{fmtSg(r.sg_ott)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(r.sg_app) }}>{fmtSg(r.sg_app)}</td>
                      <td style={{ ...tdBase(i), textAlign: "center", color: sgColor2(r.sg_putt) }}>{fmtSg(r.sg_putt)}</td>
                      <td style={{ ...tdBase(i), textAlign: "right", color: MUTED, fontSize: "0.78em" }}>
                        {r.earnings ?? "—"}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={9} style={{ background: "#07101c", padding: "10px 16px", borderBottom: "1px solid #0d1e2e" }}>
                          <TournamentResultsPanel tid={r.tournament_id} highlightPlayer={playerName} />
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
        <p style={{ color: MUTED, fontSize: "0.83em" }}>No career data found.</p>
      )}
    </div>
  );
}

// ── Profile view ──────────────────────────────────────────────────────────────

function ProfileView({ profile }: { profile: PlayerProfile }) {
  const m = profile.our_model;

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
              <Badge badge={m.badge} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 6 }}>
              <span style={{ fontSize: "0.82em", color: MUTED }}>
                {m.world_rank != null ? `World #${Math.round(m.world_rank)}` : "World rank —"}
              </span>
              <UsePips uses={m.uses_remaining} />
              <span style={{ fontSize: "0.72em", color: MUTED }}>{m.uses_remaining}/3 uses left</span>
            </div>
          </div>
          {/* vs field ranks */}
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.6em", fontWeight: 800, color: GREEN }}>
                {m.win_rank != null ? `#${m.win_rank}` : "—"}
              </div>
              <div style={{ fontSize: "0.68em", color: LABEL }}>WIN RANK</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.6em", fontWeight: 800, color: BLUE }}>
                {m.top10_rank != null ? `#${m.top10_rank}` : "—"}
              </div>
              <div style={{ fontSize: "0.68em", color: LABEL }}>TOP10 RANK</div>
            </div>
          </div>
        </div>
      </div>

      {/* Section 2: Our Model */}
      <div style={card}>
        <p style={sectionLabel}>Our Model</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <Chip label="Win%" value={fmtPct(m.win_prob)} color={GREEN} />
          <Chip label="Top 10%" value={fmtPct(m.top10_prob)} color={BLUE} />
          <Chip label="Cut%" value={fmtPct(m.cut_prob)} />
          <Chip label="Season SG" value={fmt(m.season_sg_total, 2)} color={sgColor(m.season_sg_total)} />
          {m.odds_to_win != null && (
            <Chip label="DK Odds" value={fmtOdds(m.odds_to_win)} />
          )}
          {m.model_vs_vegas_edge != null && (
            <Chip label="Edge" value={`${m.model_vs_vegas_edge > 0 ? "+" : ""}${fmt(m.model_vs_vegas_edge)}pp`} color={m.model_vs_vegas_edge > 0 ? GREEN : RED} />
          )}
        </div>
        {m.explanation && (
          <p style={{ fontSize: "0.85em", color: TEXT, margin: "0 0 8px 0", lineHeight: 1.5 }}>
            {m.explanation}
          </p>
        )}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
          {m.recommendation && (
            <span style={{ fontSize: "0.78em", color: MUTED }}>
              <span style={{ color: LABEL }}>REC </span>{m.recommendation}
            </span>
          )}
          {m.this_week_ev != null && (
            <span style={{ fontSize: "0.78em", color: GOLD }}>
              <span style={{ color: LABEL }}>EV </span>{fmtEv(m.this_week_ev)}
            </span>
          )}
          {m.form_trend != null && (
            <span style={{ fontSize: "0.78em", color: sgColor(m.form_trend) }}>
              <span style={{ color: LABEL }}>Form </span>
              {m.form_trend > 0 ? "+" : ""}{fmt(m.form_trend, 2)}
            </span>
          )}
          {m.dk_odds_direction && (
            <span style={{ fontSize: "0.78em", color: m.dk_odds_direction === "UP" ? GREEN : m.dk_odds_direction === "DOWN" ? RED : MUTED }}>
              <span style={{ color: LABEL }}>Drift </span>
              {m.dk_odds_direction === "UP" ? "▲" : m.dk_odds_direction === "DOWN" ? "▼" : "→"}
            </span>
          )}
        </div>
      </div>

      {/* Section 3: Career Stats */}
      <CareerCard playerName={profile.player_name} />

      {/* Section 4: DG Tournament Prediction */}
      {profile.dg_prediction && (
        <div style={card}>
          <p style={sectionLabel}>DG Tournament Prediction</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            <Chip label="DG Win%"    value={fmtPct(profile.dg_prediction.win)}      color={BLUE} />
            <Chip label="Top 5%"     value={fmtPct(profile.dg_prediction.top_5)}    color={BLUE} />
            <Chip label="Top 10%"    value={fmtPct(profile.dg_prediction.top_10)}   color={BLUE} />
            <Chip label="Top 20%"    value={fmtPct(profile.dg_prediction.top_20)}   color={BLUE} />
            <Chip label="Make Cut%"  value={fmtPct(profile.dg_prediction.make_cut)} color={BLUE} />
          </div>
          {/* Course fit context: baseline → adjusted */}
          {profile.dg_prediction.baseline_win != null && profile.dg_prediction.bhf_win != null && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
              background: "#091525", border: `1px solid ${BORDER}`, borderRadius: 8,
              padding: "10px 14px",
            }}>
              <span style={{ fontSize: "0.8em", color: LABEL }}>Course fit</span>
              <span style={{ fontSize: "0.88em", color: MUTED, fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(profile.dg_prediction.baseline_win)} baseline
              </span>
              <span style={{ fontSize: "0.8em", color: LABEL }}>→</span>
              <span style={{ fontSize: "0.88em", fontWeight: 700, color: BLUE, fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(profile.dg_prediction.bhf_win)} adjusted
              </span>
              {profile.dg_prediction.course_fit_delta_pct != null && (
                <span style={{
                  fontSize: "0.78em", fontWeight: 700,
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

      {/* Section 4: Course Decompositions */}
      {profile.decompositions && <DecompositionsCard dec={profile.decompositions} />}

      {/* Section 5: DG Skill Ratings */}
      {profile.skill_ratings && <SkillRatingsCard sr={profile.skill_ratings} />}

      {/* Section 6: Approach Skill */}
      {profile.approach_skill && <ApproachCard ap={profile.approach_skill} />}

      {/* Section 7: Betting Profile */}
      {profile.betting_profile && <BettingProfileCard bp={profile.betting_profile} />}
    </>
  );
}

// ── Decompositions card ───────────────────────────────────────────────────────

const DEC_ROWS: { key: keyof PlayerDecompositions; label: string }[] = [
  { key: "course_fit_delta",                   label: "Course Fit (total)" },
  { key: "total_course_history_adjustment",    label: "Course History" },
  { key: "driving_distance_adjustment",        label: "Driving Distance" },
  { key: "driving_accuracy_adjustment",        label: "Driving Accuracy" },
  { key: "strokes_gained_category_adjustment", label: "SG Category" },
  { key: "timing_adjustment",                  label: "Timing / Hot Streak" },
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
        fontSize: "0.65em", color: LABEL, marginBottom: 10,
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
          <span style={{ fontSize: "0.75em", color: LABEL }}>SG / round vs field avg</span>
        </div>
      )}

      {/* Axis label */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: "0.65em", color: LABEL, marginBottom: 10,
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
            <span style={{ width: 160, fontSize: "0.78em", color: MUTED, flexShrink: 0 }}>Drive Distance</span>
            <span style={{ fontSize: "0.88em", fontWeight: 700, color: sr.dist >= 0 ? GREEN : RED }}>
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
        <p style={{ fontSize: "0.8em", color: MUTED, marginBottom: 12 }}>
          Overall proximity: <span style={{ color: BLUE }}>{fmt(ap.overall_prox, 1)} ft</span>
        </p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
        {APPROACH_BANDS.map(({ key, label }) => {
          const band = ap[key];
          return (
            <div key={key} style={{
              background: "#091525", borderRadius: 7, padding: "8px 12px",
              border: `1px solid ${BORDER}`,
            }}>
              <div style={{ fontSize: "0.7em", color: LABEL, marginBottom: 3 }}>{label}</div>
              <div style={{ display: "flex", gap: 16 }}>
                <span style={{ fontSize: "0.82em" }}>
                  <span style={{ color: MUTED }}>SG </span>
                  <span style={{ color: sgColor(band.sg), fontWeight: 600 }}>
                    {band.sg != null ? `${band.sg >= 0 ? "+" : ""}${fmt(band.sg, 3)}` : "—"}
                  </span>
                </span>
                <span style={{ fontSize: "0.82em" }}>
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

// ── Betting profile card ──────────────────────────────────────────────────────

type RecentResult = { tournament: string; course?: string; finish: string; year: number; to_par: string; winnings?: string };

function parseRecentResults(raw: string | null): RecentResult[] {
  if (!raw || raw === "nan" || raw === "None") return [];
  try { return JSON.parse(raw) as RecentResult[]; } catch { return []; }
}

function BettingProfileCard({ bp }: { bp: import("@/lib/api").PlayerBettingProfile }) {
  const courseHistory  = parseCourseHistory(bp.course_history_raw);
  const recentResults  = parseRecentResults(bp.recent_results_raw);
  const keyBullets     = (bp.bullets ?? []).filter(b =>
    !b.startsWith("Responsible") && !b.match(/^[A-Z][a-z]+ (won|finished) this tournament/)
  ).slice(0, 6);

  return (
    <div style={card}>
      <p style={sectionLabel}>PGA Tour Insights</p>

      {/* Summary narrative */}
      {bp.summary && (
        <div style={{
          borderLeft: "3px solid #1e3a5f", paddingLeft: 12,
          marginBottom: 16, color: MUTED, fontSize: "0.85em", lineHeight: 1.65,
        }}>
          {bp.summary}
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
              background: "#091525", border: `1px solid ${BORDER}`, borderRadius: 7,
              padding: "8px 14px", textAlign: "center", minWidth: 70,
            }}>
              <div style={{ fontSize: "1.1em", fontWeight: 800, color: col ?? TEXT }}>{val}</div>
              <div style={{ fontSize: "0.65em", color: LABEL, marginTop: 1 }}>{label}</div>
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
            background: "#091525", border: `1px solid ${BORDER}`,
            borderRadius: 7, padding: "8px 12px",
          }}>
            <div style={{ fontSize: "0.68em", color: LABEL }}>{label}</div>
            <div style={{ fontSize: "1em", fontWeight: 700, color: sgColor(val) }}>
              {`${val >= 0 ? "+" : ""}${fmt(val, 2)}`}
            </div>
            {rank != null && (
              <div style={{ fontSize: "0.68em", color: MUTED }}>Rank #{Math.round(rank)}</div>
            )}
          </div>
        ) : null)}
      </div>

      {/* Driving + scoring stats row */}
      <div style={{ display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
        {bp.driving_distance != null && (
          <span style={{ fontSize: "0.82em", color: TEXT }}>
            <span style={{ color: LABEL }}>Drive </span>{fmt(bp.driving_distance, 1)} yd
          </span>
        )}
        {bp.driving_accuracy != null && (
          <span style={{ fontSize: "0.82em", color: TEXT }}>
            <span style={{ color: LABEL }}>Acc </span>{fmt(bp.driving_accuracy, 1)}%
          </span>
        )}
        {bp.gir_pct && (
          <span style={{ fontSize: "0.82em", color: TEXT }}>
            <span style={{ color: LABEL }}>GIR </span>{bp.gir_pct}
          </span>
        )}
        {bp.scrambling_pct && (
          <span style={{ fontSize: "0.82em", color: TEXT }}>
            <span style={{ color: LABEL }}>Scramble </span>{bp.scrambling_pct}
          </span>
        )}
        {bp.fedex_rank != null && (
          <span style={{ fontSize: "0.82em", color: TEXT }}>
            <span style={{ color: LABEL }}>FedEx </span>#{Math.round(bp.fedex_rank)}
          </span>
        )}
      </div>

      {/* Key insights bullets */}
      {keyBullets.length > 0 && (
        <>
          <p style={{ ...sectionLabel, marginTop: 4 }}>Key Insights</p>
          <ul style={{ margin: "0 0 16px 0", paddingLeft: 18 }}>
            {keyBullets.map((b, i) => (
              <li key={i} style={{ fontSize: "0.82em", color: MUTED, lineHeight: 1.6, marginBottom: 4 }}>
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
            <table style={{ width: "100%", borderCollapse: "collapse", background: "#091525", fontSize: "0.82em" }}>
              <thead>
                <tr>
                  {["Finish", "Tournament", "Score", "Year"].map(h => (
                    <th key={h} style={{
                      padding: "6px 10px", textAlign: h === "Finish" ? "center" : "left",
                      fontSize: "0.7em", fontWeight: 700, color: LABEL,
                      textTransform: "uppercase", letterSpacing: "0.05em",
                      borderBottom: `1px solid ${BORDER}`, background: "#0a1628",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentResults.slice(0, 8).map((r, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? "#091525" : "#0a1628" }}>
                    <td style={{ padding: "5px 10px", textAlign: "center", fontWeight: 700, color: posColor(r.finish) }}>
                      {r.finish}
                    </td>
                    <td style={{ padding: "5px 10px", color: TEXT, whiteSpace: "nowrap", overflow: "hidden", maxWidth: 220, textOverflow: "ellipsis" }}>
                      {r.tournament}
                    </td>
                    <td style={{ padding: "5px 10px", color: r.to_par.startsWith("-") ? GREEN : r.to_par === "E" ? MUTED : RED, fontWeight: 600 }}>
                      {r.to_par}
                    </td>
                    <td style={{ padding: "5px 10px", color: LABEL }}>{r.year}</td>
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
              <div style={{ fontSize: "0.75em", color: BLUE, marginBottom: 4 }}>{course.course_name}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {course.tournaments.slice(0, 8).map((t, i) => (
                  <div key={i} style={{
                    fontSize: "0.72em", background: "#0a1628", border: `1px solid ${BORDER}`,
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
