/**
 * /api/version — which deployment is serving. The client compares this
 * against the value it loaded with; a mismatch means the running bundle
 * is stale (the recurring installed-PWA ghost) and the UpdateToast
 * offers a reload. Public and tiny by design.
 */

export function GET() {
  return Response.json(
    { v: process.env.VERCEL_GIT_COMMIT_SHA ?? "dev" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
