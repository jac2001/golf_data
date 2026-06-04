#!/usr/bin/env python3
"""
Run all test questions through the chatbot and save responses to a file.

Usage:
  python3 scripts/chat/run_chat_tests.py                # Groq (free, default)
  python3 scripts/chat/run_chat_tests.py --claude       # Claude (costs credits)
  python3 scripts/chat/run_chat_tests.py --questions 1 3 5   # run specific Qs only
  python3 scripts/chat/run_chat_tests.py --out my_results.txt
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "chat"))

import golf_chatbot as gc
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

QUESTIONS = [
    ("Player", "How is Rory McIlroy looking this week?"),
    ("Player", "Tell me about Scottie Scheffler at the Memorial"),
    ("Player", "Should I use Matt Fitzpatrick this week?"),
    ("Player", "How is Si Woo Kim's form lately?"),
    ("H2H",    "McIlroy vs Scheffler this week — who do you like?"),
    ("H2H",    "Compare Aberg and Fitzpatrick for this week"),
    ("Bets",   "What are the best bets this week?"),
    ("Bets",   "Any value in the top 10 market?"),
    ("Bets",   "Best make cut plays this week?"),
    ("Course", "What does Muirfield Village reward — what kind of game wins here?"),
    ("Course", "How has the weather been affecting play this week?"),
    ("Lineup", "Who should I use this week for fantasy?"),
    ("Lineup", "When is the best time to use Scheffler this season?"),
    ("Live",   "Who's leading and what's the cut looking like?"),
    ("Live",   "Update me on the tournament"),
]


def _get_tournament_id() -> str:
    try:
        import pandas as pd
        preds = pd.read_csv(PROJECT_ROOT / "outputs" / "latest_predictions.csv")
        return str(preds["tournament_id"].iloc[0])
    except Exception:
        return "R2026023"


def run_question(question: str, tid: str, provider: str, api_key: str) -> str:
    lean = provider == "groq"  # Groq free tier has a 12K token limit
    context = gc.build_context(query=question, tournament_id=tid, lean=lean)

    if provider == "groq":
        messages = [{"role": "system", "content": context},
                    {"role": "user",   "content": question}]
        chunks = gc._stream_groq(messages, api_key)
    else:
        # Claude — use stream_response with full message format
        messages = [{"role": "system", "content": context},
                    {"role": "user",   "content": question}]
        chunks = gc.stream_response(messages, api_key, provider="anthropic")

    full_response = ""
    for chunk in chunks:
        full_response += chunk
        print(chunk, end="", flush=True)
    print()
    return full_response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", action="store_true",
                        help="Use Claude instead of Groq (costs credits)")
    parser.add_argument("--out", default="scripts/chat/test_responses.txt")
    parser.add_argument("--questions", nargs="*", type=int,
                        help="Run specific question numbers (1-based), e.g. --questions 1 3 5")
    parser.add_argument("--delay", type=int, default=0,
                        help="Seconds to wait between questions (default 0; use 20 for Groq free tier)")
    args = parser.parse_args()

    # Resolve provider + key
    if args.claude:
        provider = "anthropic"
        api_key  = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set in .env")
            sys.exit(1)
        model_label = "Claude Sonnet"
    else:
        provider = "groq"
        api_key  = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            print("ERROR: GROQ_API_KEY not set in .env")
            print("Add your key: https://console.groq.com → API Keys")
            sys.exit(1)
        model_label = "Groq / Llama 3.3 70B (free)"
        if args.delay == 0:
            print("TIP: Add --delay 20 to avoid Groq TPM rate limits when running all 15 questions.")

    tid = _get_tournament_id()
    questions_to_run = (
        [(i, QUESTIONS[i - 1]) for i in args.questions if 1 <= i <= len(QUESTIONS)]
        if args.questions
        else list(enumerate(QUESTIONS, 1))
    )

    out_path = PROJECT_ROOT / args.out
    lines = [
        "# Chat Response Test Run",
        f"# Model:      {model_label}",
        f"# Tournament: {tid}",
        f"# Date:       {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Questions:  {len(questions_to_run)}",
        "=" * 70,
        "",
    ]

    print(f"\nModel: {model_label}")
    print(f"Tournament: {tid}")
    print(f"Running {len(questions_to_run)} question(s) → {out_path}\n")

    for num, (category, question) in questions_to_run:
        header = f"Q{num} [{category}]: {question}"
        print(f"\n{'=' * 60}")
        print(header)
        print("=" * 60)

        lines += [f"## Q{num} [{category}]", f"**{question}**", ""]

        try:
            response = run_question(question, tid, provider, api_key)
            lines.append(response.strip())
        except Exception as e:
            err = f"ERROR: {e}"
            print(err)
            lines.append(err)

        lines += ["", "-" * 70, ""]
        out_path.write_text("\n".join(lines))
        print(f"\n[saved → {out_path.name}]")

        if args.delay and num < questions_to_run[-1][0]:
            print(f"[waiting {args.delay}s…]")
            time.sleep(args.delay)

    print(f"\nDone. Full output: {out_path}")


if __name__ == "__main__":
    main()
