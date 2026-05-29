"use client";

import { useState, useEffect } from "react";
import {
  getMatchups, get3Ball, refreshDgOdds,
  MatchupsResponse, ThreeBallResponse,
} from "@/lib/api";

const BOOK_ABBR: Record<string, string> = {
  Draftkings: "DK", Fanduel: "FD", Bet365: "B365", Betmgm: "MGM",
  Caesars: "CZR", Pinnacle: "PIN", Unibet: "UNI", Bovada: "BOV",
  Betonline: "BOL", Betcris: "BCR",
};

export default function MatchupsTab() {
  const [subTab, setSubTab]         = useState<"tournament" | "round" | "3ball">("tournament");
  const [tournData, setTournData]   = useState<MatchupsResponse | null>(null);
  const [roundData, setRoundData]   = useState<MatchupsResponse | null>(null);
  const [threeBall, setThreeBall]   = useState<ThreeBallResponse | null>(null);
  const [loading, setLoading]       = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);
  const [search, setSearch]         = useState("");
  const [posEvOnly, setPosEvOnly]   = useState(false);

  // Load data when sub-tab changes
  useEffect(() => {
    setLoading(true);
    if (subTab === "tournament") {
      getMatchups("tournament", "", false)
        .then(setTournData)
        .finally(() => setLoading(false));
    } else if (subTab === "round") {
      getMatchups("round", "", false)
        .then(setRoundData)
        .finally(() => setLoading(false));
    } else {
      get3Ball()
        .then(setThreeBall)
        .finally(() => setLoading(false));
    }
  }, [subTab]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshErr(null);
    try {
      await refreshDgOdds();
      // Re-load whichever sub-tab is active
      setLoading(true);
      if (subTab === "tournament") {
        getMatchups("tournament", search, posEvOnly).then(setTournData).finally(() => setLoading(false));
      } else if (subTab === "round") {
        getMatchups("round", search, posEvOnly).then(setRoundData).finally(() => setLoading(false));
      } else {
        get3Ball().then(setThreeBall).finally(() => setLoading(false));
      }
    } catch {
      setRefreshErr("Refresh failed — check FastAPI logs.");
    } finally {
      setRefreshing(false);
    }
  }

  // Re-fetch tournament/round when search/filter changes (with debounce)
  useEffect(() => {
    if (subTab === "3ball") return;
    const t = setTimeout(() => {
      setLoading(true);
      getMatchups(subTab as "tournament" | "round", search, posEvOnly)
        .then(d => subTab === "tournament" ? setTournData(d) : setRoundData(d))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [search, posEvOnly, subTab]);

  const data = subTab === "tournament" ? tournData : subTab === "round" ? roundData : null;

  return (
    <div>
      {/* Sub-tab switcher */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {(["tournament", "round", "3ball"] as const).map(t => (
          <button key={t} onClick={() => setSubTab(t)} style={{
            background: subTab === t ? "#1e3a5f" : "transparent",
            border: `1px solid ${subTab === t ? "#2a4f7f" : "#1e3a5f"}`,
            borderRadius: 6, color: subTab === t ? "#dde6f5" : "#7f8c8d",
            padding: "6px 14px", fontSize: "0.85em", fontWeight: 600, cursor: "pointer",
          }}>
            {t === "tournament" ? "Tournament H2H" : t === "round" ? "Round H2H" : "3-Ball"}
          </button>
        ))}
      </div>

      {/* Filters (tournament + round only) */}
      {subTab !== "3ball" && (
        <div style={{
          display: "flex", gap: 12, alignItems: "center", marginBottom: 16,
          padding: "12px 14px", background: "#0d1a30",
          border: "1px solid #1e3a5f", borderRadius: 8,
        }}>
          <input
            placeholder="Search player…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={inputStyle}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: "#8ba0b8", fontSize: "0.85em" }}>
            <input
              type="checkbox"
              checked={posEvOnly}
              onChange={e => setPosEvOnly(e.target.checked)}
              style={{ accentColor: "#00c44f" }}
            />
            Positive EV only
          </label>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
            {(data?.updated) && (
              <span style={{ color: "#4a6080", fontSize: "0.75em" }}>
                Updated: {data.updated}
              </span>
            )}
            <button onClick={handleRefresh} disabled={refreshing} style={btnStyle}>
              {refreshing ? "Refreshing…" : "Refresh Odds"}
            </button>
          </div>
        </div>
      )}

      {refreshErr && (
        <div style={{ color: "#e74c3c", fontSize: "0.78em", marginBottom: 8 }}>{refreshErr}</div>
      )}

      {/* 3-ball refresh bar */}
      {subTab === "3ball" && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button onClick={handleRefresh} disabled={refreshing} style={btnStyle}>
            {refreshing ? "Refreshing…" : "Refresh Odds"}
          </button>
        </div>
      )}

      {loading && <div style={{ color: "#7f8c8d", padding: 24, textAlign: "center" }}>Loading…</div>}

      {/* Tournament / Round matchup table */}
      {!loading && subTab !== "3ball" && data && (
        data.matchups.length === 0
          ? <EmptyState text="No matchups found. Try removing filters or fetching latest data." />
          : <MatchupTable data={data} />
      )}

      {/* 3-Ball pairings */}
      {!loading && subTab === "3ball" && threeBall && (
        threeBall.pairings.length === 0
          ? <EmptyState text="No 3-ball pairings available. Run fetch_dg_matchups.py to populate." />
          : <ThreeBallTable data={threeBall} />
      )}
    </div>
  );
}

// ── Matchup table ─────────────────────────────────────────────────────────────

function MatchupTable({ data }: { data: MatchupsResponse }) {
  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    whiteSpace: "nowrap",
  };

  const BOOKS_SHOW = data.books.slice(0, 6);

  return (
    <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "left" }}>Player 1</th>
            <th style={{ ...th, textAlign: "center", color: "#4cb8ff" }}>DG%</th>
            {BOOKS_SHOW.map(b => (
              <th key={`h-p1-${b}`} style={{ ...th, textAlign: "center" }}>
                {BOOK_ABBR[b] ?? b.slice(0, 3)}
              </th>
            ))}
            <th style={{ ...th, textAlign: "center", color: "#3a5060" }}>vs</th>
            <th style={{ ...th, textAlign: "left" }}>Player 2</th>
            <th style={{ ...th, textAlign: "center", color: "#4cb8ff" }}>DG%</th>
            {BOOKS_SHOW.map(b => (
              <th key={`h-p2-${b}`} style={{ ...th, textAlign: "center" }}>
                {BOOK_ABBR[b] ?? b.slice(0, 3)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.matchups.map((m, i) => {
            const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
            const td: React.CSSProperties = { padding: "6px 10px", borderBottom: "1px solid #0f2236", background: bg };

            return (
              <tr key={`${m.p1}-${m.p2}`}>
                {/* P1 name */}
                <td style={{ ...td, color: "#dde6f5", fontWeight: 600, whiteSpace: "nowrap", fontSize: "0.85em" }}>{m.p1}</td>
                {/* DG P1 */}
                <td style={{ ...td, color: "#4cb8ff", fontWeight: 700, textAlign: "center", fontSize: "0.85em" }}>{m.dg_p1.toFixed(1)}%</td>
                {/* P1 odds per book */}
                {BOOKS_SHOW.map(b => {
                  const bk = m.books[b];
                  const ev = bk?.p1_ev;
                  const isPos = ev != null && ev > 0;
                  return (
                    <td key={`p1-${b}`} style={{ ...td, textAlign: "center" }}>
                      {bk ? (
                        <span style={{
                          color: isPos ? "#00c44f" : "#3a5060",
                          fontWeight: isPos ? 700 : 400,
                          fontSize: "0.82em",
                          background: isPos ? "rgba(0,196,79,0.12)" : "transparent",
                          padding: isPos ? "1px 5px" : undefined,
                          borderRadius: isPos ? 3 : undefined,
                        }}>
                          {bk.p1_odds ?? "—"}
                          {isPos && <span style={{ fontSize: "0.75em", display: "block", color: "#00c44f" }}>+{ev!.toFixed(1)}%</span>}
                        </span>
                      ) : <span style={{ color: "#1a3050" }}>—</span>}
                    </td>
                  );
                })}
                {/* vs */}
                <td style={{ ...td, color: "#1a3050", fontWeight: 900, textAlign: "center", fontSize: "0.75em" }}>vs</td>
                {/* P2 name */}
                <td style={{ ...td, color: "#dde6f5", fontWeight: 600, whiteSpace: "nowrap", fontSize: "0.85em" }}>{m.p2}</td>
                {/* DG P2 */}
                <td style={{ ...td, color: "#4cb8ff", fontWeight: 700, textAlign: "center", fontSize: "0.85em" }}>{m.dg_p2.toFixed(1)}%</td>
                {/* P2 odds per book */}
                {BOOKS_SHOW.map(b => {
                  const bk = m.books[b];
                  const ev = bk?.p2_ev;
                  const isPos = ev != null && ev > 0;
                  return (
                    <td key={`p2-${b}`} style={{ ...td, textAlign: "center" }}>
                      {bk ? (
                        <span style={{
                          color: isPos ? "#00c44f" : "#3a5060",
                          fontWeight: isPos ? 700 : 400,
                          fontSize: "0.82em",
                          background: isPos ? "rgba(0,196,79,0.12)" : "transparent",
                          padding: isPos ? "1px 5px" : undefined,
                          borderRadius: isPos ? 3 : undefined,
                        }}>
                          {bk.p2_odds ?? "—"}
                          {isPos && <span style={{ fontSize: "0.75em", display: "block", color: "#00c44f" }}>+{ev!.toFixed(1)}%</span>}
                        </span>
                      ) : <span style={{ color: "#1a3050" }}>—</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p style={{ color: "#4a6080", fontSize: "0.70em", padding: "6px 12px", margin: 0 }}>
        {data.matchups.length} matchups · DG% = DataGolf no-vig model probability · Green = positive EV
      </p>
    </div>
  );
}

// ── 3-Ball table ──────────────────────────────────────────────────────────────

function ThreeBallTable({ data }: { data: ThreeBallResponse }) {
  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    whiteSpace: "nowrap",
  };

  return (
    <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
      {data.updated && (
        <p style={{ color: "#4a6080", fontSize: "0.70em", padding: "6px 12px", margin: 0 }}>
          Updated: {data.updated}
        </p>
      )}
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "left" }}>Tee</th>
            <th style={{ ...th, textAlign: "left" }}>Player 1</th>
            <th style={{ ...th, textAlign: "center" }}>Odds</th>
            <th style={{ ...th, textAlign: "left" }}>Player 2</th>
            <th style={{ ...th, textAlign: "center" }}>Odds</th>
            <th style={{ ...th, textAlign: "left" }}>Player 3</th>
            <th style={{ ...th, textAlign: "center" }}>Odds</th>
          </tr>
        </thead>
        <tbody>
          {data.pairings.map((p, i) => {
            const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
            const td: React.CSSProperties = { padding: "6px 10px", borderBottom: "1px solid #0f2236", background: bg };
            return (
              <tr key={`${p.teetime}-${p.group}-${i}`}>
                <td style={{ ...td, color: "#4a6080", fontSize: "0.80em" }}>{p.teetime}</td>
                <td style={{ ...td, color: "#dde6f5", fontWeight: 600, fontSize: "0.85em" }}>{p.p1}</td>
                <td style={{ ...td, color: "#f39c12", fontWeight: 700, textAlign: "center", fontSize: "0.85em" }}>{p.p1_odds}</td>
                <td style={{ ...td, color: "#dde6f5", fontWeight: 600, fontSize: "0.85em" }}>{p.p2}</td>
                <td style={{ ...td, color: "#f39c12", fontWeight: 700, textAlign: "center", fontSize: "0.85em" }}>{p.p2_odds}</td>
                <td style={{ ...td, color: p.p3 ? "#8ba0b8" : "#1a3050", fontSize: "0.85em" }}>{p.p3 ?? "—"}</td>
                <td style={{ ...td, color: p.p3 ? "#f39c12" : "#1a3050", textAlign: "center", fontSize: "0.85em" }}>{p.p3_odds ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p style={{ color: "#4a6080", fontSize: "0.70em", padding: "6px 12px", margin: 0 }}>
        {data.pairings.length} pairings · Round {data.pairings[0]?.round ?? "—"}
      </p>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{
      padding: 24, textAlign: "center", color: "#7f8c8d",
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10,
    }}>
      {text}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: "#1e3a5f", border: "1px solid #2a4f7f", borderRadius: 6,
  color: "#dde6f5", padding: "6px 14px", fontSize: "0.82em",
  fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap",
};

const inputStyle: React.CSSProperties = {
  background: "#0a1525", border: "1px solid #1e3a5f", borderRadius: 6,
  color: "#dde6f5", padding: "6px 10px", fontSize: "0.85em",
  outline: "none", width: 200,
};
