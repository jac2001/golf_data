/**
 * /api/model-sync — the model takes its turn.
 * ============================================
 * Called by a daily Vercel Cron (and callable manually). For every open,
 * unlocked, PGA event with fresh predictions the model:
 *   - weekly game: picks its 3 highest EXPECTED-PAYOUT players
 *     (Jack's expectedPayout in lib/modelBrain.ts)
 *   - fade game: fades the 3 LOWEST expected payouts among its own
 *     top-20 pool (Jack's modelFadePicks) — the favorites it believes
 *     in least
 *   - round game: picks its best unused win-chance for the next
 *     unlocked round (Jack's modelRoundPick) — it obeys the
 *     once-per-event rule like everyone else
 * Rows are inserted as user_id 'model', so locks, hidden-until-tee-off,
 * and grading treat it exactly like a human. Idempotent: an event/round
 * that already has model picks is skipped.
 *
 * Lives OUTSIDE /api/friends so Clerk doesn't gate the cron; when
 * CRON_SECRET is set, callers must present it (Vercel Cron does).
 */

import { getSql, MODEL_API } from "@/lib/db";
import { expectedPayout, modelCollegePick, modelFadePicks, modelRoundPick, Probs } from "@/lib/modelBrain";

const MODEL_ID = "model";
const MODEL_NAME = "The Model";

type OpenEvent = {
  tournament_id: string; name: string; tour: string; start_date: string;
  purse: number | null; locked: boolean; has_model: boolean;
};
type PredRow = Probs & { player_name: string };

function roundLocked(startDate: string, round: number): boolean {
  const base = new Date(`${startDate.slice(0, 10)}T00:00:00`);
  const day = new Date(base);
  day.setDate(base.getDate() + (round - 1));
  return isNaN(day.getTime()) || new Date() >= day;
}

export async function GET(req: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret && req.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const sql = getSql();
  const log: string[] = [];

  let events: OpenEvent[] = [];
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { cache: "no-store" });
    if (res.ok) events = (await res.json()).events ?? [];
  } catch { /* no events, nothing to do */ }

  // Predictions exist only for the current PGA event; the response says
  // which tournament they belong to, so we never pick off stale numbers.
  let preds: PredRow[] = [];
  let predsTid = "";
  try {
    const res = await fetch(`${MODEL_API}/api/predictions?limit=200`, { cache: "no-store" });
    if (res.ok) {
      const d = await res.json();
      predsTid = String(d.tournament_id ?? "").toUpperCase();
      preds = (d.players ?? []).filter((p: PredRow) => p.player_name);
    }
  } catch { /* handled below by the tid match */ }

  // Early in the week the DG field is a handful of commitments, and
  // probabilities over a 24-man "field" are junk (they sum to 1 over
  // whoever has entered). The model never bets off a partial field —
  // it waits for the real one, like any bettor should.
  const MIN_FIELD = 50;

  for (const ev of events.filter(e => e.has_model)) {
    const tid = ev.tournament_id.toUpperCase();
    if (tid !== predsTid || preds.length === 0) {
      log.push(`${tid}: no fresh predictions (have ${predsTid || "none"})`);
      continue;
    }
    if (preds.length < MIN_FIELD && !ev.locked) {
      log.push(`${tid}: field too small to bet (${preds.length} players) — waiting for the full field`);
      continue;
    }

    // ── Weekly trio ──
    if (!ev.locked && ev.purse) {
      const have = await sql`
        SELECT 1 FROM picks WHERE user_id = ${MODEL_ID} AND tournament_id = ${tid} LIMIT 1` as unknown[];
      if (have.length === 0) {
        const trio = preds
          .map(p => ({ name: p.player_name, ev$: expectedPayout(ev.purse!, p) }))
          .sort((a, b) => b.ev$ - a.ev$)
          .slice(0, 3);
        for (const p of trio) {
          await sql`
            INSERT INTO picks (user_id, user_name, tournament_id, player_name)
            VALUES (${MODEL_ID}, ${MODEL_NAME}, ${tid}, ${p.name})
            ON CONFLICT (user_id, tournament_id, player_name) DO NOTHING`;
        }
        log.push(`${tid}: weekly trio ${trio.map(t => t.name).join(", ")}`);
      }
    }

    // ── Fade trio: the top-20 favorites it believes in least ──
    if (!ev.locked && ev.purse) {
      const have = await sql`
        SELECT 1 FROM fade_picks WHERE user_id = ${MODEL_ID} AND tournament_id = ${tid} LIMIT 1` as unknown[];
      if (have.length === 0) {
        const fades = modelFadePicks(preds, ev.purse);
        for (const name of fades) {
          await sql`
            INSERT INTO fade_picks (user_id, user_name, tournament_id, player_name)
            VALUES (${MODEL_ID}, ${MODEL_NAME}, ${tid}, ${name})
            ON CONFLICT (user_id, tournament_id, player_name) DO NOTHING`;
        }
        log.push(`${tid}: fade trio ${fades.join(", ")}`);
      }
    }

    // ── College Game: claim the school with the best top-two EV ──
    if (!ev.locked && ev.purse) {
      const have = await sql`
        SELECT 1 FROM college_picks WHERE user_id = ${MODEL_ID} AND tournament_id = ${tid} LIMIT 1` as unknown[];
      if (have.length === 0) {
        try {
          const res = await fetch(`${MODEL_API}/api/colleges/field?tournament_id=${tid}`, { cache: "no-store" });
          const schools = res.ok ? ((await res.json()).schools ?? []) : [];
          const school = modelCollegePick(preds, ev.purse!, schools);
          if (school) {
            await sql`
              INSERT INTO college_picks (user_id, user_name, tournament_id, school)
              VALUES (${MODEL_ID}, ${MODEL_NAME}, ${tid}, ${school})
              ON CONFLICT (user_id, tournament_id) DO NOTHING`;
            log.push(`${tid}: college → ${school}`);
          }
        } catch { /* no college data — the game just has no model this week */ }
      }
    }

    // ── Round game: fill every not-yet-locked round that lacks a pick ──
    const mine = await sql`
      SELECT round, player_name FROM round_picks
      WHERE user_id = ${MODEL_ID} AND tournament_id = ${tid}` as { round: number; player_name: string }[];
    const used = mine.map(m => m.player_name);
    for (let r = 1; r <= 4; r++) {
      if (roundLocked(ev.start_date, r)) continue;
      // Never pick more than one round ahead: round r opens for the model
      // only once r-1 has locked. Without this, any extra invocation
      // (retry, manual call) would fill the whole week on day one.
      if (r > 1 && !roundLocked(ev.start_date, r - 1)) break;
      if (mine.some(m => m.round === r)) continue;
      const pick = modelRoundPick(preds, used);
      if (!pick) break;
      await sql`
        INSERT INTO round_picks (user_id, user_name, tournament_id, round, player_name)
        VALUES (${MODEL_ID}, ${MODEL_NAME}, ${tid}, ${r}, ${pick})
        ON CONFLICT (user_id, tournament_id, round) DO NOTHING`;
      used.push(pick);
      log.push(`${tid}: R${r} → ${pick}`);
    }
  }

  return Response.json({ ok: true, log });
}
