/**
 * Match Center shapes and wording, shared by /match and the home page's
 * live matchup card so both say the same thing about the same weekend.
 */

export type Golfer = { name: string; position: string; earnings: number; up_one: number; thru: string;
  to_par?: number | null; round?: number | null };
export type Line = { user_id: string; user_name: string; total: number; golfers: Golfer[]; rank: number };
export type Slate = {
  tournament_id: string; name: string; tour: "pga" | "euro"; status: "open" | "live" | "settling" | "final";
  projected: boolean; lines: Line[]; me_id: string; data_updated?: string;
  rival: { user_id: string; user_name: string; total: number } | null; gap: number; story: string;
  beating_model: number | null; humans: number;
};
export type CollegeLine = { user_id: string; user_name: string; school: string; total: number; rank: number;
  counting: { name: string; position: string; earnings: number }[] };
export type College = { tournament_id: string; name: string; status: Slate["status"]; projected: boolean;
  lines: CollegeLine[]; me_id: string; story: string } | null;
export type Match = { group?: { id: number; name: string; members: number };
  league: { id: number; name: string } | null; slates: Slate[]; college: College; checked_at?: string };
export type Group = { id: number; name: string };

export const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

export const ordinal = (n: number) =>
  `${n}${["th", "st", "nd", "rd"][((n % 100) - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th"}`;

/** A response (or saved snapshot) we can safely read. Anything else —
 *  an error body, a cached page, a snapshot from an older version of the
 *  page — is treated as absent rather than crashing the render. */
export function isMatch(x: unknown): x is Match {
  const m = x as Match | null;
  return !!m && typeof m === "object" && Array.isArray(m.slates);
}

export function slateHeadline(s: Slate): string {
  const me = s.lines.find(l => l.user_id === s.me_id);
  if (!me) return "You didn't play this one.";
  if (me.rank === 1 && s.lines.filter(l => l.rank === 1).length === 1) {
    return s.status === "final" ? "You won the week." : "You're leading.";
  }
  // Tied for first: name who you're sharing it with.
  if (me.rank === 1) {
    const others = s.lines
      .filter(l => l.rank === 1 && l.user_id !== s.me_id)
      .map(l => l.user_name)
      .join(" & ");
    return s.status === "final"
      ? `You shared the week with ${others}.`
      : `You're tied for the lead with ${others}.`;
  }
  if (s.rival && me.rank > 1) return `You're ${ordinal(me.rank)}. ${s.rival.user_name} leads you by ${money(s.gap)}.`;
  return `You're ${ordinal(me.rank)}.`;
}

/** Just you and the model (no other humans on the slate). */
export function isSoloVsModel(s: Slate): boolean {
  return s.humans <= 1 && s.lines.some(l => l.user_id === "model");
}

/** The card's top line. Solo vs the model names the gap directly;
 *  a group falls back to the rank headline (ties included). */
export function matchHeadline(s: Slate): string {
  const me = s.lines.find(l => l.user_id === s.me_id);
  const model = s.lines.find(l => l.user_id === "model");
  if (!me || !model || !isSoloVsModel(s)) return slateHeadline(s);
  const gap = Math.abs(me.total - model.total);
  const final = s.status === "final";
  if (gap === 0) return final ? "You tied the model." : "You're tied with the model.";
  if (me.total > model.total) return final ? `You beat the model by ${money(gap)}.` : `You're ahead of the model by ${money(gap)}.`;
  return final ? `The model beat you by ${money(gap)}.` : `The model leads you by ${money(gap)}.`;
}

/** "You $248,318 · Model $134,433" — you against whoever matters most:
 *  the model when solo, else the leader (or, when you lead, the chaser). */
export function totalsLine(s: Slate): string {
  const me = s.lines.find(l => l.user_id === s.me_id);
  if (!me) return "";
  const other = isSoloVsModel(s)
    ? s.lines.find(l => l.user_id === "model")
    : s.lines.find(l => l.user_id !== s.me_id && (me.rank === 1 ? true : l.rank === 1));
  if (!other) return `You ${money(me.total)}`;
  const label = other.user_id === "model" ? "Model" : other.user_name;
  return `You ${money(me.total)} · ${label} ${money(other.total)}`;
}

/** What the money means right now — never "projected" on its own. */
export function moneyNote(s: Slate): string {
  if (s.status === "final") return "Final prize money.";
  if (s.status === "settling") return "Final positions — official prize money posts shortly.";
  return "Estimated payouts if the tournament ended now.";
}

/** "−6 · Thru 12" / "E · Round 3 done" / "Not started" for one golfer. */
export function golferProgress(g: Golfer, status: Slate["status"]): string {
  const par = g.to_par == null ? "" : g.to_par === 0 ? "E" : g.to_par > 0 ? `+${g.to_par}` : `−${Math.abs(g.to_par)}`;
  const t = String(g.thru ?? "").trim().toUpperCase();
  let where = "";
  if (status === "final" || status === "settling") where = "";
  else if (t === "F" || t === "18") where = g.round ? `Round ${g.round} done` : "Round done";
  else if (t && t !== "0" && t !== "-") where = `Thru ${t}`;
  else where = "Not started";
  return [par, where].filter(Boolean).join(" · ");
}
