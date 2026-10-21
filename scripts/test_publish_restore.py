"""Failed-run recovery must restore the exact pre-run state. Run: python3 scripts/test_publish_restore.py

Audit (Oct 21): restore_prediction_outputs restored whole directories from
HEAD, so an edit made BEFORE a local pipeline run was erased when the run
failed. Each test builds a throwaway git repo and runs the real functions.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scheduled_refresh as sr  # noqa: E402

PATHS = ["outputs", "data/prediction_tracking"]


def repo(tmp: Path) -> Path:
    def git(*a):
        subprocess.run(["git", "-C", str(tmp), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (tmp / "outputs").mkdir(); (tmp / "data" / "prediction_tracking").mkdir(parents=True)
    (tmp / "outputs" / "latest_predictions.csv").write_text("committed\n")
    (tmp / "data" / "prediction_tracking" / "pred_R1.csv").write_text("committed\n")
    git("add", "-A"); git("commit", "-qm", "base")
    return tmp


def run_failed(tmp: Path, before, during) -> dict:
    """before(): local state when the run starts; during(): what the failing run writes."""
    before(tmp)
    snap = sr.snapshot_prediction_outputs(tmp, PATHS, stash_dir=tmp / ".stash")
    during(tmp)
    assert sr.restore_prediction_outputs(snap, rejected_dir=tmp / ".rejected")
    return snap


def test_local_edit_made_before_the_run_survives():
    with tempfile.TemporaryDirectory() as d:
        tmp = repo(Path(d))
        def before(t): (t / "outputs" / "latest_predictions.csv").write_text("my local edit\n")
        def during(t): (t / "outputs" / "latest_predictions.csv").write_text("rejected run\n")
        run_failed(tmp, before, during)
        assert (tmp / "outputs" / "latest_predictions.csv").read_text() == "my local edit\n"
        assert (tmp / ".rejected" / "outputs" / "latest_predictions.csv").read_text() == "rejected run\n"


def test_untracked_file_from_before_survives_and_new_files_go():
    with tempfile.TemporaryDirectory() as d:
        tmp = repo(Path(d))
        def before(t): (t / "outputs" / "my_notes.csv").write_text("mine\n")
        def during(t):
            (t / "outputs" / "my_notes.csv").write_text("overwritten by run\n")
            (t / "data" / "prediction_tracking" / "pred_R2.csv").write_text("new from run\n")
        run_failed(tmp, before, during)
        assert (tmp / "outputs" / "my_notes.csv").read_text() == "mine\n"
        assert not (tmp / "data" / "prediction_tracking" / "pred_R2.csv").exists()
        assert (tmp / ".rejected" / "data" / "prediction_tracking" / "pred_R2.csv").exists()


def test_clean_checkout_returns_to_head():
    # The CI case: nothing local, so the pre-run state is HEAD.
    with tempfile.TemporaryDirectory() as d:
        tmp = repo(Path(d))
        def during(t):
            (t / "outputs" / "latest_predictions.csv").write_text("rejected run\n")
            (t / "data" / "prediction_tracking" / "pred_R1.csv").unlink()
        snap = run_failed(tmp, lambda t: None, during)
        assert snap["saved"] == []
        assert (tmp / "outputs" / "latest_predictions.csv").read_text() == "committed\n"
        assert (tmp / "data" / "prediction_tracking" / "pred_R1.csv").read_text() == "committed\n"


def test_file_deleted_locally_before_the_run_stays_deleted():
    with tempfile.TemporaryDirectory() as d:
        tmp = repo(Path(d))
        def before(t): (t / "data" / "prediction_tracking" / "pred_R1.csv").unlink()
        def during(t): (t / "data" / "prediction_tracking" / "pred_R1.csv").write_text("run\n")
        run_failed(tmp, before, during)
        assert not (tmp / "data" / "prediction_tracking" / "pred_R1.csv").exists()


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"ok {name}")
    print(f"{len(tests)}/{len(tests)} passed")
