"use client";

/**
 * /settings — the public app's account settings.
 * ===============================================
 * Profile (how friends see you, Clerk account management), Notifications
 * (per-game reminder switches — per ACCOUNT; this device's subscription;
 * a scoped test push), Defaults (favorite tour — per device), and a
 * plain-words account section. The league dashboard's alert settings
 * are a different thing and stay behind the ⚙ in the league zone.
 */

import React, { useCallback, useEffect, useState } from "react";
import { useAuth, useClerk, useUser } from "@clerk/nextjs";
import { PageHead } from "@/components/broadcast";

const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 20, marginBottom: 16,
};
const rowStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 12, padding: "10px 0",
  borderBottom: "1px solid var(--bc-line)",
};
const btnQuiet: React.CSSProperties = {
  cursor: "pointer", fontFamily: "inherit", fontWeight: 700, fontSize: "0.78em",
  padding: "7px 14px", borderRadius: 5, background: "transparent",
  color: "var(--bc-muted)", border: "1px solid var(--bc-line)",
};

function useApi() {
  const { getToken } = useAuth();
  return useCallback(async (url: string, init: RequestInit = {}) => {
    const token = await getToken();
    const res = await fetch(url, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(String(d?.error ?? res.status));
    return d;
  }, [getToken]);
}

function Toggle({ on, busy, onClick }: { on: boolean; busy?: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={busy} style={{
      ...btnQuiet, marginLeft: "auto", minWidth: 52,
      color: on ? "#081f14" : "var(--bc-muted)",
      background: on ? "var(--bc-yellow)" : "transparent",
      borderColor: on ? "var(--bc-yellow)" : "var(--bc-line)",
    }}>
      {busy ? "…" : on ? "On" : "Off"}
    </button>
  );
}

function Row({ label, sub, children }: {
  label: string; sub?: string; children?: React.ReactNode;
}) {
  return (
    <div style={rowStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "0.9em", fontWeight: 600 }}>{label}</div>
        {sub && <div style={{ fontSize: "0.76em", color: "var(--bc-muted)", marginTop: 2 }}>{sub}</div>}
      </div>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const api = useApi();
  const { user } = useUser();
  const clerk = useClerk();

  const [prefs, setPrefs] = useState<{ remind_weekly: boolean; remind_fades: boolean } | null>(null);
  const [busyPref, setBusyPref] = useState("");
  const [devices, setDevices] = useState<{ endpoint: string; created_at: string }[] | null>(null);
  const [thisEndpoint, setThisEndpoint] = useState("");
  const [testMsg, setTestMsg] = useState("");
  const [tour, setTour] = useState<"pga" | "euro">("pga");

  useEffect(() => {
    api("/api/friends/prefs").then(d => setPrefs(d as never)).catch(() => setPrefs({ remind_weekly: true, remind_fades: true }));
    api("/api/friends/reminders").then(d => setDevices((d.subscriptions as never) ?? [])).catch(() => setDevices([]));
    try {
      const t = localStorage.getItem("favorite-tour");
      if (t === "euro" || t === "pga") setTour(t);
    } catch { /* default */ }
    if ("serviceWorker" in navigator && "PushManager" in window) {
      navigator.serviceWorker.register("/sw.js")
        .then(reg => reg.pushManager.getSubscription())
        .then(sub => setThisEndpoint(sub?.endpoint ?? ""))
        .catch(() => {});
    }
  }, [api]);

  async function flipPref(key: "remind_weekly" | "remind_fades") {
    if (!prefs) return;
    setBusyPref(key);
    try {
      const d = await api("/api/friends/prefs", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: !prefs[key] }),
      });
      setPrefs(d as never);
    } catch { /* keep old state */ }
    setBusyPref("");
  }

  async function testPush() {
    setTestMsg("Sending…");
    try {
      const d = await api("/api/friends/reminders/test", { method: "POST" });
      setTestMsg(d.sent ? `Sent to ${d.sent} device${d.sent === 1 ? "" : "s"}.` : "No subscribed devices yet — turn reminders on below.");
    } catch (e) { setTestMsg(`Failed: ${(e as Error).message}`); }
  }

  async function forgetDevice(endpoint: string) {
    try {
      await api("/api/friends/reminders", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint }),
      });
      setDevices(dv => (dv ?? []).filter(d => d.endpoint !== endpoint));
      if (endpoint === thisEndpoint) {
        const reg = await navigator.serviceWorker.ready;
        (await reg.pushManager.getSubscription())?.unsubscribe();
        setThisEndpoint("");
      }
    } catch { /* row stays */ }
  }

  async function subscribeThisDevice() {
    try {
      if ((await Notification.requestPermission()) !== "granted") return;
      const reg = await navigator.serviceWorker.ready;
      const raw = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";
      const pad = "=".repeat((4 - (raw.length % 4)) % 4);
      const bytes = Uint8Array.from(atob((raw + pad).replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes as BufferSource });
      await api("/api/friends/reminders", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON() }),
      });
      setThisEndpoint(sub.endpoint);
      setDevices(dv => [...(dv ?? []), { endpoint: sub.endpoint, created_at: new Date().toISOString() }]);
    } catch { /* permission denied or unsupported */ }
  }

  function pickTour(t: "pga" | "euro") {
    setTour(t);
    try { localStorage.setItem("favorite-tour", t); } catch { /* fine */ }
  }

  const displayName = user?.username || user?.firstName || user?.primaryEmailAddress?.emailAddress?.split("@")[0] || "…";
  const deviceHost = (e: string) => { try { return new URL(e).hostname; } catch { return "device"; } };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <PageHead kicker="Profile · notifications · defaults" title="Settings" />

      <div style={card}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Profile</div>
        <Row label={`Friends see you as “${displayName}”`}
          sub="Username beats first name beats email prefix — set a username to control it.">
          <button onClick={() => clerk.openUserProfile()} style={{ ...btnQuiet, marginLeft: "auto" }}>
            Manage account
          </button>
        </Row>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Pick reminders</div>
        {prefs && (
          <>
            <Row label="Weekly 3 reminders" sub="Nudge the day before an event locks when your 3 picks aren't in — all devices">
              <Toggle on={prefs.remind_weekly} busy={busyPref === "remind_weekly"} onClick={() => flipPref("remind_weekly")} />
            </Row>
            <Row label="Fade Game reminders" sub="Same nudge for missing fades — all devices">
              <Toggle on={prefs.remind_fades} busy={busyPref === "remind_fades"} onClick={() => flipPref("remind_fades")} />
            </Row>
          </>
        )}
        {devices !== null && devices.length === 0 && (
          <Row label="No devices subscribed"
            sub="Reminders arrive as push notifications — subscribe this device to get them.">
            <button onClick={subscribeThisDevice} style={{ ...btnQuiet, marginLeft: "auto" }}>Subscribe</button>
          </Row>
        )}
        {(devices ?? []).map(d => (
          <Row key={d.endpoint}
            label={d.endpoint === thisEndpoint ? "This device" : `Device via ${deviceHost(d.endpoint)}`}
            sub={`subscribed ${String(d.created_at).slice(0, 10)}`}>
            <button onClick={() => forgetDevice(d.endpoint)} style={{ ...btnQuiet, marginLeft: "auto" }}>
              Remove
            </button>
          </Row>
        ))}
        {devices !== null && devices.length > 0 && !thisEndpoint && "PushManager" in window && (
          <Row label="This device isn't subscribed" sub="Add it to get reminders here too.">
            <button onClick={subscribeThisDevice} style={{ ...btnQuiet, marginLeft: "auto" }}>Subscribe</button>
          </Row>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 12 }}>
          <button onClick={testPush} style={btnQuiet}>Send test notification</button>
          {testMsg && <span style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>{testMsg}</span>}
        </div>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Defaults</div>
        <Row label="Favorite tour" sub="Home and This Week open here (this device)">
          <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
            {([["pga", "PGA"], ["euro", "DPWT"]] as const).map(([id, label]) => (
              <button key={id} onClick={() => pickTour(id)} style={{
                ...btnQuiet,
                color: tour === id ? "#081f14" : "var(--bc-muted)",
                background: tour === id ? "var(--bc-yellow)" : "transparent",
                borderColor: tour === id ? "var(--bc-yellow)" : "var(--bc-line)",
              }}>{label}</button>
            ))}
          </div>
        </Row>
        <Row label="Default game" sub="The Games and Standings tabs remember the last game you opened — nothing to set." />
      </div>

      <div style={card}>
        <div style={{ fontWeight: 800, marginBottom: 6 }}>Your data</div>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "0.82em", lineHeight: 1.6 }}>
          What we store: your account (managed by Clerk — email, optional
          username), your picks, fades, round picks, bets and tails, group
          memberships, notification devices, and the reminder switches above.
          Picks stay hidden from other players until each event locks.
          Nothing is sold or shared; the site keeps no ad trackers. Want
          something deleted? Leave your groups and remove devices here, or
          ask Jack to purge your rows.
        </p>
      </div>
    </div>
  );
}
