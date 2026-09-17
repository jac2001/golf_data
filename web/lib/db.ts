/**
 * db.ts — Neon Postgres client (Friends Game data).
 * ===================================================
 * User-generated data (picks, tailed bets) lives here, NOT in the
 * FastAPI/CSV world: Render's disk is wiped on every deploy, and the
 * repo CSVs are the model's data. Lazy init so `next build` doesn't
 * crash when DATABASE_URL isn't present at build time.
 */

import { neon } from "@neondatabase/serverless";

type Sql = ReturnType<typeof neon>;

let _sql: Sql | null = null;

export function getSql(): Sql {
  if (!_sql) _sql = neon(process.env.DATABASE_URL!);
  return _sql;
}

/** The FastAPI base, reachable from Vercel functions (server-side). */
export const MODEL_API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
