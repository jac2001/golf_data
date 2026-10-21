"""Tests for the model artifact manifest. Run: python3 scripts/validation/test_model_manifest.py"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from model_manifest import MANIFEST, ROOT, check, sha256, write  # noqa: E402


def tiny(tmp: Path) -> Path:
    """A two-entry manifest (one required, one optional) over files in tmp."""
    (tmp / "req.pkl").write_bytes(b"required model")
    m = {"artifacts": {
        "req.pkl": {"required": True, "in_git": True, "sha256": sha256(tmp / "req.pkl")},
        "opt.pkl": {"required": False, "in_git": False, "sha256": None,
                    "effect_when_absent": "no extra columns"},
    }}
    path = tmp / "manifest.json"
    path.write_text(json.dumps(m))
    return path


def test_ok_with_optional_absent():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fails, notes = check(tiny(tmp), tmp)
        assert fails == []
        assert any("optional artifact absent: opt.pkl" in n for n in notes)


def test_required_missing_fails():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        m = tiny(tmp)
        (tmp / "req.pkl").unlink()
        fails, _ = check(m, tmp)
        assert fails and "missing" in fails[0]


def test_required_changed_fails_until_rewritten():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        m = tiny(tmp)
        (tmp / "req.pkl").write_bytes(b"retrained")
        fails, _ = check(m, tmp)
        assert fails and "differs" in fails[0]
        write(m, tmp)
        assert check(m, tmp)[0] == []


def test_optional_present_flagged_local_only():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        m = tiny(tmp)
        (tmp / "opt.pkl").write_bytes(b"local")
        fails, notes = check(m, tmp)
        assert fails == [] and any("local only" in n for n in notes)


def test_real_manifest_lists_what_serving_loads():
    arts = json.loads(MANIFEST.read_text())["artifacts"]
    for rel in ["data/models/win_model_final.pkl", "data/models/feature_medians.json",
                "data/models/euro/euro_won_model.pkl", "data/models/score_model_final.pkl"]:
        assert rel in arts, rel
    # Every required artifact must be one git distributes, or CI can never pass.
    assert all(e["in_git"] for e in arts.values() if e["required"])
    assert all((ROOT / r).exists() for r, e in arts.items() if e["required"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
