import sys
import pandas as pd 
import numpy as np 
from pathlib import Path 
from scipy import stats 
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    

from scripts.models.props_model import (
    american_to_prob, 
    calculate_matchup_probability,
    generate_round_score_prop
)


ODDS_DIR = Path("data/odds/")


def _name_key(name: str) -> str:
    if pd.isna(name):
        return "" 
    
    
    cleaned = str(name).replace(",", " ").replace(".", " ").replace("-", " ").lower().strip()
    
    toks = [t for t in cleaned.split(" ") if t]
    toks = [t for t in toks if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    toks.sort()
    return " ".join(toks)


def _short_name_key(name: str) -> str:
    """Loose matching key: '<last> <first_initial>'."""
    if pd.isna(name):
        return ""
    cleaned = str(name).replace(",", " ").replace(".", " ").replace("-", " ").lower().strip()
    toks = [t for t in cleaned.split(" ") if t]
    toks = [t for t in toks if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    if not toks:
        return ""
    first = toks[0]
    last = toks[-1]
    if not first or not last:
        return ""
    return f"{last} {first[0]}"


def _to_num(v):
    if pd.isna(v):
        return np.nan 
    s = str(v).replace("+", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return np.nan


def _to_int_odds(v):
    n = _to_num(v)
    if pd.isna(n):
        return None
    try:
        return int(n)
    except Exception:
        return None
    
    
def load_latest_prop_lines(tournament_id: str | None = None) -> pd.DataFrame:
    if tournament_id:
        candidates = [
            ODDS_DIR / f"prop_lines_{tournament_id}.csv",
            ODDS_DIR / f"{tournament_id}_props.csv",
        ]
        for p in candidates:
            if p.exists():
                return pd.read_csv(p)
    files = sorted(ODDS_DIR.glob("prop_lines_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    if files:
        return pd.read_csv(files[0])
    return pd.DataFrame()


def estimate_birdie_over_under_probs(player_row: dict, line: float) -> tuple[float, float]:
    # lightweight starter model; replace later with shot-level/birdie history model
    sg_app = player_row.get("sg_app", 0) or 0
    sg_putt = player_row.get("sg_putt", 0) or 0
    form = player_row.get("form_trend", 0) or 0
    expected = 3.6 + 0.9 * sg_app + 0.5 * sg_putt + 0.4 * form
    std = 1.35
    under_prob = stats.norm.cdf(line, expected, std)
    over_prob = 1 - under_prob
    return float(over_prob), float(under_prob)


def score_book_props(
    preds_df: pd.DataFrame,
    prop_lines_df: pd.DataFrame,
    course_par: int = 72,
    course_avg: float = 71.0,
) -> pd.DataFrame:
    if preds_df.empty or prop_lines_df.empty:
        return pd.DataFrame()

    df = preds_df.copy()
    df["name_key"] = df["player_name"].apply(_name_key)
    by_key = {r["name_key"]: r for _, r in df.iterrows() if r["name_key"]}
    by_short = {}
    for _, r in df.iterrows():
        sk = _short_name_key(r.get("player_name"))
        if sk:
            by_short.setdefault(sk, []).append(r)

    def _resolve_player_row(name: str):
        k = _name_key(name)
        if k in by_key:
            return by_key[k]
        sk = _short_name_key(name)
        cands = by_short.get(sk, [])
        if len(cands) == 1:
            return cands[0]
        return None

    out = []

    for _, row in prop_lines_df.iterrows():
        market = str(row.get("market", "")).strip().lower()
        book = row.get("book", row.get("sportsbook", "UNKNOWN"))
        line_source = row.get("line_source", row.get("source", "file"))

        if market == "winner":
            name = row.get("player_name")
            p_row = _resolve_player_row(name)
            if p_row is None:
                continue

            odds_raw = row.get("odds", row.get("book_odds", row.get("odds_to_win")))
            odds = _to_int_odds(odds_raw)
            if odds is None:
                continue
            model_prob = p_row.get("model_win_prob", p_row.get("win_prob"))
            try:
                model_prob = float(model_prob)
            except Exception:
                continue

            book_prob = american_to_prob(odds)
            out.append({
                "market": "winner",
                "selection": str(p_row.get("player_name", name)),
                "book_odds": odds,
                "book_prob": book_prob,
                "model_prob": model_prob,
                "edge_pts": (model_prob - book_prob) * 100,
                "book": book,
                "line_source": line_source,
            })

        elif market == "h2h":
            a = row.get("player_a")
            b = row.get("player_b")
            row_a = _resolve_player_row(a)
            row_b = _resolve_player_row(b)
            if row_a is None or row_b is None:
                continue

            p_a, _ = calculate_matchup_probability(row_a, row_b)
            p_b = 1 - p_a
            odds_a = _to_int_odds(row.get("odds_a"))
            odds_b = _to_int_odds(row.get("odds_b"))
            if odds_a is None or odds_b is None:
                continue

            book_a = american_to_prob(odds_a)
            book_b = american_to_prob(odds_b)
            name_a = row_a.get("player_name", a)
            name_b = row_b.get("player_name", b)

            out.append({
                "market": "h2h",
                "selection": f"{name_a} over {name_b}",
                "book_odds": odds_a,
                "book_prob": book_a,
                "model_prob": p_a,
                "edge_pts": (p_a - book_a) * 100,
                "book": book,
                "line_source": line_source,
            })
            out.append({
                "market": "h2h",
                "selection": f"{name_b} over {name_a}",
                "book_odds": odds_b,
                "book_prob": book_b,
                "model_prob": p_b,
                "edge_pts": (p_b - book_b) * 100,
                "book": book,
                "line_source": line_source,
            })

        elif market == "round_score":
            name = row.get("player_name")
            p_row = _resolve_player_row(name)
            if p_row is None:
                continue
            line = float(row.get("line"))
            round_num = int(row.get("round_num", 1))
            rp = generate_round_score_prop(
                p_row,
                line=line,
                round_num=round_num,
                course_par=course_par,
                course_scoring_avg=course_avg,
            )
            o_odds = _to_int_odds(row.get("over_odds"))
            u_odds = _to_int_odds(row.get("under_odds"))
            if o_odds is None or u_odds is None:
                continue
            p_name = p_row.get("player_name", name)

            out.append({
                "market": "round_score",
                "selection": f"{p_name} Over {line}",
                "book_odds": o_odds,
                "book_prob": american_to_prob(o_odds),
                "model_prob": rp.over_prob,
                "edge_pts": (rp.over_prob - american_to_prob(o_odds)) * 100,
                "book": book,
                "line_source": line_source,
            })
            out.append({
                "market": "round_score",
                "selection": f"{p_name} Under {line}",
                "book_odds": u_odds,
                "book_prob": american_to_prob(u_odds),
                "model_prob": rp.under_prob,
                "edge_pts": (rp.under_prob - american_to_prob(u_odds)) * 100,
                "book": book,
                "line_source": line_source,
            })

        elif market == "birdies":
            name = row.get("player_name")
            p_row = _resolve_player_row(name)
            if p_row is None:
                continue
            line = float(row.get("line"))
            over_prob, under_prob = estimate_birdie_over_under_probs(p_row, line)
            o_odds = _to_int_odds(row.get("over_odds"))
            u_odds = _to_int_odds(row.get("under_odds"))
            if o_odds is None or u_odds is None:
                continue
            p_name = p_row.get("player_name", name)

            out.append({
                "market": "birdies",
                "selection": f"{p_name} Over {line} Birdies",
                "book_odds": o_odds,
                "book_prob": american_to_prob(o_odds),
                "model_prob": over_prob,
                "edge_pts": (over_prob - american_to_prob(o_odds)) * 100,
                "book": book,
                "line_source": line_source,
            })
            out.append({
                "market": "birdies",
                "selection": f"{p_name} Under {line} Birdies",
                "book_odds": u_odds,
                "book_prob": american_to_prob(u_odds),
                "model_prob": under_prob,
                "edge_pts": (under_prob - american_to_prob(u_odds)) * 100,
                "book": book,
                "line_source": line_source,
            })

    result = pd.DataFrame(out)
    if result.empty:
        return result
    result["edge_pts"] = pd.to_numeric(result["edge_pts"], errors="coerce")
    result = result.sort_values("edge_pts", ascending=False)
    return result


def american_to_decimal(odds: int) -> float:
    return 1 + (odds / 100.0) if odds > 0 else 1 + (100.0 / abs(odds))


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def score_parlay(model_probs: list[float], leg_book_odds: list[int]) -> dict:
    model_prob = float(np.prod(model_probs))
    dec = [american_to_decimal(int(o)) for o in leg_book_odds]
    book_decimal = float(np.prod(dec))
    book_prob = 1.0 / book_decimal
    return {
        "model_prob": model_prob,
        "book_prob": book_prob,
        "edge_pts": (model_prob - book_prob) * 100,
        "book_parlay_odds": decimal_to_american(book_decimal),
    }
