import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs/config";

const nextConfig: NextConfig = {
  // The share images read the brand badge from disk at request time.
  outputFileTracingIncludes: {
    "/api/recap": ["./assets/brand/badge.png"],
    "/api/receipt": ["./assets/brand/badge.png"],
  },
};

// Source maps (readable stack traces) upload only when a Sentry auth
// token is configured; without one the build is unchanged.
export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
  telemetry: false,
});
