# 2026 Fantasy Golf System Improvement Plan

**Created**: February 4, 2026
**Status**: Week 1 of Season (0 uses spent)
**Goal**: Improve prediction accuracy and usage strategy for "Let It Ride" league

---

## Executive Summary

Based on analysis of American Express and Farmers Insurance Open results:
- Model is **~2x overconfident** on top-5/top-10 probabilities
- **Course fit feature is not predictive** (r=-0.10, p>0.3)
- **Many high-ranked players missed cuts** (wasted potential picks)
- Winner identification is solid (Scheffler #1, Rose #3)
- Usage optimizer exists but needs calibrated inputs

### Key Constraint
**3 uses per player across 30 tournaments** - must optimize WHEN to use elite players, not just WHO will win.

---

## Season Schedule Overview

| Tier | Count | Examples | Strategy |
|------|-------|----------|----------|
| **Majors** | 5 | Masters, PGA, US Open, Open, Players | Save elite players |
| **Signatures** | 8 | Genesis, Arnold Palmer, Memorial | Good for elite if fit |
| **Playoffs** | 3 | FedEx St. Jude, BMW, Tour Champ | End-of-season picks |
| **Standard** | 13 | Phoenix, Valspar, Houston | Mid-tier players |
| **Team** | 1 | Zurich Classic | Skip or low priority |

**Upcoming High-Value Events**:
- Week 2: AT&T Pebble Beach ($3.6M winner)
- Week 3: Genesis Invitational ($4.0M winner)
- Week 5: Arnold Palmer Invitational ($4.0M winner)
- Week 6: THE PLAYERS ($4.5M winner)
- Week 10: The Masters ($4.2M winner)

---

## Improvement Tasks

### Phase 1: Calibration & Cut Risk (Critical - This Week)

#### Task 1.1: Apply Probability Calibration in Production
**Priority**: CRITICAL
**Effort**: 1-2 hours

**Problem**: Model predicts 15% top-10 when reality is ~8%

**Solution**: Apply existing calibration factors (0.50-0.51) to `predict_tournament.py` output

```python
# In predict_tournament.py, after generating raw predictions:
calibrated_top5 = raw_top5_prob * 0.51
calibrated_top10 = raw_top10_prob * 0.51
calibrated_top20 = raw_top20_prob * 0.62
```

**Acceptance Criteria**:
- [ ] Predictions show calibrated probabilities by default
- [ ] Raw probabilities still available for comparison
- [ ] EV calculations use calibrated probabilities

---

#### Task 1.2: Build Cut Probability Model
**Priority**: HIGH
**Effort**: 3-4 hours

**Problem**: Many top-ranked players missed cuts (Thorbjornsen, Matt Wallace, Kevin Yu at AMEX)

**Solution**: Train a separate model to predict cut probability

**Features for Cut Model**:
- Recent cut streak (last 5 tournaments)
- Course history cut rate
- SG total (players with negative SG miss more cuts)
- Field strength (stronger fields = more MCs)
- Recent form volatility (high std dev = higher MC risk)

**Output**: `cut_prob` column in predictions
- Flag players with >25% cut risk as "RISKY"
- Adjust usage recommendations: don't use elite players on risky picks

**Files to modify**:
- `train_final_models.py` - add cut model training
- `predict_tournament.py` - add cut predictions
- `usage_optimizer.py` - penalize high cut-risk players

---

#### Task 1.3: Remove or Downweight Course Fit
**Priority**: HIGH
**Effort**: 30 minutes

**Problem**: `dg_fit_total` has r=-0.10 with actual finish (not predictive)

**Options**:
1. **Remove entirely** from model features
2. **Downweight significantly** (multiply by 0.1)
3. **Replace** with simpler venue history features

**Recommendation**: Remove from scoring, keep only for informational display

**Files to modify**:
- `predict_tournament.py` - remove from EV calculation
- `usage_optimizer.py` - remove course fit scoring

---

### Phase 2: Usage Strategy Integration (Week 1-2)

#### Task 2.1: Integrate Calibrated EV into Usage Optimizer
**Priority**: HIGH
**Effort**: 2 hours

**Problem**: Usage optimizer uses raw (overconfident) probabilities

**Solution**:
1. Load calibration factors in `usage_optimizer.py`
2. Recalculate EV with calibrated probabilities
3. Compare "use now" EV vs "save for later" EV with proper calibration

**New Usage Score Formula**:
```python
calibrated_ev = calculate_ev(calibrated_probs, purse)
opportunity_cost = max(future_tournament_ev) - calibrated_ev
usage_score = calibrated_ev - (opportunity_cost * scarcity_multiplier)

# scarcity_multiplier increases as uses decrease:
# 3 uses left: 1.0
# 2 uses left: 1.5
# 1 use left: 2.5
```

---

#### Task 2.2: Elite Player Protection Rules
**Priority**: MEDIUM
**Effort**: 1 hour

**Problem**: Elite players (top 15 OWGR) should be saved for high-value events

**Rules to Implement**:
| Player Tier | Uses 3 | Uses 2 | Uses 1 |
|-------------|--------|--------|--------|
| Top 5 OWGR | Sig+ only | Major+ only | Major only |
| Top 15 OWGR | Standard OK | Sig+ only | Major+ only |
| Top 30 OWGR | Any | Standard OK | Sig+ only |
| Others | Any | Any | Standard OK |

**Implementation**: Add tier-based gates in `usage_optimizer.should_use_player()`

---

#### Task 2.3: Weekly Pick Selection with Usage Awareness
**Priority**: HIGH
**Effort**: 2 hours

**New Selection Logic**:
```
For each tournament:
1. Get calibrated predictions for field
2. Filter out high cut-risk players (>25%)
3. Calculate usage-adjusted EV for each player:
   - usage_adjusted_ev = calibrated_ev * usage_recommendation_score
4. Select top 3 by usage_adjusted_ev
5. Verify no elite player wasted on low-value event
```

**Output Enhancement**: Add to picks report:
- "Usage recommendation: USE / SAVE"
- "Uses remaining after this pick: X/3"
- "Better events coming: [list]"

---

### Phase 3: Better Recent Form Features (Week 2-3)

#### Task 3.1: Hot Hand / Momentum Detection
**Priority**: MEDIUM
**Effort**: 2-3 hours

**Problem**: Jason Day (2nd at AMEX) and Justin Rose (won Farmers) had hot recent form the model underweighted

**New Features**:
```python
def calculate_momentum(player_id, last_n=5):
    return {
        'consecutive_top10s': count_consecutive_top10(player_history),
        'consecutive_cuts': count_consecutive_cuts(player_history),
        'sg_trend': linear_regression_slope(sg_total_last_5),  # positive = improving
        'recent_wins': wins_in_last_10,
        'hot_hand_flag': True if consecutive_top10s >= 3 else False
    }
```

**Integration**: Add 10-15% EV boost for players with `hot_hand_flag=True`

---

#### Task 3.2: Cut Streak Feature
**Priority**: MEDIUM
**Effort**: 1 hour

**Feature**: `consecutive_cuts_made` - how many cuts in a row

**Usage**:
- Players with 10+ consecutive cuts = reliable
- Players with recent MC = higher risk flag

---

### Phase 4: Model Retraining (Week 3-4)

#### Task 4.1: Retrain with Balanced Classes
**Priority**: MEDIUM
**Effort**: 2-3 hours

**Already Done**: Added `class_weight='balanced_subsample'` - verify it's helping

**Additional Steps**:
1. Evaluate on 2025 holdout with new weights
2. Compare calibration pre/post
3. Document any AUC changes

---

#### Task 4.2: Add Dedicated Cut Model
**Priority**: HIGH (from Task 1.2)
**Effort**: Included in 1.2

Train separate binary classifier:
- Target: `made_cut` (1) vs `missed_cut` (0)
- Use last 3 years of data
- Features: recent form, field strength, venue history

---

#### Task 4.3: Consider Removing Course Fit from Model
**Priority**: MEDIUM
**Effort**: 2 hours

**Experiment**:
1. Retrain win/top5/top10 models WITHOUT course fit features
2. Compare AUC on validation set
3. If AUC same or better → remove permanently

---

### Phase 5: Season Tracking & Learning (Ongoing)

#### Task 5.1: Weekly Results Logging
**Priority**: HIGH
**Effort**: Ongoing (15 min/week)

After each tournament:
1. Run `prediction_tracker.py record` with actual results
2. Update `season_log.csv` with picks and outcomes
3. Run calibration report to track model drift

---

#### Task 5.2: Mid-Season Model Adjustment
**Priority**: LOW (revisit week 15)
**Effort**: 4 hours

At mid-season:
1. Analyze first 15 weeks of predictions vs actuals
2. Identify systematic biases
3. Adjust calibration factors if needed
4. Consider retraining with 2026 early-season data

---

## Implementation Priority Order

### This Week (Before WM Phoenix Open)
1. **[1.1]** Apply calibration factors in production
2. **[1.3]** Remove course fit from scoring
3. **[2.1]** Integrate calibrated EV into usage optimizer
4. **[5.1]** Set up weekly tracking process

### Next 2 Weeks
5. **[1.2]** Build cut probability model
6. **[2.2]** Elite player protection rules
7. **[2.3]** Usage-aware pick selection
8. **[3.1]** Hot hand detection

### Month 1
9. **[3.2]** Cut streak feature
10. **[4.1]** Verify balanced class training
11. **[4.3]** Experiment removing course fit from model

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Top-5 calibration error | +95% overconfident | <20% | Weekly calibration report |
| Top-10 calibration error | +96% overconfident | <20% | Weekly calibration report |
| Picks making top-20 | 1-3 of 6 (2 tournaments) | 3-4 of 6 | Season log |
| Missed cut picks | Unknown | <15% of picks | Track MCs in season log |
| Elite player efficiency | N/A | Use only on Sig+/Major | Usage tracker |

---

## Files to Modify

| File | Tasks | Changes |
|------|-------|---------|
| `predict_tournament.py` | 1.1, 1.2, 1.3 | Add calibration, cut model, remove course fit |
| `usage_optimizer.py` | 1.3, 2.1, 2.2 | Calibrated EV, elite protection, remove course fit |
| `train_final_models.py` | 1.2, 4.1, 4.3 | Cut model, balanced verification, course fit removal |
| `recent_form.py` | 3.1, 3.2 | Momentum features, cut streak |
| `prediction_tracker.py` | 5.1 | Enhanced weekly tracking |

---

## Weekly Workflow (Updated)

### Pre-Tournament (Wednesday/Thursday)
1. Fetch tournament field
2. Run `predict_tournament.py` with calibration
3. Review cut risk flags
4. Check usage recommendations for top picks
5. **Verify no elite player wasted on low-value event**
6. Submit picks

### Post-Tournament (Monday)
1. Record actual results
2. Update usage tracker
3. Run calibration comparison
4. Update season log
5. Note any model learnings

---

## Questions to Resolve

1. **Cut risk threshold**: 25% seems reasonable - adjust based on results?
2. **Elite player definition**: Top 15 OWGR? Top 20? Adjust dynamically?
3. **Calibration update frequency**: Weekly? After 5 tournaments?
4. **Vegas odds integration**: Currently have ensemble - use more heavily?

---

## Notes

- WM Phoenix Open is Week 1 (Standard event, $1.7M winner share)
- Pebble Beach (Week 2) is Signature ($3.6M) - consider saving elite picks
- Genesis (Week 3) is Signature ($4.0M) - strong event for elite players
- First Major is Players Championship (Week 6) - save at least 1 use for top players

---

*Plan created: February 4, 2026*
*Next review: After WM Phoenix Open results*
