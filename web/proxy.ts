/**
 * proxy.ts — request gate (Next 16's rename of middleware.ts)
 * ============================================================
 * Runs before every matched request. Clerk attaches the session here;
 * routes listed in PROTECTED bounce signed-out visitors to /sign-in.
 * The league zone gets a second, owner-only check in its layouts —
 * this file only guarantees "signed in", not "is Jack".
 */

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtected = createRouteMatcher([
  "/fantasy(.*)",
  "/mypicks(.*)",
  "/friends(.*)",
  "/api/friends(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and static assets
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
