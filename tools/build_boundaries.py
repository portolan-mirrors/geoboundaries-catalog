#!/usr/bin/env python3
"""Build the three optimized CGAZ GeoParquet files.

    python3 tools/build_boundaries.py            # all levels
    python3 tools/build_boundaries.py 1 2        # one or more levels

Three stages per level.

1. ``ogr2ogr`` reads the GeoPackage and writes plain GeoParquet. This is the
   only step that touches the GeoPackage, because GDAL reads it far faster
   than anything else available here (about one second per level against
   minutes for a DuckDB spatial scan). It also carries the one correction the
   source needs: the GeoPackages declare ``srs_id = 0``, "Undefined geographic
   SRS", for coordinates that are plainly longitude and latitude in degrees,
   so ``-a_srs EPSG:4326`` *assigns* that CRS. Nothing is reprojected.

2. DuckDB derives the measured columns, builds the bbox struct, and orders the
   rows along a Hilbert curve over the whole globe.

3. PyArrow writes the file. The write is not delegated, because the row group
   size is the point of this catalog: other mirrors of these boundaries put
   all 49,349 ADM2 rows in a single row group, which means a client that wants
   one municipality's geometry reads the entire geometry column chunk. PyArrow
   is the only writer here that honours an exact small row group count and can
   also write the Parquet page index.
"""
from __future__ import annotations

import json
import sys

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from gbcommon import (
    LEVELS,
    repair_name_column,
    PRUNABLE_STATS,
    PUBLISH,
    ROW_GROUP_ROWS,
    WORK,
    ZSTD_LEVEL,
    geo_metadata,
    gpkg_layer,
    run,
    source_path,
    trailing_bytes,
)

# Source attribute columns, in the order the upstream GeoPackage declares them
# minus ``id``, which is present in all three files and NULL in every row of
# all three. Verified:
#   SELECT count(*), count(id) FROM st_read('geoBoundariesCGAZ_ADM2.gpkg');
#   -> 49349, 0
# The CGAZ build script lists ``id`` in its mapshaper ``-drop fields=`` call,
# so the column surviving as an empty one is an artifact of the TopoJSON to
# GeoPackage conversion rather than data. Carrying it would put a column in
# table:columns that a consumer has to reason about and that holds nothing.
SOURCE_COLUMNS = {
    0: ["shapeName", "shapeGroup", "shapeType"],
    1: ["shapeName", "shapeID", "shapeGroup", "shapeType"],
    2: ["shapeName", "shapeID", "shapeGroup", "shapeType"],
}

GLOBAL_BOUNDS = "{min_x: -180, min_y: -90, max_x: 180, max_y: 90}::BOX_2D"

# Rows whose geometry cannot be made valid without deleting the unit, so they
# are published as the upstream release has them. One row in the whole
# release: Kaafu (MDV) in the ADM1 file, a 4-point polygon of zero area.
UNREPAIRABLE = {1: 1}


def stage_raw(level: int) -> None:
    """GeoPackage to plain GeoParquet, with the CRS assigned."""
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"adm{level}.raw.parquet"
    out.unlink(missing_ok=True)
    select = ",".join(SOURCE_COLUMNS[level])
    run(
        [
            "ogr2ogr", "-f", "Parquet", str(out), str(source_path(level)),
            gpkg_layer(level),
            "-a_srs", "EPSG:4326",
            "-nln", f"cgaz_adm{level}",
            "-select", select,
            "-lco", "GEOMETRY_NAME=geometry",
            "-lco", "FID=",
            "-lco", "COMPRESSION=ZSTD",
            "-lco", "GEOMETRY_ENCODING=WKB",
        ]
    )
    print(f"  raw: {out.stat().st_size:,} bytes")


def derive_and_sort(level: int) -> pa.Table:
    """Derive the measured columns and return the table in Hilbert order.

    Every column added here is computed from the published geometry and is
    reproducible by rerunning this query.

    - ``area_km2`` and ``perimeter_km`` come from DuckDB's spheroidal
      measures on the WGS 84 ellipsoid, so they are metres on the ground
      rather than square degrees.
      ``ST_FlipCoordinates`` is not optional. DuckDB's ``ST_Area_Spheroid``
      and ``ST_Perimeter_Spheroid`` read the first ordinate as latitude, so on
      longitude-first data they silently return a wrong number where they
      return one at all. Measured before the flip: Nepal came out as 17,844
      km2 against a true 147,181, and 49 of the 218 ADM0 rows came out NaN.
      After the flip, Nepal is 147,578 km2 and no row is NaN. The flipped
      results also agree to better than 0.01% with
      ``ST_Area(ST_Transform(geometry, 'OGC:CRS84', 'EPSG:6933'))``, which is
      the NSIDC EASE-Grid 2.0 Global projection geoBoundaries says it uses for
      its own published area statistics.
    - ``compactness`` is the Polsby-Popper ratio, 4*pi*A / P**2. It is 1 for a
      circle and falls towards 0 as an outline gets long and ragged, which
      separates archipelagos and river-defined units from blocky inland ones.
    - ``country_units``, at ADM1 and ADM2, counts the rows that share a
      ``shapeGroup`` inside this one file, so it is how many units of this
      level the composite holds for that country. At ADM0 that count is 1 for
      every row and says nothing, so the ADM0 file instead carries
      ``adm1_units`` and ``adm2_units``, counted from the other two files.
    - ``bbox`` is the GeoParquet 1.1 covering struct. A reader uses it to skip
      row groups without decoding any WKB.

    The Hilbert key is taken over the fixed whole-globe envelope rather than
    the data's own extent, so the three levels and the search index are
    ordered on one comparable curve.
    """
    src = (WORK / f"adm{level}.raw.parquet").as_posix()
    has_shape_id = "shapeID" in SOURCE_COLUMNS[level]
    shape_id = "shapeID" if has_shape_id else "NULL::VARCHAR AS shapeID"

    if level == 0:
        # Every shapeGroup in the ADM0 file also appears in the ADM1 and ADM2
        # files, so these joins never widen or narrow the row set. Verified:
        #   SELECT count(*) FROM adm0 WHERE shapeGroup NOT IN
        #     (SELECT shapeGroup FROM adm1);  -> 0
        a1 = (WORK / "adm1.raw.parquet").as_posix()
        a2 = (WORK / "adm2.raw.parquet").as_posix()
        counted = f"""
      SELECT src.*, c1.n::INTEGER AS adm1_units, c2.n::INTEGER AS adm2_units
      FROM src
      LEFT JOIN (SELECT shapeGroup, count(*) n
                 FROM read_parquet('{a1}') GROUP BY 1) c1
        ON src.shapeGroup = c1.shapeGroup
      LEFT JOIN (SELECT shapeGroup, count(*) n
                 FROM read_parquet('{a2}') GROUP BY 1) c2
        ON src.shapeGroup = c2.shapeGroup
        """
        unit_cols = "adm1_units,\n      adm2_units,"
    else:
        counted = """
      SELECT *, count(*) OVER (PARTITION BY shapeGroup)::INTEGER
        AS country_units
      FROM src
        """
        unit_cols = "country_units,"

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    # The row order of a boundary file is a published contract: the names
    # index's `geometry_ref` names a row number in it and each display file
    # has to hold the same rows at the same offsets. `preserve_insertion_order
    # = false` lets the result collector emit an ORDER BY's batches out of
    # order on a parallel scan, which would make a rebuild silently reorder
    # rows -- the exact failure the sibling Overture catalog hit on 4,724
    # locality rows. Forced on for this query, and the ORDER BY below carries
    # a tiebreaker for the same reason.
    con.execute("SET preserve_insertion_order = true;")
    sql = f"""
    WITH raw AS (
      SELECT shapeName, {shape_id}, shapeGroup, shapeType, geometry
      FROM read_parquet('{src}')
    ),
    src AS (
      -- Repair the geometry that is not OGC-valid upstream, and leave the
      -- rest strictly alone. ST_MakeValid can return a GEOMETRYCOLLECTION
      -- holding the repaired polygons plus zero-area lines and points, so
      -- ST_CollectionExtract(..., 3) keeps the polygons; measured, that drops
      -- 0.0 square degrees.
      --
      -- Three branches, and each one earns its place. A row that is already
      -- valid is passed through byte for byte rather than round-tripped
      -- through GEOS. A row whose repair yields no polygon at all keeps its
      -- original geometry, because deleting a unit is worse than carrying an
      -- invalid one: exactly one row in the release does this, Kaafu in the
      -- Maldives, a 4-point polygon of zero area that ST_MakeValid resolves
      -- to a line.
      SELECT * EXCLUDE (geometry),
        CASE
          WHEN ST_IsValid(geometry) THEN geometry
          WHEN NOT ST_IsEmpty(ST_CollectionExtract(ST_MakeValid(geometry), 3))
            THEN ST_CollectionExtract(ST_MakeValid(geometry), 3)
          ELSE geometry
        END AS geometry
      FROM raw
    ),
    counted AS ({counted}),
    measured AS (
      SELECT
        * EXCLUDE (geometry),
        ST_Area_Spheroid(ST_FlipCoordinates(geometry)) / 1e6 AS area_km2,
        ST_Perimeter_Spheroid(ST_FlipCoordinates(geometry)) / 1e3
          AS perimeter_km,
        geometry
      FROM counted
    )
    SELECT
      shapeName,
      shapeID,
      shapeGroup,
      shapeType,
      {unit_cols}
      area_km2,
      perimeter_km,
      CASE WHEN perimeter_km > 0
           THEN 4 * pi() * area_km2 / (perimeter_km * perimeter_km)
           ELSE NULL END AS compactness,
      {{
        xmin: ST_XMin(geometry), ymin: ST_YMin(geometry),
        xmax: ST_XMax(geometry), ymax: ST_YMax(geometry)
      }} AS bbox,
      ST_AsWKB(geometry) AS geometry
    FROM measured
    -- The Hilbert key alone is not a total order: two units with the same
    -- key would be ordered arbitrarily and differently on each rebuild, and
    -- a rebuild that reorders rows stales every display file and every
    -- geometry_ref at once. The tiebreaker makes the order total --
    -- shapeGroup + shapeName is unique at level 0, where CGAZ has no
    -- shapeID, and shapeID is unique at levels 1 and 2 -- so the same
    -- sources produce the same file.
    ORDER BY ST_Hilbert(geometry, {GLOBAL_BOUNDS}), shapeGroup, shapeName,
             shapeID
    """
    repaired = con.execute(
        f"SELECT count(*) FROM read_parquet('{src}') "
        "WHERE NOT ST_IsValid(geometry)"
    ).fetchone()[0]
    table = con.execute(sql).to_arrow_table()
    con.close()
    print(f"  geometry: ST_MakeValid applied to {repaired:,} invalid row(s)")
    if not has_shape_id:
        table = table.drop_columns(["shapeID"])
    return table


def write_optimized(level: int, table: pa.Table) -> None:
    """Write the final file with an exact small row group size."""
    bbox_col = table.column("bbox").combine_chunks()
    bbox = [
        pc.min(bbox_col.field("xmin")).as_py(),
        pc.min(bbox_col.field("ymin")).as_py(),
        pc.max(bbox_col.field("xmax")).as_py(),
        pc.max(bbox_col.field("ymax")).as_py(),
    ]
    meta = dict(table.schema.metadata or {})
    meta[b"geo"] = geo_metadata(
        bbox=bbox, geometry_types=["Polygon", "MultiPolygon"]
    )
    table = table.replace_schema_metadata(meta)

    out_dir = PUBLISH / f"adm{level}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"cgaz_adm{level}.parquet"
    pq.write_table(
        table,
        out,
        compression="zstd",
        compression_level=ZSTD_LEVEL,
        row_group_size=ROW_GROUP_ROWS[level],
        # Statistics only where a client can prune. See
        # gbcommon.PRUNABLE_STATS: at these row group sizes the footer is a
        # term in every first select, and statistics on a Hilbert-sorted
        # file's name and measure columns prune nothing.
        write_statistics=PRUNABLE_STATS,
        write_page_index=True,
        version="2.6",
    )
    meta_out = pq.ParquetFile(out).metadata
    size = out.stat().st_size
    footer, page_index = trailing_bytes(out)
    print(
        f"  ADM{level}: {out.name} {size:,} bytes, "
        f"{meta_out.num_rows:,} rows, {meta_out.num_row_groups} row groups of "
        f"{ROW_GROUP_ROWS[level]:,}, "
        f"{(size - footer - page_index) / meta_out.num_row_groups / 1e3:.0f} KB "
        "per group"
    )
    print(
        f"  trailing metadata: {footer + page_index:,} bytes "
        f"(footer {footer:,} + page index {page_index:,}) -- published as "
        "footer_bytes"
    )
    print(f"  bbox: {json.dumps([round(v, 6) for v in bbox])}")


def verify(level: int) -> None:
    """Assert the two repairs actually took, against the written file."""
    out = PUBLISH / f"adm{level}" / f"cgaz_adm{level}.parquet"
    con = duckdb.connect()
    con.execute("LOAD spatial;")
    invalid, mojibake = con.execute(
        f"""SELECT
              count(*) FILTER (WHERE NOT ST_IsValid(geometry)),
              count(*) FILTER (WHERE shapeName LIKE '%Ã%'
                                  OR shapeName LIKE '%â€%')
            FROM read_parquet('{out.as_posix()}')"""
    ).fetchone()
    con.close()
    if invalid > UNREPAIRABLE.get(level, 0) or mojibake:
        raise SystemExit(
            f"ADM{level}: {invalid} invalid geometry, "
            f"{mojibake} double-encoded name(s) survived the repair"
        )
    print(
        f"  verified: {invalid} invalid geometry "
        f"(expected {UNREPAIRABLE.get(level, 0)}), "
        f"{mojibake} double-encoded names"
    )


def build(level: int) -> None:
    print(f"ADM{level}: building")
    stage_raw(level)
    table = derive_and_sort(level)
    table, pairs = repair_name_column(table, "shapeName")
    print(f"  shapeName: repaired {len(pairs)} double-encoded name(s)")
    write_optimized(level, table)
    verify(level)


def main(argv: list[str]) -> int:
    wanted = [int(a) for a in argv] or list(LEVELS)
    for level in wanted:
        build(level)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
