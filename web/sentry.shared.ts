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

// The web project's DSN. Public by design (it ships in every page's
// JavaScript and only allows submitting error reports), so it lives in
// code; NEXT_PUBLIC_SENTRY_DSN overrides it if the project ever changes.
// Committed because the Vercel variable didn't reach builds (2026-10-02).
const WEB_DSN = "https://231f447c919cb84b809234ff1c2ca0c4@o4512187997487104.ingest.us.sentry.io/4512188023570432";
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || WEB_DSN;

export const sentryOptions: BrowserOptions = {
  dsn,
  // Production only: local dev and preview builds stay out of the error feed.
  enabled: process.env.NEXT_PUBLIC_VERCEL_ENV === "production",
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
