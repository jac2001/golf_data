#!/bin/bash
# PostToolUse hook (Edit|Write): fast checks on the file just edited.
# Silent on success. On failure, prints the tail of the output to stderr
# and exits 2 so Claude sees it and fixes it before moving on.
ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PY="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
[ -z "$f" ] && exit 0

fail() { echo "$1" >&2; echo "$2" | tail -25 >&2; exit 2; }

case "$f" in
  "$ROOT"/web/lib/*.ts)
    out=$(cd "$ROOT/web" && npm test --silent 2>&1) || fail "web/lib tests failed after editing ${f#$ROOT/}:" "$out"
    ;;
  "$ROOT"/*.py)
    out=$("$PY" -m py_compile "$f" 2>&1) || fail "Syntax error in ${f#$ROOT/}:" "$out"
    out=$("$PY" "$ROOT/scripts/validation/duplicate_defs.py" "$f" 2>&1) || fail "Duplicate definition in ${f#$ROOT/}:" "$out"
    case "$f" in
      "$ROOT"/scripts/validation/*|"$ROOT"/scripts/predictions/*|"$ROOT"/scripts/features/*|"$ROOT"/scripts/scrapers/*|"$ROOT"/api/*)
        for t in scripts/validation/test_prediction_integrity.py scripts/validation/test_euro_integrity.py scripts/validation/test_model_manifest.py scripts/validation/test_duplicate_defs.py \
                 scripts/features/test_euro_features.py scripts/scrapers/test_euro_schedule.py scripts/scrapers/test_euro_purses.py scripts/scrapers/test_event_guard.py scripts/scrapers/test_event_names.py \
                 api/test_routes.py api/test_owner_guard.py; do
          out=$(cd "$ROOT" && "$PY" "$t" 2>&1) || fail "$t failed after editing ${f#$ROOT/}:" "$out"
        done
        ;;
    esac
    ;;
esac
exit 0
