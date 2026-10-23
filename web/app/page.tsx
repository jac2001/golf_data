"use client";

/**
 * Home — the Broadcast landing. Answers one question in five seconds:
 * who's likely to win this week, and why should you trust the answer.
 * Offseason: hero counts down to the next season's opener and the model
 * board is honestly labeled with its own event ("Last time out").
 */

import React, { useEffect, useState } from "react";
import { useStoredChoice } from "@/lib/useStoredChoice";
import Link from "next/link";
import { getHome, getInPlay, HomeData, InPlayResponse } from "@/lib/api";
import { finishNumber } from "@/lib/format";
import { Show } from "@clerk/nextjs";
import { Panel, SectionTag, StatStrip, pct, textLink } from "@/components/broadcast";
import LiveMatchCard from "@/components/LiveMatchCard";
import { useLiveEvents } from "@/lib/useLiveEvents";

const STORY_COLORS: Record<string, string> = {
  yellow: "var(--bc-yellow)", green: "var(--bc-green)", orange: "var(--bc-orange)",
};

function fmtDates(start: string, end: string): string {
  // Parse date-only strings as LOCAL dates: new Date("2027-01-21") is UTC
  // midnight, which renders as the previous day west of Greenwich.
  const local = (s: string) => {
    const [y, m, d] = s.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d);
  };
  try {
    const s = local(start), e = local(end);
    const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${fmt(s)}–${e.getDate()}`;
  } catch { return start; }
}

export default function Home() {
  const [data, setData] = useState<HomeData | null>(null);
  const [tour, setTour] = useStoredChoice<"pga" | "euro">("favorite-tour", ["pga", "euro"], "pga", false);
  const [err, setErr]   = useState("");
  const live            = useLiveEvents();

  useEffect(() => { getHome(tour).then(setData).catch(e => setErr(String(e))); }, [tour]);

  // During play the hero and board show the live leaders (PGA live board),
  // not Tuesday's chances. Only this hero event's board counts (rule 1).
  const [board, setBoard] = useState<InPlayResponse | null>(null);
  const heroTid = data?.hero?.is_live && tour === "pga" ? data.hero.tid : null;
  useEffect(() => {
    if (!heroTid) { setBoard(null); return; }
    let cancelled = false;
    getInPlay().then(d => {
      if (!cancelled) setBoard(d.tournament_id?.toUpperCase() === heroTid.toUpperCase() && d.players?.length ? d : null);
    }).catch(() => { if (!cancelled) setBoard(null); });
    return () => { cancelled = true; };
  }, [heroTid]);

  if (err)   return <div style={{ color: "var(--bc-red)", padding: 24 }}>Failed to load: {err}</div>;
  if (!data) return <div style={{ color: "var(--bc-muted)", padding: 24 }}>Loading…</div>;

  const h = data.hero;
  const toPar = (v: number | null) => v == null ? "" : v === 0 ? "E" : v > 0 ? `+${v}` : `−${Math.abs(v)}`;
  const leaders = board
    ? [...board.players].filter(p => finishNumber(p.position) != null)
        .sort((a, b) => (finishNumber(a.position) ?? 999) - (finishNumber(b.position) ?? 999)).slice(0, 3)
    : [];
  const leadGroup = leaders.filter(p => finishNumber(p.position) === 1);
  const surname = (n: string) => n.trim().split(/\s+/).slice(-1)[0];
  const leadLine = leadGroup.length && board
    ? `${leadGroup.length > 2 ? `${leadGroup.length} players` : leadGroup.map(p => surname(p.player_name)).join(" and ")} ${leadGroup.length > 1 ? "lead" : "leads"} at ${toPar(leadGroup[0].total_numeric)}${board.current_round ? ` · Round ${board.current_round}` : ""}.`
    : null;
  const matchupBanner = (
    <div style={{ marginTop: 24, padding: "18px 22px", borderRadius: 10,
      background: "var(--bc-card)", border: "1px solid var(--bc-line)",
      display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <div style={{ flex: "1 1 300px" }}>
        <div style={{ fontWeight: 900, fontSize: "1.1em" }}>Your matchup</div>
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 4 }}>
          Where you stand against your group and the model — live during every round.
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <Link href="/match" style={{
          background: "var(--bc-yellow-fill)", color: "#081f14", fontWeight: 900,
          textTransform: "uppercase", fontSize: "max(var(--fs-min), 0.78em)", letterSpacing: "0.06em",
          padding: "11px 18px", borderRadius: 4, whiteSpace: "nowrap" }}>
          View your matchup
        </Link>
        <Link href="/friends" style={textLink}>
          Make picks →
        </Link>
      </div>
    </div>
  );

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto" }}>

      {/* ── New visitor? The game comes before the forecast. ────────────── */}
      <Show when="signed-out">
        <div style={{ marginTop: 24, padding: "22px 26px", borderRadius: 10,
          background: "var(--bc-card)", border: "1px solid var(--bc-line)",
          display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          {/* The game is the main path (review item 14); forecasts support it. */}
          <div style={{ flex: "1 1 380px" }}>
            <h1 style={{ margin: 0, fontWeight: 900, fontStretch: "115%", fontSize: "clamp(1.6em, 5.5vw, 2.6em)",
              lineHeight: 1.05, textTransform: "uppercase" }}>
              Pick your golfers. Challenge your friends.{" "}
              <span style={{ color: "var(--bc-yellow)" }}>Beat the model.</span>
            </h1>
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.92em)", marginTop: 10, lineHeight: 1.55 }}>
              A weekly picks game for your group, graded by real prize money. A few minutes
              to pick, all Sunday to trash-talk.
            </div>
            <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, background: "var(--bc-panel)",
              border: "1px solid var(--bc-line)", fontSize: "max(var(--fs-min), 0.84em)" }}>
              <span style={{ color: "var(--bc-muted)", fontWeight: 700, textTransform: "uppercase",
                letterSpacing: "0.06em", fontSize: "0.85em" }}>What you&apos;d see Sunday · example</span>
              <div style={{ fontWeight: 800, marginTop: 4 }}>You&apos;re 2nd. Sam leads you by $38,000.</div>
              <div style={{ color: "var(--bc-muted)" }}>You $412,000 · Sam $450,000 · the model $301,000 (lineup earnings)</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <Link href="/sign-up?redirect_url=%2Ffriends" style={{
              background: "var(--bc-yellow-fill)", color: "#081f14", fontWeight: 900,
              textTransform: "uppercase", fontSize: "max(var(--fs-min), 0.82em)", letterSpacing: "0.06em",
              padding: "13px 22px", borderRadius: 4, whiteSpace: "nowrap" }}>
              Start a group
            </Link>
            <Link href="/how-to-play" style={{ ...textLink, whiteSpace: "nowrap" }}>
              Try the demo first →
            </Link>
          </div>
        </div>
      </Show>

      {/* ── Signed in? Your game comes before the forecast. During play the
           live matchup leads; off-weeks (or with no live slate) it's the
           plain banner. ─────────────────────────────────────────────── */}
      <Show when="signed-in">
        {live.length > 0 ? <LiveMatchCard fallback={matchupBanner} /> : matchupBanner}
      </Show>

      {/* ── Tour switch: PGA is home, the DPWT one tap away ─────────────── */}
      <div style={{ display: "flex", gap: 8, paddingTop: 20 }}>
        {([["pga", "PGA Tour"], ["euro", "DP World Tour"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTour(id)} style={{
            cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "max(var(--fs-min), 0.72em)",
            textTransform: "uppercase", letterSpacing: "0.06em",
            padding: "7px 15px", borderRadius: 4,
            color: tour === id ? "var(--bc-sel-fg)" : "var(--bc-muted)",
            background: tour === id ? "var(--bc-sel-bg)" : "transparent",
            border: `1px solid ${tour === id ? "var(--bc-sel-line)" : "var(--bc-line)"}`,
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: "28px 48px", padding: "24px 0 30px", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 700, letterSpacing: "0.16em",
                        textTransform: "uppercase", color: h?.is_live ? "var(--bc-green)" : "var(--bc-muted)" }}>
            {h ? (h.is_live ? "Live now" : "This week on tour") : "Offseason"}
            {h && ` · ${fmtDates(h.start_date, h.end_date)}`}
            {h?.course && !h.is_live && ` · ${h.course}`}
          </div>
          <h2 style={{ margin: 0, fontWeight: 900, fontStretch: "115%",
                       fontSize: "clamp(1.4em, 4.5vw, 2.4em)", lineHeight: 1.02, textTransform: "uppercase",
                       letterSpacing: "-0.01em" }}>
            {h ? h.name : "See you in January"}
          </h2>
          <div style={{ fontSize: "1em", lineHeight: 1.55, color: "var(--bc-muted)",
                        maxWidth: 560, textWrap: "pretty" as never }}>
            {h?.is_live
              ? (leadLine ?? `Rounds in progress at ${h.course || h.location}.`)
              : h
                ? h.start_date === data.season_start
                  ? `The season opener at ${h.course || h.location}. Predictions go live the Tuesday of tournament week.`
                  : `The tour heads to ${h.course || h.location} next. Predictions go live the Tuesday of tournament week.`
                : "The model is in the offseason lab."}
          </div>
          <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
            {/* Outlined, not yellow: the game card above owns the page's one
                primary action. */}
            <Link href="/predictions" style={{
              border: "1px solid var(--bc-btn2-line)", color: "var(--bc-btn2-fg)", background: "var(--bc-btn2-bg)", fontWeight: 800,
              textTransform: "uppercase", fontSize: "max(var(--fs-min), 0.82em)", letterSpacing: "0.06em",
              padding: "12px 22px", borderRadius: 4 }}>
              This week's forecast
            </Link>
          </div>
        </div>

        {/* Live leaders during play; otherwise the model board. */}
        {leaders.length > 0 ? (
        <Panel style={{ flex: "1 1 340px", maxWidth: 520, minWidth: 0 }}>
          <SectionTag>Leaders · live</SectionTag>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {leaders.map(p => (
              <div key={p.player_name} style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ fontWeight: 900, fontSize: "1.1em", color: "var(--bc-muted)", width: 34 }}>{p.position}</div>
                <div style={{ flexGrow: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700 }}>{p.player_name}</div>
                  <div style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>
                    {toPar(p.total_numeric)}{p.today != null ? ` · today ${toPar(p.today)}` : ""}
                    {p.thru && p.thru !== "18" && p.thru !== "F" && p.thru !== "0" ? ` · thru ${p.thru}` : ""}
                  </div>
                </div>
                {p.win_prob != null && (
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 900, fontSize: "1.15em" }}>{p.win_prob.toFixed(0)}%</div>
                    <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: "var(--bc-muted)" }}>win chance</div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ borderTop: "1px solid var(--bc-card)", marginTop: 16, paddingTop: 12,
                        fontSize: "max(var(--fs-min), 0.76em)", color: "var(--bc-muted)" }}>
            Live chances from DataGolf ·{" "}
            <Link href="/live" style={{ color: "var(--bc-green)" }}>live board →</Link>
          </div>
        </Panel>
        ) : (
        <Panel style={{ flex: "1 1 340px", maxWidth: 520, minWidth: 0 }}>
          <SectionTag>
            {data.board_is_hero ? "Who the model likes" : `Last time out · ${data.board_event ?? ""}`}
          </SectionTag>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {data.board.map((b, i) => (
              <div key={b.player} style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ fontWeight: 900, fontSize: "1.4em", color: "var(--bc-muted)", width: 24 }}>{i + 1}</div>
                <div style={{ flexGrow: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: "1em" }}>{b.player}</div>
                  {b.why && <div style={{ fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>{b.why}</div>}
                </div>
                {/* Finished event: the pick's actual result leads, the
                    pre-event number demotes to context. */}
                {b.finish ? (
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 900, fontSize: "1.15em",
                      color: b.finish === "WON" ? "var(--bc-yellow)" : b.finish === "MC" ? "var(--bc-muted)" : "var(--bc-text)" }}>
                      {b.finish}
                    </div>
                    <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: "var(--bc-muted)" }}>picked at {pct(b.win_prob)}</div>
                  </div>
                ) : (
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 900, fontSize: "1.15em" }}>{pct(b.win_prob)}</div>
                    <div style={{ fontSize: "max(var(--fs-min), 0.72em)", color: "var(--bc-muted)" }}>win chance</div>
                  </div>
                )}
              </div>
            ))}
            {data.board.length === 0 && (
              <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
                Predictions publish the Tuesday of tournament week.
              </div>
            )}
          </div>
          <div style={{ borderTop: "1px solid var(--bc-card)", marginTop: 16, paddingTop: 12,
                        fontSize: "max(var(--fs-min), 0.76em)", color: "var(--bc-muted)" }}>
            Pre-tournament model numbers ·{" "}
            <Link href="/predictions" style={{ color: "var(--bc-green)" }}>full field →</Link>
          </div>
        </Panel>
        )}
      </div>

      {/* ── Storylines ───────────────────────────────────────────────────── */}
      {/* Pre-event stories ("the field's hottest player") step aside during
          play; the live leaders tell the story then (Jack, Oct 23). */}
      {data.storylines.length > 0 && !h?.is_live && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                      gap: 20, paddingBottom: 30 }}>
          {data.storylines.map(s => (
            <Panel key={s.tag} accent={STORY_COLORS[s.color] ?? "var(--bc-yellow)"}
                   style={{ background: "var(--bc-card)" }}>
              <SectionTag color={STORY_COLORS[s.color]}>{s.tag}</SectionTag>
              <div style={{ fontWeight: 700, fontSize: "1.1em", lineHeight: 1.25, marginBottom: 8 }}>
                {s.headline}
              </div>
              <div style={{ fontSize: "max(var(--fs-min), 0.82em)", color: "var(--bc-muted)", lineHeight: 1.5 }}>{s.sub}</div>
            </Panel>
          ))}
        </div>
      )}

      {/* ── Trust strip ──────────────────────────────────────────────────── */}
      <div style={{ paddingBottom: 44 }}>
        <StatStrip
          title="Track record"
          // Statements that stay true, not counts with a date (the last ones
          // read "through the 3M Open, Jul 26" three months later).
          stats={[
            { value: "Pre-event", label: "every forecast is saved before the first tee shot and graded as it stood" },
            { value: "10,000", label: "simulated tournaments behind each week's chances" },
            { value: "Weekly", label: "graded against real results after every event" },
          ]}
          right={<Link href="/methodology" style={textLink}>
            How it works →</Link>}
        />
      </div>
    </div>
  );
}
