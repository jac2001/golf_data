"""
duplicate_defs.py — a function or class defined twice in the same scope.
========================================================================
Python lets a later `def` silently replace an earlier one with the same
name. That hid a real test case (test_euro_schedule.py ran 15 of 16 tests
and reported 15/15), left a dead fetch_weather in the Open-Meteo scraper,
and registered /api/model-comparison twice (audit findings 8 and 13).

    python3 scripts/validation/duplicate_defs.py            every tracked .py
    python3 scripts/validation/duplicate_defs.py a.py b.py  just these
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]


class Duplicate(NamedTuple):
    name: str        # "fetch_weather", or "Klass.method" inside a class
    first_line: int  # where the definition that gets replaced starts
    line: int        # where the replacing definition starts


def duplicate_defs(source: str) -> list[Duplicate]:
    """Every def/async def/class that replaces an earlier one in the same scope.

    Scopes to check: the module body, and each class
    body (report methods as "Klass.method"). Not duplicates (see the tests):
      - the same name in two different classes
      - @property / @<name>.setter / @<name>.deleter pairs
      - @overload (typing.overload) stubs before the real def
      - defs inside if/else or try/except (a conditional fallback is fine;
        only look at statements directly in a scope's body)
    Hints: ast.parse(source); node.body is a list of statements; check
    isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef));
    stmt.decorator_list holds ast.Name / ast.Attribute nodes.
    Return them in source order.
    """
    duplicates: list[Duplicate] = []

    def check_scope(body: list[ast.stmt], prefix: str = "") -> None:
        seen: dict[str, int] = {}
        properties: set[str] = set()
        for stmt in body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            decorators = stmt.decorator_list
            is_overload = any(
                isinstance(d, ast.Name) and d.id == "overload"
                or isinstance(d, ast.Attribute)
                and isinstance(d.value, ast.Name)
                and d.value.id == "typing" and d.attr == "overload"
                for d in decorators
            )
            if is_overload:
                continue
            is_property = any(
                isinstance(d, ast.Name) and d.id == "property"
                for d in decorators
            )
            is_accessor = stmt.name in properties and any(
                isinstance(d, ast.Attribute)
                and isinstance(d.value, ast.Name)
                and d.value.id == stmt.name
                and d.attr in {"setter", "deleter"}
                for d in decorators
            )
            name = prefix + stmt.name
            if stmt.name in seen and not is_accessor:
                duplicates.append(Duplicate(name, seen[stmt.name], stmt.lineno))
            seen[stmt.name] = stmt.lineno
            if is_property:
                properties.add(stmt.name)
            elif not is_accessor:
                properties.discard(stmt.name)
            if isinstance(stmt, ast.ClassDef):
                check_scope(stmt.body, name + ".")

    check_scope(ast.parse(source).body)
    return sorted(duplicates, key=lambda d: d.line)


def tracked_python_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split()]


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv] or tracked_python_files()
    found = 0
    for f in files:
        try:
            dupes = duplicate_defs(f.read_text())
        except SyntaxError as e:
            print(f"{f}: cannot parse ({e})")
            continue
        for d in dupes:
            rel = f.relative_to(ROOT) if f.is_relative_to(ROOT) else f
            print(f"{rel}:{d.line}: {d.name} replaces the definition at line {d.first_line}")
            found += 1
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
