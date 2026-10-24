/**
 * GET /api/friends/avatars[?group_id=N] → { avatars: { [user_id]: imageUrl } }
 * ============================================================================
 * Profile photos for the people you play with, for the group boards. Only
 * photos someone uploaded (Clerk's hasImage): everyone else is drawn with
 * their initials, The Model with the golf-ball badge. Members only (the
 * same people lib/gameScope.ts lets you see); no group = all your groups.
 * Cached 10 minutes per server instance; photos change rarely.
 */
import { auth, clerkClient } from "@clerk/nextjs/server";
import { visibleUserIds } from "@/lib/gameScope";

const cache = new Map<string, { url: string | null; at: number }>();
const TTL = 10 * 60 * 1000;

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const groupId = Number(new URL(req.url).searchParams.get("group_id") || 0) || undefined;
  const ids = await visibleUserIds(userId, groupId);
  if (!ids) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  const people = ids.filter(id => id.startsWith("user_"));
  const now = Date.now();
  const missing = people.filter(id => !cache.has(id) || now - cache.get(id)!.at > TTL);
  if (missing.length) {
    try {
      const client = await clerkClient();
      const { data } = await client.users.getUserList({ userId: missing, limit: 100 });
      const found = new Map(data.map(u => [u.id, u.hasImage ? u.imageUrl : null]));
      for (const id of missing) cache.set(id, { url: found.get(id) ?? null, at: now });
    } catch { /* no photos this time: initials everywhere */ }
  }
  const avatars: Record<string, string> = {};
  for (const id of people) {
    const url = cache.get(id)?.url;
    if (url) avatars[id] = url;
  }
  return Response.json({ avatars });
}
