"use client";

/**
 * A choice remembered on this device (tour, game mode) that hydrates
 * SAFELY. Reading localStorage inside useState's initializer looks
 * equivalent but isn't: the server has no storage and renders the
 * fallback, the browser renders the saved value, and React reuses the
 * server's HTML for attributes it thinks match — so the highlighted
 * button and the shown content could disagree (yellow on Let It Ride,
 * College on screen). Render the fallback first, adopt the saved value
 * after mount, write on change.
 */
import { useCallback, useEffect, useState } from "react";

export function useStoredChoice<T extends string>(
  key: string, allowed: readonly T[], fallback: T, persist = true,
): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(fallback);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(key);
      if (saved && (allowed as readonly string[]).includes(saved)) setValue(saved as T);
    } catch { /* storage unavailable: keep the fallback */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const choose = useCallback((v: T) => {
    setValue(v);
    if (persist) { try { localStorage.setItem(key, v); } catch { /* fine */ } }
  }, [key, persist]);

  return [value, choose];
}
