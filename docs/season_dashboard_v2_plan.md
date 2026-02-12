# Season Dashboard V2 - Enhanced Strategy Planning

## Overview

Transform the season dashboard from "obvious picks" (top players at majors) to a **strategic planning tool** that finds real value through course history, form timing, and usage optimization.

---

## Current State

The dashboard currently:
- Shows tournament calendar with importance scores
- Recommends tournaments for players (but just picks majors for everyone)
- Shows top player allocation matrix

**Problem**: Everyone gets the same advice - "use Scottie at Masters". No differentiation, no course fit analysis, no usage tracking.

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEASON DASHBOARD V2                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Data Layer   │  │ Strategy     │  │ Views                │  │
│  │              │  │ Engine       │  │                      │  │
│  │ - Schedule   │  │              │  │ - Tournament Focus   │  │
│  │ - OWGR       │──│ - Scoring    │──│ - Player Planning    │  │
│  │ - Course Hist│  │ - Weighting  │  │ - Value Finder       │  │
│  │ - Predictions│  │ - Usage Adj  │  │ - Usage Tracker      │  │
│  │ - Usage Track│  │              │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Course History Foundation

**Goal**: Build a course history database that maps players to their performance at specific venues.

### Data Sources
- `betting_profiles_*.csv` - has `course_history` JSON column
- Historical tournament results (if available)

### Tasks

#### 1.1 Create Course History Aggregator
**File**: `scripts/planning/course_history.py`

```python
# You'll build this - here's the structure:

class CourseHistoryDB:
    """Aggregates course history across all betting profiles."""

    def __init__(self):
        self.history = {}  # {player_name: {course_name: stats}}

    def load_from_betting_profiles(self, profiles_dir: Path):
        """Scan all betting_profiles_*.csv and extract course_history."""
        pass

    def get_player_course_stats(self, player: str, course: str) -> dict:
        """Get a player's history at a specific course."""
        # Returns: {times_played, avg_finish, best_finish, wins, top5s, top10s}
        pass

    def get_course_specialists(self, course: str, min_plays: int = 2) -> List:
        """Find players who perform well at this course."""
        pass

    def calculate_course_fit_score(self, player: str, course: str) -> float:
        """0-100 score for how well player fits this course."""
        pass
```

**Learning opportunity**: Parse the JSON course_history column, aggregate across files.

#### 1.2 Map Tournaments to Courses
**File**: `data/reference/tournament_courses.json`

```json
{
  "Waste Management Phoenix Open": {
    "course": "TPC Scottsdale",
    "course_aliases": ["Scottsdale", "Phoenix"]
  },
  "The Masters": {
    "course": "Augusta National",
    "course_aliases": ["Augusta"]
  }
}
```

**Your task**: Create this mapping file for all 30 tournaments.

---

## Phase 2: Smart Scoring Engine

**Goal**: Replace simple "tournament importance" with weighted multi-factor scoring.

### Tasks

#### 2.1 Create Player-Tournament Scoring System
**File**: `scripts/planning/scoring_engine.py`

```python
@dataclass
class TournamentScore:
    player: str
    tournament: str

    # Component scores (0-100 each)
    tournament_importance: float  # Purse, prestige
    course_fit: float            # Historical performance at venue
    current_form: float          # Recent results, predictions
    field_strength: float        # Weaker field = easier path

    # Weights (should sum to 1.0)
    weights: dict = field(default_factory=lambda: {
        'importance': 0.25,
        'course_fit': 0.35,   # Course history weighted heavily!
        'form': 0.25,
        'field': 0.15
    })

    @property
    def total_score(self) -> float:
        return (
            self.tournament_importance * self.weights['importance'] +
            self.course_fit * self.weights['course_fit'] +
            self.current_form * self.weights['form'] +
            self.field_strength * self.weights['field']
        )

    @property
    def value_rating(self) -> str:
        """Human-readable rating."""
        if self.total_score >= 80: return "ELITE"
        if self.total_score >= 65: return "STRONG"
        if self.total_score >= 50: return "SOLID"
        return "FADE"
```

**Learning opportunity**: Understand how weighting affects recommendations.

#### 2.2 Integrate Predictions
Pull from `latest_predictions.csv`:
- `win_prob` - probability of winning
- `form_trend` - COLD/NEUTRAL/WARM/HOT
- `hot_hand_score` - momentum indicator
- `model_vs_vegas_edge` - value vs betting markets

---

## Phase 3: Usage Tracker

**Goal**: Track which players have been used and optimize remaining picks.

### Tasks

#### 3.1 Create Usage Persistence
**File**: `data/fantasy/usage_tracker_2026.json`

```json
{
  "season": "2026",
  "max_uses_per_player": 3,
  "picks": {
    "Scottie Scheffler": {
      "times_used": 2,
      "tournaments_used": [
        {"tournament": "The Masters", "week": 10, "result": "1st", "points": 150},
        {"tournament": "THE PLAYERS Championship", "week": 6, "result": "T3", "points": 85}
      ],
      "remaining_uses": 1
    },
    "Rory McIlroy": {
      "times_used": 1,
      "tournaments_used": [
        {"tournament": "AT&T Pebble Beach Pro-Am", "week": 2, "result": "T12", "points": 35}
      ],
      "remaining_uses": 2
    }
  },
  "weekly_lineups": {
    "week_1": {
      "tournament": "Waste Management Phoenix Open",
      "lineup": ["Player A", "Player B", "Player C", "Player D"],
      "points_earned": 245
    }
  }
}
```

#### 3.2 Usage Tracker Commands
```bash
# Record a pick
python scripts/planning/usage_tracker.py --add "Scottie Scheffler" --tournament "The Masters" --result "1st"

# Check remaining uses
python scripts/planning/usage_tracker.py --check "Scottie Scheffler"

# Show all usage
python scripts/planning/usage_tracker.py --summary
```

**Learning opportunity**: JSON file I/O, data persistence patterns.

---

## Phase 4: New Dashboard Views

### 4.1 Tournament-Centric View
**Command**: `--tournament "Waste Management Phoenix Open"`

```
================================================================================
  WHO TO USE AT: WASTE MANAGEMENT PHOENIX OPEN
  Date: 2026-02-05 | Course: TPC Scottsdale | Purse: $9.6M
================================================================================

  TOP RECOMMENDATIONS (by strategic score):

  #   Player                Score   Course Fit   Form    Edge    Uses Left
  -------------------------------------------------------------------------
  1   Hideki Matsuyama      87      ★★★★★ (2W)   HOT     +3.2%   3
      → Won here 2x, currently in form, 3 uses available

  2   Scottie Scheffler     82      ★★★☆☆        WARM    +1.8%   1 ⚠️
      → Elite player but only 1 use left - save for major?

  3   Justin Thomas         78      ★★★★☆ (T3)   NEUTRAL +0.5%   3
      → Strong course history, full uses available

  4   Sam Burns             74      ★★★★☆ (T5)   WARM    +2.1%   3
      → Good value pick, course specialist

  COURSE SPECIALISTS (rank 20+, strong course history):
  -------------------------------------------------------------------------
  - Harris English: 3 plays, avg finish 8.3, best T2 (2 uses left)
  - Joel Dahmen: 4 plays, avg finish 12.1, best T5 (3 uses left)

  AVOID:
  - Jon Rahm: No course history, cold form
  - Viktor Hovland: 2 plays, avg finish 45 (missed cuts)
```

### 4.2 Value Finder View
**Command**: `--value-picks` or `--sleepers`

```
================================================================================
  VALUE FINDER - UPCOMING TOURNAMENTS
================================================================================

  Players ranked 20-50 with strong course fits:

  WASTE MANAGEMENT PHOENIX OPEN (This Week):
  - Harris English (#28): Course fit 92/100, 2 wins here
  - Sam Burns (#24): Course fit 78/100, 2 top-5s

  AT&T PEBBLE BEACH (Next Week):
  - Nick Taylor (#45): Won here 2024, course fit 95/100
  - Matt Fitzpatrick (#22): Pebble specialist, course fit 85/100

  THE PLAYERS CHAMPIONSHIP (Week 6):
  - [Most top players - limited value plays]
```

### 4.3 Player Usage Optimizer
**Command**: `--optimize "Scottie Scheffler"` (when uses are limited)

```
================================================================================
  OPTIMIZE REMAINING USES: SCOTTIE SCHEFFLER
  Uses: 2/3 used | Remaining: 1
================================================================================

  Previously used at:
  - The Masters (Week 10): 1st place, 150 pts
  - THE PLAYERS (Week 6): T3, 85 pts

  BEST OPTIONS FOR FINAL USE:

  #   Tournament              Date        Score   Why
  -------------------------------------------------------------------------
  1   U.S. Open               Jun 18      94      Major, 2x winner, peak form timing
  2   PGA Championship        May 14      88      Major, no course history but elite
  3   Memorial Tournament     Jun 4       82      Signature, Jack's place, $20M

  NOT RECOMMENDED:
  - Standard events (waste of elite player)
  - Open Championship (travel, links uncertainty)
```

---

## Phase 5: Integration & Polish

### 5.1 Update Main Dashboard
Combine all views into cohesive experience:

```bash
# Full strategic dashboard
python scripts/planning/season_dashboard.py --strategy

# This week's picks with all context
python scripts/planning/season_dashboard.py --this-week

# Interactive mode (if we want to get fancy)
python scripts/planning/season_dashboard.py --interactive
```

### 5.2 Weekly Report Generator
Auto-generate a report combining:
- This week's tournament analysis
- Recommended picks with reasoning
- Usage status for key players
- Value plays to consider

---

## Implementation Order

| Phase | Task | Complexity | Who Codes |
|-------|------|------------|-----------|
| 1.1 | Course History DB | Medium | You (learn JSON parsing) |
| 1.2 | Tournament-Course Mapping | Easy | You (create JSON file) |
| 2.1 | Scoring Engine | Medium | Together |
| 2.2 | Predictions Integration | Easy | Claude |
| 3.1 | Usage JSON Structure | Easy | You |
| 3.2 | Usage Tracker Commands | Medium | Together |
| 4.1 | Tournament-Centric View | Medium | Together |
| 4.2 | Value Finder | Easy | Claude |
| 4.3 | Usage Optimizer | Medium | Together |
| 5.1 | Dashboard Integration | Easy | Claude |
| 5.2 | Weekly Report | Easy | Claude |

---

## Questions to Decide

1. **Weighting**: How much should course history matter vs tournament prestige?
   - Current thinking: 35% course fit, 25% importance, 25% form, 15% field

2. **Value threshold**: What OWGR rank defines "value players"?
   - Suggestion: 20-60 for "value", 60+ for "sleepers"

3. **Usage warnings**: When should we warn about using elite players at lesser events?
   - Suggestion: Warn if player rank < 10 and tournament importance < 7

4. **Historical data**: How far back should course history go?
   - Suggestion: 5 years, weighted toward recent

---

## Files to Create

```
scripts/planning/
├── season_dashboard.py      # (existing, will update)
├── season_planner.py        # (existing)
├── course_history.py        # NEW - Phase 1
├── scoring_engine.py        # NEW - Phase 2
└── usage_tracker.py         # NEW - Phase 3

data/
├── fantasy/
│   └── usage_tracker_2026.json   # NEW - Phase 3
└── reference/
    └── tournament_courses.json    # NEW - Phase 1
```

---

## Ready to Start?

I recommend starting with **Phase 1.2** (tournament-course mapping) as a warmup since it's just creating a JSON file, then moving to **Phase 1.1** (Course History DB) where you'll learn JSON parsing and aggregation patterns.

Which would you like to tackle first?
