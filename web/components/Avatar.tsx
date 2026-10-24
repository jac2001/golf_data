"use client";

/**
 * A member's face on the group boards: their uploaded photo, The Model's
 * golf-ball badge, or their initials on a tinted circle. useAvatars loads
 * the photos once per page (members only, /api/friends/avatars).
 */
import { useEffect, useState } from "react";

const cache = new Map<string, Promise<Record<string, string>>>();

/** user_id -> photo URL for the people you play with (in this group, if given). */
export function useAvatars(groupId?: number | null): Record<string, string> {
  const [map, setMap] = useState<Record<string, string>>({});
  useEffect(() => {
    const key = String(groupId ?? "all");
    if (!cache.has(key)) {
      cache.set(key, fetch(`/api/friends/avatars${groupId ? `?group_id=${groupId}` : ""}`)
        .then(r => (r.ok ? r.json() : { avatars: {} }))
        .then(d => (d.avatars ?? {}) as Record<string, string>)
        .catch(() => ({})));
    }
    let alive = true;
    cache.get(key)!.then(m => { if (alive) setMap(m); });
    return () => { alive = false; };
  }, [groupId]);
  return map;
}

function initials(name: string): string {
  const parts = name.replace(/[^\p{L}\s'-]/gu, " ").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export default function Avatar({ userId, name, url, size = 24 }: {
  userId: string; name: string; url?: string; size?: number;
}) {
  const box: React.CSSProperties = { width: size, height: size, borderRadius: "50%", flexShrink: 0,
    display: "inline-flex", alignItems: "center", justifyContent: "center", verticalAlign: "middle" };
  const src = userId === "model" ? "/brand/badge.png" : url;
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" width={size} height={size} style={{ ...box, objectFit: "cover" }} />;
  }
  return (
    <span aria-hidden style={{ ...box, background: "var(--bc-raised)", color: "var(--bc-text)",
      fontSize: Math.round(size * 0.42), fontWeight: 800, letterSpacing: 0 }}>
      {initials(name)}
    </span>
  );
}
