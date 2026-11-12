#!/usr/bin/env python3
"""Build the display-geometry sidecar for each boundary level.

    python3 tools/build_display.py --measure     # tolerance sweep, writes nothing
    python3 tools/build_display.py               # build all levels
    python3 tools/build_display.py 0             # one level

Why this file exists. CGAZ ADM0 is not simplified upstream -- the vertex
reduction in the geoBoundaries build applies to ADM1 and ADM2 only -- so a
single country outline can be half a million coordinates. A browser that
decodes the United Kingdom from the full-resolution file to draw one highlight
stops responding. This sidecar is the same rows with geometry a browser can
decode in milliseconds.

Three properties make it a drop-in parallel read:

* identical row count, identical row order, and identical row group
  boundaries, so row *i* and row group *g* mean the same thing in both files
  and a client can issue the same byte-range plan against either;
* the same identity columns, so a hit resolved in the names index joins to
  this file exactly as it joins to the full-resolution one;
* its own GeoParquet 1.1 bbox covering column, so it prunes on its own.

**The geometry is deliberately outward-biased.** Simplification alone cuts
corners inward, and a shape used as a spatial filter that sits *inside* the
true boundary silently drops features near the edge. So every geometry is
simplified and then buffered outward by the same distance:

    ST_Buffer(ST_SimplifyPreserveTopology(geom, tol), tol, QUADRANT_SEGMENTS)

The result contains essentially all of the original and a margin beyond it.
Over-fetching is cheap; a missing edge feature is a wrong answer. These are
display and filter shapes, not cartographic boundaries: neighbouring units
overlap in the margin, and nothing here should be used to measure area, to
decide which side of a border a point falls on, or to publish a map that
claims to show a boundary.

**The buffer is in degrees, so it is not isotropic on the ground.** One degree
of latitude is about 111 km everywhere, but one degree of longitude is
111*cos(latitude) km, so a 0.01 degree buffer is about 1.1 km north-south
everywhere and about 1.1 km east-west at the equator but only 0.55 km at 60
degrees north. The margin therefore narrows east-west towards the poles. It
is still outward everywhere, which is the property that matters.
"""
from __future__ import annotations

import argparse
import sys

from pathlib import Path

import duckdb
import pyarrow.compute as pc
import pyarrow.parquet as pq

from gbcommon import PUBLISH, ROW_GROUP_ROWS, ZSTD_LEVEL, geo_metadata

# Simplification tolerance in degrees, per level, chosen with --measure. See
# docs/changes-from-upstream.md for the sweep these came from.
#
# ADM2 has no display file, and that is a measurement rather than an
# omission. Its geometry is already simplified by geoBoundaries: the median
# unit is 82 vertices, the 90th percentile 560 and the 99th 2,837, and only
# 14 rows of 49,349 exceed 20,000. Decoding one unit from the full-resolution
# file is already well under a millisecond. Any tolerance coarse enough to
# shrink the file meaningfully also puts a buffer of a kilometre or more
# around units that are only a few kilometres across, which is a poor trade
# for a level where nothing was slow.
TOLERANCE = {0: 0.01, 1: 0.01}

# Quadrant segments for the outward buffer. The default of 8 rounds every
# corner with eight segments and inflates the vertex count past what
# simplification just removed, which defeats the point of the file. 2 keeps a
# corner cheap while still bulging outward rather than cutting across.
QUADRANT_SEGMENTS = 2

IDENTITY = {
    0: ["shapeName", "shapeGroup", "shapeType"],
    1: ["shapeName", "shapeID", "shapeGroup", "shapeType"],
}


def source(level: int) -> str:
    return (PUBLISH / f"adm{level}" / f"cgaz_adm{level}.parquet").as_posix()


# The tolerance is capped per feature at a fraction of the unit's own linear
# size. A flat 0.01 degrees is about 1.1 km, which is nothing against a
# country and almost everything against Sliema, a Maltese local council 1.3
# km2 in area: a flat tolerance cost it 8% of its area and Baiti in Nauru
# 9%. Scaling by sqrt(area)/25 keeps the displacement under about 4% of a
# unit's width whatever its size, and leaves large units on the flat 0.01.
# The floor stops a degenerate zero-area row collapsing the expression.
PER_FEATURE_TOLERANCE = (
    "greatest(1e-6, least({tol}, sqrt(ST_Area(geometry)) / 25))"
)


def display_geometry_sql(tol: float) -> str:
    t = PER_FEATURE_TOLERANCE.format(tol=tol)
    return f"ST_Buffer(ST_SimplifyPreserveTopology(geometry, {t}), {t}, {QUADRANT_SEGMENTS})"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET preserve_insertion_order = true;")
    return con


def measure(level: int, tolerances: list[float]) -> None:
    """Report vertices and validity per candidate tolerance. Writes nothing."""
    con = connect()
    src = source(level)
    base = con.execute(
        f"""SELECT count(*), sum(ST_NPoints(geometry)),
                   max(ST_NPoints(geometry))
            FROM read_parquet('{src}')"""
    ).fetchone()
    print(
        f"ADM{level}: {base[0]:,} rows, {base[1]:,} vertices, "
        f"max {base[2]:,} per feature"
    )
    for tol in tolerances:
        geom = display_geometry_sql(tol)
        row = con.execute(
            f"""WITH d AS (SELECT {geom} AS g, geometry AS o
                           FROM read_parquet('{src}'))
                SELECT sum(ST_NPoints(g)), max(ST_NPoints(g)),
                       count(*) FILTER (WHERE ST_IsEmpty(g)),
                       count(*) FILTER (WHERE NOT ST_IsValid(g)),
                       count(*) FILTER (WHERE NOT ST_Covers(g, o))
                FROM d"""
        ).fetchone()
        print(
            f"  tol {tol:<7} vertices {row[0]:>11,}  max/feature {row[1]:>8,}"
            f"  empty {row[2]}  invalid {row[3]}  not-covering {row[4]}"
        )
    con.close()


def build(level: int) -> None:
    tol = TOLERANCE[level]
    src = source(level)
    cols = IDENTITY[level]
    geom = display_geometry_sql(tol)
    print(f"ADM{level}: display geometry, tolerance {tol} degrees")

    con = connect()
    table = con.execute(
        f"""
        WITH d AS (
          SELECT {', '.join(cols)}, {geom} AS g
          FROM read_parquet('{src}')
        )
        SELECT {', '.join(cols)},
          {{xmin: ST_XMin(g), ymin: ST_YMin(g),
            xmax: ST_XMax(g), ymax: ST_YMax(g)}} AS bbox,
          ST_AsWKB(g) AS geometry
        FROM d
        """
    ).to_arrow_table()
    con.close()

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

    out = PUBLISH / f"adm{level}" / f"cgaz_adm{level}_display.parquet"
    pq.write_table(
        table,
        out,
        compression="zstd",
        compression_level=ZSTD_LEVEL,
        # The same row group size as the full-resolution file, so row group g
        # holds the same rows in both and a client can plan one set of ranges.
        row_group_size=ROW_GROUP_ROWS[level],
        write_statistics=True,
        write_page_index=True,
        version="2.6",
    )
    verify(level, out)


def verify(level: int, out) -> None:
    """Row alignment, validity, and how much of the original is retained."""
    full = pq.ParquetFile(source(level)).metadata
    disp = pq.ParquetFile(out).metadata
    if full.num_rows != disp.num_rows:
        raise SystemExit("row count drifted from the full-resolution file")
    if full.num_row_groups != disp.num_row_groups:
        raise SystemExit("row group count drifted")
    for i in range(full.num_row_groups):
        if full.row_group(i).num_rows != disp.row_group(i).num_rows:
            raise SystemExit(f"row group {i} holds a different number of rows")

    con = connect()
    # POSITIONAL JOIN pairs row i with row i, which is the alignment the file
    # promises, so this verifies the promise rather than assuming it.
    stats = con.execute(
        f"""
        WITH j AS (
          SELECT f.shapeName AS fname, d.shapeName AS dname,
                 f.geometry AS o, d.geometry AS g
          FROM read_parquet('{source(level)}') f
          POSITIONAL JOIN read_parquet('{out.as_posix()}') d
        ),
        m AS (
          SELECT fname, dname, ST_NPoints(g) AS v, ST_IsEmpty(g) AS empty,
                 NOT ST_IsValid(g) AS invalid,
                 CASE WHEN ST_Area(o) > 0
                      THEN ST_Area(ST_Intersection(g, o)) / ST_Area(o)
                      ELSE 1.0 END AS retained
          FROM j
        )
        SELECT count(*) FILTER (WHERE fname IS DISTINCT FROM dname),
               sum(v), max(v), count(*) FILTER (WHERE empty),
               count(*) FILTER (WHERE invalid),
               min(retained), count(*) FILTER (WHERE retained < 0.99)
        FROM m
        """
    ).fetchone()
    worst = con.execute(
        f"""
        WITH j AS (
          SELECT f.shapeName AS n, f.shapeGroup AS grp,
                 f.geometry AS o, d.geometry AS g
          FROM read_parquet('{source(level)}') f
          POSITIONAL JOIN read_parquet('{out.as_posix()}') d
        )
        SELECT n, grp,
               round(ST_Area(ST_Intersection(g, o)) / ST_Area(o) * 100, 4)
        FROM j WHERE ST_Area(o) > 0
        ORDER BY ST_Area(ST_Intersection(g, o)) / ST_Area(o) LIMIT 5
        """
    ).fetchall()
    con.close()

    misaligned, verts, maxv, empty, invalid, worst_frac, below99 = stats
    size = out.stat().st_size
    full_size = Path(source(level)).stat().st_size
    print(
        f"  {disp.num_rows:,} rows in {disp.num_row_groups} row groups, "
        f"aligned with the full-resolution file ({misaligned} mismatched name)"
    )
    print(
        f"  {size:,} bytes, {full_size / size:.1f}x smaller than full "
        f"resolution ({full_size:,})"
    )
    print(
        f"  vertices {verts:,} (max {maxv:,} per feature), "
        f"empty {empty}, invalid {invalid}"
    )
    print(
        f"  area of the original retained: worst {worst_frac * 100:.4f}%, "
        f"{below99} feature(s) under 99%"
    )
    for name, grp, pct in worst:
        print(f"    {pct:8.4f}%  {name} ({grp})")
    if empty or misaligned:
        raise SystemExit("display geometry is empty, or rows are misaligned")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--measure", action="store_true")
    args = ap.parse_args(argv)
    levels = args.levels or sorted(TOLERANCE)
    for level in levels:
        if args.measure:
            measure(level, [0.02, 0.01, 0.005, 0.002, 0.001])
        else:
            build(level)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
