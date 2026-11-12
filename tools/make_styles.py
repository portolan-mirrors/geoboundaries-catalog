#!/usr/bin/env python3
"""Generate the style JSON for every collection.

    python3 tools/make_styles.py

The styles are generated rather than hand-written because every class break in
them is a measured number. The query that produced each break is quoted in the
spec below, so a style and its justification cannot drift apart. Rerun
``tools/distributions.sql`` against the published files to check them.

Two rules shape every style here.

**The legend rule.** As of 2026-08-12 the Portolan data browser derives a
legend only from a ``fill`` layer whose ``fill-color`` is a ``match`` or
``step`` array expression. See
https://github.com/portolan-sdi/portolan-browser/blob/main/src/utils/portolanStyles.js
So the three polygon collections use ``step`` or ``match`` on ``fill-color``
and nothing else, and the point collection gets no legend at all, which its
agent guide says out loud.

**Every branch is real.** Each ``match`` branch and each ``step`` band below
carries the count of features that land in it, measured on the built file. A
legend listing a class the data does not hold is the most common visible
defect in a new catalog.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog"

# Palettes vary by collection so that four boundary cards in a grid do not
# read as four copies of one dataset.
WARM = ["#f7e3c0", "#e7c388", "#d19a4e", "#b26f2c", "#8a4a1c", "#5c2d11"]
TEAL = ["#e2f4f2", "#a8dfd9", "#60bcbd", "#3387a8", "#275a8f", "#1d3167"]
VIOLET = ["#f4e6f8", "#dcbae4", "#bf87cb", "#9b55ad", "#702f87", "#45175e"]
AMBER = ["#fff0c9", "#ffd27a", "#f4a23c", "#da6a1f", "#a63f13"]

GREY = "#cfcfcf"
DISPUTED = "#c1272d"


def fill(source_layer: str, color, *, opacity: float = 0.85) -> dict:
    return {
        "id": f"{source_layer}-fill",
        "type": "fill",
        "source": "data",
        "source-layer": source_layer,
        "paint": {
            "fill-color": color,
            "fill-opacity": opacity,
            "fill-outline-color": "rgba(40,40,40,0.35)",
        },
    }


def outline(source_layer: str, color: str = "rgba(30,30,30,0.55)") -> dict:
    return {
        "id": f"{source_layer}-line",
        "type": "line",
        "source": "data",
        "source-layer": source_layer,
        "paint": {"line-color": color, "line-width": 0.4},
    }


def step(field: str, palette: list[str], breaks: list[float]) -> list:
    """A step expression: palette[0] below breaks[0], then one per break."""
    assert len(palette) == len(breaks) + 1, (field, len(palette), len(breaks))
    expr: list = ["step", ["coalesce", ["get", field], 0], palette[0]]
    for value, color in zip(breaks, palette[1:]):
        expr += [value, color]
    return expr


def match(field: str, pairs: list[tuple[str, str]], fallback: str) -> list:
    expr: list = ["match", ["get", field]]
    for value, color in pairs:
        expr += [value, color]
    expr.append(fallback)
    return expr


def polygon_style(name: str, pmtiles: str, layer: str, color) -> dict:
    return {
        "version": 8,
        "name": name,
        "sources": {"data": {"type": "vector", "url": f"pmtiles://../{pmtiles}"}},
        "layers": [fill(layer, color), outline(layer)],
    }


def point_style(name: str, pmtiles: str, layer: str, color) -> dict:
    return {
        "version": 8,
        "name": name,
        "sources": {"data": {"type": "vector", "url": f"pmtiles://../{pmtiles}"}},
        "layers": [
            {
                "id": f"{layer}-circle",
                "type": "circle",
                "source": "data",
                "source-layer": layer,
                "paint": {
                    "circle-color": color,
                    "circle-radius": [
                        "interpolate", ["linear"], ["zoom"],
                        0, 1.1, 4, 2.6, 8, 5.0,
                    ],
                    "circle-opacity": 0.85,
                    "circle-stroke-width": 0.3,
                    "circle-stroke-color": "rgba(30,30,30,0.5)",
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# The specs. Counts beside each band were measured on the built files.
# ---------------------------------------------------------------------------

SPECS: dict[str, list[tuple[str, str, dict]]] = {}

SPECS["adm0"] = [
    # default. Country area, 6 bands.
    #   SELECT CASE WHEN area_km2 < 1000 ... END, count(*) FROM adm0 GROUP BY 1
    #   -> <1k 37 | 1k-25k 31 | 25k-150k 57 | 150k-600k 47
    #      | 600k-2.5M 36 | >=2.5M 10
    ("default", "Country area", polygon_style(
        "Country area", "adm0.pmtiles", "adm0",
        step("area_km2", WARM, [1_000, 25_000, 150_000, 600_000, 2_500_000]),
    )),
    # Administrative status. The one thing a reader has to know about CGAZ:
    # it does not draw a country "as it represents itself", it clips to US
    # Department of State international boundaries and carries the contested
    # ground as 20 separate polygons.
    #   SELECT shapeType, count(*) FROM adm0 GROUP BY 1
    #   -> ADM0 198 | DISP 20
    ("status", "Recognized boundary or disputed area", polygon_style(
        "Recognized boundary or disputed area", "adm0.pmtiles", "adm0",
        match("shapeType", [("ADM0", "#b5a07c"), ("DISP", DISPUTED)], GREY),
    )),
    # First-level units per country.
    #   SELECT CASE WHEN adm1_units = 1 ... END, count(*) FROM adm0 GROUP BY 1
    #   -> 1 unit 23 | 2-10 80 | 11-25 84 | 26-50 25 | >50 6
    ("adm1-units", "First-level units per country", polygon_style(
        "First-level units per country", "adm0.pmtiles", "adm0",
        step("adm1_units", WARM[1:], [2, 11, 26, 51]),
    )),
    # Outline compactness, Polsby-Popper 4*pi*A/P^2.
    #   -> <0.05 51 | 0.05-0.15 50 | 0.15-0.30 73 | 0.30-0.50 33 | >=0.50 11
    ("compactness", "Outline compactness", polygon_style(
        "Outline compactness", "adm0.pmtiles", "adm0",
        step("compactness", WARM[:5], [0.05, 0.15, 0.30, 0.50]),
    )),
]

SPECS["adm1"] = [
    # default. First-level unit area, 6 bands.
    #   -> <500 519 | 500-3k 575 | 3k-12k 838 | 12k-50k 741
    #      | 50k-200k 435 | >=200k 116
    ("default", "First-level unit area", polygon_style(
        "First-level unit area", "adm1.pmtiles", "adm1",
        step("area_km2", TEAL, [500, 3_000, 12_000, 50_000, 200_000]),
    )),
    # Units per country: how finely the composite divides each country.
    #   -> 1 23 | 2-10 539 | 11-20 959 | 21-35 937 | >35 766
    ("units-per-country", "First-level units in this country", polygon_style(
        "First-level units in this country", "adm1.pmtiles", "adm1",
        step("country_units", TEAL[1:], [2, 11, 21, 36]),
    )),
    # What the geometry actually is. CGAZ fills gaps with the next coarser
    # level, so not every row in the ADM1 file is an ADM1 unit.
    #   SELECT shapeType, count(*) FROM adm1 GROUP BY 1
    #   -> ADM1 3202 | DISP 20 | ADM0 2
    ("source-level", "What each polygon really is", polygon_style(
        "What each polygon really is", "adm1.pmtiles", "adm1",
        match(
            "shapeType",
            [("ADM1", "#3387a8"), ("ADM0", "#f4a23c"), ("DISP", DISPUTED)],
            GREY,
        ),
    )),
    # Outline compactness.
    #   -> <0.05 103 | 0.05-0.15 364 | 0.15-0.30 980 | 0.30-0.50 1169
    #      | >=0.50 608
    ("compactness", "Outline compactness", polygon_style(
        "Outline compactness", "adm1.pmtiles", "adm1",
        step("compactness", TEAL[:5], [0.05, 0.15, 0.30, 0.50]),
    )),
]

SPECS["adm2"] = [
    # default. Second-level unit area, 6 bands.
    #   -> <50 7154 | 50-250 11522 | 250-1k 12394 | 1k-5k 13483
    #      | 5k-25k 4069 | >=25k 727
    ("default", "Second-level unit area", polygon_style(
        "Second-level unit area", "adm2.pmtiles", "adm2",
        step("area_km2", VIOLET, [50, 250, 1_000, 5_000, 25_000]),
    )),
    # Units per country.
    #   -> <=10 116 | 11-100 4924 | 101-500 13446 | 501-2000 11674
    #      | >2000 19189
    ("units-per-country", "Second-level units in this country", polygon_style(
        "Second-level units in this country", "adm2.pmtiles", "adm2",
        step("country_units", VIOLET[1:], [11, 101, 501, 2001]),
    )),
    # What the geometry actually is. 22 countries have no second-level data,
    # so the ADM2 file carries their ADM1 or ADM0 polygon instead.
    #   SELECT shapeType, count(*) FROM adm2 GROUP BY 1
    #   -> ADM2 49015 | ADM1 312 | DISP 20 | ADM0 2
    ("source-level", "What each polygon really is", polygon_style(
        "What each polygon really is", "adm2.pmtiles", "adm2",
        match(
            "shapeType",
            [("ADM2", "#9b55ad"), ("ADM1", "#f4a23c"), ("ADM0", "#2b8a4a"),
             ("DISP", DISPUTED)],
            GREY,
        ),
    )),
    # Outline compactness.
    #   -> <0.05 175 | 0.05-0.15 1218 | 0.15-0.30 8742 | 0.30-0.50 20754
    #      | >=0.50 18460
    ("compactness", "Outline compactness", polygon_style(
        "Outline compactness", "adm2.pmtiles", "adm2",
        step("compactness", VIOLET[:5], [0.05, 0.15, 0.30, 0.50]),
    )),
]

SPECS["names"] = [
    # default. Administrative level of each indexed name.
    #   SELECT level, count(*) FROM names GROUP BY 1
    #   -> 0 218 | 1 3202 | 2 48978
    # Level 2 is 93% of the rows, so it takes the mid tone a reader can
    # actually see; the rare level-0 points take the darkest.
    ("default", "Indexed names by administrative level", point_style(
        "Indexed names by administrative level", "names.pmtiles", "names",
        step("level", [AMBER[4], AMBER[3], AMBER[2]], [1, 2]),
    )),
    # How ambiguous a name is. 32 units are called Washington.
    #   -> unique 44258 | 2-3 5583 | 4-9 1679 | >=10 878
    ("ambiguity", "How many units share this name", point_style(
        "How many units share this name", "names.pmtiles", "names",
        step("name_dupes", AMBER[:4], [2, 4, 10]),
    )),
    # Area of the named unit, a usable relevance proxy for autocomplete.
    #   -> <10 2419 | 10-100 9389 | 100-1k 19648 | 1k-10k 17182 | >=10k 3760
    ("unit-area", "Area of the named unit", point_style(
        "Area of the named unit", "names.pmtiles", "names",
        step("area_km2", AMBER, [10, 100, 1_000, 10_000]),
    )),
]


def main() -> int:
    written = 0
    for collection, styles in SPECS.items():
        out_dir = CATALOG / collection / "styles"
        out_dir.mkdir(parents=True, exist_ok=True)
        for slug, title, doc in styles:
            doc["name"] = title
            path = out_dir / f"{slug}.json"
            path.write_text(json.dumps(doc, indent=2) + "\n")
            written += 1
            print(f"  {path.relative_to(CATALOG.parent)}")
    print(f"{written} style files written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
