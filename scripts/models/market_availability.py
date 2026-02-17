#!/usr/bin/env python3
"""
Market Availability Layer
=========================

Tracks which betting markets are available from each sportsbook,
with timestamps, staleness detection, and diff alerts.

Markets tracked:
- winner: Tournament winner odds
- h2h: Head-to-head matchups
- round_score: Round score over/unders
- birdies: Birdie props
- top5, top10, top20: Position finish props

Books tracked:
- DRAFTKINGS
- FANDUEL (via PGA Tour)
- MODEL (internal predictions)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import json

PROJECT_ROOT = Path(__file__).parent.parent.parent
ODDS_DIR = PROJECT_ROOT / "data" / "odds"
SNAPSHOT_DIR = ODDS_DIR / "snapshots"
AVAILABILITY_FILE = ODDS_DIR / "market_availability.json"


def _json_serializable(obj):
    """Convert numpy/pandas types to JSON-serializable Python types."""
    import numpy as np
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj


class MarketType(str, Enum):
    WINNER = "winner"
    H2H = "h2h"
    ROUND_SCORE = "round_score"
    BIRDIES = "birdies"
    TOP5 = "top5"
    TOP10 = "top10"
    TOP20 = "top20"
    MAKE_CUT = "make_cut"


class DataSource(str, Enum):
    DRAFTKINGS = "DRAFTKINGS"
    FANDUEL = "FANDUEL"
    MODEL = "MODEL"


class Staleness(str, Enum):
    FRESH = "fresh"        # < 5 minutes
    RECENT = "recent"      # 5-30 minutes
    STALE = "stale"        # 30-60 minutes
    EXPIRED = "expired"    # > 60 minutes


@dataclass
class MarketStatus:
    """Status of a single market from a single source."""
    market: MarketType
    source: DataSource
    available: bool
    player_count: int = 0
    last_updated: Optional[datetime] = None
    staleness: Staleness = Staleness.EXPIRED

    def to_dict(self) -> Dict:
        return {
            "market": self.market.value,
            "source": self.source.value,
            "available": bool(self.available),
            "player_count": int(self.player_count),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "staleness": self.staleness.value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MarketStatus":
        last_updated = None
        if data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            market=MarketType(data["market"]),
            source=DataSource(data["source"]),
            available=data.get("available", False),
            player_count=data.get("player_count", 0),
            last_updated=last_updated,
            staleness=Staleness(data.get("staleness", "expired")),
        )


@dataclass
class MarketAvailability:
    """Aggregated market availability across all sources."""
    tournament_id: str
    markets: Dict[str, Dict[str, MarketStatus]] = field(default_factory=dict)
    last_scan: Optional[datetime] = None
    alerts: List[Dict] = field(default_factory=list)

    def get_status(self, market: MarketType, source: DataSource) -> Optional[MarketStatus]:
        """Get status for a specific market/source combo."""
        market_key = market.value
        source_key = source.value
        return self.markets.get(market_key, {}).get(source_key)

    def set_status(self, status: MarketStatus):
        """Update status for a market/source."""
        market_key = status.market.value
        source_key = status.source.value

        if market_key not in self.markets:
            self.markets[market_key] = {}

        # Check for changes to generate alerts
        old_status = self.markets[market_key].get(source_key)
        if old_status:
            if old_status.available and not status.available:
                self.alerts.append({
                    "type": "market_removed",
                    "market": market_key,
                    "source": source_key,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            elif not old_status.available and status.available:
                self.alerts.append({
                    "type": "market_added",
                    "market": market_key,
                    "source": source_key,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        self.markets[market_key][source_key] = status
        self.last_scan = datetime.now(timezone.utc)

    def get_available_sources(self, market: MarketType) -> List[DataSource]:
        """Get all sources that have this market available."""
        market_key = market.value
        sources = []
        for source_key, status in self.markets.get(market_key, {}).items():
            if status.available and status.staleness != Staleness.EXPIRED:
                sources.append(DataSource(source_key))
        return sources

    def get_best_source(self, market: MarketType) -> Optional[DataSource]:
        """Get freshest available source for a market."""
        market_key = market.value
        best = None
        best_time = None

        for source_key, status in self.markets.get(market_key, {}).items():
            if not status.available:
                continue
            if status.last_updated:
                if best_time is None or status.last_updated > best_time:
                    best = DataSource(source_key)
                    best_time = status.last_updated

        return best

    def get_summary(self) -> Dict:
        """Get summary stats for display."""
        total_markets = 0
        available_markets = 0
        fresh_markets = 0
        stale_markets = 0
        books_connected = set()

        for market_key, sources in self.markets.items():
            for source_key, status in sources.items():
                total_markets += 1
                if status.available:
                    available_markets += 1
                    books_connected.add(source_key)
                    if status.staleness == Staleness.FRESH:
                        fresh_markets += 1
                    elif status.staleness in [Staleness.STALE, Staleness.EXPIRED]:
                        stale_markets += 1

        return {
            "total_markets": total_markets,
            "available_markets": available_markets,
            "fresh_markets": fresh_markets,
            "stale_markets": stale_markets,
            "books_connected": list(books_connected),
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "recent_alerts": self.alerts[-5:] if self.alerts else [],
        }

    def to_dict(self) -> Dict:
        return {
            "tournament_id": self.tournament_id,
            "markets": {
                mk: {sk: sv.to_dict() for sk, sv in sources.items()}
                for mk, sources in self.markets.items()
            },
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "alerts": self.alerts[-20:],  # Keep last 20 alerts
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MarketAvailability":
        markets = {}
        for mk, sources in data.get("markets", {}).items():
            markets[mk] = {
                sk: MarketStatus.from_dict(sv)
                for sk, sv in sources.items()
            }

        last_scan = None
        if data.get("last_scan"):
            try:
                last_scan = datetime.fromisoformat(data["last_scan"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            tournament_id=data.get("tournament_id", ""),
            markets=markets,
            last_scan=last_scan,
            alerts=data.get("alerts", []),
        )


def calculate_staleness(last_updated: Optional[datetime]) -> Staleness:
    """Calculate staleness level from timestamp."""
    if not last_updated:
        return Staleness.EXPIRED

    now = datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    age = now - last_updated

    if age < timedelta(minutes=5):
        return Staleness.FRESH
    elif age < timedelta(minutes=30):
        return Staleness.RECENT
    elif age < timedelta(minutes=60):
        return Staleness.STALE
    else:
        return Staleness.EXPIRED


def scan_draftkings_availability(tournament_id: str) -> Dict[MarketType, MarketStatus]:
    """Scan DraftKings prop files for market availability."""
    import pandas as pd

    results = {}
    prop_file = ODDS_DIR / f"prop_lines_{tournament_id}.csv"

    if not prop_file.exists():
        # All markets unavailable
        for market in [MarketType.WINNER, MarketType.H2H, MarketType.ROUND_SCORE, MarketType.BIRDIES]:
            results[market] = MarketStatus(
                market=market,
                source=DataSource.DRAFTKINGS,
                available=False,
            )
        return results

    try:
        df = pd.read_csv(prop_file)

        # Get file modification time as last_updated
        last_updated = datetime.fromtimestamp(prop_file.stat().st_mtime, tz=timezone.utc)
        staleness = calculate_staleness(last_updated)

        # Count markets
        market_counts = df["market"].value_counts().to_dict() if "market" in df.columns else {}

        for market in [MarketType.WINNER, MarketType.H2H, MarketType.ROUND_SCORE, MarketType.BIRDIES]:
            count = market_counts.get(market.value, 0)
            results[market] = MarketStatus(
                market=market,
                source=DataSource.DRAFTKINGS,
                available=count > 0,
                player_count=count,
                last_updated=last_updated,
                staleness=staleness,
            )

    except Exception as e:
        print(f"Error scanning DraftKings: {e}")
        for market in [MarketType.WINNER, MarketType.H2H, MarketType.ROUND_SCORE, MarketType.BIRDIES]:
            results[market] = MarketStatus(
                market=market,
                source=DataSource.DRAFTKINGS,
                available=False,
            )

    return results


def scan_fanduel_availability(tournament_id: str) -> Dict[MarketType, MarketStatus]:
    """Scan FanDuel odds from PGA Tour leaderboard."""
    import pandas as pd

    results = {}
    live_dir = PROJECT_ROOT / "data" / "live"
    leaderboard_file = live_dir / f"leaderboard_{tournament_id.lower()}.csv"

    if not leaderboard_file.exists():
        results[MarketType.WINNER] = MarketStatus(
            market=MarketType.WINNER,
            source=DataSource.FANDUEL,
            available=False,
        )
        return results

    try:
        df = pd.read_csv(leaderboard_file)

        last_updated = datetime.fromtimestamp(leaderboard_file.stat().st_mtime, tz=timezone.utc)
        staleness = calculate_staleness(last_updated)

        # Check for odds_to_win column
        has_odds = "odds_to_win" in df.columns
        odds_count = 0
        if has_odds:
            odds_count = int(df["odds_to_win"].notna().sum())
            if odds_count == 0:
                odds_count = int((df["odds_to_win"] != "").sum())

        results[MarketType.WINNER] = MarketStatus(
            market=MarketType.WINNER,
            source=DataSource.FANDUEL,
            available=odds_count > 0,
            player_count=odds_count,
            last_updated=last_updated,
            staleness=staleness,
        )

    except Exception as e:
        print(f"Error scanning FanDuel: {e}")
        results[MarketType.WINNER] = MarketStatus(
            market=MarketType.WINNER,
            source=DataSource.FANDUEL,
            available=False,
        )

    return results


def scan_model_availability(tournament_id: str) -> Dict[MarketType, MarketStatus]:
    """Scan model prediction files for availability."""
    import pandas as pd

    results = {}
    outputs_dir = PROJECT_ROOT / "outputs"

    # Look for prediction files
    pred_patterns = [
        outputs_dir / f"{tournament_id}_predictions.csv",
        outputs_dir / f"{tournament_id.lower()}_predictions.csv",
    ]

    pred_file = None
    for p in pred_patterns:
        if p.exists():
            pred_file = p
            break

    # Also check for any recent predictions
    if not pred_file:
        for f in outputs_dir.glob("*_predictions.csv"):
            if tournament_id.lower() in f.stem.lower():
                pred_file = f
                break

    if not pred_file:
        for market in [MarketType.WINNER, MarketType.TOP5, MarketType.TOP10, MarketType.TOP20, MarketType.MAKE_CUT]:
            results[market] = MarketStatus(
                market=market,
                source=DataSource.MODEL,
                available=False,
            )
        return results

    try:
        df = pd.read_csv(pred_file)
        last_updated = datetime.fromtimestamp(pred_file.stat().st_mtime, tz=timezone.utc)
        staleness = calculate_staleness(last_updated)

        player_count = len(df)

        # Check which probability columns exist
        has_win = "win_prob" in df.columns or "win_probability" in df.columns
        has_top5 = "top5_prob" in df.columns or "top_5_prob" in df.columns
        has_top10 = "top10_prob" in df.columns or "top_10_prob" in df.columns
        has_top20 = "top20_prob" in df.columns or "top_20_prob" in df.columns
        has_cut = "make_cut_prob" in df.columns or "cut_prob" in df.columns

        results[MarketType.WINNER] = MarketStatus(
            market=MarketType.WINNER,
            source=DataSource.MODEL,
            available=has_win,
            player_count=player_count if has_win else 0,
            last_updated=last_updated,
            staleness=staleness,
        )

        results[MarketType.TOP5] = MarketStatus(
            market=MarketType.TOP5,
            source=DataSource.MODEL,
            available=has_top5,
            player_count=player_count if has_top5 else 0,
            last_updated=last_updated,
            staleness=staleness,
        )

        results[MarketType.TOP10] = MarketStatus(
            market=MarketType.TOP10,
            source=DataSource.MODEL,
            available=has_top10,
            player_count=player_count if has_top10 else 0,
            last_updated=last_updated,
            staleness=staleness,
        )

        results[MarketType.TOP20] = MarketStatus(
            market=MarketType.TOP20,
            source=DataSource.MODEL,
            available=has_top20,
            player_count=player_count if has_top20 else 0,
            last_updated=last_updated,
            staleness=staleness,
        )

        results[MarketType.MAKE_CUT] = MarketStatus(
            market=MarketType.MAKE_CUT,
            source=DataSource.MODEL,
            available=has_cut,
            player_count=player_count if has_cut else 0,
            last_updated=last_updated,
            staleness=staleness,
        )

    except Exception as e:
        print(f"Error scanning model: {e}")
        for market in [MarketType.WINNER, MarketType.TOP5, MarketType.TOP10, MarketType.TOP20, MarketType.MAKE_CUT]:
            results[market] = MarketStatus(
                market=market,
                source=DataSource.MODEL,
                available=False,
            )

    return results


def scan_all_availability(tournament_id: str) -> MarketAvailability:
    """Scan all sources and build complete availability picture."""
    availability = MarketAvailability(tournament_id=tournament_id)

    # Load existing to preserve alerts
    if AVAILABILITY_FILE.exists():
        try:
            with open(AVAILABILITY_FILE) as f:
                old_data = json.load(f)
                if old_data.get("tournament_id") == tournament_id:
                    availability.alerts = old_data.get("alerts", [])
        except Exception:
            pass

    # Scan each source
    for status in scan_draftkings_availability(tournament_id).values():
        availability.set_status(status)

    for status in scan_fanduel_availability(tournament_id).values():
        availability.set_status(status)

    for status in scan_model_availability(tournament_id).values():
        availability.set_status(status)

    # Save
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    with open(AVAILABILITY_FILE, "w") as f:
        json.dump(availability.to_dict(), f, indent=2)

    return availability


def load_availability(tournament_id: str) -> MarketAvailability:
    """Load cached availability or scan fresh."""
    if AVAILABILITY_FILE.exists():
        try:
            with open(AVAILABILITY_FILE) as f:
                data = json.load(f)
                if data.get("tournament_id") == tournament_id:
                    avail = MarketAvailability.from_dict(data)
                    # Check if scan is recent
                    if avail.last_scan:
                        age = datetime.now(timezone.utc) - avail.last_scan
                        if age < timedelta(minutes=2):
                            return avail
        except Exception:
            pass

    return scan_all_availability(tournament_id)


def get_staleness_badge(staleness: Staleness) -> Dict[str, str]:
    """Get display info for staleness badge."""
    badges = {
        Staleness.FRESH: {"label": "LIVE", "color": "#10b981", "icon": "🟢"},
        Staleness.RECENT: {"label": "RECENT", "color": "#f59e0b", "icon": "🟡"},
        Staleness.STALE: {"label": "STALE", "color": "#ef4444", "icon": "🟠"},
        Staleness.EXPIRED: {"label": "EXPIRED", "color": "#6b7280", "icon": "⚫"},
    }
    return badges.get(staleness, badges[Staleness.EXPIRED])


def get_source_label(source: DataSource, is_sportsbook: bool = None) -> str:
    """Get display label indicating if data is from sportsbook or model."""
    if source == DataSource.MODEL:
        return "📊 Model"
    else:
        return f"🎰 {source.value.title()}"


if __name__ == "__main__":
    import sys
    tournament_id = sys.argv[1] if len(sys.argv) > 1 else "R2026005"

    print(f"Scanning market availability for {tournament_id}...")
    avail = scan_all_availability(tournament_id)

    summary = avail.get_summary()
    print(f"\nSummary:")
    print(f"  Available markets: {summary['available_markets']}/{summary['total_markets']}")
    print(f"  Fresh markets: {summary['fresh_markets']}")
    print(f"  Books connected: {', '.join(summary['books_connected']) or 'None'}")

    print(f"\nMarket Details:")
    for market_key, sources in avail.markets.items():
        print(f"\n  {market_key}:")
        for source_key, status in sources.items():
            badge = get_staleness_badge(status.staleness)
            avail_str = f"✓ {status.player_count} lines" if status.available else "✗ unavailable"
            print(f"    {source_key}: {avail_str} {badge['icon']} {badge['label']}")

    if avail.alerts:
        print(f"\nRecent Alerts:")
        for alert in avail.alerts[-5:]:
            print(f"  [{alert['type']}] {alert['market']} @ {alert['source']} - {alert['timestamp']}")
