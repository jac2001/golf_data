"use client";

/**
 * The Games tab: the four game cards and whichever game is chosen.
 *
 * Which game opens (lib/landing.ts landingGame, Jack's rule): a ?game=
 * link wins; otherwise this device's last tap, the group's most-played
 * game, and what's open this week decide. Only a person's own TAP is
 * remembered: a landing the page chose isn't saved as their choice.
 */

import LetItRideTab from "@/components/LetItRideTab";
import { useEffect, useState } from "react";
import { getOpenEvents } from "@/lib/api";
import { GAME_IDS, landingGame } from "@/lib/landing";
import type { GameId } from "@/lib/landing";
import { useApi } from "./shared";
import { CollegeTab } from "./CollegeGame";
import { FadeTab } from "./FadeGame";
import { RoundGameTab } from "./RoundGame";

// ── Games: one tab, three modes ──────────────────────────────────────────────

export type GameMode = GameId;

const STORE_KEY = "friends-game-mode";

const isGame = (v: string | null): v is GameId => !!v && (GAME_IDS as readonly string[]).includes(v);
export const GAME_MODES: { id: GameMode; name: string; tag: string }[] = [
  { id: "ride",    name: "Let It Ride",  tag: "Pick 3 · most money wins · uses budgeted all season" },
  { id: "rounds",  name: "Round Game",   tag: "1 per round · to par" },
  { id: "fades",   name: "Fade Game",    tag: "Fade 3 stars · least money wins" },
  { id: "college", name: "College Game", tag: "Claim a school · best 2 alumni count" },
];

export function GamesTab() {
  const api = useApi();
  const [mode, setMode] = useState<GameMode | null>(null);

  useEffect(() => {
    // 1. A link that names a game (/friends?game=rounds) wins outright.
    const linked = new URLSearchParams(window.location.search).get("game");
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

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
        gap: 8, marginBottom: 16 }}>
        {GAME_MODES.map(g => {
          const on = mode === g.id;
          return (
            <button key={g.id} onClick={() => pick(g.id)} style={{
              cursor: "pointer", textAlign: "left", fontFamily: "inherit",
              background: on ? "var(--bc-raised)" : "var(--bc-card)",
              border: on ? "1px solid var(--bc-line-hi)" : "1px solid var(--bc-line)",
              borderRadius: 8, padding: "10px 12px", minWidth: 0,
            }}>
              <div style={{ fontWeight: 900, fontSize: "max(var(--fs-min), 0.86em)", letterSpacing: "0.02em",
                color: "var(--bc-text)" }}>
                {g.name}
              </div>
              <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.7em)", marginTop: 3, lineHeight: 1.35 }}>
                {g.tag}
              </div>
            </button>
          );
        })}
      </div>
      {mode === null && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {mode === "rounds" && <RoundGameTab />}
      {mode === "fades" && <FadeTab />}
      {mode === "college" && <CollegeTab />}
      {mode === "ride" && <LetItRideTab />}
    </>
  );
}
