#!/usr/bin/env python3
"""The names index's ``geometry_ref`` pointers into the boundary files have to
be right.

This is the catalog's load-bearing claim for the ``select()`` fast path
(design doc §6.2/§6.4, ``names/AGENTS.md`` "The geometry_ref fast path, and
why it must be verified"). ``geometry_ref`` names a file, a row group and a
row; a client range-reads that row group and takes that row. If the pointer
is stale or wrong, the client gets **another unit's polygon** and nothing
looks wrong: the geometry is valid, the bbox is plausible, and the map flies
somewhere else. No schema validator catches it -- only resolving the pointer
against the actual boundary files does.

Three things are checked, all against the built files:

1. ``row // row_group_rows`` (the level's fixed row group size, from
   ``gbcommon.ROW_GROUP_ROWS`` and cross-checked against the manifest's own
   ``boundaries[].row_group_rows``) equals the published ``row_group``.
2. The row at that offset in the level's full-resolution boundary file holds
   the expected join key: ``shapeID`` at levels 1 and 2, ``shapeGroup``
   (CGAZ has no ``shapeID`` at level 0) at level 0.
3. Where a display file exists for the level (ADM0, ADM1), the same row
   offset in it holds the same join key -- what makes one pointer valid
   against either file.

This catalog's parquet files carry no ``cnmw:catalog_version`` footer
metadata yet (``names/index.json``'s own notes document that), so unlike
cn-geocoder-overture's version of this test, there is no footer version pin
to check here -- `geocoder-core`'s version-skew check is correspondingly
inert against this catalog today, which is a known, documented gap, not an
oversight.

It needs the built data, which lives outside git (``GB_STAGING``). When the
staging tree is absent it skips, which is what happens in CI. Run it locally
after any rebuild of ``tools/build_names.py``:

    python3 tests/test_index_refs.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

try:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    print("skip: pyarrow is not installed")
    raise SystemExit(0)

from gbcommon import PUBLISH, ROW_GROUP_ROWS  # noqa: E402

MANIFEST = ROOT / "catalog" / "names" / "index.json"
NAMES_PATH = PUBLISH / "names" / "cgaz_names.parquet"
# Sampling rather than exhaustive: resolving every one of 52,398 pointers
# means reading every id column in the catalog for each level repeatedly. A
# systematic fault (an off-by-one in the row_index arithmetic, a level/file
# mismatch) shows up in the first handful of rows, and the seed is fixed so a
# failure is reproducible.
SAMPLE = 2000
SEED = 7

EXPECTED_FILE = {0: "cgaz_adm0.parquet", 1: "cgaz_adm1.parquet", 2: "cgaz_adm2.parquet"}


def main() -> int:
    if not NAMES_PATH.exists():
        print(f"skip: no built index at {NAMES_PATH}; run tools/build_names.py first")
        return 0
    if not MANIFEST.exists():
        print(f"error: {MANIFEST} is missing; run tools/build_names.py")
        return 1

    manifest = json.loads(MANIFEST.read_text())
    errors: list[str] = []

    # 0. The manifest's own row_group_rows must agree with the constant the
    #    boundary files were actually written with -- otherwise a client
    #    that trusts the manifest computes the wrong row_group.
    by_level = {b["level"]: b for b in manifest["boundaries"]}
    for level, expected_rows in ROW_GROUP_ROWS.items():
        declared = by_level.get(level, {}).get("row_group_rows")
        if declared != expected_rows:
            errors.append(
                f"level {level}: manifest row_group_rows={declared!r}, "
                f"gbcommon.ROW_GROUP_ROWS={expected_rows!r}"
            )
    if not errors:
        print(f"OK   manifest row_group_rows agrees with gbcommon.ROW_GROUP_ROWS: {ROW_GROUP_ROWS}")

    table = pq.read_table(
        NAMES_PATH, columns=["name", "level", "country", "shape_id", "geometry_ref"]
    )
    refs = table.filter(pc.invert(pc.is_null(table.column("geometry_ref"))))
    print(f"OK   {refs.num_rows:,} of {table.num_rows:,} rows carry a geometry_ref")
    if refs.num_rows != table.num_rows:
        errors.append(
            f"{table.num_rows - refs.num_rows:,} row(s) carry no geometry_ref "
            "at all -- every indexed row should have one"
        )

    rows = refs.to_pylist()
    random.seed(SEED)
    sample = random.sample(rows, min(SAMPLE, len(rows)))
    by_level_sample: dict[int, list[dict]] = {}
    for row in sample:
        by_level_sample.setdefault(row["level"], []).append(row)

    checked = 0
    for level in sorted(by_level_sample):
        items = by_level_sample[level]
        full_path = PUBLISH / f"adm{level}" / f"cgaz_adm{level}.parquet"
        if not full_path.exists():
            print(f"skip: {full_path} is not built")
            continue
        id_column = "shapeGroup" if level == 0 else "shapeID"
        full_ids = pq.read_table(full_path, columns=[id_column]).column(id_column).to_pylist()

        display_path = PUBLISH / f"adm{level}" / f"cgaz_adm{level}_display.parquet"
        display_ids = None
        if display_path.exists():
            display_ids = pq.read_table(display_path, columns=[id_column]).column(id_column).to_pylist()

        row_group_rows = ROW_GROUP_ROWS[level]
        for row in items:
            ref = row["geometry_ref"]
            expected_key = row["country"] if level == 0 else row["shape_id"]

            if ref["file"] != EXPECTED_FILE[level]:
                errors.append(
                    f"level {level}: geometry_ref.file is {ref['file']!r}, "
                    f"expected {EXPECTED_FILE[level]!r}"
                )
                continue

            index, group = ref["row"], ref["row_group"]
            if not 0 <= index < len(full_ids):
                errors.append(f"level {level}: row {index} is out of range")
                continue
            if index // row_group_rows != group:
                errors.append(
                    f"level {level}: row {index} is in row group "
                    f"{index // row_group_rows}, not the published {group}"
                )
            if full_ids[index] != expected_key:
                errors.append(
                    f"level {level}: geometry_ref for {row['name']!r} points "
                    f"at row {index}, which holds {id_column}={full_ids[index]!r} "
                    f"and not {expected_key!r}"
                )
            if display_ids is not None and display_ids[index] != expected_key:
                errors.append(
                    f"level {level}: the display file holds "
                    f"{id_column}={display_ids[index]!r} at row {index}, where "
                    f"the full file holds {expected_key!r}"
                )
            checked += 1
        print(f"OK   level {level}: {len(items):,} pointer(s) resolve against {full_path.name}" + (f" and {display_path.name}" if display_ids is not None else ""))

    if errors:
        print("\n".join(f"error  {e}" for e in errors))
        return 1
    print(
        f"OK: {checked:,} sampled geometry_ref(s) resolve to the right unit "
        f"in every available file"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
