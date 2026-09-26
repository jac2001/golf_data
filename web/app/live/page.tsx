/**
 * app/live/page.tsx — Live tournament page
 * =========================================
 * Four tabs: Leaderboard, vs Predictions, My Lineup, SG Stats.
 *
 * Uses the same lazy-loading pattern as the predictions page:
 * - "leaderboard" tab loads on mount
 * - Other tabs only fetch data when first clicked (tracked in a Set)
 * - SgStats tab also has its own round_param state for the round selector
 */

"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  getTournament, getInPlay, getVsPredictions, getMyLineupLive, getSgStats, getHoleScores,
  refreshHoleScores, getLivePulse, getHoleStats, getSettings, getWithdrawals, getLineup,
  Tournament, InPlayResponse, VsPredPlayer, MyLineupResponse, SgStatsResponse, HoleScoresResponse,
  HoleStatsResponse, LivePulse as LivePulseData, WithdrawalsResponse,
  getOpenEvents, getEuroLive, EuroLive, getEuroCourse,
} from "@/lib/api";
import InPlayLeaderboard from "@/components/InPlayLeaderboard";
import VsPredictions from "@/components/VsPredictions";
import MyLineupLive from "@/components/MyLineupLive";
import SgStatsTable from "@/components/SgStatsTable";
import HoleStatsTable from "@/components/HoleStatsTable";
import LivePulse from "@/components/LivePulse";
import AlertBanner from "@/components/AlertBanner";

type Tab = "leaderboard" | "vspred" | "mylineup" | "sg" | "holes";

import { PageHead, SubTabs } from "@/components/broadcast";

const TABS: { id: Tab; label: string }[] = [
  { id: "leaderboard", label: "Leaderboard"    },
  { id: "vspred",      label: "vs Forecast"    },
  { id: "mylineup",    label: "My Lineup"      },
  { id: "sg",          label: "Strokes Gained" },
  { id: "holes",       label: "Hole Stats"     },
];

const POLL_INTERVAL_MS = 60_000; // refresh leaderboard every 60 seconds

export default function LivePage() {

  const [tour, setTour] = useState<"pga" | "euro">(() => {
    try { return localStorage.getItem("favorite-tour") === "euro" ? "euro" : "pga"; }
    catch { return "pga"; }
  });
  const [activeTab, setActiveTab] = useState<Tab>("leaderboard");
  const [loaded, setLoaded] = useState<Set<Tab>>(new Set(["leaderboard"]));
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  function activateTab(tab: Tab) {
    setActiveTab(tab);
    setLoaded(prev => new Set([...prev, tab]));
  }

  // ── Data state ───────────────────────────────────────────────────────────────
  const [tournament,   setTournament]   = useState<Tournament | null>(null);
  const [inPlay,       setInPlay]       = useState<InPlayResponse | null>(null);
  const [holeScores,   setHoleScores]   = useState<HoleScoresResponse | null>(null);
  const [vsData,       setVsData]       = useState<VsPredPlayer[] | null>(null);
  const [lineupData,   setLineupData]   = useState<MyLineupResponse | null>(null);
  const [sgData,       setSgData]       = useState<SgStatsResponse | null>(null);
  const [sgRound,      setSgRound]      = useState("event_avg");
  const [holeStatsData, setHoleStatsData] = useState<HoleStatsResponse | null>(null);
  const [loadingHoles,  setLoadingHoles]  = useState(false);

  const [myPicks,       setMyPicks]       = useState<string[]>([]);
  const [wds,           setWds]           = useState<WithdrawalsResponse | null>(null);
  const [pulse,         setPulse]         = useState<LivePulseData | null>(null);
  const [pulseLoading,  setPulseLoading]  = useState(false);
  const [pulseError,    setPulseError]    = useState<string | null>(null);

  const [loadingLb,     setLoadingLb]     = useState(true);
  const [refreshing,    setRefreshing]    = useState(false);
  const [loadingVs,     setLoadingVs]     = useState(false);
  const [loadingLineup, setLoadingLineup] = useState(false);
  const [loadingSg,     setLoadingSg]     = useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const [lastPollAt,    setLastPollAt]    = useState<Date | null>(null);
  const [nextPollIn,    setNextPollIn]    = useState<number>(POLL_INTERVAL_MS / 1000);

  const pollTimer  = useRef<ReturnType<typeof setInterval> | null>(null);
  const countTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Leaderboard fetch (called on mount + every 60s) ──────────────────────────
  const fetchLeaderboard = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const [ip, hs] = await Promise.all([getInPlay(), getHoleScores()]);
      setInPlay(ip);
      setHoleScores(hs);
      setLastPollAt(new Date());
      setNextPollIn(POLL_INTERVAL_MS / 1000);
      // On manual refresh, kick off a background hole-scores scrape
      // (takes ~30s; the next auto-poll will pick up the results)
      if (!silent) refreshHoleScores().catch(() => {});
    } catch {
      // silently ignore poll errors to avoid flashing the error screen
    } finally {
      setRefreshing(false);
    }
  }, []);

  // ── Initial load: settings + tournament header + in-play leaderboard ────────
  useEffect(() => {
    async function load() {
      try {
        const [t, ip, hs, settings] = await Promise.all([
          getTournament(), getInPlay(), getHoleScores(), getSettings(),
        ]);
        getWithdrawals().then(setWds).catch(() => {});
        getLineup().then(l => {
          if (l.confirmed) setMyPicks(l.picks.map(p => p.player_name));
        }).catch(() => {});
        setTournament(t);
        setInPlay(ip);
        setHoleScores(hs);
        setLastPollAt(new Date());
        // Apply saved default tab and SG round from settings
        const defaultTab = (settings.live?.default_tab ?? "leaderboard") as Tab;
        if (TABS.some(t => t.id === defaultTab)) {
          setActiveTab(defaultTab);
          setLoaded(prev => new Set([...prev, defaultTab]));
        }
        const defaultSgRound = settings.live?.default_sg_round ?? "event_avg";
        setSgRound(defaultSgRound);
        setSettingsLoaded(true);
      } catch {
        setError("Could not connect to the API. Is FastAPI running on port 8000?");
      } finally {
        setLoadingLb(false);
      }
    }
    load();

    // Auto-poll every 60 seconds
    pollTimer.current = setInterval(() => fetchLeaderboard(true), POLL_INTERVAL_MS);

    // Countdown ticker (every second)
    countTimer.current = setInterval(() => {
      setNextPollIn(prev => (prev <= 1 ? POLL_INTERVAL_MS / 1000 : prev - 1));
    }, 1000);

    return () => {
      if (pollTimer.current)  clearInterval(pollTimer.current);
      if (countTimer.current) clearInterval(countTimer.current);
    };
  }, [fetchLeaderboard]);

  // ── Lazy load: vs predictions ────────────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("vspred") || vsData) return;
    setLoadingVs(true);
    getVsPredictions().then(d => setVsData(d.players)).finally(() => setLoadingVs(false));
  }, [loaded]);

  // ── Lazy load: my lineup ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("mylineup") || lineupData) return;
    setLoadingLineup(true);
    getMyLineupLive().then(setLineupData).finally(() => setLoadingLineup(false));
  }, [loaded]);

  // ── Lazy load: SG stats (also re-fetches when round selector changes) ────────
  useEffect(() => {
    if (!loaded.has("sg")) return;
    setLoadingSg(true);
    getSgStats(sgRound).then(setSgData).finally(() => setLoadingSg(false));
  }, [loaded, sgRound]);

  // ── Lazy load: hole stats ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!loaded.has("holes") || holeStatsData) return;
    setLoadingHoles(true);
    getHoleStats().then(setHoleStatsData).finally(() => setLoadingHoles(false));
  }, [loaded]);

  function handleRoundChange(r: string) {
    setSgRound(r);
    setSgData(null); // clear so effect re-fetches
  }

  async function fetchPulse(force = false) {
    setPulseLoading(true);
    setPulseError(null);
    try {
      const p = await getLivePulse(force);
      setPulse(p);
    } catch (e: unknown) {
      setPulseError(e instanceof Error ? e.message : "Could not generate pulse.");
    } finally {
      setPulseLoading(false);
    }
  }

  // ── Error screen ──────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div style={{ maxWidth: 600, margin: "40px auto", padding: 24, background: "rgba(224,85,85,0.10)", border: "1px solid rgba(224,85,85,0.35)", borderRadius: 10, color: "var(--negative)" }}>
        <strong>Error</strong>
        <p style={{ margin: "8px 0 0", color: "var(--negative)", fontSize: "0.9em" }}>{error}</p>
      </div>
    );
  }

  const currentRound = inPlay?.current_round ?? null;
  const leader = inPlay?.players?.[0] ?? null;

  if (tour === "euro") {
    return (
      <div className="page-wrap">
        <AlertBanner />
        <PageHead kicker="DP World Tour" title="Live" />
        <TourPills tour={tour} setTour={setTour} />
        <EuroLiveView />
      </div>
    );
  }

  return (
    <div className="page-wrap">
      <AlertBanner />

      {/* ── Tournament header ────────────────────────────────────────────── */}
      <PageHead
        kicker={tournament
          ? [inPlay?.event_name || tournament.name,
             currentRound ? `Round ${currentRound}` : null,
             leader ? `Leader: ${leader.player_name} (${leader.total ?? "E"})` : null,
            ].filter(Boolean).join(" · ")
          : "Loading tournament…"}
        title="Live"
        right={!loadingLb ? (
          <div style={{ textAlign: "right", flexShrink: 0 }}>
            <button
              onClick={() => fetchLeaderboard(false)}
              disabled={refreshing}
              style={{
                background: refreshing ? "transparent" : "var(--bc-yellow)",
                border: "1px solid var(--bc-yellow)", borderRadius: 4,
                color: refreshing ? "var(--bc-muted)" : "#081f14",
                padding: "9px 16px", fontSize: "0.72em", fontWeight: 900,
                textTransform: "uppercase", letterSpacing: "0.06em",
                cursor: refreshing ? "default" : "pointer", fontFamily: "inherit",
              }}
            >
              {refreshing ? "Refreshing…" : "Refresh Now"}
            </button>
            <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", marginTop: 4 }}>
              {lastPollAt && `Updated ${lastPollAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
              {lastPollAt && ` · next in ${nextPollIn}s`}
            </div>
          </div>
        ) : undefined}
      />

      <TourPills tour={tour} setTour={setTour} />

      {/* ── At-a-glance strip — only if in-play loaded ──────────────────── */}
      {inPlay && !loadingLb && inPlay.players.length > 0 && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          <GlanceCard label="Field Size" value={String(inPlay.count)} />
          {leader && (
            <GlanceCard
              label="Leader"
              value={leader.player_name}
              sub={leader.total ?? "E"}
            />
          )}
          {leader?.win_prob != null && (
            <GlanceCard
              label="Leader Win%"
              value={`${leader.win_prob.toFixed(1)}%`}
              sub="DG live"
            />
          )}
          {currentRound && <GlanceCard label="Round" value={String(currentRound)} />}
        </div>
      )}

      {/* ── Tab switcher ─────────────────────────────────────────────────── */}
      <SubTabs tabs={TABS} active={activeTab} onChange={activateTab} />

      {/* ── Tab content ──────────────────────────────────────────────────── */}

      {activeTab === "leaderboard" && (
        loadingLb ? <Spinner /> : inPlay ? (
          <>
            <LivePulse
              pulse={pulse}
              loading={pulseLoading}
              error={pulseError}
              onGenerate={() => fetchPulse(false)}
              onRefresh={() => fetchPulse(true)}
            />
            {wds && wds.count > 0 && (
              <div style={{
                marginBottom: 12, padding: "6px 12px",
                background: "#1a0a00", border: "1px solid #7a3a00",
                borderRadius: 6, fontSize: "0.8em", color: "var(--bc-orange)",
              }}>
                <span style={{ fontWeight: 700 }}>WD this week: </span>
                {wds.withdrawals.map(w => w.player_name).join(", ")}
              </div>
            )}
            <InPlayLeaderboard
              players={inPlay.players}
              currentRound={inPlay.current_round}
              lastUpdate={inPlay.last_update}
              holeScores={holeScores?.by_player}
              myPicks={myPicks}
            />
          </>
        ) : <Empty text="No leaderboard data. Tournament may not have started." />
      )}

      {activeTab === "vspred" && (
        loadingVs ? <Spinner /> : vsData ? (
          <VsPredictions players={vsData} myPicks={myPicks} />
        ) : <Empty text="No comparison data available." />
      )}

      {activeTab === "mylineup" && (
        loadingLineup ? <Spinner /> : lineupData ? (
          <MyLineupLive picks={lineupData.picks} tournament={lineupData.tournament} holeScores={holeScores?.by_player} />
        ) : <Empty text="No lineup found. Run the season strategy pipeline." />
      )}

      {activeTab === "sg" && (
        loadingSg ? <Spinner /> : sgData ? (
          <SgStatsTable
            players={sgData.players}
            roundParam={sgData.round_param}
            updated={sgData.updated}
            onRoundChange={handleRoundChange}
            holeScores={holeScores?.by_player}
            myPicks={myPicks}
          />
        ) : (
          <SgStatsTable
            players={[]}
            roundParam={sgRound}
            updated={null}
            onRoundChange={handleRoundChange}
            holeScores={holeScores?.by_player}
            myPicks={myPicks}
          />
        )
      )}

      {activeTab === "holes" && (
        loadingHoles ? <Spinner /> : holeStatsData ? (
          <HoleStatsTable
            holes={holeStatsData.holes}
            round={holeStatsData.round}
            updated={holeStatsData.updated}
          />
        ) : <Empty text="No hole stats available yet." />
      )}

    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

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

/** DPWT live leaderboard from the in-play snapshot — honest about its
 *  freshness (age + which round the scores cover come from the API,
 *  the same computation the assistant's context uses). */
type EuroLiveTab = "leaderboard" | "holes" | "scorecards";
const EURO_LIVE_TABS: { id: EuroLiveTab; label: string }[] = [
  { id: "leaderboard", label: "Leaderboard"  },
  { id: "holes",       label: "Hole by Hole" },
  { id: "scorecards",  label: "Scorecards"   },
];

function EuroLiveView() {
  const [eventName, setEventName] = useState("");
  const [data, setData] = useState<EuroLive | null>(null);
  const [holes, setHoles] = useState<HoleStatsResponse | null>(null);
  const [holeRound, setHoleRound] = useState("event_avg");
  const [tab, setTab] = useState<EuroLiveTab>("leaderboard");
  const [par, setPar] = useState<number | null>(null);
  const [cardSearch, setCardSearch] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    getHoleStats(holeRound, "euro").then(setHoles).catch(() => {});
  }, [holeRound]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    getOpenEvents().then(d => {
      const ev = (d.events ?? []).filter(e => e.tour === "euro")
        .find(e => !e.finished) ?? (d.events ?? []).filter(e => e.tour === "euro")[0];
      if (!ev) { setErr("No DP World Tour event this week."); return; }
      setEventName(ev.name);
      getEuroCourse(ev.tournament_id).then(c => setPar(c.par)).catch(() => {});
      const load = () => getEuroLive(ev.tournament_id).then(setData)
        .catch(() => setErr("Could not load the euro leaderboard."));
      load();
      // The server caches DG's feed for 5 min; polling at 2 keeps the
      // page within a couple minutes of it without extra DG calls.
      timer = setInterval(load, 120_000);
    }).catch(() => setErr("Could not load events."));
    return () => { if (timer) clearInterval(timer); };
  }, []);

  if (err) return <Empty text={err} />;
  if (!data) return <Spinner />;
  if (data.players.length === 0) {
    return <Empty text="No live scores yet — the first snapshot lands once play starts." />;
  }

  const fmtScore = (v: number | null) =>
    v == null ? "—" : v > 0 ? `+${v}` : v === 0 ? "E" : String(v);
  const age = data.snapshot_age_minutes;
  const ageStr = age == null ? "" : age < 90 ? `${age} min ago` : `${Math.round(age / 60)}h ago`;
  const isLiveFeed = data.source === "live";
  const coverage = isLiveFeed
    ? (data.current_round ? `Round ${data.current_round}` : "")
    : data.rounds_complete
      ? `scores through R${data.rounds_complete}${data.rounds_complete < 4 ? ` · R${data.rounds_complete + 1} may be underway` : " · final"}`
      : "";
  const th: React.CSSProperties = {
    padding: "7px 12px", borderBottom: "1px solid var(--bc-line)", fontSize: "0.68em",
    fontWeight: 700, color: "var(--bc-muted)", textTransform: "uppercase",
    letterSpacing: "0.05em", whiteSpace: "nowrap", textAlign: "right",
  };
  const td: React.CSSProperties = {
    padding: "6px 12px", borderBottom: "1px solid var(--bc-card)",
    fontSize: "0.85em", textAlign: "right", fontVariantNumeric: "tabular-nums",
  };

  return (
    <>
    <SubTabs tabs={EURO_LIVE_TABS} active={tab} onChange={setTab} />
    {tab === "leaderboard" && (
    <div style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "14px 18px 6px", fontWeight: 800 }}>
        {eventName}
        <span style={{ color: isLiveFeed ? "var(--bc-green)" : "var(--bc-muted)", fontWeight: isLiveFeed ? 700 : 400, fontSize: "0.72em", marginLeft: 8 }}>
          {isLiveFeed ? `LIVE · updated ${age === 0 ? "just now" : ageStr}` : `snapshot ${ageStr}`}
          {coverage ? ` · ${coverage}` : ""}
        </span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={{ ...th, textAlign: "center", width: 46 }}>Pos</th>
            <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
            <th style={th}>Total</th>
            <th style={th}>Today</th>
            <th style={th}>Thru</th>
            <th style={th}>R1</th><th style={th}>R2</th><th style={th}>R3</th><th style={th}>R4</th>
            <th style={th}>Pre-event win%</th>
          </tr></thead>
          <tbody>
            {data.players.map((p, i) => (
              <tr key={i}>
                <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "0.78em" }}>{p.position || "—"}</td>
                <td style={{ ...td, textAlign: "left", fontWeight: i < 3 ? 700 : 600 }}>{p.player_name}</td>
                <td style={{ ...td, fontWeight: 800,
                  color: (p.total ?? 0) < 0 ? "var(--bc-green)" : (p.total ?? 0) > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                  {fmtScore(p.total)}
                </td>
                <td style={{ ...td, color: "var(--bc-muted)" }}>{fmtScore(p.today)}</td>
                <td style={{ ...td, color: "var(--bc-muted)" }}>{p.thru || "—"}</td>
                {p.rounds.map((r, ri) => (
                  <td key={ri} style={{ ...td, color: "var(--bc-muted)" }}>{r != null ? Math.round(r) : "—"}</td>
                ))}
                <td style={{ ...td, color: "var(--bc-yellow)", fontSize: "0.8em" }}>
                  {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    )}

    {tab === "holes" && (
      holes && holes.holes.length > 0 ? (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800 }}>{eventName}</span>
            <span style={{ color: "var(--bc-muted)", fontSize: "0.78em" }}>hole scoring by round</span>
            <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
              {["event_avg", "1", "2", "3", "4"].map(r => (
                <button key={r} onClick={() => setHoleRound(r)} style={{
                  background: holeRound === r ? "#0a1f3a" : "var(--bc-panel)",
                  border: `1px solid ${holeRound === r ? "#1e5a3f" : "var(--bc-line)"}`,
                  borderRadius: 5, color: holeRound === r ? "var(--bc-green)" : "var(--bc-muted)",
                  padding: "4px 12px", fontSize: "0.76em", fontWeight: 700, cursor: "pointer",
                }}>{r === "event_avg" ? "Current" : `R${r}`}</button>
              ))}
            </div>
          </div>
          <HoleStatsTable holes={holes.holes} round={holes.round} updated={holes.updated} />
        </div>
      ) : <Empty text="Hole stats land once the round is underway." />
    )}

    {tab === "scorecards" && (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
          <input
            placeholder="Search player…"
            value={cardSearch}
            onChange={e => setCardSearch(e.target.value)}
            style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
              color: "var(--bc-text)", padding: "7px 12px", fontSize: "0.85em", outline: "none", width: 200 }}
          />
          <span style={{ color: "var(--bc-muted)", fontSize: "0.75em" }}>
            Round scores{par != null ? ` · par ${par}` : ""} — hole-level detail has no DP World Tour source,
            so these are round cards, not hole cards.
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 12 }}>
          {data.players
            .filter(p => p.player_name.toLowerCase().includes(cardSearch.toLowerCase()))
            .map((p, i) => (
              <div key={i} style={{ background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 8, padding: "12px 14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9em" }}>{p.player_name}</span>
                  <span style={{ fontWeight: 800, fontSize: "0.9em", fontVariantNumeric: "tabular-nums",
                    color: (p.total ?? 0) < 0 ? "var(--bc-green)" : (p.total ?? 0) > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                    {p.position || "—"} · {fmtScore(p.total)}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {p.rounds.map((r, ri) => {
                    const vs = r != null && par != null ? Math.round(r) - par : null;
                    return (
                      <div key={ri} style={{ flex: 1, textAlign: "center", borderRadius: 5, padding: "6px 0",
                        background: vs == null ? "var(--bc-panel)" : vs < 0 ? "#0a1e12" : vs > 0 ? "#1e0d0d" : "var(--bc-panel)",
                        border: `1px solid ${vs == null ? "var(--bc-line)" : vs < 0 ? "#1e5a3f" : vs > 0 ? "#5a2a2a" : "var(--bc-line)"}` }}>
                        <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase" }}>R{ri + 1}</div>
                        <div style={{ fontWeight: 800, fontSize: "0.92em", fontVariantNumeric: "tabular-nums",
                          color: vs == null ? "var(--bc-muted)" : vs < 0 ? "var(--bc-green)" : vs > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                          {r != null ? Math.round(r) : "—"}
                        </div>
                      </div>
                    );
                  })}
                </div>
                {p.thru && p.thru !== "—" && p.today != null && (
                  <div style={{ marginTop: 6, fontSize: "0.72em", color: "var(--bc-muted)" }}>
                    today {fmtScore(p.today)} · thru {p.thru}
                  </div>
                )}
              </div>
            ))}
        </div>
      </div>
    )}
    </>
  );
}

function GlanceCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 140px", minWidth: 120,
    }}>
      <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1em", fontWeight: 700, color: "var(--bc-text)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", marginTop: 2 }}>{sub}</div>}
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
