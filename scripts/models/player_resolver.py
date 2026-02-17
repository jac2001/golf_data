#!/usr/bin/env python3
"""
Player Name Resolution Service
==============================

Centralized player matching across all data sources:
- Model predictions
- DraftKings props
- FanDuel / PGA Tour odds
- Live leaderboard
- Historical data

Provides confidence scoring and mismatch logging for QA.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
import re

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
RESOLVER_CACHE = DATA_DIR / "cache" / "player_resolver.json"
MISMATCH_LOG = DATA_DIR / "cache" / "player_mismatches.json"


@dataclass
class PlayerMatch:
    """Result of a player name resolution."""
    canonical_name: str
    player_id: Optional[str] = None
    confidence: float = 1.0
    source: str = "exact"
    alternatives: List[str] = field(default_factory=list)


@dataclass
class PlayerResolver:
    """Centralized player name resolution."""

    # Canonical player database: player_id -> canonical info
    players: Dict[str, Dict] = field(default_factory=dict)

    # Name lookup indices
    exact_index: Dict[str, str] = field(default_factory=dict)  # normalized_name -> player_id
    fuzzy_index: Dict[str, List[str]] = field(default_factory=dict)  # last_first_initial -> player_ids

    # Mismatch tracking
    mismatches: List[Dict] = field(default_factory=list)

    def normalize_name(self, name: str) -> str:
        """Normalize a player name for matching."""
        if pd.isna(name) or not name:
            return ""

        name = str(name).strip()

        # Handle "Last, First" format -> "First Last"
        if "," in name:
            parts = name.split(",", 1)
            if len(parts) == 2:
                name = f"{parts[1].strip()} {parts[0].strip()}"

        # Lowercase
        name = name.lower()

        # Remove suffixes
        for suffix in [" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"]:
            name = name.replace(suffix, "")

        # Remove special characters but keep spaces
        name = re.sub(r"[^a-z\s]", "", name)

        # Collapse whitespace
        name = " ".join(name.split())

        return name

    def get_fuzzy_key(self, name: str) -> str:
        """Generate fuzzy matching key (last name + first initial)."""
        normalized = self.normalize_name(name)
        if not normalized:
            return ""

        parts = normalized.split()
        if len(parts) < 2:
            return normalized

        first = parts[0]
        last = parts[-1]
        return f"{last}_{first[0]}" if first else last

    def build_index(self, players_df: pd.DataFrame):
        """Build lookup indices from a player database."""
        if players_df.empty:
            return

        for _, row in players_df.iterrows():
            player_id = str(row.get("player_id", "")).strip()
            if not player_id:
                continue

            # Get all name variations
            names = set()
            for col in ["player_name", "name", "display_name", "full_name"]:
                if col in row and pd.notna(row[col]):
                    names.add(str(row[col]).strip())

            if not names:
                continue

            # Store canonical info
            canonical = list(names)[0]
            self.players[player_id] = {
                "player_id": player_id,
                "canonical_name": canonical,
                "names": list(names),
                "country": str(row.get("country", "")).strip(),
            }

            # Build exact index
            for name in names:
                normalized = self.normalize_name(name)
                if normalized:
                    self.exact_index[normalized] = player_id

            # Build fuzzy index
            for name in names:
                fuzzy_key = self.get_fuzzy_key(name)
                if fuzzy_key:
                    if fuzzy_key not in self.fuzzy_index:
                        self.fuzzy_index[fuzzy_key] = []
                    if player_id not in self.fuzzy_index[fuzzy_key]:
                        self.fuzzy_index[fuzzy_key].append(player_id)

    def resolve(self, name: str, source: str = "unknown") -> PlayerMatch:
        """Resolve a player name to canonical form."""
        if not name or pd.isna(name):
            return PlayerMatch(canonical_name="", confidence=0, source="empty")

        name = str(name).strip()
        normalized = self.normalize_name(name)

        # Try exact match first
        if normalized in self.exact_index:
            player_id = self.exact_index[normalized]
            player = self.players.get(player_id, {})
            return PlayerMatch(
                canonical_name=player.get("canonical_name", name),
                player_id=player_id,
                confidence=1.0,
                source="exact",
            )

        # Try fuzzy match
        fuzzy_key = self.get_fuzzy_key(name)
        if fuzzy_key in self.fuzzy_index:
            candidates = self.fuzzy_index[fuzzy_key]
            if len(candidates) == 1:
                player_id = candidates[0]
                player = self.players.get(player_id, {})
                return PlayerMatch(
                    canonical_name=player.get("canonical_name", name),
                    player_id=player_id,
                    confidence=0.8,
                    source="fuzzy",
                    alternatives=[self.players.get(c, {}).get("canonical_name", "") for c in candidates],
                )
            elif len(candidates) > 1:
                # Multiple candidates - log mismatch
                self.log_mismatch(name, source, candidates, "ambiguous_fuzzy")
                return PlayerMatch(
                    canonical_name=name,
                    confidence=0.4,
                    source="ambiguous",
                    alternatives=[self.players.get(c, {}).get("canonical_name", "") for c in candidates],
                )

        # No match found - return as-is with low confidence
        self.log_mismatch(name, source, [], "no_match")
        return PlayerMatch(
            canonical_name=name,
            confidence=0.2,
            source="unmatched",
        )

    def log_mismatch(self, name: str, source: str, candidates: List[str], reason: str):
        """Log a name resolution mismatch for QA."""
        self.mismatches.append({
            "name": name,
            "source": source,
            "candidates": candidates,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

    def get_mismatch_report(self) -> pd.DataFrame:
        """Generate mismatch report for QA."""
        if not self.mismatches:
            return pd.DataFrame()
        return pd.DataFrame(self.mismatches)

    def save_cache(self):
        """Save resolver state to cache."""
        RESOLVER_CACHE.parent.mkdir(parents=True, exist_ok=True)

        cache_data = {
            "players": self.players,
            "exact_index": self.exact_index,
            "fuzzy_index": self.fuzzy_index,
            "updated_at": datetime.now().isoformat(),
        }

        with open(RESOLVER_CACHE, "w") as f:
            json.dump(cache_data, f, indent=2)

        # Save mismatches
        if self.mismatches:
            with open(MISMATCH_LOG, "w") as f:
                json.dump(self.mismatches[-100:], f, indent=2)  # Keep last 100

    @classmethod
    def load_cache(cls) -> "PlayerResolver":
        """Load resolver from cache."""
        resolver = cls()

        if RESOLVER_CACHE.exists():
            try:
                with open(RESOLVER_CACHE) as f:
                    data = json.load(f)
                resolver.players = data.get("players", {})
                resolver.exact_index = data.get("exact_index", {})
                resolver.fuzzy_index = data.get("fuzzy_index", {})
            except Exception:
                pass

        return resolver


def build_resolver_from_sources() -> PlayerResolver:
    """Build a resolver from all available data sources."""
    resolver = PlayerResolver()

    # Load from player database
    player_files = [
        DATA_DIR / "players" / "pga_players_2026.csv",
        DATA_DIR / "players" / "pga_players_2025.csv",
    ]

    for path in player_files:
        if path.exists():
            try:
                df = pd.read_csv(path)
                resolver.build_index(df)
            except Exception:
                continue

    # Load from recent predictions
    pred_files = list(OUTPUTS_DIR.glob("*_predictions.csv")) + list(OUTPUTS_DIR.glob("*_latest.csv"))
    for path in pred_files[:5]:  # Limit to recent files
        if path.exists():
            try:
                df = pd.read_csv(path)
                if "player_id" in df.columns and "player_name" in df.columns:
                    resolver.build_index(df)
            except Exception:
                continue

    # Load from live leaderboard
    live_files = list((DATA_DIR / "live").glob("leaderboard_*.csv"))
    for path in live_files[:3]:
        if path.exists():
            try:
                df = pd.read_csv(path)
                if "player_id" in df.columns and "player_name" in df.columns:
                    resolver.build_index(df)
            except Exception:
                continue

    resolver.save_cache()
    return resolver


# Global resolver instance
_resolver: Optional[PlayerResolver] = None


def get_resolver() -> PlayerResolver:
    """Get or create the global resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = PlayerResolver.load_cache()
        if not _resolver.players:
            _resolver = build_resolver_from_sources()
    return _resolver


def resolve_player(name: str, source: str = "unknown") -> PlayerMatch:
    """Resolve a player name using the global resolver."""
    return get_resolver().resolve(name, source)


def resolve_players_in_df(df: pd.DataFrame, name_col: str = "player_name", source: str = "unknown") -> pd.DataFrame:
    """Add resolved player info to a DataFrame."""
    if name_col not in df.columns:
        return df

    resolver = get_resolver()
    df = df.copy()

    resolved = df[name_col].apply(lambda x: resolver.resolve(x, source))

    df["resolved_name"] = resolved.apply(lambda x: x.canonical_name)
    df["resolved_id"] = resolved.apply(lambda x: x.player_id)
    df["resolve_confidence"] = resolved.apply(lambda x: x.confidence)
    df["resolve_source"] = resolved.apply(lambda x: x.source)

    return df


def match_dataframes(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    name_col1: str = "player_name",
    name_col2: str = "player_name",
    source1: str = "df1",
    source2: str = "df2",
) -> Tuple[pd.DataFrame, Dict]:
    """Match two DataFrames by resolved player names."""
    resolver = get_resolver()

    # Resolve names in both DataFrames
    df1 = df1.copy()
    df2 = df2.copy()

    df1["_resolved"] = df1[name_col1].apply(lambda x: resolver.resolve(x, source1))
    df2["_resolved"] = df2[name_col2].apply(lambda x: resolver.resolve(x, source2))

    df1["_match_key"] = df1["_resolved"].apply(lambda x: x.canonical_name.lower())
    df2["_match_key"] = df2["_resolved"].apply(lambda x: x.canonical_name.lower())

    # Merge on match key
    merged = df1.merge(df2, on="_match_key", how="outer", suffixes=("_1", "_2"), indicator=True)

    # Stats
    stats = {
        "total_1": len(df1),
        "total_2": len(df2),
        "matched": int((merged["_merge"] == "both").sum()),
        "only_in_1": int((merged["_merge"] == "left_only").sum()),
        "only_in_2": int((merged["_merge"] == "right_only").sum()),
        "match_rate_1": (merged["_merge"] == "both").sum() / len(df1) if len(df1) > 0 else 0,
        "match_rate_2": (merged["_merge"] == "both").sum() / len(df2) if len(df2) > 0 else 0,
    }

    # Clean up
    merged = merged.drop(columns=["_resolved_1", "_resolved_2", "_match_key"], errors="ignore")

    return merged, stats


if __name__ == "__main__":
    import sys

    print("Building player resolver from all sources...")
    resolver = build_resolver_from_sources()

    print(f"\nLoaded {len(resolver.players)} players")
    print(f"Exact index entries: {len(resolver.exact_index)}")
    print(f"Fuzzy index entries: {len(resolver.fuzzy_index)}")

    # Test resolution
    test_names = [
        "Scottie Scheffler",
        "Scheffler, Scottie",
        "scottie scheffler",
        "S. Scheffler",
        "Rory McIlroy",
        "McIlroy, Rory",
        "Collin Morikawa",
        "Morikawa, Collin",
        "Unknown Player",
    ]

    print("\nTest resolutions:")
    for name in test_names:
        match = resolver.resolve(name, "test")
        print(f"  '{name}' -> '{match.canonical_name}' (conf={match.confidence:.2f}, src={match.source})")

    # Show mismatches
    if resolver.mismatches:
        print(f"\nMismatches logged: {len(resolver.mismatches)}")
        for m in resolver.mismatches[:5]:
            print(f"  {m['name']} ({m['source']}): {m['reason']}")
