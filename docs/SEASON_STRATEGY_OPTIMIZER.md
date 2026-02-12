# Season Strategy Optimizer - 3 Uses Per Player Rule

## The Challenge

**Rule**: Each player can only be used **3 times per season**

**Implication**: You can't just pick Scottie Scheffler every week!

**Strategy**: Must allocate your 3 uses of elite players to **maximize season-long EV**

---

## Tournament Types & Purses

### 2026 PGA Tour Season Structure

**Signature Events** (~8 events, $20M purse):
- Genesis Invitational
- Arnold Palmer Invitational
- RBC Heritage
- Wells Fargo Championship
- Memorial Tournament
- Travelers Championship
- BMW Championship

**Majors** (4 events, $18-20M):
- Masters
- PGA Championship
- U.S. Open
- The Open Championship

**Playoffs** (3 events, $20M+):
- FedEx St. Jude Championship
- BMW Championship
- Tour Championship

**Standard Events** (~30 events, $8-9.6M):
- American Express
- Farmers Insurance Open
- AT&T Pebble Beach
- ... most other tournaments

---

## Strategic Considerations

### When to Use Elite Players (Scheffler, Rahm, McIlroy, etc.)

**Option 1: Save for Biggest Events**
- Use Scheffler at: Masters, U.S. Open, Tour Championship
- Pros: Maximum prize pool, highest EV potential
- Cons: May miss easy wins at weaker-field events

**Option 2: Use at Weakest Fields**
- Use Scheffler at: Opposite-field events when stars skip
- Pros: Higher win probability, less competition
- Cons: Lower EV due to smaller purse

**Option 3: Use at Course Fits**
- Use Scheffler at: Tournaments where he has elite course history
- Pros: Highest win probability at specific venues
- Cons: May not align with biggest purses

**Option 4: Optimize EV**
- Use Scheffler when: `(Win% × Purse × Multiplier)` is maximized
- Pros: Mathematically optimal
- Cons: Ignores variance and competition

---

## Season Optimizer Algorithm

### Step 1: Forecast All Tournaments

For each player, predict:
- Win probability at each tournament
- Expected value at each tournament
- Likelihood of making top-20 (fantasy points)

**Example for Scottie Scheffler**:

```python
tournaments = {
    'American Express': {'win_prob': 0.35, 'purse': 9600000, 'field_strength': 6},
    'Farmers Insurance': {'win_prob': 0.28, 'purse': 9300000, 'field_strength': 7},
    'Genesis Invitational': {'win_prob': 0.25, 'purse': 20000000, 'field_strength': 9},
    'Arnold Palmer': {'win_prob': 0.22, 'purse': 20000000, 'field_strength': 9},
    'Masters': {'win_prob': 0.18, 'purse': 18000000, 'field_strength': 10},
    # ... all 40 tournaments
}
```

### Step 2: Calculate Marginal Value

**Marginal Value** = EV(using Scheffler) - EV(next best available player)

```python
# Tournament: Genesis Invitational ($20M)
scheffler_ev = 0.25 * 20000000 * 0.20  # 25% win, 20% prize
next_best_ev = 0.08 * 20000000 * 0.20  # Next best: 8% win

marginal_value = scheffler_ev - next_best_ev
# = $1M - $320K = $680K marginal gain
```

### Step 3: Optimize Allocation

Use **Integer Linear Programming** to maximize total season EV:

```python
# Maximize: Sum of (EV_player_tournament × used_player_tournament)
# Subject to:
#   - Each player used ≤ 3 times
#   - Each tournament picks exactly 3 players
#   - used_player_tournament ∈ {0, 1}
```

### Step 4: Adjust for Risk

**Conservative**: Favor tournaments where you need Scheffler less
**Aggressive**: Save elite players for majors/playoffs

---

## Implementation Plan

### Phase 1: Season Schedule & Forecasting (3-4 hours)

**File**: `scripts/planning/forecast_season.py`

**Features**:
- Load 2026 PGA Tour schedule
- For each tournament:
  - Predict likely field strength
  - Estimate purse
  - Forecast each player's win probability
- Output: `season_forecast_2026.csv`

**Example Output**:
```csv
week,tournament,purse,field_strength,player_name,win_prob,top10_prob,ev
1,Sony Open,8300000,7,Scheffler,0.32,0.75,486000
1,Sony Open,8300000,7,Rahm,0.18,0.65,312000
2,American Express,9600000,6,Scheffler,0.35,0.78,524000
```

---

### Phase 2: Optimal Allocation Optimizer (4-6 hours)

**File**: `scripts/planning/optimize_player_allocation.py`

**Algorithm**:
```python
from scipy.optimize import linprog
import pulp

def optimize_season_allocation(forecast_df, league_rules):
    """
    Optimize which players to use when

    Args:
        forecast_df: Predictions for all players × all tournaments
        league_rules: Dict with constraints (uses_per_player=3, picks_per_week=3)

    Returns:
        Optimal allocation plan
    """

    # Create optimization problem
    prob = pulp.LpProblem("Season_Allocation", pulp.LpMaximize)

    # Decision variables: use_player_tournament[player][week] ∈ {0,1}
    uses = {}
    for player in players:
        for week in weeks:
            uses[(player, week)] = pulp.LpVariable(
                f"use_{player}_{week}",
                cat='Binary'
            )

    # Objective: Maximize total expected value
    prob += pulp.lpSum([
        forecast_df.loc[player, week]['ev'] * uses[(player, week)]
        for player in players
        for week in weeks
    ])

    # Constraint 1: Each player used ≤ 3 times
    for player in players:
        prob += pulp.lpSum([uses[(player, week)] for week in weeks]) <= 3

    # Constraint 2: Pick exactly 3 players per week
    for week in weeks:
        prob += pulp.lpSum([uses[(player, week)] for player in players]) == 3

    # Solve
    prob.solve()

    # Extract solution
    allocation = []
    for player in players:
        for week in weeks:
            if uses[(player, week)].varValue == 1:
                allocation.append({
                    'week': week,
                    'player': player,
                    'ev': forecast_df.loc[player, week]['ev']
                })

    return pd.DataFrame(allocation)
```

---

### Phase 3: Weekly Allocation Tool (2-3 hours)

**File**: `scripts/planning/weekly_allocation_advisor.py`

**Features**:
- Show optimal picks for this week
- Show remaining uses for each player
- Suggest when to use elite players
- Calculate opportunity cost of using player now vs later

**Example Output**:
```
WEEK 2: American Express

RECOMMENDED PICKS:
1. Scottie Scheffler (2/3 uses remaining)
   - EV: $524K
   - Marginal value: $280K over next best
   - ⚠️ Alternative: Save for Genesis (+$156K EV)

2. Ben Griffin (3/3 uses remaining)
   - EV: $295K
   - Good course history, use now

3. Michael Brennan (3/3 uses remaining)
   - EV: $333K
   - Strong recent form, use now

ELITE PLAYERS STATUS:
Scheffler: 1/3 used (Sony Open)
  → Optimal remaining: Genesis, Masters
Rahm: 0/3 used
  → Optimal: Genesis, Arnold Palmer, Masters
McIlroy: 0/3 used
  → Optimal: Bay Hill, Memorial, U.S. Open
```

---

## Strategic Frameworks

### Framework 1: "Big Fish, Small Pond"

**Strategy**: Use elite players at **weaker field events** where they dominate

**Logic**:
- Scheffler at American Express: 35% win (weak field)
- Scheffler at Masters: 18% win (strongest field)

**When to use**:
- Early season (before injury risk)
- Opposite-field weeks
- Course fit tournaments

**Pros**: Higher win probability
**Cons**: Lower EV due to smaller purse

---

### Framework 2: "Save for Majors"

**Strategy**: Use elite players only at **Majors + Playoffs**

**Logic**:
- Majors: $18-20M purse, maximum prestige
- Playoffs: $20M+, season on the line
- 7 total events = use elite players 2-3x each

**When to use**:
- Conservative leagues
- When you have depth

**Pros**: Maximum EV potential
**Cons**: May miss easy wins at weaker events

---

### Framework 3: "Course History Advantage"

**Strategy**: Use elite players where they have **elite course history**

**Examples**:
- Scheffler at Augusta (Masters) - elite history
- Rahm at Torrey Pines (Farmers) - elite history
- DJ at Pebble Beach - dominant history

**Logic**: Course fit > field strength sometimes

**Pros**: Highest win probability at specific venues
**Cons**: May not align with purse size

---

### Framework 4: "Mathematical Optimal" (Recommended)

**Strategy**: Use **optimizer algorithm** to maximize total season EV

**Process**:
1. Forecast all tournaments
2. Calculate marginal value
3. Solve optimization problem
4. Adjust for variance/risk

**Pros**: Mathematically proven best
**Cons**: Requires accurate forecasts

---

## Player Tiers & Allocation

### Tier 1: Elite (Use Wisely - 3x only)
**Players**: Scheffler, Rahm, McIlroy, Schauffele, Hovland

**Strategy**:
- Save for Signatures/Majors/Playoffs
- Use at dominant course fits
- Avoid opposite-field weeks (they'll skip anyway)

**Expected value per use**: $500K-900K

---

### Tier 2: Strong (Strategic 3x)
**Players**: Cantlay, Thomas, Spieth, Morikawa, Finau

**Strategy**:
- Use at Signatures or course fits
- Mix of majors and regular events
- Consider field strength

**Expected value per use**: $300K-500K

---

### Tier 3: Solid (Flexible 3x)
**Players**: Homa, Day, Clark, Burns, English

**Strategy**:
- Use at course fits
- Target weaker field events
- Fill gaps when elites are saved

**Expected value per use**: $200K-350K

---

### Tier 4: Value Plays (Use Freely)
**Players**: Griffin, Jaeger, Mouw, Brennan

**Strategy**:
- Use anytime they have high EV
- Course history + recent form plays
- No need to save (less scarce)

**Expected value per use**: $150K-300K

---

## Weekly Decision Framework

### Questions to Ask Each Week

**1. Is this a premium tournament?**
- Major? → Strong yes for elite players
- Signature ($20M)? → Yes for elite players
- Playoff? → Strong yes for elite players
- Standard? → Save elites unless...

**2. Does an elite player have dominant course fit?**
- Scheffler at Augusta? → Use
- Rahm at Torrey Pines? → Consider
- No clear fit? → Save

**3. What's the field strength?**
- Opposite-field week (many stars skip)? → Use elites
- Strongest field? → Save unless major
- Average field? → Depends on other factors

**4. How many uses remaining?**
- 3/3 left, Week 5? → Can use one elite
- 1/3 left, Week 25? → SAVE for playoff/major
- 0/3 left? → Use different player

**5. What's the opportunity cost?**
```
EV(use Scheffler now) - EV(use next best)
vs
EV(use Scheffler at best remaining tournament) - EV(next best there)

If NOW > LATER → Use now
If LATER > NOW → Save
```

---

## Example Season Plan

### Scottie Scheffler 3-Use Allocation

**Option A: Maximize EV**
1. **Genesis Invitational** - $20M, strong field, course fit
2. **Masters** - $18M, major, elite course history
3. **Tour Championship** - $75M (!), season finale

**Expected total**: $2.8M EV

---

**Option B: Maximize Win Probability**
1. **American Express** - 35% win (weak field)
2. **Sony Open** - 32% win (weak field)
3. **Pebble Beach** - 30% win (course fit)

**Expected total**: $1.9M EV, but higher win probability

---

**Option C: Balanced**
1. **Genesis Invitational** - $20M signature
2. **Masters** - Major
3. **American Express** - Weak field, high win%

**Expected total**: $2.4M EV, good balance

---

## Tools to Build

### 1. Season Forecast Generator
```bash
python scripts/planning/forecast_season.py --year 2026
# Output: season_forecast_2026.csv
```

### 2. Optimal Allocation Solver
```bash
python scripts/planning/optimize_allocation.py \
    --forecast season_forecast_2026.csv \
    --strategy maximize_ev
# Output: optimal_allocation_2026.csv
```

### 3. Weekly Advisor
```bash
python scripts/planning/weekly_advisor.py \
    --week 2 \
    --allocation optimal_allocation_2026.csv
# Shows: Who to pick this week, who to save
```

### 4. Add to Dashboard
New page: **"📅 Season Planner"**
- View optimal allocation
- Track uses remaining
- See opportunity cost
- Adjust strategy

---

## Implementation Priority

### Phase 1: Basic Tracking (1-2 hours) ⭐ START HERE
**File**: `outputs/player_usage_tracker.csv`

```csv
player_name,uses_remaining,weeks_used,optimal_weeks_remaining
Scottie Scheffler,2,"[1,5]","[15,20,38]"
Jon Rahm,3,"[]","[8,15,30]"
```

**Tool**: Simple tracker
```bash
python scripts/planning/track_usage.py --player "Scheffler" --week 2
# Updates tracker after each week
```

---

### Phase 2: Season Forecast (3-4 hours)
- Build tournament schedule database
- Estimate field strength
- Forecast win probabilities
- Calculate expected values

---

### Phase 3: Optimizer (4-6 hours)
- Integer linear programming
- Maximize season-long EV
- Output optimal allocation
- Sensitivity analysis

---

### Phase 4: Weekly Advisor (2-3 hours)
- Compare current week to plan
- Show opportunity cost
- Recommend adjustments
- Track actual vs plan

---

## Key Insights

### 1. Don't Use All Elites Early
❌ **Bad**: Use Scheffler, Rahm, McIlroy in weeks 1-3
✅ **Good**: Save 1-2 uses of each for majors/playoffs

### 2. Consider Field Strength
**Weak field week** (opposite-field event):
- Scheffler might have 35% win chance
- High value even at smaller purse

**Strong field week** (major):
- Scheffler might have 18% win chance
- Still high EV due to huge purse

### 3. Use Value Plays Liberally
Players like Griffin, Brennan, Jaeger:
- Less scarce (won't make ALL events)
- Use whenever EV is high
- No need to optimize allocation

### 4. Track Throughout Season
After each week:
- Update uses remaining
- Recalculate optimal allocation
- Adjust based on form/injuries

---

## Next Steps

**Want me to build**:

1. **Player Usage Tracker** (1 hour) - Simple CSV + script
2. **Season Forecast Tool** (3 hours) - Predict all tournaments
3. **Allocation Optimizer** (5 hours) - Mathematical optimal plan
4. **Weekly Advisor** (2 hours) - Decision support tool
5. **Dashboard Integration** (2 hours) - Add season planner page

**Which should we start with?** I recommend starting with #1 (Usage Tracker) since American Express is this week and you'll want to track Scheffler usage!

---

*Created: January 19, 2026*
*Status: Strategy Framework*
*Next: Build player usage tracker*