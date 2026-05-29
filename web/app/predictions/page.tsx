/**
 * app/predictions/page.tsx — This Week page
 * ==========================================
 * Four tabs: Field (predictions table), Lineup (3 picks),
 * Tee Times (grouped by time slot), Course (hole scorecard).
 *
 * Data loading pattern here is slightly different from betting/page.tsx:
 * - The tournament header loads immediately on mount (like betting page)
 * - Each tab loads its own data lazily — only when you first click it.
 *   This is done by tracking which tabs have been "activated" in a Set,
 *   then triggering useEffect only when a new tab becomes active.
 *   This avoids loading all four datasets on page load.
 */

"use client";

import { useState, useEffect } from "react";
import {
  getTournament, getPredictions, getLineup, getTeeTimes, getCourse, getModelComparison,
  getWeather, getWithdrawals,
  Tournament, PredictionsResponse, LineupResponse, TeeTimesResponse, CourseResponse,
  ModelCompPlayer, WeatherResponse, WithdrawalsResponse, CourseFitResponse,
  getCourseFit, PlayerPrediction,
} from "@/lib/api";
import PredictionsTable from "@/components/PredictionsTable";
import LineupCards from "@/components/LineupCards";
import TeeTimesGrid from "@/components/TeeTimesGrid";
import CourseCard from "@/components/CourseCard";
import ModelComparison from "@/components/ModelComparison";
import WeatherStrip from "@/components/WeatherStrip";
import WithdrawalsTab from "@/components/WithdrawalsTab";
import CourseFitTab from "@/components/CourseFitTab";
type Tab = "field" | "lineup" | "teetimes" | "course" | "dg" | "wd" | "coursefit";

const TABS_BASE: { key: Tab; label: string }[] = [
    { key: "field",      label: "Field" },
    { key: "lineup",     label: "Lineup" },
    { key: "teetimes",   label: "Tee Times" },
    { key: "course",     label: "Course" },
    { key: "dg",         label: "vs DG Model" },
    { key: "coursefit",  label: "Course Fit" },   // ← add this
  ];

export default function PredictionsPage() {

  // ── Tab state ────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>("field");

  // Track which tabs have ever been activated (so we only fetch each once)
  const [loaded, setLoaded] = useState<Set<Tab>>(new Set(["field"]));

  function activateTab(tab: Tab) {
    setActiveTab(tab);
    setLoaded(prev => new Set([...prev, tab]));
  }

  // ── Data state ───────────────────────────────────────────────────────────────
  const [tournament, setTournament]   = useState<Tournament | null>(null);
  const [preds, setPreds]             = useState<PredictionsResponse | null>(null);
  const [lineup, setLineup]           = useState<LineupResponse | null>(null);
  const [teeTimes, setTeeTimes]       = useState<TeeTimesResponse | null>(null);
  const [course, setCourse]           = useState<CourseResponse | null>(null);
  const [dgComp, setDgComp]           = useState<ModelCompPlayer[] | null>(null);
  const [weather, setWeather]         = useState<WeatherResponse | null>(null);
  const [wds, setWds]                 = useState<WithdrawalsResponse | null>(null);

  const [loadingField, setLoadingField]       = useState(true);
  const [loadingLineup, setLoadingLineup]     = useState(false);
  const [loadingTT, setLoadingTT]             = useState(false);
  const [loadingCourse, setLoadingCourse]     = useState(false);
  const [loadingDg, setLoadingDg]             = useState(false);
  const [loadingWd, setLoadingWd] = useState(false);
  const [courseFit, setCourseFit] = useState<CourseFitResponse | null>(null);
  const [loadingCourseFit, setLoadingCourseFit] = useState(false);
  const [error, setError]                     = useState<string | null>(null);

  // ── Initial load: tournament + field + weather + withdrawals count ───────────
  useEffect(() => {
    async function load() {
      try {
        const [t, p] = await Promise.all([getTournament(), getPredictions(200)]);
        setTournament(t);
        setPreds(p);
        // Lineup, weather, and withdrawals load alongside — failures are non-fatal
        getLineup().then(setLineup).catch(() => {});
        getWeather().then(setWeather).catch(() => {});
        getWithdrawals().then(setWds).catch(() => {});
      } catch {
        setError("Could not connect to the API. Is FastAPI running on port 8000?");
      } finally {
        setLoadingField(false);
      }
    }
    load();
  }, []);

  // ── Lazy load: lineup (no-op if already loaded eagerly on mount) ─────────────
  useEffect(() => {
    if (!loaded.has("lineup") || lineup) return;
    setLoadingLineup(true);
    getLineup().then(setLineup).catch(() => {}).finally(() => setLoadingLineup(false));
  }, [loaded]);

  // ── Lazy load: tee times ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("teetimes") || teeTimes) return;
    setLoadingTT(true);
    getTeeTimes().then(setTeeTimes).finally(() => setLoadingTT(false));
  }, [loaded]);

  // ── Lazy load: course ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("course") || course) return;
    setLoadingCourse(true);
    getCourse().then(setCourse).catch(() => setCourse({ tournament_id: "", course_name: "", par: null, yardage: null, holes: [] })).finally(() => setLoadingCourse(false));
  }, [loaded]);

  // ── Lazy load: DG model comparison ───────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("dg") || dgComp) return;
    setLoadingDg(true);
    getModelComparison(30).then(d => setDgComp(d.players)).finally(() => setLoadingDg(false));
  }, [loaded]);

  // ── Lazy load: withdrawals (full list — count already loaded on mount) ────────
  useEffect(() => {
    if (!loaded.has("wd") || wds) return;
    setLoadingWd(true);
    getWithdrawals().then(setWds).finally(() => setLoadingWd(false));
  }, [loaded]);

  useEffect(() => {
    if (!loaded.has("coursefit") || courseFit) return;
    setLoadingCourseFit(true);
    getCourseFit().then(setCourseFit).finally(() => setLoadingCourseFit(false));
  }, [loaded]);

  // Build tab list with dynamic WD badge
  const confirmedWds = wds?.confirmed_count ?? 0;
  const TABS = [
    ...TABS_BASE,
    {
      key: "wd" as Tab,
      label: confirmedWds > 0 ? `Withdrawals (${confirmedWds})` : "Withdrawals",
    },
  ];

  // ── Error / loading screens ───────────────────────────────────────────────────
  if (error) {
    return (
      <div style={{ maxWidth: 600, margin: "40px auto", padding: 24, background: "#1a0d0d", border: "1px solid #5f1e1e", borderRadius: 10, color: "#e74c3c" }}>
        <strong>Error</strong>
        <p style={{ margin: "8px 0 0", color: "#c0392b", fontSize: "0.9em" }}>{error}</p>
      </div>
    );
  }

  return (
    <div className="page-wrap">

      {/* ── Tournament header ────────────────────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 800, color: "#dde6f5", margin: 0 }}>
          This Week
        </h1>
        {tournament ? (
          <p style={{ color: "#7f8c8d", fontSize: "0.88em", margin: "4px 0 0" }}>
            {tournament.name}
            {tournament.current_round && ` · Round ${tournament.current_round}`}
            {tournament.round_status && ` · ${tournament.round_status}`}
            {tournament.leader_name  && ` · Leader: ${tournament.leader_name}`}
            {tournament.leader_score != null && ` (${tournament.leader_score > 0 ? "+" : ""}${tournament.leader_score})`}
          </p>
        ) : (
          <p style={{ color: "#3a5060", fontSize: "0.85em", margin: "4px 0 0" }}>Loading tournament…</p>
        )}
      </div>

      {/* ── At-a-glance strip ────────────────────────────────────────────── */}
      {preds && !loadingField && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <GlanceCard label="Field Size" value={String(preds.count)} />
          <GlanceCard
            label="Model Favorite"
            value={preds.players[0]?.player_name ?? "—"}
            sub={preds.players[0]?.win_prob != null ? `${(preds.players[0].win_prob * 100).toFixed(1)}% win` : ""}
          />
          <GlanceCard
            label="Avg Win Prob"
            value={`${(preds.players.reduce((s, p) => s + (p.win_prob ?? 0), 0) / preds.players.length * 100).toFixed(1)}%`}
            sub="field average"
          />
          <GlanceCard
            label="Lineup Picks"
            value={lineup?.picks.map(p => p.player_name.split(" ").pop()).join(", ") ?? "—"}
            sub="this week's selections"
          />
          <FieldStrengthCard players={preds.players} />
        </div>
      )}

      {/* ── Weather strip ────────────────────────────────────────────────── */}
      {weather && weather.days.length > 0 && (
        <WeatherStrip days={weather.days} savedAt={weather.saved_at} />
      )}

      {/* ── Weekly narrative ─────────────────────────────────────────────── */}
      {preds && (
        <WeeklyNarrative
          text={preds.weekly_narrative ?? ""}
          generatedAt={preds.analysis_generated_at ?? ""}
        />
      )}

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1e3a5f", paddingBottom: 0, flexWrap: "wrap" }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.key;
          const isWdAlert = tab.key === "wd" && confirmedWds > 0;
          const labelColor = isActive ? "#dde6f5" : isWdAlert ? "#e74c3c" : "#7f8c8d";
          const borderColor = isActive ? (isWdAlert ? "#e74c3c" : "#00c44f") : "transparent";
          return (
            <button
              key={tab.key}
              onClick={() => activateTab(tab.key)}
              style={{
                background: "transparent", border: "none",
                borderBottom: `2px solid ${borderColor}`,
                color: labelColor,
                padding: "8px 16px", fontSize: "0.88em",
                fontWeight: isActive ? 700 : 500,
                cursor: "pointer", marginBottom: -1, transition: "color 0.15s",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Tab content ──────────────────────────────────────────────────── */}

      {activeTab === "field" && (
        loadingField
          ? <Spinner />
          : preds
            ? <PredictionsTable players={preds.players} />
            : <Empty text="No predictions available." />
      )}

      {activeTab === "lineup" && (
        loadingLineup
          ? <Spinner />
          : lineup
            ? <LineupCards picks={lineup.picks} narrative={lineup.weekly_narrative} generatedAt={lineup.generated_at} />
            : <Empty text="No lineup data. Run the season strategy pipeline." />
      )}

      {activeTab === "teetimes" && (
        loadingTT
          ? <Spinner />
          : teeTimes
            ? <TeeTimesGrid data={teeTimes} />
            : <Empty text="No tee times available." />
      )}

      {activeTab === "course" && (
        loadingCourse
          ? <Spinner />
          : course
            ? <CourseCard data={course} />
            : <Empty text="No course data available." />
      )}

      {activeTab === "dg" && (
        loadingDg
          ? <Spinner />
          : dgComp
            ? <ModelComparison players={dgComp} />
            : <Empty text="No DG comparison data available." />
      )}

      {activeTab === "wd" && (
        loadingWd
          ? <Spinner />
          : wds
            ? <WithdrawalsTab withdrawals={wds.withdrawals} />
            : <Empty text="No withdrawal data available." />
      )}

      {activeTab === "coursefit" && (
        loadingCourseFit
          ? <Spinner />
          : courseFit
            ? <CourseFitTab data={courseFit} />
            : <Empty text="No course fit data available." />
      )}

    </div>
  );
}

// ── Small helper components ───────────────────────────────────────────────────

function WeeklyNarrative({ text, generatedAt }: { text: string; generatedAt: string }) {
  const [running, setRunning] = useState(false);
  const [msg, setMsg]         = useState("");

  async function rerun() {
    setRunning(true);
    setMsg("");
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/generate-analysis`, { method: "POST" });
      const d = await r.json();
      setMsg(d.message ?? "Started.");
    } catch {
      setMsg("Failed to start — check the server.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{
      background: "#080f1e",
      border: "1px solid #1e3a5f",
      borderLeft: `3px solid ${text ? "#00c44f" : "#2a3a4a"}`,
      borderRadius: 8,
      padding: "14px 18px",
      marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: text ? 8 : 0 }}>
        <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Weekly Analysis
          {generatedAt && text && <span style={{ marginLeft: 12, color: "#2a3a4a" }}>{generatedAt}</span>}
        </div>
        <button
          onClick={rerun}
          disabled={running}
          style={{
            background: "none", border: "1px solid #1e3a5f", borderRadius: 5,
            color: running ? "#4a6080" : "#7a9ab8", fontSize: "0.75em",
            padding: "3px 10px", cursor: running ? "default" : "pointer",
          }}
        >
          {running ? "Running…" : "Rerun"}
        </button>
      </div>
      {text
        ? <p style={{ color: "#9ab0c8", fontSize: "0.88em", lineHeight: 1.65, margin: 0 }}>{text}</p>
        : <p style={{ color: "#4a6080", fontSize: "0.84em", margin: 0, fontStyle: "italic" }}>
            No analysis for this week yet. Click Rerun to generate (~60 seconds).
          </p>
      }
      {msg && <p style={{ color: "#f0c040", fontSize: "0.78em", marginTop: 8, marginBottom: 0 }}>{msg}</p>}
    </div>
  );
}

// ── Field Strength ────────────────────────────────────────────────────────────
// Counts how many OWGR top-10/25/50 players are in the field, then assigns
// a tier label. Thresholds based on typical tour event composition:
//   Elite (40+ top-50):  major-caliber field
//   Signature (28+):     signature events, WGC-style
//   Strong (18+):        typical Tier A events
//   Average (10+):       mid-tier stops
//   Weak (<10):          opposite-field / developmental events
function fieldStrength(players: PlayerPrediction[]): {
  label: string; color: string; top10: number; top25: number; top50: number; medRank: number;
} {
  const ranks = players.map(p => p.world_rank).filter((r): r is number => r != null && r > 0);
  const top10 = ranks.filter(r => r <= 10).length;
  const top25 = ranks.filter(r => r <= 25).length;
  const top50 = ranks.filter(r => r <= 50).length;
  const sorted = [...ranks].sort((a, b) => a - b);
  const medRank = sorted.length > 0 ? sorted[Math.floor(sorted.length / 2)] : 0;
  let label = "Weak"; let color = "#4a6080";
  if (top50 >= 40) { label = "Elite";      color = "#ffd700"; }
  else if (top50 >= 28) { label = "Signature"; color = "#00c44f"; }
  else if (top50 >= 18) { label = "Strong";    color = "#4cb8ff"; }
  else if (top50 >= 10) { label = "Average";   color = "#aab8c8"; }
  return { label, color, top10, top25, top50, medRank };
}

function FieldStrengthCard({ players }: { players: PlayerPrediction[] }) {
  const { label, color, top10, top25, top50, medRank } = fieldStrength(players);
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 160px", minWidth: 150,
    }}>
      <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Field Strength
      </div>
      <div style={{ fontSize: "1em", fontWeight: 700, color, marginTop: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 3 }}>
        {top10} top-10 · {top25} top-25 · {top50} top-50
      </div>
      <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 1 }}>
        Median rank #{medRank}
      </div>
    </div>
  );
}

function GlanceCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 140px", minWidth: 130,
    }}>
      <div style={{ fontSize: "0.65em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1em", fontWeight: 700, color: "#dde6f5", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "0.65em", color: "#4a6080", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function Spinner() {
  return <div style={{ color: "#7f8c8d", padding: "40px 0", textAlign: "center" }}>Loading…</div>;
}

function Empty({ text }: { text: string }) {
  return (
    <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
      {text}
    </div>
  );
}
