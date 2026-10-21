"""Tests for duplicate_defs. Run: python3 scripts/validation/test_duplicate_defs.py"""
import sys
from pathlib import Path
from textwrap import dedent

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from duplicate_defs import Duplicate, duplicate_defs  # noqa: E402


def dupes(src: str) -> list[Duplicate]:
    return duplicate_defs(dedent(src))


def test_module_level_function_twice():
    # The test_euro_schedule.py bug: the second def hid the first test.
    assert dupes("""
        def test_a():
            pass

        def test_a():
            pass
    """) == [Duplicate("test_a", 2, 5)]


def test_async_and_class_count():
    assert dupes("""
        async def f(): ...
        class f: ...
    """) == [Duplicate("f", 2, 3)]


def test_method_twice_in_one_class():
    assert dupes("""
        class Client:
            def get(self): ...
            def get(self): ...
    """) == [Duplicate("Client.get", 3, 4)]


def test_same_method_in_two_classes_is_fine():
    assert dupes("""
        class A:
            def run(self): ...
        class B:
            def run(self): ...
    """) == []


def test_property_setter_pair_is_fine():
    assert dupes("""
        class T:
            @property
            def x(self): return 1
            @x.setter
            def x(self, v): ...
            @x.deleter
            def x(self): ...
    """) == []


def test_overload_stubs_are_fine():
    assert dupes("""
        from typing import overload
        @overload
        def f(x: int) -> int: ...
        @overload
        def f(x: str) -> str: ...
        def f(x): return x
    """) == []


def test_conditional_fallback_is_fine():
    assert dupes("""
        try:
            from fast import parse
        except ImportError:
            def parse(s): ...
        if True:
            def g(): ...
        else:
            def g(): ...
    """) == []


def test_decorated_route_handlers_twice_still_count():
    # The /api/model-comparison bug: decorators other than property/overload
    # don't make a second definition legitimate.
    assert dupes("""
        @app.get("/x")
        def handler(): ...
        @app.get("/x")
        def handler(): ...
    """) == [Duplicate("handler", 3, 5)]


def test_three_definitions_report_each_replacement():
    assert dupes("""
        def f(): ...
        def f(): ...
        def f(): ...
    """) == [Duplicate("f", 2, 3), Duplicate("f", 3, 4)]


if __name__ == "__main__":
    passed = 0
    tests = [(n, fn) for n, fn in list(globals().items()) if n.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  ok    {name}")
        except NotImplementedError:
            print(f"  TODO  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name} {e}")
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)
