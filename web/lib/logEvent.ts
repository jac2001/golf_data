"use client";

/**
 * Log a browser-side product event (POST /api/events, which allowlists the
 * names). Fire-and-forget: measurement never blocks or breaks the page.
 * Signed-out visitors are simply not logged (the route needs a session).
 */
export function logEvent(event: string, props: Record<string, string | number | boolean> = {}): void {
  try {
    fetch("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, props }), keepalive: true,
    }).catch(() => {});
  } catch { /* never */ }
}
