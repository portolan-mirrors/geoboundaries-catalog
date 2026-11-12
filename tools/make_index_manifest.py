#!/usr/bin/env python3
"""Refresh the measured fields of ``catalog/names/index.json``.

    python3 tools/make_index_manifest.py           # rewrite in place
    python3 tools/make_index_manifest.py --check   # fail if it would change

``catalog/names/index.json`` is the kilobyte a geocoder fetches before
anything else, and most of what it says is a number taken off a built file:
sizes, checksums, row counts, row group counts, row group sizes and the
trailing-metadata sizes. Those are generated here. Everything else in the file
-- `notes`, `attribution`, the per-level join columns, `dropped_unnamed` --
is hand-written prose and fact that this script has no other source for, and
it is preserved byte for byte.

**What ``footer_bytes`` is for.** A range client has to read a Parquet file's
metadata before it can read any row group, and it has no way to know how big
that metadata is: hyparquet therefore speculates a 512 KiB tail and fetches
again when it guesses short. Measured against the live catalog, that
speculative read was 524,288 bytes against a real need of 90,369 on ADM0 --
and on the sibling Overture index, whose footer is 2 MB, it is a guaranteed
second round trip. So this publishes both exact sizes:

* ``footer_bytes`` -- the whole trailing span, thrift footer **plus** page
  index. One request of exactly this many bytes from the end of the file
  leaves a client holding every piece of metadata the file has.
* ``footer_metadata_bytes`` -- the thrift footer alone, which is the minimum a
  reader needs to locate row groups. hyparquet never reads the page index
  bodies (it has no sub-chunk read), so a hyparquet client should ask for this
  smaller number.

Either way the read is one exactly-sized request instead of a speculative one,
which is the whole point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from gbcommon import (
    EXTRACTION_DATE,
    NAMES_ROW_GROUP_ROWS,
    PUBLISH,
    ROW_GROUP_ROWS,
    trailing_bytes,
)

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "catalog" / "names" / "index.json"

NAMES = PUBLISH / "names" / "cgaz_names.parquet"


def checksum(path: Path) -> str:
    """A multihash sha2-256, the form STAC's file extension expects."""
    return "1220" + hashlib.sha256(path.read_bytes()).hexdigest()


def file_entry(path: Path) -> dict:
    """The measured description of one published parquet file."""
    md = pq.ParquetFile(path).metadata
    footer, page_index = trailing_bytes(path)
    return {
        "size": path.stat().st_size,
        "row_count": md.num_rows,
        "row_groups": md.num_row_groups,
        "footer_bytes": footer + page_index,
        "footer_metadata_bytes": footer,
    }


def boundary_paths(level: int) -> tuple[Path, Path]:
    d = PUBLISH / f"adm{level}"
    return (
        d / f"cgaz_adm{level}.parquet",
        d / f"cgaz_adm{level}_display.parquet",
    )


def refresh(doc: dict) -> dict:
    """Update the measured fields of a loaded manifest, in place and in order."""
    if not NAMES.exists():
        sys.exit(f"missing {NAMES}; run tools/build_names.py first")

    names_md = pq.ParquetFile(NAMES).metadata
    footer, page_index = trailing_bytes(NAMES)
    doc["rows"] = names_md.num_rows
    doc["index_version"] = f"{EXTRACTION_DATE}T00:00:00Z"
    index = doc["index"]
    index["size"] = NAMES.stat().st_size
    index["checksum"] = checksum(NAMES)
    index["row_groups"] = names_md.num_row_groups
    index["row_group_rows"] = NAMES_ROW_GROUP_ROWS
    index["footer_bytes"] = footer + page_index
    index["footer_metadata_bytes"] = footer

    for entry in doc["boundaries"]:
        level = entry["level"]
        full_path, display_path = boundary_paths(level)
        if not full_path.exists():
            sys.exit(f"missing {full_path}; run tools/build_boundaries.py first")
        entry["row_group_rows"] = ROW_GROUP_ROWS[level]
        full = file_entry(full_path)
        full["url"] = entry["full"]["url"]
        entry["full"] = {k: full[k] for k in
                         ("url", "size", "row_count", "row_groups",
                          "footer_bytes", "footer_metadata_bytes")}
        if display_path.exists():
            disp = file_entry(display_path)
            # A level that gains a display file for the first time has no URL
            # to preserve, so derive it from the file that exists.
            disp["url"] = (
                entry.get("display", {}).get("url")
                or f"../adm{level}/{display_path.name}"
            )
            entry["display"] = {k: disp[k] for k in
                                ("url", "size", "row_count", "row_groups",
                                 "footer_bytes", "footer_metadata_bytes")}
        elif "display" in entry:
            del entry["display"]

        md_full = pq.ParquetFile(full_path).metadata
        if md_full.num_row_groups and ROW_GROUP_ROWS[level] != md_full.row_group(0).num_rows:
            sys.exit(
                f"level {level}: the built file has "
                f"{md_full.row_group(0).num_rows} rows in its first group but "
                f"gbcommon.ROW_GROUP_ROWS says {ROW_GROUP_ROWS[level]}"
            )
        if "display" in entry:
            md_disp = pq.ParquetFile(display_path).metadata
            if md_disp.num_rows != md_full.num_rows:
                sys.exit(f"level {level}: display row count differs from full")
            if md_disp.num_row_groups != md_full.num_row_groups:
                sys.exit(f"level {level}: display row group count differs from full")
    return doc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the manifest is out of date")
    args = ap.parse_args(argv)

    before = MANIFEST.read_text()
    doc = refresh(json.loads(before))
    after = json.dumps(doc, indent=2) + "\n"

    if args.check:
        if after != before:
            print(f"error  {MANIFEST.relative_to(REPO)} is out of date; "
                  "run python3 tools/make_index_manifest.py")
            return 1
        print(f"OK   {MANIFEST.relative_to(REPO)} matches the built files")
        return 0

    MANIFEST.write_text(after)
    print(f"{MANIFEST.relative_to(REPO)}: {doc['rows']:,} index rows")
    print(
        f"  index   {doc['index']['size']:>12,} bytes, "
        f"{doc['index']['row_groups']:>4} groups of "
        f"{doc['index']['row_group_rows']:>5,}, "
        f"footer_bytes {doc['index']['footer_bytes']:>9,} "
        f"(metadata only {doc['index']['footer_metadata_bytes']:>9,})"
    )
    for entry in doc["boundaries"]:
        for kind in ("full", "display"):
            if kind not in entry:
                continue
            f = entry[kind]
            print(
                f"  L{entry['level']} {kind:<7} {f['size']:>12,} bytes, "
                f"{f['row_groups']:>4} groups of "
                f"{entry['row_group_rows']:>5,}, "
                f"footer_bytes {f['footer_bytes']:>9,} "
                f"(metadata only {f['footer_metadata_bytes']:>9,})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
