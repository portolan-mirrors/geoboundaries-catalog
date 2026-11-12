#!/usr/bin/env python3
"""Shared constants and helpers for the geoBoundaries CGAZ build.

Nothing here touches the published catalog. The build reads the upstream
GeoPackages from ``sources/`` under the staging root and writes data files to
``publish/`` under the same root, which ``catalog.publish.yaml`` names as
``data_dir``. ``tools/publish.py`` never reads that tree, so the publish
boundary is unchanged.
"""
from __future__ import annotations

import json
import os
import subprocess
import unicodedata
from pathlib import Path

# The staging root. Override with GB_STAGING. It sits outside the repository
# because the files are hundreds of megabytes and git keeps every version of a
# binary forever.
_DEFAULT_STAGING = Path(__file__).resolve().parents[2] / "geoboundaries-staging"
STAGING = Path(os.environ.get("GB_STAGING", _DEFAULT_STAGING))
SOURCES = STAGING / "sources"
WORK = STAGING / "work"
PUBLISH = STAGING / "publish"

# The upstream release. CGAZ is served from the default branch of the
# geoBoundaries core repository through git-lfs, so a URL alone does not pin a
# version. SOURCE_COMMIT is the commit that last changed any file under
# releaseData/CGAZ, found with:
#
#   gh api "repos/wmgeolab/geoBoundaries/commits?path=releaseData/CGAZ&per_page=1"
#
SOURCE_REPO = "https://github.com/wmgeolab/geoBoundaries"
SOURCE_COMMIT = "4004e96433a2bdc54cac2b88d7d2e694c89cb818"
SOURCE_COMMIT_DATE = "2024-04-20T10:23:58Z"
EXTRACTION_DATE = "2026-11-12"

LEVELS = (0, 1, 2)


def source_url(level: int) -> str:
    return (
        f"{SOURCE_REPO}/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM{level}.gpkg"
    )


def source_path(level: int) -> Path:
    return SOURCES / f"geoBoundariesCGAZ_ADM{level}.gpkg"


def gpkg_layer(level: int) -> str:
    return f"globalADM{level}"


# Rows per row group, per level. This is the most consequential number in the
# catalog, because hyparquet -- the reader a browser uses -- has no sub-chunk
# read: asking for row 3 of a 512-row group fetches that group's whole
# geometry column chunk. One feature costs one row group, so the group size
# *is* the per-feature cost.
#
# Shrinking the groups is not free. Parquet's footer carries one thrift record
# per column per row group and the page index one entry per page per column
# per row group; both sit at the end of the file and a range client reads them
# before any data. Halving the group size doubles them. A client pays two
# terms:
#
#     first select  = trailing bytes (footer + page index) + one row group
#     later selects =                                        one row group
#
# A geocoder session resolves one feature far more often than ten, so these
# minimize the first. `tools/rowgroup_sweep.py` produced the table, measured
# against the published files with statistics restricted to PRUNABLE_STATS:
#
#   level  rows/grp  groups  trailing  geom/grp  first select
#   ADM0          1     218   348,440   253,427       601,867  <- chosen
#   ADM0          2     109   175,837   737,734       913,571
#   ADM0          4      55    90,369 1,453,199     1,543,568  (shipped before)
#   ADM1          8     403   701,108    90,209       791,317
#   ADM1         16     202   353,080   223,000       576,080  <- chosen
#   ADM1         32     101   177,863   436,226       614,089
#   ADM1         64      51    93,073   962,786     1,055,859  (shipped before)
#   ADM2        128     386   690,487   160,070       850,557
#   ADM2        256     193   346,581   324,655       671,236  <- chosen
#   ADM2        512      97   175,681   654,394       830,075  (shipped before)
#
# The cost is file size: smaller groups compress worse, so ADM0 grows about
# 7.9%, ADM1 7.5% and ADM2 3.8%. These files exist to be range-read one
# feature at a time from a browser. The whole-file download is the secondary
# use, and the upstream GeoPackage serves it better anyway -- see the README's
# "The upstream data vs our optimized files".
#
# ADM0 at one row per group is deliberate rather than degenerate: there are
# 218 countries, a country is the unit a client asks for, and one row group
# per country is 218 groups. `gpio check` warns about it; see
# docs/conformance.md.
ROW_GROUP_ROWS = {0: 1, 1: 16, 2: 256}

# The columns that get row group statistics in the boundary and display files.
#
# Everything else is footer bytes that buy nothing. These files are
# Hilbert-sorted, so `shapeName`, `area_km2`, `perimeter_km`, `compactness`,
# `country_units` and `shapeType` have min/max ranges overlapping across
# essentially every row group -- a client cannot prune on them -- while a min
# and a max of `shapeName` is two strings per group per file. Measured on ADM2
# at 256 rows per group: restricting statistics to this list cut the trailing
# bytes from 670,381 to 346,581, which is 324 KB off every client's first
# select.
#
# The `bbox` entries are the struct's **leaf** paths. PyArrow matches
# `write_statistics` against the leaf path, not the top-level column, so
# listing `"bbox"` silently drops statistics from all four leaves -- and those
# four are the GeoParquet 1.1 covering, the only spatial pruning these files
# offer. Measured the wrong way round once; the four leaves are four doubles
# per group and load-bearing.
PRUNABLE_STATS = [
    "shapeID",
    "shapeGroup",
    "bbox.xmin",
    "bbox.ymin",
    "bbox.xmax",
    "bbox.ymax",
]

# The search index is sorted by name_norm, so a client that wants a name
# prefix fetches a contiguous run of row groups. The target is bytes, not
# rows: a row group of 100-150 KiB is what makes a prefix lookup a 5-25 ms
# range request, and doubling the group size doubles both the latency and the
# bytes fetched. At this schema's measured 83.7 compressed bytes per row,
# 1,536 rows lands a group at about 129 KiB.
#
#   python3 -c "import pyarrow.parquet as pq, os; p='cgaz_names.parquet'; \
#     print(os.path.getsize(p) / pq.read_metadata(p).num_rows)"
NAMES_ROW_GROUP_ROWS = 1536
NAMES_ROW_GROUP_TARGET_KIB = (100, 150)

ZSTD_LEVEL = 15


def run(cmd: list[str] | str, **kw) -> None:
    """Run a command, echo it, and fail loudly."""
    shell = isinstance(cmd, str)
    printable = cmd if shell else " ".join(cmd)
    print(f"  $ {printable}", flush=True)
    subprocess.run(cmd, shell=shell, check=True, **kw)


# The lead sequences a double-encoded UTF-8 string can start a damaged
# character with. The guard is a cheap pre-filter; the round trip below is
# what actually decides.
MOJIBAKE_LEADS = ("Ã", "Â", "â€", "Å", "Ä")


def repair_mojibake(name: str) -> tuple[str, bool]:
    """Undo one round of UTF-8 bytes read as Latin-1, where that applies.

    38 rows of the upstream release carry double-encoded names: the ADM1 file
    holds ``RegiÃ³n de ValparaÃ­so`` where the intended name is ``Región de
    Valparaíso``. The damage is a pure byte-level round trip, so encoding the
    string back to Latin-1 and decoding it as UTF-8 reverses it exactly.

    The guard is narrow. The round trip has to succeed, the result has to
    differ from the input, and the input has to hold one of the mojibake lead
    sequences. Anything else is returned unchanged, which is why legitimate
    Nordic names such as ``Äänekoski`` pass through: ``Ä`` is a lead sequence,
    but ``Äänekoski`` encoded to Latin-1 is not valid UTF-8, so the round trip
    raises and the name is kept.

    All 38 hits were inspected by hand and are listed in
    docs/changes-from-upstream.md. There is no false positive.
    """
    if not any(lead in name for lead in MOJIBAKE_LEADS):
        return name, False
    try:
        repaired = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name, False
    if repaired == name:
        return name, False
    return repaired, True


def repair_name_column(table, column: str):
    """Apply repair_mojibake to one string column of an Arrow table."""
    import pyarrow as pa

    values = table.column(column).to_pylist()
    repaired, pairs = [], []
    for raw in values:
        if raw is None:
            repaired.append(None)
            continue
        fixed, changed = repair_mojibake(raw)
        repaired.append(fixed)
        if changed:
            pairs.append((raw, fixed))
    table = table.set_column(
        table.schema.get_field_index(column), column,
        pa.array(repaired, pa.string()),
    )
    return table, pairs


def normalize_name(name: str | None) -> str | None:
    """Lowercase and strip accents, for prefix matching on a sorted column.

    NFKD decomposes a precomposed accented character into its base character
    plus a combining mark; dropping category ``Mn`` removes the mark. ``Cote
    d'Ivoire`` and ``Côte d'Ivoire`` therefore normalize to the same string.
    Characters with no Latin decomposition, such as Han or Cyrillic, pass
    through lowercased and otherwise unchanged.
    """
    if name is None:
        return None
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", stripped).casefold().strip()


def shrink_bbox_float32(bbox_array):
    """Recast a float64 bbox struct to float32, rounding outward.

    Halves what the bbox costs in a file small enough that a browser loads
    the whole thing, which is the search index's primary consumption mode. A
    naive cast is not safe: float32 rounds to nearest, so an xmin could round
    *up* and leave part of the geometry outside the bbox that claims to cover
    it, which silently breaks both row group pruning and a map fly-to. So
    each minimum is nudged towards -inf and each maximum towards +inf
    whenever the cast moved it the wrong way. The resulting box is never
    smaller than the true one, which is what GeoParquet's covering requires.

    float32 holds about 7 significant decimal digits, so a degree value keeps
    roughly 1e-5 degrees, about a metre. That is far finer than CGAZ's
    simplified geometry.
    """
    import numpy as np
    import pyarrow as pa

    def outward(values, towards):
        exact = np.asarray(values, dtype=np.float64)
        cast = exact.astype(np.float32)
        wrong = (cast > exact) if towards < 0 else (cast < exact)
        if wrong.any():
            cast[wrong] = np.nextafter(
                cast[wrong], np.float32(towards * np.inf)
            )
        return pa.array(cast, pa.float32())

    bbox_array = bbox_array.combine_chunks()
    return pa.StructArray.from_arrays(
        [
            outward(bbox_array.field("xmin").to_numpy(zero_copy_only=False), -1),
            outward(bbox_array.field("ymin").to_numpy(zero_copy_only=False), -1),
            outward(bbox_array.field("xmax").to_numpy(zero_copy_only=False), +1),
            outward(bbox_array.field("ymax").to_numpy(zero_copy_only=False), +1),
        ],
        names=["xmin", "ymin", "xmax", "ymax"],
    )


def trailing_bytes(path: Path) -> tuple[int, int]:
    """``(footer_metadata, page_index)`` -- the two metadata spans at the end.

    Parquet writes the page index after the last row group and the thrift
    footer after that, so everything from the end of the last column chunk's
    pages to EOF is metadata and nothing else. A client that fetches that
    whole span in one exactly-sized request holds the footer *and* the page
    index and needs no second round trip. That total is what
    ``names/index.json`` publishes as ``footer_bytes``.

    The first element is the thrift footer alone -- the ``FileMetaData``
    message plus its four-byte length and the trailing ``PAR1``. It is the
    *minimum* exact tail a reader needs, and it is published separately as
    ``footer_metadata_bytes`` because hyparquet never reads the page index
    bodies: it has no sub-chunk read, so a hyparquet client can ask for this
    smaller number and skip the page index entirely. Both numbers are exact,
    so either way the read is one request rather than hyparquet's speculative
    512 KiB tail.

    ``file_offset`` is optional in the format and PyArrow writes 0 for it, so
    a chunk's start is taken from its dictionary page where it has one and
    from its first data page otherwise.
    """
    import pyarrow.parquet as pq

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


def geo_metadata(
    *,
    geometry_column: str = "geometry",
    bbox_column: str = "bbox",
    bbox: list[float],
    geometry_types: list[str],
) -> bytes:
    """A GeoParquet 1.1.0 ``geo`` metadata value with bbox covering.

    The ``crs`` key is omitted, which the GeoParquet specification defines as
    OGC:CRS84 (longitude, latitude in degrees on WGS 84). That is the CRS the
    upstream coordinates are already in, so nothing is reprojected.
    """
    doc = {
        "version": "1.1.0",
        "primary_column": geometry_column,
        "columns": {
            geometry_column: {
                "encoding": "WKB",
                "geometry_types": geometry_types,
                "bbox": bbox,
                "covering": {
                    "bbox": {
                        "xmin": [bbox_column, "xmin"],
                        "ymin": [bbox_column, "ymin"],
                        "xmax": [bbox_column, "xmax"],
                        "ymax": [bbox_column, "ymax"],
                    }
                },
            }
        },
    }
    return json.dumps(doc).encode("utf-8")
