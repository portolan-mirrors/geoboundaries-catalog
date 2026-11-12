# AGENTS.md — CGAZ ADM2, Second-Level Administrative Boundaries

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

49,349 second-level administrative units worldwide: counties, districts,
municipalities, communes, municípios. Public root:
`https://data.source.coop/portolan-mirrors/geoboundaries-catalog/catalog.json`

This is a **mirror**. [geoBoundaries](https://www.geoboundaries.org/) is the
producer and the authoritative source.

```
adm2/cgaz_adm2.parquet   101 MB, 49,349 rows, 97 row groups of 512 rows
adm2/adm2.pmtiles        101 MB, zoom 0-9, layer "adm2"
```

How each polygon got here **[researched,
[gbCGAZBuild.py](https://github.com/wmgeolab/geoBoundaryBot/blob/main/gbCGAZBuild.py)]**:
for every ISO code, the country's `gbOpen` ADM2 GeoJSON goes through

```
mapshaper-xl <ADM2.geojson> -simplify keep-shapes percentage=0.10 \
  -clip <that country's US DoS ADM0 polygon> -o format=topojson
```

Where no ADM2 file exists the script falls back to the country's ADM1 file, and
failing that its ADM0 file. The per-country results are merged, cleaned with
`-clean gap-fill-area=10000km2 keep-shapes`, and the 20 disputed-area polygons
are merged in. Measured result: 13,183,670 vertices over 49,349 units, a mean
of 267 **[derived]**. The exact simplification parameter for this release
cannot be pinned to one script version; see the note in
[`adm1/AGENTS.md`](../adm1/AGENTS.md).

## Layout and how to exploit it

Rows are ordered along a Hilbert curve over the whole globe, in **97 row groups
of 512 rows**, about 1.05 MB each, with a Parquet page index on every column.

This is the number that matters most in this catalog. The mirror this one
replaces put all 49,349 rows in a single row group, so a client that wanted one
municipality's geometry had to read the entire geometry column chunk, roughly
97 MB. Here the same fetch is one range request of about 1 MB, chosen from the
measured 3.0 KB of compressed geometry per unit. `gpio check` warns that 512
rows per group is "very low"; that guidance is written for scan-heavy
analytics, and this file is built for single-feature lookups from a browser.

Prune on the `bbox` covering struct, which lets a reader skip row groups
without decoding any WKB:

```sql
-- The smallest units around central Nairobi
SELECT shapeName, shapeGroup, round(area_km2, 1) AS area_km2
FROM 'adm2/cgaz_adm2.parquet'
WHERE bbox.xmin < 36.9 AND bbox.xmax > 36.7
  AND bbox.ymin < -1.2 AND bbox.ymax > -1.4
ORDER BY area_km2 LIMIT 6;
```
```
Mathare            KEN  3.3
Embakasi North     KEN  5.0
Ruaraka            KEN  7.1
Embakasi Central   KEN  8.2
Kamukunji          KEN  8.4
Embakasi West      KEN  9.6
```

## Columns

| column | type | meaning | tier |
|---|---|---|---|
| `shapeName` | VARCHAR | Unit name, as published. **NULL for 37 rows**; 45,116 distinct over 49,312 named rows | [attested](https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2) + derived |
| `shapeID` | VARCHAR | Unique key, `<boundary id>B<shape integer>`. Unique over all 49,349 rows | attested + derived |
| `shapeGroup` | VARCHAR | ISO 3166-1 alpha-3, or a disputed-area code `111`-`129` / `ESH` | attested + derived |
| `shapeType` | VARCHAR | `ADM2` (49,015), `ADM1` (312), `DISP` (20), `ADM0` (2) | attested + derived |
| `country_units` | INTEGER | Rows in this file sharing this `shapeGroup`, 1 to 5,570 | derived |
| `area_km2` | DOUBLE | Geodesic area, km2, on the simplified geometry | derived |
| `perimeter_km` | DOUBLE | Geodesic perimeter, km | derived |
| `compactness` | DOUBLE | Polsby-Popper, 4*pi*A/P^2 | derived |
| `bbox` | STRUCT | GeoParquet 1.1 covering: xmin, ymin, xmax, ymax as DOUBLE | derived |
| `geometry` | BLOB (WKB) | Polygon or MultiPolygon, CRS84 | attested |

`shapeID` is built the same way as at ADM1, and the prefix is **level-specific**:
Afghanistan is `17698898` here against `12653393` in the ADM1 collection,
matching the geoBoundaries boundary IDs `AFG-ADM2-17698898` and
`AFG-ADM1-12653393` **[attested,
[API documentation](https://www.geoboundaries.org/api.html); derived, verified
against that API]**. See [`adm1/AGENTS.md`](../adm1/AGENTS.md) for the full
structure.

## Quirks that produce silently wrong answers

**334 of 49,349 rows are not second-level units.** 312 are first-level units
standing in for 22 countries that have no second level, 20 are disputed areas,
and 2 are whole countries **[derived]**:

```sql
SELECT shapeType, count(*) FROM 'adm2/cgaz_adm2.parquet' GROUP BY 1
ORDER BY 2 DESC;
```
```
ADM2  49015
ADM1    312
DISP     20
ADM0      2
```

The 22 countries with no second level, and how many rows each contributes:

```sql
SELECT shapeGroup, count(*) AS n FROM 'adm2/cgaz_adm2.parquet'
WHERE shapeType IN ('ADM0', 'ADM1') GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
```
```
MLT  68
MDA  37
MNE  23
MHL  22
LBY  22
NRU  14
KNA  14
TTO  14
```

Add `shapeType = 'ADM2'` to any query that means second-level units.

**37 rows have no name.** `shapeName` is NULL for 24 rows in Japan, 12 in
Turkmenistan and 1 in China **[derived]**:

```sql
SELECT shapeGroup, count(*) FROM 'adm2/cgaz_adm2.parquet'
WHERE shapeName IS NULL GROUP BY 1 ORDER BY 2 DESC;
```
```
JPN  24
TKM  12
CHN   1
```

They are real polygons with real `shapeID`s and real geometry, and they are
kept here. They are **absent from the [`names`](../names/collection.json)
collection**, because there is nothing to search for, so that index is 37 rows
short of this file's named units.

**A name is not an identifier.** 45,116 distinct names over 49,312 named rows.
32 units fold to `washington`, 26 each to `franklin` and `jefferson`
**[derived]**. Join on `shapeID`, never on `shapeName`.

**"Second level" means different things in different countries.** A row may be
a US county, a Brazilian município, a French commune or a Japanese
municipality. The level number is structural, not semantic. `area_km2` spans
from 0.000 to 12,063,872 in one column, the latter being Antarctica carried up
from ADM0 **[derived]**.

**Nothing links a unit to the first-level unit containing it.** `shapeGroup`
to a country is the only relationship CGAZ publishes, and the `shapeID`
prefixes differ between levels, so no prefix or substring match works. Building
the hierarchy means a spatial join, and on simplified clipped geometry that
misassigns units along shared edges. This is the biggest gap in the dataset.

**843 of the 49,349 geometries were not OGC-valid upstream, and all 843 are
repaired here** **[derived]**. The published file carries
`ST_CollectionExtract(ST_MakeValid(geometry), 3)` for those rows and the other
48,506 byte for byte; 0 rows fail `ST_IsValid` now. Area introduced is under
0.24 km2 on every row but one: Sabaya (BOL) moves from 6,304.4 to 6,969.5 km2,
because the signed-area sum over its self-overlapping ring was cancelling part
of the shape, so the repair corrects the number rather than inflating it.

**Simplification collapses the smallest units.** 107 rows measure under
0.1 km2, concentrated in Saint Lucia's urban districts and Pacific atolls
**[derived]**. The units are real; their geometry did not survive the 10%
vertex reduction at a usable size.

**14 names in this file were double-encoded upstream, and are repaired here**
**[derived]**: ten New Zealand local board and district names whose macrons
arrive damaged, and four Peruvian provinces. `shapeName` carries the repaired
text; the before-and-after table is in
[changes-from-upstream.md](../changes-from-upstream.md).

**Norwegian unit names carry artifacts from their source file.** Several read
`"Evje og Hornnes" nor`, with the quotation marks and the trailing ` nor` in
the data **[derived]**.

## Worked queries

Every query below was run against the built file before it was written down.

The countries with the most second-level units:

```sql
SELECT shapeGroup, any_value(country_units) AS units
FROM 'adm2/cgaz_adm2.parquet' GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
```
```
BRA  5570
ROU  3235
USA  3231
MEX  2457
CHN  2370
```

One unit's geometry, fetched through the search index. This is the geocoder
path: the index gives the `shapeID`, the join gives the polygon.

```sql
SELECT n.name, n.country_name, round(b.area_km2, 1) AS area_km2,
       ST_NPoints(b.geometry) AS vertices
FROM 'names/cgaz_names.parquet' n
JOIN 'adm2/cgaz_adm2.parquet' b ON n.shape_id = b.shapeID
WHERE n.level = 2 AND n.name_norm LIKE 'kisumu%';
```
```
Kisumu Central  Kenya   67.5  19
Kisumu West     Kenya  312.6  35
Kisumu East     Kenya  166.2  48
```

The smallest named units, which is where the simplification shows:

```sql
SELECT shapeName, shapeGroup, round(area_km2, 3) AS area_km2
FROM 'adm2/cgaz_adm2.parquet'
WHERE shapeType = 'ADM2' AND shapeName IS NOT NULL
ORDER BY area_km2 LIMIT 5;
```
```
Male'      MDV  0.000
Maribor    SVN  0.001
Chilanga   SLV  0.001
Teraina    KIR  0.002
Makur      FSM  0.003
```

## Related collections

[`adm0`](../adm0/collection.json) and [`adm1`](../adm1/collection.json) hold
the coarser levels; **only `shapeGroup` joins them to this one**, not
`shapeID`. [`names`](../names/collection.json) is the search index; its
level-2 rows join here on `names.shape_id = adm2.shapeID`.

## Structure

Assets and structural links resolve relative to the object that carries them.
