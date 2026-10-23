"use client";

/** Head-to-Head tab: two profiles side by side.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { PlayerProfile, getPlayerProfile, getInPlay, type InPlayPlayer } from "@/lib/api";
import { GOLD, BORDER, CARD_BG, GREEN, MUTED, TEXT, card, fmt, sectionLabel, tint, Notice } from "./shared";
import { PlayerSelect } from "./PlayerPicker";
import { MISSING, fmtSigned } from "@/lib/format";
import { matchupVerdict, type Category } from "@/lib/matchupVerdict";
import { nameKey } from "@/lib/names";
import styles from "./players.module.css";



// ── Head-to-Head tab ─────────────────────────────────────────────────────────

export function H2HTab({ players }: { players: string[] }) {
  const [p1Name, setP1Name]     = useState("");
  const [p2Name, setP2Name]     = useState("");
  const [p1, setP1]             = useState<PlayerProfile | null>(null);
  const [p2, setP2]             = useState<PlayerProfile | null>(null);
  const [loadingP1, setLoadingP1] = useState(false);
  const [loadingP2, setLoadingP2] = useState(false);
  const [failed, setFailed]       = useState<string | null>(null);   // the golfer whose profile didn't load

  function load(name: string, which: 1 | 2) {
    const setLoading = which === 1 ? setLoadingP1 : setLoadingP2;
    const setData    = which === 1 ? setP1 : setP2;
    setLoading(true);
    setData(null);
    setFailed(null);
    getPlayerProfile(name).then(setData).catch(() => setFailed(name)).finally(() => setLoading(false));
  }

  function handleP1(name: string) { setP1Name(name); if (name) load(name, 1); }
  function handleP2(name: string) { setP2Name(name); if (name) load(name, 2); }

  const ready = p1 && p2 && !loadingP1 && !loadingP2;

  // This week's live board (PGA): "this week so far" and a suggested matchup.
  const [live, setLive] = useState<InPlayPlayer[] | null>(null);
  useEffect(() => {
    getInPlay().then(d => setLive(d.players ?? null)).catch(() => setLive(null));
  }, []);
  const suggest = (live ?? []).filter(p => players.includes(p.player_name)).slice(0, 2);

  return (
    <>
      {/* Two selectors */}
      <div className={styles.h2hPickers} style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 12, alignItems: "center", marginBottom: 24 }}>
        <div>
          <div style={{ ...sectionLabel, marginBottom: 6 }}>Player 1</div>
          <PlayerSelect players={players} value={p1Name} onChange={handleP1} id="h2h-p1" placeholder="Select player 1…" />
        </div>
        <div className={styles.h2hVs} style={{ fontSize: "1.1em", fontWeight: 900, color: "var(--bc-line)", paddingTop: 22 }}>VS</div>
        <div>
          <div style={{ ...sectionLabel, marginBottom: 6 }}>Player 2</div>
          <PlayerSelect players={players} value={p2Name} onChange={handleP2} id="h2h-p2" placeholder="Select player 2…" />
        </div>
      </div>

      {(loadingP1 || loadingP2) && <Notice kind="loading">Loading…</Notice>}
      {failed && <Notice kind="error">Couldn&apos;t load {failed}&apos;s profile. Pick the golfer again to retry.</Notice>}

      {ready && <H2HView p1={p1!} p2={p2!} live={live} />}

      {!p1Name && !p2Name && (
        <div style={{ textAlign: "center", padding: "40px 0", color: MUTED, fontSize: "max(var(--fs-min), 0.88em)" }}>
          Pick two golfers above to compare them.
          {suggest.length === 2 && (
            <div style={{ marginTop: 14 }}>
              <button onClick={() => { handleP1(suggest[0].player_name); handleP2(suggest[1].player_name); }} style={{
                cursor: "pointer", fontFamily: "inherit", fontWeight: 800, padding: "10px 16px", borderRadius: 8,
                background: "var(--bc-btn2-bg)", color: "var(--bc-btn2-fg)", border: "1px solid var(--bc-btn2-line)",
              }}>
                Try this week&apos;s top two: {suggest[0].player_name} vs {suggest[1].player_name}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}


// ── H2H view ──────────────────────────────────────────────────────────────────

function H2HView({ p1, p2, live }: { p1: PlayerProfile; p2: PlayerProfile; live: InPlayPlayer[] | null }) {
  const m1 = p1.our_model;
  const m2 = p2.our_model;
  const short = (n: string) => n.split(" ").slice(-1)[0];

  // The answer first (Jack's lib/matchupVerdict.ts), then the numbers.
  const sg = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
  const cats: Category[] = [
    { say: "better approach play", a: p1.skill_ratings?.app ?? null, b: p2.skill_ratings?.app ?? null, higherBetter: true, tie: 0.05, fmt: sg },
    { say: "better off the tee", a: p1.skill_ratings?.ott ?? null, b: p2.skill_ratings?.ott ?? null, higherBetter: true, tie: 0.05, fmt: sg },
    { say: "better around the green", a: p1.skill_ratings?.arg ?? null, b: p2.skill_ratings?.arg ?? null, higherBetter: true, tie: 0.05, fmt: sg },
    { say: "better putting", a: p1.skill_ratings?.putt ?? null, b: p2.skill_ratings?.putt ?? null, higherBetter: true, tie: 0.05, fmt: sg },
    { say: "better recent form", a: m1.form_trend ?? null, b: m2.form_trend ?? null, higherBetter: true, tie: 0.05, fmt: sg },
    { say: "longer off the tee", a: p1.betting_profile?.driving_distance ?? null, b: p2.betting_profile?.driving_distance ?? null,
      higherBetter: true, tie: 0.5, fmt: v => `${v.toFixed(1)} yd` },
    { say: "a better world rank", a: m1.world_rank ?? null, b: m2.world_rank ?? null, higherBetter: false, tie: 0.5, fmt: v => `#${Math.round(v)}` },
  ];
  let verdict = null;
  try {
    verdict = matchupVerdict(short(p1.player_name), short(p2.player_name),
      { a: m1.win_prob ?? null, b: m2.win_prob ?? null, tie: 0.002 }, cats);
  } catch { /* the table below still answers */ }

  // This week so far, from the live board (both golfers on it, or nothing).
  const board = new Map((live ?? []).map(p => [nameKey(p.player_name), p]));
  const l1 = board.get(nameKey(p1.player_name)), l2 = board.get(nameKey(p2.player_name));
  const toPar = (v: number | null) => v == null ? "" : v === 0 ? "E" : v > 0 ? `+${v}` : `−${Math.abs(v)}`;
  const liveLine = (n: string, p: InPlayPlayer) =>
    `${short(n)} ${p.position ?? ""} ${toPar(p.total_numeric)}${p.today != null ? ` (today ${toPar(p.today)})` : ""}`.replace(/\s+/g, " ").trim();

  return (
    <>
      {(verdict || (l1 && l2)) && (
        <div style={{ ...card, marginBottom: 16 }}>
          {l1 && l2 && (
            <div style={{ fontSize: "max(var(--fs-min), 0.86em)", color: MUTED, marginBottom: verdict ? 8 : 0 }}>
              <strong style={{ color: TEXT }}>This week so far:</strong> {liveLine(p1.player_name, l1)} · {liveLine(p2.player_name, l2)}
            </div>
          )}
          {verdict && <>
            <div style={{ fontWeight: 900, fontSize: "1.15em", lineHeight: 1.3 }}>{verdict.headline}</div>
            {verdict.reasons.length > 0 && (
              <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: MUTED, fontSize: "max(var(--fs-min), 0.88em)", lineHeight: 1.5 }}>
                {verdict.reasons.map(x => <li key={x}>{x}</li>)}
              </ul>
            )}
            {m1.win_prob != null && <div style={{ color: MUTED, fontSize: "max(var(--fs-min), 0.78em)", marginTop: 8 }}>
              Win chances are our pre-tournament numbers; skills are DataGolf&apos;s ratings.</div>}
          </>}
        </div>
      )}

      {/* Header cards (stacked on phones) */}
      <div className={styles.h2hCards} style={{ display: "grid", gridTemplateColumns: "1fr 48px 1fr", gap: 0, marginBottom: 20, alignItems: "stretch" }}>
        <H2HHeaderCard profile={p1} accent={GREEN} />
        <div className={styles.h2hVs} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 900, color: "var(--bc-line)" }}>VS</span>
        </div>
        <H2HHeaderCard profile={p2} accent={GOLD} />
      </div>

      {/* Every number, one tap away. */}
      <details>
      <summary style={{ cursor: "pointer", fontWeight: 800, margin: "4px 0 10px", fontSize: "max(var(--fs-min), 0.9em)" }}>
        Every number side by side
      </summary>
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>

        <H2HSection label="Model Predictions" />
        <H2HRow label="Win %" va={m1.win_prob != null ? m1.win_prob * 100 : null} vb={m2.win_prob != null ? m2.win_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Top 10 %" va={m1.top10_prob != null ? m1.top10_prob * 100 : null} vb={m2.top10_prob != null ? m2.top10_prob * 100 : null} fmt=".1f" suffix="%" higherBetter />
        <H2HRow label="Cut %" va={m1.cut_prob != null ? m1.cut_prob * 100 : null} vb={m2.cut_prob != null ? m2.cut_prob * 100 : null} fmt=".0f" suffix="%" higherBetter />

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

        <H2HSection label="This week's DataGolf adjustments" />
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
      </details>
    </>
  );
}


function H2HHeaderCard({ profile, accent }: { profile: PlayerProfile; accent: string }) {
  const m = profile.our_model;
  const isGreen = accent === GREEN;
  return (
    <div style={{
      background: CARD_BG, border: `1px solid ${tint(accent, 27)}`,
      borderRadius: 12, padding: "18px 16px", textAlign: "center",
    }}>
      <Link
        href={`/players?player=${encodeURIComponent(profile.player_name)}`}
        style={{ textDecoration: "none" }}
      >
        <div style={{ fontSize: "1.25em", fontWeight: 800, color: TEXT, marginBottom: 2 }}>
          {profile.player_name.split(" ").slice(-1)[0]}
        </div>
        <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: MUTED, marginBottom: 12 }}>
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
            <div style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", color: MUTED, textTransform: "uppercase", letterSpacing: "0.08em" }}>{lbl}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {m.odds_to_win != null && (
          <span style={{ fontSize: "max(var(--fs-min), 0.78em)", color: MUTED }}>
            Odds to win {m.odds_to_win >= 0 ? "+" : ""}{Math.round(m.odds_to_win)}
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
      fontSize: "max(var(--fs-min-xs), 0.65em)", fontWeight: 700, color: MUTED,
      textTransform: "uppercase", letterSpacing: "0.1em",
      borderTop: `1px solid ${BORDER}`,
    }}>
      {label}
    </div>
  );
}


function fmtH2H(v: number, fmt: string, prefix: string, suffix: string): string {
  // fmt is "+.2f" (signed) or ".1f" (plain); the digit is the decimals.
  const dp = Number(fmt.match(/\.(\d)/)?.[1] ?? 0);
  const body = fmt.startsWith("+") ? fmtSigned(v, dp) : Number.isFinite(v) ? v.toFixed(dp) : MISSING;
  return body === MISSING ? MISSING : `${prefix}${body}${suffix}`;
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

  const aStr = a != null ? fmtH2H(a, fmt, prefix, suffix) : MISSING;
  const bStr = b != null ? fmtH2H(b, fmt, prefix, suffix) : MISSING;

  const aColor = aWins ? GREEN : bWins ? "var(--bc-muted)" : TEXT;
  const bColor = bWins ? GOLD  : aWins ? "var(--bc-muted)" : TEXT;
  const barA   = aWins ? GREEN : "var(--bc-card)";
  const barB   = bWins ? GOLD  : "var(--bc-card)";

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
