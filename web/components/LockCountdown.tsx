"use client";

/** "Locks in 4h 12m · midnight ET" — ticks every 30s, flips to "Locked".
 *  The time comes from lib/lockTime.ts, the same clock the server
 *  enforces, so the countdown can never disagree with the lock. */
import { useEffect, useState } from "react";
import { lockAt, TOUR_TZ_LABEL } from "@/lib/lockTime";

export default function LockCountdown({ startDate, tour, addDays = 0, label = "Locks" }: {
  startDate: string; tour: string; addDays?: number; label?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  if (!startDate) return null;
  const at = lockAt(startDate, tour, addDays).getTime();
  if (isNaN(at)) return null;
  const left = at - now;
  const tz = TOUR_TZ_LABEL[tour] ?? "ET";

  if (left <= 0) return <span style={{ color: "var(--bc-muted)", fontWeight: 700 }}>Locked</span>;
  const d = Math.floor(left / 86_400_000);
  const h = Math.floor((left % 86_400_000) / 3_600_000);
  const m = Math.floor((left % 3_600_000) / 60_000);
  const soon = left < 3 * 3_600_000;
  return (
    <span style={{ color: soon ? "var(--bc-orange)" : "var(--bc-green)", fontWeight: 700 }}>
      {label} in {d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`}
      <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · midnight {tz}</span>
    </span>
  );
}
