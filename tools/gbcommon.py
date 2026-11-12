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


# Rows per row group, chosen per level from the measured compressed bytes per
# row so that one row group is roughly 1.5-2 MB and a client that wants one
# unit's geometry fetches about that much. See tools/build_boundaries.py for
# the measurement and docs/pipeline.md for the numbers.
ROW_GROUP_ROWS = {0: 4, 1: 64, 2: 512}

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
