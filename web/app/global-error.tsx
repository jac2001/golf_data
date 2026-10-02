"use client";

/**
 * Last-resort error screen: a crash in the root layout itself. Reports to
 * Sentry and offers a reload instead of a blank page.
 */
import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { Sentry.captureException(error); }, [error]);
  return (
    <html lang="en">
      <body style={{ background: "#0c2a1c", color: "#f2f7f0", fontFamily: "system-ui, sans-serif",
        display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", margin: 0 }}>
        <div style={{ textAlign: "center", padding: 24 }}>
          <h1 style={{ fontSize: "1.4em" }}>Something went wrong</h1>
          <p style={{ color: "#9dbfa9" }}>It&apos;s been reported. Try again in a moment.</p>
          <button onClick={() => reset()} style={{ marginTop: 12, padding: "10px 18px", borderRadius: 4,
            border: "none", background: "#ffd24a", color: "#081f14", fontWeight: 800, cursor: "pointer" }}>
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
