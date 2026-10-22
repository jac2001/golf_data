"use client";

/**
 * The Games tab: the four game cards and whichever game is chosen.
 *
 * Which game opens (lib/landing.ts landingGame, Jack's rule): a ?game=
 * link wins; otherwise this device's last tap, the group's most-played
 * game, and what's open this week decide. Only a person's own TAP is
 * remembered: a landing the page chose isn't saved as their choice.
 */

import LetItRideTab, { LetItRideStandings } from "@/components/LetItRideTab";
import { useEffect, useState } from "react";
import { getOpenEvents } from "@/lib/api";
import { GAME_IDS, landingGame } from "@/lib/landing";
import type { GameId } from "@/lib/landing";
import { HowToPlay } from "./HowToPlay";
import { FadeStandings } from "./FadeStandings";
import { CollegeStandings } from "./CollegeGame";
import { card, useApi } from "./shared";
import { useActiveGroup } from "./ActiveGroup";
import { CollegeTab } from "./CollegeGame";
import { FadeTab } from "./FadeGame";
import { RoundGameTab } from "./RoundGame";
import { WeekChecklist } from "./WeekChecklist";

// ── Games: one tab, three modes ──────────────────────────────────────────────

export type GameMode = GameId;

const STORE_KEY = "friends-game-mode";

/** Inside each game: make picks, see the season, read the rules. */
type View = "picks" | "standings" | "rules";
const VIEWS: { id: View; label: string }[] = [
  { id: "picks", label: "Picks" },
  { id: "standings", label: "Standings" },
  { id: "rules", label: "How to play" },
];

const isGame = (v: string | null): v is GameId => !!v && (GAME_IDS as readonly string[]).includes(v);
export const GAME_MODES: { id: GameMode; name: string; short: string; tag: string }[] = [
  { id: "ride",    name: "Let It Ride",  short: "Let It Ride", tag: "Pick 3 · most money wins · uses budgeted all season" },
  { id: "rounds",  name: "Round Game",   short: "Round",   tag: "1 per round · to par" },
  { id: "fades",   name: "Fade Game",    short: "Fade",    tag: "Fade 3 stars · least money wins" },
  { id: "college", name: "College Game", short: "College", tag: "Claim a school · best 2 alumni count" },
];

export function GamesTab() {
  const api = useApi();
  const { group } = useActiveGroup();
  const [mode, setMode] = useState<GameMode | null>(null);
  const [view, setView] = useState<View>("picks");

  useEffect(() => {
    // 1. A link that names a game (/friends?game=rounds) wins outright.
    const q = new URLSearchParams(window.location.search);
    const v = q.get("view");
    if (v === "standings" || v === "rules") setView(v);
    const linked = q.get("game");
    if (isGame(linked)) { setMode(linked); return; }

    // 2. Otherwise Jack's rule. Storage can throw (private mode): no tap then.
    let lastChosen: GameId | null = null;
    try { const v = localStorage.getItem(STORE_KEY); if (isGame(v)) lastChosen = v; } catch { /* none */ }

    let cancelled = false;
    Promise.all([
      api("/api/friends/landing").then(d => d.groupPicks as Record<GameId, number>).catch(() => null),
      getOpenEvents().then(d => d.events ?? []).catch(() => null),
    ]).then(([groupPicks, events]) => {
      if (cancelled) return;
      const evs = events ?? [];
      const pickable = evs.filter(e => !e.locked && !e.finished);
      const open: Record<GameId, boolean> = events === null
        ? { ride: true, rounds: true, fades: true, college: true }   // unknown: don't rule games out
        : {
            ride: pickable.length > 0,
            rounds: evs.some(e => !e.finished),                      // picks run round by round
            fades: pickable.some(e => e.has_model),
            college: pickable.some(e => e.tour !== "euro"),
          };
      let chosen: GameId;
      try {
        chosen = landingGame({ groupPicks: groupPicks ?? { ride: 0, rounds: 0, fades: 0, college: 0 }, lastChosen, open });
      } catch {
        chosen = lastChosen ?? "ride";
      }
      setMode(chosen);
    });
    return () => { cancelled = true; };
  }, [api]);

  /** A person's own tap: show it and remember it on this device. */
  function pick(g: GameMode) {
    setMode(g);
    try { localStorage.setItem(STORE_KEY, g); } catch { /* fine */ }
  }

  const tabBtn = (on: boolean): React.CSSProperties => ({
    flex: 1, minHeight: 44, cursor: "pointer", fontFamily: "inherit", background: "transparent",
    border: "none", borderBottom: `3px solid ${on ? "var(--bc-yellow-fill)" : "transparent"}`,
    color: on ? "var(--bc-text)" : "var(--bc-muted)", fontWeight: on ? 900 : 800,
    fontSize: "max(var(--fs-min), 0.8em)", textTransform: "uppercase", letterSpacing: "0.06em",
  });

  return (
    <>
      {group && <WeekChecklist groupId={group.id} refreshKey={`${mode}:${view}`} onPick={g => { pick(g); setView("picks"); }} />}
      <nav aria-label="Games" style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
        gap: 4, background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10,
        padding: 4, marginBottom: 12 }}>
        {GAME_MODES.map(g => {
          const on = mode === g.id;
          return (
            <button key={g.id} onClick={() => pick(g.id)} aria-pressed={on} title={g.tag} style={{
              minHeight: 44, cursor: "pointer", fontFamily: "inherit", borderRadius: 7, minWidth: 0,
              padding: "0 2px", fontSize: "max(var(--fs-min), 0.84em)", fontWeight: on ? 900 : 800,
              background: on ? "var(--bc-sel-bg)" : "transparent",
              border: `1px solid ${on ? "var(--bc-sel-line)" : "transparent"}`,
              color: on ? "var(--bc-sel-fg)" : "var(--bc-muted)",
            }}>
              {g.short}
            </button>
          );
        })}
      </nav>
      <div role="tablist" style={{ display: "flex", borderBottom: "1px solid var(--bc-line)", marginBottom: 14 }}>
        {VIEWS.map(v => (
          <button key={v.id} role="tab" aria-selected={view === v.id} onClick={() => setView(v.id)}
            style={tabBtn(view === v.id)}>{v.label}</button>
        ))}
      </div>
      {mode === null && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {mode !== null && view === "picks" && <>
        {mode === "rounds" && <RoundGameTab />}
        {mode === "fades" && <FadeTab />}
        {mode === "college" && <CollegeTab />}
        {mode === "ride" && <LetItRideTab group={group} />}
      </>}
      {mode !== null && view === "standings" && <>
        {mode === "ride" && (group ? <LetItRideStandings groupId={group.id} /> : <LetItRideStandings />)}
        {mode === "fades" && <FadeStandings />}
        {mode === "college" && <CollegeStandings />}
        {mode === "rounds" && (
          <div style={card}>
            <p style={{ margin: 0, color: "var(--bc-muted)", lineHeight: 1.6 }}>
              The Round Game is scored one event at a time, so there&apos;s no
              season table: the event board is on the Picks tab.
            </p>
          </div>
        )}
      </>}
      {mode !== null && view === "rules" && <HowToPlay game={mode} />}
    </>
  );
}
