"use client";

import { LivePulse as LivePulseData } from "@/lib/api";

const BG     = "#060d1a";
const BORDER = "#1a3050";
const TEXT   = "#dde6f5";
const MUTED  = "#7a9ab8";
const LABEL  = "#3a5060";
const GREEN  = "#00c44f";
const GOLD   = "#f1c40f";
const RED    = "#e05555";
const PURPLE = "#c070f0";

type Props = {
  pulse:       LivePulseData | null;
  loading:     boolean;
  error:       string | null;
  onGenerate:  () => void;
  onRefresh:   () => void;
};

export default function LivePulse({ pulse, loading, error, onGenerate, onRefresh }: Props) {

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (!pulse && !loading && !error) {
    return (
      <div style={{
        background: BG, border: `1px dashed ${BORDER}`, borderRadius: 10,
        padding: "16px 20px", marginBottom: 20,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      }}>
        <div>
          <div style={{ fontSize: "0.88em", fontWeight: 700, color: TEXT, marginBottom: 2 }}>
            Live Pulse
          </div>
          <div style={{ fontSize: "0.75em", color: MUTED }}>
            AI analysis of what&apos;s happening right now — leaders, hot players, your picks.
          </div>
        </div>
        <button onClick={onGenerate} style={{
          background: GREEN + "22", border: `1px solid ${GREEN}55`,
          color: GREEN, borderRadius: 8, padding: "8px 18px",
          fontSize: "0.82em", fontWeight: 700, cursor: "pointer", flexShrink: 0,
          whiteSpace: "nowrap",
        }}>
          Generate Pulse
        </button>
      </div>
    );
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{
        background: BG, border: `1px dashed ${BORDER}`, borderRadius: 10,
        padding: "20px", marginBottom: 20, textAlign: "center",
      }}>
        <div style={{ fontSize: "0.85em", color: MUTED }}>Generating live pulse…</div>
        <div style={{ fontSize: "0.72em", color: LABEL, marginTop: 4 }}>
          Reading leaderboard + SG stats and asking Claude
        </div>
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div style={{
        background: "#1a0808", border: `1px solid ${RED}44`, borderRadius: 10,
        padding: "14px 20px", marginBottom: 20,
      }}>
        <span style={{ fontSize: "0.82em", color: RED }}>{error}</span>
        <button onClick={onGenerate} style={{
          marginLeft: 12, fontSize: "0.78em", color: MUTED,
          background: "none", border: "none", cursor: "pointer", textDecoration: "underline",
        }}>
          Try again
        </button>
      </div>
    );
  }

  if (!pulse) return null;

  const s = pulse.sections;
  const ts = pulse.generated_ts
    ? new Date(pulse.generated_ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";

  return (
    <div style={{
      background: BG, border: `1px solid ${BORDER}`, borderRadius: 10,
      marginBottom: 20, overflow: "hidden",
    }}>
      {/* Header bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: `1px solid ${BORDER}`,
        background: "#080f1e",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            fontSize: "0.65em", fontWeight: 800, color: GREEN,
            textTransform: "uppercase", letterSpacing: "0.12em",
            background: GREEN + "18", border: `1px solid ${GREEN}33`,
            borderRadius: 4, padding: "2px 8px",
          }}>
            Live Pulse
          </span>
          <span style={{ fontSize: "0.72em", color: MUTED }}>
            R{pulse.current_round} · {pulse.tournament_name}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {pulse.cached && ts && (
            <span style={{ fontSize: "0.65em", color: LABEL }}>updated {ts}</span>
          )}
          <button onClick={onRefresh} style={{
            background: "none", border: `1px solid ${BORDER}`,
            color: MUTED, borderRadius: 6, padding: "3px 10px",
            fontSize: "0.72em", cursor: "pointer",
          }}>
            Refresh
          </button>
        </div>
      </div>

      {/* Headline */}
      {s.headline && (
        <div style={{
          padding: "12px 18px", borderBottom: `1px solid ${BORDER}`,
          fontSize: "0.92em", fontWeight: 700, color: TEXT, lineHeight: 1.4,
        }}>
          {s.headline}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>

        {/* Left column: Leaders + Round Story */}
        <div style={{ borderRight: `1px solid ${BORDER}` }}>
          {s.leaders && (
            <Section label="Leaders" color={GOLD}>
              {s.leaders}
            </Section>
          )}
          {s.round_story && (
            <Section label="Round Story" color={MUTED}>
              {s.round_story}
            </Section>
          )}
          {s.your_picks && (
            <Section label="Your Picks" color={PURPLE}>
              {s.your_picks}
            </Section>
          )}
        </div>

        {/* Right column: On Fire + To Watch */}
        <div>
          {s.on_fire && s.on_fire.length > 0 && (
            <PlayerListSection label="On Fire" color={GREEN} players={s.on_fire} />
          )}
          {s.to_watch && s.to_watch.length > 0 && (
            <PlayerListSection label="To Watch" color={GOLD} players={s.to_watch} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({ label, color, children }: {
  label: string; color: string; children: React.ReactNode
}) {
  return (
    <div style={{ padding: "12px 16px", borderBottom: `1px solid ${BORDER}` }}>
      <div style={{
        fontSize: "0.62em", fontWeight: 800, color,
        textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6,
      }}>
        {label}
      </div>
      <p style={{ margin: 0, fontSize: "0.82em", color: TEXT, lineHeight: 1.65 }}>
        {children}
      </p>
    </div>
  );
}

function PlayerListSection({ label, color, players }: {
  label: string; color: string;
  players: { name: string; blurb: string }[];
}) {
  return (
    <div style={{ padding: "12px 16px", borderBottom: `1px solid ${BORDER}` }}>
      <div style={{
        fontSize: "0.62em", fontWeight: 800, color,
        textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {players.map((p, i) => (
          <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span style={{
              fontSize: "0.7em", fontWeight: 700, color,
              background: color + "18", border: `1px solid ${color}33`,
              borderRadius: 4, padding: "2px 7px", flexShrink: 0, marginTop: 1,
              whiteSpace: "nowrap",
            }}>
              {p.name.split(" ").slice(-1)[0]}
            </span>
            <p style={{ margin: 0, fontSize: "0.80em", color: TEXT, lineHeight: 1.6 }}>
              {p.blurb}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
