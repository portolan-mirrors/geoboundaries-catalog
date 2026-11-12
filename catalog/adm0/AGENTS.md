# AGENTS.md — CGAZ ADM0, Country Boundaries

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

218 country-level polygons from the geoBoundaries CGAZ composite. Public root:
`https://data.source.coop/portolan-mirrors/geoboundaries-catalog/catalog.json`

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

```
adm0/cgaz_adm0.parquet   97 MB, 218 rows, 55 row groups of 4 rows
adm0/adm0.pmtiles        7.1 MB, zoom 0-6, layer "adm0"
```

**These are not boundaries as countries claim them.** CGAZ "clipped to
international boundaries (US Department of State), with gaps filled between
borders" **[attested,
[geoBoundaries README](https://github.com/wmgeolab/geoBoundaries)]**, and
"disputed areas are removed and replaced with polygons following US Department
of State definitions" **[attested,
[globalDownloads.html](https://www.geoboundaries.org/globalDownloads.html)]**.
geoBoundaries' per-country releases, which do represent each nation "as they
would represent themselves", are a different product and are not mirrored here.

The outlines come from the US Department of State Large Scale International
Boundaries file of March 2020, dissolved to one polygon per ISO code
**[researched,
[gbCGAZBuild.py](https://github.com/wmgeolab/geoBoundaryBot/blob/main/gbCGAZBuild.py),
which reads `./dta/usDoSLSIB_Mar2020.geojson` and dissolves on `ISO_CODE`]**.
Unlike ADM1 and ADM2, this level is **not simplified**: the 10% vertex
reduction in that script applies to the lower levels, and the line that would
simplify the composite is commented out. Measured: 10,101,960 vertices across
218 units, a mean of 46,339 **[derived]**. That is why 218 country polygons
weigh more than 49,349 municipalities.

Territories are merged into their parent state, so Greenland is part of the
Denmark polygon and has no row of its own **[attested, the `country_renamer`
mapping in `gbCGAZBuild.py`]**.

## Layout and how to exploit it

Rows are ordered along a Hilbert curve over the whole globe, and the file is
cut into **55 row groups of 4 rows**, about 1.77 MB each. That is deliberate.
Four rows per group is far below any general-purpose guidance, and `gpio check`
warns about it; the warning is correct in general and wrong here. At 513 KB of
compressed geometry per country, a row group of 1,000 rows would be the whole
file, which is exactly the defect in other mirrors of this data: fetching one
country's outline costs a 97 MB read. With 4-row groups and the GeoParquet 1.1
`bbox` covering column, it costs one range request of about 1.8 MB.

Every column carries a Parquet page index, so a reader can narrow further
inside a row group.

Use the `bbox` struct, not the geometry, for any spatial predicate you want
pruned:

```sql
-- Which country covers 2.35 E, 48.85 N? Reads the bbox column, then one
-- row group's geometry.
SELECT shapeName, shapeGroup
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm0/cgaz_adm0.parquet'
WHERE bbox.xmin <= 2.35 AND bbox.xmax >= 2.35
  AND bbox.ymin <= 48.85 AND bbox.ymax >= 48.85
  AND ST_Contains(geometry, ST_Point(2.35, 48.85));
```
```
France  FRA
```

Beware that a bbox test alone is not a containment test: France's bbox spans
-178.19 to 172.06 longitude because of its overseas territories
**[derived]**, so the bbox filter above passes several candidates before
`ST_Contains` decides.

## Columns

| column | type | meaning | tier |
|---|---|---|---|
| `shapeName` | VARCHAR | Country or disputed-area name, as published | [attested](https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2) |
| `shapeGroup` | VARCHAR | ISO 3166-1 alpha-3, **or** a geoBoundaries disputed-area code | attested + derived |
| `shapeType` | VARCHAR | `ADM0` (198 rows) or `DISP` (20 rows) | attested + derived |
| `adm1_units` | INTEGER | Rows in the `adm1` collection for this `shapeGroup`, 1 to 83 | derived |
| `adm2_units` | INTEGER | Rows in the `adm2` collection for this `shapeGroup`, 1 to 5,570 | derived |
| `area_km2` | DOUBLE | Geodesic area, km2, WGS 84 ellipsoid | derived |
| `perimeter_km` | DOUBLE | Geodesic perimeter, km | derived |
| `compactness` | DOUBLE | Polsby-Popper, 4*pi*A/P^2 | derived |
| `bbox` | STRUCT | GeoParquet 1.1 covering: xmin, ymin, xmax, ymax as DOUBLE | derived |
| `geometry` | BLOB (WKB) | Polygon or MultiPolygon, CRS84 | attested |

**There is no `shapeID` column in this file.** The ADM1 and ADM2 collections
have one; CGAZ ADM0 does not publish it. `shapeGroup` is the key here, and it
is unique: 218 distinct values over 218 rows **[derived]**.

**There is no `id` column either.** The upstream GeoPackage has one and it is
NULL in all 218 rows, so it is not carried. The upstream build lists `id` in
its mapshaper `-drop fields=` call, which is why the column survives as an
empty one **[attested, `gbCGAZBuild.py`; derived, `count(id) = 0`]**.

`area_km2` and `perimeter_km` are computed with DuckDB's spheroidal measures
after flipping the coordinate order, because those functions read the first
ordinate as latitude. Verification: this agrees to better than 0.01% with
`ST_Area(ST_Transform(geometry, 'OGC:CRS84', 'EPSG:6933'))`, the NSIDC
EASE-Grid 2.0 Global projection geoBoundaries says it uses for its own area
statistics **[attested,
[API documentation](https://www.geoboundaries.org/api.html): "measured in
square kilometers (based on a EASE-GRID 2 projection)"; derived]**. Sanity
check against published figures: Albania 28,679 km2 against 28,748, Nepal
147,578 against 147,181 **[derived]**.

## Quirks that produce silently wrong answers

**20 rows are not countries.** `shapeType = 'DISP'` marks Abyei, Aksai Chin,
CH-IN, Demchok, Dragonja, Dramana-Shakatoe, Falkland Islands (UK), Gaza Strip,
Isla Brasilera, Kalapani, Koualou, Liancourt Rocks, No Man's Land, Paracel Is,
Sanafir & Tiran Is., Senkakus, Siachen-Saltoro, Spratly Is, West Bank and
Western Sahara **[derived]**. `WHERE shapeType = 'ADM0'` gives the 198
recognized countries.

**`shapeGroup` is not an ISO code for those 20 rows.** They carry `111`
through `129`, except Western Sahara which uses `ESH` **[derived]**. Joining
this column to an ISO-keyed table silently drops or mismatches them.

**218 rows is not a count of sovereign states.** It is 198 country polygons
plus 20 disputed areas, and the 198 already have their dependent territories
merged in.

**87 of the 218 geometries are not OGC-valid** **[derived]**, and the same 87
fail on a direct conversion of the upstream GeoPackage, so the invalidity is
upstream. Drawing and bbox queries are unaffected; overlays are not. Call
`ST_MakeValid(geometry)` before any topological operation.

**`compactness` is low for countries with islands**, because island outlines
add perimeter without much area. Canada reads 0.003 and Russia 0.017
**[derived]**. It measures outline raggedness, not shape in any political
sense.

**No validity dates.** geoBoundaries records a `boundaryYearRepresented` per
source boundary **[attested, API documentation]**; CGAZ does not carry it. The
collection's temporal extent is the upstream release date, not a period of
validity.

## Worked queries

Every query below was run against the built file before it was written down.

The ten countries CGAZ divides most finely:

```sql
SELECT shapeName, shapeGroup, adm1_units, adm2_units
FROM 'adm0/cgaz_adm0.parquet'
WHERE shapeType = 'ADM0'
ORDER BY adm2_units DESC LIMIT 10;
```
```
Brazil         BRA  27  5570
Romania        ROU  42  3235
United States  USA  56  3231
Mexico         MEX  32  2457
China          CHN  33  2370
Russia         RUS  83  2326
Japan          JPN  47  1731
Colombia       COL  33  1122
Turkey         TUR  81   972
Thailand       THA  77   928
```

The countries with no subnational breakdown at all:

```sql
SELECT shapeName, shapeGroup, round(area_km2, 2) AS area_km2
FROM 'adm0/cgaz_adm0.parquet'
WHERE shapeType = 'ADM0' AND adm1_units = 1 AND adm2_units = 1
ORDER BY area_km2 DESC;
```
```
Antarctica    ATA  12350369.48
Vatican City  VAT        0.52
```

The three largest and three smallest polygons, which show the span the styles
have to cover:

```sql
SELECT shapeName, round(area_km2) AS area_km2, round(compactness, 3) AS comp
FROM 'adm0/cgaz_adm0.parquet' ORDER BY area_km2 DESC LIMIT 3;
```
```
Russia      16930381  0.017
Antarctica  12350369  0.031
Canada       9963459  0.003
```
```sql
SELECT shapeName, round(area_km2, 2) AS area_km2
FROM 'adm0/cgaz_adm0.parquet' ORDER BY area_km2 LIMIT 3;
```
```
Liancourt Rocks  0.16
Spratly Is       0.44
Vatican City     0.52
```

## Related collections

[`adm1`](../adm1/collection.json) and [`adm2`](../adm2/collection.json) hold
the subnational levels, keyed to this one by `shapeGroup`.
[`names`](../names/collection.json) is the search index; its level-0 rows join
back here on `names.country = adm0.shapeGroup`, because there is no `shapeID`
at this level.

## Structure

Assets and structural links resolve relative to the object that carries them.
