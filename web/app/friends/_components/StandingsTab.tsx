"use client";

/**
 * Season standings for every game.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useEffect, useState } from "react";
import { LetItRideStandings } from "@/components/LetItRideTab";
import { useStoredChoice } from "@/lib/useStoredChoice";
import { CollegeStandings } from "./CollegeGame";
import { GAME_MODES } from "./GamesTab";
import { ModelBadge, btnQuiet, card, cell, hdr, useApi } from "./shared";

export function StandingsTab() {
  // Season standings exist for the weekly and fade games only — the
  // Round Game is per-tournament by design (its whole-event board
  // lives on the Games tab), so no "rounds" pill here and a
  // remembered "rounds" mode falls back to picks.
  const [mode, setMode] = useStoredChoice<"ride" | "fades" | "college">("friends-game-mode",
    ["ride", "fades", "college"], "ride", false);

  return (
    <>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {GAME_MODES.filter(g => g.id !== "rounds").map(g => {
          const on = mode === g.id;
          return (
            <button key={g.id} onClick={() => setMode(g.id as "ride" | "fades" | "college")} style={{
              ...btnQuiet, padding: "7px 14px",
              color: on ? "var(--bc-text)" : "var(--bc-muted)",
              background: on ? "var(--bc-raised)" : "transparent",
              borderColor: on ? "var(--bc-line-hi)" : "var(--bc-line)",
            }}>
              {g.name}
            </button>
          );
        })}
      </div>
      {mode === "ride" && <LetItRideStandings />}
      {mode === "fades" && <FadeStandings />}
      {mode === "college" && <CollegeStandings />}
    </>
  );
}

/** Fade Game season: EVENT WINS, not a money sum — summing a
 *  lowest-wins score would reward never playing. */
export type FadeSeasonRow = { user_id: string; user_name: string; wins: number; entered: number; settled: number };

export function FadeStandings() {
  const api = useApi();
  const [rows, setRows] = useState<FadeSeasonRow[] | null>(null);
  const [me, setMe] = useState("");

  useEffect(() => {
    api("/api/friends/fadeboard")
      .then(d => { setRows((d.standings as FadeSeasonRow[]) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setRows([]));
  }, [api]);

  if (!rows) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (rows.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        No fades yet — the season tally starts once the first Fade Game
        week settles. Place yours on the Games tab.
      </p>
    </div>
  );

  return (
    <>
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>#</th><th style={hdr}>Player</th>
            <th style={{ ...hdr, textAlign: "right" }}>Event wins</th>
            <th style={{ ...hdr, textAlign: "right" }}>Entered</th>
          </tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.user_id} style={{ background: r.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
                <td style={{ ...cell, fontWeight: 800, color: "var(--bc-muted)" }}>{i + 1}</td>
                <td style={{ ...cell, fontWeight: 700 }}>
                  {r.user_name}
                  {r.user_id === "model" && <ModelBadge />}
                  {r.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                </td>
                <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                  {r.wins}
                </td>
                <td style={{ ...cell, textAlign: "right", color: "var(--bc-muted)" }}>{r.entered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)", marginTop: 10 }}>
        Scored in event wins — lowest combined earnings takes the week.
        Weekly boards live inside the Fade Game on the Games tab.
      </p>
    </>
  );
}
