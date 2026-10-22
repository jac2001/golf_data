"use client";

/** Head-to-Head tab: two profiles side by side.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useState } from "react";
import Link from "next/link";
import { PlayerProfile, getPlayerProfile } from "@/lib/api";
import { BLUE, BORDER, CARD_BG, GREEN, LABEL, MUTED, TEXT, card, fmt, sectionLabel } from "./shared";
import { PlayerSelect } from "./PlayerPicker";


// ── Head-to-Head tab ─────────────────────────────────────────────────────────

export function H2HTab({ players }: { players: string[] }) {
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
        <div style={{ fontSize: "1.1em", fontWeight: 900, color: "var(--bc-line)", paddingTop: 22 }}>VS</div>
        <div>
          <div style={{ ...sectionLabel, marginBottom: 6 }}>Player 2</div>
          <PlayerSelect players={players} value={p2Name} onChange={handleP2} id="h2h-p2" placeholder="Select player 2…" />
        </div>
      </div>

      {(loadingP1 || loadingP2) && <p style={{ color: MUTED }}>Loading…</p>}

      {ready && <H2HView p1={p1!} p2={p2!} />}

      {!p1Name && !p2Name && (
        <div style={{ textAlign: "center", padding: "48px 0", color: LABEL, fontSize: "max(var(--fs-min), 0.88em)" }}>
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
          <span style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 900, color: "var(--bc-line)" }}>VS</span>
        </div>
        <H2HHeaderCard profile={p2} accent={BLUE} />
      </div>

      {/* Comparison grid */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>

        <H2HSection label="Model Predictions" />
        <H2HRow label="Win %" va={m1.win_prob != null ? m1.win_prob * 100 : null} vb={m2.win_prob != null ? m2.win_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Top 10 %" va={m1.top10_prob != null ? m1.top10_prob * 100 : null} vb={m2.top10_prob != null ? m2.top10_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Cut %" va={m1.cut_prob != null ? m1.cut_prob * 100 : null} vb={m2.cut_prob != null ? m2.cut_prob * 100 : null} fmt=".0f" suffix="%" higherBetter />
        <H2HRow label="Our edge vs market" va={m1.model_vs_vegas_edge != null ? m1.model_vs_vegas_edge * 100 : null} vb={m2.model_vs_vegas_edge != null ? m2.model_vs_vegas_edge * 100 : null} fmt="+.1f" suffix="pp" higherBetter />

        <H2HSection label="DG Model" />
        <H2HRow label="DG Win %" va={p1.dg_prediction?.win != null ? p1.dg_prediction.win * 100 : null} vb={p2.dg_prediction?.win != null ? p2.dg_prediction.win * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="DG Top 10 %" va={p1.dg_prediction?.top_10 != null ? p1.dg_prediction.top_10 * 100 : null} vb={p2.dg_prediction?.top_10 != null ? p2.dg_prediction.top_10 * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="DG Course-Adj Win%" va={p1.dg_prediction?.bhf_win != null ? p1.dg_prediction.bhf_win * 100 : null} vb={p2.dg_prediction?.bhf_win != null ? p2.dg_prediction.bhf_win * 100 : null} fmt=".1f" suffix="%" higherBetter />

        <H2HSection label="Season Form" />
        <H2HRow label="Season SG (our data)" va={m1.season_sg_total} vb={m2.season_sg_total} fmt="+.2f" higherBetter />
        <H2HRow label="Form Trend" va={m1.form_trend} vb={m2.form_trend} fmt="+.2f" higherBetter />
        <H2HRow label="World Rank" va={m1.world_rank} vb={m2.world_rank} fmt=".0f" higherBetter={false} prefix="#" />

        <H2HSection label="Skill Ratings (DG)" />
        <H2HRow label="Skill rating (DataGolf)" va={p1.skill_ratings?.total} vb={p2.skill_ratings?.total} fmt="+.2f" higherBetter />
        <H2HRow label="Off the Tee" va={p1.skill_ratings?.ott} vb={p2.skill_ratings?.ott} fmt="+.2f" higherBetter />
        <H2HRow label="Approach" va={p1.skill_ratings?.app} vb={p2.skill_ratings?.app} fmt="+.2f" higherBetter />
        <H2HRow label="Around Green" va={p1.skill_ratings?.arg} vb={p2.skill_ratings?.arg} fmt="+.2f" higherBetter />
        <H2HRow label="Putting" va={p1.skill_ratings?.putt} vb={p2.skill_ratings?.putt} fmt="+.2f" higherBetter />

        <H2HSection label="Course Fit" />
        <H2HRow label="Course fit (strokes/round)" va={p1.decompositions?.total_fit_adjustment} vb={p2.decompositions?.total_fit_adjustment} fmt="+.2f" higherBetter />
        <H2HRow label="Distance Adj." va={p1.decompositions?.driving_distance_adjustment} vb={p2.decompositions?.driving_distance_adjustment} fmt="+.3f" higherBetter />
        <H2HRow label="Timing Adj." va={p1.decompositions?.timing_adjustment} vb={p2.decompositions?.timing_adjustment} fmt="+.3f" higherBetter />

        <H2HSection label="PGA Tour Stats" />
        <H2HRow label="Season SG (PGA TOUR)" va={p1.betting_profile?.sg_total} vb={p2.betting_profile?.sg_total} fmt="+.2f" higherBetter />
        <H2HRow label="SG OTT" va={p1.betting_profile?.sg_ott} vb={p2.betting_profile?.sg_ott} fmt="+.2f" higherBetter />
        <H2HRow label="SG Approach" va={p1.betting_profile?.sg_app} vb={p2.betting_profile?.sg_app} fmt="+.2f" higherBetter />
        <H2HRow label="SG Putt" va={p1.betting_profile?.sg_putt} vb={p2.betting_profile?.sg_putt} fmt="+.2f" higherBetter />
        <H2HRow label="Drive Distance" va={p1.betting_profile?.driving_distance} vb={p2.betting_profile?.driving_distance} fmt=".1f" suffix=" yd" higherBetter />
        <H2HRow label="Season Wins" va={p1.betting_profile?.wins} vb={p2.betting_profile?.wins} fmt=".0f" higherBetter />
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
        <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: LABEL, marginBottom: 12 }}>
          {profile.player_name}
          {m.world_rank != null && ` · #${Math.round(m.world_rank)} World`}
        </div>
      </Link>
      <div style={{ display: "flex", justifyContent: "space-around", marginBottom: 10 }}>
        {[
          ["WIN", m.win_prob != null ? `${(m.win_prob * 100).toFixed(1)}%` : "—"],
          ["TOP 10", m.top10_prob != null ? `${(m.top10_prob * 100).toFixed(1)}%` : "—"],
          ["MAKES CUT", m.cut_prob != null ? `${(m.cut_prob * 100).toFixed(0)}%` : "—"],
        ].map(([lbl, val]) => (
          <div key={lbl}>
            <div style={{ fontSize: "1.35em", fontWeight: 800, color: accent }}>{val}</div>
            <div style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", color: LABEL, textTransform: "uppercase", letterSpacing: "0.08em" }}>{lbl}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {m.odds_to_win != null && (
          <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: MUTED }}>
            {m.odds_to_win >= 0 ? "+" : ""}{Math.round(m.odds_to_win)}
          </span>
        )}
      </div>
    </div>
  );
}


// ── H2H row helpers ───────────────────────────────────────────────────────────

function H2HSection({ label }: { label: string }) {
  return (
    <div style={{
      background: "var(--bc-panel)", padding: "6px 16px",
      fontSize: "max(var(--fs-min-xs), 0.65em)", fontWeight: 700, color: LABEL,
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

  const aColor = aWins ? GREEN : bWins ? "var(--bc-muted)" : TEXT;
  const bColor = bWins ? BLUE  : aWins ? "var(--bc-muted)" : TEXT;
  const barA   = aWins ? GREEN : "var(--bc-card)";
  const barB   = bWins ? BLUE  : "var(--bc-card)";

  return (
    <div>
      {/* Label row */}
      <div style={{
        textAlign: "center", fontSize: "max(var(--fs-min-xs), 0.65em)", color: "var(--bc-line)",
        textTransform: "uppercase", letterSpacing: "0.09em", paddingTop: 9,
      }}>
        {label}
      </div>
      {/* Value | bar | value */}
      <div style={{
        display: "grid", gridTemplateColumns: "auto 1fr auto",
        alignItems: "center", gap: 12, padding: "5px 20px 10px",
        borderBottom: `1px solid var(--bc-panel)`,
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
