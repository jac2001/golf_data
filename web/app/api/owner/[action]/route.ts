/**
 * /api/owner/[action] — the admin relay for the API's owner-only actions.
 * ======================================================================
 * Render refuses these without the proxy secret (api/owner_guard.py), so
 * the browser can't call them directly. This route checks the signed-in
 * account is an admin (lib/admin.ts), allows only the actions and methods
 * listed below, bounds their parameters, and forwards with the secret.
 * Hiding a button isn't the protection; this check and Render's are.
 */
import { auth } from "@clerk/nextjs/server";
import { isAdmin } from "@/lib/admin";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// action -> upstream path and the methods it accepts.
const ACTIONS: Record<string, { path: string; methods: string[] }> = {
  "refresh-bets":        { path: "/api/refresh-bets",              methods: ["POST"] },
  "refresh-odds":        { path: "/api/refresh-odds",              methods: ["POST"] },
  "refresh-dg-odds":     { path: "/api/refresh-dg-odds",           methods: ["POST"] },
  "refresh-intel":       { path: "/api/refresh-intel",             methods: ["POST"] },
  "refresh-hole-scores": { path: "/api/live/refresh-hole-scores",  methods: ["POST"] },
  "picks":               { path: "/api/picks",                     methods: ["POST", "DELETE"] },
  "settings":            { path: "/api/settings",                  methods: ["PATCH"] },
};

async function relay(req: Request, params: Promise<{ action: string }>) {
  const { userId } = await auth();
  if (!userId) return Response.json({ detail: "Sign in first." }, { status: 401 });
  if (!isAdmin(userId)) return Response.json({ detail: "Admins only." }, { status: 403 });

  const { action } = await params;
  const spec = ACTIONS[action];
  if (!spec) return Response.json({ detail: "Unknown action." }, { status: 404 });
  if (!spec.methods.includes(req.method)) return Response.json({ detail: "Method not allowed." }, { status: 405 });

  // refresh-intel launches LLM work per golfer: cap how many.
  let query = "";
  if (action === "refresh-intel") {
    const n = Number(new URL(req.url).searchParams.get("top_n") ?? 20);
    query = `?top_n=${Math.min(Math.max(Number.isFinite(n) ? Math.round(n) : 20, 1), 30)}`;
  }

  const body = req.method === "POST" || req.method === "DELETE" || req.method === "PATCH"
    ? await req.text() : undefined;
  const upstream = await fetch(`${API_BASE}${spec.path}${query}`, {
    method: req.method,
    headers: {
      "X-Chat-Proxy-Secret": process.env.CHAT_PROXY_SECRET ?? "",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body || undefined,
    cache: "no-store",
  });
  return Response.json(await upstream.json().catch(() => ({})), { status: upstream.status });
}

type Ctx = { params: Promise<{ action: string }> };
export const POST = (req: Request, { params }: Ctx) => relay(req, params);
export const DELETE = (req: Request, { params }: Ctx) => relay(req, params);
export const PATCH = (req: Request, { params }: Ctx) => relay(req, params);
