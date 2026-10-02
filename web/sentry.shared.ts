/**
 * Sentry settings shared by browser, server and edge. Error monitoring
 * only, tuned for privacy:
 *   - no DSN env var → Sentry stays off (local dev, previews without it)
 *   - dataCollection locked down → no user info, cookies, headers or
 *     request/response bodies (chat messages never leave via Sentry).
 *     v11 collects ALL of these by default, so each is set explicitly.
 *   - no session replay → nobody's screen is recorded
 *   - 10% of requests traced for performance, enough to spot slow routes
 */
import type { BrowserOptions } from "@sentry/nextjs";

export const sentryOptions: BrowserOptions = {
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  enabled: !!process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_VERCEL_ENV ?? process.env.NODE_ENV,
  dataCollection: {
    userInfo: false,
    cookies: false,
    httpHeaders: false,
    httpBodies: [],
    urlQueryParams: true,   // ids like group_id/tournament_id; secrets are filtered by the SDK
    genAI: { inputs: false, outputs: false },
  },
  tracesSampleRate: 0.1,
};
