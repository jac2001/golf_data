"use client";

/**
 * /how-to-play — the game-first front door. PUBLIC on purpose.
 * =============================================================
 * A new visitor learns what they pick, how they score, whom they beat,
 * and tries a real selection against the model BEFORE any sign-in wall.
 * The ML story lives on /methodology; this page sells the Sunday ritual.
 */

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHead } from "@/components/broadcast";
import { getPredictions, getOpenEvents, PlayerPrediction } from "@/lib/api";
import { expectedPayout } from "@/lib/modelBrain";

const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 20, marginBottom: 16,
};
const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

const GAMES = [
  { name: "Weekly 3", tag: "Pick 3 golfers before Thursday. Your score is their combined prize money. Most money in your group wins the week." },
  { name: "Round Game", tag: "One golfer per round, each player once per event, scored against par. Miss the cut with your pick and it costs you +5." },
  { name: "Fade Game", tag: "Pick 3 of the top-20 favorites you think will FLOP. Lowest combined earnings wins — fade the champion and you eat his whole check." },
];

export default function HowToPlayPage() {
  const [field, setField] = useState<PlayerPrediction[]>([]);
  const [purse, setPurse] = useState(6_000_000);
  const [eventName, setEventName] = useState("");
  const [picks, setPicks] = useState<string[]>([]);

  useEffect(() => {
    getPredictions(20).then(d => {
      setField((d.players ?? []).filter(p => p.player_name));
      getOpenEvents().then(o => {
        const ev = (o.events ?? []).find(e =>
          e.tournament_id.toUpperCase() === String(d.tournament_id ?? "").toUpperCase());
        if (ev?.purse) setPurse(ev.purse);
        setEventName(ev?.name ?? String(d.tournament_id ?? ""));
      }).catch(() => setEventName(String(d.tournament_id ?? "")));
    }).catch(() => {});
  }, []);

  const trioValue = useMemo(() =>
    picks.reduce((s, name) => {
      const p = field.find(f => f.player_name === name);
      return p ? s + expectedPayout(purse, p) : s;
    }, 0), [picks, field, purse]);

  const modelTrio = field.slice(0, 3);
  const modelValue = useMemo(() =>
    modelTrio.reduce((s, p) => s + expectedPayout(purse, p), 0), [modelTrio, purse]);

  function toggle(name: string) {
    setPicks(ps => ps.includes(name) ? ps.filter(p => p !== name)
      : ps.length >= 3 ? ps : [...ps, name]);
  }

  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      <PageHead kicker="Thirty seconds a week · bragging rights all Sunday" title="How to Play" />

      {/* The pitch */}
      <div style={{ ...card, padding: 28 }}>
        <div style={{ fontSize: "1.6em", fontWeight: 900, lineHeight: 1.25, letterSpacing: "-0.01em" }}>
          Pick your golfers. Challenge your friends.<br />
          <span style={{ color: "var(--bc-yellow)" }}>Beat the model.</span>
        </div>
        <p style={{ color: "var(--bc-muted)", fontSize: "0.92em", lineHeight: 1.6, maxWidth: 620, marginBottom: 0 }}>
          Every tournament week you make picks before Thursday&apos;s tee-off,
          follow the leaderboard with your group, and settle it Sunday when the
          real prize money posts. Our prediction model plays too, under the
          same rules — beating it is the badge.
        </p>
      </div>

      {/* The games */}
      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", marginBottom: 16 }}>
        {GAMES.map(g => (
          <div key={g.name} style={{ ...card, marginBottom: 0 }}>
            <div style={{ fontWeight: 900, color: "var(--bc-yellow)", marginBottom: 6 }}>{g.name}</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.84em", lineHeight: 1.55 }}>{g.tag}</div>
          </div>
        ))}
      </div>

      {/* Scoring example */}
      <div style={card}>
        <div style={{ fontWeight: 800, marginBottom: 8 }}>Scoring, in one example</div>
        <p style={{ color: "var(--bc-muted)", fontSize: "0.86em", lineHeight: 1.6, margin: 0 }}>
          Say your Weekly 3 are Scheffler, Bridgeman and Poston. Scheffler
          finishes 2nd (<strong style={{ color: "var(--bc-text)" }}>$1.09M</strong>),
          Bridgeman wins (<strong style={{ color: "var(--bc-text)" }}>$1.08M</strong>),
          Poston misses the cut (<strong style={{ color: "var(--bc-text)" }}>$0</strong>).
          Your week: <strong style={{ color: "var(--bc-yellow)" }}>$2.17M</strong>.
          Highest total in your group takes the week; season standings add up
          every week you play. Everyone&apos;s picks stay hidden until tee-off,
          so nobody copies.
        </p>
      </div>

      {/* Sample group — clearly an example */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 18px 6px", fontWeight: 800 }}>
          A group, Sunday night
          <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.74em", marginLeft: 8 }}>example</span>
        </div>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <tbody>
            {[["1", "Alex", "$2.41M", false], ["2", "The Model", "$2.17M", true],
              ["3", "You", "$1.98M", false], ["4", "Sam", "$0.62M", false]].map(([rk, nm, val, isModel]) => (
              <tr key={String(nm)}>
                <td style={{ padding: "8px 18px", color: "var(--bc-yellow)", fontWeight: 800, width: 40,
                  borderBottom: "1px solid var(--bc-line)" }}>{rk}</td>
                <td style={{ padding: "8px 12px", fontWeight: 700, borderBottom: "1px solid var(--bc-line)" }}>
                  {nm}
                  {isModel ? <span style={{ marginLeft: 8, fontSize: "0.62em", fontWeight: 900, letterSpacing: "0.08em",
                    color: "#081f14", background: "var(--bc-yellow)", borderRadius: 3, padding: "2px 6px" }}>MODEL</span> : null}
                </td>
                <td style={{ padding: "8px 18px", textAlign: "right", fontWeight: 800,
                  fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--bc-line)" }}>{val}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Live demo */}
      {field.length > 0 && (
        <div style={card}>
          <div style={{ fontWeight: 800 }}>
            Try it — no account needed
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.76em", marginLeft: 8 }}>
              {eventName} · model win chances shown
            </span>
          </div>
          <p style={{ color: "var(--bc-muted)", fontSize: "0.8em", margin: "6px 0 12px" }}>
            Tap three. We&apos;ll price your trio with the model&apos;s expected
            prize money and stack it against the model&apos;s own picks.
          </p>
          <div style={{ display: "grid", gap: 6, gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))" }}>
            {field.map(p => {
              const on = picks.includes(p.player_name);
              return (
                <button key={p.player_name} onClick={() => toggle(p.player_name)} style={{
                  cursor: "pointer", fontFamily: "inherit", textAlign: "left",
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "8px 12px", borderRadius: 6, fontSize: "0.84em",
                  color: on ? "#081f14" : "var(--bc-text)",
                  background: on ? "var(--bc-yellow)" : "var(--bc-panel)",
                  border: `1px solid ${on ? "var(--bc-yellow)" : "var(--bc-line)"}`,
                }}>
                  <span style={{ fontWeight: 700, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p.player_name}
                  </span>
                  <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums",
                    color: on ? "#081f14" : "var(--bc-muted)" }}>
                    {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                  </span>
                </button>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 16, marginTop: 14 }}>
            <div style={{ fontSize: "0.88em" }}>
              <span style={{ color: "var(--bc-muted)" }}>Your trio ({picks.length}/3): </span>
              <strong>{picks.length ? money(trioValue) : "—"}</strong>
              <span style={{ color: "var(--bc-muted)" }}> expected</span>
            </div>
            <div style={{ fontSize: "0.88em" }}>
              <span style={{ color: "var(--bc-muted)" }}>The model&apos;s trio: </span>
              <strong>{money(modelValue)}</strong>
            </div>
            {picks.length === 3 && (
              <div style={{ fontSize: "0.88em", fontWeight: 800,
                color: trioValue >= modelValue ? "var(--bc-green)" : "var(--bc-red-text)" }}>
                {trioValue >= modelValue
                  ? `You'd out-project the model by ${money(trioValue - modelValue)}`
                  : `Model projects ${money(modelValue - trioValue)} ahead — prove it wrong`}
              </div>
            )}
          </div>
          <p style={{ color: "var(--bc-muted)", fontSize: "0.74em", marginTop: 10, marginBottom: 0 }}>
            Expected value is pre-tournament projection; real games grade on the
            actual purse Sunday night.
          </p>
        </div>
      )}

      {/* CTAs */}
      <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap", margin: "22px 0 8px" }}>
        <Link href="/sign-up" style={{
          background: "var(--bc-yellow)", color: "#081f14", fontWeight: 900,
          textTransform: "uppercase", fontSize: "0.82em", letterSpacing: "0.06em",
          padding: "13px 24px", borderRadius: 4 }}>
          Create a free account
        </Link>
        <Link href="/friends" style={{ fontWeight: 700, fontSize: "0.82em",
          textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--bc-yellow)" }}>
          Already playing? Your group →
        </Link>
      </div>
      <p style={{ color: "var(--bc-muted)", fontSize: "0.8em", lineHeight: 1.6 }}>
        Groups are invite-only: create one, text a friend the code, done. No
        money changes hands — the stakes are strictly bragging rights.
        Curious how the model actually works? That story lives at{" "}
        <Link href="/methodology" style={{ color: "var(--bc-yellow)" }}>How the model works</Link>.
      </p>
    </div>
  );
}
