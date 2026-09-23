"use client";

/**
 * UpdateToast — "a new version exists, tap to reload."
 * =====================================================
 * An installed PWA keeps its running bundle until fully closed, so a
 * user can sit on last week's app indefinitely (three incidents and
 * counting). This polls /api/version — crucially ALSO on
 * visibilitychange, the exact moment a resumed PWA is stalest — and
 * offers one tap to the current deployment. It never force-reloads:
 * yanking the page mid-pick would be worse than staleness.
 */

import React, { useEffect, useRef, useState } from "react";

const POLL_MS = 5 * 60_000;

export default function UpdateToast() {
  const baseline = useRef<string | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let stop = false;
    async function check() {
      try {
        const res = await fetch("/api/version", { cache: "no-store" });
        if (!res.ok) return;
        const { v } = await res.json();
        if (stop || !v) return;
        if (baseline.current === null) baseline.current = v;   // what we loaded with
        else if (v !== baseline.current) setStale(true);
      } catch { /* offline — nothing to update to */ }
    }
    check();
    const timer = setInterval(check, POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") check(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { stop = true; clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, []);

  if (!stale) return null;
  return (
    <button onClick={() => location.reload()} style={{
      position: "fixed", bottom: 18, left: "50%", transform: "translateX(-50%)",
      zIndex: 1000, cursor: "pointer", fontFamily: "inherit",
      background: "var(--bc-yellow)", color: "#081f14", fontWeight: 800,
      fontSize: "0.82em", padding: "11px 20px", borderRadius: 999,
      border: "none", boxShadow: "0 4px 18px rgba(0,0,0,0.45)",
    }}>
      Golf Edge updated — tap to reload
    </button>
  );
}
