/**
 * /api/generate-analysis — owner-only relay.
 *
 * The Render endpoint kicks a BATCH of LLM calls, so it now demands the
 * proxy secret; this route holds the secret server-side and only fires
 * for site admins (lib/admin.ts, the same list as /api/owner/*).
 */
import { auth } from "@clerk/nextjs/server";
import { isAdmin } from "@/lib/admin";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST() {
  const { userId } = await auth();
  if (!isAdmin(userId)) {
    return Response.json({ detail: "Analysis reruns are owner-only." }, { status: 403 });
  }

  const upstream = await fetch(`${API_BASE}/api/generate-analysis`, {
    method: "POST",
    headers: { "X-Chat-Proxy-Secret": process.env.CHAT_PROXY_SECRET ?? "" },
  });
  return Response.json(await upstream.json().catch(() => ({})), { status: upstream.status });
}
