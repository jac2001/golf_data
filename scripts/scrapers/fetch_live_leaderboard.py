#!/usr/bin/env python3
"""
PGA Tour Live Leaderboard Scraper
=================================

Fetches live tournament leaderboard data from PGA Tour website.
Includes scores, positions, round-by-round data, and cut line info.

Usage:
    python fetch_live_leaderboard.py                    # Current tournament
    python fetch_live_leaderboard.py --tournament-id R2026005
    python fetch_live_leaderboard.py --list             # List active tournaments
"""

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIVE_DIR = DATA_DIR / "live"
GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}
LEADERBOARD_QUERY_FULL = """
query LeaderboardV3($id: ID!) {
  leaderboardV3(id: $id) {
    tournamentName
    currentRound
    roundStatusDisplay
    cutLine {
      cutScore
      cutCount
    }
    players {
      ... on PlayerRowV3 {
        position
        positionChange
        total
        thru
        currentRound
        currentHole
        status
        movement
        oddsToWin
        oddsSwing
        teeTime
        rounds {
          roundNumber
          score
          parRelativeScore
        }
        player {
          id
          firstName
          lastName
          displayName
          country
        }
      }
    }
  }
}
"""
LEADERBOARD_QUERY_MINIMAL = """
query LeaderboardV3($id: ID!) {
  leaderboardV3(id: $id) {
    players {
      ... on PlayerRowV3 {
        position
        total
        thru
        player {
          id
          firstName
          lastName
          displayName
          country
        }
      }
    }
  }
}
"""


def build_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = build_session()


def parse_r_id(rid: str):
    """Split RYYYYNNN into (year, event)."""
    m = re.match(r"R(\d{4})(\d{3})", rid)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _first_non_empty(*values):
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_score_to_numeric(value) -> Optional[int]:
    """Parse score strings like E, +3, -4, CUT into numeric form."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value)

    s = str(value).strip().upper()
    if not s:
        return None
    if s in {"E", "EVEN"}:
        return 0
    if s in {"CUT", "MC", "W/D", "WD", "DQ", "DNS", "MDF"}:
        return 999
    try:
        return int(s.replace("+", ""))
    except ValueError:
        m = re.search(r"[-+]?\d+", s)
        if m:
            return int(m.group(0))
    return None


def american_odds_to_probability(odds_str: str) -> Optional[float]:
    """Convert American odds string to implied probability.

    Examples:
        +185 -> 0.351 (35.1%)
        -150 -> 0.600 (60.0%)
    """
    if not odds_str:
        return None

    odds_str = str(odds_str).strip()
    if not odds_str or odds_str == "-":
        return None

    try:
        # Remove any + prefix and convert
        if odds_str.startswith("+"):
            odds = int(odds_str[1:])
            return 100 / (odds + 100)
        elif odds_str.startswith("-"):
            odds = abs(int(odds_str[1:]))
            return odds / (odds + 100)
        else:
            # Assume positive if no sign
            odds = int(odds_str)
            if odds > 0:
                return 100 / (odds + 100)
            else:
                return abs(odds) / (abs(odds) + 100)
    except (ValueError, ZeroDivisionError):
        return None


def _extract_player_info(player: Dict) -> Dict:
    row_player = player.get("player") if isinstance(player, dict) else {}
    if not isinstance(row_player, dict):
        row_player = {}

    first_name = _first_non_empty(
        row_player.get("firstName"),
        player.get("firstName"),
    )
    last_name = _first_non_empty(
        row_player.get("lastName"),
        player.get("lastName"),
    )
    full_name_fallback = " ".join([p for p in [first_name, last_name] if p]).strip()

    return {
        "player_id": _first_non_empty(row_player.get("id"), player.get("id")),
        "player_name": _first_non_empty(
            row_player.get("displayName"),
            player.get("displayName"),
            player.get("playerName"),
            full_name_fallback,
        ),
        "country": _first_non_empty(
            row_player.get("country"),
            player.get("country"),
        ) or "",
    }


def _position_sort_key(value) -> int:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 9999
    s = str(value).strip().upper()
    if not s:
        return 9999
    if s in {"CUT", "MC", "W/D", "WD", "DQ", "DNS"}:
        return 9000
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    return 9999


def _normalize_player_id(pid) -> Optional[str]:
    if pid is None:
        return None
    try:
        if isinstance(pid, float) and math.isnan(pid):
            return None
    except TypeError:
        pass
    s = str(pid).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def load_player_lookup(tournament_id: Optional[str]) -> Dict[str, Dict[str, str]]:
    """Load player name/country map from local field CSVs for fallback enrichment."""
    fields_dir = DATA_DIR / "fields"
    players_dir = DATA_DIR / "players"

    tournament_id = str(tournament_id).upper().strip() if tournament_id else ""
    candidate_paths = []
    if tournament_id:
        candidate_paths.extend([
            fields_dir / f"field_{tournament_id}.csv",
            fields_dir / f"{tournament_id.lower()}.csv",
        ])
        if fields_dir.exists():
            candidate_paths.extend(sorted(fields_dir.glob(f"*{tournament_id}*.csv")))

    # Global fallback: player database
    candidate_paths.extend([
        players_dir / "pga_players_2026.csv",
        players_dir / "pga_players_2025.csv",
    ])

    seen = set()
    lookup: Dict[str, Dict[str, str]] = {}
    for path in candidate_paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            field_df = pd.read_csv(path)
        except Exception:
            continue
        if "player_id" not in field_df.columns:
            continue

        for _, row in field_df.iterrows():
            key = _normalize_player_id(row.get("player_id"))
            if not key:
                continue
            lookup[key] = {
                "player_name": str(row.get("player_name", "")).strip(),
                "country": str(row.get("country", "")).strip(),
            }

    return lookup


def _candidate_score(candidate: Dict) -> int:
    """Score candidate leaderboard payloads to avoid picking field-only data."""
    players = candidate.get("players", [])
    if not isinstance(players, list) or not players:
        return -1

    named = 0
    with_position = 0
    with_total = 0
    for p in players:
        if not isinstance(p, dict):
            continue
        info = _extract_player_info(p)
        if info["player_name"]:
            named += 1
        if _first_non_empty(p.get("position"), p.get("pos"), p.get("currentPosition")) is not None:
            with_position += 1
        if _first_non_empty(p.get("total"), p.get("parRelativeScore"), p.get("toPar")) is not None:
            with_total += 1

    return len(players) + (named * 3) + with_position + with_total


def _iter_candidate_dicts(obj):
    """Yield dict nodes that could contain leaderboard data."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if isinstance(cur.get("players"), list):
                yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def fetch_leaderboard_from_graphql(tournament_id: str) -> Optional[Dict]:
    """Fetch leaderboard directly from PGA Tour GraphQL API."""
    queries = [LEADERBOARD_QUERY_FULL, LEADERBOARD_QUERY_MINIMAL]
    for idx, query in enumerate(queries, start=1):
        payload = {
            "operationName": "LeaderboardV3",
            "query": query,
            "variables": {"id": tournament_id},
        }
        try:
            resp = SESSION.post(
                GRAPHQL_URL,
                headers=GRAPHQL_HEADERS,
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  GraphQL attempt {idx} HTTP {resp.status_code}")
                continue
            data = resp.json()
            if data.get("errors"):
                print(f"  GraphQL attempt {idx} errors: {data['errors'][:1]}")
                continue
            leaderboard = data.get("data", {}).get("leaderboardV3")
            if (
                isinstance(leaderboard, dict)
                and isinstance(leaderboard.get("players"), list)
                and leaderboard["players"]
            ):
                leaderboard.setdefault("id", tournament_id)
                return leaderboard
        except Exception as e:
            print(f"  GraphQL attempt {idx} failed: {e}")
    return None


def fetch_leaderboard_from_html(tournament_id: str) -> Optional[Dict]:
    """Fetch leaderboard by scraping HTML and extracting __NEXT_DATA__."""
    url = "https://www.pgatour.com/leaderboard"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        print(f"  Fetching: {url}")
        resp = SESSION.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        next_data = soup.find("script", id="__NEXT_DATA__")

        if not next_data or not next_data.string:
            print("  No __NEXT_DATA__ found")
            return None

        data = json.loads(next_data.string)
        props = data.get("props", {}).get("pageProps", {})
        dehydrated = props.get("dehydratedState", {})
        queries = dehydrated.get("queries", [])

        # Find leaderboard data (query with 'players' containing 'scoringData')
        leaderboard_data = None
        tournament_info = None
        odds_data = {}

        for q in queries:
            qdata = q.get("state", {}).get("data")
            if not isinstance(qdata, dict):
                continue

            # Tournament info (has tournamentName and roundStatusDisplay)
            if "tournamentName" in qdata and "roundStatusDisplay" in qdata:
                tid = qdata.get("id", "")
                if tournament_id is None or tid == tournament_id:
                    tournament_info = qdata

            # Leaderboard players (has 'players' with nested 'player' and 'scoringData')
            if "players" in qdata and isinstance(qdata["players"], list) and qdata["players"]:
                first_player = qdata["players"][0]
                if isinstance(first_player, dict) and "scoringData" in first_player:
                    tid = qdata.get("tournamentId", "")
                    if tournament_id is None or tid == tournament_id:
                        leaderboard_data = qdata

            # Odds data (has 'oddsEnabled' and 'players' with 'odds')
            if "oddsEnabled" in qdata and qdata.get("players"):
                for p in qdata["players"]:
                    if isinstance(p, dict) and "playerId" in p and "odds" in p:
                        odds_data[str(p["playerId"])] = p.get("odds", "")

        if not leaderboard_data:
            print("  No leaderboard data found in page")
            return None

        # Transform to standard format
        players = []
        for p in leaderboard_data.get("players", []):
            if not isinstance(p, dict):
                continue

            player_info = p.get("player", {})
            scoring = p.get("scoringData", {})
            player_id = str(player_info.get("id", ""))

            # Get odds for this player
            player_odds = odds_data.get(player_id, "")

            # Parse rounds
            rounds_raw = scoring.get("rounds", ["-", "-", "-", "-"])
            rounds = []
            for i, r in enumerate(rounds_raw[:4], start=1):
                score = None
                if r and r != "-":
                    try:
                        score = int(r)
                    except (ValueError, TypeError):
                        score = None
                rounds.append({
                    "roundNumber": i,
                    "score": score,
                })

            players.append({
                "id": player_id,
                "player": {
                    "id": player_id,
                    "firstName": player_info.get("firstName", ""),
                    "lastName": player_info.get("lastName", ""),
                    "displayName": player_info.get("displayName", ""),
                    "country": player_info.get("country", ""),
                },
                "position": scoring.get("position", ""),
                "positionChange": scoring.get("movementAmount", 0),
                "total": scoring.get("total", "E"),
                "thru": scoring.get("thru", ""),
                "currentRound": scoring.get("currentRound", 1),
                "currentHole": scoring.get("currentHole"),
                "status": scoring.get("playerState", "ACTIVE"),
                "movement": scoring.get("movementDirection", ""),
                "oddsToWin": player_odds,
                "rounds": rounds,
                "teeTime": "",
            })

        result = {
            "id": leaderboard_data.get("tournamentId", tournament_id),
            "tournamentName": tournament_info.get("tournamentName", "") if tournament_info else "",
            "currentRound": tournament_info.get("currentRound", 1) if tournament_info else 1,
            "roundStatusDisplay": tournament_info.get("roundStatusDisplay", "") if tournament_info else "",
            "players": players,
        }

        print(f"  Found {len(players)} players")
        return result

    except Exception as e:
        print(f"  Error fetching leaderboard: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_active_tournaments() -> List[Dict]:
    """Fetch list of currently active tournaments from schedule."""
    schedule_candidates = [
        DATA_DIR / "schedule" / "pga_schedule.csv",
        DATA_DIR / "raw" / "schedule_2026.csv",
        DATA_DIR / "raw" / "pgatour_schedule_2026.csv",
        DATA_DIR / "raw" / "pgatour_schedule_2025.csv",
    ]

    schedule_path = next((p for p in schedule_candidates if p.exists()), None)
    if schedule_path is None:
        return []

    try:
        df = pd.read_csv(schedule_path)
    except Exception:
        return []

    if df.empty or "start_date" not in df.columns:
        return []

    df = df.copy()
    if "tournament_id" in df.columns and "id" not in df.columns:
        df["id"] = df["tournament_id"]
    if "tournament_name" in df.columns and "tournamentName" not in df.columns:
        df["tournamentName"] = df["tournament_name"]
    if "location" in df.columns and "courseName" not in df.columns:
        df["courseName"] = df["location"]

    today = datetime.now().strftime("%Y-%m-%d")
    current = df[
        (df["start_date"] <= today) &
        (df.get("end_date", df["start_date"]) >= today)
    ]
    if not current.empty:
        return current.to_dict("records")

    upcoming = df[df["start_date"] > today].head(3)
    return upcoming.to_dict("records")


def fetch_leaderboard(tournament_id: str) -> Optional[Dict]:
    """Fetch leaderboard for a specific tournament."""
    leaderboard = fetch_leaderboard_from_graphql(tournament_id)
    if leaderboard:
        return leaderboard
    return fetch_leaderboard_from_html(tournament_id)


def parse_leaderboard_to_df(leaderboard: Dict, tournament_id: Optional[str] = None) -> pd.DataFrame:
    """Convert leaderboard data to DataFrame."""
    if not leaderboard or "players" not in leaderboard:
        return pd.DataFrame()

    rows = []
    effective_tournament_id = tournament_id or leaderboard.get("id")
    player_lookup = load_player_lookup(effective_tournament_id)
    cut_line = leaderboard.get("cutLine") or {}
    cut_score = _parse_score_to_numeric(cut_line.get("cutScore")) if cut_line else None
    current_round = _safe_int(leaderboard.get("currentRound"), default=1)

    for player in leaderboard["players"]:
        if not isinstance(player, dict):
            continue

        player_info = _extract_player_info(player)
        player_key = _normalize_player_id(player_info["player_id"])
        lookup_row = player_lookup.get(player_key) if player_key else None
        if lookup_row:
            if not player_info["player_name"]:
                player_info["player_name"] = lookup_row.get("player_name", "")
            if not player_info["country"]:
                player_info["country"] = lookup_row.get("country", "")
        if not player_info["player_name"] and player_key:
            player_info["player_name"] = f"Player {player_key}"

        # Parse rounds
        rounds = player.get("rounds") or []
        round_scores = {}
        total_strokes = 0
        for idx, r in enumerate(rounds, start=1):
            if not isinstance(r, dict):
                continue
            round_number = _safe_int(r.get("roundNumber"), default=idx)
            score_value = _first_non_empty(r.get("score"), r.get("strokes"))
            round_scores[f"R{round_number}"] = score_value
            try:
                if score_value is not None and str(score_value).strip() != "":
                    total_strokes += int(float(score_value))
            except (TypeError, ValueError):
                continue

        total_display = _first_non_empty(
            player.get("total"),
            player.get("parRelativeScore"),
            player.get("toPar"),
            "E",
        )
        total_numeric = _parse_score_to_numeric(total_display)
        if total_numeric is None:
            total_numeric = 999

        status = str(_first_non_empty(player.get("status"), "active")).lower()
        made_cut = status not in {"cut", "mc", "wd", "w/d", "dq", "withdrawn"}
        if cut_score is not None and current_round >= 2 and total_numeric < 900:
            made_cut = total_numeric <= cut_score

        # Parse odds
        odds_to_win = _first_non_empty(player.get("oddsToWin"), "")
        odds_swing = _first_non_empty(player.get("oddsSwing"), "")

        rows.append({
            "position": _first_non_empty(player.get("position"), player.get("pos"), player.get("currentPosition"), ""),
            "position_change": _safe_int(player.get("positionChange"), default=0),
            "player_id": player_info["player_id"],
            "player_name": player_info["player_name"] or "",
            "country": player_info["country"],
            "total": total_display,
            "total_numeric": total_numeric,
            "thru": _first_non_empty(player.get("thru"), ""),
            "current_round": _safe_int(player.get("currentRound"), default=current_round),
            "current_hole": player.get("currentHole"),
            "R1": round_scores.get("R1"),
            "R2": round_scores.get("R2"),
            "R3": round_scores.get("R3"),
            "R4": round_scores.get("R4"),
            "total_strokes": total_strokes,
            "made_cut": made_cut,
            "status": status or "active",
            "movement": _first_non_empty(player.get("movement"), ""),
            "odds_to_win": odds_to_win,
            "odds_swing": odds_swing,
            "tee_time": _first_non_empty(player.get("teeTime"), ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Drop rows with no player identity
    df = df[~(df["player_id"].isna() & (df["player_name"].fillna("").str.strip() == ""))]

    if df.empty:
        return df

    # Sort by official position when present, then score, then name.
    df["pos_sort"] = df["position"].apply(_position_sort_key)
    df = df.sort_values(["pos_sort", "total_numeric", "player_name"], kind="stable").drop(columns=["pos_sort"])
    df = df.reset_index(drop=True)

    return df


def calculate_cut_projection(df: pd.DataFrame, cut_count: int = 65) -> Dict:
    """Project the cut line based on current scores."""
    if df.empty or "total_numeric" not in df.columns:
        return {}

    active = df.copy()
    if "status" in active.columns:
        status_lower = active["status"].astype(str).str.lower()
        active = active[~status_lower.isin({"wd", "w/d", "withdrawn", "dq", "dns"})]
    if active.empty:
        return {}

    # If tournament has not started yet (no positions/thru), skip cut projection.
    has_positions = active["position"].notna().any() if "position" in active.columns else False
    has_thru = active["thru"].fillna("").astype(str).str.strip().ne("").any() if "thru" in active.columns else False
    if not has_positions and not has_thru:
        return {}

    active = active[active["total_numeric"].notna()].copy()
    if active.empty:
        return {}
    active["total_numeric"] = pd.to_numeric(active["total_numeric"], errors="coerce")
    active = active[active["total_numeric"].notna()]
    if active.empty:
        return {}

    active = active.sort_values("total_numeric")

    if len(active) >= cut_count:
        cut_player = active.iloc[cut_count - 1]
        projected_cut = int(cut_player["total_numeric"])
        cut_position = _first_non_empty(cut_player.get("position"), cut_count)
    else:
        projected_cut = int(active["total_numeric"].max())
        cut_position = len(active)

    bubble_players = active[
        (active["total_numeric"] >= projected_cut - 1) &
        (active["total_numeric"] <= projected_cut + 1)
    ]

    return {
        "projected_cut_score": int(projected_cut),
        "projected_cut_position": cut_position,
        "bubble_count": int(len(bubble_players)),
        "safely_in": int(len(active[active["total_numeric"] < projected_cut - 1])),
        "safely_out": int(len(active[active["total_numeric"] > projected_cut + 1])),
    }


def _json_safe(value: Any):
    """Convert numpy/pandas scalars and NaN values to JSON-safe Python primitives."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()

    # numpy/pandas scalar support
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    if value is pd.NA:
        return None
    return value


def write_json_atomic(path: Path, payload: Dict):
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(_json_safe(payload), f, indent=2)
    tmp_path.replace(path)


def main():
    parser = argparse.ArgumentParser(description="Fetch live PGA Tour leaderboard")
    parser.add_argument("--tournament-id", help="Tournament ID (e.g., R2026005)")
    parser.add_argument("--list", action="store_true", help="List active tournaments")
    parser.add_argument("--output", help="Output CSV path")
    args = parser.parse_args()

    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching from PGA Tour...")

    # List mode
    if args.list:
        tournaments = fetch_active_tournaments()
        if not tournaments:
            print("No active tournaments found")
            return

        print(f"\nFound {len(tournaments)} active tournaments:")
        for t in tournaments:
            course_name = _first_non_empty(t.get("courseName"), t.get("location"), "TBD")
            print(f"  {t.get('tournamentName') or t.get('tournament_name') or 'Tournament'}")
            print(f"    ID: {t.get('id') or t.get('tournament_id')}")
            print(f"    Course: {course_name}")
            if t.get("status"):
                print(f"    Status: {t.get('status')}")
        return

    # Get tournament ID
    tournament_id = args.tournament_id
    if not tournament_id:
        # Try to find current active tournament
        tournaments = fetch_active_tournaments()
        if tournaments:
            tournament_id = tournaments[0].get("id") or tournaments[0].get("tournament_id")
            print(f"  Auto-selected: {tournaments[0].get('tournamentName') or tournaments[0].get('tournament_name')}")
        else:
            print("No active tournaments. Use --tournament-id to specify.")
            return

    # Fetch leaderboard
    print(f"  Fetching leaderboard for: {tournament_id}")
    leaderboard = fetch_leaderboard(tournament_id)

    if not leaderboard:
        print("  Failed to fetch leaderboard")
        return

    tournament_name = leaderboard.get("tournamentName", tournament_id)
    round_status = leaderboard.get("roundStatusDisplay", "")
    current_round = _safe_int(leaderboard.get("currentRound"), default=1)
    cut_line = leaderboard.get("cutLine", {}) or {}

    print(f"\n{tournament_name}")
    print(f"Round {current_round} - {round_status}")

    if cut_line:
        print(f"Cut Line: {cut_line.get('cutScore', 'TBD')} ({cut_line.get('cutCount', 65)} players)")

    # Parse to DataFrame
    df = parse_leaderboard_to_df(leaderboard, tournament_id=tournament_id)

    if df.empty:
        print("  No leaderboard data")
        return

    # Calculate cut projection
    cut_projection = calculate_cut_projection(df)
    if cut_projection:
        print(f"\nCut Projection:")
        print(f"  Projected: {cut_projection.get('projected_cut_score', 'E')}")
        print(f"  Bubble players: {cut_projection.get('bubble_count', 0)}")
        print(f"  Safely in: {cut_projection.get('safely_in', 0)}")

    # Display top 20
    print(f"\n{'Pos':<6} {'Player':<25} {'Total':<8} {'Thru':<6} {'R1':<5} {'R2':<5} {'R3':<5} {'R4':<5} {'Odds':<10}")
    print("-" * 85)

    for _, row in df.head(20).iterrows():
        pos = str(row['position'])
        name = row['player_name'][:24]
        total = str(row['total'])
        thru = str(row['thru']) if row['thru'] else ""
        r1 = str(row['R1']) if pd.notna(row['R1']) else "-"
        r2 = str(row['R2']) if pd.notna(row['R2']) else "-"
        r3 = str(row['R3']) if pd.notna(row['R3']) else "-"
        r4 = str(row['R4']) if pd.notna(row['R4']) else "-"
        odds = str(row['odds_to_win']) if row['odds_to_win'] else "-"

        print(f"{pos:<6} {name:<25} {total:<8} {thru:<6} {r1:<5} {r2:<5} {r3:<5} {r4:<5} {odds:<10}")

    # Save
    if args.output:
        out_path = Path(args.output)
    else:
        slug = tournament_id.lower().replace("-", "_")
        out_path = LIVE_DIR / f"leaderboard_{slug}.csv"

    df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")

    # Also save metadata
    meta = {
        "tournament_id": tournament_id,
        "tournament_name": tournament_name,
        "current_round": current_round,
        "round_status": round_status,
        "cut_line": cut_line,
        "cut_projection": cut_projection,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(df),
    }
    meta_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}_meta.json"
    write_json_atomic(meta_path, meta)
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    main()
