# CGAZ ADM1 — First-Level Administrative Boundaries

3,224 first-level administrative units worldwide — states, provinces, regions,
governorates, prefectures — from the geoBoundaries **Comprehensive Global
Administrative Zones** composite, as GeoParquet you can query in place and
PMTiles you can draw.

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

| | |
|---|---|
| Rows | 3,224 (3,202 `ADM1`, 20 `DISP`, 2 `ADM0`) |
| GeoParquet | 76 MB, 51 row groups of 64 rows, zstd, bbox covering |
| PMTiles | 17 MB, zoom 0-7 |
| CRS | CRS84 (EPSG:4326), as published |
| Vertices | 8,830,663, a mean of 2,739 per unit |

## How these polygons were made

For each country, geoBoundaries takes its own `gbOpen` ADM1 file, reduces it to
roughly a tenth of its vertices with mapshaper, and clips the result to that
country's US Department of State outline. The per-country results are merged
and gap-filled, and 20 disputed-area polygons are merged in.

Where a country has no first-level data the build substitutes its country
polygon, which is why two rows here — Antarctica and Vatican City — are whole
countries. The composite has no holes; the `shapeType` column is what tells you
what you are looking at.

## Known issues

- **Not every row is a first-level unit.** 3,202 are; 20 are disputed areas and
  2 are whole countries. Filter on `shapeType = 'ADM1'`.
- **No parent key.** Nothing links a first-level unit to the second-level units
  inside it. `shapeID` prefixes are per country *and* per level, so Afghanistan
  is `12653393` here and `17698898` at ADM2 and the two cannot be matched.
  Building the hierarchy means a spatial join, which on simplified clipped
  geometry misassigns units along shared edges. This is the largest gap in the
  dataset.
- **Geometry is simplified and clipped**, so it is not the source geometry. Use
  geoBoundaries' single-country releases when you need the full-resolution
  original.
- **25 names are double-encoded upstream**, including all 16 Chilean regions,
  which read `RegiÃ³n de ValparaÃ­so` where `Región de Valparaíso` was meant.
  `shapeName` carries the damage through, because this is a mirror; the
  [names collection](../names/collection.json) repairs it in its searchable
  column so the units stay findable.
- **346 of the 3,224 geometries are not OGC-valid**, and the same 346 fail on a
  direct conversion of the upstream GeoPackage, so the invalidity is upstream.
  Call `ST_MakeValid` before any overlay.
- **Simplification collapses the smallest units.** Four rows measure under
  0.1 km², and Kaafu in the Maldives measures 0.0 km² from four vertices. Do
  not use this level for small-island work.
- **No validity dates**, and no per-unit source license: the CGAZ build drops
  both fields that geoBoundaries records per source boundary.

The full list, with the queries behind each number, is in
[AGENTS.md](AGENTS.md).

## Styles

Four, each built from a measured distribution:

| style | shows | classes |
|---|---|---|
| First-level unit area (default) | geodesic area in six bands | 519 / 575 / 838 / 741 / 435 / 116 |
| First-level units in this country | `country_units` | 23 / 539 / 959 / 937 / 766 |
| What each polygon really is | `shapeType` | 3,202 / 2 / 20 |
| Outline compactness | Polsby-Popper ratio | 103 / 364 / 980 / 1,169 / 608 |

## License

**CC-BY-4.0.** Attribution is required. In written work, cite:

> Runfola, D. et al. (2020) geoBoundaries: A global database of political
> administrative boundaries. PLoS ONE 15(4): e0231866.
> [https://doi.org/10.1371/journal.pone.0231866](https://doi.org/10.1371/journal.pone.0231866)

On the web, show "geoBoundaries" linked to
[www.geoboundaries.org](https://www.geoboundaries.org/) somewhere prominent on
the page that uses the boundaries.

## Provenance

Built from
[geoBoundariesCGAZ_ADM1.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM1.gpkg)
(144 MB), downloaded 2026-11-12. The release mirrored here is commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20.

Nothing is reprojected: the upstream GeoPackage declares `srs_id = 0`,
"Undefined geographic SRS", for coordinates that are plainly degrees, so the
build assigns EPSG:4326. One column is dropped, an `id` column that is NULL in
all 3,224 rows. Everything added is measured: geodesic area and perimeter, a
compactness ratio, a per-country unit count, and a bbox covering struct. The
complete transform list is in `.portolan/metadata.yaml` in the
[repository](https://github.com/portolan-mirrors/geoboundaries).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

SELECT shapeName, shapeGroup, round(area_km2) AS area_km2, country_units
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries/adm1/cgaz_adm1.parquet'
WHERE shapeType = 'ADM1' AND shapeGroup = 'KEN'
ORDER BY area_km2 DESC LIMIT 10;
```
