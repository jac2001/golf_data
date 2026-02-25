#!/usr/bin/env python3
"""
PGA Tour Betting Profile Scraper
=================================

Fetches detailed betting profile data for players in a tournament field.
This data enhances the golf assistant's reasoning with:
- Current betting odds and movement
- Recent form and results
- Course history insights
- Player bio and stats

Usage:
    # Fetch profiles for current tournament
    python scripts/scrapers/fetch_betting_profiles.py --tournament-id R2026016

    # Fetch for specific field file
    python scripts/scrapers/fetch_betting_profiles.py --tournament-id R2026016 --field data/fields/american_express_2026_clean.csv
"""

import argparse
import requests
import pandas as pd
import json
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import time
import re
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.tournament_context import (
    resolve_tournament_context as resolve_shared_tournament_context,
    tournament_name_match as shared_tournament_name_match,
)
# ============================================================================
# Configuration
# ============================================================================

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "betting_profiles"
ODDS_CACHE_DIR = PROJECT_ROOT / "data" / "odds"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Some tournaments use a different article slug than schedule power_slug.
BETTING_SLUG_OVERRIDES = {
    "cognizant-classic": "cognizant-classic-in-the-palm-beaches",
}

# ============================================================================
# GraphQL Queries
# ============================================================================

# Tournament odds with player details
TOURNAMENT_ODDS_QUERY = """
query TournamentOddsToWin($tournamentId: ID!) {
  tournamentOddsToWin(tournamentId: $tournamentId) {
    tournamentId
    tournamentName
    players {
      playerId
      oddsToWin
      oddsSwing
      oddsSort
    }
  }
}
"""

# Player profile query
# NOTE: PGA Tour frequently changes the schema; keep this minimal to avoid validation errors.
PLAYER_PROFILE_QUERY = """
query PlayerProfileOverview($playerId: ID!) {
  playerProfileOverview(playerId: $playerId) {
    id
  }
}
"""

# Player recent results - NOTE: playerResults query no longer exists in API
# We now derive recent form from course history data instead
# Keeping this as a placeholder for documentation
PLAYER_RESULTS_QUERY = None  # Deprecated - API removed this query

# Player career stats
PLAYER_STATS_QUERY = """
query PlayerStats($playerId: ID!, $tourCode: TourCode!, $year: Int) {
  playerStats(playerId: $playerId, tourCode: $tourCode, year: $year) {
    tourCode
    year
    events
    wins
    topTens
    topTwentyFives
    cuts
    cupPoints
    cupRank
  }
}
"""

# Leaderboard query (to get player IDs)
LEADERBOARD_QUERY = """
query LeaderboardV3($id: ID!) {
  leaderboardV3(id: $id) {
    players {
      ... on PlayerRowV3 {
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

# Player strokes gained and detailed stats
PLAYER_PROFILE_STATS_QUERY = """
query PlayerProfileStats($playerId: ID!) {
  playerProfileStats(playerId: $playerId) {
    stats {
      statId
      title
      value
      rank
      fieldAverage
      category
    }
  }
}
"""

# Player course history - results at specific courses (hardcoded PGA Tour)
PLAYER_COURSE_HISTORY_QUERY = """
query PlayerCourseResults($playerId: String!) {
  playerProfileCourseResults(playerId: $playerId, tourCode: R) {
    tourCode
    courses {
      courseName
      courseId
      tournaments {
        tournamentName
        year
        position
        total
        toPar
        winnings
      }
    }
  }
}
"""


# ============================================================================
# API Functions
# ============================================================================

def fetch_graphql(query: str, variables: dict) -> dict:
    """Execute a GraphQL query."""
    payload = {
        "query": query,
        "variables": variables,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"    HTTP {resp.status_code}")
            return {}
    except requests.RequestException as e:
        print(f"    Request error: {e}")
        return {}


def fetch_tournament_field(tournament_id: str) -> List[Dict]:
    """Fetch the tournament field with player IDs."""
    print(f"  Fetching tournament field...")

    data = fetch_graphql(LEADERBOARD_QUERY, {"id": tournament_id})

    # Handle missing data gracefully
    if not data or not data.get("data"):
        print(f"    No leaderboard data found")
        return []

    leaderboard = data.get("data", {}).get("leaderboardV3")
    if not leaderboard:
        print(f"    No leaderboard found for tournament")
        return []

    players = leaderboard.get("players", [])
    if not players:
        print(f"    No players in leaderboard")
        return []

    field = []
    for p in players:
        if not p:  # Skip empty entries
            continue
        player_info = p.get("player", {})
        if not player_info:
            continue
        if player_info.get("id"):
            field.append({
                "player_id": int(player_info["id"]),
                "player_name": player_info.get("displayName", ""),
                "country": player_info.get("country", ""),
                "position": p.get("position", ""),
                "total": p.get("total", ""),
            })

    print(f"    Found {len(field)} players in field")
    return field


def fetch_tournament_odds(tournament_id: str) -> Dict[int, Dict]:
    """Fetch betting odds for tournament."""
    print(f"  Fetching betting odds...")

    data = fetch_graphql(TOURNAMENT_ODDS_QUERY, {"tournamentId": tournament_id})
    odds_data = data.get("data", {}).get("tournamentOddsToWin", {})

    tournament_name = odds_data.get("tournamentName", "")
    players = odds_data.get("players", [])

    odds_map = {}
    for p in players:
        player_id = int(p.get("playerId", 0))
        odds_str = p.get("oddsToWin", "")

        # Parse odds to probability
        odds_numeric = None
        implied_prob = None
        if odds_str:
            try:
                odds_numeric = int(odds_str.replace("+", ""))
                if odds_numeric >= 0:
                    implied_prob = 100 / (odds_numeric + 100)
                else:
                    implied_prob = abs(odds_numeric) / (abs(odds_numeric) + 100)
            except ValueError:
                pass

        odds_map[player_id] = {
            "odds_to_win": odds_str,
            "odds_numeric": odds_numeric,
            "implied_prob": implied_prob,
            "odds_swing": p.get("oddsSwing", ""),
            "odds_rank": p.get("oddsSort", 999),
            "player_name": p.get("playerName", ""),
        }

    print(f"    Found odds for {len(odds_map)} players")
    return odds_map, tournament_name


def load_cached_odds(odds_csv: Path) -> Tuple[Dict[int, Dict], str]:
    """
    Load odds from a previously scraped CSV as a fallback when the GraphQL
    endpoint is unreachable (e.g., offline, DNS blocked, or rate limited).
    """
    if not odds_csv.exists():
        print(f"    No cached odds file at {odds_csv}")
        return {}, ""

    print(f"  Loading cached odds from {odds_csv}...")
    try:
        df = pd.read_csv(odds_csv)
    except Exception as e:
        print(f"    Could not read cached odds: {e}")
        return {}, ""

    odds_map = {}
    for _, row in df.iterrows():
        player_id = int(row["player_id"])
        odds_map[player_id] = {
            "odds_to_win": row.get("odds_to_win", ""),
            "odds_numeric": row.get("odds_numeric"),
            "implied_prob": row.get("implied_prob"),
            "odds_swing": row.get("odds_swing", ""),
            "odds_rank": row.get("odds_rank", 999),
            "player_name": row.get("player_name", ""),
        }

    tournament_name = ""
    if "tournament_name" in df.columns and not df["tournament_name"].empty:
        tournament_name = df["tournament_name"].iloc[0]

    print(f"    Loaded odds for {len(odds_map)} players from cache")
    return odds_map, tournament_name


def fetch_player_profile(player_id: int) -> Dict:
    """Fetch detailed player profile."""
    data = fetch_graphql(PLAYER_PROFILE_QUERY, {"playerId": str(player_id)})
    # Soft-fail if the schema changed and errors are returned
    if data.get("errors"):
        return {}

    profile = data.get("data", {}).get("playerProfileOverview", {})
    print(f"    Fetched profile for player ID {player_id}")
    print(f"      Profile data keys: {list(profile.keys())}")
    if not profile:
        return {}

    return {
        # Minimal placeholder; schema trimmed to avoid validation errors
        "world_rank": None,
        "previous_rank": None,
        "fedex_rank": None,
        "fedex_points": None,
        "country": None,
        "turned_pro": None,
        "career_earnings": None,
    }


def fetch_player_results(player_id: int, limit: int = 5) -> List[Dict]:
    """
    Fetch player's recent results.

    NOTE: The original playerResults API query was removed by PGA Tour.
    We now extract recent results from course history data instead.
    This function is called after fetch_player_course_history.
    """
    # This is now a no-op - results are extracted from course history
    # See extract_recent_form_from_course_history() instead
    return []


def extract_recent_form_from_course_history(course_history: Dict, limit: int = 5) -> List[Dict]:
    """
    Extract recent tournament results from course history data.

    Args:
        course_history: Dict with 'course_history' key containing list of courses
        limit: Max number of results to return

    Returns:
        List of recent results sorted by year (most recent first)
    """
    if not course_history or not course_history.get("course_history"):
        return []

    all_results = []
    for course in course_history.get("course_history", []):
        course_name = course.get("course_name", "")
        for tourn in course.get("tournaments", []):
            all_results.append({
                "tournament": tourn.get("tournament", ""),
                "course": course_name,
                "finish": tourn.get("position", ""),
                "year": tourn.get("year", 0),
                "to_par": tourn.get("to_par", ""),
                "winnings": tourn.get("winnings", ""),
            })

    # Sort by year descending (most recent first)
    all_results.sort(key=lambda x: x.get("year", 0), reverse=True)

    return all_results[:limit]


def fetch_player_stats(player_id: int, year: int = None) -> Dict:
    """Fetch player's season stats."""
    if year is None:
        year = datetime.now().year

    data = fetch_graphql(PLAYER_STATS_QUERY, {
        "playerId": str(player_id),
        "tourCode": "R",
        "year": year
    })

    stats = data.get("data", {}).get("playerStats", {})

    if not stats:
        return {}

    return {
        "events": stats.get("events", 0),
        "wins": stats.get("wins", 0),
        "top_10s": stats.get("topTens", 0),
        "top_25s": stats.get("topTwentyFives", 0),
        "cuts_made": stats.get("cuts", 0),
    }


def fetch_player_sg_stats(player_id: int) -> Dict:
    """Fetch player's strokes gained breakdown and detailed stats."""
    data = fetch_graphql(PLAYER_PROFILE_STATS_QUERY, {"playerId": str(player_id)})

    if data.get("errors"):
        return {}

    # playerProfileStats returns an array of category objects
    profile_stats = data.get("data", {}).get("playerProfileStats", [])

    if not profile_stats:
        return {}

    # Flatten all stats from all categories
    all_stats = []
    for category in profile_stats:
        stats = category.get("stats", [])
        all_stats.extend(stats)

    if not all_stats:
        return {}

    # Map common stat titles to our keys (flexible matching)
    sg_stats = {}
    stat_mapping = {
        "sg: off the tee": "sg_ott",
        "sg: off-the-tee": "sg_ott",
        "sg: approach to green": "sg_app",
        "sg: approach the green": "sg_app",
        "sg: around the green": "sg_arg",
        "sg: around-the-green": "sg_arg",
        "sg: putting": "sg_putt",
        "sg: tee to green": "sg_t2g",
        "sg: tee-to-green": "sg_t2g",
        "sg: total": "sg_total",
        "driving distance": "driving_distance",
        "driving accuracy percentage": "driving_accuracy",
        "greens in regulation percentage": "gir_pct",
        "greens in regulation pct": "gir_pct",
        "gir percentage": "gir_pct",
        "putting average": "putting_avg",
        "scrambling": "scrambling_pct",
        "scoring average": "scoring_avg",
    }

    for stat in all_stats:
        title = stat.get("title", "").lower().strip()
        if title in stat_mapping:
            key = stat_mapping[title]
            sg_stats[key] = stat.get("value")
            sg_stats[f"{key}_rank"] = stat.get("rank")
            sg_stats[f"{key}_field_avg"] = stat.get("fieldAverage")

    return sg_stats


def fetch_player_course_history(player_id: int, course_name: str = None) -> Dict:
    """Fetch player's history at specific courses."""
    data = fetch_graphql(PLAYER_COURSE_HISTORY_QUERY, {
        "playerId": str(player_id)
    })

    if not data:
        return {}

    if data.get("errors"):
        return {}

    courses_data = data.get("data", {}).get("playerProfileCourseResults", {}).get("courses", [])

    if not courses_data:
        return {}

    # Build course history summary
    all_courses = []
    for course in courses_data:
        course_info = {
            "course_name": course.get("courseName", ""),
            "course_id": course.get("courseId", ""),
            "tournaments": []
        }

        for tourn in course.get("tournaments", []):
            course_info["tournaments"].append({
                "tournament": tourn.get("tournamentName", ""),
                "year": tourn.get("year"),
                "position": tourn.get("position", ""),
                "total": tourn.get("total", ""),
                "to_par": tourn.get("toPar", ""),
                "winnings": tourn.get("winnings", ""),
            })

        all_courses.append(course_info)

    # If a specific course is requested, filter to that
    if course_name:
        course_name_lower = course_name.lower()
        matching = [c for c in all_courses if course_name_lower in c["course_name"].lower()]
        if matching:
            return {
                "course_history": matching,
                "course_history_summary": _summarize_course_history(matching)
            }

    # Return all course history (limited to most recent/relevant)
    return {
        "course_history": all_courses[:10],  # Limit to 10 courses
        "course_history_summary": _summarize_course_history(all_courses[:5])
    }


def _summarize_course_history(courses: List[Dict]) -> str:
    """Summarize course history into a readable string."""
    if not courses:
        return "No course history"

    summaries = []
    for course in courses[:3]:  # Top 3 courses
        course_name = course.get("course_name", "")[:30]
        tournaments = course.get("tournaments", [])
        if tournaments:
            recent = tournaments[0]  # Most recent
            pos = recent.get("position", "")
            year = recent.get("year", "")
            summaries.append(f"{pos} at {course_name} ({year})")

    return "; ".join(summaries) if summaries else "No course history"


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _slugify_text(value: str) -> str:
    return _normalize_text(value).replace(" ", "-")


def _name_tokens(value: str) -> set:
    stop = {
        "the", "and", "of", "at", "in", "to", "open", "championship",
        "classic", "invitational", "pro", "am", "presented", "by",
        "palm", "beaches", "beach",
    }
    return {t for t in _normalize_text(value).split() if t and t not in stop}


def _tournament_name_match(actual: str, expected: str) -> bool:
    return shared_tournament_name_match(actual, expected)


def _slugify_player_name(name: str) -> str:
    # Convert "Last, First" to "first-last" and strip accents.
    raw = str(name or "").strip()
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            raw = f"{parts[1]} {parts[0]}"
    return _slugify_text(raw)


def _resolve_tournament_context(tournament_id: str) -> Dict[str, str]:
    """
    Resolve schedule metadata for a tournament ID.
    Returns keys: tournament_name, power_slug, start_date, year.
    """
    tid = str(tournament_id or "").strip().upper()
    row = resolve_shared_tournament_context(tournament_id=tid)
    return {
        "tournament_name": str(row.get("tournament_name", "")).strip(),
        "power_slug": str(row.get("power_slug", "")).strip(),
        "start_date": str(row.get("start_date", "")).strip(),
        "year": str(row.get("year", "")).strip(),
    }


def _extract_betting_profile_links(html: str, year: str) -> List[str]:
    """
    Parse betting-profile article links from listing HTML.
    """
    links = re.findall(r'href="([^"]+)"', html)
    out = []
    year_pat = f"/article/news/betting-profile/{year}/"
    for href in links:
        h = str(href or "").strip()
        if not h:
            continue
        if h.startswith("/"):
            h = f"https://www.pgatour.com{h}"
        if not h.startswith("https://www.pgatour.com/"):
            continue
        if year_pat not in h:
            continue
        out.append(h.split("?")[0].split("#")[0])
    # ordered unique
    return list(dict.fromkeys(out))


def _discover_betting_profile_slug(
    year: str,
    tournament_name: str,
    power_slug: str,
) -> Tuple[str, str]:
    """
    Discover a tournament betting-profile slug from the PGA listing page.

    Returns:
      (slug, sample_url)
    """
    listing_url = "https://www.pgatour.com/news/betting-profile"
    try:
        resp = requests.get(listing_url, headers=HTML_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return "", ""

    links = _extract_betting_profile_links(resp.text, year)
    if not links:
        return "", ""

    pslug = str(power_slug or "").strip().lower().replace("_", "-")
    expected = str(tournament_name or "").strip()
    scored: List[Tuple[int, str, str]] = []
    for url in links:
        m = re.search(r"/article/news/betting-profile/\d{4}/([^/]+)/", url)
        if not m:
            continue
        slug = m.group(1).strip().lower()
        score = 0
        if pslug and pslug in slug:
            score += 4
        if expected and _tournament_name_match(slug.replace("-", " "), expected):
            score += 3
        scored.append((score, slug, url))

    if not scored:
        return "", ""

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[0]
    if top[0] == 0:
        # Keep deterministic fallback to first link if no confident match.
        return scored[0][1], scored[0][2]
    return top[1], top[2]


def _parse_betting_article_from_next_data(html: str) -> Dict[str, str]:
    """
    Parse PGA Tour betting-profile article fields from __NEXT_DATA__ JSON.
    Returns empty dict if the article payload is missing.
    """
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except Exception:
        return {}

    queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    article = None
    for q in queries:
        qkey = q.get("queryKey", [])
        if qkey and qkey[0] == "newsArticleDetails":
            article = q.get("state", {}).get("data", {})
            break
    if not article or not article.get("nodes"):
        return {}

    paragraphs: List[str] = []
    bullets: List[str] = []
    headings: List[str] = []
    body_parts: List[str] = []

    for node in article.get("nodes", []):
        if not isinstance(node, dict):
            continue
        tname = str(node.get("__typename", ""))
        if tname in {"NewsArticleParagraph", "NewsArticleOddsParagraph"}:
            segs = node.get("segments", [])
            text = " ".join(s.get("value", "") for s in segs if isinstance(s, dict) and s.get("value"))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                paragraphs.append(text)
                body_parts.append(text)
        elif tname in {"NewsArticleHeader", "NewsArticleHeading"}:
            text = node.get("text", "") or node.get("value", "")
            if not text:
                for hs in node.get("headerSegments", []):
                    for seg in hs.get("segments", []):
                        if isinstance(seg, dict) and seg.get("value"):
                            text = seg.get("value")
                            break
                    if text:
                        break
            text = re.sub(r"\s+", " ", str(text)).strip()
            if text:
                headings.append(text)
                body_parts.append(f"## {text}")
        elif tname in {"NewsArticleList", "UnorderedListNode", "OrderedListNode"}:
            for item in node.get("items", []):
                txt = ""
                if isinstance(item, dict):
                    segs = item.get("segments", [])
                    txt = " ".join(s.get("value", "") for s in segs if isinstance(s, dict) and s.get("value"))
                elif isinstance(item, str):
                    txt = item
                txt = re.sub(r"\s+", " ", str(txt)).strip()
                if txt:
                    bullets.append(txt)
                    body_parts.append(f"- {txt}")

    published_at = ""
    date_ms = article.get("datePublished")
    if date_ms:
        try:
            published_at = datetime.fromtimestamp(int(date_ms) / 1000).isoformat()
        except Exception:
            pass

    return {
        "title": str(article.get("headline", "")).strip(),
        "summary": " ".join(paragraphs[:3]).strip(),
        "body": "\n".join(paragraphs).strip(),
        "body_formatted": "\n\n".join(body_parts).strip(),
        "bullets": " | ".join(bullets).strip(),
        "headings": " | ".join(headings).strip(),
        "published_at": published_at,
        "article_tournament_name": str(article.get("tournamentName", "")).strip(),
    }


def _fetch_article(url: str) -> Dict[str, str]:
    try:
        resp = requests.get(url, headers=HTML_HEADERS, timeout=20)
        if resp.status_code != 200 or not resp.text:
            return {}
    except Exception:
        return {}
    article = _parse_betting_article_from_next_data(resp.text)
    if not article:
        return {}
    article["article_url"] = url
    return article


def _build_article_url_candidates(
    player_name: str,
    year: str,
    tournament_slug: str,
    sample_url: str = "",
) -> List[str]:
    base = f"https://www.pgatour.com/article/news/betting-profile/{year}/{tournament_slug}"
    name_slug = _slugify_player_name(player_name)
    if not name_slug:
        return []

    candidates = [
        f"{base}/{name_slug}-pga-tour-betting-stats-{tournament_slug}-{year}",
        f"{base}/{name_slug}-pga-tour-betting-stats-{tournament_slug}",
        f"{base}/{name_slug}",
    ]

    if sample_url and f"/{tournament_slug}/" in sample_url:
        tail = sample_url.split(f"/{tournament_slug}/", 1)[1]
        if "-pga-tour-betting-stats-" in tail:
            rest = tail.split("-pga-tour-betting-stats-", 1)[1]
            if rest:
                candidates.insert(0, f"{base}/{name_slug}-pga-tour-betting-stats-{rest}")

    # ordered unique
    seen = set()
    return [u for u in candidates if not (u in seen or seen.add(u))]


def _resolve_betting_profile_article_context(
    tournament_id: str,
    tournament_name: str,
) -> Dict[str, str]:
    context = _resolve_tournament_context(tournament_id)
    year = context.get("year", "") or str(datetime.now().year)
    name = tournament_name or context.get("tournament_name", "")
    power_slug = context.get("power_slug", "")

    discovered_slug, sample_url = _discover_betting_profile_slug(year, name, power_slug)
    candidates = []
    if discovered_slug:
        candidates.append(discovered_slug)
    if power_slug:
        candidates.append(power_slug.lower().replace("_", "-"))
        override = BETTING_SLUG_OVERRIDES.get(power_slug.lower().replace("_", "-"))
        if override:
            candidates.append(override)
    if name:
        candidates.append(_slugify_text(name))

    seen = set()
    slug_candidates = [s for s in candidates if s and not (s in seen or seen.add(s))]
    return {
        "year": year,
        "slug_candidates": slug_candidates,
        "sample_url": sample_url,
    }


def _fetch_player_betting_profile_article(player_name: str, article_ctx: Dict[str, str]) -> Dict[str, str]:
    year = article_ctx.get("year", "")
    sample_url = article_ctx.get("sample_url", "")
    for slug in article_ctx.get("slug_candidates", []):
        urls = _build_article_url_candidates(player_name, year, slug, sample_url=sample_url)
        for url in urls:
            article = _fetch_article(url)
            if article.get("summary") or article.get("bullets") or article.get("body"):
                article["article_slug"] = slug
                return article
    return {}


# ============================================================================
# Main Profile Builder
# ============================================================================

def fetch_player_names_bulk(player_ids: List[int]) -> Dict[int, str]:
    """Fetch player names in bulk using player profile API."""
    print(f"  Fetching player names...")

    name_map = {}
    for player_id in player_ids:
        try:
            data = fetch_graphql(PLAYER_PROFILE_QUERY, {"playerId": str(player_id)})
            player_data = data.get("data", {}).get("playerProfileOverview", {})
            print(f"    Fetched name for player ID {player_id}")
            if player_data:
                first = player_data.get("firstName", "")
                last = player_data.get("lastName", "")
                display = player_data.get("displayName", "")
                name_map[player_id] = display or f"{first} {last}".strip() or f"Player {player_id}"
            time.sleep(0.05)  # Rate limit
        except Exception:
            pass

    print(f"    Found names for {len(name_map)} players")
    return name_map


def build_betting_profiles(
    tournament_id: str,
    field_csv: str = None,
    odds_csv: str = None,
    max_players: int = None,
    delay: float = 0.3,
    offline: bool = False,
    profiles: bool = False,
) -> pd.DataFrame:
    """
    Build comprehensive betting profiles for tournament field.

    Args:
        tournament_id: PGA Tour tournament ID (e.g., R2026016)
        field_csv: Optional CSV with player names to filter to
        max_players: Limit number of players to fetch (for testing)
        delay: Delay between API calls to avoid rate limiting

    Returns:
        DataFrame with betting profiles
    """
    print("\n" + "=" * 60)
    print("  BUILDING BETTING PROFILES")
    print("=" * 60)

    # Decide odds source
    odds_map: Dict[int, Dict] = {}
    tournament_name = ""
    tournament_context = _resolve_tournament_context(tournament_id)

    # Prefer live odds unless offline is requested
    if not offline:
        odds_map, tournament_name = fetch_tournament_odds(tournament_id)

    # Fallback to cached odds if live call failed or offline flag is set
    if not odds_map:
        default_odds_csv = ODDS_CACHE_DIR / f"pga_odds_{tournament_id}.csv"
        odds_source = Path(odds_csv) if odds_csv else default_odds_csv
        odds_map, tournament_name = load_cached_odds(odds_source)

    if not tournament_name:
        tournament_name = tournament_context.get("tournament_name", "")

    # Fetch field from leaderboard when online
    field: List[Dict] = []
    if not offline:
        field = fetch_tournament_field(tournament_id)

    # If no leaderboard, build field from odds data
    if not field and odds_map:
        print("  Building field from odds data...")

        # Sort player IDs by odds rank (favorites first)
        sorted_players = sorted(odds_map.items(), key=lambda x: x[1].get('odds_rank', 999))
        player_ids = [p[0] for p in sorted_players]

        # Limit if needed
        if max_players:
            player_ids = player_ids[:max_players]

        # Use names from odds data if present; otherwise fetch (requires network)
        name_map = {pid: data.get("player_name") for pid, data in odds_map.items() if data.get("player_name")}
        if not name_map and not offline:
            name_map = fetch_player_names_bulk(player_ids)

        for player_id in player_ids:
            name = name_map.get(player_id, f"Player {player_id}")
            field.append({
                "player_id": player_id,
                "player_name": name,
                "country": "",
                "position": "",
                "total": "",
            })

    # If no field from API but we have a field CSV, build from CSV
    if not field and field_csv:
        print(f"  Building field from CSV: {field_csv}")
        try:
            field_df = pd.read_csv(field_csv)
            field = []
            for _, row in field_df.iterrows():
                pid = row.get("player_id")
                if pd.notna(pid):
                    pid = int(pid)
                field.append({
                    "player_id": pid,
                    "player_name": row.get("player_name", f"Player {pid}"),
                    "country": row.get("country", ""),
                    "position": "",
                    "total": "",
                })
            print(f"    Loaded {len(field)} players from CSV")
        except Exception as e:
            print(f"    Could not load field CSV: {e}")

    if not field:
        print("  No field data available")
        return pd.DataFrame()

    # Filter to field CSV if provided (for when we have both API field and CSV filter)
    if field_csv and len(field) > 0:
        try:
            field_df = pd.read_csv(field_csv)
            # Normalize column name variants
            if "player_name" not in field_df.columns and "player_id" not in field_df.columns:
                raise ValueError("field CSV must contain column 'player_name' or 'player_id'")

            field_ids = set()
            if "player_id" in field_df.columns:
                field_ids = set(field_df["player_id"].dropna().astype(int).tolist())

            def norm_name(n: str) -> str:
                n = str(n or "").lower().strip()
                n = n.replace(",", " ")
                n = re.sub(r"\\s+", " ", n)
                return n

            field_names = set(field_df["player_name"].apply(norm_name).tolist()) if "player_name" in field_df.columns else set()
            # If we still don't have a field (offline) build it from CSV
            if not field:
                field = [
                    {
                        "player_id": row.get("player_id") or None,
                        "player_name": row["player_name"],
                        "country": row.get("country", ""),
                        "position": "",
                        "total": "",
                    }
                    for _, row in field_df.iterrows()
                ]
            else:
                if field_ids:
                    field = [p for p in field if p.get("player_id") in field_ids]
                elif field_names:
                    field = [p for p in field if norm_name(p.get("player_name")) in field_names]
            if len(field) == 0:
                print("  ⚠️ Field filter matched 0 players; skipping filter")
                # fall back to unfiltered field
                field = fetch_tournament_field(tournament_id) if not offline else field
            print(f"  Filtered to {len(field)} players from field CSV")
        except Exception as e:
            print(f"  Could not filter by field CSV: {e}")

    # Limit for testing
    if max_players:
        field = field[:max_players]

    # Build profiles
    records = []
    total = len(field)
    fetch_profiles = bool(profiles)
    article_ctx = {"year": "", "slug_candidates": [], "sample_url": ""}
    if not offline:
        article_ctx = _resolve_betting_profile_article_context(
            tournament_id=tournament_id,
            tournament_name=tournament_name,
        )
        slugs = ", ".join(article_ctx.get("slug_candidates", [])[:3]) or "none"
        print(f"  Betting article slugs: {slugs}")

    print(f"\n  Fetching detailed profiles for {total} players...")
    print("-" * 60)

    for i, player in enumerate(field, 1):
        player_id = player['player_id']
        player_name = player['player_name']

        print(f"  [{i}/{total}] {player_name}...", end=" ", flush=True)

        # Get odds
        odds = odds_map.get(player_id, {})

        # Get profile (optional because PGA profile schema changes often)
        profile = {}
        if fetch_profiles and not offline:
            try:
                profile = fetch_player_profile(player_id)
            except Exception:
                pass

        # Get season stats
        stats = {}
        if not offline:
            try:
                stats = fetch_player_stats(player_id)
            except Exception:
                pass

        # Get strokes gained stats
        sg_stats = {}
        if not offline:
            try:
                sg_stats = fetch_player_sg_stats(player_id)
            except Exception:
                pass

        # Get course history
        course_history = {}
        if not offline:
            try:
                course_history = fetch_player_course_history(player_id)
            except Exception:
                pass

        # Extract recent results from course history (since playerResults API was removed)
        recent_results = extract_recent_form_from_course_history(course_history, limit=5)
        article = {}
        if not offline and article_ctx.get("slug_candidates"):
            try:
                article = _fetch_player_betting_profile_article(player_name, article_ctx)
            except Exception:
                article = {}

        # Build profile record
        record = {
            "player_id": player_id,
            "player_name": player_name,
            "country": player.get("country", profile.get("country", "")),

            # Odds
            "odds_to_win": odds.get("odds_to_win", ""),
            "odds_numeric": odds.get("odds_numeric"),
            "implied_prob": odds.get("implied_prob"),
            "odds_swing": odds.get("odds_swing", ""),
            "odds_rank": odds.get("odds_rank", 999),

            # Rankings
            "world_rank": profile.get("world_rank"),
            "previous_rank": profile.get("previous_rank"),
            "fedex_rank": profile.get("fedex_rank"),
            "fedex_points": profile.get("fedex_points"),

            # Season stats
            "events_played": stats.get("events", 0),
            "wins": stats.get("wins", 0),
            "top_10s": stats.get("top_10s", 0),
            "top_25s": stats.get("top_25s", 0),
            "cuts_made": stats.get("cuts_made", 0),

            # Strokes Gained stats
            "sg_total": sg_stats.get("sg_total"),
            "sg_total_rank": sg_stats.get("sg_total_rank"),
            "sg_ott": sg_stats.get("sg_ott"),
            "sg_ott_rank": sg_stats.get("sg_ott_rank"),
            "sg_app": sg_stats.get("sg_app"),
            "sg_app_rank": sg_stats.get("sg_app_rank"),
            "sg_arg": sg_stats.get("sg_arg"),
            "sg_arg_rank": sg_stats.get("sg_arg_rank"),
            "sg_putt": sg_stats.get("sg_putt"),
            "sg_putt_rank": sg_stats.get("sg_putt_rank"),
            "driving_distance": sg_stats.get("driving_distance"),
            "driving_accuracy": sg_stats.get("driving_accuracy"),
            "gir_pct": sg_stats.get("gir_pct"),
            "scrambling_pct": sg_stats.get("scrambling_pct"),

            # Course history
            "course_history": json.dumps(course_history.get("course_history", [])) if course_history else "",
            "course_history_summary": course_history.get("course_history_summary", ""),

            # Recent results (extracted from course history)
            "recent_results": json.dumps(recent_results) if recent_results else "",

            # Form summary (from course history data)
            "recent_form_summary": _summarize_form_from_history(recent_results) if recent_results else "",

            # Tournament-specific betting profile article
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "bullets": article.get("bullets", ""),
            "headings": article.get("headings", ""),
            "body": article.get("body", ""),
            "body_formatted": article.get("body_formatted", ""),
            "published_at": article.get("published_at", ""),
            "article_url": article.get("article_url", ""),
            "article_slug": article.get("article_slug", ""),
            "article_tournament_name": article.get("article_tournament_name", ""),
        }

        records.append(record)
        print("done")

        # Rate limiting
        time.sleep(delay)

    df = pd.DataFrame(records)

    # Sort by odds rank
    if "odds_rank" in df.columns:
        df = df.sort_values("odds_rank")
    else:
        print("⚠️ odds_rank not available; skipping odds-based sort")

    # Add tournament info
    df["tournament_id"] = tournament_id
    df["tournament_name"] = tournament_name
    df["fetched_at"] = datetime.now().isoformat()

    return df


def _summarize_form(results: List[Dict]) -> str:
    """Create a brief form summary from recent results (legacy format)."""
    if not results:
        return "No recent results"

    summaries = []
    for r in results[:3]:
        finish = r.get("finish", "")
        tournament = r.get("tournament", "")[:20]
        if finish:
            summaries.append(f"{finish} at {tournament}")

    return "; ".join(summaries) if summaries else "No recent results"


def _summarize_form_from_history(results: List[Dict]) -> str:
    """
    Create a brief form summary from course history results.

    Args:
        results: List of dicts with tournament, finish, year keys

    Returns:
        String like "T4 at Hero World (2025); 1 at Masters (2024); T8 at PGA (2024)"
    """
    if not results:
        return "No recent results"

    summaries = []
    for r in results[:5]:  # Show up to 5 recent results
        finish = r.get("finish", "")
        tournament = r.get("tournament", "")[:25]
        year = r.get("year", "")
        if finish and tournament:
            summaries.append(f"{finish} at {tournament} ({year})")

    return "; ".join(summaries) if summaries else "No recent results"


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch betting profiles for tournament field",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--tournament-id", required=True,
                       help="PGA Tour tournament ID (e.g., R2026016)")
    parser.add_argument("--field", type=str, default=None,
                       help="Optional field CSV to filter players")
    parser.add_argument("--odds-csv", type=str, default=None,
                       help="Optional odds CSV to use instead of live API")
    parser.add_argument("--max-players", type=int, default=None,
                       help="Limit players to fetch (for testing)")
    parser.add_argument("--output", type=str, default=None,
                       help="Output CSV path")
    parser.add_argument("--delay", type=float, default=0.3,
                       help="Delay between API calls (seconds)")
    parser.add_argument("--offline", action="store_true",
                       help="Skip network calls and rely on cached CSVs")
    parser.add_argument("--profiles", action="store_true",
                       help="Fetch detailed player profiles (experimental; may fail if schema changes)")

    args = parser.parse_args()

    # Build profiles
    df = build_betting_profiles(
        tournament_id=args.tournament_id,
        field_csv=args.field,
        odds_csv=args.odds_csv,
        max_players=args.max_players,
        delay=args.delay,
        offline=args.offline,
        profiles=args.profiles,
    )

    if len(df) == 0:
        print("\n  No profiles built!")
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"betting_profiles_{args.tournament_id}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # Summary
    print("\n" + "=" * 60)
    print("  BETTING PROFILE SUMMARY")
    print("=" * 60)

    print(f"\n  Tournament: {df['tournament_name'].iloc[0]}")
    print(f"  Players: {len(df)}")
    print(f"  With odds: {df['odds_to_win'].notna().sum()}")

    print(f"\n  Top 10 by Odds:")
    print("-" * 60)

    top10 = df.head(10)
    for _, row in top10.iterrows():
        name = str(row["player_name"])[:25].ljust(25)
        odds = row["odds_to_win"] if row["odds_to_win"] else "N/A"
        swing = row["odds_swing"]
        swing_icon = "↑" if swing == "UP" else "↓" if swing == "DOWN" else "→"
        form = str(row["recent_form_summary"])[:40]
        print(f"  {name} {odds:>8} {swing_icon}  {form}")

    print(f"\n  Saved to: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
