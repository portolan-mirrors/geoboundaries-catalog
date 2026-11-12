#!/usr/bin/env python3
"""Generate every collection.json from the built data files.

    python3 tools/make_collections.py

Row counts, bounding boxes, and asset sizes and checksums are read from the
files in the staging tree rather than typed in, because a number typed in is a
number that goes stale on the next rebuild without anything noticing. The
prose, the keywords, and the column descriptions live in the spec below, which
is the one place to edit them.

Run ``tools/build_boundaries.py``, ``tools/build_names.py`` and
``tools/build_pmtiles.py`` first.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from gbcommon import (
    EXTRACTION_DATE,
    PUBLISH,
    SOURCE_COMMIT_DATE,
    source_path,
    source_url,
)

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "catalog"
PUBLIC_BASE = "https://data.source.coop/portolan-mirrors/geoboundaries-catalog"

LICENSE = "CC-BY-4.0"

PROVIDERS = [
    {
        "name": "geoBoundaries, William & Mary geoLab",
        "description": (
            "The geoBoundaries Global Database of Political Administrative "
            "Boundaries, built by the community and William & Mary geoLab. "
            "CGAZ composites country submissions against US Department of "
            "State international boundaries."
        ),
        "roles": ["producer", "licensor"],
        "url": "https://www.geoboundaries.org/",
    },
    {
        "name": "Portolan Mirrors",
        "description": (
            "Republishes the CGAZ release as cloud-native GeoParquet and "
            "PMTiles. Adds no boundaries and changes no geometry."
        ),
        "roles": ["processor", "host"],
        "url": "https://github.com/portolan-mirrors/geoboundaries-catalog",
    },
]

# Column documentation. Tier and source for every entry:
#
# shapeName, shapeGroup, shapeType, shapeID -- attested. The field list and
#   the ADM0/ADM1/ADM2 meanings are published in the Earth Engine catalog
#   entry for geoBoundaries 6.0.0, which carries geoBoundaries' own schema
#   description. The structure of shapeID follows from the boundaryID
#   definition in the geoBoundaries API documentation, and was verified
#   against the API: the ADM1 rows for AFG all carry the shapeID prefix
#   12653393, and the API returns boundaryID "AFG-ADM1-12653393".
# everything else -- derived, by tools/build_boundaries.py and
#   tools/build_names.py. The queries are in those files.
SHAPE_NAME = {
    "name": "shapeName",
    "type": "string",
    "description": (
        "Name of the administrative unit, carried through byte for byte as "
        "geoBoundaries published it. Not normalized, not transliterated, and "
        "not unique: 37 ADM2 rows have no name at all and 32 second-level "
        "units are called Washington. The names collection carries a folded "
        "form for searching."
    ),
}
SHAPE_ID = {
    "name": "shapeID",
    "type": "string",
    "description": (
        "geoBoundaries shape identifier, and the join key back to this file "
        "from the names collection. It is the numeric part of the source "
        "boundary's geoBoundaries boundaryID, then the letter B, then an "
        "integer unique to the shape within that boundary, for example "
        "12653393B40111500734429 against boundaryID AFG-ADM1-12653393. The "
        "prefix is therefore constant for every unit of one country at one "
        "level, and changes only when the underlying source data changes. The "
        "20 disputed-area rows instead carry DIS001 to DIS020. Unique within "
        "this file."
    ),
}
SHAPE_GROUP = {
    "name": "shapeGroup",
    "type": "string",
    "description": (
        "ISO 3166-1 alpha-3 code of the country the unit belongs to. The 20 "
        "disputed-area rows carry a geoBoundaries-internal code instead, 111 "
        "through 129, except Western Sahara which uses ESH. All 218 values "
        "appear in all three boundary files, which is what makes the "
        "composite seamless."
    ),
}


def shape_type(file_level: int, composition: str) -> dict:
    return {
        "name": "shapeType",
        "type": "string",
        "description": (
            "What the polygon actually is: ADM0 a country, ADM1 a first-level "
            "unit, ADM2 a second-level unit, DISP a disputed area. It is not "
            f"always ADM{file_level} in this file. CGAZ fills gaps with the "
            "next coarser level available for a country, and carries the "
            f"disputed areas in all three files. Here: {composition}."
        ),
    }


AREA = {
    "name": "area_km2",
    "type": "double",
    "description": (
        "Derived. Geodesic area of the polygon in square kilometres on the "
        "WGS 84 ellipsoid. Measured from the simplified CGAZ geometry, so it "
        "is not the unit's official area. Agrees to better than 0.01% with "
        "the NSIDC EASE-Grid 2.0 Global projection that geoBoundaries says it "
        "uses for its own published area statistics."
    ),
}
PERIMETER = {
    "name": "perimeter_km",
    "type": "double",
    "description": (
        "Derived. Geodesic perimeter in kilometres on the WGS 84 ellipsoid, "
        "from the simplified CGAZ geometry."
    ),
}
COMPACTNESS = {
    "name": "compactness",
    "type": "double",
    "description": (
        "Derived. Polsby-Popper ratio, 4*pi*area/perimeter^2. 1.0 for a "
        "circle, falling towards 0 as an outline gets long or fragmented, so "
        "it separates archipelagos and river-defined units from blocky inland "
        "ones. Computed on the simplified geometry, so it reads lower than it "
        "would on the full-resolution single-country files."
    ),
}
BBOX = {
    "name": "bbox",
    "type": "struct",
    "description": (
        "GeoParquet 1.1 bbox covering struct, with xmin, ymin, xmax and ymax "
        "as doubles in CRS84. A reader prunes row groups on this without "
        "decoding any geometry. It is also the extent to fly a map to."
    ),
}
GEOMETRY = {
    "name": "geometry",
    "type": "geometry",
    "description": (
        "Polygon or MultiPolygon as WKB, in CRS84 (longitude, latitude on "
        "WGS 84). The upstream GeoPackage declares no CRS at all; these are "
        "the same coordinates with EPSG:4326 assigned, not reprojected."
    ),
}


def country_units(level: int) -> dict:
    return {
        "name": "country_units",
        "type": "int32",
        "description": (
            f"Derived. How many rows of this file share this row's "
            f"shapeGroup, which is how many level-{level} units the composite "
            f"holds for that country. Counted over this file only."
        ),
    }


def boundary_spec(level: int, *, title: str, short: str, description: str,
                  keywords: list[str], composition: str,
                  extra_columns: list[dict], row_group_rows: int,
                  max_zoom: int, style_titles: dict[str, str]) -> dict:
    columns = [SHAPE_NAME]
    if level > 0:
        columns.append(SHAPE_ID)
    columns += [SHAPE_GROUP, shape_type(level, composition)]
    columns += extra_columns
    columns += [AREA, PERIMETER, COMPACTNESS, BBOX, GEOMETRY]
    return {
        "dir": f"adm{level}",
        "id": f"adm{level}",
        "title": title,
        "short": short,
        "description": description,
        "keywords": keywords,
        "parquet": f"cgaz_adm{level}.parquet",
        "pmtiles": f"adm{level}.pmtiles",
        "pmtiles_layer": f"adm{level}",
        "max_zoom": max_zoom,
        "row_group_rows": row_group_rows,
        "columns": columns,
        "source_gpkg": source_url(level),
        "source_gpkg_title": (
            f"geoBoundariesCGAZ_ADM{level}.gpkg, the upstream GeoPackage"
        ),
        "styles": style_titles,
        "geometry_types": ["Polygon", "MultiPolygon"],
    }


SPECS: list[dict] = [
    boundary_spec(
        0,
        title="CGAZ ADM0 - Country Boundaries",
        short="Country Boundaries",
        description=(
            "The 218 country-level polygons of the geoBoundaries CGAZ "
            "composite, as GeoParquet 1.1 with bbox covering metadata and "
            "spatially sorted into 55 row groups of 4 rows, so a client can "
            "pull one country's geometry in a single range request instead of "
            "downloading 97 MB. 198 rows are recognized countries and 20 are "
            "disputed areas carried as polygons of their own. The outlines "
            "come from the US Department of State Large Scale International "
            "Boundaries file, dissolved to one polygon per ISO code, and "
            "unlike the ADM1 and ADM2 levels they are not simplified: 10.1 "
            "million vertices across 218 units. Read the "
            "[agent guide](AGENTS.md) before querying, and note that CGAZ "
            "ADM0 publishes no `shapeID`, so `shapeGroup` is the join key at "
            "this level."
        ),
        keywords=[
            "administrative boundaries", "countries", "ADM0", "geoBoundaries",
            "CGAZ", "global", "disputed territories", "GeoParquet", "PMTiles",
        ],
        composition="198 ADM0 and 20 DISP",
        extra_columns=[
            {
                "name": "adm1_units",
                "type": "int32",
                "description": (
                    "Derived. How many rows the ADM1 collection holds for "
                    "this shapeGroup. 1 means the composite has no "
                    "first-level breakdown for that country and carries its "
                    "ADM0 polygon in the ADM1 file instead. Ranges from 1 to "
                    "83."
                ),
            },
            {
                "name": "adm2_units",
                "type": "int32",
                "description": (
                    "Derived. How many rows the ADM2 collection holds for "
                    "this shapeGroup. Ranges from 1 to 5,570, the latter "
                    "being Brazil."
                ),
            },
        ],
        row_group_rows=4,
        max_zoom=6,
        style_titles={
            "default": "Country area",
            "status": "Recognized boundary or disputed area",
            "adm1-units": "First-level units per country",
            "compactness": "Outline compactness",
        },
    ),
    boundary_spec(
        1,
        title="CGAZ ADM1 - First-Level Administrative Boundaries",
        short="First-Level Administrative Boundaries",
        description=(
            "3,224 first-level administrative units worldwide (states, "
            "provinces, regions, governorates) from the geoBoundaries CGAZ "
            "composite, as GeoParquet 1.1 with bbox covering metadata and "
            "spatially sorted into 51 row groups of 64 rows. 3,202 rows are "
            "genuine first-level units; 20 are disputed areas and 2 are "
            "countries with no first-level breakdown, Antarctica and Vatican "
            "City, carried up so the composite stays seamless. Geometry is "
            "each country's geoBoundaries submission simplified to roughly a "
            "tenth of its vertices and clipped to US Department of State "
            "international boundaries. Read the [agent guide](AGENTS.md): "
            "`shapeType` is what tells you whether a row is really an ADM1 "
            "unit, and the composite publishes no key linking a unit to its "
            "parent country's subdivisions. A second GeoParquet file, "
            "`cgaz_adm1_display.parquet`, carries the same rows in the same "
            "order with geometry simplified and buffered outward, 13 MB "
            "against 75, for drawing and for spatial filtering."
        ),
        keywords=[
            "administrative boundaries", "states", "provinces", "regions",
            "ADM1", "geoBoundaries", "CGAZ", "global", "subnational",
            "GeoParquet", "PMTiles",
        ],
        composition="3,202 ADM1, 20 DISP and 2 ADM0",
        extra_columns=[country_units(1)],
        row_group_rows=64,
        max_zoom=7,
        style_titles={
            "default": "First-level unit area",
            "units-per-country": "First-level units in this country",
            "source-level": "What each polygon really is",
            "compactness": "Outline compactness",
        },
    ),
    boundary_spec(
        2,
        title="CGAZ ADM2 - Second-Level Administrative Boundaries",
        short="Second-Level Administrative Boundaries",
        description=(
            "49,349 second-level administrative units worldwide (counties, "
            "districts, municipalities, communes) from the geoBoundaries CGAZ "
            "composite, as GeoParquet 1.1 with bbox covering metadata and "
            "spatially sorted into 97 row groups of 512 rows, so one unit's "
            "geometry costs about 1 MB to fetch rather than the whole 101 MB "
            "file. 49,015 rows are genuine second-level units; 312 are "
            "first-level units standing in for 22 countries that have no "
            "second-level data, 20 are disputed areas and 2 are countries. "
            "Brazil alone contributes 5,570 rows. Read the "
            "[agent guide](AGENTS.md): 37 rows have no name, and `shapeType` "
            "is what tells you whether a row is really an ADM2 unit."
        ),
        keywords=[
            "administrative boundaries", "counties", "districts",
            "municipalities", "ADM2", "geoBoundaries", "CGAZ", "global",
            "subnational", "GeoParquet", "PMTiles",
        ],
        composition="49,015 ADM2, 312 ADM1, 20 DISP and 2 ADM0",
        extra_columns=[country_units(2)],
        row_group_rows=512,
        max_zoom=9,
        style_titles={
            "default": "Second-level unit area",
            "units-per-country": "Second-level units in this country",
            "source-level": "What each polygon really is",
            "compactness": "Outline compactness",
        },
    ),
    {
        "dir": "names",
        "id": "names",
        "title": "CGAZ Name Search Index",
        "short": "Name Search Index",
        "description": (
            "A search sidecar, not a boundary dataset: one row per named "
            "administrative unit across all three CGAZ levels, 52,398 rows in "
            "3.6 MB, sorted by a folded form of the name. The sort is the "
            "whole design. The intended use is to load the file whole, which "
            "at this size takes a couple of hundred milliseconds in a "
            "browser; row group statistics on `name_norm` are tight, "
            "non-overlapping alphabetical ranges, so a client that will not "
            "load 3.6 MB can instead resolve a typed prefix from one or two "
            "101 KiB row groups by HTTP range request. Each row carries the "
            "`shapeID` that joins it back to the boundary collection for its "
            "level, a bbox to fly a map to, a point inside the unit, and how "
            "many other units share the same name. The [agent guide](AGENTS.md) "
            "has both lookup recipes and the join back to geometry."
        ),
        "keywords": [
            "geocoding", "search index", "place names", "gazetteer",
            "autocomplete", "geoBoundaries", "CGAZ", "GeoParquet",
        ],
        "parquet": "cgaz_names.parquet",
        "pmtiles": "names.pmtiles",
        "pmtiles_layer": "names",
        "max_zoom": 8,
        "row_group_rows": 1536,
        "geometry_types": ["Point"],
        "source_gpkg": None,
        "styles": {
            "default": "Indexed names by administrative level",
            "ambiguity": "How many units share this name",
            "unit-area": "Area of the named unit",
        },
        "columns": [
            {
                "name": "name",
                "type": "string",
                "description": (
                    "The unit's name exactly as geoBoundaries publishes it, "
                    "including the 38 rows whose upstream text is "
                    "double-encoded UTF-8. Display this; search name_norm."
                ),
            },
            {
                "name": "name_norm",
                "type": "string",
                "description": (
                    "Derived, and the column the file is sorted by. The name "
                    "lowercased with Unicode case folding and with combining "
                    "accent marks stripped through NFKD, so 'Zurich' finds "
                    "'Zürich'. The 38 double-encoded upstream names are "
                    "repaired here first, so 'region de valparaiso' finds the "
                    "row whose published name is 'RegiÃ³n de ValparaÃ­so'. "
                    "Scripts with no Latin decomposition, such as Han, are "
                    "lowercased and otherwise unchanged."
                ),
            },
            {
                "name": "level",
                "type": "int8",
                "description": (
                    "0, 1 or 2: which boundary collection holds this unit's "
                    "geometry. 218 rows at level 0, 3,202 at level 1, 48,978 "
                    "at level 2."
                ),
            },
            {
                "name": "shape_type",
                "type": "string",
                "description": (
                    "ADM0, ADM1, ADM2 or DISP, from the boundary row. Every "
                    "row's shape_type matches its level, because the index "
                    "takes each unit only from the file that level natively "
                    "belongs to; DISP rows sit at level 0."
                ),
            },
            {
                "name": "country",
                "type": "string",
                "description": (
                    "The boundary row's shapeGroup: ISO 3166-1 alpha-3, or a "
                    "geoBoundaries disputed-area code 111 to 129. Also the "
                    "join key back to the ADM0 collection for level-0 rows."
                ),
            },
            {
                "name": "country_name",
                "type": "string",
                "description": (
                    "Derived. The ADM0 shapeName for this row's country, "
                    "joined on shapeGroup, so an autocomplete can show "
                    "'Zurich, Switzerland' without a second fetch. NULL for "
                    "the 20 disputed areas, which have no ADM0 parent."
                ),
            },
            {
                "name": "shape_id",
                "type": "string",
                "description": (
                    "The boundary row's shapeID, and the join key back to the "
                    "ADM1 or ADM2 collection. NULL for every level-0 row, "
                    "because CGAZ ADM0 publishes no shapeID; join those on "
                    "country instead."
                ),
            },
            {
                "name": "area_km2",
                "type": "double",
                "description": (
                    "Derived. The unit's geodesic area in square kilometres, "
                    "copied from its boundary row and rounded to three "
                    "decimals. Useful as a relevance weight: of two units "
                    "with the same name, the larger is usually the one meant."
                ),
            },
            {
                "name": "name_dupes",
                "type": "int32",
                "description": (
                    "Derived. How many rows in this index share this row's "
                    "name_norm, counted worldwide and across levels. 1 for "
                    "44,258 rows; 878 rows sit in a name shared by 10 or more "
                    "units, and 32 units are called Washington. An "
                    "autocomplete needs this to decide when to disambiguate."
                ),
            },
            {
                "name": "bbox",
                "type": "struct",
                "description": (
                    "GeoParquet 1.1 bbox covering struct, xmin, ymin, xmax, "
                    "ymax in CRS84: the unit's full extent, copied from its "
                    "boundary row. This is what to fly a map to after a hit. "
                    "Stored as float32 rather than float64 to halve what it "
                    "costs in a file meant to be loaded whole, with every "
                    "bound rounded outward so the box still contains the "
                    "unit. Verified against the ADM2 collection: 0 of 48,978 "
                    "joined rows have a bbox narrower than their true extent. "
                    "Precision is about 1e-5 degrees, roughly a metre. The "
                    "boundary collections keep float64."
                ),
            },
            {
                "name": "geometry",
                "type": "geometry",
                "description": (
                    "Derived. A Point as WKB in CRS84, from "
                    "ST_PointOnSurface of the unit's polygon, so it is "
                    "guaranteed to fall inside the unit rather than outside "
                    "it the way a centroid can. Use it for a marker, not as "
                    "the unit's geometry."
                ),
            },
        ],
    },
]


def checksum(path: Path) -> str:
    """A multihash sha2-256, the form STAC's file extension expects."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"1220{digest}"


def clamp_wgs84(bbox: list[float]) -> list[float]:
    """Clamp a bbox to the valid WGS84 range.

    Two reasons it can fall outside. The upstream geometry reaches
    180.0000000000001 east, a floating-point artifact of the upstream build
    that is 1e-13 degrees wide. And the search index's bbox struct is float32
    rounded outward, which pushes its east edge to 180.000015, about 1.5 m.
    Neither is a real coordinate past the antimeridian, and rashid's PTL-BBX-001
    correctly refuses a STAC extent outside [-180, 180]. The GeoParquet files
    keep their measured bbox so the covering metadata still contains every
    geometry; only the STAC extent is clamped.
    """
    xmin, ymin, xmax, ymax = bbox
    return [
        max(-180.0, xmin), max(-90.0, ymin),
        min(180.0, xmax), min(90.0, ymax),
    ]


def parquet_stats(path: Path) -> dict:
    md = pq.ParquetFile(path)
    geo = json.loads(md.schema_arrow.metadata[b"geo"])
    primary = geo["primary_column"]
    return {
        "rows": md.metadata.num_rows,
        "row_groups": md.metadata.num_row_groups,
        "bbox": geo["columns"][primary]["bbox"],
        "primary": primary,
    }


def build(spec: dict) -> dict:
    data_dir = PUBLISH / spec["dir"]
    out_dir = CATALOG / spec["dir"]
    parquet = data_dir / spec["parquet"]
    pmtiles = data_dir / spec["pmtiles"]
    for path in (parquet, pmtiles):
        if not path.exists():
            sys.exit(f"missing {path}; run the build tools first")
    stats = parquet_stats(parquet)

    display = data_dir / spec["parquet"].replace(".parquet", "_display.parquet")

    assets: dict[str, dict] = {
        "data": {
            "href": f"./{spec['parquet']}",
            "type": "application/vnd.apache.parquet",
            "title": (
                f"{spec['short']}, GeoParquet 1.1 "
                f"({stats['row_groups']} row groups of "
                f"{spec['row_group_rows']:,} rows, zstd)"
            ),
            "roles": ["data"],
            "file:size": parquet.stat().st_size,
            "file:checksum": checksum(parquet),
            "table:primary_geometry": stats["primary"],
        },
        "pmtiles": {
            "href": f"./{spec['pmtiles']}",
            "type": "application/vnd.pmtiles",
            "title": f"{spec['short']}, vector tiles to zoom {spec['max_zoom']}",
            "roles": ["visual", "data"],
            "file:size": pmtiles.stat().st_size,
            "file:checksum": checksum(pmtiles),
            "pmtiles:layers": [spec["pmtiles_layer"]],
        },
    }
    if display.exists():
        disp_stats = parquet_stats(display)
        assets["display"] = {
            # "overview" is STAC's common role for a reduced-resolution
            # version of the data asset, which is exactly what this is. The
            # "data" role stays on the verbatim file.
            "href": f"./{display.name}",
            "type": "application/vnd.apache.parquet",
            "title": (
                f"{spec['short']}, display and filter geometry "
                f"({disp_stats['row_groups']} row groups of "
                f"{spec['row_group_rows']:,} rows, aligned with the data "
                "asset)"
            ),
            "roles": ["data", "overview"],
            "description": (
                "The same rows in the same order and the same row group "
                "boundaries as the data asset, with geometry simplified and "
                "then buffered **outward** by the simplification tolerance, "
                "so the shape contains the true boundary rather than cutting "
                "inside it. Built for drawing an outline fast and for "
                "pre-filtering another dataset, where over-fetching is cheap "
                "and a missing edge feature is a wrong answer. Neighbouring "
                "units overlap in the margin. Do not measure area from it, "
                "do not use it to decide which side of a border a point "
                "falls on, and do not publish it as a boundary. See the "
                "[catalog agent guide](../AGENTS.md) and "
                "[changes-from-upstream.md](../changes-from-upstream.md)."
            ),
            "file:size": display.stat().st_size,
            "file:checksum": checksum(display),
            "table:primary_geometry": disp_stats["primary"],
            "table:row_count": disp_stats["rows"],
        }

    for slug, title in spec["styles"].items():
        style_path = out_dir / "styles" / f"{slug}.json"
        if not style_path.exists():
            sys.exit(f"missing {style_path}; run tools/make_styles.py first")
        key = "style-default" if slug == "default" else f"style-{slug}"
        assets[key] = {
            "href": f"./styles/{slug}.json",
            "type": "application/vnd.mapbox.style+json",
            "title": title,
            "roles": ["style", "default"] if slug == "default" else ["style"],
            "file:size": style_path.stat().st_size,
            "file:checksum": checksum(style_path),
        }
    if spec["source_gpkg"]:
        # file:size and file:checksum come from the downloaded copy in the
        # staging tree, so they pin the exact upstream bytes this collection
        # was built from. CGAZ is served from a moving branch, so without
        # them "the file at that URL" is not a version.
        local = source_path(int(spec["id"][-1]))
        assets["source-gpkg"] = {
            "href": spec["source_gpkg"],
            "type": "application/geopackage+sqlite3",
            "title": spec["source_gpkg_title"],
            "roles": ["data", "source"],
            "file:size": local.stat().st_size,
            "file:checksum": checksum(local),
            "description": (
                "The file this collection was built from, at its original "
                "location. Served through git-lfs from the default branch, so "
                "the URL is not version-pinned; the release this collection "
                "mirrors is the commit recorded in processing_notes."
            ),
        }
    thumb = out_dir / f"{spec['id']}.thumb.png"
    if thumb.exists():
        assets["thumbnail"] = {
            "href": f"./{thumb.name}",
            "type": "image/png",
            "title": f"{spec['short']}, rendered from the default style",
            "roles": ["thumbnail"],
            "file:size": thumb.stat().st_size,
            "file:checksum": checksum(thumb),
        }

    links = [
        {"rel": "root", "href": "../catalog.json", "type": "application/json",
         "title": "geoBoundaries CGAZ Global Administrative Boundaries"},
        {"rel": "parent", "href": "../catalog.json",
         "type": "application/json",
         "title": "geoBoundaries CGAZ Global Administrative Boundaries"},
        {"rel": "describedby", "href": "./README.md", "type": "text/markdown",
         "title": "Collection README"},
        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown",
         "title": "Collection agent guide"},
        {"rel": "via",
         "href": "https://www.geoboundaries.org/globalDownloads.html",
         "type": "text/html",
         "title": "geoBoundaries CGAZ downloads (upstream source)"},
        {"rel": "cite-as", "href": "https://doi.org/10.1371/journal.pone.0231866",
         "type": "text/html",
         "title": ("Runfola et al. (2020), geoBoundaries: A global database "
                   "of political administrative boundaries, PLoS ONE 15(4): "
                   "e0231866")},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
         "type": "text/html",
         "title": "Creative Commons Attribution 4.0 International"},
        {"rel": "pmtiles", "href": f"./{spec['pmtiles']}",
         "type": "application/vnd.pmtiles",
         "title": f"{spec['short']}, vector tiles",
         "pmtiles:layers": [spec["pmtiles_layer"]]},
    ]
    for sibling in SPECS:
        if sibling["id"] == spec["id"]:
            continue
        links.append({
            "rel": "related",
            "href": f"../{sibling['dir']}/collection.json",
            "type": "application/json",
            "title": sibling["title"],
        })

    doc = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [
            "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/file/v2.1.0/schema.json",
            "https://stac-extensions.github.io/web-map-links/v1.3.0/schema.json",
        ],
        "id": spec["id"],
        "title": spec["title"],
        "description": spec["description"],
        "license": LICENSE,
        "keywords": spec["keywords"],
        "providers": PROVIDERS,
        "extent": {
            "spatial": {
                "bbox": [[round(v, 6) for v in clamp_wgs84(stats["bbox"])]]
            },
            # CGAZ publishes no validity dates per unit: the build drops
            # geoBoundaries' boundaryYearRepresented field. The interval is
            # therefore the upstream release itself, the commit that last
            # changed any file under releaseData/CGAZ.
            "temporal": {
                "interval": [[SOURCE_COMMIT_DATE, SOURCE_COMMIT_DATE]]
            },
        },
        # PTL-PRO-003: a mirror has to say when it last synced. This is the
        # date the upstream GeoPackages were downloaded, not the build time,
        # because that is what a reader compares against the live upstream.
        "updated": f"{EXTRACTION_DATE}T00:00:00Z",
        "table:primary_geometry": stats["primary"],
        "table:row_count": stats["rows"],
        "table:columns": spec["columns"],
        "assets": assets,
        "links": links,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "collection.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    print(
        f"  {path.relative_to(REPO)}: {stats['rows']:,} rows, "
        f"{len(assets)} assets, {len(spec['columns'])} columns"
    )
    return doc


def main() -> int:
    for spec in SPECS:
        build(spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
