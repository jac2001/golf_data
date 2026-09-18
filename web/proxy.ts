/**
 * proxy.ts — request gate (Next 16's rename of middleware.ts)
 * ============================================================
 * Runs before every matched request. Clerk attaches the session here;
 * routes listed in PROTECTED bounce signed-out visitors to /sign-in.
 * The league zone gets a second, owner-only check in its layouts —
 * this file only guarantees "signed in", not "is Jack".
 */

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest, type NextFetchEvent } from "next/server";

// Signed-in-only. The public storefront stays open: / (home),
// /methodology (trust), /predictions (top-10 teaser — the page itself
// truncates for signed-out viewers), sign-in/up. Everything with real
// edge (full forecast, betting, live, players) or real cost (assistant
// burns API credits per question) needs the free account.
const isProtected = createRouteMatcher([
  "/fantasy(.*)",
  "/mypicks(.*)",
  "/friends(.*)",
  "/betting(.*)",
  "/live(.*)",
  "/players(.*)",
  "/assistant(.*)",
  "/history(.*)",
  "/api/friends(.*)",
]);

const withClerk = clerkMiddleware(async (auth, req) => {
  if (!isProtected(req)) return;

  // API routes answer signed-out callers HERE with an uncacheable 401.
  // Clerk's protect() would 404 instead — and that 404 is the prerendered
  // static not-found page, which Vercel's CDN happily caches UNDER THE API
  // PATH. One anonymous GET then poisons the route for every signed-in
  // user until the next deploy. (CDN cache keys are per-URL; they don't
  // know one response was auth-dependent unless told via Cache-Control.)
  if (req.nextUrl.pathname.startsWith("/api/")) {
    const { userId } = await auth();
    if (!userId) {
      return Response.json(
        { error: "Unauthorized" },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }
    return;
  }

  await auth.protect();  // pages: redirect to /sign-in and back
});

/** Host gate BEFORE Clerk ever sees the request: the old vercel.app URL
 *  still lives in browsers with pre-migration dev-instance cookies that
 *  production Clerk rejects as invalid (→ HTML 404s). One canonical
 *  domain, one cookie jar. 308 keeps the method + path. */
export default function proxy(req: NextRequest, event: NextFetchEvent) {
  const host = req.headers.get("host") ?? "";
  if (host.endsWith(".vercel.app")) {
    const url = new URL(req.nextUrl.pathname + req.nextUrl.search, "https://playgolfedge.com");
    return NextResponse.redirect(url, 308);
  }
  return withClerk(req, event);
}

export const config = {
  matcher: [
    // Skip Next.js internals and static assets
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
