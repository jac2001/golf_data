#!/usr/bin/env python3
# scripts/scrapers/capture_pga_odds_network.py

import argparse
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www.pgatour.com/tournaments/2026/cognizant-classic-in-the-palm-beaches/R2026010/odds"
OUT = Path("data/odds/pga_odds_network_capture.json")

KEYWORDS = ("odds", "market", "bet", "sportsbook", "fanduel", "graphql")

def keep_url(u: str) -> bool:
    lu = u.lower()
    return any(k in lu for k in KEYWORDS)


def _try_parse_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_graphql_meta(post_data: str):
    """Extract operationName + key vars from GraphQL request payload."""
    js = _try_parse_json(post_data or "")
    if not isinstance(js, dict):
        return {}
    vars_obj = js.get("variables", {}) if isinstance(js.get("variables"), dict) else {}
    return {
        "operation_name": js.get("operationName", ""),
        "query_head": str(js.get("query", "")).split("\n", 1)[0][:200],
        "variables": vars_obj,
        "tournament_id_var": vars_obj.get("tournamentId"),
        "odds_to_win_id_var": vars_obj.get("oddsToWinId"),
    }


def main():
    parser = argparse.ArgumentParser(description="Capture PGA odds page network traffic")
    parser.add_argument("--url", default=URL, help="Odds page URL to open")
    parser.add_argument("--output", default=str(OUT), help="Output JSON file")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    args = parser.parse_args()

    out_path = Path(args.output)
    captured = []
    closing = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bool(args.headless))
        page = browser.new_page()

        def on_response(resp):
            try:
                if closing:
                    return
                url = resp.url
                if not keep_url(url):
                    return

                req = resp.request
                post_data = req.post_data or ""
                body = ""
                try:
                    body = resp.text()
                except Exception:
                    body = ""

                gql_meta = {}
                if "graphql" in url.lower():
                    gql_meta = _extract_graphql_meta(post_data)

                item = {
                    "status": resp.status,
                    "method": req.method,
                    "url": url,
                    "request_headers": dict(req.headers),
                    "request_post_data": post_data[:20000],
                    "response_headers": dict(resp.headers),
                    "response_body": body[:200000],
                }
                if gql_meta:
                    item.update(gql_meta)
                captured.append(item)

                if gql_meta.get("operation_name"):
                    tid = gql_meta.get("tournament_id_var")
                    oid = gql_meta.get("odds_to_win_id_var")
                    print(f"{resp.status} {req.method} {url} | op={gql_meta['operation_name']} | tournamentId={tid} | oddsToWinId={oid}")
                else:
                    print(f"{resp.status} {req.method} {url}")
            except Exception:
                # Prevent async callback exceptions from surfacing as unhandled futures.
                return

        page.on("response", on_response)

        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)

        # Click likely market tabs/buttons/links.
        labels = [
            "Market", "Matchup", "Best Score",
            "Round 1", "Round 2", "Round 3", "Round 4",
            "Winner", "Top 5", "Top 10", "Top 20", "Make Cut",
            "Finishes", "Groups", "Player Props", "3 Ball", "Nationality",
        ]
        for label in labels:
            clicked = False
            for locator in [
                page.locator("button", has_text=re.compile(label, re.I)),
                page.locator('[role="tab"]', has_text=re.compile(label, re.I)),
                page.locator("a", has_text=re.compile(label, re.I)),
            ]:
                if locator.count() == 0:
                    continue
                try:
                    locator.first.click(timeout=2500)
                    page.wait_for_timeout(1800)
                    clicked = True
                    break
                except Exception:
                    pass
            if clicked:
                continue

        # Let in-flight requests settle before teardown.
        page.wait_for_timeout(2500)
        closing = True
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

        browser.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(captured, indent=2))

    gql_ops = {}
    for row in captured:
        op = row.get("operation_name")
        if op:
            gql_ops[op] = gql_ops.get(op, 0) + 1

    print(f"\nSaved: {out_path} ({len(captured)} responses)")
    if gql_ops:
        print("GraphQL operations seen:")
        for op, cnt in sorted(gql_ops.items(), key=lambda x: (-x[1], x[0])):
            print(f"  - {op}: {cnt}")

if __name__ == "__main__":
    main()
