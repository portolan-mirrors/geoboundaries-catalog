#!/usr/bin/env python3
"""Build one PMTiles archive per CGAZ level, plus one for the name index.

    python3 tools/build_pmtiles.py            # all four
    python3 tools/build_pmtiles.py adm1       # one target

``ogr2ogr`` streams the published GeoParquet to newline-delimited GeoJSON on
stdout and tippecanoe reads it from a pipe, so no intermediate GeoJSON is
written. The styles read the attributes carried here, so the ``-select`` list
and the style expressions have to stay in step.

Maximum zoom is set per level rather than globally. A country outline is
legible long before a municipality is, and every extra zoom level on the ADM2
archive costs tiles nobody opens.
"""
from __future__ import annotations

import subprocess
import sys

from gbcommon import PUBLISH, run

# target -> (source parquet, layer name, max zoom, attribute list, extra args)
TARGETS: dict[str, tuple[str, str, int, list[str], list[str]]] = {
    "adm0": (
        "adm0/cgaz_adm0.parquet", "adm0", 6,
        ["shapeName", "shapeGroup", "shapeType", "adm1_units", "adm2_units",
         "area_km2", "compactness"],
        [],
    ),
    "adm1": (
        "adm1/cgaz_adm1.parquet", "adm1", 7,
        ["shapeName", "shapeID", "shapeGroup", "shapeType", "country_units",
         "area_km2", "compactness"],
        [],
    ),
    "adm2": (
        "adm2/cgaz_adm2.parquet", "adm2", 9,
        ["shapeName", "shapeID", "shapeGroup", "shapeType", "country_units",
         "area_km2", "compactness"],
        [],
    ),
    "names": (
        "names/cgaz_names.parquet", "names", 8,
        ["name", "level", "shape_type", "country", "country_name",
         "area_km2", "name_dupes"],
        ["-r1", "--drop-densest-as-needed"],
    ),
}

# Polygon tiling. --detect-shared-borders keeps a shared edge between two
# neighbouring units simplified identically, so the composite stays seamless
# instead of opening hairline gaps as it simplifies. --coalesce-smallest-as-
# needed merges the smallest features rather than dropping them when a tile
# runs over the size limit, which keeps the fill continuous.
POLYGON_ARGS = [
    "--detect-shared-borders",
    "--coalesce-smallest-as-needed",
    "--simplification=4",
    "--simplify-only-low-zooms",
]


def build(target: str) -> None:
    rel, layer, maxzoom, fields, extra = TARGETS[target]
    src = PUBLISH / rel
    out = src.parent / f"{target}.pmtiles"
    is_points = target == "names"
    args = extra if is_points else POLYGON_ARGS

    ogr = [
        "ogr2ogr", "-f", "GeoJSONSeq", "/vsistdout/", str(src),
        "-select", ",".join(fields),
    ]
    tip = [
        "tippecanoe", "-o", str(out), "-f", "-q",
        "-l", layer,
        "-n", f"geoBoundaries CGAZ {target}",
        "-z", str(maxzoom), "-Z", "0",
        *args,
    ]
    print(f"{target}: {' '.join(ogr)} | {' '.join(tip)}", flush=True)
    with subprocess.Popen(ogr, stdout=subprocess.PIPE) as reader:
        subprocess.run(tip, stdin=reader.stdout, check=True)
        reader.stdout.close()
        if reader.wait() != 0:
            raise SystemExit(f"{target}: ogr2ogr failed")
    print(f"  {out.name}: {out.stat().st_size:,} bytes")
    run(["pmtiles", "show", str(out)])


def main(argv: list[str]) -> int:
    for target in argv or list(TARGETS):
        if target not in TARGETS:
            sys.exit(f"unknown target {target}; one of {', '.join(TARGETS)}")
        build(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
