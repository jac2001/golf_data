"use client";

import { Show, useAuth } from "@clerk/nextjs";
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
  const color      = MARKET_COLORS[bet.market] ?? "var(--bc-muted)";
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
    if (bet.confidence >= 0.80) return { confLabel: "HIGH",     confColor: "var(--bc-green)" };
    if (bet.confidence >= 0.70) return { confLabel: "MODERATE", confColor: "var(--bc-orange)" };
    return                             { confLabel: "LEAN",     confColor: "var(--bc-muted)" };
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

  const [tailed, setTailed]   = useState(false);
  const [tailing, setTailing] = useState(false);
  const { getToken } = useAuth();

  // "Tail" = the Friends Game version of Track: logs this bet against YOUR
  // account (Neon), graded later by the honest ledger.
  async function handleTail() {
    if (tailing || !bet.recommendation_id) return;
    setTailing(true);
    try {
      const token = await getToken();
      const res = await fetch("/api/friends/tail", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          recommendation_id: bet.recommendation_id,
          tournament_id:     bet.tournament_id ?? "",
          bet_label:         bet.selection_label ?? bet.player_name,
          odds_american:     bet.odds_american,
          stake_units:       1.0,
        }),
      });
      const d = await res.json();
      if (!d.error) setTailed(!!d.tailed);
    } catch { /* leave button as-is */ } finally {
      setTailing(false);
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
      background: isPick ? "#060e09" : "var(--bc-panel)",
      borderTop: isPick ? "1px solid color-mix(in srgb, var(--bc-green) 20%, transparent)" : "1px solid var(--bc-line)",
      borderRight: isPick ? "1px solid color-mix(in srgb, var(--bc-green) 20%, transparent)" : "1px solid var(--bc-line)",
      borderBottom: isPick ? "1px solid color-mix(in srgb, var(--bc-green) 20%, transparent)" : "1px solid var(--bc-line)",
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
              fontSize: "0.65em", fontWeight: 700, color: "var(--bc-green)",
              background: "color-mix(in srgb, var(--bc-green) 15%, transparent)", padding: "2px 7px", borderRadius: 4,
              border: "1px solid color-mix(in srgb, var(--bc-green) 27%, transparent)",
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
              style={{ fontSize: "1.05em", fontWeight: 700, color: isPick ? "var(--bc-green)" : "var(--bc-text)", textDecoration: "none", whiteSpace: "nowrap" }}
              onMouseEnter={e => (e.currentTarget.style.color = "var(--bc-yellow)")}
              onMouseLeave={e => (e.currentTarget.style.color = isPick ? "var(--bc-green)" : "var(--bc-text)")}
            >
              {bet.player_name}
            </Link>
            {isPick && (
              <span style={{ fontSize: "0.58em", fontWeight: 800, color: "var(--bc-green)", background: "color-mix(in srgb, var(--bc-green) 15%, transparent)", border: "1px solid color-mix(in srgb, var(--bc-green) 27%, transparent)", borderRadius: 3, padding: "2px 5px", whiteSpace: "nowrap" }}>
                MY PICK
              </span>
            )}
          </div>
          {opponent && (
            <div style={{ fontSize: "0.80em", color: "var(--bc-muted)", marginTop: 3, fontWeight: 500 }}>
              vs{" "}
              <Link
                href={`/players?player=${encodeURIComponent(opponent)}`}
                style={{ color: "var(--bc-muted)", textDecoration: "none" }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--bc-yellow)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--bc-muted)")}
              >
                {opponent}
              </Link>
            </div>
          )}

          {/* ── Intel warning ── */}
          {bet.intel_warning && (
            <div style={{
              marginTop: 5, fontSize: "0.68em", fontWeight: 600,
              color: "var(--bc-orange)", background: "rgba(255,210,74,0.08)",
              border: "1px solid rgba(95,74,0,0.27)", borderRadius: 4,
              padding: "2px 7px", display: "inline-block",
            }}>
              ⚠ {bet.intel_warning}
            </div>
          )}

          {/* ── Live tournament context ── */}
          {bet.live_position && (() => {
            const isLeader = bet.live_position === "1" || bet.live_position === "T1";
            const scoreNum = bet.live_total ? parseFloat(bet.live_total) : null;
            const scoreColor = scoreNum != null && scoreNum < 0 ? "var(--bc-green)" : scoreNum != null && scoreNum > 0 ? "var(--bc-red)" : "var(--bc-text)";
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
                    color: isLeader ? "var(--bc-orange)" : "var(--bc-muted)",
                    background: isLeader ? "rgba(255,210,74,0.10)" : "var(--bc-panel)",
                    padding: "2px 8px", borderRadius: 4,
                    border: `1px solid ${isLeader ? "color-mix(in srgb, var(--bc-orange) 27%, transparent)" : "var(--bc-muted)"}`,
                  }}>
                    {bet.live_position}
                  </span>
                  <span style={{ fontSize: "0.82em", fontWeight: 700, color: scoreColor }}>
                    {bet.live_total ?? "E"}
                  </span>
                  {bet.live_thru && (
                    <span style={{ fontSize: "0.72em", color: "var(--bc-muted)" }}>
                      {bet.live_thru === "F" ? "Finished" : `thru ${bet.live_thru}`}
                    </span>
                  )}
                </div>
                {/* Round-by-round scores */}
                {rounds && (
                  <div style={{ fontSize: "0.68em", color: "var(--bc-muted)", letterSpacing: "0.03em" }}>
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
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--bc-card)" }}>

        {/* Model bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ color: "var(--bc-muted)", fontSize: "0.72em", width: 52, flexShrink: 0 }}>Model</span>
          <div style={{ flex: 1, background: "var(--bc-card)", borderRadius: 3, height: 5 }}>
            <div style={{ width: `${modelBar}%`, background: "var(--bc-green)", borderRadius: 3, height: 5 }} />
          </div>
          <span style={{ color: "var(--bc-green)", fontSize: "0.82em", fontWeight: 700, width: 46, textAlign: "right", flexShrink: 0 }}>
            {modelPct.toFixed(1)}%
          </span>
        </div>

        {/* Market bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ color: "var(--bc-muted)", fontSize: "0.72em", width: 52, flexShrink: 0 }}>Market</span>
          <div style={{ flex: 1, background: "var(--bc-card)", borderRadius: 3, height: 5 }}>
            <div style={{ width: `${marketBar}%`, background: "var(--bc-yellow)", borderRadius: 3, height: 5 }} />
          </div>
          <span style={{ color: "var(--bc-yellow)", fontSize: "0.82em", fontWeight: 700, width: 46, textAlign: "right", flexShrink: 0 }}>
            {marketPct.toFixed(1)}%
          </span>
        </div>

        {/* Stats row: edge / EV / kelly */}
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <Stat label="Edge" value={bet.edge_pts != null ? `+${bet.edge_pts.toFixed(1)}pp` : "—"} color={color} />
          <Stat label="EV / $1" value={bet.ev_per_1 != null ? `$${bet.ev_per_1.toFixed(2)}` : "—"} color="var(--bc-green)" />
          {kellyDollar && (
            <Stat
              label="Kelly"
              value={`${((bet.kelly_fraction ?? 0) * 100).toFixed(1)}% · $${kellyDollar}`}
              color="var(--bc-orange)"
            />
          )}
        </div>
      </div>

      {/* ── Why? button + reason panel ── */}
      <div style={{ marginTop: 12, borderTop: "1px solid var(--bc-card)", paddingTop: 10 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleWhyClick}
            style={{
              background: "transparent",
              border: "1px solid var(--bc-line)",
              borderRadius: 5,
              color: reasonOpen ? "var(--bc-muted)" : "var(--bc-yellow)",
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
                border: `1px solid ${tracked ? "color-mix(in srgb, var(--bc-green) 27%, transparent)" : "var(--bc-line)"}`,
                borderRadius: 5,
                color: tracked ? "var(--bc-green)" : "var(--bc-muted)",
                fontSize: "0.75em",
                fontWeight: 600,
                padding: "4px 10px",
                cursor: tracked ? "default" : "pointer",
              }}
            >
              {tracking ? "Adding…" : tracked ? "Tracked ✓" : "Track Bet"}
            </button>
            {bet.recommendation_id && (
              <Show when="signed-in">
                <button
                  onClick={handleTail}
                  disabled={tailing}
                  title="Log this bet to your Friends Game record"
                  style={{
                    background: tailed ? "color-mix(in srgb, var(--bc-yellow) 12%, transparent)" : "transparent",
                    border: `1px solid ${tailed ? "color-mix(in srgb, var(--bc-yellow) 40%, transparent)" : "var(--bc-line)"}`,
                    borderRadius: 5,
                    color: tailed ? "var(--bc-yellow)" : "var(--bc-muted)",
                    fontSize: "0.75em",
                    fontWeight: 600,
                    padding: "4px 10px",
                    cursor: "pointer",
                  }}
                >
                  {tailing ? "…" : tailed ? "Tailed ✓" : "Tail"}
                </button>
              </Show>
            )}
        </div>

        {reasonOpen && (
          <div style={{ marginTop: 10, fontSize: "0.82em", lineHeight: 1.6, color: "var(--bc-muted)" }}>
            {reasonLoading
              ? <span style={{ color: "var(--bc-muted)" }}>Generating…</span>
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
      <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
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
          border: "1px solid var(--bc-line)",
          borderRadius: 5,
          color: open ? "var(--bc-muted)" : "var(--bc-orange)",
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
            <span style={{ fontSize: "0.8em", color: "var(--bc-muted)" }}>Loading…</span>
          ) : lines ? (
            <>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78em" }}>
                <thead>
                  <tr style={{ color: "var(--bc-muted)" }}>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "left" }}>Book</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Odds</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Implied</th>
                    <th style={{ paddingBottom: 4, fontWeight: 600, textAlign: "right" }}>Edge</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.lines.map((l, i) => {
                    const isBest = l.book === lines.best_book;
                    const edgeColor = l.edge_pp != null && l.edge_pp > 0 ? "var(--bc-green)"
                                    : l.edge_pp != null && l.edge_pp < 0 ? "var(--bc-red)"
                                    : "var(--bc-muted)";
                    return (
                      <tr key={i} style={{ borderTop: "1px solid var(--bc-card)" }}>
                        <td style={{ padding: "5px 0", color: isBest ? "var(--bc-orange)" : "var(--bc-muted)", fontWeight: isBest ? 700 : 400 }}>
                          {l.book}{isBest ? " ★" : ""}
                        </td>
                        <td style={{ textAlign: "right", color: isBest ? "var(--bc-orange)" : "var(--bc-text)", fontWeight: isBest ? 700 : 400 }}>
                          {l.odds_american}
                        </td>
                        <td style={{ textAlign: "right", color: "var(--bc-muted)" }}>
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
                <div style={{ fontSize: "0.68em", color: "var(--bc-muted)", marginTop: 6 }}>
                  DG updated {lines.last_updated}
                </div>
              )}
            </>
          ) : (
            <span style={{ fontSize: "0.8em", color: "var(--bc-red)" }}>No line data available.</span>
          )}
        </div>
      )}
    </div>
  );
}
