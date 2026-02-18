# Predictions Data Dictionary

Generated: 2026-02-17 21:30

| Column | Description |
|--------|-------------|
| player_id | PGA Tour player ID (primary key) |
| player_name | Player name |
| sg_total | Recent SG:Total (form window) |
| sg_ott | Recent SG:Off-the-Tee |
| sg_app | Recent SG:Approach |
| sg_arg | Recent SG:Around-the-Green |
| sg_putt | Recent SG:Putting |
| sg_t2g | Recent SG:Tee-to-Green |
| season_sg_total | Season-to-date SG:Total average |
| season_sg_ott | Season SG:Off-the-Tee average |
| season_sg_app | Season SG:Approach average |
| season_sg_putt | Season SG:Putting average |
| season_sg_t2g | Season SG:Tee-to-Green average |
| season_sg_arg | Season SG:Around-the-Green average |
| sg_blend_current_weight | No description available |
| sg_blend_prior_weight | No description available |
| sg_blend_tournaments | No description available |
| hist_times_played | Number of starts at this course |
| hist_avg_finish | Average finish at this course |
| hist_best_finish | Best finish at this course |
| hist_wins | Wins at this course |
| hist_top5s | Top-5s at this course |
| hist_top10s | Top-10s at this course |
| hist_cut_rate | Cut-made rate at this course (0-1) |
| hist_missed_cuts | Missed cuts at this course |
| has_won_here | 1/0 flag: has won at this course |
| has_course_history | 1/0 flag: has course history |
| has_made_cut_here | 1/0 flag: has made a cut here |
| venue_avg_finish | Venue average finish baseline (field-level) |
| venue_finish_std | Venue finish standard deviation (volatility) |
| wins_at_venue | No description available |
| world_rank | Current world rank (lower is better) |
| field_avg_rank | Average world rank of the field |
| field_median_rank | Median world rank of the field |
| form_trend | SG:Total trend over recent events (positive = improving) |
| finish_consistency | Normalized finish volatility (lower = steadier) |
| recent_top10s | Recency-weighted top-10 count over last N events |
| recent_top5s | Top-5s over last N events |
| recent_wins | Wins over last N events |
| recent_cuts_made | Cuts made over last N events |
| recent_cuts_pct | Cut-made % over last N events (0-1) |
| consecutive_top10s | No description available |
| consecutive_cuts | No description available |
| hot_hand_flag | No description available |
| hot_hand_score | No description available |
| momentum_trend | No description available |
| recent_birdie_avg | Recency-weighted birdies per round |
| recent_bogey_avg | Recency-weighted bogeys per round |
| recent_scoring_avg | Recency-weighted scoring average |
| recent_gir_pct | Recency-weighted GIR% |
| recent_scrambling | Recency-weighted scrambling% |
| recent_bounce_back | Recency-weighted bounce-back% |
| recent_final_round | Recency-weighted final-round scoring |
| recent_sand_save | Recency-weighted sand save% |
| dg_fit_ott | Course-fit component: Off-the-Tee |
| dg_fit_app | Course-fit component: Approach |
| dg_fit_arg | Course-fit component: Around-the-Green |
| dg_fit_putt | Course-fit component: Putting |
| dg_fit_total | Total course-fit score (sum of components) |
| win_prob | Predicted win probability (0-1) |
| top5_prob | Predicted top-5 probability (0-1) |
| top10_prob | Predicted top-10 probability (0-1) |
| top20_prob_raw | No description available |
| top20_prob | No description available |
| win_prob_calibrated | No description available |
| top5_prob_calibrated | No description available |
| top10_prob_calibrated | No description available |
| top20_prob_calibrated | No description available |
| win_prob_raw | No description available |
| top5_prob_raw | No description available |
| top10_prob_raw | No description available |
| cut_prob | Probability of making the cut (0-1, higher = safer) |
| cut_risk | Cut risk category: LOW (>85%), MEDIUM (65-85%), ELEVATED (45-65%), HIGH (<45%) |
| miss_cut_prob | Probability of missing the cut (1 - cut_prob) |
| expected_value | Expected earnings value based on purse + probabilities (USD) |
| vegas_prob | No description available |
| odds_to_win | No description available |
| odds_numeric | No description available |
| odds_rank | No description available |
| ensemble_win_prob | No description available |
| ensemble_win_prob_normalized | No description available |
| model_vs_vegas_edge | No description available |
| is_value_bet | No description available |
| odds_drift_flag | No description available |
| odds_drift_level | No description available |