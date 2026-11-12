# AGENTS.md — CGAZ Name Search Index

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

**A search sidecar, not a boundary dataset.** One row per named administrative
unit across all three CGAZ levels, built so that a static client with no server
can turn a typed name into a `shapeID`, a bbox and a point. Public root:
`https://data.source.coop/portolan-mirrors/geoboundaries-catalog/catalog.json`

```
names/cgaz_names.parquet   3.6 MB, 52,398 rows, 35 row groups of 1,536 rows
names/names.pmtiles        12 MB, zoom 0-8, layer "names"
```

The `geometry` column is **one point per unit**, from `ST_PointOnSurface` of
the unit's polygon, which is guaranteed to fall inside the unit where a
centroid is not. The unit's actual shape lives in the
[`adm0`](../adm0/collection.json), [`adm1`](../adm1/collection.json) or
[`adm2`](../adm2/collection.json) collection. Do not compute area, length or
containment from this file.

### Which rows are indexed, and which are not

CGAZ is a seamless composite, so a country with no ADM2 data appears in the
ADM2 file carried up from a coarser level, and the 20 disputed-area polygons
appear in all three files. Indexing every row of every file would return
Antarctica three times for one query. A row is indexed only from the file its
own `shapeType` belongs to:

| source file | rows taken | `level` |
|---|---|---|
| `adm0` | `shapeType IN ('ADM0', 'DISP')` | 0 |
| `adm1` | `shapeType = 'ADM1'` | 1 |
| `adm2` | `shapeType = 'ADM2'` | 2 |

Measured **[derived]**:

```sql
SELECT level, shape_type, count(*) AS n
FROM 'names/cgaz_names.parquet' GROUP BY 1, 2 ORDER BY 1, 3 DESC;
```
```
0  ADM0    198
0  DISP     20
1  ADM1   3202
2  ADM2  48978
```

**37 ADM2 units are missing on purpose.** Their `shapeName` is NULL upstream —
24 in Japan, 12 in Turkmenistan, 1 in China — so there is nothing to search
for. They exist in the `adm2` collection with geometry and `shapeID`s. A client
that treats this index as a complete list of second-level units will be 37
short **[derived]**.

## Layout and how to exploit it

The file is sorted by `(name_norm, level, country)` and written in **35 row
groups of 1,536 rows**, about 101 KiB each, with a Parquet page index on every
column. The row group size targets bytes, not rows: at 69 compressed bytes per
row, 1,536 rows lands inside the 100-150 KiB band where a prefix lookup is a
single small range request. Doubling the group size doubles both the latency
and the bytes fetched.

Because the file is sorted, row group statistics on `name_norm` are tight,
non-overlapping alphabetical ranges **[derived]**:

```
row group  0  1,536 rows  ['"evje og hornnes" nor' .. 'algeria']
row group  1  1,536 rows  ['algiers'              .. 'asomatos keryneias']
row group 17  1,536 rows  ['maha chana chai'      .. 'mendes']
row group 34    174 rows  ['جومين'                .. '鹿港鎮']
```

Measured selectivity over all 676 two-letter prefixes: a prefix touches a
**minimum of 1, a median of 1 and a maximum of 3** row groups. `wash` touches
1, `san` touches 2, the bare letter `s` touches 5 **[derived]**.

File geometry, for a client that plans its reads:

| | bytes |
|---|---|
| whole file | 3,623,011 |
| Parquet footer | 60,974 |
| page index region | 25,614 |
| footer + page index | 86,596 |
| one row group, all columns | ~103,500 |
| one row group, the 7 search columns | ~45,600 |

## Two ways to use it

### (a) Full load — the intended path

At 3.6 MB this is the primary consumption mode. Browser clients read it with
[hyparquet](https://github.com/hyparam/hyparquet) plus
[hyparquet-compressors](https://github.com/hyparam/hyparquet-compressors),
which is required because every column chunk is **ZSTD** and hyparquet ships no
zstd codec of its own **[derived]**. hyparquet's default footer prefetch is
512 KiB, and this file's footer plus page index is 86,596 bytes, so one
prefetch has everything it needs to plan **[derived]**.

Measured on Node 22 against the built file:

```js
import { parquetMetadataAsync, parquetReadObjects, asyncBufferFromFile }
  from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

const file = await asyncBufferFromFile('cgaz_names.parquet')  // or asyncBufferFromUrl
const metadata = await parquetMetadataAsync(file)

const rows = await parquetReadObjects({
  file, metadata, compressors,
  columns: ['name', 'name_norm', 'level', 'country_name', 'shape_id',
            'area_km2', 'name_dupes'],
})
const hits = rows.filter(r => r.name_norm.startsWith('zurich'))
```
```
full load of 7 columns: 52398 rows in 117 ms
full load of every column: 52398 rows in 250 ms
prefix "zurich": [["Zürich","Switzerland",1],["Zürich","Switzerland",2]]
```

Leaving out `geometry` and `bbox` is what makes the 7-column load twice as
fast; fetch those for the hits only, or keep them if you want to fly the map
without a second read.

### (b) Sorted range requests — the fallback for a bigger index

Read the footer, keep the row groups whose `name_norm` min/max range can hold
the prefix, and read only those rows. This is what the sort buys, and it is the
path to use if this index grows past what you want to download.

```js
const prefix = 'zurich'
let rowStart = 0, found = [], scanned = 0
for (const rg of metadata.row_groups) {
  const n = Number(rg.num_rows)
  const col = rg.columns.find(c => c.meta_data.path_in_schema[0] === 'name_norm')
  const { min_value: min, max_value: max } = col.meta_data.statistics
  // the prefix range [prefix, prefix + '￿'] has to overlap [min, max]
  if (!(max < prefix || min > prefix + '￿')) {
    scanned++
    const part = await parquetReadObjects({
      file, metadata, compressors,
      columns: ['name', 'name_norm', 'level', 'country_name', 'shape_id'],
      rowStart, rowEnd: rowStart + n,
    })
    found.push(...part.filter(r => r.name_norm.startsWith(prefix)))
  }
  rowStart += n
}
```
```
range-request path: read 1 of 35 row groups, 2 hits
[["Zürich","Switzerland",1,"70761945B4468941998498"],
 ["Zürich","Switzerland",2,"98125504B49363097971591"]]
```

Both snippets were run against the built file before being written down.
`asyncBufferFromUrl` gives the same behaviour over HTTPS, because
`data.source.coop` serves range requests.

The same thing in SQL, where DuckDB does the row group pruning from the
statistics itself:

```sql
SELECT name, country_name, level, name_dupes, round(area_km2) AS area_km2
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/names/cgaz_names.parquet'
WHERE name_norm LIKE 'zurich%'
ORDER BY level, area_km2 DESC;
```
```
Zürich  Switzerland  1  2  1729
Zürich  Switzerland  2  2    93
```

`LIKE 'prefix%'` prunes; `LIKE '%fragment%'` does not, and reads the whole
`name_norm` column.

## Columns

| column | type | meaning | tier |
|---|---|---|---|
| `name` | VARCHAR | The unit's name exactly as geoBoundaries publishes it. **Display this.** | attested |
| `name_norm` | VARCHAR | Folded form, and the sort key. **Search this.** | derived |
| `level` | TINYINT | 0, 1 or 2: which boundary collection holds the geometry | derived |
| `shape_type` | VARCHAR | `ADM0`, `ADM1`, `ADM2` or `DISP`, from the boundary row | attested |
| `country` | VARCHAR | The boundary row's `shapeGroup`: ISO 3166-1 alpha-3, or `111`-`129` / `ESH` | attested + derived |
| `country_name` | VARCHAR | The ADM0 `shapeName` for `country`. **NULL for the 20 disputed areas** | derived |
| `shape_id` | VARCHAR | The boundary row's `shapeID`. **NULL for every level-0 row** | attested + derived |
| `area_km2` | DOUBLE | The unit's geodesic area, copied from its boundary row | derived |
| `name_dupes` | INTEGER | How many rows in this index share this `name_norm` | derived |
| `bbox` | STRUCT | xmin, ymin, xmax, ymax as **FLOAT32**, rounded outward | derived |
| `geometry` | BLOB (WKB) | Point inside the unit, CRS84. Not the unit's shape | derived |

### How `name_norm` is built

NFKD decomposition, combining marks (Unicode category `Mn`) dropped, recomposed
NFC, Unicode case folding, strip. So `Zürich` normalizes to `zurich` and
`Malmö` to `malmo` **[derived]**. Scripts with no Latin decomposition, such as
Han and Cyrillic, are lowercased and otherwise unchanged, so `鹿港鎮` is
findable only by the same script.

Before normalizing, 38 rows whose upstream text is double-encoded UTF-8 are
repaired: the string is encoded to Latin-1 and decoded as UTF-8, applied only
when that round trip succeeds, changes the string, and the string holds one of
the mojibake lead sequences. All 38 were checked by hand — 16 Chilean regions,
7 Portuguese districts, 10 New Zealand names with macrons, 4 Peruvian
provinces, 2 Seychelles districts — with no false positive. The rule is in
[`tools/build_names.py`](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_names.py).

**The repair touches `name_norm` only.** `name` stays byte-for-byte as
published, because this is a mirror. So for those 38 rows the searchable form
and the displayable form differ, and an interface that shows `name` will show
the mojibake:

```sql
SELECT name, name_norm FROM 'names/cgaz_names.parquet'
WHERE name_norm LIKE 'region de valparaiso%';
```
```
RegiÃ³n de ValparaÃ­so   region de valparaiso
```

## Joining back to geometry

**The join key depends on the level.** `shape_id` is NULL for all 218 level-0
rows, because CGAZ ADM0 publishes no `shapeID` **[derived]**. A single join on
`shape_id` silently drops every country and every disputed area.

Levels 1 and 2, on `shape_id`:

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

Level 0, on `country`:

```sql
SELECT n.name, b.shapeType, round(b.area_km2) AS area_km2,
       b.adm1_units, b.adm2_units
FROM 'names/cgaz_names.parquet' n
JOIN 'adm0/cgaz_adm0.parquet' b ON n.country = b.shapeGroup
WHERE n.level = 0 AND n.name_norm IN ('kenya', 'western sahara');
```
```
Western Sahara  DISP  269141   1    1
Kenya           ADM0  586084  47  290
```

The level-aware form, which is what a client should ship:

```sql
WITH hit AS (
  SELECT * FROM 'names/cgaz_names.parquet' WHERE name_norm LIKE 'kisumu%'
)
SELECT h.name, h.level, b.shapeType, b.geometry
FROM hit h JOIN 'adm2/cgaz_adm2.parquet' b ON h.shape_id = b.shapeID
WHERE h.level = 2
UNION ALL
SELECT h.name, h.level, b.shapeType, b.geometry
FROM hit h JOIN 'adm1/cgaz_adm1.parquet' b ON h.shape_id = b.shapeID
WHERE h.level = 1
UNION ALL
SELECT h.name, h.level, b.shapeType, b.geometry
FROM hit h JOIN 'adm0/cgaz_adm0.parquet' b ON h.country = b.shapeGroup
WHERE h.level = 0;
```

In a browser, do not join at all: take `shape_id` and `level` from the hit,
then range-read the one row group of the right boundary file that the `bbox`
covering column points at. That is why the boundary files have small row
groups.

### Which boundary file to range-read

**Draw from the display file, analyse from the full-resolution one.**

| what you are doing | read |
|---|---|
| Draw the unit's outline on a map, now | `adm0/cgaz_adm0_display.parquet`, `adm1/cgaz_adm1_display.parquet` |
| Filter *another* dataset to this unit | the same display file |
| Clip, measure, export, or any analysis | `adm{N}/cgaz_adm{N}.parquet` |
| Second-level units, anything | `adm2/cgaz_adm2.parquet` — there is no ADM2 display file, because its median unit is 82 coordinates and nothing there was slow |

The display files hold **the same rows in the same order with the same row
group boundaries** as the full-resolution files, so the row index and the row
group number you got from the full-resolution plan work unchanged against
either. Row *i* is the same unit in both.

Why it matters at ADM0: Canada is **528,021 coordinates** at full resolution
and **68,973** in the display file; the United Kingdom is 61,752 against 6,815
**[derived]**. CGAZ does not simplify ADM0 at all, so decoding a country
outline from the full-resolution file to draw one highlight is what makes a
browser tab stop responding.

**The display geometry is buffered outward on purpose**, by the same distance
it was simplified by, so it contains the true boundary rather than cutting
corners inside it. Measured: every feature retains at least 99.87% of its
original area, and no feature falls below 99% **[derived]**. That bias is what
makes it safe as a spatial filter — you over-fetch a little rather than
silently dropping features along the edge — and it is also why neighbouring
units overlap in the margin and why you must not measure area from it. The
full rule, and the latitude caveat on a buffer measured in degrees, is in the
[catalog agent guide](../AGENTS.md).

## Quirks that produce silently wrong answers

**A name is not an identifier.** 8,140 rows share their `name_norm` with at
least one other unit, and 878 of those sit in a name shared by ten or more
units **[derived]**. Use `name_dupes` to decide when to disambiguate, and
`country_name` plus `level` to do it:

```sql
SELECT name, max(name_dupes) AS units FROM 'names/cgaz_names.parquet'
GROUP BY 1 ORDER BY 2 DESC LIMIT 6;
```
```
Washington  32
Jefferson   26
Franklin    26
Lincoln     25
Jackson     24
Unión       22
```

`Unión` shows the folding at work: it shares a `name_norm` with every `Union`.

**Accent folding is lossy on purpose.** It makes accent-insensitive search
work and it inflates `name_dupes` for pairs like `Unión`/`Union`. It does not
transliterate.

**`country_name` is NULL for the 20 disputed areas.** They have no ADM0 parent
to join to, and their `country` is a geoBoundaries code, not an ISO code
**[derived]**.

**There are no parent names.** No province or region field, because CGAZ
publishes no key linking a second-level unit to the first-level unit containing
it. An autocomplete can offer "Springfield, United States" but not
"Springfield, Illinois, United States" without a spatial join.

**The `bbox` is FLOAT32, approximate by about a metre, and rounded outward.**
It always contains the unit, never less. Verified against the ADM2 collection:
0 of 48,978 joined rows have a bbox narrower than their true extent
**[derived]**. The boundary collections carry FLOAT64 bboxes if you need exact
ones.

**`area_km2` at levels 1 and 2 is measured on simplified geometry.** It is a
usable relevance weight, not an official figure.

**The PMTiles archive produces no legend in the data browser.** The browser
derives a legend only from a `fill` layer with a `match` or `step`
`fill-color`, and this collection's geometry is points, so its three styles use
`circle-color` and carry their meaning in the style name instead. See
[portolanStyles.js](https://github.com/portolan-sdi/portolan-browser/blob/main/src/utils/portolanStyles.js).

## Related collections

[`adm0`](../adm0/collection.json), [`adm1`](../adm1/collection.json) and
[`adm2`](../adm2/collection.json) hold the geometry this index points at. This
collection is derived from those three and from nothing else, so it cannot
disagree with them.

## Structure

Assets and structural links resolve relative to the object that carries them.
