# Predictions Data Dictionary

Generated: 2026-03-31 19:34

| Column | Description |
|--------|-------------|
| tournament_id | No description available |
| player_id | PGA Tour player ID (primary key) |
| player_name | Player name |
| sg_total | Recent SG:Total (form window) |
| sg_ott | Recent SG:Off-the-Tee |
| sg_app | Recent SG:Approach |
| sg_putt | Recent SG:Putting |
| sg_t2g | Recent SG:Tee-to-Green |
| season_sg_total | Season-to-date SG:Total average |
| season_sg_ott | Season SG:Off-the-Tee average |
| season_sg_app | Season SG:Approach average |
| season_sg_putt | Season SG:Putting average |
| season_sg_t2g | Season SG:Tee-to-Green average |
| sg_arg | Recent SG:Around-the-Green |
| season_sg_arg | Season SG:Around-the-Green average |
| recent_sg_weighted | No description available |
| recent_sg_trend | No description available |
| recent_sg_ott_weighted | No description available |
| recent_sg_app_weighted | No description available |
| recent_sg_putt_weighted | No description available |
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
| world_rank_log | No description available |
| field_avg_rank | Average world rank of the field |
| field_median_rank | Median world rank of the field |
| season_sg_ott_vs_field | No description available |
| field_avg_season_sg_ott | No description available |
| season_sg_app_vs_field | No description available |
| field_avg_season_sg_app | No description available |
| season_sg_arg_vs_field | No description available |
| field_avg_season_sg_arg | No description available |
| season_sg_putt_vs_field | No description available |
| field_avg_season_sg_putt | No description available |
| season_sg_total_vs_field | No description available |
| field_avg_season_sg_total | No description available |
| season_sg_ott_field_pct | No description available |
| season_sg_ott_field_rank | No description available |
| season_sg_app_field_pct | No description available |
| season_sg_app_field_rank | No description available |
| season_sg_arg_field_pct | No description available |
| season_sg_arg_field_rank | No description available |
| season_sg_putt_field_pct | No description available |
| season_sg_putt_field_rank | No description available |
| driving_dist_val | No description available |
| driving_acc_val | No description available |
| gir_pct_val | No description available |
| putts_per_round_val | No description available |
| sand_save_val | No description available |
| one_putt_pct_val | No description available |
| scrambling_val | No description available |
| par4_scoring_val | No description available |
| par5_scoring_val | No description available |
| birdie_avg_val | No description available |
| par3_scoring_val | No description available |
| bogey_avoid_val | No description available |
| driving_dist_field_avg | No description available |
| driving_dist_field_rank | No description available |
| driving_dist_field_pct | No description available |
| driving_acc_field_avg | No description available |
| driving_acc_field_rank | No description available |
| driving_acc_field_pct | No description available |
| gir_pct_field_avg | No description available |
| gir_pct_field_rank | No description available |
| gir_pct_field_pct | No description available |
| one_putt_pct_field_avg | No description available |
| one_putt_pct_field_rank | No description available |
| one_putt_pct_field_pct | No description available |
| scrambling_field_avg | No description available |
| scrambling_field_rank | No description available |
| scrambling_field_pct | No description available |
| putts_per_round_field_avg | No description available |
| putts_per_round_field_rank | No description available |
| putts_per_round_field_pct | No description available |
| sand_save_field_avg | No description available |
| sand_save_field_rank | No description available |
| sand_save_field_pct | No description available |
| bogey_avoid_field_avg | No description available |
| bogey_avoid_field_rank | No description available |
| bogey_avoid_field_pct | No description available |
| birdie_avg_field_avg | No description available |
| birdie_avg_field_rank | No description available |
| birdie_avg_field_pct | No description available |
| par3_scoring_field_avg | No description available |
| par3_scoring_field_rank | No description available |
| par3_scoring_field_pct | No description available |
| par4_scoring_field_avg | No description available |
| par4_scoring_field_rank | No description available |
| par4_scoring_field_pct | No description available |
| par5_scoring_field_avg | No description available |
| par5_scoring_field_rank | No description available |
| par5_scoring_field_pct | No description available |
| recent_r1_avg | No description available |
| recent_r2_avg | No description available |
| recent_r3_avg | No description available |
| recent_r4_avg | No description available |
| closing_delta | No description available |
| recent_r1_avg_field_pct | No description available |
| recent_r1_avg_vs_field | No description available |
| recent_r2_avg_field_pct | No description available |
| recent_r2_avg_vs_field | No description available |
| recent_r3_avg_field_pct | No description available |
| recent_r3_avg_vs_field | No description available |
| recent_r4_avg_field_pct | No description available |
| recent_r4_avg_vs_field | No description available |
| closing_delta_field_pct | No description available |
| closing_delta_vs_field | No description available |
| form_trend | SG:Total trend over recent events (positive = improving) |
| finish_consistency | Normalized finish volatility (lower = steadier) |
| recent_top10s | Recency-weighted top-10 count over last N events |
| recent_top5s | Top-5s over last N events |
| recent_wins | Wins over last N events |
| recent_cuts_made | Cuts made over last N events |
| recent_cuts_pct | Cut-made % over last N events (0-1) |
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
| predictive_sg_weighted | No description available |
| dg_fit_total | Total course-fit score (sum of components) |
| field_avg_predictive_sg_weighted | No description available |
| predictive_sg_weighted_vs_field | No description available |
| course_starts | No description available |
| course_made_cut_rate | No description available |
| course_top_10_rate | No description available |
| course_top_20_rate | No description available |
| course_win_rate | No description available |
| course_avg_finish | No description available |
| course_best_finish | No description available |
| course_avg_to_par | No description available |
| course_avg_earnings | No description available |
| course_last_season | No description available |
| course_sg_total_avg | Historical average SG:Total at this specific course |
| course_sg_ott_avg | Historical average SG:Off-the-Tee at this specific course |
| course_sg_app_avg | Historical average SG:Approach at this specific course |
| course_sg_putt_avg | Historical average SG:Putting at this specific course |
| course_sg_t2g_avg | No description available |
| course_sg_total_weighted | Recency-weighted SG:Total at this specific course |
| course_sg_ott_weighted | Recency-weighted SG:Off-the-Tee at this course |
| course_sg_app_weighted | Recency-weighted SG:Approach at this course |
| course_sg_putt_weighted | Recency-weighted SG:Putting at this course |
| course_sg_t2g_weighted | Recency-weighted SG:Tee-to-Green at this course |
| course_sg_trend | Trend in SG:Total at this course over time (positive = improving year-over-year) |
| course_sg_recent_vs_early | Difference between recent and early SG at this course (positive = recent improvement) |
| course_sg_total_vs_avg | Course SG edge: how much better/worse at this course vs overall (positive = course specialist) |
| course_sg_ott_vs_avg | OTT edge at this course vs overall average |
| course_sg_app_vs_avg | Approach edge at this course vs overall average |
| course_sg_putt_vs_avg | Putting edge at this course vs overall average |
| course_sg_t2g_vs_avg | Tee-to-Green edge at this course vs overall average |
| overall_sg_total_avg | Player's career-average SG:Total across all courses |
| course_stat_101_driving_distance_weighted | No description available |
| course_stat_102_driving_accuracy_weighted | No description available |
| course_stat_103_gir_percentage_weighted | No description available |
| course_stat_104_putts_per_round_weighted | No description available |
| course_stat_108_birdie_or_better_weighted | No description available |
| course_stat_111_sand_save_percentage_weighted | No description available |
| course_stat_119_1_putt_percentage_weighted | No description available |
| course_stat_120_scoring_average_weighted | No description available |
| course_stat_130_scrambling_weighted | No description available |
| course_stat_142_par_4_scoring_weighted | No description available |
| has_similar_course_data | No description available |
| similar_course_sg_estimate | No description available |
| course_sg_starts | Number of prior starts with usable SG history at this course |
| course_sg_vs_avg | No description available |
| course_history_confidence | Reliability score for course history signal (0-1; higher = more starts/history) |
| has_course_form_history | No description available |
| has_course_sg_history | Boolean flag: player has SG history at this course |
| course_experience_tier | No description available |
| course_perf_score | No description available |
| is_defending_champion | No description available |
| first_start_of_season | No description available |
| last_start_position | No description available |
| post_top5_last_start | No description available |
| missed_cut_last_start | No description available |
| consecutive_top10s | No description available |
| pre_major_flag | No description available |
| sg_event_count | No description available |
| recent_par3_scoring_field_pct | No description available |
| recent_par4_scoring_field_pct | No description available |
| recent_par5_scoring_field_pct | No description available |
| win_prob | Predicted win probability (0-1) |
| top5_prob | Predicted top-5 probability (0-1) |
| top10_prob | Predicted top-10 probability (0-1) |
| projected_score | Regression model: predicted 4-round to-par total (e.g. -12.5) |
| projected_score_vs_field | No description available |
| score_rank | Field rank by projected_score (1 = best/lowest projected score) |
| proj_ceiling | No description available |
| proj_median | No description available |
| proj_floor | No description available |
| top20_prob_raw | No description available |
| top20_prob | No description available |
| win_prob_calibrated | No description available |
| top5_prob_calibrated | No description available |
| top10_prob_calibrated | No description available |
| top20_prob_calibrated | No description available |
| win_prob_raw | No description available |
| top5_prob_raw | No description available |
| top10_prob_raw | No description available |
| boom_bust_score | No description available |
| finish_std | No description available |
| low_variance | No description available |
| cut_miss_rate | No description available |
| course_adjustment | Post-model probability adjustment from course history/similar-course signals |
| course_adjustment_confidence | Confidence applied to course adjustment (0-1) |
| win_prob_pre_course_adj | No description available |
| top5_prob_pre_course_adj | No description available |
| top10_prob_pre_course_adj | No description available |
| top20_prob_pre_course_adj | No description available |
| kft_adjustment | No description available |
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
| expert_pct | No description available |
| dfs_ownership_proj | No description available |