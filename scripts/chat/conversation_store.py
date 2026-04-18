"""
Conversation log — DuckDB read/write for assistant Q&A history.

Two public functions:
  log_exchange()  — called by dashboard after every assistant response
  get_recent()    — called by golf_chatbot.py to inject prior context

The table (conversation_log) lives in data/golf_data.db alongside all other
tables. Schema is defined in scripts/database/schema.py.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Max chars stored/injected for the short summary.
# Long enough to capture the key recommendation; short enough to stay
# within Groq's token budget when 5 entries are injected at once.
_SHORT_LEN = 800


def _get_conn():
    """Import here to avoid circular deps and missing-package errors at import time."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
    from db import get_conn
    return get_conn(read_only=False)


def log_exchange(
    tournament_id: str | None,
    phase: str,
    question: str,
    response: str,
) -> None:
    """
    Persist one Q&A exchange to the conversation_log table.

    Called from dashboard.py after every successful assistant response.
    Silently swallows all errors — a logging failure should never break
    the chat experience.

    tournament_id: R-prefixed ID (e.g. 'R2026041') or None if unknown
    phase:         pre_tournament / round_1 / round_2 / round_3 / round_4 / complete
    question:      full user question (stored as-is)
    response:      full assistant response (truncated to _SHORT_LEN for injection,
                   full text stored in response_full for your records)
    """
    try:
        response_short = response[:_SHORT_LEN].rstrip()
        if len(response) > _SHORT_LEN:
            response_short += "…"

        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO conversation_log
                    (timestamp, tournament_id, phase, question, response_short, response_full)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [datetime.now(), tournament_id, phase, question, response_short, response],
            )
    except Exception:
        pass  # never block the chat on a log write failure


def get_recent(
    tournament_id: str | None,
    limit: int = 8,
) -> List[Dict]:
    """
    Return the most recent exchanges for the given tournament.

    Used by golf_chatbot.py to build the 'Previous Conversations' context block.
    Returns a list of dicts with keys: timestamp, phase, question, response_short.
    Returns [] on any error (chatbot falls back to no history gracefully).

    tournament_id: R-prefixed ID — only same-tournament history is injected
                   (last week's Valero chat is irrelevant for The Masters)
    limit:         how many exchanges to surface; 5 is enough for continuity
                   without bloating the system prompt
    """
    try:
        if not tournament_id:
            return []

        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, phase, question, response_short
                FROM conversation_log
                WHERE tournament_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                [tournament_id, limit],
            ).fetchall()

        # Reverse so oldest is first (natural reading order in the prompt)
        rows = list(reversed(rows))

        return [
            {
                "timestamp": row[0],
                "phase":     row[1],
                "question":  row[2],
                "response_short": row[3],
            }
            for row in rows
        ]
    except Exception:
        return []
