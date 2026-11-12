<!-- Published copy. The source is docs/changes-from-upstream.md in
     https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main, and tools/make_changes_doc.py keeps the two in step.
     Edit the source, not this file. -->

# Changes from vanilla geoBoundaries

**This catalog is not a byte-for-byte mirror.** It repairs faults in the
upstream release and adds products geoBoundaries does not publish. Every
deviation is listed here, with what changed, why, how to reproduce it, and how
to get the vanilla behaviour instead.

Upstream release mirrored: commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20, the last commit that changed any file under
`releaseData/CGAZ`. Downloaded 2026-11-12.

## How to get vanilla geoBoundaries

Every collection carries a `source-gpkg` asset pointing at the upstream file it
was built from, with `file:size` and `file:checksum` recorded so you can
confirm you have the same bytes:

- [geoBoundariesCGAZ_ADM0.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM0.gpkg) — 162,144,256 bytes
- [geoBoundariesCGAZ_ADM1.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM1.gpkg) — 144,470,016 bytes
- [geoBoundariesCGAZ_ADM2.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM2.gpkg) — 240,824,320 bytes

Those URLs serve the current default branch, so they move. Check the checksum
against the asset before assuming you have the release this catalog mirrors.

## Summary

| # | Change | Kind | Scope |
|---|---|---|---|
| 1 | Double-encoded names repaired | fix | 38 rows |
| 2 | Invalid geometry repaired with `ST_MakeValid` | fix | 1,276 of 52,791 rows |
| 3 | All-NULL `id` column dropped | removal | every row |
| 4 | CRS assigned (upstream declares none) | fix | every row |
| 5 | Measured columns added | addition | every row |
| 6 | Hilbert row order, and row groups sized for single-feature reads | restructure | every row |
| 7 | GeoParquet 1.1 bbox covering column added | addition | every row |
| 8 | Format: GeoPackage to GeoParquet and PMTiles | restructure | every row |
| 9 | Name search index | new product | ours entirely |
| 10 | Display geometry sidecars | new product | ours entirely, all three levels |
| 11 | Row group statistics restricted to the prunable columns | restructure | every row group |

Nothing is filtered out: every row and every attribute of the upstream release
is present, including the 20 disputed areas, the backfilled coarser-level rows
and the 37 rows with no name.

---

## 1. Double-encoded names repaired

**What.** 38 `shapeName` values in the upstream release are UTF-8 bytes that
were read once as Latin-1 and re-encoded, so they publish as `RegiÃ³n de
ValparaÃ­so` where `Región de Valparaíso` was meant. This catalog publishes
the repaired text in `shapeName` (boundary collections) and `name` (names
collection). 24 are in the ADM1 file and 14 in the ADM2 file; ADM0 has none.

**Why.** The damaged form is not a name anyone types, searches for, or wants on
a label. Carrying it verbatim would make 38 administrative units effectively
unreachable through this catalog's own search index, which is the catalog's
main purpose.

**How it is decided.** The damage is a pure byte-level round trip, so encoding
the string back to Latin-1 and decoding it as UTF-8 reverses it exactly. The
repair is applied only when the string holds one of the lead sequences `Ã`,
`Â`, `â€`, `Å`, `Ä`, the round trip succeeds, and the result differs. The
guard is what lets legitimate Nordic names through: `Äänekoski` starts with a
lead sequence, but encoded to Latin-1 it is not valid UTF-8, so the round trip
raises and the name is kept. All 38 hits were inspected by hand. There is no
false positive, and nothing else in the catalog is touched.

**How to reproduce.** `repair_mojibake` in
[`tools/gbcommon.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/gbcommon.py), applied in
[`tools/build_boundaries.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_boundaries.py).

```bash
python3 tools/mojibake_report.py          # regenerates the table below
python3 tools/mojibake_report.py --count  # 38
```

**How to get vanilla.** Read `shapeName` from the upstream GeoPackage.

### The 38 names

Regenerate with `python3 tools/mojibake_report.py`.

| level | country | as geoBoundaries publishes it | as published here |
|---|---|---|---|
| ADM1 | `CHL` | `RegiÃ³n Metropolitana de Santiago` | Región Metropolitana de Santiago |
| ADM1 | `CHL` | `RegiÃ³n de Antofagasta` | Región de Antofagasta |
| ADM1 | `CHL` | `RegiÃ³n de Arica y Parinacota` | Región de Arica y Parinacota |
| ADM1 | `CHL` | `RegiÃ³n de Atacama` | Región de Atacama |
| ADM1 | `CHL` | `RegiÃ³n de AysÃ©n del Gral.IbaÃ±ez del Campo` | Región de Aysén del Gral.Ibañez del Campo |
| ADM1 | `CHL` | `RegiÃ³n de Coquimbo` | Región de Coquimbo |
| ADM1 | `CHL` | `RegiÃ³n de La AraucanÃ­a` | Región de La Araucanía |
| ADM1 | `CHL` | `RegiÃ³n de Los Lagos` | Región de Los Lagos |
| ADM1 | `CHL` | `RegiÃ³n de Los RÃ­os` | Región de Los Ríos |
| ADM1 | `CHL` | `RegiÃ³n de Magallanes y AntÃ¡rtica Chilena` | Región de Magallanes y Antártica Chilena |
| ADM1 | `CHL` | `RegiÃ³n de TarapacÃ¡` | Región de Tarapacá |
| ADM1 | `CHL` | `RegiÃ³n de ValparaÃ­so` | Región de Valparaíso |
| ADM1 | `CHL` | `RegiÃ³n de Ãuble` | Región de Ñuble |
| ADM1 | `CHL` | `RegiÃ³n del BÃ­o-BÃ­o` | Región del Bío-Bío |
| ADM1 | `CHL` | `RegiÃ³n del Libertador Bernardo O'Higgins` | Región del Libertador Bernardo O'Higgins |
| ADM1 | `CHL` | `RegiÃ³n del Maule` | Región del Maule |
| ADM1 | `PRT` | `BRAGANÃA` | BRAGANÇA |
| ADM1 | `PRT` | `RegiÃ£o AutÃ³noma da Madeira` | Região Autónoma da Madeira |
| ADM1 | `PRT` | `RegiÃ£o AutÃ³noma dos AÃ§ores` | Região Autónoma dos Açores |
| ADM1 | `PRT` | `SANTARÃM` | SANTARÉM |
| ADM1 | `PRT` | `SETÃBAL` | SETÚBAL |
| ADM1 | `PRT` | `ÃVORA` | ÉVORA |
| ADM1 | `SYC` | `La RiviÃ¨re` | La Rivière |
| ADM1 | `SYC` | `Roche CaÃ¯m` | Roche Caïm |
| ADM2 | `NZL` | `KaipÄtiki Local Board Area` | Kaipātiki Local Board Area |
| ADM2 | `NZL` | `Maungakiekie-TÄmaki Local Board Area` | Maungakiekie-Tāmaki Local Board Area |
| ADM2 | `NZL` | `MÄngere-ÅtÄhuhu Local Board Area` | Māngere-Ōtāhuhu Local Board Area |
| ADM2 | `NZL` | `PuketÄpapa Local Board Area` | Puketāpapa Local Board Area |
| ADM2 | `NZL` | `WaitematÄ Local Board Area` | Waitematā Local Board Area |
| ADM2 | `NZL` | `WaitÄkere Ranges Local Board Area` | Waitākere Ranges Local Board Area |
| ADM2 | `NZL` | `ÅpÅtiki District` | Ōpōtiki District |
| ADM2 | `NZL` | `ÅrÄkei Local Board Area` | Ōrākei Local Board Area |
| ADM2 | `NZL` | `Åtara-Papatoetoe Local Board Area` | Ōtara-Papatoetoe Local Board Area |
| ADM2 | `NZL` | `Åtorohanga District` | Ōtorohanga District |
| ADM2 | `PER` | `CaÃ±ete` | Cañete |
| ADM2 | `PER` | `Datem del MaraÃ±on` | Datem del Marañon |
| ADM2 | `PER` | `FerreÃ±afe` | Ferreñafe |
| ADM2 | `PER` | `MaraÃ±on` | Marañon |

Note that the repair fixes the encoding and nothing else. `Datem del Marañon`
and `Marañon` keep the missing accent on the final `o` that the upstream source
has; that is a spelling in the source data, not an encoding fault, so it is
left alone.

## 2. Invalid geometry repaired

**What.** 1,276 of the 52,791 boundary rows fail `ST_IsValid` in the upstream
release. All but one are repaired here.

| level | invalid upstream | repaired | left as-is |
|---|---|---|---|
| ADM0 | 87 | 87 | 0 |
| ADM1 | 346 | 345 | 1 |
| ADM2 | 843 | 843 | 0 |

The one exception is **Kaafu (MDV)** in the ADM1 file, a four-point polygon of
zero area. `ST_MakeValid` resolves it to a line, so a polygon-only repair would
delete the unit. Deleting an administrative unit is worse than carrying an
invalid geometry, so that row is published exactly as upstream has it.

**Why.** Invalid geometry is not a cosmetic problem. A self-intersecting ring
makes area, overlay, union and intersection undefined, and a client doing
spatial work against this catalog would get silently wrong answers with no
error. Repairing once, here, is cheaper than every consumer discovering it.

**How.** `ST_CollectionExtract(ST_MakeValid(geometry), 3)`. `ST_MakeValid` can
return a `GEOMETRYCOLLECTION` holding the repaired polygons plus zero-area
lines and points; `ST_CollectionExtract(..., 3)` keeps the polygons. Measured,
that discards 0.0 square degrees — the dropped parts have no area.

**Rows that were already valid are untouched.** The builder branches on
`ST_IsValid` and passes a valid row through rather than round-tripping it
through GEOS. Verified: 0 valid rows changed, byte-identical WKB.

**Area introduced.** On the repaired rows:

| level | max absolute delta | max relative delta |
|---|---|---|
| ADM0 | 0.003 km² | 0.000% |
| ADM1 | 0.0038 km² | 0.0002% |
| ADM2 | 665.13 km² | 10.55% |

The ADM2 figure is **one row**: Sabaya (BOL), a 663-point self-intersecting
polygon whose area went from 6,304.4 km² to 6,969.5 km². The signed-area sum
over an invalid self-overlapping ring cancels part of the shape, so the
"before" number was the wrong one and the repair corrects it rather than
inflating it. The next largest delta anywhere in the catalog is 0.885 km², and
every other row moves by under 0.24 km². Measured delta on rows that were
already valid: exactly 0.

**Note on derived columns.** `area_km2`, `perimeter_km` and `compactness` are
computed *after* the repair, so they describe the published geometry.

**How to reproduce.**

```sql
LOAD spatial;
SELECT count(*) FROM 'work/adm2.raw.parquet' WHERE NOT ST_IsValid(geometry);
-- 843
SELECT count(*) FROM
  'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm2/cgaz_adm2.parquet'
WHERE NOT ST_IsValid(geometry);
-- 0
```

**How to get vanilla.** Read geometry from the upstream GeoPackage.

**PMTiles were rebuilt** after this change, because the tiles carry
`shapeName` and `area_km2` as attributes and those changed. The rendered
outlines are visually unaffected: at tile resolution a self-intersection
repair is below a pixel everywhere except Sabaya.

## 3. All-NULL `id` column dropped

**What.** The upstream GeoPackages carry a column named `id` that is NULL in
every row of all three files: 0 non-null of 218, 3,224 and 49,349. It is not
published here.

**Why.** geoBoundaries' own build lists `id` among the fields it drops, in the
`-drop fields=` argument of
[`gbCGAZBuild.py`](https://github.com/wmgeolab/geoBoundaryBot/blob/main/gbCGAZBuild.py),
so the surviving empty column is an artifact of the TopoJSON to GeoPackage
conversion rather than data. Publishing it would put a column in
`table:columns` that every consumer has to read about and that holds nothing.

**This is the one place the catalog removes something.** Nothing else upstream
is dropped.

**How to reproduce.**
`SELECT count(*), count(id) FROM st_read('geoBoundariesCGAZ_ADM2.gpkg');`
returns `49349, 0`.

**How to get vanilla.** Read the GeoPackage; the column will be there and
empty.

## 4. CRS assigned

**What.** All three upstream GeoPackages declare `srs_id = 0`, "Undefined
geographic SRS", in `gpkg_contents`, for coordinates that are plainly degrees
of longitude and latitude. This catalog publishes them as CRS84 (longitude,
latitude on WGS 84), which in GeoParquet is the default and is written by
omitting the `crs` key.

**Why.** A file that does not say what its coordinates mean cannot be used
without a guess. Software that honours the declaration refuses to reproject,
or reprojects from nothing.

**Nothing is reprojected.** The coordinates are unchanged; only the
declaration is added, with `ogr2ogr -a_srs EPSG:4326`.

**How to reproduce.**
`SELECT srs_id FROM sqlite_scan('geoBoundariesCGAZ_ADM0.gpkg','gpkg_contents');`
returns `0`.

**How to get vanilla.** There is no vanilla to return to: the upstream value
is "undefined", not a different CRS.

## 5. Measured columns added

**What.** These columns do not exist upstream. They are computed from the
published geometry, and every one is reproducible by rerunning
[`tools/build_boundaries.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_boundaries.py).

| column | in | what it is |
|---|---|---|
| `area_km2` | adm0, adm1, adm2 | Geodesic area on the WGS 84 ellipsoid, from `ST_Area_Spheroid(ST_FlipCoordinates(geometry))` |
| `perimeter_km` | adm0, adm1, adm2 | Geodesic perimeter, same basis |
| `compactness` | adm0, adm1, adm2 | Polsby-Popper ratio, `4*pi*area/perimeter²` |
| `country_units` | adm1, adm2 | Rows in the same file sharing this row's `shapeGroup` |
| `adm1_units`, `adm2_units` | adm0 | Rows in the ADM1 and ADM2 collections for this `shapeGroup` |
| `bbox` | all four | See change 7 |

**Why.** `area_km2` and `compactness` are what the styles classify on, and
without them every consumer would reproject to measure anything. The unit
counts answer "how finely is this country divided", which the composite
otherwise only answers with a `GROUP BY` over 49,349 rows.

**The `ST_FlipCoordinates` is not optional.** DuckDB's spheroidal measures read
the first ordinate as latitude. Without the flip, Nepal measured 17,844 km²
against a true 147,181, and 49 of the 218 ADM0 rows came out NaN. With it,
Nepal is 147,578 km² and nothing is NaN. The flipped results agree to better
than 0.01% with `ST_Area(ST_Transform(geometry, 'OGC:CRS84', 'EPSG:6933'))`,
the NSIDC EASE-Grid 2.0 Global projection geoBoundaries says it uses for its
own published area statistics.

**These are measurements, not official figures.** ADM1 and ADM2 geometry is
simplified by geoBoundaries before it reaches this catalog, so areas computed
on it are smaller than the units' published areas.

**How to get vanilla.** Ignore the columns; nothing else depends on them.

## 6. Hilbert row order, and row groups sized for single-feature reads

**What.** Rows are reordered along a Hilbert space-filling curve over the whole
globe, and each file is cut into row groups sized by a measured sweep of what
one feature costs a range client.

| file | rows | row groups | rows per group | one feature | first select |
|---|---|---|---|---|---|
| adm0 | 218 | 218 | 1 | 209.5 KB | 481.2 KB |
| adm1 | 3,224 | 202 | 16 | 251.2 KB | 519.2 KB |
| adm2 | 49,349 | 193 | 256 | 519.7 KB | 781.5 KB |
| names | 52,398 | 35 | 1,536 | 111.4 KB | 187.0 KB |

"One feature" is a cold hyparquet read of one row group, all columns, median
over 24 random rows. "First select" adds the thrift footer, which is what a
client pays on its very first read of a file. At ADM0 that is one row group per
country.

**The sizes were retuned on 2026-11-12**: ADM0 went from 4 rows per group to
1, ADM1 from 64 to 16, ADM2 from 512 to 256. Measured over the real network
against the live catalog beforehand, one ADM2 feature cost 1.35 MB and
2,120 ms, one ADM0 feature 1.23 MB and 2,326 ms, and one ADM1 feature 674.5 KB
and 1,103 ms.

**Why.** This is the reason the catalog exists. Another mirror of this data
put all 49,349 ADM2 rows in a single row group, so a client that wanted one
municipality's geometry had to read the entire geometry column chunk, close to
100 MB, to get one polygon.

The quantity being minimized is specific, and it is not bytes per row group.
hyparquet, the reader a browser uses, has no sub-chunk read: fetching one
feature pulls that row group's whole geometry column chunk, so one feature
costs one row group whatever else is in it. Shrinking row groups is not free
either, because the thrift footer carries one record per column per row group
and the page index one entry per page per column per row group, both at the
end of the file, and a range client reads them before any data. So what the
sweep minimizes is *trailing bytes plus one row group*, which is exactly what
a client's first select costs. The sweep is
[`tools/rowgroup_sweep.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/rowgroup_sweep.py); the chosen sizes are
`ROW_GROUP_ROWS` in [`tools/gbcommon.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/gbcommon.py), with the
reasoning in the comment beside them.

**The full files grew**, by 7.9% at ADM0, 7.5% at ADM1 and 3.8% at ADM2,
because smaller row groups compress worse. That is the deliberate price of the
layout: these files exist to be range-read one feature at a time from a
browser, and the whole-file download is the secondary use, which the upstream
GeoPackage serves better anyway.

| file | before | after |
|---|---|---|
| adm0/cgaz_adm0.parquet | 96,593,435 B | 104,201,824 B |
| adm1/cgaz_adm1.parquet | 74,997,064 B | 80,585,156 B |
| adm2/cgaz_adm2.parquet | 100,448,329 B | 104,282,056 B |
| names/cgaz_names.parquet | 3,895,531 B | 3,901,414 B |

`gpio check` warns that these row group sizes are "very low". That guidance is
written for scan-heavy analytics, where a large row group amortizes per-group
overhead across a full-table read. The tradeoff is accepted and recorded in
[docs/conformance.md](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/docs/conformance.md).

**The trailing metadata is published, so a client never has to guess.** Every
file entry in [`catalog/names/index.json`](./names/index.json) carries
two exact sizes. `footer_bytes` is the whole trailing span, thrift footer plus
page index, so one range request of exactly that many bytes from the end of a
file leaves a client holding all of the file's metadata.
`footer_metadata_bytes` is the thrift footer alone, the minimum a reader needs
to locate row groups, and it is what a hyparquet client should pass as
`initialFetchSize`, because hyparquet never reads the page index bodies.

| file | `footer_bytes` | `footer_metadata_bytes` |
|---|---|---|
| names/cgaz_names.parquet | 107,089 | 75,606 |
| adm0 full | 348,440 | 271,716 |
| adm0 display | 251,358 | 189,008 |
| adm1 full | 353,080 | 267,958 |
| adm1 display | 279,870 | 205,330 |
| adm2 full | 346,581 | 261,810 |
| adm2 display | 274,277 | 200,258 |

Without these a client pays hyparquet's speculative 512 KiB (524,288-byte)
tail on the first read of every file, and on any file whose footer exceeds
512 KiB it pays a second round trip as well.

**Row order is not meaningful data.** The upstream file order carries no
information: it is the order countries were processed in. Nothing upstream
references a row index.

**The Hilbert order needs a tiebreaker to be reproducible.**
`tools/build_boundaries.py`'s `ORDER BY ST_Hilbert(...)` carries a
`shapeGroup, shapeName, shapeID` tiebreaker and forces
`preserve_insertion_order = true`. The Hilbert key alone is not a total order,
so without a tiebreaker a rebuild could reorder rows arbitrarily — and a
rebuild that reorders rows stales every display file and every `geometry_ref`
in the names index at once. The sibling Overture catalog hit exactly this on
4,724 locality rows.

**How to reproduce.**

```bash
python3 tools/rowgroup_sweep.py     # the row group size sweep
python3 tools/build_boundaries.py   # write the files at the chosen sizes
```

**How to get vanilla.** There is no vanilla row group layout to return to: a
GeoPackage is a SQLite database and has no row groups at all. Sort by whatever
you need; the rows are the same rows.

## 7. bbox covering column added

**What.** Every file carries a `bbox` struct column of `xmin`, `ymin`, `xmax`,
`ymax`, declared in the GeoParquet 1.1 `covering` metadata.

**Why.** It lets a reader skip row groups on a spatial predicate without
decoding any WKB, and it gives a client the extent to fly a map to after a
search hit.

Two details worth knowing. GDAL would have named this column `geometry_bbox`;
this catalog names it `bbox`, and the name is in the `geo` metadata, so read
it there rather than assuming either. And in the **names** collection only, the
struct is `float32` rather than `float64`, with every bound rounded outward so
the box still contains the unit — that halves what it costs in a file meant to
be loaded whole in a browser. Verified: 0 of 48,978 joined rows have a bbox
narrower than their true extent. Precision is about 1e-5 degrees, roughly a
metre. The boundary collections keep `float64`.

**How to get vanilla.** Ignore the column.

## 8. Format

**What.** GeoPackage in, GeoParquet 1.1 (WKB, zstd level 15, Parquet page
index on every column) and PMTiles out.

**Why.** A GeoPackage has to be downloaded whole before it can be queried. The
whole point of this catalog is reading in place over HTTP range requests.

**How to get vanilla.** The `source-gpkg` asset on each collection links the
original file.

## 9. Name search index — entirely our product

**What.** The `names` collection does not exist upstream in any form. It is one
row per named administrative unit across all three levels, 52,398 rows, sorted
by a folded form of the name, with `name_norm`, `country_name`, `name_dupes`,
a point inside the unit, and the `shapeID` that joins back to geometry.

**Why.** geoBoundaries publishes boundaries, not a gazetteer. A browser
geocoder needs to turn typed text into an identifier without a server, and
nothing upstream supports that.

**What it is derived from.** The three boundary collections in this catalog,
not the upstream GeoPackages, so the index and the geometry it points at cannot
disagree.

**What it leaves out.** Rows whose own `shapeType` does not match the file they
sit in, so a unit is indexed once rather than three times; and the 37 rows with
no `shapeName`, because there is nothing to search for. Both are documented in
[the collection's agent guide](./names/AGENTS.md).

**How to reproduce.**
[`tools/build_names.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_names.py).

**How to get vanilla.** There is no upstream equivalent. Build your own index
from the GeoPackages, or ignore the collection.

## 10. Display geometry sidecars — entirely our product

**What.** All three boundary collections carry a second GeoParquet file,
`cgaz_adm{N}_display.parquet`, holding the same rows in the same order with
simplified, outward-buffered geometry and the identity columns.

| | full resolution | display | ratio | max coordinates per feature |
|---|---|---|---|---|
| ADM0 | 104,201,824 B | 7,521,581 B | 13.9x | 528,021 → 68,973 |
| ADM1 | 80,585,156 B | 13,179,712 B | 6.1x | 572,801 → 54,043 |
| ADM2 | 104,282,056 B | 42,419,433 B | 2.5x | 187,879 → 36,029 |

Spot checks at ADM0: the United Kingdom goes from 61,752 coordinates to 6,815,
Norway from 131,567 to 16,434, Canada from 528,021 to 68,973, and all three
stay recognisable with their island groups intact.

**Why.** CGAZ ADM0 is not simplified upstream — the vertex reduction in the
geoBoundaries build applies to ADM1 and ADM2 only — so one country outline can
be hundreds of thousands of coordinates. A browser that decodes the United
Kingdom from the full-resolution file to draw a highlight stops responding.

### ADM2 gained its display file on 2026-11-12

This reverses an earlier decision, recorded here and elsewhere in this catalog
as "ADM2 has no display file". The old reasoning was right about the wrong
quantity. ADM2 geometry *is* already simplified upstream — the median unit is
82 coordinates, the 90th percentile 560, the 99th 2,837, and only 14 rows of
49,349 exceed 20,000 — so *decoding* one unit was never slow.

But a client does not decode one unit from an isolated byte range. hyparquet
has no sub-chunk read, so fetching one ADM2 feature pulls that row group's
entire geometry column chunk, and measured against the live catalog that was a
median of 1.35 MB and 2.1 seconds, worst case 3.5 MB and 4.3 seconds. The cost
was bytes per row group, and it is the **tail** that fills a row group — the
99th percentile and those 14 huge rows — not the median 82.

**The divisor is 18 at ADM2, against 25 at ADM0 and ADM1.** 25 is about 4% of
a unit's width; 18 is about 5.6%. The extra came from the byte budget: a
256-row group has to land near 150 KB, and divisor 25 left the median group at
165 KiB. The sweep over all 49,349 features:

| divisor | file | median row group | worst containment | features under 99% |
|---|---|---|---|---|
| 25 | 44.92 MB | 165 KiB | 99.332% | 0 |
| 20 | 43.11 MB | 156 KiB | 99.042% | 0 |
| **18** | **42.42 MB** | **151 KiB** | **99.146%** | **0** |
| 16 | 41.79 MB | 147 KiB | 98.883% | 1 |
| 15 | 41.50 MB | 146 KiB | 99.050% | 0 |

**Containment is not monotonic in the divisor** — 16 fails where 15 does not —
because a coarser simplification can remove the very vertex whose corner the
buffer then fails to cover. That is why 18 was chosen rather than riding the
aggressive end of a non-monotonic curve.

`ST_ReducePrecision` was tried as a cheaper lever and rejected: it raises
`TopologyException: side location conflict` on the ADM2 geometry at both 1e-4
and 3e-4.

Result: 12,980,126 coordinates reduced to 2,854,112, a factor of 4.5, with a
maximum of 36,029 per feature, 0 empty geometries and 0 invalid ones. Geometry
per row group is a median of 151 KiB, a 95th percentile of 430 KiB and a
maximum of 1,173 KiB.

**The three properties that make it a drop-in parallel read.** Identical row
count, identical row order and identical row group boundaries, so row *i* and
row group *g* mean the same thing in both files and one byte-range plan serves
either. The same identity columns, so a hit from the names index joins the same
way. Its own bbox covering column, so it prunes on its own.

**The geometry is deliberately outward-biased.**

```sql
ST_Buffer(ST_SimplifyPreserveTopology(geometry, tol), tol, 2)
-- tol = greatest(1e-6, least(0.01, sqrt(ST_Area(geometry)) / divisor))
-- divisor = 25 at ADM0 and ADM1, 18 at ADM2
```

Simplification alone cuts corners inward, and a shape used as a spatial filter
that sits inside the true boundary silently drops features near the edge.
Buffering outward by the simplification tolerance makes the result contain the
original instead. Over-fetching is cheap; a missing edge feature is a wrong
answer.

**The tolerance is capped per feature at a fraction of the unit's own size.**
A flat 0.01 degrees is about 1.1 km, which is nothing against a country and
almost everything against Sliema, a Maltese local council of 1.3 km². Measured
with a flat tolerance, Sliema lost 8% of its area and Baiti in Nauru 9%.
Scaling the tolerance by `sqrt(area)/25` keeps the displacement under about 4%
of a unit's width whatever its size, and leaves large units on the flat 0.01.
At ADM2 the divisor is 18, which is about 5.6%, for the reason given above.

**Verified** against the full-resolution file, row by row through a
`POSITIONAL JOIN`:

| | ADM0 | ADM1 | ADM2 |
|---|---|---|---|
| rows, row groups aligned | 218 in 218 | 3,224 in 202 | 49,349 in 193 |
| coordinates | 501,232 | 893,321 | 2,854,112 |
| max coordinates per feature | 68,973 | 54,043 | 36,029 |
| empty geometries introduced | 0 | 0 | 0 |
| invalid geometries introduced | 0 | 0 | 0 |
| worst area of the original retained | 99.9535% (Kiribati) | 99.8714% (Gilbert Islands, KIR) | 99.1461% (Contla de Juan Cuamatzi, MEX) |
| features retaining under 99% | 0 | 0 | 0 |
| geometry per row group, median / p95 / max | 10 / 131 / 1,001 KiB | 37 / 134 / 1,107 KiB | 151 / 430 / 1,173 KiB |

The five worst-contained features at each level, which is where to look if a
filter built from a display shape behaves oddly:

| level | the five worst |
|---|---|
| ADM0 | Kiribati 99.9535%, St Vincent & the Grenadines 99.9605%, Tonga 99.9750%, Marshall Is 99.9780%, Maldives 99.9853% |
| ADM1 | Gilbert Islands (KIR) 99.8714%, Moore's Island (BHS) 99.9141%, Haa Dhaalu (MDV) 99.9246%, Kardzhali (BGR) 99.9329%, Cabinda (AGO) 99.9484% |
| ADM2 | Contla de Juan Cuamatzi (MEX) 99.1461%, João Monlevade (BRA) 99.1694%, Esan West (NGA) 99.2584%, Općina Borovo (HRV) 99.2588%, IZVOARELE SUCEVEI (ROU) 99.2608% |

**Row alignment is verified, not assumed.**
[`tools/build_display.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_display.py) checks it per level as it
builds, and `tests/test_index_refs.py` samples all three levels: 2,000
`geometry_ref` pointers — 8 at level 0, 121 at level 1 and 1,871 at level 2 —
all resolving to the right unit in both the full and the display file.

Buffering with 8 quadrant segments, the GEOS default, rounds every corner and
puts back more coordinates than simplification removed. 2 segments keeps a
corner cheap while still bulging outward rather than cutting across.

**How much it over-fetches.** The margin is the price of never missing an edge
feature, and it is small for a mainland country and large for scattered
atolls, because a fixed buffer is a bigger fraction of a small shape:

| country | coordinates, full → display | original inside the display shape | display area as % of original |
|---|---|---|---|
| Canada | 528,021 → 68,973 | 99.9999% | 101.5% |
| Indonesia | 253,551 → 18,598 | 99.9998% | 103.4% |
| Chile | 250,687 → 16,990 | 99.9993% | 105.5% |
| Norway | 131,567 → 16,434 | 99.9998% | 106.3% |
| United Kingdom | 61,752 → 6,815 | 99.9999% | 105.0% |
| Kiribati | — | 99.9535% | 252.0% |

Kiribati is the worst case in the catalog and the reason to read this section:
its land is a scatter of atolls a few hundred metres across, so a buffer of a
few hundred metres more than doubles the area. A filter built from it will
over-fetch heavily around such features. It will not miss them.

**Consequences a consumer has to know.** Neighbouring units overlap in the
margin. These shapes are not cartographic boundaries: do not measure area from
them, do not decide which side of a border a point falls on with them, and do
not publish a map that claims they show a boundary. Use them to draw a quick
outline and to pre-filter a download, then go to the full-resolution file.

**The buffer is in degrees, so it is not isotropic on the ground.** One degree
of latitude is about 111 km everywhere; one degree of longitude is
111·cos(latitude) km. A 0.01 degree buffer is therefore about 1.1 km
north-south everywhere, about 1.1 km east-west at the equator, and about
0.55 km east-west at 60° north. The margin narrows east-west towards the
poles. It is outward everywhere, which is the property that matters.

**How to reproduce.**

```bash
python3 tools/build_display.py --measure   # the tolerance sweep
python3 tools/build_display.py             # build
```

**Asset role.** The display file is published with
`"roles": ["data", "overview"]`. `overview` is STAC's common role for a
reduced-resolution version of the data asset, which is exactly what it is. The
plain `data` role stays on the verbatim full-resolution file, so a client that
only understands `data` gets the real geometry.

**How to get vanilla.** Ignore the `display` assets and read the `data` asset,
which is the full-resolution geometry.

## 11. Row group statistics restricted to the prunable columns

**What.** Every boundary and display file carries row group statistics for
`shapeID`, `shapeGroup` and the four `bbox` struct leaves — `bbox.xmin`,
`bbox.ymin`, `bbox.xmax`, `bbox.ymax` — and for nothing else. Statistics on
`shapeName`, `shapeType`, `country_units`, `area_km2`, `perimeter_km`,
`compactness` and `geometry` are not written.

**Why.** These files are Hilbert-sorted, so those columns' min/max ranges
overlap across essentially every row group and prune nothing, while a min and a
max of `shapeName` is two strings per row group per file. With 193 to 218 row
groups per file, that is metadata a range client downloads before any data and
can never use. Measured on ADM2 at 256 rows per group, the restriction cut the
trailing bytes from 670,381 to 346,581 — 324 KB off every client's first
select.

The `bbox` entries have to name the struct's **leaf** paths. PyArrow matches
`write_statistics` against the leaf path, not the top-level column, so listing
`"bbox"` silently drops statistics from all four leaves, and those four are the
GeoParquet 1.1 covering — the only spatial pruning these files offer.

**What a consumer loses.** A query predicate on `shapeName`, `shapeType` or any
measured column reads every row group's pages rather than skipping groups on
statistics. Predicates on `shapeID`, `shapeGroup` and the bbox still prune, and
those are the three a single-feature lookup uses. The Parquet page index is
still written on every column.

**How to reproduce.** `PRUNABLE_STATS` in
[`tools/gbcommon.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/gbcommon.py), applied by
[`tools/build_boundaries.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_boundaries.py) and
[`tools/build_display.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_display.py).

**How to get vanilla.** There is nothing to return to: a GeoPackage carries no
Parquet metadata at all. Rewrite the file with PyArrow and no
`write_statistics` restriction if you want statistics on every column.

---

## What is *not* changed

Recorded here so nobody has to check:

- **The 20 disputed-area polygons** are carried exactly as upstream has them,
  with their geoBoundaries-internal `shapeGroup` codes `111`–`129` and `ESH`.
- **The backfilled rows** — 312 first-level units standing in for countries
  with no second level, 2 countries with no first level — are carried, with
  `shapeType` saying what they really are. Nothing is dropped to make the
  levels "clean".
- **The 37 rows with no `shapeName`** keep their NULL name and their geometry.
  They are excluded from the names index only, because an index entry with no
  name is not searchable.
- **`shapeID`, `shapeGroup`, `shapeType`** are byte-for-byte upstream.
- **The missing `shapeID` at ADM0** is upstream's choice; no identifier is
  invented to fill it.
- **No parent key is invented.** CGAZ publishes nothing linking a second-level
  unit to the first-level unit containing it, and this catalog does not guess
  one with a spatial join.
- **Coordinates are not reprojected, snapped, or precision-reduced.**
