#!/usr/bin/env python3
"""
Betting Profile Article Scraper
================================

Purpose
-------
Scrape PGA Tour betting-profile article pages (e.g.,
https://www.pgatour.com/article/news/betting-profile/2026/the-american-express/ben-griffin-pga-tour-betting-stats-the-american-express-2026)
into structured text so we can enrich betting profiles with narrative blurbs.

Outputs
-------
CSV/JSONL (choose via flags) with columns/keys:
  - player_name       Best-effort name parsed from meta/title/URL
  - title             Article title
  - subtitle          Meta description, if present
  - author            Meta author, if present
  - published_at      Meta article:published_time, ISO string if present
  - tournament_slug   Slug inferred from URL (e.g., "the-american-express-2026")
  - url               Source URL
  - summary           First ~3 paragraphs concatenated
  - headings          H2/H3 text joined with " | "
  - bullets           LI text joined with " | "
  - body              Paragraph text joined with single newlines
  - body_formatted    Simple markdown-ish reconstruction (headings + bullets + paragraphs with blank lines)

Usage
-----
    python scripts/scrapers/fetch_betting_profile_articles.py \
        --urls <url1> <url2> ... \
        --output data/betting_profiles/american_express_2026_articles.csv

    # Or supply a file with one URL per line
    python scripts/scrapers/fetch_betting_profile_articles.py \
        --url-file data/urls/american_express_2026.txt

    # Or pass URLs positionally (no flag)
    python scripts/scrapers/fetch_betting_profile_articles.py \
        https://www.pgatour.com/.../player-article

    # Build URLs from a field CSV using a template with {name_slug}
    python scripts/scrapers/fetch_betting_profile_articles.py \
        --field-csv data/fields/american_express_2026_clean.csv \
        --url-template \"https://www.pgatour.com/article/news/betting-profile/2026/the-american-express/{name_slug}-pga-tour-betting-stats-the-american-express-2026\" \
        --output data/betting_profiles/american_express_2026_articles.csv

Notes
-----
- Requires `beautifulsoup4`. If missing, install with:
    pip install beautifulsoup4
- Designed to fail soft: if a URL can’t be fetched or parsed, it’s logged and
  skipped so the rest still succeed.
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - dependency check
    print("beautifulsoup4 is required. Install with: pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

def fetch_html(url: str, timeout: int = 20) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200 and resp.text:
            return resp.text
        print(f"  ! HTTP {resp.status_code} for {url}")
    except Exception as e:  # pragma: no cover - network error path
        print(f"  ! Request failed for {url}: {e}")
    return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def drop_noise_elements(soup: BeautifulSoup) -> None:
    """Remove obvious non-article elements to reduce nav/leaderboard chatter."""
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "button", "input", "form"]):
        tag.decompose()

    noise_re = re.compile(
        r"(nav|menu|header|footer|breadcrumb|social|share|leaderboard|scores|pagination|newsletter|ads?)",
        re.I,
    )
    for tag in soup.find_all(attrs={"role": re.compile("navigation|banner|contentinfo|complementary", re.I)}):
        tag.decompose()
    for tag in soup.find_all(class_=noise_re):
        tag.decompose()
    for tag in soup.find_all(id=noise_re):
        tag.decompose()


def paragraph_is_noise(text: str, expected_name: str = "") -> bool:
    """Heuristic to drop scoreboard/menu fragments."""
    if not text:
        return True
    if len(text) <= 2:
        return True
    lower = text.lower()
    if lower in {"leaderboard", "menu", "search", "view leaderboard", "view all news"}:
        return True
    # Pure numbers or small scoreboard tokens like "T4", "-19", "1"
    if re.fullmatch(r"[tT]?\d{1,2}", text):
        return True
    if re.fullmatch(r"-?\d{1,2}", text):
        return True
    # Mostly digits/punctuation
    digits = sum(c.isdigit() for c in text)
    if digits > 0 and digits / max(len(text), 1) > 0.6:
        return True
    # Unrelated betting profile links
    if "betting profile" in lower and expected_name and expected_name.lower() not in lower:
        return True
    # Footer/general site chrome
    noise_phrases = {
        "view all news",
        "the tour",
        "quick links",
        "shop",
        "apps",
        "partnerships",
        "copyright",
        "about",
        "careers",
        "tpc network",
        "contact",
        "tourcast",
        "impact",
        "marketing partners",
        "affiliates",
        "media",
        "advertise",
        "superstore",
        "tickets",
        "mastercard tickets",
        "pga tour vision",
    }
    if any(phrase in lower for phrase in noise_phrases):
        return True
    return False


def extract_player_name(url: str, title: str) -> str:
    # Prefer title cue before a separator
    if title:
        for sep in [" - ", " | ", " — "]:
            if sep in title:
                candidate = title.split(sep)[0]
                return clean_text(candidate)
    # Fallback to URL slug
    slug = url.rstrip("/").split("/")[-1]
    parts = slug.split("-")
    # Stop collecting tokens once we hit obvious non-name markers
    stop_tokens = {"pga", "tour", "betting", "stats", "the", "and", "of", "profile"}
    name_tokens = []
    for token in parts:
        if token.isdigit() or token in stop_tokens:
            break
        name_tokens.append(token)
    return clean_text(" ".join(t.capitalize() for t in name_tokens)) or slug


def extract_tournament_slug(url: str) -> str:
    # URL pattern: .../betting-profile/2026/the-american-express/<slug>
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return parts[-2]
    return ""


def parse_next_data_article(html: str) -> Optional[Dict[str, str]]:
    """
    Parse article from __NEXT_DATA__ JSON (PGA Tour uses Next.js).
    Returns None if no article data found.
    """
    import json

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    queries = data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])

    article = None
    for q in queries:
        qkey = q.get('queryKey', [])
        if qkey and qkey[0] == 'newsArticleDetails':
            article = q.get('state', {}).get('data', {})
            break

    if not article or not article.get('nodes'):
        return None

    # Extract content from nodes
    paragraphs = []
    headings = []
    bullets = []
    formatted_parts = []

    for node in article.get('nodes', []):
        if not isinstance(node, dict):
            continue

        typename = node.get('__typename', '')

        if typename == 'NewsArticleParagraph':
            segments = node.get('segments', [])
            text = ' '.join(s.get('value', '') for s in segments if s.get('value'))
            if text:
                paragraphs.append(clean_text(text))
                formatted_parts.append(clean_text(text))

        elif typename == 'NewsArticleOddsParagraph':
            # Odds paragraph - extract text content
            segments = node.get('segments', [])
            text = ' '.join(s.get('value', '') for s in segments if s.get('value'))
            if text:
                paragraphs.append(clean_text(text))
                formatted_parts.append(clean_text(text))

        elif typename in ('NewsArticleHeader', 'NewsArticleHeading'):
            text = node.get('text', '') or node.get('value', '')
            if not text:
                # Try segments
                segments = node.get('segments', [])
                text = ' '.join(s.get('value', '') for s in segments if s.get('value'))
            if not text:
                # Try headerSegments (PGA Tour format)
                for hs in node.get('headerSegments', []):
                    for seg in hs.get('segments', []):
                        if seg.get('value'):
                            text = seg.get('value')
                            break
                    if text:
                        break
            if text:
                headings.append(clean_text(text))
                formatted_parts.append(f"## {clean_text(text)}")

        elif typename in ('NewsArticleList', 'UnorderedListNode', 'OrderedListNode'):
            items = node.get('items', [])
            for item in items:
                if isinstance(item, dict):
                    segments = item.get('segments', [])
                    text = ' '.join(s.get('value', '') for s in segments if s.get('value'))
                elif isinstance(item, str):
                    text = item
                else:
                    continue
                if text:
                    bullets.append(clean_text(text))
                    formatted_parts.append(f"- {clean_text(text)}")

    # Convert timestamp to ISO date
    published_at = ""
    date_ms = article.get('datePublished')
    if date_ms:
        try:
            from datetime import datetime
            published_at = datetime.fromtimestamp(date_ms / 1000).isoformat()
        except Exception:
            pass

    return {
        "title": article.get('headline', ''),
        "subtitle": "",
        "author": "",
        "published_at": published_at,
        "headings": " | ".join(headings),
        "bullets": " | ".join(bullets),
        "body": "\n".join(paragraphs),
        "body_formatted": "\n\n".join(formatted_parts),
        "summary": " ".join(paragraphs[:3]),
        "tournament_name": article.get('tournamentName', ''),
        "player_names": ", ".join(article.get('playerNames', [])),
    }


def parse_article(html: str, expected_name: str = "") -> Dict[str, str]:
    # First try Next.js __NEXT_DATA__ extraction (PGA Tour uses this)
    next_data = parse_next_data_article(html)
    if next_data and next_data.get('body'):
        return next_data

    # Fall back to HTML parsing for other sites
    soup = BeautifulSoup(html, "html.parser")
    drop_noise_elements(soup)

    title = ""
    meta_title = soup.find("meta", property="og:title")
    if meta_title and meta_title.get("content"):
        title = meta_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    subtitle = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        subtitle = meta_desc["content"].strip()
    elif soup.find("meta", property="og:description"):
        subtitle = soup.find("meta", property="og:description").get("content", "").strip()

    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()

    published_at = ""
    meta_pub = soup.find("meta", property="article:published_time")
    if meta_pub and meta_pub.get("content"):
        published_at = meta_pub["content"].strip()

    # Locate the main article container
    candidates = [
        soup.find("article"),
        soup.find("div", class_=re.compile("article-body|article__body|rich-text|content-body")),
    ]
    container = next((c for c in candidates if c), soup)

    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in container.find_all("p")]
    paragraphs = [p for p in paragraphs if p and not paragraph_is_noise(p, expected_name)]

    headings = [clean_text(h.get_text(" ", strip=True)) for h in container.find_all(["h2", "h3"])]
    headings = [h for h in headings if h]

    bullets = [clean_text(li.get_text(" ", strip=True)) for li in container.find_all("li")]
    bullets = [b for b in bullets if b and not paragraph_is_noise(b, expected_name)]

    # Build a simple markdown-ish formatted body following DOM order
    formatted_parts = []
    for node in container.descendants:
        if getattr(node, "name", None) in ["h2", "h3"]:
            level = "##" if node.name == "h2" else "###"
            text = clean_text(node.get_text(" ", strip=True))
            if text and not paragraph_is_noise(text, expected_name):
                formatted_parts.append(f"{level} {text}")
        elif getattr(node, "name", None) == "p":
            text = clean_text(node.get_text(" ", strip=True))
            if text and not paragraph_is_noise(text, expected_name):
                formatted_parts.append(text)
        elif getattr(node, "name", None) in ["ul", "ol"]:
            for li in node.find_all("li", recursive=False):
                text = clean_text(li.get_text(" ", strip=True))
                if text and not paragraph_is_noise(text, expected_name):
                    formatted_parts.append(f"- {text}")

    body = "\n".join(paragraphs)
    body_formatted = "\n\n".join(formatted_parts)
    summary = " ".join(paragraphs[:3])

    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "published_at": published_at,
        "headings": " | ".join(headings),
        "bullets": " | ".join(bullets),
        "body": body,
        "body_formatted": body_formatted,
        "summary": summary,
    }


def scrape_url(url: str) -> Optional[Dict[str, str]]:
    html = fetch_html(url)
    if not html:
        return None

    # Get a first-pass player name from URL to aid noise filtering
    provisional_name = extract_player_name(url, "")
    parsed = parse_article(html, expected_name=provisional_name)
    player_name = extract_player_name(url, parsed.get("title", "")) or provisional_name
    tournament_slug = extract_tournament_slug(url)

    return {
        "player_name": player_name,
        "title": parsed.get("title", ""),
        "subtitle": parsed.get("subtitle", ""),
        "author": parsed.get("author", ""),
        "published_at": parsed.get("published_at", ""),
        "tournament_slug": tournament_slug,
        "url": url,
        "summary": parsed.get("summary", ""),
        "headings": parsed.get("headings", ""),
        "bullets": parsed.get("bullets", ""),
        "body": parsed.get("body", ""),
        "body_formatted": parsed.get("body_formatted", ""),
    }


def slugify_name(name: str) -> str:
    """
    Convert player name to URL slug format.
    Handles "Last, First" -> "first-last" conversion.
    Handles special characters like Å -> a, é -> e, etc.
    """
    import unicodedata

    # Handle "Last, First" format
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) == 2:
            name = f"{parts[1].strip()} {parts[0].strip()}"

    # Normalize unicode characters (Å -> A, é -> e, etc.)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))

    # Convert to lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")


def read_urls(args) -> List[str]:
    urls = []
    # Positional URLs (no flag)
    if args.positional_urls:
        urls.extend(args.positional_urls)
    # Flagged URLs
    if args.urls:
        urls.extend(args.urls)
    # File of URLs
    if args.url_file:
        path = Path(args.url_file)
        if path.exists():
            with path.open() as f:
                urls.extend([line.strip() for line in f if line.strip()])
    # Generate from field CSV + template
    if args.field_csv and args.url_template:
        field_path = Path(args.field_csv)
        if field_path.exists():
            import pandas as pd

            try:
                df = pd.read_csv(field_path)
                col = args.name_column or "player_name"
                for name in df[col].dropna().astype(str):
                    slug = slugify_name(name)
                    urls.append(args.url_template.format(name_slug=slug, name=name, slug=slug))
            except Exception as e:
                print(f"Could not build URLs from field CSV: {e}")
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            deduped.append(u)
            seen.add(u)
    return deduped


def save_csv(rows: List[Dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "player_name",
        "title",
        "subtitle",
        "author",
        "published_at",
        "tournament_slug",
        "url",
        "summary",
        "headings",
        "bullets",
        "body",
        "body_formatted",
    ]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_jsonl(rows: List[Dict[str, str]], output: Path) -> None:
    import json

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape PGA betting-profile article pages")
    parser.add_argument("positional_urls", nargs="*", help="Article URLs (positional)")
    parser.add_argument("--urls", nargs="*", help="Article URLs")
    parser.add_argument("--url-file", help="File with one URL per line")
    parser.add_argument("--field-csv", help="Field CSV with player names to build URLs")
    parser.add_argument("--name-column", default="player_name", help="Column in field CSV containing player names")
    parser.add_argument(
        "--url-template",
        help="Template with {name_slug} (and optional {name} or {slug}) to build URLs from field CSV",
    )
    parser.add_argument("--output", help="Output file path (CSV or JSONL, inferred by extension)")
    args = parser.parse_args()

    urls = read_urls(args)
    if not urls:
        print("No URLs provided.")
        return 1

    output = Path(args.output) if args.output else Path("data/betting_profiles/article_blurbs.csv")

    print(f"\n{'='*60}")
    print(f"  SCRAPING BETTING PROFILE ARTICLES")
    print(f"{'='*60}")
    print(f"  URLs to scrape: {len(urls)}")
    print(f"{'='*60}\n")

    rows = []
    for i, url in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] Fetching...", end=" ", flush=True)
        row = scrape_url(url)
        if row and row.get('body'):
            rows.append(row)
            print(f"✓ {row.get('player_name', 'Unknown')}")
        else:
            print(f"✗ Skipped (no content)")

    if output.suffix.lower() == ".jsonl":
        save_jsonl(rows, output)
    else:
        save_csv(rows, output)

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Scraped: {len(rows)}/{len(urls)} articles")
    print(f"  Output:  {output}")

    if rows:
        print(f"\n  Players with betting profiles:")
        print(f"  {'-'*56}")
        for row in rows[:10]:  # Show first 10
            name = row.get('player_name', 'Unknown')[:25].ljust(25)
            body_preview = row.get('body', '')[:50] + "..." if row.get('body') else "(no body)"
            print(f"    {name} {body_preview}")
        if len(rows) > 10:
            print(f"    ... and {len(rows) - 10} more")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
