"use client";

/**
 * The Games tab: the four game cards and whichever game is chosen.
 * Split out of app/friends/page.tsx unchanged.
 */

import LetItRideTab from "@/components/LetItRideTab";
import { useStoredChoice } from "@/lib/useStoredChoice";
import { CollegeTab } from "./CollegeGame";
import { FadeTab } from "./FadeGame";
import { RoundGameTab } from "./RoundGame";

// ── Games: one tab, three modes ──────────────────────────────────────────────

export type GameMode = "ride" | "rounds" | "fades" | "college";
export const GAME_MODES: { id: GameMode; name: string; tag: string }[] = [
  { id: "ride",    name: "Let It Ride",  tag: "Pick 3 · most money wins · uses budgeted all season" },
  { id: "rounds",  name: "Round Game",   tag: "1 per round · to par" },
  { id: "fades",   name: "Fade Game",    tag: "Fade 3 stars · least money wins" },
  { id: "college", name: "College Game", tag: "Claim a school · best 2 alumni count" },
];

export function GamesTab() {
  // Remembered per device — a convenience, so the page still renders
  // fine when storage is unavailable (private mode, prerender).
  // A remembered "picks" (Weekly 3, retired) isn't allowed, so it lands on "ride".
  const [mode, pick] = useStoredChoice<GameMode>("friends-game-mode",
    ["ride", "rounds", "fades", "college"], "ride");

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
      {mode === "rounds" && <RoundGameTab />}
      {mode === "fades" && <FadeTab />}
      {mode === "college" && <CollegeTab />}
      {mode === "ride" && <LetItRideTab />}
    </>
  );
}
