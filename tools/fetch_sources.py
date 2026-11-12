#!/usr/bin/env python3
"""Download the three upstream CGAZ GeoPackages into the staging tree.

    python3 tools/fetch_sources.py

The files are served through git-lfs, so the ``/raw/main/`` URL redirects to
``media.githubusercontent.com``. ``curl -L`` follows that. Nothing here enters
git: the staging root sits outside the repository.
"""
from __future__ import annotations

import sys

from gbcommon import LEVELS, SOURCES, run, source_path, source_url


def main() -> int:
    SOURCES.mkdir(parents=True, exist_ok=True)
    for level in LEVELS:
        dest = source_path(level)
        if dest.exists():
            print(f"ADM{level}: already present ({dest.stat().st_size:,} bytes)")
            continue
        print(f"ADM{level}: downloading {source_url(level)}")
        run(["curl", "-fsSL", "-o", str(dest), source_url(level)])
        print(f"ADM{level}: {dest.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
