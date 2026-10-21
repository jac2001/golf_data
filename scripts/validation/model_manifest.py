"""
model_manifest.py — which model artifacts this run actually loaded.
===================================================================
Serving code loaded some pickles only "if present". The score models
existed on Jack's machine but not in git, so CI silently ran without them
while local runs wrote projected_score / proj_* columns (audit finding 11).
They are disabled everywhere now (Oct 21); round_matchup_model.pkl is still
optional and local-only. "Works locally" proves nothing about production.

data/models/manifest.json lists every serving artifact: who loads it,
required or optional, whether git distributes it, and its sha256.

    check()     -> (failures, notes)   required missing/changed = failure
    present()   -> {path: sha256|None} what THIS environment has
    python3 scripts/validation/model_manifest.py           report
    python3 scripts/validation/model_manifest.py --write   re-record checksums
                                                           after a deliberate retrain
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "models" / "manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(manifest: Path = MANIFEST) -> dict:
    return json.loads(manifest.read_text())


def present(manifest: Path = MANIFEST, root: Path = ROOT) -> dict[str, str | None]:
    """sha256 of every listed artifact found here, None for the absent ones."""
    out: dict[str, str | None] = {}
    for rel in load(manifest)["artifacts"]:
        p = root / rel
        out[rel] = sha256(p) if p.exists() else None
    return out


def check(manifest: Path = MANIFEST, root: Path = ROOT) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    entries = load(manifest)["artifacts"]
    have = present(manifest, root)
    for rel, e in entries.items():
        got = have[rel]
        if e["required"]:
            if got is None:
                failures.append(f"required model artifact missing: {rel}")
            elif got != e["sha256"]:
                failures.append(f"{rel} differs from data/models/manifest.json "
                                f"(retrained? re-record with model_manifest.py --write)")
        elif got is None:
            notes.append(f"ℹ optional artifact absent: {rel} ({e['effect_when_absent']})")
        else:
            same = "" if got == e.get("sha256") else " (checksum differs from manifest)"
            notes.append(f"ℹ optional artifact present: {rel}{same}"
                         + ("" if e["in_git"] else " — local only, CI does not have it"))
    if not failures:
        n = sum(1 for e in entries.values() if e["required"])
        notes.append(f"✓ Model artifacts: {n} required present and match the manifest")
    return failures, notes


def write(manifest: Path = MANIFEST, root: Path = ROOT) -> None:
    """Re-record checksums for artifacts present here; keep everything else."""
    m = load(manifest)
    for rel, got in present(manifest, root).items():
        if got is not None:
            m["artifacts"][rel]["sha256"] = got
    manifest.write_text(json.dumps(m, indent=2) + "\n")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write()
        print(f"wrote {MANIFEST.relative_to(ROOT)}")
    fails, notes = check()
    for line in notes + [f"✗ {f}" for f in fails]:
        print(line)
    raise SystemExit(1 if fails else 0)
