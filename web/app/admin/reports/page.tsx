"use client";

/**
 * /admin/reports — the site admin's review queue for chirp reports a group
 * owner can't fairly review (reports about the owner's own chirps). The API
 * refuses anyone not in lib/admin.ts, so this page shows nothing to others.
 */

import { useCallback, useEffect, useState } from "react";
import { PageHead } from "@/components/broadcast";

type Row = { chirp_id: string; text: string; author: string; tournament_id: string; created_at: string;
  group_name: string; reports: number; reasons: string[] };

export default function AdminReportsPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    fetch("/api/admin/chirp-reports").then(async r => {
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error ?? `Request failed (${r.status})`);
      setRows(d.reports ?? []);
    }).catch(e => { setErr(e.message); setRows([]); });
  }, []);
  useEffect(load, [load]);

  async function resolve(id: string, action: "dismiss" | "remove") {
    if (action === "remove" && !confirm("Remove this chirp for everyone in its group?")) return;
    const r = await fetch("/api/friends/chirps/resolve", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, action }) });
    if (!r.ok) setErr((await r.json().catch(() => ({}))).error ?? "Couldn't resolve it.");
    load();
  }

  const btn: React.CSSProperties = { minHeight: 40, padding: "0 14px", cursor: "pointer", fontFamily: "inherit",
    fontWeight: 800, borderRadius: 6, border: "1px solid var(--bc-line-hi)", background: "transparent", color: "var(--bc-text)" };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <PageHead kicker="Admin" title="Chirp reports" />
      <p style={{ color: "var(--bc-muted)", marginTop: -6 }}>
        Reports about a group owner&apos;s own chirps. Owners review everything else in their own thread.
      </p>
      {err && <div style={{ color: "var(--bc-muted)", margin: "10px 0" }}>{err}</div>}
      {rows === null && <p style={{ color: "var(--bc-muted)" }}>Loading…</p>}
      {rows?.length === 0 && !err && <p style={{ color: "var(--bc-muted)" }}>Nothing to review.</p>}
      {rows?.map(r => (
        <div key={r.chirp_id} style={{ background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10,
          padding: 14, marginBottom: 10 }}>
          <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)" }}>
            {r.group_name} · {r.tournament_id} · {r.author} (owner) · {new Date(r.created_at).toLocaleString()}
          </div>
          <div style={{ fontWeight: 700, margin: "6px 0" }}>{r.text}</div>
          <div style={{ color: "var(--bc-orange)", fontWeight: 800, fontSize: "max(var(--fs-min), 0.82em)" }}>
            Reported {r.reports} {r.reports === 1 ? "time" : "times"}{r.reasons.length ? `: ${r.reasons.join(" · ")}` : ""}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button onClick={() => resolve(r.chirp_id, "dismiss")} style={btn}>Dismiss</button>
            <button onClick={() => resolve(r.chirp_id, "remove")} style={{ ...btn, borderColor: "var(--bc-orange)" }}>Remove chirp</button>
          </div>
        </div>
      ))}
    </div>
  );
}
