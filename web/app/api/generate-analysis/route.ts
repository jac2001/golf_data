/**
 * /api/generate-analysis — owner-only relay.
 *
 * The Render endpoint kicks a BATCH of LLM calls, so it now demands the
 * proxy secret; this route holds the secret server-side and only fires
 * for the site owner (same LEAGUE_OWNER_EMAIL gate as the league zone).
 */
import { currentUser } from "@clerk/nextjs/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST() {
  const user = await currentUser();
  const owner = (process.env.LEAGUE_OWNER_EMAIL ?? "").toLowerCase();
  const isOwner = !!owner && (user?.emailAddresses ?? [])
    .some(e => e.emailAddress.toLowerCase() === owner);
  if (!isOwner) {
    return Response.json({ detail: "Analysis reruns are owner-only." }, { status: 403 });
  }

  const upstream = await fetch(`${API_BASE}/api/generate-analysis`, {
    method: "POST",
    headers: { "X-Chat-Proxy-Secret": process.env.CHAT_PROXY_SECRET ?? "" },
  });
  return Response.json(await upstream.json().catch(() => ({})), { status: upstream.status });
}
