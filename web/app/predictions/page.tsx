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
  getCourseFit, getOpenEvents, getEuroWeek, getEventRounds, EuroWeekMeta, EventRounds, PlayerPrediction, IntelResponse,
} from "@/lib/api";
import PredictionsTable from "@/components/PredictionsTable";
import LineupCards from "@/components/LineupCards";
import TeeTimesGrid from "@/components/TeeTimesGrid";
import CourseCard from "@/components/CourseCard";
import ModelComparison from "@/components/ModelComparison";
import WeatherStrip from "@/components/WeatherStrip";
import CourseFitTab from "@/components/CourseFitTab";
import { PageHead, SubTabs } from "@/components/broadcast";
import Link from "next/link";
import { useUser } from "@clerk/nextjs";
type Tab = "field" | "lineup" | "teetimes" | "course" | "dg" | "coursefit";

const TABS: { id: Tab; label: string }[] = [
  { id: "field",     label: "Field"        },
  { id: "lineup",    label: "Lineup"       },
  { id: "teetimes",  label: "Tee Times"    },
  { id: "course",    label: "Course Guide" },
  { id: "dg",        label: "vs DataGolf"  },
  { id: "coursefit", label: "Course Fit"   },
];

export default function PredictionsPage() {

  // ── Tab state ────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>("field");
  const [tour, setTour] = useState<"pga" | "euro">(() => {
    try { return localStorage.getItem("favorite-tour") === "euro" ? "euro" : "pga"; }
    catch { return "pga"; }
  });
  const [eventState, setEventState] = useState<{ finished: boolean; nextName: string; nextStart: string } | null>(null);

  // Track which tabs have ever been activated (so we only fetch each once)
  const [loaded, setLoaded] = useState<Set<Tab>>(new Set(["field"]));

  function activateTab(tab: Tab) {
    setActiveTab(tab);
    setLoaded(prev => new Set([...prev, tab]));
  }

  // ── Data state ───────────────────────────────────────────────────────────────
  const [tournament, setTournament]   = useState<Tournament | null>(null);
  // Signed-out visitors get a top-10 teaser of the field tab only — the
  // free account unlocks the full forecast and the other tabs.
  const { isSignedIn } = useUser();
  const [preds, setPreds]             = useState<PredictionsResponse | null>(null);
  const [lineup, setLineup]           = useState<LineupResponse | null>(null);

  // Between tournaments this page shows the LAST completed event (its
  // predictions are the newest that exist) — say so explicitly, and say
  // what's next, instead of letting round-4 weather imply it's live.
  useEffect(() => {
    const tid = preds?.tournament_id;
    if (!tid) return;
    getOpenEvents().then(d => {
      const evs = d.events ?? [];
      const cur = evs.find(e => e.tournament_id.toUpperCase() === tid.toUpperCase());
      const next = evs.find(e => !e.finished && e.tour !== "euro");
      setEventState({
        finished: !!cur?.finished,
        nextName: next?.name ?? "",
        nextStart: next?.start_date?.slice(0, 10) ?? "",
      });
    }).catch(() => {});
  }, [preds?.tournament_id]);
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
    getCourse().then(setCourse).catch(() => setCourse({ tournament_id: "", course_name: "", par: null, yardage: null, holes: [], history: null })).finally(() => setLoadingCourse(false));
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
      <div style={{ maxWidth: 600, margin: "40px auto", padding: 24, background: "rgba(224,85,85,0.10)", border: "1px solid rgba(224,85,85,0.35)", borderRadius: 10, color: "var(--bc-red)" }}>
        <strong>Error</strong>
        <p style={{ margin: "8px 0 0", color: "var(--negative)", fontSize: "0.9em" }}>{error}</p>
      </div>
    );
  }

  if (tour === "euro") {
    return (
      <div className="page-wrap">
        <PageHead
          kicker="DP World Tour · numbers by DataGolf's euro model until the January retrain"
          title="This Week"
        />
        <TourPills tour={tour} setTour={setTour} />
        <EuroWeek />
      </div>
    );
  }

  return (
    <div className="page-wrap">

      {/* ── Tournament header ────────────────────────────────────────────── */}
      <PageHead
        kicker={[
          tournament?.name ?? "Loading tournament…",
          tournament?.current_round ? `Round ${tournament.current_round}` : null,
          tournament?.round_status ?? null,
          tournament?.leader_name ? `Leader: ${tournament.leader_name}` : null,
          lastUpdated ? `updated ${lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : null,
        ].filter(Boolean).join(" · ")}
        title="This Week"
      />

      <TourPills tour={tour} setTour={setTour} />

      {eventState?.finished && (
        <div style={{ marginBottom: 16, padding: "12px 16px", borderRadius: 8,
          background: "color-mix(in srgb, var(--bc-yellow) 10%, transparent)",
          border: "1px solid color-mix(in srgb, var(--bc-yellow) 35%, transparent)",
          color: "var(--bc-yellow)", fontSize: "0.86em", fontWeight: 600 }}>
          Final — this tournament is over; you&apos;re viewing its last
          predictions and results.
          {eventState.nextName && (
            <> Next up: <strong>{eventState.nextName}</strong>
            {eventState.nextStart && ` (starts ${eventState.nextStart})`} — fresh
            predictions land Tuesday, and picks are open now on the{" "}
            <Link href="/friends" style={{ color: "var(--bc-yellow)", textDecoration: "underline" }}>
              Friends Game
            </Link>.</>
          )}
        </div>
      )}

      {/* ── At-a-glance strip ────────────────────────────────────────────── */}
      {preds && !loadingField && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <GlanceCard label="Field Size" value={String(preds.field_size ?? preds.count)} accent="var(--bc-yellow)" />
          <GlanceCard
            label="Location"
            value={tournament?.location || "—"}
            accent="var(--bc-green)"
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
            accent="var(--bc-yellow)"
          />
          <GlanceCard
            label="Defending Champ"
            value={tournament?.defending_champion || "—"}
            sub={tournament?.defending_champion_year ? `${tournament.defending_champion_year} winner` : undefined}
            accent="var(--bc-orange)"
          />
          <GlanceCard
            label="Lineup Picks"
            value={lineup?.confirmed && lineup.picks.length ? lineup.picks.map(p => p.player_name.split(" ").pop()).join(", ") : "Not set"}
            sub={lineup?.confirmed ? "confirmed this week" : "no picks confirmed yet"}
            accent="var(--bc-orange)"
            onClick={() => setActiveTab("lineup")}
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

      {/* ── Tab switcher (full tab set is signed-in only) ────────────────── */}
      {isSignedIn && <SubTabs tabs={TABS} active={activeTab} onChange={activateTab} />}

      {/* ── Tab content ──────────────────────────────────────────────────── */}

      {activeTab === "field" && (
        loadingField
          ? <Spinner />
          : preds
            ? <>
                <PredictionsTable
                  players={isSignedIn ? preds.players : preds.players.slice(0, 10)}
                  intel={intel?.players ?? []}
                  myPicks={lineup?.confirmed ? lineup.picks.map(p => p.player_name) : []}
                />
                {!isSignedIn && (
                  <div style={{
                    marginTop: 16, padding: "22px 24px", textAlign: "center",
                    background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10,
                  }}>
                    <div style={{ fontWeight: 800, fontSize: "1.05em", marginBottom: 6 }}>
                      That&apos;s the top 10 of {preds.field_size ?? preds.count} players
                    </div>
                    <p style={{ color: "var(--bc-muted)", fontSize: "0.86em", margin: "0 0 14px", lineHeight: 1.6 }}>
                      A free account unlocks the whole field, the betting board,
                      live tracking, player profiles, and the Friends Game.
                    </p>
                    <Link href="/sign-up" style={{
                      display: "inline-block", background: "var(--bc-yellow)", color: "#081f14",
                      fontWeight: 900, textTransform: "uppercase", fontSize: "0.8em",
                      letterSpacing: "0.06em", padding: "12px 22px", borderRadius: 5,
                    }}>
                      Create free account
                    </Link>
                  </div>
                )}
              </>
            : <Empty text="No predictions available." />
      )}

      {activeTab === "lineup" && (
        loadingLineup ? <Spinner /> :
        lineup?.stale ? (
          <div style={{ padding: "32px 24px", textAlign: "center", background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.95em", marginBottom: 8 }}>
              No lineup generated for this tournament yet.
            </div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.8em", marginBottom: 20 }}>
              Last generated for: <span style={{ color: "var(--bc-muted)" }}>{lineup.stale_tournament}</span>
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
                background: generatingLineup ? "var(--bc-panel)" : "#0a1f3a",
                border: "1px solid #1e5a3f", borderRadius: 6,
                color: generatingLineup ? "var(--bc-muted)" : "var(--bc-green)",
                padding: "8px 20px", fontSize: "0.85em", fontWeight: 700,
                cursor: generatingLineup ? "default" : "pointer",
              }}
            >
              {generatingLineup ? "Starting…" : "Generate Lineup"}
            </button>
            {generateMsg && (
              <div style={{ marginTop: 12, color: "var(--bc-yellow)", fontSize: "0.78em" }}>{generateMsg}</div>
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
            ? <TeeTimesGrid
                data={teeTimes}
                myPicks={lineup?.confirmed ? lineup.picks.map(p => p.player_name) : []}
              />
            : <Empty text="No tee times available." />
      )}

      {activeTab === "course" && (
        <>
          {intel && <CourseConditionsCard intel={intel} />}
          {loadingCourse
            ? <Spinner />
            : course
              ? <CourseCard data={course} />
              : <Empty text="No course data available." />}
        </>
      )}

      {activeTab === "dg" && (
        loadingDg
          ? <Spinner />
          : dgComp
            ? (
              <div>
                {dgMeta && (
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
                    <span style={{ color: "var(--bc-text)", fontWeight: 700, fontSize: "1em" }}>
                      vs DataGolf — {dgMeta.tournament_name}
                    </span>
                    <span style={{ color: "var(--bc-muted)", fontSize: "0.78em" }}>{dgMeta.players_compared} players matched</span>
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

function TourPills({ tour, setTour }: {
  tour: "pga" | "euro"; setTour: (t: "pga" | "euro") => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      {([["pga", "PGA Tour"], ["euro", "DP World Tour"]] as const).map(([id, label]) => (
        <button key={id} onClick={() => setTour(id)} style={{
          cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "0.72em",
          textTransform: "uppercase", letterSpacing: "0.06em",
          padding: "7px 15px", borderRadius: 4,
          color: tour === id ? "#081f14" : "var(--bc-muted)",
          background: tour === id ? "var(--bc-yellow)" : "transparent",
          border: `1px solid ${tour === id ? "var(--bc-yellow)" : "var(--bc-line)"}`,
        }}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** The DPWT week — the SAME UI as the PGA view, euro data underneath:
 *  GlanceCards, WeatherStrip, SubTabs, and the same PredictionsTable
 *  (sorting, search, column toggles included). Tabs whose euro data
 *  sources don't exist yet say so inside the same chrome. */
type EuroTab = "field" | "course" | "teetimes";
const EURO_TABS: { id: EuroTab; label: string }[] = [
  { id: "field",    label: "Field"        },
  { id: "teetimes", label: "Tee Times"    },
  { id: "course",   label: "Course Guide" },
];

function EuroWeek() {
  const [eventName, setEventName] = useState("");
  const [rows, setRows] = useState<PlayerPrediction[] | null>(null);
  const [meta, setMeta] = useState<EuroWeekMeta | null>(null);
  const [live, setLive] = useState<EventRounds | null>(null);
  const [tab, setTab] = useState<EuroTab>("field");
  const [src, setSrc] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    getOpenEvents().then(d => {
      const ev = (d.events ?? []).filter(e => e.tour === "euro")
        .find(e => !e.finished) ?? (d.events ?? []).filter(e => e.tour === "euro")[0];
      if (!ev) { setErr("No DP World Tour event this week."); setRows([]); return; }
      setEventName(ev.name);
      getEuroWeek(ev.tournament_id).then(setMeta).catch(() => {});
      getEventRounds(ev.tournament_id)
        .then(r => { if (r.rounds_available > 0) setLive(r); }).catch(() => {});
      getPredictions(200, ev.tournament_id)
        .then(p => { setRows(p.players ?? []); setSrc(p.source ?? "model"); })
        .catch(() => {
          setErr("Model numbers for this event haven't posted yet — fields and Friends Game picks still work.");
          setRows([]);
        });
    }).catch(() => { setErr("Could not load events."); setRows([]); });
  }, []);

  if (rows === null) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (rows.length === 0 && !meta) return <p style={{ color: "var(--bc-muted)" }}>{err}</p>;

  const money = (v: number) =>
    v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${Math.round(v).toLocaleString()}`;

  // Open-Meteo days dressed as the PGA WeatherStrip's shape — same
  // component, so the two tours' forecasts can never look different.
  const weatherDays = (meta?.weather ?? []).map(w => ({
    day: new Date(w.date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" }),
    condition: w.precip_pct >= 50 ? "DAY_RAIN" : w.precip_pct >= 25 ? "DAY_PARTLY_CLOUDY" : "DAY_SUNNY",
    wind_mph: String(Math.round(w.wind_mph)), wind_dir: "",
    precip_pct: String(w.precip_pct), humidity: "",
    high_f: String(Math.round(w.tmax)), low_f: String(Math.round(w.tmin)),
  }));

  // Euro rows through the PGA table: alias the sim/sort fields the
  // component expects onto the probabilities we have.
  const tableRows = rows.map(r => ({
    ...r,
    win_prob_sim: r.win_prob, top5_prob_sim: r.top5_prob,
    top10_prob_sim: r.top10_prob, top20_prob_sim: r.top20_prob,
    make_cut_prob_sim: r.cut_prob,
  })) as PlayerPrediction[];

  const liveRows = live ? Object.values(live.players)
    .map(p => {
      const scores = Object.entries(p.rounds).sort(([a], [b]) => Number(a) - Number(b));
      return { name: p.player_name, scores, total: scores.reduce((s, [, v]) => s + v, 0) };
    })
    .filter(p => p.scores.length > 0)
    .sort((a, b) => a.total - b.total).slice(0, 10) : [];

  const emptyTab = (what: string, why: string) => (
    <div style={{ background: "var(--bc-card)", border: "1px solid var(--bc-line)",
      borderRadius: 10, padding: 24, color: "var(--bc-muted)", fontSize: "0.88em", lineHeight: 1.6 }}>
      <strong style={{ color: "var(--bc-text)" }}>{what}</strong> isn&apos;t available for
      DP World Tour events yet — {why}
    </div>
  );

  return (
    <>
      {meta && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <GlanceCard label="Course" value={meta.course} sub={meta.location} accent="var(--bc-yellow)" />
          <GlanceCard label="Dates" value={`${meta.start_date.slice(5)} → ${meta.end_date.slice(5)}`} accent="var(--bc-yellow)" />
          <GlanceCard label="Field Size" value={String(meta.field_size || rows.length)} accent="var(--bc-yellow)" />
          {meta.purse != null && (
            <GlanceCard label="Purse" value={money(meta.purse)}
              sub={meta.purse_estimated ? "estimated" : undefined} accent="var(--bc-yellow)" />
          )}
          <GlanceCard label="Model" value={src === "model" ? "Golf Edge euro" : "DataGolf"} accent="var(--bc-yellow)" />
        </div>
      )}

      {weatherDays.length > 0 && <WeatherStrip days={weatherDays} />}

      {liveRows.length > 0 && (
        <div style={{ background: "var(--bc-card)", border: "1px solid var(--bc-line)",
          borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "14px 18px 6px", fontWeight: 800 }}>
            {eventName} — live
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.72em", marginLeft: 8 }}>
              {live!.rounds_available} round{live!.rounds_available === 1 ? "" : "s"} posted · top 10 to par
            </span>
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {liveRows.map((p, i) => (
                <tr key={i}>
                  <td style={{ padding: "6px 18px", fontWeight: 600, fontSize: "0.86em", borderBottom: "1px solid var(--bc-line)" }}>{p.name}</td>
                  <td style={{ padding: "6px 18px", textAlign: "right", fontSize: "0.84em", color: "var(--bc-muted)", borderBottom: "1px solid var(--bc-line)" }}>
                    {p.scores.map(([r, v]) => `R${r} ${v > 0 ? "+" + v : v === 0 ? "E" : v}`).join(" · ")}
                  </td>
                  <td style={{ padding: "6px 18px", textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--bc-line)",
                    color: p.total < 0 ? "var(--bc-green)" : p.total > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                    {p.total > 0 ? "+" + p.total : p.total === 0 ? "E" : p.total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SubTabs tabs={EURO_TABS} active={tab} onChange={setTab} />

      {tab === "field" && (rows.length > 0
        ? <PredictionsTable players={tableRows} />
        : <p style={{ color: "var(--bc-muted)" }}>{err}</p>)}
      {tab === "teetimes" && emptyTab("Tee times",
        "the DP World Tour feed publishes them closer to each round; they land here when a source exists.")}
      {tab === "course" && emptyTab("The course guide",
        "hole-by-hole data has no DPWT source yet. The essentials live in the cards above.")}
    </>
  );
}

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
      background: "var(--bc-panel)",
      borderTop: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)",
      borderLeft: `3px solid ${text ? "var(--bc-green)" : "var(--bc-line)"}`,
      borderRadius: 8,
      padding: "14px 18px",
      marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: text ? 8 : 0 }}>
        <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Weekly Analysis
          {generatedAt && text && <span style={{ marginLeft: 12, color: "var(--bc-line)" }}>{generatedAt}</span>}
        </div>
        <button
          onClick={rerun}
          disabled={running}
          style={{
            background: "none", border: "1px solid var(--bc-line)", borderRadius: 5,
            color: running ? "var(--bc-muted)" : "var(--bc-muted)", fontSize: "0.75em",
            padding: "3px 10px", cursor: running ? "default" : "pointer",
          }}
        >
          {running ? "Running…" : "Rerun"}
        </button>
      </div>
      {text
        ? <p style={{ color: "var(--bc-muted)", fontSize: "0.88em", lineHeight: 1.65, margin: 0 }}>{text}</p>
        : <p style={{ color: "var(--bc-muted)", fontSize: "0.84em", margin: 0, fontStyle: "italic" }}>
            No analysis for this week yet. Click Rerun to generate (~60 seconds).
          </p>
      }
      {msg && <p style={{ color: "var(--bc-yellow)", fontSize: "0.78em", marginTop: 8, marginBottom: 0 }}>{msg}</p>}
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
  let label = "Weak"; let color = "var(--bc-muted)";
  if (top50 >= 40) { label = "Elite";      color = "var(--bc-yellow)"; }
  else if (top50 >= 28) { label = "Signature"; color = "var(--bc-green)"; }
  else if (top50 >= 18) { label = "Strong";    color = "var(--bc-yellow)"; }
  else if (top50 >= 10) { label = "Average";   color = "var(--bc-muted)"; }
  return { label, color, top10, top25, top50, medRank };
}

function FieldStrengthCard({ players }: { players: PlayerPrediction[] }) {
  const { label, color, top10, top25, top50, medRank } = fieldStrength(players);
  return (
    <div style={{
      background: `linear-gradient(180deg, ${color}12 0%, var(--bc-panel) 55%)`,
      borderLeft: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)",
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
      <div style={{ fontSize: "0.66em", color: "var(--bc-muted)", marginTop: 3 }}>
        {top10} top-10 · {top25} top-25 · {top50} top-50
      </div>
      <div style={{ fontSize: "0.66em", color: "var(--bc-muted)", marginTop: 1 }}>
        Median rank #{medRank}
      </div>
    </div>
  );
}

function GlanceCard({ label, value, sub, accent = "var(--bc-yellow)", onClick }: {
  label: string; value: string; sub?: string; accent?: string; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: `linear-gradient(180deg, ${accent}12 0%, var(--bc-panel) 55%)`,
        borderLeft: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)",
        borderTop: `3px solid ${accent}`,
        borderRadius: 8,
        padding: "12px 16px",
        flex: "1 1 140px", minWidth: 130,
        position: "relative", overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        transition: onClick ? "border-color 0.15s, background 0.15s" : undefined,
      }}
      onMouseEnter={onClick ? e => (e.currentTarget.style.borderColor = accent) : undefined}
      onMouseLeave={onClick ? e => (e.currentTarget.style.borderColor = "var(--bc-line)") : undefined}
    >
      <div style={{ fontSize: "0.62em", color: `${accent}99`, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>
        {label}
      </div>
      <div style={{
        fontSize: "1.1em", fontWeight: 800, color: "var(--bc-text)",
        marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "0.66em", color: "var(--bc-muted)", marginTop: 3 }}>{sub}</div>}
      {onClick && <div style={{ fontSize: "0.6em", color: `${accent}66`, marginTop: 4 }}>click to view</div>}
    </div>
  );
}

function CourseConditionsCard({ intel }: { intel: IntelResponse }) {
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState("");
  const cc = intel.course_conditions;
  const outlookColor = cc.scoring_outlook === "low" ? "var(--bc-green)" : cc.scoring_outlook === "high" ? "var(--bc-red)" : "var(--bc-orange)";
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
    <div style={{ background: "var(--bc-panel)", borderTop: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)", borderLeft: "3px solid var(--bc-yellow)", borderRadius: 8, padding: "14px 18px", marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
            Course Intel · {cc.course_name}
            {intel.age_hours != null && (
              <span style={{ marginLeft: 10, color: "var(--bc-line)" }}>as of {intel.age_hours.toFixed(0)}h ago</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
            {cc.rough_length && (
              <span style={{ fontSize: "0.8em", color: "var(--bc-muted)" }}>
                <span style={{ color: "var(--bc-muted)" }}>Rough </span>{cc.rough_length}
              </span>
            )}
            {cc.green_speed && (
              <span style={{ fontSize: "0.8em", color: "var(--bc-muted)" }}>
                <span style={{ color: "var(--bc-muted)" }}>Greens </span>{cc.green_speed}
              </span>
            )}
            <span style={{ fontSize: "0.8em" }}>
              <span style={{ color: "var(--bc-muted)" }}>Scoring </span>
              <span style={{ color: outlookColor, fontWeight: 600, textTransform: "capitalize" }}>{cc.scoring_outlook}</span>
            </span>
            {injuredCount > 0 && (
              <span style={{ fontSize: "0.8em", color: "var(--bc-red)", fontWeight: 600 }}>
                {injuredCount} injury flag{injuredCount > 1 ? "s" : ""}
              </span>
            )}
          </div>
          {cc.setup_notes && (
            <p style={{ color: "var(--bc-muted)", fontSize: "0.82em", lineHeight: 1.6, margin: 0 }}>{cc.setup_notes}</p>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          style={{ background: "none", border: "1px solid var(--bc-line)", borderRadius: 5, color: refreshing ? "var(--bc-muted)" : "var(--bc-muted)", fontSize: "0.75em", padding: "3px 10px", cursor: refreshing ? "default" : "pointer", whiteSpace: "nowrap" }}
        >
          {refreshing ? "Running…" : "Refresh Intel"}
        </button>
      </div>
      {msg && <p style={{ color: "var(--bc-yellow)", fontSize: "0.78em", marginTop: 8, marginBottom: 0 }}>{msg}</p>}
    </div>
  );
}

function Spinner() {
  return <div style={{ color: "var(--bc-muted)", padding: "40px 0", textAlign: "center" }}>Loading…</div>;
}

function Empty({ text }: { text: string }) {
  return (
    <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
      {text}
    </div>
  );
}
