#!/usr/bin/env python3
"""Render each collection's thumbnail from its own default style.

    python3 tools/make_thumbnails.py            # all four
    python3 tools/make_thumbnails.py adm2       # one

The canonical way to build a Portolan thumbnail is to render
``styles/default.json`` server-side with chiitiler, through MapLibre GL Native.
That needs a clone of chiitiler, which was not available in the environment
this catalog was built in, so this script renders the same style's colours from
the GeoParquet instead: it parses the ``step`` or ``match`` expression out of
``styles/default.json`` and colours every feature by it. The image a reader
sees therefore agrees with the legend the browser derives from the same
expression, which is the property that matters. It is not a MapLibre render:
there is no basemap, and line widths are matplotlib's.

Framing. Each image is 3:2, matching the browser card, which is 350-700 px
wide and 250 px tall. Four world maps in a card grid would be four
indistinguishable cards, so only the country level is framed to the full
extent; the other three are framed on a region that shows what that level
actually looks like. The window for each is recorded in WINDOWS below.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from gbcommon import PUBLISH  # noqa: E402

CATALOG = Path(__file__).resolve().parents[1] / "catalog"

# collection -> (parquet, (west, south, east, north) or None for full extent,
#                simplify tolerance in degrees, label)
# Each window is already at the aspect given, so no reshaping happens; they
# were chosen by eye from the rendered image, which is the only way to choose
# a frame. A different region per collection is deliberate: four world maps in
# a card grid are four cards a reader cannot tell apart.
WINDOWS: dict[str, dict] = {
    "adm0": {
        "parquet": "adm0/cgaz_adm0.parquet",
        "window": (-180.0, -90.0, 180.0, 90.0), "aspect": 2.0,
        "simplify": 0.05, "edge": 0.15,
        "label": "the whole world, the only full-extent frame",
    },
    "adm1": {
        "parquet": "adm1/cgaz_adm1.parquet",
        "window": (-11.0, 34.0, 43.0, 70.0), "aspect": 1.5,
        "simplify": 0.01, "edge": 0.15,
        "label": "Europe and the Mediterranean",
    },
    "adm2": {
        "parquet": "adm2/cgaz_adm2.parquet",
        "window": (-78.0, -33.0, -33.0, -3.0), "aspect": 1.5,
        "simplify": 0.004, "edge": 0.06,
        "label": "Brazil, which contributes 5,570 of the 49,349 rows",
    },
    "names": {
        "parquet": "names/cgaz_names.parquet",
        "window": (-20.0, -36.0, 55.0, 14.0), "aspect": 1.5,
        "simplify": 0.0, "edge": 0.0, "markersize": 3.4,
        "label": "Africa",
    },
}

WATER = "#eef1f3"
TARGET_ASPECT = 1.5
WIDTH_PX = 1200
DPI = 100


def eval_step(expr: list, value) -> str:
    """Evaluate a MapLibre step expression for one value."""
    fallback = expr[2]
    if value is None:
        return fallback
    colour = fallback
    for i in range(3, len(expr), 2):
        if value >= expr[i]:
            colour = expr[i + 1]
        else:
            break
    return colour


def eval_match(expr: list, value) -> str:
    """Evaluate a MapLibre match expression for one value."""
    pairs = expr[2:-1]
    for i in range(0, len(pairs), 2):
        if pairs[i] == value:
            return pairs[i + 1]
    return expr[-1]


def style_colours(style_path: Path) -> tuple[str, callable, str]:
    """The field, the colour function, and the layer kind of a default style."""
    style = json.loads(style_path.read_text())
    layer = next(
        layer for layer in style["layers"]
        if layer["type"] in {"fill", "circle"}
    )
    key = "fill-color" if layer["type"] == "fill" else "circle-color"
    expr = layer["paint"][key]
    kind = expr[0]
    getter = expr[1]
    # ["coalesce", ["get", f], 0] or ["get", f]
    field = getter[1][1] if getter[0] == "coalesce" else getter[1]
    if kind == "step":
        return field, (lambda v: eval_step(expr, v)), layer["type"]
    if kind == "match":
        return field, (lambda v: eval_match(expr, v)), layer["type"]
    raise SystemExit(f"{style_path}: default style is neither step nor match")


def frame(bounds, window, target=TARGET_ASPECT):
    """A window at the target aspect, in degrees."""
    west, south, east, north = window or bounds
    # Mercator is not used here: at these extents a plain equirectangular plot
    # with an aspect correction reads correctly, and the frame has to be 3:2 in
    # the plotted coordinates, not in metres.
    cx, cy = (west + east) / 2, (south + north) / 2
    width, height = east - west, north - south
    if width / height < target:
        width = height * target
    else:
        height = width / target
    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def render(name: str) -> None:
    spec = WINDOWS[name]
    rel, window = spec["parquet"], spec["window"]
    tolerance, label, aspect = spec["simplify"], spec["label"], spec["aspect"]
    src = PUBLISH / rel
    if not src.exists():
        sys.exit(f"missing {src}; run the build tools first")
    field, colour_of, kind = style_colours(
        CATALOG / name / "styles" / "default.json"
    )

    gdf = gpd.read_parquet(src, columns=[field, "geometry"])
    west, south, east, north = frame(
        tuple(gdf.total_bounds), window, aspect)
    if window:
        gdf = gdf.cx[west:east, south:north]
    if tolerance:
        gdf = gdf.set_geometry(gdf.geometry.simplify(tolerance))
    colours = [colour_of(v) for v in gdf[field]]

    height_px = int(WIDTH_PX / aspect)
    fig, ax = plt.subplots(
        figsize=(WIDTH_PX / DPI, height_px / DPI), dpi=DPI
    )
    fig.patch.set_facecolor(WATER)
    if kind == "fill":
        gdf.plot(ax=ax, color=colours, linewidth=spec["edge"],
                 edgecolor="#2b2b2b", antialiased=True)
    else:
        gdf.plot(ax=ax, color=colours, markersize=spec.get("markersize", 2.2),
                 linewidth=0, alpha=0.9)
    # After plotting: geopandas resets the axes background.
    ax.set_facecolor(WATER)
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_aspect("auto")
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    out = CATALOG / name / f"{name}.thumb.png"
    fig.savefig(out, dpi=DPI, facecolor=fig.get_facecolor(), pad_inches=0)
    plt.close(fig)
    print(
        f"  {out.relative_to(CATALOG.parent)}: {out.stat().st_size:,} bytes, "
        f"{len(gdf):,} features, {label}, "
        f"bbox {west:.1f},{south:.1f},{east:.1f},{north:.1f}"
    )


def main(argv: list[str]) -> int:
    for name in argv or list(WINDOWS):
        if name not in WINDOWS:
            sys.exit(f"unknown collection {name}")
        render(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
