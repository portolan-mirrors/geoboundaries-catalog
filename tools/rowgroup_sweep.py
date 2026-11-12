#!/usr/bin/env python3
"""Re-tune the boundary files' row group size against what a select() costs.

    python3 tools/rowgroup_sweep.py            # every level, the default grid
    python3 tools/rowgroup_sweep.py 2 --rows 128,256,512
    python3 tools/rowgroup_sweep.py 2 --stats-subset

Why this exists. A client resolving one feature knows its row -- the names
index publishes `geometry_ref` -- so the only question left is how many bytes
the row group holding that row costs. hyparquet has no sub-chunk read: asking
for row 3 of a 512-row group fetches that group's whole geometry column
chunk. So the per-feature cost is set by the row group size and by nothing
else, and shrinking the groups shrinks it linearly.

The cost of shrinking is the footer. Parquet's footer carries one thrift
record per column per row group, and the page index carries one entry per page
per column per row group; both sit at the end of the file and a range client
reads them before it reads any data. Halving the group size doubles them.

So this is a two-term minimization, and the term that matters depends on how
many features a session resolves:

    first select   = trailing bytes (footer + page index) + one row group
    later selects  =                                       one row group

A geocoder session resolves one feature far more often than ten, so this tool
reports both and the decision in `gbcommon.ROW_GROUP_ROWS` minimizes the
first. `tools/measure_reads.mjs` then confirms the chosen size with the reader
a browser actually uses, which is the number that ships in the README.

The variants are written into the staging work tree from the *published*
file, not rebuilt from the GeoPackage, so every variant holds byte-identical
geometry in byte-identical row order and the only difference between them is
the layout under test.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pyarrow.parquet as pq

from gbcommon import PUBLISH, ROW_GROUP_ROWS, WORK, ZSTD_LEVEL

SWEEP = WORK / "sweep"

# Candidate rows per group, per level. Each grid brackets the shipped value so
# the table shows the direction of the tradeoff rather than one point on it.
GRID = {
    0: [1, 2, 4, 8],
    1: [8, 16, 32, 64, 128],
    2: [32, 64, 128, 256, 512],
}

# The columns a client prunes on. Statistics on anything else are footer bytes
# that buy nothing: these files are Hilbert-sorted, so every other column's
# min/max overlaps across every group, and a min and a max of `shapeName` is
# two strings per group per file.
#
# The bbox entries are the struct's **leaf paths**. PyArrow matches
# `write_statistics` against the leaf path, not the top-level column, so
# listing `"bbox"` silently drops statistics from all four leaves -- and those
# four are the GeoParquet 1.1 covering, which is the whole spatial pruning
# mechanism of these files. Measured the wrong way round once; the four leaves
# are cheap (four doubles per group) and load-bearing.
PRUNABLE = [
    "shapeID", "shapeGroup",
    "bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax",
]


def trailing_bytes(path: Path) -> tuple[int, int]:
    """(footer, page index) -- the two spans at the end of the file.

    Parquet writes the page index after the last row group and the thrift
    footer after that, so everything from the end of the last column chunk's
    pages to EOF is metadata. A client that fetches that whole span in one
    exactly-sized request has the footer *and* the page index and needs no
    second round trip, which is what `footer_bytes` in the index manifest is
    for.
    """
    md = pq.ParquetFile(path).metadata
    last = md.row_group(md.num_row_groups - 1)
    end_of_data = 0
    for i in range(last.num_columns):
        col = last.column(i)
        start = col.dictionary_page_offset or col.data_page_offset
        end_of_data = max(end_of_data, start + col.total_compressed_size)
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(-8, 2)
        metadata_len = int.from_bytes(fh.read(8)[:4], "little")
    footer = metadata_len + 8
    return footer, size - end_of_data - footer


def geometry_group_bytes(path: Path) -> tuple[int, int, int]:
    """Median, max and mean compressed bytes of the geometry chunk per group.

    The geometry column is 97% of these files, so this is very nearly what a
    one-feature read costs; `tools/measure_reads.mjs` measures the rest.
    """
    md = pq.ParquetFile(path).metadata
    sizes = []
    for g in range(md.num_row_groups):
        rg = md.row_group(g)
        idx = next(
            i for i in range(rg.num_columns)
            if rg.column(i).path_in_schema == "geometry"
        )
        sizes.append(rg.column(idx).total_compressed_size)
    sizes.sort()
    mid = sizes[len(sizes) // 2]
    return mid, sizes[-1], sum(sizes) // len(sizes)


def write_variant(src: Path, out: Path, rows: int, *, stats_subset: bool) -> Path:
    """Rewrite src with a different row group size, in the same row order."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    reader = pq.ParquetFile(src)
    schema = reader.schema_arrow
    statistics = PRUNABLE if stats_subset else True
    writer = pq.ParquetWriter(
        out,
        schema,
        compression="zstd",
        compression_level=ZSTD_LEVEL,
        write_statistics=statistics,
        write_page_index=True,
        version="2.6",
    )
    try:
        # Batches a multiple of the group size, so every group written is
        # exactly full and row // rows names the group it is in.
        batch = max(rows, (65_536 // rows) * rows)
        for rb in reader.iter_batches(batch_size=batch):
            import pyarrow as pa

            writer.write_table(pa.Table.from_batches([rb]), row_group_size=rows)
    finally:
        writer.close()
    return out


def human(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.2f} MiB"
    return f"{n / 1024:.0f} KiB"


def sweep(level: int, grid: list[int], *, stats_subset: bool) -> list[dict]:
    src = PUBLISH / f"adm{level}" / f"cgaz_adm{level}.parquet"
    if not src.exists():
        sys.exit(f"missing {src}; run tools/build_boundaries.py first")
    rows_total = pq.ParquetFile(src).metadata.num_rows
    out_rows = []
    print(
        f"\nADM{level}: {rows_total:,} rows, source {src.stat().st_size:,} bytes"
        + ("  [statistics restricted to the prunable columns]" if stats_subset else "")
    )
    print(
        f"  {'rows/grp':>9} {'groups':>7} {'size':>12} {'footer':>11} "
        f"{'page idx':>11} {'trailing':>11} {'geom/grp':>11} {'worst grp':>11} "
        f"{'1st select':>12}"
    )
    for rows in grid:
        tag = "s" if stats_subset else "a"
        out = SWEEP / f"adm{level}.rg{rows}{tag}.parquet"
        write_variant(src, out, rows, stats_subset=stats_subset)
        md = pq.ParquetFile(out).metadata
        footer, page_index = trailing_bytes(out)
        gmid, gmax, _ = geometry_group_bytes(out)
        size = out.stat().st_size
        first = footer + page_index + gmid
        rec = {
            "level": level,
            "rows_per_group": rows,
            "groups": md.num_row_groups,
            "size": size,
            "footer": footer,
            "page_index": page_index,
            "trailing": footer + page_index,
            "geometry_median_group": gmid,
            "geometry_max_group": gmax,
            "first_select": first,
            "stats_subset": stats_subset,
            "path": out.as_posix(),
        }
        out_rows.append(rec)
        print(
            f"  {rows:>9,} {md.num_row_groups:>7,} {size:>12,} {footer:>11,} "
            f"{page_index:>11,} {footer + page_index:>11,} {gmid:>11,} "
            f"{gmax:>11,} {first:>12,}"
        )
    best = min(out_rows, key=lambda r: r["first_select"])
    print(
        f"  minimum first-select cost at {best['rows_per_group']:,} rows/group: "
        f"{human(best['first_select'])} "
        f"(shipped today: {ROW_GROUP_ROWS[level]:,})"
    )
    return out_rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("levels", nargs="*", type=int)
    ap.add_argument("--rows", help="comma-separated rows-per-group grid")
    ap.add_argument(
        "--stats-subset", action="store_true",
        help="write statistics only for the prunable columns",
    )
    ap.add_argument("--keep", action="store_true", help="keep the variants")
    ap.add_argument("--json", help="write the table to this path")
    args = ap.parse_args(argv)

    levels = args.levels or sorted(GRID)
    results: list[dict] = []
    for level in levels:
        grid = [int(x) for x in args.rows.split(",")] if args.rows else GRID[level]
        results += sweep(level, grid, stats_subset=args.stats_subset)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2) + "\n")
        print(f"\nwritten to {args.json}")
    if not args.keep:
        shutil.rmtree(SWEEP, ignore_errors=True)
        print(f"removed {SWEEP}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
