"use client";

import { useState } from "react";
import Link from "next/link";
import {
    Bet, fmtOdds, MARKET_COLORS, MARKET_LABELS, BOOK_ABBR,
    getBetReason, getBetLines, BetLinesResponse, addToBetSlip,
  } from "@/lib/api";

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

type Props = {
  bet: Bet;
  bankroll: number;
  myPicks?: string[];
};

export default function BetCard({ bet, bankroll, myPicks = [] }: Props) {
  const isPick     = new Set(myPicks.map(normName)).has(normName(bet.player_name));
  const color      = MARKET_COLORS[bet.market] ?? "#4a90d9";
  const marketLbl  = MARKET_LABELS[bet.market]  ?? bet.market;
  const bookLbl    = BOOK_ABBR[bet.book.toUpperCase()] ?? bet.book.slice(0, 3);
  const modelPct   = bet.model_prob * 100;
  const marketPct  = bet.book_prob  * 100;
  const probMax    = Math.max(modelPct, marketPct, 1);
  const modelBar   = Math.min(100, (modelPct / probMax) * 100);
  const marketBar  = Math.min(100, (marketPct / probMax) * 100);

  const kellyDollar = bet.kelly_fraction
    ? (bet.kelly_fraction * bankroll).toFixed(0)
    : null;

  const { confLabel, confColor } = (() => {
    if (bet.confidence >= 0.80) return { confLabel: "HIGH",     confColor: "#00c44f" };
    if (bet.confidence >= 0.70) return { confLabel: "MODERATE", confColor: "#f39c12" };
    return                             { confLabel: "LEAN",     confColor: "#7f8c8d" };
  })();

  // ── Why? state ────────────────────────────────────────────────────────────
  const [reason,        setReason]        = useState<string | null>(null);
  const [reasonLoading, setReasonLoading] = useState(false);
  const [reasonOpen,    setReasonOpen]    = useState(false);
  const [tracked,       setTracked]       = useState(false);
  const [tracking,      setTracking]      = useState(false);


  async function handleTrack() {
    if (tracked || tracking) return;
    setTracking(true);
    try {
      const res = await addToBetSlip({
        recommendation_id: bet.recommendation_id ?? null,
        tournament_id:     bet.tournament_id ?? "",
        player_name:       bet.player_name,
        market:            bet.market,
        selection_label:   bet.selection_label ?? bet.player_name,
        odds_american:     bet.odds_american,
        stake_units:       1.0,
      });
      if (res.ok || res.message?.includes("Already")) setTracked(true);
    } catch {
      // silently fail — don't disrupt the UI
    } finally {
      setTracking(false);
    }
  }

  const opponent = (() => {
    if (!bet.group_members || !bet.market.startsWith("h2h")) return undefined;
    const parts = bet.group_members.split("|").map(s => s.replace(/\s*\(.*?\)/, "").trim());
    return parts.find(p => !p.toLowerCase().startsWith(bet.player_name.split(",")[0].toLowerCase()));
  })();

  async function handleWhyClick() {
    if (reasonOpen && reason) { setReasonOpen(false); return; }
    setReasonOpen(true);
    if (reason) return;
    setReasonLoading(true);
    try {
      const data = await getBetReason(bet.player_name, bet.market, opponent);
      setReason(data.reason);
    } catch {
      setReason("Could not generate reason. Check the API.");
    } finally {
      setReasonLoading(false);
    }
  }

  return (
    <div style={{
      background: isPick ? "#060e09" : "#0d1a30",
      borderTop: isPick ? "1px solid #00c44f33" : "1px solid #1e3a5f",
      borderRight: isPick ? "1px solid #00c44f33" : "1px solid #1e3a5f",
      borderBottom: isPick ? "1px solid #00c44f33" : "1px solid #1e3a5f",
      borderLeft: `4px solid ${color}`,
      borderRadius: 10,
      padding: "16px 18px",
      marginBottom: 12,
    }}>

      {/* ── Header row: badges + odds ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
          <div style={{ marginBottom: 5, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{
              fontSize: "0.65em", fontWeight: 700, color: "#00c44f",
              background: "#0d2e18", padding: "2px 7px", borderRadius: 4,
              border: "1px solid #00c44f44",
            }}>
              {bookLbl}
            </span>
            <span style={{ fontSize: "0.65em", fontWeight: 600, color, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {marketLbl}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Link
              href={`/players?player=${encodeURIComponent(bet.player_name)}`}
              style={{ fontSize: "1.05em", fontWeight: 700, color: isPick ? "#00c44f" : "#dde6f5", textDecoration: "none", whiteSpace: "nowrap" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
              onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : "#dde6f5")}
            >
              {bet.player_name}
            </Link>
            {isPick && (
              <span style={{ fontSize: "0.58em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", border: "1px solid #00c44f44", borderRadius: 3, padding: "2px 5px", whiteSpace: "nowrap" }}>
                MY PICK
              </span>
            )}
          </div>
          {opponent && (
            <div style={{ fontSize: "0.80em", color: "#6a8aaa", marginTop: 3, fontWeight: 500 }}>
              vs{" "}
              <Link
                href={`/players?player=${encodeURIComponent(opponent)}`}
                style={{ color: "#6a8aaa", textDecoration: "none" }}
                onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                onMouseLeave={e => (e.currentTarget.style.color = "#6a8aaa")}
              >
                {opponent}
              </Link>
            </div>
          )}

          {/* ── Intel warning ── */}
          {bet.intel_warning && (
            <div style={{
              marginTop: 5, fontSize: "0.68em", fontWeight: 600,
              color: "#f39c12", background: "#1a1200",
              border: "1px solid #5f4a0044", borderRadius: 4,
              padding: "2px 7px", display: "inline-block",
            }}>
              ⚠ {bet.intel_warning}
            </div>
          )}

          {/* ── Live tournament context ── */}
          {bet.live_position && (() => {
            const isLeader = bet.live_position === "1" || bet.live_position === "T1";
            const scoreNum = bet.live_total ? parseFloat(bet.live_total) : null;
            const scoreColor = scoreNum != null && scoreNum < 0 ? "#00c44f" : scoreNum != null && scoreNum > 0 ? "#e74c3c" : "#dde6f5";
            const rounds = [
              bet.live_r1 && `R1 ${bet.live_r1}`,
              bet.live_r2 && `R2 ${bet.live_r2}`,
              bet.live_r3 && `R3 ${bet.live_r3}`,
            ].filter(Boolean).join("  ·  ");
            return (
              <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
                {/* Position + total + thru */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: "0.72em", fontWeight: 700,
                    color: isLeader ? "#f39c12" : "#8ba0b8",
                    background: isLeader ? "#2a1f00" : "#0d1e2e",
                    padding: "2px 8px", borderRadius: 4,
                    border: `1px solid ${isLeader ? "#f39c1244" : "#2a4060"}`,
                  }}>
                    {bet.live_position}
                  </span>
                  <span style={{ fontSize: "0.82em", fontWeight: 700, color: scoreColor }}>
                    {bet.live_total ?? "E"}
                  </span>
                  {bet.live_thru && (
                    <span style={{ fontSize: "0.72em", color: "#4a6080" }}>
                      {bet.live_thru === "F" ? "Finished" : `thru ${bet.live_thru}`}
                    </span>
                  )}
                </div>
                {/* Round-by-round scores */}
                {rounds && (
                  <div style={{ fontSize: "0.68em", color: "#4a6080", letterSpacing: "0.03em" }}>
                    {rounds}
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: "1.6em", fontWeight: 800, color, lineHeight: 1 }}>
            {fmtOdds(bet.odds_american)}
          </div>
          <span style={{
            fontSize: "0.68em", fontWeight: 700, color: confColor,
            background: "rgba(255,255,255,0.07)", padding: "2px 7px", borderRadius: 4,
          }}>
            {confLabel}
          </span>
        </div>
      </div>

      {/* ── Probability bars + stats ── */}
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #1a2537" }}>

        {/* Model bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ color: "#8ba0b8", fontSize: "0.72em", width: 52, flexShrink: 0 }}>Model</span>
          <div style={{ flex: 1, background: "#1a2537", borderRadius: 3, height: 5 }}>
            <div style={{ width: `${modelBar}%`, background: "#00c44f", borderRadius: 3, height: 5 }} />
          </div>
          <span style={{ color: "#00c44f", fontSize: "0.82em", fontWeight: 700, width: 46, textAlign: "right", flexShrink: 0 }}>
            {modelPct.toFixed(1)}%
          </span>
        </div>

        {/* Market bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ color: "#8ba0b8", fontSize: "0.72em", width: 52, flexShrink: 0 }}>Market</span>
          <div style={{ flex: 1, background: "#1a2537", borderRadius: 3, height: 5 }}>
            <div style={{ width: `${marketBar}%`, background: "#4cb8ff", borderRadius: 3, height: 5 }} />
          </div>
          <span style={{ color: "#4cb8ff", fontSize: "0.82em", fontWeight: 700, width: 46, textAlign: "right", flexShrink: 0 }}>
            {marketPct.toFixed(1)}%
          </span>
        </div>

        {/* Stats row: edge / EV / kelly */}
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <Stat label="Edge" value={bet.edge_pts != null ? `+${bet.edge_pts.toFixed(1)}pp` : "—"} color={color} />
          <Stat label="EV / $1" value={bet.ev_per_1 != null ? `$${bet.ev_per_1.toFixed(2)}` : "—"} color="#00c44f" />
          {kellyDollar && (
            <Stat
              label="Kelly"
              value={`${((bet.kelly_fraction ?? 0) * 100).toFixed(1)}% · $${kellyDollar}`}
              color="#f39c12"
            />
          )}
        </div>
      </div>

      {/* ── Why? button + reason panel ── */}
      <div style={{ marginTop: 12, borderTop: "1px solid #1a2537", paddingTop: 10 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleWhyClick}
            style={{
              background: "transparent",
              border: "1px solid #2a4f7f",
              borderRadius: 5,
              color: reasonOpen ? "#7f8c8d" : "#4cb8ff",
              fontSize: "0.75em",
              fontWeight: 600,
              padding: "4px 10px",
              cursor: "pointer",
            }}
          >
            {reasonOpen ? "Hide" : "Why this bet?"}
          </button>

          <LineShopButton player={bet.player_name} market={bet.market} />
            <button
              onClick={handleTrack}
              disabled={tracked || tracking}
              style={{
                background: tracked ? "#0c1f14" : "transparent",
                border: `1px solid ${tracked ? "#00c44f44" : "#2a4f7f"}`,
                borderRadius: 5,
                color: tracked ? "#00c44f" : "#8ba0b8",
                fontSize: "0.75em",
                fontWeight: 600,
                padding: "4px 10px",
                cursor: tracked ? "default" : "pointer",
              }}
            >
              {tracking ? "Adding…" : tracked ? "Tracked ✓" : "Track Bet"}
            </button>
        </div>

        {reasonOpen && (
          <div style={{ marginTop: 10, fontSize: "0.82em", lineHeight: 1.6, color: "#b0c4d8" }}>
            {reasonLoading
              ? <span style={{ color: "#4a6080" }}>Generating…</span>
              : reason}
          </div>
        )}
      </div>

    </div>
  );
}

// ── Stat helper ───────────────────────────────────────────────────────────────

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div style={{ fontSize: "0.65em", color: "#7f8c8d", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </div>
      <div style={{ fontSize: "1em", fontWeight: 800, color }}>{value}</div>
    </div>
  );
}

// ── Line Shop ─────────────────────────────────────────────────────────────────

function LineShopButton({ player, market }: { player: string; market: string }) {
  const [lines,   setLines]   = useState<BetLinesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [open,    setOpen]    = useState(false);

  const supported = ["outright", "top5", "top10", "top20", "make_cut"].includes(market);
  if (!supported) return null;

  async function handleOpen() {
    if (open && lines) { setOpen(false); return; }
    setOpen(true);
    if (lines) return;
    setLoading(true);
    try {
      setLines(await getBetLines(player, market));
    } catch {
      setLines(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        onClick={handleOpen}
        style={{
          background: "transparent",
          border: "1px solid #2a4f7f",
          borderRadius: 5,
          color: open ? "#7f8c8d" : "#f39c12",
          fontSize: "0.75em",
          fontWeight: 600,
          padding: "4px 10px",
          cursor: "pointer",
        }}
      >
        {open ? "Hide" : "Line Shop"}
      </button>

      {open && (
        <div style={{ marginTop: 10 }}>
          {loading ? (
            <span style={{ fontSize: "0.8em", color: "#4a6080" }}>Loading…</span>
          ) : lines ? (
            <>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78em" }}>
                <thead>
                  <tr style={{ color: "#4a6080" }}>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "left" }}>Book</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Odds</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Implied</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Edge</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.lines.map((l, i) => {
                    const isBest = l.book === lines.best_book;
                    const edgeColor = l.edge_pp != null && l.edge_pp > 0 ? "#00c44f"
                                    : l.edge_pp != null && l.edge_pp < 0 ? "#e74c3c"
                                    : "#7f8c8d";
                    return (
                      <tr key={i} style={{ borderTop: "1px solid #1a2537" }}>
                        <td style={{ padding: "5px 0", color: isBest ? "#f39c12" : "#8ba0b8", fontWeight: isBest ? 700 : 400 }}>
                          {l.book}{isBest ? " ★" : ""}
                        </td>
                        <td style={{ textAlign: "right", color: isBest ? "#f39c12" : "#dde6f5", fontWeight: isBest ? 700 : 400 }}>
                          {l.odds_american}
                        </td>
                        <td style={{ textAlign: "right", color: "#8ba0b8" }}>
                          {(l.implied_prob * 100).toFixed(1)}%
                        </td>
                        <td style={{ textAlign: "right", color: edgeColor }}>
                          {l.edge_pp != null ? `${l.edge_pp > 0 ? "+" : ""}${l.edge_pp.toFixed(1)}pp` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {lines.last_updated && (
                <div style={{ fontSize: "0.68em", color: "#3a5060", marginTop: 6 }}>
                  DG updated {lines.last_updated}
                </div>
              )}
            </>
          ) : (
            <span style={{ fontSize: "0.8em", color: "#e74c3c" }}>No line data available.</span>
          )}
        </div>
      )}
    </div>
  );
}
