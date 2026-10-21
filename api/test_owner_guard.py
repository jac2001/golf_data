"""Tests for owner_guard. Run: python3 api/test_owner_guard.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from owner_guard import HEADER, require_owner  # noqa: E402

app = FastAPI()


@app.post("/write", dependencies=[Depends(require_owner)])
def write() -> dict:
    return {"ok": True}


client = TestClient(app)


def test_no_secret_configured_refuses_everyone():
    os.environ.pop("CHAT_PROXY_SECRET", None)
    assert client.post("/write").status_code == 403
    assert client.post("/write", headers={HEADER: ""}).status_code == 403


def test_anonymous_and_wrong_secret_refused():
    os.environ["CHAT_PROXY_SECRET"] = "s3cret"
    assert client.post("/write").status_code == 403
    assert client.post("/write", headers={HEADER: "nope"}).status_code == 403


def test_right_secret_allowed():
    os.environ["CHAT_PROXY_SECRET"] = "s3cret"
    r = client.post("/write", headers={HEADER: "s3cret"})
    assert r.status_code == 200 and r.json() == {"ok": True}


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
