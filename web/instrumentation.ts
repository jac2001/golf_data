/**
 * Server-side Sentry for route handlers, server components and the proxy.
 * onRequestError reports any error Next catches while rendering or
 * handling a request — the crashes users would otherwise only see as a
 * blank 500.
 */
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "./sentry.shared";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init(sentryOptions);
  }
}

export const onRequestError = Sentry.captureRequestError;
