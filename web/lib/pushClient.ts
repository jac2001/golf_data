"use client";

/**
 * pushClient.ts — browser-side push + "has picked" helpers.
 * ==========================================================
 * Shared by Settings (the full device list) and InstallCard (the
 * one-time ask after a first pick), so there is one subscribe path.
 */

type Api = (url: string, init?: RequestInit) => Promise<unknown>;

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window
    && "Notification" in window;
}

/** Ask permission (if needed), subscribe this browser, save it. Returns the
 *  endpoint, or null when permission was refused or push is unsupported. */
export async function subscribeThisDevice(api: Api): Promise<string | null> {
  if (!pushSupported()) return null;
  if ((await Notification.requestPermission()) !== "granted") return null;
  const reg = await navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);
  const raw = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";
  const pad = "=".repeat((4 - (raw.length % 4)) % 4);
  const bytes = Uint8Array.from(atob((raw + pad).replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes as BufferSource });
  await api("/api/friends/reminders", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription: sub.toJSON() }),
  });
  return sub.endpoint;
}

/** This browser's current subscription endpoint, or "" if none. */
export async function currentEndpoint(): Promise<string> {
  if (!pushSupported()) return "";
  try {
    const reg = await navigator.serviceWorker.register("/sw.js");
    return (await reg.pushManager.getSubscription())?.endpoint ?? "";
  } catch { return ""; }
}

// ── "has this device made a pick?" ───────────────────────────────────────────
// Set after any successful pick save; InstallCard listens for the event so
// the card can appear right after the pick, not on the next page load.

const PICKED_KEY = "ge-has-picked";
export const PICKED_EVENT = "ge:picked";

export function markPicked(): void {
  try { localStorage.setItem(PICKED_KEY, "1"); } catch { /* fine */ }
  window.dispatchEvent(new Event(PICKED_EVENT));
}

export function hasPicked(): boolean {
  try { return localStorage.getItem(PICKED_KEY) === "1"; } catch { return false; }
}
