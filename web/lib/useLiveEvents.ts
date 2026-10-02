"use client";

/**
 * useLiveEvents — which events are in play right now (locked, not yet
 * finished), from the API's events/open list. The nav and the home page
 * use it to make Match Center the front door Thursday through Sunday.
 * Re-checks every 5 minutes so a tab left open flips at tee-off and back
 * after the finish. Failure reads as "nothing live": the site simply
 * stays in its off-week layout.
 */

import { useEffect, useState } from "react";
import { getOpenEvents, OpenEvent } from "@/lib/api";

export function useLiveEvents(): OpenEvent[] {
  const [live, setLive] = useState<OpenEvent[]>([]);
  useEffect(() => {
    let alive = true;
    const check = () => getOpenEvents()
      .then(d => { if (alive) setLive((d.events ?? []).filter(e => e.locked && !e.finished)); })
      .catch(() => { if (alive) setLive([]); });
    check();
    const t = setInterval(check, 300_000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return live;
}
