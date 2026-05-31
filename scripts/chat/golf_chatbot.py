"""
Golf chat assistant — context builder + Groq streaming response.

Context is query-aware: the blocks included depend on what the user asked.
  - Player question  → player deep-dive + SG + odds movement
  - Bet question     → bets + odds movement + weather
  - Live question    → leaderboard + cut projection
  - Lineup question  → my picks + usage + predictions
  - Weather/course   → weather forecast + course profile
  - General          → full overview (default)
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"
OUTPUTS = PROJECT_ROOT / "outputs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_name(name: str) -> str:
    """Normalize 'Last, First' → 'First Last'. Pass-through otherwise."""
    s = str(name).strip()
    if ", " in s:
        last, first = s.split(", ", 1)
        return f"{first} {last}"
    return s


def _safe_int(val) -> int | None:
    """Parse a position string like 'T4', 'WIN', '1' to int. Returns None if not parseable."""
    if val is None:
        return None
    s = str(val).strip().upper().lstrip("T")
    if s == "WIN":
        return 1
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _american_to_implied(odds) -> float | None:
    """Convert American odds to implied probability (0–1)."""
    try:
        o = float(odds)
        if o > 0:
            return 100 / (o + 100)
        else:
            return abs(o) / (abs(o) + 100)
    except (TypeError, ValueError):
        return None


def _fmt_odds(odds) -> str:
    """Format American odds as +1300 or -110."""
    try:
        o = int(float(odds))
        return f"+{o}" if o > 0 else str(o)
    except (TypeError, ValueError):
        return "—"


def _fmt_course_history(row) -> str:
    """Compact course history: '5 starts · 3 T10s · 2 wins' or 'No history'."""
    starts = int(row.get("hist_times_played", 0) or 0)
    if starts == 0:
        return "No history"
    top10s = int(row.get("hist_top10s", 0) or 0)
    wins   = int(row.get("hist_wins", 0) or 0)
    parts  = [f"{starts} starts", f"{top10s} T10s"]
    if wins:
        parts.append(f"{wins} win{'s' if wins > 1 else ''}")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Course historical scoring context
# ---------------------------------------------------------------------------

def _course_winning_context(tid: str | None) -> dict:
    """Return historical winning score and field avg at this course.

    Scans all leaderboard CSVs for tournaments sharing the same event number
    (last 3 digits of tid, e.g. '020' for Houston Open across all years).
    Returns:
        {
          'winner_avg': float,   # median winning score (to par)
          'cut_avg': float,      # median score at the cut bubble (~top 65)
          'years': int,          # number of historical seasons found
          'winning_range': str,  # e.g. "-10 to -20"
        }
    or {} if not enough data.
    """
    if not tid:
        return {}

    # Extract event suffix (last 3 chars: '020', '475', etc.)
    event_suffix = tid[-3:]
    hist_dir = DATA / "historical"
    winning_scores = []
    cut_scores = []

    try:
        for f in sorted(hist_dir.glob("leaderboards_20*.csv")):
            df = pd.read_csv(f, low_memory=False)
            if "tournament_id" not in df.columns:
                continue
            # Match any year's version of this event
            mask = df["tournament_id"].astype(str).str.endswith(event_suffix)
            t = df[mask].copy()
            if t.empty:
                continue

            # Parse to_par — handle 'E' (even par) and string formats
            def _parse_to_par(v):
                s = str(v).strip().upper()
                if s in ("E", "EVEN", "PAR"):
                    return 0.0
                try:
                    return float(s)
                except (ValueError, TypeError):
                    return None

            t["_to_par"] = t["to_par"].apply(_parse_to_par)
            t = t[t["_to_par"].notna()]

            # Winner (position == '1')
            winner = t[t["position"].astype(str).str.strip() == "1"]
            if not winner.empty:
                winning_scores.append(float(winner.iloc[0]["_to_par"]))

            # Cut line: players who made cut (not CUT/MC/WD), near the bubble
            made_cut = t[~t["position"].astype(str).str.strip().isin(["CUT", "MC", "WD", "DQ"])]
            if len(made_cut) >= 20:
                # 70th percentile (top ~30% of finishers) ≈ typical cut line
                cut_scores.append(float(made_cut["_to_par"].quantile(0.30)))

    except Exception:
        pass

    if len(winning_scores) < 2:
        return {}

    return {
        "winner_avg": round(sum(winning_scores) / len(winning_scores), 1),
        "winner_median": round(sorted(winning_scores)[len(winning_scores) // 2], 1),
        "cut_avg": round(sum(cut_scores) / len(cut_scores), 1) if cut_scores else None,
        "winning_range": f"{int(max(winning_scores))} to {int(min(winning_scores))}",
        "years": len(winning_scores),
    }


# Cache so we only scan CSVs once per chatbot session
_course_context_cache: dict[str, dict] = {}
_player_course_history_cache: dict[str, dict] = {}


def _get_course_winning_context(tid: str | None) -> dict:
    if not tid:
        return {}
    if tid not in _course_context_cache:
        _course_context_cache[tid] = _course_winning_context(tid)
    return _course_context_cache[tid]


def _get_player_course_years(player_id: str | int | None, player_name: str, tid: str | None) -> list[dict]:
    """Return per-year results for a player at this course.

    Returns list of dicts sorted newest first:
        [{'year': 2025, 'position': 'T4', 'to_par': -14}, ...]
    """
    if not tid:
        return []
    cache_key = f"{player_id}_{player_name}_{tid[-3:]}"
    if cache_key in _player_course_history_cache:
        return _player_course_history_cache[cache_key]

    event_suffix = tid[-3:]
    hist_dir = DATA / "historical"
    results = []

    def _parse_to_par(v):
        s = str(v).strip().upper()
        if s in ("E", "EVEN", "PAR"):
            return 0
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    def _fmt_pos(pos_str: str) -> str:
        s = str(pos_str).strip()
        if s in ("CUT", "MC", "WD", "DQ"):
            return s
        try:
            n = int(float(s))
            return f"T{n}" if n > 1 else "WIN"
        except (ValueError, TypeError):
            return s

    pid_str = str(int(float(player_id))) if player_id is not None else None

    try:
        for f in sorted(hist_dir.glob("leaderboards_20*.csv")):
            df = pd.read_csv(f, low_memory=False)
            if "tournament_id" not in df.columns:
                continue
            mask = df["tournament_id"].astype(str).str.endswith(event_suffix)
            t = df[mask]
            if t.empty:
                continue

            # Match by player_id first, then by name
            row = pd.DataFrame()
            if pid_str and "player_id" in t.columns:
                row = t[t["player_id"].astype(str).apply(lambda x: str(int(float(x))) if x.replace('.', '', 1).isdigit() else x) == pid_str]
            if row.empty and "player_name" in t.columns:
                # Normalize names for comparison
                def _norm(n):
                    n = str(n).strip().lower()
                    if ", " in n:
                        last, first = n.split(", ", 1)
                        return f"{first} {last}"
                    return n
                pname_norm = _norm(player_name)
                row = t[t["player_name"].apply(_norm) == pname_norm]

            if row.empty:
                continue

            r = row.iloc[0]
            year = int(r.get("year", 0)) if pd.notna(r.get("year", None)) else None
            if not year:
                # Try to extract from filename e.g. leaderboards_2024.csv
                try:
                    year = int(f.stem.split("_")[-1])
                except (ValueError, IndexError):
                    continue

            pos = _fmt_pos(str(r.get("position", "?")))
            to_par = _parse_to_par(r.get("to_par", ""))
            results.append({"year": year, "position": pos, "to_par": to_par})

    except Exception:
        pass

    results.sort(key=lambda x: x["year"], reverse=True)
    _player_course_history_cache[cache_key] = results
    return results






def _post_tournament_summary_block(tid: str | None = None) -> str:
    """
    Read the post-tournament summary file for a recently completed tournament.
    Returns the summary as a context block, or empty string if not found.
    """
    if not tid:
        return ""
    summary_path = PROJECT_ROOT / "logs" / f"post_tournament_summary_{tid}.txt"
    if not summary_path.exists():
        return ""
    try:
        content = summary_path.read_text().strip()
        if not content:
            return ""
        return f"## POST-TOURNAMENT SUMMARY\n{content}"
    except Exception:
        return ""   
        
        

        



# ---------------------------------------------------------------------------
# Tournament ID detection
# ---------------------------------------------------------------------------

def _detect_tournament_id() -> str | None:
    """Auto-detect active or upcoming tournament ID.

    Priority:
    1. tournament_id column in latest_predictions.csv (stamped at generation time)
    2. Current/upcoming tournament from schedule (this week's tournament by date)
    3. recommended_bets_latest.csv tournament_id
    4. Most recent non-Official live meta file (active round)
    5. Most recent live meta file (fallback)
    """
    # 1. Predictions file — most reliable when stamped correctly
    preds_path = OUTPUTS / "latest_predictions.csv"
    if preds_path.exists():
        try:
            df = pd.read_csv(preds_path, usecols=lambda c: c in ("tournament_id",), nrows=5)
            if "tournament_id" in df.columns and not df.empty:
                val = df["tournament_id"].dropna()
                if not val.empty:
                    return str(val.mode().iloc[0])
        except Exception:
            pass

    # 2. Schedule — find this week's tournament by date
    sched_path = DATA / "raw" / "schedule_2026.csv"
    if sched_path.exists():
        try:
            sched = pd.read_csv(sched_path)
            today = datetime.now().date()
            for _, row in sched.iterrows():
                start = pd.to_datetime(row.get("start_date"), errors="coerce")
                end   = pd.to_datetime(row.get("end_date"),   errors="coerce")
                if pd.isna(start):
                    continue
                # Tournament week: Mon before start through Sun of tournament end
                week_start = start.date() - __import__("datetime").timedelta(days=start.weekday())
                week_end   = end.date() if pd.notna(end) else start.date() + __import__("datetime").timedelta(days=6)
                if week_start <= today <= week_end:
                    return str(row["tournament_id"])
            # If between tournaments, return the next upcoming one
            future = sched[pd.to_datetime(sched["start_date"], errors="coerce").dt.date > today]
            if not future.empty:
                return str(future.iloc[0]["tournament_id"])
        except Exception:
            pass

    # 3. Recommended bets latest
    bets_path = DATA / "odds" / "recommended_bets_latest.csv"
    if bets_path.exists():
        try:
            df = pd.read_csv(bets_path, usecols=["tournament_id"], nrows=5)
            if not df.empty:
                return str(df["tournament_id"].mode().iloc[0])
        except Exception:
            pass

    meta_files = glob.glob(str(DATA / "live" / "leaderboard_r*_meta.json"))
    if not meta_files:
        return None

    for mf in meta_files:
        try:
            with open(mf) as f:
                meta = json.load(f)
            if str(meta.get("round_status", "")).lower() != "official":
                return meta.get("tournament_id")
        except Exception:
            pass

    meta_files.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(meta_files[0]) as f:
            return json.load(f).get("tournament_id")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Normalize accented characters to ASCII equivalents (e.g. Å → A, é → e)."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _extract_players(query: str) -> list[str]:
    """Find player names mentioned in the query. Returns list of formatted names.
    Matches on last name (≥4 chars) OR first name (≥4 chars, unique enough to avoid false positives).
    Accent-insensitive: 'Aberg' matches 'Åberg'.
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, usecols=["player_name"])
        # Normalize query: lowercase + strip accents so 'aberg' matches 'åberg'
        q_lower = _strip_accents(query.lower())
        matched = []
        # Build a set of first names that appear more than once — too ambiguous to match on
        all_names = [_strip_accents(_fmt_name(str(r)).lower()).split() for r in df["player_name"]]
        first_name_counts: dict[str, int] = {}
        for parts in all_names:
            if parts:
                first_name_counts[parts[0]] = first_name_counts.get(parts[0], 0) + 1

        for raw in df["player_name"]:
            name = _fmt_name(str(raw))
            # Use accent-stripped version for matching only; keep original for display
            parts = _strip_accents(name.lower()).split()
            last  = parts[-1] if parts else ""
            first = parts[0]  if parts else ""

            found = False
            # Match on last name (≥4 chars)
            if len(last) >= 4 and re.search(rf'\b{re.escape(last)}\b', q_lower):
                found = True
            # Match on first name (≥4 chars, only if unique in the field)
            elif len(first) >= 4 and first_name_counts.get(first, 0) == 1:
                if re.search(rf'\b{re.escape(first)}\b', q_lower):
                    found = True
            # Full-name fallback: any 2 consecutive words from player name appear together in query
            # Handles short names like "Min Woo Lee" (last="lee" 3 chars, first="min" 3 chars)
            if not found and len(parts) >= 2:
                for i in range(len(parts) - 1):
                    bigram = parts[i] + r'\s+' + parts[i + 1]
                    if re.search(bigram, q_lower):
                        found = True
                        break
            if found:
                matched.append(name)

        return matched
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Historical query helpers
# ---------------------------------------------------------------------------

def _extract_year(query: str) -> int | None:
    """Extract an explicit year or resolve 'last year' / 'this year'."""
    q = query.lower()
    m = re.search(r'\b(20[12][0-9])\b', q)
    if m:
        return int(m.group(1))
    current = datetime.now().year
    if re.search(r'\blast\s+year\b', q):
        return current - 1
    if re.search(r'\b2\s+years?\s+ago\b', q):
        return current - 2
    if re.search(r'\bprevious\s+year\b', q):
        return current - 1
    return None


def _is_historical_query(q: str) -> bool:
    """True if the query is asking about past results."""
    year = _extract_year(q)
    if year and year < datetime.now().year:
        return True
    return any(w in q for w in [
        "last year", "previous year", "years ago", "historically",
        "who won", "winner of", "past results", "history", "all time",
        "career", "career history", "career record", "ever won",
        "how many times", "how often", "previous results",
        # Course/major record patterns
        "record at", "history at", "at the masters", "at augusta",
        "at the open", "at pga", "at the players", "at bay hill",
        "masters record", "major record", "course record", "major history",
        "at this course", "at this event", "at this tournament",
        "how many wins", "how many times won", "times played",
        "prior starts", "past performance", "historical performance",
    ])


# Build a lookup: keyword → event suffix from historical schedule
_EVENT_KEYWORD_MAP: dict[str, str] | None = None

def _build_event_keyword_map() -> dict[str, str]:
    """Load all known tournament names and build keyword → event suffix map."""
    hist_dir = DATA / "historical"
    name_to_suffix: dict[str, str] = {}
    for f in sorted(hist_dir.glob("leaderboards_20*.csv")):
        try:
            df = pd.read_csv(f, usecols=["tournament_id", "tournament_name"], low_memory=False)
            for _, row in df.drop_duplicates("tournament_id").iterrows():
                tid = str(row["tournament_id"]).strip()
                name = str(row["tournament_name"]).strip().lower()
                suffix = tid[-3:]
                name_to_suffix[name] = suffix
                # Also index individual significant words (≥5 chars)
                for word in re.findall(r'[a-z]{5,}', name):
                    if word not in ("championship", "invitational", "presented", "classic",
                                    "memorial", "tournament", "children", "players"):
                        name_to_suffix.setdefault(word, suffix)
        except Exception:
            continue
    return name_to_suffix


def _extract_event_from_query(query: str) -> str | None:
    """Return event suffix (last 3 digits of tid) if the query names a known event."""
    q = query.lower()

    # Hard-coded major tournament keywords — checked first so they always win
    _MAJOR_KEYWORDS: list[tuple[str, str]] = [
        ("masters",          "014"),
        ("augusta",          "014"),
        ("us open",          "026"),
        ("u.s. open",        "026"),
        ("pga championship", "047"),
        ("the open",         "100"),
        ("british open",     "100"),
        ("open championship","100"),
        ("the players",      "011"),
        ("players championship", "011"),
        ("bay hill",         "005"),
        ("arnold palmer",    "005"),
        ("riviera",          "007"),
        ("genesis",          "007"),
        ("memorial",         "020"),
        ("muirfield",        "020"),
    ]
    for keyword, suffix in _MAJOR_KEYWORDS:
        if keyword in q:
            return suffix

    global _EVENT_KEYWORD_MAP
    if _EVENT_KEYWORD_MAP is None:
        _EVENT_KEYWORD_MAP = _build_event_keyword_map()
    # Try full name matches from CSV data (longer = more specific)
    best = None
    best_len = 0
    for name, suffix in _EVENT_KEYWORD_MAP.items():
        if len(name) > 4 and name in q and len(name) > best_len:
            best = suffix
            best_len = len(name)
    return best


def _historical_tournament_block(event_suffix: str, year: int, top_n: int = 15) -> str:
    """Return top-N leaderboard for a past edition of an event."""
    hist_dir = DATA / "historical"
    f = hist_dir / f"leaderboards_{year}.csv"
    if not f.exists():
        return f"## Historical Results\nNo data available for {year}."
    try:
        df = pd.read_csv(f, low_memory=False)
        mask = df["tournament_id"].astype(str).str.endswith(event_suffix)
        t = df[mask].copy()
        if t.empty:
            return f"## Historical Results\nNo {year} results found for this event."

        tname = str(t["tournament_name"].iloc[0]) if "tournament_name" in t.columns else f"Event (suffix {event_suffix})"

        def _parse_to_par(v):
            s = str(v).strip().upper()
            if s in ("E", "EVEN", "PAR"):
                return 0
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return None

        def _fmt_pos(p):
            s = str(p).strip()
            if s in ("CUT", "MC", "WD", "DQ"):
                return s
            try:
                n = int(float(s))
                return f"T{n}" if n > 1 else "1st"
            except (ValueError, TypeError):
                return s

        t["_to_par"] = t["to_par"].apply(_parse_to_par)
        def _pos_sort_key(p):
            s = str(p).strip()
            if s in ("CUT", "MC", "WD", "DQ"):
                return 999
            s = s.lstrip("Tt")  # strip leading T/t (e.g. "T2" → "2")
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 999
        t["_pos_num"] = t["position"].apply(_pos_sort_key)
        t = t.sort_values("_pos_num").head(top_n)

        lines = [f"## {tname} — {year} Results (Top {min(top_n, len(t))})"]
        rows = ["| Pos | Player | Score | R1 | R2 | R3 | R4 |", "|-----|--------|-------|----|----|----|----|"]
        for _, r in t.iterrows():
            pos = _fmt_pos(r.get("position", "?"))
            name = _fmt_name(str(r.get("player_name", "?")))
            tp = r["_to_par"]
            tp_str = f"{tp:+d}" if tp is not None else "—"
            def _rs(col):
                v = r.get(col)
                if pd.isna(v):
                    return "—"
                try:
                    n = int(float(v))
                    return f"{n:+d}" if n != 0 else "E"
                except (ValueError, TypeError):
                    return "—"
            rows.append(f"| {pos} | {name} | {tp_str} | {_rs('r1_to_par')} | {_rs('r2_to_par')} | {_rs('r3_to_par')} | {_rs('r4_to_par')} |")
        lines.extend(rows)
        return "\n".join(lines)
    except Exception as e:
        return f"## Historical Results\nError loading data: {e}"


def _player_season_history_block(player_names: list[str], year: int) -> str:
    """All finishes for named player(s) in a given season."""
    hist_dir = DATA / "historical"
    f = hist_dir / f"leaderboards_{year}.csv"
    if not f.exists():
        return f"## Player History\nNo data available for {year}."
    try:
        df = pd.read_csv(f, low_memory=False)
        df["_name_norm"] = df["player_name"].apply(lambda n: _fmt_name(str(n)).lower())

        lines = [f"## Player Results — {year} Season"]
        for pname in player_names:
            # Match by last name
            pname_lower = pname.lower()
            last = pname_lower.split()[-1]
            mask = df["_name_norm"].str.contains(last, na=False)
            # Narrow by first name if multiple hits
            if first := (pname_lower.split()[0] if ' ' in pname_lower else ""):
                narrow = df[mask]["_name_norm"].str.startswith(first)
                if narrow.any():
                    mask = mask & df["_name_norm"].str.startswith(first)
            rows = df[mask].copy()
            if rows.empty:
                lines.append(f"\n### {pname}: No results found for {year}")
                continue

            actual_name = _fmt_name(str(rows.iloc[0]["player_name"]))
            lines.append(f"\n### {actual_name} — {year}")

            def _fmt_pos(p):
                s = str(p).strip()
                if s in ("CUT", "MC", "WD", "DQ"):
                    return s
                try:
                    n = int(float(s))
                    return f"T{n}" if n > 1 else "WIN"
                except (ValueError, TypeError):
                    return s

            def _parse_tp(v):
                s = str(v).strip().upper()
                if s in ("E", "EVEN"):
                    return 0
                try:
                    return int(float(s))
                except (ValueError, TypeError):
                    return None

            def _ps_key(p):
                s = str(p).strip()
                if s in ("CUT", "MC", "WD", "DQ"):
                    return 999
                s = s.lstrip("Tt")
                try:
                    return int(float(s))
                except (ValueError, TypeError):
                    return 999
            rows["_pos_num"] = rows["position"].apply(_ps_key)
            rows = rows.sort_values("_pos_num")

            tbl = ["| Tournament | Pos | Score |", "|------------|-----|-------|"]
            wins = cuts_made = total = 0
            top10s = 0
            for _, r in rows.iterrows():
                pos = _fmt_pos(r.get("position", "?"))
                tname = str(r.get("tournament_name", r.get("tournament_id", "?")))
                tp = _parse_tp(r.get("to_par", ""))
                tp_str = f"{tp:+d}" if tp is not None else "—"
                tbl.append(f"| {tname} | {pos} | {tp_str} |")
                total += 1
                if pos not in ("CUT", "MC", "WD", "DQ"):
                    cuts_made += 1
                    if pos == "WIN":
                        wins += 1
                    try:
                        if int(float(str(r.get("position","999")).strip())) <= 10:
                            top10s += 1
                    except (ValueError, TypeError):
                        pass

            summary = f"{total} starts · {wins} win{'s' if wins != 1 else ''} · {top10s} top-10s · {cuts_made}/{total} cuts made"
            lines.append(f"**Season summary**: {summary}")
            lines.extend(tbl)
        return "\n".join(lines)
    except Exception as e:
        return f"## Player History\nError: {e}"


def _classify_query(query: str) -> dict:
    """Return intent flags from user query."""
    q = query.lower()
    players = _extract_players(q)
    is_h2h = (
        len(players) == 2 and
        any(w in q for w in [" vs ", " versus ", " or ", "compare", "between", "better", "over"])
    )
    is_compare = (
        not is_h2h and
        len(players) >= 2 and (
            len(players) >= 3 or
            any(w in q for w in ["rank", "tier", "which of", "among", "stack", "order",
                                  "prioritize", "best of", "who do i", "who should i"])
        )
    )
    
    _rn_match = re.search(r'\b(?:round\s*|r)([1-4])\b', q)    
    _round_num_detected = int(_rn_match.group(1)) if _rn_match else None 
    
    if not _round_num_detected:
        if any(w in q for w in ['first round', 'opening round']): _round_num_detected = 1
        elif any(w in q for w in ["second round"]):                        _round_num_detected = 2                   
        elif any(w in q for w in ["third round", "moving day"]):           _round_num_detected = 3                   
        elif any(w in q for w in ["final round", "sunday"]):               _round_num_detected = 4
            
            
    
    return {
        "players":           players,
        "is_player":         bool(players) and not is_h2h and not is_compare,
        "is_h2h":            is_h2h,
        "is_compare":        is_compare,
        "is_bet":            any(w in q for w in ["bet", "wager", "odds", "value", "edge", "parlay", "prop", "book", "wager"]) or re.search(r'\bline\b', q) is not None,
        "is_live":           any(w in q for w in ["live", "leaderboard", "leading", "update", "score", "round", "cut", "leader", "current", "standing", "position"]),
        "is_round_recap":    any(w in q for w in [
      "recap", "what happened", "summarize", "round summary", "how did round",                                     
      "how was round", "how was today", "what happened today", "what happened in round",                           
      "who led after", "after round", "movers", "big movers", "who moved",                                         
      "low round", "best round", "scoring today",                                                                  
  ]),                                                                                                              
  "recap_round_num":   _round_num_detected, 
        "is_lineup":         any(w in q for w in ["lineup", "fantasy", "team", "build", "choose", "draft", "who should i pick", "my picks"]) or (any(w in q for w in ["pick", "use", "start"]) and not bool(players)),
        "is_picks_checkin":  any(w in q for w in [
            "how are my picks", "my picks doing", "check my picks", "picks update",
            "how is my team", "my team doing", "pick update", "how are my players",
            "how did my picks", "my lineup doing", "picks check", "picks status",
            "how is aberg doing", "how is åberg doing", "how is schauffele doing",
            "how is bryson doing", "my picks today", "picks today",
        ]),
        "is_weather":        any(w in q for w in ["weather", "wind", "rain", "forecast", "conditions", "temperature", "temp"]),
        "is_course":         any(w in q for w in ["course", "hole", "layout", "yardage", "field", "green", "fairway", "rough", "setup"]),
        "is_value":          any(w in q for w in ["value", "underdog", "long shot", "longshot", "undervalued", "sharp"]),
        "is_field_overview": any(w in q for w in [
            "field overview", "who's in the field", "best plays", "best plays this week",
            "names nobody", "under the radar", "sleeper", "sleepers", "dark horse",
            "contrarian", "who do you like", "who to watch", "who should i watch",
            "best options", "top options", "who stands out", "interesting plays",
            "overview of the field", "field breakdown", "who are the best",
        ]) and not bool(players),
        "is_course_breakdown": any(w in q for w in [
            "wins at", "wins here", "game plan", "what game", "type of player", "fits this course",
            "course breakdown", "what skills", "what does this course", "who fits", "favors",
            "advantage", "suits", "bomber", "accuracy", "iron play", "ball striker",
            "what kind of player", "who should win", "course fit",
        ]) or (any(w in q for w in ["what wins", "who wins"]) and not bool(players)),
        "is_daily_bet": any(w in q for w in [
            "recommend a bet", "best bet today", "bet of the day", "what should i bet",
            "daily bet", "give me a bet", "top bet", "best bet for today",
            "what to bet", "betting recommendation", "bet recommendation",
            "recommended bet", "what bet", "bet today", "should i bet",
        ]),
        "is_scoring_prop": any(w in q for w in [                                                                        
      "birdie", "birdies", "eagle", "eagles", "bogey-free", "bogey free",                                       
      "no bogey", "clean round", "fewest bogey", "fewest mistakes",                                               
      "scoring prop", "most birdies", "birdie leader", "who scored",                                              
      "scoring leader", "scoring stat", "best scorer",                                                            
  ]),
        "is_tournament_results": any(w in q for w in [
      "how did we do", "bet results", "how did bets", "our roi", "our pnl",
      "how did i do", "results this week", "tournament results", "how were bets",
      "what was our roi", "betting results",
  ]),
        "is_season_performance": any(w in q for w in [
            "how's the model done", "how has the model done", "model performance",
            "season performance", "how accurate", "model accuracy", "calibration",
            "how good is the model", "is the model good", "model results",
            "season results", "season record", "season roi", "season bets",
            "how are bets doing", "bets this season", "overall roi", "overall results",
            "how have we done", "how have bets done", "model done this season",
            "season so far", "results so far", "how is the model",
        ]),

        "is_pick_reason": bool(players) and any(w in q for w in [
            "why pick", "why should i pick", "make the case", "case for",
            "should i pick", "worth picking", "good pick", "strong pick",
            "explain the pick", "why is", "why him", "why them",
            "tell me about", "break down", "breakdown", "analysis of",
            "what do you think about", "thoughts on", "take on",
            "worth using", "worth starting", "start or sit",
        ]),
        "is_strategy": any(w in q for w in [
            "when to use", "best time to use", "when should i use", "when is the best",
            "save for", "save him for", "save them for", "which event to use",
            "which week to use", "best event for", "best tournament for",
            "uses left", "uses remaining", "still have uses", "usage strategy",
            "season strategy", "when do i use", "when to play",
            "waste a use", "spend a use", "burn a use",
        ]) or bool(re.search(r'\bsave\b.{1,25}\bfor\b', q)),
        "is_historical": _is_historical_query(q),
        "historical_year": _extract_year(q),
        "historical_event": _extract_event_from_query(q),
        # Market-specific intent — which market is the user asking about?
        "market_focus": (
            "make_cut"      if any(w in q for w in ["make cut", "make the cut", "cut line", "survive the cut", "weekend"]) else
            "outright"      if any(w in q for w in ["win outright", "to win", "winner", "champion", "outright"]) else
            "top5"          if any(w in q for w in ["top 5", "top five", "top-5", "t5"]) else
            "top10"         if any(w in q for w in ["top 10", "top ten", "top-10", "t10"]) else
            "top20"         if any(w in q for w in ["top 20", "top twenty", "top-20", "t20"]) else
            "h2h"           if any(w in q for w in ["matchup", "head to head", "head-to-head", "h2h", "versus", " vs "]) else
            "h2h_r1"        if any(w in q for w in ["first round matchup", "r1 matchup", "round 1 matchup", "first round leader"]) else
            "wire_to_wire"  if any(w in q for w in ["wire to wire", "wire-to-wire", "lead wire", "lead all four"]) else
            "group_winner"  if any(w in q for w in ["group", "3-ball", "3ball", "threeball"]) else
            None
        ),
        "is_intel": any(w in q for w in [
            "intel", "facts", "tournament facts", "tournament intel",
            "key facts", "historical facts", "stat cards", "stats about",
            "generate intel", "give me intel", "tell me about this tournament",
            "tell me about the course", "what should i know", "what do i need to know",
            "tournament history", "course history", "course stats", "augusta history",
            "masters history", "who has won", "winners at", "recent winners",
            "what are the trends", "trends at", "patterns at",
        ]),
    }


# ---------------------------------------------------------------------------
# Context blocks
# ---------------------------------------------------------------------------

# Cache web news per session so we don't hammer DDG on every follow-up
_web_news_cache: dict[str, str] = {}


def _fetch_player_news(player_names: list[str], tournament_name: str = "") -> str:
    """
    Search DuckDuckGo for recent news on the queried players + tournament.
    Returns a compact block of top snippets (max ~400 words total).
    Cached per player+tournament key for the session.
    """
    if not player_names:
        return ""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return ""

    tourn_label = tournament_name or "PGA Tour 2026"
    lines = ["## RECENT NEWS (web)"]
    found_any = False

    for pname in player_names[:3]:  # cap at 3 players to stay concise
        cache_key = f"{pname.lower()}_{tourn_label.lower()[:20]}"
        if cache_key in _web_news_cache:
            lines.append(_web_news_cache[cache_key])
            found_any = True
            continue

        # Two targeted queries: tournament context + injury/form status
        queries = [
            f"{pname} {tourn_label} 2026",
            f"{pname} injury withdraw form 2026",
        ]
        seen_titles: set[str] = set()
        snippets = []
        for query in queries:
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=4, timelimit="m"))
                if not results:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(query, max_results=4))
                for r in results:
                    body = r.get("body", "").strip()
                    title = r.get("title", "").strip()
                    if not body or len(body) < 30 or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    snippet = body[:220].rstrip() + ("..." if len(body) > 220 else "")
                    snippets.append(f"- **{title[:80]}**: {snippet}")
                    if len(snippets) >= 4:
                        break
            except Exception:
                pass
            if len(snippets) >= 4:
                break

        if snippets:
            block = f"\n### {pname}\n" + "\n".join(snippets)
            _web_news_cache[cache_key] = block
            lines.append(block)
            found_any = True

    if not found_any:
        return ""
    lines.append("\nNOTE: Web news is live — use it for injuries, withdrawals, and current storylines. For numerical stats, use the model data above.")
    return "\n".join(lines)


def _fetch_tournament_news(tournament_name: str) -> str:
    """
    Search DuckDuckGo for current tournament-wide news: conditions, WDs, storylines, preview.
    Cached per tournament name for the session.
    """
    if not tournament_name:
        return ""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return ""

    cache_key = f"tourn_{tournament_name.lower()[:30]}"
    if cache_key in _web_news_cache:
        return _web_news_cache[cache_key]

    queries = [
        f"{tournament_name} 2026 news withdrawal conditions",
        f"{tournament_name} 2026 preview favorites",
    ]
    seen_titles: set[str] = set()
    snippets = []
    for query in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4, timelimit="m"))
            if not results:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=4))
            for r in results:
                title = r.get("title", "").strip()
                body = r.get("body", "").strip()
                if not body or len(body) < 30 or title in seen_titles:
                    continue
                seen_titles.add(title)
                snippet = body[:220].rstrip() + ("..." if len(body) > 220 else "")
                snippets.append(f"- **{title[:80]}**: {snippet}")
                if len(snippets) >= 4:
                    break
        except Exception:
            pass
        if len(snippets) >= 4:
            break

    if not snippets:
        return ""

    result = "## TOURNAMENT NEWS (web)\n" + "\n".join(snippets)
    result += "\nNOTE: Web news is live — use it for current storylines, WDs, and conditions. For model/stats data use the blocks above."
    _web_news_cache[cache_key] = result
    return result


def _fanduel_markets_block(tid: str | None, player_names: list[str] | None = None) -> str:
    """
    Load pga_market_odds_{tid}.csv and return all FanDuel market context.
    Markets: To Win, Matchup (18-hole R1, 72-hole), Finish (Top5/10/20),
             Group, Player Props (1st Round Leader, Make Cut, Top Senior),
             3-Ball, Nationality, Tournament Props.

    If player_names provided: show player-specific lines across all markets.
    Always: show market catalog so the LLM knows what's available to discuss.
    """
    if not tid:
        return ""
    path = DATA / "odds" / f"pga_market_odds_{tid}.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
    except Exception:
        return ""
    if df.empty:
        return ""

    sections: list[str] = ["## FANDUEL MARKETS (via PGA Tour)"]
    fetched = df["fetched_at"].iloc[0] if "fetched_at" in df.columns else ""
    if fetched:
        sections.append(f"*Data as of: {str(fetched)[:16]}*\n")

    def _name_key(n: str) -> str:
        return str(n).strip().lower()

    def _matches_player(row_name: str, targets: list[str]) -> bool:
        rk = _name_key(row_name)
        for t in targets:
            tk = _name_key(t)
            if tk in rk or rk in tk:
                return True
            rl = rk.split()[-1] if rk.split() else ""
            tl = tk.split()[-1] if tk.split() else ""
            if rl and tl and rl == tl:
                return True
        return False

    def _fmt_dir(d) -> str:
        return {"UP": "▲", "DOWN": "▼", "CONSTANT": "→"}.get(str(d).upper(), "")

    def _fmt_american(v) -> str:
        try:
            n = int(float(v))
            return f"+{n}" if n > 0 else str(n)
        except (ValueError, TypeError):
            return str(v)

    def _player_rows(market_type: str) -> "pd.DataFrame":
        sub = df[df["market_type"] == market_type].copy()
        if sub.empty or not player_names:
            return sub.iloc[0:0]
        return sub[sub["player_name"].apply(lambda n: _matches_player(n, player_names))]

    # ── To Win ───────────────────────────────────────────────────────────────
    prows = _player_rows("ODDS_TO_WIN")
    if not prows.empty:
        sections.append("### To Win")
        for _, r in prows.sort_values("odds_numeric").iterrows():
            imp = float(r.get("implied_prob", 0)) * 100
            sections.append(
                f"- **{r['player_name']}**: {_fmt_american(r['odds_numeric'])} "
                f"({imp:.1f}% implied) {_fmt_dir(r.get('odd_direction',''))}"
            )
        sections.append("")

    # ── Finish (Top 5 / Top 10 / Top 20) ─────────────────────────────────────
    # Prefer "Incl. Ties" lines; deduplicate so each tier shows once per player
    finish_all = df[df["market_type"] == "FINISH"].copy()
    if not finish_all.empty and player_names:
        prows = finish_all[finish_all["player_name"].apply(lambda n: _matches_player(n, player_names))]
        if not prows.empty:
            # Keep "Incl. Ties" over bare tier name for same player/tier
            def _tier(s: str) -> str:
                s = s.lower()
                if "20" in s: return "Top 20"
                if "10" in s: return "Top 10"
                if "5"  in s: return "Top 5"
                return s
            prows = prows.copy()
            prows["_tier"] = prows["submarket_name"].apply(_tier)
            prows["_pref"] = prows["submarket_name"].str.contains("Incl", case=False, na=False).astype(int)
            prows = prows.sort_values("_pref", ascending=False).drop_duplicates(["player_name", "_tier"])
            sections.append("### Finish Props")
            for _, r in prows.sort_values(["player_name", "_tier"]).iterrows():
                sections.append(
                    f"- **{r['player_name']}** {r['_tier']}: "
                    f"{_fmt_american(r['odds_numeric'])} {_fmt_dir(r.get('odd_direction',''))}"
                )
            sections.append("")

    # ── Player Props (1st Round Leader, Make Cut, Top Senior) ────────────────
    prows = _player_rows("PLAYER_PROPS")
    if not prows.empty:
        sections.append("### Player Props")
        for _, r in prows.sort_values(["player_name", "submarket_name"]).iterrows():
            sections.append(
                f"- **{r['player_name']}** — {r.get('submarket_name','')}: "
                f"{_fmt_american(r['odds_numeric'])} {_fmt_dir(r.get('odd_direction',''))}"
            )
        sections.append("")

    # ── Matchups: 18-hole (Round 1) and 72-hole ───────────────────────────────
    matchups = df[df["market_type"] == "MATCHUP_PROPS"].copy()
    if not matchups.empty and player_names:
        mask = matchups["player_name"].apply(lambda n: _matches_player(n, player_names))
        if "opponent_name" in matchups.columns:
            mask = mask | matchups["opponent_name"].fillna("").apply(
                lambda n: _matches_player(n, player_names)
            )
        prows = matchups[mask]
        if not prows.empty:
            seen: set[str] = set()
            by_sub: dict[str, list[str]] = {}
            for gid, grp in prows.groupby("bet_group_id"):
                if str(gid) in seen:
                    continue
                seen.add(str(gid))
                sub = str(grp.iloc[0].get("submarket_name", "")).strip()
                by_sub.setdefault(sub, [])
                pair = []
                for _, r in grp.iterrows():
                    pair.append(
                        f"  {r['player_name']}: {_fmt_american(r['odds_numeric'])} "
                        f"{_fmt_dir(r.get('odd_direction',''))}"
                    )
                by_sub[sub].extend(pair + [""])
            for sub, lines in sorted(by_sub.items()):
                sections.append(f"### Matchup — {sub}")
                sections.extend(lines[:30])

    # ── 3-Ball (Round 1) ─────────────────────────────────────────────────────
    threeball = df[df["market_type"] == "THREE_BALL"].copy()
    if not threeball.empty and player_names:
        mask = threeball["player_name"].apply(lambda n: _matches_player(n, player_names))
        prows = threeball[mask]
        if not prows.empty:
            seen: set[str] = set()
            sections.append("### 3-Ball (Round 1)")
            for gid, grp in prows.groupby("bet_group_id"):
                if str(gid) in seen:
                    continue
                # Find full group including non-matching players
                full_grp = threeball[threeball["bet_group_id"] == gid]
                seen.add(str(gid))
                for _, r in full_grp.sort_values("odds_numeric").iterrows():
                    sections.append(
                        f"  {r['player_name']}: {_fmt_american(r['odds_numeric'])} "
                        f"{_fmt_dir(r.get('odd_direction',''))}"
                    )
                sections.append("")

    # ── Group Props ───────────────────────────────────────────────────────────
    groups = df[df["market_type"] == "GROUP"].copy()
    if not groups.empty and player_names:
        prows = groups[groups["player_name"].apply(lambda n: _matches_player(n, player_names))]
        if not prows.empty:
            sections.append("### Group Props")
            for _, r in prows.sort_values("odds_numeric").iterrows():
                sections.append(
                    f"- **{r['player_name']}**: {_fmt_american(r['odds_numeric'])} "
                    f"{_fmt_dir(r.get('odd_direction',''))}"
                )
            sections.append("")

    # ── Nationality ───────────────────────────────────────────────────────────
    nationality = df[df["market_type"] == "NATIONALITY"].copy()
    if not nationality.empty and player_names:
        prows = nationality[nationality["player_name"].apply(lambda n: _matches_player(n, player_names))]
        if not prows.empty:
            sections.append("### Nationality Props")
            for _, r in prows.sort_values(["submarket_name", "odds_numeric"]).iterrows():
                sections.append(
                    f"- **{r['player_name']}** ({r.get('submarket_name','')}): "
                    f"{_fmt_american(r['odds_numeric'])} {_fmt_dir(r.get('odd_direction',''))}"
                )
            sections.append("")

    # ── Tournament Props (Wire-to-Wire, etc.) ────────────────────────────────
    tprops = df[df["market_type"] == "TOURNAMENT_PROPS"].copy()
    if not tprops.empty and player_names:
        prows = tprops[tprops["player_name"].apply(lambda n: _matches_player(n, player_names))]
        if not prows.empty:
            sections.append("### Tournament Props")
            for _, r in prows.sort_values("odds_numeric").iterrows():
                sections.append(
                    f"- **{r['player_name']}** {r.get('submarket_name','')}: "
                    f"{_fmt_american(r['odds_numeric'])} {_fmt_dir(r.get('odd_direction',''))}"
                )
            sections.append("")

    # ── Market catalog (always shown so LLM knows what's askable) ─────────────
    mkt_summary = (
        df.groupby(["market_type", "submarket_name"])
        .size()
        .reset_index(name="n")
    )
    catalog_lines = []
    for mt, grp in mkt_summary.groupby("market_type"):
        subs = ", ".join(grp["submarket_name"].tolist())
        catalog_lines.append(f"  {mt}: {subs}")
    sections.append("### Available FanDuel Markets")
    sections.extend(catalog_lines)

    if len(sections) <= 2:
        return ""
    return "\n".join(sections)


def _multi_book_odds_block(tid: str | None, player_names: list[str] | None = None, top_n: int = 15) -> str:
    """
    Load multi-book odds and return a comparison block.
    Auto-selects the 2 books with the most data (prefers DK + FanDuel, falls back to BetMGM/BetRivers).
    If player_names given, shows those players first then fills to top_n.
    """
    # Prefer dedicated FanDuel file for this event, fall back to multi-book CSV
    fd_path = None
    if tid:
        _fd_candidate = DATA / "odds" / f"fanduel_odds_{tid}.csv"
        if _fd_candidate.exists():
            fd_path = _fd_candidate

    mb_path = DATA / "odds" / "multi_book_odds_latest.csv"
    if not mb_path.exists() and not fd_path:
        return ""
    try:
        df = pd.read_csv(mb_path) if mb_path.exists() else pd.DataFrame()

        # Sort by consensus implied prob
        if "implied_prob_consensus" in df.columns:
            df = df.sort_values("implied_prob_consensus", ascending=False)
        elif "odds_consensus" in df.columns:
            df = df.sort_values("odds_consensus", ascending=True)

        # Discover which book columns have actual data (>10 rows filled)
        BOOK_COLS = {
            "odds_draftkings": "DK",
            "odds_fanduel":    "FanDuel",
            "odds_betmgm":     "BetMGM",
            "odds_betrivers":  "BetRivers",
            "odds_betonlineag":"BetOnline",
            "odds_caesars":    "Caesars",
            "odds_bovada":     "Bovada",
        }
        available = {col: label for col, label in BOOK_COLS.items()
                     if col in df.columns and df[col].notna().sum() > 10}

        # Merge FanDuel dedicated file if it exists (higher priority than multi-book for FD)
        if fd_path and fd_path.exists():
            try:
                _fdf = pd.read_csv(fd_path)
                _fdf = _fdf[_fdf["sportsbook"].str.upper() == "FANDUEL"] if "sportsbook" in _fdf.columns else _fdf
                if "fanduel_odds" in _fdf.columns and "player_name" in _fdf.columns:
                    _fd_map = dict(zip(_fdf["player_name"].str.lower(), _fdf["fanduel_odds"]))
                    if not df.empty:
                        df["odds_fanduel"] = df["player_name"].str.lower().map(_fd_map).combine_first(df.get("odds_fanduel", pd.Series(dtype=float)))
                    available["odds_fanduel"] = "FanDuel"
            except Exception:
                pass

        if not available or df.empty:
            return ""

        # Pick best 2 books: DK first, then FD, then next best
        _preferred = ["odds_draftkings", "odds_fanduel", "odds_betmgm", "odds_betrivers", "odds_betonlineag"]
        selected_cols = [c for c in _preferred if c in available][:2]
        if not selected_cols:
            selected_cols = list(available.keys())[:2]

        # Prioritise requested players, then fill
        if player_names:
            p_lower = [p.lower() for p in player_names]
            mask_prio = df["player_name"].str.lower().apply(
                lambda n: any(pl.split()[-1] in n for pl in p_lower)
            )
            prio_df = df[mask_prio]
            rest_df = df[~mask_prio].head(max(0, top_n - len(prio_df)))
            df_show = pd.concat([prio_df, rest_df]).head(top_n)
        else:
            df_show = df.head(top_n)

        rows = []
        for _, r in df_show.iterrows():
            pname = str(r["player_name"])
            imp = r.get("implied_prob_consensus")
            imp_str = f"{float(imp)*100:.1f}%" if pd.notna(imp) else "—"
            row = {"Player": pname}
            odds_vals = {}
            for col in selected_cols:
                lbl = available[col]
                val = r.get(col)
                row[lbl] = _fmt_odds(val) if pd.notna(val) else "—"
                if pd.notna(val):
                    odds_vals[lbl] = float(val)
            row["Consensus Implied%"] = imp_str
            # Spread between the two selected books
            if len(odds_vals) == 2:
                imps = [_american_to_implied(v) or 0 for v in odds_vals.values()]
                spread = abs(imps[0] - imps[1]) * 100
                row["Book Spread"] = f"{spread:.1f}pp" if spread > 0.5 else "<1pp"
            rows.append(row)

        out_df = pd.DataFrame(rows)
        book_labels = [available[c] for c in selected_cols if c in available]
        note = f"Comparing {' vs '.join(book_labels)}. Book Spread = difference in implied win% — large spread = line shop opportunity."
        return f"## MULTI-BOOK ODDS ({' vs '.join(book_labels)})\n{note}\n" + out_df.to_markdown(index=False)
    except Exception as e:
        return f"## MULTI-BOOK ODDS\n(unavailable: {e})"


def _top_markets_summary_block(tid: str | None, preds_df: "pd.DataFrame | None" = None, top_n: int = 8) -> str:
    """
    Compact cross-market value summary for general bet/lineup questions.
    Shows top value opportunities across all FanDuel markets + DK outright.
    Designed for when no specific player is asked about.
    """
    if not tid:
        return ""
    fd_path = DATA / "odds" / f"pga_market_odds_{tid}.csv"
    recs_path = DATA / "odds" / "recommended_bets_latest.csv"
    if not fd_path.exists() and not recs_path.exists():
        return ""

    lines: list[str] = ["## BETTING MARKET SUMMARY"]

    # ── Top value bets from recommend_bets output ─────────────────────────────
    if recs_path.exists():
        try:
            recs = pd.read_csv(recs_path)
            # Filter to this tournament
            if "tournament_id" in recs.columns:
                recs = recs[recs["tournament_id"].str.upper() == tid.upper()]
            if not recs.empty:
                for col in ["edge_pts", "model_prob", "book_prob", "odds_american"]:
                    if col in recs.columns:
                        recs[col] = pd.to_numeric(recs[col], errors="coerce")
                # Top value bets by edge, skip content_card
                good = recs[
                    (recs["market"].astype(str) != "content_card") &
                    (recs["edge_pts"].fillna(0) >= 2.0)
                ].sort_values("edge_pts", ascending=False).head(top_n)

                if not good.empty:
                    lines.append(f"\n### Top Value Bets (edge ≥ 2pp, model vs no-vig market)")
                    lines.append("| Player | Market | Book | Odds | Model% | Market% | Edge |")
                    lines.append("|--------|--------|------|------|--------|---------|------|")
                    for _, r in good.iterrows():
                        pname = str(r.get("player_name", "—"))
                        mkt = str(r.get("market", "")).replace("_", " ").title()
                        book = str(r.get("book", "")).upper()
                        book_short = "DK" if "DRAFT" in book else ("FD" if "FANDUEL" in book else book[:3])
                        odds_v = int(r["odds_american"]) if pd.notna(r.get("odds_american")) else 0
                        odds_s = f"+{odds_v}" if odds_v > 0 else str(odds_v)
                        mp = float(r["model_prob"]) * 100 if pd.notna(r.get("model_prob")) else 0
                        bp = float(r["book_prob"]) * 100 if pd.notna(r.get("book_prob")) else 0
                        ep = float(r["edge_pts"]) if pd.notna(r.get("edge_pts")) else 0
                        lines.append(f"| {pname} | {mkt} | {book_short} | {odds_s} | {mp:.1f}% | {bp:.1f}% | **+{ep:.1f}pp** |")
                    lines.append("")
        except Exception:
            pass

    # ── FanDuel market snapshot ───────────────────────────────────────────────
    if fd_path.exists():
        try:
            fd = pd.read_csv(fd_path)
            if not fd.empty:
                # Make Cut market — show top-value (lowest odds = most likely makes = value on favourites)
                mc = fd[(fd["market_type"] == "PLAYER_PROPS") &
                        (fd["submarket_name"].str.contains("Make The Cut", case=False, na=False))].copy()
                if not mc.empty:
                    mc["odds_numeric"] = pd.to_numeric(mc["odds_numeric"], errors="coerce")
                    mc = mc.dropna(subset=["odds_numeric"]).sort_values("odds_numeric")
                    lines.append("### Make The Cut — FanDuel Prices (cheapest 8 favourites)")
                    for _, r in mc.head(8).iterrows():
                        o = int(r["odds_numeric"])
                        imp = float(r.get("implied_prob", 0)) * 100
                        lines.append(f"- {r['player_name']}: {'+'+ str(o) if o>0 else o} ({imp:.0f}% implied)")
                    lines.append("")

                # 1st Round Leader — top 6 by implied prob
                r1 = fd[(fd["market_type"] == "PLAYER_PROPS") &
                        (fd["submarket_name"].str.contains("1st Round", case=False, na=False))].copy()
                if not r1.empty:
                    r1["implied_prob"] = pd.to_numeric(r1["implied_prob"], errors="coerce")
                    r1 = r1.dropna(subset=["implied_prob"]).sort_values("implied_prob", ascending=False)
                    lines.append("### 1st Round Leader — FanDuel (top 6 by implied prob)")
                    for _, r in r1.head(6).iterrows():
                        o = int(r.get("odds_numeric", 0))
                        imp = float(r.get("implied_prob", 0)) * 100
                        lines.append(f"- {r['player_name']}: {'+'+ str(o) if o>0 else o} ({imp:.0f}%)")
                    lines.append("")

                # Wire-to-Wire — top 5
                w2w = fd[(fd["market_type"] == "TOURNAMENT_PROPS") &
                         (fd["submarket_name"].str.contains("Wire", case=False, na=False))].copy()
                if not w2w.empty:
                    w2w["implied_prob"] = pd.to_numeric(w2w["implied_prob"], errors="coerce")
                    w2w = w2w.dropna(subset=["implied_prob"]).sort_values("implied_prob", ascending=False)
                    lines.append("### Wire-to-Wire Winner — FanDuel (top 5)")
                    for _, r in w2w.head(5).iterrows():
                        o = int(r.get("odds_numeric", 0))
                        imp = float(r.get("implied_prob", 0)) * 100
                        lines.append(f"- {r['player_name']}: {'+'+ str(o) if o>0 else o} ({imp:.0f}%)")
                    lines.append("")

                # Odds direction movers — who's being bet INTO this week
                movers = fd[(fd["market_type"] == "ODDS_TO_WIN") &
                            (fd["odd_direction"].str.upper() == "UP")].copy() if "odd_direction" in fd.columns else pd.DataFrame()
                if not movers.empty:
                    movers["implied_prob"] = pd.to_numeric(movers["implied_prob"], errors="coerce")
                    movers = movers.sort_values("implied_prob", ascending=False)
                    mover_names = ", ".join(movers["player_name"].head(6).tolist())
                    lines.append(f"### Shortening Odds (being bet): {mover_names}")
                    lines.append("")
        except Exception:
            pass

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def _augusta_pick_block(tid: str, market: str = "top10") -> str:
    """
    Augusta-specific composite scorer for qualified players (5+/8 criteria).
    Called when market edge tables show no positive edge on historically viable players.
    Ranks by: Augusta avg to_par (30%), SG T2G form (25%), cut rate (20%),
              driving distance rank (15%), model probability (10%).
    Returns a markdown block with the best available pick and reasoning.
    """
    qual_path = DATA / "qualitative" / f"masters_qualifiers_{tid}.csv"
    if not qual_path.exists():
        return ""

    def _nk(n: str) -> str:
        s = str(n).strip().lower()
        if ", " in s:
            p = s.split(", ", 1)
            return f"{p[1]} {p[0]}"
        return s

    def _fmt(raw: str) -> str:
        s = str(raw).strip()
        if ", " in s:
            parts = s.split(", ", 1)
            return f"{parts[1]} {parts[0]}"
        return s

    try:
        qdf = pd.read_csv(qual_path)
        qdf = qdf[qdf["qualifier_score"] >= 5].copy()
        if qdf.empty:
            return ""

        # Merge model top-10 probability from latest predictions
        preds_path = OUTPUTS / "latest_predictions.csv"
        if preds_path.exists():
            preds = pd.read_csv(preds_path)
            prob_col = (
                f"{market}_prob_calibrated" if f"{market}_prob_calibrated" in preds.columns
                else "top10_prob_calibrated" if "top10_prob_calibrated" in preds.columns
                else "top10_prob" if "top10_prob" in preds.columns
                else None
            )
            if prob_col:
                preds["_key"] = preds["player_name"].apply(_nk)
                qdf["_key"] = qdf["player_name"].apply(_nk)
                prob_map = dict(zip(preds["_key"], pd.to_numeric(preds[prob_col], errors="coerce")))
                qdf["model_prob"] = qdf["_key"].map(prob_map)
            else:
                qdf["model_prob"] = float("nan")
        else:
            qdf["model_prob"] = float("nan")

        def _minmax(s: pd.Series) -> pd.Series:
            mn, mx = s.min(), s.max()
            if mx == mn:
                return pd.Series([0.5] * len(s), index=s.index)
            return (s - mn) / (mx - mn)

        # Component scores (all 0–1, higher = better)
        qdf["augusta_avg_to_par"] = pd.to_numeric(qdf["augusta_avg_to_par"], errors="coerce").fillna(0)
        qdf["sg_t2g_last4_total"] = pd.to_numeric(qdf["sg_t2g_last4_total"], errors="coerce").fillna(0)
        qdf["augusta_starts"]     = pd.to_numeric(qdf["augusta_starts"], errors="coerce").fillna(1).clip(lower=1)
        qdf["augusta_cuts_made"]  = pd.to_numeric(qdf["augusta_cuts_made"], errors="coerce").fillna(0)
        qdf["driving_dist_field_rank"] = pd.to_numeric(qdf["driving_dist_field_rank"], errors="coerce").fillna(88)

        qdf["_s_aug"]     = _minmax(-qdf["augusta_avg_to_par"])           # lower avg = better
        qdf["_s_form"]    = _minmax(qdf["sg_t2g_last4_total"])
        qdf["_s_consist"] = _minmax(qdf["augusta_cuts_made"] / qdf["augusta_starts"])
        qdf["_s_dist"]    = _minmax(-qdf["driving_dist_field_rank"])      # lower rank = better
        qdf["_s_prob"]    = _minmax(pd.to_numeric(qdf.get("model_prob", 0), errors="coerce").fillna(0))

        qdf["_composite"] = (
            0.30 * qdf["_s_aug"] +
            0.25 * qdf["_s_form"] +
            0.20 * qdf["_s_consist"] +
            0.15 * qdf["_s_dist"] +
            0.10 * qdf["_s_prob"]
        )
        qdf = qdf.sort_values("_composite", ascending=False)

        lines = ["", "### Augusta Composite Ranking — Best Available Pick"]
        lines.append("_(No market edge on qualified players. Ranking by Augusta history + current form.)_")
        lines.append("")
        lines.append("| # | Player | Qual | Augusta Avg | SG T2G (L4) | Cut Rate | Dist Rank | Score |")
        lines.append("|---|--------|------|-------------|-------------|----------|-----------|-------|")

        for i, (_, r) in enumerate(qdf.head(6).iterrows(), 1):
            pn    = _fmt(str(r["player_name"]))
            qs    = int(r["qualifier_score"])
            avg   = r["augusta_avg_to_par"]
            avg_s = f"{avg:+.2f}" if pd.notna(avg) else "N/A"
            t2g   = r["sg_t2g_last4_total"]
            t2g_s = f"{float(t2g):+.2f}" if pd.notna(t2g) else "N/A"
            cuts  = int(r["augusta_cuts_made"])
            starts = int(r["augusta_starts"])
            dist  = int(r["driving_dist_field_rank"])
            comp  = float(r["_composite"])
            lines.append(f"| {i} | {pn} | {qs}/8 | {avg_s} | {t2g_s} | {cuts}/{starts} | T{dist} | {comp:.3f} |")

        # Top pick narrative
        top       = qdf.iloc[0]
        top_name  = _fmt(str(top["player_name"]))
        top_qs    = int(top["qualifier_score"])
        top_aug   = top["augusta_avg_to_par"]
        top_t2g   = top["sg_t2g_last4_total"]
        top_cuts  = int(top["augusta_cuts_made"])
        top_starts = int(top["augusta_starts"])
        top_dist  = int(top["driving_dist_field_rank"])

        lines.append("")
        lines.append(f"**BEST POSITIONED: {top_name} ({top_qs}/8 qualifiers)**")
        reasons = []
        if pd.notna(top_aug) and top_aug < 0:
            reasons.append(f"Augusta avg {top_aug:+.2f} to par")
        if pd.notna(top_t2g) and float(top_t2g) >= 15:
            reasons.append(f"SG T2G last 4 starts: {float(top_t2g):+.2f} shots")
        if top_starts > 0:
            reasons.append(f"{top_cuts}/{top_starts} cuts made at Augusta")
        if top_dist <= 50:
            reasons.append(f"driving distance T{top_dist} in field (length at Augusta matters)")
        if reasons:
            lines.append(" | ".join(reasons))
        lines.append("")
        lines.append("_Caveat: No market edge found — book prices this player above model. This is a best-available pick by Augusta criteria, not a value bet. Bet size should be reduced accordingly._")

        return "\n".join(lines)

    except Exception:
        return ""


def _market_deep_block(market: str, tid: str | None, top_n: int = 6) -> str:
    """
    Deep context block for a specific betting market.
    Shows top recs for that market with full reasoning + model context.
    Called when user asks about a specific market (make_cut, h2h, outright, etc.)
    """
    if not tid:
        return ""

    recs_path = DATA / "odds" / "recommended_bets_latest.csv"
    if not recs_path.exists():
        return ""

    _market_labels = {
        "make_cut":     "Make The Cut",
        "outright":     "Outright Winner",
        "top5":         "Top 5 Finish",
        "top10":        "Top 10 Finish",
        "top20":        "Top 20 Finish",
        "h2h":          "Head-to-Head Matchup",
        "h2h_r1":       "1st Round H2H Matchup",
        "wire_to_wire": "Wire-to-Wire Winner",
        "group_winner": "Group / 3-Ball Winner",
    }
    _market_logic = {
        "make_cut":     "Model uses SG:APP + SG:ARG as primary drivers (Augusta rewards approach accuracy). Players with >= 0.5 SG combined in iron play and scrambling score highest. Edge is real when model shows ≥ 5pp gap vs FanDuel no-vig implied.",
        "outright":     "Model blends gradient boost (75%) + market consensus (25%). Top features: world_rank_log, predictive_sg_weighted (DataGolf weights OTT=1.2, APP=1.0), course SG fit, form_trend. Win prob capped at 20%.",
        "top5":         "Same model as outright but with calibrated top-5 probability. Higher variance — best edges come from players the market undervalues vs model SG profile.",
        "top10":        "Most stable market for finding edges. Model top-10 prob correlates well with calibration. Look for players with strong APP + ARG SG who the book prices as longshots.",
        "h2h":          "Model compares calibrated finish probability between two players. Edge arises from SG advantage not fully priced into short lines. Fade heavy chalk when model gap is < 5pp.",
        "h2h_r1":       "R1 H2H driven by tee time (morning/afternoon), course setup knowledge, and R1 SG profile. Morning rounds historically favorable at Augusta (softer greens). Form trend is key.",
        "wire_to_wire": "Geometric mean of win_prob × R1 leader probability. High variance — only bet when model shows > 3pp edge AND player is in top 5 win probability. Max 60% blend toward model (40% market shrinkage).",
        "group_winner": "3-ball scoring uses relative SG vs pairing. Check tee times and morning/afternoon splits. Edges are most reliable when model SG rank gap is ≥ 20 positions.",
    }

    # Base rate context per market (helps LLM frame probability)
    _base_rate = {
        "make_cut":     "Masters field ~88 players, ~54 make cut (~44% base rate). Model prob > 60% = meaningfully above base rate.",
        "outright":     "Field ~88. Random win prob = ~1.1%. Model caps at 20%. Anything above 10% is elite.",
        "top10":        "~10/88 players = ~11% base rate. Model prob > 18% = strong edge zone.",
        "top5":         "~5/88 = ~6% base rate. Model prob > 12% = strong edge zone.",
        "h2h":          "50% base rate (coin flip). Model prob > 60% = real edge. > 70% = strong edge.",
        "h2h_r1":       "50% base rate. Morning tee times favor softer greens at Augusta. Form trend matters.",
        "wire_to_wire": "Rare outcome — ~5% historical rate. Only bet with multiple aligned signals.",
        "group_winner": "~33% base rate in 3-balls. Look for SG rank gap ≥ 20 positions vs both opponents.",
    }

    def _fmt_name(raw: str) -> str:
        s = str(raw).strip()
        if ", " in s:
            parts = s.split(", ", 1)
            return f"{parts[1]} {parts[0]}"
        return s

    try:
        recs = pd.read_csv(recs_path)
        if "tournament_id" in recs.columns:
            recs = recs[recs["tournament_id"].astype(str).str.upper() == tid.upper()]
        recs = recs[recs["bet_type"].astype(str) != "content_card"]

        mkt_recs = recs[recs["market"].astype(str).str.lower() == market.lower()].copy()
        for col in ["edge_pts", "model_prob", "book_prob", "confidence", "odds_american"]:
            if col in mkt_recs.columns:
                mkt_recs[col] = pd.to_numeric(mkt_recs[col], errors="coerce")

        label = _market_labels.get(market, market.replace("_", " ").title())
        logic = _market_logic.get(market, "")
        base_rate_note = _base_rate.get(market, "")

        lines = [f"## {label.upper()} — MODEL DEEP DIVE"]
        if base_rate_note:
            lines.append(f"**Base rate**: {base_rate_note}")
        if logic:
            lines.append(f"**Model logic**: {logic}")
        lines.append("")

        if mkt_recs.empty:
            # For Augusta top-10/outright/top5: lead with the Augusta composite pick, edge tables are secondary context
            is_augusta_market = market in ("top10", "top5", "outright", "top20")
            aug_block = _augusta_pick_block(tid, market) if is_augusta_market else ""
            if aug_block:
                lines.append(aug_block)
                lines.append("")
                lines.append("---")
                lines.append("_Edge context (informational — no automated threshold met):_")
                lines.append("")
            else:
                lines.append(f"_No {label} bets meet the automated edge threshold. Best available by model edge (informational):_")
                lines.append("")
            prop_path = DATA / "odds" / f"prop_lines_{tid}.csv"
            if prop_path.exists():
                try:
                    pl = pd.read_csv(prop_path)
                    pl = pl[pl["market"].astype(str).str.lower() == market.lower()].copy()
                    pl["_implied"] = pd.to_numeric(pl["odds"], errors="coerce").apply(
                        lambda o: (100/(o+100) if o > 0 else abs(o)/(abs(o)+100)) if pd.notna(o) else None
                    )

                    def _nk(n: str) -> str:
                        s = str(n).strip().lower()
                        if ", " in s:
                            p = s.split(", ", 1); return f"{p[1]} {p[0]}"
                        return s

                    # Load model probs
                    preds_path = OUTPUTS / "latest_predictions.csv"
                    preds_raw = pd.read_csv(preds_path) if preds_path.exists() else pd.DataFrame()
                    prob_col = (f"{market}_prob" if not preds_raw.empty and f"{market}_prob" in preds_raw.columns
                                else "top10_prob" if not preds_raw.empty and "top10_prob" in preds_raw.columns
                                else None)
                    preds_sub = preds_raw[["player_name", prob_col]].copy() if (not preds_raw.empty and prob_col) else pd.DataFrame()

                    # Load qualifier scores
                    qual_path = DATA / "qualitative" / f"masters_qualifiers_{tid}.csv"
                    qual_map: dict[str, int] = {}
                    if qual_path.exists():
                        try:
                            qdf = pd.read_csv(qual_path)
                            for _, qr in qdf.iterrows():
                                qual_map[_nk(str(qr["player_name"]))] = int(qr.get("qualifier_score", 0))
                        except Exception:
                            pass

                    pl["_key"] = pl["player_name"].apply(_nk)
                    if not preds_sub.empty:
                        preds_sub["_key"] = preds_sub["player_name"].apply(_nk)
                        pl = pl.merge(preds_sub[["_key", prob_col]], on="_key", how="left")
                        pl["_edge"] = (pd.to_numeric(pl[prob_col], errors="coerce") - pl["_implied"]) * 100
                        pl["_qscore"] = pl["_key"].map(qual_map).fillna(0).astype(int)

                        # Split into two tables: qualified (5+) and eliminated
                        qualified = pl[pl["_qscore"] >= 5].sort_values("_edge", ascending=False).head(6)
                        eliminated = pl[pl["_qscore"] < 3].sort_values("_edge", ascending=False).head(5)

                        def _rows(df_sub):
                            for _, r in df_sub.iterrows():
                                pn = _fmt_name(str(r.get("player_name", "—")))
                                o = int(r.get("odds", 0))
                                os = f"+{o}" if o > 0 else str(o)
                                bp = float(r["_implied"]) * 100 if pd.notna(r.get("_implied")) else 0
                                mp = float(r[prob_col]) * 100 if pd.notna(r.get(prob_col)) else 0
                                ep = float(r["_edge"]) if pd.notna(r.get("_edge")) else 0
                                qs = int(r.get("_qscore", 0))
                                lines.append(f"| {pn} | {os} | {bp:.1f}% | {mp:.1f}% | {ep:+.1f}pp | {qs}/8 |")

                        if not qualified.empty:
                            pos_q = qualified[qualified["_edge"] > 0]
                            lines.append("### Historically viable players (5+/8) — sorted by edge")
                            if pos_q.empty:
                                lines.append("_All qualified players have NEGATIVE edge — book prices them above model. The correct play is PASS._")
                            lines.append("| Player | Odds | Book% | Model% | Edge | Qual |")
                            lines.append("|--------|------|-------|--------|------|------|")
                            _rows(qualified)
                            lines.append("")

                        if not eliminated.empty:
                            lines.append("### Positive edges — but on ELIMINATED players (false positives)")
                            lines.append("_These players fail basic Augusta criteria. Model edge is from general SG stats, not Augusta performance._")
                            lines.append("| Player | Odds | Book% | Model% | Edge | Qual |")
                            lines.append("|--------|------|-------|--------|------|------|")
                            _rows(eliminated)
                            lines.append("")

                        lines.append("_CONTEXT FOR LLM: The Augusta Composite Ranking above is the primary recommendation. The qualified player edge table above shows book pricing — all negative means the book is efficient here. The eliminated player edges are false positives. The pick should be the #1 player from the Augusta Composite Ranking._")
                except Exception:
                    pass
            return "\n".join(lines)

        # Sort by edge for value table
        by_edge = mkt_recs.sort_values("edge_pts", ascending=False).head(top_n)
        # Best probability pick (may differ from best edge)
        best_prob_row = mkt_recs.sort_values("model_prob", ascending=False).iloc[0]
        best_prob_name = _fmt_name(best_prob_row.get("player_name", ""))
        best_edge_name = _fmt_name(by_edge.iloc[0].get("player_name", ""))

        if best_prob_name != best_edge_name:
            lines.append(f"**Best value (edge)**: {best_edge_name} | **Highest probability**: {best_prob_name}")
            lines.append("_These differ — value bet has a bigger market disagreement; probability bet has a higher absolute chance._")
            lines.append("")

        lines.append(f"### {label} Value Bets — sorted by edge")
        lines.append("| Player | Odds | Model% | Market% | Edge | Conf | History | Key Driver |")
        lines.append("|--------|------|--------|---------|------|------|---------|------------|")

        for _, r in by_edge.iterrows():
            pname = _fmt_name(r.get("player_name", "—"))
            odds_v = int(r["odds_american"]) if pd.notna(r.get("odds_american")) else 0
            odds_s = f"+{odds_v}" if odds_v > 0 else str(odds_v)
            mp = float(r["model_prob"]) * 100 if pd.notna(r.get("model_prob")) else 0
            bp = float(r["book_prob"]) * 100 if pd.notna(r.get("book_prob")) else 0
            ep = float(r["edge_pts"]) if pd.notna(r.get("edge_pts")) else 0
            conf = float(r["confidence"]) if pd.notna(r.get("confidence")) else 0
            conf_s = f"{conf*100:.0f}%"
            # Extract history flag from reasoning
            reasoning = str(r.get("reasoning", ""))
            has_hist = "✓" if "course history" not in reasoning.lower() or "no course" not in reasoning.lower() else "—"
            has_hist = "—" if "No course history" in reasoning else "✓"
            # Key driver: first SG bullet
            key_driver = "—"
            for part in reasoning.split(" | "):
                if "SG" in part and "#" in part:
                    key_driver = part.strip()[:40]
                    break
            lines.append(f"| {pname} | {odds_s} | {mp:.1f}% | {bp:.1f}% | **+{ep:.1f}pp** | {conf_s} | {has_hist} | {key_driver} |")

        lines.append("")
        lines.append("_History ✓ = has Augusta rounds in model. — = model extrapolating from SG profile only (lower confidence)._")
        lines.append("")

        # Full reasoning for top-edge pick
        top = by_edge.iloc[0]
        top_name = _fmt_name(top.get("player_name", ""))
        top_reasoning = str(top.get("reasoning", "")).strip()
        if top_reasoning and top_reasoning.lower() not in ("nan", "none", ""):
            lines.append(f"**Full reasoning — {top_name} (best edge):**")
            for part in top_reasoning.split(" | "):
                lines.append(f"- {part.strip()}")
            lines.append("")

        # Full reasoning for best-prob pick if different
        if best_prob_name != best_edge_name:
            bp_reasoning = str(best_prob_row.get("reasoning", "")).strip()
            if bp_reasoning and bp_reasoning.lower() not in ("nan", "none", ""):
                lines.append(f"**Full reasoning — {best_prob_name} (highest probability):**")
                for part in bp_reasoning.split(" | "):
                    lines.append(f"- {part.strip()}")
                lines.append("")

        return "\n".join(lines)

    except Exception:
        return ""





def _masters_qualifiers_block(tid: str | None) -> str:
    """
    Shows each player's score against the 10 historical Masters elimination
    criteria (from PGA Tour 'From 91 to One' framework).
    """
    if not tid:
        return ""

    path = DATA / "qualitative" / f"masters_qualifiers_{tid}.csv"
    if not path.exists():
        return ""

    try:
        df = pd.read_csv(path)

        lines = ["## MASTERS QUALIFIER SCORES (historical elimination criteria)"]
        lines.append("_8 criteria: prior start, top-30, cut 2025, top-6 major 2024-25, Augusta avg, SG T2G, driving dist, career wins_")
        lines.append("_Plus 2 informational flags: is_defending_champion, is_betting_favorite_")
        lines.append("")

        # High qualifiers — score 6+
        top = df[df["qualifier_score"] >= 6].head(12)
        if not top.empty:
            lines.append("### High Qualifiers (6+/8) — historically these are the contenders")
            lines.append("| Player | Score | Aug avg/round | SG T2G/round | Aug starts | Cuts | Missing |")
            lines.append("|--------|-------|---------------|--------------|------------|------|---------|")
            for _, r in top.iterrows():
                name = str(r["player_name"])
                if ", " in name:
                    p = name.split(", ", 1)
                    name = f"{p[1]} {p[0]}"
                score = f"{int(r['qualifier_score'])}/8"

                # Augusta avg to par per round (total / starts / 4 rounds)
                aug_starts = float(r.get("augusta_starts", 0) or 0)
                aug_avg_total = r.get("augusta_avg_to_par")
                if pd.notna(aug_avg_total) and aug_starts >= 1:
                    aug_per_round = float(aug_avg_total) / max(aug_starts * 4, 1)
                    aug_str = f"{aug_per_round:+.2f}/rd ({int(aug_starts)} starts)"
                else:
                    aug_str = "—"

                # SG T2G per round (total over events / events / ~4 rounds)
                sg_total = r.get("sg_t2g_last4_total")
                sg_events = float(r.get("sg_t2g_events", 4) or 4)
                if pd.notna(sg_total) and sg_events >= 1:
                    sg_per_round = float(sg_total) / (sg_events * 4)
                    sg_str = f"{sg_per_round:+.2f}/rd"
                else:
                    sg_str = "—"

                cuts_made = int(r.get("augusta_cuts_made", 0) or 0)
                cuts_str = f"{cuts_made}/{int(aug_starts)}" if aug_starts >= 1 else "—"

                failed_raw = str(r.get("qualifiers_failed", "")).strip()
                failed = "—" if failed_raw.lower() in ("", "nan", "none") else failed_raw

                # Add flags
                flags = []
                if int(r.get("is_defending_champion", 0)):
                    flags.append("defending champ")
                if int(r.get("is_betting_favorite", 0)):
                    flags.append("betting fav")
                flag_str = f" ({', '.join(flags)})" if flags else ""

                lines.append(f"| {name}{flag_str} | {score} | {aug_str} | {sg_str} | {int(aug_starts)} | {cuts_str} | {failed} |")
            lines.append("")

        # Mid-tier — score 3-5
        mid = df[(df["qualifier_score"] >= 3) & (df["qualifier_score"] < 6)].head(8)
        if not mid.empty:
            lines.append("### Mid-tier (3–5/8) — long shots; need multiple criteria to fall right")
            lines.append("| Player | Score | Passed |")
            lines.append("|--------|-------|--------|")
            for _, r in mid.iterrows():
                name = str(r["player_name"])
                if ", " in name:
                    p = name.split(", ", 1)
                    name = f"{p[1]} {p[0]}"
                score = f"{int(r['qualifier_score'])}/8"
                passed = str(r.get("qualifiers_passed", "")) or "—"
                lines.append(f"| {name} | {score} | {passed} |")
            lines.append("")

        # Early eliminations
        out = df[df["qualifier_score"] <= 1]["player_name"].tolist()
        out_names = []
        for n in out:
            if ", " in n:
                p = n.split(", ", 1)
                out_names.append(f"{p[1]} {p[0]}")
            else:
                out_names.append(n)
        if out_names:
            lines.append(f"### Historical eliminations (≤1/8 criteria): {', '.join(out_names[:15])}")

        return "\n".join(lines)

    except Exception:
        return ""


def _odds_fallback_block(tid: str, top_n: int = 20) -> str:
    """
    Fallback when latest_predictions.csv is for a different tournament.
    Reads sportsbook odds from prop_lines_{tid}.csv + course history from
    leaderboard CSVs so the LLM still has meaningful probability context.
    """
    if not tid:
        return ""

    odds_path = DATA / "odds" / f"prop_lines_{tid}.csv"
    if not odds_path.exists():
        return f"## FIELD OVERVIEW (odds fallback)\n(No odds file found for {tid})"

    try:
        odds_df = pd.read_csv(odds_path)
        outright = odds_df[odds_df["market"] == "outright"].copy()
        if outright.empty:
            return f"## FIELD OVERVIEW (odds fallback)\n(No outright market data in prop_lines_{tid}.csv)"

        # Compute implied win prob from American odds
        outright["_implied"] = outright["odds"].apply(_american_to_implied)

        # Remove placeholders / bad odds
        outright = outright[outright["_implied"] > 0.0005].copy()
        outright = outright.sort_values("_implied", ascending=False).head(top_n).reset_index(drop=True)

        # ── Build course history from leaderboard CSVs ────────────────────
        event_suffix = tid[-3:] if len(tid) >= 3 else ""
        hist_rows: list[dict] = []
        if event_suffix:
            for lb_path in sorted((DATA / "historical").glob("leaderboards_20*.csv")):
                try:
                    lb = pd.read_csv(lb_path, dtype=str)
                    lb = lb[lb["tournament_id"].fillna("").str.endswith(event_suffix)]
                    if lb.empty:
                        continue
                    for _, r in lb.iterrows():
                        hist_rows.append({
                            "player_name": str(r.get("player_name", "")),
                            "year": str(r.get("year", "")),
                            "position": str(r.get("position", "")),
                            "to_par": r.get("to_par", ""),
                        })
                except Exception:
                    continue

        # Aggregate: starts, wins, top-5s, avg to-par per player name
        from collections import defaultdict
        hist_agg: dict[str, dict] = defaultdict(lambda: {"starts": 0, "wins": 0, "top5": 0, "to_par_sum": 0, "to_par_cnt": 0})
        for hr in hist_rows:
            key = hr["player_name"].strip().lower()
            d = hist_agg[key]
            d["starts"] += 1
            pos = hr["position"].strip().upper()
            if pos in ("1", "WIN", "1ST"):
                d["wins"] += 1
            try:
                rank = int(pos.lstrip("T"))
                if rank <= 5:
                    d["top5"] += 1
            except (ValueError, AttributeError):
                pass
            try:
                tp = float(hr["to_par"])
                d["to_par_sum"] += tp
                d["to_par_cnt"] += 1
            except (TypeError, ValueError):
                pass

        # ── Build output table ────────────────────────────────────────────
        rows = []
        for i, row in outright.iterrows():
            pname = str(row["player_name"]).strip()
            implied = row["_implied"]
            dk_odds = _fmt_odds(row["odds"])
            implied_str = f"{implied*100:.1f}%"

            # Match to hist_agg by last name
            pkey = pname.strip().lower()
            hlast = pname.split()[-1].lower() if pname.split() else ""
            hist = next(
                (v for k, v in hist_agg.items() if k == pkey or k.split()[-1] == hlast),
                None
            )
            if hist and hist["starts"] > 0:
                avg_tp = hist["to_par_sum"] / hist["to_par_cnt"] if hist["to_par_cnt"] else None
                course_str = f"{hist['starts']} starts, {hist['wins']} W, {hist['top5']} T5"
                if avg_tp is not None:
                    course_str += f", avg {avg_tp:+.1f}"
            else:
                course_str = "No history"

            rows.append({
                "Rank": i + 1,
                "Player": pname,
                "DK Odds": dk_odds,
                "Implied Win%": implied_str,
                "Course History": course_str,
            })

        out_df = pd.DataFrame(rows)
        note = (
            "NOTE: Model predictions not yet run for this tournament. "
            "Probabilities are derived from DraftKings sportsbook outright odds (vig-inclusive implied). "
            "Course history is from all available leaderboard data."
        )
        return f"## FIELD OVERVIEW (sportsbook odds fallback — model not yet run for {tid})\n{note}\n" + out_df.to_markdown(index=False)

    except Exception as e:
        return f"## FIELD OVERVIEW (odds fallback)\n(Error loading odds for {tid}: {e})"







_MAJOR_SUFFIXES = {"014", "026", "047", "100"}

# LIV players who qualify for Majors — keyed by "Last, First" to match predictions CSV
_LIV_PLAYER_NOTES = {
    "Rahm, Jon":          "2023 Masters champion, ranked #29 OWGR",
    "DeChambeau, Bryson": "2024 US Open champion, ranked #24 OWGR",
    "Koepka, Brooks":     "5-time major champion (2023 PGA, 2x US Open, 2x PGA)",
    "Johnson, Dustin":    "2020 Masters champion; ranked #585 OWGR (SG data is zeroed — treat as unknown)",
    "Mickelson, Phil":    "3-time Masters champion; check news for withdrawal status",
    "Reed, Patrick":      "2018 Masters champion",
    "Garcia, Sergio":     "2017 Masters champion",
    "Smith, Cameron":     "2022 Open champion",
    "Stenson, Henrik":    "2016 Open champion",
    "Gooch, Talor":       "LIV, no recent PGA Tour SG",
    "Niemann, Joaquin":   "LIV, no recent PGA Tour SG",
    "Ancer, Abraham":     "LIV, no recent PGA Tour SG",
}


def _liv_players_block(tid: str | None) -> str:
    """
    For Major tournaments: show LIV players in the field with DK odds,
    course history, and a clear staleness warning on model data.
    Only fires for Masters (014), US Open (026), PGA Championship (047), The Open (100).
    """
    if not tid:
        return ""
    suffix = str(tid)[-3:]
    if suffix not in _MAJOR_SUFFIXES:
        return ""

    pred_path = OUTPUTS / "latest_predictions.csv"
    if not pred_path.exists():
        return ""

    try:
        df = pd.read_csv(pred_path)
    except Exception:
        return ""

    # LIV players present in predictions
    liv_names = list(_LIV_PLAYER_NOTES.keys())
    liv_df = df[df["player_name"].isin(liv_names)].copy()
    if liv_df.empty:
        return ""

    # Load DK odds for these players
    odds_map: dict[str, float] = {}
    opath = DATA / "odds" / f"prop_lines_{tid}.csv"
    if opath.exists():
        try:
            odf = pd.read_csv(opath)
            odf = odf[odf["market"] == "outright"]
            for _, row in odf.iterrows():
                odds_map[str(row["player_name"]).strip().lower()] = float(row["odds"])
        except Exception:
            pass

    # Course history from leaderboard CSVs
    hist_map: dict[str, dict] = {}
    ev_suffix = suffix
    for lbf in sorted((DATA / "historical").glob("leaderboards_20*.csv")):
        try:
            lbdf = pd.read_csv(lbf, dtype=str)
            lbdf = lbdf[lbdf["tournament_id"].fillna("").str.endswith(ev_suffix)]
            for _, r in lbdf.iterrows():
                key = str(r.get("player_name", "")).strip().lower()
                if not key:
                    continue
                if key not in hist_map:
                    hist_map[key] = {"starts": 0, "wins": 0, "best": None, "to_pars": []}
                hist_map[key]["starts"] += 1
                pos = str(r.get("position", "")).strip().upper()
                if pos in ("1", "WIN", "1ST"):
                    hist_map[key]["wins"] += 1
                try:
                    tp = float(str(r.get("to_par", "")).strip())
                    hist_map[key]["to_pars"].append(tp)
                except (ValueError, TypeError):
                    pass
        except Exception:
            continue

    def _get_hist(name: str) -> str:
        key = name.strip().lower()
        last = key.split(", ")[0].split()[-1] if ", " in key else key.split()[-1]
        h = hist_map.get(key) or next(
            (v for k, v in hist_map.items() if k.split(", ")[0].split()[-1] == last), None
        )
        if not h or h["starts"] == 0:
            return "No history"
        s = f"{h['starts']}x"
        if h["wins"]:
            s += f" {h['wins']}W"
        if h["to_pars"]:
            s += f" avg{sum(h['to_pars'])/len(h['to_pars']):+.1f}"
        return s

    def _get_odds(name: str) -> str:
        key = name.strip().lower()
        last = key.split(", ")[0].split()[-1] if ", " in key else key.split()[-1]
        v = odds_map.get(key) or next(
            (val for k, val in odds_map.items() if k.split()[-1] == last), None
        )
        if v is None:
            return "—"
        return _fmt_odds(v)

    liv_df = liv_df.sort_values("win_prob_calibrated", ascending=False)
    rows = []
    for _, row in liv_df.iterrows():
        name = str(row["player_name"])
        note = _LIV_PLAYER_NOTES.get(name, "LIV Tour player")
        model_prob = f"{row['win_prob_calibrated']*100:.1f}%" if pd.notna(row.get("win_prob_calibrated")) else "—"
        sg = f"{row['sg_total']:+.2f}" if pd.notna(row.get("sg_total")) and row.get("sg_total", 0) != 0 else "stale/missing"
        rows.append({
            "Player": _fmt_name(name),
            "DK Odds": _get_odds(name),
            "Model Win%": model_prob,
            "SG Total (pre-LIV)": sg,
            "Augusta History": _get_hist(name),
            "Note": note,
        })

    if not rows:
        return ""

    out_df = pd.DataFrame(rows)
    header = (
        "## LIV PLAYERS IN FIELD (Major)\n"
        "WARNING: These players' SG data is from their last PGA Tour season — could be 1-2+ years stale. "
        "Model win% likely UNDERSTATES their actual ability. "
        "Use DK Odds + Augusta History as primary signals for these players, not model rank.\n"
    )
    return header + out_df.to_markdown(index=False)


def _dg_field_stats_block(tid: str | None = None) -> str:
    """Synthesized DataGolf field stats — one row per player in the current field.

    Joins five data sources into a single scannable overview:
      1. dg_field_latest.csv         — who's in the field, DG rank, OWGR rank
      2. dg_pre_tournament_latest.csv — win/top10/make_cut probs (baseline_history_fit model)
      3. dg_skill_ratings_latest.csv  — total skill score + OTT/APP/ARG/PUTT
      4. dg_course_fit_latest.csv     — course fit delta (positive = course suits player)
      5. player_course_performance.csv — historical results at this course

    Sorted by DG rank so the LLM sees the field in the same order as the DG stats page.
    This is the equivalent of the DataGolf "field stats" tab in text form.
    """
    field_path   = DATA / "datagolf" / "dg_field_latest.csv"
    preds_path   = DATA / "datagolf" / "dg_pre_tournament_latest.csv"
    skill_path   = DATA / "datagolf" / "dg_skill_ratings_latest.csv"
    fit_path     = DATA / "datagolf" / "dg_course_fit_latest.csv"
    course_path  = DATA / "processed" / "player_course_performance.csv"

    if not field_path.exists():
        return ""

    try:
        # ── 1. Field spine ──
        field_df = pd.read_csv(field_path)
        if field_df.empty:
            return ""
        event_name  = field_df["event_name"].iloc[0]  if "event_name"  in field_df.columns else ""
        course_name = field_df["course_name"].iloc[0] if "course_name" in field_df.columns else ""

        def _nk(n: str) -> str:
            s = str(n).strip().lower()
            if "," in s:
                p = s.split(",", 1)
                return f"{p[1].strip()} {p[0].strip()}"
            return s

        field_df["_key"] = field_df["player_name"].apply(_nk)
        field_df = field_df.sort_values("dg_rank", na_position="last").reset_index(drop=True)

        # ── 2. DG probabilities (baseline_history_fit model) ──
        prob_map: dict[str, dict] = {}
        if preds_path.exists():
            pdf = pd.read_csv(preds_path)
            pdf = pdf[pdf["model"] == "baseline_history_fit"]
            pdf["_key"] = pdf["player_name"].apply(_nk)
            for _, r in pdf.iterrows():
                prob_map[r["_key"]] = {
                    "win":      r.get("win"),
                    "top_10":   r.get("top_10"),
                    "make_cut": r.get("make_cut"),
                }

        # ── 3. Skill ratings ──
        skill_map: dict[str, dict] = {}
        if skill_path.exists():
            sdf = pd.read_csv(skill_path)
            sdf["_key"] = sdf["player_name"].apply(_nk)
            for _, r in sdf.iterrows():
                skill_map[r["_key"]] = {
                    "total": r.get("dg_skill_total"),
                    "ott":   r.get("dg_skill_ott"),
                    "app":   r.get("dg_skill_app"),
                    "arg":   r.get("dg_skill_arg"),
                    "putt":  r.get("dg_skill_putt"),
                }

        # ── 4. Course fit delta ──
        fit_map: dict[str, float] = {}
        if fit_path.exists():
            fdf = pd.read_csv(fit_path)
            fdf["_key"] = fdf["player_name"].apply(_nk)
            for _, r in fdf.iterrows():
                fit_map[r["_key"]] = float(r.get("course_fit_delta", 0) or 0)

        # ── 5. Course history (filter to this course) ──
        hist_map: dict[str, dict] = {}
        if course_path.exists() and course_name:
            cdf = pd.read_csv(course_path)
            # Match by course name — keep row with most rounds if duplicates
            c_sub = cdf[cdf["course_name"].str.contains(
                course_name.split()[0], case=False, na=False
            )]
            if c_sub.empty and tid:
                # Fallback: try course_key matching event suffix
                pass
            if not c_sub.empty:
                c_sub = (
                    c_sub.sort_values("course_sg_total_rounds", ascending=False)
                    .drop_duplicates("player_name", keep="first")
                )
                c_sub["_key"] = c_sub["player_name"].apply(_nk)
                for _, r in c_sub.iterrows():
                    starts = int(r.get("starts", 0) or 0)
                    if starts == 0:
                        continue
                    hist_map[r["_key"]] = {
                        "starts":    starts,
                        "best":      r.get("best_finish"),
                        "avg_to_par": r.get("avg_to_par"),
                        "top10_rate": r.get("top_10_rate"),
                        "sg_avg":    r.get("course_sg_total_avg"),
                        "win_rate":  r.get("win_rate"),
                    }

        # ── Build output ──
        lines = [
            f"## DG FIELD STATS — {event_name}" + (f" at {course_name}" if course_name else ""),
            "Sorted by DG rank. skill=DG total skill score | fit_delta=course fit edge vs baseline | "
            "hist=starts/best finish/avg to par at this course",
            "",
        ]

        for _, row in field_df.iterrows():
            name = str(row.get("player_name", "")).strip()
            key  = row["_key"]
            dg_r = row.get("dg_rank")
            wr   = row.get("owgr_rank")

            prob  = prob_map.get(key, {})
            skill = skill_map.get(key, {})
            fit_d = fit_map.get(key)
            hist  = hist_map.get(key, {})

            # Build compact line
            rank_s  = f"DG#{int(dg_r)}" if pd.notna(dg_r) else ""
            wr_s    = f"WR#{int(wr)}"   if pd.notna(wr)   else ""
            win_s   = f"win {float(prob['win'])*100:.1f}%"    if prob.get("win")      is not None else ""
            t10_s   = f"T10 {float(prob['top_10'])*100:.0f}%" if prob.get("top_10")   is not None else ""
            cut_s   = f"cut {float(prob['make_cut'])*100:.0f}%" if prob.get("make_cut") is not None else ""
            sk_s    = f"skill {float(skill['total']):+.2f}" if skill.get("total") is not None else ""
            fit_s   = f"fit_delta {float(fit_d):+.4f}" if fit_d is not None else ""

            hist_s = ""
            if hist:
                n   = hist["starts"]
                bf  = f"T{int(float(hist['best']))}" if pd.notna(hist.get("best")) else "?"
                atp = f"{float(hist['avg_to_par']):+.1f}/tourn" if pd.notna(hist.get("avg_to_par")) else ""
                wr_ = f"WON {int(hist['win_rate']*n)}x" if hist.get("win_rate", 0) and hist["win_rate"] * n >= 1 else ""
                t10r = f"{int(round(hist['top10_rate']*100))}% T10" if pd.notna(hist.get("top10_rate")) else ""
                sg_h = f"SG {float(hist['sg_avg']):+.2f}" if pd.notna(hist.get("sg_avg")) else ""
                hist_parts = [f"{n}st" if n == 1 else f"{n}st+", bf, atp]
                if wr_:
                    hist_parts.append(wr_)
                elif t10r:
                    hist_parts.append(t10r)
                if sg_h:
                    hist_parts.append(sg_h)
                hist_s = "hist: " + " · ".join(p for p in hist_parts if p)

            parts = [p for p in [rank_s, wr_s, win_s, t10_s, cut_s, sk_s, fit_s, hist_s] if p]
            lines.append(f"  **{name}** | " + " | ".join(parts))

        return "\n".join(lines)

    except Exception as e:
        return f"## DG FIELD STATS\n(unavailable: {e})"


def _field_tiers_block(top_n: int = 30) -> str:
    """Segment the field into Elite / Mid-Tier / Value tiers with a contrarian signal.

    Logic:
      - Loads win_prob (our model) and odds_to_win (market American odds) from latest_predictions.csv.
      - Converts market odds to implied probability, then computes the gap:
          edge = model_win_prob - market_implied_prob
        A positive edge means our model likes this player MORE than the market does.
      - Tiers are defined by model rank (win_prob order), not world rank:
          Elite:    model rank 1–8   (realistic win contenders our model has at >3%)
          Mid-Tier: model rank 9–20  (in-form players, top-10 probability, smaller win upside)
          Value:    model rank 21–top_n but with the largest positive model-vs-market edge
        The Value tier is the contrarian signal — players the market is underpricing relative
        to what our model sees. These are the "names nobody's talking about."
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)

        # Model probability and market implied probability
        if "win_prob" not in df.columns:
            return ""
        df = df.sort_values("win_prob", ascending=False).reset_index(drop=True)
        df["model_rank"] = range(1, len(df) + 1)

        # Convert market odds to implied probability (no vig removal — raw implied)
        def _implied(odds_val):
            try:
                o = float(odds_val)
                return 100.0 / (o + 100.0) if o > 0 else abs(o) / (abs(o) + 100.0)
            except (TypeError, ValueError):
                return None

        odds_col = next((c for c in ["odds_to_win", "dk_win_odds_american", "win_odds_american"]
                         if c in df.columns and df[c].notna().any()), None)
        if odds_col:
            df["_market_implied"] = df[odds_col].apply(_implied)
        else:
            df["_market_implied"] = None

        df["_edge"] = df.apply(
            lambda r: float(r["win_prob"]) - r["_market_implied"]
            if pd.notna(r.get("_market_implied")) else None,
            axis=1,
        )

        top_df = df.head(top_n)
        elite   = top_df[top_df["model_rank"] <= 8]
        mid     = top_df[(top_df["model_rank"] >= 9) & (top_df["model_rank"] <= 20)]
        # Value = any player in top_n where model likes them materially more than the market.
        # No rank floor — a model #3 at +22500 is the biggest contrarian play in the field.
        # Threshold: edge > 1.5pp (model win% at least 1.5 points above market implied win%).
        value_pool = top_df[
            top_df["_edge"].notna() & (top_df["_edge"] > 0.015)
        ].nlargest(6, "_edge")

        def _fmt_row(r, show_edge: bool = False) -> str:
            name   = r["player_name"]
            wp     = float(r["win_prob"]) * 100
            t10    = r.get("top10_prob_calibrated") or r.get("top10_prob")
            t10_s  = f"{float(t10)*100:.0f}% T10" if pd.notna(t10) else ""
            mi     = r.get("_market_implied")
            odds_s = _fmt_odds(r.get(odds_col)) if odds_col else ""
            wr     = r.get("world_rank")
            wr_s   = f"#{int(wr)}" if pd.notna(wr) else ""
            momentum = str(r.get("momentum_trend") or "").upper()
            mom_s  = f" [{momentum}]" if momentum in ("HOT", "COLD") else ""

            parts = [f"**{name}**{mom_s} (model #{int(r['model_rank'])}, WR {wr_s})"]
            parts.append(f"win {wp:.1f}%")
            if t10_s:
                parts.append(t10_s)
            if odds_s:
                parts.append(f"market {odds_s}")
            if show_edge and pd.notna(mi) and r.get("_edge") is not None:
                edge_pp = float(r["_edge"]) * 100
                parts.append(f"model edge +{edge_pp:.1f}pp vs market")
            return "  " + " | ".join(parts)

        lines = ["## FIELD TIERS — MODEL RANKING WITH MARKET CONTEXT"]
        lines.append(
            "Elite = model's realistic win contenders. Mid-Tier = strong T10 candidates. "
            "Value = players our model likes significantly more than the market does."
        )
        lines.append("")

        lines.append("### ELITE (model ranks 1–8, realistic win contenders)")
        for _, r in elite.iterrows():
            lines.append(_fmt_row(r))

        lines.append("")
        lines.append("### MID-TIER (model ranks 9–20, strong T10 candidates)")
        for _, r in mid.iterrows():
            lines.append(_fmt_row(r))

        if not value_pool.empty:
            lines.append("")
            lines.append("### VALUE / CONTRARIAN (model likes meaningfully more than market)")
            lines.append("  edge = model win% minus market implied win% — the market is underpricing these players")
            for _, r in value_pool.iterrows():
                lines.append(_fmt_row(r, show_edge=True))

        return "\n".join(lines)
    except Exception as e:
        return f"## FIELD TIERS\n(unavailable: {e})"


def _predictions_block(top_n: int = 15, supplement_odds_tid: str | None = None) -> str:
    """Top N players ranked by win probability.

    supplement_odds_tid: if set and predictions have no odds, load DK odds from
    prop_lines_{tid}.csv and merge them in so the LLM sees real market prices.
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df.sort_values("win_prob", ascending=False).head(top_n).reset_index(drop=True)
        df["player_name"] = df["player_name"].apply(_fmt_name)

        # Build WD set from withdrawals file so withdrawn players are clearly flagged
        def _wd_key(n: str) -> str:
            return re.sub(r"[^a-z]", "", n.lower())

        _wd_names: set[str] = set()
        _wd_tid = supplement_odds_tid or _detect_tournament_id()
        if _wd_tid:
            _wd_path = DATA / "news" / f"withdrawals_{_wd_tid}.json"
            if _wd_path.exists():
                try:
                    _wd_list = json.loads(_wd_path.read_text())
                    for _w in _wd_list:
                        if str(_w.get("status", "")).upper() == "WITHDRAWN":
                            _wd_names.add(_wd_key(str(_w.get("player_name", ""))))
                except Exception:
                    pass
        if _wd_names:
            df["player_name"] = df["player_name"].apply(
                lambda n: f"{n} (WD)" if _wd_key(n) in _wd_names else n
            )

        # Supplement with sportsbook odds when predictions odds columns are null
        _dk_odds_map: dict[str, float] = {}
        if supplement_odds_tid:
            _opath = DATA / "odds" / f"prop_lines_{supplement_odds_tid}.csv"
            if _opath.exists():
                try:
                    _odf = pd.read_csv(_opath)
                    _odf = _odf[_odf["market"] == "outright"]
                    for _, _or in _odf.iterrows():
                        _dk_odds_map[str(_or["player_name"]).strip().lower()] = float(_or["odds"])
                except Exception:
                    pass

        out = pd.DataFrame()
        out["Model Rank"] = range(1, len(df) + 1)
        out["Player"] = df["player_name"]

        def _odds_with_implied(odds):
            o = _fmt_odds(odds)
            imp = _american_to_implied(odds)
            if imp is not None:
                return f"{o} ({imp*100:.0f}% implied)"
            return o

        odds_col = next((c for c in ["odds_to_win", "dk_win_odds_american", "win_odds_american"] if c in df.columns and df[c].notna().any()), None)

        if odds_col:
            out["Win Odds (Implied%)"] = df[odds_col].apply(_odds_with_implied)
        elif _dk_odds_map:
            # Merge in DK odds by name
            def _lookup_dk(pname: str) -> str:
                key = pname.strip().lower()
                last = key.split()[-1] if key.split() else ""
                odds_val = _dk_odds_map.get(key) or next(
                    (v for k, v in _dk_odds_map.items() if k.split()[-1] == last), None
                )
                return _odds_with_implied(odds_val) if odds_val else "—"
            out["DK Odds (Implied%)"] = df["player_name"].apply(_lookup_dk)
        else:
            out["Win Odds (Implied%)"] = "—"
        out["Est. Win%"]   = (df["win_prob"] * 100).round(1).astype(str) + "%"
        out["World Rank"]  = df["world_rank"].apply(lambda x: f"#{int(x)}" if pd.notna(x) else "—")

        # Projected score — the single authoritative projection number
        if "projected_score" in df.columns:
            out["Proj Score"] = df["projected_score"].apply(
                lambda x: f"{x:+.1f}" if pd.notna(x) else "—"
            )
        if "proj_median" in df.columns:
            out["Proj Median"] = df["proj_median"].apply(
                lambda x: f"{x:+.1f}" if pd.notna(x) else "—"
            )

        out["Top 10%"]     = (df["top10_prob"] * 100).round(0).astype(int).astype(str) + "%"

        # Build course history from leaderboard CSVs (more reliable than predictions columns)
        _lb_hist_map: dict[str, dict] = {}
        _lb_tid = supplement_odds_tid or (df["tournament_id"].iloc[0] if "tournament_id" in df.columns else None)
        if _lb_tid:
            _ev_suffix = str(_lb_tid)[-3:]
            for _lbf in sorted((DATA / "historical").glob("leaderboards_20*.csv")):
                try:
                    _lbdf = pd.read_csv(_lbf, dtype=str)
                    _lbdf = _lbdf[_lbdf["tournament_id"].fillna("").str.endswith(_ev_suffix)]
                    if _lbdf.empty:
                        continue
                    for _, _lr in _lbdf.iterrows():
                        _key = str(_lr.get("player_name", "")).strip().lower()
                        if not _key:
                            continue
                        if _key not in _lb_hist_map:
                            _lb_hist_map[_key] = {"starts": 0, "wins": 0, "top10": 0}
                        _lb_hist_map[_key]["starts"] += 1
                        _pos = str(_lr.get("position", "")).strip().upper()
                        if _pos in ("1", "WIN", "1ST"):
                            _lb_hist_map[_key]["wins"] += 1
                        try:
                            if int(float(_pos.lstrip("T"))) <= 10:
                                _lb_hist_map[_key]["top10"] += 1
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    continue

        def _fmt_ch_real(row) -> str:
            pname = str(row.get("player_name", "")).strip().lower()
            # Try exact match, then last-name match
            hist = _lb_hist_map.get(pname)
            if hist is None:
                last = pname.split(", ")[0].split()[-1] if pname else ""
                hist = next((v for k, v in _lb_hist_map.items() if k.split(", ")[0].split()[-1] == last or k.split()[-1] == last), None)
            if hist and hist["starts"] > 0:
                s = f"{hist['starts']}x"
                if hist["wins"]:
                    s += f" {hist['wins']}W"
                if hist["top10"]:
                    s += f" {hist['top10']}T10"
                return s
            return _fmt_course_history(row)  # fall back to predictions columns

        if _lb_hist_map:
            out["Course Hist"] = df.apply(_fmt_ch_real, axis=1)
        else:
            out["Course Hist"] = df.apply(_fmt_course_history, axis=1)

        if "live_top10_prob" in df.columns:
            out["Live T10%"] = (df["live_top10_prob"] * 100).round(0).fillna(0).astype(int).astype(str) + "%"

        note = (
            "IMPORTANT: Players are listed in Model Rank order (1 = model's top pick). "
            "Proj Score is the authoritative 4-round projection (to par). Proj Median is the 50th-percentile outcome. "
            "DO NOT reorder players against Model Rank when building tiers. "
            "Est. Win% is our estimate — compare to Implied% for value. "
            "Player stats, form, and course history are in the FORM & STATS section below."
        )
        return f"## FIELD OVERVIEW — Top {top_n} contenders\n{note}\n" + out.to_markdown(index=False)
    except Exception as e:
        return f"## FIELD OVERVIEW\n(unavailable: {e})"


def _player_deep_dive_block(player_names: list[str], tid: str | None = None, include_odds: bool = False, effective_tid: str | None = None) -> str:
    """Detailed stat card for each named player — SG breakdown, odds, finish probs, course history.

    effective_tid: if set and different from tid, course history and odds are sourced from
    the effective event (e.g. Masters) rather than the currently loaded predictions.
    """
    if not player_names:
        return ""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""

    # Pre-load fallback odds file for effective event when predictions are stale
    _eff_odds: dict[str, dict] = {}  # lower player_name → {odds, implied}
    _stale_preds = bool(effective_tid and effective_tid != tid)
    if _stale_preds and effective_tid:
        _eff_odds_path = DATA / "odds" / f"prop_lines_{effective_tid}.csv"
        if _eff_odds_path.exists():
            try:
                _odf = pd.read_csv(_eff_odds_path)
                _odf = _odf[_odf["market"] == "outright"]
                for _, _or in _odf.iterrows():
                    _eff_odds[str(_or["player_name"]).strip().lower()] = {
                        "odds": _or["odds"],
                        "implied": _american_to_implied(_or["odds"]),
                    }
            except Exception:
                pass

    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)

        field_size = len(df)

        # Resolve course par from characteristics file (default 72)
        course_par = 72
        if tid:
            year = datetime.now().year
            prof_path = DATA / "course_characteristics" / f"{tid.lower()}_{year}_profiles.csv"
            if prof_path.exists():
                try:
                    course_par = int(pd.read_csv(prof_path).iloc[0].get("course_par", 72))
                except Exception:
                    pass

        lines = [
            f"## PLAYER SPOTLIGHT: {', '.join(player_names)}",
            "INSTRUCTION: Every number in this block MUST appear verbatim in your response. Do not paraphrase or replace with adjectives.",
        ]

        for pname in player_names:
            # Match by exact last name first, then fall back to substring
            # Prevents "Scott" from matching "Scottie Scheffler"
            parts = pname.lower().split()
            last  = parts[-1]
            first = parts[0] if len(parts) > 1 else ""

            # 1. Exact last name match (case-insensitive)
            def _last_name(n):
                n = n.lower()
                return n.split()[-1] if n else ""
            mask_exact = df["player_name"].apply(_last_name) == last
            rows = df[mask_exact]

            # 2. If multiple hits (e.g. "Rose" matches "Justin Rose" and "Rose Zhang"),
            #    narrow by first name if we have it
            if len(rows) > 1 and first:
                first_mask = rows["player_name"].str.lower().str.startswith(first)
                if first_mask.any():
                    rows = rows[first_mask]

            # 3. Fall back to substring if exact match found nothing
            if rows.empty:
                mask_sub = df["player_name"].str.lower().str.contains(last, na=False)
                rows = df[mask_sub]

            if rows.empty:
                lines.append(f"\n### {pname}: Not found in this week's field")
                continue

            r = rows.iloc[0]
            actual = r["player_name"]
            wr = r.get("world_rank")
            wr_str = f"World #{int(wr)}" if pd.notna(wr) else ""
            lines.append(f"\n### {actual}" + (f" ({wr_str})" if wr_str else ""))

            # --- Odds & value (only shown for betting questions) ---
            win_prob  = float(r.get("win_prob", 0) or 0)
            t5        = float(r.get("top5_prob",  0) or 0)
            t10       = float(r.get("top10_prob", 0) or 0)
            t20       = float(r.get("top20_prob", 0) or 0)

            # If predictions are stale, override with effective-event sportsbook odds
            _eff_player_odds = None
            if _stale_preds and _eff_odds:
                _pkey = actual.strip().lower()
                _plast = _pkey.split()[-1] if _pkey.split() else ""
                _eff_player_odds = _eff_odds.get(_pkey) or next(
                    (v for k, v in _eff_odds.items() if k.split()[-1] == _plast), None
                )
                if _eff_player_odds:
                    # Replace model win_prob with market implied
                    win_prob = _eff_player_odds["implied"] or win_prob
                    # t5/t10/t20 not available from outright; leave as-is

            if include_odds:
                if _eff_player_odds:
                    odds    = _fmt_odds(_eff_player_odds["odds"])
                    implied = _eff_player_odds["implied"]
                else:
                    odds    = _fmt_odds(r.get("odds_to_win"))
                    implied = _american_to_implied(r.get("odds_to_win"))
                if implied:
                    value_flag = ""
                    if win_prob > implied * 1.3:
                        value_flag = " ← we like him MORE than the market"
                    elif win_prob < implied * 0.7:
                        value_flag = " ← market favors him more than we do"
                    lines.append(f"**Win odds**: {odds} (book implies {implied*100:.0f}% chance){value_flag}")
                else:
                    lines.append(f"**Win odds**: {odds}")
                lines.append(f"**Finish chances**: Top 5: {t5*100:.0f}% | Top 10: {t10*100:.0f}% | Top 20: {t20*100:.0f}%")

            # --- Form (plain English, no raw numbers) ---
            mc_last   = int(r.get("missed_cut_last_start", 0) or 0)
            t5_last   = int(r.get("post_top5_last_start",  0) or 0)
            last_pos  = r.get("last_start_position")
            consec_c  = int(r.get("consecutive_cuts",   0) or 0)
            consec_t  = int(r.get("consecutive_top10s", 0) or 0)
            r_t10     = float(r.get("recent_top10s",    0) or 0)
            r_cuts    = float(r.get("recent_cuts_pct",  0) or 0)
            hot       = bool(r.get("hot_hand_flag", False))
            hot_score = float(r.get("hot_hand_score", 0) or 0)
            ft        = float(r.get("form_trend",    0) or 0)

            try:
                last_pos_int = int(float(last_pos)) if last_pos and float(last_pos) < 999 else None
            except (TypeError, ValueError):
                last_pos_int = None

            # --- Season summary ---
            n_events    = int(r.get("sg_event_count", 0) or 0)
            r_wins      = int(r.get("recent_wins",  0) or 0)
            r_t5s       = int(r.get("recent_top5s", 0) or 0)
            r_t10s_raw  = float(r.get("recent_top10s", 0) or 0)
            r_scoring   = r.get("recent_scoring_avg")
            if n_events >= 1:
                season_parts = [f"{n_events} starts this season"]
                if r_wins:
                    season_parts.append(f"{r_wins} win{'s' if r_wins > 1 else ''}")
                if r_t5s:
                    season_parts.append(f"{r_t5s} top-5{'s' if r_t5s > 1 else ''}")
                if r_t10s_raw >= 1:
                    season_parts.append(f"{int(round(r_t10s_raw))} top-10s in last 5 starts")
                if consec_c:
                    season_parts.append(f"{consec_c} consecutive cuts made")
                if pd.notna(r_scoring) and float(r_scoring) > 0:
                    season_parts.append(f"scoring avg {float(r_scoring):.2f}/round")
                lines.append(f"**This season**: {' · '.join(season_parts)}")

            form_parts = []
            if mc_last:
                form_parts.append("missed the cut last start")
            elif last_pos_int:
                label = " (top-5)" if t5_last else (" (top-10)" if last_pos_int <= 10 else "")
                form_parts.append(f"T{last_pos_int} last start{label}")

            if consec_t >= 2:
                form_parts.append(f"{consec_t} consecutive top-10s")
            if hot:
                form_parts.append(f"in peak form (hot-hand score {int(hot_score)}/10)")
            elif ft > 0.5:
                form_parts.append("trending up")
            elif ft < -0.5:
                form_parts.append("trending down")
            if r_cuts >= 0.8:
                form_parts.append(f"making {r_cuts*100:.0f}% of cuts recently")
            elif r_cuts < 0.5:
                form_parts.append(f"missing cuts at an alarming rate ({r_cuts*100:.0f}% made)")

            if form_parts:
                lines.append(f"**Recent form**: {' · '.join(form_parts)}")

            # --- SG strokes gained (raw value + field rank for every category) ---
            sg_cats = [
                ("season_sg_total",  "season_sg_total_field_rank",  "total"),
                ("season_sg_t2g",    "season_sg_t2g_field_rank",    "tee-to-green"),
                ("season_sg_ott",    "season_sg_ott_field_rank",    "off the tee"),
                ("season_sg_app",    "season_sg_app_field_rank",    "approach"),
                ("season_sg_arg",    "season_sg_arg_field_rank",    "around green"),
                ("season_sg_putt",   "season_sg_putt_field_rank",   "putting"),
            ]
            stat_parts = []
            for val_col, rank_col, label in sg_cats:
                val  = r.get(val_col)
                rank = r.get(rank_col)
                if pd.isna(val) and pd.isna(rank):
                    continue
                val_str  = f"{float(val):+.3f} SG/round" if pd.notna(val) else ""
                rank_str = f"#{int(rank)} in field" if pd.notna(rank) else ""
                combined = ", ".join(filter(None, [val_str, rank_str]))
                stat_parts.append(f"{label}: {combined}")
            if stat_parts:
                lines.append(f"**Strokes Gained**: {' · '.join(stat_parts)}")

            # --- Traditional stats ---
            trad_parts = []
            drv_dist = r.get("driving_dist_val")
            drv_acc  = r.get("driving_acc_val")
            gir      = r.get("gir_pct_val")
            scramble = r.get("scrambling_val")
            sand     = r.get("sand_save_val")
            bogey_av = r.get("bogey_avoid_val")
            putts_r  = r.get("putts_per_round_val")
            one_putt = r.get("one_putt_pct_val")
            birdie_v = r.get("birdie_avg_val")
            birdie_r = r.get("birdie_avg_field_rank")
            consist  = r.get("finish_consistency")
            if pd.notna(drv_dist): trad_parts.append(f"drives it {float(drv_dist):.0f} yds")
            if pd.notna(drv_acc):  trad_parts.append(f"{float(drv_acc):.1f}% driving accuracy")
            if pd.notna(gir):      trad_parts.append(f"{float(gir):.1f}% GIR")
            if pd.notna(scramble): trad_parts.append(f"{float(scramble):.1f}% scrambling")
            if pd.notna(sand):     trad_parts.append(f"{float(sand):.1f}% sand saves")
            if pd.notna(bogey_av): trad_parts.append(f"{float(bogey_av):.1f}% bogey avoidance")
            if pd.notna(putts_r):  trad_parts.append(f"{float(putts_r):.2f} putts/round")
            if pd.notna(one_putt): trad_parts.append(f"{float(one_putt):.1f}% one-putt")
            if pd.notna(birdie_v):
                rank_str = f" (#{int(birdie_r)} in field)" if pd.notna(birdie_r) else ""
                trad_parts.append(f"{float(birdie_v):.2f} birdies/round{rank_str}")
            if trad_parts:
                # Split into ball-striking and scoring lines for readability
                ball_striking = [p for p in trad_parts if any(x in p for x in ["yds", "accuracy", "GIR", "scrambling", "sand"])]
                scoring_stats = [p for p in trad_parts if any(x in p for x in ["bogey", "putts", "one-putt", "birdies"])]
                other = [p for p in trad_parts if p not in ball_striking and p not in scoring_stats]
                sample_note = f" (based on {n_events} starts)" if n_events and n_events < 6 else ""
                if ball_striking:
                    lines.append(f"**Ball striking**{sample_note}: {' · '.join(ball_striking)}")
                if scoring_stats:
                    lines.append(f"**Scoring stats**: {' · '.join(scoring_stats)}")
                if other:
                    lines.append(f"**Other**: {' · '.join(other)}")

            # --- Course history + course-specific performance ---
            # Always source starts/wins/top5s from leaderboard CSVs — the pipeline's
            # course_starts / hist_times_played can be wrong (e.g. shows 4 not 13 for Rory at Augusta).
            _hist_lookup_tid = effective_tid if (effective_tid and effective_tid != tid) else tid
            _pid = r.get("player_id")
            _real_hist = _get_player_course_years(_pid, actual, _hist_lookup_tid)

            # Always prefer real leaderboard data; fall back to predictions columns
            _pred_starts = max(int(r.get("course_starts", 0) or 0), int(r.get("hist_times_played", 0) or 0))
            n_starts  = len(_real_hist) if _real_hist else _pred_starts
            wins      = sum(1 for h in _real_hist if h["position"] == "WIN") if _real_hist else int(r.get("hist_wins", 0) or 0)
            t5s_here  = sum(1 for h in _real_hist if _safe_int(h["position"]) is not None and _safe_int(h["position"]) <= 5) if _real_hist else int(r.get("hist_top5s", 0) or 0)
            t10s      = sum(1 for h in _real_hist if _safe_int(h["position"]) is not None and _safe_int(h["position"]) <= 10) if _real_hist else int(r.get("hist_top10s", 0) or 0)
            _tp_vals  = [h["to_par"] for h in _real_hist if h["to_par"] is not None]
            avg_to_par = sum(_tp_vals) / len(_tp_vals) if _tp_vals else r.get("course_avg_to_par")
            _best_entry = min((h for h in _real_hist if _safe_int(h["position"]) is not None), key=lambda h: _safe_int(h["position"]), default=None) if _real_hist else None
            best      = _safe_int(_best_entry["position"]) if _best_entry else r.get("course_best_finish")
            hist_best = best
            hist_avg  = None  # not needed when we have real starts
            hist_cut  = None
            cut_rt    = float(r.get("course_made_cut_rate", 1) or 1)
            c_scoring = r.get("course_stat_120_scoring_average_weighted")
            c_drv_acc = r.get("course_stat_102_driving_accuracy_weighted")
            c_sg_app  = r.get("course_sg_app_weighted")
            c_sg_ott  = r.get("course_sg_ott_weighted")
            c_sg_putt = r.get("course_sg_putt_weighted")

            # Year-by-year results table (always shown when real history exists)
            if _real_hist:
                _yr_lines = ["| Year | Result | Score to Par |", "|------|--------|--------------|"]
                for _yh in _real_hist:
                    _tp_s = f"{_yh['to_par']:+d}" if _yh["to_par"] is not None else "—"
                    _yr_lines.append(f"| {_yh['year']} | {_yh['position']} | {_tp_s} |")
                lines.append(f"**{actual} at this event — year-by-year:**\n" + "\n".join(_yr_lines))

            if n_starts == 0:
                lines.append("**Course history**: No history here — first start at this venue")
            else:
                ch_parts = [f"{n_starts} start{'s' if n_starts != 1 else ''} at this course"]
                if wins:
                    ch_parts.append(f"WON {wins}x" if wins > 1 else "won here before")
                if t5s_here:
                    ch_parts.append(f"{t5s_here} top-5{'s' if t5s_here > 1 else ''} here")
                elif t10s:
                    ch_parts.append(f"{t10s} top-10{'s' if t10s > 1 else ''} here")
                best_val = best or hist_best
                if pd.notna(best_val) and float(best_val) <= 20:
                    ch_parts.append(f"best finish T{int(float(best_val))}")
                if pd.notna(hist_avg):
                    ch_parts.append(f"avg finish T{int(float(hist_avg))}")
                if pd.notna(avg_to_par):
                    atp = float(avg_to_par)
                    _ctx_tid = effective_tid if (effective_tid and effective_tid != tid) else tid
                    ctx = _get_course_winning_context(_ctx_tid)
                    if ctx:
                        w_avg = ctx["winner_avg"]
                        off_pace = round(atp - w_avg, 1)
                        off_str = f"{off_pace:+.1f} vs typical winner"
                        ch_parts.append(
                            f"avg {atp:+.1f}/tournament here "
                            f"({off_str}; winner typically {w_avg:+.0f} at this course)"
                        )
                    else:
                        ch_parts.append(f"avg {atp:+.1f} per tournament")
                elif pd.notna(c_scoring):
                    ch_parts.append(f"scoring avg {float(c_scoring):.1f}/round here ({float(c_scoring) * 4:.0f} est. total)")
                cut_rate = float(hist_cut) if pd.notna(hist_cut) else cut_rt
                if cut_rate < 0.5 and n_starts >= 3:
                    ch_parts.append(f"makes cut only {cut_rate*100:.0f}% of the time here")
                elif cut_rate >= 0.9 and n_starts >= 3:
                    ch_parts.append(f"makes cut {cut_rate*100:.0f}% here")
                lines.append(f"**Course history**: {' · '.join(ch_parts)}")

                # Course-specific strengths/weaknesses vs season stats
                c_stat_parts = []
                if pd.notna(c_sg_ott):
                    c_val = float(c_sg_ott)
                    if c_val >= 0.4:
                        c_stat_parts.append(f"elite off-the-tee here (+{c_val:.2f} SG/round historically)")
                    elif c_val <= -0.3:
                        c_stat_parts.append(f"drives it poorly at this course ({c_val:+.2f} SG/round)")
                if pd.notna(c_drv_acc):
                    season_acc = float(r.get("driving_acc_val") or 0)
                    c_val = float(c_drv_acc)
                    if c_val >= 65:
                        c_stat_parts.append(f"hits fairways here ({c_val:.0f}% driving acc)")
                    elif season_acc and c_val > season_acc + 5:
                        c_stat_parts.append(f"drives straighter here than season avg ({c_val:.0f}% vs {season_acc:.0f}%)")
                if pd.notna(c_sg_app):
                    c_val = float(c_sg_app)
                    if c_val >= 0.3:
                        c_stat_parts.append(f"strong approach play at this course (+{c_val:.2f} SG/round)")
                    elif c_val <= -0.2:
                        c_stat_parts.append(f"struggles with irons here ({c_val:+.2f} SG/round)")
                if pd.notna(c_sg_putt):
                    c_val = float(c_sg_putt)
                    if c_val >= 0.3:
                        c_stat_parts.append(f"putts well on these greens (+{c_val:.2f} SG/round)")
                    elif c_val <= -0.3:
                        c_stat_parts.append(f"poor putter on these greens ({c_val:+.2f} SG/round)")
                if c_stat_parts:
                    lines.append(f"**At this course specifically**: {' · '.join(c_stat_parts)}")

            # --- Augusta qualifier data (Masters week only) ---
            _aug_lookup_tid = effective_tid if (effective_tid and effective_tid != tid) else tid
            if _aug_lookup_tid and _aug_lookup_tid.upper().endswith("014"):
                _aug_q_path = DATA / "qualitative" / f"masters_qualifiers_{_aug_lookup_tid.upper()}.csv"
                if _aug_q_path.exists():
                    try:
                        _aug_df = pd.read_csv(_aug_q_path)
                        def _aug_nk2(n: str) -> str:
                            s = str(n).strip().lower()
                            if ", " in s:
                                p = s.split(", ", 1)
                                return f"{p[1]} {p[0]}"
                            return s
                        _a_key = _aug_nk2(actual)
                        _aug_df["_key"] = _aug_df["player_name"].apply(_aug_nk2)
                        _aug_row = _aug_df[_aug_df["_key"] == _a_key]
                        if not _aug_row.empty:
                            _ar = _aug_row.iloc[0]
                            _aq_score  = int(_ar.get("qualifier_score", 0))
                            _aq_max    = int(_ar.get("qualifier_max", 8))
                            _aq_avg    = _ar.get("augusta_avg_to_par")
                            _aq_cuts   = _ar.get("augusta_cuts_made")
                            _aq_starts = _ar.get("augusta_starts")
                            _aq_top30  = _ar.get("augusta_top30s")
                            _aq_t2g    = _ar.get("sg_t2g_last4_total")
                            _aq_dist   = _ar.get("driving_dist_field_rank")
                            _aq_comp   = _ar.get("aug_composite")
                            _aq_rank   = _ar.get("aug_rank")
                            _aq_passed = str(_ar.get("qualifiers_passed", "")).strip()
                            _aq_failed = str(_ar.get("qualifiers_failed", "")).strip()

                            aug_parts = [f"**Augusta Qualifier Score**: {_aq_score}/{_aq_max}"]
                            if pd.notna(_aq_avg):
                                aug_parts.append(f"career avg to-par at Augusta: {float(_aq_avg):+.2f}")
                            if pd.notna(_aq_cuts) and pd.notna(_aq_starts):
                                aug_parts.append(f"{int(_aq_cuts)}/{int(_aq_starts)} cuts made at Augusta")
                            if pd.notna(_aq_top30):
                                aug_parts.append(f"{int(_aq_top30)} top-30 finish{'es' if int(_aq_top30) > 1 else ''} at Augusta")
                            if pd.notna(_aq_t2g):
                                aug_parts.append(f"SG T2G last 4 starts: {float(_aq_t2g):+.2f} shots")
                            if pd.notna(_aq_dist):
                                aug_parts.append(f"driving distance T{int(_aq_dist)} in field")
                            if pd.notna(_aq_comp) and pd.notna(_aq_rank):
                                aug_parts.append(f"Augusta composite rank: #{int(_aq_rank)} (score {float(_aq_comp):.3f})")
                            lines.append(" · ".join(aug_parts))
                            if _aq_passed and _aq_passed.lower() not in ("nan", "none", ""):
                                lines.append(f"**Criteria passed**: {_aq_passed}")
                            if _aq_failed and _aq_failed.lower() not in ("nan", "none", ""):
                                lines.append(f"**Criteria failed**: {_aq_failed}")
                    except Exception:
                        pass

            # --- Par scoring breakdown (rank + avg value) ---
            par3_rank = r.get("par3_scoring_field_rank")
            par4_rank = r.get("par4_scoring_field_rank")
            par5_rank = r.get("par5_scoring_field_rank")
            par4_val  = r.get("par4_scoring_val")
            par5_val  = r.get("par5_scoring_val")
            par_parts = []
            for label, rank_col, val_col in [
                ("par 3s", par3_rank, None),
                ("par 4s", par4_rank, par4_val),
                ("par 5s", par5_rank, par5_val),
            ]:
                if pd.isna(rank_col):
                    continue
                rank = int(rank_col)
                val_str = f" (avg {float(val_col):+.2f})" if pd.notna(val_col) else ""
                if rank <= 10:
                    par_parts.append(f"elite {label} (#{rank} in field{val_str})")
                elif rank <= 20:
                    par_parts.append(f"strong {label} (#{rank}{val_str})")
                elif rank > field_size * 0.75:
                    par_parts.append(f"weak {label} (#{rank} of {field_size}{val_str})")
                else:
                    par_parts.append(f"avg {label} (#{rank}{val_str})")
            if par_parts:
                lines.append(f"**Par scoring**: {' · '.join(par_parts)}")

            # --- Round-by-round tendencies (always show all available avgs) ---
            r1    = r.get("recent_r1_avg");  r1_pct = r.get("recent_r1_avg_field_pct")
            r2    = r.get("recent_r2_avg");  r2_pct = r.get("recent_r2_avg_field_pct")
            r3    = r.get("recent_r3_avg");  r3_pct = r.get("recent_r3_avg_field_pct")
            r4    = r.get("recent_r4_avg");  r4_pct = r.get("recent_r4_avg_field_pct")
            closing_delta = r.get("closing_delta")
            _rnd  = [(1, r1, r1_pct), (2, r2, r2_pct), (3, r3, r3_pct), (4, r4, r4_pct)]
            _have = [(n, float(v), float(p)) for n, v, p in _rnd if pd.notna(v) and pd.notna(p)]
            round_parts = []
            if len(_have) >= 2:
                # Show vs-par AND actual score (e.g. R1: -2.8 (69.2))
                rnd_strs = [f"R{n}: {v:+.1f} ({course_par + v:.1f})" for n, v, p in _have]
                round_parts.append(f"round avgs — {' | '.join(rnd_strs)}")
                # Flag notable patterns
                for n, v, p in _have:
                    if n == 1 and p >= 0.85:
                        round_parts.append("strong starter")
                    elif n == 1 and p <= 0.20:
                        round_parts.append("slow starter")
                    if n == 4 and p >= 0.85:
                        round_parts.append("elite Sunday closer")
                    elif n == 4 and p <= 0.20:
                        round_parts.append("fades on Sundays")
            elif _have:
                n, v, p = _have[0]
                round_parts.append(f"R{n} avg {v:+.1f}")
            if pd.notna(closing_delta):
                cd = float(closing_delta)
                if cd <= -0.5:
                    round_parts.append(f"gains strokes closing tournaments (delta {cd:+.2f})")
                elif cd >= 0.5:
                    round_parts.append(f"loses strokes on Sundays vs Thursday (delta {cd:+.2f})")
            if round_parts:
                lines.append(f"**Round tendencies**: {' · '.join(round_parts)}")

            # --- Projected score (median + range) ---
            proj_vs  = r.get("projected_score_vs_field")
            p_floor  = r.get("proj_floor")
            p_median = r.get("proj_median")
            p_ceil   = r.get("proj_ceiling")
            if pd.notna(p_median):
                proj_str = f"median {float(p_median):+.1f} vs field"
                if pd.notna(p_floor) and pd.notna(p_ceil):
                    proj_str += f" | range: {float(p_floor):+.1f} (floor) to {float(p_ceil):+.1f} (ceiling)"
                lines.append(f"**Projection**: {proj_str}")
            elif pd.notna(proj_vs):
                lines.append(f"**Projection**: {float(proj_vs):+.1f} vs field average")

            # --- Live position if tournament in progress ---
            if "live_position" in r and pd.notna(r.get("live_position")):
                total  = r.get("total", "?")
                thru   = r.get("thru",  "?")
                live_w = r.get("live_win_prob")
                live_str = f" | Updated win chance: {float(live_w)*100:.1f}%" if pd.notna(live_w) else ""
                lines.append(f"**Live position**: {r['live_position']} | {total} total | thru {thru}{live_str}")

        result = "\n".join(lines)
        _dg_skill = _dg_skill_block(player_names)
        if _dg_skill:
            result = result + "\n\n" + _dg_skill
        _dg_app = _dg_approach_detail_block(player_names)
        if _dg_app:
            result = result + "\n\n" + _dg_app
        return result
    except Exception as e:
        return f"## PLAYER SPOTLIGHT\n(unavailable: {e})"


def _pick_reason_context_block(player_names: list[str], tid: str | None = None) -> str:
    """
    Enriched context for "why should I pick X?" fantasy lineup questions.
    Layers the player deep-dive with:
      - Model rank + finish probabilities (no sportsbook language)
      - Usage remaining from usage_tracker_2026.json (max 3 uses per season)
      - League-wide usage totals from league_total_usages.csv (scraped from fantasy site)
      - Key model drivers: SG, course fit, form trend, course history
      - Expert consensus count
      - Honest concerns (recent cuts, form dip, bad course history)
    """
    base = _player_deep_dive_block(player_names, tid, include_odds=False)
    if not base:
        return ""

    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return base

    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)
        df["_name_key"] = df["player_name"].str.lower().str.strip()

        # Model rank by win probability
        df = df.sort_values("win_prob", ascending=False).reset_index(drop=True)
        df["_model_rank"] = range(1, len(df) + 1)

        # Expert picks
        expert_counts: dict[str, int] = {}
        if tid:
            ep_path = DATA / "expert_picks" / f"expert_picks_{tid}.csv"
            if not ep_path.exists():
                ep_path = DATA / "expert_picks" / "expert_picks_latest.csv"
            if ep_path.exists():
                try:
                    ep = pd.read_csv(ep_path)
                    name_col = next((c for c in ep.columns if "player" in c.lower() or "name" in c.lower()), None)
                    if name_col:
                        for nm in ep[name_col].dropna():
                            nk = _fmt_name(str(nm)).lower().strip()
                            expert_counts[nk] = expert_counts.get(nk, 0) + 1
                except Exception:
                    pass

        # Usage tracker — my team's uses remaining per player
        usage_data: dict[str, dict] = {}
        usage_path = DATA / "fantasy" / "usage_tracker_2026.json"
        if usage_path.exists():
            try:
                import json
                raw_usage = json.loads(usage_path.read_text())
                usage_data = raw_usage.get("picks", {})
            except Exception:
                pass

        # Recent results map: normalized name → [(position, tournament_name), ...]
        recent_results_map: dict[str, list] = {}
        lb_2026 = DATA / "historical" / "leaderboards_2026.csv"
        if lb_2026.exists():
            try:
                lb = pd.read_csv(lb_2026)
                for _, row in lb.iterrows():
                    nk = _fmt_name(str(row.get("player_name", ""))).lower().strip()
                    entry = (str(row.get("position", "?")), str(row.get("tournament_name", "")))
                    recent_results_map.setdefault(nk, []).append(entry)
                # Keep only last 5 results per player (CSV is ordered oldest-first)
                recent_results_map = {k: v[-5:] for k, v in recent_results_map.items()}
            except Exception:
                pass

        # League-wide usage: normalized name → {times_used, util_pct}
        league_usage: dict[str, dict] = {}
        lu_path = DATA / "fantasy" / "league_total_usages.csv"
        if lu_path.exists():
            try:
                lu = pd.read_csv(lu_path)
                for _, row in lu.iterrows():
                    nk = _fmt_name(str(row.get("player_name", ""))).lower().strip()
                    league_usage[nk] = {
                        "times_used": int(row.get("times_used", 0) or 0),
                        "util_pct":   float(row.get("util_pct", 0) or 0),
                    }
            except Exception:
                pass

        extra_lines = ["\n## PICK CASE BUILDER"]
        extra_lines.append("Use this block to structure your fantasy reasoning. Lead with the 2-3 strongest reasons, then one honest concern, then a clear verdict.\n")

        for pname in player_names:
            parts = pname.lower().split()
            last = parts[-1]
            mask = df["player_name"].apply(lambda n: n.lower().split()[-1] == last)
            if not mask.any():
                mask = df["player_name"].str.lower().str.contains(last, na=False)
            if not mask.any():
                continue
            r = df[mask].iloc[0]
            actual = r["player_name"]

            model_rank  = int(r.get("_model_rank", 999))
            field_size  = len(df)
            win_prob    = float(r.get("win_prob", 0) or 0)
            t10_prob    = float(r.get("top10_prob", 0) or 0)
            t20_prob    = float(r.get("top20_prob", 0) or 0)
            dg_fit      = float(r.get("dg_fit_total", 0) or 0)
            pred_sg_w   = float(r.get("predictive_sg_weighted", 0) or 0)
            sg_total    = float(r.get("season_sg_total", 0) or 0)
            form_trend  = float(r.get("form_trend", 0) or 0)
            mc_last     = int(r.get("missed_cut_last_start", 0) or 0)
            consec_mc   = int(r.get("consecutive_missed_cuts", 0) or 0)
            course_hist = int(max(r.get("hist_times_played", 0) or 0, r.get("course_starts", 0) or 0))
            hist_t10s   = int(r.get("hist_top10s", 0) or 0)
            n_events    = int(r.get("sg_event_count", 0) or 0)

            extra_lines.append(f"### {actual} — Fantasy Pick Case")

            # Field standing — model rank only, no market language
            pct = round((1 - (model_rank - 1) / max(field_size, 1)) * 100)
            standing = f"Model ranks him #{model_rank} of {field_size} in the field (top {100-pct+1}%)"
            extra_lines.append(f"**Field standing**: {standing}")

            # Finish probabilities
            extra_lines.append(
                f"**Model probabilities**: Win {win_prob*100:.1f}% · Top-10 {t10_prob*100:.0f}% · Top-20 {t20_prob*100:.0f}%"
            )

            # Recent results — last 5 starts, most recent first
            # Try exact match, then last-name match
            recent = recent_results_map.get(nk, [])
            if not recent:
                for key, val in recent_results_map.items():
                    if key.split()[-1] == nk.split()[-1]:
                        recent = val
                        break
            if recent:
                result_parts = [f"{pos} ({tname})" for pos, tname in recent]
                extra_lines.append(f"**Recent results**: {' · '.join(result_parts)}")
            else:
                extra_lines.append("**Recent results**: no 2026 results found")

            # Usage remaining — critical for fantasy decision
            usage_entry = None
            for name_key, udata in usage_data.items():
                if _strip_accents(name_key.lower()) == _strip_accents(actual.lower()):
                    usage_entry = udata
                    break
            if usage_entry is not None:
                remaining = usage_entry.get("remaining_uses", 3)
                times_used = usage_entry.get("times_used", 0)
                past = usage_entry.get("tournaments_used", [])
                past_str = ", ".join(
                    f"{t.get('tournament','?')} ({t.get('result','?')})"
                    for t in past
                ) if past else "none yet"
                if remaining == 0:
                    extra_lines.append(f"**Usage**: INELIGIBLE — used all 3 times this season. Past: {past_str}")
                elif remaining == 1:
                    extra_lines.append(
                        f"**Usage**: {remaining} use remaining (used {times_used}x — last chance to play him). Past: {past_str}"
                    )
                else:
                    extra_lines.append(
                        f"**Usage**: {remaining} uses remaining ({times_used} used). Past: {past_str}"
                    )
            else:
                extra_lines.append("**Usage**: 3 uses remaining (not yet used this season)")

            # League-wide usage — from the fantasy site's total_golfer_usages page
            # Match by last name since site uses abbreviated formats like "Fitzpatrick, M"
            last_name = nk.split()[-1] if nk else ""
            lu_entry = None
            # Try exact normalized match first, then last-name fallback
            for key, val in league_usage.items():
                if _strip_accents(key) == _strip_accents(nk):
                    lu_entry = val
                    break
            if lu_entry is None:
                for key, val in league_usage.items():
                    if key.split()[-1] == last_name:
                        lu_entry = val
                        break

            LEAGUE_SIZE = 28
            TOTAL_POOL = LEAGUE_SIZE * 3  # 84 maximum uses across the league
            if lu_entry:
                times = lu_entry["times_used"]
                util  = lu_entry["util_pct"]
                # Thresholds based on 84 total possible uses (28 teams × 3):
                #   > 20 uses (~25%+) = high-demand chalk, many teams have already spent uses
                #   10-20 uses = moderate popularity
                #   < 10 uses = low demand, others are avoiding or overlooking him
                if times >= 20:
                    scarcity = (
                        f"HIGH DEMAND — {times}/{TOTAL_POOL} total uses ({util}%). "
                        f"Roughly {max(1, times // 3)}+ teams have used him multiple times. "
                        f"If your uses are still available, protect them carefully."
                    )
                elif times >= 10:
                    scarcity = (
                        f"MODERATE — {times}/{TOTAL_POOL} uses ({util}%). "
                        f"A fair number of teams have used him but he's not yet exhausted across the league."
                    )
                else:
                    scarcity = (
                        f"LOW DEMAND — {times}/{TOTAL_POOL} uses ({util}%). "
                        f"Most teams are not targeting him — either a contrarian value pick or the field is cold on him."
                    )
                extra_lines.append(
                    f"**League usage** (season total, 28 teams × max 3 = 84 pool): {times} uses ({util}%) — {scarcity}"
                )
            else:
                extra_lines.append(
                    "**League usage**: not found in league tracker — likely unused or first-time pick across the league"
                )

            # Key model drivers
            drivers = []
            if pred_sg_w > 0.3:
                drivers.append(f"elite predictive SG ({pred_sg_w:+.3f}/round on course-weighted skills)")
            elif pred_sg_w > 0.1:
                drivers.append(f"solid predictive SG ({pred_sg_w:+.3f}/round)")
            if dg_fit > 0.2:
                drivers.append(f"strong course-fit score ({dg_fit:+.3f}) — game matches what wins here")
            elif dg_fit > 0.05:
                drivers.append(f"positive course fit ({dg_fit:+.3f})")
            if sg_total > 0.5:
                drivers.append(f"strong season SG total ({sg_total:+.3f}/round)")
            if hist_t10s >= 2 and course_hist >= 3:
                drivers.append(f"{hist_t10s} top-10s in {course_hist} starts at this venue")
            elif hist_t10s >= 1 and course_hist >= 2:
                drivers.append(f"top-10 history here ({hist_t10s} in {course_hist} starts)")
            if form_trend > 0.5:
                drivers.append("form is trending up coming into this week")
            if n_events >= 3 and sg_total > 0.2:
                drivers.append(f"consistent form across {n_events} events this season")

            if drivers:
                extra_lines.append("**Why the model likes him**:")
                for d in drivers[:4]:
                    extra_lines.append(f"  - {d}")

            # Expert consensus
            exp_count = expert_counts.get(nk, 0)
            if exp_count > 0:
                extra_lines.append(
                    f"**Expert consensus**: appears in {exp_count} expert lineups "
                    f"({exp_count/max(1,sum(v > 0 for v in expert_counts.values()))*100:.0f}% of experts have him)"
                )
            else:
                extra_lines.append("**Expert consensus**: not widely held by experts — either contrarian or overlooked")

            # Honest concerns
            concerns = []
            if usage_entry and usage_entry.get("remaining_uses", 3) == 0:
                concerns.append("INELIGIBLE — no uses remaining this season")
            elif usage_entry and usage_entry.get("remaining_uses", 3) == 1:
                concerns.append("only 1 use left — consider saving for a stronger spot")
            if mc_last:
                concerns.append("missed the cut last start")
            if consec_mc >= 2:
                concerns.append(f"missed {consec_mc} cuts in a row — form is questionable")
            if form_trend < -0.5:
                concerns.append("form trend is declining recently")
            if course_hist < 2:
                concerns.append(f"limited course history ({course_hist} starts) — unknown quantity here")
            elif course_hist >= 3 and hist_t10s == 0:
                concerns.append(f"no top-10s in {course_hist} previous starts at this course")
            if dg_fit < -0.1:
                concerns.append(f"course fit is negative ({dg_fit:.3f}) — this track may not suit his game")
            if pred_sg_w < 0 and sg_total < 0:
                concerns.append("SG is below field average — model may be overstating his chances")
            if n_events < 4:
                concerns.append(f"only {n_events} events tracked this season — small sample size")

            if concerns:
                extra_lines.append("**Honest concerns**:")
                for c in concerns[:3]:
                    extra_lines.append(f"  - {c}")
            else:
                extra_lines.append("**Honest concerns**: no major red flags — clean case")

            extra_lines.append("")

        return base + "\n" + "\n".join(extra_lines)

    except Exception as e:
        return base + f"\n\n## PICK CASE BUILDER\n(unavailable: {e})"


def _build_recent_results_map(n_results: int = 8) -> dict[str, str]:
    """
    Build a map of player_name -> recent results string from leaderboard CSVs.
    Reads current + prior season, sorted by tournament_id (chronological).
    Returns e.g. {"Rory McIlroy": "T2 Genesis → T14 Pebble → WD Arnold Palmer → T46 PLAYERS"}
    """
    from datetime import datetime as _dt
    cur_year = _dt.now().year
    lb_frames = []
    for yr in [cur_year - 1, cur_year]:
        p = DATA / "historical" / f"leaderboards_{yr}.csv"
        if p.exists():
            try:
                df = pd.read_csv(p, usecols=["tournament_id", "tournament_name", "player_name", "position"])
                df["year"] = yr
                lb_frames.append(df)
            except Exception:
                pass
    if not lb_frames:
        return {}

    combined = pd.concat(lb_frames, ignore_index=True)
    combined = combined.sort_values(["year", "tournament_id"])

    # Short tournament name map for readability
    _short = {
        "The Genesis Invitational": "Genesis",
        "AT&T Pebble Beach Pro-Am": "Pebble",
        "WM Phoenix Open": "Phoenix",
        "Farmers Insurance Open": "Farmers",
        "The American Express": "AmEx",
        "Sony Open in Hawaii": "Sony",
        "Arnold Palmer Invitational": "Arnold Palmer",
        "Arnold Palmer Invitational presented by Mastercard": "Arnold Palmer",
        "THE PLAYERS Championship": "PLAYERS",
        "Cognizant Classic in The Palm Beaches": "Cognizant",
        "Valspar Championship": "Valspar",
        "Texas Children's Houston Open": "Houston",
        "Valero Texas Open": "Valero",
        "Masters Tournament": "Masters",
        "RBC Heritage": "RBC Heritage",
        "Wells Fargo Championship": "Wells Fargo",
        "PGA Championship": "PGA Champ",
        "Charles Schwab Challenge": "Colonial",
        "the Memorial Tournament": "Memorial",
        "U.S. Open": "US Open",
        "Rocket Classic": "Rocket",
        "The Open Championship": "The Open",
        "FedEx St. Jude Championship": "St. Jude",
        "BMW Championship": "BMW",
        "TOUR Championship": "TOUR Champ",
        "Truist Championship": "Truist",
    }

    def _pos_str(pos: str) -> str:
        s = str(pos).strip()
        if s in ("", "nan", "None", "999"):
            return "WD"
        if s == "1":
            return "WON"
        if s.upper() in ("WD", "DQ", "MDF", "CUT"):
            return s.upper()
        try:
            v = int(float(s))
            if v >= 100:
                return "MC"
            return f"T{v}"
        except Exception:
            return s

    def _short_name(full: str) -> str:
        for k, v in _short.items():
            if k.lower() in full.lower():
                return v
        # Fallback: first 2 words
        parts = full.split()
        return " ".join(parts[:2]) if len(parts) >= 2 else full

    result_map: dict[str, str] = {}
    for player, grp in combined.groupby("player_name"):
        grp = grp.tail(n_results)
        parts = []
        for _, row in grp.iterrows():
            pos = _pos_str(str(row["position"]))
            tname = _short_name(str(row["tournament_name"]))
            parts.append(f"{pos} {tname}")
        result_map[str(player)] = " → ".join(parts)

    return result_map


def _player_form_context_block(top_n: int = 20, tid: str | None = None) -> str:
    """
    Plain-English form, stats, and course history for the top contenders.
    Designed for Claude to use as a golf analyst would — results, streaks, strengths.
    Avoids raw SG numbers; uses field ranks and descriptive language instead.
    """
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["player_name"] = df["player_name"].apply(_fmt_name)
        full_field_size = len(df)  # actual field size before filtering
        df = df.sort_values("win_prob", ascending=False).head(top_n).copy()

        def _last_result(row) -> str:
            pos = row.get("last_start_position")
            mc  = row.get("missed_cut_last_start", 0)
            t5  = row.get("post_top5_last_start", 0)
            try:
                pos = int(float(pos))
            except (TypeError, ValueError):
                pos = None
            if mc:
                return "MC last start"
            if pos is None or pos >= 999:
                return "no recent result"
            if t5:
                return f"T{pos} last start (top-5 finish)"
            if pos <= 10:
                return f"T{pos} last start (top-10)"
            return f"T{pos} last start"

        def _form_streak(row) -> str:
            cuts  = int(row.get("consecutive_cuts", 0) or 0)                                                      
            t10s  = int(row.get("consecutive_top10s", 0) or 0)
            r_t10 = float(row.get("recent_top10s", 0) or 0)                                                       
            r_cut = float(row.get("recent_cuts_pct", 0) or 0)
            parts = []  
            
            # momentum tag first -- most important signam
            momentum = str(row.get("momentum_trend") or "").upper()                                               
            rec_sg   = row.get("recent_sg_weighted")                                                              
            ssn_sg   = row.get("season_sg_total")                                                                 
            if momentum in ("HOT", "COLD") and pd.notna(rec_sg) and pd.notna(ssn_sg):                             
                delta = float(rec_sg) - float(ssn_sg)                                                             
                tag   = "HOT" if momentum == "HOT" else "COLD"                                                    
                parts.append(f"[{tag}] recent SG {float(rec_sg):+.2f} vs season avg {float(ssn_sg):+.2f} (delta {delta:+.2f})")                                                                                                   
            elif pd.notna(rec_sg) and pd.notna(ssn_sg):   
                delta = float(rec_sg) - float(ssn_sg)                                                             
                if abs(delta) >= 0.2:                     
                    parts.append(f"recent SG {float(rec_sg):+.2f} ({delta:+.2f} {'above' if delta > 0 else        
  'below'} season avg)")     
                        
            birdie  = row.get("recent_birdie_avg")
            scr_avg = row.get("recent_scoring_avg")
            if pd.notna(birdie):
                scr_str = f", scoring avg {float(scr_avg):.1f}" if pd.notna(scr_avg) else ""
                parts.append(f"{float(birdie):.1f} birdies/round recently{scr_str}")
                                                                                                                    
              # result streaks                                                                                      
            if t10s >= 2:                                                                                         
                parts.append(f"{t10s} top-10s in a row")                                                          
            elif r_t10 >= 2:                              
                parts.append(f"{int(round(r_t10))} top-10s in last 5 starts")                                     
            if cuts >= 5:                                                    
                parts.append(f"{cuts} cuts in a row")                                                             
            elif r_cut >= 0.8:                            
                parts.append(f"making cuts ({int(r_cut*100)}%)")                                                  
            elif r_cut < 0.5:                                   
                parts.append("struggling to make cuts")                                                           
                      
            ft = float(row.get("form_trend", 0) or 0)                                                             
            if ft > 0.5 and momentum != "HOT":       
                parts.append("trending up")                                                                       
            elif ft < -0.5 and momentum != "COLD":                                                                
                parts.append("trending down")
                                                                                                                
            return ", ".join(parts) if parts else "steady form"










        def _sg_strengths(row) -> str:
            """SG profile with actual values and field ranks."""
            sg_map = {
                "OTT": ("season_sg_ott", "season_sg_ott_field_rank"),
                "APP": ("season_sg_app", "season_sg_app_field_rank"),
                "ARG": ("season_sg_arg", "season_sg_arg_field_rank"),
                "PUTT": ("season_sg_putt", "season_sg_putt_field_rank"),
            }
            parts = []
            for label, (val_col, rank_col) in sg_map.items():
                val = row.get(val_col)
                rank = row.get(rank_col)
                if pd.isna(val) and pd.isna(rank):
                    continue
                val_str = f"{float(val):+.2f}/rd" if pd.notna(val) else ""
                rank_str = f"#{int(rank)}" if pd.notna(rank) else ""
                parts.append(f"SG:{label} {val_str} ({rank_str})")
            return "; ".join(parts) if parts else ""

        def _course_narrative(row) -> str:
            starts  = int(row.get("course_starts", 0) or 0)
            hist_s  = int(row.get("hist_times_played", 0) or 0)
            best    = row.get("course_best_finish")
            avg     = row.get("course_avg_finish")
            wins    = int(row.get("hist_wins", 0) or 0)
            t10s    = int(row.get("hist_top10s", 0) or 0)
            cut_rt  = float(row.get("course_made_cut_rate", 1) or 1)
            # Use the larger of course_starts or hist_times_played
            n = max(starts, hist_s)
            if n == 0:
                return "no course history"
            parts = [f"{n} start{'s' if n != 1 else ''} here"]
            if wins:
                parts.append(f"WON {wins}x" if wins > 1 else "WON here before")
            elif t10s >= 2:
                parts.append(f"{t10s} top-10s")
            elif t10s == 1:
                parts.append("1 top-10")
            if pd.notna(best) and float(best) <= 15:
                parts.append(f"best finish T{int(float(best))}")
            if cut_rt < 0.5 and n >= 3:
                parts.append("struggles to make weekend")
            return " · ".join(parts)

        # Build recent results map from leaderboard CSVs (cross-season)
        _recent_results_map = _build_recent_results_map(n_results=8)

        lines = [
            "## FORM, STATS & COURSE HISTORY",
            "Full stat context per contender — cite these numbers directly in responses.",
            "",
        ]

        for _, row in df.iterrows():
            name   = row["player_name"]
            wr     = row.get("world_rank")
            wr_str = f"World #{int(wr)}" if pd.notna(wr) else ""
            model_rank = row.get("model_rank") or row.name + 1
            top10p = row.get("top10_prob_calibrated") or row.get("top10_prob")
            top10_str = f"{float(top10p)*100:.0f}% top-10 prob" if pd.notna(top10p) else ""
            last   = _last_result(row)
            streak = _form_streak(row)
            sg_str = _sg_strengths(row)
            course = _course_narrative(row)

            # Recent results sequence from leaderboard history
            recent_seq = _recent_results_map.get(name) or _recent_results_map.get(
                # Try "Last, First" format
                f"{name.split()[-1]}, {' '.join(name.split()[:-1])}" if " " in name else name
            ) or ""

            line = f"**{name}**"
            meta = []
            if wr_str:
                meta.append(wr_str)
            if model_rank:
                meta.append(f"model #{int(model_rank)}")
            if top10_str:
                meta.append(top10_str)
            if meta:
                line += f" ({', '.join(meta)})"
            if recent_seq:
                line += f"\n  Recent: {recent_seq}"
            line += f"\n  Form: {streak.capitalize()}."
            if sg_str:
                line += f" SG: {sg_str}."
            line += f" Course: {course}."

            # Append critical extras: course scoring avg, par-3 concern, R4 closing, projection
            extras = []
            avg_to_par = row.get("course_avg_to_par")
            c_scoring  = row.get("course_stat_120_scoring_average_weighted")
            if pd.notna(avg_to_par) and int(row.get("hist_times_played", 0) or 0) >= 2:
                atp = float(avg_to_par)
                ctx = _get_course_winning_context(tid)
                if ctx:
                    off_pace = round(atp - ctx["winner_avg"], 1)
                    extras.append(
                        f"avg {atp:+.1f}/tournament here "
                        f"({off_pace:+.1f} vs typical winner of {ctx['winner_avg']:+.0f})"
                    )
                else:
                    extras.append(f"avg {atp:+.1f}/tournament here")
            elif pd.notna(c_scoring) and int(row.get("hist_times_played", 0) or 0) >= 2:
                extras.append(f"scoring avg {float(c_scoring):.1f}/round here")

            par3_rank = row.get("par3_scoring_field_rank")
            if pd.notna(par3_rank):
                r = int(par3_rank)
                if r <= 10:
                    extras.append("elite par-3 scorer")
                elif r > full_field_size * 0.75:
                    extras.append(f"poor par-3 scorer (#{r}) — concern at this course")

            _rnd_labels = [("R1", "recent_r1_avg", "recent_r1_avg_vs_field"),
                           ("R2", "recent_r2_avg", "recent_r2_avg_vs_field"),
                           ("R3", "recent_r3_avg", "recent_r3_avg_vs_field"),
                           ("R4", "recent_r4_avg", "recent_r4_avg_vs_field")]
            _rnd_parts = []
            for _lbl, _avg_col, _vs_col in _rnd_labels:
                _avg = row.get(_avg_col)
                _vs  = row.get(_vs_col)
                if pd.notna(_avg) and pd.notna(_vs):
                    _arrow = "▲" if float(_vs) <= -0.5 else ("▼" if float(_vs) >= 0.5 else "—")
                    _rnd_parts.append(f"{_lbl}: {float(_avg):+.1f} ({float(_vs):+.1f} vs field {_arrow})")
            if _rnd_parts:
                extras.append("Round scoring: " + " | ".join(_rnd_parts))                                         
                                        
                    
            proj = row.get("projected_score")
            if pd.notna(proj):
                extras.append(f"projected {float(proj):+.1f} for the week")

            if extras:
                line += f" Key: {' · '.join(extras)}."
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        return f"## FORM & STATS\n(unavailable: {e})"


def _odds_movement_block(player_names: list[str] | None = None) -> str:
    """Price drift from odds snapshots — biggest movers, or movement for specific players."""
    snap_dir = DATA / "odds" / "snapshots"
    if not snap_dir.exists():
        return ""
    try:
        snap_files = sorted(snap_dir.glob("odds_snapshot_*.csv"))
        # Only use snapshots from the last 7 days (keeps within current tournament week)
        cutoff = datetime.now() - timedelta(days=7)
        recent = []
        for f in snap_files:
            try:
                ts_str = f.stem.replace("odds_snapshot_", "")
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M")
                if ts >= cutoff:
                    recent.append(f)
            except Exception:
                continue

        if len(recent) < 2:
            return ""

        first = pd.read_csv(recent[0])
        last  = pd.read_csv(recent[-1])

        for df in [first, last]:
            df["player_name"] = df["player_name"].apply(_fmt_name)

        merged = first.merge(last, on="player_name", suffixes=("_open", "_now"))
        merged = merged.dropna(subset=["odds_numeric_open", "odds_numeric_now"])

        def imp(o):
            try:
                o = float(o)
                return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
            except Exception:
                return None

        merged["prob_open"] = merged["odds_numeric_open"].apply(imp)
        merged["prob_now"]  = merged["odds_numeric_now"].apply(imp)
        merged = merged.dropna(subset=["prob_open", "prob_now"])
        merged["prob_chg"] = merged["prob_now"] - merged["prob_open"]
        merged = merged.sort_values("prob_chg", ascending=False)

        if player_names:
            p_lower = [p.lower() for p in player_names]
            mask = merged["player_name"].str.lower().apply(
                lambda n: any(pl in n or n in pl for pl in p_lower)
            )
            subset = merged[mask]
        else:
            # Top 5 shortened + top 5 lengthened
            top5 = merged.head(5)
            bot5 = merged.tail(5).sort_values("prob_chg")
            subset = pd.concat([top5, bot5]).drop_duplicates()

        if subset.empty:
            return ""

        t0 = recent[0].stem.replace("odds_snapshot_", "")
        t1 = recent[-1].stem.replace("odds_snapshot_", "")
        lines = [f"## ODDS MOVEMENT ({t0} → {t1})", "Positive = odds shortened (became more favored)."]

        for _, row in subset.iterrows():
            o_open = _fmt_odds(row["odds_numeric_open"])
            o_now  = _fmt_odds(row["odds_numeric_now"])
            chg    = row["prob_chg"]
            arrow  = "▲" if chg > 0.005 else ("▼" if chg < -0.005 else "→")
            pct    = f"{chg*100:+.1f}pp"
            lines.append(f"- {row['player_name']}: {o_open} → {o_now} {arrow} ({pct})")

        return "\n".join(lines)
    except Exception as e:
        return f"## ODDS MOVEMENT\n(unavailable: {e})"


def _weather_block(tid: str) -> str:
    """4-round weather forecast from cached weather JSON."""
    if not tid:
        return ""
    path = DATA / "weather" / f"{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)
        daily = data.get("daily", [])
        if not daily:
            return ""
        round_labels = ["Thursday (R1)", "Friday (R2)", "Saturday (R3)", "Sunday (R4)"]
        lines = ["## WEATHER FORECAST"]
        for i, day in enumerate(daily[:4]):
            label  = round_labels[i] if i < 4 else f"Day {i+1}"
            hi     = str(day.get("temperature", {}).get("maxTempF", "?")).replace("°F","")
            lo     = str(day.get("temperature", {}).get("minTempF", "?")).replace("°F","")
            wind   = day.get("windSpeedMPH", "?")
            precip = day.get("precipitation", "?")
            desc   = day.get("condition", "").replace("_", " ").title()
            wdir   = day.get("windDirection", "").replace("_", " ").title()
            lines.append(
                f"- {label}: {desc} | {lo}–{hi}°F | Wind: {wind} mph {wdir} | Precip: {precip}"
            )
        saved = data.get("saved_at", "")
        if saved:
            lines.append(f"_(forecast as of {saved[:10]})_")
        return "\n".join(lines)
    except Exception as e:
        return f"## WEATHER\n(unavailable: {e})"


def _live_odds_context_block(tid: str) -> str:
    """In-play win odds + pre-tournament movement for live responses.

    Joins:
      - live leaderboard (current position + live odds_to_win)
      - pre-tournament DK odds (dk_odds_R{tid}.csv)
      - current prop lines (top5/top10 markets)
    Computes odds movement and derives market signals.
    """
    if not tid:
        return ""
    tid_lower = tid.lower()
    lb_path    = DATA / "live"  / f"leaderboard_{tid_lower}.csv"
    pre_path   = DATA / "odds"  / f"dk_odds_{tid}.csv"
    props_path = DATA / "odds"  / f"prop_lines_{tid}.csv"

    if not lb_path.exists():
        return ""
    try:
        lb = pd.read_csv(lb_path)
        if lb.empty or "odds_to_win" not in lb.columns:
            return ""

        lb["player_name"] = lb["player_name"].apply(_fmt_name)
        top15 = lb.head(15).copy()

        # Pre-tournament odds for movement comparison
        pre_map: dict[str, float] = {}
        if pre_path.exists():
            try:
                pre = pd.read_csv(pre_path)
                pre["player_name"] = pre["player_name"].apply(_fmt_name)
                for _, row in pre.iterrows():
                    pre_map[row["player_name"]] = float(row.get("dk_odds_numeric", row.get("dk_odds", 0)) or 0)
            except Exception:
                pass

        # Top-5 and Top-10 odds lookup
        top5_map:  dict[str, str] = {}
        top10_map: dict[str, str] = {}
        if props_path.exists():
            try:
                props = pd.read_csv(props_path)
                props["player_name"] = props["player_name"].apply(_fmt_name)
                for mkt, out_map in [("top5", top5_map), ("top10", top10_map)]:
                    sub = props[props["market"] == mkt]
                    for _, row in sub.iterrows():
                        o = float(row.get("odds", 0) or 0)
                        out_map[row["player_name"]] = _fmt_odds(o)
            except Exception:
                pass

        rows = []
        for _, r in top15.iterrows():
            name  = r["player_name"]
            pos   = str(r.get("position", "?"))
            total = str(r.get("total", "?"))
            cur_o = r.get("odds_to_win")
            if pd.isna(cur_o):
                continue

            cur_o = float(cur_o)
            cur_str = _fmt_odds(cur_o)
            imp_cur = _american_to_implied(cur_o)

            # Movement vs pre-tournament
            pre_o = pre_map.get(name)
            if pre_o and pre_o > 0:
                imp_pre = _american_to_implied(pre_o)
                if imp_pre and imp_cur:
                    move_pct = (imp_cur - imp_pre) / imp_pre * 100
                    arrow = "▼" if move_pct > 5 else ("▲" if move_pct < -5 else "→")
                    pre_str = _fmt_odds(pre_o)
                    move_str = f"{arrow} (was {pre_str}, {move_pct:+.0f}% probability shift)"
                else:
                    move_str = ""
            else:
                move_str = "(no pre-tournament line)"

            t5_str  = top5_map.get(name, "—")
            t10_str = top10_map.get(name, "—")

            rows.append(
                f"- **{name}** | {pos} ({total}) | Win: {cur_str} "
                f"({imp_cur*100:.0f}% implied) {move_str} | T5: {t5_str} | T10: {t10_str}"
            )

        if not rows:
            return ""

        # Market signal: who is the market most confident about?
        contenders = top15[top15["odds_to_win"].notna()].copy()
        contenders["_imp"] = contenders["odds_to_win"].apply(
            lambda x: _american_to_implied(float(x)) or 0
        )
        top_pick = contenders.nlargest(1, "_imp").iloc[0]["player_name"] if not contenders.empty else ""

        # Biggest odds move (largest probability shift)
        biggest_move = ""
        best_shift = 0.0
        for _, r in contenders.iterrows():
            name  = r["player_name"]
            pre_o = pre_map.get(name)
            cur_o = float(r["odds_to_win"])
            if pre_o and pre_o > 0:
                ip = _american_to_implied(cur_o) or 0
                pp = _american_to_implied(pre_o) or 0
                if pp > 0:
                    shift = (ip - pp) / pp
                    if shift > best_shift:
                        best_shift = shift
                        biggest_move = f"{name} ({_fmt_odds(pre_o)} → {_fmt_odds(cur_o)}, +{shift*100:.0f}% prob shift)"

        lines = ["## IN-PLAY WIN ODDS & MARKET MOVEMENT"]
        lines.append("Current DraftKings win odds + movement since pre-tournament open. Use this to reason about market confidence and value.")
        lines.append("")
        lines += rows
        lines.append("")
        if top_pick:
            lines.append(f"**Market leader**: {top_pick} is the market's top choice to win.")
        if biggest_move:
            lines.append(f"**Biggest mover**: {biggest_move} — market has heavily re-priced this player.")
        lines.append("")
        lines.append("NOTE: Win odds reflect current tournament position. T5/T10 odds reflect remaining rounds.")

        return "\n".join(lines)
    except Exception as e:
        return f"## IN-PLAY ODDS\n(unavailable: {e})"


def _live_tournament_stats_block(tid: str) -> str:
    """Live in-tournament SG and stats from scorecardStatsComparison.

    Reads data/live/live_tournament_stats_{tid}.json (written by fetch_live_tournament_stats.py).
    Shows SG total/OTT/APP/ATG/PUTT for leaderboard players, with field ranks.
    Far more relevant than season stats for mid-tournament analysis.
    """
    if not tid:
        return ""
    path = DATA / "live" / f"live_tournament_stats_{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)

        player_map: dict[str, str] = data.get("player_map", {})
        categories    = data.get("categories", {})
        fetched_at    = data.get("fetched_at", "")[:16].replace("T", " ")
        rounds_done   = data.get("rounds_fetched", [])
        current_round = data.get("current_round", "?")

        if not categories:
            return ""

        # Use cumulative (sum of per-round values) — matches PGA Tour website display
        sg_data = categories.get("STROKES_GAINED", {}).get("cumulative", {})
        scoring  = categories.get("SCORING",       {}).get("cumulative", {})
        driving  = categories.get("OFF_TEE",       {}).get("cumulative", {})

        # Order players by leaderboard position (same order as player_ids list)
        ordered_pids = data.get("player_ids", list(player_map.keys()))

        rnd_label = f"through Round {max(rounds_done, key=int)}" if rounds_done else f"Round {current_round}"
        lines = [
            f"## LIVE TOURNAMENT STATS — {tid} ({rnd_label}, as of {fetched_at} UTC)",
            "Cumulative strokes gained vs field — matches PGA Tour website. More relevant than season stats.",
            "Values = total SG accumulated over completed rounds (not per-round average). Rank = field position.",
            "",
        ]

        # SG table
        sg_cat_labels = [
            ("SG: Total",              "SG Tot"),
            ("SG: Off the Tee",        "OTT"),
            ("SG: Approach the Green", "APP"),
            ("SG: Around the Green",   "ATG"),
            ("SG: Putting",            "PUTT"),
        ]
        lines.append("**Strokes Gained — This Tournament:**")
        header_cols = ["Player"] + [lbl for _, lbl in sg_cat_labels]
        rows = []
        for pid in ordered_pids:
            if pid not in sg_data:
                continue
            name  = _fmt_name(player_map.get(pid, f"ID:{pid}"))
            p_row = [name]
            for stat_name, _ in sg_cat_labels:
                entry = sg_data[pid].get(stat_name, {})
                val   = entry.get("value", None)
                rank  = entry.get("rank",  "—")
                try:
                    val_str = f"{float(val):+.3f}"
                except (TypeError, ValueError):
                    val_str = "—"
                p_row.append(f"{val_str} (#{rank})")
            rows.append(p_row)

        if rows:
            # Format as simple markdown table
            col_widths = [max(len(str(r[i])) for r in [header_cols] + rows) for i in range(len(header_cols))]
            def _fmt_row(r):
                return "| " + " | ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(r))) + " |"
            lines.append(_fmt_row(header_cols))
            lines.append("|" + "|".join("-" * (w + 2) for w in col_widths) + "|")
            for r in rows:
                lines.append(_fmt_row(r))

        # Key insight lines from the data
        lines.append("")
        lines.append("**Tournament leaders by SG category:**")
        for stat_name, short in sg_cat_labels:
            best_pid  = None
            best_val  = -999.0
            for pid in ordered_pids:
                entry = sg_data.get(pid, {}).get(stat_name, {})
                try:
                    v = float(entry.get("value", -999))
                    if v > best_val:
                        best_val = v
                        best_pid = pid
                except (TypeError, ValueError):
                    pass
            if best_pid and best_val > -999:
                name = _fmt_name(player_map.get(best_pid, best_pid))
                rank = sg_data.get(best_pid, {}).get(stat_name, {}).get("rank", "?")
                lines.append(f"  - {short}: **{name}** ({best_val:+.3f} cumulative, #{rank} in field)")

        # Scoring stats if available
        if scoring:
            lines.append("")
            lines.append("**Scoring stats this tournament (birdies, bogeys, scoring avg):**")
            for pid in ordered_pids[:8]:
                if pid not in scoring:
                    continue
                name = _fmt_name(player_map.get(pid, pid))
                parts = []
                for stat_name, stat_data in scoring[pid].items():
                    val  = stat_data.get("value", "")
                    rank = stat_data.get("rank",  "")
                    if val and val != "—":
                        parts.append(f"{stat_name}: {val} (#{rank})")
                if parts:
                    lines.append(f"  - {name}: {' · '.join(parts[:3])}")

        return "\n".join(lines)
    except Exception as e:
        return f"## LIVE TOURNAMENT STATS\n(unavailable: {e})"


def _live_course_stats_block(tid: str) -> str:
    """Live hole-by-hole course stats for the current tournament."""
    if not tid:
        return ""
    path = DATA / "live" / f"course_stats_{tid}.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            d = json.load(f)

        holes = d.get("holes", [])
        if not holes:
            return ""

        def _pct(val: str) -> str:
            return str(val).replace("%", "").strip() + "%"

        fetched = d.get("fetched_at", "")[:16].replace("T", " ")
        lines = [
            f"## LIVE COURSE STATS — {d.get('course_name', tid)} (as of {fetched} UTC)",
            f"Par {d.get('par')} | {d.get('yardage')} yards — scoring averages vs par across all completed rounds this week.",
            "",
        ]

        # Sort by scoring average descending for hardest/easiest context
        sorted_holes = sorted(holes, key=lambda h: float(h["scoringAverage"]), reverse=True)
        hardest = sorted_holes[:4]
        easiest = sorted_holes[-3:]

        lines.append("**Hardest holes this week** (where scores are lost):")
        for h in hardest:
            avg = float(h["scoringAverage"])
            lines.append(
                f"  Hole {h['holeNum']:2d}: avg {avg:+.3f} vs par | "
                f"birdie {_pct(h['birdiesPercent'])} | bogey {_pct(h['bogeysPercent'])} | dbl+ {_pct(h['doubleBogeysPercent'])}"
            )

        lines.append("")
        lines.append("**Easiest holes this week** (birdie opportunities):")
        for h in reversed(easiest):
            avg = float(h["scoringAverage"])
            lines.append(
                f"  Hole {h['holeNum']:2d}: avg {avg:+.3f} vs par | "
                f"birdie {_pct(h['birdiesPercent'])} | bogey {_pct(h['bogeysPercent'])}"
            )

        lines.append("")
        lines.append("**All holes** (hole | avg vs par | birdie% | bogey%):")
        for h in sorted(holes, key=lambda h: h["holeNum"]):
            avg = float(h["scoringAverage"])
            lines.append(
                f"  H{h['holeNum']:2d}  {avg:+.3f}  birdie={_pct(h['birdiesPercent'])}  bogey={_pct(h['bogeysPercent'])}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"## LIVE COURSE STATS\n(unavailable: {e})"


def _my_picks_live_block(tid: str | None) -> str:
    """
    Live check-in for the user's current fantasy picks.
    Reads this week's lineup from usage_tracker, cross-references live leaderboard
    for position, score, thru, odds movement, and cut status.
    """
    if not tid:
        return ""
    tid_lower = tid.lower()
    lb_path = DATA / "live" / f"leaderboard_{tid_lower}.csv"
    if not lb_path.exists():
        return ""

    # Load this week's picks from usage tracker
    usage_path = DATA / "fantasy" / "usage_tracker_2026.json"
    this_week_picks: list[str] = []
    if usage_path.exists():
        try:
            udata = json.loads(usage_path.read_text())
            wl = udata.get("weekly_lineups", {})
            # Find the lineup for this tournament
            for wk, info in wl.items():
                if str(info.get("tournament_id", "")).upper() == tid.upper():
                    this_week_picks = [str(p) for p in info.get("lineup", [])]
                    break
            # Fallback: numerically most recent week
            if not this_week_picks and wl:
                def _wk_num(k):
                    import re
                    m = re.search(r'\d+', str(k))
                    return int(m.group()) if m else 0
                latest = max(wl.keys(), key=_wk_num)
                this_week_picks = [str(p) for p in wl[latest].get("lineup", [])]
        except Exception:
            pass

    try:
        lb = pd.read_csv(lb_path)
        if lb.empty:
            return ""

        # Load meta for round/cut info
        meta_path = DATA / "live" / f"leaderboard_{tid_lower}_meta.json"
        current_round = 1
        round_status = "In Progress"
        cut_proj = {}
        if meta_path.exists():
            try:
                meta = json.loads(Path(meta_path).read_text())
                current_round = int(meta.get("current_round", 1))
                round_status = str(meta.get("round_status", ""))
                cut_proj = meta.get("cut_projection", {})
            except Exception:
                pass

        proj_cut = cut_proj.get("projected_cut_score")
        proj_cut_str = f"E" if proj_cut == 0 else (f"{proj_cut:+d}" if proj_cut is not None else "TBD")

        lines = [
            f"## MY PICKS — LIVE STATUS (R{current_round}, {round_status})",
            f"_Projected cut: {proj_cut_str} | Safely in: {cut_proj.get('safely_in','?')} | Safely out: {cut_proj.get('safely_out','?')}_",
            "",
        ]

        def _nk(n: str) -> str:
            return str(n).strip().lower()

        # Build lookup from leaderboard
        lb["_key"] = lb["player_name"].apply(_nk)
        lb_map = {row["_key"]: row for _, row in lb.iterrows()}

        def _cut_status(row) -> str:
            total = row.get("total_numeric")
            if pd.isna(total):
                return "?"
            if proj_cut is None:
                return "—"
            if total <= proj_cut:
                return "safely in" if total <= proj_cut - 3 else "on the line"
            return "in danger"

        def _odds_str(o) -> str:
            if pd.isna(o):
                return "—"
            o = int(o)
            return f"+{o}" if o > 0 else str(o)

        if this_week_picks:
            lines.append("### This Week's Picks")
            lines.append("| Pick | Position | Score | Thru | R1 | Odds | Cut Status |")
            lines.append("|------|----------|-------|------|----|------|------------|")
            for pick_raw in this_week_picks:
                pick_key = _nk(pick_raw)
                # Try partial match
                row = lb_map.get(pick_key)
                if row is None:
                    for k, r in lb_map.items():
                        if pick_key.split()[-1] in k:
                            row = r
                            break
                if row is None:
                    lines.append(f"| {pick_raw} | — | — | — | — | — | — |")
                    continue
                pos = str(row.get("position", "—"))
                total = str(row.get("total", "—"))
                thru = str(row.get("thru", "—"))
                r1 = row.get("R1")
                r1_str = f"{int(r1):+d}" if pd.notna(r1) else "—"
                odds = _odds_str(row.get("odds_to_win"))
                cut = _cut_status(row)
                lines.append(f"| {row['player_name']} | {pos} | {total} | thru {thru} | {r1_str} | {odds} | {cut} |")
            lines.append("")

        # Top 10 of full leaderboard for context
        top = lb.sort_values("total_numeric").head(10)
        lines.append("### Leaderboard Top 10")
        lines.append("| Pos | Player | Score | Thru | R1 | Odds |")
        lines.append("|-----|--------|-------|------|----|------|")
        for _, row in top.iterrows():
            pos = str(row.get("position", "—"))
            name = str(row.get("player_name", "—"))
            total = str(row.get("total", "—"))
            thru = str(row.get("thru", "—"))
            r1 = row.get("R1")
            r1_str = f"{int(r1):+d}" if pd.notna(r1) else "—"
            odds = _odds_str(row.get("odds_to_win"))
            lines.append(f"| {pos} | {name} | {total} | {thru} | {r1_str} | {odds} |")

        return "\n".join(lines)
    except Exception as e:
        return f"## MY PICKS — LIVE STATUS\n(unavailable: {e})"


def _live_sg_from_hole_scores(tid: str | None) -> str:
    """
    Derive approximate strokes gained from hole scores vs field average.
    Reads data/live/hole_scores_{tid_lower}.csv.
    For each completed hole, computes field average score, then each player's
    score relative to field (positive = gaining strokes vs field).
    Returns SG leaders and user's picks position.
    """
    if not tid:
        return ""
    tid_lower = tid.lower()
    path = DATA / "live" / f"hole_scores_{tid_lower}.csv"
    if not path.exists():
        return ""
    try:
        hs = pd.read_csv(path)
        if hs.empty:
            return ""

        # Hole columns h1..h18 (raw scores), h1_rel..h18_rel (vs par per hole)
        rel_cols = [f"h{i}_rel" for i in range(1, 19)]
        available = [c for c in rel_cols if c in hs.columns]
        if not available:
            return ""

        # Only use holes where at least 30% of the field has data
        usable = []
        for col in available:
            valid = hs[col].dropna()
            if len(valid) >= max(5, len(hs) * 0.30):
                usable.append(col)

        if not usable:
            return ""

        # Field average at each usable hole
        field_avgs = {col: float(hs[col].dropna().mean()) for col in usable}

        # Per-player SG proxy: sum of (field_avg - player_score) for each completed hole
        # Positive = player is gaining strokes vs field
        sg_rows = []
        for _, row in hs.iterrows():
            player = str(row.get("player_name", ""))
            total_sg = 0.0
            holes_counted = 0
            for col in usable:
                val = row.get(col)
                if pd.notna(val):
                    # SG = field_avg - player_score (lower score = gaining vs field)
                    total_sg += field_avgs[col] - float(val)
                    holes_counted += 1
            if holes_counted > 0 and player:
                sg_rows.append({
                    "player": player,
                    "sg_vs_field": round(total_sg, 2),
                    "holes": holes_counted,
                })

        if not sg_rows:
            return ""

        sg_df = pd.DataFrame(sg_rows).sort_values("sg_vs_field", ascending=False)
        n_holes = len(usable)

        lines = [
            f"## LIVE SG PROXY (hole scores vs field avg, {n_holes} holes)",
            "_Approximate strokes gained — positive = gaining vs field. Updates as holes complete._",
            "",
            "### Leaders (gaining most vs field)",
        ]
        lines.append("| Rank | Player | SG vs Field | Holes |")
        lines.append("|------|--------|-------------|-------|")
        for i, (_, r) in enumerate(sg_df.head(15).iterrows(), 1):
            sg = r["sg_vs_field"]
            lines.append(f"| {i} | {r['player']} | {sg:+.2f} | {r['holes']} |")

        # Highlight user's picks in the ranking
        pick_names = ["Schauffele", "DeChambeau", "Åberg", "Aberg"]
        pick_rows = sg_df[sg_df["player"].apply(
            lambda n: any(p.lower() in n.lower() for p in pick_names)
        )]
        if not pick_rows.empty:
            lines.append("")
            lines.append("### My Picks — SG Proxy Rank")
            lines.append("| Player | SG vs Field | Field Rank |")
            lines.append("|--------|-------------|------------|")
            for _, r in pick_rows.iterrows():
                rank = int(sg_df.index[sg_df["player"] == r["player"]].tolist()[0]) + 1
                # Get actual rank position
                rank = sg_df["sg_vs_field"].rank(ascending=False).loc[
                    sg_df["player"] == r["player"]
                ].iloc[0]
                lines.append(f"| {r['player']} | {r['sg_vs_field']:+.2f} | #{int(rank)} |")

        return "\n".join(lines)
    except Exception as e:
        return f"## LIVE SG PROXY\n(unavailable: {e})"


def _scoring_prop_block(tid: str | None, query: str = "", round_num: int | None = None) -> str:
    """
    Answer scoring prop questions using live tournament stats.

    Reads data/live/live_tournament_stats_{tid}.json (fetched every live refresh).
    Covers: birdie leaders, bogey-free, eagle leaders, fewest bogeys, scoring summary.

    round_num=None → cumulative totals across all completed rounds.
    round_num=N    → per-round stats for that specific round.
    """
    if not tid:
        return ""

    stats_path = DATA / "live" / f"live_tournament_stats_{tid}.json"
    if not stats_path.exists():
        return ""

    try:
        raw = json.loads(stats_path.read_text())
    except Exception:
        return ""

    player_map: dict[str, str] = raw.get("player_map", {})
    cats = raw.get("categories", {})
    scoring = cats.get("SCORING", {})

    # ── Choose per-round or cumulative data ───────────────────────────────────
    if round_num is not None:
        source = scoring.get("per_round", {}).get(str(round_num), {})
        scope_label = f"Round {round_num}"
    else:
        source = scoring.get("cumulative", {})
        scope_label = "Tournament (all rounds)"

    if not source:
        return f"## SCORING STATS\nNo scoring data available yet for {scope_label}.\n"

    # ── Build player rows ─────────────────────────────────────────────────────
    rows = []
    for pid, stats in source.items():
        if not isinstance(stats, dict):
            continue
        name = player_map.get(str(pid), f"Player {pid}")
        def _v(stat: str) -> int:
            val = stats.get(stat, {})
            if isinstance(val, dict):
                try: return int(float(val.get("value", 0) or 0))
                except: return 0
            try: return int(float(val or 0))
            except: return 0
        def _r(stat: str) -> str:
            val = stats.get(stat, {})
            if isinstance(val, dict):
                r = val.get("rank", "")
                return f"#{r}" if r else "—"
            return "—"
        rows.append({
            "pid":     pid,
            "name":    name,
            "birdies": _v("Birdies"),
            "pars":    _v("Pars"),
            "bogeys":  _v("Bogeys"),
            "doubles": _v("Double Bogeys"),
            "eagles":  _v("Eagles -"),
            "b_rank":  _r("Birdies"),
            "bog_rank":_r("Bogeys"),
        })

    if not rows:
        return ""

    df = pd.DataFrame(rows)

    # ── Detect query intent ───────────────────────────────────────────────────
    q = query.lower()
    is_birdie   = any(w in q for w in ["birdie", "birdies", "most birdie"])
    is_eagle    = any(w in q for w in ["eagle", "eagles"])
    is_bogey_free = any(w in q for w in ["bogey-free", "bogey free", "no bogey", "clean round", "bogey less"])
    is_fewest_bogey = any(w in q for w in ["fewest bogey", "least bogey", "avoid bogey", "fewest mistakes"])

    lines = [f"## SCORING STATS — {scope_label}"]
    lines.append(f"Source: PGA Tour live tournament stats ({len(df)} players tracked)\n")

    # ── Birdie leaders ────────────────────────────────────────────────────────
    birdie_top = df.nlargest(10, "birdies")[["name", "birdies", "b_rank", "bogeys", "eagles"]]
    lines.append("**Birdie Leaders:**")
    for _, r in birdie_top.iterrows():
        eagle_str = f" | {int(r['eagles'])} eagle{'s' if r['eagles']!=1 else ''}" if r["eagles"] > 0 else ""
        lines.append(
            f"  {r['name']:<25} {int(r['birdies'])} birdies {r['b_rank']}  "
            f"| {int(r['bogeys'])} bogeys{eagle_str}"
        )
    lines.append("")

    # ── Eagle leaders ─────────────────────────────────────────────────────────
    eagle_df = df[df["eagles"] > 0].sort_values("eagles", ascending=False)
    if not eagle_df.empty:
        lines.append("**Eagle leaders:**")
        for _, r in eagle_df.head(5).iterrows():
            lines.append(f"  {r['name']}: {int(r['eagles'])} eagle(s)")
        lines.append("")

    # ── Bogey-free / fewest bogeys ────────────────────────────────────────────
    bogey_free = df[df["bogeys"] == 0].sort_values("birdies", ascending=False)
    if not bogey_free.empty:
        names = ", ".join(bogey_free.head(8)["name"].tolist())
        lines.append(f"**Bogey-free ({scope_label}):** {names}\n")

    fewest = df.nsmallest(8, "bogeys")[["name", "bogeys", "birdies", "bog_rank"]]
    lines.append("**Fewest bogeys:**")
    for _, r in fewest.iterrows():
        lines.append(
            f"  {r['name']:<25} {int(r['bogeys'])} bogeys {r['bog_rank']}  "
            f"| {int(r['birdies'])} birdies"
        )
    lines.append("")

    # ── Scoring efficiency summary (birdies - bogeys) ─────────────────────────
    df["net"] = df["birdies"] - df["bogeys"] - (df["doubles"] * 2)
    net_top = df.nlargest(8, "net")[["name", "birdies", "bogeys", "eagles", "net"]]
    lines.append("**Best scoring efficiency (birdies − bogeys):**")
    for _, r in net_top.iterrows():
        eagle_str = f" + {int(r['eagles'])}E" if r["eagles"] > 0 else ""
        lines.append(
            f"  {r['name']:<25} +{int(r['birdies'])}B / -{int(r['bogeys'])}bog{eagle_str}  "
            f"(net {int(r['net']):+d})"
        )
    lines.append("")

    return "\n".join(lines)


def _round_recap_block(tid: str | None, round_num: int | None = None) -> str:
    """
    Narrative round recap for a completed or in-progress round.

    Covers: leaders, low round, field scoring avg, biggest movers (R2+),
    cut situation (R2), and user's picks. round_num=None auto-detects the
    most recently completed round from the live leaderboard.
    """
    if not tid:
        return ""

    _PAR = 72  # Augusta National

    # ── Load leaderboard ──────────────────────────────────────────────────────
    lb_path = DATA / "live" / f"leaderboard_{tid.lower()}.csv"
    if not lb_path.exists():
        return ""
    try:
        lb = pd.read_csv(lb_path)
    except Exception:
        return ""

    if lb.empty:
        return ""

    # ── Determine which round to recap ────────────────────────────────────────
    # Use the highest round column that has real data for most players
    round_cols = ["R1", "R2", "R3", "R4"]
    completed_rounds = []
    for col in round_cols:
        if col in lb.columns:
            n_valid = pd.to_numeric(lb[col], errors="coerce").notna().sum()
            if n_valid >= len(lb) * 0.5:  # at least half the field has a score
                completed_rounds.append(int(col[1]))

    if not completed_rounds:
        return (
            "## ROUND RECAP — DATA NOT AVAILABLE\n"
            "No round scoring data has been loaded into the system yet. "
            "DO NOT report any scores, positions, or leaders. "
            "Tell the user no round data is currently available.\n"
        )

    if round_num is None:
        round_num = completed_rounds[-1]
    elif round_num not in completed_rounds:
        latest = completed_rounds[-1]
        return (
            f"## ROUND {round_num} RECAP — DATA NOT AVAILABLE\n"
            f"Round {round_num} scoring data has not been loaded into the system yet. "
            f"Latest round with data: Round {latest}.\n"
            f"DO NOT report any Round {round_num} scores, positions, or leaders. "
            f"Tell the user the data is not yet available and offer to recap Round {latest} instead.\n"
        )

    r_col = f"R{round_num}"
    lb[r_col] = pd.to_numeric(lb[r_col], errors="coerce")

    # Only players who have a score for this round
    played = lb[lb[r_col].notna()].copy()
    if played.empty:
        return f"## ROUND {round_num} RECAP\nNo scoring data available.\n"

    played["r_to_par"] = played[r_col] - _PAR
    field_avg = float(played[r_col].mean())
    field_avg_to_par = field_avg - _PAR
    low_score = int(played[r_col].min())
    low_to_par = low_score - _PAR

    # ── Leaders after this round ──────────────────────────────────────────────
    # Use total_numeric for overall standing after round_num
    lb["total_numeric"] = pd.to_numeric(lb["total_numeric"], errors="coerce")
    leaders = lb.nsmallest(8, "total_numeric")[
        ["player_name", "position", "total_numeric", r_col]
    ].copy()

    # ── Low round scorers ─────────────────────────────────────────────────────
    low_round_players = played.nsmallest(5, r_col)[["player_name", r_col, "r_to_par"]].copy()

    # ── Biggest movers (R2+) ──────────────────────────────────────────────────
    movers_up = movers_dn = None
    if round_num >= 2 and "position_change" in lb.columns:
        lb["position_change"] = pd.to_numeric(lb["position_change"], errors="coerce")
        moved = lb[lb["position_change"].notna()].copy()
        if not moved.empty:
            movers_up = moved[moved["position_change"] > 0].nlargest(4, "position_change")[
                ["player_name", "position", "position_change", r_col, "total_numeric"]
            ]
            movers_dn = moved[moved["position_change"] < 0].nsmallest(4, "position_change")[
                ["player_name", "position", "position_change", r_col, "total_numeric"]
            ]

    # ── Cut situation (R2 only) ───────────────────────────────────────────────
    cut_info = ""
    if round_num == 2:
        meta_path = DATA / "live" / f"leaderboard_{tid.lower()}_meta.json"
        if meta_path.exists():
            try:
                import json as _json
                meta = _json.loads(meta_path.read_text())
                cut_proj = meta.get("cut_projection", {})
                proj_score = cut_proj.get("projected_cut_score")
                bubble = cut_proj.get("bubble_count", 0)
                safely_in = cut_proj.get("safely_in", 0)
                safely_out = cut_proj.get("safely_out", 0)
                if proj_score is not None:
                    cut_info = (
                        f"\n**Cut line:** Projected at {int(proj_score):+d} | "
                        f"{safely_in} safely in, {safely_out} safely out, {bubble} on the bubble"
                    )
            except Exception:
                pass

        # Fallback: use made_cut column if available
        if not cut_info and "made_cut" in lb.columns:
            made = lb["made_cut"].sum() if lb["made_cut"].dtype == bool else (lb["made_cut"] == True).sum()
            missed = len(lb) - made
            cut_info = f"\n**Cut:** {int(made)} made, {int(missed)} missed"

    # ── User picks status ─────────────────────────────────────────────────────
    picks_info = ""
    try:
        usage_path = DATA / "fantasy" / "usage_tracker_2026.json"
        if usage_path.exists():
            import json as _json2
            tracker = _json2.loads(usage_path.read_text())
            wl = tracker.get("weekly_lineups", {})

            def _wk_num(k: str) -> int:
                m = re.search(r"(\d+)", k)
                return int(m.group(1)) if m else 0

            if wl:
                latest_week = max(wl.keys(), key=_wk_num)
                picks = wl[latest_week].get("lineup", wl[latest_week].get("players", []))
                if picks:
                    pick_lines = []
                    for pick_name in picks:
                        # Match against leaderboard (First Last format)
                        row = lb[lb["player_name"].str.lower() == pick_name.lower()]
                        if row.empty:
                            # Try last name match
                            last = pick_name.split()[-1].lower()
                            row = lb[lb["player_name"].str.lower().str.contains(last, na=False)]
                        if not row.empty:
                            r = row.iloc[0]
                            pos = r.get("position", "?")
                            total = r.get("total_numeric", None)
                            rnd_score = r.get(r_col, None)
                            total_str = f"{int(total):+d}" if pd.notna(total) else "E"
                            rnd_to_par = int(rnd_score) - _PAR
                            rnd_str = (f"{rnd_to_par:+d}" if rnd_to_par != 0 else "E") if pd.notna(rnd_score) else "?"
                            pick_lines.append(
                                f"  {pick_name}: {pos} ({total_str} total, {rnd_str} today)"
                            )
                        else:
                            pick_lines.append(f"  {pick_name}: not found in leaderboard")
                    picks_info = "\n**Your picks:**\n" + "\n".join(pick_lines)
    except Exception:
        pass

    # ── Field snapshot ────────────────────────────────────────────────────────
    under_par = (played["r_to_par"] < 0).sum()
    at_par = (played["r_to_par"] == 0).sum()
    over_par = (played["r_to_par"] > 0).sum()

    # ── Format output ─────────────────────────────────────────────────────────
    sign = lambda n: f"{int(n):+d}" if n != 0 else "E"

    lines = [f"## ROUND {round_num} RECAP — {tid}"]
    lines.append(
        f"Par {_PAR} | Field avg: {field_avg:.1f} ({sign(field_avg_to_par)}) | "
        f"Low round: {low_score} ({sign(low_to_par)})"
    )
    lines.append(
        f"Under par: {int(under_par)} | At par: {int(at_par)} | Over par: {int(over_par)}"
    )
    if cut_info:
        lines.append(cut_info)
    lines.append("")

    lines.append(f"**Leaderboard after Round {round_num}:**")
    for _, row in leaders.iterrows():
        pos = row.get("position", "?")
        name = row["player_name"]
        total = row["total_numeric"]
        rnd = row[r_col]
        total_str = sign(total) if pd.notna(total) else "E"
        rnd_str = sign(rnd - _PAR) if pd.notna(rnd) else "?"
        lines.append(f"  {pos:<5} {name:<25} {total_str}  (R{round_num}: {rnd_str})")
    lines.append("")

    lines.append(f"**Low round of the day (Round {round_num}):**")
    for _, row in low_round_players.iterrows():
        lines.append(f"  {row['player_name']}: {int(row[r_col])} ({sign(row['r_to_par'])})")
    lines.append("")

    if movers_up is not None and not movers_up.empty:
        lines.append("**Biggest movers up:**")
        for _, row in movers_up.iterrows():
            rnd = row.get(r_col)
            rnd_str = sign(rnd - _PAR) if pd.notna(rnd) else "?"
            lines.append(
                f"  {row['player_name']}: +{int(row['position_change'])} spots → {row['position']} "
                f"({sign(row['total_numeric'])} total, {rnd_str} today)"
            )
        lines.append("")

    if movers_dn is not None and not movers_dn.empty:
        lines.append("**Biggest movers down:**")
        for _, row in movers_dn.iterrows():
            rnd = row.get(r_col)
            rnd_str = sign(rnd - _PAR) if pd.notna(rnd) else "?"
            lines.append(
                f"  {row['player_name']}: {int(row['position_change'])} spots → {row['position']} "
                f"({sign(row['total_numeric'])} total, {rnd_str} today)"
            )
        lines.append("")

    if picks_info:
        lines.append(picks_info)
        lines.append("")

    return "\n".join(lines)


def _leaderboard_age_minutes(tid: str) -> int | None:
    """Return how many minutes old the local leaderboard CSV is, or None if it doesn't exist."""
    import time as _time
    path = DATA / "live" / f"leaderboard_{tid.lower()}.csv"
    if not path.exists():
        return None
    return int((_time.time() - path.stat().st_mtime) / 60)


def _web_live_scores_block(tournament_name: str) -> str:
    """Search the web for a current leaderboard when local CSV data is stale.

    Used as a real-time fallback: if the scheduler hasn't refreshed in >60 min
    the model gets live scores from DuckDuckGo snippets rather than stale CSV data.
    Returns a formatted block to prepend to the system prompt.
    """
    if not tournament_name:
        return ""
    search_query = f"{tournament_name} leaderboard scores 2026 live"
    raw = _execute_web_search(search_query, max_results=4)
    if not raw or raw.startswith("Search failed") or raw.startswith("No results"):
        return ""
    return (
        "## WEB LIVE SCORES (real-time search — use this when local data is stale)\n"
        "The following web results contain the most current available leaderboard info. "
        "Scores, positions, and names come from third-party sources and may not be perfectly "
        "formatted — extract the key standings as best you can.\n\n"
        + raw
    )


def _live_leaderboard_block(tid: str) -> str:
    """Live leaderboard top 20. Only shown if at least 1 round is complete."""
    if not tid:
        return ""
    tid_lower = tid.lower()
    path = DATA / "live" / f"leaderboard_{tid_lower}.csv"
    if not path.exists():
        return ""
    try:
        # Freshness: how old is the data?
        import time as _time
        _age_min = int((_time.time() - path.stat().st_mtime) / 60)
        if _age_min > 90:
            _freshness = f"⚠️ DATA IS {_age_min} MINUTES OLD — may not reflect current standings"
        else:
            _freshness = f"Updated {_age_min} min ago"

        df = pd.read_csv(path)
        if df.empty:
            return ""

        meta_path = DATA / "live" / f"leaderboard_{tid_lower}_meta.json"
        rounds_complete = 0
        round_status = ""
        cut_info = ""
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                rounds_complete = int(meta.get("current_round", 0))
                round_status = meta.get("round_status", "")
                cp = meta.get("cut_projection", {})
                if cp:
                    cut_score = cp.get("projected_cut_score", "?")
                    bubble    = cp.get("bubble_count", "?")
                    cut_info  = (
                        f"\n\n## CUT PROJECTION: {cut_score:+d} | {bubble} players on bubble"
                        if isinstance(cut_score, int)
                        else f"\n\n## CUT PROJECTION: {cut_score} | {bubble} players on bubble"
                    )
            except Exception:
                pass

        if rounds_complete == 0:
            return cut_info

        df["player_name"] = df["player_name"].apply(_fmt_name)

        cols = ["position", "player_name", "total", "thru", "current_round"]
        preds_path = OUTPUTS / "latest_predictions.csv"
        if preds_path.exists():
            try:
                preds = pd.read_csv(preds_path, usecols=["player_name", "live_win_prob", "win_prob"])
                preds["player_name"] = preds["player_name"].apply(_fmt_name)
                df = df.merge(preds, on="player_name", how="left")
                df["live_win%"] = (df["live_win_prob"] * 100).round(1).astype(str) + "%"
                df["pre_win%"]  = (df["win_prob"] * 100).round(1).astype(str) + "%"
                cols += ["live_win%", "pre_win%"]
            except Exception:
                pass

        df = df.head(20)[[c for c in cols if c in df.columns]].copy()
        df.columns = [c.replace("_", " ").title() for c in df.columns]

        status_label = f" — {round_status}" if round_status else ""
        header = f"## LIVE LEADERBOARD — Round {rounds_complete} of 4{status_label} [{_freshness}]"
        return header + "\n" + df.to_markdown(index=False) + cut_info
    except Exception as e:
        return f"## LIVE LEADERBOARD\n(unavailable: {e})"


def _course_fit_reasoning_block(tid: str | None) -> str:
    """
    Data-driven course demand reasoning: what skills historically win at this venue.
    Loads hole data (current year first, then historical fallback).
    Derives: hardest holes, birdie holes, par-3 difficulty, finish strength needed.
    """
    if not tid:
        return ""

    year = datetime.now().year
    course_df = None

    # 1. Try current year file
    cur_path = DATA / "course_characteristics" / f"all_courses_{year}.csv"
    if cur_path.exists():
        try:
            df = pd.read_csv(cur_path)
            subset = df[df["tournament_id"] == tid]
            if not subset.empty:
                course_df = subset.copy()
        except Exception:
            pass

    # 2. Fallback to historical file (same course, different year)
    if course_df is None or course_df.empty:
        hist_path = DATA / "course_characteristics" / "all_courses_historical_2023_2025.csv"
        if hist_path.exists():
            try:
                df = pd.read_csv(hist_path)
                # Match by tournament_id pattern (e.g. R2026011 → R2023011)
                base_id = tid[-3:]  # last 3 chars = event number e.g. "011"
                mask = df["tournament_id"].astype(str).str.endswith(base_id)
                subset = df[mask]
                if not subset.empty:
                    # Average across years for more stable estimates
                    course_df = subset.groupby("hole_num", as_index=False).agg(
                        hole_par=("hole_par", "first"),
                        hole_yards=("hole_yards", "mean"),
                        scoring_avg=("scoring_avg", "mean"),
                        scoring_diff=("scoring_diff", "mean"),
                    )
                    # Get course name from most recent year
                    course_name = df[mask]["course_name"].iloc[-1] if "course_name" in df.columns else ""
                    tournament_name = df[mask]["tournament_name"].iloc[-1] if "tournament_name" in df.columns else tid
            except Exception:
                pass

    if course_df is None or course_df.empty:
        return ""

    try:
        h = course_df.copy()
        if "course_name" not in locals():
            course_name = h.get("course_name", pd.Series([""])).iloc[0] if "course_name" in h.columns else ""
            tournament_name = h.get("tournament_name", pd.Series([tid])).iloc[0] if "tournament_name" in h.columns else tid

        par_counts = h.groupby("hole_par")["hole_num"].count()
        n_par3 = int(par_counts.get(3, 0))
        n_par4 = int(par_counts.get(4, 0))
        n_par5 = int(par_counts.get(5, 0))
        course_par = int(h["hole_par"].sum()) if len(h) == 18 else 72

        # Scoring stats by par type
        par3_avg_diff = h[h["hole_par"] == 3]["scoring_diff"].mean()
        par4_avg_diff = h[h["hole_par"] == 4]["scoring_diff"].mean()
        par5_avg_diff = h[h["hole_par"] == 5]["scoring_diff"].mean()

        # Hardest 3 holes (highest scoring_diff = most over par)
        hardest = h.nlargest(3, "scoring_diff")[["hole_num", "hole_par", "hole_yards", "scoring_diff"]]
        # Best birdie holes (lowest scoring_diff = most under par)
        birdie_holes = h.nsmallest(3, "scoring_diff")[["hole_num", "hole_par", "hole_yards", "scoring_diff"]]

        # Finish strength: how hard is the closing stretch (last 4 holes)?
        last4 = h[h["hole_num"] >= 15]["scoring_diff"].mean() if len(h[h["hole_num"] >= 15]) >= 3 else None

        lines = [f"## COURSE FIT REASONING: {tournament_name} ({course_name or tid})"]
        lines.append(f"Par {course_par} | {n_par3} par-3s, {n_par4} par-4s, {n_par5} par-5s | Data averaged from 2023–2025")
        lines.append("")

        # Par-type difficulty
        lines.append("**What this course demands (by the numbers):**")
        if pd.notna(par3_avg_diff):
            p3_desc = "hard — above-par scoring" if par3_avg_diff > 0.05 else ("easy — birdie opportunities" if par3_avg_diff < -0.05 else "neutral")
            lines.append(f"- Par 3s ({n_par3} holes): avg {par3_avg_diff:+.3f} vs par — {p3_desc}. Iron precision from the tee is {'critical' if par3_avg_diff > 0.05 else 'less of a factor'}.")
        if pd.notna(par4_avg_diff):
            p4_desc = "penal — mistakes are punished" if par4_avg_diff > 0.08 else ("scoring opportunities" if par4_avg_diff < 0 else "neutral")
            lines.append(f"- Par 4s ({n_par4} holes): avg {par4_avg_diff:+.3f} vs par — {p4_desc}. {'Accuracy and scrambling matter here.' if par4_avg_diff > 0.05 else ''}")
        if pd.notna(par5_avg_diff):
            p5_desc = "birdie opportunities — must convert" if par5_avg_diff < -0.15 else ("difficult par 5s" if par5_avg_diff > 0 else "modest birdie holes")
            lines.append(f"- Par 5s ({n_par5} holes): avg {par5_avg_diff:+.3f} vs par — {p5_desc}.")

        # Hardest holes
        lines.append("")
        lines.append("**Hardest holes (where tournaments are lost):**")
        for _, row in hardest.iterrows():
            lines.append(f"- Hole {int(row['hole_num'])} (Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): avg {row['scoring_diff']:+.3f} vs par")

        # Birdie holes
        lines.append("")
        lines.append("**Birdie opportunities (where tournaments are won):**")
        for _, row in birdie_holes.iterrows():
            lines.append(f"- Hole {int(row['hole_num'])} (Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): avg {row['scoring_diff']:+.3f} vs par")

        # Closing stretch
        if pd.notna(last4):
            close_desc = "brutal finish" if last4 > 0.15 else ("demanding" if last4 > 0.05 else "manageable")
            lines.append("")
            lines.append(f"**Closing stretch (holes 15–18)**: avg {last4:+.3f} vs par — {close_desc}. {'Closing ability and nerves are decisive.' if last4 > 0.05 else ''}")

        # Derived skill requirements
        lines.append("")
        lines.append("**KEY SKILL REQUIREMENTS derived from scoring data:**")
        if par3_avg_diff > 0.05:
            lines.append(f"- IRON PLAY FROM THE TEE: par 3s average +{par3_avg_diff:.3f} — players who miss par-3 greens bleed bogeys. Par-3 field rank is a direct predictor here.")
        if par4_avg_diff > 0.06:
            lines.append(f"- SCRAMBLING & SHORT GAME: par 4s average +{par4_avg_diff:.3f} — greens are missed regularly; recovery skill separates the field. Around-green SG and scrambling % are critical.")
        if par5_avg_diff < -0.15:
            lines.append(f"- PAR-5 CONVERSION: par 5s average {par5_avg_diff:.3f} — players who can't birdie the par 5s fall behind. Par-5 scoring rank matters.")
        if last4 and last4 > 0.10:
            lines.append(f"- CLOSING ABILITY: the final 4 holes average +{last4:.3f} — players who can't close the back nine fade. R4 scoring average is a key predictor.")

        result = "\n".join(lines)
        _decomp = _dg_decompositions_block(tid)
        if _decomp:
            result = result + "\n\n" + _decomp
        return result
    except Exception as e:
        return f"## COURSE FIT REASONING\n(unavailable: {e})"


def _course_fit_players_block(tid: str | None, top_n: int = 12) -> str:
    """Map field players to course demands derived from hole scoring data.

    For each key skill requirement (iron play, scrambling, par-5 conversion, closing),
    show the top 5 players in the field ranked by that specific stat.
    Only emits sections for demands that are clearly present at this course.
    """
    if not tid:
        return ""

    # Need course demand data first
    year = datetime.now().year
    course_df = None

    cur_path = DATA / "course_characteristics" / f"all_courses_{year}.csv"
    if cur_path.exists():
        try:
            df = pd.read_csv(cur_path)
            subset = df[df["tournament_id"] == tid]
            if not subset.empty:
                course_df = subset.copy()
        except Exception:
            pass

    if course_df is None or course_df.empty:
        hist_path = DATA / "course_characteristics" / "all_courses_historical_2023_2025.csv"
        if hist_path.exists():
            try:
                df = pd.read_csv(hist_path)
                base_id = tid[-3:]
                mask = df["tournament_id"].astype(str).str.endswith(base_id)
                subset = df[mask]
                if not subset.empty:
                    course_df = subset.groupby("hole_num", as_index=False).agg(
                        hole_par=("hole_par", "first"),
                        scoring_diff=("scoring_diff", "mean"),
                    )
            except Exception:
                pass

    preds_path = OUTPUTS / "latest_predictions.csv"
    if not preds_path.exists():
        return ""

    try:
        preds = pd.read_csv(preds_path)
        preds["player_name"] = preds["player_name"].apply(_fmt_name)
        preds = preds.sort_values("win_prob", ascending=False).head(top_n).copy()

        sections = ["## COURSE FIT — TOP PLAYERS BY SKILL DEMAND"]

        # Determine demands from hole data if available
        demands = {}
        if course_df is not None and not course_df.empty:
            h = course_df
            par3_diff = h[h["hole_par"] == 3]["scoring_diff"].mean() if "hole_par" in h.columns else None
            par4_diff = h[h["hole_par"] == 4]["scoring_diff"].mean() if "hole_par" in h.columns else None
            par5_diff = h[h["hole_par"] == 5]["scoring_diff"].mean() if "hole_par" in h.columns else None
            last4_diff = h[h["hole_num"] >= 15]["scoring_diff"].mean() if "hole_num" in h.columns and len(h[h["hole_num"] >= 15]) >= 3 else None

            if par3_diff is not None and par3_diff > 0.05:
                demands["iron_play"] = ("SG Approach (Iron Play from Tee)", "season_sg_app_field_rank", "season_sg_app", par3_diff, "par-3")
            if par4_diff is not None and par4_diff > 0.06:
                demands["scrambling"] = ("Around-Green / Scrambling", "season_sg_arg_field_rank", "season_sg_arg", par4_diff, "par-4")
            if par5_diff is not None and par5_diff < -0.15:
                demands["par5"] = ("Par-5 Conversion (Distance + Power)", "season_sg_ott_field_rank", "season_sg_ott", par5_diff, "par-5")
            if last4_diff is not None and last4_diff > 0.10:
                demands["closing"] = ("Closing Ability (R4 Scoring)", "recent_r4_avg_field_pct", "recent_r4_avg", last4_diff, "finish")

        # Always include overall SG and approach as a baseline
        if "iron_play" not in demands:
            demands["approach"] = ("SG Approach (Iron Play)", "season_sg_app_field_rank", "season_sg_app", None, "overall")
        demands["sg_total"] = ("Overall Strokes Gained (Total)", "season_sg_total_field_rank", "season_sg_total", None, "overall")
        demands["putting"] = ("Putting (SG Putt)", "season_sg_putt_field_rank", "season_sg_putt", None, "putting")
        demands["course_history"] = ("Course History", "hist_times_played", "hist_avg_finish", None, "history")

        for key, (label, rank_col, val_col, diff, hole_type) in demands.items():
            diff_str = f" (course demands: {diff:+.3f} avg vs par on {hole_type}s)" if diff is not None else ""
            sections.append(f"\n**{label}**{diff_str}:")

            if key == "course_history":
                # Sort by most starts + best avg finish
                sub = preds.copy()
                sub["_starts"] = sub.get("hist_times_played", pd.Series(0, index=sub.index)).fillna(0)
                sub["_avg"]    = sub.get("hist_avg_finish",   pd.Series(999, index=sub.index)).fillna(999)
                sub = sub[sub["_starts"] >= 1].sort_values(["_starts", "_avg"], ascending=[False, True]).head(5)
                for _, row in sub.iterrows():
                    starts = int(row.get("hist_times_played", 0) or 0)
                    wins   = int(row.get("hist_wins", 0) or 0)
                    avg_f  = row.get("hist_avg_finish")
                    avg_s  = row.get("hist_avg_finish")
                    win_str = " · WON here" if wins else ""
                    avg_str = f" · avg finish T{int(float(avg_s))}" if pd.notna(avg_s) else ""
                    sections.append(f"  - {row['player_name']}: {starts} start{'s' if starts != 1 else ''}{win_str}{avg_str}")
            elif key == "closing":
                # Sort by R4 scoring (best R4 field pct = highest pct value)
                sub = preds.copy()
                if "recent_r4_avg_field_pct" in sub.columns:
                    sub = sub.dropna(subset=["recent_r4_avg_field_pct"]).sort_values("recent_r4_avg_field_pct", ascending=False).head(5)
                    for _, row in sub.iterrows():
                        r4_val = row.get("recent_r4_avg")
                        r4_pct = float(row["recent_r4_avg_field_pct"])
                        val_str = f" (avg R4: {float(r4_val):+.1f}/round)" if pd.notna(r4_val) else ""
                        pct_str = f" #{int(r4_pct * len(preds))} in field" if pd.notna(r4_pct) else ""
                        sections.append(f"  - {row['player_name']}{val_str}{pct_str}")
                else:
                    sections.append("  (R4 data not available)")
            else:
                # Sort by rank column (ascending = better rank = #1 is best)
                if rank_col in preds.columns:
                    sub = preds.dropna(subset=[rank_col]).sort_values(rank_col, ascending=True).head(5)
                    for _, row in sub.iterrows():
                        rank = row.get(rank_col)
                        val  = row.get(val_col)
                        rank_str = f"#{int(rank)} in field" if pd.notna(rank) else ""
                        val_str  = f"{float(val):+.3f} SG/round" if pd.notna(val) else ""
                        combined = " · ".join(filter(None, [val_str, rank_str]))
                        sections.append(f"  - {row['player_name']}: {combined}")
                else:
                    sections.append(f"  ({rank_col} not available in data)")

        return "\n".join(sections)
    except Exception as e:
        return f"## COURSE FIT — TOP PLAYERS BY SKILL\n(unavailable: {e})"


_MARKET_LABELS = {
    "outright":    "Win",
    "top5":        "Top 5",
    "top10":       "Top 10",
    "top20":       "Top 20",
    "top30":       "Top 30",
    "make_cut":    "Make Cut",
    "miss_cut":    "Miss Cut",
    "group_winner": "3-Ball Win",
    "h2h":         "Matchup (H2H)",
    "h2h_r1":      "Rd1 Matchup",
    "r2_leader":   "R2 Leader",
}


def _recommended_bets_block(top_n: int = 10) -> str:
    """Top recommended bets — player-case-first format.

    Each bet card leads with the player rationale (SG, course fit, form),
    then confirms the price. The LLM should present bets in the same order:
    why the player, then why the odds are good.
    """
    tid = _detect_tournament_id()
    live_path   = (DATA / "odds" / f"recommended_bets_live_{tid}.csv") if tid else None
    static_path = DATA / "odds" / "recommended_bets_latest.csv"

    is_live = bool(live_path and live_path.exists())
    path    = live_path if is_live else static_path

    if not path or not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df = df[df["status"] == "priced"].copy() if "status" in df.columns else df
        _sb  = "kelly_fraction" if "kelly_fraction" in df.columns else "edge_pts"
        df   = df.sort_values(_sb, ascending=False).head(top_n)
        if df.empty:
            return ""

        source_label = "LIVE (mid-tournament)" if is_live else "pre-tournament"
        lines = [
            f"## BET RECOMMENDATIONS ({source_label})",
            "IMPORTANT: When presenting these bets, lead with WHY the player fits "
            "(their SG strengths, course history, recent form) and use the edge/odds "
            "as confirmation — never lead with the edge number.",
            "",
        ]

        for _, row in df.iterrows():
            player  = _fmt_name(str(row.get("player_name", "?")))
            mkt     = _MARKET_LABELS.get(str(row.get("market", "")).lower(),
                                          str(row.get("market", "")).replace("_","").title())
            odds    = _fmt_odds(row.get("odds_american"))
            book    = str(row.get("book", "") or "")
            mp      = float(pd.to_numeric(row.get("model_prob"), errors="coerce") or 0) * 100
            bp      = float(pd.to_numeric(row.get("book_prob"),  errors="coerce") or 0) * 100
            edge    = float(pd.to_numeric(row.get("edge_pts"),   errors="coerce") or 0)
            kelly   = float(pd.to_numeric(row.get("kelly_fraction"), errors="coerce") or 0)
            conf    = float(pd.to_numeric(row.get("confidence"),     errors="coerce") or 0)

            book_str  = f" ({book})" if book else ""
            kelly_str = f"  Kelly: {kelly*100:.1f}%" if kelly > 0 else ""
            conf_str  = f"  Conf: {conf:.0%}" if conf > 0 else ""

            lines.append(f"### {player} — {mkt} {odds}{book_str}")
            lines.append(f"Model: {mp:.1f}%  Book: {bp:.1f}%  Edge: +{edge:.1f}pp{kelly_str}{conf_str}")

            # Reasoning bullets — player case first
            raw = str(row.get("reasoning", "") or "").strip()
            if raw:
                bullets = [b.strip() for b in raw.split("|") if b.strip()]
                for b in bullets[:5]:
                    lines.append(f"  - {b}")
            lines.append("")

        lines.append(
            "Market key: Win=outright; Top10/20=finish in top 10/20; Make Cut=survives cut; "
            "H2H/Matchup=beats paired opponent; 3-Ball=beats specific 3-ball group."
        )
        return "\n".join(lines)
    except Exception as e:
        return f"## BET RECOMMENDATIONS\n(unavailable: {e})"


def _tournament_intel_block(tid: str | None, tournament_name: str = "") -> str:
    """
    Tournament intel block: curated facts + computed historical stats.

    Reads data/tournament_facts/facts.json for curated entries, then
    computes real stats from leaderboards_*.csv (winners, cut rates, experience).
    Returns a markdown block ready for injection into the LLM system prompt.
    """
    lines = ["## TOURNAMENT INTEL"]

    # ── Curated facts from JSON ───────────────────────────────────────────────
    facts_path = DATA / "tournament_facts" / "facts.json"
    curated_facts: list[dict] = []
    if facts_path.exists():
        try:
            data = json.loads(facts_path.read_text())
            tid_upper = (tid or "").strip().upper()
            name_lower = (tournament_name or "").strip().lower()
            for entry in data.get("tournaments", []):
                matched = False
                if entry.get("id") and entry["id"].upper() == tid_upper:
                    matched = True
                if not matched:
                    for pat in entry.get("name_patterns", []):
                        if pat.lower() in name_lower:
                            matched = True
                            break
                if matched:
                    curated_facts = entry.get("facts", [])
                    break
        except Exception:
            pass

    if curated_facts:
        lines.append("\n### Key Tournament Facts")
        for f in curated_facts:
            lines.append(f"- **{f.get('stat','')}**: {f.get('detail','')}")

    # ── Computed historical stats from leaderboard data ───────────────────────
    if not tid:
        return "\n".join(lines)

    event_suffix = tid[-3:]
    hist_dir = DATA / "historical"
    all_rows: list[pd.DataFrame] = []
    for f in sorted(hist_dir.glob("leaderboards_20*.csv")):
        try:
            df = pd.read_csv(f, low_memory=False)
            mask = df["tournament_id"].astype(str).str.endswith(event_suffix)
            chunk = df[mask].copy()
            if not chunk.empty:
                # Extract year from filename
                yr = int(re.search(r"(\d{4})", f.stem).group(1))
                chunk["_year"] = yr
                all_rows.append(chunk)
        except Exception:
            continue

    if not all_rows:
        return "\n".join(lines)

    hist = pd.concat(all_rows, ignore_index=True)

    def _parse_tp(v) -> float | None:
        s = str(v).strip().upper()
        if s in ("E", "EVEN", "PAR"):
            return 0.0
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    hist["_tp"] = hist["to_par"].apply(_parse_tp)
    hist["_made_cut"] = ~hist["position"].astype(str).str.strip().isin(["CUT", "MC", "WD", "DQ"])

    winners = hist[hist["position"].astype(str).str.strip() == "1"].sort_values("_year")
    total_editions = hist["_year"].nunique()
    total_players = len(hist)
    made_cut_count = hist["_made_cut"].sum()

    lines.append(f"\n### Computed Historical Stats ({hist['_year'].min()}–{hist['_year'].max()}, {total_editions} editions)")

    # Winners table
    if not winners.empty:
        lines.append("\n**Past Winners:**")
        lines.append("| Year | Winner | Score |")
        lines.append("|------|--------|-------|")
        for _, w in winners.sort_values("_year", ascending=False).iterrows():
            tp = w["_tp"]
            tp_str = f"{int(tp):+d}" if tp is not None and not pd.isna(tp) else "—"
            lines.append(f"| {int(w['_year'])} | {_fmt_name(str(w['player_name']))} | {tp_str} |")

    # Winning score range
    if not winners["_tp"].isna().all():
        avg_win = winners["_tp"].dropna().mean()
        min_win = winners["_tp"].dropna().min()
        max_win = winners["_tp"].dropna().max()
        lines.append(f"\n**Winning score:** avg {avg_win:.1f} to par | range {int(max_win):+d} to {int(min_win):+d}")

    # Cut rate
    cut_rate = made_cut_count / total_players * 100 if total_players > 0 else 0
    lines.append(f"**Cut rate:** {cut_rate:.0f}% of the field makes the cut ({int(made_cut_count)}/{total_players} player-starts)")

    # Multi-time winners
    multi = winners.groupby("player_name").size().sort_values(ascending=False)
    multi_winners = multi[multi >= 2]
    if not multi_winners.empty:
        lines.append("\n**Multiple winners at this event:**")
        for name, cnt in multi_winners.items():
            lines.append(f"- {_fmt_name(str(name))}: {cnt} wins")

    # Course experience leaders in current field
    preds_path = OUTPUTS / "latest_predictions.csv"
    if preds_path.exists():
        try:
            preds = pd.read_csv(preds_path, usecols=["player_name", "player_id", "win_prob", "odds_to_win"])
            field_names = set(preds["player_name"].dropna().tolist())

            def _nkey(n: str) -> str:
                n = str(n).strip().lower()
                if "," in n:
                    last, first = n.split(",", 1)
                    return f"{first.strip()} {last.strip()}"
                return n

            exp = hist.groupby("player_name").agg(
                starts=("_year", "count"),
                wins=("position", lambda x: sum(str(v).strip() == "1" for v in x)),
                top5=("position", lambda x: sum(str(v).strip() in ["1","2","3","4","5","T2","T3","T4","T5"] for v in x)),
                avg_tp=("_tp", "mean"),
            ).reset_index()
            exp["_nkey"] = exp["player_name"].apply(_nkey)
            field_nkeys = {_nkey(n) for n in field_names}
            in_field = exp[exp["_nkey"].isin(field_nkeys)].sort_values("starts", ascending=False)

            if not in_field.empty:
                lines.append(f"\n**This week's field — Augusta/course experience:**")
                lines.append(f"{len(in_field)} players in this field have prior starts at this event.")
                veterans = in_field[in_field["starts"] >= 3]
                if not veterans.empty:
                    lines.append(f"{len(veterans)} players have 3+ prior starts (veterans).")
                    lines.append("| Player | Starts | Wins | Top-5s | Avg Score |")
                    lines.append("|--------|--------|------|--------|-----------|")
                    for _, r in veterans.head(15).iterrows():
                        avg = f"{r['avg_tp']:.1f}" if not pd.isna(r["avg_tp"]) else "—"
                        name_disp = _fmt_name(str(r["player_name"]))
                        lines.append(f"| {name_disp} | {int(r['starts'])} | {int(r['wins'])} | {int(r['top5'])} | {avg} |")
        except Exception:
            pass

    return "\n".join(lines)


def _web_intel_player_block(player_names: list[str], tid: str | None) -> str:
    """Pull pre-computed web intel for specific players from data/intel/tournament_intel_R{tid}.json."""
    if not tid or not player_names:
        return ""
    path = DATA / "intel" / f"tournament_intel_{tid}.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ""

    players = data.get("players", [])
    # Build lookup: normalize both sides to "first last" lowercase for matching
    def _norm(n: str) -> str:
        n = str(n).strip().lower()
        if ", " in n:
            last, first = n.split(", ", 1)
            return f"{first} {last}"
        return n

    lookup = {_norm(p["player_name"]): p for p in players if "player_name" in p}

    lines = ["## WEB INTEL (pre-tournament agent)"]
    found = False
    for name in player_names:
        record = lookup.get(_norm(name))
        if not record or "error" in record:
            continue
        found = True
        lines.append(f"\n### {_fmt_name(record['player_name'])}")
        if record.get("injury_flag"):
            lines.append(f"INJURY ALERT: {record.get('injury_detail', 'injury reported')}")
        sentiment_label = {"positive": "trending positive", "negative": "trending negative"}.get(
            record.get("sentiment", ""), "neutral"
        )
        lines.append(f"Sentiment: {sentiment_label}")
        if record.get("recent_form_summary"):
            lines.append(f"Form: {record['recent_form_summary']}")
        if record.get("key_quote"):
            lines.append(f'Quote: "{record["key_quote"]}"')

    if not found:
        return ""

    generated_at = data.get("generated_at", "")
    if generated_at:
        lines.append(f"\n_Intel generated: {generated_at[:10]}_")

    return "\n".join(lines)


def _web_intel_alerts_block(tid: str | None) -> str:
    """Compact injury + course conditions block for bet/general queries."""
    if not tid:
        return ""
    path = DATA / "intel" / f"tournament_intel_{tid}.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ""

    lines = ["## WEB INTEL ALERTS"]

    # Injury flags
    injured = [
        p for p in data.get("players", [])
        if p.get("injury_flag") and "error" not in p
    ]
    if injured:
        lines.append("\n### Injury / Withdrawal Flags")
        for p in injured:
            name = _fmt_name(p["player_name"])
            detail = p.get("injury_detail") or "injury reported"
            lines.append(f"- **{name}**: {detail}")
    else:
        lines.append("\nNo injury flags among top predicted players.")

    # Negative sentiment players (excluding injured — already listed)
    injured_names = {p["player_name"] for p in injured}
    negative = [
        p for p in data.get("players", [])
        if p.get("sentiment") == "negative" and p["player_name"] not in injured_names
        and "error" not in p
    ]
    if negative:
        lines.append("\n### Negative Form Signals")
        for p in negative[:3]:
            lines.append(f"- **{_fmt_name(p['player_name'])}**: {p.get('recent_form_summary', '')}")

    # Course conditions
    course = data.get("course_conditions", {})
    if course and "error" not in course:
        lines.append("\n### Course Conditions")
        if course.get("rough_length"):
            lines.append(f"- Rough: {course['rough_length']}")
        if course.get("green_speed"):
            lines.append(f"- Greens: {course['green_speed']}")
        if course.get("setup_notes"):
            lines.append(f"- Setup: {course['setup_notes']}")
        if course.get("scoring_outlook"):
            lines.append(f"- Scoring outlook: {course['scoring_outlook']}")

    generated_at = data.get("generated_at", "")
    if generated_at:
        lines.append(f"\n_Intel generated: {generated_at[:10]}_")

    return "\n".join(lines)


def _course_profile_block(tid: str) -> str:
    """Course summary + hardest/easiest holes."""
    if not tid:
        return ""
    tid_lower = tid.lower()
    year = datetime.now().year
    hole_path    = DATA / "course_characteristics" / f"{tid_lower}_{year}.csv"
    profile_path = DATA / "course_characteristics" / f"{tid_lower}_{year}_profiles.csv"
    lines = []

    if profile_path.exists():
        try:
            p = pd.read_csv(profile_path).iloc[0]
            course  = p.get("course_name", "")
            par     = int(p.get("course_par", 72))
            yardage = p.get("course_yardage", "")
            scoring = float(p.get("total_scoring_avg", 0))
            birdie  = float(p.get("birdie_pct", 0))
            bogey   = float(p.get("bogey_pct", 0))
            p3      = int(p.get("par3_count", 0))
            p4      = int(p.get("par4_count", 0))
            p5      = int(p.get("par5_count", 0))
            lines.append(f"## COURSE PROFILE: {course}")
            lines.append(f"Par {par} | {yardage} yards | {p3} par-3s, {p4} par-4s, {p5} par-5s")
            lines.append(f"Field scoring avg: {scoring:.3f} | Birdie rate: {birdie:.1f}% | Bogey rate: {bogey:.1f}%")
        except Exception as e:
            lines.append(f"## COURSE PROFILE\n(unavailable: {e})")

    if hole_path.exists():
        try:
            h = pd.read_csv(hole_path).sort_values("difficulty_rank")
            hardest = h.head(3)
            easiest = h.tail(3).sort_values("difficulty_rank", ascending=False)

            def _hole_str(row) -> str:
                return (
                    f"  Hole {int(row['hole_num'])} "
                    f"(Par {int(row['hole_par'])}, {int(row['hole_yards'])} yds): "
                    f"avg {row['scoring_avg']:.3f} ({row['scoring_diff']:+.3f} vs par)"
                )

            lines.append("\nHardest holes:")
            for _, r in hardest.iterrows():
                lines.append(_hole_str(r))
            lines.append("\nEasiest holes (birdie chances):")
            for _, r in easiest.iterrows():
                lines.append(_hole_str(r))
        except Exception:
            pass

    return "\n".join(lines) if lines else ""


def _expert_picks_block() -> str:
    """Expert consensus — full lineups, consensus counts, winner picks, and comments."""
    path = DATA / "expert_picks" / "expert_picks_latest.csv"
    if not path.exists():
        return ""
    try:
        import ast as _ast
        df = pd.read_csv(path)
        if df.empty:
            return ""

        def _parse_names(val) -> list[str]:
            if pd.isna(val) or str(val).strip() in ("", "[]"):
                return []
            try:
                parsed = _ast.literal_eval(str(val))
                if isinstance(parsed, list):
                    return [_fmt_name(n) for n in parsed if n]
            except Exception:
                pass
            return [_fmt_name(n.strip()) for n in str(val).split(",") if n.strip()]

        # Build consensus: count appearances across all starter + bench lineups
        from collections import Counter
        appearance_counts: Counter = Counter()
        winner_counts: Counter = Counter()
        n_experts = len(df)

        for _, row in df.iterrows():
            starters = _parse_names(row.get("lineup_player_names", ""))
            bench    = _parse_names(row.get("bench_player_names", ""))
            for p in starters + bench:
                appearance_counts[p] += 1
            winner = _fmt_name(str(row.get("winner_name", "") or ""))
            if winner:
                winner_counts[winner] += 1

        lines = ["## EXPERT CONSENSUS"]
        lines.append(f"({n_experts} experts — PGA Tour fantasy analysts)")
        lines.append("")

        # Consensus table: players named by 2+ experts
        top_consensus = [(p, c) for p, c in appearance_counts.most_common(15) if c >= 2]
        if top_consensus:
            lines.append("### Most-Selected Players (starter + bench appearances)")
            for player, count in top_consensus:
                wins = winner_counts.get(player, 0)
                win_str = f" | winner pick: {wins}/{n_experts}" if wins else ""
                lines.append(f"- {player}: {count}/{n_experts} experts{win_str}")
            lines.append("")

        # Winner picks summary
        if winner_counts:
            lines.append("### Winner Picks")
            for player, count in winner_counts.most_common():
                lines.append(f"- {player}: {count}/{n_experts} experts")
            lines.append("")

        # Individual expert lineups
        lines.append("### Individual Expert Lineups")
        for _, row in df.iterrows():
            expert  = str(row.get("expert_name", "?"))
            starters = _parse_names(row.get("lineup_player_names", ""))
            bench    = _parse_names(row.get("bench_player_names", ""))
            winner   = _fmt_name(str(row.get("winner_name", "") or ""))
            comment  = str(row.get("comment", "") or "").strip()
            short    = comment[:150] + "…" if len(comment) > 150 else comment
            starters_str = ", ".join(starters) if starters else "—"
            bench_str    = ", ".join(bench)    if bench    else "—"
            lines.append(f"**{expert}** — winner: {winner}")
            lines.append(f"  Starters: {starters_str}")
            if bench:
                lines.append(f"  Bench: {bench_str}")
            if short:
                lines.append(f"  \"{short}\"")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"## EXPERT CONSENSUS\n(unavailable: {e})"


def _power_rankings_block() -> str:
    """Model power rankings — top 20 players tiered by win probability."""
    try:
        preds_path = OUTPUTS / "latest_predictions.csv"
        if not preds_path.exists():
            return ""
        df = pd.read_csv(preds_path)
        prob_col = "win_prob_calibrated" if "win_prob_calibrated" in df.columns else "win_prob"
        df[prob_col] = pd.to_numeric(df[prob_col], errors="coerce")
        df = df[df[prob_col].notna()].sort_values(prob_col, ascending=False).head(20).reset_index(drop=True)
        if df.empty:
            return ""

        lines = ["## MODEL POWER RANKINGS (top 20 by win probability)"]
        tiers = {1: "TIER 1 — Contenders", 5: "TIER 2 — Strong plays", 11: "TIER 3 — Value range"}
        for i, (_, row) in enumerate(df.iterrows(), 1):
            if i in tiers:
                lines.append(f"\n### {tiers[i]}")
            name     = _fmt_name(str(row.get("player_name", "?")))
            win_pct  = float(row[prob_col]) * 100
            t10_pct  = float(pd.to_numeric(row.get("top10_prob"), errors="coerce") or 0) * 100
            wr_raw   = pd.to_numeric(row.get("world_rank"), errors="coerce")
            sg_raw   = pd.to_numeric(row.get("sg_total"), errors="coerce")
            odds_raw = pd.to_numeric(row.get("odds_to_win"), errors="coerce")

            wr_str   = f"WR#{int(wr_raw)}" if pd.notna(wr_raw) and wr_raw < 400 else ""
            sg_str   = f"SG {sg_raw:+.2f}" if pd.notna(sg_raw) else ""
            odds_str = f"({int(odds_raw):+d})" if pd.notna(odds_raw) and odds_raw != 0 else ""
            meta     = "  ".join(s for s in [wr_str, sg_str, odds_str] if s)

            lines.append(f"{i:2}. {name} — Win {win_pct:.1f}%  Top-10 {t10_pct:.0f}%  {meta}")

        return "\n".join(lines)
    except Exception:
        return ""


def _lineup_eligible_block(tid: str | None) -> str:
    """Pre-filtered eligible player list for lineup decisions.

    Pulls the confirmed field CSV, removes withdrawn players, cross-references
    usage tracker for remaining uses, and adds Augusta composite scores when
    available. Gives the LLM a hard-bounded candidate pool so it can't
    recommend players who aren't in the field.

    Returns three lists:
      CONFIRMED ELIGIBLE — in field, not WD, uses remaining, sorted by fit
      ZERO USES LEFT     — in field but fully used up
      NOT IN FIELD       — players in usage history but not this week's field
    """
    if not tid:
        return ""

    # Load confirmed field
    field_path = DATA / "fields" / f"field_{tid}.csv"
    if not field_path.exists():
        return ""
    try:
        field_df = pd.read_csv(field_path)
        field_names_raw = field_df["player_name"].dropna().tolist()
    except Exception:
        return ""

    def _nk(n: str) -> str:
        s = str(n).strip().lower()
        if ", " in s:
            p = s.split(", ", 1); return f"{p[1]} {p[0]}"
        return s

    field_keys = {_nk(n): n for n in field_names_raw}

    # Load withdrawals
    wd_keys: set[str] = set()
    wd_path = DATA / "news" / f"withdrawals_{tid}.json"
    if wd_path.exists():
        try:
            import json as _json
            wds = _json.loads(wd_path.read_text())
            for entry in (wds if isinstance(wds, list) else [wds]):
                if entry.get("status") != "WITHDRAWN":
                    continue
                pn = entry.get("player_name") or entry.get("name", "")
                if pn:
                    wd_keys.add(_nk(str(pn)))
        except Exception:
            pass

    # Load usage tracker
    usage_path = DATA / "fantasy" / "usage_tracker_2026.json"
    max_uses = 3
    used_map: dict[str, int] = {}  # nk → times_used
    if usage_path.exists():
        try:
            import json as _json
            udata = _json.loads(usage_path.read_text())
            max_uses = int(udata.get("max_uses_per_player", 3))
            for pname, info in udata.get("picks", {}).items():
                used_map[_nk(str(pname))] = int(info.get("times_used", 0))
        except Exception:
            pass

    # Load model top10_prob
    prob_map: dict[str, float] = {}
    preds_path = OUTPUTS / "latest_predictions.csv"
    if preds_path.exists():
        try:
            pdf = pd.read_csv(preds_path, usecols=lambda c: c in ["player_name", "top10_prob", "top10_prob_calibrated"])
            prob_col = "top10_prob_calibrated" if "top10_prob_calibrated" in pdf.columns else "top10_prob"
            if prob_col in pdf.columns:
                for _, pr in pdf.iterrows():
                    prob_map[_nk(str(pr["player_name"]))] = float(pr.get(prob_col, 0) or 0)
        except Exception:
            pass

    # Compute Augusta composite scores from raw qualifiers file
    aug_comp_map: dict[str, float] = {}
    aug_qual_map: dict[str, int] = {}
    aug_path = DATA / "qualitative" / f"masters_qualifiers_{tid}.csv"
    if aug_path.exists():
        try:
            adf = pd.read_csv(aug_path)
            # Numeric conversions
            adf["augusta_avg_to_par"]     = pd.to_numeric(adf.get("augusta_avg_to_par", 0), errors="coerce").fillna(0)
            adf["sg_t2g_last4_total"]     = pd.to_numeric(adf.get("sg_t2g_last4_total", 0), errors="coerce").fillna(0)
            adf["augusta_starts"]         = pd.to_numeric(adf.get("augusta_starts", 1), errors="coerce").fillna(1).clip(lower=1)
            adf["augusta_cuts_made"]      = pd.to_numeric(adf.get("augusta_cuts_made", 0), errors="coerce").fillna(0)
            adf["driving_dist_field_rank"]= pd.to_numeric(adf.get("driving_dist_field_rank", 88), errors="coerce").fillna(88)
            adf["_key"] = adf["player_name"].apply(_nk)
            # Map model prob
            adf["_prob"] = adf["_key"].map(prob_map).fillna(0)

            def _mm(s: pd.Series) -> pd.Series:
                mn, mx = s.min(), s.max()
                return pd.Series([0.5] * len(s), index=s.index) if mx == mn else (s - mn) / (mx - mn)

            adf["_s_aug"]     = _mm(-adf["augusta_avg_to_par"])
            adf["_s_form"]    = _mm(adf["sg_t2g_last4_total"])
            adf["_s_consist"] = _mm(adf["augusta_cuts_made"] / adf["augusta_starts"])
            adf["_s_dist"]    = _mm(-adf["driving_dist_field_rank"])
            adf["_s_prob"]    = _mm(adf["_prob"])
            adf["_composite"] = (
                0.30 * adf["_s_aug"] + 0.25 * adf["_s_form"] +
                0.20 * adf["_s_consist"] + 0.15 * adf["_s_dist"] + 0.10 * adf["_s_prob"]
            )
            for _, ar in adf.iterrows():
                k2 = str(ar["_key"])
                aug_comp_map[k2] = round(float(ar["_composite"]), 3)
                aug_qual_map[k2] = int(ar.get("qualifier_score", 0))
        except Exception:
            pass

    eligible, zero_uses, wd_players = [], [], []
    not_in_field_but_used = []

    for k, display in field_keys.items():
        # Format as "First Last"
        name = _fmt_name(display) if ", " in display else display
        uses = used_map.get(k, 0)
        remaining = max_uses - uses
        is_wd = k in wd_keys
        aq = aug_qual_map.get(k, 0)
        comp = aug_comp_map.get(k)
        p10 = prob_map.get(k, 0)
        sort_key = comp if comp is not None else p10

        if is_wd:
            wd_players.append(name)
        elif remaining <= 0:
            zero_uses.append(name)
        else:
            eligible.append((sort_key, name, remaining, aq, comp, p10))

    # Players in usage history but NOT in this week's field
    for pname_raw, used in used_map.items():
        if pname_raw not in field_keys and used > 0:
            # Try to find a display name
            not_in_field_but_used.append(pname_raw.title())

    eligible.sort(key=lambda x: x[0], reverse=True)

    lines = ["## LINEUP ELIGIBILITY CHECK"]
    lines.append(f"_Confirmed from field_{tid}.csv · withdrawals checked · usage tracker cross-referenced_")
    lines.append(f"**Max uses per player**: {max_uses} · **Tournament**: {tid}")
    lines.append("")

    if wd_players:
        lines.append(f"**WITHDRAWN / DO NOT USE**: {', '.join(wd_players)}")
        lines.append("")

    lines.append(f"**CONFIRMED ELIGIBLE** ({len(eligible)} players with uses remaining) — sorted by Augusta fit / model top-10 prob:")
    lines.append("| Player | Uses Left | Qual (8) | Aug Fit | Top-10% |")
    lines.append("|--------|-----------|----------|---------|---------|")
    for sort_key, name, rem, aq, comp, p10 in eligible[:30]:
        comp_s = f"{comp:.3f}" if comp is not None else "—"
        lines.append(f"| {name} | {rem}/{max_uses} | {aq}/8 | {comp_s} | {p10*100:.1f}% |")

    if zero_uses:
        lines.append("")
        lines.append(f"**ZERO USES REMAINING** (cannot use): {', '.join(zero_uses[:15])}")

    if not_in_field_but_used:
        lines.append("")
        lines.append(f"**NOT IN THIS WEEK'S FIELD** (do not recommend): {', '.join(not_in_field_but_used[:15])}")

    lines.append("")
    lines.append("**INSTRUCTION**: You may ONLY recommend players from the CONFIRMED ELIGIBLE table above. Any player in NOT IN FIELD or ZERO USES REMAINING is off the board.")

    return "\n".join(lines)


def _my_picks_block() -> str:
    """Current week picks + remaining uses."""
    path = DATA / "fantasy" / "usage_tracker_2026.json"
    if not path.exists():
        return ""
    try:
        with open(path) as f:
            data = json.load(f)
        weekly   = data.get("weekly_lineups", {})
        max_uses = int(data.get("max_uses_per_player", 3))

        # Find most recent week that has an actual lineup submitted
        _weeks_with_picks = [
            (int(k.split("_")[1]), k) for k, v in weekly.items()
            if v.get("lineup")
        ]
        if _weeks_with_picks:
            _latest_num, _latest_key = max(_weeks_with_picks)
            cur_week = weekly[_latest_key]
        else:
            cur_week = None
        picks    = data.get("picks", {})

        # Detect current tournament to flag stale lineup data
        current_tid = _detect_tournament_id()
        sched_path = DATA / "raw" / "schedule_2026.csv"
        current_tournament_name = None
        if current_tid and sched_path.exists():
            try:
                sched = pd.read_csv(sched_path)
                row = sched[sched["tournament_id"] == current_tid]
                if not row.empty:
                    current_tournament_name = row.iloc[0]["tournament_name"]
            except Exception:
                pass

        lines = ["## MY PICKS"]
        if cur_week:
            lineup     = cur_week.get("lineup", [])
            tournament = cur_week.get("tournament", "")

            # Check if the stored lineup is from a prior tournament
            is_stale = (
                current_tournament_name and
                tournament and
                tournament.lower() not in current_tournament_name.lower() and
                current_tournament_name.lower() not in tournament.lower()
            )

            if is_stale:
                # Show last week's picks WITH results so the LLM can report on them
                pick_details = []
                for name in lineup:
                    info = picks.get(name, {})
                    tournaments_used = info.get("tournaments_used", [])
                    # Find the result for this specific tournament
                    last_result = next(
                        (t for t in reversed(tournaments_used)
                         if t.get("tournament", "").lower() == tournament.lower()),
                        None
                    )
                    if last_result:
                        result = last_result.get("result", "?")
                        pts = last_result.get("points", 0)
                        pick_details.append(f"{name} ({result}, {pts} pts)")
                    else:
                        pick_details.append(name)
                total_pts = cur_week.get("points_earned") or cur_week.get("earnings_earned", 0)
                lines.append(
                    f"**LAST WEEK ({tournament}) picks**: {', '.join(pick_details)} — "
                    f"{total_pts} total points"
                )
                lines.append(
                    f"**THIS WEEK ({current_tournament_name or current_tid})**: No picks submitted yet."
                )
            else:
                total_pts = cur_week.get("points_earned") or cur_week.get("earnings_earned", 0)
                lines.append(
                    f"**Week {cur_week.get('week','?')} lineup — {tournament}**: "
                    + ", ".join(lineup)
                    + (f" — {total_pts:,} pts" if total_pts else "")
                )

        # Build uses-remaining from weekly_lineups (the authoritative source)
        use_counts: dict[str, int] = {}
        for wk_data in weekly.values():
            for pname in wk_data.get("lineup", []):
                if pname:
                    use_counts[pname] = use_counts.get(pname, 0) + 1

        used_players = {n: cnt for n, cnt in use_counts.items() if cnt > 0}
        if used_players:
            lines.append("\n**Season uses consumed (players with at least 1 use spent):**")
            for pname in sorted(used_players, key=lambda n: use_counts[n], reverse=True):
                cnt  = use_counts[pname]
                left = max_uses - cnt
                lines.append(f"- {pname}: {cnt} use(s) spent, {left} remaining")

        # Season earnings summary
        total_earnings = sum(
            w.get("earnings_earned") or 0 for w in weekly.values()
            if w.get("earnings_earned")
        )
        if total_earnings:
            lines.append(f"\n**Season total earnings: {total_earnings:,}**")

        return "\n".join(lines)
    except Exception as e:
        return f"## MY PICKS\n(unavailable: {e})"


def _season_strategy_block(player_names: list[str] | None = None, lean: bool = False) -> str:
    """Season usage strategy for tracked players (or specific players if named).

    lean: if True, omit the full season plan and conflict tables (saves ~15K chars).
    The per-player verdict cards are always included — those are the useful part.
    """
    try:
        from scripts.predictions.season_strategy import get_season_strategy
        strategy = get_season_strategy()
    except Exception as e:
        return f"## SEASON STRATEGY\n(unavailable: {e})"

    if "error" in strategy:
        return f"## SEASON STRATEGY\n(unavailable: {strategy['error']})"

    player_strategy = strategy.get("player_strategy", {})
    season_plan     = strategy.get("season_plan", {})
    plan_conflicts  = strategy.get("plan_conflicts", {})
    if not player_strategy:
        return ""

    # If specific players requested, filter; else show all tracked players
    if player_names:
        def _norm(n):
            return re.sub(r"[^a-z]", "", n.lower())
        norms = [_norm(p) for p in player_names]
        player_strategy = {
            k: v for k, v in player_strategy.items()
            if any(_norm(k) == n or _norm(k) in n or n in _norm(k) for n in norms)
        }

    if not player_strategy:
        return ""

    current_event  = strategy.get("current_event", {})
    cur_event_name = current_event.get("name", "this week")

    lines = ["## SEASON STRATEGY"]
    lines.append(f"Current event: {cur_event_name}")
    lines.append("")

    # ── Per-player cards ──────────────────────────────────────────────────────
    for player, info in player_strategy.items():
        uses_left       = info.get("uses_left", "?")
        tier            = info.get("tier", "standard")
        eff_rank        = info.get("eff_rank")
        world_rank      = info.get("world_rank")
        sg_season       = info.get("sg_season", 0.0)
        sg_career       = info.get("sg_career", 0.0)
        sg_trend        = info.get("sg_trend", 0.0)
        recent_sg       = info.get("recent_sg", 0.0)
        in_field        = info.get("in_field", False)
        use_this_week   = info.get("use_this_week", False)
        is_hot          = info.get("is_hot_streak", False)
        hot_override    = info.get("hot_streak_override", False)
        reason          = info.get("reason", "")
        best_events     = info.get("best_events", [])
        probs           = info.get("this_week_probs", {}) or {}

        hot_tag = " [HOT STREAK]" if is_hot else ""
        lines.append(f"### {player}{hot_tag}")
        lines.append(f"Uses: {uses_left}/3 remaining | Tier: {tier} | WR #{world_rank or '?'} | Eff Rank #{int(eff_rank) if eff_rank else '?'}")

        # SG signal — show both season and career when available; trend direction
        _baseline = sg_career if sg_career != 0.0 else 0.0
        if sg_season and sg_season != 0.0:
            _adv = recent_sg - _baseline if _baseline != 0.0 else 0.0
            _trend_str = "rising" if sg_trend > 0.05 else "falling" if sg_trend < -0.05 else "stable"
            if is_hot:
                lines.append(f"SG 2026: {sg_season:+.2f} | Recent: {recent_sg:+.2f} ({_adv:+.2f} vs career) | Trend: {_trend_str} ← form surge")
            else:
                lines.append(f"SG 2026: {sg_season:+.2f}/round | Trend: {_trend_str}")
        elif sg_career and sg_career != 0.0:
            _trend_str = "rising" if sg_trend > 0.05 else "falling" if sg_trend < -0.05 else "stable"
            lines.append(f"Career SG: {sg_career:+.2f}/round (limited 2026 data) | Trend: {_trend_str}")

        # This week
        if in_field and probs:
            win_pct = probs.get("win_prob", 0) * 100
            t10_pct = probs.get("top10_prob", 0) * 100
            cut_pct = probs.get("cut_prob", 0) * 100
            ev_raw  = info.get("this_week_ev", 0)
            lines.append(f"This week ({cur_event_name}): IN FIELD | Win {win_pct:.1f}% | Top-10 {t10_pct:.0f}% | Cut {cut_pct:.0f}% | EV {ev_raw:.0f}")
        elif in_field:
            lines.append("This week: IN FIELD (no prediction data)")
        else:
            lines.append("This week: NOT IN FIELD")

        # Best events
        if best_events:
            lines.append("Best windows:")
            _max_ev = max((e.get("ev", 0) for e in best_events), default=1) or 1
            for ev_info in best_events[:3]:
                ev_name   = ev_info.get("name", "?")
                ev_raw    = ev_info.get("ev", 0)
                ev_score  = round(ev_raw / _max_ev * 10, 1)
                ev_type   = ev_info.get("type", "")
                csg       = ev_info.get("course_sg")
                weeks_out = ev_info.get("weeks_away", 0)
                qual_flag = "" if ev_info.get("qualified", True) else " ⚠ not in 2025 field"
                ev_date   = ev_info.get("start_date", "")[:10]
                date_str  = f" ({ev_date})" if ev_date else ""
                csg_str   = f" | course SG {csg:+.2f}" if csg and csg != 0.0 else ""
                urgency   = " ← SOON" if 0 < weeks_out <= 2 else ""
                lines.append(f"  · {ev_name}{date_str} — EV {ev_score}/10 [{ev_type}]{csg_str}{qual_flag}{urgency}")

        # Verdict
        if hot_override:
            verdict = "USE THIS WEEK (hot streak override)"
        elif use_this_week:
            verdict = "USE THIS WEEK"
        else:
            verdict = "SAVE"
        lines.append(f"Verdict: {verdict} — {reason}")
        lines.append("")

    # ── Season allocation plan ────────────────────────────────────────────────
    # Only show full plan when no specific player was filtered (i.e. general query)
    # Skip in lean mode — the per-player verdicts above are sufficient for lineup questions.
    if not player_names and season_plan and not lean:
        lines.append("## OPTIMAL SEASON PLAN")
        lines.append("Greedy allocation: highest-EV assignment made first, max 3 players/week.")
        lines.append("")
        for event_name, ev_data in season_plan.items():
            assigned  = ev_data.get("assigned", [])
            overflow  = ev_data.get("overflow", [])
            ev_date   = ev_data.get("date", "")[:10]
            ev_tier   = ev_data.get("tier", "")
            if not assigned:
                continue
            tier_tag  = f" [{ev_tier}]" if ev_tier else ""
            date_tag  = f" ({ev_date})" if ev_date else ""
            over_str  = f" | overflow → {', '.join(overflow)}" if overflow else ""
            lines.append(f"  {event_name}{date_tag}{tier_tag}: {', '.join(assigned)}{over_str}")
        lines.append("")

    # ── Conflict warnings ─────────────────────────────────────────────────────
    if not player_names and plan_conflicts and not lean:
        lines.append("## SCHEDULING CONFLICTS")
        lines.append("Events where more than 3 of your players peak — you'll need to make hard choices:")
        lines.append("")
        for event_name, conf in sorted(plan_conflicts.items(),
                                        key=lambda x: x[1].get("week", 0)):
            wants    = conf.get("wants", [])
            assigned = conf.get("assigned", [])
            overflow = conf.get("overflow", [])
            ev_date  = conf.get("date", "")[:10]
            ev_tier  = conf.get("tier", "")
            tier_tag = f" [{ev_tier}]" if ev_tier else ""
            lines.append(f"  {event_name} ({ev_date}){tier_tag}")
            lines.append(f"    Wants slot ({len(wants)}): {', '.join(wants)}")
            lines.append(f"    Gets slot (top 3 by EV): {', '.join(assigned)}")
            if overflow:
                lines.append(f"    Needs alt event: {', '.join(overflow)}")
            lines.append("")

    return "\n".join(lines)


def _league_context_block() -> str:
    """League standings, weekly picks, ownership, and rival intel."""
    standings_path = DATA / "fantasy" / "league_standings.csv"
    weekly_path    = DATA / "fantasy" / "league_weekly_picks.csv"
    usage_path     = DATA / "fantasy" / "league_player_usage.csv"

    if not standings_path.exists():
        return ""

    MY_TEAM = "WineTime"
    lines = ["## LEAGUE CONTEXT (Louisiana/Delaware Connection — 28 teams, max 3 uses/player)"]

    try:
        standings = pd.read_csv(standings_path)
        my_row    = standings[standings["team_name"] == MY_TEAM]
        my_place  = my_row["place"].iloc[0] if not my_row.empty else "?"
        my_earn   = my_row["earnings"].iloc[0] if not my_row.empty else "?"
        my_back   = my_row["earnings_back"].iloc[0] if not my_row.empty else "?"
        lines.append(f"\n**Season Standings — {MY_TEAM} is {my_place} | {my_earn} | {my_back} back**")
        top5 = standings.head(5)[["place", "team_name", "owner", "earnings", "earnings_back"]]
        lines.append(top5.to_markdown(index=False))
        if not my_row.empty and int(my_row.index[0]) >= 5:
            lines.append(f"...  {my_place} | {MY_TEAM} | {my_earn} | {my_back} back")
    except Exception as e:
        lines.append(f"(standings unavailable: {e})")

    if weekly_path.exists():
        try:
            weekly = pd.read_csv(weekly_path)
            weekly = weekly.sort_values("total_earnings", ascending=False).reset_index(drop=True)

            # Determine which tournament this weekly data represents
            current_tid = _detect_tournament_id()
            sched_path = DATA / "raw" / "schedule_2026.csv"
            current_tname = None
            if current_tid and sched_path.exists():
                try:
                    sched = pd.read_csv(sched_path)
                    row = sched[sched["tournament_id"] == current_tid]
                    if not row.empty:
                        current_tname = row.iloc[0]["tournament_name"]
                except Exception:
                    pass

            # Infer weekly data tournament from usage_tracker last lineup
            usage_path2 = DATA / "fantasy" / "usage_tracker_2026.json"
            weekly_data_tname = None
            if usage_path2.exists():
                try:
                    udata = json.load(open(usage_path2))
                    wl = udata.get("weekly_lineups", {})
                    if wl:
                        last = wl[max(wl.keys())]
                        weekly_data_tname = last.get("tournament", "")
                except Exception:
                    pass

            data_label = weekly_data_tname or "last week"
            is_stale = (
                current_tname and weekly_data_tname and
                weekly_data_tname.lower() not in current_tname.lower() and
                current_tname.lower() not in weekly_data_tname.lower()
            )
            staleness_note = (
                f" ⚠️ NOTE: This data is from {data_label}, NOT {current_tname}. "
                f"Picks for {current_tname} have not been submitted yet."
                if is_stale else ""
            )

            my_week = weekly[weekly["team_name"] == MY_TEAM]
            if not my_week.empty:
                r = my_week.iloc[0]
                lines.append(
                    f"\n**{MY_TEAM} — {data_label} results (rank #{r['weekly_rank']}): "
                    f"{r['player_1']} ${r['earnings_1']:,} | "
                    f"{r['player_2']} ${r['earnings_2']:,} | "
                    f"{r['player_3']} ${r['earnings_3']:,} | "
                    f"Total ${r['total_earnings']:,}**"
                    + staleness_note
                )

            top12 = weekly.head(12)
            if MY_TEAM not in top12["team_name"].values:
                top12 = pd.concat([top12, weekly[weekly["team_name"] == MY_TEAM]]).drop_duplicates()
            lines.append(f"\n**{data_label} standings (top 12 + {MY_TEAM}):**{' (LAST WEEK — not current)' if is_stale else ''}")
            display = top12[["weekly_rank","team_name","player_1","player_2","player_3","total_earnings"]].copy()
            display["total_earnings"] = display["total_earnings"].apply(lambda x: f"${x:,}")
            lines.append(display.to_markdown(index=False))

            all_picks = pd.concat([
                weekly[["player_1"]].rename(columns={"player_1": "player"}),
                weekly[["player_2"]].rename(columns={"player_2": "player"}),
                weekly[["player_3"]].rename(columns={"player_3": "player"}),
            ]).query("player != 'VACANT'")["player"].value_counts()
            lines.append(f"\n**Player ownership — {data_label} (# of teams):**{' (LAST WEEK data)' if is_stale else ''}")
            lines.append(" | ".join(f"{p}: {c}" for p, c in all_picks.items()))
        except Exception as e:
            lines.append(f"(weekly picks unavailable: {e})")

    if usage_path.exists():
        try:
            usage = pd.read_csv(usage_path)
            locked = usage[usage["uses_left"] == 0].copy()
            if not locked.empty:
                locked_summary = (
                    locked[locked["team_name"] != MY_TEAM]
                    .groupby("player")["team_name"]
                    .apply(lambda teams: ", ".join(sorted(teams)))
                    .reset_index()
                    .rename(columns={"team_name": "locked_out_teams"})
                    .sort_values("player")
                )
                lines.append("\n**Rival teams locked out of players (used all 3x):**")
                lines.append(locked_summary.to_markdown(index=False))

            my_usage = usage[usage["team_name"] == MY_TEAM][["player","times_used","uses_left","total_earned"]]
            if not my_usage.empty:
                lines.append(f"\n**{MY_TEAM} player use history:**")
                my_usage = my_usage.sort_values("times_used", ascending=False).copy()
                my_usage["total_earned"] = my_usage["total_earned"].apply(lambda x: f"${int(x):,}")
                lines.append(my_usage.to_markdown(index=False))
        except Exception as e:
            lines.append(f"(usage data unavailable: {e})")

    return "\n".join(lines)


_KNOWN_TOURNAMENT_NAMES: dict[str, str] = {
    "014": "Masters Tournament",
    "026": "U.S. Open Championship",
    "100": "The Open Championship",
    "047": "PGA Championship",
    "011": "The Players Championship",
    "005": "Arnold Palmer Invitational",
    "007": "The Genesis Invitational",
    "020": "Memorial Tournament",
}


def _tournament_state(tid: str) -> dict:
    """Return tournament phase dict."""
    # Use known name for recognised events even before meta file exists
    _suffix = tid[-3:] if tid and len(tid) >= 3 else ""
    _fallback_name = _KNOWN_TOURNAMENT_NAMES.get(_suffix, tid)
    state = {"name": _fallback_name, "round": 0, "round_status": "", "phase": "pre_tournament"}
    if not tid:
        return state
    meta_path = DATA / "live" / f"leaderboard_{tid.lower()}_meta.json"
    if not meta_path.exists():
        # Try to get name from schedule CSV
        try:
            sched = pd.read_csv(DATA / "raw" / "schedule_2026.csv", dtype=str)
            match = sched[sched["tournament_id"].str.upper() == tid.upper()]
            if not match.empty:
                state["name"] = str(match.iloc[0].get("tournament_name", _fallback_name))
        except Exception:
            pass
        return state
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        state["name"]         = meta.get("tournament_name", tid)
        state["round"]        = int(meta.get("current_round", 0))
        state["round_status"] = meta.get("round_status", "")
        state["fetched_at"]   = meta.get("fetched_at", "")
        r  = state["round"]
        rs = state["round_status"].lower()
        # "groupings official" / "no round" = tee times set but no golf played yet
        _pre_play_statuses = {"groupings official", "no round", "not started", ""}
        _round_done_statuses = {"official", "complete", "completed", "final"}
        if r == 4 and rs in _round_done_statuses:
            state["phase"] = "complete"
        elif r == 0 or rs in _pre_play_statuses:
            state["phase"] = "pre_tournament"
        elif rs in _round_done_statuses:
            # Round r is fully official — all scores are in
            state["phase"] = f"round_{r}"
        else:
            # Round r is actively in progress (some players still on course)
            state["phase"] = f"round_{r}_in_progress"
    except Exception:
        pass
    return state


def _tournament_state_block(tid: str) -> str:
    """Inject tournament state header so the LLM knows how to frame responses."""
    ts    = _tournament_state(tid)
    phase = ts["phase"]
    name  = ts["name"]
    r     = ts["round"]

    if phase == "pre_tournament":
        status_line = "PRE-TOURNAMENT — no rounds have been played yet."
        instruction = (
            "Focus on pre-tournament analysis: predictions, betting value, lineup decisions, course fit. "
            "Do not reference live scores or leaderboard positions."
        )
    elif phase == "complete":
        status_line = "TOURNAMENT COMPLETE — all 4 rounds are official."
        instruction = (
            "This tournament is FINISHED. When asked about it, reference final results. "
            "Shift any lineup/betting questions toward the NEXT TOURNAMENT on the schedule."
        )
    elif phase.endswith("_in_progress"):
        # Round is actively being played — scores are live but not all players are done
        rounds_remaining = 4 - r
        status_line = f"ROUND {r} OF 4 IN PROGRESS — some players still on course."
        instruction = (
            f"Round {r} is CURRENTLY BEING PLAYED — do NOT say it is complete. "
            "The leaderboard shows live scoring and positions may still change today. "
            "Focus on who is leading, who is making moves, and who is fading. "
            f"Rounds remaining after today: {rounds_remaining - 1}. "
            f"A player needs to be within ~{max(4, rounds_remaining * 4)} strokes to have a realistic chance. "
            "Betting questions: focus on in-play value. "
            "Lineup questions: picks are locked for this week."
        )
    else:
        # Round is fully official
        rounds_remaining = 4 - r
        status_line = f"ROUND {r} OF 4 COMPLETE (OFFICIAL) — {rounds_remaining} round(s) remaining."
        instruction = (
            f"Round {r} scores are official. We are mid-tournament. "
            "Focus on the live leaderboard: who's leading, who's surged or faded, who still has a realistic chance. "
            f"A player needs to be within ~{max(4, rounds_remaining * 4)} strokes to have a serious chance. "
            "Betting questions: focus on in-play value based on current position. "
            "Lineup questions: picks are already locked for this week."
        )

    fetched = ts.get("fetched_at", "")
    freshness = f" (data last refreshed: {fetched[:16].replace('T',' ')} UTC)" if fetched else ""

    return (
        f"## TOURNAMENT STATUS: {name}\n"
        f"{status_line}{freshness}\n"
        f"RESPOND ACCORDINGLY: {instruction}"
    )


def _conversation_history_block(tournament_id: str | None, limit: int = 5) -> str:
    """
    Inject the last N assistant exchanges for this tournament into the system prompt.

    Why same-tournament only: prior-week conversations are stale context. What was
    said about TPC San Antonio is irrelevant when you're now at Augusta. Filtering
    by tournament_id keeps the injected history immediately relevant.

    Why 5 exchanges: enough to give the LLM continuity (it remembers what you asked
    Monday when you follow up Thursday) without consuming so many tokens that the
    actual player/odds data gets pushed out.

    Returns empty string on any error so the chatbot degrades gracefully.
    """
    if not tournament_id:
        return ""
    try:
        from scripts.chat.conversation_store import get_recent
        rows = get_recent(tournament_id, limit=limit)
    except Exception:
        return ""

    if not rows:
        return ""

    lines = ["## PREVIOUS CONVERSATIONS THIS WEEK"]
    lines.append("(Use this to avoid repeating yourself and to build on prior answers.)\n")

    for row in rows:
        ts = row["timestamp"]
        # Format timestamp compactly: "Mon Mar 30 · 2:14 PM"
        try:
            ts_str = ts.strftime("%-d %b · %-I:%M %p") if hasattr(ts, "strftime") else str(ts)
        except Exception:
            ts_str = str(ts)

        phase_label = (row.get("phase") or "").replace("_", " ")
        lines.append(f"[{ts_str} · {phase_label}]")
        lines.append(f"Q: {row['question']}")
        lines.append(f"A: {row['response_short']}")
        lines.append("")

    return "\n".join(lines)


def _dg_approach_detail_block(players: list[str]) -> str:
    """DataGolf approach skill breakdown by distance band (last 24 months).

    Reads dg_approach_skill_l24.csv — updated by scheduled_refresh.py.
    Shows SG/shot, GIR rate, and proximity for each distance band.
    Critical for course-fit reasoning: does the player's strength match
    the yardages this course demands from the fairway and rough?
    """
    if not players:
        return ""
    path = DATA / "datagolf" / "dg_approach_skill_l24.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["_key"] = df["player_name"].apply(
            lambda n: _fmt_name(str(n)).lower().strip()
        )

        # Distance bands: (label, fw_sg_col, fw_gir_col, fw_prox_col, rgh_sg_col)
        BANDS = [
            ("50-100y",  "50_100_fw_sg_per_shot",   "50_100_fw_gir_rate",   "50_100_fw_proximity_per_shot",   None),
            ("100-150y", "100_150_fw_sg_per_shot",  "100_150_fw_gir_rate",  "100_150_fw_proximity_per_shot",  "under_150_rgh_sg_per_shot"),
            ("150-200y", "150_200_fw_sg_per_shot",  "150_200_fw_gir_rate",  "150_200_fw_proximity_per_shot",  "over_150_rgh_sg_per_shot"),
            ("200y+",    "over_200_fw_sg_per_shot", "over_200_fw_gir_rate", "over_200_fw_proximity_per_shot", None),
        ]

        lines = ["## DG APPROACH SKILL — LAST 24 MONTHS (by distance band)"]
        lines.append(
            "sg/shot=strokes gained per shot vs PGA Tour avg | GIR=greens in regulation rate | "
            "Prox=avg proximity to hole (ft) | Rgh=from rough"
        )
        lines.append("")

        found = 0
        for pname in players:
            pk = pname.lower().strip()
            pk_last = pk.split()[-1]
            match = df[df["_key"] == pk]
            if match.empty:
                match = df[df["_key"].str.contains(pk_last, na=False)]
            if match.empty:
                continue
            r = match.iloc[0]
            name_fmt = _fmt_name(str(r["player_name"]))
            overall_sg  = r.get("approach_skill_sg", None)
            overall_prx = r.get("approach_skill_proximity", None)
            hdr = f"**{name_fmt}**"
            if pd.notna(overall_sg) and pd.notna(overall_prx):
                hdr += f" — overall approach SG/shot: {float(overall_sg):+.4f} | avg proximity: {float(overall_prx):.1f}ft"
            lines.append(hdr)

            for label, fw_sg, fw_gir, fw_prx, rgh_sg in BANDS:
                parts = []
                sg_val  = r.get(fw_sg)
                gir_val = r.get(fw_gir)
                prx_val = r.get(fw_prx)
                if pd.notna(sg_val):
                    parts.append(f"FW sg/shot {float(sg_val):+.3f}")
                if pd.notna(gir_val):
                    parts.append(f"GIR {float(gir_val)*100:.0f}%")
                if pd.notna(prx_val):
                    parts.append(f"prox {float(prx_val):.1f}ft")
                if rgh_sg:
                    rv = r.get(rgh_sg)
                    if pd.notna(rv):
                        parts.append(f"Rgh sg/shot {float(rv):+.3f}")
                if parts:
                    lines.append(f"  {label}: {' | '.join(parts)}")

            lines.append("")
            found += 1

        if not found:
            return ""
        return "\n".join(lines).rstrip()
    except Exception:
        return ""


def _dg_skill_block(players: list[str]) -> str:
    """DataGolf skill ratings snapshot for named players.

    Reads dg_skill_ratings_latest.csv — updated by scheduled_refresh.py.
    Shows: OTT, APP, ARG, PUTT skill scores, driving distance and accuracy.
    """
    if not players:
        return ""
    path = DATA / "datagolf" / "dg_skill_ratings_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["_key"] = df["player_name"].apply(
            lambda n: _fmt_name(str(n)).lower().strip()
        )

        lines = ["## DG SKILL RATINGS (DataGolf model, current season)"]
        lines.append("OTT=off-tee  APP=approach  ARG=around-green  PUTT=putting  Dist=yards vs field avg  Acc=%fairways vs field avg")
        lines.append("")

        found = 0
        for pname in players:
            pk = pname.lower().strip()
            pk_last = pk.split()[-1]
            match = df[df["_key"] == pk]
            if match.empty:
                match = df[df["_key"].str.contains(pk_last, na=False)]
            if match.empty:
                continue
            r = match.iloc[0]
            total = float(r.get("dg_skill_total", 0) or 0)
            ott   = float(r.get("dg_skill_ott", 0) or 0)
            app   = float(r.get("dg_skill_app", 0) or 0)
            arg   = float(r.get("dg_skill_arg", 0) or 0)
            putt  = float(r.get("dg_skill_putt", 0) or 0)
            dist  = float(r.get("dg_skill_dist", 0) or 0)
            acc   = float(r.get("dg_skill_acc", 0) or 0)
            lines.append(
                f"**{_fmt_name(str(r['player_name']))}** — Total: {total:+.3f} | "
                f"OTT: {ott:+.3f} | APP: {app:+.3f} | ARG: {arg:+.3f} | PUTT: {putt:+.3f} | "
                f"Dist: {dist:+.1f}yd | Acc: {acc*100:+.1f}%"
            )
            found += 1

        if not found:
            return ""
        return "\n".join(lines)
    except Exception:
        return ""


def _dg_decompositions_block(tid: str | None, players: list[str] | None = None) -> str:
    """DataGolf prediction decomposition — course adjustments for this event.

    Reads dg_decompositions_{tid}.csv (updated by scheduled_refresh.py).
    Shows: baseline vs final prediction, course-history adj, total fit adj,
    course_fit_delta (DG's net advantage/disadvantage vs field).
    """
    if not tid:
        return ""
    path = DATA / "datagolf" / f"dg_decompositions_{tid.upper()}.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        df["_key"] = df["player_name"].apply(
            lambda n: _fmt_name(str(n)).lower().strip()
        )

        course_name = df["course_name"].iloc[0] if "course_name" in df.columns else ""
        event_name  = df["event_name"].iloc[0]  if "event_name"  in df.columns else tid

        lines = [
            f"## DG COURSE DECOMPOSITIONS — {event_name}"
            + (f" at {course_name}" if course_name else "")
        ]
        lines.append(
            "baseline_pred=DG baseline (no course adj) | final_pred=with all adjustments | "
            "course_hist_adj=course-history effect | fit_adj=total course-fit adjustment | "
            "fit_delta=net strokes gained vs avg field at this venue"
        )
        lines.append("")

        if players:
            # Show only requested players
            rows = []
            for pname in players:
                pk_last = pname.lower().strip().split()[-1]
                m = df[df["_key"] == pname.lower().strip()]
                if m.empty:
                    m = df[df["_key"].str.contains(pk_last, na=False)]
                if not m.empty:
                    rows.append(m.iloc[0])
        else:
            # Top 20 by final_pred
            rows = df.nlargest(20, "final_pred").itertuples(index=False)
            rows = list(rows)

        for r in rows:
            name    = _fmt_name(str(r["player_name"] if hasattr(r, "__getitem__") else getattr(r, "player_name", "")))
            base    = float(r["baseline_pred"] if hasattr(r, "__getitem__") else getattr(r, "baseline_pred", 0) or 0)
            final   = float(r["final_pred"]    if hasattr(r, "__getitem__") else getattr(r, "final_pred",    0) or 0)
            ch_adj  = float(r["total_course_history_adjustment"] if hasattr(r, "__getitem__") else getattr(r, "total_course_history_adjustment", 0) or 0)
            fit_adj = float(r["total_fit_adjustment"] if hasattr(r, "__getitem__") else getattr(r, "total_fit_adjustment", 0) or 0)
            cf_del  = float(r["course_fit_delta"] if hasattr(r, "__getitem__") else getattr(r, "course_fit_delta", 0) or 0)
            lines.append(
                f"**{name}** — baseline: {base:.2f} | final: {final:.2f} | "
                f"course_hist: {ch_adj:+.3f} | fit_adj: {fit_adj:+.3f} | fit_delta: {cf_del:+.4f}"
            )

        return "\n".join(lines)
    except Exception:
        return ""


def _dg_course_fit_block(tid: str | None, top_n: int = 15) -> str:
    """DataGolf course-fit leaderboard for this event.

    Reads dg_course_fit_latest.csv — updated by scheduled_refresh.py.
    Shows players sorted by course_fit_delta (net edge over avg field at this venue).
    bhf_win = DG's baseline+history+fit win probability.
    """
    if not tid:
        return ""
    path = DATA / "datagolf" / "dg_course_fit_latest.csv"
    if not path.exists():
        return ""
    try:
        df = pd.read_csv(path)
        if df.empty or "course_fit_delta" not in df.columns:
            return ""

        df = df.sort_values("course_fit_delta", ascending=False)
        top = df.head(top_n)
        bottom = df.tail(5)

        event_ref = f"(tid={tid})"
        lines = [f"## DG COURSE FIT RANKING — top {top_n} fits {event_ref}"]
        lines.append(
            "course_fit_delta = strokes-gained edge vs avg field at this venue | "
            "bhf_win = DG win probability (baseline+history+fit)"
        )
        lines.append("")
        lines.append("### Best Course Fits")
        for _, r in top.iterrows():
            name = _fmt_name(str(r["player_name"]))
            delta = float(r["course_fit_delta"])
            pct   = float(r.get("course_fit_delta_pct", 0) or 0)
            bhf   = float(r.get("bhf_win", 0) or 0)
            lines.append(
                f"  {name}: fit_delta={delta:+.4f} ({pct:+.1%} vs baseline) | "
                f"bhf_win={bhf*100:.2f}%"
            )

        lines.append("")
        lines.append("### Worst Course Fits (bottom 5)")
        for _, r in bottom.iterrows():
            name  = _fmt_name(str(r["player_name"]))
            delta = float(r["course_fit_delta"])
            pct   = float(r.get("course_fit_delta_pct", 0) or 0)
            lines.append(f"  {name}: fit_delta={delta:+.4f} ({pct:+.1%} vs baseline)")

        return "\n".join(lines)
    except Exception:
        return ""


def _strategy_reasoning_block() -> str:
    """Pre-generated AI lineup recommendation from strategy_reasoning.json.

    Generated by generate_strategy_reasoning.py (runs the combinatorial optimizer +
    Claude Haiku). Provides authoritative USE/SAVE verdicts with prose reasoning
    so the chatbot can answer lineup questions consistently with the My Lineup tab.
    """
    path = OUTPUTS / "strategy_reasoning.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text())
        players     = data.get("players", {})
        lineup      = data.get("lineup", [])
        narrative   = data.get("weekly_narrative", "").strip()
        tournament  = data.get("tournament", "")
        generated   = data.get("generated_at", "")[:10]

        if not players and not lineup:
            return ""

        lines = [f"## AI LINEUP RECOMMENDATION — {tournament} (generated {generated})"]
        lines.append(
            "This recommendation was produced by the combinatorial prize-money optimizer "
            "and is the authoritative starting point for lineup questions this week."
        )
        lines.append("")

        if narrative:
            lines.append("### WEEKLY NARRATIVE (optimizer rationale)")
            lines.append(narrative)
            lines.append("")

        if lineup:
            lines.append("### RECOMMENDED LINEUP (optimizer pick — 3 players)")
            for name in lineup:
                p    = players.get(name, {})
                ev   = int(p.get("this_week_ev", 0))
                uses = p.get("uses_left", "?")
                tier = p.get("tier", "").upper() or "PICK"
                lines.append(f"- {name}: {ev:,} EV this week | {uses}/3 uses remaining | {tier} | RECOMMENDATION: USE NOW")
            lines.append("")

        # SAVE players with generated narratives
        save_players = [
            (n, d) for n, d in players.items()
            if d.get("recommendation") == "SAVE" and d.get("narrative")
        ]
        if save_players:
            lines.append("### WHY SAVE (players to hold back this week — with reasoning)")
            for name, pd_ in save_players:
                uses     = pd_.get("uses_left", "?")
                ev       = int(pd_.get("this_week_ev", 0))
                in_field = pd_.get("in_field", False)
                field_tag = f"{ev:,} EV this week" if in_field else "NOT IN FIELD this week"
                narrative_txt = pd_.get("narrative", "").strip()
                lines.append(f"\n**{name}** ({uses}/3 uses, {field_tag})")
                lines.append(narrative_txt)
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"## AI LINEUP RECOMMENDATION\n(unavailable: {e})"


def _season_context_block() -> str:
    """Load the pre-generated season performance summary (outputs/assistant_context.md).

    Updated after each tournament by build_assistant_context.py.
    Covers: season accuracy, recent results, bet grading, CLV, feature importance.
    """
    path = OUTPUTS / "assistant_context.md"
    if not path.exists():
        return ""
    try:
        content = path.read_text().strip()
        if not content:
            return ""
        return content
    except Exception:
        return ""


def _recent_recaps_block(n: int = 6) -> str:
    """Load the most recent N tournament recap narratives from outputs/tournament_recap_*.json.

    Returns a compact block listing each tournament and its AI-generated recap,
    sorted newest first. Used to give the LLM quick recall of recent results
    without having to read full leaderboard CSVs.
    """
    import json as _json
    recap_dir = OUTPUTS
    recap_files = sorted(recap_dir.glob("tournament_recap_R*.json"), reverse=True)
    if not recap_files:
        return ""

    sched_map: dict[str, str] = {}
    date_map:  dict[str, str] = {}
    try:
        sched = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv")
        sched_map = dict(zip(sched["tournament_id"].astype(str), sched["tournament_name"]))
        date_map  = dict(zip(sched["tournament_id"].astype(str), sched["start_date"]))
    except Exception:
        pass

    entries: list[tuple[str, str, str]] = []  # (date, tid, narrative)
    for f in recap_files:
        try:
            data = _json.loads(f.read_text())
            tid       = data.get("tournament_id", "").upper()
            narrative = data.get("narrative", "").strip()
            winner    = data.get("winner", "")
            t_name    = sched_map.get(tid) or data.get("tournament_name", tid)
            t_date    = date_map.get(tid, "")
            if narrative:
                entries.append((t_date, tid, t_name, winner, narrative))
        except Exception:
            continue

    # Sort by date descending, take most recent n
    entries.sort(key=lambda x: x[0], reverse=True)
    entries = entries[:n]

    if not entries:
        return ""

    lines = ["## RECENT TOURNAMENT RECAPS"]
    for t_date, tid, t_name, winner, narrative in entries:
        date_str = str(t_date)[:10] if t_date else ""
        lines.append(f"\n**{t_name}** ({date_str}) — Winner: {winner}")
        lines.append(narrative)

    return "\n".join(lines)


def _season_performance_block() -> str:
    """Model calibration + bet ROI summary built from prediction_history.csv and recommended_bets_results.csv."""
    lines = ["## MODEL SEASON PERFORMANCE (2026)"]
    try:
        ph_path = OUTPUTS / "prediction_history.csv"
        if ph_path.exists():
            ph = pd.read_csv(ph_path)
            ph_results = ph[ph["result_recorded"] == True].copy() if "result_recorded" in ph.columns else pd.DataFrame()

            if not ph_results.empty:
                # Per-tournament calibration
                lines.append("\n### Prediction accuracy by tournament")
                for tid, grp in ph_results.groupby("tournament_id"):
                    t_name = grp["tournament_name"].iloc[0] if "tournament_name" in grp.columns else tid
                    n = len(grp)
                    results = []
                    for col, label in [("actual_won","Win"), ("actual_top5","Top-5"),
                                       ("actual_top10","Top-10"), ("actual_top20","Top-20")]:
                        if col in grp.columns:
                            pred_col = col.replace("actual_", "predicted_")
                            # Use calibrated prob if available
                            prob_col = (
                                "win_prob_calibrated"   if col == "actual_won"   and "win_prob_calibrated"   in grp.columns else
                                "top5_prob_calibrated"  if col == "actual_top5"  and "top5_prob_calibrated"  in grp.columns else
                                "top10_prob_calibrated" if col == "actual_top10" and "top10_prob_calibrated" in grp.columns else
                                "top20_prob_calibrated" if col == "actual_top20" and "top20_prob_calibrated" in grp.columns else
                                "predicted_win_prob"    if col == "actual_won"   else
                                "predicted_top5_prob"   if col == "actual_top5"  else
                                "predicted_top10_prob"  if col == "actual_top10" else
                                "predicted_top20_prob"
                            )
                            if prob_col in grp.columns and col in grp.columns:
                                actual   = pd.to_numeric(grp[col], errors="coerce").fillna(0)
                                pred     = pd.to_numeric(grp[prob_col], errors="coerce").dropna()
                                hit_rate = actual.mean()
                                avg_pred = pred.mean() if not pred.empty else 0
                                ratio    = hit_rate / avg_pred if avg_pred > 0 else None
                                ratio_str = f"{ratio:.2f}x" if ratio else "—"
                                results.append(f"{label}: predicted {avg_pred*100:.1f}% avg → actual {hit_rate*100:.1f}% hit rate ({ratio_str})")
                    lines.append(f"\n**{t_name}** ({n} players)")
                    for r in results:
                        lines.append(f"  - {r}")

                # Overall calibration
                lines.append("\n### Overall calibration (all tournaments with results)")
                for col, label, prob_col in [
                    ("actual_won",   "Win",    "predicted_win_prob"),
                    ("actual_top5",  "Top-5",  "predicted_top5_prob"),
                    ("actual_top10", "Top-10", "predicted_top10_prob"),
                    ("actual_top20", "Top-20", "predicted_top20_prob"),
                ]:
                    if col in ph_results.columns and prob_col in ph_results.columns:
                        actual   = pd.to_numeric(ph_results[col], errors="coerce").fillna(0)
                        pred     = pd.to_numeric(ph_results[prob_col], errors="coerce").fillna(0)
                        hit_rate = actual.mean()
                        avg_pred = pred.mean()
                        ratio    = hit_rate / avg_pred if avg_pred > 0 else None
                        ratio_str = f"{ratio:.2f}x" if ratio else "—"
                        lines.append(f"  - {label}: avg predicted {avg_pred*100:.1f}% → actual hit rate {hit_rate*100:.1f}% (calibration ratio {ratio_str}; ideal = 1.00x)")
            else:
                lines.append("(No tournament results recorded yet this season.)")
    except Exception as e:
        lines.append(f"(Prediction history unavailable: {e})")

    try:
        rb_path = DATA / "odds" / "recommended_bets_results.csv"
        if rb_path.exists():
            rb = pd.read_csv(rb_path)
            graded = rb[rb["outcome_status"].notna()] if "outcome_status" in rb.columns else pd.DataFrame()
            if not graded.empty:
                lines.append("\n### Betting results by tournament")
                tid_col = "tournament_id" if "tournament_id" in graded.columns else None
                if tid_col:
                    for tid, grp in graded.groupby(tid_col):
                        wins    = (grp["outcome_status"] == "won").sum()
                        total   = len(grp)
                        pnl_col = "pnl_per_1" if "pnl_per_1" in grp.columns else None
                        pnl_str = ""
                        if pnl_col:
                            pnl   = grp[pnl_col].sum()
                            roi   = pnl / total * 100
                            pnl_str = f"  P&L: {pnl:+.2f}u  ROI: {roi:+.1f}%"
                        lines.append(f"  - {tid}: {wins}/{total} wins ({wins/total*100:.0f}%){pnl_str}")

                # Season totals
                total_bets  = len(graded)
                total_wins  = (graded["outcome_status"] == "won").sum()
                pnl_col     = "pnl_per_1" if "pnl_per_1" in graded.columns else None
                total_pnl   = graded[pnl_col].sum() if pnl_col else None
                total_roi   = total_pnl / total_bets * 100 if total_pnl is not None else None
                lines.append(f"\n**Season totals**: {total_wins}/{total_bets} wins ({total_wins/total_bets*100:.0f}%)" +
                             (f"  P&L: {total_pnl:+.2f}u  ROI: {total_roi:+.1f}%" if total_pnl is not None else ""))
    except Exception as e:
        lines.append(f"(Bet results unavailable: {e})")

    return "\n".join(lines)


def _schedule_block(current_tid: str | None = None) -> str:
    """Season schedule: completed, current, and next 3 upcoming."""
    path = DATA / "raw" / "schedule_2026.csv"
    if not path.exists():
        return ""
    try:
        sched = pd.read_csv(path)
        today = datetime.now().date()

        complete_tids = set()
        for mf in glob.glob(str(DATA / "live" / "leaderboard_r*_meta.json")):
            try:
                with open(mf) as f:
                    m = json.load(f)
                if m.get("round_status", "").lower() == "official":
                    complete_tids.add(str(m.get("tournament_id", "")))
            except Exception:
                pass

        lines = ["## 2026 SEASON SCHEDULE"]
        lines.append("(Predictions are only available for the CURRENT week.)")

        upcoming_shown = 0
        skipped = 0

        for _, row in sched.iterrows():
            tid   = str(row.get("tournament_id", ""))
            name  = row.get("tournament_name", "")
            ttype = row.get("tournament_type", "")
            purse = row.get("purse", "")
            week  = int(row.get("week", 0))
            start = str(row.get("start_date", ""))
            end   = str(row.get("end_date", ""))

            try:
                start_date = datetime.strptime(start, "%Y-%m-%d").date()
            except Exception:
                start_date = None

            is_done     = tid in complete_tids and tid != current_tid
            is_current  = tid == current_tid
            is_upcoming = start_date and start_date > today and not is_done and not is_current

            if is_done:
                marker = "✓ DONE "
            elif is_current:
                marker = "▶ NOW  "
            elif is_upcoming:
                if upcoming_shown < 3:
                    marker = "→ NEXT " if upcoming_shown == 0 else "  "
                    upcoming_shown += 1
                else:
                    skipped += 1
                    continue
            else:
                continue

            lines.append(f"{marker}Wk{week:02d} | {name} | {ttype} | {purse} | {start} – {end}")

        if skipped:
            lines.append(f"  ... + {skipped} more upcoming tournaments")

        return "\n".join(lines)
    except Exception as e:
        return f"## SCHEDULE\n(unavailable: {e})"


# ---------------------------------------------------------------------------
# Player live context — tee time, odds movement, live position, active bets
# (injected into every player-related response path)
# ---------------------------------------------------------------------------

def _player_live_context(player_names: list[str], tid: str | None) -> str:
    """For each named player: tee time, current odds + move, live position, active bets.

    This is what you'd normally have to look up on three different tabs on PGA Tour.
    Injected automatically on any player question so you don't have to ask.
    """
    if not player_names:
        return ""

    # ── 1. Live leaderboard (tee time + position) ───────────────────────────
    live_df: pd.DataFrame | None = None
    if tid:
        lpath = DATA / "live" / f"leaderboard_{tid.lower()}.csv"
        if lpath.exists():
            try:
                live_df = pd.read_csv(lpath)
                live_df["player_name"] = live_df["player_name"].apply(_fmt_name)
            except Exception:
                pass

    # ── 2. Odds movement from snapshots (opening → latest) ──────────────────
    odds_move: dict[str, str] = {}
    snap_dir = DATA / "odds" / "snapshots"
    if snap_dir.exists():
        try:
            snaps = sorted(snap_dir.glob("odds_snapshot_*.csv"))
            cutoff = datetime.now() - timedelta(days=7)
            recent = []
            for sf in snaps:
                try:
                    ts = datetime.strptime(sf.stem.replace("odds_snapshot_", ""), "%Y%m%d_%H%M")
                    if ts >= cutoff:
                        recent.append(sf)
                except Exception:
                    continue
            if len(recent) >= 2:
                first_snap = pd.read_csv(recent[0])
                last_snap  = pd.read_csv(recent[-1])
                first_snap["player_name"] = first_snap["player_name"].apply(_fmt_name)
                last_snap["player_name"]  = last_snap["player_name"].apply(_fmt_name)
                merged = first_snap.merge(last_snap, on="player_name", suffixes=("_open", "_now"))
                for _, row in merged.iterrows():
                    try:
                        o_open = float(row["odds_numeric_open"])
                        o_now  = float(row["odds_numeric_now"])
                        def _imp(o):
                            return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
                        chg = _imp(o_now) - _imp(o_open)
                        arrow = "▲ shortened" if chg > 0.01 else ("▼ drifted" if chg < -0.01 else "→ stable")
                        odds_move[row["player_name"].lower()] = (
                            f"{_fmt_odds(o_open)} → {_fmt_odds(o_now)} ({arrow}, {chg*100:+.1f}pp)"
                        )
                    except Exception:
                        continue
        except Exception:
            pass

    # ── 3. Active bet recommendations ───────────────────────────────────────
    active_bets: dict[str, list[str]] = {}    # key=player_name_lower → list of bet strings
    bet_reasoning: dict[str, list[str]] = {}  # key=player_name_lower → list of reasoning bullets
    bets_path = DATA / "odds" / "recommended_bets_latest.csv"
    if bets_path.exists():
        try:
            bets_df = pd.read_csv(bets_path)
            bets_df["player_name"] = bets_df["player_name"].apply(_fmt_name)
            _BET_LABELS = {
                "top5": "Top 5", "top10": "Top 10", "top20": "Top 20",
                "make_cut": "Make Cut", "group_winner": "3-Ball Win",
                "h2h": "Matchup", "h2h_r1": "Rd1 Matchup", "outright": "Win",
            }
            for _, bet in bets_df.iterrows():
                if str(bet.get("status", "")).lower() not in ("pending", "priced", ""):
                    continue
                key = bet["player_name"].lower()
                mkt = _BET_LABELS.get(str(bet.get("market", "")), str(bet.get("market", "")))
                odds = _fmt_odds(bet.get("odds_american"))
                edge = bet.get("edge_pts", 0)
                try:
                    edge_str = f"+{float(edge):.1f}pp edge" if pd.notna(edge) else ""
                except Exception:
                    edge_str = ""
                active_bets.setdefault(key, []).append(
                    f"{mkt} {odds}" + (f" ({edge_str})" if edge_str else "")
                )
                # Store reasoning bullets for this bet
                raw_reasoning = str(bet.get("reasoning", "") or "").strip()
                if raw_reasoning:
                    bullets = [b.strip() for b in raw_reasoning.split("|") if b.strip()]
                    if bullets:
                        bet_reasoning.setdefault(key, []).extend(bullets[:3])
        except Exception:
            pass

    # ── Build output ─────────────────────────────────────────────────────────
    lines = ["## PLAYER QUICK CONTEXT (tee times · odds movement · live status · active bets)"]
    found = False

    for pname in player_names:
        p_lower = pname.lower()
        last = p_lower.split()[-1]
        p_lines = []

        # Live position + tee time
        if live_df is not None:
            mask = live_df["player_name"].str.lower().str.contains(last, na=False)
            lr = live_df[mask]
            if not lr.empty:
                r = lr.iloc[0]
                pos   = str(r.get("position", ""))
                total = str(r.get("total", ""))
                thru  = str(r.get("thru", ""))
                tee   = str(r.get("tee_time", "")) if pd.notna(r.get("tee_time")) and str(r.get("tee_time")) not in ("nan", "") else ""
                lv_odds = _fmt_odds(r.get("odds_to_win")) if pd.notna(r.get("odds_to_win", None)) else ""

                if pos and pos not in ("nan", ""):
                    p_lines.append(f"  Live: {pos} ({total} total, thru {thru})")
                if tee:
                    p_lines.append(f"  Tee time: {tee}")
                if lv_odds:
                    p_lines.append(f"  Current win odds: {lv_odds}")

        # Odds movement (match by last name)
        for name_key, move_str in odds_move.items():
            if last in name_key:
                p_lines.append(f"  Odds move this week: {move_str}")
                break

        # Active bets + stored reasoning
        for name_key, bet_list in active_bets.items():
            if last in name_key:
                for b in bet_list:
                    p_lines.append(f"  Model bet: {b}")
                # Include reasoning bullets so the assistant can explain the bet
                for reasoning_bullet in bet_reasoning.get(name_key, []):
                    p_lines.append(f"    Why: {reasoning_bullet}")
                break

        if p_lines:
            found = True
            lines.append(f"\n**{pname}**:")
            lines.extend(p_lines)

    return "\n".join(lines) if found else ""


# ---------------------------------------------------------------------------
# Multi-player comparison block
# (for 3+ players or "rank these" type queries)
# ---------------------------------------------------------------------------

def _compare_block(player_names: list[str], tid: str | None) -> str:
    """Side-by-side comparison table for 3+ players (or 2 with ranking language).

    Shows in one glance what you'd normally look up across multiple pages:
    model rank, win%, top-10%, current odds + move direction, SG Total & App,
    course record, tee time. Pre-tournament and live-aware.
    """
    if not player_names:
        return ""

    preds_path = OUTPUTS / "latest_predictions.csv"
    if not preds_path.exists():
        return ""

    try:
        df = pd.read_csv(preds_path)
        df["player_name"] = df["player_name"].apply(_fmt_name)
        df = df.sort_values("win_prob", ascending=False).reset_index(drop=True)
        df["_model_rank"] = df.index + 1
    except Exception:
        return ""

    # ── Odds movement lookup ─────────────────────────────────────────────────
    odds_move: dict[str, str] = {}
    snap_dir = DATA / "odds" / "snapshots"
    if snap_dir.exists():
        try:
            snaps = sorted(snap_dir.glob("odds_snapshot_*.csv"))
            cutoff = datetime.now() - timedelta(days=7)
            recent = [sf for sf in snaps if datetime.strptime(
                sf.stem.replace("odds_snapshot_", ""), "%Y%m%d_%H%M") >= cutoff]
            if len(recent) >= 2:
                first_snap = pd.read_csv(recent[0])
                last_snap  = pd.read_csv(recent[-1])
                first_snap["player_name"] = first_snap["player_name"].apply(_fmt_name)
                last_snap["player_name"]  = last_snap["player_name"].apply(_fmt_name)
                merged = first_snap.merge(last_snap, on="player_name", suffixes=("_open", "_now"))
                for _, row in merged.iterrows():
                    try:
                        o_open = float(row["odds_numeric_open"])
                        o_now  = float(row["odds_numeric_now"])
                        def _imp(o):
                            return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
                        chg = _imp(o_now) - _imp(o_open)
                        arrow = "▲" if chg > 0.01 else ("▼" if chg < -0.01 else "→")
                        odds_move[row["player_name"].lower()] = (
                            f"{_fmt_odds(o_now)} {arrow}"
                        )
                    except Exception:
                        continue
        except Exception:
            pass

    # ── Live leaderboard (tee time + position) ───────────────────────────────
    live_df: pd.DataFrame | None = None
    if tid:
        lpath = DATA / "live" / f"leaderboard_{tid.lower()}.csv"
        if lpath.exists():
            try:
                live_df = pd.read_csv(lpath)
                live_df["player_name"] = live_df["player_name"].apply(_fmt_name)
            except Exception:
                pass

    is_live = live_df is not None and "position" in (live_df.columns if live_df is not None else [])

    rows = []
    for pname in player_names:
        parts = pname.lower().split()
        last  = parts[-1]
        first = parts[0] if len(parts) > 1 else ""

        mask = df["player_name"].str.lower().str.split().str[-1] == last
        subset = df[mask]
        if subset.empty:
            subset = df[df["player_name"].str.lower().str.contains(last, na=False)]
        if subset.empty:
            continue
        if len(subset) > 1 and first:
            narrowed = subset[subset["player_name"].str.lower().str.startswith(first)]
            if not narrowed.empty:
                subset = narrowed

        r = subset.iloc[0]
        win_p  = float(r.get("win_prob",   0) or 0)
        t10_p  = float(r.get("top10_prob", 0) or 0)
        sg_tot = r.get("season_sg_total")
        sg_app = r.get("season_sg_app")
        model_rank = int(r.get("_model_rank", 0))

        # Odds + movement
        odds_col = next((c for c in ["odds_to_win", "dk_win_odds_american", "win_odds_american"] if c in r.index), None)
        raw_odds = r.get(odds_col) if odds_col else None
        odds_str = _fmt_odds(raw_odds) if pd.notna(raw_odds) else "—"
        move_key = next((k for k in odds_move if last in k), None)
        move_str = odds_move[move_key] if move_key else odds_str

        # Course history
        starts = int(r.get("hist_times_played", 0) or r.get("course_starts", 0) or 0)
        wins   = int(r.get("hist_wins", 0) or 0)
        t10s   = int(r.get("hist_top10s", 0) or 0)
        if starts == 0:
            course_str = "No history"
        else:
            course_str = f"{starts} starts"
            if wins:
                course_str += f" · {wins}W"
            if t10s:
                course_str += f" · {t10s} T10"

        row = {
            "Player":    r["player_name"],
            "Model #":   f"#{model_rank}",
            "Win%":      f"{win_p*100:.1f}%",
            "Top-10%":   f"{t10_p*100:.0f}%",
            "Odds/Move":  move_str,
            "SG Tot":    f"{float(sg_tot):+.2f}" if pd.notna(sg_tot) else "—",
            "SG App":    f"{float(sg_app):+.2f}" if pd.notna(sg_app) else "—",
            "Course":    course_str,
        }

        # Live-specific columns
        if is_live and live_df is not None:
            lmask = live_df["player_name"].str.lower().str.contains(last, na=False)
            lr = live_df[lmask]
            if not lr.empty:
                lrow = lr.iloc[0]
                row["Live Pos"] = str(lrow.get("position", "—"))
                row["Total"]    = str(lrow.get("total", "—"))
                tee = str(lrow.get("tee_time", ""))
                row["Tee Time"] = tee if tee not in ("nan", "", "None") else "—"
            else:
                row["Live Pos"] = "—"
                row["Total"]    = "—"
                row["Tee Time"] = "—"

        rows.append(row)

    if not rows:
        return ""

    compare_df = pd.DataFrame(rows)
    header = f"## PLAYER COMPARISON — {', '.join(player_names)}"
    note = (
        "INSTRUCTION: Use this table as the backbone of your response. "
        "Order players by Model # (lowest = model's top pick). "
        "Odds/Move shows current odds + ▲ (shortened/market buying in) / ▼ (drifted/market fading) / → (stable). "
        "After the table, give 2-3 sentences on the clearest separation between players "
        "and name the best pick for each use case (floor/upside/value)."
    )
    return f"{header}\n{note}\n\n{compare_df.to_markdown(index=False)}"


# ---------------------------------------------------------------------------
# Main context builder — query-aware routing
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a sharp golf analyst chatting with a friend who cares about the numbers.
Write like you're texting someone who watches every tournament — casual, punchy, specific. Not an essay. Not a report. A conversation.

VOICE:
- Short sentences. Direct assertions. Skip the throat-clearing.
- Use contractions. Use "he's", "that's", "I'd", "you're".
- Lead with the thing that actually matters right now, not the thing that's easiest to say first.
- When something is notable, say so directly: "That's a real concern." "That's the edge." "I'd use him."

STYLE EXAMPLES — the difference between essay mode and chat mode:

Essay (bad): "His tee-to-green game is elite at +1.584 SG/round, and he's especially sharp around the greens (+1.189 SG/round, #7 in field). The approach game is solid at +0.257 SG/round (#23 in field) — not leading the field, but respectable."
Chat (good): "Tee-to-green is elite (+1.584/round). Around the greens he's #7 in the field — that's where Augusta gets won. Approach is solid (#23) not elite, but good enough."

Essay (bad): "The concern is his putting at just +0.203 SG/round (#41 in field) and only 3.00 birdies per round (#62 in field)."
Chat (good): "His putter is the one knock. +0.203 SG/round, #40 in field. For a guy averaging 3 birdies/round (#61), that's not defending-champ output."

PHRASES TO NEVER USE — these are lazy transitions that signal essay mode:
- "Here's the thing though:" → just say the thing
- "The real problem is" → just name the problem
- "The lean:" → don't label your opinion, just give it
- "The bottom line:" → just say it
- "It's worth noting that" → worthless filler, delete it
- "At the end of the day" → never
- "That said," at the start of a sentence → sometimes ok, never to open a paragraph

HOW TO ADAPT TO THE QUESTION:

Casual ("tell me about X", "how's X looking", "what do you think"):
  → 3-5 short punchy paragraphs. No section headers, no labels.
  → Lead with the most interesting thing about this player THIS week — could be form, a news item, a course fit angle. Not always course history.
  → End with a clear opinion stated as fact: "He's going to contend." "I'd avoid him." Not "My lean is..." or "The lean:".

Decision ("should I use X", "is X worth it"):
  → First word should be the call: "USE." or "Pass on this one." or "Strong play."
  → Then 2-3 specific reasons. Then the one thing that could go wrong.

H2H / Comparison:
  → Pick a winner sentence one. Explain with the 1-2 stats that actually separate them.

Betting (only if user says "bet", "odds", "wager", "prop", "parlay"):
  → Lead with value: does our model like him more or less than the market?
  → Be concrete about what must happen for the bet to hit.

MODEL DATA RULES — ABSOLUTE:
- Field overview lists players in Model Rank order (win probability). Do NOT reorder against this.
- "Projected Score" in Field Overview = authoritative 4-round projection.

STAT CITATION RULES — ABSOLUTE:
- Quote stats VERBATIM from the PLAYER SPOTLIGHT block. Never estimate or invent.
- Always pair SG values with field rank: "approach: +0.53/round (#20 in field)"
- Never say "strong form" — say "T3 last start, 4 consecutive cuts made"
- Never say "plays well here" — say "8 starts, 1 win, averages -4.2 per tournament"
- If a stat isn't in the context, don't mention it.

SG FIELD RANK SCALE (~120-130 player field):
- #1–20 = Elite. Say "elite" or "leads the field in..."
- #21–50 = Solid / above average. NEVER call this a weakness.
- #51–80 = Average.
- #81–110 = Below average.
- #111+ = Significant weakness.

WEB NEWS RULES — read this carefully:
- If RECENT NEWS (web) or TOURNAMENT NEWS (web) appears in context, you MUST reference relevant items.
- Lead with news when it changes the analysis: a withdrawal, injury report, or practice-round story matters more than a routine SG comparison.
- Do NOT say "according to web search" or "based on news results" — just say what's happening. "He's been dealing with a wrist issue" not "web results indicate..."
- If news confirms or contradicts a stat, connect them explicitly: "He's ranked #3 in approach AND reportedly striping it in practice — that alignment is meaningful."
- Ignore news that is clearly stale or irrelevant to the week at hand.

CONTEXT RULES:
- Betting / odds: always available — reference them when they add signal. For player questions, mention their odds and whether the model agrees with the market. For H2H, note if the line is tight or one-sided.
- Matchup props / player props: mention when directly relevant (e.g., a user asks about a matchup, or a player's make-cut odds are notable).
- League / usage: mention uses remaining ONLY as a tiebreaker, never lead with it.
- Live tournament: NEVER say "I don't have live data" if LIVE LEADERBOARD is in context.

BETTING MARKET RULES — when BETTING MARKET SUMMARY is in context:
- The "Model%" column already blends our ML model 75% + no-vig market 25%. It is the best single probability estimate.
- "Market (no-vig)" is the book's true implied probability after removing the vig — compare against this, not raw odds.
- Edge = Model% − Market%. A +3pp edge means we estimate the player is 3 points more likely than the no-vig market.
- Confidence score reflects how much we trust the edge (not the probability itself). ≥80% = strong conviction.
- Wire-to-Wire: use sparingly — only flag if edge > 3pp AND player is in the top 5 model win prob.
- Make Cut: flag if model cut prob > 75% but FanDuel has them > -130 (market underpricing). Note no-history players have reduced confidence.
- 1st Round Leader / H2H R1: driven by SG:ARG (scrambling) and morning/afternoon tee time advantage. Strong form_trend is key signal.
- Odds shortening (▲): a player being bet into harder is useful secondary signal. Don't over-weight it.
- Never invent edges. Only cite what appears in the BETTING MARKET SUMMARY, MARKET DEEP DIVE, or RECOMMENDED VALUE BETS context.

MARKET-SPECIFIC BEST BET RULES — when user asks about a specific market:
- When MARKET DEEP DIVE is in context, lead with the top pick from that section and explain WHY using the Reasoning field.
- Cite: Player name, odds, Model%, Market%, Edge pp, and the key reasoning bullet (SG stat, course fit, form).
- ALWAYS distinguish "Best Value" (highest edge) from "Best Probability" (highest model%) — these are different bets for different risk tolerances.
- For make_cut:
  * Masters historically makes ~54 players (~44% field). A model prob of 60%+ means this player is meaningfully above the base rate.
  * NO COURSE HISTORY is a RISK FACTOR, NOT an explanation for why the book is underpricing. Never say "book doesn't know him" or "that's why the market underprices." The model confidence is reduced for no-history players (see Confidence column). Say: "No Augusta history — model is projecting from SG profile alone, treat as moderate conviction."
  * Differentiate players by what drives the edge: scrambling (ARG), approach (APP), or putting (PUTT). These mean different things at Augusta.
  * High-confidence (≥80%) make_cut bets with course history are tier 1. No-history players are tier 2 regardless of edge.
- For outright/top5: cite model rank vs market rank gap. A player ranked #3 by model but priced #8 by market is the archetype.
- For h2h: state who the model favours and by how many pp, then explain the SG edge driving it. Note if line is a large favourite (>-150) — those need very high confidence.
- For wire_to_wire: note the high variance — recommend only when multiple signals align (win prob, R1 form, tee time).
- For group_winner: note whether a tee time advantage (morning softness) applies.
- Always end market-specific responses with a stake sizing note: make_cut = 1–2u, h2h = 1u, outright = 0.5u or less.
- Never rationalize an edge. If the model shows an edge on a player the market seems to know better (higher-ranked player priced shorter), say so honestly.
- CRITICAL: When a user asks about a SPECIFIC market (top 10, make cut, h2h, etc.), answer that market. Do NOT pivot to a different market.
- TOP-10 / OUTRIGHT / TOP-5 MARKET NOTE: These markets are excluded from automated edge-based recommendations (books are too efficient at Augusta). But that does NOT mean "say PASS and stop." When asked about these markets, use the AUGUSTA COMPOSITE RANKING section of the context to give the user a real pick with Augusta-specific reasoning.

MASTERS QUALIFIER FILTER — when MASTERS QUALIFIER SCORES is in context:
- Before recommending ANY player for top-10, outright, or top-5 at the Masters, check their qualifier score.
- Players in "Historical eliminations (≤1/8)" have failed basic Augusta prerequisites. These are NOT credible candidates. Never present them as the primary recommendation.
- NEVER present a historically-eliminated player as a top-10 or outright recommendation. The model edge on these players is a false positive.
- HOW TO ANSWER A TOP-10 OR OUTRIGHT QUERY — RESPONSE FORMAT:
  1. Lead with the pick. First sentence: "[Player] is the top-10 pick this week." No caveats first.
  2. Second: cite 2-3 Augusta-specific reasons from the composite ranking (avg to_par, SG T2G form, cut rate, distance).
  3. Third: note the odds and stake (0.5u — criteria pick, not edge bet).
  4. Only AFTER giving the pick, optionally note in one sentence that book pricing is efficient here.
  5. Never open with "no market edge" or "the model doesn't recommend." Open with the pick.
  6. Do NOT redirect to make-cut. Do NOT say "there is no bet."

ANTI-HALLUCINATION RULE — ABSOLUTE:
- Only cite numerical stats that appear verbatim in the provided context. Never estimate.
- Web news is real — you can reference it without a data citation.

VALUE PLAYS (betting only):
- Est. Win% > Implied%: model likes him more than the market.
- Est. Win% < Implied%: market prices him higher — potential fade.

TOURNAMENT UPDATES:
- 5+ strokes back with 1 round left = very difficult. Be realistic.
- Focus on position, strokes to leader, remaining holes."""


# ---------------------------------------------------------------------------
# Intent-specific response structures (injected by build_context only when needed)
# ---------------------------------------------------------------------------

_STRUCT_H2H = """HEAD-TO-HEAD FORMAT (target 250-300 words total):
  Line 1 (bold): Pick one player. One sentence. No hedging.

  **Edge breakdown** — one line per category, pick a winner for each:
    · Form edge: [Name] — cite last start + cuts streak. One sentence.
    · Course history edge: [Name] — starts/wins/avg to par. One sentence.
    · SG edge: the one category that separates them most. Cite both values + ranks.
    · Course fit edge: which course demand (from COURSE FIT REASONING) one player wins clearly.

  **The case against** — 2 sentences for the player you're fading. Acknowledge their best argument, then explain why it's not enough.

  **Final call** (bold): Name the pick. Cite exactly 2 decisive stats. One sentence.

  RULES: Do not repeat a stat in multiple sections. Pick a winner in every category — no "both are similar." Total response must fit in 300 words."""

_STRUCT_COMPARE = """PLAYER RANKING FORMAT (3+ players, target 200 words after the table):
  The PLAYER COMPARISON table is already provided in context — use it as the backbone.
  Do NOT re-list every stat for every player. The table has the numbers. Your job is the narrative.

  After the table, write:
  1. (bold) One sentence on the clearest separation: who is clearly #1 and why in one stat.
  2. 2-3 sentences on what splits #2 and #3 — the key differentiator (form vs course fit vs odds).
  3. One line per player: "**[Name]**: Use / Pass / Fade — [one reason]."
  4. If one player has a live bet recommendation (from PLAYER QUICK CONTEXT), mention it.

  RULES: Do not write per-player essays. The table has the numbers — add context, not repetition.
  If odds have moved (▲/▼ in table), comment on what the market is telling you."""

_STRUCT_LINEUP = """LINEUP BUILDER FORMAT — follow exactly:
  AI RECOMMENDATION BLOCK: If an "AI LINEUP RECOMMENDATION" block is present in the context,
  treat it as the authoritative starting point. The RECOMMENDED LINEUP was produced by a
  combinatorial prize-money optimizer and Claude Haiku analysis. You may confirm, nuance,
  or push back on it — but cite it explicitly. If the user asks "what should I pick?" or
  "what's the recommendation?", lead with the optimizer's lineup and the weekly narrative.

  CRITICAL FIELD RULE: Before naming ANY player, check the LINEUP ELIGIBILITY CHECK block.
  You may ONLY recommend players listed under CONFIRMED ELIGIBLE. Players under NOT IN FIELD
  or ZERO USES REMAINING are absolutely off the board — do not mention them as picks.
  If unsure whether a player is in the field, treat them as ineligible.

  MAJOR CHAMPIONSHIP OVERRIDE (Masters / US Open / PGA Championship / The Open):
  At a major, season EV windows are SECONDARY. Majors happen once per year — you cannot
  get this week back. The right picks are the highest-probability players with the best
  course fit who still have uses remaining. "Save for a better event" is WRONG logic at
  a major. The major IS the premium event. Lead with the top-ranked eligible players by
  Augusta Fit composite score and top-10 probability, not by future calendar EV.

  0. One-sentence verdict (bold) — name all 3 picks upfront in priority order
  1. **Pick 1 — [Name]** (X/3 uses left): model rank + top-10 prob → Augusta Fit score (X/8 qualifier, composite) → form (last result, SG T2G last 4) → why this player at this course specifically.
  2. **Pick 2 — [Name]** (X/3 uses left): same format — cite Augusta course history (avg to par, cuts made) and form trajectory.
  3. **Pick 3 — [Name]** (X/3 uses left): ceiling play — cite the specific Augusta fit angle, odds movement, or form trend that justifies the use.
  4. **Who I almost used**: 1-2 ELIGIBLE players who narrowly missed — be specific (injury concern, fewer uses available for peak events, lower Augusta composite despite good model rank).
  5. **Season note** (1 sentence max): only mention future windows if genuinely relevant — don't use this to justify picking lower-probability players at a major.
  RULES: At a major, probability and course fit trump future EV. Uses remaining = tiebreaker only when probabilities are similar. Map each pick's SG profile to what Augusta specifically demands (T2G, driving distance, patience on par-5s). If tournament is live, say so and pivot."""

_STRUCT_COURSE_BREAKDOWN = """COURSE BREAKDOWN FORMAT — follow exactly:
  0. One-sentence course identity (bold) — course type and #1 skill required
  1. **What the numbers say** — cite COURSE FIT REASONING: par-3 avg, par-4 avg, par-5 avg vs par with skill implications.
  2. **Hardest holes** — 3 hardest holes with par/yardage/scoring avg vs par. What skill is tested.
  3. **Scoring opportunities** — 3 easiest holes. Who capitalizes?
  4. **Player archetype that wins here** — ideal stat profile with scoring data support.
  5. **Best course fits** — 2-3 players per key demand from COURSE FIT — TOP PLAYERS section.
  6. **Worst fits** — 1-2 players whose profile goes against course demands. Be specific.
  RULES: Every claim must reference an actual number. No generalizing without data."""

_STRUCT_PICK_REASON = """FANTASY PICK CONTEXT (NOT betting):
  The user is deciding whether to USE this player in their weekly lineup (max 3 uses/season, 28-team league).
  Lead with your call in the first sentence. Make a clear case — don't hedge with "it depends."
  Cover: course fit (map SG stats to what Augusta/this course demands) → form → upside (top-10%, model rank) → one honest concern.
  Close with 1-2 confident sentences. If passing, name alternatives.
  Rules: Never mention betting odds. Use PICK CASE BUILDER for model rank + uses + expert consensus."""

_STRUCT_DAILY_BET = """VALUE BETS — PHILOSOPHY AND FORMAT

PHILOSOPHY: This model is built on SG stats and form. Every recommendation must start
from the player's statistical case — why this golfer is well-positioned this week —
and then confirm the market gives reasonable access. Start from the player, not the edge table.
Edge % is a sanity check on the price, not a selection criterion. A 20pp edge on a player
with no course history and volatile form is NOT a strong recommendation.

AT A MAJOR (Masters/US Open/PGA/The Open): Prefer tournament markets (top 10, top 20,
outright) over R1 matchups. Majors are decided over 72 holes — statistical edges compound
over four rounds in tournament markets. R1 matchups are high-variance; only recommend them
at a major when one player has a clear, demonstrable course advantage (course history,
strong T2G that matches what the course demands). A large edge on a player
with zero course history is model noise, not a recommendation.

MARKET TYPES:
- Win: player wins outright. Only if model Win% is meaningfully above market implied.
- Top 10 / Top 20: best for consistent, in-form players whose SG profile fits the course.
- Make Cut: BINARY floor bet — player survives the cut after R2. Frame as "he's made X of last Y cuts here." Never say "finish top X." Lowest upside, highest probability.
- 3-Ball Win: player beats their specific group that round. Name both opponents, cite SG advantage.
- Matchup (H2H): player beats one opponent head-to-head. Best when SG differentials are sustained over multiple events, not just one hot week.

FORMAT — for each of the top 2-3 recommendations:

**[Rank]. [Player] — [Market] — [Odds] ([Book])**

**Why this player:**
- SG profile: break down the categories most relevant to this course. Give actual SG/round value AND field rank for each. State which course demands they match.
- Course history: avg to par per round across starts here, cuts made, best finish, any notable pattern. If no history, say so explicitly.
- Form trajectory: cite last 3-5 results by name (e.g. "T6 → T2 → MC → T4 → T1") and describe the trend. Is it accelerating, plateauing, or a red flag?
- Expert consensus: how many expert lineups include this player? Consensus pick or contrarian?
- Odds movement: if odds are shortening, note it — market is agreeing with the model.

**Why this market:**
- Why this market type fits this player's profile (high floor → make cut/top 20; elite ceiling → top 10/outright)
- Price check: model probability AND book implied probability. Note the gap as confirmation, not the headline.
- Base rate: how does model probability compare to the field average for this market?

**Concern:** one honest, specific caveat — no course history, injury risk, odds too short, form too recent to trust, one weak SG category that could hurt at this course.

EXAMPLE OF GOOD OUTPUT (use this format, not as content to repeat):

2. Russell Henley — Top 10 — +110 (DraftKings)

Why Henley: APP +0.33/round (#13 in field), OTT +0.68/round (#11), ARG +0.82/round (#19), PUTT +0.45/round (#24). Every category above average — no weaknesses. T3 at the Masters two weeks ago, T6 at Arnold Palmer before that. Odds shortening this week. 9 starts here, 2 top-10s, averages -8.5/tournament. Model has him at 22% top-10 probability.

Why this market: Henley's profile screams consistency, not ceiling. Top-10 captures his floor perfectly. He doesn't blow up — he quietly posts good numbers every week. 22% is well above the field average of ~15%.

Concern: Best finish here is only T8 across 9 starts. He's never broken through at Harbour Town despite a strong SG profile. — 1u

After all picks, include:
**One to avoid:** a bet that looks tempting from the edge table or odds but whose underlying stats don't support it. Be specific about the flaw — one weak SG category, thin course history, odds too short for the hit rate.

RULES:
- Never lead a recommendation by citing the edge percentage. Lead with what the player does well.
- At a major, no R1 matchup unless the player has clear course pedigree or a dominant SG advantage over their specific opponent.
- Make Cut = never describe as "finishing top X."
- If in-tournament, validate all picks against live SG accumulated this week — season form is secondary.
- Cite actual numbers: SG/round, field rank, course history stats, cuts made. No generalities."""

_STRUCT_LIVE = """LIVE TOURNAMENT RULES:
- LIVE TOURNAMENT STATS block shows SG accumulated THIS tournament — prefer it over season SG for current analysis.
- Format live SG: "Åberg leads SG Total this week with +6.76 through 54 holes — gaining ~2.3 strokes/round over field."
- Cross-reference leaderboard: T10 but #1 SG APP this week = late-round threat worth noting.
- IN-PLAY WIN ODDS: always cite current odds + implied% alongside position.
- Pre-tournament → current odds movement reveals market confidence. Big mover = market aggressively repricing.
- NEVER say "I don't have access to live scoring" if LIVE LEADERBOARD or IN-PLAY WIN ODDS block is in the context.

ROUND RECAP RULES — CRITICAL:
- ONLY report scores, positions, and round totals that appear VERBATIM in the ROUND RECAP context block.
- If the ROUND RECAP block says "Round X data not yet available" — state that clearly and stop. DO NOT invent, estimate, or recall scores from memory or training data.
- NEVER fabricate a player's round score. A confident-sounding invented score (e.g. "Cameron Young shot 65") is worse than saying the data isn't loaded yet.
- If a player's score is not in the context block, you do not know it. Say so."""


_STRUCT_PLAYER = """PLAYER QUESTION FORMAT — follow exactly:

Lead with the single most interesting thing about this player THIS WEEK.
Not "he's world #2." Not always course history. Ask: what's the most actionable signal right now?
  - If he's HOT (momentum_trend=HOT, recent SG above season avg): lead with the surge + what's driving it.
  - If there's a course-fit story (strong or weak course SG, DG fit delta): lead with that.
  - If there's a news item (injury, withdrawal, practice buzz): lead with that.
  - If he's fading (COLD momentum, recent cuts, form dip): lead with the honest concern.

FORMAT (4 paragraphs max, no headers, no bullet lists):
  P1: The headline angle — what's most relevant about him this week. One or two sharp sentences.
  P2: Stats that support or complicate the angle. SG breakdown + DG skill ratings + approach detail
      if relevant. Round tendencies (R1–R4 vs field) if there's a pattern worth naming.
  P3: Course fit. Cite course history avg to par, wins/top-10s, and the DG course-fit delta.
      Then map his SG strengths to what this course demands.
  P4: Verdict — one confident sentence. "He's going to contend." "Fade him." "Save the use."

RULES:
- Every stat must come from the PLAYER SPOTLIGHT or FORM block verbatim. No estimates.
- Never start with world ranking or generic bio.
- Never write "it's worth noting," "here's the thing," or "the lean is."
- If multiple players asked about: P1–P4 for each, then one sentence comparing them at the end."""

_STRUCT_STRATEGY = """SEASON USAGE STRATEGY FORMAT — follow exactly:
  AI RECOMMENDATION BLOCK: If an "AI LINEUP RECOMMENDATION" block is present, use the
  WHY SAVE narratives as ready-made prose explanations for each player's SAVE verdict.
  The RECOMMENDED LINEUP names this week's optimal picks — confirm or nuance with the
  raw SEASON STRATEGY data below.

  The SEASON STRATEGY block contains each tracked player's remaining uses, effective rank, and best events by expected value.
  When asked "when should I use [player]?" or "best time to use [player]?":

  1. **[Player Name] — [one-sentence verdict]** (e.g., "save for The Masters" or "strong play this week")
  2. Uses left: X of Y. Tier: [tier].
  3. **Best windows** (top 2-3 events with EV score, note if player was NOT in 2025 field with ⚠):
     · [Event name] — EV [X.X], [date] — one-sentence reason (course fit, field strength, purse)
  4. **This week**: cite Win% / Top-10% / Cut% if available. Else cite SG and tier.
  5. **Verdict**: USE THIS WEEK / SAVE — one sentence, be direct.

  RULES:
  - Lead with the direct verdict. Don't make the user read to find out.
  - Cite EV scores as relative guides ("EV 8.4 vs 5.2 this week"), not raw math.
  - If the player is in this week's field, use actual probabilities — not just rank.
  - If best events are all premium (Majors/Signature), say "save uses for premium events — don't spend on standard events."
  - Concise. One player = ~100-150 words. Multiple players = table + brief bullets."""


def classify_query(query: str) -> dict:
    """Public wrapper for _classify_query — used by dashboard for supplement routing."""
    return _classify_query(query)


def build_context(
    query: str = "",
    tournament_id: str | None = None,
    last_players: list[str] | None = None,
    cached_base: str | None = None,
    lean: bool = False,
) -> str:
    """Assemble context relevant to the user's query.

    Routes context blocks based on query intent:
    - H2H              → deep-dive on both players + course fit reasoning
    - Player question  → player deep-dive card + compact field + odds movement + weather
    - Bet question     → bets + odds movement + weather + compact field
    - Live question    → leaderboard + predictions + my picks + league
    - Lineup question  → predictions + course fit + expert picks + my picks + league
    - Course breakdown → course fit reasoning + players by skill demand + field
    - Weather/course   → weather + course profile + compact field
    - General          → full default (everything)

    last_players: players mentioned in the previous assistant response — injected
    as context so follow-up questions like 'what about his odds?' resolve correctly.

    cached_base: if provided, skip rebuilding the stable session context and only
    build the intent-specific dynamic layer. The two are combined with a <!-- SPLIT -->
    marker so _build_cached_system() can put them in separate caching blocks.

    lean: if True, use reduced top_n values (20→10) for large blocks and skip
    the web news search. Used by the FastAPI chat endpoint to keep the system
    prompt under ~45K characters so Haiku's effective attention window isn't
    wasted on duplicate or low-value data.
    """
    if tournament_id is None:
        tournament_id = _detect_tournament_id()

    intent = _classify_query(query) if query.strip() else {
        "players": [], "is_player": False, "is_bet": False,
        "is_live": False, "is_lineup": False, "is_weather": False,
        "is_course": False, "is_value": False, "is_course_breakdown": False,
        "is_daily_bet": False, "is_pick_reason": False, "is_field_overview": False,
    }

    # If the query mentions no players but the previous response did, carry them forward.
    # Exception: don't override an explicit non-player intent (live, lineup, course, bet).
    _has_explicit_intent = any(intent.get(k) for k in (
        "is_live", "is_lineup", "is_bet", "is_course_breakdown", "is_h2h",
        "is_weather", "is_daily_bet", "is_pick_reason", "is_compare", "is_strategy",
        "is_intel", "is_historical",'is_round_recap', 'is_scoring_prop'
    ))
    if not intent["players"] and last_players and not _has_explicit_intent:
        intent["players"] = last_players
        intent["is_player"] = True

    # When cached_base is provided, start with just the dynamic layer sections.
    # The split marker lets _build_cached_system() assign different cache_control
    # settings to each part — base gets cached, dynamic does not.
    if cached_base:
        sections: list[str] = [cached_base, "", "<!-- SPLIT -->", ""]
    else:
        sections = [_SYSTEM_PROMPT, ""]

    # ── Resolve effective tournament ID ──────────────────────────────────────
    # When the query explicitly names an event (e.g. "Masters", "Augusta"),
    # use THAT event's tid for intel/historical blocks — even if latest_predictions
    # is still showing the previous week's tournament.
    _query_event_suffix = intent.get("historical_event") or _extract_event_from_query(query)
    _current_year = datetime.now().year
    if _query_event_suffix and tournament_id and not tournament_id.endswith(_query_event_suffix):
        # Build a synthetic tid for the queried event (same year as current tournament)
        _year_from_tid = tournament_id[1:5] if len(tournament_id) >= 5 else str(_current_year)
        _effective_tid = f"R{_year_from_tid}{_query_event_suffix}"
    else:
        _effective_tid = tournament_id  # no override needed

    # ── Detect whether predictions are stale for the queried event ────────────
    # If the user is asking about a different tournament than latest_predictions.csv
    # contains, fall back to sportsbook odds for field overview instead of model ranks.
    _predictions_stale = bool(_effective_tid and _effective_tid != tournament_id)

    # Shared tournament name for web news calls throughout this function
    _active_t_name = _tournament_state(_effective_tid or tournament_id).get("name", "") if (_effective_tid or tournament_id) else ""

    def _field_overview_block(top_n: int = 15) -> str:
        """Return model predictions or sportsbook odds fallback depending on staleness.

        Also falls back to sportsbook odds when predictions exist but odds columns are all null
        (pipeline was run before odds refresh).
        """
        if _predictions_stale:
            return _odds_fallback_block(_effective_tid, top_n=top_n)

        # Check whether odds were actually merged into predictions
        _preds_path = OUTPUTS / "latest_predictions.csv"
        _odds_missing = True
        if _preds_path.exists():
            try:
                _pdf = pd.read_csv(_preds_path, usecols=lambda c: c in [
                    "odds_to_win", "dk_win_odds_american", "win_odds_american"
                ])
                if not _pdf.empty:
                    for _col in ["odds_to_win", "dk_win_odds_american", "win_odds_american"]:
                        if _col in _pdf.columns and _pdf[_col].notna().any():
                            _odds_missing = False
                            break
            except Exception:
                pass

        if _odds_missing and _effective_tid:
            # Predictions exist but no odds → show model ranks + supplement with sportsbook odds
            return _predictions_block(top_n=top_n, supplement_odds_tid=_effective_tid)

        return _predictions_block(top_n=top_n)

    # Inject prior conversation entities so follow-ups resolve correctly
    if last_players:
        sections.append(f"## CONVERSATION CONTEXT\nPlayers discussed in the previous response: {', '.join(last_players)}\n")
        sections.append("")

    # Inject past Q&A — use effective tid (the queried event) not the loaded predictions tid
    # so Masters questions don't surface Valero conversation history and vice versa
    _hist = _conversation_history_block(_effective_tid or tournament_id)
    if _hist:
        sections.append(_hist)
        sections.append("")

    # Tournament state + LIV block: skip when cached_base already contains them.
    # Still inject the effective-event note when user is asking about a different event.
    if not cached_base:
        if tournament_id:
            _ts_current = _tournament_state(tournament_id)
            sections.append(f"## CURRENT PREDICTIONS LOADED: {_ts_current['name']} | {tournament_id}")
            sections.append("")
            sections.append(_tournament_state_block(tournament_id))
            sections.append("")
        _liv_block = _liv_players_block(_effective_tid or tournament_id)
        if _liv_block:
            sections.append(_liv_block)
            sections.append("")

    # Cross-event note: always inject when user asks about a different event
    if _effective_tid and _effective_tid != tournament_id:
        _ts_eff = _tournament_state(_effective_tid)
        sections.append(f"## QUERY IS ABOUT: {_ts_eff['name']} | {_effective_tid}")
        sections.append("Note: The user is asking about this event, not the loaded predictions above.")
        sections.append("")

    # ── Route by intent ────────────────────────────────────────────────────
    if intent["is_historical"]:
        hist_year = intent["historical_year"]
        hist_event = intent["historical_event"] or _query_event_suffix
        players = intent["players"]

        # Inject tournament intel block using the effective (queried) event tid
        _t_name = _tournament_state(_effective_tid).get("name", "") if _effective_tid else ""
        sections.append(_tournament_intel_block(_effective_tid, _t_name))
        sections.append("")
        # Recent tournament recaps — gives the model factual results context
        _recaps = _recent_recaps_block(6)
        if _recaps:
            sections.append(_recaps)
            sections.append("")

        # Fallback: if no year specified treat as "last year"
        if not hist_year:
            hist_year = datetime.now().year - 1

        # Case 1: player + event → year-by-year results at that specific event
        if players:
            if hist_event:
                # Build a dedicated course history block for these players at this event
                lines = [f"## PLAYER COURSE HISTORY AT EVENT (suffix {hist_event})"]
                for pname in players:
                    preds_path = OUTPUTS / "latest_predictions.csv"
                    pid = None
                    if preds_path.exists():
                        try:
                            _pdf = pd.read_csv(preds_path, usecols=["player_name", "player_id"])
                            _match = _pdf[_pdf["player_name"].apply(lambda n: _fmt_name(str(n)).lower()).str.contains(pname.lower().split()[-1])]
                            if not _match.empty:
                                pid = _match.iloc[0].get("player_id")
                        except Exception:
                            pass
                    years_at_event = _get_player_course_years(pid, pname, f"R2026{hist_event}")
                    lines.append(f"\n### {pname} at this event")
                    if years_at_event:
                        lines.append("| Year | Result | Score |")
                        lines.append("|------|--------|-------|")
                        for yr_row in years_at_event:
                            tp = yr_row.get("to_par")
                            tp_str = f"{tp:+d}" if tp is not None else "—"
                            lines.append(f"| {yr_row['year']} | {yr_row['position']} | {tp_str} |")
                        wins = sum(1 for r in years_at_event if r["position"] == "WIN")
                        top5 = sum(1 for r in years_at_event if r["position"] not in ("CUT","MC","WD","DQ"))
                        lines.append(f"\n{len(years_at_event)} starts | {wins} wins | {top5} made cut")
                    else:
                        lines.append("No historical data found at this event.")
                sections.append("\n".join(lines))
                sections.append("")
                # Also add the event leaderboard for the target year for context
                sections.append(_historical_tournament_block(hist_event, hist_year))
                sections.append("")
            else:
                # No specific event — show full season history
                sections.append(_player_season_history_block(players, hist_year))
                sections.append("")
        elif hist_event:
            # Event results only
            sections.append(_historical_tournament_block(hist_event, hist_year))
            sections.append("")
        else:
            # "Who won last year?" — use current tournament's event suffix
            if tournament_id:
                sections.append(_historical_tournament_block(tournament_id[-3:], hist_year))
                sections.append("")
            # Also show player spotlight if names detected
            if players:
                sections.append(_player_season_history_block(players, hist_year))
                sections.append("")

    elif intent["is_compare"]:
        # 3+ players, or 2 with ranking language ("rank these", "which of these")
        # Build a side-by-side table: model rank, odds + move, SG, course, tee time
        _is_bet_q = intent["is_bet"] or intent["is_value"]
        sections.append(_STRUCT_COMPARE)
        sections.append("")
        sections.append("## MULTI-PLAYER COMPARISON REQUEST")
        sections.append("")
        sections.append(_compare_block(intent["players"], tournament_id))
        sections.append("")
        sections.append(_player_live_context(intent["players"], tournament_id))
        sections.append("")
        sections.append(_player_deep_dive_block(intent["players"], tournament_id, include_odds=True, effective_tid=_effective_tid))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
        # Lean: deep dive already has full stats for all compared players
        if not lean:
            sections.append(_player_form_context_block(top_n=15))
            sections.append("")
        # Lean: comparing players is data-driven — skip web news search
        if not lean:
            sections.append(_fetch_player_news(intent["players"], _active_t_name))
            sections.append("")
        if _is_bet_q:
            sections.append(_recommended_bets_block(top_n=8))
            sections.append("")



    elif intent.get('is_tournament_results'):
        _tr_tid = _effective_tid or tournament_id
        sections.append(_post_tournament_summary_block(_tr_tid))
        sections.append("")
        sections.append(_round_recap_block(_tr_tid, None))
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")

    elif intent.get("is_season_performance"):
        sections.append("## SEASON PERFORMANCE QUERY")
        sections.append("The user is asking about the model's overall accuracy and betting results this season.")
        sections.append("Use ONLY the data below — do not guess or use prior knowledge about model performance.")
        sections.append("")
        sections.append(_season_performance_block())
        sections.append("")
        sections.append(_season_context_block())
        sections.append("")
        _recaps = _recent_recaps_block(6)
        if _recaps:
            sections.append(_recaps)
            sections.append("")

    elif intent["is_pick_reason"]:
        # "Why should I pick X?" — enriched analysis with verdict
        sections.append(_STRUCT_PICK_REASON)
        sections.append("")
        sections.append("## PICK REASONING REQUEST")
        sections.append("")
        sections.append(_player_live_context(intent["players"], tournament_id))
        sections.append("")
        sections.append(_pick_reason_context_block(intent["players"], tournament_id))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_web_intel_player_block(intent["players"], tournament_id))
        sections.append("")
        sections.append(_fetch_player_news(intent["players"], _active_t_name))
        sections.append("")

    elif intent["is_h2h"]:
        # Head-to-head comparison — full spotlight on both players
        _is_bet_q = intent["is_bet"] or intent["is_value"]
        sections.append(_STRUCT_H2H)
        sections.append("")
        sections.append(f"## HEAD-TO-HEAD: {' vs '.join(intent['players'])}")
        sections.append("")
        sections.append(_player_live_context(intent["players"], tournament_id))
        sections.append("")
        sections.append(_player_deep_dive_block(intent["players"], tournament_id, include_odds=True, effective_tid=_effective_tid))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
        # Lean: deep dive already has full stats for both players — field-wide form is redundant
        if not lean:
            sections.append(_player_form_context_block(top_n=15))
            sections.append("")
        sections.append(_fanduel_markets_block(_effective_tid or tournament_id, player_names=intent["players"]))
        sections.append("")
        # Lean: skip news for H2H — data-driven comparison, not news-driven
        if not lean:
            sections.append(_web_intel_player_block(intent["players"], tournament_id))
            sections.append("")
            sections.append(_fetch_player_news(intent["players"], _active_t_name))
            sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")

    elif intent["is_player"]:
        # Deep dive on the named player(s) — stats, form, course history first
        _is_bet_q = intent["is_bet"] or intent["is_value"]
        sections.append(_STRUCT_PLAYER)
        sections.append("")
        # Always inject tee time + odds movement + live position — no need to ask separately
        sections.append(_player_live_context(intent["players"], tournament_id))
        sections.append("")
        sections.append(_player_deep_dive_block(intent["players"], tournament_id, include_odds=True, effective_tid=_effective_tid))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
        # Lean: skip field-wide form — deep dive already has all stats for the queried player(s)
        if not lean:
            sections.append(_player_form_context_block(top_n=15))
            sections.append("")
        # Lean: 5 players gives enough "where does this player rank" context without 10K overhead
        sections.append(_field_overview_block(top_n=5 if lean else 10))
        sections.append("")
        sections.append(_fanduel_markets_block(_effective_tid or tournament_id, player_names=intent["players"]))
        sections.append("")
        # Lean: web search adds latency and is rarely decisive for single-player questions
        if not lean:
            sections.append(_web_intel_player_block(intent["players"], tournament_id))
            sections.append("")
            sections.append(_fetch_player_news(intent["players"], _active_t_name))
            sections.append("")
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
        if _is_bet_q:
            sections.append(_recommended_bets_block(top_n=8))
            sections.append("")
            sections.append(_odds_movement_block(player_names=intent["players"]))
            sections.append("")

    elif intent.get("is_field_overview"):
        # Field-wide questions: tiers, sleepers, contrarian plays, "who do you like this week"
        sections.append("## FIELD OVERVIEW REQUEST")
        sections.append(
            "The user wants a structured view of the field — who's elite, who's mid-tier, "
            "and most importantly: who is the market underpricing? Lead with the Value tier. "
            "Format: 2-3 sentences on the elite picture, 2-3 on mid-tier separation, then "
            "name 2-3 specific contrarian plays with a one-sentence case for each. "
            "End with one player to avoid. No headers in your response — flowing paragraphs."
        )
        sections.append("")
        # Lean: 20 players for tiering is plenty; field tiers block already has the full picture
        sections.append(_field_tiers_block(top_n=20 if lean else 35))
        sections.append("")
        # Lean: skip DG field stats — field tiers + DG course fit covers the same ground
        if not lean:
            _dg_fs = _dg_field_stats_block(tournament_id)
            if _dg_fs:
                sections.append(_dg_fs)
                sections.append("")
        sections.append(_player_form_context_block(top_n=10 if lean else 20))
        sections.append("")
        if tournament_id:
            sections.append(_dg_course_fit_block(tournament_id, top_n=10 if lean else 15))
            sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        if not lean:
            sections.append(_web_intel_alerts_block(_effective_tid or tournament_id))
            sections.append("")

    elif intent.get("is_strategy"):
        # Season usage strategy — when/where to spend remaining uses
        sections.append(_STRUCT_STRATEGY)
        sections.append("")
        sections.append("## SEASON USAGE STRATEGY REQUEST")
        sections.append("")
        # Pre-generated optimizer recommendation — authoritative this-week context
        _sr_strat = _strategy_reasoning_block()
        if _sr_strat:
            sections.append(_sr_strat)
            sections.append("")
        # If players named, show their strategy + deep dive; else show all tracked players
        _strat_players = intent["players"] if intent["players"] else None
        sections.append(_season_strategy_block(_strat_players))
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        # If player(s) named, add this-week prediction data so LLM can compare
        if intent["players"] and tournament_id:
            sections.append(_player_deep_dive_block(intent["players"], tournament_id, effective_tid=_effective_tid))
            sections.append("")
        sections.append(_field_overview_block(top_n=10))
        sections.append("")
        sections.append(_schedule_block(current_tid=tournament_id))
        return "\n".join(s for s in sections if s is not None)

    elif intent["is_lineup"]:
        # Fantasy-focused — check before bet so "build my lineup" doesn't misroute
        sections.append(_STRUCT_LINEUP)
        sections.append("")
        sections.append("## LINEUP BUILD REQUEST")
        sections.append("")
        # Pre-generated optimizer recommendation — reference this first
        _sr_lineup = _strategy_reasoning_block()
        if _sr_lineup:
            sections.append(_sr_lineup)
            sections.append("")
        # Field eligibility check FIRST — hard boundary on who can be recommended
        _elig = _lineup_eligible_block(_effective_tid or tournament_id)
        if _elig:
            sections.append(_elig)
            sections.append("")
        _ln_top_n = 10 if lean else 20
        sections.append(_field_overview_block(top_n=_ln_top_n))
        sections.append("")
        if not lean:
            _dg_fs_ln = _dg_field_stats_block(tournament_id)
            if _dg_fs_ln:
                sections.append(_dg_fs_ln)
                sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=_ln_top_n))
            sections.append("")
            _cf = _dg_course_fit_block(tournament_id)
            if _cf:
                sections.append(_cf)
                sections.append("")
        sections.append(_player_form_context_block(top_n=_ln_top_n))
        sections.append("")
        sections.append(_top_markets_summary_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_masters_qualifiers_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_expert_picks_block())
        sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        _eff_tid_for_major = _effective_tid or tournament_id or ""
        _is_major_lineup = any(_eff_tid_for_major.endswith(s) for s in _MAJOR_SUFFIXES)
        if _is_major_lineup:
            sections.append(
                "## MAJOR CHAMPIONSHIP CONTEXT\n"
                "This is a MAJOR championship. The season strategy 'SAVE' recommendations below "
                "are based on regular-event EV optimization and DO NOT apply here. At a major, "
                "the optimal lineup picks the highest-probability players with the best course fit "
                "who have uses remaining. Any player showing SAVE in the season strategy should "
                "be reconsidered as a USE at a major unless they have an injury concern or 0 uses left.\n"
            )
        sections.append(_season_strategy_block(lean=lean))
        sections.append("")
        sections.append(_league_context_block())
        sections.append("")
        if not lean:
            sections.append(_fetch_tournament_news(_active_t_name))
            sections.append("")
            sections.append(_web_intel_alerts_block(_effective_tid or tournament_id))
            sections.append("")

    elif intent.get("is_intel"):
        # Tournament intel: curated facts + historical stats + course profile + field experience
        sections.append("## TOURNAMENT INTEL REQUEST")
        sections.append("")
        _t_name = _tournament_state(_effective_tid).get("name", "") if _effective_tid else ""
        sections.append(_tournament_intel_block(_effective_tid, _t_name))
        sections.append("")
        if _effective_tid:
            sections.append(_course_fit_reasoning_block(_effective_tid))
            sections.append("")
            sections.append(_course_profile_block(_effective_tid))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_field_overview_block(top_n=10))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10))
        sections.append("")
        sections.append(_fanduel_markets_block(_effective_tid or tournament_id, top_n=15))
        sections.append("")
        # Web news for tournament intel — player-specific + tournament-wide
        _intel_players = intent.get("players") or []
        if _intel_players:
            sections.append(_fetch_player_news(_intel_players, _active_t_name))
            sections.append("")
        sections.append(_web_intel_alerts_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_fetch_tournament_news(_active_t_name))
        sections.append("")

    elif intent["is_course_breakdown"]:
        # Full course analysis — what game wins here, best fits, worst fits
        sections.append(_STRUCT_COURSE_BREAKDOWN)
        sections.append("")
        sections.append("## COURSE BREAKDOWN REQUEST")
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=12 if lean else 20))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_course_profile_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        sections.append(_field_overview_block(top_n=10 if lean else 15))
        sections.append("")
        # Lean: course fit players already shows form-weighted rankings — full form block redundant
        if not lean:
            sections.append(_player_form_context_block(top_n=15))
            sections.append("")
        if not lean:
            sections.append(_web_intel_alerts_block(tournament_id))
            sections.append("")
            sections.append(_fetch_tournament_news(_active_t_name))
        sections.append("")

    elif intent.get("market_focus") and (intent["is_bet"] or intent["is_value"] or intent["is_daily_bet"]):
        # Market-specific bet query — player quality first, market mechanics second
        _mkt = intent["market_focus"]
        _tid_eff = _effective_tid or tournament_id
        sections.append(_STRUCT_DAILY_BET)
        sections.append("")
        sections.append(f"## {_mkt.upper().replace('_',' ')} MARKET — BEST BETS")
        sections.append("")
        # Player quality first
        sections.append(_masters_qualifiers_block(_tid_eff))
        sections.append("")
        sections.append(_field_overview_block(top_n=10 if lean else 15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10 if lean else 15))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=10 if lean else 15))
            sections.append("")
        # Expert consensus always included — key signal for market bets
        sections.append(_expert_picks_block())
        sections.append("")
        # Lean: skip tournament intel (historical course facts, 5-8K) — course fit reasoning covers it
        if not lean:
            sections.append(_tournament_intel_block(tournament_id, _active_t_name))
            sections.append("")
            sections.append(_web_intel_alerts_block(_tid_eff))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        # Market mechanics last — model logic, edge reference
        sections.append(_market_deep_block(_mkt, _tid_eff))
        sections.append("")
        sections.append(_recommended_bets_block(top_n=10))
        sections.append("")
        sections.append(_top_markets_summary_block(_tid_eff))
        sections.append("")
        sections.append(_odds_movement_block())
        sections.append("")

    elif intent["is_daily_bet"]:
        # Full betting synthesis — player quality first, then market reference data
        sections.append(_STRUCT_DAILY_BET)
        sections.append("")
        sections.append("## DAILY BET RECOMMENDATION REQUEST")
        sections.append("")
        # Player quality data FIRST — this is what drives the recommendation
        sections.append(_masters_qualifiers_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_field_overview_block(top_n=10 if lean else 15))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10 if lean else 15))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=10 if lean else 15))
            sections.append("")
        # Expert consensus always — key signal
        sections.append(_expert_picks_block())
        sections.append("")
        # Lean: skip tournament intel — course fit reasoning covers the key course facts
        if not lean:
            sections.append(_tournament_intel_block(tournament_id, _active_t_name))
            sections.append("")
            sections.append(_web_intel_alerts_block(tournament_id))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        # Market reference LAST — confirms price, not starting point
        sections.append(_recommended_bets_block(top_n=15))
        sections.append("")
        sections.append(_top_markets_summary_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_odds_movement_block())
        sections.append("")
        if tournament_id:
            _ts = _tournament_state(tournament_id)
            if _ts["phase"] not in ("pre_tournament", "complete"):
                sections.append(_STRUCT_LIVE)
                sections.append("")
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
            sections.append(_live_odds_context_block(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        # Lean: expert_picks and my_picks already added above — skip duplicate
        if not lean:
            sections.append(_expert_picks_block())
            sections.append("")
            sections.append(_my_picks_block())
            sections.append("")
        if not lean:
            sections.append(_fetch_tournament_news(_active_t_name))
            sections.append("")

    elif intent["is_bet"] or intent["is_value"]:
        # Player quality first, market reference second
        sections.append(_STRUCT_DAILY_BET)
        sections.append("")
        # Player quality data first
        sections.append(_masters_qualifiers_block(_effective_tid or tournament_id))
        sections.append("")
        # Lean: 15 players covers the relevant betting tier range without full field
        sections.append(_field_tiers_block(top_n=15 if lean else 30))
        sections.append("")
        sections.append(_field_overview_block(top_n=10 if lean else 12))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10 if lean else 12))
        sections.append("")
        if tournament_id:
            sections.append(_course_fit_reasoning_block(tournament_id))
            sections.append("")
            sections.append(_course_fit_players_block(tournament_id, top_n=10 if lean else 12))
            sections.append("")
        # Expert picks always — key signal for value identification
        sections.append(_expert_picks_block())
        sections.append("")
        # Lean: skip tournament intel — saves 5-8K, course fit reasoning covers the essentials
        if not lean:
            sections.append(_tournament_intel_block(tournament_id, _active_t_name))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        # Market reference last
        sections.append(_recommended_bets_block(top_n=15))
        sections.append("")
        sections.append(_top_markets_summary_block(_effective_tid or tournament_id))
        sections.append("")
        sections.append(_odds_movement_block())
        sections.append("")
        if tournament_id:
            _ts = _tournament_state(tournament_id)
            if _ts["phase"] not in ("pre_tournament", "complete"):
                sections.append(_STRUCT_LIVE)
                sections.append("")
                sections.append(_live_leaderboard_block(tournament_id))
                sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_weather_block(tournament_id))
            sections.append("")
        if not lean:
            sections.append(_web_intel_alerts_block(tournament_id))
            sections.append("")
            sections.append(_fetch_tournament_news(_active_t_name))
            sections.append("")

    elif intent.get("is_scoring_prop"):
        # Prop questions: birdie leaders, bogey-free, eagles, scoring efficiency
        _sp_tid = _effective_tid or tournament_id
        _sp_rnd = intent.get("recap_round_num")  # None = cumulative, N = specific round
        sections.append(_STRUCT_LIVE)
        sections.append("")
        sections.append(_scoring_prop_block(_sp_tid, query=query, round_num=_sp_rnd))
        sections.append("")
        # Add live leaderboard for positional context
        if _sp_tid:
            sections.append(_live_leaderboard_block(_sp_tid))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")

    elif intent.get("is_round_recap"):
        _rr_tid = _effective_tid or tournament_id
        _rr_num = intent.get("recap_round_num")
        sections.append(_STRUCT_LIVE)
        sections.append("")
        sections.append(_round_recap_block(_rr_tid, _rr_num))
        sections.append("")
        sections.append(_live_sg_from_hole_scores(_rr_tid))
        sections.append("")
        # Include bet P&L summary if tournament is complete
        _pt_summary = _post_tournament_summary_block(_rr_tid)
        if _pt_summary:
            sections.append(_pt_summary)
            sections.append("")
        # Include recent tournament recaps — especially useful when asking
        # "what happened at X" about a past event
        _recaps = _recent_recaps_block(6)
        if _recaps:
            sections.append(_recaps)
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")


    elif intent.get("is_picks_checkin"):
        # Live check-in for user's picks — position, score, SG proxy, cut status
        sections.append(_STRUCT_LIVE)
        sections.append("")
        _ck_tid = _effective_tid or tournament_id
        sections.append(_my_picks_live_block(_ck_tid))
        sections.append("")
        sections.append(_live_sg_from_hole_scores(_ck_tid))
        sections.append("")
        if _ck_tid:
            sections.append(_live_odds_context_block(_ck_tid))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")

    elif intent["is_live"]:
        # Leaderboard + live stats + live odds first, then field context
        sections.append(_STRUCT_LIVE)
        sections.append("")
        if tournament_id:
            sections.append(_my_picks_live_block(tournament_id))
            sections.append("")
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
            sections.append(_live_sg_from_hole_scores(tournament_id))
            sections.append("")
            sections.append(_live_course_stats_block(tournament_id))
            sections.append("")
            sections.append(_live_odds_context_block(tournament_id))
            sections.append("")
        # In lean mode: field overview and form are pre-tournament data — drop them
        # for live queries. The leaderboard above is the only authoritative source.
        if not lean:
            sections.append(_field_overview_block(top_n=15))
            sections.append("")
            sections.append(_player_form_context_block(top_n=10))
            sections.append("")
        sections.append(_my_picks_block())
        sections.append("")
        if not lean:
            sections.append(_league_context_block())
            sections.append("")
            sections.append(_fetch_tournament_news(_active_t_name))
            sections.append("")

    elif intent["is_weather"] or intent["is_course"]:
        if tournament_id:
            sections.append(_weather_block(tournament_id))
            sections.append("")
            sections.append(_course_profile_block(tournament_id))
            sections.append("")
            sections.append(_web_intel_alerts_block(tournament_id))
            sections.append("")
        sections.append(_field_overview_block(top_n=10))
        sections.append("")
        sections.append(_player_form_context_block(top_n=10))
        sections.append("")

    else:
        # General: full overview — skip stable blocks when cached_base provided
        if not cached_base:
            sections.append(_field_overview_block(top_n=10 if lean else 15))
            sections.append("")
            sections.append(_player_form_context_block(top_n=10 if lean else 15))
            sections.append("")
            if tournament_id:
                sections.append(_course_profile_block(tournament_id))
                sections.append("")
                sections.append(_weather_block(tournament_id))
                sections.append("")
            sections.append(_recommended_bets_block())
            sections.append("")
            sections.append(_expert_picks_block())
            sections.append("")
            sections.append(_my_picks_block())
            sections.append("")
            sections.append(_league_context_block())
            sections.append("")
            sections.append(_season_context_block())
            sections.append("")
            _recaps = _recent_recaps_block(6)
            if _recaps:
                sections.append(_recaps)
                sections.append("")
        # Live leaderboard and news are always dynamic (change frequently)
        if tournament_id:
            sections.append(_live_leaderboard_block(tournament_id))
            sections.append("")
        if not lean:
            sections.append(_fetch_tournament_news(_active_t_name))
            sections.append("")

    # Schedule: skip when cached_base already has it
    if not cached_base:
        sections.append(_schedule_block(current_tid=tournament_id))

    return "\n".join(s for s in sections if s is not None)


def build_base_context(tournament_id: str | None = None) -> str:
    """Build the stable session-level context layer.

    Called ONCE per conversation session and cached in st.session_state.
    Contains everything that doesn't change between questions within a session:
    system prompt, tournament state, field overview, form, course, weather,
    betting recs, expert picks, league, season context, Augusta qualifiers.

    The dynamic per-turn context (player spotlights, market deep dives, live
    leaderboard, conversation history) is built separately in build_context()
    and appended after a <!-- SPLIT --> marker.

    Cache benefit: Anthropic's prompt caching hits on this block for the
    entire conversation — saves ~70% of context rebuild work per turn.
    """
    if tournament_id is None:
        tournament_id = _detect_tournament_id()

    sections: list[str] = [_SYSTEM_PROMPT, ""]

    if tournament_id:
        _ts = _tournament_state(tournament_id)
        sections.append(f"## CURRENT TOURNAMENT: {_ts.get('name', '')} | {tournament_id}")
        sections.append("")
        sections.append(_tournament_state_block(tournament_id))
        sections.append("")

    # LIV players (Majors only)
    _liv = _liv_players_block(tournament_id)
    if _liv:
        sections.append(_liv)
        sections.append("")

    # Field overview — model predictions / sportsbook odds
    _preds_path = OUTPUTS / "latest_predictions.csv"
    _odds_missing = True
    if _preds_path.exists():
        try:
            _pdf = pd.read_csv(_preds_path, usecols=lambda c: c in [
                "odds_to_win", "dk_win_odds_american", "win_odds_american"
            ])
            for _col in ["odds_to_win", "dk_win_odds_american", "win_odds_american"]:
                if _col in _pdf.columns and _pdf[_col].notna().any():
                    _odds_missing = False
                    break
        except Exception:
            pass

    if _odds_missing and tournament_id:
        sections.append(_predictions_block(top_n=15, supplement_odds_tid=tournament_id))
    else:
        sections.append(_predictions_block(top_n=15))
    sections.append("")

    # Power rankings — clean model tier list for LLM quick reference
    sections.append(_power_rankings_block())
    sections.append("")

    # Form overview (most expensive single block — ~0.3s file I/O)
    sections.append(_player_form_context_block(top_n=20, tid=tournament_id))
    sections.append("")

    # Course + weather (stable within session)
    if tournament_id:
        sections.append(_course_profile_block(tournament_id))
        sections.append("")
        sections.append(_weather_block(tournament_id))
        sections.append("")
        _cf_fit = _dg_course_fit_block(tournament_id)
        if _cf_fit:
            sections.append(_cf_fit)
            sections.append("")

    # Betting context
    sections.append(_recommended_bets_block())
    sections.append("")
    sections.append(_top_markets_summary_block(tournament_id))
    sections.append("")

    # Expert picks and league (stable within session)
    # Note: _my_picks_block() is intentionally excluded here — it's in build_context()
    # so it always reflects the latest picks/results without being stale from cache.
    sections.append(_expert_picks_block())
    sections.append("")
    sections.append(_league_context_block())
    sections.append("")

    # Pre-generated AI lineup recommendation (stable — generated at pipeline time)
    _sr = _strategy_reasoning_block()
    if _sr:
        sections.append(_sr)
        sections.append("")

    # Season-level context + recent tournament recaps
    sections.append(_season_context_block())
    sections.append("")
    _recaps = _recent_recaps_block(6)
    if _recaps:
        sections.append(_recaps)
        sections.append("")

    # Augusta qualifier scoring (Masters only — tid ending in "014")
    if tournament_id and tournament_id.upper().endswith("014"):
        _aug_blk = _masters_qualifiers_block(tournament_id)
        if _aug_blk:
            sections.append(_aug_blk)
            sections.append("")

    # Schedule
    sections.append(_schedule_block(current_tid=tournament_id))
    sections.append("")

    return "\n".join(s for s in sections if s is not None)


# ---------------------------------------------------------------------------
# Tool execution helpers
# ---------------------------------------------------------------------------

def _execute_web_search(query: str, max_results: int = 5) -> str:
    """Run a DuckDuckGo search and return formatted results as plain text."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return "Web search unavailable."
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit="m"))
        if not results:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"Search failed: {e}"
    if not results:
        return "No results found."
    lines = [f"Search results for: {query}\n"]
    for r in results:
        title = r.get("title", "").strip()
        body  = r.get("body",  "").strip()
        if body:
            lines.append(f"**{title}**\n{body[:350].rstrip()}{'...' if len(body)>350 else ''}\n")
    return "\n".join(lines)


_WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for CURRENT golf information not in the stats data: player withdrawals, "
        "injury reports, practice-round news, course conditions, or breaking news. "
        "Do NOT use this for tournament leaderboard scores or round results — "
        "those come from the ROUND RECAP and LIVE LEADERBOARD context blocks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Specific search query, e.g. 'Masters 2026 withdrawals' or 'Rory McIlroy wrist injury April 2026'"
            }
        },
        "required": ["query"],
    },
}


def execute_tool_loop(
    messages: list[dict],
    api_key: str,
    max_rounds: int = 2,
    allow_web_search: bool = True, 
) -> tuple[list[dict], list[str]]:
    """
    Run web-search tool calls before the final streaming response.

    Returns:
        updated_messages  — messages list with tool results appended
        searches_run      — list of query strings that were executed
    """
    if not allow_web_search:
        return messages, [] 
    
    
    
    
    
    if not api_key.startswith("sk-ant-"):
        return messages, []   # Groq doesn't support tool use

    try:
        from anthropic import Anthropic
    except ImportError:
        return messages, []

    system_text = ""
    conv: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            conv.append({"role": m["role"], "content": m["content"]})

    system_blocks = _build_cached_system(system_text)
    client = Anthropic(api_key=api_key)
    searches_run: list[str] = []

    for _ in range(max_rounds):
        try:
            resp = client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=512,
                temperature=0.3,
                system=system_blocks,
                messages=conv,
                tools=[_WEB_SEARCH_TOOL],
                tool_choice={"type": "auto"},
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )
        except Exception:
            break

        if resp.stop_reason != "tool_use":
            break

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "web_search":
                query = block.input.get("query", "")
                searches_run.append(query)
                result_text = _execute_web_search(query)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        if not tool_results:
            break

        # Serialize content blocks for the next API call
        serialized = []
        for b in resp.content:
            if hasattr(b, "model_dump"):
                serialized.append(b.model_dump())
            elif hasattr(b, "dict"):
                serialized.append(b.dict())
            else:
                serialized.append(b)
        conv.append({"role": "assistant", "content": serialized})
        conv.append({"role": "user", "content": tool_results})

    updated = [{"role": "system", "content": system_text}] + conv
    return updated, searches_run


# ---------------------------------------------------------------------------
# Groq streaming
# ---------------------------------------------------------------------------

_CLAUDE_MODEL  = "claude-sonnet-4-6"
_GROQ_PRIMARY  = "llama-3.3-70b-versatile"
_GROQ_FALLBACK = "llama-3.1-8b-instant"


def stream_response(messages: list[dict], api_key: str, provider: str = "auto") -> Iterator[str]:
    """Stream a response — Claude primary (if Anthropic key), Groq fallback (free).

    provider:
      "auto"      → use Claude if api_key looks like an Anthropic key, else Groq
      "anthropic" → always Claude
      "groq"      → always Groq
    """
    is_anthropic = api_key.startswith("sk-ant-") or provider == "anthropic"
    if not is_anthropic and provider != "groq":
        # detect by prefix
        is_anthropic = api_key.startswith("sk-ant-")

    if is_anthropic:
        yield from _stream_claude(messages, api_key)
    else:
        yield from _stream_groq(messages, api_key)


def _build_cached_system(system: str) -> list[dict]:
    """Split system content into cached + uncached blocks for Anthropic prompt caching.

    Two-layer strategy:
      Block 1 (cached)   — base session context: system rules + stable weekly data.
                           Built by build_base_context(), identical across all turns
                           in a conversation → high Anthropic cache hit rate.
      Block 2 (uncached) — dynamic per-turn context: player spotlights, market deep
                           dives, live leaderboard, conversation history. Changes
                           every turn — caching would never hit.

    Split signal: the <!-- SPLIT --> marker inserted by build_context() when a
    cached_base was provided. Falls back to the old ## -header split when the
    marker is absent (backward-compatible with direct build_context() calls).
    """
    # Primary split: explicit <!-- SPLIT --> marker from two-layer build
    if "<!-- SPLIT -->" in system:
        parts = system.split("<!-- SPLIT -->", 1)
        base    = parts[0].rstrip()
        dynamic = parts[1].lstrip()
        blocks: list[dict] = []
        if base:
            blocks.append({
                "type": "text",
                "text": base,
                "cache_control": {"type": "ephemeral"},  # stable — high hit rate
            })
        if dynamic:
            blocks.append({
                "type": "text",
                "text": dynamic,
                # No cache_control: changes every turn, caching would never hit
            })
        return blocks

    # Fallback: old ## -header split (used when cached_base was not provided)
    split_idx = system.find("\n## ")
    if split_idx == -1:
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    static  = system[:split_idx].rstrip()
    dynamic = system[split_idx:].lstrip()
    blocks = []
    if static:
        blocks.append({
            "type": "text",
            "text": static,
            "cache_control": {"type": "ephemeral"},
        })
    if dynamic:
        blocks.append({
            "type": "text",
            "text": dynamic,
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def _stream_claude(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream from Claude (Anthropic). Uses prompt caching on system + context blocks."""
    try:
        from anthropic import Anthropic
    except ImportError:
        yield "*(anthropic package not installed — run: pip install anthropic)*"
        return

    system_text = ""
    conv = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            conv.append(m)

    system_blocks = _build_cached_system(system_text)

    client = Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=_CLAUDE_MODEL,
            max_tokens=3000,
            temperature=0.6,
            system=system_blocks,
            messages=conv,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"*(Claude error: {e})*"


def _stream_groq(messages: list[dict], api_key: str) -> Iterator[str]:
    """Stream from Groq with rate-limit fallback to smaller model."""
    from groq import Groq, RateLimitError

    client = Groq(api_key=api_key)

    def _stream(model: str):
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.6,
            max_tokens=3000,
        )

    try:
        for chunk in _stream(_GROQ_PRIMARY):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
    except RateLimitError:
        yield f"*(Daily limit reached for {_GROQ_PRIMARY} — switching to {_GROQ_FALLBACK})*\n\n"
        for chunk in _stream(_GROQ_FALLBACK):
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta


def extract_mentioned_players(text: str) -> list[str]:
    """Return player names (First Last) that appear in the given text."""
    path = OUTPUTS / "latest_predictions.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, usecols=["player_name"])
        text_lower = text.lower()
        found = []
        for raw in df["player_name"]:
            name = _fmt_name(str(raw))
            last = name.split()[-1].lower()
            if len(last) >= 4 and last in text_lower:
                found.append(name)
        return found[:5]  # cap at 5
    except Exception:
        return []


def generate_followup_questions(
    response_text: str,
    last_players: list[str],
    phase: str,
) -> list[str]:
    """Generate 3 contextual follow-up questions based on who was just discussed."""
    _PHASE_FALLBACK = {
        "pre_tournament":  ["Who are the biggest risks this week?", "What kind of player wins at this course?", "Build my 3 picks this week"],
        "round_1":         ["Who's still a realistic winner?", "Any surprise leaders to know about?", "Who to watch closely in Round 2?"],
        "round_2":         ["Who has the best closing record from this position?", "Who's the biggest threat to the leader?", "Who do you like to make a big move this weekend?"],
        "round_3":         ["Who has the best closing record in the field?", "What does the winning score look like from here?", "Any sleepers who could make a late charge?"],
        "round_4":         ["Who tends to buckle under pressure?", "What does the winner need to shoot?", "Who's the best putter among the current leaders?"],
        "complete":        ["What should I prioritize next week?", "Who outperformed their pre-tournament ranking?", "How did the recommended bets finish?"],
    }
    if not last_players:
        return _PHASE_FALLBACK.get(phase, _PHASE_FALLBACK["pre_tournament"])

    p = last_players[0]
    questions = [f"What are {p}'s odds and value this week?"]
    if len(last_players) >= 2:
        p2 = last_players[1]
        questions.append(f"How does {p} compare to {p2}?")
    else:
        questions.append(f"How has {p} played this course historically?")
    questions.append(_PHASE_FALLBACK.get(phase, _PHASE_FALLBACK["pre_tournament"])[0])
    return questions[:3]
