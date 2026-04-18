from scripts.scrapers.dg_client import dg_get 
import pandas as pd
def fetch_skill_ratings():
    return dg_get("/preds/skill-ratings", {'display': 'values'})



def parse_response(data: dict) -> pd.DataFrame:
    rows = data.get("players", [])
    last_updated = data.get("last_updated", "")
    records = []
    for p in rows:
        records.append({
             "dg_id":         p.get("dg_id"),
              "player_name":   p.get("player_name", ""),
              "last_updated":  last_updated,
              "dg_skill_total": p.get("sg_total"),
              "dg_skill_ott":   p.get("sg_ott"),
              "dg_skill_app":   p.get("sg_app"),
              "dg_skill_arg":   p.get("sg_arg"),
              "dg_skill_putt":  p.get("sg_putt"),
              "dg_skill_dist":  p.get("driving_dist"),
              "dg_skill_acc":   p.get("driving_acc"),
        })
        
    return pd.DataFrame(records)

