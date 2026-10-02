/**
 * Browser-side Sentry: uncaught errors and failed renders on visitors'
 * devices. Runs before the app becomes interactive (Next's
 * instrumentation-client convention).
 */
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "./sentry.shared";

Sentry.init(sentryOptions);

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
