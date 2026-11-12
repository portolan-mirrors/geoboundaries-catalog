# CGAZ Name Search Index

A search sidecar for the three boundary collections in this catalog: one row
per named administrative unit across all three CGAZ levels, 52,398 rows in
3.6 MB, sorted by a folded form of the name.

It exists so that a **static client with no server** can turn a typed name into
a `shapeID`, an extent and a point — the lookup half of a browser geocoder.

This is a **mirror**, derived from geoBoundaries data.
[geoBoundaries](https://www.geoboundaries.org/) is the producer and the
authoritative source.

| | |
|---|---|
| Rows | 52,398 (218 at level 0, 3,202 at level 1, 48,978 at level 2) |
| GeoParquet | 3.6 MB, 35 row groups of 1,536 rows, zstd, page index |
| Row group | ~101 KiB |
| Footer + page index | 86,596 bytes |
| PMTiles | 12 MB, zoom 0-8 |
| CRS | CRS84 (EPSG:4326) |

**The geometry column is one point per unit**, placed inside the unit by
`ST_PointOnSurface`. It is a marker, not the unit's shape. The shape lives in
the [`adm0`](../adm0/collection.json), [`adm1`](../adm1/collection.json) or
[`adm2`](../adm2/collection.json) collection.

## Two ways to use it

**Load it whole.** 3.6 MB, and the seven columns a search needs read in about
120 ms in Node; all eleven in about 250 ms. This is the intended path. Browser
clients read it with [hyparquet](https://github.com/hyparam/hyparquet) plus
[hyparquet-compressors](https://github.com/hyparam/hyparquet-compressors),
which is required because every column chunk is zstd.

**Or range-request it.** Because the file is sorted, row group statistics on
`name_norm` are tight, non-overlapping alphabetical ranges. Measured over all
676 two-letter prefixes, a prefix touches a minimum of one, a median of one and
a maximum of three row groups — so a prefix lookup is one or two reads of
~101 KiB without downloading the file. The footer plus page index is 86,596
bytes, inside hyparquet's 512 KiB default prefetch, so one request plans the
rest.

Both paths, with runnable code and the join back to geometry, are in
[AGENTS.md](AGENTS.md).

## What each row carries

`name` as geoBoundaries publishes it, for display. `name_norm`, the folded form
to search: lowercased with Unicode case folding and with accents stripped, so
"zurich" finds "Zürich". `level` and `shape_type`, saying which boundary
collection holds the geometry. `country` and `country_name`, so an autocomplete
can show "Zürich, Switzerland" without a second fetch. `shape_id`, the join key.
`area_km2`, a usable relevance weight. `name_dupes`, how many units share the
name. `bbox`, the extent to fly a map to. And the point.

> **Not a byte-for-byte mirror.** This catalog repairs faults in the upstream
> release and adds products geoBoundaries does not publish. Every deviation,
> with how to reproduce it and how to get the vanilla behaviour, is in
> [changes-from-upstream.md](../changes-from-upstream.md).

## Known issues

- **The join key depends on the level.** `shape_id` is NULL for all 218 level-0
  rows, because CGAZ ADM0 publishes no `shapeID`. Join level 0 on
  `country = shapeGroup` instead. A single join on `shape_id` silently drops
  every country and every disputed area.
- **37 unnamed ADM2 units are missing by design** — 24 in Japan, 12 in
  Turkmenistan, 1 in China. They exist in the `adm2` collection. This index is
  not a complete list of second-level units.
- **A name is not an identifier.** 8,140 rows share their folded name with at
  least one other unit; 878 sit in a name shared by ten or more. 32 units fold
  to "washington". Use `name_dupes` to decide when to disambiguate.
- **38 names are repaired rather than mirrored.** `name` carries the repaired
  text, for example `Región de Valparaíso` where geoBoundaries publishes
  `RegiÃ³n de ValparaÃ­so`, so display and search agree and no client has to
  repeat the repair. The upstream bytes are preserved in the before-and-after
  table in [changes-from-upstream.md](../changes-from-upstream.md).
- **`country_name` is NULL for the 20 disputed areas.** They have no country to
  join to, and their `country` is a geoBoundaries code, not an ISO code.
- **No parent names.** CGAZ publishes no key linking a second-level unit to the
  first-level unit containing it, so there is no province or region field. An
  autocomplete can offer "Springfield, United States" but not "Springfield,
  Illinois, United States" without a spatial join.
- **Accent folding is lossy on purpose.** "Unión" and "Union" collide, which is
  what makes accent-insensitive search work and also inflates `name_dupes` for
  such pairs. It does not transliterate: a Han or Arabic name is findable only
  by the same script.
- **The bbox is float32**, rounded outward so it always contains the unit, and
  approximate by about a metre. The boundary collections carry float64 bboxes.
- **Prefix search is cheap; substring search is not.** `LIKE 'prefix%'` prunes
  row groups. `LIKE '%fragment%'` reads the whole `name_norm` column.

## Styles

Three. **None of them produces a legend in the data browser**, because the
browser derives a legend only from a `fill` layer and this collection's
geometry is points; each style carries its meaning in its name instead.

| style | shows | classes |
|---|---|---|
| Indexed names by administrative level (default) | `level` | 218 / 3,202 / 48,978 |
| How many units share this name | `name_dupes` | 44,258 / 5,583 / 1,679 / 878 |
| Area of the named unit | `area_km2` | 2,419 / 9,389 / 19,648 / 17,182 / 3,760 |

## License

**CC-BY-4.0.** Attribution is required. In written work, cite:

> Runfola, D. et al. (2020) geoBoundaries: A global database of political
> administrative boundaries. PLoS ONE 15(4): e0231866.
> [https://doi.org/10.1371/journal.pone.0231866](https://doi.org/10.1371/journal.pone.0231866)

On the web, show "geoBoundaries" linked to
[www.geoboundaries.org](https://www.geoboundaries.org/) somewhere prominent on
the page that uses the boundaries.

## Provenance

Built by
[tools/build_names.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_names.py)
from the three boundary collections in this catalog, not from the upstream
GeoPackages, so the index and the geometry it points at cannot disagree.
Upstream release: commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20, extracted 2026-11-12. The normalization rule, the mojibake
repair rule and the row selection rule are in that script and in
`.portolan/metadata.yaml` in the
[repository](https://github.com/portolan-mirrors/geoboundaries-catalog).

## Access

```sql
INSTALL httpfs; LOAD httpfs;

SELECT name, country_name, level, name_dupes, round(area_km2) AS area_km2
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/names/cgaz_names.parquet'
WHERE name_norm LIKE 'zurich%'
ORDER BY level, area_km2 DESC;
```
