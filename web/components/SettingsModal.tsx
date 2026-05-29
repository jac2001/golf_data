"use client";

import { useState, useEffect, useCallback } from "react";
import { getSettings, patchSettings, AppSettings } from "@/lib/api";

const BG     = "#0a1220";
const BG2    = "#0d1a30";
const BORDER = "#1e3a5f";
const MUTED  = "#5a7090";
const GREEN  = "#00c44f";
const TEXT   = "#dde6f5";

// ── Small sub-components ──────────────────────────────────────────────────────

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      style={{
        width: 36, height: 20, borderRadius: 10, border: "none",
        background: on ? GREEN : "#1e3a5f",
        position: "relative", cursor: "pointer", flexShrink: 0,
        transition: "background 0.2s",
      }}
    >
      <span style={{
        position: "absolute", top: 3, left: on ? 19 : 3,
        width: 14, height: 14, borderRadius: "50%", background: "#fff",
        transition: "left 0.2s",
      }} />
    </button>
  );
}

function Row({
  label, sub, children,
}: { label: string; sub?: string; children: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "10px 0", borderBottom: `1px solid ${BORDER}`,
    }}>
      <div>
        <div style={{ fontSize: "0.85em", color: TEXT }}>{label}</div>
        {sub && <div style={{ fontSize: "0.72em", color: MUTED, marginTop: 2 }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontSize: "0.68em", fontWeight: 700, color: MUTED,
        textTransform: "uppercase", letterSpacing: "0.08em",
        marginBottom: 4,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [saving,   setSaving]   = useState(false);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => {});
  }, []);

  // Instant-save: merge patch into local state and send to API
  const save = useCallback(async (patch: Record<string, unknown>) => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await patchSettings(patch);
      setSettings(updated);
    } finally {
      setSaving(false);
    }
  }, [settings]);

  // Helpers that build the nested patch object for common paths
  const setAlert  = (key: string, val: unknown) => save({ alerts: { [key]: val } });
  const setEvent  = (key: string, val: boolean) => save({ alerts: { events: { [key]: val } } });
  const setLive   = (key: string, val: unknown) => save({ live: { [key]: val } });

  if (!settings) {
    return (
      <Backdrop onClose={onClose}>
        <div style={{ color: MUTED, padding: 40, textAlign: "center" }}>Loading…</div>
      </Backdrop>
    );
  }

  const a = settings.alerts;
  const l = settings.live;

  return (
    <Backdrop onClose={onClose}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.05em", fontWeight: 800, color: TEXT }}>Settings</h2>
          {saving && <span style={{ fontSize: "0.7em", color: MUTED, marginTop: 2, display: "block" }}>Saving…</span>}
        </div>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: MUTED,
          fontSize: "1.3em", cursor: "pointer", lineHeight: 1,
        }}>×</button>
      </div>

      {/* ── Notifications ──────────────────────────────────────────────────── */}
      <Section title="Notifications">
        <Row label="macOS desktop notifications" sub="Fires even when you're not watching the dashboard">
          <Toggle on={a.mac_notifications} onChange={v => setAlert("mac_notifications", v)} />
        </Row>
        <Row label="In-app toast alerts" sub="Floating banners in the web dashboard">
          <Toggle on={a.web_toasts} onChange={v => setAlert("web_toasts", v)} />
        </Row>
      </Section>

      {/* ── Alert events ───────────────────────────────────────────────────── */}
      <Section title="Alert Events">
        <Row label="Your pick takes the lead" sub="Fires when one of your picks moves to #1">
          <Toggle on={a.events.my_pick_leads} onChange={v => setEvent("my_pick_leads", v)} />
        </Row>
        <Row label="Your pick enters top 5">
          <Toggle on={a.events.my_pick_top5} onChange={v => setEvent("my_pick_top5", v)} />
        </Row>
        <Row label="Your pick enters top 10">
          <Toggle on={a.events.my_pick_top10} onChange={v => setEvent("my_pick_top10", v)} />
        </Row>
        <Row label="Your pick makes a big move" sub={`Gains ${a.bigmove_threshold}+ positions in one update`}>
          <Toggle on={a.events.my_pick_bigmove} onChange={v => setEvent("my_pick_bigmove", v)} />
        </Row>
        <Row label="Tournament leader changes" sub="Any time the #1 spot changes hands">
          <Toggle on={a.events.leader_change} onChange={v => setEvent("leader_change", v)} />
        </Row>
      </Section>

      {/* ── Sensitivity ────────────────────────────────────────────────────── */}
      <Section title="Sensitivity">
        <Row
          label="Big-move threshold"
          sub="How many positions gained counts as a 'big move'"
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input
              type="range" min={3} max={10} step={1}
              value={a.bigmove_threshold}
              onChange={e => setAlert("bigmove_threshold", Number(e.target.value))}
              style={{ width: 90, accentColor: GREEN }}
            />
            <span style={{ fontSize: "0.88em", color: TEXT, minWidth: 16, textAlign: "center" }}>
              {a.bigmove_threshold}
            </span>
          </div>
        </Row>
        <Row label="Minimum severity" sub="Hide alerts below this level">
          <div style={{ display: "flex", gap: 4 }}>
            {(["low", "normal", "high"] as const).map(s => (
              <button key={s} onClick={() => setAlert("min_severity", s)} style={{
                background: a.min_severity === s ? "#0d2e18" : BG2,
                border: `1px solid ${a.min_severity === s ? GREEN : BORDER}`,
                color: a.min_severity === s ? GREEN : MUTED,
                borderRadius: 5, padding: "3px 10px",
                fontSize: "0.75em", cursor: "pointer",
                textTransform: "capitalize",
              }}>
                {s}
              </button>
            ))}
          </div>
        </Row>
      </Section>

      {/* ── Live page ──────────────────────────────────────────────────────── */}
      <Section title="Live Page">
        <Row label="Default tab">
          <select
            value={l.default_tab}
            onChange={e => setLive("default_tab", e.target.value)}
            style={{
              background: BG2, border: `1px solid ${BORDER}`, color: TEXT,
              borderRadius: 5, padding: "4px 8px", fontSize: "0.82em",
            }}
          >
            {[
              ["leaderboard", "Leaderboard"],
              ["vspred",      "vs Predictions"],
              ["mylineup",    "My Lineup"],
              ["sg",          "Live SG Stats"],
              ["holes",       "Hole Stats"],
            ].map(([val, label]) => (
              <option key={val} value={val}>{label}</option>
            ))}
          </select>
        </Row>
        <Row label="Default SG stats round">
          <select
            value={l.default_sg_round}
            onChange={e => setLive("default_sg_round", e.target.value)}
            style={{
              background: BG2, border: `1px solid ${BORDER}`, color: TEXT,
              borderRadius: 5, padding: "4px 8px", fontSize: "0.82em",
            }}
          >
            {[
              ["event_avg", "Event avg"],
              ["1", "Round 1"], ["2", "Round 2"],
              ["3", "Round 3"], ["4", "Round 4"],
            ].map(([val, label]) => (
              <option key={val} value={val}>{label}</option>
            ))}
          </select>
        </Row>
      </Section>
    </Backdrop>
  );
}

// ── Backdrop (click-outside to close) ────────────────────────────────────────

function Backdrop({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 10000,
        background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: BG, border: `1px solid ${BORDER}`, borderRadius: 12,
          padding: 24, width: 420, maxWidth: "calc(100vw - 32px)",
          maxHeight: "calc(100vh - 64px)", overflowY: "auto",
          boxShadow: "0 20px 60px rgba(0,0,0,0.7)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
