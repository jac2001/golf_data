/**
 * /api/chat — the assistant's only public door.
 *
 * The browser never talks to Render's /api/chat directly anymore: this
 * server route requires a Clerk sign-in, then relays the request with
 * the shared CHAT_PROXY_SECRET and the user's id. Render refuses chat
 * requests without the secret (once its env sets CHAT_PROXY_SECRET),
 * so nobody can spend the Anthropic budget by curling the raw API —
 * and per-user daily quotas become enforceable because every request
 * carries a real identity instead of a proxy IP.
 *
 * The upstream response is SSE; we stream its body through untouched.
 */
import { auth } from "@clerk/nextjs/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return Response.json(
      { detail: "Sign in to use the assistant." },
      { status: 401 },
    );
  }

  const body = await req.text();
  const upstream = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Chat-Proxy-Secret": process.env.CHAT_PROXY_SECRET ?? "",
      "X-User-Id": userId,
    },
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "text/event-stream",
      "Cache-Control": "no-store",
    },
  });
}
