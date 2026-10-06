/**
 * /api/watchdog — makes sure the GitHub pipeline actually ran.
 * ============================================================
 * GitHub's scheduled workflows are best-effort on a free public repo: in
 * one week a settlement was dropped, another started 7 hours late, France
 * settled hours late, and a Tuesday prediction run never started. Vercel
 * Cron is reliable, so once a day (vercel.json, 15:00 UTC) this route
 * checks the OUTCOMES and re-dispatches whatever is missing:
 *
 *   1. A finished event (last 10 days) that still isn't settled
 *        PGA  → data-refresh, schedule=post-tournament
 *        DPWT → data-refresh, schedule=monday (holds the euro settle step)
 *   2. Tue+ and an open PGA event starting within 3 days with no predictions
 *        → tuesday-predictions
 *   3. Wed+ and an open DPWT event starting within 3 days with no predictions
 *        → data-refresh, schedule=wednesday-morning
 *
 * Safe to run any time: a workflow already queued/running, or dispatched
 * in the last 3 hours, is left alone. Every dispatch is reported to Sentry
 * so a missed schedule becomes an alert instead of a surprise.
 *
 * Needs GITHUB_DISPATCH_TOKEN (fine-grained, this repo only, Actions:
 * read/write). Without it the route only reports what it WOULD do.
 */
import * as Sentry from "@sentry/nextjs";
import { cronUnauthorized } from "@/lib/cronAuth";
import { MODEL_API } from "@/lib/db";

const REPO = "jac2001/golf_data";
const COOLDOWN_MS = 3 * 3_600_000;

type Ev = { tournament_id: string; name: string; tour: string; start_date: string;
  locked: boolean; finished: boolean };

async function api<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${MODEL_API}${path}`, { cache: "no-store" });
    return res.ok ? await res.json() as T : null;
  } catch { return null; }
}

async function github(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${process.env.GITHUB_DISPATCH_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init?.headers ?? {}),
    },
  });
}

/** Busy = a run of this workflow is queued/running, or one started recently. */
async function busy(workflow: string): Promise<boolean> {
  const res = await github(`/actions/workflows/${workflow}/runs?per_page=5`);
  if (!res.ok) return true;   // can't tell → don't pile on
  const { workflow_runs } = await res.json() as
    { workflow_runs: { status: string; created_at: string }[] };
  return workflow_runs.some(r => r.status !== "completed"
    || Date.now() - Date.parse(r.created_at) < COOLDOWN_MS);
}

export async function GET(req: Request) {
  const denied = cronUnauthorized(req);
  if (denied) return denied;

  const events = (await api<{ events: Ev[] }>("/api/events/open"))?.events;
  if (!events) return Response.json({ ok: false, log: ["events/open unavailable — nothing checked"] });

  const now = Date.now();
  const day = new Date().getUTCDay();          // 0 Sun … 2 Tue, 3 Wed
  const daysFrom = (d: string) => (Date.parse(d) - now) / 86_400_000;
  const needs: { workflow: string; schedule?: string; why: string }[] = [];

  // 1. Finished but unsettled.
  for (const e of events.filter(e => e.finished && daysFrom(e.start_date) > -10)) {
    const earn = await api<{ settled?: boolean }>(`/api/results/earnings?tournament_id=${e.tournament_id}`);
    if (earn && !earn.settled) {
      needs.push(e.tournament_id.startsWith("E")
        ? { workflow: "data-refresh.yml", schedule: "monday", why: `${e.name} finished but isn't settled` }
        : { workflow: "data-refresh.yml", schedule: "post-tournament", why: `${e.name} finished but isn't settled` });
    }
  }

  // 2 + 3. This week's predictions missing.
  for (const e of events.filter(e => !e.locked && !e.finished && daysFrom(e.start_date) <= 3)) {
    const euro = e.tournament_id.startsWith("E");
    if (euro ? day < 3 : day < 2) continue;    // too early in the week to expect them
    const p = await api<{ tournament_id?: string }>(`/api/predictions?limit=1&tournament_id=${e.tournament_id}`);
    if (String(p?.tournament_id ?? "").toUpperCase() === e.tournament_id) continue;
    needs.push(euro
      ? { workflow: "data-refresh.yml", schedule: "wednesday-morning", why: `${e.name} has no predictions yet` }
      : { workflow: "tuesday-predictions.yml", why: `${e.name} has no predictions yet` });
  }

  const log: string[] = [];
  if (!needs.length) return Response.json({ ok: true, log: ["all good — nothing missing"] });
  const armed = !!process.env.GITHUB_DISPATCH_TOKEN;

  // One dispatch per workflow+schedule; data-refresh runs serialize anyway.
  const seen = new Set<string>();
  for (const n of needs) {
    const id = `${n.workflow}:${n.schedule ?? ""}`;
    if (seen.has(id)) { log.push(`${n.why} — covered by the dispatch above`); continue; }
    seen.add(id);
    if (!armed) { log.push(`${n.why} → WOULD dispatch ${id} (no GITHUB_DISPATCH_TOKEN)`); continue; }
    if (await busy(n.workflow)) { log.push(`${n.why} → ${n.workflow} is running or ran recently; leaving it`); continue; }
    const res = await github(`/actions/workflows/${n.workflow}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main", ...(n.schedule ? { inputs: { schedule: n.schedule } } : {}) }),
    });
    const ok = res.status === 204;
    log.push(`${n.why} → ${ok ? "dispatched" : `dispatch FAILED (${res.status})`} ${id}`);
    Sentry.captureMessage(`Watchdog: ${n.why} → ${ok ? "dispatched" : "dispatch failed"} ${id}`, ok ? "warning" : "error");
  }
  return Response.json({ ok: true, armed, log });
}
