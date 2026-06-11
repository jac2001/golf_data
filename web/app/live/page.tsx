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
  refreshHoleScores, getLivePulse, getHoleStats, getSettings, getWithdrawals,
  Tournament, InPlayResponse, VsPredPlayer, MyLineupResponse, SgStatsResponse, HoleScoresResponse,
  HoleStatsResponse, LivePulse as LivePulseData, WithdrawalsResponse,
} from "@/lib/api";
import InPlayLeaderboard from "@/components/InPlayLeaderboard";
import VsPredictions from "@/components/VsPredictions";
import MyLineupLive from "@/components/MyLineupLive";
import SgStatsTable from "@/components/SgStatsTable";
import HoleStatsTable from "@/components/HoleStatsTable";
import LivePulse from "@/components/LivePulse";
import AlertBanner from "@/components/AlertBanner";

type Tab = "leaderboard" | "vspred" | "mylineup" | "sg" | "holes";

const TABS: { key: Tab; label: string }[] = [
  { key: "leaderboard", label: "Leaderboard"    },
  { key: "vspred",      label: "vs Predictions" },
  { key: "mylineup",    label: "My Lineup"      },
  { key: "sg",          label: "Live SG Stats"  },
  { key: "holes",       label: "Hole Stats"     },
];

const POLL_INTERVAL_MS = 60_000; // refresh leaderboard every 60 seconds

export default function LivePage() {

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
        setTournament(t);
        setInPlay(ip);
        setHoleScores(hs);
        setLastPollAt(new Date());
        // Apply saved default tab and SG round from settings
        const defaultTab = (settings.live?.default_tab ?? "leaderboard") as Tab;
        if (TABS.some(t => t.key === defaultTab)) {
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
      <div style={{ maxWidth: 600, margin: "40px auto", padding: 24, background: "#1a0d0d", border: "1px solid #5f1e1e", borderRadius: 10, color: "#e74c3c" }}>
        <strong>Error</strong>
        <p style={{ margin: "8px 0 0", color: "#c0392b", fontSize: "0.9em" }}>{error}</p>
      </div>
    );
  }

  const currentRound = inPlay?.current_round ?? null;
  const leader = inPlay?.players?.[0] ?? null;

  return (
    <div className="page-wrap">
      <AlertBanner />

      {/* ── Tournament header ────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: "1.4em", fontWeight: 800, color: "#dde6f5", margin: 0 }}>
            Live
          </h1>
          {tournament ? (
            <p style={{ color: "#7f8c8d", fontSize: "0.88em", margin: "4px 0 0" }}>
              {inPlay?.event_name || tournament.name}
              {currentRound && ` · Round ${currentRound}`}
              {inPlay?.last_update && (
                <span style={{ color: "#4a6080", marginLeft: 6 }}>· DG {inPlay.last_update}</span>
              )}
              {leader && ` · Leader: ${leader.player_name} (${leader.total ?? "E"})`}
            </p>
          ) : (
            <p style={{ color: "#3a5060", fontSize: "0.85em", margin: "4px 0 0" }}>Loading tournament…</p>
          )}
        </div>

        {/* ── Refresh controls ──────────────────────────────────────────── */}
        {!loadingLb && (
          <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 20 }}>
            <button
              onClick={() => fetchLeaderboard(false)}
              disabled={refreshing}
              style={{
                background: refreshing ? "#0d1a30" : "#0a1f3a",
                border: "1px solid #1e3a5f", borderRadius: 6,
                color: refreshing ? "#4a6080" : "#00c44f",
                padding: "6px 14px", fontSize: "0.78em", fontWeight: 700,
                cursor: refreshing ? "default" : "pointer",
              }}
            >
              {refreshing ? "Refreshing…" : "Refresh Now"}
            </button>
            <div style={{ fontSize: "0.65em", color: "#3a5060", marginTop: 4 }}>
              {lastPollAt && `Updated ${lastPollAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
              {lastPollAt && ` · next in ${nextPollIn}s`}
            </div>
          </div>
        )}
      </div>

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
      <div className="tab-bar" style={{ marginBottom: 20, borderBottom: "1px solid #1e3a5f", paddingBottom: 0 }}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => activateTab(tab.key)}
            style={{
              background: "transparent",
              border: "none",
              borderBottom: `2px solid ${activeTab === tab.key ? "#00c44f" : "transparent"}`,
              color: activeTab === tab.key ? "#dde6f5" : "#7f8c8d",
              padding: "8px 16px",
              fontSize: "0.88em",
              fontWeight: activeTab === tab.key ? 700 : 500,
              cursor: "pointer",
              marginBottom: -1,
              transition: "color 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

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
                borderRadius: 6, fontSize: "0.8em", color: "#e09040",
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
            />
          </>
        ) : <Empty text="No leaderboard data. Tournament may not have started." />
      )}

      {activeTab === "vspred" && (
        loadingVs ? <Spinner /> : vsData ? (
          <VsPredictions players={vsData} />
        ) : <Empty text="No comparison data available." />
      )}

      {activeTab === "mylineup" && (
        loadingLineup ? <Spinner /> : lineupData ? (
          <MyLineupLive picks={lineupData.picks} tournament={lineupData.tournament} />
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
          />
        ) : (
          <SgStatsTable
            players={[]}
            roundParam={sgRound}
            updated={null}
            onRoundChange={handleRoundChange}
            holeScores={holeScores?.by_player}
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

function GlanceCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 140px", minWidth: 120,
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
