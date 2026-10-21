"""Spec for odds_move. Run: python3 scripts/predictions/test_odds_move.py"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from odds_move import odds_move  # noqa: E402


def test_favorite_warming_is_down():
    # 8% -> 9%: +12.5% relative, +1.0pp absolute. Odds shortened.
    assert odds_move(0.08, 0.09) == "DOWN"


def test_favorite_cooling_is_up():
    # 8% -> 7%: -12.5% relative, -1.0pp. Odds lengthened.
    assert odds_move(0.08, 0.07) == "UP"


def test_longshot_wobble_is_noise():
    # 0.4% -> 0.3%: -25% relative, but only 0.1pp. Books shading longshots.
    assert odds_move(0.004, 0.003) is None


def test_small_favorite_move_is_noise():
    # 20% -> 21%: +1pp absolute but only +5% relative.
    assert odds_move(0.20, 0.21) is None


def test_exactly_on_both_thresholds_counts():
    # 2% -> 2.2%: exactly +10% relative and exactly +0.2pp.
    assert odds_move(0.02, 0.022) == "DOWN"


def test_missing_or_invalid_is_none():
    for a, b in [(None, 0.05), (0.05, None), (math.nan, 0.05), (0.05, math.nan),
                 (0.0, 0.05), (0.05, 0.0), (-0.01, 0.05), (0.05, 1.5)]:
        assert odds_move(a, b) is None, (a, b)


def test_no_change_is_none():
    assert odds_move(0.05, 0.05) is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    passed = 0
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
