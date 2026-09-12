/**
 * methodology/page.tsx — How the System Works
 * ============================================
 * Static methodology page: the full modeling story from raw data to bet
 * recommendation, with the season's real evaluation numbers. Written to be
 * readable by a non-specialist; every number comes from a file in the repo
 * (model_test_metrics.json, benchmark_vs_dg_summary.json, season retrospective).
 */

import React from "react";

export const metadata = { title: "Methodology — Golf Edge" };

const wrap: React.CSSProperties = { maxWidth: 860, margin: "0 auto" };
const h2: React.CSSProperties = {
  color: "#e8f0f8", fontSize: "1.25em", marginTop: 42, marginBottom: 10,
  borderBottom: "1px solid #1e3a5f", paddingBottom: 8,
};
const p: React.CSSProperties = { color: "#c8d8e8", lineHeight: 1.65, margin: "12px 0", fontSize: "0.95em" };
const note: React.CSSProperties = {
  background: "#0a1525", border: "1px solid #1e3a5f", borderRadius: 8,
  padding: "12px 16px", margin: "16px 0", color: "#9ab8d0", fontSize: "0.88em", lineHeight: 1.6,
};
const cell: React.CSSProperties = {
  padding: "8px 12px", borderBottom: "1px solid #1a2a3a", textAlign: "right",
  fontSize: "0.86em", color: "#c8d8e8",
};
const cellL: React.CSSProperties = { ...cell, textAlign: "left" };
const hdr: React.CSSProperties = {
  ...cell, color: "#7a9ab8", fontWeight: 600, fontSize: "0.76em",
  textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid #1e3a5f",
};
const hdrL: React.CSSProperties = { ...hdr, textAlign: "left" };
const good: React.CSSProperties = { color: "#00c44f" };
const bad: React.CSSProperties = { color: "#e05555" };
const code: React.CSSProperties = {
  background: "#0d1e30", padding: "1px 6px", borderRadius: 4, fontSize: "0.9em",
  fontFamily: "ui-monospace, monospace", color: "#9ecbff",
};

export default function MethodologyPage() {
  return (
    <div style={wrap}>
      <h1 style={{ color: "#e8f0f8", fontSize: "1.6em", marginBottom: 4 }}>How the System Works</h1>
      <div style={{ color: "#7a9ab8", fontSize: "0.9em" }}>
        From raw data to probabilities to bets — with the real 2026 numbers, including the losing ones.
      </div>

      {/* ── 1. Overview ─────────────────────────────────────────────── */}
      <h2 style={h2}>1 · The pipeline at a glance</h2>
      <p style={p}>
        Every week the system ingests data from five sources (DataGolf, the PGA Tour&apos;s
        GraphQL API, DraftKings, Open-Meteo weather, and a fantasy league site) through ~30
        scraper scripts into a DuckDB database — 1.4M+ tournament-stat rows covering
        2016–2026. From that history it computes 62 features per player, runs them through
        calibrated Random Forest classifiers to produce win / top-5 / top-10 / top-20
        probabilities, cross-checks them with a 10,000-run Monte Carlo simulation, converts
        sportsbook odds into fair probabilities to find mispriced markets, and publishes
        everything here. The whole cycle — ingestion, prediction, settlement, grading,
        recalibration, deployment — runs automatically on a weekly schedule.
      </p>

      {/* ── 2. Models ───────────────────────────────────────────────── */}
      <h2 style={h2}>2 · The model: 48,000 rows of history, one question</h2>
      <p style={p}>
        The training table has 48,592 rows — one per player per tournament since 2016. Each
        row holds the player&apos;s stats <i>as they stood before that event</i> (strokes-gained
        form, world rank, course history) plus what actually happened: did they win, make the
        top 5, top 10, top 20. The model&apos;s only job: given the before-stats, predict the
        probability of the after-outcome. Winning is rare — 0.77% of rows — and that
        imbalance drives most design choices below.
      </p>
      <p style={p}>
        The classifiers are Random Forests: hundreds of decision trees, each trained on a
        random resample of the data and deliberately constrained —{" "}
        <span style={code}>max_depth=5</span>, <span style={code}>min_samples_leaf=25</span>.
        Those constraints stop any tree from memorizing individuals. Without them, a tree
        happily learns &quot;rank 240–260 and exactly 12 events played → 100% win rate&quot;
        because one lucky qualifier fits that description once in history. Requiring 25+
        players per leaf forces every probability to come from a real sample. A prediction
        like &quot;5.5% to win&quot; means precisely: of past player-weeks that resembled this
        profile, about 1 in 18 won.
      </p>

      {/* ── 3. Validation ───────────────────────────────────────────── */}
      <h2 style={h2}>3 · Validation: time only moves forward</h2>
      <p style={p}>
        Golf data is a time series, so the cardinal sin is letting the model peek at the
        future. Training uses only years before 2025; nothing after is touched during
        tuning. And because every tuning decision was made by looking at 2025 results, the
        2025 score is slightly flattered — like grading yourself on the practice exam you
        studied from. The 2026 season was never used for any decision, making it the honest
        number:
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%", margin: "8px 0" }}>
        <thead><tr>
          <th style={hdrL}>Market</th><th style={hdr}>AUC 2025 (tuning year)</th><th style={hdr}>AUC 2026 (untouched)</th>
        </tr></thead>
        <tbody>
          {[["Win", "0.837", "0.809"], ["Top 5", "0.750", "0.769"],
            ["Top 10", "0.733", "0.732"], ["Top 20", "0.736", "0.705"]].map(([m, a, b]) => (
            <tr key={m}><td style={cellL}>{m}</td><td style={cell}>{a}</td><td style={cell}><b>{b}</b></td></tr>
          ))}
        </tbody>
      </table>
      <p style={p}>
        AUC measures ranking skill: 0.81 for the win model means that given a random winner
        and non-winner, the model rates the winner higher 81% of the time (0.5 = coin flip).
      </p>

      {/* ── 4. Calibration ──────────────────────────────────────────── */}
      <h2 style={h2}>4 · Calibration: does 10% mean 10%?</h2>
      <p style={p}>
        A model can rank players well and still exaggerate — saying 30% when reality is 18%.
        For betting, that&apos;s fatal: expected value is computed from the probability
        itself, not the ranking. So each forest is wrapped in isotonic calibration
        (<span style={code}>CalibratedClassifierCV</span>), which learns a monotonic
        correction from predicted to observed frequencies on held-out folds. The proof is in
        a full season of graded predictions — 3,171 across 29 tournaments:
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%", margin: "8px 0" }}>
        <thead><tr>
          <th style={hdrL}>Market</th><th style={hdr}>Predicted avg</th><th style={hdr}>Actual rate</th><th style={hdr}>Ratio</th>
        </tr></thead>
        <tbody>
          {[["Win", "0.97%", "0.95%", "0.98"], ["Top 5", "4.89%", "5.39%", "1.10"],
            ["Top 10", "9.78%", "10.47%", "1.07"], ["Top 20", "18.32%", "21.04%", "1.15"]].map(([m, a, b, r]) => (
            <tr key={m}><td style={cellL}>{m}</td><td style={cell}>{a}</td><td style={cell}>{b}</td><td style={cell}><b>{r}</b></td></tr>
          ))}
        </tbody>
      </table>
      <p style={p}>
        A ratio of 1.00 is perfect; the season ran 0.98–1.15. The published probabilities
        also blend market odds (capped at 25% weight for top-ranked players) and expert
        consensus (12%) — so part of that calibration comes from the market itself, not
        pure model skill. That distinction matters in the benchmark below.
      </p>

      {/* ── 5. Monte Carlo ──────────────────────────────────────────── */}
      <h2 style={h2}>5 · Monte Carlo: playing the tournament 10,000 times</h2>
      <p style={p}>
        Point probabilities can&apos;t answer questions like &quot;how often do these three
        players all cash?&quot; — for that you need whole simulated tournaments. Each
        player gets a scoring distribution: a mean from model-projected strokes gained and a
        standard deviation estimated from their own round-to-round variance (minimum 20
        rounds). The simulator then plays each round as a random draw, applies a small 0.06
        autocorrelation between rounds (hot streaks are real but weak — a DataGolf research
        finding), cuts the field to 65 after round two, and tallies finishing positions
        across 10,000 tournaments. The counts become probabilities, and the full position
        matrix feeds lineup projections. Sampling uses the Gumbel-max trick, which turns
        sequential &quot;draw without replacement&quot; into one vectorized numpy operation —
        all 10,000 simulations compute simultaneously, and the simulated rates match the
        model&apos;s probabilities to within 0.003 MAE.
      </p>

      {/* ── 6. De-vig / EV ──────────────────────────────────────────── */}
      <h2 style={h2}>6 · Odds, vig, and what &quot;edge&quot; really means</h2>
      <p style={p}>
        Sportsbook odds are not probabilities — they include the book&apos;s margin
        (&quot;vig&quot;). Convert every player&apos;s top-10 odds into implied probabilities
        and they&apos;ll sum to ~12 when only 10 spots exist; the extra ~20% is the
        book&apos;s cut. De-vigging removes it: for pool markets each book&apos;s implied
        probabilities are proportionally rescaled to sum to the number of paid spots — always
        per book, never pooled across books (mixing books halves the apparent vig and
        manufactures phantom edges; that was a real bug, found and fixed). Binary markets
        like make-cut get a flat ~5% correction. An &quot;edge&quot; is then model probability
        minus fair probability, with a 1.5-point minimum before anything is recommended,
        staked by half-Kelly.
      </p>
      <p style={p}>
        The 2026 results are the best lesson in the whole project — 740 graded bets:
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%", margin: "8px 0" }}>
        <thead><tr>
          <th style={hdrL}>Market</th><th style={hdr}>Record</th><th style={hdr}>ROI</th>
        </tr></thead>
        <tbody>
          <tr><td style={cellL}>Make cut</td><td style={cell}>10/10</td><td style={{ ...cell, ...good }}>+52.9%</td></tr>
          <tr><td style={cellL}>Head-to-head, round 4</td><td style={cell}>25/58</td><td style={{ ...cell, ...good }}>+4.1%</td></tr>
          <tr><td style={cellL}>Head-to-head, rounds 1–3</td><td style={cell}>71/215</td><td style={{ ...cell, ...bad }}>−25% to −41%</td></tr>
          <tr><td style={cellL}>Group / placement / outright</td><td style={cell}>53/467</td><td style={{ ...cell, ...bad }}>−8% to −100%</td></tr>
          <tr><td style={cellL}><b>Total</b></td><td style={cell}><b>160/740</b></td><td style={{ ...cell, ...bad }}><b>−22.3%</b></td></tr>
        </tbody>
      </table>
      <p style={p}>
        A well-calibrated model lost 22% — because being right about probabilities is not
        the same as beating the market&apos;s probabilities by more than the vig. Where the
        system won tells the story: make-cut markets (books price them laziest) and
        round-4 matchups (where the live data pipeline updates faster than the lines).
        Those two niches are the 2027 focus; the broad markets go to paper-trading.
      </p>

      {/* ── 7. Benchmark ────────────────────────────────────────────── */}
      <h2 style={h2}>7 · Benchmark: head-to-head with the industry standard</h2>
      <p style={p}>
        DataGolf is the reference model in golf analytics. Their pre-tournament predictions
        were snapshotted <i>before</i> each event all season — no hindsight — giving a fair
        head-to-head on 1,492 matched predictions across 14 tournaments. Result: DataGolf
        wins on log loss by 4–5% in every market (win: 0.0443 vs 0.0463) and is clearly
        better at fine-grained ranking (Spearman 0.378 vs 0.310). This system is better
        calibrated in all four markets (win ratio 1.017 vs 1.040) — though, honestly noted,
        part of that calibration edge comes from blending market odds, which DataGolf&apos;s
        pure-model numbers don&apos;t do. For a solo project against a decade-old commercial
        model, within 5% on log loss is the result I&apos;m proudest of on this page.
      </p>

      {/* ── 8. Limitations ──────────────────────────────────────────── */}
      <h2 style={h2}>8 · Known limitations</h2>
      <div style={note}>
        <b>Things I would tell a reviewer before they found them:</b><br />
        · Validation is a single temporal split, not walk-forward cross-validation — the
        top offseason priority.<br />
        · The 0.20 cap on win probability is a heuristic patch for over-confident favorites,
        not a modeled fix.<br />
        · Small no-cut fields (playoffs, signature events) use a model trained mostly on
        144-player cut events, and the simulator hard-codes a 65-player cut.<br />
        · Bet logging silently stopped in April; the last ~15 weeks of recommendations were
        never graded. The recorded +12.2pt average closing-line value contradicts the −22%
        ROI and is under audit — until then it doesn&apos;t get cited.<br />
        · Player-name matching across five data sources is fuzzy by nature; normalizers
        handle most of it, manual mappings catch the rest.
      </div>

      <div style={{ ...note, marginTop: 28 }}>
        Built solo as a learning project — Python, scikit-learn, XGBoost, DuckDB, FastAPI,
        Next.js. Every number on this page is reproducible from the repository:
        model metrics from <span style={code}>outputs/model_test_metrics.json</span>,
        benchmark from <span style={code}>outputs/benchmark_vs_dg_summary.json</span>,
        season results from <span style={code}>outputs/season_2026_retrospective.md</span>.
      </div>
    </div>
  );
}
