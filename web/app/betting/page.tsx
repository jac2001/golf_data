/**
 * app/betting/page.tsx — Value Bets page
 * ========================================
 * Because this file is at app/betting/page.tsx, Next.js automatically
 * serves it at the URL /betting. No router config needed.
 *
 * "use client" makes this a Client Component, which means it runs in
 * the browser and can use React state (useState) and side effects (useEffect).
 * Without it, the component runs on the server and can't handle user interaction.
 *
 * State in React is like a variable that, when changed, causes the UI to
 * re-render automatically — similar to how Streamlit reruns on interaction,
 * except only the affected component updates (not the whole page).
 */

"use client";

import { useState, useEffect } from "react";
import {
  getBets, getOddsComparison, getTournament, refreshBets, getExpertPicks, getBestBet, getLineup,
  Bet, OddsComparison, Tournament, MARKET_LABELS, ExpertPicksResponse, BestBet,
} from "@/lib/api";
import Link from "next/link";
import BetCard from "@/components/BetCard";
import BookTable from "@/components/BookTable";
import MatchupsTab from "@/components/MatchupsTab";
import OddsExplorer from "@/components/OddsExplorer";
import ExpertPicksTab from "@/components/ExpertPicksTab";

// Markets available as filter pills
const MARKET_PILLS: { key: string; label: string }[] = [
  { key: "all",         label: "All"      },
  { key: "top10",       label: "Top 10"   },
  { key: "top20",       label: "Top 20"   },
  { key: "top5",        label: "Top 5"    },
  { key: "make_cut",    label: "Make Cut" },
  { key: "h2h_r1",      label: "H2H R1"  },
  { key: "h2h_r2",      label: "H2H R2"  },
  { key: "h2h_r3",      label: "H2H R3"  },
  { key: "h2h_r4",      label: "H2H R4"  },
];

export default function BettingPage() {

  // ── State ──────────────────────────────────────────────────────────────────
  // useState(initialValue) returns [currentValue, setterFunction].
  // Calling the setter re-renders the component with the new value.
  const [activeTab, setActiveTab]     = useState<"bets" | "matchups" | "odds" | "expert">("bets");
  const [tournament, setTournament]   = useState<Tournament | null>(null);
  const [bets, setBets]               = useState<Bet[]>([]);
  const [oddsData, setOddsData]       = useState<OddsComparison | null>(null);
  const [market, setMarket]           = useState("all");
  const [minEdge, setMinEdge]         = useState(0);
  const [bankroll, setBankroll]       = useState(1000);
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);
  const [showTable, setShowTable]     = useState(false);
  const [tableMarket, setTableMarket] = useState("top10");
  const [expertData, setExpertData]   = useState<ExpertPicksResponse | null>(null);
  const [loadingExpert, setLoadingExpert] = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [bestBet, setBestBet]         = useState<BestBet | null>(null);
  const [myPicks, setMyPicks]         = useState<string[]>([]);

  // ── Data fetching ──────────────────────────────────────────────────────────
  // useEffect(fn, [deps]) runs `fn` after render, when any value in `deps` changes.
  // An empty array [] means "run once when the page first loads."
  useEffect(() => {
    async function load() {
      try {
        // Run all three API calls in parallel (like asyncio.gather in Python)
        const [t, b, o, bb] = await Promise.all([
          getTournament(),
          getBets("all", 0),
          getOddsComparison("top10"),
          getBestBet().catch(() => null),
        ]);
        setTournament(t);
        setBets(b.bets);
        setOddsData(o);
        if (bb?.available) setBestBet(bb);
        getLineup().then(l => {
          if (l.confirmed) setMyPicks(l.picks.map(p => p.player_name));
        }).catch(() => {});
      } catch (e) {
        setError("Could not connect to the API. Make sure FastAPI is running on port 8000.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []); // Empty deps = run once on mount

  // Re-fetch book table when tableMarket changes
  useEffect(() => {
    getOddsComparison(tableMarket).then(setOddsData).catch(() => {});
  }, [tableMarket]);

  // Lazy-load expert picks when tab first opened
  useEffect(() => {
    if (activeTab !== "expert" || expertData || loadingExpert) return;
    setLoadingExpert(true);
    getExpertPicks().then(setExpertData).catch(() => {}).finally(() => setLoadingExpert(false));
  }, [activeTab]);

  // ── Derived values (computed from state — like @property in Python) ────────
  const filteredBets = bets
    .filter((b) => market === "all" || b.market === market)
    .filter((b) => b.edge_pts != null && b.edge_pts >= minEdge)
    .sort((a, b) => b.edge_pts - a.edge_pts);

  // ── Handlers ──────────────────────────────────────────────────────────────
  async function handleRefresh() {
    setRefreshing(true);
    try {
      const result = await refreshBets();
      setBets(result.bets);
    } catch {
      setError("Refresh failed. Check the API logs.");
    } finally {
      setRefreshing(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  // Everything below is JSX — the HTML-like syntax React uses.
  // Conditional rendering: `{condition && <Element />}` = show if true.
  // List rendering: `{array.map(item => <Element key={item.id} />)}`.

  if (loading) return <LoadingScreen />;
  if (error)   return <ErrorScreen message={error} />;

  return (
    <div className="page-wrap-md">

      {/* ── Tournament header ── */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 800, color: "#dde6f5", margin: 0 }}>
          Value Bets
        </h1>
        {tournament && (
          <p style={{ color: "#7f8c8d", fontSize: "0.88em", margin: "4px 0 0" }}>
            {tournament.name}
            {tournament.current_round && ` · Round ${tournament.current_round}`}
            {tournament.leader_name && ` · Leader: ${tournament.leader_name}`}
            {tournament.leader_score != null && ` (${tournament.leader_score > 0 ? "+" : ""}${tournament.leader_score})`}
          </p>
        )}
      </div>

      {/* ── Tab switcher ── */}
      <div className="tab-bar" style={{ marginBottom: 24, borderBottom: "1px solid #1e3a5f", paddingBottom: 0 }}>
        {(["bets", "matchups", "odds", "expert"] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              background: "transparent",
              borderTop: "none", borderLeft: "none", borderRight: "none",
              borderBottom: `2px solid ${activeTab === tab ? "#00c44f" : "transparent"}`,
              color: activeTab === tab ? "#dde6f5" : "#7f8c8d",
              padding: "8px 16px",
              fontSize: "0.88em",
              fontWeight: activeTab === tab ? 700 : 500,
              cursor: "pointer",
              marginBottom: -1,
              transition: "color 0.15s",
            }}
          >
            {tab === "bets" ? "Value Bets" : tab === "matchups" ? "Matchups" : tab === "odds" ? "Odds Explorer" : "Expert Picks"}
          </button>
        ))}
      </div>

      {activeTab === "matchups" && <MatchupsTab />}
      {activeTab === "odds" && <OddsExplorer />}
      {activeTab === "expert" && (
        loadingExpert
          ? <div style={{ color: "#7f8c8d", padding: "40px 0", textAlign: "center" }}>Loading…</div>
          : expertData
            ? <ExpertPicksTab experts={expertData.experts} consensus={expertData.consensus} tournament={expertData.tournament} />
            : <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
                No expert picks available yet for this tournament.
              </div>
      )}

      {activeTab === "bets" && <>

      {/* ── Best Bet featured card ── */}
      {bestBet && <BestBetCard bet={bestBet} myPicks={myPicks} />}

      {/* ── Filter bar ── */}
      <div style={{
        marginBottom: 20, padding: "14px 16px",
        background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10,
      }}>
        {/* Market pills */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          {MARKET_PILLS.map(({ key, label }) => {
            const active = market === key;
            // Only show H2H round pills if there are bets for that market
            const hasBets = bets.some(b => b.market === key);
            if (key.startsWith("h2h_") && !hasBets) return null;
            return (
              <button
                key={key}
                onClick={() => setMarket(key)}
                style={{
                  padding: "5px 12px", borderRadius: 20, fontSize: "0.78em", fontWeight: 600,
                  cursor: "pointer", transition: "all 0.15s",
                  background: active ? "#00c44f" : "transparent",
                  color:      active ? "#000"    : "#8ba0b8",
                  border:     active ? "1px solid #00c44f" : "1px solid #2a4060",
                }}
              >
                {label}
                {key !== "all" && (
                  <span style={{ marginLeft: 5, opacity: 0.7, fontSize: "0.9em" }}>
                    {bets.filter(b => b.market === key).length || ""}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Second row: edge slider + bankroll + refresh */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <FilterGroup label={`Min Edge: ${minEdge.toFixed(1)}pp`}>
            <input
              type="range" min={0} max={8} step={0.5}
              value={minEdge}
              onChange={(e) => setMinEdge(Number(e.target.value))}
              style={{ width: 130, accentColor: "#00c44f" }}
            />
          </FilterGroup>

          <FilterGroup label="Bankroll ($)">
            <input
              type="number" min={100} max={100000} step={100}
              value={bankroll}
              onChange={(e) => setBankroll(Number(e.target.value))}
              style={{ ...selectStyle, width: 100 }}
            />
          </FilterGroup>

          <div style={{ flex: 1 }} />

          <button onClick={handleRefresh} disabled={refreshing} style={btnStyle}>
            {refreshing ? "Refreshing…" : "Refresh Bets"}
          </button>
        </div>
      </div>

      {/* ── Summary strip ── */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <Metric label="Recommendations" value={String(filteredBets.length)} />
        <Metric
          label="Avg Edge"
          value={filteredBets.length
            ? `${(filteredBets.reduce((s, b) => s + b.edge_pts, 0) / filteredBets.length).toFixed(1)}pp`
            : "—"}
        />
        <Metric
          label="Best Edge"
          value={filteredBets.length ? `+${filteredBets[0].edge_pts.toFixed(1)}pp` : "—"}
        />
        <Metric
          label="Avg EV / $1"
          value={filteredBets.length
            ? `$${(filteredBets.reduce((s, b) => s + b.ev_per_1, 0) / filteredBets.length).toFixed(2)}`
            : "—"}
        />
      </div>

      {/* ── Bet cards ── */}
      {filteredBets.length === 0 ? (
        <div style={{
          padding: "24px", textAlign: "center", color: "#7f8c8d",
          background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10,
          marginBottom: 20,
        }}>
          No bets meet the current filters. Try lowering the edge threshold or changing the market.
        </div>
      ) : (
        <div style={{ marginBottom: 24 }}>
          <SectionLabel>Singles · {filteredBets.length} bets</SectionLabel>
          {filteredBets.map((bet, i) => (
            <BetCard key={`${bet.player_name}-${bet.market}-${bet.book}-${i}`} bet={bet} bankroll={bankroll} myPicks={myPicks} />
          ))}
        </div>
      )}

      {/* ── Book comparison table ── */}
      <div style={{ marginBottom: 24 }}>
        {/* Toggle button */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: showTable ? 12 : 0 }}>
          <button
            onClick={() => setShowTable(!showTable)}
            style={{ ...btnStyle, background: showTable ? "#1e3a5f" : "transparent", fontSize: "0.85em" }}
          >
            {showTable ? "▲ Hide" : "▼ Show"} Book Comparison
          </button>

          {showTable && (
            <select
              value={tableMarket}
              onChange={(e) => setTableMarket(e.target.value)}
              style={{ ...selectStyle, fontSize: "0.85em" }}
            >
              {["top10", "top5", "top20", "outright"].map((m) => (
                <option key={m} value={m}>{MARKET_LABELS[m] ?? m}</option>
              ))}
            </select>
          )}

          {showTable && oddsData && (
            <span style={{ color: "#7f8c8d", fontSize: "0.78em" }}>
              {oddsData.players.length} players · {oddsData.books.length} books
            </span>
          )}
        </div>

        {showTable && oddsData && <BookTable data={oddsData} />}
      </div>

      </>}

    </div>
  );
}

// ── Small reusable components ─────────────────────────────────────────────────
// These are defined in the same file because they're only used here.
// If they were needed in multiple pages, they'd go in components/.

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: "0.70em", fontWeight: 700, color: "#7f8c8d",
      textTransform: "uppercase", letterSpacing: "0.08em",
      marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 16px", flex: "1 1 120px", minWidth: 100,
    }}>
      <div style={{ fontSize: "0.68em", color: "#7f8c8d", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1.1em", fontWeight: 700, color: "#dde6f5", marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: "0.68em", color: "#7f8c8d", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function LoadingScreen() {
  return (
    <div style={{ textAlign: "center", padding: 80, color: "#7f8c8d" }}>
      Loading…
    </div>
  );
}

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

function BestBetCard({ bet, myPicks = [] }: { bet: BestBet; myPicks?: string[] }) {
  const isPick = new Set(myPicks.map(normName)).has(normName(bet.player_name));
  return (
    <div style={{
      background: isPick ? "#040e09" : "#060f1a",
      borderTop: isPick ? "1px solid #00c44f55" : "1px solid #00c44f44",
      borderRight: isPick ? "1px solid #00c44f55" : "1px solid #00c44f44",
      borderBottom: isPick ? "1px solid #00c44f55" : "1px solid #00c44f44",
      borderLeft: "3px solid #00c44f",
      borderRadius: 10,
      padding: "16px 20px",
      marginBottom: 20,
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            fontSize: "0.62em", fontWeight: 800, color: "#00c44f",
            textTransform: "uppercase", letterSpacing: "0.12em",
            background: "#00c44f18", border: "1px solid #00c44f33",
            borderRadius: 4, padding: "2px 8px",
          }}>
            Best Bet
          </span>
          <span style={{ fontSize: "0.75em", color: "#5a7090" }}>
            {bet.tournament_name}
          </span>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <span style={{ fontSize: "0.78em", color: "#00c44f", fontWeight: 700 }}>
            +{bet.edge_pts.toFixed(1)}pp edge
          </span>
          <span style={{ fontSize: "0.78em", color: "#4cb8ff" }}>
            +{bet.ev_pct.toFixed(1)}% EV
          </span>
        </div>
      </div>

      {/* Bet details */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Link
          href={`/players?player=${encodeURIComponent(bet.player_name)}`}
          style={{ fontSize: "1.05em", fontWeight: 800, color: isPick ? "#00c44f" : "#dde6f5", textDecoration: "none" }}
          onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
          onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : "#dde6f5")}
        >
          {bet.player_name}
        </Link>
        {isPick && (
          <span style={{ fontSize: "0.58em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", border: "1px solid #00c44f44", borderRadius: 3, padding: "2px 5px" }}>
            MY PICK
          </span>
        )}
        <span style={{ fontSize: "0.88em", color: "#7f8c8d" }}>
          {bet.market_label} · {bet.odds_str} · {bet.book}
        </span>
      </div>

      {/* Reasoning */}
      {bet.reasoning && (
        <p style={{ margin: 0, fontSize: "0.84em", color: "#a0b8d0", lineHeight: 1.65 }}>
          {bet.reasoning}
        </p>
      )}
    </div>
  );
}

function ErrorScreen({ message }: { message: string }) {
  return (
    <div style={{
      maxWidth: 600, margin: "40px auto", padding: 24,
      background: "#1a0d0d", border: "1px solid #5f1e1e", borderRadius: 10,
      color: "#e74c3c",
    }}>
      <strong>Error</strong>
      <p style={{ margin: "8px 0 0", color: "#c0392b", fontSize: "0.9em" }}>{message}</p>
    </div>
  );
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const selectStyle: React.CSSProperties = {
  background: "#0a1525",
  border: "1px solid #1e3a5f",
  borderRadius: 6,
  color: "#dde6f5",
  padding: "6px 10px",
  fontSize: "0.88em",
  outline: "none",
};

const btnStyle: React.CSSProperties = {
  background: "#1e3a5f",
  border: "1px solid #2a4f7f",
  borderRadius: 6,
  color: "#dde6f5",
  padding: "7px 14px",
  fontSize: "0.88em",
  fontWeight: 600,
  cursor: "pointer",
};
