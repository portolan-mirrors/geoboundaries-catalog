#!/usr/bin/env python3
"""The published deviation record has to match its source.

docs/changes-from-upstream.md is authoritative; catalog/changes-from-upstream.md
is the copy that reaches object storage, where most readers will meet it. A
copy that has drifted is worse than no copy, because it says the catalog does
something it no longer does.

Run: python3 tests/test_changes_doc.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from make_changes_doc import DST, SRC, rewrite, BANNER  # noqa: E402

if not SRC.exists() or not DST.exists():
    print(f"error  missing {SRC if not SRC.exists() else DST}")
    raise SystemExit(1)

expected = BANNER + rewrite(SRC.read_text())
if DST.read_text() != expected:
    print(
        "error  catalog/changes-from-upstream.md is stale.\n"
        "       Run: python3 tools/make_changes_doc.py"
    )
    raise SystemExit(1)

print("OK: the published deviation record matches its source")
