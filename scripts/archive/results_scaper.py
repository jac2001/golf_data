import pandas as pd 

import requests
import json 
import time 


GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"



DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    # NOTE: x-api-key may rotate. If this breaks, recapture from DevTools.
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}


def post_graphql(payload, retries=3, sleep=1.0):
    for attempt in range(retries):
        resp = requests.post(
            GRAPHQL_URL,
            headers=DEFAULT_HEADERS,
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            if attempt < retries - 1:
                time.sleep(sleep)
                continue
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise RuntimeError("Invalid JSON response")

        if data.get("errors"):
            raise RuntimeError(f"GraphQL errors: {data['errors']}")

        return data

    raise RuntimeError("GraphQL request failed after retries")

def fetch_past_results(tournament_id: str, tournament_name: str | None = None):
    year = int(tournament_id[1:5])
    payload = {
        "query": """
        query TournamentPastResults($tournamentId: ID!) {
          tournamentPastResults(id: $tournamentId) {
            id
            players {
              id
              position
              total
              parRelativeScore
              player {
                id
                displayName
                country
              }
              rounds {
                score
                parRelativeScore
              }
              additionalData
            }
          }
        }
        """,
        "variables": {
            "tournamentId": tournament_id
        },
        "operationName": "TournamentPastResults"
    }

    data = post_graphql(payload)

    tpr = data.get("data", {}).get("tournamentPastResults")
  
    if not tpr or not tpr.get("players"):
        raise RuntimeError(f"No past results for {tournament_id}")

    rows = []
    for p in tpr["players"]:
       
        rows.append({
            "tournament_id": tournament_id,
            "tournament_name": tournament_name,
            'year': year,
            "player_id": p["player"]["id"],
            "player_name": p["player"]["displayName"],
            "position": p["position"],
            "total_score": p["total"],
            "to_par": p["parRelativeScore"],
            "fedex_points": p["additionalData"][0] if len(p["additionalData"]) > 0 else None,
            "earnings": p["additionalData"][1] if len(p["additionalData"]) > 1 else None,
            "rounds_played": len(p["rounds"])
        })

    return pd.DataFrame(rows)

tournament_ids_df = pd.read_csv('/Users/jacklegnon/Desktop/golf_data/tournament_ids.csv')
tournament_name_lookup = {}
if "tournament_name" in tournament_ids_df.columns:
    tournament_name_lookup = (
        tournament_ids_df
        .set_index("tournament_id")["tournament_name"]
        .astype(str)
        .to_dict()
    )
tournament_ids = (
    tournament_ids_df["tournament_id"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

print(f"Loaded {len(tournament_ids)} tournament IDs")



leaderboards = []
for tid in tournament_ids:
    try:
        print(f"Fetching leaderboard for {tid}")
        df = fetch_past_results(
            tid,
            tournament_name_lookup.get(tid)
        )
        if df.empty:
            print(f"[WARN] empty leaderboard for {tid}")
            continue 
        print(f'[OK] {tid}: {len(df)} rows.')

        leaderboards.append(df)
    except Exception as e:
        print(f"[WARN] Failed {tid}: {e}")
if not leaderboards:
    raise RuntimeError(
        'No leaderboards were scraped. '
        "Check GraphQL erros above."
    )
leaderboards_df = pd.concat(leaderboards, ignore_index=True)
print(f"Total leaderboards rows: {len(leaderboards_df)}")
leaderboards_df.to_csv('tournament_leaderboards.csv', index=False)