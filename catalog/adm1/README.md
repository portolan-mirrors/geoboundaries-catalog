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
| GeoParquet | 81 MB, 202 row groups of 16 rows, zstd, bbox covering |
| PMTiles | 17 MB, zoom 0-7 |
| CRS | CRS84 (EPSG:4326), as published |
| Vertices | 8,644,779 as published, a mean of 2,681 per unit (The upstream GeoPackage holds 8,830,663; this catalog publishes fewer because `ST_MakeValid` drops degenerate vertices from the geometry it repairs) |

## How these polygons were made

For each country, geoBoundaries takes its own `gbOpen` ADM1 file, reduces it to
roughly a tenth of its vertices with mapshaper, and clips the result to that
country's US Department of State outline. The per-country results are merged
and gap-filled, and 20 disputed-area polygons are merged in.

Where a country has no first-level data the build substitutes its country
polygon, which is why two rows here — Antarctica and Vatican City — are whole
countries. The composite has no holes; the `shapeType` column is what tells you
what you are looking at.

> **Not a byte-for-byte mirror.** This catalog repairs faults in the upstream
> release and adds products geoBoundaries does not publish. Every deviation,
> with how to reproduce it and how to get the vanilla behaviour, is in
> [changes-from-upstream.md](../changes-from-upstream.md).

## The display file

`cgaz_adm1_display.parquet` holds **the same rows in the same order with the
same row group boundaries** as the data file, with geometry simplified and
then buffered outward by the same distance. Row *i* and row group *g* mean the
same unit in both, so one byte-range plan serves either. It is 13 MB against
the data file's 81 MB, and one unit's outline costs about 39 KB there against
251 KB in the data file.

Use it to draw an outline, and to pre-filter another dataset to this unit. The
outward bias is deliberate: a filter shape that sits inside the true boundary
silently drops features along the edge, and over-fetching is cheap. Every
feature retains at least 99.87% of its original area, the worst case being the
Gilbert Islands (KIR) at 99.8714%.

Do **not** measure area from it, do not use it to decide which side of a
border a point falls on, and do not publish it as a boundary: neighbouring
units overlap in the margin. For any of that, read the data file. The full
rule and the latitude caveat on a buffer measured in degrees are in the
[catalog agent guide](../AGENTS.md).

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
- **24 names are double-encoded upstream, and are repaired here.** All 16
  Chilean regions read `RegiÃ³n de ValparaÃ­so` upstream where `Región de
  Valparaíso` was meant, plus 6 Portuguese and 2 Seychelles districts.
  `shapeName` carries the repaired text; the full before-and-after table is in
  [changes-from-upstream.md](../changes-from-upstream.md).
- **346 of the 3,224 geometries were not OGC-valid upstream, and 345 are
  repaired here.** At most 0.0038 km² of area was introduced. The exception is
  Kaafu (MDV), a four-point polygon of zero area that `ST_MakeValid` resolves
  to a line; repairing it would delete the unit, so it is published as
  upstream has it.
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
| Outline compactness | Polsby-Popper ratio | 103 / 363 / 981 / 1,169 / 608 |

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
[repository](https://github.com/portolan-mirrors/geoboundaries-catalog).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

SELECT shapeName, shapeGroup, round(area_km2) AS area_km2, country_units
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm1/cgaz_adm1.parquet'
WHERE shapeType = 'ADM1' AND shapeGroup = 'KEN'
ORDER BY area_km2 DESC LIMIT 10;
```
