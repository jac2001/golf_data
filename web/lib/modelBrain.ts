// web/lib/modelBrain.ts  — YOUR function to write


/** Average % of purse paid per finishing bucket (PGA standard table). */
const BUCKET_PAYOUT_PCT = {
  win: 18.0,        // P1
  p2to5: 6.6,       // avg of positions 2–5
  p6to10: 3.0,      // avg of 6–10
  p11to20: 1.6,     // avg of 11–20
  madeCutRest: 0.45 // avg of 21st through last paid spot
};

export type Probs = {
  win_prob: number | null;    // e.g. 0.055  (cumulative!)
  top5_prob: number | null;
  top10_prob: number | null;
  top20_prob: number | null;
  cut_prob: number | null;
};


/** Expected prize money for one player: purse × Σ (bucketProb × bucketPct). */
export function expectedPayout(purse: number, probs: Probs): number {
    const ladder = ["win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob"] as const;
    const filled: Record<string, number> = {};
    let prev = 0;
    for (const rung of ladder) {
        filled[rung] = probs[rung] ?? prev;   // copy, never mutate the input
        prev = filled[rung];
    }

    const bucketProb = {
        win: filled.win_prob,
        p2to5: Math.max(filled.top5_prob - filled.win_prob, 0),
        p6to10: Math.max(filled.top10_prob - filled.top5_prob, 0),
        p11to20: Math.max(filled.top20_prob - filled.top10_prob, 0),
        madeCutRest: Math.max(filled.cut_prob - filled.top20_prob, 0)
    };
    return purse * (Object.keys(bucketProb).reduce((sum, key) => sum + bucketProb[key as keyof typeof bucketProb] * BUCKET_PAYOUT_PCT[key as keyof typeof BUCKET_PAYOUT_PCT] / 100, 0));
}

/** Round Game: the model's pick for a round — best win chance it hasn't used. */
export function modelRoundPick(
  field: { player_name: string; win_prob: number | null }[],
  alreadyUsed: string[],
): string | null {
  // TODO(Jack): filter out used names, return the highest win_prob player
    // (null if the field is empty). One line of filter + one reduce/sort.
    if (field.length === 0) {
        return null;
    }
    const availablePlayers: { player_name: string; win_prob: number | null }[] = field.filter(player => !alreadyUsed.includes(player.player_name));
    if (availablePlayers.length === 0) {
        return null;
    }
    const bestPlayer = availablePlayers.reduce((prev, current) => (prev.win_prob ?? 0) > (current.win_prob ?? 0) ? prev : current);
    return bestPlayer.player_name; 
}

/** The Fade Game pool: the event's top N by model win chance. */
export function fadePool(preds: (Probs & { player_name: string })[], n = 20) {
  // TODO(Jack): return the n players with the highest win_prob.
    // (Sort a COPY — [...preds] — remember the mutation lesson.)
    
const sortedPreds = [...preds].sort((a, b) => (b.win_prob ?? 0) - (a.win_prob ?? 0)); // descending order
    return sortedPreds.slice(0, n);
}












/** The model's fade trio: from the pool, the 3 players it expects to
 *  EARN THE LEAST — the favorites it believes in least. */
export function modelFadePicks(
  preds: (Probs & { player_name: string })[],
  purse: number,
): string[] {
  // TODO(Jack):
  // 1. pool = fadePool(preds)
  // 2. score each pool player with expectedPayout(purse, p)
  // 3. return the names of the 3 LOWEST — mind the sort direction!
    //    (In the weekly trio we sorted b-a for highest; here it flips.)
    const pool = fadePool(preds);
    const scoredPool = pool.map(p => ({ player_name: p.player_name, expectedPayout: expectedPayout(purse, p) }));
    const sortedScoredPool = scoredPool.sort((a, b) => a.expectedPayout - b.expectedPayout); // ascending order
    return sortedScoredPool.slice(0, 3).map(p => p.player_name);

}

/** Canonical key for name joins: lowercase sorted tokens, so
 *  "Last, First" / "First Last" / stray punctuation all collide.
 *  Raw-string joins fail SILENTLY (a mismatched player prices at $0). */
const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

/** College Game: the school whose BEST TWO alumni carry the highest
 *  combined expected payout — the model optimizes the game's actual
 *  score function (best-2), never roster depth. (Jack wrote this;
 *  review fixed one seam: the EV lookup is keyed by nameKey, not raw
 *  spelling.) */
export function modelCollegePick(
  preds: (Probs & { player_name: string })[],
  purse: number,
  schools: { school: string; players: string[] }[],
): string | null {
  if (schools.length === 0) {
    return null;
  }

  const nameToEV: Record<string, number> = {};
  for (const p of preds) {
    nameToEV[nameKey(p.player_name)] = expectedPayout(purse, p);
  }

  let bestSchool: string | null = null;
  let bestSum = -1;

  for (const school of schools) {
    const evs = school.players.map(player => nameToEV[nameKey(player)] ?? 0);
    evs.sort((a, b) => b - a); // descending order
    const topTwoSum = evs.slice(0, 2).reduce((sum, ev) => sum + ev, 0);
    if (topTwoSum > bestSum) {
      bestSum = topTwoSum;
      bestSchool = school.school;
    }
  }

  return bestSchool;
}