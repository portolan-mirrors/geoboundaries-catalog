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
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from gbcommon import (
    NAMES_ROW_GROUP_ROWS,
    PUBLISH,
    ZSTD_LEVEL,
    geo_metadata,
    normalize_name,
)

OUT_DIR = PUBLISH / "names"
OUT = OUT_DIR / "cgaz_names.parquet"


def repair_mojibake(name: str) -> tuple[str, bool]:
    """Undo one round of UTF-8 bytes read as Latin-1, where that applies.

    30 upstream rows carry double-encoded names: the ADM1 file holds
    ``RegiÃ³n de ValparaÃ­so`` where the intended name is ``Región de
    Valparaíso``. The damage is a pure byte-level round trip, so encoding the
    string back to Latin-1 and decoding it as UTF-8 reverses it exactly.

    The repair is applied only to ``name_norm``, never to ``name``. ``name``
    stays byte-for-byte what geoBoundaries publishes, because this catalog is
    a mirror. ``name_norm`` exists to be searched, and a name nobody can type
    is a name nobody can find.

    The guard is narrow. The round trip has to succeed, the result has to
    differ from the input, and the input has to hold one of the mojibake lead
    bytes. Anything else is returned unchanged.
    """
    if not any(c in name for c in ("Ã", "Â", "â€", "Å", "Ä")):
        return name, False
    try:
        repaired = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name, False
    if repaired == name:
        return name, False
    return repaired, True


SQL = """
INSTALL spatial; LOAD spatial;
WITH a0 AS (SELECT * FROM read_parquet('{a0}')),
     a1 AS (SELECT * FROM read_parquet('{a1}')),
     a2 AS (SELECT * FROM read_parquet('{a2}')),
     countries AS (
       SELECT shapeGroup, shapeName AS country_name
       FROM a0 WHERE shapeType = 'ADM0'
     ),
     picked AS (
       SELECT 0::TINYINT AS level, shapeName AS name, NULL::VARCHAR AS shape_id,
              shapeGroup, shapeType AS shape_type, area_km2, geometry
       FROM a0 WHERE shapeType IN ('ADM0', 'DISP') AND shapeName IS NOT NULL
       UNION ALL
       SELECT 1::TINYINT, shapeName, shapeID,
              shapeGroup, shapeType, area_km2, geometry
       FROM a1 WHERE shapeType = 'ADM1' AND shapeName IS NOT NULL
       UNION ALL
       SELECT 2::TINYINT, shapeName, shapeID,
              shapeGroup, shapeType, area_km2, geometry
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
    table = con.execute(SQL.format(a0=a0, a1=a1, a2=a2)).to_arrow_table()
    con.close()

    names = table.column("name").to_pylist()
    repaired_count = 0
    norms = []
    for raw in names:
        fixed, changed = repair_mojibake(raw)
        repaired_count += changed
        norms.append(normalize_name(fixed))

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
        "shape_id", "area_km2", "name_dupes", "bbox", "geometry",
    ]
    table = table.select(order)

    idx = pc.sort_indices(
        table,
        sort_keys=[("name_norm", "ascending"), ("level", "ascending"),
                   ("country", "ascending")],
    )
    table = table.take(idx)

    bbox_col = table.column("bbox").combine_chunks()
    bbox = [
        pc.min(bbox_col.field("xmin")).as_py(),
        pc.min(bbox_col.field("ymin")).as_py(),
        pc.max(bbox_col.field("xmax")).as_py(),
        pc.max(bbox_col.field("ymax")).as_py(),
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
    print(f"  mojibake repaired in name_norm for {repaired_count} rows")
    print(f"  bbox: {[round(v, 6) for v in bbox]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
