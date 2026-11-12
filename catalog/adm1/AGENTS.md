# AGENTS.md — CGAZ ADM1, First-Level Administrative Boundaries

Guidance for AI agents and automated clients working with this collection.

**One rule survives every edit to this file.** Every claim here is either quoted
from a source or measured from the data. If you cannot point at where a fact
came from, it does not belong in this file. An agent acting on an invented join
key or an invented column name produces a confident wrong answer, and nothing
downstream catches it.

Each factual claim is tagged with how it was established:
**[attested]** the publisher states it, with a link;
**[researched]** found outside the source's own metadata, with a link;
**[derived]** computed from the published data, with the query that computed it.

## What this collection holds

3,224 first-level administrative units worldwide: states, provinces, regions,
governorates, prefectures. Public root:
`https://data.source.coop/portolan-mirrors/geoboundaries/catalog.json`

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

```
adm1/cgaz_adm1.parquet   76 MB, 3,224 rows, 51 row groups of 64 rows
adm1/adm1.pmtiles        17 MB, zoom 0-7, layer "adm1"
```

How each polygon got here **[researched,
[gbCGAZBuild.py](https://github.com/wmgeolab/geoBoundaryBot/blob/main/gbCGAZBuild.py)]**:
for every ISO code, the country's `gbOpen` ADM1 GeoJSON goes through

```
mapshaper-xl <ADM1.geojson> -simplify keep-shapes percentage=0.10 \
  -clip <that country's US DoS ADM0 polygon> -o format=topojson
```

so roughly a tenth of the vertices survive and the outline is cut to the US
Department of State international boundary. The per-country results are merged,
cleaned with `-clean gap-fill-area=10000km2 keep-shapes`, and the 20
disputed-area polygons are merged in. Where a country has no ADM1 file the
script substitutes its ADM0 file, which is why two rows here are whole
countries.

The exact parameter for the release mirrored here cannot be pinned to one
script version: `gbCGAZBuild.py` and
`geoBoundaryBuilder/archive/cgazBuild.py` both carry
`-simplify keep-shapes percentage=0.10`, while the refactored
`geoBoundaryBuilder/modules/cgaz_builder.py` has that line commented out. The
10% figure is quoted from the two scripts that have it. Measured result:
8,830,663 vertices over 3,224 units, a mean of 2,739 **[derived]**.

## Layout and how to exploit it

Rows are ordered along a Hilbert curve over the whole globe, in **51 row groups
of 64 rows**, about 1.49 MB each, with a Parquet page index on every column.
The group size comes from measurement, not convention: this file holds about
21.7 KB of compressed geometry per unit, so 64 rows is what lands a row group
near 1.5 MB. A conventional 50,000-row group would put all 3,224 units in one
group and make a single-province fetch a 76 MB read.

Prune with the `bbox` covering struct before touching geometry:

```sql
SELECT shapeName, shapeGroup, round(area_km2) AS area_km2
FROM 'adm1/cgaz_adm1.parquet'
WHERE bbox.xmin < 14.6 AND bbox.xmax > 14.2
  AND bbox.ymin < 50.2 AND bbox.ymax > 49.9
ORDER BY area_km2;
```
```
Hlavní město Praha  CZE    496
Ústecký kraj        CZE   5344
Středočeský kraj    CZE  10930
Sachsen             DEU  18446
```

Four units, not one: the filter is a bbox overlap test, so a unit whose
bounding box touches the window is returned even when its outline does not.

## Columns

| column | type | meaning | tier |
|---|---|---|---|
| `shapeName` | VARCHAR | Unit name, as published. Not unique: 3,143 distinct over 3,224 rows | [attested](https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2) + derived |
| `shapeID` | VARCHAR | Unique key, `<boundary id>B<shape integer>`. Unique over all 3,224 rows | attested + derived |
| `shapeGroup` | VARCHAR | ISO 3166-1 alpha-3, or a disputed-area code `111`-`129` / `ESH` | attested + derived |
| `shapeType` | VARCHAR | `ADM1` (3,202), `DISP` (20), `ADM0` (2) | attested + derived |
| `country_units` | INTEGER | Rows in this file sharing this `shapeGroup`, 1 to 83 | derived |
| `area_km2` | DOUBLE | Geodesic area, km2, on the simplified geometry | derived |
| `perimeter_km` | DOUBLE | Geodesic perimeter, km | derived |
| `compactness` | DOUBLE | Polsby-Popper, 4*pi*A/P^2 | derived |
| `bbox` | STRUCT | GeoParquet 1.1 covering: xmin, ymin, xmax, ymax as DOUBLE | derived |
| `geometry` | BLOB (WKB) | Polygon or MultiPolygon, CRS84 | attested |

### How `shapeID` is built

geoBoundaries documents `boundaryID` as "a combination of the ISO code, the
boundary type, and a unique identifier for the boundary generated based on the
input metadata and geometry. This only changes if the underlying data changes",
with the example `ALB-ADM0-26141361` **[attested,
[API documentation](https://www.geoboundaries.org/api.html)]**. `shapeID` is
the numeric part of that, then `B`, then an integer unique to the shape within
the boundary.

Verified: every ADM1 row for Afghanistan carries the prefix `12653393`, and
`https://www.geoboundaries.org/api/current/gbOpen/AFG/ADM1/` returns
`"boundaryID": "AFG-ADM1-12653393"` **[derived]**. So the prefix identifies the
country-and-level source boundary and changes only when that source data
changes; the suffix identifies the shape.

The 20 disputed-area rows break the pattern: their `shapeID` is `DIS001`
through `DIS020`, with no `B` **[derived]**.

**The prefix is level-specific.** Afghanistan is `12653393` here and
`17698898` in the ADM2 collection, matching `AFG-ADM2-17698898`. A prefix match
therefore cannot be used to link an ADM1 unit to the ADM2 units inside it; see
[related collections](#related-collections).

## Quirks that produce silently wrong answers

**Not every row is a first-level unit.** 3,202 have `shapeType = 'ADM1'`, 20
are disputed areas, and 2 are whole countries, Antarctica and Vatican City,
carried up because CGAZ has no first-level data for them **[derived]**:

```sql
SELECT shapeType, count(*) FROM 'adm1/cgaz_adm1.parquet' GROUP BY 1;
```
```
ADM1  3202
DISP    20
ADM0     2
```

**`shapeGroup` is not an ISO code for 20 rows**, and `country_units = 1` picks
up all 20 disputed areas along with the 2 carried-up countries, because each
disputed area is the only row in its own `shapeGroup` **[derived]**. Add
`shapeType = 'ADM1'` when you mean first-level units.

**Nothing links a unit to its subdivisions or to a parent region.** The only
relationship CGAZ publishes is `shapeGroup` to a country. Reconstructing the
hierarchy requires a spatial join, and on simplified clipped geometry that
misassigns units along shared edges.

**25 names in this file are double-encoded upstream**, including all 16 Chilean
regions: `RegiÃ³n de ValparaÃ­so` where `Región de Valparaíso` was meant, plus
7 Portuguese districts and 2 Seychelles districts **[derived]**. `shapeName`
carries them through unchanged, because this is a mirror. The
[`names`](../names/collection.json) collection repairs them in its `name_norm`
column, so the units stay findable:

```sql
SELECT count(*) FROM 'adm1/cgaz_adm1.parquet'
WHERE shapeName LIKE '%Ã%' OR shapeName LIKE '%Å%' OR shapeName LIKE '%Ä%';
-- 25
```

**346 of the 3,224 geometries are not OGC-valid** **[derived]**, and the same
346 fail on a direct conversion of the upstream GeoPackage, so the invalidity
is upstream. Call `ST_MakeValid(geometry)` before any overlay, union or
intersection. Drawing and bbox queries are unaffected.

**Simplification collapses the smallest units.** Four rows measure under
0.1 km2, and Kaafu in the Maldives measures 0.0 km2 from 4 vertices
**[derived]**. The unit is real; its geometry did not survive the 10% vertex
reduction at a usable size. Do not use this level for small-island work.

**Areas and perimeters are measured on simplified, clipped geometry.** They are
reproducible and comparable within this file, and they are not official
figures. `compactness` reads higher here than it would on full-resolution
outlines, because simplification smooths coastlines.

## Worked queries

Every query below was run against the built file before it was written down.

The countries divided into the most first-level units:

```sql
SELECT shapeGroup, any_value(country_units) AS units
FROM 'adm1/cgaz_adm1.parquet'
WHERE shapeType = 'ADM1'
GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
```
```
RUS  83
TUR  81
THA  77
MLT  68
VNM  64
```

Malta in fourth place is not an error: CGAZ carries Malta's 68 local councils
as its first level, and the same 68 polygons reappear in the ADM2 collection
with `shapeType = 'ADM1'` because there is no second level below them.

The least compact first-level units, which is where simplification and island
groups bite hardest:

```sql
SELECT shapeName, shapeGroup, round(area_km2) AS area_km2,
       round(compactness, 4) AS comp
FROM 'adm1/cgaz_adm1.parquet'
WHERE shapeType = 'ADM1' AND area_km2 > 1000
ORDER BY compactness LIMIT 4;
```
```
RegiÃ³n de Magallanes y AntÃ¡rtica Chilena    CHL   118693  0.0009
Nunavut                                       CAN  2075655  0.0019
RegiÃ³n de AysÃ©n del Gral.IbaÃ±ez del Campo  CHL   101185  0.0033
Nordland                                      NOR    36953  0.0065
```

The two Chilean rows show the upstream double encoding as it actually reads
in a query result.

One unit's geometry, fetched through the search index:

```sql
SELECT n.name, n.country_name, round(b.area_km2) AS area_km2,
       ST_NPoints(b.geometry) AS vertices
FROM 'names/cgaz_names.parquet' n
JOIN 'adm1/cgaz_adm1.parquet' b ON n.shape_id = b.shapeID
WHERE n.level = 1 AND n.name_norm = 'zurich';
```
```
Zürich  Switzerland  1729  885
```

## Related collections

[`adm0`](../adm0/collection.json) holds the country polygons; join on
`shapeGroup`. [`adm2`](../adm2/collection.json) holds the second level, but
**only `shapeGroup` joins the two**, not `shapeID`, because the prefixes are
per level. [`names`](../names/collection.json) is the search index; its
level-1 rows join here on `names.shape_id = adm1.shapeID`.

## Structure

Assets and structural links resolve relative to the object that carries them.
