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

import { useState, useEffect, useRef, useCallback } from "react";
import {
  getTournament, getPredictions, getLineup, getTeeTimes, getCourse, getModelComparison,
  getWeather, getIntel, refreshIntel, generateLineup,
  Tournament, PredictionsResponse, LineupResponse, TeeTimesResponse, CourseResponse,
  ModelCompPlayer, WeatherResponse, CourseFitResponse,
  getCourseFit, PlayerPrediction, IntelResponse,
} from "@/lib/api";
import PredictionsTable from "@/components/PredictionsTable";
import LineupCards from "@/components/LineupCards";
import TeeTimesGrid from "@/components/TeeTimesGrid";
import CourseCard from "@/components/CourseCard";
import ModelComparison from "@/components/ModelComparison";
import WeatherStrip from "@/components/WeatherStrip";
import CourseFitTab from "@/components/CourseFitTab";
type Tab = "field" | "lineup" | "teetimes" | "course" | "dg" | "coursefit";

const TABS: { key: Tab; label: string }[] = [
  { key: "field",     label: "Field"       },
  { key: "lineup",    label: "Lineup"      },
  { key: "teetimes",  label: "Tee Times"   },
  { key: "course",    label: "Course"      },
  { key: "dg",        label: "vs DG Model" },
  { key: "coursefit", label: "Course Fit"  },
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
  const [dgMeta, setDgMeta]           = useState<{ tournament_name: string; players_compared: number } | null>(null);
  const [weather, setWeather]         = useState<WeatherResponse | null>(null);
  const [intel, setIntel]             = useState<IntelResponse | null>(null);

  const [generatingLineup, setGeneratingLineup] = useState(false);
  const [generateMsg, setGenerateMsg]           = useState<string | null>(null);

  const [loadingField, setLoadingField]       = useState(true);
  const [loadingLineup, setLoadingLineup]     = useState(false);
  const [loadingTT, setLoadingTT]             = useState(false);
  const [loadingCourse, setLoadingCourse]     = useState(false);
  const [loadingDg, setLoadingDg]             = useState(false);
  const [courseFit, setCourseFit] = useState<CourseFitResponse | null>(null);
  const [loadingCourseFit, setLoadingCourseFit] = useState(false);
  const [error, setError]                     = useState<string | null>(null);
  const [lastUpdated, setLastUpdated]         = useState<Date | null>(null);

  const REFRESH_MS = 5 * 60 * 1000; // 5 minutes
  const pollTimer  = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Core data fetch (called on mount + every 5 min) ──────────────────────────
  const fetchCore = useCallback(async (silent = false) => {
    try {
      const [t, p] = await Promise.all([getTournament(), getPredictions(200)]);
      setTournament(t);
      setPreds(p);
      setLastUpdated(new Date());
      if (!silent) {
        getLineup().then(setLineup).catch(() => {});
        getWeather().then(setWeather).catch(() => {});
        getIntel().then(setIntel).catch(() => {});
      }
    } catch {
      if (!silent) setError("Could not connect to the API. Is FastAPI running on port 8000?");
    } finally {
      if (!silent) setLoadingField(false);
    }
  }, []);

  // ── Initial load + auto-refresh every 5 minutes ──────────────────────────────
  useEffect(() => {
    fetchCore(false);
    pollTimer.current = setInterval(() => fetchCore(true), REFRESH_MS);
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, [fetchCore]);

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
    getModelComparison()
      .then(d => {
        if (!d?.players?.length) return;
        setDgComp(d.players);
        setDgMeta({ tournament_name: d.tournament_name, players_compared: d.players_compared });
      })
      .catch(() => null)
      .finally(() => setLoadingDg(false));
  }, [loaded]);

  useEffect(() => {
    if (!loaded.has("coursefit") || courseFit) return;
    setLoadingCourseFit(true);
    getCourseFit().then(setCourseFit).finally(() => setLoadingCourseFit(false));
  }, [loaded]);


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
            {lastUpdated && (
              <span style={{ color: "#2a3a50", marginLeft: 10 }}>
                · updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </p>
        ) : (
          <p style={{ color: "#3a5060", fontSize: "0.85em", margin: "4px 0 0" }}>Loading tournament…</p>
        )}
      </div>

      {/* ── At-a-glance strip ────────────────────────────────────────────── */}
      {preds && !loadingField && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <GlanceCard label="Field Size" value={String(preds.field_size ?? preds.count)} accent="#4cb8ff" />
          <GlanceCard
            label="Location"
            value={tournament?.location || "—"}
            accent="#7ecf9e"
          />
          <GlanceCard
            label="Purse"
            value={(() => {
              const p = tournament?.purse;
              if (p == null) return "—";
              const s = String(p).replace(/[$,]/g, "").replace(/\.00$/, "");
              const n = parseFloat(s);
              return isNaN(n) ? String(p) : `$${Math.round(n).toLocaleString()}`;
            })()}
            accent="#f1c40f"
          />
          <GlanceCard
            label="Defending Champ"
            value={tournament?.defending_champion || "—"}
            sub={tournament?.defending_champion_year ? `${tournament.defending_champion_year} winner` : undefined}
            accent="#e67e22"
          />
          <GlanceCard
            label="Lineup Picks"
            value={lineup?.confirmed && lineup.picks.length ? lineup.picks.map(p => p.player_name.split(" ").pop()).join(", ") : "Not set"}
            sub={lineup?.confirmed ? "confirmed this week" : "no picks confirmed yet"}
            accent="#9b59b6"
            onClick={() => setActiveTab("lineup")}
          />
          <FieldStrengthCard players={preds.players} />
        </div>
      )}

      {/* ── Weather strip ────────────────────────────────────────────────── */}
      {weather && weather.days.length > 0 && (
        <WeatherStrip days={weather.days} savedAt={weather.saved_at} />
      )}

      {/* ── Course conditions + intel ─────────────────────────────────────── */}
      {intel && <CourseConditionsCard intel={intel} />}

      {/* ── Weekly narrative ─────────────────────────────────────────────── */}
      {preds && (
        <WeeklyNarrative
          text={preds.weekly_narrative ?? ""}
          generatedAt={preds.analysis_generated_at ?? ""}
        />
      )}

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1e3a5f", paddingBottom: 0, flexWrap: "wrap" }}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => activateTab(tab.key)}
            style={{
              background: "transparent", border: "none",
              borderBottom: `2px solid ${activeTab === tab.key ? "#00c44f" : "transparent"}`,
              color: activeTab === tab.key ? "#dde6f5" : "#7f8c8d",
              padding: "8px 16px", fontSize: "0.88em",
              fontWeight: activeTab === tab.key ? 700 : 500,
              cursor: "pointer", marginBottom: -1, transition: "color 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ──────────────────────────────────────────────────── */}

      {activeTab === "field" && (
        loadingField
          ? <Spinner />
          : preds
            ? <PredictionsTable players={preds.players} intel={intel?.players ?? []} />
            : <Empty text="No predictions available." />
      )}

      {activeTab === "lineup" && (
        loadingLineup ? <Spinner /> :
        lineup?.stale ? (
          <div style={{ padding: "32px 24px", textAlign: "center", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
            <div style={{ color: "#7a9ab8", fontSize: "0.95em", marginBottom: 8 }}>
              No lineup generated for this tournament yet.
            </div>
            <div style={{ color: "#4a6080", fontSize: "0.8em", marginBottom: 20 }}>
              Last generated for: <span style={{ color: "#5a7090" }}>{lineup.stale_tournament}</span>
            </div>
            <button
              onClick={async () => {
                setGeneratingLineup(true);
                setGenerateMsg(null);
                try {
                  const r = await generateLineup();
                  setGenerateMsg(r.message ?? "Running in background — reload in ~30 seconds.");
                } catch {
                  setGenerateMsg("Failed to start. Is the API running?");
                } finally {
                  setGeneratingLineup(false);
                }
              }}
              disabled={generatingLineup}
              style={{
                background: generatingLineup ? "#0d1929" : "#0a1f3a",
                border: "1px solid #1e5a3f", borderRadius: 6,
                color: generatingLineup ? "#4a6080" : "#00c44f",
                padding: "8px 20px", fontSize: "0.85em", fontWeight: 700,
                cursor: generatingLineup ? "default" : "pointer",
              }}
            >
              {generatingLineup ? "Starting…" : "Generate Lineup"}
            </button>
            {generateMsg && (
              <div style={{ marginTop: 12, color: "#f0c040", fontSize: "0.78em" }}>{generateMsg}</div>
            )}
          </div>
        ) :
        lineup ? (
          <LineupCards picks={lineup.picks} narrative={lineup.weekly_narrative} generatedAt={lineup.generated_at} />
        ) : (
          <Empty text="No lineup data. Run the season strategy pipeline." />
        )
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
            ? (
              <div>
                {dgMeta && (
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
                    <span style={{ color: "#dde6f5", fontWeight: 700, fontSize: "1em" }}>
                      vs DataGolf — {dgMeta.tournament_name}
                    </span>
                    <span style={{ color: "#4a6080", fontSize: "0.78em" }}>{dgMeta.players_compared} players matched</span>
                  </div>
                )}
                <ModelComparison players={dgComp} />
              </div>
            )
            : <Empty text="No DG comparison data available." />
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
      background: `linear-gradient(180deg, ${color}12 0%, #0d1a30 55%)`,
      border: "1px solid #1e3a5f",
      borderTop: `3px solid ${color}`,
      borderRadius: 8,
      padding: "12px 16px",
      flex: "1 1 160px", minWidth: 150,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{ fontSize: "0.62em", color: `${color}99`, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>
        Field Strength
      </div>
      <div style={{ fontSize: "1.1em", fontWeight: 800, color, marginTop: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: "0.66em", color: "#4a6080", marginTop: 3 }}>
        {top10} top-10 · {top25} top-25 · {top50} top-50
      </div>
      <div style={{ fontSize: "0.66em", color: "#3a5060", marginTop: 1 }}>
        Median rank #{medRank}
      </div>
    </div>
  );
}

function GlanceCard({ label, value, sub, accent = "#4cb8ff", onClick }: {
  label: string; value: string; sub?: string; accent?: string; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: `linear-gradient(180deg, ${accent}12 0%, #0d1a30 55%)`,
        border: "1px solid #1e3a5f",
        borderTop: `3px solid ${accent}`,
        borderRadius: 8,
        padding: "12px 16px",
        flex: "1 1 140px", minWidth: 130,
        position: "relative", overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        transition: onClick ? "border-color 0.15s, background 0.15s" : undefined,
      }}
      onMouseEnter={onClick ? e => (e.currentTarget.style.borderColor = accent) : undefined}
      onMouseLeave={onClick ? e => (e.currentTarget.style.borderColor = "#1e3a5f") : undefined}
    >
      <div style={{ fontSize: "0.62em", color: `${accent}99`, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>
        {label}
      </div>
      <div style={{
        fontSize: "1.1em", fontWeight: 800, color: "#dde6f5",
        marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "0.66em", color: "#4a6080", marginTop: 3 }}>{sub}</div>}
      {onClick && <div style={{ fontSize: "0.6em", color: `${accent}66`, marginTop: 4 }}>click to view</div>}
    </div>
  );
}

function CourseConditionsCard({ intel }: { intel: IntelResponse }) {
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState("");
  const cc = intel.course_conditions;
  const outlookColor = cc.scoring_outlook === "low" ? "#00c44f" : cc.scoring_outlook === "high" ? "#e74c3c" : "#f39c12";
  const injuredCount = intel.players.filter(p => p.injury_flag).length;

  async function handleRefresh() {
    setRefreshing(true);
    setMsg("");
    try {
      const d = await refreshIntel(20);
      setMsg(d.message);
    } catch {
      setMsg("Failed to start refresh.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div style={{ background: "#080f1e", border: "1px solid #1e3a5f", borderLeft: "3px solid #4cb8ff", borderRadius: 8, padding: "14px 18px", marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
            Course Intel · {cc.course_name}
            {intel.age_hours != null && (
              <span style={{ marginLeft: 10, color: "#2a3a4a" }}>as of {intel.age_hours.toFixed(0)}h ago</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
            {cc.rough_length && (
              <span style={{ fontSize: "0.8em", color: "#8ba0b8" }}>
                <span style={{ color: "#4a6080" }}>Rough </span>{cc.rough_length}
              </span>
            )}
            {cc.green_speed && (
              <span style={{ fontSize: "0.8em", color: "#8ba0b8" }}>
                <span style={{ color: "#4a6080" }}>Greens </span>{cc.green_speed}
              </span>
            )}
            <span style={{ fontSize: "0.8em" }}>
              <span style={{ color: "#4a6080" }}>Scoring </span>
              <span style={{ color: outlookColor, fontWeight: 600, textTransform: "capitalize" }}>{cc.scoring_outlook}</span>
            </span>
            {injuredCount > 0 && (
              <span style={{ fontSize: "0.8em", color: "#e74c3c", fontWeight: 600 }}>
                {injuredCount} injury flag{injuredCount > 1 ? "s" : ""}
              </span>
            )}
          </div>
          {cc.setup_notes && (
            <p style={{ color: "#7a90a8", fontSize: "0.82em", lineHeight: 1.6, margin: 0 }}>{cc.setup_notes}</p>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          style={{ background: "none", border: "1px solid #1e3a5f", borderRadius: 5, color: refreshing ? "#4a6080" : "#7a9ab8", fontSize: "0.75em", padding: "3px 10px", cursor: refreshing ? "default" : "pointer", whiteSpace: "nowrap" }}
        >
          {refreshing ? "Running…" : "Refresh Intel"}
        </button>
      </div>
      {msg && <p style={{ color: "#f0c040", fontSize: "0.78em", marginTop: 8, marginBottom: 0 }}>{msg}</p>}
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
