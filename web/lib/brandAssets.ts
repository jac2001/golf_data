/**
 * Brand files for the server-drawn images (Sunday recap, pick receipts,
 * link preview): the badge and Archivo Black (SIL OFL, assets/fonts/OFL.txt).
 * Read once per server instance. Node only: these use the filesystem.
 * The routes that use them list the files in next.config.ts
 * (outputFileTracingIncludes) so they ship with the function.
 */
import { readFile } from "node:fs/promises";
import { join } from "node:path";

// Literal paths, one per file: a path built from a variable makes the
// bundler trace the whole project into these routes.
let badgeP: Promise<string> | null = null;
/** The round badge as a data URL, or "" if it can't be read (images still render). */
export const brandBadge = () => (badgeP ??= readFile(join(process.cwd(), "assets/brand/badge.png"))
  .then(b => `data:image/png;base64,${b.toString("base64")}`).catch(() => ""));

let fontP: Promise<ArrayBuffer | null> | null = null;
/** Archivo Black for ImageResponse `fonts`, or null (falls back to the default font). */
export const archivoBlack = () => (fontP ??= readFile(join(process.cwd(), "assets/fonts/ArchivoBlack-Regular.ttf"))
  .then(b => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer).catch(() => null));

/** The `fonts` option for ImageResponse: Archivo Black when it loaded. */
export async function brandFonts() {
  const data = await archivoBlack();
  return data ? [{ name: "Archivo Black", data, weight: 400 as const, style: "normal" as const }] : [];
}
