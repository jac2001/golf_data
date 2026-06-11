/**
 * api.ts — API client
 * ====================
 * All functions that talk to the FastAPI backend live here.
 * Pages import these functions instead of writing raw fetch() calls.
 *
 * Think of this like a Python module:
 *   from api import get_bets, get_odds_comparison
 */

// The FastAPI server address. In dev it runs on port 8000.
// When deployed, this would be your production API URL.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── TypeScript types ─────────────────────────────────────────────────────────
// These describe the shape of data coming back from the API.
// Like Python dataclasses — they help catch mistakes before you run the code.

export type Bet = {
  recommendation_id: string | null;
  tournament_id: string | null;
  player_name: string;
  market: string;
  book: string;
  odds_american: number;
  model_prob: number;   // 0–1
  book_prob: number;    // 0–1
  edge_pts: number;     // percentage points of edge
  ev_per_1: number;     // expected value per $1 wagered
  confidence: number;   // 0–1
  kelly_fraction: number | null;
  selection_label: string;
  group_members: string | null;
  // Live tournament context (null if pre-tournament)
  live_position: string | null;
  live_total:    string | null;
  live_thru:     string | null;
  live_r1:       string | null;
  live_r2:       string | null;
  live_r3:       string | null;
  // Intel warning from fetch_tournament_intel.py (empty string = no flag)
  intel_warning: string | null;
};

export type OddsPlayer = {
  player: string;
  model_prob: number | null;   // percentage (already *100)
  book_odds: Record<string, string | null>;  // { DRAFTKINGS: "+350", ... }
  edge_vs_dk: number | null;
  ref_book: string;
};

export type OddsComparison = {
  tournament_id: string;
  market: string;
  books: string[];
  ref_book: string;
  players: OddsPlayer[];
};

export type Tournament = {
  tournament_id: string;
  name?: string;
  current_round?: number;
  round_status?: string;
  leader_score?: number;
  leader_name?: string;
};

export type BetsResponse = {
  tournament_id: string;
  bets: Bet[];
  count: number;
};

export type PlayerIntel = {
  player_name: string;          // "First Last" — normalized by API
  injury_flag: boolean;
  injury_detail: string | null;
  recent_form_summary: string;
  key_quote: string | null;
  sentiment: "positive" | "neutral" | "negative";
  sources: string[];
};

export type CourseConditions = {
  course_name: string;
  rough_length: string | null;
  green_speed: string | null;
  setup_notes: string;
  scoring_outlook: "low" | "moderate" | "high";
  sources: string[];
};

export type IntelResponse = {
  tid: string;
  tournament_name: string;
  generated_at: string;
  age_hours: number | null;
  course_conditions: CourseConditions;
  players: PlayerIntel[];
};

// ── API functions ─────────────────────────────────────────────────────────────
// Each function calls one FastAPI endpoint and returns typed data.
// `async` means "this might take a moment — wait for it."

export async function getTournament(): Promise<Tournament> {
  const res = await fetch(`${API_BASE}/api/tournament`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load tournament");
  return res.json();
}

export async function getBets(market = "all", minEdge = 0): Promise<BetsResponse> {
  const params = new URLSearchParams({ market, min_edge: String(minEdge) });
  const res = await fetch(`${API_BASE}/api/bets?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load bets");
  return res.json();
}

export async function getOddsComparison(market = "top10"): Promise<OddsComparison> {
  const res = await fetch(`${API_BASE}/api/odds/comparison?market=${market}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to load odds comparison");
  return res.json();
}

export async function refreshBets(): Promise<BetsResponse> {
  const res = await fetch(`${API_BASE}/api/refresh-bets`, { method: "POST" });
  if (!res.ok) throw new Error("Refresh failed");
  return res.json();
}

// ── This Week types ───────────────────────────────────────────────────────────

export type PlayerPrediction = {
  player_name: string;
  world_rank: number | null;
  win_prob: number | null;
  top5_prob: number | null;
  top10_prob: number | null;
  top20_prob: number | null;
  cut_prob: number | null;
  season_sg_total: number | null;
  model_vs_vegas_edge: number | null;
  form_trend: number | null;
  odds_to_win: number | null;
  dk_odds_direction: string | null;
  // Physics-based simulation probs (DataGolf-style Monte Carlo)
  win_prob_sim: number | null;
  top5_prob_sim: number | null;
  top10_prob_sim: number | null;
  top20_prob_sim: number | null;
  make_cut_prob_sim: number | null;
  uses_remaining: number;       // 0–3 from usage tracker (default 3)
  badge: string;                // "USE" | "SAVE" | "MAXED" | ""
  recommendation: string;
  this_week_ev: number | null;  // season EV in dollars
  explanation: string;          // bullet-style analysis e.g. "Elite ball striking · Course specialist"
};

export type PredictionsResponse = {
  tournament_id: string;
  players: PlayerPrediction[];
  count: number;
  weekly_narrative: string;
  analysis_generated_at: string;
};

export type LineupPick = {
  player_name: string;
  recommendation: string;
  tier: string;
  uses_left: number | null;
  in_field: boolean;
  narrative: string;
  win_prob: number | null;
  top10_prob: number | null;
  world_rank: number | null;
  odds_to_win: string;
  form_trend: number | null;
  season_sg: number | null;
  drift: string;
  this_week_ev: number | null;
};

export type LineupResponse = {
  tournament_id: string;
  tournament: string;
  generated_at: string;
  weekly_narrative: string;
  picks: LineupPick[];
};

export type TeeTimePlayer = {
  name: string;
  start_tee: number | null;
  model_rank: number | null;
  world_rank: number | null;
  win_prob: number | null;
  top10_prob: number | null;
  form_trend: number | null;
  edge: number | null;
  drift: string;

};

export type TeeTimeGroup = {
  tee_time: string;
  players: TeeTimePlayer[];
};

export type TeeTimesResponse = {
  tournament_id: string;
  round: number | null;
  groups: TeeTimeGroup[];
};

export type CourseHole = {
  hole_num: number;
  hole_par: number;
  hole_yards: number | null;
  scoring_avg: number | null;
  scoring_diff: number | null;
  difficulty_rank: number | null;
  birdies: number | null;
  bogeys: number | null;
};

export type CourseResponse = {
  tournament_id: string;
  course_name: string;
  par: number | null;
  yardage: number | null;
  holes: CourseHole[];
};

// ── This Week fetch functions ──────────────────────────────────────────────────

export async function getPredictions(limit = 80): Promise<PredictionsResponse> {
  const res = await fetch(`${API_BASE}/api/predictions?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load predictions");
  return res.json();
}

export async function getLineup(): Promise<LineupResponse> {
  const res = await fetch(`${API_BASE}/api/lineup`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load lineup");
  return res.json();
}

export async function getTeeTimes(): Promise<TeeTimesResponse> {
  const res = await fetch(`${API_BASE}/api/tee-times`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load tee times");
  return res.json();
}

export type ModelCompPlayer = {
  player: string;
  our_rank: number;
  dg_rank: number | null;
  delta: number | null;
  our_win: number | null;
  dg_win: number | null;
  our_top10: number | null;
  dg_top10: number | null;
};

export async function getCourse(): Promise<CourseResponse> {
  const res = await fetch(`${API_BASE}/api/course`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load course data");
  return res.json();
}

// ── Matchup types ─────────────────────────────────────────────────────────────

export type MatchupBookOdds = {
  p1_odds: string | null;
  p2_odds: string | null;
  p1_ev: number | null;
  p2_ev: number | null;
};

export type Matchup = {
  p1: string;
  p2: string;
  dg_p1: number;   // percent (already *100)
  dg_p2: number;
  ties: string;
  books: Record<string, MatchupBookOdds>;
};

export type MatchupsResponse = {
  tournament_id: string;
  market: string;
  books: string[];
  matchups: Matchup[];
  updated: string | null;
};

export type ThreeBallPairing = {
  round: number | null;
  group: number | null;
  teetime: string;
  p1: string;
  p1_odds: string;
  p2: string;
  p2_odds: string;
  p3: string | null;
  p3_odds: string | null;
};

export type ThreeBallResponse = {
  tournament_id: string;
  pairings: ThreeBallPairing[];
  updated: string | null;
};

export type OddsExplorerBook = {
  odds: string | null;
  ev: number | null;
};

export type OddsExplorerPlayer = {
  player: string;
  dg_prob: number | null;
  books: Record<string, OddsExplorerBook>;
  has_pos_ev: boolean;
};

export type OddsExplorerResponse = {
  tournament_id: string;
  market: string;
  books: string[];
  players: OddsExplorerPlayer[];
  updated: string | null;
};

// ── New API functions ──────────────────────────────────────────────────────────

export async function getMatchups(
  market: "tournament" | "round" = "tournament",
  search = "",
  posEvOnly = false,
): Promise<MatchupsResponse> {
  const params = new URLSearchParams({
    market, search,
    pos_ev_only: String(posEvOnly),
  });
  const res = await fetch(`${API_BASE}/api/matchups?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load matchups");
  return res.json();
}

export async function get3Ball(): Promise<ThreeBallResponse> {
  const res = await fetch(`${API_BASE}/api/3ball`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load 3-ball pairings");
  return res.json();
}

export async function getOddsExplorer(market = "top_10"): Promise<OddsExplorerResponse> {
  const res = await fetch(`${API_BASE}/api/odds/explorer?market=${market}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load odds explorer");
  return res.json();
}

export async function refreshDgOdds(): Promise<{ ok: boolean; updated: string | null }> {
  const res = await fetch(`${API_BASE}/api/refresh-dg-odds`, { method: "POST" });
  if (!res.ok) throw new Error("Refresh failed");
  return res.json();
}

// ── Live types ────────────────────────────────────────────────────────────────

export type LeaderboardPlayer = {
  position: string | null;
  position_change: number | null;
  player_name: string;
  country: string | null;
  total: string | null;
  total_numeric: number | null;
  thru: string | null;
  current_round: number | null;
  R1: number | null;
  R2: number | null;
  R3: number | null;
  R4: number | null;
  total_strokes: number | null;
  made_cut: boolean | null;
  status: string | null;
  movement: string | null;
};

export type InPlayPlayer = {
  player_name: string;
  position: string | null;
  country: string | null;
  total: string | null;
  total_numeric: number | null;
  thru: string | null;
  current_round: number | null;
  R1: number | null;
  R2: number | null;
  R3: number | null;
  R4: number | null;
  today: number | null;
  made_cut: boolean;
  movement: string | null;
  win_prob: number | null;
  top5_prob: number | null;
  top10_prob: number | null;
  top20_prob: number | null;
};

export type InPlayResponse = {
  tournament_id: string;
  event_name: string;
  current_round: number | null;
  last_update: string;
  players: InPlayPlayer[];
  count: number;
};

export type CutProjection = {
  projected_cut_score: number | null;
  bubble_count: number | null;
  safely_in: number | null;
  safely_out: number | null;
};

export type LeaderboardResponse = {
  tournament_id: string;
  players: LeaderboardPlayer[];
  count: number;
  current_round: number | null;
  round_status: string | null;
  cut_projection: CutProjection | null;
  fetched_at: string | null;
};

export type VsPredPlayer = {
  player: string;
  position: string | null;
  total: string | null;
  total_numeric: number | null;
  thru: string | null;
  made_cut: boolean | null;
  status: string | null;
  model_rank: number | null;
  win_prob: number | null;   // already *100
  top10_prob: number | null; // already *100
  rank_diff: number | null;  // positive = outperforming model, negative = underperforming
};

export type MyPickPlayer = {
  player: string;
  position: string | null;
  total: string | null;
  total_numeric: number | null;
  thru: string | null;
  R1: number | null;
  R2: number | null;
  R3: number | null;
  R4: number | null;
  made_cut: boolean | null;
  status: string | null;
  position_change: number | null;
  movement: string | null;
};

export type MyLineupResponse = {
  tournament_id: string;
  tournament: string;
  picks: MyPickPlayer[];
};

export type SgStatPlayer = {
  player: string;
  position: number | null;
  total: number | null;
  thru: string | null;
  round: string | null;
  sg_total: number | null;
  sg_ott: number | null;
  sg_app: number | null;
  sg_arg: number | null;
  sg_putt: number | null;
  sg_t2g: number | null;
  driving_dist: number | null;
  driving_acc: number | null;
};

export type SgStatsResponse = {
  tournament_id: string;
  players: SgStatPlayer[];
  round_param: string;
  updated: string | null;
};

// ── Live fetch functions ───────────────────────────────────────────────────────

export async function getInPlay(): Promise<InPlayResponse> {
  const res = await fetch(`${API_BASE}/api/live/inplay`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load in-play data");
  return res.json();
}

export async function refreshHoleScores(): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/api/live/refresh-hole-scores`, { method: "POST" });
  if (!res.ok) throw new Error("Hole scores refresh failed");
  return res.json();
}

export async function getLeaderboard(): Promise<LeaderboardResponse> {
  const res = await fetch(`${API_BASE}/api/leaderboard`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load leaderboard");
  return res.json();
}

export async function getVsPredictions(): Promise<{ tournament_id: string; players: VsPredPlayer[] }> {
  const res = await fetch(`${API_BASE}/api/live/vs-predictions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load vs-predictions");
  return res.json();
}

export async function getMyLineupLive(): Promise<MyLineupResponse> {
  const res = await fetch(`${API_BASE}/api/live/my-lineup`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load my lineup");
  return res.json();
}

export async function getSgStats(roundParam = "event_avg"): Promise<SgStatsResponse> {
  const res = await fetch(`${API_BASE}/api/live/sg-stats?round_param=${roundParam}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load SG stats");
  return res.json();
}

export type HoleData = {
  hole: number;
  strokes: number | null;
  par: number | null;
  rel: number | null;  // relative to par: -2=eagle, -1=birdie, 0=par, 1=bogey, 2+=double
};

export type HoleScoresResponse = {
  tournament_id: string;
  by_player: Record<string, Record<string, HoleData[]>>;  // player → round# → 18 holes
};

export async function getHoleScores(): Promise<HoleScoresResponse> {
  const res = await fetch(`${API_BASE}/api/live/hole-scores`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load hole scores");
  return res.json();
}

// ── Live hole stats (DG per-hole scoring) ─────────────────────────────────────

export type HoleWaveStats = {
  players_thru: number;
  avg_score:    number | null;
  vs_par:       number | null;
  birdies:      number;
  pars:         number;
  bogeys:       number;
  doubles:      number;
  eagles:       number;
  birdie_pct:   number | null;
  bogey_pct:    number | null;
  double_pct:   number | null;
};

export type DgHole = {
  hole:         number;
  par:          number;
  yardage:      number | null;
  players_thru: number;
  avg_score:    number | null;
  vs_par:       number | null;
  birdies:      number;
  pars:         number;
  bogeys:       number;
  doubles:      number;
  eagles:       number;
  birdie_pct:   number | null;
  bogey_pct:    number | null;
  double_pct:   number | null;
  morning:      HoleWaveStats;
  afternoon:    HoleWaveStats;
};

export type HoleStatsResponse = {
  event_name: string;
  round:      number | null;
  holes:      DgHole[];
  updated:    string;
};

export async function getHoleStats(roundParam = "event_avg"): Promise<HoleStatsResponse> {
  const res = await fetch(`${API_BASE}/api/live/hole-stats?round_param=${roundParam}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load hole stats");
  return res.json();
}

// ── Player profile types ──────────────────────────────────────────────────────

export type PlayerOurModel = {
  win_prob: number | null;
  top10_prob: number | null;
  cut_prob: number | null;
  world_rank: number | null;
  season_sg_total: number | null;
  form_trend: number | null;
  model_vs_vegas_edge: number | null;
  odds_to_win: number | null;
  dk_odds_direction: string | null;
  uses_remaining: number;
  badge: string;
  recommendation: string;
  this_week_ev: number | null;
  explanation: string;
  win_rank: number | null;
  top10_rank: number | null;
};

export type PlayerDgPrediction = {
  win: number | null;
  top_5: number | null;
  top_10: number | null;
  top_20: number | null;
  make_cut: number | null;
  bhf_win: number | null;
  baseline_win: number | null;
  course_fit_delta: number | null;
  course_fit_delta_pct: number | null;
};

export type PlayerDecompositions = {
  course_history_adjustment: number | null;
  total_course_history_adjustment: number | null;
  driving_accuracy_adjustment: number | null;
  driving_distance_adjustment: number | null;
  timing_adjustment: number | null;
  age_adjustment: number | null;
  strokes_gained_category_adjustment: number | null;
  total_fit_adjustment: number | null;
  true_sg_adjustments: number | null;
  course_fit_delta: number | null;
};

export type PlayerSkillRatings = {
  total: number | null;
  ott: number | null;
  app: number | null;
  arg: number | null;
  putt: number | null;
  dist: number | null;
  acc: number | null;
};

export type ApproachBand = {
  sg: number | null;
  prox: number | null;
};

export type PlayerApproachSkill = {
  "50_100": ApproachBand;
  "100_150": ApproachBand;
  "150_200": ApproachBand;
  "over_200": ApproachBand;
  "rgh_under_150": ApproachBand;
  "rgh_over_150": ApproachBand;
  overall_prox: number | null;
};

export type PlayerBettingProfile = {
  sg_total: number | null;
  sg_total_rank: number | null;
  sg_ott: number | null;
  sg_ott_rank: number | null;
  sg_app: number | null;
  sg_app_rank: number | null;
  sg_arg: number | null;
  sg_arg_rank: number | null;
  sg_putt: number | null;
  sg_putt_rank: number | null;
  driving_distance: number | null;
  driving_accuracy: number | null;
  gir_pct: string | null;
  scrambling_pct: string | null;
  fedex_rank: number | null;
  events_played: number | null;
  wins: number | null;
  top_10s: number | null;
  cuts_made: number | null;
  summary: string | null;
  bullets: string[];
  course_history_raw: string | null;
  recent_results_raw: string | null;
};

export type PlayerProfile = {
  player_name: string;
  tournament_id: string;
  our_model: PlayerOurModel;
  dg_prediction: PlayerDgPrediction | null;
  decompositions: PlayerDecompositions | null;
  skill_ratings: PlayerSkillRatings | null;
  approach_skill: PlayerApproachSkill | null;
  betting_profile: PlayerBettingProfile | null;
};

export async function getPlayerList(): Promise<{ players: string[] }> {
  const res = await fetch(`${API_BASE}/api/players/list`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load player list");
  return res.json();
}

export type FieldStatsPlayer = {
  player_name: string;
  world_rank: number | null;
  season_sg_total: number | null;
  season_sg_ott: number | null;
  season_sg_app: number | null;
  season_sg_arg: number | null;
  season_sg_putt: number | null;
  season_sg_ott_field_rank: number | null;
  season_sg_app_field_rank: number | null;
  season_sg_arg_field_rank: number | null;
  season_sg_putt_field_rank: number | null;
  course_sg_total_avg: number | null;
  course_sg_ott_avg: number | null;
  course_sg_app_avg: number | null;
  course_sg_putt_avg: number | null;
  course_sg_starts: number | null;
  course_made_cut_rate: number | null;
  course_win_rate: number | null;
  dg_course_fit_delta: number | null;
  dg_course_fit_delta_pct: number | null;
  form_trend: number | null;
  consecutive_cuts: number | null;
  consecutive_top10s: number | null;
  recent_top10s: number | null;
  recent_wins: number | null;
  missed_cut_last_start: number | null;
  dg_win: number | null;
  dg_top10: number | null;
  win_prob: number | null;
  top10_prob: number | null;
};

export async function getFieldStats(): Promise<{ players: FieldStatsPlayer[] }> {
  const res = await fetch(`${API_BASE}/api/players/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load field stats");
  return res.json();
}

export async function getPlayerProfile(name: string): Promise<PlayerProfile> {
  const params = new URLSearchParams({ player: name });
  const res = await fetch(`${API_BASE}/api/players/profile?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load player profile");
  return res.json();
}

// ── My Picks types ────────────────────────────────────────────────────────────

export type WeeklyLineup = {
  week: number | null;
  tournament: string;
  date: string;
  lineup: string[];
  finish: number | null;
  earnings: number;
};

export type TournamentUsed = {
  tournament: string;
  week: number | null;
  date: string;
  result: string | null;
  earnings: number;
};

export type RosterPlayer = {
  player_name: string;
  times_used: number;
  remaining_uses: number;
  total_earnings: number;
  tournaments: TournamentUsed[];
};

export type MyPicksSummary = {
  total_earnings: number;
  total_weeks: number;
  total_players: number;
  best_week: WeeklyLineup | null;
  avg_earnings: number;
};

export type MyPicksResponse = {
  season: number;
  last_updated: string;
  max_uses: number;
  weeks: WeeklyLineup[];
  roster: RosterPlayer[];
  summary: MyPicksSummary;
};

export async function getMyPicks(): Promise<MyPicksResponse> {
  const res = await fetch(`${API_BASE}/api/mypicks`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load my picks");
  return res.json();
}

// ── Weather types ─────────────────────────────────────────────────────────────

export type WeatherDay = {
  day: string;           // "Thu" | "Fri" | "Sat" | "Sun"
  condition: string;     // "DAY_SUNNY" | "DAY_PARTLY_CLOUDY" | etc.
  wind_mph: string;
  wind_dir: string;
  precip_pct: string;
  humidity: string;
  high_f: string;
  low_f: string;
};

export type WeatherResponse = {
  tournament_id: string;
  saved_at: string;
  days: WeatherDay[];
};

export type Withdrawal = {
  player_name: string;
  status: "WITHDRAWN" | "POSSIBLE_WD" | string;
  source: string;
  detected_at: string;
};

export type WithdrawalsResponse = {
  tournament_id: string;
  withdrawals: Withdrawal[];
  count: number;
  confirmed_count: number;
};

export async function getWeather(): Promise<WeatherResponse> {
  const res = await fetch(`${API_BASE}/api/weather`, { cache: "no-store" });
  if (!res.ok) throw new Error("No weather data");
  return res.json();
}

export async function getWithdrawals(): Promise<WithdrawalsResponse> {
  const res = await fetch(`${API_BASE}/api/withdrawals`, { cache: "no-store" });
  if (!res.ok) throw new Error("No withdrawals data");
  return res.json();
}

// ── Expert picks types ────────────────────────────────────────────────────────

export type ExpertPick = {
  expert_name: string;
  expert_title: string;
  winner_pick: string | null;
  lineup: string[];
  bench: string[];
  comment: string | null;
};

export type ExpertConsensusPlayer = {
  player_name: string;
  lineup_mentions: number;
  winner_picks: number;
  total_mentions: number;
  lineup_pct: number;
  winner_pct: number;
};

export type ExpertPicksResponse = {
  tournament: string;
  expert_count: number;
  experts: ExpertPick[];
  consensus: ExpertConsensusPlayer[];
};

export async function getExpertPicks(): Promise<ExpertPicksResponse> {
  const res = await fetch(`${API_BASE}/api/expert-picks`, { cache: "no-store" });
  if (!res.ok) throw new Error("No expert picks data");
  return res.json();
}

// ── Settings ──────────────────────────────────────────────────────────────────

export type AlertEvents = {
  my_pick_leads:   boolean;
  my_pick_top5:    boolean;
  my_pick_top10:   boolean;
  my_pick_bigmove: boolean;
  leader_change:   boolean;
};

export type AppSettings = {
  alerts: {
    mac_notifications: boolean;
    web_toasts:        boolean;
    events:            AlertEvents;
    bigmove_threshold: number;
    min_severity:      "low" | "normal" | "high";
  };
  live: {
    default_tab:        string;
    default_sg_round:   string;
    poll_interval_secs: number;
  };
};

export async function getSettings(): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/api/settings`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load settings");
  return res.json();
}

export async function patchSettings(patch: Record<string, unknown>): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/api/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Failed to save settings");
  return res.json();
}

// ── Live alerts ───────────────────────────────────────────────────────────────

export type LiveAlert = {
  id:       string;
  type:     string;
  title:    string;
  body:     string;
  ts:       string;
  severity: "low" | "normal" | "high";
  read:     boolean;
};

export type AlertsResponse = {
  alerts:        LiveAlert[];
  total_unread:  number;
};

export async function getAlerts(markRead = true): Promise<AlertsResponse> {
  const res = await fetch(
    `${API_BASE}/api/alerts?mark_read=${markRead}`,
    { cache: "no-store" },
  );
  if (!res.ok) return { alerts: [], total_unread: 0 };
  return res.json();
}

// ── Chat types ────────────────────────────────────────────────────────────────

export type ChatMessage = { role: "user" | "assistant"; content: string };

export function streamChat(
  query: string,
  messages: ChatMessage[],
  lastPlayers: string[],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, messages, last_players: lastPlayers }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "API error" }));
        onError(err.detail ?? "Chat API error");
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") { onDone(); return; }
          try { onChunk(JSON.parse(payload).text ?? ""); } catch {}
        }
      }
      onDone();
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      onError(String(e));
    }
  })();

  return () => controller.abort();
}

export async function rateChat(
  query: string,
  response: string,
  rating: "up" | "down",
  tid: string = "",
): Promise<void> {
  await fetch(`${API_BASE}/api/chat/rate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, response, rating, tid }),
  });
}

// ── Formatting helpers ────────────────────────────────────────────────────────
// Small utility functions used by multiple components.

export function fmtOdds(n: number | null | undefined): string {
  if (n == null) return "—";
  return n >= 0 ? `+${n}` : String(n);
}

export function fmtPct(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

// Market display names — same mapping as the Streamlit dashboard
export const MARKET_LABELS: Record<string, string> = {
  outright:     "Win",
  top5:         "Top 5",
  top10:        "Top 10",
  top20:        "Top 20",
  make_cut:     "Make Cut",
  h2h:          "Matchup",
  group_winner: "Group Winner",
};

// Accent colors per market (matches the Streamlit color scheme)
export const MARKET_COLORS: Record<string, string> = {
  outright:     "#f1c40f",
  top5:         "#3498db",
  top10:        "#00c44f",
  top20:        "#9b59b6",
  make_cut:     "#1abc9c",
  h2h:          "#e67e22",
  group_winner: "#e74c3c",
};

// ── History types ────────────────────────────────────────────────────────────

export type HistoryTop10Entry = { player: string; position: string; to_par: string | number };

export type HistoryTournament = {
  tournament_id: string;
  name: string;
  start_date: string;
  purse: string | number;
  winner: string;
  winner_score: string | number;
  winner_earnings: string;
  field_size: number;
  recap: string | null;
  top10: HistoryTop10Entry[];
};

export type HistoryModelRow = {
  tournament_id: string;
  name: string;
  date: string;
  field_size: number;
  win_pred_avg: number;
  win_actual_pct: number | null;
  top5_pred_avg: number;
  top5_actual_pct: number | null;
  top10_pred_avg: number;
  top10_actual_pct: number | null;
  rank_corr: number | null;
};

export type HistoryBetMarket = { market: string; bets: number; wins: number; pnl: number };

export type HistoryBetRow = {
  tournament_id: string;
  name: string;
  bets: number;
  wins: number;
  pnl: number;
  roi: number;
  markets: HistoryBetMarket[];
};

export type HistoryBetsResponse = {
  tournaments: HistoryBetRow[];
  overall: { bets: number; wins: number; pnl: number; roi: number };
};

export async function getHistoryTournaments(): Promise<HistoryTournament[]> {
  const r = await fetch(`${API_BASE}/api/history/tournaments`);
  if (!r.ok) throw new Error("Failed to load tournament history");
  const d = await r.json();
  return d.tournaments;
}

export async function getHistoryModel(): Promise<HistoryModelRow[]> {
  const r = await fetch(`${API_BASE}/api/history/model`);
  if (!r.ok) throw new Error("Failed to load model history");
  const d = await r.json();
  return d.tournaments;
}

export async function getHistoryBets(): Promise<HistoryBetsResponse> {
  const r = await fetch(`${API_BASE}/api/history/bets`);
  if (!r.ok) throw new Error("Failed to load bet history");
  return r.json();
}


export async function getBetReason(player: string, market: string, opponent?: string): Promise<{ reason: string; cached: boolean }> {
    const params = new URLSearchParams({ player, market });
    if (opponent) params.set("opponent", opponent);
    const res = await fetch(`${API_BASE}/api/bets/reason?${params}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}
  


export interface BetLine {
    book: string;
    odds_american: string;
    implied_prob: number;
    edge_pp: number | null;
  }

export interface BetLinesResponse {
  player: string;
  market: string;
  model_prob: number | null;
  best_odds: string | null;
  best_book: string | null;
  lines: BetLine[];
  last_updated: string | null;
}




// Book abbreviations for display
export const BOOK_ABBR: Record<string, string> = {
  DRAFTKINGS: "DK",
  FANDUEL:    "FD",
  BET365:     "B365",
  BETMGM:     "MGM",
  CAESARS:    "CZR",
  PINNACLE:   "PIN",
  UNIBET:     "UNI",
  BOVADA:     "BOV",
};


export async function getBetLines(player: string, market: string): Promise<BetLinesResponse> {
    const params = new URLSearchParams({ player, market });
    const res = await fetch(`${API_BASE}/api/bets/lines?${params}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }
// ── Live Pulse ────────────────────────────────────────────────────────────

export interface LivePulsePlayer {
  name:  string;
  blurb: string;
}

export interface LivePulseSections {
  headline:    string;
  leaders:     string;
  on_fire:     LivePulsePlayer[];
  to_watch:    LivePulsePlayer[];
  your_picks:  string;
  round_story: string;
}

export interface LivePulse {
  tournament_id:   string;
  tournament_name: string;
  current_round:   number;
  sections:        LivePulseSections;
  generated_ts:    number;
  cached:          boolean;
}

export async function getLivePulse(force = false): Promise<LivePulse> {
  const params = new URLSearchParams({ force: String(force) });
  const res = await fetch(`${API_BASE}/api/live/pulse?${params}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Failed to generate live pulse");
  }
  return res.json();
}

// ── Player Synopsis ───────────────────────────────────────────────────────

export interface PlayerSynopsisSections {
  form:           string;
  course_fit:     string;
  betting_angle:  string;
  fantasy:        string;
}

export interface PlayerSynopsis {
  player_name:     string;
  tournament_name: string;
  course_name:     string;
  sections:        PlayerSynopsisSections;
  generated_ts:    number;
  cached:          boolean;
}

export async function getPlayerSynopsis(
  player: string,
  force = false,
): Promise<PlayerSynopsis> {
  const params = new URLSearchParams({ player, force: String(force) });
  const res = await fetch(`${API_BASE}/api/players/synopsis?${params}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Failed to generate synopsis");
  }
  return res.json();
}

// ── Course Fit ─────────────────────────────────────────────────────────────

export interface CourseFitProfile {
  ott:  number;   // 0–1 relative importance of off-the-tee
  app:  number;   // approach
  arg:  number;   // around the green
  putt: number;   // putting
}

export interface CourseFitPlayer {
  player_name:         string;
  overall_rank:        number;
  win_prob:            number | null;
  top10_prob:          number | null;
  win_prob_pre_adj:    number | null;
  win_prob_shift:      number | null;   // positive = course gives this player a boost
  course_fit_delta:    number | null;
  dg_course_fit_delta: number | null;
  has_history:         boolean;
  course_starts:       number | null;
  cut_rate:            number | null;
  top10_rate:          number | null;
  avg_to_par:          number | null;
  experience_tier:     string;
  sg_ott_vs_avg:       number | null;
  sg_app_vs_avg:       number | null;
  sg_putt_vs_avg:      number | null;
  sg_t2g_vs_avg:       number | null;
  dg_win:              number | null;
  dg_top10:            number | null;
  world_rank:          number | null;
  pga_starts:          number;
  pga_top10s:          number;
  pga_wins:            number;
  uses_remaining:      number | null;   // null = not in your fantasy roster
  // DG decomposition fields
  dg_timing_adj:       number | null;   // current form adjustment
  dg_fit_adj:          number | null;   // total course fit adjustment
  dg_hist_adj:         number | null;   // course history adjustment
  dg_final_pred:       number | null;   // DG final SG prediction (vs field mean)
  dg_baseline_pred:    number | null;   // DG baseline (skill only, no course adjustments)
}

export interface CourseFitResponse {
  tournament_id:        string;
  course_name:          string;
  course_history_type:  "venue" | "tournament";
  course_profile:       CourseFitProfile;
  players:              CourseFitPlayer[];
}

export async function getCourseFit(): Promise<CourseFitResponse> {
  const res = await fetch(`${API_BASE}/api/course-fit`);
  if (!res.ok) throw new Error(`course-fit ${res.status}`);
  return res.json();
}

export type BestBet = {
  available: boolean;
  tournament_id: string;
  tournament_name: string;
  player_name: string;
  market: string;
  market_label: string;
  selection_label: string;
  book: string;
  odds_american: number;
  odds_str: string;
  edge_pts: number;
  ev_pct: number;
  model_prob: number;
  book_prob: number;
  reasoning: string;
  generated_at: string;
};

export async function getBestBet(): Promise<BestBet> {
  const res = await fetch(`${API_BASE}/api/bets/best`, { cache: "no-store" });
  if (!res.ok) throw new Error(`best-bet ${res.status}`);
  return res.json();
}

export async function getIntel(): Promise<IntelResponse> {
  const res = await fetch(`${API_BASE}/api/intel`, { cache: "no-store" });
  if (!res.ok) throw new Error(`intel ${res.status}`);
  return res.json();
}

export async function refreshIntel(topN = 20): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/api/refresh-intel?top_n=${topN}`, { method: "POST" });
  if (!res.ok) throw new Error(`refresh-intel ${res.status}`);
  return res.json();
}
// ── Bet Slip ──────────────────────────────────────────────────────────────────

  // A single bet you've chosen to track
export type SlipBet = {
    id: string;
    recommendation_id: string | null;
    tournament_id: string;
    player_name: string;
    market: string;
    selection_label: string;
    odds_american: number;
    stake_units: number;
    placed_at: string;
    // Filled in automatically after the tournament settles:
    outcome_status: "pending" | "won" | "lost";
    outcome_win: boolean | null;
    pnl_per_unit: number | null;
    pnl_usd: number | null;
    // Live tournament context (null if pre-tournament or not yet on course):
    live_position: string | null;
    live_total:    string | null;
    live_thru:     string | null;
    live_r1:       string | null;
    live_r2:       string | null;
    live_r3:       string | null;
    live_r4:       string | null;
    live_status:   "on_track" | "marginal" | "off_track" | "finished" | "tracking" | null;
};
  



// Season-wide summary stats
export type TournamentPnl = {
  tid: string;
  won: number;
  total: number;
  pnl_units: number;
  pnl_dollars: number;
};

export type SlipStats = {
  total_bets: number;
  graded: number;
  pending: number;
  won: number;
  lost: number;
  total_staked: number;
  total_pnl: number;          // in units
  total_pnl_dollars: number;  // in real $
  roi_pct: number | null;
  hit_rate: number | null;
  // Bankroll
  starting_bankroll: number | null;
  unit_size: number;
  current_bankroll: number | null;
  by_tournament: TournamentPnl[];
};

export type BetSlipResponse = {
  bets: SlipBet[];
  stats: SlipStats;
};

// What we send to the API when adding a bet
export type BetSlipEntry = {
  recommendation_id?: string | null;
  tournament_id: string;
  player_name: string;
  market: string;
  selection_label: string;
  odds_american: number;
  stake_units?: number;
};

export async function getBetSlip(): Promise<BetSlipResponse> {
  const res = await fetch(`${API_BASE}/api/bet-slip`, { cache: "no-store" });
  if (!res.ok) throw new Error(`bet-slip ${res.status}`);
  return res.json();
}


export async function addToBetSlip(entry: BetSlipEntry): Promise<{ ok: boolean; id?: string; message?: string }> {
  const res = await fetch(`${API_BASE}/api/bet-slip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error(`add-slip ${res.status}`);
  return res.json();
}

export async function removeFromBetSlip(id: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/api/bet-slip/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`remove-slip ${res.status}`);
  return res.json();
}

// ── Model vs DataGolf comparison (rich endpoint) ──────────────────────────────

export type MarketCorrelation = {
  market: string;
  spearman_rho: number;
};

export type ModelDisagreement = {
  player_name: string;
  our_win_pct: number;
  dg_win_pct: number;
  diff_pp: number;
  our_top10: number | null;
  dg_top10: number;
  direction: "higher" | "lower";
};

export type ModelComparison = {
  tournament_id: string;
  tournament_name: string;
  players_compared: number;
  overall_spearman_rho: number;
  markets: MarketCorrelation[];
  our_top10: { player: string; prob: number }[];
  dg_top10:  { player: string; prob: number }[];
  disagreements: ModelDisagreement[];
  players: ModelCompPlayer[];
};

export async function getModelComparison(): Promise<ModelComparison> {
  const res = await fetch(`${API_BASE}/api/model-comparison`, { cache: "no-store" });
  if (!res.ok) throw new Error(`model-comparison ${res.status}`);
  return res.json();
}