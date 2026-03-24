#!/usr/bin/env python3                                                                                                
"""                                                                                                                   
Walk-Forward Time-Series Cross-Validation
==========================================                                                                            
Evaluates model accuracy year by year, the honest way.    
                                                                                                                    
Instead of one train/test split, we use rolling windows:                                                              
- Train 2016-2021 → test 2022                                                                                       
- Train 2016-2022 → test 2023                                                                                       
- Train 2016-2023 → test 2024                           
- Train 2016-2024 → test 2025
                                                                                                                    
This tells us:
1. How stable is accuracy across years? (degrading = model needs more features)                                     
2. What's the realistic AUC we should expect going forward?                                                         
3. Which targets (win/top5/top10/top20) are most predictable?
                                                                                                                    
Outputs:                                                  
    outputs/timeseries_cv_results.csv  — AUC + Brier score per fold × target                                          
    outputs/timeseries_cv_report.txt   — plain-English summary                                                        
"""                                                                                                                   
from __future__ import annotations                                                                                    
from pathlib import Path                                                                                              
import warnings                                           
warnings.filterwarnings("ignore")
                                                                                                                    
import numpy as np
import pandas as pd                                                                                                   
from sklearn.ensemble import RandomForestClassifier       
from sklearn.metrics import roc_auc_score, brier_score_loss
                                                                                                                    
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"                                                                                  
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"                                                                               

# Same feature groups as train_final_models.py                                                                        
TARGETS = {"win": "won", "top5": "top5", "top10": "top10", "top20": "top20"}
                                                                                                                    
# Walk-forward folds: each tuple is (test_year, min_train_year)                                                       
# We need at least 3 years of training data before testing                                                            
FOLDS = [                                                                                                             
    (2022, 2016),                                                                                                     
    (2023, 2016),
    (2024, 2016),                                                                                                     
    (2025, 2016),                                         
]




RF_PARAMS = dict(
    n_estimators=200,                                                                                                 
      max_depth=6,                                          
      min_samples_split=40,                                                                                             
      min_samples_leaf=20,
      max_features="sqrt",                                                                                              
      random_state=42,                                      
      class_weight="balanced_subsample",                                                                                
      n_jobs=1
)



def get_features(df: pd.DataFrame) -> list[str]:
    """Mirror the feature selection from train_final_models.py."""                                                    
    season_sg  = [c for c in df.columns if c.startswith("season_sg_")]                                                
    hist       = [c for c in df.columns if c.startswith("hist_") or c.startswith("has_")]                             
    venue      = [c for c in df.columns if c in ("venue_avg_finish", "venue_finish_std")]                             
    field      = [c for c in df.columns if "field_" in c]                                                             
    rank       = ["world_rank_log"] if "world_rank_log" in df.columns else ["world_rank"]
    form_names = [                                                                                                    
        "form_trend", "finish_consistency", "recent_top10s", "recent_top5s",                                          
        "recent_cuts_pct", "recent_birdie_avg", "recent_bogey_avg",                                                   
        "recent_scoring_avg", "recent_gir_pct", "recent_scrambling",                                                  
        "recent_bounce_back", "recent_final_round", "recent_sand_save",                                               
        "recent_sg_weighted", "recent_sg_trend",                                                                      
        "recent_sg_ott_weighted", "recent_sg_app_weighted",                                                           
        "recent_sg_arg_weighted", "recent_sg_putt_weighted",                                                          
    ]                                                                                                                 
    form    = [c for c in df.columns if c in form_names]                                                              
    dg_fit  = [c for c in df.columns if c.startswith("dg_fit_") or c == "predictive_sg_weighted"]                     
                                                                                                                    
    all_feats = season_sg + hist + venue + field + rank + form + dg_fit                                               
    seen, deduped = set(), []                                                                                         
    for f in all_feats:                                                                                               
        if f not in seen:                                 
            seen.add(f)                                                                                               
            deduped.append(f)
                                                                                                                    
    return [f for f in deduped if f in df.columns]        

                                                                                                                    
def run_fold(df: pd.DataFrame, features: list[str],
            test_year: int, min_train_year: int) -> dict:                                                            
    """Train on all years before test_year, evaluate on test_year."""                                                 
    train = df[(df["year"] >= min_train_year) & (df["year"] < test_year)].copy()
    test  = df[df["year"] == test_year].copy()                                                                        
                                                                                                                    
    # Impute with training medians (never leak test stats)                                                            
    medians = train[features].median(numeric_only=True)                                                               
    train[features] = train[features].fillna(medians)                                                                 
    test[features]  = test[features].fillna(medians)                                                                  

    row = {                                                                                                           
        "test_year":  test_year,                          
        "train_years": f"{min_train_year}-{test_year - 1}",                                                           
        "n_train": len(train),
        "n_test":  len(test),                                                                                         
    }                                                     
                                                                                                                    
    X_train = train[features].values                      
    X_test  = test[features].values
                                                                                                                    
    for label, target_col in TARGETS.items():                                                                         
        if target_col not in df.columns:                                                                              
            continue                                                                                                  
        y_train = train[target_col].fillna(0).values      
        y_test  = test[target_col].fillna(0).values
                                                                                                                    
        if y_train.sum() < 5 or y_test.sum() < 2:                                                                     
            row[f"{label}_auc"]   = float("nan")                                                                      
            row[f"{label}_brier"] = float("nan")                                                                      
            continue                                      
                                                                                                                    
        rf = RandomForestClassifier(**RF_PARAMS)          
        rf.fit(X_train, y_train)
        probs = rf.predict_proba(X_test)[:, 1]                                                                        

        row[f"{label}_auc"]   = round(roc_auc_score(y_test, probs), 4)                                                
        row[f"{label}_brier"] = round(brier_score_loss(y_test, probs), 4)
                                                                                                                    
    return row                                            


def main():
    # Load training data
    processed = DATA_DIR / "processed"                                                                                
    candidates = sorted(processed.glob("master_training_data_*.csv"),
                        key=lambda p: p.stat().st_mtime, reverse=True)                                                
    if not candidates:                                    
        print("ERROR: No master_training_data_*.csv found. Run merge script first.")                                  
        return                                                                                                        
    data_file = candidates[0]
    print(f"Loading {data_file.name}...")                                                                             
                                                        
    df = pd.read_csv(data_file)                                                                                       
    # Exclude 2026 partial season from both train and test
    df = df[df["year"] <= 2025].copy()                                                                                
    print(f"  {len(df):,} rows, years {df['year'].min()}-{df['year'].max()}")
                                                                                                                    
    features = get_features(df)                           
    print(f"  {len(features)} features\n")                                                                            
                                                                                                                    
    # Run all folds
    rows = []                                                                                                         
    for test_year, min_year in FOLDS:                     
        print(f"Fold: train {min_year}-{test_year - 1} → test {test_year}...", end=" ", flush=True)
        row = run_fold(df, features, test_year, min_year)                                                             
        rows.append(row)
        aucs = [f"{label}={row[f'{label}_auc']:.4f}"                                                                  
                for label in TARGETS if f"{label}_auc" in row]                                                        
        print("  ".join(aucs))                                                                                        
                                                                                                                    
    results = pd.DataFrame(rows)                                                                                      
    out_csv = OUTPUTS_DIR / "timeseries_cv_results.csv"   
    results.to_csv(out_csv, index=False)                                                                              
    print(f"\nSaved → {out_csv.name}")
                                                                                                                    
    # Plain-English report                                
    lines = []                                                                                                        
    lines.append("Walk-Forward Cross-Validation Report")  
    lines.append("=" * 50)
    lines.append(f"Data: {data_file.name}")                                                                           
    lines.append(f"Features: {len(features)}")
    lines.append("")                                                                                                  
    lines.append("AUC by year (higher = better, 0.5 = random, 1.0 = perfect):")
    lines.append(f"{'Year':<8} {'Win':>8} {'Top5':>8} {'Top10':>8} {'Top20':>8}")                                     
    lines.append("-" * 42)                                                                                            
    for _, r in results.iterrows():                                                                                   
        lines.append(                                                                                                 
            f"{int(r['test_year']):<8} "                                                                              
            f"{r.get('win_auc', float('nan')):>8.4f} "
            f"{r.get('top5_auc', float('nan')):>8.4f} "                                                               
            f"{r.get('top10_auc', float('nan')):>8.4f} "                                                              
            f"{r.get('top20_auc', float('nan')):>8.4f}"
        )                                                                                                             
    lines.append("-" * 42)                                
                                                                                                                    
    # Averages                                            
    for label in TARGETS:
        col = f"{label}_auc"                                                                                          
        if col in results.columns:
            avg = results[col].mean()                                                                                 
            lines.append(f"  Avg {label} AUC: {avg:.4f}") 
                                                                                                                    
    lines.append("")
    lines.append("Interpretation:")                                                                                   
    lines.append("  AUC > 0.75 = strong predictive power")                                                            
    lines.append("  AUC 0.65-0.75 = moderate (typical for golf)")                                                     
    lines.append("  AUC < 0.65 = weak / near random")                                                                 
    lines.append("")                                                                                                  
    lines.append("Brier Score (lower = better calibrated, 0.0 = perfect):")                                           
    lines.append(f"{'Year':<8} {'Win':>8} {'Top5':>8} {'Top10':>8} {'Top20':>8}")                                     
    lines.append("-" * 42)                                                                                            
    for _, r in results.iterrows():                                                                                   
        lines.append(                                                                                                 
            f"{int(r['test_year']):<8} "                                                                              
            f"{r.get('win_brier', float('nan')):>8.4f} "
            f"{r.get('top5_brier', float('nan')):>8.4f} "                                                             
            f"{r.get('top10_brier', float('nan')):>8.4f} "                                                            
            f"{r.get('top20_brier', float('nan')):>8.4f}"
        )                                                                                                             
                                                        
    report = "\n".join(lines)                                                                                         
    out_txt = OUTPUTS_DIR / "timeseries_cv_report.txt"    
    out_txt.write_text(report)                                                                                        
    print(f"Saved → {out_txt.name}")
    print()                                                                                                           
    print(report)                                                                                                     

                                                                                                                    
if __name__ == "__main__":                                
    main()