"use client";

/**
 * The Friends page's current group, shared by everything below the group
 * bar. Loaded once; boards and standings read `groupQuery` and pass it to
 * their routes (which already scope by group_id and 403 non-members —
 * lib/gameScope.ts). Which group opens is Jack's lib/activeGroup.ts rule.
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { pickActiveGroup } from "@/lib/activeGroup";
import type { Group } from "./GroupsTab";
import { useApi } from "./shared";

const STORE_KEY = "friends-group";

type ActiveGroupState = {
  /** null while loading. */
  groups: Group[] | null;
  /** The current group, or null (loading, or in no group). */
  group: Group | null;
  choose: (id: number) => void;
  reload: () => void;
  /** "&group_id=12" for a board URL, or "" (no group: the route's own default). */
  groupQuery: string;
};

const Ctx = createContext<ActiveGroupState>({
  groups: null, group: null, choose: () => {}, reload: () => {}, groupQuery: "",
});

export const useActiveGroup = () => useContext(Ctx);

export function ActiveGroupProvider({ children }: { children: React.ReactNode }) {
  const api = useApi();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);

  const reload = useCallback(() => {
    api("/api/friends/groups")
      .then(d => {
        const gs = (d.groups as Group[]) ?? [];
        setGroups(gs);
        const linked = Number(new URLSearchParams(window.location.search).get("group")) || null;
        let stored: number | null = null;
        try { stored = Number(localStorage.getItem(STORE_KEY)) || null; } catch { /* none */ }
        const ids = gs.map(g => g.id);
        setActiveId(prev => {
          // Keep a choice made on this page if it's still valid (e.g. after joining another group).
          if (prev !== null && ids.includes(prev)) return prev;
          try { return pickActiveGroup(ids, linked, stored); } catch { return ids[0] ?? null; }
        });
      })
      .catch(() => setGroups([]));
  }, [api]);
  useEffect(reload, [reload]);

  const choose = useCallback((id: number) => {
    setActiveId(id);
    try { localStorage.setItem(STORE_KEY, String(id)); } catch { /* fine */ }
  }, []);

  const group = groups?.find(g => g.id === activeId) ?? null;
  const groupQuery = group ? `&group_id=${group.id}` : "";

  return <Ctx.Provider value={{ groups, group, choose, reload, groupQuery }}>{children}</Ctx.Provider>;
}
