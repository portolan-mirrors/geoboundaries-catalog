#!/usr/bin/env python3
"""Print the table of repaired names, as markdown.

    python3 tools/mojibake_report.py            # markdown table
    python3 tools/mojibake_report.py --count    # just the count

Reads the *raw* staged conversions under ``work/``, which are the upstream
GeoPackages with nothing changed but the CRS assignment, so the "upstream"
column is what geoBoundaries actually publishes. Rerun this after any refetch
and paste the result into docs/changes-from-upstream.md; if the count moves,
the documentation is stale.
"""
from __future__ import annotations

import sys

import duckdb

from gbcommon import LEVELS, WORK, repair_mojibake


def rows():
    con = duckdb.connect()
    out = []
    for level in LEVELS:
        src = (WORK / f"adm{level}.raw.parquet").as_posix()
        for name, group in con.execute(
            f"SELECT shapeName, shapeGroup FROM read_parquet('{src}') "
            "WHERE shapeName IS NOT NULL"
        ).fetchall():
            fixed, changed = repair_mojibake(name)
            if changed:
                out.append((level, group, name, fixed))
    con.close()
    return sorted(out, key=lambda r: (r[0], r[1], r[3]))


def main(argv: list[str]) -> int:
    found = rows()
    if "--count" in argv:
        print(len(found))
        return 0
    print("| level | country | as geoBoundaries publishes it | as published here |")
    print("|---|---|---|---|")
    for level, group, before, after in found:
        print(f"| ADM{level} | `{group}` | `{before}` | {after} |")
    print()
    print(f"{len(found)} names.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
