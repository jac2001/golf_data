/**
 * Who may call a scheduled-job route (model-sync, reminders-cron).
 *
 * Vercel Cron sends `Authorization: Bearer $CRON_SECRET` automatically
 * when the env var is set; the Tuesday GitHub workflow sends the same
 * header. The old check only ran IF the secret was set, so with it unset
 * the routes were open to anyone with the URL — fail-open. Now:
 *   - secret set   → the header must match
 *   - secret unset → refused in production (fail-closed), allowed in
 *                    local dev so `next dev` still works
 */
export function cronUnauthorized(req: Request): Response | null {
  const secret = process.env.CRON_SECRET;
  if (!secret) {
    if (process.env.VERCEL_ENV === "production") {
      return Response.json({ error: "CRON_SECRET is not configured" }, { status: 503 });
    }
    return null;
  }
  return req.headers.get("authorization") === `Bearer ${secret}`
    ? null
    : Response.json({ error: "Unauthorized" }, { status: 401 });
}
