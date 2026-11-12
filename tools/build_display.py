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

from gbcommon import (
    PRUNABLE_STATS,
    PUBLISH,
    ROW_GROUP_ROWS,
    ZSTD_LEVEL,
    geo_metadata,
    trailing_bytes,
)

# Simplification tolerance in degrees, per level, chosen with --measure. See
# docs/changes-from-upstream.md for the sweep these came from.
#
# **Why ADM2 now has a display file.** The first pass left it out, and the
# reasoning was sound about the wrong quantity. ADM2 geometry is already
# simplified upstream -- median 82 vertices, 90th percentile 560 -- so
# *decoding* one unit was never slow, and that is what the old comment here
# measured. But a client does not decode one unit from an isolated byte range.
# hyparquet has no sub-chunk read, so fetching one ADM2 feature pulls that row
# group's whole geometry column chunk: measured against the live catalog, a
# median of 1.35 MB and 2.1 s, worst case 3.5 MB and 4.3 s. The cost was never
# vertices per feature, it was **bytes per row group read**, and it is the tail
# that fills a group -- the 99th percentile at 2,837 vertices and the 14 rows
# above 20,000, not the median 82.
#
# Simplifying ADM2 at the tolerance below cuts 12,980,126 vertices to
# 2,854,112, a 4.5x reduction, and a 256-row group's geometry chunk from
# 324,655 bytes to about 155,000. That is the file this level was missing.
TOLERANCE = {0: 0.01, 1: 0.01, 2: 0.01}

# Quadrant segments for the outward buffer. The default of 8 rounds every
# corner with eight segments and inflates the vertex count past what
# simplification just removed, which defeats the point of the file. 2 keeps a
# corner cheap while still bulging outward rather than cutting across.
QUADRANT_SEGMENTS = 2

IDENTITY = {
    0: ["shapeName", "shapeGroup", "shapeType"],
    1: ["shapeName", "shapeID", "shapeGroup", "shapeType"],
    2: ["shapeName", "shapeID", "shapeGroup", "shapeType"],
}


def source(level: int) -> str:
    return (PUBLISH / f"adm{level}" / f"cgaz_adm{level}.parquet").as_posix()


# The tolerance is capped per feature at a fraction of the unit's own linear
# size. A flat 0.01 degrees is about 1.1 km, which is nothing against a
# country and almost everything against Sliema, a Maltese local council 1.3
# km2 in area: a flat tolerance cost it 8% of its area and Baiti in Nauru
# 9%. Scaling by sqrt(area)/DIVISOR keeps the displacement under 1/DIVISOR of
# a unit's width whatever its size, and leaves large units on the flat 0.01.
# The floor stops a degenerate zero-area row collapsing the expression.
PER_FEATURE_TOLERANCE = (
    "greatest(1e-6, least({tol}, sqrt(ST_Area(geometry)) / {divisor}))"
)

# The denominator of that fraction, per level: the outline may move by at most
# 1/DIVISOR of sqrt(area). 25 is 4% of a unit's width, and is what ADM0 and
# ADM1 ship.
#
# ADM2 uses 18, about 5.6%, and the extra came from the byte budget: a 256-row
# group has to land near 150 KB for the file to be worth fetching at all, and
# 25 left the median group at 165 KB. The sweep over all 49,349 features, with
# "worst" the smallest fraction of any one unit's true area that its display
# polygon still contains:
#
#   divisor  file size  vertices   geom/grp median  worst containment  <99%
#        25   44.92 MB  3,035,819         165 KiB           99.332%       0
#        20   43.11 MB  2,903,755         156 KiB           99.042%       0
#        18   42.42 MB  2,854,112         151 KiB           99.146%       0  <-
#        16   41.79 MB  2,807,029         147 KiB           98.883%       1
#        15   41.50 MB  2,784,942         146 KiB           99.050%       0
#
# Containment is not monotonic in the divisor -- 16 drops one feature below
# 99% where 15 drops none -- because a coarser simplification can remove the
# very vertex whose corner the buffer then fails to cover. That is a reason to
# stop at the first divisor that meets the byte target with margin rather than
# to ride the aggressive end of a non-monotonic curve, which is why this is 18
# and not 15.
#
# ST_ReducePrecision was tried as a cheaper lever -- snapping coordinates to a
# grid makes the float64 mantissas repetitive and compresses far better -- and
# rejected: it raises `TopologyException: side location conflict` on the ADM2
# geometry at both 1e-4 and 3e-4.
TOLERANCE_DIVISOR = {0: 25, 1: 25, 2: 18}


def display_geometry_sql(tol: float, divisor: int = 25) -> str:
    t = PER_FEATURE_TOLERANCE.format(tol=tol, divisor=divisor)
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
        geom = display_geometry_sql(tol, TOLERANCE_DIVISOR[level])
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
    divisor = TOLERANCE_DIVISOR[level]
    src = source(level)
    cols = IDENTITY[level]
    geom = display_geometry_sql(tol, divisor)
    print(
        f"ADM{level}: display geometry, tolerance {tol} degrees capped at "
        f"sqrt(area)/{divisor}"
    )

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
        # Statistics only where a client can prune, the same list the
        # full-resolution file uses. See gbcommon.PRUNABLE_STATS: the trailing
        # metadata is a term in every first select, and these files are
        # Hilbert-sorted, so nothing else prunes.
        write_statistics=PRUNABLE_STATS,
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

    # What a client actually pays for one feature: the trailing metadata once,
    # then one row group's geometry chunk. hyparquet has no sub-chunk read, so
    # the per-group figure is the per-feature figure and it is the number this
    # file exists to lower.
    footer, page_index = trailing_bytes(out)
    groups = []
    for g in range(disp.num_row_groups):
        rg = disp.row_group(g)
        idx = next(
            i for i in range(rg.num_columns)
            if rg.column(i).path_in_schema == "geometry"
        )
        groups.append(rg.column(idx).total_compressed_size)
    groups.sort()
    median_group = groups[len(groups) // 2]
    p95 = groups[int(0.95 * len(groups))]
    print(
        f"  trailing metadata {footer + page_index:,} bytes "
        f"(footer {footer:,} + page index {page_index:,})"
    )
    print(
        f"  geometry per row group: median {median_group / 1024:,.0f} KiB, "
        f"p95 {p95 / 1024:,.0f} KiB, max {groups[-1] / 1024:,.0f} KiB"
    )
    print(
        f"  one feature costs {median_group / 1024:,.0f} KiB, a first select "
        f"{(footer + page_index + median_group) / 1024:,.0f} KiB"
    )

    if empty or misaligned:
        raise SystemExit("display geometry is empty, or rows are misaligned")
    # Containment is the guarantee this file makes, so a breach fails the
    # build rather than being printed and shipped. The outward buffer is what
    # makes it hold; a feature under 99% means the simplification removed a
    # vertex the buffer then failed to cover, and the tolerance divisor for
    # that level has to come down.
    if below99:
        raise SystemExit(
            f"{below99} feature(s) retain under 99% of their true area -- "
            f"lower TOLERANCE_DIVISOR[{level}] (currently "
            f"{TOLERANCE_DIVISOR[level]})"
        )


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
