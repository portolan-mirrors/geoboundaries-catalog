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
| GeoParquet | 104 MB, 193 row groups of 256 rows, zstd, bbox covering |
| PMTiles | 101 MB, zoom 0-9 |
| CRS | CRS84 (EPSG:4326), as published |
| Vertices | 12,980,126 as published, a mean of 263 per unit, 187,879 at most (The upstream GeoPackage holds 13,183,670; this catalog publishes fewer because `ST_MakeValid` drops degenerate vertices from the geometry it repairs) |

## Why the row groups are small

193 row groups of 256 rows is the point of this collection. The CGAZ ADM2
mirror this one replaces put all 49,349 rows in a single row group, so a client
that wanted one municipality's geometry had to read the whole geometry column
chunk — close to 100 MB for one polygon. Here that fetch is a single range
request of about 520 KB, and the GeoParquet 1.1 bbox covering column plus a
Hilbert row order let a reader find the right group without decoding any
geometry.

The size is not a bytes-per-group target. hyparquet, the reader a browser uses,
has no sub-chunk read, so one feature costs one whole row group; but the
Parquet footer carries a record per column per row group and a range client
reads it before any data, so a smaller group means a larger footer. 256 rows is
what minimizes the sum — the trailing bytes plus one row group, which is what a
client's first select costs. Here that first select is 781.5 KB.

Row group statistics are written only for `shapeID`, `shapeGroup` and the four
`bbox` struct leaves, which are the only columns a Hilbert-sorted file lets a
client prune on. That alone cut the trailing bytes from 670,381 to 346,581.

Every column also carries a Parquet page index, so a reader can narrow further
inside a group.

## How these polygons were made

For each country, geoBoundaries takes its own `gbOpen` ADM2 file, reduces it to
roughly a tenth of its vertices with mapshaper, and clips the result to that
country's US Department of State outline. Where no second-level data exists the
build falls back to the country's first-level file, and failing that to its
country polygon. The results are merged and gap-filled, and 20 disputed-area
polygons are merged in.

> **Not a byte-for-byte mirror.** This catalog repairs faults in the upstream
> release and adds products geoBoundaries does not publish. Every deviation,
> with how to reproduce it and how to get the vanilla behaviour, is in
> [changes-from-upstream.md](../changes-from-upstream.md).

## The display file

`cgaz_adm2_display.parquet` holds **the same rows in the same order with the
same row group boundaries** as the data file, with geometry simplified and then
buffered outward by the same distance. Row *i* and row group *g* mean the same
unit in both, so one byte-range plan serves either. It is 42 MB against the
data file's 104 MB, and one unit's outline costs about 191 KB there against
520 KB in the data file.

Use it to draw an outline, and to pre-filter another dataset to this unit. The
outward bias is deliberate: a filter shape that sits inside the true boundary
silently drops features along the edge, and over-fetching is cheap. Every
feature retains at least 99% of its original area, the worst case being Contla
de Juan Cuamatzi (MEX) at 99.1461%.

Do **not** measure area from it, do not use it to decide which side of a
border a point falls on, and do not publish it as a boundary: neighbouring
units overlap in the margin. For any of that, read the data file. The full
rule and the latitude caveat on a buffer measured in degrees are in the
[catalog agent guide](../AGENTS.md).

**This level gained its display file on 2026-11-12**, reversing an earlier
decision that was right about the wrong quantity. CGAZ already simplifies ADM2
upstream — the median unit is 82 coordinates, the 90th percentile 560, the 99th
2,837, and only 14 rows of 49,349 exceed 20,000 — so *decoding* one unit was
never slow. But a client does not decode one unit from an isolated byte range:
it fetches the whole row group's geometry column chunk, and against the live
catalog that was a median of 1.35 MB and 2.1 seconds, worst case 3.5 MB and
4.3 seconds. The cost was bytes per row group, and what fills a row group is
the tail — the 99th percentile and those 14 huge rows — not the median 82.

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
- **843 of the 49,349 geometries were not OGC-valid upstream, and all 843 are
  repaired here.** 0 rows fail `ST_IsValid` now. Area introduced is under
  0.24 km² on every row but one: Sabaya (BOL) moves from 6,304.4 to 6,969.5
  km², because the signed-area sum over its self-overlapping ring was
  cancelling part of the shape.
- **Simplification collapses the smallest units.** 107 rows measure under
  0.1 km², concentrated in Saint Lucia's urban districts and Pacific atolls.
- **14 names are double-encoded upstream and are repaired here** — 10 New
  Zealand names whose macrons arrive damaged, 4 Peruvian provinces. Several
  Norwegian names still carry quotation marks and a trailing " nor" from their
  source file; that is a spelling in the source, not an encoding fault, so it
  is left alone.
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
| Outline compactness | Polsby-Popper ratio | 175 / 1,218 / 8,741 / 20,755 / 18,460 |

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
[repository](https://github.com/portolan-mirrors/geoboundaries-catalog).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

-- The smallest units around central Nairobi, pruned on the bbox column
SELECT shapeName, shapeGroup, round(area_km2, 1) AS area_km2
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm2/cgaz_adm2.parquet'
WHERE bbox.xmin < 36.9 AND bbox.xmax > 36.7
  AND bbox.ymin < -1.2 AND bbox.ymax > -1.4
ORDER BY area_km2 LIMIT 6;
```
