#!/usr/bin/env python3
# /Users/jacklegnon/Desktop/golf_data/scripts/scrapers/probe_pga_odds_markets.py

import argparse
import base64
import gzip
import json
from collections import Counter
from typing import Any, Iterable

import requests

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

DEFAULT_TOURNAMENT_ID = "R2026010"

Q_OUTRIGHT_FULL = """
query TournamentOddsToWin($tournamentId: ID!) {
  tournamentOddsToWin(tournamentId: $tournamentId) {
    tournamentId
    tournamentName
    players {
      playerId
      oddsToWin
      oddsSwing
      oddsSort
      oddsDirection
    }
  }
}
"""

Q_OUTRIGHT_SAFE = """
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

Q_COMPRESSED = """
query oddsToWinCompressed($oddsToWinId: ID!) {
  oddsToWinCompressed(oddsToWinId: $oddsToWinId) {
    id
    payload
  }
}
"""

Q_INTROSPECTION = """
query IntrospectionQuery {
  __schema {
    queryType {
      fields {
        name
        args { name }
      }
    }
  }
}
"""


def walk(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from walk(x)


def post(query: str, operation: str, variables: dict) -> dict:
    r = requests.post(
        GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query, "operationName": operation, "variables": variables},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", str(data["errors"])))
    return data


def try_query(query: str, operation: str, variables: dict) -> dict:
    """Run one GraphQL query and return a structured result object."""
    try:
        data = post(query, operation, variables)
        return {"ok": True, "data": data, "error": ""}
    except Exception as e:
        return {"ok": False, "data": {}, "error": str(e)}


def decode_payload(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return raw

    s = raw.strip()
    if not s:
        return s

    # plain JSON string
    if s[:1] in "{[":
        try:
            return json.loads(s)
        except Exception:
            pass

    # base64 (possibly gzip)
    try:
        b = base64.b64decode(s, validate=False)
        try:
            b = gzip.decompress(b)
        except Exception:
            pass
        text = b.decode("utf-8", errors="ignore").strip()
        if text[:1] in "{[":
            return json.loads(text)
        return text
    except Exception:
        return s


def discover_markets(payload_obj: Any) -> Counter:
    market_counter = Counter()
    market_keys = (
        "marketName", "market", "name", "offerLabel",
        "subcategoryName", "categoryName", "marketType"
    )
    odds_keys = ("odds", "oddsToWin", "americanOdds", "oddsAmerican", "displayOdds", "price")

    for node in walk(payload_obj):
        label = None
        for k in market_keys:
            if isinstance(node.get(k), str) and node.get(k).strip():
                label = node[k].strip()
                break
        if not label:
            continue

        has_odds_here = any(k in node for k in odds_keys)
        has_selections = any(isinstance(node.get(k), list) for k in ("selections", "outcomes", "offers", "players"))
        if has_odds_here or has_selections:
            market_counter[label] += 1

    return market_counter


def find_available_markets(payload_obj: Any) -> list[dict]:
    """Find availableMarkets array anywhere in the decoded payload tree."""
    out: list[dict] = []
    for node in walk(payload_obj):
        arr = node.get("availableMarkets")
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict) and item.get("id") is not None:
                    out.append(item)
    # Deduplicate by id.
    by_id = {}
    for m in out:
        mid = str(m.get("id"))
        by_id[mid] = m
    return list(by_id.values())


def _summarize_payload(decoded: Any) -> tuple[str, int, list[str]]:
    """Return (primary_row_key, row_count, sample_keys) for decoded payload."""
    if not isinstance(decoded, dict):
        return ("", 0, [])
    for key in ("players", "selections", "outcomes", "entries", "offers", "rows"):
        arr = decoded.get(key)
        if isinstance(arr, list):
            sample_keys = list(arr[0].keys()) if arr and isinstance(arr[0], dict) else []
            return (key, len(arr), sample_keys[:20])
    return ("", 0, list(decoded.keys())[:20])


def main():
    parser = argparse.ArgumentParser(description="Probe PGA Tour odds markets via GraphQL")
    parser.add_argument("--tournament-id", default=DEFAULT_TOURNAMENT_ID, help="Tournament ID like R2026010")
    parser.add_argument(
        "--market-id",
        action="append",
        default=[],
        help="Optional market id(s) to probe directly (repeat or comma-separated).",
    )
    parser.add_argument(
        "--suffix",
        default="american",
        help="oddsToWinId suffix (default: american)",
    )
    args = parser.parse_args()
    tournament_id = str(args.tournament_id).strip()
    suffix = str(args.suffix).strip() or "american"
    manual_market_ids = []
    for token in args.market_id:
        for part in str(token).split(","):
            part = part.strip()
            if part:
                manual_market_ids.append(part)

    print(f"Probing PGA odds for {tournament_id}")

    # 1) known outright endpoint with schema-safe fallback.
    out_result = try_query(Q_OUTRIGHT_FULL, "TournamentOddsToWin", {"tournamentId": tournament_id})
    if (not out_result["ok"]) and ("oddsDirection" in out_result["error"]):
        print("  oddsDirection not present in schema; retrying safe odds query...")
        out_result = try_query(Q_OUTRIGHT_SAFE, "TournamentOddsToWin", {"tournamentId": tournament_id})

    if out_result["ok"]:
        out = out_result["data"]
        players = out.get("data", {}).get("tournamentOddsToWin", {}).get("players", []) or []
        print(f"  tournamentOddsToWin players: {len(players)}")
        if players:
            print(f"  sample keys: {list(players[0].keys())}")
    else:
        print(f"  tournamentOddsToWin failed: {out_result['error']}")

    # 2) compressed endpoint variants.
    compressed_ok = False
    decoded_base = None
    for op_name in ["oddsToWinCompressed", "OddsToWinCompressed"]:
        comp_result = try_query(Q_COMPRESSED, op_name, {"oddsToWinId": tournament_id})
        if not comp_result["ok"]:
            print(f"  {op_name} failed: {comp_result['error']}")
            continue

        compressed_ok = True
        comp = comp_result["data"]
        node = comp.get("data", {}).get("oddsToWinCompressed") or {}
        raw_payload = node.get("payload")
        decoded = decode_payload(raw_payload)
        decoded_base = decoded
        markets = discover_markets(decoded)
        row_key, row_count, row_keys = _summarize_payload(decoded)

        print(f"  {op_name} payload type: {type(decoded).__name__}")
        if row_key:
            print(f"  primary rows: {row_key} ({row_count})")
            if row_keys:
                print(f"  sample row keys: {row_keys}")
        if markets:
            print(f"\nDiscovered market labels via {op_name} (top 30):")
            for name, cnt in markets.most_common(30):
                print(f"  {name}: {cnt}")
        else:
            print(f"  No extra market structure detected via {op_name}.")
        break

    if not compressed_ok:
        print("  No compressed odds operation succeeded.")
        decoded_base = None

    # 2b) probe other market IDs if available.
    available_markets = find_available_markets(decoded_base) if decoded_base is not None else []
    if available_markets:
        print("\n  availableMarkets discovered:")
        for m in available_markets:
            print(
                f"    id={m.get('id')} | type={m.get('marketType', '')} | "
                f"name={m.get('name', '')} | display={m.get('displayName', '')}"
            )

    market_ids_to_probe = [str(m.get("id")) for m in available_markets if m.get("id") is not None]
    if manual_market_ids:
        market_ids_to_probe = manual_market_ids

    if market_ids_to_probe:
        print(f"\n  probing {len(market_ids_to_probe)} market id(s) via oddsToWinId pattern...")
        for mid in market_ids_to_probe:
            odds_to_win_id = f"{tournament_id}-{mid}-{suffix}"
            probe_res = try_query(Q_COMPRESSED, "oddsToWinCompressed", {"oddsToWinId": odds_to_win_id})
            if not probe_res["ok"]:
                print(f"    {odds_to_win_id}: FAILED ({probe_res['error']})")
                continue
            node = probe_res["data"].get("data", {}).get("oddsToWinCompressed") or {}
            decoded = decode_payload(node.get("payload"))
            row_key, row_count, row_keys = _summarize_payload(decoded)
            print(f"    {odds_to_win_id}: OK type={type(decoded).__name__} rows={row_key or 'n/a'}:{row_count}")
            if row_keys:
                print(f"      sample keys: {row_keys}")
            labels = discover_markets(decoded)
            if labels:
                top = ", ".join([f"{k}({v})" for k, v in labels.most_common(5)])
                print(f"      market labels: {top}")

    # 3) introspection hints (if enabled)
    try:
        intro = post(Q_INTROSPECTION, "IntrospectionQuery", {})
        fields = intro.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
        candidates = [
            f for f in fields
            if any(t in f.get("name", "").lower() for t in ("odds", "market", "line", "bet"))
        ]
        print("\nSchema fields containing odds/market/line/bet:")
        for f in candidates[:80]:
            args = ", ".join(a.get("name", "") for a in f.get("args", []))
            print(f"  {f.get('name')}({args})")
    except Exception as e:
        print(f"\nIntrospection unavailable: {e}")


if __name__ == "__main__":
    main()
