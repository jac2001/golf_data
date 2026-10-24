"use client";

/**
 * /admin/scorecard — the pilot's weekly scorecard (launch plan, section 6).
 * The API refuses anyone not in lib/admin.ts, so this page shows nothing to
 * others. Measure 6 (support needed per group) is Jack's own notes.
 */

import { useEffect, useState } from "react";
import { PageHead } from "@/components/broadcast";

type Ratio = { n: number; of: number };
type Data = {
  scorecard: Record<string, Ratio> | null;
  error?: string;
  events: string[];
  perEvent: { tid: string; players: number }[];
};

const MEASURES: { key: string; label: string; unit?: string }[] = [
  { key: "invitedWhoPicked",   label: "Invited players who made a pick after joining" },
  { key: "pickedAgain",        label: "Players who picked again in a later event" },
  { key: "steadyGroups",       label: "Groups with several active players in every event" },
  { key: "checkedMatchCenter", label: "Pickers who checked the Match Center during play" },
  { key: "invitesShared",      label: "Invites and nudges shared", unit: "people" },
];

export default function AdminScorecardPage() {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/admin/scorecard").then(async r => {
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error ?? `Request failed (${r.status})`);
      setD(j);
    }).catch(e => setErr(e.message));
  }, []);

  const card: React.CSSProperties = { background: "var(--bc-card)", border: "1px solid var(--bc-line)",
    borderRadius: 10, padding: 14, marginBottom: 10 };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <PageHead kicker="Admin" title="Pilot scorecard" />
      <p style={{ color: "var(--bc-muted)", marginTop: -6 }}>
        The main signal is groups that keep playing week after week. Admins, test logins and the model are left out of every count.
      </p>
      {err && <p style={{ color: "var(--bc-muted)" }}>{err}</p>}
      {!d && !err && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {d && !d.scorecard && <p style={{ color: "var(--bc-orange)" }}>Scorecard not computed yet: {d.error}</p>}
      {d?.scorecard && MEASURES.map(m => {
        const r = d.scorecard![m.key];
        return (
          <div key={m.key} style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <span style={{ fontWeight: 700 }}>{m.label}</span>
            <span style={{ fontWeight: 900, fontSize: "1.2em", whiteSpace: "nowrap" }}>
              {m.unit ? `${r.n} by ${r.of} ${m.unit}` : `${r.n} of ${r.of}`}
            </span>
          </div>
        );
      })}
      {d && (
        <div style={card}>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Players picking per event</div>
          {d.perEvent.length === 0 && <div style={{ color: "var(--bc-muted)" }}>No picks recorded yet.</div>}
          {d.perEvent.map(e => (
            <div key={e.tid} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
              <span>{e.tid}</span><span style={{ fontWeight: 800 }}>{e.players}</span>
            </div>
          ))}
        </div>
      )}
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
        Support needed per group isn&apos;t tracked here. Keep it in your own notes.
      </p>
    </div>
  );
}
