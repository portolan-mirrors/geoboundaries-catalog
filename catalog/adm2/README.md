# CGAZ ADM2 — Second-Level Administrative Boundaries

49,349 second-level administrative units worldwide — counties, districts,
municipalities, communes, municípios — from the geoBoundaries **Comprehensive
Global Administrative Zones** composite, as GeoParquet you can query in place
and PMTiles you can draw.

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

| | |
|---|---|
| Rows | 49,349 (49,015 `ADM2`, 312 `ADM1`, 20 `DISP`, 2 `ADM0`) |
| GeoParquet | 101 MB, 97 row groups of 512 rows, zstd, bbox covering |
| PMTiles | 101 MB, zoom 0-9 |
| CRS | CRS84 (EPSG:4326), as published |
| Vertices | 13,183,670, a mean of 267 per unit |

## Why the row groups are small

97 row groups of 512 rows is the point of this collection. The CGAZ ADM2 mirror
this one replaces put all 49,349 rows in a single row group, so a client that
wanted one municipality's geometry had to read the whole geometry column chunk —
about 97 MB for one polygon. Here that fetch is a single range request of about
1 MB, and the GeoParquet 1.1 bbox covering column plus a Hilbert row order let
a reader find the right group without decoding any geometry.

Every column also carries a Parquet page index, so a reader can narrow further
inside a group.

## How these polygons were made

For each country, geoBoundaries takes its own `gbOpen` ADM2 file, reduces it to
roughly a tenth of its vertices with mapshaper, and clips the result to that
country's US Department of State outline. Where no second-level data exists the
build falls back to the country's first-level file, and failing that to its
country polygon. The results are merged and gap-filled, and 20 disputed-area
polygons are merged in.

## Known issues

- **334 of 49,349 rows are not second-level units.** 312 are first-level units
  standing in for 22 countries that have no second level — Malta contributes 68,
  Moldova 37, Montenegro 23 — plus 20 disputed areas and 2 whole countries.
  Filter on `shapeType = 'ADM2'` for the 49,015 genuine ones.
- **37 rows have no name at all**: 24 in Japan, 12 in Turkmenistan, 1 in China.
  They are real polygons with real `shapeID`s and are kept here, but they are
  absent from the [names collection](../names/collection.json), which is
  therefore 37 rows short of this file's named units.
- **No parent key.** Nothing links a second-level unit to the first-level unit
  containing it, and the `shapeID` prefixes differ between levels, so no prefix
  match works. Building the hierarchy means a spatial join, which on simplified
  clipped geometry misassigns units along shared edges.
- **Names repeat heavily.** 45,116 distinct names over 49,312 named rows. 32
  units fold to "washington". Join on `shapeID`, never on `shapeName`.
- **"Second level" means different things in different countries** — a US
  county, a Brazilian município, a French commune. The level is structural, not
  semantic, and `area_km2` spans 0.000 to 12,063,872 in one column.
- **843 of the 49,349 geometries are not OGC-valid**, and the same 843 fail on
  a direct conversion of the upstream GeoPackage, so the invalidity is
  upstream. Call `ST_MakeValid` before any overlay.
- **Simplification collapses the smallest units.** 107 rows measure under
  0.1 km², concentrated in Saint Lucia's urban districts and Pacific atolls.
- **Six names are double-encoded upstream**, and several Norwegian names carry
  quotation marks and a trailing " nor" from their source file.
- **No validity dates**, and no per-unit source license: the CGAZ build drops
  both fields that geoBoundaries records per source boundary.

The full list, with the queries behind each number, is in
[AGENTS.md](AGENTS.md).

## Styles

Four, each built from a measured distribution:

| style | shows | classes |
|---|---|---|
| Second-level unit area (default) | geodesic area in six bands | 7,154 / 11,522 / 12,394 / 13,483 / 4,069 / 727 |
| Second-level units in this country | `country_units` | 116 / 4,924 / 13,446 / 11,674 / 19,189 |
| What each polygon really is | `shapeType` | 49,015 / 312 / 2 / 20 |
| Outline compactness | Polsby-Popper ratio | 175 / 1,218 / 8,742 / 20,754 / 18,460 |

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
[geoBoundariesCGAZ_ADM2.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM2.gpkg)
(241 MB), downloaded 2026-11-12. The release mirrored here is commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20.

Nothing is reprojected: the upstream GeoPackage declares `srs_id = 0`,
"Undefined geographic SRS", for coordinates that are plainly degrees, so the
build assigns EPSG:4326. One column is dropped, an `id` column that is NULL in
all 49,349 rows. Everything added is measured: geodesic area and perimeter, a
compactness ratio, a per-country unit count, and a bbox covering struct. The
complete transform list is in `.portolan/metadata.yaml` in the
[repository](https://github.com/portolan-mirrors/geoboundaries).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

-- The smallest units around central Nairobi, pruned on the bbox column
SELECT shapeName, shapeGroup, round(area_km2, 1) AS area_km2
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries/adm2/cgaz_adm2.parquet'
WHERE bbox.xmin < 36.9 AND bbox.xmax > 36.7
  AND bbox.ymin < -1.2 AND bbox.ymax > -1.4
ORDER BY area_km2 LIMIT 6;
```
