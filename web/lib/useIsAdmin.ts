"use client";

/**
 * useIsAdmin: whether the signed-in viewer is a site admin (lib/admin.ts).
 * For showing admin-only controls. It is NOT the protection: the server
 * routes check again (app/api/owner/[action], api/owner_guard.py).
 */
import { useUser } from "@clerk/nextjs";
import { isAdmin } from "@/lib/admin";

export function useIsAdmin(): boolean {
  const { user } = useUser();
  return isAdmin(user?.id);
}
