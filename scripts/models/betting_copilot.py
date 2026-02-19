#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ODDS_DIR = DATA_DIR / "odds"
EXPERT_DIR = DATA_DIR / "expert_picks"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

TID_PATTERN = re.compile(r"(R\d{7})", re.IGNORECASE)


def _extract_tournament_id(value: Any) -> str:
    if value is None:
        return ""
    m = TID_PATTERN.search(str(value))
    return m.group(1).upper() if m else ""


def _to_num(value: Any) -> float:
    return pd.to_numeric(value, errors="coerce")


def _fmt_pct(prob: Any) -> str:
    v = _to_num(prob)
    return "—" if pd.isna(v) else f"{float(v) * 100:.2f}%"


def _fmt_pts(value: Any) -> str:
    v = _to_num(value)
    return "—" if pd.isna(v) else f"{float(v):+.2f} pts"


def _fmt_ev(value: Any) -> str:
    v = _to_num(value)
    return "—" if pd.isna(v) else f"{float(v) * 100:+.2f}%"


def _fmt_odds(value: Any) -> str:
    v = _to_num(value)
    if pd.isna(v):
        return "—"
    i = int(v)
    return f"+{i}" if i > 0 else str(i)


def _american_to_prob(odds: Any) -> float:
    v = _to_num(odds)
    if pd.isna(v) or float(v) == 0:
        return np.nan
    v = float(v)
    if v > 0:
        return 100.0 / (v + 100.0)
    return abs(v) / (abs(v) + 100.0)


def _normalize_name_key(name: Any) -> str:
    if pd.isna(name):
        return ""
    s = str(name).strip().lower()
    if "," in s:
        parts = s.split(",", 1)
        if len(parts) == 2:
            s = f"{parts[1].strip()} {parts[0].strip()}"
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t and t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    toks.sort()
    return " ".join(toks)


def _parse_name_list(value: Any) -> list[str]:
    s = str(value or "").strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [str(x).strip() for x in obj if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in re.split(r"\s*\|\s*", s) if x.strip()]


def resolve_tournament_id(explicit_tid: str = "") -> str:
    tid = _extract_tournament_id(explicit_tid)
    if tid:
        return tid

    files = sorted(ODDS_DIR.glob("recommended_bets_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return _extract_tournament_id(files[0].stem)

    latest = ODDS_DIR / "recommended_bets_latest.csv"
    if latest.exists():
        try:
            d = pd.read_csv(latest, nrows=1)
            if not d.empty and "tournament_id" in d.columns:
                return _extract_tournament_id(d.iloc[0]["tournament_id"])
        except Exception:
            pass
    return ""


def load_recommendations(tid: str) -> tuple[pd.DataFrame, Path | None]:
    candidates: list[Path] = []
    if tid:
        candidates.append(ODDS_DIR / f"recommended_bets_{tid}.csv")

    rid_files = sorted(ODDS_DIR.glob("recommended_bets_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates.extend(rid_files[:5])

    latest = ODDS_DIR / "recommended_bets_latest.csv"
    if latest.exists():
        candidates.append(latest)

    seen = set()
    ordered = []
    for p in candidates:
        if p.exists() and p not in seen:
            seen.add(p)
            ordered.append(p)

    for p in ordered:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty:
            continue
        if tid and "tournament_id" in df.columns:
            df = df[df["tournament_id"].astype(str).str.upper() == tid].copy()
            if df.empty:
                continue

        for col in ["edge_pts", "confidence", "ev_per_1", "model_prob", "book_prob", "odds_american"]:
            if col not in df.columns:
                df[col] = np.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if "book_prob" in df.columns:
            missing_book = df["book_prob"].isna() & df["odds_american"].notna()
            df.loc[missing_book, "book_prob"] = df.loc[missing_book, "odds_american"].apply(_american_to_prob)

        if "selection_label" not in df.columns:
            df["selection_label"] = ""
        if "bet_type" not in df.columns:
            df["bet_type"] = "single"
        if "market" not in df.columns:
            df["market"] = ""
        if "player_name" not in df.columns:
            df["player_name"] = ""

        return df.reset_index(drop=True), p

    return pd.DataFrame(), None


def load_expert_picks(tid: str) -> tuple[pd.DataFrame, Path | None]:
    candidates: list[Path] = []
    if tid:
        candidates.append(EXPERT_DIR / f"expert_picks_{tid}.csv")

    rid_files = sorted(EXPERT_DIR.glob("expert_picks_R*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates.extend(rid_files[:5])

    for name in ["expert_picks_latest.csv", "expert_picks_ep_table.csv"]:
        p = EXPERT_DIR / name
        if p.exists():
            candidates.append(p)

    seen = set()
    ordered = []
    for p in candidates:
        if p.exists() and p not in seen:
            seen.add(p)
            ordered.append(p)

    for p in ordered:
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if df.empty:
            continue
        if "expert_name" not in df.columns and "expert" in df.columns:
            df["expert_name"] = df["expert"]
        if "winner_name" not in df.columns and "winner" in df.columns:
            df["winner_name"] = df["winner"]
        if "lineup_player_names" not in df.columns:
            df["lineup_player_names"] = ""
        return df.reset_index(drop=True), p

    return pd.DataFrame(), None


def resolve_predictions_path(tid: str) -> Path | None:
    candidates: list[Path] = []

    if tid:
        for p in OUTPUTS_DIR.glob("*_latest.csv"):
            try:
                d = pd.read_csv(p, nrows=1)
                if not d.empty and "tournament_id" in d.columns:
                    if _extract_tournament_id(d.iloc[0].get("tournament_id", "")) == tid:
                        candidates.append(p)
            except Exception:
                continue

    candidates.extend([OUTPUTS_DIR / "latest_predictions.csv", OUTPUTS_DIR / "latest.csv"])
    candidates.extend(sorted(OUTPUTS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:20])

    seen = set()
    for p in candidates:
        if p.exists() and p not in seen:
            seen.add(p)
            return p
    return None


def rank_recommendations(df: pd.DataFrame, risk_profile: str) -> pd.DataFrame:
    work = df.copy()

    edge = pd.to_numeric(work.get("edge_pts"), errors="coerce").fillna(0.0)
    conf = pd.to_numeric(work.get("confidence"), errors="coerce").fillna(0.0) * 100.0
    ev = pd.to_numeric(work.get("ev_per_1"), errors="coerce").fillna(0.0) * 100.0
    odds = pd.to_numeric(work.get("odds_american"), errors="coerce").fillna(0.0).abs()

    if risk_profile == "conservative":
        score = (0.45 * edge) + (0.40 * conf) + (0.15 * ev) - np.where(odds > 3000, 8.0, 0.0)
    elif risk_profile == "aggressive":
        score = (0.55 * edge) + (0.20 * conf) + (0.25 * ev) + np.where(odds > 2500, np.minimum(6.0, odds / 3000.0), 0.0)
    else:
        score = (0.50 * edge) + (0.30 * conf) + (0.20 * ev)

    work["copilot_score"] = score
    work = work.sort_values(["copilot_score", "edge_pts", "confidence"], ascending=[False, False, False], na_position="last")
    return work.reset_index(drop=True)


def summarize_experts(expert_df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"winner_consensus": [], "lineup_mentions": {}}
    if expert_df.empty:
        return out

    if "winner_name" in expert_df.columns:
        winners = expert_df["winner_name"].fillna("").astype(str).str.strip()
        winners = winners[winners != ""]
        if not winners.empty:
            counts = winners.value_counts()
            total = max(1, int(len(expert_df)))
            out["winner_consensus"] = [
                {"player": str(name), "count": int(cnt), "share_pct": float(cnt) / total * 100.0}
                for name, cnt in counts.head(5).items()
            ]

    mentions: dict[str, int] = {}
    for v in expert_df.get("lineup_player_names", pd.Series(dtype=object)).fillna(""):
        for nm in _parse_name_list(v):
            k = _normalize_name_key(nm)
            if k:
                mentions[k] = mentions.get(k, 0) + 1
    out["lineup_mentions"] = mentions
    return out


def summarize_fantasy_angles(pred_path: Path | None, expert_summary: dict[str, Any], max_rows: int = 15) -> dict[str, list[str]]:
    out = {"core": [], "pivots": []}
    if pred_path is None or not pred_path.exists():
        return out

    try:
        preds = pd.read_csv(pred_path)
    except Exception:
        return out
    if preds.empty or "player_name" not in preds.columns:
        return out

    top_col = "top10_prob" if "top10_prob" in preds.columns else ("top20_prob" if "top20_prob" in preds.columns else "")
    if not top_col:
        return out

    preds = preds.copy()
    preds["player_name"] = preds["player_name"].fillna("").astype(str).str.strip()
    preds = preds[preds["player_name"] != ""]
    preds[top_col] = pd.to_numeric(preds[top_col], errors="coerce")
    preds = preds[preds[top_col].notna()].sort_values(top_col, ascending=False).head(max_rows)
    if preds.empty:
        return out

    mentions = expert_summary.get("lineup_mentions", {}) or {}
    preds["name_key"] = preds["player_name"].apply(_normalize_name_key)
    preds["expert_mentions"] = preds["name_key"].map(lambda k: mentions.get(k, 0))

    core = preds[preds["expert_mentions"] >= 2].head(4)
    pivots = preds[preds["expert_mentions"] == 0].head(4)

    out["core"] = [
        f"{r.player_name} ({top_col}: {float(getattr(r, top_col))*100:.1f}%)"
        for r in core.itertuples(index=False)
    ]
    out["pivots"] = [
        f"{r.player_name} ({top_col}: {float(getattr(r, top_col))*100:.1f}%)"
        for r in pivots.itertuples(index=False)
    ]
    return out


def build_deterministic_answer(
    tid: str,
    question: str,
    risk_profile: str,
    ranked_df: pd.DataFrame,
    expert_summary: dict[str, Any],
    fantasy_summary: dict[str, list[str]],
    max_picks: int,
) -> str:
    singles = ranked_df[ranked_df["bet_type"].astype(str).str.lower() == "single"].head(max_picks).copy()
    cards = ranked_df[ranked_df["bet_type"].astype(str).str.lower() == "content_card"].head(3).copy()

    lines: list[str] = []
    lines.append(f"### Betting Copilot ({risk_profile.title()})")
    if tid:
        lines.append(f"**Tournament:** `{tid}`")
    if question.strip():
        lines.append(f"**Question:** {question.strip()}")
    lines.append("")

    if singles.empty and cards.empty:
        lines.append("No tracked recommendations found. Run `python3 scripts/models/recommend_bets.py --tournament-id RYYYYNNN` first.")
        return "\n".join(lines)

    if not singles.empty:
        lines.append("#### Best Tracked Bets")
        for i, row in enumerate(singles.itertuples(), 1):
            label = str(getattr(row, "selection_label", "") or getattr(row, "title", "") or "Recommendation").strip()
            line = (
                f"{i}. **{label}** (`{_fmt_odds(getattr(row, 'odds_american', np.nan))}`) | "
                f"model `{_fmt_pct(getattr(row, 'model_prob', np.nan))}` vs "
                f"book `{_fmt_pct(getattr(row, 'book_prob', np.nan))}` | "
                f"edge `{_fmt_pts(getattr(row, 'edge_pts', np.nan))}` | "
                f"ev `{_fmt_ev(getattr(row, 'ev_per_1', np.nan))}` | "
                f"conf `{_to_num(getattr(row, 'confidence', np.nan)):.2f}`"
            )
            lines.append(line)
        lines.append("")

    if not cards.empty:
        lines.append("#### DraftKings Content Cards")
        for i, row in enumerate(cards.itertuples(), 1):
            title = str(getattr(row, "title", "") or getattr(row, "selection_label", "")).strip()
            legs = int(_to_num(getattr(row, "selection_count", np.nan)) or 0)
            lines.append(
                f"{i}. **{title}** ({legs} legs, `{_fmt_odds(getattr(row, 'odds_american', np.nan))}`) | "
                f"edge `{_fmt_pts(getattr(row, 'edge_pts', np.nan))}` | "
                f"ev `{_fmt_ev(getattr(row, 'ev_per_1', np.nan))}` | "
                f"conf `{_to_num(getattr(row, 'confidence', np.nan)):.2f}`"
            )
        lines.append("")

    consensus = expert_summary.get("winner_consensus", [])
    if consensus:
        lines.append("#### Expert Consensus Pulse")
        for row in consensus[:3]:
            lines.append(f"- {row['player']}: {row['count']} winner pick(s) ({row['share_pct']:.0f}%)")
        lines.append("")

    core = fantasy_summary.get("core", [])
    pivots = fantasy_summary.get("pivots", [])
    if core or pivots:
        lines.append("#### Fantasy Strategy Angle")
        if core:
            lines.append(f"- Core: {', '.join(core[:3])}")
        if pivots:
            lines.append(f"- Pivots: {', '.join(pivots[:3])}")
        lines.append("")

    bankroll_hint = {
        "conservative": "Stakes: 0.5u singles; avoid high-variance cards unless confidence >= 0.85.",
        "balanced": "Stakes: 0.75u top singles; 0.25u on at most one card.",
        "aggressive": "Stakes: 1.0u top singles; up to 0.5u spread across 1-2 high-edge cards.",
    }.get(risk_profile, "Stakes: keep unit size consistent; bet edge, not emotion.")
    lines.append(f"**Bankroll Hint:** {bankroll_hint}")

    return "\n".join(lines)


def maybe_query_ollama(
    use_llm: bool,
    model: str,
    ollama_url: str,
    question: str,
    deterministic_answer: str,
    ranked_df: pd.DataFrame,
    max_context_rows: int = 12,
) -> tuple[str, str]:
    if not use_llm:
        return "", ""

    context_cols = [c for c in [
        "recommendation_id", "bet_type", "market", "selection_label", "title",
        "odds_american", "model_prob", "book_prob", "edge_pts", "ev_per_1", "confidence"
    ] if c in ranked_df.columns]
    ctx = ranked_df[context_cols].head(max_context_rows).copy()

    prompt = (
        "You are a grounded golf betting assistant.\n"
        "Rules:\n"
        "1) Only discuss picks present in the ALLOWED_RECOMMENDATIONS table.\n"
        "2) Do not invent players, odds, lines, or new bets.\n"
        "3) Keep answer concise and practical.\n\n"
        f"User question:\n{question.strip() or 'Summarize best bets and fantasy angle.'}\n\n"
        f"ALLOWED_RECOMMENDATIONS (JSON):\n{ctx.to_json(orient='records')}\n\n"
        f"Baseline deterministic analysis:\n{deterministic_answer}\n\n"
        "Return markdown."
    )

    try:
        resp = requests.post(
            ollama_url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 900},
            },
            timeout=90,
        )
        if resp.status_code != 200:
            return "", f"Ollama status {resp.status_code}"
        txt = str(resp.json().get("response", "")).strip()
        if not txt:
            return "", "Ollama returned empty response"
        return txt, ""
    except Exception as e:
        return "", str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grounded betting + fantasy copilot")
    parser.add_argument("--tournament-id", default="", help="Tournament ID like R2026007")
    parser.add_argument("--question", default="", help="User question for copilot")
    parser.add_argument("--risk-profile", choices=["conservative", "balanced", "aggressive"], default="balanced")
    parser.add_argument("--max-picks", type=int, default=5)
    parser.add_argument("--use-llm", action="store_true", help="Use local Ollama model")
    parser.add_argument("--ollama-model", default="llama3.2")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    tid = resolve_tournament_id(args.tournament_id)
    rec_df, rec_path = load_recommendations(tid)

    if rec_df.empty:
        payload = {
            "ok": False,
            "tournament_id": tid,
            "error": "No tracked recommendations found.",
            "answer_markdown": "No tracked recommendations found. Run recommend_bets first.",
        }
        print(json.dumps(payload) if args.format == "json" else payload["answer_markdown"])
        return 0

    ranked_df = rank_recommendations(rec_df, args.risk_profile)

    expert_df, expert_path = load_expert_picks(tid)
    expert_summary = summarize_experts(expert_df)

    pred_path = resolve_predictions_path(tid)
    fantasy_summary = summarize_fantasy_angles(pred_path, expert_summary)

    deterministic_answer = build_deterministic_answer(
        tid=tid,
        question=args.question,
        risk_profile=args.risk_profile,
        ranked_df=ranked_df,
        expert_summary=expert_summary,
        fantasy_summary=fantasy_summary,
        max_picks=max(1, int(args.max_picks)),
    )

    llm_answer, llm_err = maybe_query_ollama(
        use_llm=bool(args.use_llm),
        model=str(args.ollama_model).strip() or "llama3.2",
        ollama_url=str(args.ollama_url).strip() or "http://localhost:11434/api/generate",
        question=args.question,
        deterministic_answer=deterministic_answer,
        ranked_df=ranked_df,
    )

    used_llm = bool(llm_answer)
    final_answer = llm_answer if used_llm else deterministic_answer
    if llm_err:
        final_answer = f"{final_answer}\n\n> LLM fallback note: {llm_err}"

    payload = {
        "ok": True,
        "tournament_id": tid,
        "used_llm": used_llm,
        "recommendations_source": rec_path.name if rec_path else "",
        "expert_source": expert_path.name if expert_path else "",
        "predictions_source": pred_path.name if pred_path else "",
        "answer_markdown": final_answer,
    }

    if args.format == "json":
        print(json.dumps(payload))
    else:
        print(final_answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
