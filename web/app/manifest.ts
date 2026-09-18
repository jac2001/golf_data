/**
 * manifest.ts — the PWA manifest (served at /manifest.webmanifest).
 * ==================================================================
 * This is what makes "Add to Home Screen" install Golf Edge like an
 * app: its own icon, splash colors, and standalone display (no browser
 * chrome). Next generates and links it automatically from this file.
 */

import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Golf Edge",
    short_name: "Golf Edge",
    description: "Golf predictions, betting board, and the Friends Game",
    start_url: "/",
    display: "standalone",
    background_color: "#0c2a1c",
    theme_color: "#081f14",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
