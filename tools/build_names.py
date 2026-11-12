#!/usr/bin/env python3
"""Build the name search index sidecar.

    python3 tools/build_names.py

One row per named administrative unit across all three CGAZ levels, sorted by
``name_norm``, with small row groups and a Parquet page index. The point of
the sort is that a client can resolve a typed prefix with HTTP range requests
instead of downloading the file: the row groups a prefix can live in are a
contiguous run, and the page index narrows it further.

Run ``tools/build_boundaries.py`` first. This script reads the published
GeoParquet files rather than the GeoPackages, so the index and the boundaries
cannot disagree.

Which rows are indexed
----------------------
CGAZ is a seamless composite, so a country with no ADM2 data appears in the
ADM2 file carried up from its ADM1 or ADM0 geometry, and the 20 disputed-area
polygons appear in all three files. Indexing every row of every file would
return Antarctica three times for one query.

A row is indexed when the file it sits in is the file that level natively
belongs to, which is the rule ``shapeType`` already encodes:

| file | indexed rows | level |
|---|---|---|
| ADM0 | ``shapeType IN ('ADM0', 'DISP')`` | 0 |
| ADM1 | ``shapeType = 'ADM1'`` | 1 |
| ADM2 | ``shapeType = 'ADM2'`` | 2 |

Rows with no ``shapeName`` are not indexed, because there is nothing to search
for. There are 37 of them, all in the ADM2 file.

``geometry_ref`` -- the ``select()`` fast path
-----------------------------------------------
Every row also carries ``geometry_ref``, a ``{file, row_group, row}`` pointer
into that level's full-resolution boundary file (design doc §6.2/§6.4). The
``row`` is the physical row offset the unit sits at in ``cgaz_adm{level}
.parquet``, captured with DuckDB's ``file_row_number`` option on
``read_parquet`` straight off the published file this script reads -- not
recomputed or assumed from any join -- so it is exactly the row a client's
range-read will land on. ``row_group`` is that offset floor-divided by the
level's fixed row group size (``gbcommon.ROW_GROUP_ROWS``: 4 for ADM0, 64 for
ADM1, 512 for ADM2), which is also what ``tools/build_boundaries.py`` writes
the file with.

The boundary files are Hilbert-sorted, not sorted by ``(country, shapeID)``,
so this reference is **advisory**, never authoritative: a client must verify
the row it reads still carries the expected join key (``shapeID``, or
``shapeGroup`` at level 0, since CGAZ ADM0 has no ``shapeID`` column at all)
and fall back to scanning candidate row groups by statistics on any mismatch.
That is what makes it safe against a version-skewed boundary file, per design
doc §6.4. Because the display files are row-aligned with the full files at
every level that has one (verified directly: same row, same ``shapeID``/
``shapeGroup``, for all of ADM0 and ADM1), the same ``row``/``row_group`` pair
is valid against either file -- a client need not special-case which
resolution it is fetching.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from gbcommon import (
    repair_mojibake,
    shrink_bbox_float32,
    NAMES_ROW_GROUP_ROWS,
    PUBLISH,
    ROW_GROUP_ROWS,
    ZSTD_LEVEL,
    geo_metadata,
    normalize_name,
)

OUT_DIR = PUBLISH / "names"
OUT = OUT_DIR / "cgaz_names.parquet"


SQL = """
INSTALL spatial; LOAD spatial;
WITH a0 AS (
       SELECT * EXCLUDE (file_row_number), file_row_number AS row_index
       FROM read_parquet('{a0}', file_row_number=true)
     ),
     a1 AS (
       SELECT * EXCLUDE (file_row_number), file_row_number AS row_index
       FROM read_parquet('{a1}', file_row_number=true)
     ),
     a2 AS (
       SELECT * EXCLUDE (file_row_number), file_row_number AS row_index
       FROM read_parquet('{a2}', file_row_number=true)
     ),
     countries AS (
       SELECT shapeGroup, shapeName AS country_name
       FROM a0 WHERE shapeType = 'ADM0'
     ),
     picked AS (
       SELECT 0::TINYINT AS level, shapeName AS name, NULL::VARCHAR AS shape_id,
              shapeGroup, shapeType AS shape_type, area_km2, geometry, row_index
       FROM a0 WHERE shapeType IN ('ADM0', 'DISP') AND shapeName IS NOT NULL
       UNION ALL
       SELECT 1::TINYINT, shapeName, shapeID,
              shapeGroup, shapeType, area_km2, geometry, row_index
       FROM a1 WHERE shapeType = 'ADM1' AND shapeName IS NOT NULL
       UNION ALL
       SELECT 2::TINYINT, shapeName, shapeID,
              shapeGroup, shapeType, area_km2, geometry, row_index
       FROM a2 WHERE shapeType = 'ADM2' AND shapeName IS NOT NULL
     )
SELECT
  p.name,
  p.level,
  p.shape_type,
  p.shapeGroup AS country,
  c.country_name,
  p.shape_id,
  round(p.area_km2, 3) AS area_km2,
  {{
    xmin: ST_XMin(p.geometry), ymin: ST_YMin(p.geometry),
    xmax: ST_XMax(p.geometry), ymax: ST_YMax(p.geometry)
  }} AS bbox,
  -- Advisory select() fast path (design doc §6.2/§6.4; see the module
  -- docstring above). `row_index` is the physical offset this exact row
  -- sits at in the published cgaz_adm{{level}}.parquet, captured via
  -- read_parquet(..., file_row_number=true) above -- never recomputed from
  -- a join, so it cannot drift from what a range-read will actually land
  -- on. `row_group` is that offset floor-divided by the level's fixed row
  -- group size (gbcommon.ROW_GROUP_ROWS).
  CASE p.level
    WHEN 0 THEN {{
      file: 'cgaz_adm0.parquet'::VARCHAR,
      row_group: (p.row_index // {rg0})::INTEGER,
      row: p.row_index::BIGINT
    }}
    WHEN 1 THEN {{
      file: 'cgaz_adm1.parquet'::VARCHAR,
      row_group: (p.row_index // {rg1})::INTEGER,
      row: p.row_index::BIGINT
    }}
    WHEN 2 THEN {{
      file: 'cgaz_adm2.parquet'::VARCHAR,
      row_group: (p.row_index // {rg2})::INTEGER,
      row: p.row_index::BIGINT
    }}
  END AS geometry_ref,
  ST_AsWKB(ST_PointOnSurface(p.geometry)) AS geometry
FROM picked p
LEFT JOIN countries c ON p.shapeGroup = c.shapeGroup
"""


def main() -> int:
    a0 = (PUBLISH / "adm0" / "cgaz_adm0.parquet").as_posix()
    a1 = (PUBLISH / "adm1" / "cgaz_adm1.parquet").as_posix()
    a2 = (PUBLISH / "adm2" / "cgaz_adm2.parquet").as_posix()
    for path in (a0, a1, a2):
        if not Path(path).exists():
            sys.exit(f"missing {path}; run tools/build_boundaries.py first")

    con = duckdb.connect()
    table = con.execute(
        SQL.format(
            a0=a0, a1=a1, a2=a2,
            rg0=ROW_GROUP_ROWS[0], rg1=ROW_GROUP_ROWS[1], rg2=ROW_GROUP_ROWS[2],
        )
    ).to_arrow_table()
    con.close()

    # The boundary collections already carry repaired names, so this is an
    # assertion rather than a repair: anything still double-encoded here means
    # the boundary files were not rebuilt.
    names = table.column("name").to_pylist()
    leftover = 0
    norms = []
    for raw in names:
        fixed, changed = repair_mojibake(raw)
        leftover += changed
        norms.append(normalize_name(fixed))
    if leftover:
        raise SystemExit(
            f"{leftover} double-encoded name(s) reached the index; "
            "rerun tools/build_boundaries.py first"
        )

    table = table.append_column("name_norm", pa.array(norms, pa.string()))

    # name_dupes: how many indexed units share this name_norm anywhere in the
    # world. An autocomplete needs it, because a bare name is often not an
    # answer: "Santa Maria" matches dozens of Brazilian municipalities, and a
    # client that does not know that cannot decide whether to disambiguate.
    counts: dict[str, int] = {}
    for n in norms:
        counts[n] = counts.get(n, 0) + 1
    table = table.append_column(
        "name_dupes", pa.array([counts[n] for n in norms], pa.int32())
    )

    # name_norm straight after name, so the file reads the way it sorts.
    order = [
        "name", "name_norm", "level", "shape_type", "country", "country_name",
        "shape_id", "area_km2", "name_dupes", "bbox", "geometry_ref", "geometry",
    ]
    table = table.select(order)

    idx = pc.sort_indices(
        table,
        sort_keys=[("name_norm", "ascending"), ("level", "ascending"),
                   ("country", "ascending")],
    )
    table = table.take(idx)

    # float32 bbox, rounded outward. See shrink_bbox_float32: the index is
    # meant to be loaded whole in a browser, and four doubles per row was
    # 1.9 MB of a 4.4 MB file.
    narrowed = shrink_bbox_float32(table.column("bbox"))
    table = table.set_column(
        table.schema.get_field_index("bbox"), "bbox", narrowed
    )

    bbox_col = table.column("bbox").combine_chunks()
    bbox = [
        float(pc.min(bbox_col.field("xmin")).as_py()),
        float(pc.min(bbox_col.field("ymin")).as_py()),
        float(pc.max(bbox_col.field("xmax")).as_py()),
        float(pc.max(bbox_col.field("ymax")).as_py()),
    ]
    meta = dict(table.schema.metadata or {})
    meta[b"geo"] = geo_metadata(bbox=bbox, geometry_types=["Point"])
    table = table.replace_schema_metadata(meta)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        OUT,
        compression="zstd",
        compression_level=ZSTD_LEVEL,
        row_group_size=NAMES_ROW_GROUP_ROWS,
        write_statistics=True,
        write_page_index=True,
        version="2.6",
    )
    md = pq.ParquetFile(OUT).metadata
    size = OUT.stat().st_size
    print(
        f"names: {OUT.name} {size:,} bytes, {md.num_rows:,} rows, "
        f"{md.num_row_groups} row groups, "
        f"{size / md.num_row_groups / 1024:.0f} KiB per group"
    )
    print("  names arrive already repaired: 0 double-encoded reached here")
    print(f"  bbox: {[round(v, 6) for v in bbox]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
