#!/usr/bin/env python3
"""Publish the deviation record into the catalog.

    python3 tools/make_changes_doc.py

docs/changes-from-upstream.md is the authoritative copy and lives with the
rest of the repository documentation. A reader who meets this catalog as a
pile of Parquet files on object storage never sees the repository, and the one
thing they most need to know is that the data is not a byte-for-byte mirror.
So the same text is published inside catalog/, and tests/test_changes_doc.py
fails if the two drift apart.

Relative links are rewritten to absolute GitHub links on the way, because the
published copy sits in a different tree.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "changes-from-upstream.md"
DST = ROOT / "catalog" / "changes-from-upstream.md"
REPO = "https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main"

BANNER = (
    "<!-- Published copy. The source is docs/changes-from-upstream.md in\n"
    f"     {REPO}, and tools/make_changes_doc.py keeps the two in step.\n"
    "     Edit the source, not this file. -->\n\n"
)


def rewrite(text: str) -> str:
    """Point repository-relative links at GitHub."""
    text = re.sub(r"\]\(\.\./tools/", f"]({REPO}/tools/", text)
    text = re.sub(r"\]\(\.\./catalog/", "](./", text)
    text = re.sub(r"\]\(conformance\.md\)", f"]({REPO}/docs/conformance.md)", text)
    return text


def main() -> int:
    if not SRC.exists():
        sys.exit(f"missing {SRC}")
    DST.write_text(BANNER + rewrite(SRC.read_text()))
    print(f"  {DST.relative_to(ROOT)}: {DST.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
