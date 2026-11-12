# CGAZ ADM0 — Country Boundaries

The 218 country-level polygons of the geoBoundaries **Comprehensive Global
Administrative Zones** composite: 198 recognized countries and 20 disputed
areas, as GeoParquet you can query in place and PMTiles you can draw.

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

| | |
|---|---|
| Rows | 218 (198 `ADM0`, 20 `DISP`) |
| GeoParquet | 97 MB, 55 row groups of 4 rows, zstd, bbox covering |
| PMTiles | 7.1 MB, zoom 0-6 |
| CRS | CRS84 (EPSG:4326), as published |
| Vertices | 10,101,960, a mean of 46,339 per country |

## What these boundaries are, and are not

CGAZ outlines come from the **US Department of State Large Scale International
Boundaries** file, dissolved to one polygon per ISO code. geoBoundaries
describes the composite as "clipped to international boundaries (US Department
of State), with gaps filled between borders", and says "disputed areas are
removed and replaced with polygons following US Department of State
definitions".

So these are **not** the boundaries a country claims for itself. geoBoundaries'
per-country releases do represent each nation "as they would represent
themselves", and two of those can overlap; these cannot. If sovereignty matters
to your use, this is the wrong product.

Dependent territories are merged into their parent state, so Greenland is part
of the Denmark polygon and has no row of its own. 218 rows is not a list of 218
sovereign states.

Unlike the ADM1 and ADM2 levels, **this level is not simplified** — the vertex
reduction in the upstream build applies to the lower levels only. That is why
218 country polygons weigh more than 49,349 municipalities. Use the PMTiles
archive to draw outlines; the GeoParquet is for analysis.

## Known issues

- **No `shapeID` column.** ADM1 and ADM2 have one; CGAZ ADM0 does not publish
  it. `shapeGroup` is the join key here, and it is unique.
- **20 rows are disputed areas, not countries.** Filter on
  `shapeType = 'ADM0'` for the 198 recognized ones.
- **`shapeGroup` is not an ISO code for those 20 rows.** They carry `111`
  through `129`, except Western Sahara which uses `ESH`.
- **87 of the 218 geometries are not OGC-valid.** The same 87 fail on a direct
  conversion of the upstream GeoPackage, so the invalidity is upstream. Call
  `ST_MakeValid` before any overlay; drawing and bbox queries are unaffected.
- **No validity dates.** geoBoundaries records a year represented per source
  boundary; the CGAZ build drops it.
- **Areas are measured, not official.** `area_km2` is geodesic area on the
  published geometry. For this level the geometry is full-resolution, so the
  numbers land close to published figures (Albania 28,679 against 28,748 km²),
  but they are still derived.

The full list, with the queries behind each number, is in
[AGENTS.md](AGENTS.md).

## Styles

Four, each built from a measured distribution:

| style | shows | classes |
|---|---|---|
| Country area (default) | geodesic area in six bands | 37 / 31 / 57 / 47 / 36 / 10 |
| Recognized boundary or disputed area | `shapeType` | 198 / 20 |
| First-level units per country | `adm1_units` | 23 / 80 / 84 / 25 / 6 |
| Outline compactness | Polsby-Popper ratio | 51 / 50 / 73 / 33 / 11 |

## License

**CC-BY-4.0.** Attribution is required. In written work, cite:

> Runfola, D. et al. (2020) geoBoundaries: A global database of political
> administrative boundaries. PLoS ONE 15(4): e0231866.
> [https://doi.org/10.1371/journal.pone.0231866](https://doi.org/10.1371/journal.pone.0231866)

On the web, show "geoBoundaries" linked to
[www.geoboundaries.org](https://www.geoboundaries.org/) somewhere prominent on
the page that uses the boundaries. Country outlines derive from the US
Department of State LSIB file.

## Provenance

Built from
[geoBoundariesCGAZ_ADM0.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM0.gpkg)
(162 MB), downloaded 2026-11-12. The release mirrored here is commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20, the last commit that changed any file under
`releaseData/CGAZ`; CGAZ is served from the default branch through git-lfs, so
the URL alone does not pin a version.

Nothing is reprojected. The upstream GeoPackage declares `srs_id = 0`,
"Undefined geographic SRS", for coordinates that are plainly degrees, so the
build assigns EPSG:4326. One column is dropped, an `id` column that is NULL in
all 218 rows. Everything added is measured: geodesic area and perimeter, a
compactness ratio, unit counts from the other two levels, and a bbox covering
struct. The complete transform list is in `.portolan/metadata.yaml` in the
[repository](https://github.com/portolan-mirrors/geoboundaries-catalog).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

SELECT shapeName, shapeGroup, adm1_units, adm2_units
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm0/cgaz_adm0.parquet'
WHERE shapeType = 'ADM0'
ORDER BY adm2_units DESC LIMIT 10;
```
